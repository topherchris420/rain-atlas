"""Benchmark orchestration through the same ledger and execution policy."""

import json
from pathlib import Path

from ..agents.lab import Budget, Engineer, Lab, author
from ..agents.roles import PrincipalInvestigator
from ..ledger.store import Ledger
from ..observatory.export import export
from ..skills.registry import Registry
from . import PROTOCOLS


def run(
    root: Path,
    trials: int | None = None,
    registry: Registry | None = None,
    *,
    protocol: str = "spectral-stress",
) -> dict:
    if protocol not in PROTOCOLS:
        raise ValueError(f"unknown benchmark protocol: {protocol}")
    calibrated = protocol == "spectral-calibration"
    if calibrated:
        from . import calibration

        trials = calibration.DEFAULT_TRIALS if trials is None else trials
        seed = calibration.SEED
        preregistration = {
            "title": "Spectral calibration benchmark",
            "question": "How much false-alarm control and tone sensitivity survive a change of noise model?",
            "hypothesis": "A reference panel suppresses false alarms under white and AR(1) noise while retaining sensitivity to strong tones.",
            "null_hypothesis": "The reference panel does not improve false alarms relative to the white-noise threshold.",
            "design": calibration.design(trials, seed),
            "acceptance": [
                "retain all null and injected-tone cases, including the out-of-panel oscillatory null",
                "compare the canonical result and artifact hashes in an exact same-seed replay",
            ],
        }
        statement = "Measured whole-band declarations and localization under declared synthetic noise models."
        conclusion = "The reference-panel bound depends on exchangeability. The oscillatory null measures a failure outside that condition."
    else:
        from .spectral import CASES

        trials = 12 if trials is None else trials
        seed = 20261104
        preregistration = {
            "title": "Spectral stress benchmark",
            "question": "When do classical spectral methods fail under model misspecification?",
            "hypothesis": "Close frequencies and colored noise reduce recovery and increase false detections.",
            "null_hypothesis": "Performance is unchanged from separated tones and white noise.",
            "design": {"trials_per_case": trials, "seed": seed, "cases": list(CASES), "tolerance_hz": 0.08},
            "acceptance": [
                "retain all failures and unknown-truth cases; no performance threshold used to hide failures"
            ],
        }
        statement = (
            "Measured per-case detection errors and disagreement; no claim of general scientific reliability."
        )
        conclusion = "A diagnostic benchmark, not a validated general reliability claim."

    root = Path(root).resolve()
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError("benchmark root already has a ledger")
    registry = registry or Registry(home=root / "home")
    lab = Lab(ledger, registry, root / "runs", budget=Budget(max_runs=2, max_seconds=1800))
    pi = PrincipalInvestigator(lab)
    exp = pi.preregister(preregistration).object
    engineer = Engineer(lab)
    entry, result = engineer.execute(
        exp,
        registry.get(f"{protocol}-benchmark"),
        {"trials": trials},
        seed=seed,
        purpose=preregistration["title"],
    )
    if not result.ok:
        raise RuntimeError(str(result.error))
    data = result.outputs["results"]
    claim = ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": statement,
            "value": data,
            "evidence": [entry.object],
            "author": author("computational-scientist"),
        },
    )
    reproduction = {"seed": seed, "trials": trials}
    if calibrated:
        replay, matches = engineer.reproduce(exp, entry)
        reproduction.update(record=replay.object, exact_match=matches)
    pi.report(
        exp,
        findings=[{"claims": [claim.object], "verdict": "unresolved"}],
        limitations=data["limitations"],
        reproduction=reproduction,
        conclusion=conclusion,
        negative_results=data["rows"],
    )
    if ledger.verify():
        raise ValueError("benchmark ledger verification failed")
    out = root / "benchmark.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    export(ledger.root, root / "observatory", registry=registry)
    if calibrated and not reproduction["exact_match"]:
        raise RuntimeError("spectral calibration replay differed; both runs are recorded in the ledger")
    return {"results": data, "path": str(out), "experiment": exp, "run": entry.object}
