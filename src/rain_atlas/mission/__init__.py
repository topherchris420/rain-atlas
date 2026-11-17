"""Research Mission Controller: an Omnara/Maxxwell-inspired replica.

Target: Omnara (Apache-2.0) and Maxxwell by Rindler, reconstructed by
Recursive Engineering & Analysis. See ``rain_atlas.rea.investigations.omnara``
and ``rain_atlas.rea.investigations.maxxwell`` for the recorded evidence.

Reconstructed capabilities:

* persistent tasks with an explicit state machine
  (``pending → running → awaiting_approval → … → completed``);
* delegation to registered agents whose *generation* is always recorded
  (``scripted``, ``model`` or ``human``) so model-driven reasoning is never
  confused with scripted policies;
* approval requests that pause a task until a human resolves them;
* failure recovery with bounded, recorded retries;
* supervision: query, cancel, and human takeover of a task;
* observability hooks: every transition is traced;
* memory hooks: findings are written to scientific memory.

Deviations from the references are recorded in the investigation packages:
this controller is single-process and deterministic by design, and it does
not manage OS processes, remote machines or third-party runtimes.
"""

from .controller import (
    ApprovalPause,
    MissionController,
    MissionStatus,
    approval_granted,
)
from .models import (
    AgentHandle,
    ApprovalRequest,
    Mission,
    Task,
    TaskStatus,
    Transition,
)

__all__ = [
    "AgentHandle",
    "ApprovalPause",
    "ApprovalRequest",
    "Mission",
    "MissionController",
    "MissionStatus",
    "Task",
    "TaskStatus",
    "Transition",
    "approval_granted",
]
