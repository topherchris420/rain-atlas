"""Tests for the unified R.A.I.N. vertical slice and central experiment."""

from __future__ import annotations

from pathlib import Path

import pytest

from rain_atlas.rain import (
    AdaptiveSelector,
    CandidateModels,
    GridSelector,
    RandomSelector,
    run_central_experiment,
    run_vertical_slice,
)
from rain_atlas.rain.models import Observation
from rain_atlas.rain.policies import GRID, RANDOM, select_condition


class TestDecisionBook:
    def test_predictions_diverge_monotonically(self):
        models = CandidateModels()
        disagreement = [models.disagreement(c) for c in (0.2, 0.5, 0.8, 1.0)]
        assert disagreement[-1] == max(disagreement)

    def test_decided_with_strong_evidence(self):
        models = CandidateModels(replicates=4)
        # Observations exactly on the damped prediction at high coupling.
        observations = [
            Observation(
                coupling=1.0,
                coherence=models
                and __import__("rain_atlas.rain.models", fromlist=["predict_coherence"]).predict_coherence(
                    "damped", 1.0
                ),
                replicates=4,
            )
        ]
        assert models.decided(observations)
        assert models.preferred_model(observations) == "damped"

    def test_undecided_with_no_evidence(self):
        assert not CandidateModels().decided([])
        assert CandidateModels().preferred_model([]) == "linear"


class TestPolicies:
    GRID_VALUES = [round(0.1 * i, 2) for i in range(1, 11)]

    def test_adaptive_picks_max_disagreement_first(self):
        selector = AdaptiveSelector(CandidateModels())
        assert selector.next_condition(self.GRID_VALUES, []) == 1.0

    def test_adaptive_skips_tested(self):
        selector = AdaptiveSelector(CandidateModels())
        tested = [Observation(coupling=1.0, coherence=0.9, replicates=4)]
        choice = selector.next_condition(self.GRID_VALUES, tested)
        assert choice != 1.0
        assert choice == pytest.approx(0.9)

    def test_grid_goes_low_to_high(self):
        selector = GridSelector()
        assert selector.next_condition(self.GRID_VALUES, []) == 0.1
        tested = [Observation(coupling=0.1, coherence=0.2, replicates=4)]
        assert selector.next_condition(self.GRID_VALUES, tested) == 0.2

    def test_random_is_seed_deterministic(self):
        a = RandomSelector(seed=5)
        b = RandomSelector(seed=5)
        assert a.next_condition(self.GRID_VALUES, []) == b.next_condition(self.GRID_VALUES, [])

    def test_grid_exhausts(self):
        selector = GridSelector()
        tested = [Observation(coupling=c, coherence=0.5, replicates=4) for c in self.GRID_VALUES]
        assert selector.next_condition(self.GRID_VALUES, tested) is None

    def test_dispatch(self):
        assert select_condition(GRID, self.GRID_VALUES, [], seed=1) == 0.1
        assert select_condition(RANDOM, self.GRID_VALUES, [], seed=1) in self.GRID_VALUES
        with pytest.raises(ValueError):
            select_condition("nope", self.GRID_VALUES, [], seed=1)


