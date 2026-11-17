"""Experiment-selection policies for the central scientific experiment.

Each policy decides which condition to run next given what the agent knows.
All policies are *scripted* -- deterministic code, never a language model --
so the comparison measures the selection architecture, not model luck.
"""

from __future__ import annotations

import random
from typing import Protocol

from .models import CandidateModels, Observation

PolicyName = str

ADAPTIVE = "adaptive"
ADAPTIVE_NO_MEMORY = "adaptive-no-memory"
GRID = "grid"
RANDOM = "random"

POLICIES = (ADAPTIVE, ADAPTIVE_NO_MEMORY, GRID, RANDOM)


class Selector(Protocol):
    name: PolicyName

    def next_condition(self, grid: list[float], observations: list[Observation]) -> float | None:
        """Choose the next coupling value, or None when the grid is exhausted."""


class AdaptiveSelector:
    """Maximum-disagreement selection among untested conditions."""

    name = ADAPTIVE

    def __init__(self, models: CandidateModels) -> None:
        self.models = models

    def next_condition(self, grid: list[float], observations: list[Observation]) -> float | None:
        tested = {round(obs.coupling, 6) for obs in observations}
        remaining = [c for c in grid if round(c, 6) not in tested]
        if not remaining:
            return None
        return max(remaining, key=lambda c: (self.models.disagreement(c), -abs(c - 0.5)))


class GridSelector:
    """Fixed heuristic: run the grid in order, low to high."""

    name = GRID

    def next_condition(self, grid: list[float], observations: list[Observation]) -> float | None:
        tested = {round(obs.coupling, 6) for obs in observations}
        for value in sorted(grid):
            if round(value, 6) not in tested:
                return value
        return None


class RandomSelector:
    """Seeded random selection among untested conditions."""

    name = RANDOM

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def next_condition(self, grid: list[float], observations: list[Observation]) -> float | None:
        tested = {round(obs.coupling, 6) for obs in observations}
        remaining = [c for c in grid if round(c, 6) not in tested]
        if not remaining:
            return None
        return self._rng.choice(sorted(remaining))


def select_condition(
    policy: PolicyName, grid: list[float], observations: list[Observation], *, seed: int
) -> float | None:
    """Dispatch to a policy by name (used by the central experiment)."""

    if policy == ADAPTIVE or policy == ADAPTIVE_NO_MEMORY:
        return AdaptiveSelector(CandidateModels()).next_condition(grid, observations)
    if policy == GRID:
        return GridSelector().next_condition(grid, observations)
    if policy == RANDOM:
        return RandomSelector(seed).next_condition(grid, observations)
    raise ValueError(f"unknown policy {policy!r}; expected one of {POLICIES}")
