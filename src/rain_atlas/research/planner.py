"""Experiment selection: the closed loop and the baselines it must beat.

The closed loop chooses the design with the largest *expected information
gain* about the hypotheses currently in contention::

    EIG(d) = sum_i w_i E_{y ~ p(y | d, h_i, data)} [ log p(y | h_i) - log sum_j w_j p(y | h_j) ]

estimated by simulating each contender's posterior predictive (posterior
draws of coefficients and noise, common random numbers across designs) and
scoring every simulated experiment with the exact incremental evidence of
every contender. Because the contenders and their parameter posteriors come
from the observations, the choice depends on what has been seen.

Candidates are a fixed quasi-random pool over the approved design space plus
observation-derived candidates: the estimated resonance (and twice it, for
parametric terms), and replications of earlier conditions (sentinels for
change). Every candidate is checked against the approved space by the
caller's scope guard.

Baselines share everything except selection:

* :class:`FixedSweep` -- a conventional stepped-sine schedule;
* :class:`RandomDesign` -- seeded uniform designs;
* :class:`OpenLoopOptimal` -- sequential D-optimal design computed from the
  prior alone (no observation can change it);
* :class:`Yoked` -- replays the closed loop's sequence from a *different*
  problem: the same distribution of designs with the dependence on this
  problem's observations removed;
* :class:`LegacyDisagreement` -- the existing ATLAS rule ported to this
  domain: maximum disagreement between the two leading fixed hypotheses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .inference import Analysis, Fit, Hypothesis, Posterior, batch_stats
from .oscillator import (
    CORE,
    DEFAULT_SPACE,
    DT,
    INDEX,
    OPTIONAL,
    STEPS,
    Design,
    coefficient_vector,
    design_pool,
    features,
    regression_data,
    response_amplitude,
    simulate,
)
from .oscillator import EXPANSION as EXPANSION_TERMS
from .oscillator import LIBRARY as LIBRARY_ORDER

CLIP = 25.0


@dataclass
class Choice:
    design: Design
    policy: str
    purpose: str
    utility: float | None = None
    reason: str = ""
    ranked: list[dict] = field(default_factory=list)
    contenders: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "design": self.design.to_dict(),
            "policy": self.policy,
            "purpose": self.purpose,
            "utility_nats": self.utility,
            "reason": self.reason,
            "ranked": self.ranked,
            "contenders": self.contenders,
        }


def _clip_design(d: Design, space: dict) -> Design:
    (a0, a1), (w0, w1), (x0, x1) = (space[k] for k in DEFAULT_SPACE)
    return Design(
        min(max(d.amplitude, a0), a1), min(max(d.frequency, w0), w1), min(max(d.x0, x0), x1)
    ).rounded()


def contenders(
    posterior: Posterior, limit: int, mass: float = 0.999, *, watch_change: bool = True
) -> list[Fit]:
    """Distinct leading hypotheses holding most of the posterior mass.

    With *watch_change*, the strongest change hypothesis always takes a seat
    (at its own, possibly small, posterior weight): the planner keeps asking
    whether the system may have changed.
    """

    out = _leading(posterior, limit, mass)
    if watch_change and not any(f.hypothesis.has_change for f in out):
        best = next((f for f in posterior.fits if f.hypothesis.has_change and f.probability > 1e-6), None)
        if best is not None and len(out) >= 1:
            out.append(best)
    return out


def _leading(posterior: Posterior, limit: int, mass: float) -> list[Fit]:
    out: list[Fit] = []
    seen: set = set()
    total = 0.0
    for f in posterior.fits:
        key = f.hypothesis
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
        total += f.probability
        if len(out) >= limit or total >= mass:
            break
    return out


def simulate_experiments(
    thetas: np.ndarray, sigmas: np.ndarray, designs: Sequence[Design], eps: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simulate len(designs) x len(thetas) experiments; returns stats and amplitudes."""

    D, M = len(designs), len(thetas)
    A = np.repeat([d.amplitude for d in designs], M)
    W = np.repeat([d.frequency for d in designs], M)
    X0 = np.repeat([d.x0 for d in designs], M)
    theta = np.tile(thetas, (D, 1))
    noise = np.tile(sigmas * math.sqrt(DT), D)  # regression-unit sd -> process scale
    e = np.tile(eps, (D, 1))
    x, v, u = simulate(theta, A, W, X0, noise, e, clip=CLIP)
    phi, y = regression_data(x, v, u)
    G, h, q, n = batch_stats(phi, y)
    return G, h, q, n, response_amplitude(x)


