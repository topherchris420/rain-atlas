"""Uncertainty for the benchmark: paired, family-stratified bootstrap over problems.

Problems are the independent units. Every arm runs on the same problems
(common random numbers), so arm differences are computed per problem and
resampled together. Proportions additionally get a Wilson score interval and
the reported interval is the union of the two, so zero-event cells do not
produce falsely narrow intervals (the convention of ``rain central`` v2).
Verdicts are three-valued: *supported* when the whole interval satisfies the
hypothesis, *contradicted* when the whole interval violates it, *unresolved*
otherwise.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from ..science.uncertainty import wilson


class PairedBootstrap:
    def __init__(self, families: Sequence[str], *, seed: int, resamples: int = 10_000):
        self.families = np.asarray(families)
        rng = np.random.default_rng(seed)
        self.index = []
        for family in sorted(set(self.families.tolist())):
            members = np.flatnonzero(self.families == family)
            self.index.append(members[rng.integers(0, len(members), size=(resamples, len(members)))])
        self.resamples = resamples

    def means(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=float)
        total = sum(values[idx].sum(axis=1) for idx in self.index)
        count = sum(idx.shape[1] for idx in self.index)
        return total / count

    def interval(self, values: np.ndarray, alpha: float) -> tuple[float, float]:
        samples = self.means(values)
        lo, hi = np.quantile(samples, [alpha / 2, 1 - alpha / 2])
        return float(lo), float(hi)


def proportion_interval(boot: PairedBootstrap, flags: np.ndarray, alpha: float) -> tuple[float, float]:
    flags = np.asarray(flags, dtype=float)
    lo, hi = boot.interval(flags, alpha)
    w = wilson(int(flags.sum()), len(flags), alpha)
    return min(lo, w["low"]), max(hi, w["high"])


def three_valued(interval: tuple[float, float], holds: Callable[[float], bool]) -> str:
    lo, hi = interval
    if holds(lo) and holds(hi):
        return "supported"
    if not holds(lo) and not holds(hi):
        return "contradicted"
    return "unresolved"


def combine(verdicts: Sequence[str]) -> str:
    """Intersection hypothesis: supported only if every part is supported."""

    if any(v == "contradicted" for v in verdicts):
        return "contradicted"
    if all(v == "supported" for v in verdicts):
        return "supported"
    return "unresolved"
