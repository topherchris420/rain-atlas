"""Integrator empirical order, embedded-pair accuracy, and independent-library agreement."""

import math

import numpy as np
import pytest

from rain_atlas.orrery.constants import GMAT_EARTH_MU as MU
from rain_atlas.orrery.integrators import integrate
from rain_atlas.orrery.kepler import elements_to_state, kepler_propagate, orbital_period

R0, V0 = elements_to_state(7000.0, 0.1, math.radians(30), 0.3, 0.5, 0.2, MU)
Y0 = np.concatenate([R0, V0])
PERIOD = orbital_period(7000.0, MU)
TRUTH = np.concatenate(kepler_propagate(R0, V0, PERIOD, MU))


def _rhs(t, y):
    r = y[:3]
    return np.concatenate([y[3:], -MU * r / np.linalg.norm(r) ** 3])


def _accel(t, r):
    return -MU * r / np.linalg.norm(r) ** 3


@pytest.mark.parametrize(
    "method,base_h,expected",
    [("rk4", 60.0, 4), ("yoshida4", 60.0, 4), ("verlet", 20.0, 2), ("dp54", 120.0, 5), ("rkf78", 480.0, 8)],
)
def test_empirical_convergence_order(method, base_h, expected):
    errs = []
    for factor in (1, 2, 4):
        h = base_h / factor
        n = math.ceil(PERIOD / h)
        res = integrate(_rhs, 0.0, Y0, [PERIOD], method=method, step=PERIOD / n, accel=_accel)
        errs.append(np.linalg.norm(res.states[-1, :3] - TRUTH[:3]))
    orders = [math.log(errs[i] / errs[i + 1], 2) for i in range(len(errs) - 1)]
    # The finest-step pair is closest to the asymptotic order; coarse steps undershoot.
    assert orders[-1] > expected - 0.6, orders


@pytest.mark.parametrize("method", ["dp54", "rkf78", "scipy-dop853"])
def test_adaptive_hits_tolerance(method):
    res = integrate(_rhs, 0.0, Y0, [PERIOD], method=method, rtol=1e-12, atol=1e-12)
    assert np.linalg.norm(res.states[-1, :3] - TRUTH[:3]) < 1e-4  # km


def test_output_times_hit_exactly():
    times = np.linspace(0, PERIOD, 7)
    res = integrate(_rhs, 0.0, Y0, times, method="rkf78", rtol=1e-11, atol=1e-11)
    assert np.allclose(res.times, times, atol=0)
    for i, t in enumerate(times):
        truth = kepler_propagate(R0, V0, t, MU)[0]
        assert np.linalg.norm(res.states[i, :3] - truth) < 1e-4


def test_gmat_rss_step_norm_runs_and_agrees():
    res = integrate(_rhs, 0.0, Y0, [PERIOD], method="rkf78", error_norm="gmat-rss-step", accuracy=1e-11)
    assert np.linalg.norm(res.states[-1, :3] - TRUTH[:3]) < 1e-3
    assert res.accepted > 0


def test_symplectic_energy_bounded_over_many_orbits():
    # A fixed-step symplectic method keeps energy error bounded, not growing.
    times = np.arange(0, 50 * PERIOD + 1, PERIOD)
    res = integrate(_rhs, 0.0, Y0, times, method="yoshida4", step=30.0, accel=_accel)
    energy = 0.5 * np.sum(res.states[:, 3:] ** 2, axis=1) - MU / np.linalg.norm(res.states[:, :3], axis=1)
    drift = np.abs((energy - energy[0]) / energy[0])
    assert drift.max() < 1e-6
