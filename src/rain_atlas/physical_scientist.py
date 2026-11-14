"""Evidence-first resonance experiment slice. No hardware actuation or AI claims.

A single-mode oscillator is a surrogate, not a finite-element plate model.
Selection uses between-model variance as an information-gain *proxy*.
"""

from __future__ import annotations

import csv
import io
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from .agents.lab import author
from .ledger.store import Ledger

FREQUENCY_BOUNDS_HZ = (20.0, 1000.0)


@dataclass(frozen=True)
class ResonanceModel:
    name: str
    natural_hz: float
    quality: float = 12.0
    gain: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("model requires a name")
        if not (20 <= self.natural_hz <= 1000) or not math.isfinite(self.natural_hz):
            raise ValueError("natural_hz out of range")
        if not (1 <= self.quality <= 100) or not math.isfinite(self.quality):
            raise ValueError("quality out of range")
        if not (0 < self.gain <= 10) or not math.isfinite(self.gain):
            raise ValueError("gain out of range")

    def response(self, frequency_hz: float) -> float:
        validate_frequency(frequency_hz)
        x = frequency_hz / self.natural_hz
        return self.gain / math.sqrt((1 - x * x) ** 2 + (x / self.quality) ** 2)


def validate_frequency(value: float) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("frequency must be finite")
    if not FREQUENCY_BOUNDS_HZ[0] <= value <= FREQUENCY_BOUNDS_HZ[1]:
        raise ValueError("frequency outside software planning envelope")


