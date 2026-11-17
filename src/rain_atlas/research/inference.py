"""Exact Bayesian evidence for competing explanations of the observations.

Every hypothesis is a linear-Gaussian regression of the one-step acceleration
on a set of grammar terms, so its marginal likelihood (evidence) under a
Normal-Inverse-Gamma prior is available in closed form::

    theta | s2 ~ N(m0, s2 V0),   s2 ~ InvGamma(a0, b0)
    log Z = -n/2 log 2pi + 1/2 log(|V0^-1| / |Vn^-1|) + a0 log b0 - an log bn
            + lgamma(an) - lgamma(a0)

A hypothesis is ``(structure, change_at, changed)``. A change hypothesis adds
coefficients that apply only to experiments ``>= change_at``; a changed term
already in the structure is a *shift*, a changed term outside it is an
*onset*. All design matrices are assembled from per-experiment sufficient
statistics with prefix sums, so evaluating hundreds of hypotheses costs a few
milliseconds. Evaluation is batched by dimension.

These formulas are the scientific core: tests compare them with brute-force
numerical integration and with direct regression on stacked rows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
from scipy.special import gammaln

from .oscillator import EXPANSION, INDEX, LIBRARY, OPTIONAL, L, MemoryPrior

LOG_2PI = math.log(2.0 * math.pi)
OPTIONAL_PENALTY = math.log(3.0)
UNANTICIPATED_PENALTY = math.log(20.0)


@dataclass
class ExperimentStats:
    """Sufficient statistics of one experiment over the full term library."""

    G: np.ndarray  # (L, L)  sum phi phi^T
    h: np.ndarray  # (L,)    sum phi y
    q: float  # sum y^2
    n: float  # rows (effective rows when weighted)

    @classmethod
    def from_rows(
        cls, phi: np.ndarray, y: np.ndarray, weights: np.ndarray | None = None
    ) -> "ExperimentStats":
        if weights is None:
            return cls(phi.T @ phi, phi.T @ y, float(y @ y), float(len(y)))
        w = np.asarray(weights, dtype=float)
        pw = phi * w[:, None]
        return cls(pw.T @ phi, pw.T @ y, float((w * y) @ y), float(np.sum(w)))


def batch_stats(phi: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Sufficient statistics for a batch of simulated experiments (B, T, L), (B, T)."""

    G = np.einsum("btl,btm->blm", phi, phi)
    h = np.einsum("btl,bt->bl", phi, y)
    q = np.einsum("bt,bt->b", y, y)
    n = np.full(y.shape[0], float(y.shape[1]))
    return G, h, q, n


@dataclass(frozen=True)
class Hypothesis:
    structure: tuple[str, ...]
    change_at: int | None = None
    changed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        order = tuple(t for t in LIBRARY if t in self.structure)
        if order != self.structure:
            object.__setattr__(self, "structure", order)
        if self.change_at is None and self.changed:
            raise ValueError("changed terms require a change point")

    @property
    def has_change(self) -> bool:
        return self.change_at is not None

    @property
    def onsets(self) -> tuple[str, ...]:
        return tuple(t for t in self.changed if t not in self.structure)

    @property
    def shifts(self) -> tuple[str, ...]:
        return tuple(t for t in self.changed if t in self.structure)

    def current_structure(self) -> tuple[str, ...]:
        return tuple(t for t in LIBRARY if t in self.structure or t in self.onsets)

    def label(self) -> str:
        base = "{" + ", ".join(self.structure) + "}"
        if not self.has_change:
            return base
        parts = []
        if self.shifts:
            parts.append("shift " + ", ".join(self.shifts))
        if self.onsets:
            parts.append("onset " + ", ".join(self.onsets))
        return f"{base} with change at experiment {self.change_at + 1} ({'; '.join(parts)})"

    def to_dict(self) -> dict:
        return {"structure": list(self.structure), "change_at": self.change_at, "changed": list(self.changed)}

    @classmethod
    def from_dict(cls, data: dict) -> "Hypothesis":
        return cls(tuple(data["structure"]), data.get("change_at"), tuple(data.get("changed", ())))


def structural_log_prior(
    structure: Iterable[str], bonus: dict[tuple[str, ...], float] | None = None
) -> float:
    structure = tuple(t for t in LIBRARY if t in set(structure))
    value = -OPTIONAL_PENALTY * sum(t in OPTIONAL for t in structure)
    value -= UNANTICIPATED_PENALTY * sum(t in EXPANSION for t in structure)
    if bonus:
        value += bonus.get(structure, 0.0)
    return value


