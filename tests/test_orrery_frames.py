"""Earth-orientation frame transforms against Vallado's worked example.

Vallado, *Fundamentals of Astrodynamics and Applications* (4th ed., 2013),
example 3-15 / the IAU-76/FK5 reduction worked through the book: epoch
2004-04-06 07:51:28.386009 UTC, with the EOP for that day, carrying a state
between the ITRF (EarthFixed) and GCRF/J2000 (treated here as MJ2000Eq).

The published J2000 state uses the EOP nutation corrections (dPsi, dEps), so the
test enables them. ORRERY reproduces the published position to ~1e-5 km; the
residual is dominated by the textbook quoting the Julian date to fewer digits
than the GMST series resolves (about 1e-7 deg of Earth rotation, ~1 cm at GEO,
sub-cm here), which is documented, not a modelling error.
"""

import math

import numpy as np
import pytest

from rain_atlas.orrery.eop import EopTable
from rain_atlas.orrery.frames import EarthOrientation, gmst_1982
from rain_atlas.orrery.timescales import Epoch

# Vallado EOP for 2004-04-06 (example data).
VALLADO_EOP = {
    "x_arcsec": -0.140682,
    "y_arcsec": 0.333309,
    "ut1_utc_s": -0.4399619,
    "lod_s": 0.0015563,
    "dpsi_arcsec": -0.052195,
    "deps_arcsec": -0.003875,
}
R_ITRF = np.array([-1033.4793830, 7901.2952754, 6380.3565958])
V_ITRF = np.array([-3.225636520, -2.872451450, 5.531924446])
R_J2000 = np.array([5102.508959, 6123.011403, 6378.136925])
V_J2000 = np.array([-4.743220156, 0.790536497, 5.533755728])


def _vallado_orientation() -> EarthOrientation:
    rows = [{"mjd": m, **VALLADO_EOP} for m in (53099, 53100, 53101, 53102, 53103)]
    eop = EopTable.from_rows(rows, {"name": "vallado-2004-04-06"})
    return EarthOrientation(eop, nutation_corrections=True, nutation_interval_s=0.0)


def _rotation():
    tt = Epoch.from_iso("UTC", "2004-04-06T07:51:28.386009").to("TT")
    return _vallado_orientation().at(tt)


def test_itrf_to_j2000_position():
    r = _rotation().fixed_to_inertial(R_ITRF)
    assert np.linalg.norm(r - R_J2000) < 2e-5  # km


def test_itrf_to_j2000_velocity():
    _, v = _rotation().fixed_to_inertial(R_ITRF, V_ITRF)
    assert np.linalg.norm(v - V_J2000) < 1e-8  # km/s


def test_j2000_to_itrf_position():
    r = _rotation().inertial_to_fixed(R_J2000)
    assert np.linalg.norm(r - R_ITRF) < 2e-5


def test_round_trip_is_machine_precision():
    rot = _rotation()
    r, v = rot.fixed_to_inertial(R_ITRF, V_ITRF)
    r2, v2 = rot.inertial_to_fixed(r, v)
    assert np.linalg.norm(r2 - R_ITRF) < 1e-9
    assert np.linalg.norm(v2 - V_ITRF) < 1e-12


def test_rotation_matrix_is_orthonormal():
    m = _rotation().matrix
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(m) == pytest.approx(1.0, abs=1e-12)


def test_gmst_1982_matches_vallado():
    # Published GMST for the example is 312.8098943 deg.
    ut1 = Epoch.from_iso("UTC", "2004-04-06T07:51:28.386009").to("TT")
    eop = _vallado_orientation().eop
    ut1 = Epoch.from_iso("UTC", "2004-04-06T07:51:28.386009").to("UT1", eop)
    gmst_deg = math.degrees(gmst_1982(ut1)) % 360.0
    assert gmst_deg == pytest.approx(312.8098943, abs=2e-7)
