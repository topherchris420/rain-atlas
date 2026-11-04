import numpy as np
import pytest

from rain_atlas.experiments.synchronization import Settings, run
from rain_atlas.ledger.store import Ledger
from rain_atlas.science.synchronization import measure
from rain_atlas.science.uncertainty import disjoint_samples, holm, mean_interval, wilson


def test_uncertainty_known_answers_and_leakage():
    assert mean_interval([1, 1, 1])["low"] == 1
    ci = wilson(0, 100)
    assert ci["low"] == 0 and 0.03 < ci["high"] < 0.04
    assert holm([0.01, 0.04, 0.03])["adjusted"] == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.01, 0.04, 0.03])["reject"] == [True, False, False]
    with pytest.raises(ValueError):
        disjoint_samples(["one"], ["one"])
    with pytest.raises(ValueError):
        mean_interval([1])


def test_measure_independent_negative_and_positive_controls():
    t = np.arange(1000) * 0.1
    negative = np.column_stack([-0.5 * t, 0.5 * t])
    positive = np.column_stack([t, t + 0.2])
    paths = np.array([[negative] * 4, [positive] * 4])

    class Context:
        def load_array(self, ref):
            return paths

    inp = {"phases": {}, "conditions": [{"coupling": 0}, {"coupling": 2}], "dt": 0.1, "burn_s": 0}
    for method in ("phase", "frequency"):
        result = measure({**inp, "method": method}, Context())
        assert [r["outcome"] for r in result["rows"]] == ["contradicted", "corroborated"]


@pytest.mark.slow
def test_synchronization_end_to_end(tmp_path, registry):
    result = run(
        tmp_path,
        Settings(
            replicates=4, figures=False, couplings=(0, 0.6, 1.4, 2), diffusions=(0, 0.5), phase_lags=(0,)
        ),
        registry=registry,
    )
    assert all(a["passed"] for a in result["acceptance"]), result["acceptance"]
    assert result["negative_results"] and result["ledger_problems"] == []
    ledger = Ledger(tmp_path / "ledger")
    entries = list(ledger.entries())
    assert entries[0].kind == "preregistration"
    assert len(list(ledger.entries("challenge"))) == 2 * len(result["findings"])
    assert sum(r["outputs_match"] and r["artifacts_match"] for _, r in ledger.records("reproduction")) == 2
    assert (tmp_path / "observatory" / "index.html").is_file()
    assert all(f["reference_locked"] is None for f in result["findings"] if f["condition"]["diffusion"] > 0)
