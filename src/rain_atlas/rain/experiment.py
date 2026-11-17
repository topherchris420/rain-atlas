"""The central scientific experiment of the unified architecture -- protocol v2.

Research question
-----------------

*Does combining adaptive experiment selection with persistent scientific
memory let a research system reach correct decisions with fewer experiments,
without increasing false conclusions -- including when the world changes
after the memory was written?*

Why a second protocol
---------------------

Protocol v1 (:mod:`rain_atlas.rain.experiment_v1`) could not fail: the world
never changed, the memory arm reused the previous mission's decisive data,
one experiment almost always decided, no arm ever erred, and six programs
were judged on point estimates. v2 is built so that every hypothesis can be
contradicted by the data:

* **The problem needs several experiments.** Observation noise is 0.15 per
  replicate (v1: 0.06). With 4 replicates, one experiment at the most
  informative condition carries about 1.8 nats of expected evidence,
  against a decision threshold of 5 nats.
* **The world can change.** Half of the programs are *shifting*: the hidden
  model switches once, at an unannounced mission. Remembered evidence is
  then stale, which is exactly when persistent memory can mislead.
* **Memory has to earn its keep.** Two memory architectures are compared
  with the same selection policy and no memory:

  - ``naive-memory`` (the v1 integrated arm): pool remembered and fresh
    evidence and decide on the pooled Bayes factor -- possibly without
    running anything;
  - ``verified-memory`` (the integrated architecture): remembered evidence
    counts only after fresh evidence in *this* mission confirms it (a
    3-nat sequential check). Fresh evidence that contradicts memory at that
    level quarantines the memories (deleted with history retained, a
    contradiction recorded) and the mission continues on fresh evidence
    alone. The stale-memory error per check is bounded by roughly
    ``1 / (1 + e^3)`` (about 4.7 %).
* **Baselines are not straw men.** Besides the ascending sweep and seeded
  random selection, an **ordering control** runs the grid high to low with
  no model knowledge. Maximum-disagreement selection does not depend on the
  observations here, so the control should match it exactly; if it does,
  the selection advantage is an ordering effect, not adaptivity.
* **Uncertainty decides.** 150 programs per regime x 4 missions. Programs
  are the independent units: every arm sees the same twins (common random
  numbers), and intervals come from a paired, regime-stratified bootstrap
  over programs. Each of the four hypotheses is tested at a Bonferroni level
  of 0.05 / 4. For false-conclusion rates the interval is the union of the
  bootstrap interval and Newcombe's score interval, so zero-event cells do
  not produce falsely narrow intervals. Verdicts are three-valued:
  *supported* when the whole interval satisfies the hypothesis,
  *contradicted* when the whole interval violates it, *unresolved* otherwise.

Preregistered hypotheses
------------------------

* **H1 (efficiency):** in stationary worlds, ``verified-memory`` needs at
  least 25 % fewer experiments per mission than ``no-memory``.
* **H2 (safety):** in shifting worlds, the ``verified-memory``
  false-conclusion rate exceeds the ``no-memory`` rate by at most 5
  percentage points.
* **H3 (the v1 blind spot):** in shifting worlds, the ``naive-memory``
  false-conclusion rate exceeds the ``no-memory`` rate by more than 5
  percentage points.
* **H4 (selection):** across both regimes, ``no-memory`` (maximum
  disagreement, no memory) needs fewer experiments per mission than both
  the ascending sweep and random selection.

All policies are deterministic scripted code; no language model is involved
in any arm. The preregistration record is written to the ledger before any
twin is run.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..canonical import sha256_json
from ..ledger.store import Ledger
from ..memory import ScientificMemory
from ..science.uncertainty import wilson
from ..simulation import Scenario, ServiceTwin
from .experiment_v1 import CentralExperimentV1Result, run_central_experiment_v1
from .models import CANDIDATES, DAMPED, LINEAR, CandidateModels, Observation
from .policies import AdaptiveSelector, DescendingGridSelector, GridSelector, RandomSelector, Selector

PROTOCOL = "rain-central/v2"
PROTOCOLS = ("v2", "v1")

GRID = [round(0.1 * i, 2) for i in range(1, 11)]
OBSERVATION_SIGMA = 0.15
REPLICATES = 4
BUDGET_PER_MISSION = 8
MISSIONS_PER_PROGRAM = 4
PROGRAMS_PER_REGIME = 150
REGIMES = ("stationary", "shifting")
DECISION_NATS = 5.0
CONFIRMATION_NATS = 3.0
ALPHA = 0.05
FAMILY = ("H1", "H2", "H3", "H4")
BOOTSTRAP_RESAMPLES = 4000
BASE_SEED = 20261117

VERIFIED = "verified-memory"
NAIVE = "naive-memory"
NO_MEMORY = "no-memory"
GRID_ASCENDING = "grid-ascending"
GRID_DESCENDING = "grid-descending"
RANDOM = "random"
ARMS = (VERIFIED, NAIVE, NO_MEMORY, GRID_ASCENDING, GRID_DESCENDING, RANDOM)
MEMORY_ARMS = (VERIFIED, NAIVE)

H1_MIN_REDUCTION = 0.25
H2_MAX_EXCESS = 0.05
H3_MIN_EXCESS = 0.05

HYPOTHESES = {
    "H1": "in stationary worlds, verified-memory needs >=25% fewer experiments per mission than no-memory",
    "H2": "in shifting worlds, the verified-memory false-conclusion rate exceeds no-memory by <=5 percentage points",
    "H3": "in shifting worlds, the naive-memory false-conclusion rate exceeds no-memory by >5 percentage points",
    "H4": "across regimes, no-memory (maximum disagreement) needs fewer experiments per mission than the ascending sweep and random selection",
}


def _seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:6], "big")


def _model_for(log_bayes: float) -> str:
    return LINEAR if log_bayes >= 0 else DAMPED


# -- the world ------------------------------------------------------------------


@dataclass(frozen=True)
class Program:
    """One research program: a sequence of missions on twins hidden from the agents."""

    regime: str
    index: int
    models: tuple[str, ...]
    shift_at: int | None
    seeds: tuple[int, ...]

    @property
    def scope(self) -> str:
        return f"{self.regime}-{self.index:04d}"

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "index": self.index,
            "models": list(self.models),
            "shift_at": self.shift_at,
            "seeds": list(self.seeds),
        }


def build_programs(base_seed: int, programs_per_regime: int, missions: int) -> list[Program]:
    """Deterministic worlds; identical for every arm (common random numbers)."""

    if missions < 2:
        raise ValueError("protocol v2 needs at least two missions per program")
    programs = []
    for regime in REGIMES:
        for index in range(programs_per_regime):
            rng = random.Random(f"{base_seed}:{regime}:{index}:world")
            first = rng.choice(CANDIDATES)
            if regime == "stationary":
                shift_at = None
                models = (first,) * missions
            else:
                shift_at = rng.randint(1, missions - 1)
                other = DAMPED if first == LINEAR else LINEAR
                models = (first,) * shift_at + (other,) * (missions - shift_at)
            seeds = tuple(_seed(base_seed, regime, index, mission) for mission in range(missions))
            programs.append(Program(regime, index, models, shift_at, seeds))
    return programs


# -- one mission --------------------------------------------------------------------


@dataclass
class MissionRecord:
    arm: str
    regime: str
    program: int
    mission: int
    true_model: str
    after_shift: bool
    experiments: int
    decided: bool
    preferred: str
    remembered: int
    quarantined: bool
    log_bayes_fresh: float
    log_bayes_memory: float

    @property
    def false_conclusion(self) -> bool:
        return self.decided and self.preferred != self.true_model

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "regime": self.regime,
            "program": self.program,
            "mission": self.mission,
            "true_model": self.true_model,
            "after_shift": self.after_shift,
            "experiments": self.experiments,
            "decided": self.decided,
            "preferred": self.preferred,
            "false_conclusion": self.false_conclusion,
            "remembered": self.remembered,
            "quarantined": self.quarantined,
            "log_bayes_fresh": round(self.log_bayes_fresh, 6),
            "log_bayes_memory": round(self.log_bayes_memory, 6),
        }


def _decision(arm: str, fresh: float, memory: float, has_memory: bool) -> tuple[bool, str]:
    """The preregistered decision rule for *arm* given log Bayes factors."""

    if arm == NAIVE:
        pooled = fresh + memory
        return abs(pooled) >= DECISION_NATS, _model_for(pooled)
    if arm == VERIFIED and has_memory:
        if abs(fresh) >= DECISION_NATS:
            return True, _model_for(fresh)
        pooled = fresh + memory
        confirmed = abs(fresh) >= CONFIRMATION_NATS and _model_for(fresh) == _model_for(memory)
        return confirmed and abs(pooled) >= DECISION_NATS, _model_for(pooled)
    return abs(fresh) >= DECISION_NATS, _model_for(fresh)


def _selector(arm: str, seed: int, models: CandidateModels) -> Selector:
    if arm in (VERIFIED, NAIVE, NO_MEMORY):
        return AdaptiveSelector(models)
    if arm == GRID_ASCENDING:
        return GridSelector()
    if arm == GRID_DESCENDING:
        return DescendingGridSelector()
    if arm == RANDOM:
        return RandomSelector(seed)
    raise ValueError(f"unknown arm {arm!r}")


def _recall(memory: ScientificMemory, scope: str) -> list[Observation]:
    found = memory.get_all(filters={"agent_id": scope, "kind": "observation"})
    return [
        Observation(
            coupling=float(item["metadata"]["coupling"]),
            coherence=float(item["metadata"]["coherence"]),
            replicates=int(item["metadata"]["replicates"]),
        )
        for item in found["results"]
    ]


def _remember(memory: ScientificMemory, scope: str, observations: list[Observation], mission: int) -> None:
    for obs in observations:
        memory.add(
            f"Observation: coupling {obs.coupling} gave phase coherence {obs.coherence} (mission {mission})",
            agent_id=scope,
            metadata={
                "kind": "observation",
                "coupling": obs.coupling,
                "coherence": obs.coherence,
                "replicates": obs.replicates,
                "mission": mission,
            },
            infer=False,
        )


def _quarantine(memory: ScientificMemory, scope: str, mission: int, fresh: float, remembered: float) -> None:
    memory.delete_all(filters={"agent_id": scope, "kind": "observation"})
    memory.add(
        f"Contradiction: fresh evidence in mission {mission} (log Bayes factor {fresh:+.2f}) contradicts "
        f"the remembered conclusion ({remembered:+.2f}); earlier observations quarantined",
        agent_id=scope,
        metadata={"kind": "contradiction", "mission": mission},
        infer=False,
    )


def run_mission(
    arm: str,
    program: Program,
    mission: int,
    *,
    models: CandidateModels,
    budget: int,
    base_seed: int,
    memory: ScientificMemory | None = None,
) -> MissionRecord:
    """Run one mission of *program* under *arm*'s policy and decision rule."""

    true_model = program.models[mission]
    twin = ServiceTwin(
        Scenario(
            seed=program.seeds[mission],
            true_model=true_model,
            hidden_parameters={"observation_sigma": OBSERVATION_SIGMA},
        )
    )
    selector = _selector(arm, _seed(base_seed, "random", program.scope, mission), models)
    remembered = _recall(memory, program.scope) if memory is not None and arm in MEMORY_ARMS else []
    log_memory = models.log_bayes_factor(remembered) if remembered else 0.0
    fresh: list[Observation] = []
    quarantined = False
    experiments = 0
    while True:
        log_fresh = models.log_bayes_factor(fresh)
        if (
            arm == VERIFIED
            and remembered
            and abs(log_fresh) >= CONFIRMATION_NATS
            and _model_for(log_fresh) != _model_for(log_memory)
        ):
            assert memory is not None
            _quarantine(memory, program.scope, mission, log_fresh, log_memory)
            quarantined = True
            remembered = []
            log_memory = 0.0
        decided, preferred = _decision(arm, log_fresh, log_memory, bool(remembered))
        if decided or experiments >= budget:
            break
        condition = selector.next_condition(GRID, fresh)
        if condition is None:
            break
        response = twin.run_experiment(condition, replicates=REPLICATES)
        fresh.append(Observation(coupling=condition, coherence=response["coherence"], replicates=REPLICATES))
        experiments += 1
    if memory is not None and arm in MEMORY_ARMS:
        _remember(memory, program.scope, fresh, mission)
    return MissionRecord(
        arm=arm,
        regime=program.regime,
        program=program.index,
        mission=mission,
        true_model=true_model,
        after_shift=program.shift_at is not None and mission >= program.shift_at,
        experiments=experiments,
        decided=decided,
        preferred=preferred,
        remembered=len(remembered),
        quarantined=quarantined,
        log_bayes_fresh=log_fresh,
        log_bayes_memory=log_memory,
    )