def expected_information(
    analysis: Analysis,
    fits: Sequence[Fit],
    weights: np.ndarray,
    designs: Sequence[Design],
    *,
    seed: int,
    draws: int = 2,
) -> np.ndarray:
    """Monte-Carlo EIG (nats) of each design about the contenders *fits*."""

    weights = np.asarray(weights, dtype=float)
    weights = weights / weights.sum()
    rng = np.random.default_rng(seed)
    thetas, sigmas, owners = [], [], []
    for i, fit in enumerate(fits):
        th, sg = fit.draw(rng, draws)
        thetas.append(th)
        sigmas.append(sg)
        owners += [i] * draws
    theta = np.vstack(thetas)
    sigma = np.concatenate(sigmas)
    owners_arr = np.array(owners)
    eps = rng.standard_normal((len(theta), STEPS))
    G, h, q, n, _ = simulate_experiments(theta, sigma, designs, eps)
    logp = analysis.new_data_log_marginal(fits, G, h, q, n)  # (D*S, J)
    logp = np.where(np.isfinite(logp), logp, -1e12)
    mixed = logp + np.log(np.maximum(weights, 1e-300))[None, :]
    m = mixed.max(axis=1, keepdims=True)
    log_mix = (m + np.log(np.exp(mixed - m).sum(axis=1, keepdims=True)))[:, 0]
    S = len(theta)
    own = logp[np.arange(len(logp)), np.tile(owners_arr, len(designs))]
    info = (own - log_mix).reshape(len(designs), S)
    per_owner = np.zeros((len(designs), len(fits)))
    for i in range(len(fits)):
        per_owner[:, i] = info[:, owners_arr == i].mean(axis=1)
    return np.maximum(per_owner @ weights, 0.0)


def predicted_amplitude(fit: Fit, design: Design, *, seed: int, draws: int = 64) -> dict:
    """Posterior-predictive interval of the response amplitude at *design*."""

    rng = np.random.default_rng(seed)
    theta, sigma = fit.draw(rng, draws)
    eps = rng.standard_normal((draws, STEPS))
    *_, amp = simulate_experiments(theta, sigma, [design], eps)
    q = np.quantile(amp, [0.005, 0.025, 0.05, 0.5, 0.95, 0.975, 0.995])
    return {
        "range": [float(np.min(amp)), float(np.max(amp))],
        "median": float(q[3]),
        "interval_90": [float(q[2]), float(q[4])],
        "interval_95": [float(q[1]), float(q[5])],
        "interval_99": [float(q[0]), float(q[6])],
        "draws": draws,
    }


class Policy:
    name = "abstract"
    observation_dependent = False

    def explore(self, state: "PlanningState") -> Choice:
        raise NotImplementedError

    def challenge(self, state: "PlanningState", target: Fit, neighbours: Sequence[Fit]) -> Choice:
        choice = self.explore(state)
        choice.purpose = "challenge"
        return choice


@dataclass
class PlanningState:
    analysis: Analysis
    posterior: Posterior
    space: dict
    history: list[Design]
    step: int
    seed: int
    candidate_terms: tuple[str, ...] = ()
    eig_draws: int = 2
    eig_contenders: int = 4
    encompassing: list[tuple[float, Fit, Fit]] | None = None  # (weight, encompassing fit, contender)


def parameter_information(fit: Fit, designs: Sequence[Design], nominal: np.ndarray) -> np.ndarray:
    """Expected information about *fit*'s coefficients from each design (nats).

    For a linear-Gaussian model the gain is 0.5 log det(I + V G), with V the
    posterior covariance factor and G the design's regressor Gram matrix,
    evaluated on a noise-free trajectory of the *nominal* model.
    """

    D = len(designs)
    x, v, u = simulate(
        np.tile(nominal, (D, 1)),
        np.array([d.amplitude for d in designs]),
        np.array([d.frequency for d in designs]),
        np.array([d.x0 for d in designs]),
        np.zeros(D),
        np.zeros((D, STEPS)),
        clip=CLIP,
    )
    phi = features(x[:, :-1], v[:, :-1], u)
    G = np.einsum("btl,btm->blm", phi, phi)
    M = fit.post_map
    Vn = np.linalg.inv(fit.Vninv)
    A = np.einsum("ij,kl,blm,nm->bin", Vn, M, G, M)  # V (M G M^T)
    k = len(Vn)
    _, logdet = np.linalg.slogdet(np.eye(k)[None] + A)
    return 0.5 * logdet


