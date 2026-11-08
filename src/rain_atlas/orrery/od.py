"""Orbit determination from synthetic tracking: batch least squares and NEES consistency.

Observations are generated from a truth trajectory and a ground station, then an
estimator recovers the epoch state from a perturbed a-priori, using only the
observations and the dynamics (no knowledge of the truth state). This is a
closed identical-twin experiment: the dynamics model used to generate and to
estimate are the same, so a correct estimator must recover the truth to the
noise floor, and its reported covariance must be statistically consistent.

Measurement model (Vallado 2013, chapter 4). A station at ECEF position
``r_site`` (from geodetic latitude, longitude, height) has inertial position
``R = M(t)^T r_site`` with ``M`` the MJ2000Eq->EarthFixed rotation. For a
spacecraft state (r, v):

    rho_vec = r - R,         range     = |rho_vec|,
    rho_dot = (rho_vec . (v - omega x R-in-ECI... )) ... handled via the frame,
    range_rate = rho_vec . (v - V_site) / range,

where V_site is the inertial velocity of the station (Earth rotation). Partials
d range / d r and d range_rate / d[r, v] are analytic; the mapping from epoch
state to observation epoch uses the state-transition matrix from the force
model, so H_i = (d obs / d state_i) Phi(t_i, t0).

Batch least squares (normal equations, Vallado algorithm 69):

    dx = (sum_i H_i^T W_i H_i + P0^-1)^-1 (sum_i H_i^T W_i dy_i + P0^-1 (x0_bar - x0)),

iterated with the state re-propagated each pass until ||dx|| stops improving.
W_i = diag(1/sigma^2). The returned covariance is the inverse information matrix.

NEES check: over M Monte-Carlo truth/observation realisations, the normalized
estimation error squared ``e^T P^-1 e`` (e = estimate - truth, 6 DOF) should
average near 6; the fraction inside the chi-square 95% interval is reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .forces import ForceModel
from .frames import EarthOrientation, geodetic_to_ecef
from .integrators import integrate


@dataclass
class GroundStation:
    name: str
    lat_rad: float
    lon_rad: float
    height_km: float
    radius_km: float
    flattening: float
    orientation: EarthOrientation
    min_elevation_rad: float = np.radians(5.0)

    def ecef(self) -> np.ndarray:
        return geodetic_to_ecef(self.lat_rad, self.lon_rad, self.height_km, self.radius_km, self.flattening)

    def inertial(self, model: ForceModel, t: float) -> tuple[np.ndarray, np.ndarray]:
        rot = self.orientation.at(model.epoch.plus_seconds(t))
        r_ecef = self.ecef()
        r_eci = rot.matrix.T @ r_ecef
        omega = np.array([0.0, 0.0, rot.omega_e])
        v_eci = np.cross(omega, r_eci)
        return r_eci, v_eci

    def observe(self, model: ForceModel, t: float, state: np.ndarray) -> dict | None:
        r_site, v_site = self.inertial(model, t)
        rho = state[:3] - r_site
        rng = float(np.linalg.norm(rho))
        up = r_site / np.linalg.norm(r_site)
        elevation = np.arcsin(float(rho @ up) / rng)
        if elevation < self.min_elevation_rad:
            return None
        rrate = float(rho @ (state[3:6] - v_site)) / rng
        return {"range_km": rng, "range_rate_km_s": rrate, "elevation_rad": elevation}

    def partials(self, model: ForceModel, t: float, state: np.ndarray) -> np.ndarray:
        r_site, v_site = self.inertial(model, t)
        rho = state[:3] - r_site
        drho = state[3:6] - v_site
        rng = float(np.linalg.norm(rho))
        u = rho / rng
        h = np.zeros((2, 6))
        h[0, :3] = u
        h[1, :3] = drho / rng - (rho @ drho) * rho / rng**3
        h[1, 3:6] = u
        return h


@dataclass
class Observation:
    t: float
    station: int
    values: np.ndarray  # [range, range_rate]


def simulate_observations(
    model: ForceModel,
    x0: np.ndarray,
    stations: list[GroundStation],
    times: np.ndarray,
    sigma: np.ndarray,
    rng: np.random.Generator | None = None,
    noisy: bool = True,
) -> tuple[list[Observation], np.ndarray]:
    traj = integrate(model.rhs, 0.0, x0, times, method="rkf78", rtol=1e-12, atol=1e-12)
    obs: list[Observation] = []
    for t, state in zip(traj.times, traj.states):
        for s, station in enumerate(stations):
            meas = station.observe(model, float(t), state)
            if meas is None:
                continue
            values = np.array([meas["range_km"], meas["range_rate_km_s"]])
            if noisy and rng is not None:
                values = values + rng.normal(0.0, sigma)
            obs.append(Observation(float(t), s, values))
    return obs, traj.states


@dataclass
class BatchResult:
    estimate: np.ndarray
    covariance: np.ndarray
    iterations: int
    residual_rms: list[float]
    converged: bool
    observations_used: int
    warnings: list[str] = field(default_factory=list)


def batch_least_squares(
    model: ForceModel,
    stations: list[GroundStation],
    observations: list[Observation],
    x0_bar: np.ndarray,
    sigma: np.ndarray,
    apriori_cov: np.ndarray | None = None,
    max_iter: int = 15,
    tol: float = 1e-9,
) -> BatchResult:
    weight = 1.0 / sigma**2
    times = np.array(sorted({o.t for o in observations}))
    if times[0] != 0.0:
        times = np.concatenate([[0.0], times])
    x0 = x0_bar.astype(float).copy()
    p0_inv = np.linalg.inv(apriori_cov) if apriori_cov is not None else np.zeros((6, 6))
    residual_rms, converged = [], False
    info = np.zeros((6, 6))
    for iteration in range(max_iter):
        y0 = np.concatenate([x0, np.eye(6).ravel()])
        traj = integrate(model.rhs_stm, 0.0, y0, times, method="rkf78", rtol=1e-12, atol=1e-12)
        states = {float(t): traj.states[i] for i, t in enumerate(times)}
        info = p0_inv.copy()
        normal_rhs = p0_inv @ (x0_bar - x0)
        sq, count = 0.0, 0
        for o in observations:
            full = states[o.t]
            state, phi = full[:6], full[6:42].reshape(6, 6)
            predicted = stations[o.station].observe(model, o.t, state)
            if predicted is None:
                continue
            dy = o.values - np.array([predicted["range_km"], predicted["range_rate_km_s"]])
            h = stations[o.station].partials(model, o.t, state) @ phi
            w = np.diag(weight)
            info += h.T @ w @ h
            normal_rhs += h.T @ w @ dy
            sq += float(dy @ (weight * dy))
            count += 1
        dx = np.linalg.solve(info, normal_rhs)
        x0 = x0 + dx
        residual_rms.append(float(np.sqrt(sq / max(count, 1))))
        if np.linalg.norm(dx[:3]) < tol:
            converged = True
            break
    return BatchResult(x0, np.linalg.inv(info), iteration + 1, residual_rms, converged, len(observations))


def nees_study(
    model_factory,
    stations_factory,
    x0_truth: np.ndarray,
    times: np.ndarray,
    sigma: np.ndarray,
    apriori_sigma: np.ndarray,
    trials: int,
    seed: int = 20260115,
) -> dict:
    """Monte-Carlo NEES: mean normalized error over ``trials`` realisations."""

    master = np.random.default_rng(seed)
    nees, pos_err, converged = [], [], 0
    for _ in range(trials):
        rng = np.random.default_rng(master.integers(2**63))
        model = model_factory()
        stations = stations_factory(model)
        obs, _ = simulate_observations(model, x0_truth, stations, times, sigma, rng, noisy=True)
        x0_bar = x0_truth + rng.normal(0.0, apriori_sigma)
        p0 = np.diag(apriori_sigma**2)
        result = batch_least_squares(model, stations, obs, x0_bar, sigma, apriori_cov=p0)
        converged += int(result.converged)
        err = result.estimate - x0_truth
        nees.append(float(err @ np.linalg.solve(result.covariance, err)))
        pos_err.append(float(np.linalg.norm(err[:3]) * 1000.0))
    nees = np.array(nees)
    # chi-square(6) 95% two-sided interval on the *mean* NEES over `trials` samples.
    from scipy.stats import chi2  # noqa: PLC0415

    lo = chi2.ppf(0.025, 6 * trials) / trials
    hi = chi2.ppf(0.975, 6 * trials) / trials
    return {
        "trials": trials,
        "mean_nees": float(np.mean(nees)),
        "expected_nees": 6.0,
        "nees_95_interval": [lo, hi],
        "consistent": bool(lo <= np.mean(nees) <= hi),
        "median_position_error_m": float(np.median(pos_err)),
        "convergence_rate": converged / trials,
    }