# -- analysis -----------------------------------------------------------------------


@dataclass
class ArmSummary:
    arm: str
    regime: str
    missions: int
    experiments: int
    decided: int
    false_conclusions: int
    quarantines: int
    after_shift_missions: int
    after_shift_false: int

    @property
    def mean_experiments(self) -> float:
        return self.experiments / self.missions if self.missions else 0.0

    def to_dict(self) -> dict:
        false_rate = wilson(self.false_conclusions, self.missions) if self.missions else None
        return {
            "arm": self.arm,
            "regime": self.regime,
            "missions": self.missions,
            "experiments": self.experiments,
            "mean_experiments": round(self.mean_experiments, 4),
            "decided": self.decided,
            "undecided": self.missions - self.decided,
            "false_conclusions": self.false_conclusions,
            "false_rate": round(self.false_conclusions / self.missions, 4) if self.missions else 0.0,
            "false_rate_wilson95": [round(false_rate["low"], 4), round(false_rate["high"], 4)]
            if false_rate
            else None,
            "quarantines": self.quarantines,
            "after_shift_missions": self.after_shift_missions,
            "after_shift_false": self.after_shift_false,
        }


def _summarize(records: list[MissionRecord]) -> dict[str, dict[str, ArmSummary]]:
    out: dict[str, dict[str, ArmSummary]] = {}
    for arm in ARMS:
        out[arm] = {}
        for regime in (*REGIMES, "all"):
            rows = [r for r in records if r.arm == arm and (regime == "all" or r.regime == regime)]
            out[arm][regime] = ArmSummary(
                arm=arm,
                regime=regime,
                missions=len(rows),
                experiments=sum(r.experiments for r in rows),
                decided=sum(r.decided for r in rows),
                false_conclusions=sum(r.false_conclusion for r in rows),
                quarantines=sum(r.quarantined for r in rows),
                after_shift_missions=sum(r.after_shift for r in rows),
                after_shift_false=sum(r.after_shift and r.false_conclusion for r in rows),
            )
    return out


