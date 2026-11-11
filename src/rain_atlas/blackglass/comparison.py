"""Behavioural Comparison Laboratory.

Two comparisons, both over *observed facts* (never runtime behaviour):

* :func:`compare_spec_to_observation` — does the binary exhibit the evidence the
  reconstruction predicts? A reconstruction of MD5 predicts the sine-table
  constants; of base64, its alphabet. Finding them in the observation is
  independent corroboration that the bytes implement the claimed algorithm;
  a missing prediction contradicts the reconstruction. This is the cross-check
  that turns a *reconstructed* interpretation into a testable claim.
* :func:`compare_observations` — the routine-level delta between two firmware
  versions (the Firmware Evolution Analyzer's core), expressed as added/removed
  calls, strings and constants and the size change.

Outcomes use the ledger's vocabulary (corroborated / contradicted / inconclusive).
"""

from __future__ import annotations

from .routines import BehaviorSpec, RoutineObservation


def _present(expected: tuple[str, ...], haystack: frozenset[str]) -> tuple[list[str], list[str]]:
    hay_lower = {h.lower() for h in haystack}
    present = [e for e in expected if e.lower() in hay_lower]
    missing = [e for e in expected if e.lower() not in hay_lower]
    return present, missing


def _string_present(expected: tuple[str, ...], strings: tuple[str, ...]) -> tuple[list[str], list[str]]:
    present, missing = [], []
    for e in expected:
        if any(e in s for s in strings):
            present.append(e)
        else:
            missing.append(e)
    return present, missing


def compare_spec_to_observation(spec: BehaviorSpec, observation: RoutineObservation) -> dict:
    """Check a reconstruction's predicted binary evidence against the observation."""

    constants = frozenset(
        c for c in (f.target or f.detail for f in observation.facts if f.kind == "constant") if c
    )
    strings = tuple(f.target or f.detail for f in observation.facts if f.kind == "string-ref")
    calls = observation.call_targets()

    const_present, const_missing = _present(spec.expects_constants, constants)
    str_present, str_missing = _string_present(spec.expects_strings, strings)
    call_present, call_missing = _present(spec.relies_on_calls, calls)

    predicted = spec.expects_constants or spec.expects_strings
    if not predicted:
        outcome = "inconclusive"
    elif const_missing or str_missing:
        outcome = "contradicted"
    else:
        outcome = "corroborated"
    detail = (
        f"constants {len(const_present)}/{len(spec.expects_constants)}, "
        f"strings {len(str_present)}/{len(spec.expects_strings)}, "
        f"relied-on calls {len(call_present)}/{len(spec.relies_on_calls)}"
    )
    return {
        "method": "reconstruction-predicted evidence vs observed facts",
        "outcome": outcome,
        "detail": detail,
        "constants_present": const_present,
        "constants_missing": const_missing,
        "strings_present": str_present,
        "strings_missing": str_missing,
        "calls_present": call_present,
        "calls_missing": call_missing,
    }


def compare_observations(base: RoutineObservation, target: RoutineObservation) -> dict:
    """Routine-level difference between two firmware versions (evolution analysis)."""

    def facts(obs: RoutineObservation, kind: str) -> frozenset[str]:
        return frozenset(f.target or f.detail for f in obs.facts if f.kind == kind)

    base_calls, tgt_calls = base.call_targets(), target.call_targets()
    base_str, tgt_str = facts(base, "string-ref"), facts(target, "string-ref")
    base_const, tgt_const = facts(base, "constant"), facts(target, "constant")
    changed = (
        base.binary_sha256 != target.binary_sha256
        or base_calls != tgt_calls
        or base_str != tgt_str
        or base_const != tgt_const
        or base.size != target.size
    )
    return {
        "routine": base.name,
        "base_sha256": base.binary_sha256,
        "target_sha256": target.binary_sha256,
        "identical_bytes": base.binary_sha256 == target.binary_sha256,
        "size_delta": target.size - base.size,
        "calls_added": sorted(tgt_calls - base_calls),
        "calls_removed": sorted(base_calls - tgt_calls),
        "strings_added": sorted(tgt_str - base_str),
        "strings_removed": sorted(base_str - tgt_str),
        "constants_added": sorted(tgt_const - base_const),
        "constants_removed": sorted(base_const - tgt_const),
        "changed": changed,
    }
