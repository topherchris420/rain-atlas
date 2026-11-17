"""Deterministic protocol compilation and validation.

The compiler works with a declared *variable lexicon* supplied by the
caller (the research domain). A hypothesis is parsed with transparent
templates::

    "increasing <variable> increases <measure>"
    "<variable> controls <measure>"
    "<variable> has no effect on <measure>"

producing a :class:`ProtocolSpec` with an independent variable, a dependent
measure, simulated instruments, ordered steps, preregistered acceptance
criteria and safety constraints.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..canonical import canonical_bytes, sha256_bytes


class ValidationError(ValueError):
    """A protocol that cannot be compiled or is unsafe to execute."""


@dataclass
class ProtocolStep:
    """One executable action of a protocol."""

    index: int
    action: str  # set-variable | run-ensemble | measure | compare | record
    instrument: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProtocolSpec:
    """A validated, executable experimental specification."""

    protocol_id: str
    question: str
    hypothesis: str
    null_hypothesis: str
    independent_variable: str
    dependent_measure: str
    control_conditions: dict[str, Any] = field(default_factory=dict)
    instruments: list[str] = field(default_factory=list)
    steps: list[ProtocolStep] = field(default_factory=list)
    acceptance: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "protocol_id": self.protocol_id,
            "question": self.question,
            "hypothesis": self.hypothesis,
            "null_hypothesis": self.null_hypothesis,
            "independent_variable": self.independent_variable,
            "dependent_measure": self.dependent_measure,
            "control_conditions": self.control_conditions,
            "instruments": list(self.instruments),
            "steps": [step.to_dict() for step in self.steps],
            "acceptance": self.acceptance,
            "safety": self.safety,
            "variables": self.variables,
        }

    def digest(self) -> str:
        return sha256_bytes(canonical_bytes(self.to_dict()))

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.steps:
            problems.append("protocol has no steps")
        for step in self.steps:
            if step.instrument not in self.instruments:
                problems.append(f"step {step.index} uses undeclared instrument {step.instrument!r}")
        if not self.acceptance:
            problems.append("protocol has no preregistered acceptance criteria")
        if not self.safety.get("physical_actuation") == "forbidden":
            problems.append("protocol does not forbid physical actuation")
        return problems


_HYPOTHESIS_RE = re.compile(
    r"^(?:increasing|raising|higher)\s+(?P<iv>[a-z\s]+?)\s+"
    r"(?:increases|improves|raises|strengthens|controls|affects)\s+(?P<dv>[a-z\s]+?)\.?$",
    re.IGNORECASE,
)
_NULL_RE = re.compile(
    r"^(?P<iv>[a-z\s]+?)\s+has no effect on\s+(?P<dv>[a-z\s]+?)\.?$",
    re.IGNORECASE,
)
_RELATION_RE = re.compile(
    r"^(?P<iv>[a-z\s]+?)\s+(?:controls|affects|determines|increases|decreases|"
    r"improves|reduces)\s+(?P<dv>[a-z\s]+?)\.?$",
    re.IGNORECASE,
)


class ProtocolCompiler:
    """Compiles research questions and hypotheses into validated protocols."""

    def __init__(self, variable_lexicon: dict[str, dict[str, Any]]) -> None:
        """*variable_lexicon* maps lowercase variable names to their metadata:

        ``{"coupling strength": {"symbol": "k", "range": [0.0, 1.0],
        "default_points": 9, "instrument": "oscillator-bench", "measure_of":
        "phase locking"}}``
        """

        self.lexicon = {name.lower(): meta for name, meta in variable_lexicon.items()}
        for name, meta in self.lexicon.items():
            for required in ("symbol", "range", "instrument"):
                if required not in meta:
                    raise ValidationError(f"lexicon entry {name!r} lacks {required!r}")
            low, high = meta["range"]
            if not low < high:
                raise ValidationError(f"lexicon entry {name!r} has an empty range")

    def compile(
        self,
        question: str,
        hypothesis: str,
        *,
        points: int | None = None,
        replicates: int = 8,
        acceptance_threshold: float = 0.7,
    ) -> ProtocolSpec:
        iv, dv = self._parse_hypothesis(hypothesis)
        meta = self.lexicon.get(iv)
        if meta is None:
            raise ValidationError(
                f"hypothesis variable {iv!r} is not in the declared lexicon ({sorted(self.lexicon)})"
            )
        if points is not None and points < 2:
            raise ValidationError("an experiment needs at least two points")
        n_points = points or int(meta.get("default_points", 9))
        replicates = max(2, replicates)
        instrument = str(meta["instrument"])
        low, high = meta["range"]
        protocol_id = sha256_bytes(canonical_bytes(["protocol", question, hypothesis, n_points, replicates]))[
            :16
        ]
        spec = ProtocolSpec(
            protocol_id=protocol_id,
            question=question,
            hypothesis=hypothesis,
            null_hypothesis=f"{iv} has no effect on {dv}",
            independent_variable=iv,
            dependent_measure=dv,
            instruments=[instrument],
            acceptance={
                "metric": f"{dv} at the highest {iv}",
                "threshold": acceptance_threshold,
                "comparison": "greater_than",
                "registered_before_execution": True,
            },
            safety={
                "physical_actuation": "forbidden",
                "instruments": "simulated only",
                "human_approval_required_for": "any change to acceptance criteria",
            },
            variables={iv: meta},
            control_conditions={"seed": None, "replicates": replicates},
        )
        spec.steps = self._default_steps(
            instrument=instrument, meta=meta, n_points=n_points, replicates=replicates
        )
        problems = spec.problems()
        if problems:
            raise ValidationError("; ".join(problems))
        return spec

    def _parse_hypothesis(self, hypothesis: str) -> tuple[str, str]:
        text = hypothesis.strip().rstrip(".")
        match = _HYPOTHESIS_RE.match(text)
        if match:
            return match.group("iv").strip().lower(), match.group("dv").strip().lower()
        match = _NULL_RE.match(text)
        if match:
            return match.group("iv").strip().lower(), match.group("dv").strip().lower()
        match = _RELATION_RE.match(text)
        if match:
            return match.group("iv").strip().lower(), match.group("dv").strip().lower()
        # Fall back: any declared variable present anywhere in the hypothesis.
        for name in sorted(self.lexicon, key=len, reverse=True):
            if name in text.lower():
                relation = _RELATION_RE.search(text)
                if relation:
                    return (
                        relation.group("iv").strip().lower(),
                        relation.group("dv").strip().lower(),
                    )
                return name, "the dependent measure"
        raise ValidationError(
            f"could not parse hypothesis {hypothesis!r}; expected shapes like "
            "'increasing <variable> increases <measure>'"
        )

    def _default_steps(
        self, *, instrument: str, meta: dict[str, Any], n_points: int, replicates: int
    ) -> list[ProtocolStep]:
        low, high = meta["range"]
        values = [round(low + (high - low) * i / (n_points - 1), 6) for i in range(n_points)]
        steps = [
            ProtocolStep(
                index=1,
                action="set-variable",
                instrument=instrument,
                parameters={"variable": meta["symbol"], "values": values},
            ),
            ProtocolStep(
                index=2,
                action="run-ensemble",
                instrument=instrument,
                parameters={"replicates": replicates, "measure": "dependent"},
            ),
            ProtocolStep(
                index=3,
                action="measure",
                instrument=instrument,
                parameters={"statistic": "mean-over-ensemble"},
            ),
            ProtocolStep(
                index=4,
                action="compare",
                instrument=instrument,
                parameters={"against": "preregistered acceptance"},
            ),
            ProtocolStep(
                index=5,
                action="record",
                instrument=instrument,
                parameters={"destination": "evidence ledger"},
            ),
        ]
        return steps