class _Bootstrap:
    """Paired, regime-stratified bootstrap over programs (the independent units)."""

    def __init__(
        self, records: list[MissionRecord], programs: int, missions: int, *, seed: int, resamples: int
    ):
        self.experiments: dict[tuple[str, str], np.ndarray] = {}
        self.false: dict[tuple[str, str], np.ndarray] = {}
        for arm in ARMS:
            for regime in REGIMES:
                exp = np.zeros((programs, missions))
                err = np.zeros((programs, missions))
                for r in records:
                    if r.arm == arm and r.regime == regime:
                        exp[r.program, r.mission] = r.experiments
                        err[r.program, r.mission] = float(r.false_conclusion)
                self.experiments[arm, regime] = exp
                self.false[arm, regime] = err
        rng = np.random.default_rng(seed)
        self.index = {regime: rng.integers(0, programs, size=(resamples, programs)) for regime in REGIMES}

    def _mean(self, table: dict, arm: str, regimes: tuple[str, ...], resampled: bool) -> np.ndarray | float:
        if not resampled:
            return float(np.mean(np.concatenate([table[arm, r].ravel() for r in regimes])))
        total = sum(table[arm, r][self.index[r]].sum(axis=(1, 2)) for r in regimes)
        count = sum(table[arm, r].size for r in regimes)
        return total / count

    def mean_experiments(self, arm: str, regimes: tuple[str, ...], resampled: bool = True):
        return self._mean(self.experiments, arm, regimes, resampled)

    def false_rate(self, arm: str, regimes: tuple[str, ...], resampled: bool = True):
        return self._mean(self.false, arm, regimes, resampled)


