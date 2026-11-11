"""DE421 ephemeris and the ICRF frame tie against GMAT-reported body positions."""

import numpy as np
import pytest

from rain_atlas.orrery.ephemeris import Ephemeris, FrameTie, et_from_epoch
from rain_atlas.orrery.timescales import Epoch

# GMAT R2026a (DE421/SPICE) MJ2000Eq positions of the Moon and Sun relative to Earth
# at 2026-01-15 00:00:00 UTC, from a reference run (km).
GMAT_MOON = np.array([-126366.3068933751, -336871.1213879104, -185409.3135274333])
GMAT_SUN = np.array([60961944.36274343, -122885591.3924775, -53269545.79083563])


@pytest.fixture(scope="module")
def eph():
    return Ephemeris.load("de421_2026")


@pytest.fixture(scope="module")
def tie():
    return FrameTie("gmat-icrf-table")


def _et():
    tdb = Epoch.from_iso("UTC", "2026-01-15T00:00:00").to("TDB")
    return et_from_epoch(tdb)


def test_moon_matches_gmat_with_frame_tie(eph, tie):
    raw = eph.position("moon", "earth", _et())
    a1 = Epoch.from_iso("UTC", "2026-01-15T00:00:00").to("A1").gmat_modjulian()
    tied = tie.matrix(a1) @ raw
    assert np.linalg.norm(tied - GMAT_MOON) < 1e-3  # km (metre level)
    # Without the tie, the ICRF/FK5 difference is tens of metres.
    assert np.linalg.norm(raw - GMAT_MOON) > 0.01


def test_sun_matches_gmat_with_frame_tie(eph, tie):
    raw = eph.position("sun", "earth", _et())
    a1 = Epoch.from_iso("UTC", "2026-01-15T00:00:00").to("A1").gmat_modjulian()
    tied = tie.matrix(a1) @ raw
    assert np.linalg.norm(tied - GMAT_SUN) < 0.05  # km
    assert np.linalg.norm(raw - GMAT_SUN) > 1.0  # ICRF/FK5 offset is ~15 km at 1 au


def test_moon_minus_earth_shortcut_is_consistent(eph):
    et = _et()
    direct = eph.state("moon", "earth", et)[0]
    chained = eph.position("moon", "ssb", et) - eph.position("earth", "ssb", et)
    assert np.linalg.norm(direct - chained) < 1e-6


def test_chebyshev_velocity_matches_position_derivative(eph):
    et = _et()
    seg = eph.segments[301]
    _, v = seg.state(et)
    h = 1.0
    r_plus = seg.state(et + h)[0]
    r_minus = seg.state(et - h)[0]
    assert np.allclose(v, (r_plus - r_minus) / (2 * h), rtol=1e-7)


def test_frame_tie_none_is_identity(eph):
    tie = FrameTie("none")
    assert np.allclose(tie.matrix(31055.5), np.eye(3))


def test_frame_tie_matrix_is_orthonormal(tie):
    a1 = Epoch.from_iso("UTC", "2026-01-15T00:00:00").to("A1").gmat_modjulian()
    m = tie.matrix(a1)
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
