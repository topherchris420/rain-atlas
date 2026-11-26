"""Fixed-sample planning for one predeclared mission-level error bound."""

from scipy.stats import binom


def maximum_passing_count(missions: int, ceiling: float, alpha: float) -> int | None:
    """Largest count rejecting P(error) >= ceiling; None means not even zero passes.

    This is a one-sided exact binomial test for independent, identically
    distributed Bernoulli mission outcomes. Alpha is the per-test budget.
    """
    if missions < 1:
        raise ValueError("missions must be positive")
    if not 0 < ceiling < 1 or not 0 < alpha < 1:
        raise ValueError("ceiling and alpha must lie strictly between zero and one")
    passed, failed = -1, missions
    while failed - passed > 1:
        middle = (passed + failed) // 2
        if binom.cdf(middle, missions, ceiling) <= alpha:
            passed = middle
        else:
            failed = middle
    return None if passed < 0 else passed


def probability_of_passing(missions: int, ceiling: float, alpha: float, true_rate: float) -> float:
    """Power at an assumed mission error rate, not a rate inferred from prior results."""
    if not 0 <= true_rate <= 1:
        raise ValueError("true_rate must be between zero and one")
    cutoff = maximum_passing_count(missions, ceiling, alpha)
    return 0.0 if cutoff is None else float(binom.cdf(cutoff, missions, true_rate))