def _percentile(samples: np.ndarray, alpha: float) -> tuple[float, float]:
    finite = samples[np.isfinite(samples)]
    low, high = np.quantile(finite, [alpha / 2, 1 - alpha / 2])
    return float(low), float(high)


def _newcombe(x1: int, n1: int, x2: int, n2: int, alpha: float) -> tuple[float, float]:
    """Newcombe hybrid score interval for p1 - p2 (handles zero events)."""

    a, b = wilson(x1, n1, alpha), wilson(x2, n2, alpha)
    p1, p2 = x1 / n1, x2 / n2
    low = p1 - p2 - math.sqrt((p1 - a["low"]) ** 2 + (b["high"] - p2) ** 2)
    high = p1 - p2 + math.sqrt((a["high"] - p1) ** 2 + (p2 - b["low"]) ** 2)
    return low, high


def _verdict(interval: tuple[float, float], test: Callable[[float], bool]) -> str:
    low, high = interval
    if test(low) and test(high):
        return "supported"
    if not test(low) and not test(high):
        return "contradicted"
    return "unresolved"


def _evaluate(
    records: list[MissionRecord],
    summaries: dict,
    programs: int,
    missions: int,
    base_seed: int,
    resamples: int,
) -> dict[str, dict[str, Any]]:
    boot = _Bootstrap(records, programs, missions, seed=_seed(base_seed, "bootstrap"), resamples=resamples)
    alpha = ALPHA / len(FAMILY)
    stationary, shifting, both = ("stationary",), ("shifting",), REGIMES
    out: dict[str, dict[str, Any]] = {}

    # H1: relative reduction in experiments per mission, stationary worlds.
    base = boot.mean_experiments(NO_MEMORY, stationary)
    with np.errstate(divide="ignore", invalid="ignore"):
        samples = 1.0 - boot.mean_experiments(VERIFIED, stationary) / base
    point_base = boot.mean_experiments(NO_MEMORY, stationary, resampled=False)
    point = (
        1.0 - boot.mean_experiments(VERIFIED, stationary, resampled=False) / point_base if point_base else 0.0
    )
    interval = _percentile(samples, alpha)
    out["H1"] = {
        "estimate": point,
        "interval": interval,
        "threshold": H1_MIN_REDUCTION,
        "verdict": _verdict(interval, lambda v: v >= H1_MIN_REDUCTION),
        "arms": [VERIFIED, NO_MEMORY],
    }

    # H2 / H3: excess false-conclusion rate over no-memory, shifting worlds.
    reference = summaries[NO_MEMORY]["shifting"]
    for hypothesis, arm, test, threshold in (
        ("H2", VERIFIED, lambda v: v <= H2_MAX_EXCESS, H2_MAX_EXCESS),
        ("H3", NAIVE, lambda v: v > H3_MIN_EXCESS, H3_MIN_EXCESS),
    ):
        arm_summary = summaries[arm]["shifting"]
        samples = boot.false_rate(arm, shifting) - boot.false_rate(NO_MEMORY, shifting)
        b_low, b_high = _percentile(samples, alpha)
        n_low, n_high = _newcombe(
            arm_summary.false_conclusions,
            arm_summary.missions,
            reference.false_conclusions,
            reference.missions,
            alpha,
        )
        interval = (min(b_low, n_low), max(b_high, n_high))
        out[hypothesis] = {
            "estimate": boot.false_rate(arm, shifting, resampled=False)
            - boot.false_rate(NO_MEMORY, shifting, resampled=False),
            "interval": interval,
            "interval_bootstrap": (b_low, b_high),
            "interval_newcombe": (n_low, n_high),
            "threshold": threshold,
            "verdict": _verdict(interval, test),
            "arms": [arm, NO_MEMORY],
        }

    # H4: experiment difference no-memory minus each baseline, both regimes
    # (each of the two comparisons at alpha/2: both must hold).
    parts = {}
    for baseline in (GRID_ASCENDING, RANDOM):
        samples = boot.mean_experiments(NO_MEMORY, both) - boot.mean_experiments(baseline, both)
        interval = _percentile(samples, alpha / 2)
        parts[baseline] = {
            "estimate": boot.mean_experiments(NO_MEMORY, both, resampled=False)
            - boot.mean_experiments(baseline, both, resampled=False),
            "interval": interval,
            "verdict": _verdict(interval, lambda v: v < 0),
        }
    verdicts = {part["verdict"] for part in parts.values()}
    combined = (
        "supported"
        if verdicts == {"supported"}
        else ("contradicted" if "contradicted" in verdicts else "unresolved")
    )
    out["H4"] = {
        "comparisons": parts,
        "threshold": 0.0,
        "verdict": combined,
        "arms": [NO_MEMORY, GRID_ASCENDING, RANDOM],
    }

    for record in out.values():
        record["alpha"] = alpha
    return out


