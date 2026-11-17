"""Trace and observation models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..canonical import canonical_bytes, sha256_bytes


class ObservationType:
    SPAN = "SPAN"
    GENERATION = "GENERATION"
    EVENT = "EVENT"
    TOOL = "TOOL"
    RETRIEVER = "RETRIEVER"
    EVALUATOR = "EVALUATOR"
    EMBEDDING = "EMBEDDING"
    GUARDRAIL = "GUARDRAIL"

    ALL = (SPAN, GENERATION, EVENT, TOOL, RETRIEVER, EVALUATOR, EMBEDDING, GUARDRAIL)


class ObservationLevel:
    DEBUG = "DEBUG"
    DEFAULT = "DEFAULT"
    WARNING = "WARNING"
    ERROR = "ERROR"

    ALL = (DEBUG, DEFAULT, WARNING, ERROR)


def _new_id(*parts: Any) -> str:
    return sha256_bytes(canonical_bytes(list(parts)))[:20]


@dataclass
class UsageDetails:
    input: int = 0
    output: int = 0
    total: int = 0
    time_to_first_token_ms: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CostDetails:
    input: float = 0.0
    output: float = 0.0
    total: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Observation:
    """One node in a trace tree (a span, generation or event)."""

    id: str
    trace_id: str
    type: str
    name: str
    parent_observation_id: str | None = None
    start_time_ms: float = 0.0
    end_time_ms: float | None = None
    level: str = ObservationLevel.DEFAULT
    status_message: str = ""
    version: str = ""
    input: Any = None
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    model_parameters: dict[str, Any] = field(default_factory=dict)
    usage: UsageDetails | None = None
    cost: CostDetails | None = None
    prompt_name: str = ""
    prompt_version: int | None = None

    def __post_init__(self) -> None:
        if self.type not in ObservationType.ALL:
            raise ValueError(f"observation type {self.type!r} must be one of {ObservationType.ALL}")
        if self.level not in ObservationLevel.ALL:
            raise ValueError(f"level {self.level!r} must be one of {ObservationLevel.ALL}")

    @property
    def latency_ms(self) -> float | None:
        if self.end_time_ms is None:
            return None
        return round(self.end_time_ms - self.start_time_ms, 3)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "traceId": self.trace_id,
            "type": self.type,
            "name": self.name,
            "parentObservationId": self.parent_observation_id,
            "startTime": self.start_time_ms,
            "endTime": self.end_time_ms,
            "latency": self.latency_ms,
            "level": self.level,
            "statusMessage": self.status_message,
            "version": self.version,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata,
            "model": self.model,
            "modelParameters": self.model_parameters,
            "usageDetails": self.usage.to_dict() if self.usage else None,
            "costDetails": self.cost.to_dict() if self.cost else None,
            "promptName": self.prompt_name,
            "promptVersion": self.prompt_version,
        }


@dataclass
class Score:
    """A named evaluation value attached to a trace or observation."""

    id: str
    trace_id: str
    name: str
    value: Any
    observation_id: str | None = None
    comment: str = ""
    data_type: str = "numeric"  # numeric | categorical | boolean

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "traceId": self.trace_id,
            "name": self.name,
            "value": self.value,
            "observationId": self.observation_id,
            "comment": self.comment,
            "dataType": self.data_type,
        }


@dataclass
class Trace:
    """A recorded execution: one root observation tree plus scores."""

    id: str
    name: str = ""
    session_id: str = ""
    user_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    environment: str = "local"
    release: str = ""
    input: Any = None
    output: Any = None
    timestamp_ms: float = 0.0
    observations: list[Observation] = field(default_factory=list)
    scores: list[Score] = field(default_factory=list)

    @staticmethod
    def new_id(name: str, timestamp_ms: float, sequence: int) -> str:
        return _new_id("trace", name, timestamp_ms, sequence)

    def root_observations(self) -> list[Observation]:
        return [o for o in self.observations if o.parent_observation_id is None]

    def children_of(self, observation_id: str) -> list[Observation]:
        return [o for o in self.observations if o.parent_observation_id == observation_id]

    def total_usage(self) -> dict:
        usage = UsageDetails()
        for obs in self.observations:
            if obs.usage:
                usage.input += obs.usage.input
                usage.output += obs.usage.output
                usage.total += obs.usage.total
        return usage.to_dict()

    def total_cost(self) -> float:
        return round(sum(o.cost.total for o in self.observations if o.cost), 6)

    def errors(self) -> list[Observation]:
        return [o for o in self.observations if o.level == ObservationLevel.ERROR]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "sessionId": self.session_id,
            "userId": self.user_id,
            "metadata": self.metadata,
            "tags": self.tags,
            "environment": self.environment,
            "release": self.release,
            "input": self.input,
            "output": self.output,
            "timestamp": self.timestamp_ms,
            "observations": [o.to_dict() for o in self.observations],
            "scores": [s.to_dict() for s in self.scores],
        }

    def add_score(
        self, name: str, value: Any, *, comment: str = "", observation_id: str | None = None
    ) -> Score:
        score = Score(
            id=_new_id("score", self.id, name, value),
            trace_id=self.id,
            name=name,
            value=value,
            observation_id=observation_id,
            comment=comment,
        )
        self.scores.append(score)
        return score
