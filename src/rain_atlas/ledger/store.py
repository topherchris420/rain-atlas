"""Content-addressed, append-only, hash-chained evidence store.

Layout under the ledger root::

    objects/sha256/<2 hex>/<62 hex>     immutable objects (JSON or bytes)
    log.jsonl                           one line per appended record
    vault/<commitment hex>.json         sealed values (never in objects/)
    log.lock                            writer lock

Each log line is ``{"seq", "at", "kind", "object", "prev", "hash"}``. ``hash``
is the SHA-256 of the canonical line without ``hash``; ``prev`` is the previous
line's ``hash``. :meth:`Ledger.verify` recomputes all of it. A digest is not a
signature: verification proves the history is internally consistent, not who
wrote it.
"""

from __future__ import annotations

import json
import os
import secrets
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..canonical import HASH_PREFIX, canonical_bytes, sha256_bytes, sha256_json

GENESIS = HASH_PREFIX + "0" * 64


class LedgerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    seq: int
    at: str
    kind: str
    object: str
    prev: str
    hash: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "at": self.at, "kind": self.kind, "object": self.object, "prev": self.prev, "hash": self.hash}


def _hex(ref: str) -> str:
    if not isinstance(ref, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", ref):
        raise LedgerError(f"not a sha256 reference: {ref!r}")
    return ref[len(HASH_PREFIX) :]


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    with tmp.open("xb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


@contextmanager
def _locked(path: Path, timeout_s: float = 30.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+b")
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt  # noqa: PLC0415

                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl  # noqa: PLC0415

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise LedgerError(f"could not lock {path} within {timeout_s}s") from None
                time.sleep(0.05)
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt  # noqa: PLC0415

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


class Ledger:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.objects = self.root / "objects" / "sha256"
        self.log_path = self.root / "log.jsonl"
        self.vault = self.root / "vault"
        self.lock_path = self.root / "log.lock"
        self.root.mkdir(parents=True, exist_ok=True)

    # objects --------------------------------------------------------------
    def _object_path(self, ref: str) -> Path:
        hex_ = _hex(ref)
        return self.objects / hex_[:2] / hex_[2:]

    def put_bytes(self, data: bytes) -> str:
        ref = sha256_bytes(data)
        path = self._object_path(ref)
        if path.exists():
            if path.read_bytes() != data:
                raise LedgerError(f"object {ref} exists with different bytes (store corrupted)")
            return ref
        _atomic_write(path, data)
        return ref

    def put_json(self, value: Any) -> str:
        return self.put_bytes(canonical_bytes(value))

    def put_file(self, path: Path) -> str:
        return self.put_bytes(Path(path).read_bytes())

    def get_bytes(self, ref: str) -> bytes:
        path = self._object_path(ref)
        if path.is_symlink():
            raise LedgerError(f"object {ref} is a symlink")
        if not path.exists():
            raise LedgerError(f"object {ref} not found")
        data = path.read_bytes()
        if sha256_bytes(data) != ref:
            raise LedgerError(f"object {ref} fails its hash check")
        return data

    def get_json(self, ref: str) -> Any:
        return json.loads(self.get_bytes(ref).decode("utf-8"))

    def has(self, ref: str) -> bool:
        return self._object_path(ref).exists()

    # log ------------------------------------------------------------------
    def entries(self, kind: str | None = None) -> Iterator[Entry]:
        if not self.log_path.exists():
            return
        with self.log_path.open(encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                if line.strip():
                    try:
                        entry = Entry(**json.loads(line))
                    except (ValueError, TypeError) as exc:
                        raise LedgerError(f"malformed log line {number}; preserve history and recover in a new ledger") from exc
                    if kind is None or entry.kind == kind:
                        yield entry

    def records(self, kind: str | None = None) -> Iterator[tuple[Entry, dict]]:
        for entry in self.entries(kind):
            yield entry, self.get_json(entry.object)

    def _last(self) -> Entry | None:
        last = None
        for last in self.entries():
            pass
        return last

    def append(self, kind: str, record: dict) -> Entry:
        """Store *record* and append it to the chain; returns the new entry."""

        if not kind or not kind.replace("-", "").isalnum():
            raise LedgerError(f"invalid record kind {kind!r}")
        ref = self.put_json(record)
        with _locked(self.lock_path):
            last = self._last()
            body = {
                "seq": 0 if last is None else last.seq + 1,
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "kind": kind,
                "object": ref,
                "prev": GENESIS if last is None else last.hash,
            }
            entry = Entry(**body, hash=sha256_json(body))
            with self.log_path.open("ab") as fh:
                fh.write(canonical_bytes(entry.to_dict()) + b"\n")
                fh.flush()
                os.fsync(fh.fileno())
        return entry

    def find(self, object_ref: str) -> Entry | None:
        for entry in self.entries():
            if entry.object == object_ref:
                return entry
        return None

    # sealing ----------------------------------------------------------------
    def seal(self, label: str, value: Any, *, context: dict | None = None) -> tuple[Entry, str]:
        """Commit to *value* without revealing it; returns (entry, commitment)."""

        salt = secrets.token_hex(32)
        commitment = sha256_bytes(salt.encode("ascii") + canonical_bytes(value))
        _atomic_write(self.vault / f"{_hex(commitment)}.json", canonical_bytes({"salt": salt, "value": value}))
        entry = self.append("seal", {"label": label, "commitment": commitment, "context": context or {}})
        return entry, commitment

    def unseal(self, commitment: str, *, after: list[str] | None = None) -> tuple[Entry, Any]:
        """Publish a sealed value. *after* lists object refs that must precede it."""

        path = self.vault / f"{_hex(commitment)}.json"
        if not path.exists():
            raise LedgerError(f"no vault entry for {commitment}")
        stored = json.loads(path.read_text(encoding="utf-8"))
        if sha256_bytes(stored["salt"].encode("ascii") + canonical_bytes(stored["value"])) != commitment:
            raise LedgerError("vault entry does not match its commitment")
        entry = self.append(
            "unseal",
            {"commitment": commitment, "salt": stored["salt"], "value": stored["value"], "after": after or []},
        )
        return entry, stored["value"]

    # verification -----------------------------------------------------------
    def verify(self) -> list[str]:
        """Recompute the chain, every object hash and the record rules."""

        from .records import record_problems  # noqa: PLC0415

        problems: list[str] = []
        prev = GENESIS
        seq_of: dict[str, int] = {}
        expected_seq = 0
        try:
            entries = list(self.entries())
        except (LedgerError, UnicodeError) as exc:
            return [str(exc)]
        for entry in entries:
            body = entry.to_dict()
            claimed = body.pop("hash")
            if entry.seq != expected_seq:
                problems.append(f"seq {entry.seq}: expected seq {expected_seq}")
            if entry.prev != prev:
                problems.append(f"seq {entry.seq}: prev does not match the previous entry's hash")
            if sha256_json(body) != claimed:
                problems.append(f"seq {entry.seq}: entry hash mismatch (log line edited)")
            try:
                record = self.get_json(entry.object)
            except (LedgerError, ValueError, UnicodeError, OSError) as exc:
                problems.append(f"seq {entry.seq}: {exc}")
                record = None
            if record is not None:
                try:
                    found = record_problems(self, entry, record, seq_of)
                except (ValueError, TypeError, KeyError, AttributeError, OSError, LedgerError) as exc:
                    found = [f"invalid record or dependency: {exc}"]
                problems.extend(f"seq {entry.seq} ({entry.kind}): {p}" for p in found)
            seq_of.setdefault(entry.object, entry.seq)
            prev = claimed
            expected_seq += 1
        return problems