def _weights(fits: Sequence[Fit]) -> np.ndarray:
    return np.array([max(f.probability, 1e-12) for f in fits])


class ClosedLoop(Policy):
    """Expected-information-gain design over observation-derived contenders."""

    name = "closed-loop"
    observation_dependent = True

    def __init__(self, pool_size: int = 32):
        self.pool_size = pool_size

    def candidates(self, state: PlanningState) -> list[tuple[Design, str]]:
        out: list[tuple[Design, str]] = [(d, "pool") for d in design_pool(state.space, self.pool_size)]
        top = state.posterior.top
        theta = top.current_coefficients()
        stiffness = -theta[INDEX["x"]]
        a_max = state.space["amplitude"][1]
        x_max = state.space["x0"][1]
        if stiffness > 0:
            w0 = math.sqrt(stiffness)
            out.append((_clip_design(Design(a_max, w0, 0.0), state.space), "estimated resonance"))
            out.append(
                (_clip_design(Design(a_max, w0, x_max), state.space), "estimated resonance, displaced")
            )
            out.append(
                (_clip_design(Design(0.7 * a_max, w0, 0.0), state.space), "estimated resonance, moderate")
            )
            if "x*u" in state.candidate_terms:
                out.append((_clip_design(Design(a_max, 2 * w0, x_max), state.space), "parametric resonance"))
        for d in state.history[-2:]:
            out.append((d, "replication (change sentinel)"))
        if state.history:
            out.append((state.history[0], "replication of the first condition"))
        seen, unique = set(), []
        for d, why in out:
            if d not in seen:
                seen.add(d)
                unique.append((d, why))
        return unique

    def explore(self, state: PlanningState) -> Choice:
        """Maximize total expected information: about the hypotheses and their coefficients."""

        fits = contenders(state.posterior, state.eig_contenders)
        cands = self.candidates(state)
        designs = [d for d, _ in cands]
        labels = [{"label": f.hypothesis.label(), "probability": f.probability} for f in fits]
        if len(fits) >= 2:
            eig = expected_information(
                state.analysis, fits, _weights(fits), designs, seed=state.seed, draws=state.eig_draws
            )
        else:
            eig = np.zeros(len(designs))
        info = np.zeros(len(designs))
        if state.encompassing:
            # Expected parameter information, averaged over the contenders:
            # sum_h P(h) I(Y; theta_h | h), each on its encompassing structure.
            weights = np.array([max(w, 0.0) for w, _, _ in state.encompassing])
            weights = weights / weights.sum()
            for w, fit_h, nominal_from in zip(
                weights, (e[1] for e in state.encompassing), (e[2] for e in state.encompassing)
            ):
                nominal = (
                    nominal_from.current_coefficients() if state.history else coefficient_vector(NOMINAL)
                )
                info += w * parameter_information(fit_h, designs, nominal)
        total = eig + info
        order = np.argsort(-total, kind="stable")
        best = int(order[0])
        ranked = [
            {
                "design": cands[i][0].to_dict(),
                "origin": cands[i][1],
                "utility_nats": float(total[i]),
                "hypothesis_nats": float(eig[i]),
                "parameter_nats": float(info[i]),
            }
            for i in order[:5]
        ]
        reason = (
            f"maximizes expected information: {eig[best]:.3f} nats about {len(fits)} competing explanations "
            f"+ {info[best]:.3f} nats about their coefficients; candidate origin: {cands[best][1]}"
        )
        choice = Choice(cands[best][0], self.name, "explore", float(total[best]), reason, ranked, labels)
        choice.hypothesis_information = float(eig[best])  # type: ignore[attr-defined]
        return choice

    def challenge(self, state: PlanningState, target: Fit, neighbours: Sequence[Fit]) -> Choice:
        """The fresh condition where the neighbours would most visibly beat *target*."""

        visited = [d.normalized(state.space) for d in state.history]
        cands = [
            (d, why)
            for d, why in self.candidates(state)
            if not visited
            or min(float(np.linalg.norm(d.normalized(state.space) - v)) for v in visited) >= 0.2
        ]
        if not cands:
            cands = self.candidates(state)
        fits = [target] + [n for n in neighbours if n.hypothesis != target.hypothesis]
        if len(fits) < 2:
            return Choice(
                cands[0][0], self.name, "challenge", None, "no neighbouring explanation to separate"
            )
        weights = np.full(len(fits), 1.0 / len(fits))  # adversarial: rivals get equal weight
        eig = expected_information(
            state.analysis, fits, weights, [d for d, _ in cands], seed=state.seed + 17, draws=state.eig_draws
        )
        order = np.argsort(-eig, kind="stable")
        best = int(order[0])
        ranked = [
            {"design": cands[i][0].to_dict(), "origin": cands[i][1], "eig_nats": float(eig[i])}
            for i in order[:5]
        ]
        return Choice(
            cands[best][0],
            self.name,
            "challenge",
            float(eig[best]),
            "unvisited condition where the leading explanation and its neighbours disagree most "
            f"({eig[best]:.3f} nats with rivals weighted equally)",
            ranked,
            [{"label": f.hypothesis.label(), "probability": f.probability} for f in fits],
        )


