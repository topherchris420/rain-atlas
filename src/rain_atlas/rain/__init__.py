"""Unified R.A.I.N. integration: the reconstructed capabilities connected.

This package connects the independently reconstructed replicas into one
scientific intelligence loop::

    hypothesis proposal (inference provider, model or scripted)
        → protocol compilation
        → simulation twin
        → agent coordination with approvals
        → observability traces
        → scientific memory
        → local-first knowledge
        → evaluation and replication
        → ATLAS evidence ledger
"""

from .experiment import CentralExperimentResult, run_central_experiment
from .models import CandidateModels, GridCondition
from .models import Observation as ModelObservation
from .policies import (
    AdaptiveSelector,
    GridSelector,
    PolicyName,
    RandomSelector,
    select_condition,
)
from .vertical import VerticalSliceResult, run_vertical_slice

__all__ = [
    "AdaptiveSelector",
    "CandidateModels",
    "CentralExperimentResult",
    "GridCondition",
    "GridSelector",
    "ModelObservation",
    "PolicyName",
    "RandomSelector",
    "VerticalSliceResult",
    "run_central_experiment",
    "run_vertical_slice",
    "select_condition",
]
