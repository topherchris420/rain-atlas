"""Tests for the Scientific Observability Engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from rain_atlas.ledger.store import Ledger
from rain_atlas.observability import (
    EvalDataset,
    Observation,
    ObservationLevel,
    ObservationType,
    Tracer,
    compare_runs,
    run_eval,
    score_close,
)


class StepClock:
    """Deterministic clock advancing 10ms per call."""

    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        self.value += 10.0
        return self.value


@pytest.fixture()
def clock() -> StepClock:
    return StepClock()


class TestTracing:
    def test_trace_hierarchy(self, clock):
        tracer = Tracer(clock=clock)
        with tracer.trace("mission-run", session_id="m1") as trace:
            with trace.span("protocol-compile") as span:
                span.record_input({"question": "q"})
                span.record_output({"protocol": "p"})
                with span.generation("hypothesis-model", model="mock-1") as gen:
                    gen.record_usage(input=10, output=4)
                with span.tool("memory-search"):
                    pass
            with trace.span("evaluation") as span:
                span.record_level(ObservationLevel.WARNING, "one check marginal")

        assert len(tracer.traces) == 1
        result = trace.trace
        roots = result.root_observations()
        assert len(roots) == 1  # the trace scope's own root span
        children = result.children_of(roots[0].id)
        assert [o.name for o in children] == ["protocol-compile", "evaluation"]
        gen_children = result.children_of(children[0].id)
        assert [o.type for o in gen_children] == [ObservationType.GENERATION, ObservationType.TOOL]

    def test_latency_from_injected_clock(self, clock):
        tracer = Tracer(clock=clock)
        with tracer.trace("t") as trace:
            with trace.span("outer"):
                with trace.span("inner"):
                    pass
        spans = trace.trace.observations
        outer = next(o for o in spans if o.name == "outer")
        inner = next(o for o in spans if o.name == "inner")
        assert outer.latency_ms is not None and outer.latency_ms > 0
        assert inner.latency_ms == 10.0

    def test_exceptions_recorded_as_error_level(self, clock):
        tracer = Tracer(clock=clock)
        with pytest.raises(RuntimeError):
            with tracer.trace("t") as trace:
                with trace.span("failing"):
                    raise RuntimeError("boom")
        failing = next(o for o in trace.trace.observations if o.name == "failing")
        assert failing.level == ObservationLevel.ERROR
        assert "boom" in failing.status_message
        assert failing.latency_ms is not None

    def test_usage_and_cost_rollup(self, clock):
        tracer = Tracer(clock=clock)
        with tracer.trace("t") as trace:
            with trace.span("a"):
                with trace.generation("g1", model="m") as gen:
                    gen.record_usage(input=100, output=50, input_cost=0.01, output_cost=0.02)
                with trace.generation("g2", model="m") as gen:
                    gen.record_usage(input=10, output=5, input_cost=0.001, output_cost=0.002)
        usage = trace.trace.total_usage()
        assert usage["input"] == 110 and usage["output"] == 55 and usage["total"] == 165
        assert trace.trace.total_cost() == pytest.approx(0.033)

    def test_scores_on_trace(self, clock):
        tracer = Tracer(clock=clock)
        with tracer.trace("t") as trace:
            trace.add_score("experiment_quality", 0.83, comment="preregistered metric")
        assert trace.trace.scores[0].name == "experiment_quality"
        assert trace.trace.scores[0].value == 0.83

    def test_event_level_validation(self):
        with pytest.raises(ValueError):
            Observation(id="x", trace_id="t", type="WAT", name="n")
        with pytest.raises(ValueError):
            Observation(id="x", trace_id="t", type="SPAN", name="n", level="BAD")

    def test_trace_json_round_trip(self, clock):
        tracer = Tracer(clock=clock)
        with tracer.trace("t", metadata={"mission": 1}) as trace:
            with trace.span("s"):
                pass
        payload = trace.trace.to_dict()
        assert payload["observations"][0]["parentObservationId"] is None


class TestLedgerExport:
    def test_export_creates_verified_ledger_records(self, clock, tmp_path: Path):
        ledger = Ledger(tmp_path / "ledger")
        ledger.append(
            "preregistration",
            {
                "title": "mission experiment",
                "question": "does the mission controller select experiments well?",
                "hypothesis": "integrated selection improves information gain",
                "null_hypothesis": "selection policy does not matter",
                "design": "compare policies on a simulated twin",
                "acceptance": "preregistered metrics",
                "created_by": {"role": "pi", "generation": "scripted"},
            },
        )
        experiment = ledger.entries("preregistration").__next__().object
        tracer = Tracer(clock=clock)
        with tracer.trace("mission") as trace:
            with trace.span("compile"):
                pass
        bundle_ref = tracer.export_to_ledger(
            ledger, experiment=experiment, author={"role": "engineer", "generation": "scripted"}
        )
        assert ledger.has(bundle_ref)
        notes = list(ledger.records("note"))
        assert len(notes) == 1
        assert "observability export" in notes[0][1]["text"]
        assert ledger.verify() == []

    def test_write_json(self, clock, tmp_path: Path):
        tracer = Tracer(clock=clock)
        with tracer.trace("t"):
            pass
        path = tracer.write_json(tmp_path / "traces" / "traces.json")
        assert path.exists()


class TestEvals:
    def test_dataset_and_run(self):
        dataset = EvalDataset(name="tone-recovery", description="cases")
        dataset.add_case(input={"freq": 440.0}, expected=440.0)
        dataset.add_case(input={"freq": 880.0}, expected=880.0)

        run = run_eval(
            dataset,
            "welch-detector",
            system=lambda case: case["freq"],
            scorer=lambda expected, actual: (
                abs(expected - actual) <= 2.0,
                score_close(expected, actual, tolerance=0.01),
                "",
            ),
        )
        assert run.pass_rate() == 1.0
        assert run.mean_score() == 1.0

    def test_compare_runs_finds_regressions(self):
        dataset = EvalDataset(name="d")
        dataset.add_case({"x": 1}, expected=1)
        dataset.add_case({"x": 2}, expected=2)
        baseline = run_eval(
            dataset, "baseline", lambda c: c["x"], lambda e, a: (e == a, 1.0 if e == a else 0.0, "")
        )
        candidate = run_eval(
            dataset,
            "candidate",
            lambda c: c["x"] if c["x"] == 1 else 99,
            lambda e, a: (e == a, 1.0 if e == a else 0.0, ""),
        )
        comparison = compare_runs(baseline, candidate)
        assert len(comparison["regressions"]) == 1
        assert comparison["mean_score_delta"] == -0.5

    def test_score_close_boundaries(self):
        assert score_close(100.0, 100.0) == 1.0
        assert score_close(100.0, 110.0) == 0.0
        assert 0.0 < score_close(100.0, 103.0) < 1.0

    def test_incomparable_datasets_rejected(self):
        d1, d2 = EvalDataset(name="a"), EvalDataset(name="b")
        r1 = run_eval(d1, "x", lambda c: c, lambda e, a: (True, 1.0, ""))
        r2 = run_eval(d2, "y", lambda c: c, lambda e, a: (True, 1.0, ""))
        with pytest.raises(ValueError):
            compare_runs(r1, r2)

    def test_attach_eval_to_trace(self, clock):
        tracer = Tracer(clock=clock)
        dataset = EvalDataset(name="d")
        dataset.add_case({"x": 1}, expected=1)
        run = run_eval(dataset, "r", lambda c: c["x"], lambda e, a: (e == a, 1.0, ""))
        with tracer.trace("t") as trace:
            from rain_atlas.observability.evals import attach_eval_to_trace

            attach_eval_to_trace(trace.trace, run, "eval")
        names = {s.name for s in trace.trace.scores}
        assert "eval.mean" in names and "eval.pass_rate" in names