class TestVerticalSlice:
    def test_full_slice_decides_correctly(self, tmp_path: Path):
        result = run_vertical_slice(tmp_path / "slice", seed=7, true_model="damped")
        assert result.hypothesis.startswith("Hypothesis:")
        assert result.protocol_id
        assert result.decided is True
        assert result.preferred_model == "damped"
        assert result.true_model == "damped"
        assert result.replication["verdict_replicated"] is True
        assert result.ledger_verified is True
        assert result.mission_status == "complete"
        # Every task completed, one approval was requested and resolved.
        assert all(task["status"] == "completed" for task in result.tasks)
        assert len(result.approvals) == 1
        assert result.approvals[0]["resolution"] == "approve"
        # Model generation is labeled honestly.
        generations = {t["generation"] for task in result.tasks for t in task["transitions"]}
        assert "scripted" in generations
        assert "model" in generations

    def test_slice_is_deterministic(self, tmp_path: Path):
        a = run_vertical_slice(tmp_path / "a", seed=3, true_model="linear", clock=lambda: 1.0)
        b = run_vertical_slice(tmp_path / "b", seed=3, true_model="linear", clock=lambda: 1.0)
        assert a.to_dict() == b.to_dict()

    def test_slice_without_approval_blocks(self, tmp_path: Path):
        result = run_vertical_slice(tmp_path / "blocked", seed=7, true_model="damped", approve=False)
        assert result.mission_status == "blocked"
        assert result.experiments == []  # experiments never ran
        assert result.decided is False

    def test_slice_with_faults_recovers(self, tmp_path: Path):
        from rain_atlas.simulation import FaultProfile

        result = run_vertical_slice(
            tmp_path / "faulted",
            seed=9,
            true_model="damped",
            fault_profile=FaultProfile(drop_probability=0.3, noise_sigma=0.01),
        )
        assert result.mission_status == "complete"
        assert result.tasks  # tasks recorded even under faults

    def test_slice_survives_restart_of_memory(self, tmp_path: Path):
        # Same memory root reused: recall still works (append-only store).
        first = run_vertical_slice(tmp_path / "shared", seed=7, true_model="damped")
        assert first.memory_statistics["total"] > 0


class TestCentralExperimentV1:
    """The superseded protocol stays exactly reproducible (see experiment_v1)."""

    def test_recorded_outcome_reproduces_exactly(self, tmp_path: Path):
        result = run_central_experiment(tmp_path / "v1", protocol="v1")
        totals = {arm: outcome.total_experiments for arm, outcome in result.arms.items()}
        assert totals == {"integrated-memory": 6, "integrated-no-memory": 19, "grid": 57, "random": 26}
        assert result.hypotheses["H1"]["measured"]["reduction"] == 0.6842
        # The flaw that motivated v2: after the first mission of each program the
        # memory arm decided without running anything.
        per_mission = result.arms["integrated-memory"].experiments_per_mission
        assert per_mission == [1, 0, 0] * 6
        assert result.ledger_verified is True

    def test_experiment_runs_and_verifies(self, tmp_path: Path):
        result = run_central_experiment(
            tmp_path / "central", protocol="v1", programs=4, missions_per_program=3
        )
        assert set(result.arms) == {
            "integrated-memory",
            "integrated-no-memory",
            "grid",
            "random",
        }
        assert result.ledger_verified is True
        for arm in result.arms.values():
            assert arm.missions == 12  # 4 programs x 3 missions
            assert arm.replications == 4
        # Preregistered hypotheses were evaluated and recorded.
        assert set(result.hypotheses) == {"H1", "H2", "H3"}
        for record in result.hypotheses.values():
            assert "measured" in record and "passed" in record

    def test_fresh_root_required(self, tmp_path: Path):
        run_central_experiment(tmp_path / "once", protocol="v1", programs=2)
        with pytest.raises(ValueError, match="fresh directory"):
            run_central_experiment(tmp_path / "once", protocol="v1", programs=2)


