"""The research loop: decisions follow evidence, scope is enforced, and the critic works."""

from __future__ import annotations

import numpy as np
import pytest

from rain_atlas.research import critic
from rain_atlas.research.charter import CharterError, check, default_charter, digest
from rain_atlas.research.engine import ARMS, ResearchEngine
from rain_atlas.research.governance import ScopeGuard, ScopeViolation, authorization_record
from rain_atlas.research.inference import Analysis, ExperimentStats, Hypothesis, Posterior, PriorSpec
from rain_atlas.research.oscillator import (
    LIBRARY,
    Design,
    Instrument,
    World,
    generate_problems,
    make_problem,
    structure_of,
)
from rain_atlas.research.planner import ClosedLoop, OpenLoopOptimal, PlanningState, Yoked

CHARTER = default_charter()


def mission(world, *, arm="closed-loop", memory=None, charter=CHARTER, **kw):
    return ResearchEngine(
        charter, Instrument(world), mission_id="t", seed=world.seed + 1, arm=arm, memory=memory, **kw
    )


def test_charter_validation_and_digest():
    assert digest(CHARTER) == digest(default_charter())
    with pytest.raises(CharterError):
        check(default_charter(**{"environment.hardware_control": True}))
    with pytest.raises(CharterError):
        check(
            default_charter(
                **{
                    "environment.model_provider": {
                        "kind": "ollama",
                        "url": "http://example.com",
                        "model": "m",
                    }
                }
            )
        )
    assert digest(default_charter(**{"budgets.experiments_per_mission": 12})) != digest(CHARTER)


def test_stationary_duffing_is_identified_and_supported():
    world = World({"x": -1.3, "v": -0.16, "u": 1.0, "x^3": -0.4}, noise_scale=0.3, seed=910_001)
    result = mission(world).run()
    c = result.conclusion
    assert result.stop_reason == "decision-challenged"
    assert c["verdict"] == "supported" and c["asserted"]
    assert tuple(c["structure"]) == structure_of(world.coefficients)
    assert c["falsification"] == "corroborated" and c["independent"] == "corroborated" and c["reproduced"]
    assert c["change"] is None
    # the prediction for every experiment after the first was recorded before it ran
    plans = [e for e in result.events if e["event"] == "plan"]
    assert all(p["prediction"] for p in plans[1:])
    for p in plans:
        obs = next(e for e in result.events if e["event"] == "observation" and e["index"] == p["index"])
        assert p["seq"] < obs["seq"]


def test_hidden_change_is_detected_and_attributed():
    world = World(
        {"x": -1.1, "v": -0.2, "u": 0.9, "1": 0.25},
        noise_scale=0.3,
        change_at=2,
        changed_coefficients={"x": -0.72, "v": -0.2, "u": 0.9, "1": 0.25},
        seed=910_002,
    )
    c = mission(world).run().conclusion
    assert c["change"] is not None
    assert abs(c["change"]["change_at"] - 2) <= 1 and c["change"]["changed"] == ["x"]
    assert c["coefficients"]["x"]["mean"] == pytest.approx(-0.72, abs=0.1)


def test_unanticipated_term_is_admitted_by_the_critic_and_decided_by_evidence():
    world = World({"x": -1.0, "v": -0.12, "u": 1.1, "x^2*v": -0.3}, noise_scale=0.3, seed=910_003)
    result = mission(world).run()
    expansions = [
        e for e in result.events if e["event"] == "revision" and e["kind"] == "hypothesis-expansion"
    ]
    assert any("x^2*v" in e["summary"] for e in expansions)
    assert "x^2*v" in result.conclusion["structure"]
    without = mission(world, arm="closed-loop-no-critic").run()
    assert "x^2*v" not in without.conclusion["structure"]


def test_heavy_tailed_noise_revises_the_noise_assumption():
    world = World(
        {"x": -1.3, "v": -0.16, "u": 1.0, "x^3": -0.4}, noise_scale=0.3, noise="student-t3", seed=77
    )
    result = mission(world).run()
    kinds = [e["kind"] for e in result.events if e["event"] == "revision"]
    assert "assumption" in kinds
    assert result.conclusion["robust"]


