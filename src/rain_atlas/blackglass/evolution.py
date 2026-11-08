"""Firmware Evolution Analyzer: routine-level change between two versions.

Matches routines by name across two sets of observations (e.g. the same binary
in two firmware releases) and reports, per routine, the change in size, call
targets, referenced strings and constants, plus routines added or removed. It
works entirely on observed facts; it makes no runtime claim and does not decide
whether a change is a fix or a regression — only that it occurred.
"""

from __future__ import annotations

from .comparison import compare_observations
from .routines import RoutineObservation


def analyze_evolution(
    base: list[RoutineObservation],
    target: list[RoutineObservation],
    *,
    base_label: str = "base",
    target_label: str = "target",
) -> dict:
    base_by_name = {o.name: o for o in base}
    target_by_name = {o.name: o for o in target}
    common = sorted(set(base_by_name) & set(target_by_name))
    added = sorted(set(target_by_name) - set(base_by_name))
    removed = sorted(set(base_by_name) - set(target_by_name))

    routine_deltas = []
    changed = 0
    for name in common:
        delta = compare_observations(base_by_name[name], target_by_name[name])
        if delta["changed"]:
            changed += 1
        routine_deltas.append(delta)

    return {
        "base_label": base_label,
        "target_label": target_label,
        "common_routines": common,
        "added_routines": added,
        "removed_routines": removed,
        "changed_routines": changed,
        "routine_deltas": routine_deltas,
        "summary": {
            "common": len(common),
            "added": len(added),
            "removed": len(removed),
            "changed": changed,
            "unchanged": len(common) - changed,
        },
    }