def _ordering_control(records: list[MissionRecord]) -> dict[str, Any]:
    adaptive = {(r.regime, r.program, r.mission): r for r in records if r.arm == NO_MEMORY}
    fixed = {(r.regime, r.program, r.mission): r for r in records if r.arm == GRID_DESCENDING}
    identical = sum(
        1
        for key, a in adaptive.items()
        if (a.experiments, a.decided, a.preferred)
        == (fixed[key].experiments, fixed[key].decided, fixed[key].preferred)
    )
    return {
        "missions": len(adaptive),
        "identical": identical,
        "all_identical": identical == len(adaptive),
        "statement": "maximum-disagreement selection versus a fixed high-to-low sweep that uses no model knowledge",
    }


# -- the experiment -----------------------------------------------------------------


@dataclass
class CentralExperimentResult:
    protocol: str
    summaries: dict[str, dict[str, ArmSummary]] = field(default_factory=dict)
    hypotheses: dict[str, dict[str, Any]] = field(default_factory=dict)
    ordering_control: dict[str, Any] = field(default_factory=dict)
    programs_per_regime: int = 0
    missions_per_program: int = 0
    elapsed_s: float = 0.0
    ledger_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "programs_per_regime": self.programs_per_regime,
            "missions_per_program": self.missions_per_program,
            "arms": {
                arm: {regime: summary.to_dict() for regime, summary in by_regime.items()}
                for arm, by_regime in self.summaries.items()
            },
            "hypotheses": _rounded(self.hypotheses),
            "ordering_control": self.ordering_control,
            "elapsed_s": round(self.elapsed_s, 3),
            "ledger_verified": self.ledger_verified,
        }


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (list, tuple)):
        return [_rounded(v) for v in value]
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    return value


