"""The critic: finds where the current explanation is inadequate.

Diagnostics *propose*; exact evidence *decides*. Nothing here can make a
hypothesis true: a flagged term only enters the working set, where it must win
on evidence like every other explanation.

* :func:`surprise` -- prequential check of a new experiment against the
  predictive distribution fixed *before* the experiment was analyzed.
* :func:`lm_tests` -- Lagrange-multiplier (score) tests for grammar terms
  missing from the leading model, computed from sufficient statistics.
* :func:`ljung_box` -- residual whiteness of the newest experiment.
* :func:`noise_assumption` -- kurtosis test of the Gaussian-noise assumption.
* :func:`huber_weights` / :func:`huber_fit` -- the robust estimator used after
  the noise assumption fails and as the independent out-of-sample method.
* :func:`out_of_sample_check` -- robust held-out comparison of the leading
  structure against its structural neighbours (independent of the evidence).
* :func:`chow_test` -- classical F-test that coefficients differ across a
  change point (independent of the Bayesian change-point evidence).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy import stats

from .inference import Analysis, Fit
from .oscillator import INDEX, LIBRARY

SURPRISE_FLAG = 4.0
LM_ALPHA = 0.001
WHITENESS_ALPHA = 1e-4
KURTOSIS_ALPHA = 1e-4


def surprise(fit: Fit, phi: np.ndarray, y: np.ndarray, *, robust: bool = False) -> dict:
    """Standardized misfit of fresh rows under *fit*'s predictive (z > 4 is surprising).

    Gaussian mode: z = (sum of squared standardized residuals / E - n) / sqrt(2n).
    Robust mode (after the Gaussian-noise assumption has failed): the larger of
    the standardized excess of the MAD scale ratio and the standardized median,
    so heavy tails alone do not register as misfit.
    """

    mean, scale, dof = fit.predictive(phi)
    z = (y - mean) / scale
    n = len(y)
    if robust:
        ratio = 1.4826 * float(np.median(np.abs(z - np.median(z))))
        scale_z = (ratio - 1.0) / math.sqrt(1.36 / n)
        loc_z = abs(float(np.median(z))) / (1.2533 / math.sqrt(n))
        stat = float(max(scale_z, loc_z))
    else:
        expected = dof / (dof - 2.0) if dof > 2 else 1.0
        stat = float((np.sum(z * z) / expected - n) / math.sqrt(2.0 * n))
    logpdf = stats.t.logpdf(y, dof, loc=mean, scale=scale)
    return {
        "z": stat,
        "mean_log_predictive": float(np.mean(logpdf)),
        "rows": n,
        "robust": robust,
        "flag": stat > SURPRISE_FLAG,
    }


def _segment_gram(analysis: Analysis, fit: Fit):
    """Augmented X^T X, X^T phi_c, phi_c^T phi_c pieces for score tests under *fit*."""

    n = analysis.count
    G_all, h_all = analysis.prefix_G[n], analysis.prefix_h[n]
    if fit.hypothesis.change_at is None:
        cross = fit.post_map @ G_all  # (k, L): X^T phi_c for every library column c
    else:
        k = fit.hypothesis.change_at
        G_pre = analysis.prefix_G[k]
        cross = fit.pre_map @ G_pre + fit.post_map @ (G_all - G_pre)
    return fit.XtX, fit.Xty, fit.yty, fit.n, cross, G_all, h_all


def lm_tests(analysis: Analysis, fit: Fit, candidates: Sequence[str]) -> list[dict]:
    """Score tests for adding each candidate term to *fit* (one degree of freedom each)."""

    XtX, Xty, yty, n, cross, G_all, h_all = _segment_gram(analysis, fit)
    k = XtX.shape[0]
    try:
        beta = np.linalg.solve(XtX, Xty)
    except np.linalg.LinAlgError:
        return []
    sigma2 = max((yty - beta @ Xty) / max(n - k, 1.0), 1e-12)
    inv = np.linalg.inv(XtX)
    out = []
    for term in candidates:
        c = INDEX[term]
        xc = cross[:, c]
        resid_cross = h_all[c] - xc @ beta  # phi_c^T (y - X beta)
        denom = G_all[c, c] - xc @ inv @ xc  # phi_c^T M phi_c
        if denom <= 1e-9 * max(G_all[c, c], 1e-12):
            continue
        lm = float(resid_cross**2 / (sigma2 * denom))
        out.append({"term": term, "statistic": lm, "p": float(stats.chi2.sf(lm, 1))})
    out.sort(key=lambda r: (r["p"], LIBRARY.index(r["term"])))
    threshold = LM_ALPHA / max(len(out), 1)
    for r in out:
        r["proposed"] = r["p"] < threshold
    return out


def ljung_box(residuals: np.ndarray, lags: int = 5) -> dict:
    r = np.asarray(residuals, dtype=float) - np.mean(residuals)
    n = len(r)
    denom = float(r @ r)
    if n <= lags + 1 or denom <= 0:
        return {"statistic": 0.0, "p": 1.0, "flag": False}
    acf = np.array([float(r[:-k] @ r[k:]) / denom for k in range(1, lags + 1)])
    q = float(n * (n + 2) * np.sum(acf**2 / (n - np.arange(1, lags + 1))))
    p = float(stats.chi2.sf(q, lags))
    return {"statistic": q, "p": p, "flag": p < WHITENESS_ALPHA, "acf": [float(a) for a in acf]}


def noise_assumption(standardized: np.ndarray) -> dict:
    z = np.asarray(standardized, dtype=float)
    if len(z) < 20:
        return {"excess_kurtosis": 0.0, "p": 1.0, "flag": False}
    result = stats.kurtosistest(z)
    excess = float(stats.kurtosis(z))
    p = float(result.pvalue)
    return {"excess_kurtosis": excess, "p": p, "flag": p < KURTOSIS_ALPHA and excess > 0}


def huber_weights(residuals: np.ndarray, scale: float, c: float = 1.345) -> np.ndarray:
    a = np.abs(residuals) / max(scale, 1e-12)
    return np.where(a <= c, 1.0, c / np.maximum(a, 1e-12))


def robust_scale(residuals: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(residuals - np.median(residuals)))) or 1e-6


def huber_fit(phi: np.ndarray, y: np.ndarray, structure: Sequence[str], iterations: int = 25) -> np.ndarray:
    """Huber M-estimate by iteratively reweighted least squares (library-length vector)."""

    cols = [INDEX[t] for t in structure]
    X = phi[:, cols]
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iterations):
        r = y - X @ beta
        w = huber_weights(r, robust_scale(r))
        Xw = X * w[:, None]
        new = np.linalg.lstsq(Xw.T @ X, Xw.T @ y, rcond=None)[0]
        if np.allclose(new, beta, rtol=1e-10, atol=1e-12):
            beta = new
            break
        beta = new
    out = np.zeros(len(LIBRARY))
    out[cols] = beta
    return out


@dataclass
class RowSet:
    phi: np.ndarray
    y: np.ndarray

    @classmethod
    def stack(cls, parts: Sequence[tuple[np.ndarray, np.ndarray]]) -> "RowSet":
        return cls(np.vstack([p for p, _ in parts]), np.concatenate([y for _, y in parts]))


def _robust_loss(r: np.ndarray, scale: float, c: float = 1.345) -> np.ndarray:
    a = np.abs(r) / scale
    return np.where(a <= c, 0.5 * a * a, c * a - 0.5 * c * c)


def out_of_sample_check(
    train: RowSet,
    test: RowSet,
    structure: Sequence[str],
    neighbours: Sequence[tuple[str, ...]],
    alpha: float = 0.01,
) -> dict:
    """Robust held-out comparison: every term must earn its place, no neighbour may win.

    Each structure is fit with the Huber estimator on *train* and scored by
    robust loss on *test*. A reduced neighbour (one term fewer) must be
    significantly worse; an extended neighbour (one term more) must not be
    significantly better (paired one-sided t-tests over test rows).
    """

    structure = tuple(structure)
    base = huber_fit(train.phi, train.y, structure)
    r0 = test.y - test.phi @ base
    scale = robust_scale(r0)
    loss0 = _robust_loss(r0, scale)
    details = []
    outcome = "corroborated"
    for nb in neighbours:
        beta = huber_fit(train.phi, train.y, nb)
        loss = _robust_loss(test.y - test.phi @ beta, scale)
        diff = loss - loss0  # positive: neighbour worse
        sd = float(np.std(diff, ddof=1)) or 1e-12
        t = float(np.mean(diff) / (sd / math.sqrt(len(diff))))
        reduced = len(nb) < len(structure)
        if reduced:
            p = float(stats.t.sf(t, len(diff) - 1))  # H1: neighbour worse
            ok = p < alpha
            if not ok and outcome == "corroborated":
                outcome = "inconclusive"
        else:
            p = float(stats.t.cdf(t, len(diff) - 1))  # H1: neighbour better
            ok = p >= alpha
            if not ok:
                outcome = "contradicted"
        details.append(
            {"neighbour": list(nb), "kind": "reduced" if reduced else "extended", "t": t, "p": p, "ok": ok}
        )
    return {
        "method": "Huber IRLS fit on training experiments, robust loss on fresh challenge rows",
        "outcome": outcome,
        "comparisons": details,
        "test_rows": int(len(test.y)),
    }


def chow_test(pre: RowSet, post: RowSet, structure: Sequence[str], changed: Sequence[str]) -> dict:
    """F-test that *changed* coefficients differ between the pre and post segments."""

    s_cols = [INDEX[t] for t in structure]
    c_cols = [INDEX[t] for t in changed]
    X_pre = pre.phi[:, s_cols]
    X_post = post.phi[:, s_cols]
    X_r = np.vstack([X_pre, X_post])
    y = np.concatenate([pre.y, post.y])
    extra = np.vstack([np.zeros((len(pre.y), len(c_cols))), post.phi[:, c_cols]])
    X_u = np.hstack([X_r, extra])
    rss_r = float(np.sum((y - X_r @ np.linalg.lstsq(X_r, y, rcond=None)[0]) ** 2))
    rss_u = float(np.sum((y - X_u @ np.linalg.lstsq(X_u, y, rcond=None)[0]) ** 2))
    q = len(c_cols)
    dof = len(y) - X_u.shape[1]
    if dof <= 0 or rss_u <= 0:
        return {"F": 0.0, "p": 1.0, "dof": [q, max(dof, 0)]}
    F = ((rss_r - rss_u) / q) / (rss_u / dof)
    return {"F": float(F), "p": float(stats.f.sf(F, q, dof)), "dof": [q, dof]}


def _huber_beta(X: np.ndarray, y: np.ndarray, iterations: int = 10) -> np.ndarray:
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iterations):
        r = y - X @ beta
        w = huber_weights(r, robust_scale(r))
        Xw = X * w[:, None]
        beta = np.linalg.solve(Xw.T @ X + 1e-9 * np.eye(X.shape[1]), Xw.T @ y)
    return beta


def cross_validated_check(
    designs: Sequence[Sequence[np.ndarray]],
    targets: Sequence[np.ndarray],
    kinds: Sequence[str],
    *,
    robust: bool,
    alpha: float = 0.01,
    max_folds: int = 8,
) -> dict:
    """Leave-experiments-out prediction: target (designs[0]) against its neighbours.

    ``designs[j][e]`` is hypothesis j's design matrix for experiment e and
    ``targets[e]`` the observed accelerations. Each fold leaves out a group of
    experiments, refits every hypothesis (least squares, or Huber IRLS when
    the Gaussian assumption failed) and scores the left-out rows. A reduced
    neighbour must predict significantly worse than the target; an extended
    neighbour must not predict significantly better (paired z-tests over rows).
    """

    experiments = len(targets)
    if experiments < 2:
        return {"outcome": None, "reason": "fewer than two experiments to cross-validate"}
    folds = [
        list(range(experiments))[i :: min(max_folds, experiments)] for i in range(min(max_folds, experiments))
    ]
    residuals: list[list[np.ndarray]] = [[] for _ in designs]
    for fold in folds:
        train = [e for e in range(experiments) if e not in fold]
        y_train = np.concatenate([targets[e] for e in train])
        y_test = np.concatenate([targets[e] for e in fold])
        for j, per_exp in enumerate(designs):
            X_train = np.vstack([per_exp[e] for e in train])
            X_test = np.vstack([per_exp[e] for e in fold])
            if robust:
                beta = _huber_beta(X_train, y_train)
            else:
                beta = np.linalg.lstsq(X_train, y_train, rcond=None)[0]
            residuals[j].append(y_test - X_test @ beta)
    r = [np.concatenate(parts) for parts in residuals]
    scale = robust_scale(r[0])
    losses = [_robust_loss(ri, scale) if robust else 0.5 * (ri / scale) ** 2 for ri in r]
    outcome = "corroborated"
    comparisons = []
    alpha = alpha / max(len(designs) - 1, 1)  # Bonferroni across neighbours
    for j in range(1, len(designs)):
        diff = losses[j] - losses[0]
        sd = float(np.std(diff, ddof=1)) or 1e-12
        zstat = float(np.mean(diff) / (sd / math.sqrt(len(diff))))
        if kinds[j] == "reduced":
            p = float(stats.norm.sf(zstat))
            ok = p < alpha
            if not ok and outcome == "corroborated":
                outcome = "inconclusive"
        else:
            p = float(stats.norm.cdf(zstat))
            ok = p >= alpha
            if not ok:
                outcome = "contradicted"
        comparisons.append({"neighbour": j, "kind": kinds[j], "z": zstat, "p": p, "ok": ok})
    return {
        "method": (
            "leave-experiments-out cross-validation, "
            + ("Huber IRLS, robust loss" if robust else "least squares, squared loss")
        ),
        "outcome": outcome,
        "comparisons": comparisons,
        "rows": int(len(r[0])),
        "folds": len(folds),
    }
