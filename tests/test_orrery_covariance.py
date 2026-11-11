"""Covariance propagation through the STM, checked against a Kepler Monte-Carlo cloud."""

import math

import numpy as np
import pytest

from rain_atlas.orrery import covariance
from rain_atlas.orrery.constants import GMAT_EARTH_MU as MU
from rain_atlas.orrery.eop import EopTable
from rain_atlas.orrery.forces import ForceModel, PointMass
from rain_atlas.orrery.kepler import elements_to_state
from rain_atlas.orrery.timescales import Epoch

X0 = np.concatenate(elements_to_state(7000.0, 0.01, math.radians(45), 0.0, 0.0, 0.0, MU))


def test_stm_mapping_consistent_for_small_uncertainty():
    p0 = np.diag(np.array([0.1, 0.1, 0.1, 1e-4, 1e-4, 1e-4]) ** 2)
    out = covariance.covariance_study(X0, p0, 3000.0, MU, model=None, samples=4000, seed=7)
    assert out["position_block_rel_diff"] < 0.05
    assert out["mean_offset_m"] < 50.0  # near-linear: MC mean stays near the reference
    assert 0.90 < out["chi2_95_inside_fraction"] < 0.99


def test_large_uncertainty_shows_nonlinearity():
    small = covariance.covariance_study(
        X0,
        np.diag(np.array([0.1, 0.1, 0.1, 1e-4, 1e-4, 1e-4]) ** 2),
        5000.0,
        MU,
        model=None,
        samples=4000,
        seed=9,
    )
    large = covariance.covariance_study(
        X0,
        np.diag(np.array([5.0, 5.0, 5.0, 5e-3, 5e-3, 5e-3]) ** 2),
        5000.0,
        MU,
        model=None,
        samples=4000,
        seed=9,
    )
    # The linear Gaussian map is far less consistent once the cloud is large.
    assert large["chi2_95_inside_fraction"] < small["chi2_95_inside_fraction"]
    assert large["mean_offset_m"] > small["mean_offset_m"]


def test_force_model_stm_matches_kepler_flow_stm():
    # The numerically propagated STM (point-mass force model) must map a small
    # covariance the same way as the analytic Kepler-flow STM.
    eo_epoch = Epoch.from_iso("UTC", "2026-01-15T00:00:00")
    EopTable.load("eop_c04_2026")  # ensures data present
    model = ForceModel([PointMass(MU)], eo_epoch)
    p0 = np.diag(np.array([0.05, 0.05, 0.05, 5e-5, 5e-5, 5e-5]) ** 2)
    with_model = covariance.covariance_study(X0, p0, 4000.0, MU, model=model, samples=3000, seed=3)
    kepler = covariance.covariance_study(X0, p0, 4000.0, MU, model=None, samples=3000, seed=3)
    p_m = np.asarray(with_model["linear_covariance"])
    p_k = np.asarray(kepler["linear_covariance"])
    assert np.linalg.norm(p_m - p_k) / np.linalg.norm(p_k) < 1e-3


def test_propagate_covariance_is_symmetric_positive_definite():
    stm = np.eye(6)
    stm[0, 3] = 100.0
    p0 = np.diag([1.0, 1.0, 1.0, 1e-2, 1e-2, 1e-2])
    p = covariance.propagate_covariance(stm, p0)
    assert np.allclose(p, p.T)
    assert np.all(np.linalg.eigvalsh(p) > 0)


def test_ellipsoid_axes_are_sorted():
    p = np.diag([9.0, 4.0, 1.0])
    axes = covariance.ellipsoid_axes(p)
    assert axes["semi_axes_km"] == pytest.approx([3.0, 2.0, 1.0])
