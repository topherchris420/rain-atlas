"""Force-model terms: analytic/numeric gradient agreement and closed-form vs harmonic J2."""

import math

import numpy as np

from rain_atlas.orrery.constants import GMAT_CONSTANTS as C
from rain_atlas.orrery.eop import EopTable
from rain_atlas.orrery.ephemeris import Ephemeris, FrameTie
from rain_atlas.orrery.forces import (
    ForceModel,
    PointMass,
    SphericalHarmonics,
    ThirdBody,
    ZonalJ2,
    _EvalContext,
    load_gravity_field,
)
from rain_atlas.orrery.frames import EarthOrientation
from rain_atlas.orrery.kepler import elements_to_state
from rain_atlas.orrery.timescales import Epoch

EPOCH = Epoch.from_iso("UTC", "2026-01-15T00:00:00")
R0, V0 = elements_to_state(7000.0, 0.1, math.radians(45), 0.3, 0.5, 0.2, C["earth_mu_km3_s2"])


def _orientation():
    return EarthOrientation(EopTable.load("eop_c04_2026"))


def _numeric_gradient(term, ctx, r, h=1e-2):
    grad = np.empty((3, 3))
    for k in range(3):
        dr = np.zeros(3)
        dr[k] = h
        grad[:, k] = (term.accel(ctx, r + dr) - term.accel(ctx, r - dr)) / (2 * h)
    return grad


def test_point_mass_gradient_matches_finite_difference():
    model = ForceModel([PointMass(C["earth_mu_km3_s2"])], EPOCH)
    ctx = _EvalContext(model, 0.0)
    _, grad = PointMass(C["earth_mu_km3_s2"]).evaluate(ctx, R0)
    assert np.allclose(grad, _numeric_gradient(PointMass(C["earth_mu_km3_s2"]), ctx, R0), rtol=1e-5)


def test_j2_closed_form_equals_harmonic_degree2_order0():
    field = load_gravity_field("jgm3_8x8")
    j2 = -field["C"][2, 0] * math.sqrt(5)
    eo = _orientation()
    fm_j2 = ForceModel(
        [PointMass(field["mu"]), ZonalJ2(field["mu"], field["radius"], j2, "earth-fixed")], EPOCH, eo
    )
    fm_sh = ForceModel(
        [SphericalHarmonics(field["mu"], field["radius"], field["C"], field["S"], 2, 0)], EPOCH, eo
    )
    a_j2, _ = fm_j2.evaluate(100.0, R0)
    a_sh, _ = fm_sh.evaluate(100.0, R0)
    assert np.linalg.norm(a_j2 - a_sh) / np.linalg.norm(a_j2) < 1e-13


def test_j2_inertial_gradient_matches_finite_difference():
    term = ZonalJ2(C["earth_mu_km3_s2"], C["earth_radius_km"], C["earth_j2"], "inertial")
    model = ForceModel([term], EPOCH)
    ctx = _EvalContext(model, 0.0)
    _, grad = term.evaluate(ctx, R0)
    assert np.allclose(grad, _numeric_gradient(term, ctx, R0), rtol=1e-6)


def test_third_body_gradient_matches_finite_difference():
    eph = Ephemeris.load("de421_2026")
    term = ThirdBody("moon", C["moon_mu_km3_s2"], eph, frame_tie=FrameTie("none"))
    model = ForceModel([term], EPOCH)
    ctx = _EvalContext(model, 0.0)
    _, grad = term.evaluate(ctx, R0)
    assert np.allclose(grad, _numeric_gradient(term, ctx, R0), rtol=1e-6)


def test_stm_derivative_structure():
    model = ForceModel([PointMass(C["earth_mu_km3_s2"])], EPOCH)
    y = np.concatenate([R0, V0, np.eye(6).ravel()])
    dy = model.rhs_stm(0.0, y)
    assert np.allclose(dy[:3], V0)
    phi_dot = dy[6:42].reshape(6, 6)
    assert np.allclose(phi_dot[:3], np.eye(6)[3:])  # top rows are the velocity block of the identity STM


def test_energy_integral_available_only_for_conservative_terms():
    conservative = ForceModel([PointMass(C["earth_mu_km3_s2"])], EPOCH)
    assert conservative.energy(0.0, np.concatenate([R0, V0])) is not None
    eo = _orientation()
    rotating = ForceModel(
        [
            PointMass(C["earth_mu_km3_s2"]),
            ZonalJ2(C["earth_mu_km3_s2"], C["earth_radius_km"], C["earth_j2"], "earth-fixed"),
        ],
        EPOCH,
        eo,
    )
    assert rotating.energy(0.0, np.concatenate([R0, V0])) is None