@dataclass(frozen=True)
class PriorSpec:
    """Coefficient, noise and structure priors (physical units)."""

    mean: tuple[float, ...]
    sd: tuple[float, ...]
    noise_sd: float  # assumed noise standard deviation of the regression target
    a0: float = 2.0
    change_sd: float = 1.0
    structure_bonus: tuple[tuple[tuple[str, ...], float], ...] = ()
    source: str = "default"

    @classmethod
    def default(
        cls, noise_sd: float = 2.5, coefficient_sd: float = 2.0, change_sd: float = 1.0
    ) -> "PriorSpec":
        return cls(mean=(0.0,) * L, sd=(coefficient_sd,) * L, noise_sd=noise_sd, change_sd=change_sd)

    @classmethod
    def from_memory(cls, memory: MemoryPrior, default: "PriorSpec", *, inflation: float = 2.0) -> "PriorSpec":
        """A tempered prior: remembered values, widened with age, and a structural bonus."""

        mean = list(default.mean)
        sd = list(default.sd)
        widen = inflation * (1.0 + 0.5 * max(memory.age - 1, 0))
        for term in memory.structure:
            mean[INDEX[term]] = memory.mean[term]
            sd[INDEX[term]] = min(default.sd[INDEX[term]], memory.sd[term] * widen)
        structure = tuple(t for t in LIBRARY if t in memory.structure)
        return cls(
            mean=tuple(mean),
            sd=tuple(sd),
            noise_sd=memory.noise_sd,
            a0=default.a0,
            change_sd=default.change_sd,
            structure_bonus=((structure, math.log(9.0)),),
            source="memory",
        )

    def bonus(self) -> dict[tuple[str, ...], float]:
        return dict(self.structure_bonus)

    def to_dict(self) -> dict:
        return {
            "mean": dict(zip(LIBRARY, self.mean)),
            "sd": dict(zip(LIBRARY, self.sd)),
            "noise_sd": self.noise_sd,
            "a0": self.a0,
            "change_sd": self.change_sd,
            "structure_bonus": [[list(s), b] for s, b in self.structure_bonus],
            "source": self.source,
        }