def sweep_schedule(space: dict, count: int = 16) -> list[Design]:
    (a0, a1), (w0, w1), (x0, x1) = (space[k] for k in DEFAULT_SPACE)
    levels = np.linspace(w0, w1, 8)
    first = [Design(round(0.66 * a1, 4), round(float(w), 4), 0.0) for w in levels]
    second = [Design(a1, round(float(w), 4), round(0.5 * x1, 4)) for w in levels]
    schedule = first + second
    while len(schedule) < count:
        schedule += schedule
    return schedule[:count]


class FixedSweep(Policy):
    name = "fixed-sweep"

    def __init__(self, space: dict, count: int = 64):
        self.schedule = sweep_schedule(space, count)

    def explore(self, state: PlanningState) -> Choice:
        d = self.schedule[state.step % len(self.schedule)]
        return Choice(d, self.name, "explore", None, f"stepped-sine schedule position {state.step + 1}")


class RandomDesign(Policy):
    name = "random"

    def __init__(self, seed: int):
        self.seed = seed

    def explore(self, state: PlanningState) -> Choice:
        rng = np.random.default_rng([self.seed, 4241, state.step])
        (a0, a1), (w0, w1), (x0, x1) = (state.space[k] for k in DEFAULT_SPACE)
        d = Design(rng.uniform(a0, a1), rng.uniform(w0, w1), rng.uniform(x0, x1)).rounded()
        return Choice(d, self.name, "explore", None, "uniform random design (seeded)")


NOMINAL = {"x": -1.0, "v": -0.2, "u": 1.0}


class OpenLoopOptimal(Policy):
    """Greedy sequential D-optimal design from the prior's nominal model, fixed in advance."""

    name = "open-loop-optimal"

    def __init__(self, space: dict, nominal: dict[str, float] | None = None, count: int = 32, pool: int = 64):
        nominal = dict(nominal or NOMINAL)
        terms = list(CORE + OPTIONAL)
        cols = [INDEX[t] for t in terms]
        candidates = design_pool(space, pool, offset=3)
        theta = np.tile(coefficient_vector(nominal), (len(candidates), 1))
        x, v, u = simulate(
            theta,
            np.array([d.amplitude for d in candidates]),
            np.array([d.frequency for d in candidates]),
            np.array([d.x0 for d in candidates]),
            np.zeros(len(candidates)),
            np.zeros((len(candidates), STEPS)),
            clip=CLIP,
        )
        phi = features(x[:, :-1], v[:, :-1], u)[..., cols]
        grams = np.einsum("btl,btm->blm", phi, phi)
        info = np.eye(len(cols)) * 1.0
        self.schedule: list[Design] = []
        self.gains: list[float] = []
        for _ in range(count):
            _, base = np.linalg.slogdet(info)
            gains = np.array([np.linalg.slogdet(info + g)[1] - base for g in grams])
            best = int(np.argmax(gains))
            self.schedule.append(candidates[best])
            self.gains.append(float(gains[best]))
            info = info + grams[best]
        self.nominal = nominal

    def explore(self, state: PlanningState) -> Choice:
        i = state.step % len(self.schedule)
        return Choice(
            self.schedule[i],
            self.name,
            "explore",
            None,
            f"precomputed D-optimal position {i + 1} (log-det gain {self.gains[i]:.2f} under the prior nominal model)",
        )