def test_noise_limited_mission_ends_unresolved_with_an_escalation_request():
    world = World({"x": -1.6, "v": -0.3, "u": 0.8, "x^3": -0.2, "1": 0.08}, noise_scale=1.0, seed=910_005)
    result = mission(world).run()
    assert result.stop_reason == "budget-exhausted"
    assert result.conclusion["verdict"] == "unresolved" and not result.conclusion["asserted"]
    assert result.escalation["kind"] == "budget-extension" and result.escalation["grantable"]


def test_missions_are_deterministic():
    problem = make_problem("dev", "hidden-change", 1)
    a = ResearchEngine(CHARTER, problem.instrument(), mission_id="m", seed=5).run()
    b = ResearchEngine(CHARTER, problem.instrument(), mission_id="m", seed=5).run()
    assert a.digest == b.digest and a.events == b.events


def test_stale_memory_is_quarantined_and_correct_memory_is_kept():
    stale = next(p for p in generate_problems("dev", 20, ("wrong-assumptions",)) if "stale" in p.variant)
    r = ResearchEngine(CHARTER, stale.instrument(), mission_id="m", seed=1, memory=stale.memory).run()
    assert r.memory_state == "quarantined"
    good = next(p for p in generate_problems("dev", 20, ("stationary",)) if p.memory is not None)
    r = ResearchEngine(CHARTER, good.instrument(), mission_id="m", seed=1, memory=good.memory).run()
    assert r.memory_state in ("confirmed", "active")


def test_scope_guard_refuses_out_of_scope_actions():
    guard = ScopeGuard(CHARTER, "m")
    with pytest.raises(ScopeViolation) as exc:
        guard.check_design(Design(3.0, 1.0, 0.0))
    assert exc.value.request.kind == "design-space" and exc.value.request.grantable
    with pytest.raises(ScopeViolation) as exc:
        guard.check_experiment(16)
    assert exc.value.request.kind == "budget-extension"
    for check_fn, kind in (
        (lambda: guard.check_hardware("drive the shaker"), "hardware-control"),
        (lambda: guard.check_code("exec(model_output)"), "untrusted-code"),
        (lambda: guard.check_term("sin(x)"), "untrusted-code"),
        (lambda: guard.check_model_call(), "network"),
    ):
        with pytest.raises(ScopeViolation) as exc:
            check_fn()
        assert exc.value.request.kind == kind and not exc.value.request.grantable
    narrow = default_charter(**{"hypothesis_grammar.expansion": ["x^2"]})
    with pytest.raises(ScopeViolation) as exc:
        ScopeGuard(narrow, "m").check_term("x*u")
    assert exc.value.request.kind == "grammar-term"


def test_authorizations_widen_only_grantable_scope():
    request = {
        "request_id": "r1",
        "mission": "m",
        "kind": "budget-extension",
        "requested": {"experiments": 4},
        "cap": 8,
    }
    auth = authorization_record(request, operator="op", decision="approve")
    guard = ScopeGuard(CHARTER, "m", [auth])
    assert guard.experiment_budget() == 20
    with pytest.raises(ValueError):
        authorization_record(request, operator="op", decision="approve", granted={"experiments": 50})
    hardware = {"request_id": "r2", "mission": "m", "kind": "hardware-control", "requested": {}}
    auth = authorization_record(hardware, operator="op", decision="approve")
    assert auth["effective"] is False
    with pytest.raises(ScopeViolation):
        ScopeGuard(CHARTER, "m", [auth]).check_hardware("drive")


def test_budget_extension_lets_a_mission_continue():
    world = World({"x": -1.6, "v": -0.3, "u": 0.8, "x^3": -0.2, "1": 0.08}, noise_scale=1.0, seed=910_005)
    first = mission(world).run()
    auth = authorization_record({**first.escalation, "cap": 8}, operator="op", decision="approve")
    second = mission(world, guard=ScopeGuard(CHARTER, "t", [auth])).run()
    assert second.experiments > first.experiments
    # the extended mission replays the first mission exactly up to the old stopping point
    head = [e for e in first.events if e["event"] in ("plan", "observation")]
    assert [e for e in second.events if e["event"] in ("plan", "observation")][: len(head)] == head


