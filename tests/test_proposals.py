import json

import pytest

from rain_atlas.agents.lab import ApprovalRequired, BudgetExceeded, Engineer, Lab
from rain_atlas.agents.proposals import load_proposal, register, validate_proposal
from rain_atlas.ledger.store import Ledger


def proposal(registry):
    skill = registry.get("method-agreement")
    return {
        "schema": "atlas.proposal/v1",
        "action": "propose_experiment",
        "generation": "human",
        "question": "Do estimates agree?",
        "hypothesis": "Agreement is within 0.1 Hz",
        "null_hypothesis": "Methods disagree",
        "controls": "Matched and deliberately shifted frequencies",
        "criteria": "Agreement fraction >=0.8",
        "skills": [{"name": skill.name, "version": skill.version, "content_hash": skill.content_hash}],
        "budget": {"max_runs": 1, "max_seconds": 300},
        "approval_required": True,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(action="execute_shell"),
        lambda p: p.update(approval_required=False),
        lambda p: p.update(command="whoami"),
        lambda p: p["budget"].update(max_runs=10000),
        lambda p: p["skills"][0].update(content_hash="sha256:" + "0" * 64),
        lambda p: p.update(generation="model"),
    ],
)
def test_unsafe_or_stale_proposals_rejected(registry, mutate):
    p = proposal(registry)
    mutate(p)
    with pytest.raises(ValueError):
        validate_proposal(p, registry)


def test_model_provenance_is_recorded_without_evidence(tmp_path, registry):
    p = proposal(registry)
    p.update(
        generation="model",
        model={
            "identity": "offline-test-model",
            "parameters": {"temperature": 0},
            "prompt_hash": "sha256:" + "1" * 64,
        },
    )
    ledger = Ledger(tmp_path)
    exp = register(p, ledger, registry)
    assert ledger.get_json(exp)["created_by"]["generation"] == "model"
    assert ledger.verify() == []
    assert (
        not list(ledger.entries("run"))
        and not list(ledger.entries("approval"))
        and not list(ledger.entries("claim"))
    )


def test_registered_proposal_cannot_self_approve_or_reset_budget(tmp_path, registry):
    p = proposal(registry)
    ledger = Ledger(tmp_path / "ledger")
    exp = register(p, ledger, registry)
    lab = Lab(ledger, registry, tmp_path / "runs")
    engineer = Engineer(lab)
    skill = registry.get("method-agreement")
    inputs = {"estimates_a": [[1]], "estimates_b": [[1]], "tolerance_hz": 0.1}
    with pytest.raises(ApprovalRequired):
        engineer.execute(exp, skill, inputs, seed=0, purpose="proposal")
    lab.approve(exp, "tester", "wrong-skill")
    with pytest.raises(ApprovalRequired):
        engineer.execute(exp, skill, inputs, seed=0, purpose="proposal")
    lab.approve(exp, "tester", skill.name)
    _, result = engineer.execute(exp, skill, inputs, seed=0, purpose="proposal")
    assert result.ok
    restarted = Engineer(Lab(ledger, registry, tmp_path / "runs2"))
    with pytest.raises(BudgetExceeded):
        restarted.execute(exp, skill, inputs, seed=0, purpose="restart")


def test_nonfinite_proposal_rejected(tmp_path, registry):
    p = proposal(registry)
    p["budget"]["max_seconds"] = float("nan")
    file = tmp_path / "proposal.json"
    file.write_text(json.dumps(p))
    with pytest.raises(ValueError):
        load_proposal(file, registry)
