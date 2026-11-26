"""The planner must not confuse zero passing errors with impossible certification."""

from math import comb

import pytest

from rain_atlas.science.safety_planning import maximum_passing_count, probability_of_passing


def test_no_passing_count_below_the_zero_event_floor():
    assert maximum_passing_count(58, 0.05, 0.05) is None
    assert probability_of_passing(58, 0.05, 0.05, 0) == 0
    assert maximum_passing_count(59, 0.05, 0.05) == 0
    assert probability_of_passing(59, 0.05, 0.05, 0) == 1


def test_cutoff_is_the_largest_valid_count_using_the_definition():
    p = 0.05
    n = 200

    def tail(k: int) -> float:
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))

    cutoff = maximum_passing_count(n, p, 0.05)
    assert cutoff == 4
    assert tail(cutoff) <= 0.05 < tail(cutoff + 1)
    assert probability_of_passing(n, p, 0.05, p) == pytest.approx(tail(cutoff))


def test_fixed_mission_budget_and_adjusted_alpha():
    assert probability_of_passing(200, 0.05, 0.05, 0.03) == pytest.approx(0.281, abs=0.0001)
    assert probability_of_passing(800, 0.05, 0.05, 0.03) == pytest.approx(0.8713, abs=0.0001)
    assert maximum_passing_count(200, 0.05, 0.05 / 7) == 2


@pytest.mark.parametrize("missions, ceiling, alpha", [(0, 0.05, 0.05), (10, 1, 0.05), (10, 0.05, 0)])
def test_invalid_planning_parameters_fail_closed(missions, ceiling, alpha):
    with pytest.raises(ValueError):
        maximum_passing_count(missions, ceiling, alpha)


def test_invalid_assumed_rate_is_rejected():
    with pytest.raises(ValueError):
        probability_of_passing(200, 0.05, 0.05, float("nan"))
