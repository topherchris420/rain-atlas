import pytest
from conftest import fixture_ref

from rain_atlas.agents.lab import ApprovalRequired, Budget, BudgetExceeded, Engineer, Lab
from rain_atlas.ledger.store import Ledger


@pytest.fixture
def lab(tmp_path, registry):
    ledger = Ledger(tmp_path / "ledger")
    return Lab(ledger, registry, tmp_path / "runs")


def prereg(lab):
    return lab.ledger.append(
        "preregistration",
        {
            "title": "t",
            "question": "q",
            "hypothesis": "h",
            "null_hypothesis": "h0",
            "design": {},
            "acceptance": [],
            "created_by": {"role": "principal-investigator", "generation": "scripted"},
        },
    ).object


def test_builtin_skill_runs_without_approval_and_is_recorded(lab):
    exp = prereg(lab)
    skill = lab.registry.get("method-agreement")
    entry, result = Engineer(lab).execute(
        exp,
        skill,
        {"estimates_a": [[1.0]], "estimates_b": [[1.0]], "tolerance_hz": 0.1},
        seed=0,
        purpose="test",
    )
    assert result.ok
    record = lab.ledger.get_json(entry.object)
    assert record["approval"] == "auto-builtin"
    assert lab.ledger.get_json(record["inputs_object"])["tolerance_hz"] == 0.1
    assert lab.ledger.verify() == []


def test_non_builtin_skill_needs_operator_approval(lab):
    exp = prereg(lab)
    engineer = Engineer(lab)
    with pytest.raises(ApprovalRequired) as info:
        engineer.execute(exp, fixture_ref("echo"), {"values": [1]}, seed=0, purpose="test")
    assert info.value.prefix == exp[7:15]
    assert not list(lab.ledger.entries("run"))
    lab.approve(exp, operator="tester", scope="echo")
    entry, result = engineer.execute(exp, fixture_ref("echo"), {"values": [1]}, seed=0, purpose="test")
    assert result.ok and lab.ledger.get_json(entry.object)["approval"] == "operator"
    assert lab.ledger.verify() == []


def test_failed_runs_are_recorded_too(lab):
    exp = prereg(lab)
    lab.approve(exp, operator="tester", scope="naughty")
    entry, result = Engineer(lab).execute(
        exp, fixture_ref("naughty"), {"mode": "network"}, seed=0, purpose="probe"
    )
    assert result.status == "error"
    record = lab.ledger.get_json(entry.object)
    assert record["status"] == "error" and record["policy_denials"]


def test_budget_is_enforced(lab):
    exp = prereg(lab)
    lab.budget = Budget(max_runs=1)
    engineer = Engineer(lab)
    skill = lab.registry.get("method-agreement")
    inputs = {"estimates_a": [[1.0]], "estimates_b": [[1.0]], "tolerance_hz": 0.1}
    engineer.execute(exp, skill, inputs, seed=0, purpose="first")
    with pytest.raises(BudgetExceeded):
        engineer.execute(exp, skill, inputs, seed=0, purpose="second")


def test_sealed_runs_do_not_store_inputs_and_reproduce_after_unseal(lab):
    exp = prereg(lab)
    tones = [{"frequency_hz": 5.0, "amplitude": 1.0, "phase_rad": 0.0}]
    _, commitment = lab.ledger.seal("truth", {"tones": tones})
    public = {"fs": 100.0, "n": 64, "noise_std": 0.1, "realizations": 2}
    engineer = Engineer(lab)
    entry, result = engineer.execute(
        exp,
        lab.registry.get("synthetic-tones"),
        {**public, "tones": tones},
        seed=3,
        purpose="generate",
        sealed={"commitment": commitment, "public": public},
    )
    assert result.ok
    record = lab.ledger.get_json(entry.object)
    assert "inputs_object" not in record and record["sealed"]["commitment"] == commitment
    assert not (result.run_dir / "input" / "_inputs.json").exists()
    with pytest.raises(ValueError):
        engineer.reproduce(exp, entry)
    _, value = lab.ledger.unseal(commitment, after=[entry.object])
    rec, match = engineer.reproduce(exp, entry, inputs={**public, "tones": value["tones"]})
    assert match
    with pytest.raises(ValueError, match="public"):
        engineer.reproduce(exp, entry, inputs={**public, "noise_std": 0.2, "tones": value["tones"]})
    assert lab.ledger.verify() == []


def test_unsealed_run_reproduces_exactly(lab):
    exp = prereg(lab)
    engineer = Engineer(lab)
    entry, _ = engineer.execute(
        exp,
        lab.registry.get("recovery-score"),
        {"estimates": [[1.0]], "truth_hz": [1.0], "tolerance_hz": 0.1},
        seed=0,
        purpose="x",
    )
    rec, match = engineer.reproduce(exp, entry)
    assert match
    assert lab.ledger.get_json(rec.object)["outputs_match"] is True
