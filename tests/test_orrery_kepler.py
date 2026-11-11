"""Analytic two-body solutions: element round trips, solver agreement, invariants."""

import math

import numpy as np
import pytest

from rain_atlas.orrery.constants import GMAT_EARTH_MU as MU
from rain_atlas.orrery.kepler import (
    elements_to_state,
    kepler_propagate,
    orbital_period,
    solve_kepler,
    state_to_elements,
    universal_propagate,
)

CASES = [
    (7000.0, 0.01, 51.6, 30.0, 40.0, 10.0),
    (26600.0, 0.74, 63.4, 90.0, 270.0, 123.0),
    (42164.0, 1e-4, 0.1, 0.0, 0.0, 200.0),
    (9000.0, 0.3, 98.0, 220.0, 45.0, 300.0),
]


@pytest.mark.parametrize("elset", CASES)
def test_elements_state_round_trip(elset):
    a, e, i, raan, argp, nu = elset
    r, v = elements_to_state(
        a, e, math.radians(i), math.radians(raan), math.radians(argp), math.radians(nu), MU
    )
    el = state_to_elements(r, v, MU)
    assert el["a"] == pytest.approx(a, rel=1e-12)
    assert el["e"] == pytest.approx(e, abs=1e-12)
    assert math.degrees(el["i"]) == pytest.approx(i, abs=1e-10)
    assert math.degrees(el["raan"]) == pytest.approx(raan, abs=1e-9)
    assert math.degrees(el["nu"]) == pytest.approx(nu, abs=1e-9)


@pytest.mark.parametrize("e", [0.0, 0.1, 0.5, 0.9, 0.99])
def test_kepler_equation_residual(e):
    for m_deg in range(0, 360, 23):
        big_e = solve_kepler(math.radians(m_deg), e)
        assert big_e - e * math.sin(big_e) == pytest.approx(math.radians(m_deg), abs=1e-13)


@pytest.mark.parametrize("elset", CASES)
def test_kepler_and_universal_agree(elset):
    a, e, i, raan, argp, nu = elset
    r0, v0 = elements_to_state(
        a, e, math.radians(i), math.radians(raan), math.radians(argp), math.radians(nu), MU
    )
    for frac in (0.1, 0.37, 0.5, 0.83, 1.0):
        dt = frac * orbital_period(a, MU)
        rk, vk = kepler_propagate(r0, v0, dt, MU)
        ru, vu = universal_propagate(r0, v0, dt, MU)
        assert np.linalg.norm(rk - ru) < 1e-7
        assert np.linalg.norm(vk - vu) < 1e-10


@pytest.mark.parametrize("elset", CASES)
def test_energy_and_angular_momentum_conserved(elset):
    a, e, i, raan, argp, nu = elset
    r0, v0 = elements_to_state(
        a, e, math.radians(i), math.radians(raan), math.radians(argp), math.radians(nu), MU
    )
    energy0 = 0.5 * v0 @ v0 - MU / np.linalg.norm(r0)
    h0 = np.cross(r0, v0)
    for frac in (0.25, 0.5, 0.75, 1.0):
        r, v = universal_propagate(r0, v0, frac * orbital_period(a, MU), MU)
        assert 0.5 * v @ v - MU / np.linalg.norm(r) == pytest.approx(energy0, rel=1e-12)
        assert np.linalg.norm(np.cross(r, v) - h0) < 1e-9


def test_period_returns_to_start():
    r0, v0 = elements_to_state(8000.0, 0.2, math.radians(30), 0.4, 0.5, 0.6, MU)
    r, v = kepler_propagate(r0, v0, orbital_period(8000.0, MU), MU)
    assert np.linalg.norm(r - r0) < 1e-7
    assert np.linalg.norm(v - v0) < 1e-10
