"""Safety, preregistration and evidence classification regression checks."""

from __future__ import annotations

import json

import pytest

from rain_atlas.ledger.store import Ledger
from rain_atlas.physical_scientist import (
    ResonanceModel,
    demo,
    evaluate,
    observe,
    preregister,
    select_frequency,
    synthetic_csv,
)


def _models():
    return [ResonanceModel("a", 150), ResonanceModel("b", 170)]


def test_selector_is_deterministic_and_bounded():
    models = _models()
    a = select_frequency(models, [0.5, 0.5], 0.2, [145, 150, 160, 170])
    assert a == select_frequency(models, [0.5, 0.5], 0.2, [170, 145, 150, 160])
    assert a["frequency_hz"] in {145, 150, 160, 170}
    with pytest.raises(ValueError):
        select_frequency(models, [0.5, 0.5], 0.2, [150, 1001])
    with pytest.raises(ValueError):
        select_frequency(models, [0.5, 0.5], 0.2, [150], (150,))


def test_preregistration_precedes_observation_and_is_immutable(tmp_path):
    ledger = Ledger(tmp_path)
    models = _models()
    exp = preregister(ledger, models, [0.6, 0.4], 0.2, 150)
    before = ledger.get_json(exp)["design"]["prediction_response"]
    obs = observe(
        ledger,
        exp,
        synthetic_csv(models[1], 150, 0.2, 8),
        origin="synthetic",
        provenance={"generator": "damped_oscillator_v1", "seed": 8},
    )
    result = evaluate(ledger, exp, obs)
    assert result["origin"] == "synthetic"
    assert ledger.get_json(exp)["design"]["prediction_response"] == before
    assert [x.kind for x in ledger.entries()] == ["preregistration", "dataset", "report"]
    assert ledger.verify() == []
    with pytest.raises(ValueError, match="already recorded"):
        observe(
            ledger,
            exp,
            synthetic_csv(models[1], 150, 0.2, 8),
            origin="synthetic",
            provenance={"generator": "damped_oscillator_v1", "seed": 8},
        )
    with pytest.raises(ValueError, match="already evaluated"):
        evaluate(ledger, exp, obs)


def test_empirical_requires_attestation_and_matching_protocol(tmp_path):
    ledger = Ledger(tmp_path)
    exp = preregister(ledger, _models(), [0.6, 0.4], 0.2, 155)
    raw = b"frequency_hz,response\n155,0.85\n"
    with pytest.raises(ValueError, match="requires"):
        observe(ledger, exp, raw, origin="empirical", provenance={"instrument_id": "bench"})
    with pytest.raises(ValueError, match="frequency"):
        observe(
            ledger,
            exp,
            b"frequency_hz,response\n154,0.85\n",
            origin="synthetic",
            provenance={"generator": "damped_oscillator_v1", "seed": 1},
        )
    prov = {
        "operator": "local",
        "instrument_id": "bench-1",
        "calibration_ref": "unverified:v1",
        "acquired_at_utc": "2026-11-14T12:00:00Z",
        "attestation": "operator-attested",
    }
    obs = observe(ledger, exp, raw, origin="empirical", provenance=prov)
    assert evaluate(ledger, exp, obs)["evidence_level"] == "operator-attested-import"
    assert ledger.verify() == []
    assert ledger.get_bytes(ledger.get_json(obs)["object"]) == raw


@pytest.mark.parametrize(
    "bad",
    [
        b"frequency_hz,response\n150,NaN\n",
        b"frequency_hz,response\n150,-1\n",
        b"frequency_hz,response\n150,1\n150,2\n",
        b"frequency_hz,response\n150,inf\n",
    ],
)
def test_observation_rejects_bad_measurements(tmp_path, bad):
    ledger = Ledger(tmp_path)
    exp = preregister(ledger, _models(), [0.6, 0.4], 0.2, 150)
    with pytest.raises(ValueError):
        observe(
            ledger,
            exp,
            bad,
            origin="synthetic",
            provenance={"generator": "damped_oscillator_v1", "seed": 1},
        )
    assert [x.kind for x in ledger.entries()] == ["preregistration"]


def test_three_act_demo_is_explicitly_synthetic_and_replayable(tmp_path):
    result = demo(tmp_path / "new-demo", seed=7)
    assert result["evidence_level"] == "SIMULATION_ONLY"
    assert len(result["acts"]) == 3
    assert result["acts"][0]["champion_contradicted"]
    assert result["heldout_comparison"]["heldout_frequency_hz"] == 187.0
    assert result["observatory"].endswith("index.html")
    ledger = Ledger(tmp_path / "new-demo" / "ledger")
    assert ledger.verify() == []
    assert all(r["origin"] == "synthetic" for _, r in ledger.records("dataset"))
    data = json.loads((tmp_path / "new-demo" / "observatory" / "review-data.json").read_text())
    assert all(r["data"]["origin"] == "synthetic" for r in data["records"] if r["kind"] == "dataset")
