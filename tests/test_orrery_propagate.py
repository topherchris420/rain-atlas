"""Numerical propagation of the two-body scenarios against the analytic solution."""

import numpy as np
import pytest

from rain_atlas.orrery import scenarios
from rain_atlas.orrery.constants import GMAT_EARTH_MU as MU
from rain_atlas.orrery.kepler import kepler_trajectory
from rain_atlas.orrery.propagate import position_velocity_errors, propagate

ANALYTIC = scenarios.ANALYTIC_SCENARIOS

# Max position error (m) ORRERY may differ from the exact Kepler solution. The
# Molniya bound is looser: fast perigee passage at e=0.74 is the hardest to integrate.
TOL_M = {"S1-leo-twobody": 1e-3, "S2-molniya-twobody": 5e-2, "S3-geo-twobody": 1e-2}


@pytest.mark.parametrize("name", ANALYTIC)
def test_two_body_matches_analytic(name):
    scen = scenarios.scenario(name)
    traj = propagate(scen["config"])
    x0 = np.asarray(scen["config"]["initial_state"])
    ref = kepler_trajectory(x0[:3], x0[3:6], traj.times, MU)
    err = position_velocity_errors(traj.states, ref)
    assert err["max_position_error_m"] < TOL_M[name]


@pytest.mark.parametrize("name", ANALYTIC)
def test_two_body_energy_and_momentum_conserved(name):
    scen = scenarios.scenario(name)
    traj = propagate(scen["config"])
    assert traj.diagnostics["relative_energy_integral_drift"] < 1e-10
    assert traj.diagnostics["relative_angular_momentum_drift"] < 1e-11


def test_record_is_json_serialisable():
    import json

    traj = propagate(scenarios.scenario("S1-leo-twobody")["config"])
    text = json.dumps(traj.record())
    assert "orrery.orbital-dynamics" in text


def test_impulsive_maneuver_changes_velocity():
    cfg = dict(scenarios.scenario("S1-leo-twobody")["config"])
    cfg = {
        **cfg,
        "duration_s": 6000.0,
        "output_step_s": 60.0,
        "maneuvers": [{"time_s": 3000.0, "dv_km_s": [0.0, 0.0, 0.1]}],
    }
    traj = propagate(cfg)
    before = traj.states[traj.times < 3000.0][-1]
    after = traj.states[traj.times >= 3000.0][0]
    # Output at exactly 3000 s is the pre-burn state; the next sample reflects the +0.1 km/s burn.
    assert np.linalg.norm(after[3:6]) > np.linalg.norm(before[3:6])


def test_integrator_choices_agree():
    cfg = scenarios.scenario("S1-leo-twobody")["config"]
    a = propagate({**cfg, "integrator": {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12}})
    b = propagate({**cfg, "integrator": {"method": "scipy-dop853", "rtol": 1e-12, "atol": 1e-12}})
    err = position_velocity_errors(a.states, b.states)
    assert err["max_position_error_m"] < 1e-2
