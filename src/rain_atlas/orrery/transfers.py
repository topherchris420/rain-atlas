"""Civilian orbital transfers: analytic Hohmann transfers and a simple lunar-transfer designer.

Hohmann transfer between coplanar circular orbits (Vallado 2013, algorithm 36):

    a_t = (r1 + r2)/2,  dv1 = sqrt(mu/r1) (sqrt(2 r2/(r1 + r2)) - 1),
    dv2 = sqrt(mu/r2) (1 - sqrt(2 r1/(r1 + r2))),  t = pi sqrt(a_t^3/mu).

Lunar transfer (:func:`design_lunar_transfer`). A deliberately simple,
documented construction, not a mission design tool:

1. Choose a departure epoch and a parking-orbit radius r_p.
2. Iterate the arrival time t_a = half the period of the ellipse with perigee
   r_p and apogee |r_moon(t_a)| (Moon from the ephemeris, MJ2000Eq after the
   frame tie), so apogee falls where the Moon will be.
3. Put perigee opposite the Moon's arrival direction, in the plane of the
   Moon's arrival position and velocity, with velocity along h_moon x r_p_hat.
4. Solve, by bisection on the perigee speed in the full force model, for a
   chosen closest-approach distance to the Moon on the leading or trailing side.

The resulting state is frozen in ``scenarios.py`` with its derivation
recorded; the GMAT and ORRERY comparisons use the frozen numbers.
"""

from __future__ import annotations

import math

import numpy as np

from .ephemeris import Ephemeris, FrameTie, et_from_epoch
from .timescales import Epoch


def hohmann(r1: float, r2: float, mu: float) -> dict:
    if r1 <= 0 or r2 <= 0:
        raise ValueError("radii must be positive")
    at = 0.5 * (r1 + r2)
    dv1 = math.sqrt(mu / r1) * (math.sqrt(2.0 * r2 / (r1 + r2)) - 1.0)
    dv2 = math.sqrt(mu / r2) * (1.0 - math.sqrt(2.0 * r1 / (r1 + r2)))
    return {
        "transfer_sma_km": at,
        "transfer_eccentricity": abs(r2 - r1) / (r1 + r2),
        "dv1_km_s": dv1,
        "dv2_km_s": dv2,
        "total_dv_km_s": abs(dv1) + abs(dv2),
        "time_of_flight_s": math.pi * math.sqrt(at**3 / mu),
    }


def hohmann_maneuvers(r_vec, v_vec, r2: float, mu: float) -> dict:
    """Burns for a Hohmann transfer starting from a circular state (r_vec, v_vec)."""

    r_vec = np.asarray(r_vec, dtype=float)
    v_vec = np.asarray(v_vec, dtype=float)
    r1 = float(np.linalg.norm(r_vec))
    plan = hohmann(r1, r2, mu)
    vhat = v_vec / np.linalg.norm(v_vec)
    # At apoapsis the velocity is antiparallel to the departure velocity (half an orbit later).
    return plan | {
        "maneuvers": [
            {"time_s": 0.0, "dv_km_s": (plan["dv1_km_s"] * vhat).tolist()},
            {"time_s": plan["time_of_flight_s"], "dv_km_s": (-plan["dv2_km_s"] * vhat).tolist()},
        ]
    }


def moon_state(eph: Ephemeris, tie: FrameTie, tt: Epoch) -> tuple[np.ndarray, np.ndarray]:
    et = et_from_epoch(tt.to("TDB"))
    r, v = eph.state("moon", "earth", et)
    a1 = tt.gmat_modjulian() - (32.184 - 0.0343817) / 86400.0
    m = tie.matrix(a1)
    return m @ r, m @ v


def lunar_transfer_guess(epoch_utc: str, r_park: float, mu: float, eph: Ephemeris, tie: FrameTie) -> dict:
    tt0 = Epoch.from_iso("UTC", epoch_utc).to("TT")
    tof = 5.0 * 86400.0
    for _ in range(50):
        rm, vm = moon_state(eph, tie, tt0.plus_seconds(tof))
        ra = float(np.linalg.norm(rm))
        a = 0.5 * (r_park + ra)
        new = math.pi * math.sqrt(a**3 / mu)
        if abs(new - tof) < 1e-6:
            break
        tof = new
    rm, vm = moon_state(eph, tie, tt0.plus_seconds(tof))
    hhat = np.cross(rm, vm)
    hhat /= np.linalg.norm(hhat)
    phat = -rm / np.linalg.norm(rm)
    vhat = np.cross(hhat, phat)
    ra = float(np.linalg.norm(rm))
    vp = math.sqrt(2.0 * mu * ra / (r_park * (r_park + ra)))
    return {"perigee_hat": phat, "velocity_hat": vhat, "vp_two_body": vp, "tof_two_body_s": tof, "ra_km": ra}


def design_lunar_transfer(
    epoch_utc: str,
    r_park: float,
    target_closest_km: float,
    propagate_fn,
    mu: float,
    eph: Ephemeris,
    tie: FrameTie,
    side: str = "low",
    duration_s: float = 6.0 * 86400.0,
) -> dict:
    """Bisection on perigee speed for a closest lunar approach of ``target_closest_km``.

    ``propagate_fn(state, duration_s) -> (times, states)`` must propagate in the
    intended force model; ``side`` picks the root below ("low") or above
    ("high") the two-body speed.
    """

    guess = lunar_transfer_guess(epoch_utc, r_park, mu, eph, tie)
    tt0 = Epoch.from_iso("UTC", epoch_utc).to("TT")
    phat, vhat = guess["perigee_hat"], guess["velocity_hat"]

    def closest(vp: float) -> tuple[float, float]:
        state = np.concatenate([phat * r_park, vhat * vp])
        times, states = propagate_fn(state, duration_s)
        dists = []
        for t, s in zip(times, states):
            rm, _ = moon_state(eph, tie, tt0.plus_seconds(float(t)))
            dists.append(float(np.linalg.norm(s[:3] - rm)))
        i = int(np.argmin(dists))
        return dists[i], float(times[i])

    vp0 = guess["vp_two_body"]
    scan = [vp0 + d for d in np.linspace(-0.02, 0.02, 21)]
    values = [closest(v)[0] for v in scan]
    k = int(np.argmin(values))
    if side == "low":
        lo, hi = scan[0], scan[k]
        f_lo, f_hi = values[0] - target_closest_km, values[k] - target_closest_km
    else:
        lo, hi = scan[k], scan[-1]
        f_lo, f_hi = values[k] - target_closest_km, values[-1] - target_closest_km
    if f_lo * f_hi > 0:
        raise RuntimeError("target closest approach not bracketed by the speed scan")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f_mid = closest(mid)[0] - target_closest_km
        if f_mid == 0 or hi - lo < 1e-12:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    vp = 0.5 * (lo + hi)
    dmin, tmin = closest(vp)
    return {
        "initial_state": np.concatenate([phat * r_park, vhat * vp]).tolist(),
        "perigee_speed_km_s": vp,
        "two_body_perigee_speed_km_s": vp0,
        "two_body_time_of_flight_s": guess["tof_two_body_s"],
        "closest_approach_km": dmin,
        "closest_approach_time_s": tmin,
        "side": side,
        "scan": {"speeds_km_s": scan, "closest_km": values},
    }
