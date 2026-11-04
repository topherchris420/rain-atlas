"""Disposable, integrity-checked local SQLite search index; never authoritative."""

from __future__ import annotations

import sqlite3

from .store import Ledger, LedgerError

SCHEMA = "atlas.index/v1"


def search(ledger: Ledger, query: str, *, kind: str | None = None, limit: int = 50) -> list[dict]:
    """Search scientific record text; verify source and refresh stale cache first."""
    if not 1 <= limit <= 1000:
        raise ValueError("search limit must be 1..1000")
    problems = ledger.verify()
    if problems:
        raise LedgerError("cannot index broken evidence: " + "; ".join(problems[:3]))
    entries = list(ledger.entries())
    head = entries[-1].hash if entries else "empty"
    path = ledger.root / "index.sqlite"
    if path.is_symlink():
        raise LedgerError("index may not be a symlink")
    with sqlite3.connect(path) as db:
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        if tables and "metadata" not in tables:
            raise LedgerError("refusing to replace an unknown SQLite database")
        if tables and db.execute("select value from metadata where key='schema'").fetchone() != (SCHEMA,):
            raise LedgerError("unknown index schema")
        db.execute("create table if not exists metadata (key text primary key, value text)")
        db.execute(
            "create table if not exists records (id text, seq integer primary key, kind text, experiment text, text text)"
        )
        db.execute("create index if not exists record_kind on records(kind)")
        db.execute("create index if not exists record_experiment on records(experiment)")
        if db.execute("select value from metadata where key='head'").fetchone() != (head,):
            db.execute("delete from records")
            for entry, record in ledger.records():
                # Vault, unsealed values, raw inputs and run logs are not indexed.
                text = " ".join(
                    str(record.get(k, ""))
                    for k in ("title", "question", "statement", "text", "purpose", "method", "verdict")
                )
                db.execute(
                    "insert into records values (?,?,?,?,?)",
                    (entry.object, entry.seq, entry.kind, record.get("experiment"), text),
                )
            db.executemany(
                "insert or replace into metadata values (?,?)", [("schema", SCHEMA), ("head", head)]
            )
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = db.execute(
            "select id,seq,kind,experiment,text from records where text like ? escape '\\' and (? is null or kind=?) order by seq limit ?",
            ("%" + escaped + "%", kind, kind, limit),
        ).fetchall()
    return [dict(zip(("id", "seq", "kind", "experiment", "text"), r)) for r in rows]
