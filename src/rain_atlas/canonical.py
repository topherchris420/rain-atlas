"""Canonical JSON and content hashing.

Every object the ledger stores is hashed over its canonical form, so the same
logical content always has the same address:

* UTF-8, keys sorted, no insignificant whitespace;
* non-finite floats are encoded as ``{"$float": "nan" | "inf" | "-inf"}``
  because JSON has no representation for them;
* numpy scalars and arrays are converted to plain Python values.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

HASH_PREFIX = "sha256:"


def to_jsonable(value: Any) -> Any:
    """Convert numpy values, tuples and paths into canonical-JSON-safe values."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value):
            return {"$float": "nan"}
        if math.isinf(value):
            return {"$float": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys must be strings, got {type(key).__name__}")
            out[key] = to_jsonable(item)
        return out
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    # numpy without importing it at module load
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return to_jsonable(tolist())
    item = getattr(value, "item", None)
    if callable(item):
        return to_jsonable(item())
    raise TypeError(f"Value of type {type(value).__name__} is not JSON-serialisable")


def from_jsonable(value: Any) -> Any:
    """Inverse of the non-finite float encoding (other values pass through)."""

    if isinstance(value, dict):
        if set(value) == {"$float"}:
            return {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}[value["$float"]]
        return {key: from_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_jsonable(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 encoding of *value*."""

    return json.dumps(
        to_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return HASH_PREFIX + digest.hexdigest()


def tree_files(
    root: Path, *, exclude_dirs: frozenset[str] = frozenset({"__pycache__"})
) -> list[tuple[str, Path]]:
    """Regular files under *root* as ``(relative POSIX path, path)`` in canonical order.

    The order is the relative path components compared as plain strings
    (code-point order), the same on every operating system. Sorting ``Path``
    objects is not portable: Windows compares them case-insensitively, so a
    tree containing ``SKILL.md`` and ``run.py`` hashed differently on Windows
    and POSIX. Symlinks are refused rather than followed, so the listing
    always describes bytes inside *root*.
    """

    root = Path(root)
    found: list[tuple[tuple[str, ...], Path]] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in exclude_dirs for part in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed inside a skill: {rel.as_posix()}")
        if path.is_file():
            found.append((rel.parts, path))
    found.sort(key=lambda item: item[0])
    return [("/".join(parts), path) for parts, path in found]


def tree_hash(root: Path, *, exclude_dirs: frozenset[str] = frozenset({"__pycache__"})) -> str:
    """Hash a directory: canonically ordered (relative POSIX path, file hash) pairs.

    Bytes are hashed exactly as stored; line endings are not normalized, so
    a checkout must contain the committed bytes (``.gitattributes`` pins LF).
    """

    return sha256_json(
        [[name, sha256_file(path)] for name, path in tree_files(root, exclude_dirs=exclude_dirs)]
    )
