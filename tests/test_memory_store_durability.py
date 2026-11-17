"""Durability, crash-consistency and concurrency of the memory store.

These are the failure modes a long-lived local store meets in practice: a
writer killed mid-commit, a lock left behind by a crashed process, an
exception inside a transaction, another process committing between reads,
and stores written by the first on-disk layout.
"""

from __future__ import annotations

import json
import multiprocessing
import time
from pathlib import Path

import pytest

from rain_atlas.canonical import canonical_bytes
from rain_atlas.memory import MemoryStore, ScientificMemory
from rain_atlas.memory.store import MemoryStoreError

CLOCK = lambda: 1760000000.0  # noqa: E731 - deterministic test clock


def _add(memory: ScientificMemory, text: str) -> str:
    return memory.add(text, agent_id="lab", infer=False)["results"][0]["id"]


def _contents(memory: ScientificMemory) -> set[str]:
    return {item["memory"] for item in memory.get_all(filters={"agent_id": "lab"})["results"]}


class TestCrashConsistency:
    def test_uncommitted_history_tail_is_ignored_then_discarded(self, tmp_path: Path):
        root = tmp_path / "m"
        memory = ScientificMemory(root, clock=CLOCK)
        first = _add(memory, "committed finding")
        # A writer crashed after appending history but before its snapshot commit,
        # leaving a complete event and a torn half-line.
        with (root / "history.jsonl").open("ab") as handle:
            handle.write(b'{"event":"ADD","memory_id":"ghost","new_value":"x","prev_value":null}\n{"eve')
        reopened = ScientificMemory(root, clock=CLOCK)
        assert _contents(reopened) == {"committed finding"}
        assert reopened.statistics()["events"] == 1
        assert [e["event"] for e in reopened.history(first)] == ["ADD"]
        # The next commit rewrites history to the committed prefix plus its own event.
        _add(reopened, "second finding")
        lines = (root / "history.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert all(json.loads(line)["memory_id"] != "ghost" for line in lines)

    def test_snapshot_claiming_missing_events_is_reported(self, tmp_path: Path):
        root = tmp_path / "m"
        _add(ScientificMemory(root, clock=CLOCK), "finding")
        (root / "history.jsonl").write_bytes(b"")
        with pytest.raises(MemoryStoreError, match="commits 1"):
            ScientificMemory(root, clock=CLOCK)

    def test_exception_inside_transaction_rolls_back(self, tmp_path: Path):
        root = tmp_path / "m"
        memory = ScientificMemory(root, clock=CLOCK)
        _add(memory, "kept")
        with pytest.raises(RuntimeError, match="boom"):
            with memory.store.transaction():
                memory._add_raw("discarded", {"agent_id": "lab"}, None)
                raise RuntimeError("boom")
        assert _contents(memory) == {"kept"}
        assert _contents(ScientificMemory(root, clock=CLOCK)) == {"kept"}

    def test_lock_left_by_a_dead_process_does_not_block(self, tmp_path: Path):
        root = tmp_path / "m"
        root.mkdir()
        # Marker files from a crashed writer (either layout) must not deadlock writers.
        (root / ".lock").write_text("12345")
        (root / "memories.lock").write_text("12345")
        memory = ScientificMemory(root, clock=CLOCK)
        started = time.monotonic()
        _add(memory, "after crash")
        assert time.monotonic() - started < 5.0
        assert _contents(memory) == {"after crash"}


class TestVisibility:
    def test_reader_sees_commits_from_another_instance(self, tmp_path: Path):
        root = tmp_path / "m"
        reader = ScientificMemory(root, clock=CLOCK)
        writer = ScientificMemory(root, clock=CLOCK)
        assert _contents(reader) == set()
        _add(writer, "from the other instance")
        assert _contents(reader) == {"from the other instance"}

    def test_writer_never_overwrites_a_concurrent_commit(self, tmp_path: Path):
        root = tmp_path / "m"
        a = ScientificMemory(root, clock=CLOCK)
        b = ScientificMemory(root, clock=CLOCK)
        for index in range(20):
            _add(a if index % 2 else b, f"finding {index}")
        assert _contents(ScientificMemory(root, clock=CLOCK)) == {f"finding {i}" for i in range(20)}


def _worker(root: str, worker: int, count: int) -> None:
    memory = ScientificMemory(Path(root), clock=CLOCK)
    for index in range(count):
        memory.add(f"worker {worker} finding {index}", agent_id="lab", infer=False)


class TestProcesses:
    def test_concurrent_processes_lose_no_writes(self, tmp_path: Path):
        root = tmp_path / "m"
        context = multiprocessing.get_context("spawn")
        workers = [context.Process(target=_worker, args=(str(root), w, 15)) for w in range(3)]
        for process in workers:
            process.start()
        for process in workers:
            process.join(timeout=120)
            assert process.exitcode == 0
        memory = ScientificMemory(root, clock=CLOCK)
        assert len(_contents(memory)) == 45
        assert memory.statistics()["events"] == 45


class TestMigration:
    def test_first_layout_loads_and_migrates(self, tmp_path: Path):
        root = tmp_path / "m"
        root.mkdir()
        record = {
            "id": "legacy-1",
            "content": "legacy finding",
            "scope": {"agent_id": "lab"},
            "kind": "fact",
            "metadata": {},
            "created_at": "t",
            "updated_at": "t",
            "hash": "",
            "status": "active",
            "supersedes": None,
            "superseded_by": None,
            "evidence": [],
        }
        (root / "memories.json").write_bytes(canonical_bytes([record]))
        (root / "contradictions.json").write_bytes(canonical_bytes([]))
        (root / "state.json").write_bytes(canonical_bytes({"sequence": 1, "version": 1}))
        event = {
            "actor": "memory-engine",
            "event": "ADD",
            "memory_id": "legacy-1",
            "new_value": "legacy finding",
            "prev_value": None,
            "reason": "",
            "timestamp": "t",
        }
        (root / "history.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

        memory = ScientificMemory(root, clock=CLOCK)
        assert _contents(memory) == {"legacy finding"}
        _add(memory, "new finding")
        assert not (root / "state.json").exists()
        assert not (root / "contradictions.json").exists()
        reopened = ScientificMemory(root, clock=CLOCK)
        assert _contents(reopened) == {"legacy finding", "new finding"}
        assert [e["event"] for e in reopened.history("legacy-1")] == ["ADD"]
        assert reopened.statistics()["events"] == 2


class TestScale:
    def test_writes_do_not_rewrite_history(self, tmp_path: Path):
        root = tmp_path / "m"
        memory = ScientificMemory(root, clock=CLOCK)
        _add(memory, "first")
        before = (root / "history.jsonl").stat().st_ino
        for index in range(5):
            _add(memory, f"next {index}")
        # Append-only: the same file grew; it was not replaced.
        assert (root / "history.jsonl").stat().st_ino == before
        assert len((root / "history.jsonl").read_text(encoding="utf-8").splitlines()) == 6

    def test_in_memory_store_has_no_files(self):
        store = MemoryStore(None)
        memory = ScientificMemory(None, clock=CLOCK)
        _add(memory, "ephemeral")
        assert store.root is None and _contents(memory) == {"ephemeral"}