def log_evidence_batch(
    XtX: np.ndarray,
    Xty: np.ndarray,
    yty: np.ndarray,
    n: np.ndarray,
    m0: np.ndarray,
    V0inv: np.ndarray,
    a0: float,
    b0: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Batched NIG evidence. Returns log Z, mn, Vn^-1, an, bn."""

    Vninv = V0inv + XtX
    rhs = np.einsum("bij,bj->bi", V0inv, m0) + Xty
    mn = np.linalg.solve(Vninv, rhs[..., None])[..., 0]
    an = a0 + n / 2.0
    quad0 = np.einsum("bi,bij,bj->b", m0, V0inv, m0)
    quadn = np.einsum("bi,bij,bj->b", mn, Vninv, mn)
    bn = b0 + 0.5 * (yty + quad0 - quadn)
    bn = np.maximum(bn, 1e-12 * (1.0 + np.abs(yty)))
    _, ld0 = np.linalg.slogdet(V0inv)
    _, ldn = np.linalg.slogdet(Vninv)
    logz = (
        -0.5 * n * LOG_2PI
        + 0.5 * (ld0 - ldn)
        + a0 * math.log(b0)
        - an * np.log(bn)
        + gammaln(an)
        - gammaln(a0)
    )
    return logz, mn, Vninv, an, bn


@dataclass
class Fit:
    """A hypothesis evaluated on the current data."""

    hypothesis: Hypothesis
    log_evidence: float
    log_prior: float
    mn: np.ndarray
    Vninv: np.ndarray
    an: float
    bn: float
    post_map: np.ndarray  # (k, L): library features -> columns for post-change rows
    pre_map: np.ndarray  # (k, L): ... for pre-change rows
    XtX: np.ndarray
    Xty: np.ndarray
    yty: float
    n: float
    m0: np.ndarray
    V0inv: np.ndarray
    a0: float = 2.0
    b0: float = 1.0
    regime: str = "default"
    probability: float = 0.0

    @property
    def log_post(self) -> float:
        return self.log_evidence + self.log_prior

    def noise_var(self) -> float:
        return self.bn / self.an

    def covariance(self) -> np.ndarray:
        return np.linalg.inv(self.Vninv) * (self.bn / self.an)

    def current_coefficients(self) -> np.ndarray:
        return self.post_map.T @ self.mn

    def pre_change_coefficients(self) -> np.ndarray:
        return self.pre_map.T @ self.mn

    def current_sd(self) -> np.ndarray:
        cov = self.post_map.T @ self.covariance() @ self.post_map
        return np.sqrt(np.maximum(np.diag(cov), 0.0))

    def predictive(self, phi: np.ndarray, *, post: bool = True) -> tuple[np.ndarray, np.ndarray, float]:
        """Student-t predictive for new rows: mean, scale, degrees of freedom."""

        mapping = self.post_map if post else self.pre_map
        aug = phi @ mapping.T
        Vn = np.linalg.inv(self.Vninv)
        var = self.noise_var() * (1.0 + np.einsum("ti,ij,tj->t", aug, Vn, aug))
        return aug @ self.mn, np.sqrt(var), 2.0 * self.an

    def draw(self, rng: np.random.Generator, count: int) -> tuple[np.ndarray, np.ndarray]:
        """Posterior draws of current coefficients (count, L) and noise sd (count,)."""

        s2 = self.bn / rng.gamma(self.an, 1.0, size=count)
        Vn = np.linalg.inv(self.Vninv)
        chol = np.linalg.cholesky(Vn + 1e-12 * np.eye(len(Vn)))
        z = rng.standard_normal((count, len(self.mn)))
        beta = self.mn[None, :] + np.sqrt(s2)[:, None] * (z @ chol.T)
        return beta @ self.post_map, np.sqrt(s2)

    def summary(self) -> dict:
        coeffs = self.current_coefficients()
        sd = self.current_sd()
        return {
            "hypothesis": self.hypothesis.to_dict(),
            "label": self.hypothesis.label(),
            "probability": self.probability,
            "log_evidence": self.log_evidence,
            "log_prior": self.log_prior,
            "noise_sd": math.sqrt(self.noise_var()),
            "coefficients": {
                t: {"mean": float(coeffs[INDEX[t]]), "sd": float(sd[INDEX[t]])}
                for t in self.hypothesis.current_structure()
            },
        }


def change_options(structure: Sequence[str], onset_candidates: Iterable[str]) -> list[tuple[str, ...]]:
    """Attribution options: each single shift, a joint shift, and single onsets."""

    options: list[tuple[str, ...]] = [(t,) for t in structure]
    if len(structure) > 1:
        options.append(tuple(structure))
    options.extend((t,) for t in LIBRARY if t in set(onset_candidates) and t not in structure)
    return options


def change_hypotheses(
    structure: Sequence[str], n_experiments: int, onset_candidates: Iterable[str]
) -> list[Hypothesis]:
    structure = tuple(t for t in LIBRARY if t in structure)
    out = []
    for k in range(1, n_experiments):
        for changed in change_options(structure, onset_candidates):
            out.append(Hypothesis(structure, k, changed))
    return out


class Analysis:
    """Exact evaluation of hypotheses on a fixed list of experiment statistics."""

    def __init__(
        self, stats: Sequence[ExperimentStats], prior: PriorSpec, *, budget: int, change_prior: float
    ):
        """*change_prior* is the per-experiment hazard of an unannounced change."""

        self.stats = list(stats)
        self.prior = prior
        self.budget = int(budget)
        self.change_prior = float(change_prior)
        n = len(self.stats)
        self.prefix_G = np.zeros((n + 1, L, L))
        self.prefix_h = np.zeros((n + 1, L))
        self.prefix_q = np.zeros(n + 1)
        self.prefix_n = np.zeros(n + 1)
        for i, s in enumerate(self.stats):
            self.prefix_G[i + 1] = self.prefix_G[i] + s.G
            self.prefix_h[i + 1] = self.prefix_h[i] + s.h
            self.prefix_q[i + 1] = self.prefix_q[i] + s.q
            self.prefix_n[i + 1] = self.prefix_n[i] + s.n
        self.mean = np.asarray(prior.mean)
        self.sd = np.asarray(prior.sd)
        self.a0 = prior.a0
        self.b0 = prior.noise_sd**2 * (prior.a0 - 1.0)

    @property
    def count(self) -> int:
        return len(self.stats)

    def _columns(self, h: Hypothesis) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        s_idx = [INDEX[t] for t in h.structure]
        c_idx = [INDEX[t] for t in h.changed]
        k = len(s_idx) + len(c_idx)
        post_map = np.zeros((k, L))
        pre_map = np.zeros((k, L))
        for col, j in enumerate(s_idx):
            post_map[col, j] = 1.0
            pre_map[col, j] = 1.0
        for col, j in enumerate(c_idx, start=len(s_idx)):
            post_map[col, j] = 1.0
        m0 = np.concatenate(
            [self.mean[s_idx], [0.0 if t in h.structure else self.mean[INDEX[t]] for t in h.changed]]
        )
        sd = np.concatenate(
            [
                self.sd[s_idx],
                [self.prior.change_sd if t in h.structure else self.sd[INDEX[t]] for t in h.changed],
            ]
        )
        V0inv = np.diag(self.prior.noise_sd**2 / sd**2)
        return post_map, pre_map, m0, V0inv

    def _gram(self, h: Hypothesis, post_map: np.ndarray, pre_map: np.ndarray):
        n = self.count
        G_all, h_all = self.prefix_G[n], self.prefix_h[n]
        if h.change_at is None:
            XtX = post_map @ G_all @ post_map.T
            Xty = post_map @ h_all
        else:
            k = h.change_at
            G_pre, h_pre = self.prefix_G[k], self.prefix_h[k]
            G_post, h_post = G_all - G_pre, h_all - h_pre
            XtX = pre_map @ G_pre @ pre_map.T + post_map @ G_post @ post_map.T
            Xty = pre_map @ h_pre + post_map @ h_post
        return XtX, Xty, float(self.prefix_q[n]), float(self.prefix_n[n])

    def log_prior(self, h: Hypothesis) -> float:
        """Structure prior plus a per-experiment change hazard (at most one change).

        With hazard q, P(no change in the n-1 observed transitions) = (1-q)^(n-1)
        and P(change just before experiment k) = q (1-q)^(k-1); the change prior
        is then split evenly over the attribution options.
        """

        value = structural_log_prior(h.structure, self.prior.bonus())
        q = self.change_prior
        observed = max(self.count - 1, 0)
        if h.change_at is None:
            return value + (observed * math.log1p(-q) if q < 1 else -math.inf)
        if q <= 0:
            return -math.inf
        options = len(change_options(h.structure, ONSET_POOL))
        return value + math.log(q) + (h.change_at - 1) * math.log1p(-q) - math.log(options)

    def evaluate(self, hypotheses: Sequence[Hypothesis]) -> list[Fit]:
        built = []
        for h in hypotheses:
            post_map, pre_map, m0, V0inv = self._columns(h)
            XtX, Xty, yty, n = self._gram(h, post_map, pre_map)
            built.append((h, post_map, pre_map, m0, V0inv, XtX, Xty, yty, n))
        fits: list[Fit | None] = [None] * len(built)
        by_dim: dict[int, list[int]] = {}
        for i, b in enumerate(built):
            by_dim.setdefault(len(b[3]), []).append(i)
        for _, members in by_dim.items():
            XtX = np.stack([built[i][5] for i in members])
            Xty = np.stack([built[i][6] for i in members])
            yty = np.array([built[i][7] for i in members])
            n = np.array([built[i][8] for i in members])
            m0 = np.stack([built[i][3] for i in members])
            V0inv = np.stack([built[i][4] for i in members])
            logz, mn, Vninv, an, bn = log_evidence_batch(XtX, Xty, yty, n, m0, V0inv, self.a0, self.b0)
            for j, i in enumerate(members):
                h, post_map, pre_map, m0_i, V0inv_i, XtX_i, Xty_i, yty_i, n_i = built[i]
                fits[i] = Fit(
                    hypothesis=h,
                    log_evidence=float(logz[j]),
                    log_prior=self.log_prior(h),
                    mn=mn[j],
                    Vninv=Vninv[j],
                    an=float(an[j]),
                    bn=float(bn[j]),
                    post_map=post_map,
                    pre_map=pre_map,
                    XtX=XtX_i,
                    Xty=Xty_i,
                    yty=yty_i,
                    n=n_i,
                    m0=m0_i,
                    V0inv=V0inv_i,
                    a0=self.a0,
                    b0=self.b0,
                    regime=self.prior.source,
                )
        return [f for f in fits if f is not None]

    def new_data_log_marginal(
        self, fits: Sequence[Fit], G: np.ndarray, h: np.ndarray, q: np.ndarray, n: np.ndarray
    ) -> np.ndarray:
        """log p(new experiment | data, hypothesis) for B simulated experiments: (B, J).

        A new experiment comes after every change point already in the data,
        so it uses each hypothesis's post-change columns.
        """

        out = np.empty((G.shape[0], len(fits)))
        for j, fit in enumerate(fits):
            M = fit.post_map
            XtX = fit.XtX[None] + np.einsum("kl,blm,jm->bkj", M, G, M)
            Xty = fit.Xty[None] + np.einsum("kl,bl->bk", M, h)
            k = len(fit.mn)
            logz, *_ = log_evidence_batch(
                XtX,
                Xty,
                fit.yty + q,
                fit.n + n,
                np.broadcast_to(fit.m0, (len(q), k)),
                np.broadcast_to(fit.V0inv, (len(q), k, k)),
                fit.a0,
                fit.b0,
            )
            out[:, j] = logz - fit.log_evidence
        return out


# Onset terms the attribution prior counts. Kept fixed so the prior of a change
# hypothesis does not depend on which expansion terms the critic has added.
ONSET_POOL = OPTIONAL


@dataclass
class Posterior:
    """Normalized posterior over the evaluated hypotheses."""

    fits: list[Fit]
    regime_weights: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_fits(cls, fits: Sequence[Fit]) -> "Posterior":
        fits = list(fits)
        if not fits:
            return cls([])
        lp = np.array([f.log_post for f in fits])
        lp -= lp.max()
        p = np.exp(lp)
        p /= p.sum()
        for f, pi in zip(fits, p):
            f.probability = float(pi)
        fits.sort(key=lambda f: (-f.probability, f.hypothesis.label()))
        return cls(fits)

    @property
    def top(self) -> Fit:
        return self.fits[0]

    def log_marginal(self) -> float:
        lp = np.array([f.log_post for f in self.fits])
        m = lp.max()
        return float(m + np.log(np.exp(lp - m).sum()))

    def p_change(self) -> float:
        return float(sum(f.probability for f in self.fits if f.hypothesis.has_change))

    def structure_marginal(self) -> dict[tuple[str, ...], float]:
        out: dict[tuple[str, ...], float] = {}
        for f in self.fits:
            key = f.hypothesis.current_structure()
            out[key] = out.get(key, 0.0) + f.probability
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def change_location(self) -> dict[int, float]:
        out: dict[int, float] = {}
        for f in self.fits:
            if f.hypothesis.has_change:
                out[f.hypothesis.change_at] = out.get(f.hypothesis.change_at, 0.0) + f.probability
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def attribution(self) -> dict[tuple[str, ...], float]:
        total = self.p_change()
        out: dict[tuple[str, ...], float] = {}
        if total <= 0:
            return out
        for f in self.fits:
            if f.hypothesis.has_change:
                out[f.hypothesis.changed] = out.get(f.hypothesis.changed, 0.0) + f.probability / total
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def entropy(self) -> float:
        p = np.array([f.probability for f in self.fits])
        p = p[p > 0]
        return float(-(p * np.log(p)).sum())

    def summary(self, top: int = 6) -> dict:
        structures = self.structure_marginal()
        location = self.change_location()
        attribution = self.attribution()
        return {
            "top": [f.summary() for f in self.fits[:top]],
            "structures": [
                {"structure": list(s), "probability": p} for s, p in list(structures.items())[:top]
            ],
            "p_change": self.p_change(),
            "change_location": [{"change_at": k, "probability": p} for k, p in list(location.items())[:4]],
            "attribution": [{"changed": list(c), "probability": p} for c, p in list(attribution.items())[:4]],
            "entropy": self.entropy(),
            "hypotheses_evaluated": len(self.fits),
            "regimes": dict(self.regime_weights),
        }


def mixture(posteriors: dict[str, tuple[float, Posterior]]) -> Posterior:
    """Combine posteriors computed under different prior regimes (e.g. memory valid / stale).

    *posteriors* maps regime -> (prior probability, posterior). Regime weights are
    proportional to prior x marginal likelihood; hypothesis probabilities mix.
    """

    names = list(posteriors)
    logw = np.array([math.log(posteriors[r][0]) + posteriors[r][1].log_marginal() for r in names])
    logw -= logw.max()
    w = np.exp(logw)
    w /= w.sum()
    fits: list[Fit] = []
    for weight, name in zip(w, names):
        for f in posteriors[name][1].fits:
            clone = Fit(**{**f.__dict__})
            clone.probability = f.probability * float(weight)
            fits.append(clone)
    fits.sort(key=lambda f: (-f.probability, f.hypothesis.label()))
    post = Posterior(fits)
    post.regime_weights = {name: float(weight) for name, weight in zip(names, w)}
    return post