def design(
    programs_per_regime: int = PROGRAMS_PER_REGIME,
    missions: int = MISSIONS_PER_PROGRAM,
    budget: int = BUDGET_PER_MISSION,
    base_seed: int = BASE_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, Any]:
    """The complete preregistered design, as recorded in the ledger."""

    return {
        "protocol": PROTOCOL,
        "supersedes": {
            "protocol": "rain-central/v1",
            "reasons": [
                "stationary worlds only: memory could never be stale",
                "missions after the first reused decisive memory, so the 68% saving was 1 - 1/3 by construction",
                "one experiment almost always decided (expected 11 nats per experiment vs a 5-nat threshold)",
                "no false conclusions in any arm, so the safety hypothesis compared 0 with 0",
                "six programs per arm judged on point estimates without uncertainty",
            ],
        },
        "arms": list(ARMS),
        "regimes": list(REGIMES),
        "programs_per_regime": programs_per_regime,
        "missions_per_program": missions,
        "budget_per_mission": budget,
        "grid": GRID,
        "replicates": REPLICATES,
        "observation_sigma": OBSERVATION_SIGMA,
        "decision_nats": DECISION_NATS,
        "confirmation_nats": CONFIRMATION_NATS,
        "base_seed": base_seed,
        "world": "stationary: one hidden model per program; shifting: the model switches once at a mission drawn uniformly from 1..M-1; the first model is drawn per program; agents never observe either",
        "memory": {
            NAIVE: "pool remembered and fresh evidence; decide when |pooled log BF| >= 5",
            VERIFIED: "decide on fresh evidence >= 5 nats, or on pooled >= 5 nats once fresh evidence >= 3 nats agrees with memory; fresh evidence >= 3 nats against memory quarantines it",
            "store": "program-scoped ScientificMemory (in-process); observations stored verbatim; quarantine deletes with history retained and records a contradiction",
        },
        "selection": {
            VERIFIED: "maximum disagreement",
            NAIVE: "maximum disagreement",
            NO_MEMORY: "maximum disagreement",
            GRID_ASCENDING: "fixed low-to-high sweep",
            GRID_DESCENDING: "fixed high-to-low sweep (ordering control)",
            RANDOM: "seeded uniform choice among untested conditions",
        },
        "hypotheses": HYPOTHESES,
        "analysis": {
            "unit": "program (paired across arms by common random numbers)",
            "intervals": "regime-stratified percentile bootstrap over programs",
            "resamples": resamples,
            "family_alpha": ALPHA,
            "per_hypothesis_alpha": ALPHA / len(FAMILY),
            "rates": "union of the bootstrap and Newcombe hybrid-score intervals",
            "H4": "both comparisons at alpha/2; supported only if both are",
            "verdicts": "supported if the whole interval satisfies the hypothesis, contradicted if it wholly violates it, unresolved otherwise",
        },
    }


