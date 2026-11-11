"""Configured trajectory propagation with diagnostics and an exact configuration record.

A propagation is described entirely by a JSON-serialisable configuration (see
``DEFAULTS`` and docs/ORRERY.md, section 6). ``propagate`` builds the force
model, integrates to every output time, applies impulsive manoeuvres as
instantaneous velocity changes at their epochs, and returns a
:class:`Trajectory` whose ``record()`` restates the configuration, constants,
solver identity, tolerances and step statistics so a result can be checked or
re-run without the code that produced it.

Diagnostics: specific two-body energy v^2/2 - mu/r, the force model's own
energy integral when every term is conservative and time-independent (point
mass and inertial-pole J2), and the angular-momentum vector. Relative drift is
reported against the initial value.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from . import ENGINE_VERSION, PROTOCOL
from .constants import DE421_GM, GMAT_CONSTANTS, GMAT_EARTH_MU, GMAT_MOON_MU, GMAT_SUN_MU
from .eop import EopTable
from .ephemeris import Ephemeris, FrameTie
from .forces import ForceModel, PointMass, SphericalHarmonics, ThirdBody, ZonalJ2, load_gravity_field
from .frames import EarthOrientation
from .integrators import integrate
from .timescales import Epoch

DEFAULTS = {
    "epoch_utc": "2026-01-15T00:00:00",
    "initial_state": None,
    "duration_s": 86400.0,
    "output_step_s": 300.0,
    "output_times_s": None,
    "forces": {
        "constants": "gmat",
        "earth": {"model": "point-mass"},
        "third_bodies": [],
    },
    "earth_orientation": {"eop": "eop_c04_2026", "nutation_corrections": False, "nutation_interval_s": 0.0},
    "ephemeris": "de421_2026",
    "frame_tie": "gmat-icrf-table",
    "integrator": {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12, "error_norm": "mixed"},
    "stm": False,
    "maneuvers": [],
}

_MU = {
    "gmat": {"earth": GMAT_EARTH_MU, "moon": GMAT_MOON_MU, "sun": GMAT_SUN_MU},
    "de421": {"earth": DE421_GM["earth"], "moon": DE421_GM["moon"], "sun": DE421_GM["sun"]},
}


def merge(defaults: dict, overrides: dict) -> dict:
    out = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def output_times(config: dict) -> np.ndarray:
    if config.get("output_times_s"):
        return np.asarray(config["output_times_s"], dtype=float)
    duration, stepsize = float(config["duration_s"]), float(config["output_step_s"])
    n = int(round(duration / stepsize))
    if abs(n * stepsize - duration) > 1e-9 * max(1.0, duration):
        raise ValueError("duration_s must be a whole number of output steps")
    return np.arange(n + 1) * stepsize


def build_force_model(config: dict) -> ForceModel:
    forces = config["forces"]
    family = forces.get("constants", "gmat")
    if family not in _MU:
        raise ValueError(f"unknown constants family {family!r}")
    mu = _MU[family]
    epoch = Epoch.from_iso("UTC", config["epoch_utc"]).to("TT")
    earth = forces.get("earth", {"model": "point-mass"})
    model = earth.get("model", "point-mass")
    needs_frame = False
    terms: list = []
    if model == "point-mass":
        terms.append(PointMass(earth.get("mu", mu["earth"])))
    elif model == "j2":
        mu_e = earth.get("mu", mu["earth"])
        terms.append(PointMass(mu_e))
        pole = earth.get("pole", "earth-fixed")
        terms.append(
            ZonalJ2(
                mu_e,
                earth.get("radius", GMAT_CONSTANTS["earth_radius_km"]),
                earth.get("j2", GMAT_CONSTANTS["earth_j2"]),
                pole,
            )
        )
        needs_frame = pole == "earth-fixed"
    elif model == "harmonics":
        field_data = load_gravity_field(earth.get("field", "jgm3_8x8"))
        terms.append(
            SphericalHarmonics(
                field_data["mu"],
                field_data["radius"],
                field_data["C"],
                field_data["S"],
                int(earth["degree"]),
                int(earth["order"]),
                field_name=field_data["name"],
            )
        )
        needs_frame = True
    else:
        raise ValueError(f"unknown Earth gravity model {model!r}")
    third = forces.get("third_bodies", [])
    if third:
        eph = (
            Ephemeris.load(config["ephemeris"])
            if isinstance(config["ephemeris"], str)
            else config["ephemeris"]
        )
        tie = FrameTie(config.get("frame_tie", "gmat-icrf-table"))
        for body in third:
            terms.append(ThirdBody(body, mu[body], eph, frame_tie=tie))
    orientation = None
    if needs_frame:
        eo = config["earth_orientation"]
        eop = EopTable.load(eo["eop"]) if isinstance(eo["eop"], str) else eo["eop"]
        orientation = EarthOrientation(
            eop,
            nutation_corrections=bool(eo.get("nutation_corrections", False)),
            nutation_interval_s=float(eo.get("nutation_interval_s", 0.0)),
        )
    return ForceModel(terms, epoch, orientation)


@dataclass
class Trajectory:
    times: np.ndarray
    states: np.ndarray
    config: dict
    force_model: dict
    integrator: dict
    stats: dict
    diagnostics: dict
    stm: np.ndarray | None = None
    warnings: list[str] = field(default_factory=list)

    def record(self) -> dict:
        return {
            "protocol": PROTOCOL,
            "engine_version": ENGINE_VERSION,
            "configuration": self.config,
            "force_model": self.force_model,
            "integrator": self.integrator,
            "step_statistics": self.stats,
            "diagnostics": self.diagnostics,
            "warnings": self.warnings,
            "units": {"time": "s since epoch (TT)", "position": "km", "velocity": "km/s"},
        }


def diagnostics(model: ForceModel, times: np.ndarray, states: np.ndarray, mu: float) -> dict:
    r = states[:, :3]
    v = states[:, 3:6]
    rm = np.linalg.norm(r, axis=1)
    two_body = 0.5 * np.sum(v * v, axis=1) - mu / rm
    h = np.cross(r, v)
    hm = np.linalg.norm(h, axis=1)
    energies = [model.energy(t, s) for t, s in zip(times, states)]
    integral = None if any(e is None for e in energies) else np.asarray(energies, dtype=float)
    out = {
        "two_body_energy_km2_s2": two_body.tolist(),
        "angular_momentum_km2_s": hm.tolist(),
        "angular_momentum_z_km2_s": h[:, 2].tolist(),
        "relative_two_body_energy_drift": float(np.max(np.abs((two_body - two_body[0]) / two_body[0]))),
        "relative_angular_momentum_drift": float(np.max(np.abs((hm - hm[0]) / hm[0]))),
        "energy_integral_available": integral is not None,
    }
    if integral is not None:
        out["energy_integral_km2_s2"] = integral.tolist()
        out["relative_energy_integral_drift"] = float(np.max(np.abs((integral - integral[0]) / integral[0])))
        out["relative_hz_drift"] = float(np.max(np.abs((h[:, 2] - h[0, 2]) / h[0, 2]))) if h[0, 2] else None
    return out


def propagate(overrides: dict, *, keep_steps: bool = False) -> Trajectory:
    config = merge(DEFAULTS, overrides)
    if config["initial_state"] is None or len(config["initial_state"]) != 6:
        raise ValueError("initial_state must be [x, y, z, vx, vy, vz] in km and km/s (MJ2000Eq)")
    times = output_times(config)
    model = build_force_model(config)
    integ = dict(config["integrator"])
    method = integ.pop("method")
    use_stm = bool(config.get("stm"))
    if use_stm and method in ("verlet", "yoshida4"):
        raise ValueError("STM propagation needs a general (non-symplectic) integrator")
    y = np.asarray(config["initial_state"], dtype=float)
    if use_stm:
        y = np.concatenate([y, np.eye(6).ravel()])
    rhs = model.rhs_stm if use_stm else model.rhs
    burns = sorted(config.get("maneuvers", []), key=lambda b: b["time_s"])
    for b in burns:
        if not (times[0] < b["time_s"] <= times[-1]):
            raise ValueError("manoeuvre times must fall inside the propagation span")
    t_now, segments, warnings = 0.0, [], []
    states = np.empty((times.size, y.size))
    accepted = rejected = nfev = 0
    step_sizes: list[float] = []
    step_times: list[float] = []
    cursor = 0
    if times[0] == 0.0:
        states[0] = y
        cursor = 1
    for stop in [b["time_s"] for b in burns] + [times[-1] + 1.0]:
        seg = [t for t in times[cursor:] if t <= stop and t <= times[-1]]
        targets = sorted(set(seg + ([stop] if stop <= times[-1] else [])))
        if targets:
            res = integrate(
                rhs, t_now, y, np.asarray(targets), method=method, accel=model.acceleration, **integ
            )
            accepted += res.accepted
            rejected += res.rejected
            nfev += res.nfev
            step_sizes += res.step_sizes
            step_times += res.step_times
            warnings += res.warnings
            for t, s in zip(res.times, res.states):
                if cursor < times.size and abs(t - times[cursor]) < 1e-9:
                    states[cursor] = s
                    cursor += 1
            y = res.states[-1].copy()
            t_now = float(res.times[-1])
            segments.append({"from_s": float(targets[0]), "to_s": float(targets[-1])})
        if stop <= times[-1]:  # an output at a burn epoch is the pre-burn state
            burn = next(b for b in burns if b["time_s"] == stop)
            y[3:6] += np.asarray(burn["dv_km_s"], dtype=float)
    if cursor != times.size:
        raise RuntimeError("internal error: not every output time was produced")
    stats = {
        "accepted_steps": accepted,
        "rejected_steps": rejected,
        "function_evaluations": nfev,
        "force_model_evaluations": model.evaluations,
        "min_step_s": float(np.min(np.abs(step_sizes))) if step_sizes else None,
        "max_step_s": float(np.max(np.abs(step_sizes))) if step_sizes else None,
        "median_step_s": float(np.median(np.abs(step_sizes))) if step_sizes else None,
    }
    if keep_steps:
        stats["step_times_s"] = step_times
        stats["step_sizes_s"] = step_sizes
    orbit = states[:, :6]
    mu = model.terms[0].mu
    integrator_record = {
        "method": method,
        **integ,
        "error_controlled_components": "orbit state (6); STM integrated but not error-controlled"
        if use_stm
        else "orbit state (6)",
        "output_epochs": "hit exactly by step shortening",
    }
    return Trajectory(
        times=times,
        states=orbit,
        config=config,
        force_model=model.describe(),
        integrator=integrator_record,
        stats=stats,
        diagnostics=diagnostics(model, times, orbit, mu),
        stm=states[:, 6:42].reshape(-1, 6, 6) if use_stm else None,
        warnings=warnings,
    )


def position_velocity_errors(states: np.ndarray, reference: np.ndarray) -> dict:
    """Position (m) and velocity (m/s) error norms against a reference trajectory."""

    dr = np.linalg.norm(states[:, :3] - reference[:, :3], axis=1) * 1000.0
    dv = np.linalg.norm(states[:, 3:6] - reference[:, 3:6], axis=1) * 1000.0
    return {
        "position_error_m": dr.tolist(),
        "velocity_error_m_s": dv.tolist(),
        "max_position_error_m": float(np.max(dr)),
        "max_velocity_error_m_s": float(np.max(dv)),
        "final_position_error_m": float(dr[-1]),
        "final_velocity_error_m_s": float(dv[-1]),
        "rms_position_error_m": float(math.sqrt(np.mean(dr * dr))),
    }


def rtn_errors(states: np.ndarray, reference: np.ndarray) -> dict:
    """Radial, transverse (along-track) and normal position differences (m) in the reference RTN frame."""

    r = reference[:, :3]
    v = reference[:, 3:6]
    rhat = r / np.linalg.norm(r, axis=1)[:, None]
    nhat = np.cross(r, v)
    nhat /= np.linalg.norm(nhat, axis=1)[:, None]
    that = np.cross(nhat, rhat)
    d = (states[:, :3] - r) * 1000.0
    return {
        "radial_m": np.sum(d * rhat, axis=1).tolist(),
        "transverse_m": np.sum(d * that, axis=1).tolist(),
        "normal_m": np.sum(d * nhat, axis=1).tolist(),
    }