def validate_models(models: list[ResonanceModel], weights: list[float], sigma: float) -> None:
    if len(models) < 2 or len(models) != len(weights):
        raise ValueError("at least two competing models with weights required")
    if len({m.name for m in models}) != len(models):
        raise ValueError("model names must be unique")
    if not math.isfinite(sigma) or not 0 < sigma <= 10:
        raise ValueError("sigma must be finite, positive and bounded")
    if any(not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError("weights must be nonnegative and finite")
    if not math.isclose(sum(weights), 1.0, abs_tol=1e-9):
        raise ValueError("weights must sum to one")


def select_frequency(
    models: list[ResonanceModel],
    weights: list[float],
    sigma: float,
    candidates_hz: list[float],
    excluded_hz: tuple[float, ...] = (),
) -> dict:
    """Choose largest weighted predictive disagreement at matched noise variance."""
    validate_models(models, weights, sigma)
    if not candidates_hz:
        raise ValueError("no candidate frequencies")
    scores = []
    for f in sorted(set(candidates_hz)):
        validate_frequency(f)
        if f in excluded_hz:
            continue
        predictions = [m.response(f) for m in models]
        mean = sum(w * p for w, p in zip(weights, predictions))
        disagreement = sum(w * (p - mean) ** 2 for w, p in zip(weights, predictions))
        scores.append((disagreement / (sigma * sigma), f))
    if not scores:
        raise ValueError("all frequencies excluded")
    score, frequency = max(scores, key=lambda item: (item[0], -item[1]))
    return {
        "frequency_hz": frequency,
        "selection_score": score,
        "selection_rule": "weighted_between_model_variance_over_noise_variance_v1",
    }


def preregister(
    ledger: Ledger,
    models: list[ResonanceModel],
    weights: list[float],
    sigma: float,
    frequency_hz: float,
    *,
    purpose: str = "model discrimination",
    parent: str | None = None,
    selection: dict | None = None,
) -> str:
    validate_models(models, weights, sigma)
    validate_frequency(frequency_hz)
    if ledger.verify():
        raise ValueError("cannot preregister on an invalid evidence ledger")
    predictions = [m.response(frequency_hz) for m in models]
    champion = max(range(len(models)), key=lambda i: weights[i])
    design = {
        "instrument_authority": "NONE: no hardware commands implemented",
        "model_family": "linear_single_mode_damped_oscillator_surrogate",
        "models": [asdict(m) for m in models],
        "prior_weights": weights,
        "frequency_hz": frequency_hz,
        "sigma_response": sigma,
        "prediction_response": predictions,
        "response_units": "normalized amplitude (arbitrary units)",
        "purpose": purpose,
        "falsification_rule": "abs(observed - champion_prediction) > 3 * sigma_response",
        "budget": {"max_observations": 1},
    }
    record = {
        "title": f"Physical Scientist: {purpose} at {frequency_hz:.2f} Hz",
        "question": "Which candidate single-mode transfer function best predicts an unknown resonator?",
        "hypothesis": f"{models[champion].name} predicts response {predictions[champion]:.8g}",
        "null_hypothesis": "At least one competing transfer function better predicts this observation",
        "design": design,
        "acceptance": {"precommitted_three_sigma_discrepancy": True},
        "created_by": author("physical-theorist"),
    }
    if selection is not None:
        if selection.get("frequency_hz") != frequency_hz:
            raise ValueError("selection must match preregistered frequency")
        record["design"]["selection"] = selection
    if parent:
        if not any(e.object == parent for e in ledger.entries("preregistration")):
            raise ValueError("parent experiment must be an earlier preregistration")
        record["parent_experiment"] = parent
    return ledger.append("preregistration", record).object


def synthetic_csv(model: ResonanceModel, frequency_hz: float, sigma: float, seed: int) -> bytes:
    """Operator-side simulator. Never interpret its output as hardware observation."""
    if not 0 < sigma <= 10 or not math.isfinite(sigma):
        raise ValueError("invalid sigma")
    measurement = max(0.0, model.response(frequency_hz) + random.Random(seed).gauss(0, sigma))
    return f"frequency_hz,response\n{frequency_hz:.8f},{measurement:.12f}\n".encode("ascii")


def _parse_measurement(raw: bytes, expected_hz: float) -> float:
    if len(raw) > 4096 or not raw or b"\x00" in raw:
        raise ValueError("measurement must be a nonempty CSV of at most 4096 bytes")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8", errors="strict")), strict=True)
        if reader.fieldnames != ["frequency_hz", "response"]:
            raise ValueError("expected frequency_hz,response header")
        rows = list(reader)
        if len(rows) != 1 or None in rows[0]:
            raise ValueError("exactly one well-formed measurement row required")
        freq, response = float(rows[0]["frequency_hz"]), float(rows[0]["response"])
    except (UnicodeError, csv.Error, TypeError, OverflowError) as exc:
        raise ValueError("malformed measurement CSV") from exc
    validate_frequency(freq)
    if not math.isclose(freq, expected_hz, abs_tol=1e-6, rel_tol=0):
        raise ValueError("measurement frequency does not match preregistration")
    if not math.isfinite(response) or response < 0 or response > 1e6:
        raise ValueError("response must be finite, positive and bounded")
    return response


def observe(
    ledger: Ledger,
    experiment: str,
    raw_csv: bytes,
    *,
    origin: str,
    provenance: dict,
) -> str:
    """Append one raw datum. Empirical means operator-attested, not independently verified."""
    if ledger.verify():
        raise ValueError("refusing observation on invalid ledger")
    if origin not in {"synthetic", "empirical"}:
        raise ValueError("origin must be synthetic or empirical")
    if not any(e.object == experiment for e in ledger.entries("preregistration")):
        raise ValueError("unknown preregistration")
    if any(r["experiment"] == experiment for _, r in ledger.records("dataset")):
        raise ValueError("observation already recorded; create a new preregistration")
    if origin == "empirical":
        required = ("operator", "instrument_id", "calibration_ref", "acquired_at_utc")
        if any(not isinstance(provenance.get(k), str) or not provenance[k] for k in required):
            raise ValueError("empirical source requires operator, instrument, calibration and timestamp")
        if provenance.get("attestation") != "operator-attested":
            raise ValueError("empirical source requires operator-attested provenance")
    elif not ("seed" in provenance and provenance.get("generator") == "damped_oscillator_v1"):
        raise ValueError("synthetic source requires explicit simulator provenance")
    prereg = ledger.get_json(experiment)
    response = _parse_measurement(raw_csv, prereg["design"]["frequency_hz"])
    obj = ledger.put_bytes(raw_csv)
    return ledger.append(
        "dataset",
        {
            "experiment": experiment,
            "name": "single_frequency_transfer_response",
            "origin": origin,
            "media_type": "text/csv",
            "object": obj,
            "provenance": provenance,
            "frequency_hz": prereg["design"]["frequency_hz"],
            "response": response,
            "response_units": "normalized amplitude (arbitrary units)",
        },
    ).object


def evaluate(ledger: Ledger, experiment: str, observation: str) -> dict:
    """Deterministic evaluator reads only frozen hypotheses and immutable observation."""
    if ledger.verify():
        raise ValueError("refusing evaluation on invalid ledger")
    if not any(e.object == experiment for e in ledger.entries("preregistration")):
        raise ValueError("unknown experiment")
    if not any(e.object == observation for e in ledger.entries("dataset")):
        raise ValueError("unknown observation")
    if any(r.get("evaluated_observation") == observation for _, r in ledger.records("report")):
        raise ValueError("observation already evaluated")
    measurement = ledger.get_json(observation)
    if measurement["experiment"] != experiment:
        raise ValueError("cross-experiment observation forbidden")
    design = ledger.get_json(experiment)["design"]
    models = [ResonanceModel(**m) for m in design["models"]]
    prior = design["prior_weights"]
    sigma = design["sigma_response"]
    validate_models(models, prior, sigma)
    expected = [m.response(design["frequency_hz"]) for m in models]
    if any(
        not math.isclose(a, b, abs_tol=1e-9, rel_tol=1e-10)
        for a, b in zip(expected, design["prediction_response"])
    ):
        raise ValueError("frozen predictions do not match frozen models")
    observed = _parse_measurement(ledger.get_bytes(measurement["object"]), design["frequency_hz"])
    log_likelihood = [
        math.log(w) - 0.5 * ((observed - p) / sigma) ** 2 if w else -math.inf for w, p in zip(prior, expected)
    ]
    peak = max(log_likelihood)
    normalized = [math.exp(v - peak) for v in log_likelihood]
    denom = sum(normalized)
    posterior = [x / denom for x in normalized]
    champion = max(range(len(prior)), key=lambda i: prior[i])
    residual_sigma = abs(observed - expected[champion]) / sigma
    contradiction = residual_sigma > 3.0
    result = {
        "experiment": experiment,
        "observation": observation,
        "origin": measurement["origin"],
        "frequency_hz": design["frequency_hz"],
        "observed_response": observed,
        "frozen_predictions": dict(zip((m.name for m in models), expected)),
        "prior_weights": dict(zip((m.name for m in models), prior)),
        "posterior_weights": dict(zip((m.name for m in models), posterior)),
        "initial_champion": models[champion].name,
        "initial_champion_residual_sigma": residual_sigma,
        "champion_contradicted": contradiction,
        "method": "Gaussian likelihood with preregistered fixed sigma; no parameter fitting",
        "evidence_level": "simulation"
        if measurement["origin"] == "synthetic"
        else "operator-attested-import",
    }
    ledger.append(
        "report",
        {
            "experiment": experiment,
            "evaluated_observation": observation,
            "findings": [],
            "reproduction": {
                "method": "deterministic-evaluation-from-immutable-ledger",
                "tool": "scripts/physical_scientist.py evaluate",
                "inputs": [experiment, observation],
            },
            "acceptance": [
                {
                    "id": "champion_prediction",
                    "passed": not contradiction,
                    "criterion": "initial champion within 3 specified sigma",
                }
            ],
            "negative_results": (
                ["Initial champion contradicted by precommitted 3-sigma criterion"] if contradiction else []
            ),
            "limitations": [
                "Single-mode linear oscillator surrogate, not a validated plate FEM.",
                "Sigma assumed known; posterior weights depend on this assumption.",
                "Synthetic results are not physical evidence; empirical imports have operator attestation only.",
                "Hash chains verify consistency, not sensor authenticity or physical correctness.",
            ],
            "conclusion": (
                "Precommitted champion contradicted"
                if contradiction
                else "Precommitted champion not contradicted"
            )
            + f" ({result['evidence_level']})",
            "evaluation": result,
            "author": author("deterministic-statistician"),
        },
    )
    return result


def demo(root: Path, *, seed: int = 7, truth_hz: float = 186.0) -> dict:
    """Three-act SIMULATED contradiction-and-revision demonstration."""
    root = Path(root)
    if root.exists():
        raise FileExistsError("demo requires a fresh output directory")
    root.mkdir(parents=True)
    ledger = Ledger(root / "ledger")
    models = [
        ResonanceModel("low_mode", 170.0),
        ResonanceModel("mid_mode", 180.0),
        ResonanceModel("high_mode", 190.0),
    ]
    truth = ResonanceModel("hidden_simulator_only", truth_hz)
    sigma = 1.5
    prior = [0.60, 0.25, 0.15]
    grid = [float(f) for f in range(120, 221, 5)]
    seen: list[float] = []
    history: list[dict] = []
    original = prior[:]
    parent = None
    for act in ("I prediction", "II targeted follow-up"):
        selection = select_frequency(models, prior, sigma, grid, tuple(seen))
        f = selection["frequency_hz"]
        exp = preregister(ledger, models, prior, sigma, f, purpose=act, parent=parent, selection=selection)
        obs = observe(
            ledger,
            exp,
            synthetic_csv(truth, f, sigma, seed + len(seen)),
            origin="synthetic",
            provenance={"generator": "damped_oscillator_v1", "seed": seed + len(seen)},
        )
        outcome = evaluate(ledger, exp, obs)
        outcome["selection"] = selection
        history.append(outcome)
        prior = [outcome["posterior_weights"][m.name] for m in models]
        seen.append(f)
        parent = exp
    # Fixed before the demo, never adaptively selected; this tests a new frequency, not a new plate.
    holdout_hz = 187.0
    exp = preregister(
        ledger,
        models,
        prior,
        sigma,
        holdout_hz,
        purpose="III withheld-frequency predictive check",
        parent=parent,
    )
    obs = observe(
        ledger,
        exp,
        synthetic_csv(truth, holdout_hz, sigma, seed + 2),
        origin="synthetic",
        provenance={"generator": "damped_oscillator_v1", "seed": seed + 2},
    )
    outcome = evaluate(ledger, exp, obs)
    y = outcome["observed_response"]
    preds = [m.response(holdout_hz) for m in models]
    initial = sum(w * p for w, p in zip(original, preds))
    revised = sum(w * p for w, p in zip(prior, preds))
    comparison = {
        "origin": "synthetic",
        "heldout_frequency_hz": holdout_hz,
        "original_squared_error": (y - initial) ** 2,
        "revised_squared_error": (y - revised) ** 2,
        "revision_improved": (y - revised) ** 2 < (y - initial) ** 2,
        "caution": "One simulated holdout point; no independent replication, no physical evidence",
    }
    ledger.append(
        "note",
        {
            "experiment": exp,
            "text": "Held-out prediction comparison (synthetic only)",
            "comparison": comparison,
            "author": author("deterministic-statistician"),
        },
    )
    ledger.append(
        "report",
        {
            "experiment": exp,
            "findings": [],
            "reproduction": {
                "method": "recreate-three-act-simulation",
                "tool": "scripts/physical_scientist.py demo",
                "seed": seed,
                "truth_hz": truth_hz,
                "fixed_holdout_hz": holdout_hz,
            },
            "acceptance": [
                {
                    "id": "heldout_revision_improvement",
                    "passed": comparison["revision_improved"],
                    "criterion": "revised mixture reduces squared error on fixed synthetic holdout",
                }
            ],
            "negative_results": (
                ["Revised mixture did not improve the prespecified holdout"]
                if not comparison["revision_improved"]
                else []
            ),
            "limitations": [
                "Fixed single-frequency simulated holdout; no physical or cross-apparatus validation."
            ],
            "conclusion": (
                "Synthetic holdout improved"
                if comparison["revision_improved"]
                else "Synthetic holdout did not improve"
            ),
            "author": author("deterministic-statistician"),
        },
    )
    assert ledger.verify() == []
    from .observatory.export import export

    viewer = export(ledger.root, root / "observatory")
    return {
        "ledger": str(ledger.root),
        "observatory": str(viewer),
        "acts": history + [outcome],
        "heldout_comparison": comparison,
        "evidence_level": "SIMULATION_ONLY",
    }
