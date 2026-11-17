"""The :class:`MissionController`: deterministic agent orchestration.

Execution is *step-driven*: each call to :meth:`MissionController.step`
performs at most one unit of work (one task assignment, one task execution,
or one approval-resolution effect). This makes concurrent-looking missions
reproducible and testable: the same mission and the same clock always
produce the same history.

Agents pause their own execution for human decisions by calling
:meth:`MissionController.request_approval`, which raises :class:`ApprovalPause`.
The controller records the pause, waits for a human resolution, and resumes
the task afterwards -- never silently.
"""

from __future__ import annotations

from typing import Any, Callable

from ..canonical import canonical_bytes, sha256_bytes
from .models import (
    AgentHandle,
    ApprovalRequest,
    Mission,
    Task,
    TaskStatus,
    Transition,
)


class MissionStatus:
    RUNNING = "running"
    COMPLETE = "complete"
    BLOCKED = "blocked"  # only unresolved approvals remain
    STALLED = "stalled"  # unmet dependencies (a cycle or missing task)


class ApprovalPause(Exception):
    """Raised by an agent to pause its task until an approval is resolved."""


def approval_granted(mission: Mission, task: Task) -> bool:
    """True when every approval requested by *task* has been approved."""

    return all(
        approval.resolution == "approve"
        for approval in mission.approvals.values()
        if approval.task_id == task.id
    )


def _has_open_approval(mission: Mission, task: Task) -> bool:
    return any(
        not approval.is_resolved for approval in mission.approvals.values() if approval.task_id == task.id
    )


