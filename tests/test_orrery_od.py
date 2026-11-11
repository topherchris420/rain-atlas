"""Orbit determination: batch recovery of a known state and NEES covariance consistency."""

import math

import numpy as np
import pytest

from rain_atlas.orrery import od
from rain_atlas.orrery.constants import GMAT_CONSTANTS as C
from rain_atlas.orrery.eop import EopTable
from rain_atlas.orrery.forces import ForceModel, PointMass, ZonalJ2
from rain_atlas.orrery.frames import EarthOrientation
from rain_atlas.orrery.kepler import elements_to_state
from rain_atlas.orrery.timescales import Epoch

EPOCH = Epoch.from_iso("UTC", "2026-01-15T00:00:00")
X0_TRUTH = np.concatenate(
    elements_to_state(
        6878.0,
        0.01,
        math.radians(51.6),
        math.radians(30),
        math.radians(40),
        math.radians(10),
        C["earth_mu_km3_s2"],
    )
)
SIGMA = np.array([0.02, 2e-5])  # 20 m range, 2 cm/s range-rate
# A 12-hour, three-station arc makes the 6-state fully observable (rank 6); a
# shorter arc leaves one weakly observed direction and a rank-deficient normal matrix.
TIMES = np.arange(0.0, 12 * 3600.0 + 1, 30.0)


def _orientation():
    return EarthOrientation(EopTable.load("eop_c04_2026"))


def _model():
    return ForceModel(
        [
            PointMass(C["earth_mu_km3_s2"]),
            ZonalJ2(C["earth_mu_km3_s2"], C["earth_radius_km"], C["earth_j2"], "earth-fixed"),
        ],
        EPOCH,
        _orientation(),
    )


def _stations(model):
    eo = model.orientation
    return [
        od.GroundStation(
            "goldstone",
            math.radians(35.3),
            math.radians(-116.9),
            1.0,
            C["earth_radius_km"],
            C["earth_flattening"],
            eo,
        ),
        od.GroundStation(
            "canberra",
            math.radians(-35.4),
            math.radians(149.0),
            0.7,
            C["earth_radius_km"],
            C["earth_flattening"],
            eo,
        ),
        od.GroundStation(
            "madrid",
            math.radians(40.4),
            math.radians(-4.2),
            0.8,
            C["earth_radius_km"],
            C["earth_flattening"],
            eo,
        ),
    ]


def test_batch_recovers_truth_from_noiseless_observations():
    model = _model()
    stations = _stations(model)
    obs, _ = od.simulate_observations(model, X0_TRUTH, stations, TIMES, SIGMA, noisy=False)
    x0_bar = X0_TRUTH + np.array([1.0, -1.0, 0.5, 1e-3, -1e-3, 5e-4])
    result = od.batch_least_squares(model, stations, obs, x0_bar, SIGMA)
    assert result.converged
    assert np.linalg.norm(result.estimate[:3] - X0_TRUTH[:3]) * 1000 < 1.0  # m


def test_batch_residuals_near_unity_with_noise():
    model = _model()
    stations = _stations(model)
    rng = np.random.default_rng(42)
    obs, _ = od.simulate_observations(model, X0_TRUTH, stations, TIMES, SIGMA, rng, noisy=True)
    x0_bar = X0_TRUTH + rng.normal(0, np.array([1.0, 1.0, 1.0, 1e-3, 1e-3, 1e-3]))
    result = od.batch_least_squares(
        model,
        stations,
        obs,
        x0_bar,
        SIGMA,
        apriori_cov=np.diag(np.array([1.0, 1.0, 1.0, 1e-3, 1e-3, 1e-3]) ** 2),
    )
    assert result.converged
    assert 0.5 < result.residual_rms[-1] < 2.0


@pytest.mark.slow
def test_nees_is_statistically_consistent():
    result = od.nees_study(
        _model,
        _stations,
        X0_TRUTH,
        TIMES,
        SIGMA,
        apriori_sigma=np.array([1.0, 1.0, 1.0, 1e-3, 1e-3, 1e-3]),
        trials=30,
        seed=20260115,
    )
    assert result["convergence_rate"] == 1.0
    assert result["consistent"], f"mean NEES {result['mean_nees']:.2f} outside {result['nees_95_interval']}"