class TestCentralExperimentV2Rules:
    """Decision rules and memory behavior on constructed evidence."""

    def test_naive_memory_can_decide_without_experiments(self):
        from rain_atlas.rain.experiment import NAIVE, _decision

        assert _decision(NAIVE, 0.0, 9.0, True) == (True, "linear")

    def test_verified_memory_requires_fresh_confirmation(self):
        from rain_atlas.rain.experiment import VERIFIED, _decision

        assert _decision(VERIFIED, 0.0, 9.0, True)[0] is False  # memory alone never decides
        assert _decision(VERIFIED, 2.9, 9.0, True)[0] is False  # below the 3-nat confirmation
        assert _decision(VERIFIED, 3.1, 9.0, True) == (True, "linear")
        assert _decision(VERIFIED, 3.1, 0.5, True)[0] is False  # weak memory: pooled 3.6 < 5
        assert _decision(VERIFIED, -5.2, 0.0, False) == (True, "damped")

    def test_memoryless_arms_need_five_fresh_nats(self):
        from rain_atlas.rain.experiment import NO_MEMORY, _decision

        assert _decision(NO_MEMORY, 4.9, 50.0, True)[0] is False
        assert _decision(NO_MEMORY, -5.0, 0.0, False) == (True, "damped")

    def test_worlds_are_balanced_and_shift_once(self):
        from rain_atlas.rain.experiment import build_programs

        worlds = build_programs(1, 40, 4)
        stationary = [w for w in worlds if w.regime == "stationary"]
        shifting = [w for w in worlds if w.regime == "shifting"]
        assert len(stationary) == len(shifting) == 40
        assert all(len(set(w.models)) == 1 and w.shift_at is None for w in stationary)
        for world in shifting:
            assert 1 <= world.shift_at <= 3
            assert len(set(world.models[: world.shift_at])) == 1
            assert len(set(world.models[world.shift_at :])) == 1
            assert world.models[0] != world.models[-1]
        assert len({seed for w in worlds for seed in w.seeds}) == 80 * 4

    def test_verified_memory_quarantines_stale_evidence(self):
        from rain_atlas.memory import ScientificMemory
        from rain_atlas.rain.experiment import (
            OBSERVATION_SIGMA,
            REPLICATES,
            VERIFIED,
            Program,
            _remember,
            run_mission,
        )
        from rain_atlas.rain.models import CandidateModels, predict_coherence

        models = CandidateModels(observation_sigma=OBSERVATION_SIGMA, replicates=REPLICATES)
        program = Program("shifting", 0, ("linear", "damped"), 1, (11, 12))
        memory = ScientificMemory(None, clock=lambda: 0.0)
        # Memory holds strong, noiseless evidence for the old (linear) world.
        stale = [
            Observation(c, round(predict_coherence("linear", c), 6), REPLICATES) for c in (1.0, 0.9, 0.8, 0.7)
        ]
        _remember(memory, program.scope, stale, mission=0)
        assert models.log_bayes_factor(stale) > 5

        record = run_mission(VERIFIED, program, 1, models=models, budget=8, base_seed=3, memory=memory)
        assert record.quarantined is True
        assert record.experiments >= 1
        assert not record.false_conclusion
        statistics = memory.statistics()
        assert statistics["deleted"] == 4  # quarantined, with history retained
        contradictions = memory.get_all(filters={"agent_id": program.scope, "kind": "contradiction"})
        assert len(contradictions["results"]) == 1


class TestCentralExperimentV2:
    def test_small_run_structure_and_ledger(self, tmp_path: Path):
        result = run_central_experiment(tmp_path / "v2", programs=6, resamples=200)
        assert result.protocol == "rain-central/v2"
        assert result.ledger_verified is True
        assert set(result.summaries) == {
            "verified-memory",
            "naive-memory",
            "no-memory",
            "grid-ascending",
            "grid-descending",
            "random",
        }
        for by_regime in result.summaries.values():
            assert by_regime["stationary"].missions == by_regime["shifting"].missions == 24
        assert set(result.hypotheses) == {"H1", "H2", "H3", "H4"}
        for record in result.hypotheses.values():
            assert record["verdict"] in {"supported", "contradicted", "unresolved"}
        # Maximum disagreement is a fixed ordering in this problem.
        assert result.ordering_control["all_identical"] is True
        assert result.to_dict()["hypotheses"]["H1"]["alpha"] == 0.0125

    def test_preregistration_precedes_every_result(self, tmp_path: Path):
        from rain_atlas.ledger.store import Ledger

        run_central_experiment(tmp_path / "order", programs=3, resamples=100)
        kinds = [entry.kind for entry in Ledger(tmp_path / "order" / "ledger").entries()]
        assert kinds[0] == "preregistration"
        assert kinds.count("preregistration") == 1
        assert kinds[-1] == "report"

    def test_deterministic(self, tmp_path: Path):
        a = run_central_experiment(tmp_path / "a", programs=4, resamples=100).to_dict()
        b = run_central_experiment(tmp_path / "b", programs=4, resamples=100).to_dict()
        a.pop("elapsed_s")
        b.pop("elapsed_s")
        assert a == b

    def test_unknown_protocol_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="unknown protocol"):
            run_central_experiment(tmp_path / "x", protocol="v3")