class MissionController:
    """Coordinates agents, tasks, approvals and supervision for one mission."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        tracer: Any | None = None,
        memory: Any | None = None,
        default_agent: str | None = None,
    ) -> None:
        import time

        self._clock = clock or (lambda: time.time() * 1000.0)
        self._tracer = tracer
        self._memory = memory
        self._default_agent = default_agent
        self._sequence = 0
        self.missions: dict[str, Mission] = {}

    # -- construction --------------------------------------------------------

    def create_mission(self, name: str, question: str = "") -> Mission:
        self._sequence += 1
        mission = Mission(
            id=Mission.new_id(name, self._sequence),
            name=name,
            question=question,
            created_at_ms=self._clock(),
        )
        self.missions[mission.id] = mission
        return mission

    def register_agent(
        self,
        mission: Mission,
        agent_id: str,
        role: str,
        execute: Callable[[Task, Mission], Any],
        *,
        generation: str = "scripted",
        describe: str = "",
    ) -> AgentHandle:
        agent = AgentHandle(
            agent_id=agent_id,
            role=role,
            generation=generation,
            execute=execute,
            describe=describe,
        )
        mission.agents[agent_id] = agent
        return agent

    # -- state machine -------------------------------------------------------

    def _transition(
        self,
        mission: Mission,
        task: Task,
        to_status: str,
        *,
        actor: str,
        generation: str,
        reason: str = "",
    ) -> None:
        from_status = task.status
        task.status = to_status
        task.transitions.append(
            Transition(
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                generation=generation,
                timestamp_ms=self._clock(),
                reason=reason,
            )
        )
        self._trace_transition(mission, task, from_status, to_status, actor, generation, reason)

    def _trace_transition(self, mission, task, from_status, to_status, actor, generation, reason) -> None:
        if self._tracer is None or not self._tracer.traces:
            return
        latest = self._tracer.traces[-1]
        latest.observations.append(
            _make_event(latest, task, from_status, to_status, actor, generation, reason)
        )

    # -- approvals -----------------------------------------------------------

    def request_approval(self, mission: Mission, task: Task, question: str) -> None:
        """Record an approval request and pause *task* (raises ApprovalPause)."""

        approval_id = sha256_bytes(canonical_bytes(["approval", mission.id, task.id, question]))[:16]
        approval = ApprovalRequest(id=approval_id, task_id=task.id, question=question)
        mission.approvals[approval_id] = approval
        self._transition(
            mission,
            task,
            TaskStatus.AWAITING_APPROVAL,
            actor=task.assigned_agent or "controller",
            generation="scripted",
            reason="approval requested",
        )
        raise ApprovalPause(question)

    def resolve_approval(
        self,
        mission: Mission,
        approval_id: str,
        *,
        resolution: str,
        resolved_by: str,
        comment: str = "",
        generation: str = "human",
    ) -> ApprovalRequest:
        approval = mission.approvals[approval_id]
        if approval.is_resolved:
            raise ValueError(f"approval {approval_id} is already resolved")
        if mission.tasks[approval.task_id].status in TaskStatus.TERMINAL:
            raise ValueError(f"task {approval.task_id} is terminal; approval no longer applies")
        if resolution not in approval.options:
            raise ValueError(f"resolution {resolution!r} must be one of {approval.options}")
        approval.resolution = resolution
        approval.resolved_by = resolved_by
        approval.resolved_at_ms = self._clock()
        approval.comment = comment
        task = mission.tasks[approval.task_id]
        if resolution == "approve":
            self._transition(
                mission,
                task,
                TaskStatus.APPROVED,
                actor=resolved_by,
                generation=generation,
                reason=comment or "approved by operator",
            )
        else:
            self._transition(
                mission,
                task,
                TaskStatus.CANCELLED,
                actor=resolved_by,
                generation=generation,
                reason=comment or "rejected by operator",
            )
        return approval

    def pending_approvals(self, mission: Mission) -> list[ApprovalRequest]:
        return [a for a in mission.approvals.values() if not a.is_resolved]

    # -- execution -----------------------------------------------------------

    def _next_task(self, mission: Mission) -> Task | None:
        completed = mission.completed_ids()
        for task in mission.tasks.values():
            if task.status == TaskStatus.PENDING and task.dependencies_met(completed):
                return task
        return None

    def _pick_agent(self, mission: Mission, task: Task) -> AgentHandle:
        if task.assigned_agent and task.assigned_agent in mission.agents:
            return mission.agents[task.assigned_agent]
        if self._default_agent and self._default_agent in mission.agents:
            agent = mission.agents[self._default_agent]
            task.assigned_agent = agent.agent_id
            return agent
        ordered = sorted(mission.agents.items())
        if not ordered:
            raise RuntimeError(f"no agents registered in mission {mission.id}")
        agent_id, agent = ordered[0]
        task.assigned_agent = agent_id
        return agent

    def step(self, mission: Mission) -> bool:
        """Advance the mission by one unit of work. False when nothing moved."""

        # 1. Resume approved tasks.
        for task in mission.tasks.values():
            if task.status == TaskStatus.APPROVED:
                agent = self._pick_agent(mission, task)
                self._transition(
                    mission,
                    task,
                    TaskStatus.RUNNING,
                    actor=agent.agent_id,
                    generation=agent.generation,
                    reason="resuming after approval",
                )
                return True

        # 2. Start the next pending task with satisfied dependencies.
        task = self._next_task(mission)
        if task is not None:
            agent = self._pick_agent(mission, task)
            if task.requires_approval and not any(
                a.task_id == task.id for a in mission.approvals.values()
            ):
                # Controller-owned gate: never rely on the agent to ask.
                approval_id = sha256_bytes(
                    canonical_bytes(["approval", mission.id, task.id, "controller-gate"])
                )[:16]
                mission.approvals[approval_id] = ApprovalRequest(
                    id=approval_id,
                    task_id=task.id,
                    question=f"Approve execution of task {task.name!r}?",
                )
                self._transition(
                    mission,
                    task,
                    TaskStatus.AWAITING_APPROVAL,
                    actor="controller",
                    generation="scripted",
                    reason="task requires approval",
                )
                return True
            self._transition(
                mission,
                task,
                TaskStatus.RUNNING,
                actor=agent.agent_id,
                generation=agent.generation,
                reason="dependencies satisfied",
            )
            return True

        # 3. Execute one running task that is not paused for approval.
        for running in mission.tasks.values():
            if running.status == TaskStatus.RUNNING and not _has_open_approval(mission, running):
                self._execute(mission, running)
                return True

        return False

    def _execute(self, mission: Mission, task: Task) -> None:
        agent = self._pick_agent(mission, task)
        task.attempts += 1
        self._trace_execution(mission, task, agent)
        try:
            result = agent.execute(task, mission)
        except ApprovalPause as pause:
            task.attempts -= 1  # a pause is not a failed attempt
            if task.status != TaskStatus.AWAITING_APPROVAL:
                self._transition(
                    mission,
                    task,
                    TaskStatus.AWAITING_APPROVAL,
                    actor=agent.agent_id,
                    generation=agent.generation,
                    reason=str(pause) or "paused for approval",
                )
            return
        except Exception as exc:  # noqa: BLE001 - recorded as task failure
            task.error = f"{type(exc).__name__}: {exc}"
            if task.attempts <= task.max_retries:
                self._transition(
                    mission,
                    task,
                    TaskStatus.PENDING,
                    actor=agent.agent_id,
                    generation=agent.generation,
                    reason=f"attempt {task.attempts} failed; retrying",
                )
            else:
                self._transition(
                    mission,
                    task,
                    TaskStatus.FAILED,
                    actor=agent.agent_id,
                    generation=agent.generation,
                    reason=f"failed after {task.attempts} attempts",
                )
            return
        task.result = result
        task.error = ""
        self._transition(
            mission,
            task,
            TaskStatus.COMPLETED,
            actor=agent.agent_id,
            generation=agent.generation,
            reason=f"completed on attempt {task.attempts}",
        )
        self._remember(mission, task, result)

    def _trace_execution(self, mission: Mission, task: Task, agent: AgentHandle) -> None:
        if self._tracer is None or not self._tracer.traces:
            return
        latest = self._tracer.traces[-1]
        latest.observations.append(_make_tool(latest, task, agent))

    def _remember(self, mission: Mission, task: Task, result: Any) -> None:
        if self._memory is None:
            return
        findings = task.findings or [f"{task.name} completed: {result}"]
        for finding in findings:
            self._memory.add(
                [{"role": "assistant", "content": f"Finding: {finding}"}],
                agent_id=mission.id,
            )

    # -- supervision ---------------------------------------------------------

    def cancel(self, mission: Mission, task_id: str, *, actor: str = "operator") -> Task:
        task = mission.tasks[task_id]
        if task.status in TaskStatus.TERMINAL:
            raise ValueError(f"task {task_id} is already {task.status}")
        for approval in mission.approvals.values():
            if approval.task_id == task_id and not approval.is_resolved:
                approval.resolution = "reject"
                approval.resolved_by = actor
                approval.resolved_at_ms = self._clock()
                approval.comment = "invalidated by cancellation"
        self._transition(
            mission,
            task,
            TaskStatus.CANCELLED,
            actor=actor,
            generation="human",
            reason="cancelled by supervisor",
        )
        return task

    def takeover(self, mission: Mission, task_id: str, agent_id: str) -> Task:
        """Human interruption: reassign a non-terminal task to *agent_id*."""

        task = mission.tasks[task_id]
        if task.status in TaskStatus.TERMINAL:
            raise ValueError(f"task {task_id} is already {task.status}")
        if agent_id not in mission.agents:
            raise KeyError(f"agent {agent_id} is not registered")
        task.assigned_agent = agent_id
        if task.status == TaskStatus.RUNNING:
            self._transition(
                mission,
                task,
                TaskStatus.PENDING,
                actor="operator",
                generation="human",
                reason=f"taken over by {agent_id}",
            )
        return task

    def run(self, mission: Mission, *, max_steps: int = 1000) -> MissionStatus:
        """Drive the mission until quiescent; returns the terminal status."""

        for _ in range(max_steps):
            if not self.step(mission):
                break
        else:
            raise RuntimeError(f"mission {mission.id} exceeded {max_steps} steps")
        return self.status(mission)

    def status(self, mission: Mission) -> MissionStatus:
        unfinished = [task for task in mission.tasks.values() if task.status not in TaskStatus.TERMINAL]
        if not unfinished:
            return MissionStatus.COMPLETE
        if self.pending_approvals(mission):
            return MissionStatus.BLOCKED
        if all(
            task.status == TaskStatus.PENDING and not task.dependencies_met(mission.completed_ids())
            for task in unfinished
        ):
            return MissionStatus.STALLED
        return MissionStatus.RUNNING


def _make_event(latest, task, from_status, to_status, actor, generation, reason):
    from ..observability.models import Observation, ObservationType

    return Observation(
        id=sha256_bytes(canonical_bytes(["event", latest.id, task.id, to_status, len(latest.observations)]))[
            :20
        ],
        trace_id=latest.id,
        type=ObservationType.EVENT,
        name=f"task:{task.name}:{to_status}",
        input={"from": from_status},
        output={"actor": actor, "generation": generation, "reason": reason},
    )


def _make_tool(latest, task, agent):
    from ..observability.models import Observation, ObservationType

    return Observation(
        id=sha256_bytes(canonical_bytes(["tool", latest.id, task.id, len(latest.observations)]))[:20],
        trace_id=latest.id,
        type=ObservationType.TOOL,
        name=f"execute:{task.name}",
        input={"task": task.id, "attempt": task.attempts},
        metadata={"agent": agent.agent_id, "generation": agent.generation},
    )
