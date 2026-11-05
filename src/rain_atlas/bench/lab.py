"""Benchmark orchestration through the same ledger and execution policy."""

from pathlib import Path

from ..agents.lab import Budget, Engineer, Lab, author
from ..agents.roles import PrincipalInvestigator
from ..ledger.store import Ledger
from ..observatory.export import export
from ..skills.registry import Registry


def run(root: Path, trials: int = 12, registry: Registry | None = None) -> dict:
    root = Path(root).resolve()
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError("benchmark root already has a ledger")
    registry = registry or Registry(home=root / "home")
    lab = Lab(ledger, registry, root / "runs", budget=Budget(max_runs=2, max_seconds=1800))
    pi = PrincipalInvestigator(lab)
    exp = pi.preregister(
        {
            "title": "Spectral stress benchmark",
            "question": "When do classical spectral methods fail under model misspecification?",
            "hypothesis": "Close frequencies and colored noise reduce recovery and increase false detections.",
            "null_hypothesis": "Performance is unchanged from separated tones and white noise.",
            "design": {
                "trials_per_case": trials,
                "seed": 20261104,
                "cases": ["separated", "close", "white-null", "colored-null", "chirp", "amplitude-modulated"],
                "tolerance_hz": 0.08,
            },
            "acceptance": [
                "retain all failures and unknown-truth cases; no performance threshold used to hide failures"
            ],
        }
    ).object
    entry, result = Engineer(lab).execute(
        exp,
        registry.get("spectral-stress-benchmark"),
        {"trials": trials},
        seed=20261104,
        purpose="classical baseline stress evaluation",
    )
    if not result.ok:
        raise RuntimeError(str(result.error))
    data = result.outputs["results"]
    claim = ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": "Measured per-case detection errors and disagreement; no claim of general scientific reliability.",
            "value": data,
            "evidence": [entry.object],
            "author": author("computational-scientist"),
        },
    )
    pi.report(
        exp,
        findings=[{"claims": [claim.object], "verdict": "unresolved"}],
        limitations=data["limitations"],
        reproduction={"seed": 20261104, "trials": trials},
        conclusion="A diagnostic benchmark, not a validated general reliability claim.",
        negative_results=data["rows"],
    )
    if ledger.verify():
        raise ValueError("benchmark ledger verification failed")
    out = root / "benchmark.json"
    out.write_text(__import__("json").dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    export(ledger.root, root / "observatory", registry=registry)
    return {"results": data, "path": str(out), "experiment": exp, "run": entry.object}
