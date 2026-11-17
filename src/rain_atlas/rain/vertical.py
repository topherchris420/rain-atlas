"""The integrated vertical slice: one complete scientific mission.

Runs the reconstructed capabilities end to end::

1. a hypothesis is proposed (optional local inference provider, or scripted);
2. the protocol compiler validates it into an executable specification;
3. an approval gate pauses execution until resolved (by a human, or by an
   honestly-labeled scripted operator proxy in demonstrations);
4. research agents select and execute experiments on the simulation twin,
   consulting scientific memory for prior results and contradictions;
5. the observability layer records every decision;
6. the evaluator computes the preregistered decision rule;
7. the skeptic replicates on a held-out condition;
8. findings, including failures and contradictions, are written to memory
   and the knowledge store;
9. traces export into the ATLAS evidence ledger.

Every agent action records its generation (scripted/model/human), so the
slice never claims autonomy it does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..inference import InferenceProvider, MockProvider
from ..knowledge import KnowledgeStore
from ..ledger.store import Ledger
from ..memory import ScientificMemory
from ..mission import Mission, MissionController
from ..observability import Tracer
from ..protocol import ProtocolCompiler
from ..simulation import FaultProfile, ObservationFault, Scenario, ServiceTwin
from .models import CandidateModels, Observation
from .policies import AdaptiveSelector, Selector

GRID = [round(0.1 * i, 2) for i in range(1, 11)]  # 0.1 .. 1.0
HELD_OUT = 0.85
LEXICON = {
    "coupling strength": {
        "symbol": "k",
        "range": [0.0, 1.0],
        "default_points": 10,
        "instrument": "oscillator-bench",
    }
}


@dataclass
class VerticalSliceResult:
    """Everything the slice produced, ready for evidence export."""

    mission_id: str
    hypothesis: str
    protocol_id: str
    true_model: str
    preferred_model: str
    decided: bool
    mission_status: str = ""
    experiments: list[dict[str, Any]] = field(default_factory=list)
    replication: dict[str, Any] = field(default_factory=dict)
    memory_statistics: dict[str, Any] = field(default_factory=dict)
    trace_count: int = 0
    trace_observation_count: int = 0
    approvals: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    ledger_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "hypothesis": self.hypothesis,
            "protocol_id": self.protocol_id,
            "true_model": self.true_model,
            "preferred_model": self.preferred_model,
            "decided": self.decided,
            "mission_status": self.mission_status,
            "experiments": list(self.experiments),
            "replication": self.replication,
            "memory_statistics": self.memory_statistics,
            "trace_count": self.trace_count,
            "trace_observation_count": self.trace_observation_count,
            "approvals": list(self.approvals),
            "tasks": list(self.tasks),
            "ledger_verified": self.ledger_verified,
        }


def run_vertical_slice(
    root: Path,
    *,
    seed: int = 7,
    true_model: str | None = None,
    policy: Selector | None = None,
    use_memory: bool = True,
    memory_scope: str | None = None,
    provider: InferenceProvider | None = None,
    max_experiments: int = 6,
    fault_profile: FaultProfile | None = None,
    approve: bool = True,
    clock: Any | None = None,
) -> VerticalSliceResult:
    """Execute one integrated mission; deterministic for fixed inputs.

    *memory_scope* controls the scientific-memory namespace: the mission id
    by default, or a shared program scope when supplied (used by the central
    experiment to let successive missions build on prior evidence). *clock*
    overrides wall time for exact reproduction.
    """

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if true_model is None:
        true_model = "damped" if seed % 2 == 1 else "linear"
    policy = policy or AdaptiveSelector(CandidateModels())
    provider = provider or MockProvider(vocabulary=["coupling strength"])
    models = CandidateModels()

    memory = ScientificMemory(root / "memory")
    knowledge = KnowledgeStore(root / "knowledge")
    tracer = Tracer()
    twin = ServiceTwin(Scenario(seed=seed, true_model=true_model), fault_profile=fault_profile)
    controller = MissionController(tracer=tracer, memory=memory, clock=clock)
    compiler = ProtocolCompiler(LEXICON)
    mission = controller.create_mission(
        "model-discrimination", question="Which coupling model generates the twin's observations?"
    )
    scope = memory_scope or mission.id
    state: dict[str, Any] = {"observations": [], "hypothesis": "", "protocol": None, "verdict": None}

    def recall_observations() -> list[Observation]:
        found = memory.get_all(filters={"agent_id": scope, "kind": "observation"})
        return [
            Observation(
                coupling=float(item["metadata"].get("coupling", 0.0)),
                coherence=float(item["metadata"].get("coherence", 0.0)),
                replicates=int(item["metadata"].get("replicates", models.replicates)),
            )
            for item in found["results"]
        ]

    def remember_finding(text: str, metadata: dict[str, Any]) -> None:
        if use_memory:
            memory.add(f"Finding: {text}", agent_id=scope, metadata=metadata)

    # -- agent 1: proposer (model generation when a provider is supplied) -----

    def propose(task: Any, m: Mission) -> Any:
        generation = provider.complete("propose: which variable matters for phase locking?")
        state["hypothesis"] = generation.text
        with_memory = ""
        if use_memory:
            prior = memory.search("phase locking", filters={"agent_id": scope})
            if prior["results"]:
                with_memory = f" (recalled {len(prior['results'])} prior memories)"
        task.findings = [f"proposed hypothesis via {provider.name} provider{with_memory}"]
        return {"hypothesis": generation.text, "generation": generation.to_dict()}

    controller.register_agent(mission, "proposer", "principal-investigator", propose, generation="model")

    # -- agent 2: protocol compiler (deterministic, scripted) ---------------

    def compile_protocol(task: Any, m: Mission) -> Any:
        spec = compiler.compile(
            "Which coupling model explains the observations?",
            state["hypothesis"],
            points=len(GRID),
            replicates=models.replicates,
        )
        state["protocol"] = spec
        return {"protocol_id": spec.protocol_id, "steps": len(spec.steps)}

    controller.register_agent(
        mission, "compiler", "protocol-engineer", compile_protocol, generation="scripted"
    )

    # -- agent 3: experimentalist (scripted policy; approval-gated) ---------

    def run_experiments(task: Any, m: Mission) -> Any:
        if not any(approval.task_id == task.id for approval in m.approvals.values()):
            controller.request_approval(
                m, task, "Execute the compiled protocol on the simulated oscillator twin?"
            )
        # ApprovalPause raised above; execution resumes here after approval.
        attempts = 0
        dropped = 0
        fault_budget = 3 * max_experiments
        while len(state["observations"]) < max_experiments and attempts < fault_budget:
            attempts += 1
            observations = recall_observations() if use_memory else state["observations"]
            condition = policy.next_condition(GRID, observations or state["observations"])
            if condition is None:
                break
            try:
                response = twin.run_experiment(condition, replicates=models.replicates)
            except ObservationFault:
                dropped += 1
                remember_finding(
                    f"the twin dropped the observation at coupling {condition}",
                    {"mission": m.name, "kind": "fault", "coupling": condition},
                )
                continue
            observation = Observation(
                coupling=condition, coherence=response["coherence"], replicates=models.replicates
            )
            state["observations"].append(observation)
            remember_finding(
                f"at coupling {condition} the measured phase locking was {response['coherence']}",
                {
                    "mission": m.name,
                    "kind": "observation",
                    "coupling": condition,
                    "coherence": response["coherence"],
                    "replicates": models.replicates,
                },
            )
            current = recall_observations() if use_memory else state["observations"]
            if models.decided(current or state["observations"]):
                break
        return {"experiments": len(state["observations"]), "dropped": dropped, "attempts": attempts}

    controller.register_agent(
        mission, "experimentalist", "computational-scientist", run_experiments, generation="scripted"
    )

    # -- agent 4: evaluator (scripted decision rule) --------------------------

    def evaluate(task: Any, m: Mission) -> Any:
        observations = recall_observations() if use_memory else state["observations"]
        if not observations:
            observations = state["observations"]
        decided = models.decided(observations)
        preferred = models.preferred_model(observations)
        state["verdict"] = {
            "decided": decided,
            "preferred_model": preferred,
            "posterior": round(models.posterior_probability(preferred, observations), 6),
            "log_bayes_factor": round(models.log_bayes_factor(observations), 6),
        }
        if use_memory:
            memory.add(
                f"Decision: the evidence prefers the {preferred} model (decided={decided})",
                agent_id=scope,
                metadata={"mission": m.name, "kind": "decision"},
            )
        return dict(state["verdict"])

    controller.register_agent(mission, "evaluator", "statistician", evaluate, generation="scripted")

    # -- agent 5: skeptic (independent replication on held-out condition) ----

    def replicate(task: Any, m: Mission) -> Any:
        observations = state["observations"]
        fresh_twin = ServiceTwin(Scenario(seed=seed + 500_000, true_model=true_model))
        response = fresh_twin.run_experiment(HELD_OUT, replicates=models.replicates)
        held_out = Observation(
            coupling=HELD_OUT, coherence=response["coherence"], replicates=models.replicates
        )
        preferred = state["verdict"]["preferred_model"]
        replicated = models.preferred_model(observations + [held_out]) == preferred
        outcome = {
            "held_out_condition": HELD_OUT,
            "coherence": held_out.coherence,
            "verdict_replicated": replicated,
        }
        if not replicated and use_memory:
            memory.add(
                f"Finding: the held-out replication at coupling {HELD_OUT} does not "
                "support the earlier preferred model",
                agent_id=scope,
                metadata={"mission": m.name, "kind": "contradiction"},
            )
        return outcome

    controller.register_agent(mission, "skeptic", "scientific-skeptic", replicate, generation="scripted")

    # -- wire the mission -----------------------------------------------------

    propose_task = mission.submit(
        "propose-hypothesis",
        description="propose a testable hypothesis",
        agent="proposer",
    )
    compile_task = mission.submit("compile-protocol", dependencies=[propose_task.id], agent="compiler")
    run_task = mission.submit(
        "run-experiments",
        dependencies=[compile_task.id],
        requires_approval=True,
        max_retries=1,
        agent="experimentalist",
    )
    evaluate_task = mission.submit("evaluate-verdict", dependencies=[run_task.id], agent="evaluator")
    mission.submit("replicate-held-out", dependencies=[evaluate_task.id], agent="skeptic")

    with tracer.trace("vertical-slice", session_id=mission.id, tags=["rain", "vertical"]) as trace:
        for _ in range(8 * len(mission.tasks) + 32):
            if not controller.step(mission):
                break
            pending = controller.pending_approvals(mission)
            if pending and approve:
                controller.resolve_approval(
                    mission,
                    pending[0].id,
                    resolution="approve",
                    resolved_by="operator-proxy",
                    comment="scripted operator proxy approving simulated twin execution",
                    generation="scripted",
                )
        status = controller.status(mission)
        trace.record_output({"mission_status": status.value if hasattr(status, "value") else status})

    verdict = state["verdict"] or {
        "decided": False,
        "preferred_model": "unknown",
        "posterior": 0.0,
        "log_bayes_factor": 0.0,
    }

    # -- evidence export ------------------------------------------------------

    ledger = Ledger(root / "ledger")
    ledger.append(
        "preregistration",
        {
            "title": "R.A.I.N. vertical slice: model discrimination",
            "question": mission.question,
            "hypothesis": state["hypothesis"],
            "null_hypothesis": "neither candidate model is preferred",
            "design": {
                "policy": getattr(policy, "name", "custom"),
                "max_experiments": max_experiments,
                "true_model_hidden_from_agents": True,
                "decision_log_bayes": models.decision_log_bayes,
                "memory_scope": scope,
            },
            "acceptance": [
                "agents never observe the hidden model",
                "decision rule fixed before observations",
                "held-out replication agrees with the preferred model",
            ],
            "created_by": {"role": "pi", "generation": "scripted"},
        },
    )
    experiment_ref = next(ledger.entries("preregistration")).object
    trace.trace.output = verdict
    tracer.export_to_ledger(
        ledger, experiment=experiment_ref, author={"role": "engineer", "generation": "scripted"}
    )
    knowledge.put(
        "vertical-slice",
        {"mission": mission.id, "verdict": verdict},
        kind="experiment-record",
        author="rain-vertical",
    )
    knowledge.flush()
    problems = ledger.verify()

    replication_task = next(t for t in mission.tasks.values() if t.name == "replicate-held-out")
    trace_observations = sum(len(t.observations) for t in tracer.traces)
    return VerticalSliceResult(
        mission_id=mission.id,
        hypothesis=state["hypothesis"],
        protocol_id=state["protocol"].protocol_id if state["protocol"] else "",
        true_model=true_model,
        preferred_model=verdict["preferred_model"],
        decided=verdict["decided"],
        mission_status=getattr(status, "name", str(status)),
        experiments=[obs.to_dict() for obs in state["observations"]],
        replication=replication_task.result or {},
        memory_statistics=memory.statistics(),
        trace_count=len(tracer.traces),
        trace_observation_count=trace_observations,
        approvals=[a.to_dict() for a in mission.approvals.values()],
        tasks=[t.to_dict() for t in mission.tasks.values()],
        ledger_verified=not problems,
    )
