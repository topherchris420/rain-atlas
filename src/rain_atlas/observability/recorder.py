"""The :class:`Tracer`: hierarchical, deterministic trace recording.

Usage::

    tracer = Tracer(clock=monotonic_counter)
    with tracer.trace("mission-run", session_id="m1") as trace:
        with trace.span("protocol-compile") as span:
            span.input = {...}
            span.output = {...}
            with span.generation("hypothesis-model", model="mock-1") as gen:
                gen.record_usage(input=10, output=4)
        trace.add_score("experiment_quality", 0.83)

Timing uses an injectable clock (milliseconds, monotonic). The default clock
is :func:`time.perf_counter` scaled to milliseconds.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..canonical import canonical_bytes
from .models import (
    CostDetails,
    Observation,
    ObservationLevel,
    ObservationType,
    Score,
    Trace,
    UsageDetails,
    _new_id,
)

if TYPE_CHECKING:
    from ..ledger.store import Ledger


def default_clock() -> float:
    return time.perf_counter() * 1000.0


class Tracer:
    """Creates traces and nested observations with an injectable clock."""

    def __init__(self, clock: Any | None = None) -> None:
        self._clock = clock or default_clock
        self._sequence = 0
        self.traces: list[Trace] = []

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def trace(
        self,
        name: str,
        *,
        session_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        environment: str = "local",
    ) -> "TraceScope":
        now = self._clock()
        trace = Trace(
            id=Trace.new_id(name, now, self._next_sequence()),
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata or {},
            tags=list(tags or []),
            environment=environment,
            timestamp_ms=now,
        )
        self.traces.append(trace)
        return TraceScope(tracer=self, trace=trace)

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict:
        return {"traces": [trace.to_dict() for trace in self.traces]}

    def export_to_ledger(self, ledger: "Ledger", *, experiment: str, author: dict) -> str:
        """Store every trace as a ledger object; append a note record.

        Returns the object reference holding the full trace bundle. Each trace
        also becomes its own object so experiments can reference individual
        executions.
        """

        trace_refs = []
        for trace in self.traces:
            trace_refs.append(ledger.put_json({"trace": trace.to_dict()}))
        bundle_ref = ledger.put_json({"experiment": experiment, "traces": trace_refs})
        ledger.append(
            "note",
            {
                "experiment": experiment,
                "text": f"observability export with {len(self.traces)} traces",
                "author": author,
                "bundle_object": bundle_ref,
            },
        )
        return bundle_ref

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(self.to_dict()))
        return path


class _ObservationScope:
    """Context manager for one observation; also the parent for children."""

    def __init__(self, tracer: Tracer, observation: Observation, trace: Trace) -> None:
        self._tracer = tracer
        self.observation = observation
        self._trace = trace

    # -- fluent recorders ---------------------------------------------------

    def record_input(self, value: Any) -> "_ObservationScope":
        self.observation.input = value
        return self

    def record_output(self, value: Any) -> "_ObservationScope":
        self.observation.output = value
        return self

    def record_metadata(self, **values: Any) -> "_ObservationScope":
        self.observation.metadata.update(values)
        return self

    def record_level(self, level: str, message: str = "") -> "_ObservationScope":
        self.observation.level = level
        self.observation.status_message = message
        return self

    def record_usage(
        self,
        *,
        input: int = 0,
        output: int = 0,
        total: int | None = None,
        input_cost: float = 0.0,
        output_cost: float = 0.0,
        total_cost: float | None = None,
        time_to_first_token_ms: float | None = None,
    ) -> "_ObservationScope":
        self.observation.usage = UsageDetails(
            input=input,
            output=output,
            total=total if total is not None else input + output,
            time_to_first_token_ms=time_to_first_token_ms,
        )
        self.observation.cost = CostDetails(
            input=input_cost,
            output=output_cost,
            total=total_cost if total_cost is not None else input_cost + output_cost,
        )
        return self

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> "_ObservationScope":
        self.observation.start_time_ms = self._tracer._clock()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.observation.end_time_ms = self._tracer._clock()
        if exc is not None:
            self.observation.level = ObservationLevel.ERROR
            self.observation.status_message = f"{type(exc).__name__}: {exc}"
        return False  # never swallow exceptions

    # -- child factories ------------------------------------------------------

    def _child(self, obs_type: str, name: str, **kwargs: Any) -> "_ObservationScope":
        observation = Observation(
            id=_new_id("obs", self._trace.id, name, self._tracer._clock(), self._tracer._next_sequence()),
            trace_id=self._trace.id,
            type=obs_type,
            name=name,
            parent_observation_id=self.observation.id,
            **kwargs,
        )
        self._trace.observations.append(observation)
        return _ObservationScope(self._tracer, observation, self._trace)

    def span(self, name: str, **kwargs: Any) -> "_ObservationScope":
        return self._child(ObservationType.SPAN, name, **kwargs)

    def generation(self, name: str, *, model: str = "", **kwargs: Any) -> "_ObservationScope":
        return self._child(ObservationType.GENERATION, name, model=model, **kwargs)

    def event(self, name: str, **kwargs: Any) -> "_ObservationScope":
        return self._child(ObservationType.EVENT, name, **kwargs)

    def tool(self, name: str, **kwargs: Any) -> "_ObservationScope":
        return self._child(ObservationType.TOOL, name, **kwargs)

    def retriever(self, name: str, **kwargs: Any) -> "_ObservationScope":
        return self._child(ObservationType.RETRIEVER, name, **kwargs)


class TraceScope(_ObservationScope):
    """Root scope of one trace."""

    def __init__(self, tracer: Tracer, trace: Trace) -> None:
        super().__init__(
            tracer,
            Observation(
                id=Trace.new_id(trace.name, trace.timestamp_ms, 0),
                trace_id=trace.id,
                type=ObservationType.SPAN,
                name=trace.name,
            ),
            trace,
        )
        self.trace = trace
        trace.observations.append(self.observation)

    def add_score(self, name: str, value: Any, *, comment: str = "") -> Score:
        return self.trace.add_score(name, value, comment=comment)

    def __enter__(self) -> "TraceScope":
        super().__enter__()
        return self
