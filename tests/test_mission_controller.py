"""Tests for the Research Mission Controller (Omnara/Maxxwell-inspired replica)."""

from __future__ import annotations

import pytest

from rain_atlas.memory import ScientificMemory
from rain_atlas.mission import (
    MissionController,
    MissionStatus,
    TaskStatus,
    approval_granted,
)
from rain_atlas.observability import Tracer


class StepClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


@pytest.fixture()
def clock() -> StepClock:
    return StepClock()


@pytest.fixture()
def controller(clock) -> MissionController:
    return MissionController(clock=clock)


def counter_agent(agent_id="agent-1", role="researcher"):
    calls = []

    def execute(task, mission):
        calls.append((task.id, task.attempts))
        return {"task": task.name, "attempt": task.attempts}

    from rain_atlas.mission import AgentHandle

    return AgentHandle(agent_id=agent_id, role=role, generation="scripted", execute=execute), calls


class TestLifecycle:
    def test_simple_task_completes(self, controller):
        mission = controller.create_mission("verify-baseline", question="is the twin stable?")
        agent, _calls = counter_agent()
        mission.agents[agent.agent_id] = agent
        task = mission.submit("run-twin", inputs={"seed": 7})
        status = controller.run(mission)
        assert status == MissionStatus.COMPLETE
        assert task.status == TaskStatus.COMPLETED
        assert task.result["task"] == "run-twin"
        assert [t.to_status for t in task.transitions] == ["running", "completed"]

    def test_dependencies_are_respected(self, controller):
        mission = controller.create_mission("ordered")
        agent, _calls = counter_agent()
        mission.agents[agent.agent_id] = agent
        first = mission.submit("first")
        second = mission.submit("second", dependencies=[first.id])
        third = mission.submit("third", dependencies=[second.id])
        controller.run(mission)
        assert all(t.status == TaskStatus.COMPLETED for t in (first, second, third))
        # Transitions are recorded with a monotonic clock; first must finish first.
        first_done = first.transitions[-1].timestamp_ms
        second_done = second.transitions[-1].timestamp_ms
        assert first_done < second_done

    def test_dependency_cycle_stalls(self, controller):
        mission = controller.create_mission("cycle")
        agent, _calls = counter_agent()
        mission.agents[agent.agent_id] = agent
        a = mission.submit("a")
        b = mission.submit("b", dependencies=[a.id])
        a.dependencies.append(b.id)  # create the cycle
        status = controller.run(mission)
        assert status == MissionStatus.STALLED

    def test_failure_retry_then_success(self, controller):
        mission = controller.create_mission("retry")
        attempts = {"n": 0}

        def flaky(task, m):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("transient fault")
            return "ok"

        from rain_atlas.mission import AgentHandle

        mission.agents["flaky-agent"] = AgentHandle(
            agent_id="flaky-agent", role="researcher", generation="scripted", execute=flaky
        )
        task = mission.submit("flaky-task", max_retries=3)
        controller.run(mission)
        assert task.status == TaskStatus.COMPLETED
        assert task.attempts == 3
        assert [t.to_status for t in task.transitions] == [
            "running",
            "pending",
            "running",
            "pending",
            "running",
            "completed",
        ]

    def test_failure_exhausts_retries(self, controller):
        mission = controller.create_mission("doomed")

        def always_fails(task, m):
            raise ValueError("permanent fault")

        from rain_atlas.mission import AgentHandle

        mission.agents["bad"] = AgentHandle(
            agent_id="bad", role="researcher", generation="scripted", execute=always_fails
        )
        task = mission.submit("doomed-task", max_retries=1)
        controller.run(mission)
        assert task.status == TaskStatus.FAILED
        assert "permanent fault" in task.error
        assert task.attempts == 2

    def test_no_agents_registered_raises_on_start(self, controller):
        mission = controller.create_mission("empty")
        mission.submit("task")
        with pytest.raises(RuntimeError):
            controller.run(mission)


