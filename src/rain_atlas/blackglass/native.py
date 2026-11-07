"""Bounded, hash-bound imports of offline native-code call graph observations.

The snapshot is an *analysis-tool assertion*, not proof of runtime execution.
We do not ingest decompiled source or invoke Ghidra, IDA or the bridge here.
Each export must match an ELF already inventoried in the firmware image.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..canonical import sha256_file
from .model import Component

SCHEMA = "blackglass.native-calls/v1"
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_MAX_FUNCTIONS = 2048
_MAX_CALLS = 8192
_ADDRESS = re.compile(r"0x[0-9a-f]{1,16}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class NativeFunction:
    entry: str
    name: str
    size: int
    calls: tuple[str, ...]


@dataclass(frozen=True)
class NativeSnapshot:
    binary: str
    binary_sha256: str
    snapshot_sha256: str
    tool: str
    functions: tuple[NativeFunction, ...]


def _address(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("native-call address must be a hexadecimal string")
    try:
        canonical = hex(int(value, 16))
    except ValueError as exc:
        raise ValueError(f"invalid native-call address: {value!r}") from exc
    if not _ADDRESS.fullmatch(canonical) or not value.lower().startswith("0x"):
        raise ValueError(f"invalid native-call address: {value!r}")
    return canonical


def _binary_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("native snapshot needs a relative POSIX binary path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise ValueError("native snapshot binary must be a canonical contained path")
    return value


def load_snapshot(path: Path, components: list[Component]) -> NativeSnapshot:
    """Validate an untrusted JSON export against the actually imported ELF bytes.

    Hash equality binds the asserted call graph to the specific executable, but
    does not independently confirm that the disassembler recovered all calls.
    """

    path = Path(path)
    if path.stat().st_size > _MAX_SNAPSHOT_BYTES:
        raise ValueError("native snapshot exceeds the 8 MiB input cap")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid native snapshot JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError(f"native snapshot must have schema {SCHEMA}")
    binary = _binary_path(raw.get("binary"))
    indexed = {c.path: c for c in components if c.kind == "elf"}
    component = indexed.get(binary)
    if component is None:
        raise ValueError(f"native snapshot binary is not an inventoried ELF: {binary}")
    digest = raw.get("sha256")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("native snapshot requires a lowercase sha256:<64 hex> binary digest")
    if component.sha256 != digest:
        raise ValueError(f"native snapshot ELF digest mismatch: {binary}")
    tool = raw.get("tool")
    if tool not in ("ghidra", "ida"):
        raise ValueError("native snapshot tool must be 'ghidra' or 'ida'")
    rows = raw.get("functions")
    if not isinstance(rows, list) or len(rows) > _MAX_FUNCTIONS:
        raise ValueError(f"native snapshot requires at most {_MAX_FUNCTIONS} functions")
    functions: list[NativeFunction] = []
    seen: set[str] = set()
    calls_total = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"native snapshot function {index} must be an object")
        entry = _address(row.get("entry"))
        if entry in seen:
            raise ValueError(f"duplicate native function entry {entry}")
        seen.add(entry)
        name = row.get("name")
        size = row.get("size")
        calls = row.get("calls")
        if not isinstance(name, str) or not name or len(name) > 256 or any(
            ord(char) < 32 for char in name
        ):
            raise ValueError(f"invalid native function name at {entry}")
        if type(size) is not int or not 0 <= size <= 100_000_000:
            raise ValueError(f"invalid native function size at {entry}")
        if not isinstance(calls, list):
            raise ValueError(f"native calls must be a list at {entry}")
        canonical_calls = tuple(sorted({_address(call) for call in calls}, key=lambda x: int(x, 16)))
        calls_total += len(canonical_calls)
        if calls_total > _MAX_CALLS:
            raise ValueError(f"native snapshot exceeds {_MAX_CALLS} call edges")
        functions.append(NativeFunction(entry, name, size, canonical_calls))
    functions.sort(key=lambda item: int(item.entry, 16))
    return NativeSnapshot(binary, digest, sha256_file(path), tool, tuple(functions))


def load_snapshots(paths: list[Path], components: list[Component]) -> list[NativeSnapshot]:
    """Reject conflicting evidence for the same binary; output order is stable."""

    snapshots = [load_snapshot(path, components) for path in paths]
    snapshots.sort(key=lambda s: (s.binary, s.snapshot_sha256))
    seen: set[str] = set()
    for snapshot in snapshots:
        if snapshot.binary in seen:
            raise ValueError(f"multiple native snapshots for {snapshot.binary}; select one per analysis")
        seen.add(snapshot.binary)
    return snapshots
