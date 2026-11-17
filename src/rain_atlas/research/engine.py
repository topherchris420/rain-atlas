"""The research loop: plan, predict, execute, analyze, critique, revise, stop.

One :class:`ResearchEngine` runs one mission on one apparatus. Every decision
is a deterministic function of the charter, the seeds and the observations,
so a mission can be replayed exactly (that is how resume works).

Loop, per step::

    analyze      exact evidence over the working hypotheses (plus change
                 points; plus memory-valid / memory-stale regimes)
    critique     score tests for unanticipated terms, residual whiteness,
                 the Gaussian-noise assumption; admitted terms and revised
                 assumptions are recorded as revisions, then re-analyze
    decide       leading explanation >= decision probability, change question
                 resolved, attribution resolved, newest residuals white
    challenge    if decided: fresh conditions chosen to expose the leading
                 explanation, prediction recorded before the run; a failed
                 challenge sends the loop back to exploration
    explore      otherwise: the policy's next design (closed loop: maximum
                 expected information gain)
    stop         challenged decision, budget exhausted, or futility

Claims are scored by the existing three-valued verdict rule
(:func:`rain_atlas.agents.disagreement.verdict`): *supported* needs the
challenge, the independent robust check and exact re-analysis to agree.
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

import numpy as np

from ..agents.disagreement import verdict as computed_verdict
from ..canonical import sha256_json
from . import critic
from .charter import space_of
from .governance import EscalationRequest, ScopeGuard, ScopeViolation
from .inference import (
    Analysis,
    ExperimentStats,
    Fit,
    Hypothesis,
    Posterior,
    PriorSpec,
    change_hypotheses,
    mixture,
)
from .oscillator import CORE, EXPANSION, INDEX, LIBRARY, OPTIONAL, Design, MemoryPrior, Observation
from .planner import (
    NOMINAL,
    Choice,
    ClosedLoop,
    FixedSweep,
    LegacyDisagreement,
    OpenLoopOptimal,
    PlanningState,
    Policy,
    RandomDesign,
    Yoked,
    contenders,
    neighbours,
    predicted_amplitude,
    structure_variants,
)

LEGACY_DECISION_NATS = 5.0
LEGACY_MEMORY_NATS = 3.0
CHANGE_AMBIGUOUS = 0.2  # P(change) above this (and below the decision level) keeps the loop investigating
MEMORY_CONFLICT_Z = 3.5


@dataclass(frozen=True)
class EngineConfig:
    policy: str = "closed-loop"
    critic: bool = True
    change_monitor: bool = True
    challenge: bool = True
    decision_rule: str = "posterior"  # posterior | bayes-factor (legacy)
    memory: str = "verified"  # verified | legacy | ignore
    eig_draws: int = 3
    eig_contenders: int = 4
    pool_size: int = 32

    def to_dict(self) -> dict:
        return dict(self.__dict__)


ARMS: dict[str, EngineConfig] = {
    "closed-loop": EngineConfig(),
    "yoked": EngineConfig(policy="yoked"),
    "open-loop-optimal": EngineConfig(policy="open-loop-optimal"),
    "fixed-sweep": EngineConfig(policy="fixed-sweep"),
    "random": EngineConfig(policy="random"),
    "legacy-atlas": EngineConfig(
        policy="legacy-atlas",
        critic=False,
        change_monitor=False,
        challenge=False,
        decision_rule="bayes-factor",
        memory="legacy",
    ),
    "closed-loop-no-critic": EngineConfig(critic=False),
    "closed-loop-no-challenge": EngineConfig(challenge=False),
}


class InstrumentLike(Protocol):
    def run(self, design: Design, index: int) -> Observation: ...


def rounded(value: Any, digits: int = 10) -> Any:
    """JSON-ready copy with floats rounded to *digits* significant figures."""

    if isinstance(value, (float, np.floating)):
        v = float(value)
        if not math.isfinite(v):
            return None
        return float(f"{v:.{digits}g}")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.ndarray):
        return rounded(value.tolist(), digits)
    if isinstance(value, dict):
        return {str(k): rounded(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v, digits) for v in value]
    return value


@dataclass
class Decision:
    ready: bool
    structure: tuple[str, ...]
    p_structure: float
    p_change: float
    change_at: int | None
    p_location: float
    changed: tuple[str, ...]
    p_attribution: float
    target: Fit
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "structure": list(self.structure),
            "p_structure": self.p_structure,
            "p_change": self.p_change,
            "change_at": self.change_at,
            "p_location": self.p_location,
            "changed": list(self.changed),
            "p_attribution": self.p_attribution,
            "target": self.target.hypothesis.label(),
            "blockers": list(self.blockers),
        }


@dataclass
class MissionResult:
    mission_id: str
    arm: str
    stop_reason: str
    experiments: int
    designs: list[Design]
    purposes: list[str]
    events: list[dict]
    conclusion: dict
    final_fit: Fit
    final_posterior: Posterior
    digest: str
    wall_s: float
    counters: dict
    escalation: dict | None = None
    memory_state: str = "absent"

    def summary(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "arm": self.arm,
            "stop_reason": self.stop_reason,
            "experiments": self.experiments,
            "designs": [d.to_dict() for d in self.designs],
            "purposes": list(self.purposes),
            "conclusion": self.conclusion,
            "digest": self.digest,
            "counters": self.counters,
            "escalation": self.escalation,
            "memory_state": self.memory_state,
        }


def make_policy(
    config: EngineConfig,
    space: dict,
    *,
    seed: int,
    memory: MemoryPrior | None,
    donor: Sequence[Design] | None,
    donor_id: str,
) -> Policy:
    if config.policy == "closed-loop":
        return ClosedLoop(config.pool_size)
    if config.policy == "fixed-sweep":
        return FixedSweep(space)
    if config.policy == "random":
        return RandomDesign(seed)
    if config.policy == "open-loop-optimal":
        nominal = dict(NOMINAL)
        if memory is not None:
            nominal = {t: memory.mean[t] for t in memory.structure}
        return OpenLoopOptimal(space, nominal)
    if config.policy == "yoked":
        return Yoked(donor or [], space, donor_id)
    if config.policy == "legacy-atlas":
        return LegacyDisagreement(space)
    raise ValueError(f"unknown policy {config.policy}")


def r_of(lm: list[dict], term: str) -> dict:
    return next((r for r in lm if r["term"] == term), {})


class ResearchEngine:
    def __init__(
        self,
        charter: dict,
        instrument: InstrumentLike,
        *,
        mission_id: str,
        seed: int,
        arm: str = "closed-loop",
        config: EngineConfig | None = None,
        memory: MemoryPrior | None = None,
        guard: ScopeGuard | None = None,
        emit: Callable[[dict], None] | None = None,
        advisor: Any | None = None,
        donor: Sequence[Design] | None = None,
        donor_id: str = "",
        on_memory: Callable[[str, dict], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.charter = charter
        self.instrument = instrument
        self.mission_id = mission_id
        self.seed = int(seed)
        self.arm = arm
        self.config = config or ARMS[arm]
        self.guard = guard or ScopeGuard(charter, mission_id)
        self.space = self.guard.space()
        self.memory = memory if self.config.memory != "ignore" else None
        self.memory_state = "active" if self.memory is not None else "absent"
        self._emit = emit
        self.advisor = advisor
        self.on_memory = on_memory
        self.clock = clock or time.perf_counter
        self.stop_rule = charter["stopping"]
        pri = charter["priors"]
        self.default_prior = PriorSpec.default(
            noise_sd=pri["noise_sd"], coefficient_sd=pri["coefficient_sd"], change_sd=pri["change_sd"]
        )
        self.memory_prior = PriorSpec.from_memory(self.memory, self.default_prior) if self.memory else None
        self.p_memory_valid = float(pri["memory_validity"])
        self.change_prior = float(pri["change_hazard"]) if self.config.change_monitor else 0.0
        self.max_expansions = int(charter["hypothesis_grammar"]["max_expansions"])
        self.policy = make_policy(
            self.config, self.space, seed=self.seed, memory=self.memory, donor=donor, donor_id=donor_id
        )
        self.observations: list[Observation] = []
        self.rows: list[tuple[np.ndarray, np.ndarray]] = []
        self.purposes: list[str] = []
        self.candidate_terms: list[str] = []
        self.robust = False
        self.weights: list[np.ndarray | None] = []
        self.events: list[dict] = []
        self.challenge_log: list[dict] = []
        self.streak = 0
        self.streak_target: tuple | None = None
        self.futile = 0
        self.last_utility: float | None = None
        self.counters = {"hypotheses_evaluated": 0, "planning_simulations": 0, "analyses": 0}
        self._last_entropy: float | None = None
        self._latest_flags: dict = {}

    # -- recording -------------------------------------------------------------
    def emit(self, event: str, payload: dict) -> dict:
        record = {"seq": len(self.events), "mission": self.mission_id, "event": event, **rounded(payload)}
        self.events.append(record)
        if self._emit is not None:
            self._emit(record)
        return record

    # -- structures and stats --------------------------------------------------
    def working_structures(self) -> list[tuple[str, ...]]:
        extras = [t for t in OPTIONAL if t in self.guard.grammar_terms()] + list(self.candidate_terms)
        out = []
        for r in range(len(extras) + 1):
            for combo in itertools.combinations(extras, r):
                if sum(t in self.candidate_terms for t in combo) > 2:
                    continue
                out.append(tuple(t for t in LIBRARY if t in set(CORE) | set(combo)))
        return out

    def experiment_stats(self) -> list[ExperimentStats]:
        out = []
        for (phi, y), w, obs in zip(self.rows, self.weights, self.observations):
            if obs.status != "ok":
                out.append(
                    ExperimentStats(np.zeros((len(LIBRARY), len(LIBRARY))), np.zeros(len(LIBRARY)), 0.0, 0.0)
                )
            else:
                out.append(ExperimentStats.from_rows(phi, y, w if self.robust else None))
        return out

    def _posterior_under(self, stats: list[ExperimentStats], prior: PriorSpec) -> tuple[Posterior, Analysis]:
        budget = self.guard.experiment_budget()
        analysis = Analysis(stats, prior, budget=budget, change_prior=self.change_prior)
        fits = analysis.evaluate([Hypothesis(s) for s in self.working_structures()])
        if self.config.change_monitor and len(stats) >= 2:
            ranked = sorted(fits, key=lambda f: -f.log_post)[:2]
            onsets = tuple(OPTIONAL) + tuple(self.candidate_terms)
            for f in ranked:
                fits += analysis.evaluate(change_hypotheses(f.hypothesis.structure, len(stats), onsets))
        self.counters["hypotheses_evaluated"] += len(fits)
        return Posterior.from_fits(fits), analysis

    def analyze(self) -> tuple[Posterior, Analysis]:
        stats = self.experiment_stats()
        self.counters["analyses"] += 1
        default, analysis = self._posterior_under(stats, self.default_prior)
        self._default_posterior = default
        if self.memory is not None and stats:
            self._fresh_memory_fit = analysis.evaluate([Hypothesis(tuple(self.memory.structure))])[0]
        if self.memory_prior is None or self.memory_state == "quarantined" or not stats:
            return default, analysis
        remembered, _ = self._posterior_under(stats, self.memory_prior)
        if self.config.memory == "legacy":
            bf = remembered.log_marginal() - default.log_marginal()
            return (remembered if bf >= LEGACY_MEMORY_NATS else default), analysis
        post = mixture(
            {
                "memory-valid": (self.p_memory_valid, remembered),
                "memory-stale": (1.0 - self.p_memory_valid, default),
            }
        )
        return post, analysis

    # -- residual helpers ------------------------------------------------------
    def _residuals(self, fit: Fit, index: int) -> np.ndarray:
        phi, y = self.rows[index]
        post = fit.hypothesis.change_at is not None and index >= fit.hypothesis.change_at
        theta = (
            fit.current_coefficients()
            if post or not fit.hypothesis.has_change
            else fit.pre_change_coefficients()
        )
        return y - phi @ theta

    def _refresh_weights(self, fit: Fit) -> None:
        scale = math.sqrt(fit.noise_var())
        self.weights = []
        for i, obs in enumerate(self.observations):
            if obs.status != "ok":
                self.weights.append(None)
                continue
            r = self._residuals(fit, i)
            self.weights.append(critic.huber_weights(r, critic.robust_scale(r) or scale))

    # -- the critic ------------------------------------------------------------
    def update(self) -> tuple[Posterior, Analysis, dict]:
        posterior, analysis = self.analyze()
        report: dict = {"enabled": self.config.critic}
        revisions = []
        if self.config.critic and self.observations:
            for _ in range(3):  # at most a few admissions/revisions per step
                top = posterior.top
                current = set(top.hypothesis.current_structure())
                allowed = [t for t in self.guard.grammar_terms() if t in EXPANSION]
                cands = [t for t in allowed if t not in self.candidate_terms and t not in current]
                lm = critic.lm_tests(analysis, top, cands) if cands else []
                last = len(self.observations) - 1
                while last >= 0 and self.observations[last].status != "ok":
                    last -= 1
                white = (
                    critic.ljung_box(self._residuals(top, last)) if last >= 0 else {"flag": False, "p": 1.0}
                )
                scale = math.sqrt(top.noise_var())
                parts = [
                    self._residuals(top, i) / scale
                    for i, o in enumerate(self.observations)
                    if o.status == "ok"
                ]
                noise = critic.noise_assumption(np.concatenate(parts)) if parts else {"flag": False, "p": 1.0}
                report = {"enabled": True, "lm_tests": lm[:6], "whiteness": white, "noise_assumption": noise}
                changed = False
                if noise["flag"] and not self.robust:
                    self.robust = True
                    self._refresh_weights(top)
                    revisions.append(
                        self.emit(
                            "revision",
                            {
                                "kind": "assumption",
                                "summary": "Gaussian-noise assumption rejected (kurtosis test); analysis switched to "
                                "Huber-weighted statistics",
                                "evidence": noise,
                            },
                        )
                    )
                    changed = True
                proposals = [r for r in lm if r["proposed"]]
                advisor_terms = self._advisor_terms(report, top) if (white["flag"] or proposals) else []
                if len(self.candidate_terms) < self.max_expansions:
                    pick = None
                    origin = "critic score test"
                    if proposals:
                        pick = proposals[0]["term"]
                        rivals = [r["term"] for r in proposals[1:]]
                        for rival in rivals[: self.max_expansions - len(self.candidate_terms) - 1]:
                            self.candidate_terms.append(rival)
                            revisions.append(
                                self.emit(
                                    "revision",
                                    {
                                        "kind": "hypothesis-expansion",
                                        "summary": f"admitted unanticipated term {rival} alongside {pick} so evidence can "
                                        "separate them",
                                        "origin": "critic score test (also significant)",
                                        "evidence": r_of(lm, rival),
                                        "working_structures": 0,
                                    },
                                )
                            )
                    elif advisor_terms:
                        pick, origin = advisor_terms[0], "model advisor (validated against the grammar)"
                    if pick is not None:
                        self.candidate_terms.append(pick)
                        revisions.append(
                            self.emit(
                                "revision",
                                {
                                    "kind": "hypothesis-expansion",
                                    "summary": f"admitted unanticipated term {pick} into the working hypotheses",
                                    "origin": origin,
                                    "evidence": next((r for r in lm if r["term"] == pick), {}),
                                    "working_structures": len(self.working_structures()),
                                },
                            )
                        )
                        changed = True
                if not changed:
                    break
                if self.robust:
                    self._refresh_weights(posterior.top)
                posterior, analysis = self.analyze()
            self._latest_flags = report
        else:
            self._latest_flags = {}
        self._memory_check(posterior)
        return posterior, analysis, {"report": report, "revisions": [r["seq"] for r in revisions]}

    def _advisor_terms(self, report: dict, top: Fit) -> list[str]:
        if self.advisor is None:
            return []
        try:
            self.guard.check_model_call()
        except ScopeViolation as exc:
            self.emit("escalation", exc.request.to_dict())
            return []
        proposals = self.advisor.propose_terms(
            {
                "leading": top.hypothesis.label(),
                "diagnostics": rounded(report),
                "grammar": list(self.guard.grammar_terms()),
            }
        )
        accepted = []
        for p in proposals.get("terms", []):
            try:
                self.guard.check_term(p)
            except ScopeViolation as exc:
                self.emit("escalation", exc.request.to_dict())
                continue
            if p in EXPANSION and p not in self.candidate_terms:
                accepted.append(p)
        self.emit(
            "advisor",
            {
                "call": "propose_terms",
                "generation": proposals.get("generation", "scripted"),
                "proposed": proposals.get("terms", []),
                "accepted": accepted,
                "rationale": proposals.get("rationale", ""),
            },
        )
        return accepted

    def memory_conflicts(self) -> list[dict]:
        """Per-coefficient prior-data conflict of the memory against fresh evidence alone."""

        if self.memory is None or not self.observations:
            return []
        fresh = self._fresh_memory_fit
        theta, sd = fresh.current_coefficients(), fresh.current_sd()
        out = []
        for term in self.memory.structure:
            remembered = self.memory.mean.get(term, 0.0)
            mem_sd = self.memory.sd.get(term, 0.0)
            est = float(theta[INDEX[term]])
            scale = math.sqrt(float(sd[INDEX[term]]) ** 2 + mem_sd**2) or 1e-9
            z = (est - remembered) / scale
            out.append(
                {
                    "term": term,
                    "remembered": remembered,
                    "fresh": est,
                    "z": z,
                    "conflict": abs(z) > MEMORY_CONFLICT_Z,
                }
            )
        return out

    def _memory_check(self, posterior: Posterior) -> None:
        if self.memory_state not in ("active", "confirmed") or not self.observations:
            return
        stale = posterior.regime_weights.get("memory-stale", 0.0) if posterior.regime_weights else 0.0
        conflicts = self.memory_conflicts()
        conflicting = [c for c in conflicts if c["conflict"]]
        dp = self.stop_rule["decision_probability"]
        if stale >= dp or conflicting:
            self.memory_state = "quarantined"
            what = (
                ", ".join(
                    f"{c['term']} (remembered {c['remembered']:+.3g}, fresh {c['fresh']:+.3g})"
                    for c in conflicting
                )
                or f"overall P(stale) = {stale:.3f}"
            )
            details = {
                "kind": "memory-quarantine",
                "summary": f"fresh evidence contradicts the remembered characterization of {self.memory.apparatus}: "
                f"{what}; it no longer informs this mission",
                "p_stale": stale,
                "conflicts": conflicts,
                "memory": self.memory.to_dict(),
            }
            self.emit("revision", details)
            if self.on_memory:
                self.on_memory("quarantine", details)
        elif (
            self.memory_state == "active"
            and 1 - stale >= dp
            and len(self.observations) >= 3
            and all(abs(c["z"]) < 2.0 for c in conflicts)
        ):
            self.memory_state = "confirmed"
            self.emit(
                "revision",
                {
                    "kind": "memory-confirmed",
                    "summary": "fresh evidence agrees with every remembered coefficient",
                    "p_valid": 1 - stale,
                    "conflicts": conflicts,
                },
            )

    # -- decision --------------------------------------------------------------
    def decide(self, posterior: Posterior) -> Decision:
        dp = self.stop_rule["decision_probability"]
        ap = self.stop_rule["attribution_probability"]
        n = len(self.observations)
        if self.config.decision_rule == "bayes-factor":
            nochange = [f for f in posterior.fits if not f.hypothesis.has_change]
            best = nochange[0]
            second = next((f for f in nochange[1:] if f.hypothesis != best.hypothesis), None)
            gap = best.log_post - second.log_post if second else float("inf")
            ready = n >= self.stop_rule["min_experiments"] and gap >= LEGACY_DECISION_NATS
            return Decision(
                ready,
                best.hypothesis.current_structure(),
                best.probability,
                0.0,
                None,
                0.0,
                (),
                0.0,
                best,
                [] if ready else [f"log Bayes factor {gap:.2f} < {LEGACY_DECISION_NATS}"],
            )
        structures = posterior.structure_marginal()
        structure, p_s = next(iter(structures.items()))
        p_change = posterior.p_change()
        changed_now = p_change >= dp
        location = posterior.change_location()
        attribution = posterior.attribution()
        change_at, p_loc = next(iter(location.items())) if location else (None, 0.0)
        changed, p_att = next(iter(attribution.items())) if attribution else ((), 0.0)
        target = next(
            (
                f
                for f in posterior.fits
                if f.hypothesis.current_structure() == structure and f.hypothesis.has_change == changed_now
            ),
            posterior.top,
        )
        blockers = []
        if n < self.stop_rule["min_experiments"]:
            blockers.append(f"fewer than {self.stop_rule['min_experiments']} experiments")
        if p_s < dp:
            blockers.append(f"leading structure probability {p_s:.3f} < {dp}")
        if self.config.change_monitor and dp > p_change > CHANGE_AMBIGUOUS:
            blockers.append(f"possible change under investigation (P(change) = {p_change:.3f})")
        if changed_now and p_att < ap:
            blockers.append(f"attribution of the change unresolved ({p_att:.3f} < {ap})")
        if self._latest_flags.get("whiteness", {}).get("flag"):
            blockers.append("newest residuals are not white (unexplained dynamics)")
        return Decision(
            not blockers,
            structure,
            p_s,
            p_change,
            change_at if changed_now else None,
            p_loc,
            changed if changed_now else (),
            p_att,
            target,
            blockers,
        )

    # -- execution -------------------------------------------------------------
    def encompassing_fits(self, posterior: Posterior, analysis: Analysis) -> list[tuple[float, Fit, Fit]]:
        """Each contender's change structure on the largest working structure, with its weight."""

        terms = set()
        for s in self.working_structures():
            terms |= set(s)
        structure = tuple(t for t in LIBRARY if t in terms)
        out = []
        seen = set()
        for fit in contenders(posterior, self.config.eig_contenders):
            top = fit.hypothesis
            if top.has_change:
                onsets = set(top.onsets)
                h = Hypothesis(tuple(t for t in structure if t not in onsets), top.change_at, top.changed)
            else:
                h = Hypothesis(structure)
            if h in seen:
                continue
            seen.add(h)
            out.append((fit.probability, analysis.evaluate([h])[0], fit))
        return out

    def planning_state(self, posterior: Posterior, analysis: Analysis) -> PlanningState:
        return PlanningState(
            encompassing=self.encompassing_fits(posterior, analysis)
            if isinstance(self.policy, ClosedLoop)
            else None,
            analysis=analysis,
            posterior=posterior,
            space=self.space,
            history=[o.design for o in self.observations],
            step=len(self.observations),
            seed=int(np.random.SeedSequence([self.seed, 31, len(self.observations)]).generate_state(1)[0]),
            candidate_terms=tuple(self.candidate_terms),
            eig_draws=self.config.eig_draws,
            eig_contenders=self.config.eig_contenders,
        )

    def execute(self, choice: Choice, posterior: Posterior, prediction: dict | None) -> Observation:
        self.guard.check_design(choice.design)
        self.guard.check_experiment(len(self.observations))
        index = len(self.observations)
        top = posterior.top
        if prediction is None and self.observations:
            prediction = predicted_amplitude(top, choice.design, seed=self.seed + 101 * index, draws=32)
        self.emit(
            "plan",
            {
                "index": index,
                "choice": choice.to_dict(),
                "prediction": prediction,
                "predicted_under": top.hypothesis.label(),
            },
        )
        obs = self.instrument.run(choice.design, index)
        if obs.index != index or obs.design != choice.design:
            raise RuntimeError("instrument returned an observation for a different experiment")
        phi, y = obs.regression()
        self.observations.append(obs)
        self.rows.append((phi, y))
        self.weights.append(None)
        self.purposes.append(choice.purpose)
        payload: dict = {
            "index": index,
            "design": obs.design.to_dict(),
            "status": obs.status,
            "observation_digest": obs.digest(),
            "purpose": choice.purpose,
        }
        if obs.status == "ok":
            payload["amplitude"] = obs.amplitude()
            if index > 0:
                payload["surprise"] = critic.surprise(top, phi, y, robust=self.robust)
            if prediction:
                lo, hi = prediction["interval_90"]
                payload["within_predicted_90"] = bool(lo <= obs.amplitude() <= hi)
        self.emit("observation", payload)
        if self.robust:
            self._refresh_weights(top)
        return obs

    def _consistency(self, target: Fit, index: int) -> dict | None:
        """Chow test: are the newest experiment's coefficients those of the earlier data?"""

        start = target.hypothesis.change_at or 0
        earlier = [i for i in range(start, index) if self.observations[i].status == "ok"]
        if not earlier or self.observations[index].status != "ok":
            return None

        def rows(i: int) -> tuple[np.ndarray, np.ndarray]:
            phi, y = self.rows[i]
            if self.robust and self.weights[i] is not None:
                w = np.sqrt(self.weights[i])
                return phi * w[:, None], y * w
            return phi, y

        structure = target.hypothesis.current_structure()
        pre = critic.RowSet.stack([rows(i) for i in earlier])
        new = critic.RowSet.stack([rows(index)])
        return critic.chow_test(pre, new, structure, structure)

    def challenge(self, posterior: Posterior, analysis: Analysis, dec: Decision) -> None:
        target = dec.target
        nb_hyps = neighbours(target.hypothesis, self.working_structures())
        nb_fits = [f for f in analysis.evaluate(nb_hyps)] if nb_hyps else []
        state = self.planning_state(posterior, analysis)
        key = (target.hypothesis.current_structure(), target.hypothesis.has_change)
        sentinel = key == self.streak_target and self.streak % 2 == 1 and self.observations
        if sentinel:
            choice = Choice(
                self.observations[0].design,
                self.policy.name,
                "challenge",
                None,
                "sentinel: re-measures the first experiment's condition to test that the system "
                "has not changed during the mission",
            )
        else:
            choice = self.policy.challenge(state, target, nb_fits)
        index = len(self.observations)
        prediction = predicted_amplitude(target, choice.design, seed=self.seed + 7 * index + 3, draws=128)
        self.emit(
            "challenge-registered",
            {
                "index": index,
                "target": target.hypothesis.label(),
                "design": choice.design.to_dict(),
                "reason": choice.reason,
                "prediction": prediction,
                "kind": "sentinel" if sentinel else "novel-condition",
                "criteria": {
                    "corroborated": "one-step surprise z <= 3, amplitude inside the 99% predictive interval and "
                    "coefficients consistent with earlier data (Chow p >= 0.01)",
                    "contradicted": "z > 5, amplitude outside the range of 128 predictive draws widened by 10%, "
                    "or coefficients differ from earlier data (Chow p < 0.001)",
                },
            },
        )
        obs = self.execute(choice, posterior, prediction)
        outcome, z, amp = "inconclusive", None, None
        if obs.status == "ok":
            phi, y = self.rows[-1]
            s = critic.surprise(target, phi, y, robust=self.robust)
            z, amp = s["z"], obs.amplitude()
            lo99, hi99 = prediction["interval_99"]
            lo, hi = prediction["range"]
            far = amp < lo * 0.9 or amp > hi * 1.1
            chow = self._consistency(target, index)
            chow_p = 1.0 if chow is None else chow["p"]
            if s["z"] > 5.0 or far or chow_p < 1e-3:
                outcome = "contradicted"
            elif s["z"] <= 3.0 and lo99 <= amp <= hi99 and chow_p >= 0.01:
                outcome = "corroborated"
        if key != self.streak_target:
            self.streak, self.streak_target = 0, key
        self.streak = self.streak + 1 if outcome == "corroborated" else 0
        entry = {
            "index": index,
            "target": target.hypothesis.label(),
            "outcome": outcome,
            "z": z,
            "kind": "sentinel" if sentinel else "novel-condition",
            "chow": chow if obs.status == "ok" else None,
            "amplitude": amp,
            "prediction": prediction,
            "key": [list(key[0]), key[1]],
        }
        self.challenge_log.append(entry)
        self.emit("challenge", entry)
        if outcome == "contradicted":
            self.emit(
                "revision",
                {
                    "kind": "hypothesis-rejected",
                    "summary": f"challenge at experiment {index + 1} contradicted {target.hypothesis.label()}; "
                    "returning to exploration with the new data",
                    "z": z,
                    "amplitude": amp,
                },
            )

    # -- the loop --------------------------------------------------------------
    def run(self) -> MissionResult:
        started = self.clock()
        self.emit(
            "mission-start",
            {
                "arm": self.arm,
                "config": self.config.to_dict(),
                "design_space": {k: list(v) for k, v in self.space.items()},
                "budget": int(
                    self.charter["budgets"]["experiments_per_mission"]
                ),  # base; extensions are authorizations
                "grammar": list(self.guard.grammar_terms()),
                "prior": self.default_prior.to_dict(),
                "memory": self.memory.to_dict() if self.memory else None,
                "policy_observation_dependent": self.policy.observation_dependent,
            },
        )
        k_c = int(self.stop_rule["challenge_experiments"]) if self.config.challenge else 0
        while True:
            posterior, analysis, critique = self.update()
            dec = self.decide(posterior)
            self._emit_analysis(posterior, dec, critique)
            used = len(self.observations)
            budget = self.guard.experiment_budget()
            if dec.ready:
                if k_c == 0:
                    return self.finish("decision", posterior, analysis, dec, started)
                key = (dec.target.hypothesis.current_structure(), dec.target.hypothesis.has_change)
                if key == self.streak_target and self.streak >= k_c:
                    check = self.independent_check(analysis, dec.target.hypothesis)
                    self._cv = (len(self.observations), key, check)
                    outcome = check.get("outcome") if check else None
                    if outcome in ("corroborated", None):
                        return self.finish("decision-challenged", posterior, analysis, dec, started)
                    if used >= budget:
                        return self.finish("budget-exhausted", posterior, analysis, dec, started)
                    if outcome == "contradicted":
                        self.streak = 0
                        self.emit(
                            "revision",
                            {
                                "kind": "hypothesis-rejected",
                                "summary": f"the independent cross-validated check contradicts "
                                f"{dec.target.hypothesis.label()}; returning to exploration",
                                "check": check,
                            },
                        )
                    else:
                        self.emit(
                            "note",
                            {
                                "summary": "independent check inconclusive; collecting more data before "
                                "concluding",
                                "check": check,
                            },
                        )
                    try:
                        self.execute(
                            self.policy.explore(self.planning_state(posterior, analysis)), posterior, None
                        )
                    except ScopeViolation as exc:
                        return self.finish(
                            "escalation-pending", posterior, analysis, dec, started, exc.request
                        )
                    continue
                if used >= budget:
                    return self.finish("budget-exhausted", posterior, analysis, dec, started)
                try:
                    self.challenge(posterior, analysis, dec)
                except ScopeViolation as exc:
                    return self.finish("escalation-pending", posterior, analysis, dec, started, exc.request)
                continue
            if used >= budget - k_c:
                return self.finish("budget-exhausted", posterior, analysis, dec, started)
            choice = self.policy.explore(self.planning_state(posterior, analysis))
            if choice.utility is not None and self.policy.observation_dependent:
                self.counters["planning_simulations"] += 1
            self.last_utility = choice.utility
            if (
                isinstance(self.policy, ClosedLoop)
                and choice.utility is not None
                and used >= self.stop_rule["futility_min_experiments"]
            ):
                about_hypotheses = getattr(choice, "hypothesis_information", choice.utility)
                self.futile = self.futile + 1 if about_hypotheses < self.stop_rule["futility_nats"] else 0
                if self.futile >= self.stop_rule["futility_patience"]:
                    return self.finish("futility", posterior, analysis, dec, started)
            try:
                self.execute(choice, posterior, None)
            except ScopeViolation as exc:
                return self.finish("escalation-pending", posterior, analysis, dec, started, exc.request)

    def _emit_analysis(self, posterior: Posterior, dec: Decision, critique: dict) -> None:
        grouped: dict = {}
        for f in posterior.fits:
            key = (f.hypothesis.current_structure(), f.hypothesis.has_change)
            grouped[key] = grouped.get(key, 0.0) + f.probability
        p = np.array([v for v in grouped.values() if v > 0])
        entropy = float(-(p * np.log(p)).sum())
        realized = None if self._last_entropy is None else self._last_entropy - entropy
        self._last_entropy = entropy
        self.emit(
            "analysis",
            {
                "after_experiments": len(self.observations),
                "posterior": posterior.summary(top=5),
                "decision": dec.to_dict(),
                "critic": critique["report"],
                "entropy_nats": entropy,
                "information_realized_nats": realized,
                "memory_state": self.memory_state,
                "candidate_terms": list(self.candidate_terms),
                "robust": self.robust,
            },
        )

    # -- conclusions -----------------------------------------------------------
    def _rows_for(self, indices: Sequence[int]) -> critic.RowSet | None:
        parts = [self.rows[i] for i in indices if self.observations[i].status == "ok"]
        return critic.RowSet.stack(parts) if parts else None

    def independent_check(self, analysis: Analysis, hypothesis: Hypothesis) -> dict | None:
        """Cross-validated prediction of the target against its structural neighbours."""

        variants = structure_variants(hypothesis, self.guard.grammar_terms())
        hyps = [hypothesis] + [h for h, _ in variants]
        kinds = ["target"] + [k for _, k in variants]
        ok = [i for i, o in enumerate(self.observations) if o.status == "ok"]
        if len(ok) < 2:
            return None
        designs = []
        for h in hyps:
            post_map, pre_map, _, _ = analysis._columns(h)
            per = []
            for e in ok:
                post = h.change_at is None or e >= h.change_at
                per.append(self.rows[e][0] @ (post_map if post else pre_map).T)
            designs.append(per)
        detail = critic.cross_validated_check(
            designs, [self.rows[e][1] for e in ok], kinds, robust=self.robust
        )
        detail["neighbours"] = [h.label() for h in hyps[1:]]
        return detail

    def reanalysis_digest(self) -> str:
        """Fresh analysis of the recorded observations (exact reproduction check)."""

        clone = ResearchEngine(
            self.charter,
            self.instrument,
            mission_id=self.mission_id,
            seed=self.seed,
            arm=self.arm,
            config=self.config,
            memory=self.memory,
            guard=self.guard,
        )
        clone.observations = [Observation.from_dict(o.to_dict()) for o in self.observations]
        clone.rows = [o.regression() for o in clone.observations]
        clone.candidate_terms = list(self.candidate_terms)
        clone.robust = self.robust
        clone.weights = list(self.weights)
        clone.memory_state = self.memory_state
        post, _ = clone.analyze()
        return sha256_json(rounded(post.summary(top=8)))

    def finish(
        self,
        reason: str,
        posterior: Posterior,
        analysis: Analysis,
        dec: Decision,
        started: float,
        request: EscalationRequest | None = None,
    ) -> MissionResult:
        target = dec.target
        structure = target.hypothesis.current_structure()
        relevant = [
            c
            for c in self.challenge_log
            if (tuple(c["key"][0]), c["key"][1]) == (structure, target.hypothesis.has_change)
        ]
        tail = relevant[-max(self.streak, 1) :] if relevant else []
        if not self.config.challenge:
            falsification = None
        elif self.streak >= int(self.stop_rule["challenge_experiments"]) and tail:
            falsification = "corroborated"
        elif relevant and relevant[-1]["outcome"] == "contradicted":
            falsification = "contradicted"
        elif relevant:
            falsification = "inconclusive"
        else:
            falsification = None
        cached = getattr(self, "_cv", None)
        if (
            cached
            and cached[0] == len(self.observations)
            and cached[1] == (structure, target.hypothesis.has_change)
        ):
            independent_detail = cached[2]
        else:
            independent_detail = self.independent_check(analysis, target.hypothesis)
        independent = independent_detail.get("outcome") if independent_detail else None
        final_digest = sha256_json(rounded(posterior.summary(top=8)))
        reproduced = self.reanalysis_digest() == final_digest
        decided = reason in ("decision", "decision-challenged")
        verdict, reasons = computed_verdict(independent, falsification, reproduced)
        if not decided:
            verdict, reasons = "unresolved", [f"stopped without a decision ({reason})"] + dec.blockers
        if self.config.challenge:
            asserted = decided and verdict == "supported"
        else:
            asserted = decided
        coeffs = target.current_coefficients()
        sds = target.current_sd()
        change_claim = None
        if self.config.change_monitor and dec.p_change >= self.stop_rule["decision_probability"]:
            chow = None
            k = dec.change_at
            if k is not None and dec.changed:
                pre = self._rows_for(range(0, k))
                post = self._rows_for(range(k, len(self.observations)))
                shifts = [t for t in dec.changed if t in target.hypothesis.structure] or list(dec.changed)
                if pre is not None and post is not None:
                    chow = critic.chow_test(pre, post, target.hypothesis.current_structure(), shifts)
            chow_outcome = (
                None
                if chow is None
                else (
                    "corroborated"
                    if chow["p"] < 1e-3
                    else "contradicted"
                    if chow["p"] > 0.1
                    else "inconclusive"
                )
            )
            cv, creasons = computed_verdict(chow_outcome, falsification, reproduced)
            if not decided:
                cv, creasons = "unresolved", [f"stopped without a decision ({reason})"]
            change_claim = {
                "statement": f"the dynamics changed before experiment {k + 1 if k is not None else '?'}"
                + (f" ({', '.join(dec.changed)})" if dec.changed else ""),
                "change_at": k,
                "p_change": dec.p_change,
                "p_location": dec.p_location,
                "changed": list(dec.changed),
                "p_attribution": dec.p_attribution,
                "attribution_resolved": dec.p_attribution >= self.stop_rule["attribution_probability"],
                "independent": chow,
                "verdict": cv,
                "reasons": creasons,
            }
        conclusion = {
            "decided": decided,
            "asserted": bool(asserted),
            "structure": list(structure),
            "p_structure": dec.p_structure,
            "change": {"change_at": dec.change_at, "changed": list(dec.changed)}
            if dec.change_at is not None
            else None,
            "p_change": dec.p_change,
            "coefficients": {
                t: {"mean": float(coeffs[INDEX[t]]), "sd": float(sds[INDEX[t]])} for t in structure
            },
            "noise_sd": math.sqrt(target.noise_var()),
            "verdict": verdict,
            "reasons": reasons,
            "falsification": falsification,
            "independent": independent,
            "independent_detail": independent_detail,
            "reproduced": reproduced,
            "change_claim": change_claim,
            "blockers": dec.blockers,
            "memory_state": self.memory_state,
            "challenges": len(self.challenge_log),
            "robust": self.robust,
            "candidate_terms": list(self.candidate_terms),
        }
        escalation = None
        if request is not None:
            escalation = rounded(request.to_dict())
            self.emit("escalation", escalation)
        elif reason == "budget-exhausted":
            request = EscalationRequest(
                "budget-extension",
                self.mission_id,
                "the experiment budget ended before the stopping rule was met"
                + (
                    f"; the best remaining design was still expected to yield {self.last_utility:.3f} nats"
                    if self.last_utility is not None
                    else ""
                ),
                {"experiments": int(self.charter["budgets"]["max_extension_per_request"])},
                {"blockers": dec.blockers},
            )
            escalation = rounded(request.to_dict())
            escalation["cap"] = int(self.charter["budgets"]["max_extension_per_request"])
            self.emit("escalation", escalation)
        self.emit("conclusion", conclusion)
        self.emit(
            "stop",
            {"reason": reason, "experiments": len(self.observations), "memory_state": self.memory_state},
        )
        digest = sha256_json([{k: v for k, v in e.items() if k != "mission"} for e in self.events])
        return MissionResult(
            mission_id=self.mission_id,
            arm=self.arm,
            stop_reason=reason,
            experiments=len(self.observations),
            designs=[o.design for o in self.observations],
            purposes=list(self.purposes),
            events=self.events,
            conclusion=rounded(conclusion),
            final_fit=target,
            final_posterior=posterior,
            digest=digest,
            wall_s=self.clock() - started,
            counters=dict(self.counters),
            escalation=escalation,
            memory_state=self.memory_state,
        )


def run_mission(charter: dict, instrument: InstrumentLike, **kwargs: Any) -> MissionResult:
    return ResearchEngine(charter, instrument, **kwargs).run()


__all__ = ["ARMS", "EngineConfig", "MissionResult", "ResearchEngine", "run_mission", "space_of"]
