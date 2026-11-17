"""Evidence classification for REA investigations.

Every statement in an investigation package carries one of four
classifications. The rules below are enforced when a package is validated:

**OBSERVED** -- behavior directly examined in an authorized environment, for
example by executing reference software under controlled conditions or
inspecting its published source at a pinned commit.

**COMPUTED** -- a result produced through a recorded calculation or software
execution inside ATLAS (deterministic and reproducible).

**INFERRED** -- a conclusion derived from available evidence but not directly
observed. Inferred statements must cite the evidence they derive from.

**UNKNOWN** -- behavior for which sufficient evidence is unavailable.

Presenting inferred behavior as observed functionality is the primary failure
mode this module exists to prevent.
"""

from __future__ import annotations

from typing import Any

OBSERVED = "OBSERVED"
COMPUTED = "COMPUTED"
INFERRED = "INFERRED"
UNKNOWN = "UNKNOWN"

CLASSIFICATIONS = (OBSERVED, COMPUTED, INFERRED, UNKNOWN)

# Statements in these classifications must cite at least one source reference.
_REQUIRES_SOURCES = (OBSERVED, COMPUTED, INFERRED)


def validate_classification(classification: str, item: dict[str, Any]) -> list[str]:
    """Return a list of rule violations for one evidence *item* dict."""

    problems: list[str] = []
    if classification not in CLASSIFICATIONS:
        problems.append(f"classification {classification!r} is not one of {CLASSIFICATIONS}")
        return problems
    if classification in _REQUIRES_SOURCES:
        sources = item.get("sources") or []
        if not sources:
            problems.append(f"{classification} evidence must cite at least one source reference")
    if classification == INFERRED:
        if not item.get("derives_from"):
            problems.append("INFERRED evidence must list the evidence it derives from")
    if classification == UNKNOWN:
        if item.get("sources") or item.get("derives_from"):
            problems.append("UNKNOWN evidence must not cite sources it cannot assess")
    return problems


def classification_rules() -> dict[str, str]:
    """Human-readable summary of the classification rules."""

    return {
        OBSERVED: "Directly examined in an authorized environment (source at a pinned commit or executed under control).",
        COMPUTED: "Produced by a recorded, reproducible calculation or software execution.",
        INFERRED: "Derived from cited evidence but not directly observed; must reference its basis.",
        UNKNOWN: "Insufficient evidence; no sources may be asserted.",
    }
