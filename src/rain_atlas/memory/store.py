"""Local-first persistence for the scientific memory engine.

Layout under the store root::

    memories.json   committed snapshot: records, contradictions, sequence and
                    the number of committed history events (the commit point)
    history.jsonl   append-only change history, one event per line
    memories.lock   OS advisory writer lock

A write transaction appends its new events to ``history.jsonl`` (``fsync``),
then atomically replaces ``memories.json``. The snapshot is the single commit
point: events past its recorded count are an uncommitted tail from an
interrupted writer, ignored on load and discarded by the next commit. A
crashed writer therefore leaves either the old or the new state, never a mix,
and its OS lock is released by the operating system.

Each transaction reloads committed state under the lock (so it never
overwrites another writer), writes the snapshot once (not once per change)
and appends only the history it produced. Readers reload when the snapshot
on disk changed, so instances in other processes observe committed writes.

Stores written by the first layout (``memories.json`` as a bare list plus
``contradictions.json`` and ``state.json``) load transparently and are
migrated on their next commit.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Iterator

from ..fileio import append_durably, atomic_write, exclusive_lock
from .models import Contradiction, MemoryEvent, MemoryRecord


class MemoryStoreError(RuntimeError):
    pass


def _event_line(event: MemoryEvent) -> bytes:
    return json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


class MemoryStore:
    """Directory-backed store with a single atomic commit point per transaction."""

    STATE_VERSION = 2
    SNAPSHOT = "memories.json"
    HISTORY = "history.jsonl"
    LOCK = "memories.lock"
    LEGACY_FILES = ("contradictions.json", "state.json")

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else None
        self._records: dict[str, MemoryRecord] = {}
        self._contradictions: list[Contradiction] = []
        self._sequence = 0
        # History: the committed prefix of history.jsonl (parsed lazily -- only
        # history queries need it) plus events not yet committed.
        self._committed: list[MemoryEvent] | None = []
        self._committed_count = 0
        self._pending: list[MemoryEvent] = []
        self._history_clean = True  # False: history has an uncommitted or legacy tail
        self._legacy = False
        self._stamp: tuple[int, int] | None = None  # (mtime_ns, size) of the loaded snapshot
        self._depth = 0  # transaction nesting depth
        if self.root is not None:
            self._load()

    # -- persistence ---------------------------------------------------------

    def _path(self, name: str) -> Path:
        assert self.root is not None
        return self.root / name

    def _snapshot_stamp(self) -> tuple[int, int] | None:
        try:
            info = self._path(self.SNAPSHOT).stat()
        except FileNotFoundError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def _reset(self) -> None:
        self._records = {}
        self._contradictions = []
        self._sequence = 0
        self._committed = []
        self._committed_count = 0
        self._pending = []
        self._history_clean = True
        self._legacy = False

    def _load(self) -> None:
        self._reset()
        stamp = self._snapshot_stamp()
        self._stamp = stamp
        if stamp is None:
            return
        history_path = self._path(self.HISTORY)
        try:
            payload = json.loads(self._path(self.SNAPSHOT).read_text(encoding="utf-8"))
            history = history_path.read_bytes() if history_path.exists() else b""
            if isinstance(payload, list):  # first layout: migrate on the next commit
                self._legacy = True
                records = payload
                contradictions = json.loads(self._path("contradictions.json").read_text(encoding="utf-8"))
                self._sequence = int(
                    json.loads(self._path("state.json").read_text(encoding="utf-8"))["sequence"]
                )
                self._committed = [
                    MemoryEvent.from_dict(json.loads(line)) for line in history.splitlines() if line.strip()
                ]
                self._committed_count = len(self._committed)
                self._history_clean = False
            else:
                if payload.get("version") != self.STATE_VERSION:
                    raise ValueError(f"unsupported memory store version {payload.get('version')!r}")
                records = payload["records"]
                contradictions = payload["contradictions"]
                self._sequence = int(payload["sequence"])
                count = int(payload["events"])
                complete_lines = history.count(b"\n")
                if complete_lines < count:
                    raise ValueError(f"history has {complete_lines} events but the snapshot commits {count}")
                self._committed = None  # parsed on first history query
                self._committed_count = count
                self._history_clean = complete_lines == count and (not history or history.endswith(b"\n"))
            self._records = {
                record.id: record for record in (MemoryRecord.from_dict(item) for item in records)
            }
            self._contradictions = [Contradiction.from_dict(item) for item in contradictions]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise MemoryStoreError(f"memory store at {self.root} is unreadable: {exc}") from exc

    def _committed_events(self) -> list[MemoryEvent]:
        if self._committed is None:
            try:
                lines = self._path(self.HISTORY).read_bytes().splitlines()[: self._committed_count]
                events = [MemoryEvent.from_dict(json.loads(line)) for line in lines]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise MemoryStoreError(f"memory history at {self.root} is unreadable: {exc}") from exc
            if len(events) != self._committed_count:
                raise MemoryStoreError(f"memory history at {self.root} lost committed events")
            self._committed = events
        return self._committed

    def refresh(self) -> None:
        """Reload committed state if another writer changed it (no-op mid-transaction)."""

        if self.root is not None and self._depth == 0 and self._snapshot_stamp() != self._stamp:
            self._load()

    def flush(self) -> None:
        """Persist current state.

        Inside a transaction this is deferred to the transaction's single
        commit; outside one it commits immediately under the writer lock.
        """

        if self.root is None or self._depth:
            return
        with self._locked():
            self._commit()

    def _locked(self):
        assert self.root is not None
        return exclusive_lock(self._path(self.LOCK), error=MemoryStoreError)

    def _commit(self) -> None:
        assert self.root is not None
        self.root.mkdir(parents=True, exist_ok=True)
        history_path = self._path(self.HISTORY)
        if self._history_clean:
            if self._pending:
                append_durably(history_path, b"".join(_event_line(event) for event in self._pending))
        else:  # discard an uncommitted tail (or migrate) by rewriting the committed history
            events = [*self._committed_events(), *self._pending]
            atomic_write(history_path, b"".join(_event_line(event) for event in events))
        total = self._committed_count + len(self._pending)
        snapshot = {
            "version": self.STATE_VERSION,
            "sequence": self._sequence,
            "events": total,
            "records": [record.to_dict() for record in self.iter_records()],
            "contradictions": [c.to_dict() for c in self._contradictions],
        }
        atomic_write(
            self._path(self.SNAPSHOT),
            json.dumps(
                snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8"),
        )
        if self._legacy:
            for name in self.LEGACY_FILES:
                self._path(name).unlink(missing_ok=True)
            self._legacy = False
        if self._committed is not None:
            self._committed.extend(self._pending)
        self._committed_count = total
        self._pending = []
        self._history_clean = True
        self._stamp = self._snapshot_stamp()

    @contextlib.contextmanager
    def transaction(self, timeout_s: float = 30.0) -> Iterator[None]:
        """Serialize a full read-modify-write across instances and processes.

        Takes the writer lock, reloads committed state (another writer may
        have committed since this instance last read), and commits once on
        success. On an exception the
        in-memory state is rolled back to the last committed state and
        nothing is written. Nested transactions join the outermost one.
        """

        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        if self.root is None:
            self._depth = 1
            try:
                yield
            finally:
                self._depth = 0
            return
        self.root.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(self._path(self.LOCK), timeout_s=timeout_s, error=MemoryStoreError):
            self._load()
            self._depth = 1
            try:
                yield
            except BaseException:
                self._depth = 0
                self._load()
                raise
            self._depth = 0
            self._commit()

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
        self._pending.append(event)

    def event_count(self) -> int:
        return self._committed_count + len(self._pending)

    def history(self, memory_id: str) -> list[MemoryEvent]:
        return [event for event in self.all_events() if event.memory_id == memory_id]

    def all_events(self) -> list[MemoryEvent]:
        return [*self._committed_events(), *self._pending]

    # -- contradictions ------------------------------------------------------

    def add_contradiction(self, contradiction: Contradiction) -> None:
        self._contradictions.append(contradiction)

    def contradictions(self) -> list[Contradiction]:
        return list(self._contradictions)

    def contradictions_for(self, memory_id: str) -> list[Contradiction]:
        return [c for c in self._contradictions if memory_id in (c.new_memory_id, c.old_memory_id)]
