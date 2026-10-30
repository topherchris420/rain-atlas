"""Computed verdicts: evidence decides, not the number of agreeing agents.

A finding is *supported* only when an independent procedure corroborates it,
a falsification test on independent data corroborates it, and the primary
computation reproduces exactly. A disagreement that survives reproduction is
*contradicted*. Everything else is *unresolved*, and stays visible as such.
"""

from __future__ import annotations


def outcome_from_fraction(fraction: float, corroborate_at: float, contradict_below: float) -> str:
    if fraction >= corroborate_at:
        return "corroborated"
    if fraction < contradict_below:
        return "contradicted"
    return "inconclusive"


def verdict(independent: str | None, falsification: str | None, reproduced: bool | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if reproduced is not True:
        reasons.append("the primary computation did not reproduce exactly" if reproduced is False
                       else "no reproduction run was performed")
        return "unresolved", reasons
    if independent is None or falsification is None:
        reasons.append("an independent check is missing")
        return "unresolved", reasons
    if independent == "contradicted":
        reasons.append("an independent estimator disagrees beyond tolerance")
    if falsification == "contradicted":
        reasons.append("the replicate falsification test did not find the effect")
    if reasons:
        return "contradicted", reasons
    if independent == "corroborated" and falsification == "corroborated":
        return "supported", ["independent estimator agrees", "replicate test rejects absence", "reproduced exactly"]
    if independent == "inconclusive":
        reasons.append("the independent estimator agrees only in some realizations")
    if falsification == "inconclusive":
        reasons.append("the replicate test is significant in only some replicates")
    return "unresolved", reasons
