"""Stable, JSON-in/JSON-out surface used by the astrodynamics skills.

Each function takes a plain ``dict`` of inputs and returns a plain ``dict`` of
JSON-serialisable outputs, so a skill ``run.py`` is a thin wrapper. Keeping the
skills' logic here (rather than in each ``run.py``) means the executor sandbox,
the experiment and the tests all exercise the same code paths.
"""

from __future__ import annotations

import math

import numpy as np

from .constants import GMAT_CONSTANTS
from .covariance import covariance_study
from .eop import EopTable
from .ephemeris import Ephemeris, et_from_epoch
from .forces import ForceModel, PointMass, ZonalJ2
from .frames import EarthOrientation
from .kepler import elements_to_state, kepler_trajectory, orbital_period, state_to_elements
from .nbody import de421_nbody_gm, figure_eight_system, integrate_system, solar_system_from_ephemeris
from .od import GroundStation, batch_least_squares, simulate_observations
from .propagate import position_velocity_errors, propagate, rtn_errors
from .timescales import Epoch

_C = GMAT_CONSTANTS


def _elements_state(el: dict) -> list[float]:
    r, v = elements_to_state(
        el["sma_km"],
        el["ecc"],
        math.radians(el["inc_deg"]),
        math.radians(el.get("raan_deg", 0.0)),
        math.radians(el.get("argp_deg", 0.0)),
        math.radians(el.get("ta_deg", 0.0)),
        _C["earth_mu_km3_s2"],
    )
    return list(r) + list(v)


def propagate_orbit(inputs: dict) -> dict:
    """Propagate an orbit and report the final state and conservation diagnostics."""

    config = dict(inputs.get("config") or {})
    if "elements" in inputs:
        config["initial_state"] = _elements_state(inputs["elements"])
    traj = propagate(config)
    out = {
        "final_state_km_kms": traj.states[-1].tolist(),
        "num_output_points": int(traj.times.size),
        "relative_two_body_energy_drift": traj.diagnostics["relative_two_body_energy_drift"],
        "relative_angular_momentum_drift": traj.diagnostics["relative_angular_momentum_drift"],
        "accepted_steps": traj.stats["accepted_steps"],
        "method": traj.integrator["method"],
    }
    if inputs.get("compare_analytic"):
        x0 = np.asarray(config["initial_state"])
        ref = kepler_trajectory(x0[:3], x0[3:6], traj.times, _C["earth_mu_km3_s2"])
        out["analytic_max_position_error_m"] = position_velocity_errors(traj.states, ref)[
            "max_position_error_m"
        ]
    return out


def kepler_reference(inputs: dict) -> dict:
    """Closed-form two-body state after ``dt`` and the classical elements of the result."""

    mu = float(inputs.get("mu_km3_s2", _C["earth_mu_km3_s2"]))
    if "elements" in inputs:
        state = np.asarray(_elements_state(inputs["elements"]))
    else:
        state = np.asarray(inputs["state_km_kms"], dtype=float)
    dt = float(inputs["dt_s"])
    final = kepler_trajectory(state[:3], state[3:6], [dt], mu)[0]
    el = state_to_elements(final[:3], final[3:6], mu)
    return {
        "final_state_km_kms": final.tolist(),
        "sma_km": el["a"],
        "eccentricity": el["e"],
        "inclination_deg": math.degrees(el["i"]),
        "specific_energy_km2_s2": el["energy"],
        "angular_momentum_km2_s": el["h"],
        "period_s": orbital_period(el["a"], mu) if el["a"] > 0 else None,
    }


def compare_trajectories(inputs: dict) -> dict:
    """Position/velocity error statistics between a propagation and a reference trajectory.

    The reference is either an explicit ``reference_states`` array at the same
    output times, or ``self`` (identity check, which must give exactly zero).
    """

    config = dict(inputs["config"])
    traj = propagate(config)
    if inputs.get("reference") == "self":
        reference = traj.states
    else:
        reference = np.asarray(inputs["reference_states"], dtype=float)
    err = position_velocity_errors(traj.states, reference)
    rtn = rtn_errors(traj.states, reference)
    return {
        "max_position_error_m": err["max_position_error_m"],
        "final_position_error_m": err["final_position_error_m"],
        "max_velocity_error_m_s": err["max_velocity_error_m_s"],
        "rms_position_error_m": err["rms_position_error_m"],
        "final_rtn_m": [rtn["radial_m"][-1], rtn["transverse_m"][-1], rtn["normal_m"][-1]],
    }


