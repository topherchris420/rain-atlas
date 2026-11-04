"""Deterministic source snapshots; never restore or execute them automatically."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from .canonical import sha256_bytes, sha256_json


def source_snapshot(root: Path) -> tuple[bytes, str]:
    """Exact relative files and tree digest, excluding bytecode and host paths.

    ZIP timestamps and permissions are fixed. Symlinks and oversized trees
    are refused. No archive extraction occurs.
    """
    stream = io.BytesIO()
    entries = []
    size = 0
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(root).rglob("*")):
            rel = path.relative_to(root)
            if "__pycache__" in rel.parts:
                continue
            if path.is_symlink():
                raise ValueError("source snapshots refuse symlinks")
            if not path.is_file():
                continue
            size += path.stat().st_size
            if size > 32 * 1024 * 1024:
                raise ValueError("source snapshot exceeds 32 MiB")
            data = path.read_bytes()
            name = rel.as_posix()
            entries.append([name, sha256_bytes(data)])
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue(), sha256_json(entries)


def engine_root() -> Path:
    return Path(__file__).resolve().parent


def capture(ledger, skill) -> dict:
    engine_bytes, engine_hash = source_snapshot(engine_root())
    skill_bytes, skill_hash = source_snapshot(skill.path)
    if skill_hash != skill.content_hash:
        raise ValueError("skill source changed since selection")
    result = {
        "engine_source_object": ledger.put_bytes(engine_bytes),
        "engine_source_hash": engine_hash,
        "skill_source_object": ledger.put_bytes(skill_bytes),
    }
    lock = engine_root().parents[1] / "uv.lock"
    if lock.is_file():
        result["lockfile_object"] = ledger.put_file(lock)
    return result