def _state(observations, seed=3):
    stats = [ExperimentStats.from_rows(*o.regression()) for o in observations]
    analysis = Analysis(stats, PriorSpec.default(), budget=16, change_prior=0.08)
    structures = [("x", "v", "u"), ("x", "v", "u", "x^3"), ("x", "v", "u", "1"), ("x", "v", "u", "x^3", "1")]
    posterior = Posterior.from_fits(analysis.evaluate([Hypothesis(s) for s in structures]))
    return PlanningState(
        analysis=analysis,
        posterior=posterior,
        space=dict((k, tuple(v)) for k, v in CHARTER["design_space"].items()),
        history=[o.design for o in observations],
        step=len(observations),
        seed=seed,
    )


def test_closed_loop_choice_depends_on_the_observations_and_open_loop_does_not():
    d0 = Design(1.0, 1.0, 0.3)
    soft = Instrument(World({"x": -0.6, "v": -0.1, "u": 1.0}, noise_scale=0.3, seed=1)).run(d0, 0)
    stiff = Instrument(World({"x": -2.4, "v": -0.1, "u": 1.0, "x^3": -0.5}, noise_scale=0.3, seed=1)).run(
        d0, 0
    )
    policy = ClosedLoop()
    a = policy.explore(_state([soft]))
    b = policy.explore(_state([stiff]))
    assert a.design != b.design
    assert a.ranked and a.ranked[0]["utility_nats"] >= a.ranked[-1]["utility_nats"]
    space = {k: tuple(v) for k, v in CHARTER["design_space"].items()}
    ol = OpenLoopOptimal(space)
    assert ol.explore(_state([soft])).design == ol.explore(_state([stiff])).design


def test_yoked_policy_replays_its_donor_then_falls_back():
    space = {k: tuple(v) for k, v in CHARTER["design_space"].items()}
    donor = [Design(1.0, 1.0, 0.0), Design(1.5, 2.0, 0.5)]
    y = Yoked(donor, space, "other")
    st = _state([Instrument(World({"x": -1, "v": -0.1, "u": 1}, noise_scale=0.3, seed=1)).run(donor[0], 0)])
    st.step = 1
    assert y.explore(st).design == donor[1]
    st.step = 2
    assert y.explore(st).design not in donor


def test_score_test_finds_an_omitted_term_and_stays_quiet_without_one():
    rng = np.random.default_rng(0)
    phi = rng.normal(size=(2000, len(LIBRARY)))
    for omitted, expect in ((0.5, True), (0.0, False)):
        y = (
            -1.0 * phi[:, 0]
            - 0.2 * phi[:, 1]
            + omitted * phi[:, LIBRARY.index("x^2*v")]
            + rng.normal(size=2000)
        )
        a = Analysis(
            [ExperimentStats.from_rows(phi, y)], PriorSpec.default(noise_sd=1.0), budget=16, change_prior=0
        )
        fit = a.evaluate([Hypothesis(("x", "v", "u"))])[0]
        lm = critic.lm_tests(a, fit, ["x^2*v", "x*u"])
        top = next(r for r in lm if r["term"] == "x^2*v")
        assert top["proposed"] is expect


def test_cross_validated_check_rejects_a_missing_term_and_accepts_the_truth():
    rng = np.random.default_rng(1)
    designs_true, designs_reduced, designs_extended, targets = [], [], [], []
    for _ in range(4):
        X = rng.normal(size=(300, 3))
        y = X @ np.array([-1.0, -0.3, 0.8]) + 0.5 * rng.normal(size=300)
        designs_true.append(X)
        designs_reduced.append(X[:, :2])
        designs_extended.append(np.hstack([X, rng.normal(size=(300, 1))]))
        targets.append(y)
    ok = critic.cross_validated_check(
        [designs_true, designs_reduced, designs_extended],
        targets,
        ["target", "reduced", "extended"],
        robust=False,
    )
    assert ok["outcome"] == "corroborated"
    bad = critic.cross_validated_check(
        [designs_reduced, designs_true], targets, ["target", "extended"], robust=False
    )
    assert bad["outcome"] == "contradicted"


def test_every_arm_runs_and_legacy_never_claims_a_change():
    problem = make_problem("dev", "hidden-change", 3)
    for arm in ARMS:
        donor = [Design(1.0, 1.0, 0.0)] * 3 if arm == "yoked" else None
        r = ResearchEngine(
            CHARTER, problem.instrument(), mission_id="m", seed=2, arm=arm, memory=problem.memory, donor=donor
        ).run()
        assert r.experiments <= 16
        if arm == "legacy-atlas":
            assert r.conclusion["change"] is None
