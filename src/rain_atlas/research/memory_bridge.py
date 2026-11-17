"""Scientific memory for research missions, with safeguards.

Memory stores what earlier missions concluded about an apparatus. It is
*never evidence*: a recalled characterization only becomes a tempered prior
(:meth:`~rain_atlas.research.inference.PriorSpec.from_memory`), and its
validity is itself tested by every new mission (memory-valid versus
memory-stale regimes, plus a per-coefficient prior-data conflict check in the
engine). Safeguards:

* only *supported* conclusions are remembered, with their ledger claim;
* recalled memories are widened with age;
* two active, mutually contradictory characterizations of one apparatus are
  both set aside (neither becomes a prior) and the contradiction is recorded;
* a memory contradicted by fresh evidence is quarantined: deleted from the
  active set with its history retained, and a contradiction record added.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..memory import ScientificMemory
from .oscillator import LIBRARY, MemoryPrior

KIND = "characterization"


def open_memory(root: Path) -> ScientificMemory:
    return ScientificMemory(Path(root) / "memory")


def recall(memory: ScientificMemory, apparatus: str) -> tuple[MemoryPrior | None, dict]:
    found = memory.get_all(filters={"agent_id": apparatus, "kind": KIND})["results"]
    if not found:
        return None, {"status": "none", "apparatus": apparatus}
    structures = {tuple(item["metadata"]["structure"]) for item in found}
    if len(structures) > 1:
        return None, {
            "status": "contradictory",
            "apparatus": apparatus,
            "memories": [item["id"] for item in found],
            "structures": sorted(list(s) for s in structures),
            "summary": "active memories of this apparatus disagree about its structure; both are set aside",
        }
    latest = sorted(found, key=lambda item: item["metadata"].get("mission_index", 0))[-1]
    meta = latest["metadata"]
    age = max(1, len(found))
    prior = MemoryPrior(
        apparatus=apparatus,
        structure=tuple(t for t in LIBRARY if t in meta["structure"]),
        mean={k: round(float(v), 6) for k, v in meta["mean"].items()},
        sd={k: round(float(v), 6) for k, v in meta["sd"].items()},
        noise_sd=round(float(meta["noise_sd"]), 6),
        age=age,
        source="memory",
        reference=str(meta.get("claim", "")),
    )
    return prior, {"status": "recalled", "apparatus": apparatus, "memory": latest["id"]}


def remember(
    memory: ScientificMemory,
    apparatus: str,
    conclusion: dict,
    *,
    mission: str,
    claim: str,
    mission_index: int,
) -> dict:
    coeffs = conclusion["coefficients"]
    text = (
        f"Characterization of {apparatus} by mission {mission}: structure "
        f"{', '.join(conclusion['structure'])}; supported claim {claim}"
    )
    return memory.add(
        text,
        agent_id=apparatus,
        metadata={
            "kind": KIND,
            "structure": list(conclusion["structure"]),
            "mean": {t: round(float(v["mean"]), 6) for t, v in coeffs.items()},
            "sd": {t: round(float(v["sd"]), 6) for t, v in coeffs.items()},
            "noise_sd": round(float(conclusion["noise_sd"]), 6),
            "mission": mission,
            "mission_index": mission_index,
            "claim": claim,
        },
        infer=False,
    )


def quarantine(memory: ScientificMemory, apparatus: str, details: dict, *, mission: str) -> dict[str, Any]:
    found = memory.get_all(filters={"agent_id": apparatus, "kind": KIND})["results"]
    for item in found:
        memory.delete(item["id"])
    memory.add(
        f"Contradiction: mission {mission} found the remembered characterization of {apparatus} stale. "
        f"{details.get('summary', '')}",
        agent_id=apparatus,
        metadata={"kind": "contradiction", "mission": mission, "quarantined": [i["id"] for i in found]},
        infer=False,
    )
    return {"quarantined": [i["id"] for i in found], "history_retained": True}
