"""Acceptance: the ORRERY validation experiment executes and meets its criteria.

Slow (a few minutes): runs every scenario through the skills, re-propagates each
with an independent integrator, reproduces the primary runs and verifies the
ledger. Run with ``pytest -m slow``.
"""

from pathlib import Path

import pytest
from conftest import BUILTIN

from rain_atlas.experiments import orrery
from rain_atlas.ledger.store import Ledger
from rain_atlas.skills.registry import Registry

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    root = tmp_path_factory.mktemp("orrery")
    summary = orrery.run(
        root, orrery.Settings(figures=True), registry=Registry(home=root / "home", builtin_root=BUILTIN)
    )
    return root, summary


def test_all_acceptance_criteria_pass(result):
    _, summary = result
    assert [(a["id"], a["passed"]) for a in summary["acceptance"]] == [
        ("O1", True),
        ("O2", True),
        ("O3", True),
        ("O4", True),
        ("O5", True),
    ]


def test_every_scenario_supported(result):
    _, summary = result
    assert all(f["verdict"] == "supported" for f in summary["findings"])
    names = {f["scenario"] for f in summary["findings"]}
    assert names.issuperset(set(orrery.ANALYTIC_TOL_M) | set(orrery.GMAT_TOL_M) | {"S10-figure-eight"})


def test_errors_within_preregistered_tolerance(result):
    _, summary = result
    for f in summary["findings"]:
        assert f["primary_error_m"] < f["tolerance_m"]
        if f["challenge_error_m"] is not None:
            assert f["challenge_error_m"] < f["tolerance_m"]


def test_ledger_verifies_and_reproduces(result):
    root, summary = result
    assert summary["ledger_problems"] == []
    assert Ledger(root / "ledger").verify() == []
    assert all(f["reproduced"] for f in summary["findings"])


def test_report_and_observatory_written(result):
    root, summary = result
    assert Path(summary["report_path"]).exists()
    assert (root / "observatory" / "index.html").exists()
    assert "not physical validation" in summary["answer"] or "not a claim" in summary["limitations"][0]
