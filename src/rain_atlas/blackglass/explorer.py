"""Native Routine Explorer: load genuine disassembler output into the model.

Reads the ``blackglass.native-reconstruction/v1`` document emitted by the
read-only Ghidra script (``scripts/BlackglassReconstruct.java``) and turns each
routine's derived facts into a :class:`RoutineObservation`. The decompiled
pseudocode itself is held locally and referenced only by digest; this explorer
deals strictly in the non-copyrightable facts (names, addresses, sizes, callees,
string and constant references, control-flow metrics).
"""

from __future__ import annotations

import json
from pathlib import Path

from .routines import ObservedFact, RoutineObservation

SCHEMA = "blackglass.native-reconstruction/v1"
_MAX_DOC_BYTES = 8 * 1024 * 1024


def _routine_to_observation(routine: dict, header: dict) -> RoutineObservation:
    facts: list[ObservedFact] = []
    for callee in routine.get("callees", []):
        facts.append(ObservedFact("call", f"calls {callee}", target=callee))
    for value in routine.get("string_refs", []):
        facts.append(ObservedFact("string-ref", f"references string {value!r}", target=value))
    for const in routine.get("constants", []):
        facts.append(ObservedFact("constant", f"uses constant {const}", target=const))
    blocks = routine.get("basic_blocks")
    if blocks is not None:
        facts.append(ObservedFact("cfg-metric", f"{blocks} basic blocks"))
    return RoutineObservation(
        binary=header["binary"],
        binary_sha256=header["sha256"],
        entry=routine["entry"],
        name=routine["name"],
        size=int(routine["size"]),
        architecture=header.get("architecture", "unknown"),
        tool=header.get("tool", "ghidra-headless"),
        tool_version=str(header.get("tool_version", "")),
        settings=header.get("settings", "default auto-analysis"),
        facts=tuple(facts),
        decompilation_sha256=routine.get("decompilation_sha256"),
        notes=routine.get("notes", ""),
    )


def observations_from_document(doc: dict) -> list[RoutineObservation]:
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError(f"reconstruction document must have schema {SCHEMA}")
    for key in ("binary", "sha256"):
        if not isinstance(doc.get(key), str):
            raise ValueError(f"reconstruction document is missing {key!r}")
    routines = doc.get("routines")
    if not isinstance(routines, list):
        raise ValueError("reconstruction document is missing a routines list")
    observations = [_routine_to_observation(r, doc) for r in routines]
    observations.sort(key=lambda o: int(o.entry, 16))
    return observations


def load_reconstruction(path: Path) -> list[RoutineObservation]:
    path = Path(path)
    if path.stat().st_size > _MAX_DOC_BYTES:
        raise ValueError("reconstruction document exceeds the 8 MiB cap")
    return observations_from_document(json.loads(path.read_text(encoding="utf-8")))


def select(observations: list[RoutineObservation], key: str) -> RoutineObservation:
    """Select one observation by routine name or entry address."""

    for obs in observations:
        if obs.name == key or obs.entry == key:
            return obs
    raise KeyError(f"no routine named or entered at {key!r}")


def summary(observations: list[RoutineObservation]) -> dict:
    return {
        "routine_count": len(observations),
        "routines": [
            {
                "name": o.name,
                "entry": o.entry,
                "size": o.size,
                "calls": len(o.call_targets()),
                "facts": len(o.facts),
                "binary": o.binary,
                "binary_sha256": o.binary_sha256,
            }
            for o in observations
        ],
    }