def earth_orientation(inputs: dict) -> dict:
    """Rotate a state between MJ2000Eq and EarthFixed at an epoch with supplied EOP."""

    eop = EopTable.from_rows(inputs["eop_rows"], {"name": inputs.get("eop_name", "supplied")})
    eo = EarthOrientation(
        eop,
        nutation_corrections=bool(inputs.get("nutation_corrections", False)),
        nutation_interval_s=float(inputs.get("nutation_interval_s", 0.0)),
    )
    tt = Epoch.from_iso("UTC", inputs["epoch_utc"]).to("TT")
    rot = eo.at(tt)
    out = {"gmst_deg": math.degrees(rot.gmst) % 360.0}
    if inputs.get("direction", "fixed_to_inertial") == "fixed_to_inertial":
        r, v = rot.fixed_to_inertial(inputs["position_km"], inputs.get("velocity_km_s"))
    else:
        r, v = rot.inertial_to_fixed(inputs["position_km"], inputs.get("velocity_km_s"))
    out["position_km"] = list(r)
    out["velocity_km_s"] = list(v) if inputs.get("velocity_km_s") is not None else None
    return out


def _orientation() -> EarthOrientation:
    return EarthOrientation(EopTable.load("eop_c04_2026"))


def _two_body_or_j2_model(spec: dict) -> ForceModel:
    epoch = Epoch.from_iso("UTC", spec.get("epoch_utc", "2026-01-15T00:00:00"))
    mu = _C["earth_mu_km3_s2"]
    if spec.get("model", "j2") == "point-mass":
        return ForceModel([PointMass(mu)], epoch)
    eo = _orientation()
    return ForceModel(
        [PointMass(mu), ZonalJ2(mu, _C["earth_radius_km"], _C["earth_j2"], "earth-fixed")], epoch, eo
    )


def _stations(spec: list, model: ForceModel) -> list[GroundStation]:
    eo = model.orientation or _orientation()
    return [
        GroundStation(
            s["name"],
            math.radians(s["lat_deg"]),
            math.radians(s["lon_deg"]),
            float(s.get("height_km", 0.0)),
            _C["earth_radius_km"],
            _C["earth_flattening"],
            eo,
        )
        for s in spec
    ]


def simulate_tracking(inputs: dict) -> dict:
    """Range and range-rate of an orbit from ground stations at the requested times."""

    model = _two_body_or_j2_model(inputs)
    stations = _stations(inputs["stations"], model)
    x0 = np.asarray(inputs["initial_state_km_kms"], dtype=float)
    times = np.asarray(inputs["times_s"], dtype=float)
    sigma = np.array([0.0, 0.0])
    obs, _ = simulate_observations(model, x0, stations, times, sigma, noisy=False)
    return {
        "num_observations": len(obs),
        "first_range_km": float(obs[0].values[0]) if obs else None,
        "first_range_rate_km_s": float(obs[0].values[1]) if obs else None,
        "observations": [
            {
                "t_s": o.t,
                "station": stations[o.station].name,
                "range_km": o.values[0],
                "range_rate_km_s": o.values[1],
            }
            for o in obs
        ],
    }


def station_inertial_position(
    lat_deg: float, lon_deg: float, height_km: float, epoch_utc: str
) -> list[float]:
    """Inertial (MJ2000Eq) position of a ground station, for constructing overhead-geometry inputs."""

    model = ForceModel([PointMass(_C["earth_mu_km3_s2"])], Epoch.from_iso("UTC", epoch_utc), _orientation())
    station = GroundStation(
        "s",
        math.radians(lat_deg),
        math.radians(lon_deg),
        height_km,
        _C["earth_radius_km"],
        _C["earth_flattening"],
        model.orientation,
    )
    return list(station.inertial(model, 0.0)[0])


