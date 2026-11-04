"""Phase 10 acceptance: the reference experiment actually executes and meets its
preregistered criteria. Slow (several minutes); run with ``pytest -m slow``.
"""

import json
from pathlib import Path

import pytest
from conftest import BUILTIN

from rain_atlas.experiments import spectral_recovery as sr
from rain_atlas.ledger.store import Ledger
from rain_atlas.skills.registry import Registry

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def fixed(tmp_path_factory):
    root = tmp_path_factory.mktemp("spectral-recovery-fixed")
    summary = sr.run(
        root, sr.Settings(mode="fixed"), registry=Registry(home=root / "home", builtin_root=BUILTIN)
    )
    return root, summary


def by_label(summary):
    return {d["label"]: d for d in summary["datasets"]}


def test_all_preregistered_criteria_pass(fixed):
    _, summary = fixed
    failed = [(a["id"], a["detail"]) for a in summary["acceptance"] if not a["passed"]]
    assert failed == []
    assert [a["id"] for a in summary["acceptance"]] == [a["id"] for a in sr.ACCEPTANCE]


def test_numerical_tolerances(fixed):
    _, summary = fixed
    ds = by_label(summary)
    truth = [t["frequency_hz"] for t in summary["truth"]["tones"]]
    assert truth == list(sr.FIXED_FREQUENCIES_HZ)
    # +20 dB: every tone recovered in every realization, sub-0.05 Hz error
    top = ds["D1"]["scores"]["primary"]
    assert top["all_recovered_rate"] == 1.0
    for tone in top["tones"]:
        assert abs(tone["bias_hz"]) < 0.05 and tone["rmse_hz"] < 0.05
    # the independent estimator is near-efficient at high SNR
    for tone in ds["D1"]["scores"]["independent"]["tones"]:
        assert 0.5 <= tone["std_over_crlb"] <= 2.0
    # each supported finding is within 0.25 Hz of the truth, and the three tones are supported at +20 dB
    supported = [f for f in ds["D1"]["findings"] if f["verdict"] == "supported"]
    assert sorted(round(f["nearest_truth_hz"], 1) for f in supported) == sorted(truth)
    assert all(abs(f["error_hz"]) < 0.05 for f in supported)
    # -30 dB: recovery fails and is reported as a negative result
    assert ds["D5"]["scores"]["primary"]["all_recovered_rate"] < 0.5
    assert any(n["dataset"] == "D5" for n in summary["negative_results"])
    # control: noise only, nothing supported
    control = ds[summary["truth"]["control_dataset"]]
    assert control["truth"] == [] and not any(f["verdict"] == "supported" for f in control["findings"])


def test_order_of_evidence(fixed):
    root, summary = fixed
    ledger = Ledger(root / "ledger")
    entries = [e for e in ledger.entries()]
    first = {kind: min(e.seq for e in entries if e.kind == kind) for kind in {e.kind for e in entries}}
    last = {kind: max(e.seq for e in entries if e.kind == kind) for kind in {e.kind for e in entries}}
    assert first["preregistration"] == 0
    assert last["seal"] < first["dataset"]  # truth committed before any data existed
    unseal = first["unseal"]
    for kind in ("challenge", "verdict", "reproduction"):
        pre_unseal = [e for e in entries if e.kind == kind and e.seq < unseal]
        assert pre_unseal, kind
    verdicts_after = [e for e in entries if e.kind == "verdict" and e.seq > unseal]
    assert verdicts_after == []  # verdicts can't be revised after seeing the truth
    assert ledger.verify() == []


def test_sealed_truth_does_not_leak_before_unseal(fixed):
    root, summary = fixed
    ledger = Ledger(root / "ledger")
    phases = [repr(t["phase_rad"]) for t in summary["truth"]["tones"]]
    unseal = next(e.seq for e in ledger.entries("unseal"))
    sealed_runs = 0
    for entry in ledger.entries():
        if entry.seq >= unseal:
            break
        text = ledger.get_bytes(entry.object).decode("utf-8")
        assert not any(p in text for p in phases), (entry.kind, entry.seq)
        if entry.kind == "run":
            record = json.loads(text)
            if record.get("sealed"):
                sealed_runs += 1
                assert "inputs_object" not in record
                # the generator's on-disk copy of its inputs was deleted after the run
                assert not (root / "runs" / record["run_id"] / "input" / "_inputs.json").exists()
    assert sealed_runs == 2 * len(summary["datasets"])
    # Runs after the unseal (generator reproductions) may hold the published truth; that is expected.


def test_report_and_bundle(fixed):
    _, summary = fixed
    report = Path(summary["report_path"]).read_text(encoding="utf-8")
    for label in ("[COMPUTED]", "[INTERPRETED]", "[GROUND TRUTH]", "Negative results", "not blind"):
        assert label in report
    assert "FAIL" not in report.split("## Findings")[0]
    assert Path(summary["bundle_path"]).stat().st_size > 0
    assert all(fig["files"] for fig in summary["figures"])


def test_fixed_mode_is_exactly_reproducible(fixed, tmp_path):
    _, first = fixed
    again = sr.run(
        tmp_path,
        sr.Settings(mode="fixed", figures=False, bundle=False),
        registry=Registry(home=tmp_path / "home", builtin_root=BUILTIN),
    )
    for a, b in zip(first["datasets"], again["datasets"]):
        assert a["scores"] == b["scores"]
        assert [(f["value_hz"], f["verdict"]) for f in a["findings"]] == [
            (f["value_hz"], f["verdict"]) for f in b["findings"]
        ]


def test_blinded_mode_integrity(tmp_path):
    settings = sr.Settings(mode="blinded", realizations=8, replicates=5, figures=False, bundle=False)
    summary = sr.run(tmp_path, settings, registry=Registry(home=tmp_path / "home", builtin_root=BUILTIN))
    truth = [t["frequency_hz"] for t in summary["truth"]["tones"]]
    assert truth != list(sr.FIXED_FREQUENCIES_HZ)
    results = {a["id"]: a for a in summary["acceptance"]}
    for cid in ("A5", "A6", "A7"):  # integrity criteria hold at any sample size
        assert results[cid]["passed"], results[cid]["detail"]
