"""Scientific Observability Engine.

Traces, hierarchical observations (spans, generations, events, tools,
evaluators), usage/cost details, latency and scores:

* everything is local-first JSON; no server or ingestion API is required;
* timing comes from an injectable monotonic clock, so traces are exactly
  reproducible in tests and replays;
* traces export directly into the ATLAS evidence ledger.
"""

from .evals import (
    EvalCase,
    EvalDataset,
    EvalRun,
    attach_eval_to_trace,
    compare_runs,
    run_eval,
    score_close,
)
from .models import Observation, ObservationLevel, ObservationType, Score, Trace
from .recorder import Tracer

__all__ = [
    "EvalCase",
    "EvalDataset",
    "EvalRun",
    "Observation",
    "ObservationLevel",
    "ObservationType",
    "Score",
    "Trace",
    "Tracer",
    "attach_eval_to_trace",
    "compare_runs",
    "run_eval",
    "score_close",
]