def determine_orbit(inputs: dict) -> dict:
    """Batch least-squares OD on synthetic tracking; reports recovery error."""

    model = _two_body_or_j2_model(inputs)
    stations = _stations(inputs["stations"], model)
    x0_truth = np.asarray(inputs["truth_state_km_kms"], dtype=float)
    times = np.asarray(inputs["times_s"], dtype=float)
    sigma = np.asarray(inputs.get("sigma", [0.02, 2e-5]), dtype=float)
    noisy = bool(inputs.get("noisy", False))
    rng = np.random.default_rng(int(inputs.get("seed", 20260115)))
    obs, _ = simulate_observations(model, x0_truth, stations, times, sigma, rng, noisy=noisy)
    offset = np.asarray(inputs.get("apriori_offset", [1.0, -1.0, 0.5, 1e-3, -1e-3, 5e-4]), dtype=float)
    apriori_sigma = np.asarray(inputs.get("apriori_sigma", [10.0, 10.0, 10.0, 1e-2, 1e-2, 1e-2]), dtype=float)
    result = batch_least_squares(
        model, stations, obs, x0_truth + offset, sigma, apriori_cov=np.diag(apriori_sigma**2)
    )
    return {
        "converged": result.converged,
        "iterations": result.iterations,
        "observations_used": result.observations_used,
        "position_error_m": float(np.linalg.norm(result.estimate[:3] - x0_truth[:3]) * 1000.0),
        "velocity_error_m_s": float(np.linalg.norm(result.estimate[3:6] - x0_truth[3:6]) * 1000.0),
        "final_residual_rms": result.residual_rms[-1],
    }


def covariance_propagation(inputs: dict) -> dict:
    """Propagate a covariance via the STM and compare to a Kepler Monte-Carlo cloud."""

    mu = float(inputs.get("mu_km3_s2", _C["earth_mu_km3_s2"]))
    if "elements" in inputs:
        x0 = np.asarray(_elements_state(inputs["elements"]))
    else:
        x0 = np.asarray(inputs["state_km_kms"], dtype=float)
    p0 = np.diag(np.asarray(inputs["sigma0"], dtype=float) ** 2)
    out = covariance_study(
        x0,
        p0,
        float(inputs["dt_s"]),
        mu,
        model=None,
        samples=int(inputs.get("samples", 2000)),
        seed=int(inputs.get("seed", 20260115)),
    )
    return {
        "mean_offset_m": out["mean_offset_m"],
        "position_block_rel_diff": out["position_block_rel_diff"],
        "velocity_block_rel_diff": out["velocity_block_rel_diff"],
        "chi2_95_inside_fraction": out["chi2_95_inside_fraction"],
        "position_ellipsoid_volume_ratio": out["position_ellipsoid_volume_ratio"],
    }


def nbody_integration(inputs: dict) -> dict:
    """Integrate a self-gravitating N-body system (figure-eight or a DE421 subset)."""

    system_name = inputs.get("system", "figure-eight")
    if system_name == "figure-eight":
        from .nbody import FIGURE_EIGHT  # noqa: PLC0415

        system, y0 = figure_eight_system()
        periods = float(inputs.get("periods", 1))
        times = [periods * FIGURE_EIGHT["period"]]
        res = integrate_system(system, y0, times, rtol=1e-13, atol=1e-13)
        return {
            "return_error": float(np.linalg.norm(res["states"][-1] - y0))
            if abs(periods - round(periods)) < 1e-9
            else None,
            "relative_energy_drift": res["relative_energy_drift"],
            "angular_momentum_drift": res["angular_momentum_drift"],
            "barycentre_drift": res["barycentre_drift"],
        }
    if system_name == "de421":
        from .constants import DE421_GM  # noqa: PLC0415

        eph = Ephemeris.load(inputs.get("ephemeris", "de421_2026"))
        et0 = et_from_epoch(Epoch.from_iso("UTC", inputs.get("epoch_utc", "2026-01-15T00:00:00")).to("TDB"))
        bodies = inputs["bodies"]
        gm = de421_nbody_gm(DE421_GM)
        system, y0 = solar_system_from_ephemeris(eph, bodies, gm, et0, "ssb")
        span = float(inputs["duration_s"])
        res = integrate_system(system, y0, [span], rtol=1e-13, atol=1e-13)
        final = res["states"][-1].reshape(2, len(bodies), 3)
        out = {"relative_energy_drift": res["relative_energy_drift"]}
        if "earth" in bodies and "moon" in bodies:
            em = final[0][bodies.index("moon")] - final[0][bodies.index("earth")]
            em_ref = eph.state("moon", "earth", et0 + span)[0]
            out["earth_moon_vs_de421_km"] = float(np.linalg.norm(em - em_ref))
        return out
    raise ValueError(f"unknown N-body system {system_name!r}")


DISPATCH = {
    "orbit-propagation": propagate_orbit,
    "kepler-reference": kepler_reference,
    "trajectory-comparison": compare_trajectories,
    "earth-orientation": earth_orientation,
    "tracking-simulation": simulate_tracking,
    "orbit-determination": determine_orbit,
    "covariance-propagation": covariance_propagation,
    "nbody-integration": nbody_integration,
}
