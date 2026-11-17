"""Mission, task, agent and approval models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..canonical import canonical_bytes, sha256_bytes

GENERATIONS = ("scripted", "model", "human")


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = (
        PENDING,
        RUNNING,
        AWAITING_APPROVAL,
        APPROVED,
        COMPLETED,
        FAILED,
        CANCELLED,
    )
    TERMINAL = (COMPLETED, FAILED, CANCELLED)


@dataclass
class Transition:
    """One recorded state change: who caused it, when, and why."""

    from_status: str
    to_status: str
    actor: str
    generation: str
    timestamp_ms: float
    reason: str = ""

    def __post_init__(self) -> None:
        if self.generation not in GENERATIONS:
            raise ValueError(f"generation {self.generation!r} must be one of {GENERATIONS}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Task:
    """One unit of research work owned by an agent."""

    id: str
    name: str
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    dependencies: list[str] = field(default_factory=list)
    max_retries: int = 0
    status: str = TaskStatus.PENDING
    attempts: int = 0
    assigned_agent: str | None = None
    result: Any = None
    error: str = ""
    transitions: list[Transition] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def dependencies_met(self, completed: set[str]) -> bool:
        return all(dep in completed for dep in self.dependencies)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "inputs": self.inputs,
            "requires_approval": self.requires_approval,
            "dependencies": list(self.dependencies),
            "max_retries": self.max_retries,
            "status": self.status,
            "attempts": self.attempts,
            "assigned_agent": self.assigned_agent,
            "result": self.result,
            "error": self.error,
            "transitions": [t.to_dict() for t in self.transitions],
            "findings": list(self.findings),
        }


@dataclass
class AgentHandle:
    """A registered executor. *generation* records how its work is produced."""

    agent_id: str
    role: str
    generation: str  # scripted | model | human
    execute: Callable[[Task, "Mission"], Any]
    describe: str = ""

    def __post_init__(self) -> None:
        if self.generation not in GENERATIONS:
            raise ValueError(f"generation {self.generation!r} must be one of {GENERATIONS}")

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "generation": self.generation,
            "describe": self.describe,
        }


@dataclass
class ApprovalRequest:
    """A question that pauses a task until a human resolves it."""

    id: str
    task_id: str
    question: str
    options: list[str] = field(default_factory=lambda: ["approve", "reject"])
    resolution: str | None = None
    resolved_by: str | None = None
    resolved_at_ms: float | None = None
    comment: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.resolution is not None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Mission:
    """A persistent research mission: tasks, agents, approvals and outcomes."""

    id: str
    name: str
    question: str
    tasks: dict[str, Task] = field(default_factory=dict)
    agents: dict[str, AgentHandle] = field(default_factory=dict)
    approvals: dict[str, ApprovalRequest] = field(default_factory=dict)
    created_at_ms: float = 0.0

    @staticmethod
    def new_id(name: str, sequence: int) -> str:
        return sha256_bytes(canonical_bytes(["mission", name, sequence]))[:16]

    def submit(
        self,
        name: str,
        *,
        description: str = "",
        inputs: dict[str, Any] | None = None,
        requires_approval: bool = False,
        dependencies: list[str] | None = None,
        max_retries: int = 0,
        agent: str | None = None,
    ) -> Task:
        task_id = sha256_bytes(canonical_bytes(["task", self.id, name, len(self.tasks)]))[:16]
        task = Task(
            id=task_id,
            name=name,
            description=description,
            inputs=dict(inputs or {}),
            requires_approval=requires_approval,
            dependencies=list(dependencies or []),
            max_retries=max_retries,
            assigned_agent=agent,
        )
        self.tasks[task_id] = task
        return task

    def completed_ids(self) -> set[str]:
        return {task_id for task_id, task in self.tasks.items() if task.status == TaskStatus.COMPLETED}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "question": self.question,
            "created_at_ms": self.created_at_ms,
            "tasks": {task_id: task.to_dict() for task_id, task in sorted(self.tasks.items())},
            "agents": {agent_id: agent.to_dict() for agent_id, agent in sorted(self.agents.items())},
            "approvals": {
                approval_id: approval.to_dict() for approval_id, approval in sorted(self.approvals.items())
            },
        }
