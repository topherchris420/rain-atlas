"""Evaluation datasets and experiment comparisons.

Reconstructs the reference's evaluation concepts at the data-model level:
named datasets of cases, runs of a system over those cases, scored outcomes,
and comparisons between named runs (for example two configurations of one
experiment, or a component against the integrated architecture).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..canonical import canonical_bytes, sha256_bytes
from .models import Trace


@dataclass
class EvalCase:
    """One case in an evaluation dataset."""

    id: str
    input: Any
    expected: Any
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalDataset:
    """A named, versioned collection of cases with expected outcomes."""

    name: str
    cases: list[EvalCase] = field(default_factory=list)
    version: int = 1
    description: str = ""

    def add_case(self, input: Any, expected: Any, **metadata: Any) -> EvalCase:
        case = EvalCase(
            id=sha256_bytes(canonical_bytes({"input": input, "n": len(self.cases)}))[:16],
            input=input,
            expected=expected,
            metadata=metadata,
        )
        self.cases.append(case)
        return case

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "cases": [case.to_dict() for case in self.cases],
        }


def score_close(expected: float, actual: float, tolerance: float = 0.05) -> float:
    """A common scorer: 1.0 within tolerance, linear falloff otherwise."""

    if expected == 0:
        return 1.0 if abs(actual) <= tolerance else 0.0
    relative = abs(actual - expected) / abs(expected)
    return round(max(0.0, 1.0 - relative / tolerance), 4) if relative <= tolerance else 0.0


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    score: float
    actual: Any = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalRun:
    """One execution of a system over a dataset with recorded scores."""

    dataset_name: str
    run_name: str
    results: list[CaseResult] = field(default_factory=list)
    trace_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset_name,
            "run": self.run_name,
            "results": [result.to_dict() for result in self.results],
            "trace_id": self.trace_id,
        }

    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(r.score for r in self.results) / len(self.results), 6)

    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(1 for r in self.results if r.passed) / len(self.results), 6)


def run_eval(
    dataset: EvalDataset,
    run_name: str,
    system: Callable[[Any], Any],
    scorer: Callable[[Any, Any], tuple[bool, float, str]],
) -> EvalRun:
    """Execute *system* over every case; *scorer* returns (passed, score, detail)."""

    run = EvalRun(dataset_name=dataset.name, run_name=run_name)
    for case in dataset.cases:
        actual = system(case.input)
        passed, score, detail = scorer(case.expected, actual)
        run.results.append(
            CaseResult(
                case_id=case.id,
                passed=passed,
                score=score,
                actual=actual,
                detail=detail,
            )
        )
    return run


def compare_runs(baseline: EvalRun, candidate: EvalRun) -> dict:
    """Feature-level comparison of two runs over the same dataset."""

    if baseline.dataset_name != candidate.dataset_name:
        raise ValueError("runs must come from the same dataset to be comparable")
    by_id_candidate = {r.case_id: r for r in candidate.results}
    regressions = [
        r.case_id for r in baseline.results if r.passed and not by_id_candidate.get(r.case_id, r).passed
    ]
    improvements = [
        r.case_id for r in baseline.results if not r.passed and by_id_candidate.get(r.case_id, r).passed
    ]
    return {
        "dataset": baseline.dataset_name,
        "baseline": {
            "run": baseline.run_name,
            "mean_score": baseline.mean_score(),
            "pass_rate": baseline.pass_rate(),
        },
        "candidate": {
            "run": candidate.run_name,
            "mean_score": candidate.mean_score(),
            "pass_rate": candidate.pass_rate(),
        },
        "regressions": regressions,
        "improvements": improvements,
        "mean_score_delta": round(candidate.mean_score() - baseline.mean_score(), 6),
    }


def attach_eval_to_trace(trace: Trace, run: EvalRun, score_name: str) -> None:
    """Record a run's aggregate scores on a trace for evidence export."""

    trace.add_score(f"{score_name}.mean", run.mean_score())
    trace.add_score(f"{score_name}.pass_rate", run.pass_rate())
    for result in run.results:
        if not result.passed:
            trace.add_score(
                f"{score_name}.case_failed", 0.0, comment=f"case {result.case_id}: {result.detail}"
            )
