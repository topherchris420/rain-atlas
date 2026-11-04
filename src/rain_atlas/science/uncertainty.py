"""Small transparent uncertainty tools; assumptions travel with results."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats


def mean_interval(values: ArrayLike, alpha: float = 0.05) -> dict:
    """Student-t interval over independent replicates, never temporal samples."""
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or x.size < 2 or not np.isfinite(x).all() or not 0 < alpha < 1:
        raise ValueError("need >=2 finite independent replicates and 0<alpha<1")
    mean = float(x.mean())
    se = float(x.std(ddof=1) / np.sqrt(x.size))
    radius = float(stats.t.ppf(1 - alpha / 2, x.size - 1) * se)
    return {
        "mean": mean,
        "low": mean - radius,
        "high": mean + radius,
        "se": se,
        "n": int(x.size),
        "alpha": alpha,
        "method": "Student-t over independent replicate summaries",
    }


def wilson(successes: int, trials: int, alpha: float = 0.05) -> dict:
    """Wilson binomial score interval, including zero observed errors."""
    if (
        not isinstance(successes, int)
        or not isinstance(trials, int)
        or not 0 <= successes <= trials
        or trials < 1
        or not 0 < alpha < 1
    ):
        raise ValueError("require integer 0<=successes<=trials, trials>0, 0<alpha<1")
    z = float(stats.norm.ppf(1 - alpha / 2))
    p = successes / trials
    den = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / den
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials**2)) / den
    return {
        "rate": p,
        "low": 0.0 if successes == 0 else max(0.0, center - half),
        "high": 1.0 if successes == trials else min(1.0, center + half),
        "n": trials,
        "successes": successes,
        "alpha": alpha,
        "method": "Wilson score",
    }


def holm(pvalues: ArrayLike, alpha: float = 0.05) -> dict:
    """Holm family-wise adjusted p-values; valid under arbitrary dependence."""
    p = np.asarray(pvalues, dtype=float)
    if (
        p.ndim != 1
        or p.size == 0
        or not np.isfinite(p).all()
        or np.any((p < 0) | (p > 1))
        or not 0 < alpha < 1
    ):
        raise ValueError("finite p-values in [0,1] and 0<alpha<1 required")
    order = np.argsort(p)
    adj = np.empty_like(p)
    adj[order] = np.minimum(1, np.maximum.accumulate(p[order] * (p.size - np.arange(p.size))))
    return {"adjusted": adj.tolist(), "reject": (adj <= alpha).tolist(), "alpha": alpha}


def disjoint_samples(discovery: list[str], evaluation: list[str]) -> None:
    """Reject exact input-identity leakage; does not detect semantic near-duplicates."""
    if not discovery or not evaluation or set(discovery) & set(evaluation):
        raise ValueError("discovery and evaluation sample identities must be nonempty and disjoint")
