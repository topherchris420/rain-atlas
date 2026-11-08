"""Self-gravitating N-body: the figure-eight choreography and DE421 agreement."""

import numpy as np
import pytest

from rain_atlas.orrery import nbody, scenarios
from rain_atlas.orrery.constants import DE421_GM
from rain_atlas.orrery.ephemeris import Ephemeris, et_from_epoch
from rain_atlas.orrery.timescales import Epoch


def test_figure_eight_returns_to_start():
    system, y0 = nbody.figure_eight_system()
    res = nbody.integrate_system(system, y0, [nbody.FIGURE_EIGHT["period"]], rtol=1e-13, atol=1e-13)
    assert np.linalg.norm(res["states"][-1] - y0) < 1e-6


def test_figure_eight_conserves_invariants():
    system, y0 = nbody.figure_eight_system()
    times = np.linspace(0, nbody.FIGURE_EIGHT["period"], 50)
    res = nbody.integrate_system(system, y0, times, rtol=1e-13, atol=1e-13)
    assert res["relative_energy_drift"] < 1e-11
    assert res["angular_momentum_drift"] < 1e-11
    assert res["barycentre_drift"] < 1e-10


@pytest.mark.slow
def test_solar_system_tracks_de421():
    # Integrate the ten major bodies from DE421 initial conditions as Newtonian
    # point masses and compare back against the ephemeris. The residual (DE421
    # also carries relativity and asteroid perturbations this model omits) is a
    # genuine independent check, not a self-comparison. Measured on this build:
    # Earth-Moon vector ~0.9 km at 30 d, ~12 km at 1 yr; Earth-SSB ~61 km at 1 yr.
    eph = Ephemeris.load("de421_2026")
    et0 = et_from_epoch(Epoch.from_iso("UTC", "2026-01-15T00:00:00").to("TDB"))
    bodies = scenarios.NBODY_SCENARIOS["S9-solar-system-de421"]["bodies"]
    gm = nbody.de421_nbody_gm(DE421_GM)
    system, y0 = nbody.solar_system_from_ephemeris(eph, bodies, gm, et0, center="ssb")
    span = 30.0 * 86400.0
    res = nbody.integrate_system(system, y0, [span], rtol=1e-13, atol=1e-13)
    final = res["states"][-1].reshape(2, len(bodies), 3)
    ie, im = bodies.index("earth"), bodies.index("moon")
    em_model = final[0][im] - final[0][ie]
    em_ref = eph.state("moon", "earth", et0 + span)[0]
    earth_ref = eph.position("earth", "ssb", et0 + span)
    assert np.linalg.norm(em_model - em_ref) < 3.0  # km
    assert np.linalg.norm(final[0][ie] - earth_ref) < 3.0  # km
    assert res["relative_energy_drift"] < 1e-12
