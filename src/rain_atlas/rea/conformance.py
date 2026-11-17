"""Reference-versus-replica conformance harness.

A conformance case runs the *same* scenario twice: once against the reference
system (or a recorded reference behavior), once against the replica. Outputs
are compared with an explicit comparator -- never with an arbitrary
similarity score. The recorded outcome states what was compared, what the
reference was, and whether it passed.

Comparators return ``(passed: bool, details: str)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import ConformanceRecord


@dataclass
class ConformanceCase:
    """One named behavior scenario run against reference and replica."""

    name: str
    description: str
    run: Callable[[], dict[str, Any]]
    # ``run`` returns {"reference": ..., "replica": ...} plus any context.
    comparator: "Comparator"
    reference: str = ""
    ran_at: str = ""


@dataclass
class Comparator:
    """Structural comparison strategies for conformance outputs."""

    strategy: str  # exact | keys | sequence | predicate
    keys: list[str] = field(default_factory=list)
    predicate: Callable[[Any, Any], bool] | None = None

    def compare(self, reference: Any, replica: Any) -> tuple[bool, str]:
        if self.strategy == "exact":
            return reference == replica, "exact structural equality"
        if self.strategy == "keys":
            if not isinstance(reference, dict) or not isinstance(replica, dict):
                return False, "keys comparator requires dict outputs"
            missing = [key for key in self.keys if key not in replica]
            if missing:
                return False, f"replica output missing keys {missing}"
            mismatches = [key for key in self.keys if reference.get(key) != replica.get(key)]
            return not mismatches, f"compared keys {self.keys}; mismatches {mismatches}"
        if self.strategy == "sequence":
            if not isinstance(reference, list) or not isinstance(replica, list):
                return False, "sequence comparator requires list outputs"
            if len(reference) != len(replica):
                return False, f"length {len(reference)} != {len(replica)}"
            for i, (ref_item, rep_item) in enumerate(zip(reference, replica)):
                if not self._items_equal(ref_item, rep_item):
                    return False, f"sequence differs at index {i}"
            return True, f"sequence of {len(reference)} items matched"
        if self.strategy == "predicate":
            if self.predicate is None:
                return False, "predicate comparator requires a predicate"
            return bool(self.predicate(reference, replica)), "custom predicate"
        return False, f"unknown comparator strategy {self.strategy!r}"

    @staticmethod
    def _items_equal(reference: Any, replica: Any) -> bool:
        if isinstance(reference, dict) and isinstance(replica, dict):
            return reference.keys() == replica.keys() and all(
                Comparator._items_equal(reference[key], replica[key]) for key in reference
            )
        if isinstance(reference, list) and isinstance(replica, list):
            return len(reference) == len(replica) and all(
                Comparator._items_equal(a, b) for a, b in zip(reference, replica)
            )
        return reference == replica


@dataclass
class ConformanceResult:
    """The outcome of one executed conformance case."""

    case: str
    status: str  # passed | failed | errored | skipped
    reference: str
    comparator: str
    details: str = ""
    reference_output: Any = None
    replica_output: Any = None

    def to_record(self) -> ConformanceRecord:
        if self.status == "passed":
            status = "passed"
        elif self.status == "errored":
            status = "errored"
        else:
            status = "failed"
        return ConformanceRecord(
            case=self.case,
            status=status,
            reference=self.reference,
            comparator=self.comparator,
            details=self.details,
        )


class ConformanceHarness:
    """Runs cases and records outcomes as :class:`ConformanceRecord` values."""

    def __init__(self, *, reference_label: str) -> None:
        self.reference_label = reference_label
        self.records: list[ConformanceRecord] = []

    def run(self, case: ConformanceCase) -> ConformanceResult:
        try:
            outputs = case.run()
        except Exception as exc:  # noqa: BLE001 - record the failure, never hide it
            result = ConformanceResult(
                case=case.name,
                status="errored",
                reference=case.reference or self.reference_label,
                comparator=case.comparator.strategy,
                details=f"case raised {type(exc).__name__}: {exc}",
            )
        else:
            passed, details = case.comparator.compare(outputs.get("reference"), outputs.get("replica"))
            result = ConformanceResult(
                case=case.name,
                status="passed" if passed else "failed",
                reference=case.reference or self.reference_label,
                comparator=case.comparator.strategy,
                details=details,
                reference_output=outputs.get("reference"),
                replica_output=outputs.get("replica"),
            )
        self.records.append(result.to_record())
        return result

    def run_all(self, cases: list[ConformanceCase]) -> list[ConformanceResult]:
        return [self.run(case) for case in cases]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts
