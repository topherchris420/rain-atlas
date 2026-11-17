"""Unified R.A.I.N. integration: the reconstructed capabilities connected.

This package connects the independently reconstructed replicas into one
scientific intelligence loop::

    hypothesis proposal (inference replica, model or scripted)
        → protocol compilation (Infera replica)
        → simulation twin (Arga replica)
        → agent coordination with approvals (Omnara/Maxxwell replica)
        → observability traces (Langfuse replica)
        → scientific memory (Mem0 replica)
        → local-first knowledge (Epicenter replica)
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