class TestApprovals:
    def test_approval_pauses_until_human_resolves(self, controller):
        mission = controller.create_mission("critical")
        asked = {"value": False}

        def careful(task, m):
            if not asked["value"]:
                asked["value"] = True
                controller.request_approval(m, task, "May the agent modify the shared twin state?")
            return {"approved": True}

        from rain_atlas.mission import AgentHandle

        mission.agents["careful"] = AgentHandle(
            agent_id="careful", role="scientist", generation="model", execute=careful
        )
        task = mission.submit("careful-task")
        status = controller.run(mission)
        assert status == MissionStatus.BLOCKED
        assert task.status == TaskStatus.AWAITING_APPROVAL
        approvals = controller.pending_approvals(mission)
        assert len(approvals) == 1

        controller.resolve_approval(mission, approvals[0].id, resolution="approve", resolved_by="operator")
        assert approval_granted(mission, task)
        final = controller.run(mission)
        assert final == MissionStatus.COMPLETE
        assert task.status == TaskStatus.COMPLETED
        # Human decisions are recorded as human generation.
        generations = {t.generation for t in task.transitions}
        assert "human" in generations
        assert "model" in generations  # agent reasoning stays model-labeled

    def test_requires_approval_is_enforced_by_controller(self, controller):
        mission = controller.create_mission("gated")
        agent, calls = counter_agent()
        mission.agents[agent.agent_id] = agent
        task = mission.submit("gated-task", requires_approval=True)
        assert controller.run(mission) == MissionStatus.BLOCKED
        assert calls == []  # never invoked before approval
        approval = controller.pending_approvals(mission)[0]
        controller.resolve_approval(mission, approval.id, resolution="approve", resolved_by="op")
        assert controller.run(mission) == MissionStatus.COMPLETE
        assert task.attempts == 1

    def test_cancel_invalidates_pending_approval(self, controller):
        mission = controller.create_mission("cancelled")
        agent, calls = counter_agent()
        mission.agents[agent.agent_id] = agent
        task = mission.submit("gated-task", requires_approval=True)
        controller.run(mission)
        approval = controller.pending_approvals(mission)[0]
        controller.cancel(mission, task.id)
        with pytest.raises(ValueError):
            controller.resolve_approval(mission, approval.id, resolution="approve", resolved_by="op")
        controller.run(mission)
        assert calls == [] and task.status == TaskStatus.CANCELLED

    def test_rejection_cancels_task(self, controller):
        mission = controller.create_mission("rejected")

        def asks(task, m):
            controller.request_approval(m, task, "proceed?")
            return {}

        from rain_atlas.mission import AgentHandle

        mission.agents["asks"] = AgentHandle(
            agent_id="asks", role="scientist", generation="scripted", execute=asks
        )
        task = mission.submit("ask-task")
        controller.run(mission)
        approvals = controller.pending_approvals(mission)
        controller.resolve_approval(mission, approvals[0].id, resolution="reject", resolved_by="operator")
        assert task.status == TaskStatus.CANCELLED
        assert controller.status(mission) == MissionStatus.COMPLETE  # nothing unfinished

    def test_double_resolution_rejected(self, controller):
        mission = controller.create_mission("m")
        approval = None

        def asks(task, m):
            controller.request_approval(m, task, "proceed?")
            return {}

        from rain_atlas.mission import AgentHandle

        mission.agents["asks"] = AgentHandle(
            agent_id="asks", role="scientist", generation="scripted", execute=asks
        )
        mission.submit("t")
        controller.run(mission)
        approval = controller.pending_approvals(mission)[0]
        controller.resolve_approval(mission, approval.id, resolution="approve", resolved_by="op")
        with pytest.raises(ValueError):
            controller.resolve_approval(mission, approval.id, resolution="approve", resolved_by="op")

    def test_invalid_resolution_rejected(self, controller):
        mission = controller.create_mission("m")

        def asks(task, m):
            controller.request_approval(m, task, "proceed?")
            return {}

        from rain_atlas.mission import AgentHandle

        mission.agents["asks"] = AgentHandle(
            agent_id="asks", role="scientist", generation="scripted", execute=asks
        )
        mission.submit("t")
        controller.run(mission)
        approval = controller.pending_approvals(mission)[0]
        with pytest.raises(ValueError):
            controller.resolve_approval(mission, approval.id, resolution="maybe", resolved_by="op")


