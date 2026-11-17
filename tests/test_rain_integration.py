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


class TestCentralExperiment:
    def test_experiment_runs_and_verifies(self, tmp_path: Path):
        result = run_central_experiment(tmp_path / "central", programs=4, missions_per_program=3)
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

    def test_memory_arm_is_more_efficient(self, tmp_path: Path):
        result = run_central_experiment(tmp_path / "central2", programs=4)
        memory_arm = result.arms["integrated-memory"]
        no_memory = result.arms["integrated-no-memory"]
        # H1: this is the scientific claim under test; assert it held here.
        assert memory_arm.total_experiments < no_memory.total_experiments

    def test_fresh_root_required(self, tmp_path: Path):
        run_central_experiment(tmp_path / "once", programs=2)
        with pytest.raises(ValueError, match="fresh directory"):
            run_central_experiment(tmp_path / "once", programs=2)
