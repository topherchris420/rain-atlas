"""Protocol v1 of the central experiment (2026-11-16) -- superseded, kept for reproduction.

Status
------

This is the protocol whose outcome was first recorded ("H1/H2/H3
supported, 68% fewer experiments from persistent memory"). It is retained
unchanged so that outcome stays exactly reproducible
(``atlas rain central --protocol v1``). Review found that its design could
not fail:

* the hidden model never changes within a program, and the memory arm
  pools the previous missions' decisive observations, so missions 2 and 3
  of every program decide before running anything. The measured 6 vs 19
  experiments (68%) is ``1 - 1/3`` by construction, not a measurement;
* one experiment at the maximum-disagreement condition yields an expected
  log Bayes factor of about 11 against a decision threshold of 5, so the
  adaptive arm almost always decides after a single experiment;
* no arm made a false conclusion, so H2 compared 0 with 0;
* ``AdaptiveSelector`` ignores the observations (disagreement does not
  depend on them), so "adaptive" is a fixed high-to-low ordering, and the
  ascending grid baseline starts at the least informative conditions;
* six programs per arm, decided on point estimates with no uncertainty.

Protocol v2 (:mod:`rain_atlas.rain.experiment`) addresses each point.

Research question
------------------

*Can a system combining independently reconstructed specialist capabilities
design, execute, evaluate and revise scientific experiments more effectively
than simpler baseline architectures?*

Design
------

Four arms share the same decision book, twin family and budget; they differ
only in **experiment-selection policy** and **persistent scientific memory**:

* ``integrated-memory`` -- adaptive (maximum-disagreement) selection with
  program-scoped persistent memory across sequential missions;
* ``integrated-no-memory`` -- adaptive selection, fresh memory each mission;
* ``grid`` -- fixed low-to-high design (the analog of ATLAS's preregistered
  fixed sweeps), fresh memory each mission;
* ``random`` -- seeded random selection, fresh memory each mission.

Each program runs three sequential missions on twins with the same hidden
model but different seeds, then a held-out replication. The hidden model
alternates between programs; agents never observe it.

Preregistered hypotheses
------------------------

* **H1 (efficiency):** ``integrated-memory`` reaches decisions using at least
  25% fewer total experiments than ``integrated-no-memory``.
* **H2 (correctness):** ``integrated-memory`` does not exceed the
  ``integrated-no-memory`` false-conclusion rate by more than 5 percentage
  points.
* **H3 (selection):** both adaptive arms decide with fewer mean experiments
  per mission than ``grid`` and ``random``.

A negative or inconclusive outcome is an acceptable result; the experiment
is constructed so it *can* fail. All policies are deterministic scripted
code -- no language model is involved in any arm.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..canonical import sha256_json
from ..ledger.store import Ledger
from ..memory import ScientificMemory
from ..simulation import Scenario, ServiceTwin
from .models import CandidateModels, Observation
from .policies import (
    AdaptiveSelector,
    GridSelector,
    RandomSelector,
    Selector,
)

GRID = [round(0.1 * i, 2) for i in range(1, 11)]
HELD_OUT = 0.85
PROGRAMS = 6
MISSIONS_PER_PROGRAM = 3
BUDGET_PER_MISSION = 8
REPLICATES = 4
BASE_SEED = 20261116

ARMS = (
    "integrated-memory",
    "integrated-no-memory",
    "grid",
    "random",
)


@dataclass
class ArmOutcome:
    arm: str
    total_experiments: int = 0
    missions: int = 0
    decided: int = 0
    correct_when_decided: int = 0
    false_conclusions: int = 0
    undecided: int = 0
    replications: int = 0
    replication_successes: int = 0
    experiments_per_mission: list[int] = field(default_factory=list)

    @property
    def mean_experiments(self) -> float:
        return (
            round(self.total_experiments / len(self.experiments_per_mission), 4)
            if self.experiments_per_mission
            else 0.0
        )

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "total_experiments": self.total_experiments,
            "missions": self.missions,
            "decided": self.decided,
            "correct_when_decided": self.correct_when_decided,
            "false_conclusions": self.false_conclusions,
            "undecided": self.undecided,
            "replications": self.replications,
            "replication_successes": self.replication_successes,
            "mean_experiments": self.mean_experiments,
            "experiments_per_mission": list(self.experiments_per_mission),
        }


@dataclass
class CentralExperimentV1Result:
    arms: dict[str, ArmOutcome] = field(default_factory=dict)
    hypotheses: dict[str, dict[str, Any]] = field(default_factory=dict)
    elapsed_s: float = 0.0
    ledger_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "arms": {name: arm.to_dict() for name, arm in self.arms.items()},
            "hypotheses": self.hypotheses,
            "elapsed_s": round(self.elapsed_s, 3),
            "ledger_verified": self.ledger_verified,
        }


def _selector_for(arm: str, seed: int) -> Selector:
    if arm in ("integrated-memory", "integrated-no-memory"):
        return AdaptiveSelector(CandidateModels(replicates=REPLICATES))
    if arm == "grid":
        return GridSelector()
    if arm == "random":
        return RandomSelector(seed)
    raise ValueError(f"unknown arm {arm!r}")


def run_central_experiment_v1(
    root: Path,
    *,
    programs: int = PROGRAMS,
    missions_per_program: int = MISSIONS_PER_PROGRAM,
    budget: int = BUDGET_PER_MISSION,
    base_seed: int = BASE_SEED,
) -> CentralExperimentV1Result:
    """Execute the comparison; writes an ATLAS ledger under *root*."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError("central experiment root already has a ledger; use a fresh directory")
    design = {
        "arms": list(ARMS),
        "programs": programs,
        "missions_per_program": missions_per_program,
        "budget_per_mission": budget,
        "replicates": REPLICATES,
        "grid": GRID,
        "held_out": HELD_OUT,
        "decision_log_bayes": 5.0,
        "hypotheses": {
            "H1": "integrated-memory uses >=25% fewer total experiments than integrated-no-memory",
            "H2": "integrated-memory false-conclusion rate does not exceed no-memory rate by >5pp",
            "H3": "adaptive arms decide with fewer mean experiments per mission than grid and random",
        },
        "hidden_model_assignment": "program even -> linear, odd -> damped (agents never observe it)",
    }
    prereg = ledger.append(
        "preregistration",
        {
            "title": "Central experiment: integrated architecture vs simpler baselines",
            "question": "Does combining reconstructed capabilities (adaptive selection + persistent scientific memory) improve experiment efficiency without increasing false conclusions?",
            "hypothesis": "Adaptive selection with persistent memory reaches correct model decisions with fewer experiments than the same architecture without memory and than fixed or random selection.",
            "null_hypothesis": "Selection policy and memory do not change experiment efficiency or correctness.",
            "design": design,
            "acceptance": [
                "H1: >=25% fewer total experiments for integrated-memory vs integrated-no-memory",
                "H2: false-conclusion rate within +5 percentage points",
                "H3: both adaptive arms below grid and random mean experiments",
            ],
            "created_by": {"role": "pi", "generation": "scripted"},
        },
    )
    experiment = prereg.object

    outcomes = {arm: ArmOutcome(arm=arm) for arm in ARMS}
    program_records: list[dict[str, Any]] = []

    for arm in ARMS:
        for program in range(programs):
            true_model = "linear" if program % 2 == 0 else "damped"
            use_memory = arm == "integrated-memory"
            memory = ScientificMemory(root / f"memory-{arm}-p{program}") if use_memory else None
            selector = _selector_for(arm, base_seed + program)
            program_observations: list[Observation] = []
            program_experiments = 0
            for mission_idx in range(missions_per_program):
                seed = base_seed + program * 100 + mission_idx * 7
                twin = ServiceTwin(Scenario(seed=seed, true_model=true_model))
                observations = _recall(memory) if use_memory else []
                if use_memory and not observations:
                    observations = list(program_observations)
                experiments = 0
                while experiments < budget and not _decided(observations):
                    condition = selector.next_condition(GRID, observations)
                    if condition is None:
                        break
                    response = twin.run_experiment(condition, replicates=REPLICATES)
                    observations.append(
                        Observation(
                            coupling=condition,
                            coherence=response["coherence"],
                            replicates=REPLICATES,
                        )
                    )
                    experiments += 1
                program_experiments += experiments
                outcome = outcomes[arm]
                outcome.missions += 1
                outcome.experiments_per_mission.append(experiments)
                outcome.total_experiments += experiments
                decided = _decided(observations)
                preferred = _preferred(observations)
                if decided:
                    outcome.decided += 1
                    if preferred == true_model:
                        outcome.correct_when_decided += 1
                    else:
                        outcome.false_conclusions += 1
                else:
                    outcome.undecided += 1
                program_observations = observations
                if use_memory and memory is not None:
                    for obs in observations:
                        memory.add(
                            f"Finding: at coupling {obs.coupling} the measured phase locking was {obs.coherence}",
                            agent_id="research-program",
                            metadata={
                                "kind": "observation",
                                "coupling": obs.coupling,
                                "coherence": obs.coherence,
                                "replicates": obs.replicates,
                                "program": program,
                            },
                        )

            # Held-out replication for the program.
            replication_twin = ServiceTwin(
                Scenario(seed=base_seed + program * 100 + 999, true_model=true_model)
            )
            response = replication_twin.run_experiment(HELD_OUT, replicates=REPLICATES)
            held_out = Observation(coupling=HELD_OUT, coherence=response["coherence"], replicates=REPLICATES)
            # Independent replication: held-out evidence alone vs the original verdict.
            replication_consistent = _preferred([held_out]) == _preferred(program_observations)
            outcomes[arm].replications += 1
            if replication_consistent:
                outcomes[arm].replication_successes += 1
            program_records.append(
                {
                    "arm": arm,
                    "program": program,
                    "true_model": true_model,
                    "experiments": program_experiments,
                    "observations": [obs.to_dict() for obs in program_observations],
                    "held_out": held_out.to_dict(),
                    "replication_consistent": replication_consistent,
                }
            )

    # -- record runs and claims -------------------------------------------------

    run_entries = {}
    for arm in ARMS:
        metrics = outcomes[arm].to_dict()
        run_id = f"{arm}-{sha256_json(metrics)[:16]}"
        run_entries[arm] = ledger.append(
            "run",
            {
                "run_id": run_id,
                "skill": "rain-central-experiment",
                "status": "ok",
                "seed": base_seed,
                "inputs_hash": sha256_json(design),
                "experiment": experiment,
                "role": "computational-scientist",
                "arm": arm,
                "metrics": metrics,
            },
        ).object
        ledger.append(
            "dataset",
            {
                "experiment": experiment,
                "name": f"central-experiment-{arm}",
                "origin": "synthetic",
                "media_type": "application/json",
                "object": ledger.put_json({"programs": [r for r in program_records if r["arm"] == arm]}),
                "provenance": {"run": run_entries[arm], "protocol": "rain-central-experiment"},
            },
        )

    def _claim(statement: str, arm: str) -> str:
        return ledger.append(
            "claim",
            {
                "experiment": experiment,
                "category": "COMPUTED",
                "statement": statement,
                "evidence": [run_entries[arm]],
                "author": {"role": "computational-scientist", "generation": "scripted"},
            },
        ).object

    memory_arm = outcomes["integrated-memory"]
    nomem_arm = outcomes["integrated-no-memory"]
    grid_arm = outcomes["grid"]
    random_arm = outcomes["random"]

    h1_reduction = (
        1.0 - memory_arm.total_experiments / nomem_arm.total_experiments
        if nomem_arm.total_experiments
        else 0.0
    )
    h1_pass = h1_reduction >= 0.25
    false_rate_memory = memory_arm.false_conclusions / max(1, memory_arm.missions)
    false_rate_nomem = nomem_arm.false_conclusions / max(1, nomem_arm.missions)
    h2_pass = false_rate_memory <= false_rate_nomem + 0.05
    h3_pass = (
        memory_arm.mean_experiments < grid_arm.mean_experiments
        and memory_arm.mean_experiments < random_arm.mean_experiments
        and nomem_arm.mean_experiments < grid_arm.mean_experiments
        and nomem_arm.mean_experiments < random_arm.mean_experiments
    )

    hypotheses = {
        "H1": {
            "statement": design["hypotheses"]["H1"],
            "measured": {
                "integrated-memory": memory_arm.total_experiments,
                "integrated-no-memory": nomem_arm.total_experiments,
                "reduction": round(h1_reduction, 4),
            },
            "threshold": 0.25,
            "passed": h1_pass,
        },
        "H2": {
            "statement": design["hypotheses"]["H2"],
            "measured": {
                "false_rate_integrated-memory": round(false_rate_memory, 4),
                "false_rate_integrated-no-memory": round(false_rate_nomem, 4),
            },
            "threshold": "+0.05",
            "passed": h2_pass,
        },
        "H3": {
            "statement": design["hypotheses"]["H3"],
            "measured": {arm_name: outcomes[arm_name].mean_experiments for arm_name in ARMS},
            "threshold": "adaptive < grid and random",
            "passed": h3_pass,
        },
    }

    for hypothesis_id, record in hypotheses.items():
        claim = _claim(
            f"{hypothesis_id}: {record['statement']} -- measured {record['measured']}; "
            f"{'passed' if record['passed'] else 'did not pass'} the preregistered threshold",
            "integrated-memory",
        )
        verdict = (
            "supported"
            if record["passed"]
            else ("contradicted" if not record["passed"] and record["measured"] else "unresolved")
        )
        ledger.append(
            "verdict",
            {
                "experiment": experiment,
                "target": claim,
                "verdict": verdict,
                "reasons": [f"preregistered threshold {record['threshold']}"],
                "evidence": [claim],
                "author": {"role": "scientific-skeptic", "generation": "scripted"},
            },
        )

    ledger.append(
        "report",
        {
            "experiment": experiment,
            "findings": [
                {
                    "verdict": "supported" if h["passed"] else "contradicted",
                    "claims": [],
                    "statement": f"{hid}: {h['measured']}",
                }
                for hid, h in hypotheses.items()
            ],
            "limitations": [
                "the discrimination problem is synthetic and moderately easy at this noise level",
                "all policies are scripted; no language model participates in any arm",
                "three missions per program; small-sample uncertainty is not modeled",
            ],
            "reproduction": "rerun with the same seeds and design for exact reproduction",
            "author": {"role": "pi", "generation": "scripted"},
        },
    )

    problems = ledger.verify()
    return CentralExperimentV1Result(
        arms=outcomes,
        hypotheses=hypotheses,
        elapsed_s=time.perf_counter() - started,
        ledger_verified=not problems,
    )


def _decided(observations: list[Observation]) -> bool:
    return CandidateModels(replicates=REPLICATES).decided(observations)


def _preferred(observations: list[Observation]) -> str:
    return CandidateModels(replicates=REPLICATES).preferred_model(observations)


def _recall(memory: ScientificMemory | None) -> list[Observation]:
    if memory is None:
        return []
    found = memory.get_all(filters={"agent_id": "research-program", "kind": "observation"})
    seen: dict[float, Observation] = {}
    for item in found["results"]:
        coupling = round(float(item["metadata"].get("coupling", 0.0)), 6)
        seen[coupling] = Observation(
            coupling=coupling,
            coherence=float(item["metadata"].get("coherence", 0.0)),
            replicates=int(item["metadata"].get("replicates", REPLICATES)),
        )
    return list(seen.values())
