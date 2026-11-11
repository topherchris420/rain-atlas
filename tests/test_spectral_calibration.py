import json

import numpy as np
import pytest

from rain_atlas.bench.calibration import ALPHA, CALIBRATION_WINDOWS, evaluate, max_rank_pvalues
from rain_atlas.cli import main
from rain_atlas.ledger.store import Ledger


def test_rank_counts_ties_conservatively_and_scans_against_maxima():
    np.testing.assert_array_equal(
        max_rank_pvalues(np.array([0, 2, 3, 5]), np.array([4, 2, 2])),
        [1, 1, 0.5, 0.25],
    )
    with pytest.raises(ValueError, match="nonempty vectors"):
        max_rank_pvalues(np.array([1]), np.array([]))
    with pytest.raises(ValueError, match="finite"):
        max_rank_pvalues(np.array([np.nan]), np.array([1]))


def test_every_possible_held_out_rank_has_the_expected_scan_size():
    # Enumerate the test window in a fixed set of distinct whole-band maxima.
    maxima = np.arange(CALIBRATION_WINDOWS + 1)
    rejected = []
    for i, value in enumerate(maxima):
        scores = np.array([value - 0.1, value, value - 2])
        p = max_rank_pvalues(scores, np.delete(maxima, i))
        assert p.min() == (maxima.size - i) / maxima.size
        rejected.append(bool((p <= ALPHA).any()))
    assert sum(rejected) == ALPHA * maxima.size


def test_panel_preserves_model_shift_and_sensitivity_failures():
    results = evaluate(24, seed=42)
    cases = {row["case"]: row["methods"] for row in results["rows"]}
    for case in cases.values():
        panel = case["reference-panel"]["any_detection_rate"]
        assert panel["n"] == 24
        assert panel["successes"] <= min(
            case[method]["any_detection_rate"]["successes"] for method in ("white-reference", "ar1-reference")
        )
    assert cases["ar1-null"]["reference-panel"]["any_detection_rate"]["successes"] <= 4
    assert cases["ar1-null"]["welch-white-threshold"]["any_detection_rate"]["successes"] >= 20
    assert cases["oscillatory-null"]["reference-panel"]["any_detection_rate"]["successes"] >= 20
    assert cases["oscillatory-null"]["reference-panel"]["target_band_detection_rate"]["successes"] >= 20
    assert cases["ar1-weak-tone"]["reference-panel"]["target_band_detection_rate"]["successes"] <= 4
    assert cases["ar1-strong-tone"]["reference-panel"]["target_band_detection_rate"]["successes"] >= 20


def test_calibration_cli_preregisters_and_replays_outputs_and_artifacts(tmp_path, capsys):
    root = tmp_path / "calibration"
    args = ["benchmark", "--protocol", "spectral-calibration", "--root", str(root), "--trials"]
    assert main([*args, "2"]) == 1
    assert not root.exists()
    assert main([*args, "3"]) == 0, capsys.readouterr().err

    ledger = Ledger(root / "ledger")
    assert ledger.verify() == []
    assert [entry.kind for entry in ledger.entries()] == [
        "preregistration",
        "run",
        "claim",
        "run",
        "reproduction",
        "report",
    ]
    (preregistration,) = [record for _, record in ledger.records("preregistration")]
    (reproduction,) = [record for _, record in ledger.records("reproduction")]
    result = json.loads((root / "benchmark.json").read_text(encoding="utf-8"))
    assert preregistration["design"] == result["design"]
    assert reproduction["outputs_match"] and reproduction["artifacts_match"]
    assert (root / "observatory" / "index.html").is_file()
    assert main([*args, "3"]) == 1
    assert len(list(ledger.entries())) == 6
