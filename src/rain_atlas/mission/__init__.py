"""Research Mission Controller: persistent agent orchestration.

Capabilities:

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

The controller is single-process and deterministic by design; it does
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
