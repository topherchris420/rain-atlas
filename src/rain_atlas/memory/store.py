"""Local-first persistence for the scientific memory engine.

A :class:`MemoryStore` is a directory of canonical JSON documents plus a
JSONL history log. Writes are atomic (temp file + replace). The store is
local-first: no service, no database, no network. Concurrent writers are
serialized with an OS-level lock file, mirroring the ledger's approach.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Iterator

from ..canonical import canonical_bytes
from .models import Contradiction, MemoryEvent, MemoryRecord


class MemoryStoreError(RuntimeError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class MemoryStore:
    """Directory-backed store: ``memories.json``, ``history.jsonl``, ``contradictions.json``."""

    STATE_VERSION = 1

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else None
        self._records: dict[str, MemoryRecord] = {}
        self._events: list[MemoryEvent] = []
        self._contradictions: list[Contradiction] = []
        self._sequence = 0
        if self.root is not None:
            self._load()

    # -- persistence ---------------------------------------------------------

    def _paths(self) -> tuple[Path, Path, Path, Path]:
        assert self.root is not None
        return (
            self.root / "memories.json",
            self.root / "history.jsonl",
            self.root / "contradictions.json",
            self.root / "state.json",
        )

    def _load(self) -> None:
        memories_path, history_path, contradictions_path, state_path = self._paths()
        if not memories_path.exists():
            return
        try:
            payload = json.loads(memories_path.read_text(encoding="utf-8"))
            for item in payload:
                record = MemoryRecord.from_dict(item)
                self._records[record.id] = record
            self._events = [
                MemoryEvent.from_dict(json.loads(line))
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self._contradictions = [
                Contradiction.from_dict(item)
                for item in json.loads(contradictions_path.read_text(encoding="utf-8"))
            ]
            self._sequence = json.loads(state_path.read_text(encoding="utf-8"))["sequence"]
        except (OSError, ValueError, KeyError) as exc:
            raise MemoryStoreError(f"memory store at {self.root} is unreadable: {exc}") from exc

    def flush(self) -> None:
        """Persist current state; a no-op for in-memory stores."""

        if self.root is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        memories_path, history_path, contradictions_path, state_path = self._paths()
        _atomic_write(
            memories_path,
            canonical_bytes([record.to_dict() for record in self.iter_records()]),
        )
        _atomic_write(
            history_path,
            "\n".join(
                json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) for event in self._events
            ).encode("utf-8")
            + (b"\n" if self._events else b""),
        )
        _atomic_write(
            contradictions_path,
            canonical_bytes([c.to_dict() for c in self._contradictions]),
        )
        _atomic_write(
            state_path, canonical_bytes({"sequence": self._sequence, "version": self.STATE_VERSION})
        )

    @contextlib.contextmanager
    def transaction(self, timeout_s: float = 30.0) -> Iterator[None]:
        """Serialize a full read-modify-write across instances and processes.

        Acquires a directory lock file, reloads committed state so changes
        made by other writers are not overwritten, then flushes on success.
        """

        if self.root is None:
            yield
            return
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".lock"
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise MemoryStoreError(f"timed out waiting for lock {lock_path}") from None
                time.sleep(0.01)
        try:
            self._records = {}
            self._events = []
            self._contradictions = []
            self._sequence = 0
            self._load()
            yield
            self.flush()
        finally:
            os.close(fd)
            os.unlink(lock_path)

    # -- records -------------------------------------------------------------

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def put(self, record: MemoryRecord) -> None:
        if record.id in self._records:
            raise MemoryStoreError(f"memory {record.id} already exists")
        self._records[record.id] = record

    def replace(self, record: MemoryRecord) -> None:
        if record.id not in self._records:
            raise MemoryStoreError(f"memory {record.id} does not exist")
        self._records[record.id] = record

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self._records.get(memory_id)

    def iter_records(self) -> Iterator[MemoryRecord]:
        for record in sorted(self._records.values(), key=lambda r: r.id):
            yield record

    def active_records(self) -> list[MemoryRecord]:
        return [record for record in self.iter_records() if record.status == "active"]

    def delete_all(self) -> int:
        count = len(self._records)
        self._records.clear()
        self._contradictions.clear()
        return count

    # -- events --------------------------------------------------------------

    def append_event(self, event: MemoryEvent) -> None:
        self._events.append(event)

    def history(self, memory_id: str) -> list[MemoryEvent]:
        return [event for event in self._events if event.memory_id == memory_id]

    def all_events(self) -> list[MemoryEvent]:
        return list(self._events)

    # -- contradictions ------------------------------------------------------

    def add_contradiction(self, contradiction: Contradiction) -> None:
        self._contradictions.append(contradiction)

    def contradictions(self) -> list[Contradiction]:
        return list(self._contradictions)

    def contradictions_for(self, memory_id: str) -> list[Contradiction]:
        return [c for c in self._contradictions if memory_id in (c.new_memory_id, c.old_memory_id)]
