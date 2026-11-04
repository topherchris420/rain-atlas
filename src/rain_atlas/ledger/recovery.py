"""Explicit recovery of a torn final append into a new ledger, never in place."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..canonical import sha256_bytes
from .store import Ledger, LedgerError


def recover(source: Path, destination: Path) -> Ledger:
    """Preserve complete records and record the lost suffix digest in a new store.

    Only an unterminated final JSON line is recoverable. Modified complete
    records and missing/corrupt artifacts are refused. Sealed vault material
    remains solely in the original; recovery does not unblind or resume a study.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source in destination.parents or destination in source.parents:
        raise ValueError("recovery requires a fresh destination outside the source tree")
    raw = (source / "log.jsonl").read_bytes()
    if raw.endswith(b"\n"):
        raise ValueError("no torn final append to recover")
    boundary = raw.rfind(b"\n") + 1
    if boundary == 0:
        raise ValueError("no complete prefix to recover")
    prefix, tail = raw[:boundary], raw[boundary:]
    # Valid but unterminated JSON might be a completed record whose newline
    # was lost. Refuse to silently discard it.
    try:
        json.loads(tail)
    except (ValueError, UnicodeError):
        pass
    else:
        raise ValueError("final JSON is complete; manual inspection required")
    for file in (source / "objects").rglob("*"):
        if file.is_symlink():
            raise LedgerError("source objects contain a symlink")
    recovered = Ledger(destination)
    shutil.copytree(source / "objects", destination / "objects")
    recovered.log_path.write_bytes(prefix)
    problems = recovered.verify()
    if problems:
        raise LedgerError(
            "recovery prefix is invalid; destination retained for inspection: " + "; ".join(problems)
        )
    recovered.append(
        "recovery",
        {
            "source_log_hash": sha256_bytes(raw),
            "discarded_tail_hash": sha256_bytes(tail),
            "recovered_records": len(list(recovered.entries())),
            "reason": "torn final append; original preserved; vault not copied",
            "author": {"role": "operator-recovery", "generation": "human"},
        },
    )
    return recovered