class Yoked(Policy):
    """Replays another problem's closed-loop designs in order, then the fixed sweep."""

    name = "yoked"

    def __init__(self, donor: Sequence[Design], space: dict, donor_id: str = ""):
        self.donor = list(donor)
        self.donor_id = donor_id
        self.fallback = sweep_schedule(space, 64)

    def explore(self, state: PlanningState) -> Choice:
        if state.step < len(self.donor):
            return Choice(
                self.donor[state.step],
                self.name,
                "explore",
                None,
                f"replays design {state.step + 1} chosen for {self.donor_id}",
            )
        d = self.fallback[(state.step - len(self.donor)) % len(self.fallback)]
        return Choice(d, self.name, "explore", None, "donor sequence exhausted; stepped-sine fallback")


class LegacyDisagreement(Policy):
    """Existing ATLAS rule: the grid condition where the two leading models disagree most."""

    name = "legacy-atlas"
    observation_dependent = True

    def __init__(self, space: dict):
        self.grid = sweep_schedule(space, 16)

    def explore(self, state: PlanningState) -> Choice:
        fits = contenders(state.posterior, 2, watch_change=False)
        if len(fits) < 2:
            return Choice(
                self.grid[state.step % len(self.grid)], self.name, "explore", None, "single model left"
            )
        thetas = np.vstack([f.current_coefficients() for f in fits])
        zero_noise = np.zeros(len(thetas))
        *_, amp = simulate_experiments(thetas, zero_noise, self.grid, np.zeros((len(thetas), STEPS)))
        amp = amp.reshape(len(self.grid), 2)
        gap = np.abs(amp[:, 0] - amp[:, 1])
        best = int(np.argmax(gap))
        if gap[best] <= 1e-9:
            best = state.step % len(self.grid)
        return Choice(
            self.grid[best],
            self.name,
            "explore",
            float(gap[best]),
            "largest predicted response disagreement between the two leading models",
        )


def neighbours(target: Hypothesis, working: Sequence[tuple[str, ...]]) -> list[Hypothesis]:
    """Hypotheses one structural term away from *target* (same change point, if any)."""

    current = set(target.current_structure())
    out = []
    for s in working:
        diff = current.symmetric_difference(s)
        swap = len(diff) == 2 and len(s) == len(current) and not (diff & set(CORE))
        if not (len(diff) == 1 or swap) or not set(CORE) <= set(s):
            continue
        if not target.has_change:
            out.append(Hypothesis(tuple(s)))
            continue
        onsets = [t for t in target.onsets if t in s]
        pre = tuple(t for t in s if t not in onsets)
        changed = tuple(t for t in target.changed if t in s)
        if changed:
            out.append(Hypothesis(pre, target.change_at, changed))
    return out


def structure_variants(target: Hypothesis, grammar: Sequence[str]) -> list[tuple[Hypothesis, str]]:
    """One-term removals, additions and expansion-term swaps of *target* over the full grammar.

    Used by the independent cross-validated check: a reduced variant must
    predict worse; an extended or swapped variant must not predict better.
    """

    current = target.current_structure()
    variants: list[tuple[tuple[str, ...], str]] = []
    for t in current:
        if t not in CORE:
            variants.append((tuple(x for x in current if x != t), "reduced"))
    for t in grammar:
        if t not in current:
            variants.append((tuple(x for x in LIBRARY_ORDER if x in set(current) | {t}), "extended"))
    for t in current:
        if t in EXPANSION_TERMS:
            for other in grammar:
                if other in EXPANSION_TERMS and other not in current:
                    swapped = (set(current) - {t}) | {other}
                    variants.append((tuple(x for x in LIBRARY_ORDER if x in swapped), "swap"))
    out = []
    for s, kind in variants:
        if not target.has_change:
            out.append((Hypothesis(s), kind))
            continue
        onsets = [t for t in target.onsets if t in s]
        pre = tuple(t for t in s if t not in onsets)
        changed = tuple(t for t in target.changed if t in s)
        if changed:
            out.append((Hypothesis(pre, target.change_at, changed), kind))
    return out
