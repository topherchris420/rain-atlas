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


def test_falsification_outcomes_follow_the_tested_frequency(lab):
    # Regression: outcomes were paired with claims by position. A skill that
    # returned its tests in another order would attach each verdict to the
    # wrong claim, and a short response silently left claims unchallenged.
    from types import SimpleNamespace

    from rain_atlas.agents.roles import Skeptic

    exp = prereg(lab)
    run = lab.ledger.append(
        "run",
        {
            "run_id": "r",
            "skill": {"name": "x"},
            "status": "ok",
            "seed": 0,
            "inputs_hash": "sha256:" + "1" * 64,
            "experiment": exp,
            "role": "experimental-engineer",
        },
    )
    author = {"role": "computational-scientist", "generation": "scripted"}
    claims = []
    for f in (10.0, 20.0, 30.0):
        entry = lab.ledger.append(
            "claim",
            {
                "experiment": exp,
                "category": "COMPUTED",
                "statement": f"{f} Hz",
                "evidence": [run.object],
                "author": author,
            },
        )
        claims.append((entry, {"frequency_hz": f}))

    class ReversingEngineer:
        def execute(self, experiment, skill, inputs, **kwargs):
            tests = [
                {
                    "frequency_hz": f,
                    "outcome": {10.0: "corroborated", 20.0: "contradicted"}[f],
                    "fraction_significant": 1.0,
                }
                for f in reversed(inputs["frequencies_hz"])
                if f != 30.0  # a short response: 30 Hz is never tested
            ]
            return run, SimpleNamespace(ok=True, outputs={"tests": tests})

    replicates = {"$artifact": "replicates.npy", "sha256": lab.ledger.put_bytes(b"replicates")}
    outcomes = Skeptic(lab, ReversingEngineer()).falsify(
        exp, None, replicates, claims, fs=1.0, alpha=0.01, min_fraction=0.8, seed=0, label="order"
    )
    assert [outcomes[e.object] for e, _ in claims] == ["corroborated", "contradicted", "inconclusive"]
    challenged = [r["target"] for _, r in lab.ledger.records("challenge")]
    assert challenged == [e.object for e, _ in claims]