class TestSupervision:
    def test_cancel_nonterminal_task(self, controller):
        mission = controller.create_mission("supervised")

        def asks(task, m):
            controller.request_approval(m, task, "proceed?")
            return {}

        from rain_atlas.mission import AgentHandle

        mission.agents["asks"] = AgentHandle(
            agent_id="asks", role="scientist", generation="scripted", execute=asks
        )
        task = mission.submit("pausable")
        controller.run(mission)
        cancelled = controller.cancel(mission, task.id, actor="pi")
        assert cancelled.status == TaskStatus.CANCELLED
        with pytest.raises(ValueError):
            controller.cancel(mission, task.id)  # already terminal

    def test_takeover_reassigns(self, controller):
        mission = controller.create_mission("takeover")
        agent_a, _ = counter_agent("a")
        agent_b, _calls_b = counter_agent("b")
        mission.agents["a"] = agent_a
        mission.agents["b"] = agent_b
        task = mission.submit("work")
        controller.takeover(mission, task.id, "b")
        controller.run(mission)
        assert task.assigned_agent == "b"
        assert any(c[0] == task.id for c in _calls_b)


class TestIntegrationHooks:
    def test_transitions_are_traced(self, clock):
        tracer = Tracer(clock=clock)
        controller = MissionController(clock=clock, tracer=tracer)
        mission = controller.create_mission("traced")
        agent, _ = counter_agent()
        mission.agents[agent.agent_id] = agent
        mission.submit("one")
        controller.run(mission)
        assert not tracer.traces  # the controller itself creates no trace
        # Start a trace and rerun: events land on the latest trace.
        with tracer.trace("mission-run") as _scope:
            mission2 = controller.create_mission("traced-2")
            mission2.agents[agent.agent_id] = agent
            mission2.submit("two")
            controller.run(mission2)
        latest = tracer.traces[-1]
        names = [o.name for o in latest.observations]
        assert any(n.startswith("task:two:") for n in names)
        assert any(n.startswith("execute:two") for n in names)

    def test_findings_written_to_memory(self, tmp_path):
        memory = ScientificMemory(root=tmp_path / "mem")
        controller = MissionController(memory=memory)
        mission = controller.create_mission("remembered")
        agent, _ = counter_agent()
        mission.agents[agent.agent_id] = agent
        task = mission.submit("finding-task")
        task.findings = ["the twin remained stable at coupling 0.4"]
        controller.run(mission)
        results = memory.search("twin stable", filters={"agent_id": mission.id})
        assert len(results["results"]) >= 1

    def test_model_generation_distinguished_from_scripted(self, controller):
        mission = controller.create_mission("generations")
        agent, _ = counter_agent()
        agent.generation = "model"
        mission.agents[agent.agent_id] = agent
        mission.submit("m-task")
        controller.run(mission)
        task = next(iter(mission.tasks.values()))
        completion = task.transitions[-1]
        assert completion.generation == "model"

    def test_invalid_generation_rejected(self):
        from rain_atlas.mission import AgentHandle

        with pytest.raises(ValueError):
            AgentHandle(agent_id="x", role="r", generation="robot", execute=lambda t, m: None)

    def test_mission_json_round_trip(self, controller):
        mission = controller.create_mission("serialized", question="why?")
        agent, _ = counter_agent()
        mission.agents[agent.agent_id] = agent
        mission.submit("t1")
        controller.run(mission)
        import json

        payload = json.dumps(mission.to_dict())
        assert "transitions" in payload