def run_central_experiment(
    root: Path,
    *,
    protocol: str = "v2",
    programs: int | None = None,
    missions_per_program: int | None = None,
    budget: int | None = None,
    base_seed: int | None = None,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> CentralExperimentResult | CentralExperimentV1Result:
    """Execute the central experiment and write its ATLAS ledger under *root*.

    *protocol* ``"v2"`` (default) runs the falsifiable design; ``"v1"``
    reproduces the superseded 2026-11-16 protocol exactly. *programs* is the
    number of programs per regime for v2 (per arm for v1).
    """

    if protocol == "v1":
        kwargs: dict[str, Any] = {}
        if programs is not None:
            kwargs["programs"] = programs
        if missions_per_program is not None:
            kwargs["missions_per_program"] = missions_per_program
        if budget is not None:
            kwargs["budget"] = budget
        if base_seed is not None:
            kwargs["base_seed"] = base_seed
        return run_central_experiment_v1(root, **kwargs)
    if protocol != "v2":
        raise ValueError(f"unknown protocol {protocol!r}; expected one of {PROTOCOLS}")

    programs = PROGRAMS_PER_REGIME if programs is None else programs
    missions = MISSIONS_PER_PROGRAM if missions_per_program is None else missions_per_program
    budget = BUDGET_PER_MISSION if budget is None else budget
    base_seed = BASE_SEED if base_seed is None else base_seed
    if programs < 2:
        raise ValueError("protocol v2 needs at least two programs per regime")

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError("central experiment root already has a ledger; use a fresh directory")
    plan = design(programs, missions, budget, base_seed, resamples)

    # Preregistration precedes every twin run.
    experiment = ledger.append(
        "preregistration",
        {
            "title": "Central experiment v2: verified memory and adaptive selection under a changing world",
            "question": "Does adaptive selection with persistent scientific memory reach correct decisions with fewer experiments, without more false conclusions, including after the world changes?",
            "hypothesis": "Memory that must be confirmed by fresh evidence saves experiments in stationary worlds without raising false conclusions in shifting worlds; unverified memory raises them.",
            "null_hypothesis": "Memory architecture and selection policy change neither experiment efficiency nor the false-conclusion rate.",
            "design": plan,
            "design_digest": sha256_json(plan),
            "acceptance": [f"{hid}: {statement}" for hid, statement in HYPOTHESES.items()],
            "created_by": {"role": "pi", "generation": "scripted"},
        },
    ).object

    models = CandidateModels(
        observation_sigma=OBSERVATION_SIGMA, replicates=REPLICATES, decision_log_bayes=DECISION_NATS
    )
    worlds = build_programs(base_seed, programs, missions)
    records: list[MissionRecord] = []
    memory_dumps: dict[str, list[dict[str, Any]]] = {arm: [] for arm in MEMORY_ARMS}
    for arm in ARMS:
        for program in worlds:
            memory = ScientificMemory(None, clock=lambda: 0.0) if arm in MEMORY_ARMS else None
            for mission in range(missions):
                records.append(
                    run_mission(
                        arm,
                        program,
                        mission,
                        models=models,
                        budget=budget,
                        base_seed=base_seed,
                        memory=memory,
                    )
                )
            if memory is not None:
                memory_dumps[arm].append(
                    {
                        "program": program.scope,
                        "statistics": memory.statistics(),
                        "contradictions": [
                            item["memory"]
                            for item in memory.get_all(
                                filters={"agent_id": program.scope, "kind": "contradiction"}
                            )["results"]
                        ],
                    }
                )

    summaries = _summarize(records)
    hypotheses = _evaluate(records, summaries, programs, missions, base_seed, resamples)
    control = _ordering_control(records)

    # -- evidence ------------------------------------------------------------------
    ledger.append(
        "dataset",
        {
            "experiment": experiment,
            "name": "central-v2-worlds",
            "origin": "synthetic",
            "media_type": "application/json",
            "object": ledger.put_json({"programs": [p.to_dict() for p in worlds]}),
            "provenance": {"protocol": PROTOCOL, "generator": "build_programs", "base_seed": base_seed},
        },
    )
    runs: dict[str, str] = {}
    for arm in ARMS:
        metrics = {regime: summary.to_dict() for regime, summary in summaries[arm].items()}
        runs[arm] = ledger.append(
            "run",
            {
                "run_id": f"{arm}-{sha256_json(metrics)[7:23]}",
                "skill": "rain-central-experiment",
                "protocol": PROTOCOL,
                "status": "ok",
                "seed": base_seed,
                "inputs_hash": sha256_json(plan),
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
                "name": f"central-v2-missions-{arm}",
                "origin": "synthetic",
                "media_type": "application/json",
                "object": ledger.put_json({"missions": [r.to_dict() for r in records if r.arm == arm]}),
                "provenance": {"run": runs[arm], "protocol": PROTOCOL},
            },
        )
        if arm in MEMORY_ARMS:
            ledger.append(
                "dataset",
                {
                    "experiment": experiment,
                    "name": f"central-v2-memory-{arm}",
                    "origin": "synthetic",
                    "media_type": "application/json",
                    "object": ledger.put_json({"programs": memory_dumps[arm]}),
                    "provenance": {"run": runs[arm], "protocol": PROTOCOL},
                },
            )

    findings = []
    for hypothesis_id, result in hypotheses.items():
        claim = ledger.append(
            "claim",
            {
                "experiment": experiment,
                "category": "COMPUTED",
                "statement": f"{hypothesis_id}: {HYPOTHESES[hypothesis_id]} -- {_describe(hypothesis_id, result)}",
                "evidence": [runs[arm] for arm in result["arms"]],
                "author": {"role": "computational-scientist", "generation": "scripted"},
            },
        ).object
        ledger.append(
            "verdict",
            {
                "experiment": experiment,
                "target": claim,
                "verdict": result["verdict"],
                "reasons": [
                    f"{1 - result['alpha']:.4f} interval versus the preregistered threshold {result['threshold']}",
                    _describe(hypothesis_id, result),
                ],
                "evidence": [claim],
                "author": {"role": "scientific-skeptic", "generation": "scripted"},
            },
        )
        findings.append(
            {"verdict": result["verdict"], "claims": [claim], "statement": _describe(hypothesis_id, result)}
        )

    control_claim = ledger.append(
        "claim",
        {
            "experiment": experiment,
            "category": "COMPUTED",
            "statement": (
                f"Ordering control: {control['identical']} of {control['missions']} no-memory missions are "
                "identical (experiments, decision, preferred model) to a fixed high-to-low sweep"
            ),
            "evidence": [runs[NO_MEMORY], runs[GRID_DESCENDING]],
            "author": {"role": "scientific-skeptic", "generation": "scripted"},
        },
    ).object
    if control["all_identical"]:
        interpretation = ledger.append(
            "claim",
            {
                "experiment": experiment,
                "category": "INTERPRETED",
                "statement": (
                    "In this two-model problem the selection advantage of maximum disagreement over the "
                    "ascending sweep is an ordering effect: a fixed design that runs the most informative "
                    "conditions first reproduces it exactly, so H4 is not evidence of adaptivity"
                ),
                "evidence": [control_claim],
                "author": {"role": "scientific-skeptic", "generation": "scripted"},
            },
        ).object
        findings.append(
            {
                "verdict": "supported",
                "claims": [control_claim, interpretation],
                "statement": "ordering control",
            }
        )

    ledger.append(
        "report",
        {
            "experiment": experiment,
            "protocol": PROTOCOL,
            "findings": findings,
            "limitations": [
                "the discrimination problem is synthetic: two known surrogate models with correctly specified Gaussian noise",
                "one regime change per shifting program, at an unannounced mission; other change patterns are untested",
                "the confirmation threshold (3 nats) was fixed a priori from the sequential error bound, not tuned",
                "all policies are scripted; no language model participates in any arm",
                "missions within a program are dependent; programs are the independent units of analysis",
            ],
            "reproduction": "atlas rain central --protocol v2 with the recorded design (deterministic for the base seed)",
            "author": {"role": "pi", "generation": "scripted"},
        },
    )

    problems = ledger.verify()
    return CentralExperimentResult(
        protocol=PROTOCOL,
        summaries=summaries,
        hypotheses=hypotheses,
        ordering_control=control,
        programs_per_regime=programs,
        missions_per_program=missions,
        elapsed_s=time.perf_counter() - started,
        ledger_verified=not problems,
    )


def _describe(hypothesis_id: str, result: dict[str, Any]) -> str:
    if hypothesis_id == "H4":
        parts = [
            f"vs {baseline}: {part['estimate']:+.3f} experiments/mission "
            f"[{part['interval'][0]:+.3f}, {part['interval'][1]:+.3f}] ({part['verdict']})"
            for baseline, part in result["comparisons"].items()
        ]
        return "; ".join(parts) + f" -> {result['verdict']}"
    low, high = result["interval"]
    unit = "reduction" if hypothesis_id == "H1" else "excess false-conclusion rate"
    return (
        f"{unit} {result['estimate']:+.4f}, interval [{low:+.4f}, {high:+.4f}] vs threshold "
        f"{result['threshold']} -> {result['verdict']}"
    )
