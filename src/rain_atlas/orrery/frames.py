"""Inertial and Earth-fixed reference frames (IAU-1976/FK5 reduction).

Frames
------
``MJ2000Eq`` - the Earth mean equator and equinox of J2000.0 realised by the
IAU-1976/FK5 theory. ORRERY treats the axes of the JPL DE421 ephemeris (ICRF)
as MJ2000Eq without the 23 mas frame-bias rotation, as GMAT does for its
default inertial system (GMAT Math Spec, "Transformation from ICRF to
MJ2000Eq"). The bias would move the Moon by ~43 m; it is listed as a deviation.

``EarthFixed`` - ITRF realised by FK5 reduction (Vallado 2013, section 3.7;
GMAT Math Spec, "FK5 Reduction")::

    r_ITRF = PM . ST . N . P . r_MJ2000Eq

* ``P``  precession, IAU 1976 (Lieske 1977): P = R3(-z) R2(theta) R3(-zeta);
* ``N``  nutation, IAU 1980 106-term series: N = R1(-eps) R3(-dpsi) R1(eps_bar);
* ``ST`` sidereal rotation R3(theta_AST), theta_AST = GMST(IAU 1982, UT1) +
  equation of the equinoxes (with the 0.00264" and 0.000063" terms after
  JD_TT 2450449.5);
* ``PM`` polar motion R2(-x_p) R1(-y_p).

Velocities use the Earth rotation vector (0, 0, omega_e) in the pseudo-Earth-
fixed frame with omega_e = 7.29211514670698e-5 (1 - LOD/86400) rad/s; the
time derivatives of P, N and PM are neglected, as in GMAT and Vallado.

The time argument of P and N is Julian centuries of TT (GMAT uses TT and labels
it T_TDB). IERS corrections dPsi/dEps are optional (``nutation_corrections``);
GMAT R2026a does not apply them, so cross-checks against GMAT leave them off.
``nutation_interval_s`` reproduces GMAT's ``Earth.NutationUpdateInterval``
caching (GMAT default 60 s); ORRERY's default 0 recomputes at every call.

The 106 nutation coefficients (``data/nutation_iau1980.json``) are the IAU 1980
theory (Seidelmann 1982; Wahr 1981), transcribed from the ``NUTATION.DAT`` file
shipped with GMAT R2026a and checked against a published worked example
(tests/test_orrery_frames.py).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .constants import ARCSEC_TO_RAD, EARTH_ROTATION_RATE, SECONDS_PER_DAY
from .timescales import Epoch

DATA = Path(__file__).resolve().parent / "data"
TWO_PI = 2.0 * math.pi


def rot1(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]])


def rot2(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]])


def rot3(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


@lru_cache(maxsize=1)
def nutation_table() -> tuple[np.ndarray, np.ndarray]:
    """``(multipliers[106, 5], coefficients[106, 4])`` with A, B, C, D in arcsec."""

    payload = json.loads((DATA / "nutation_iau1980.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    if len(rows) != 106:
        raise ValueError("IAU 1980 nutation requires exactly 106 terms")
    mult = np.array([r["multipliers"] for r in rows], dtype=float)
    coef = np.array([r["A_B_C_D"] for r in rows], dtype=float) * payload["unit_arcsec"]
    return mult, coef


def precession_angles(t_tt: float) -> tuple[float, float, float]:
    """IAU 1976 precession angles (zeta, theta, z) in radians."""

    t2, t3 = t_tt * t_tt, t_tt * t_tt * t_tt
    zeta = (2306.2181 * t_tt + 0.30188 * t2 + 0.017998 * t3) * ARCSEC_TO_RAD
    theta = (2004.3109 * t_tt - 0.42665 * t2 - 0.041833 * t3) * ARCSEC_TO_RAD
    z = (2306.2181 * t_tt + 1.09468 * t2 + 0.018203 * t3) * ARCSEC_TO_RAD
    return zeta, theta, z


def precession_matrix(t_tt: float) -> np.ndarray:
    zeta, theta, z = precession_angles(t_tt)
    return rot3(-z) @ rot2(theta) @ rot3(-zeta)


def mean_obliquity(t_tt: float) -> float:
    t2, t3 = t_tt * t_tt, t_tt * t_tt * t_tt
    return (84381.448 - 46.8150 * t_tt - 0.00059 * t2 + 0.001813 * t3) * ARCSEC_TO_RAD


def fundamental_arguments_1980(t_tt: float) -> np.ndarray:
    """Delaunay arguments (l, l', F, D, Omega) of the IAU 1980 theory, radians."""

    t2, t3 = t_tt * t_tt, t_tt * t_tt * t_tt
    deg = math.pi / 180.0
    args = np.array(
        [
            134.96298139 * deg + (1717915922.6330 * t_tt + 31.310 * t2 + 0.064 * t3) * ARCSEC_TO_RAD,
            357.52772333 * deg + (129596581.2240 * t_tt - 0.577 * t2 - 0.012 * t3) * ARCSEC_TO_RAD,
            93.27191028 * deg + (1739527263.1370 * t_tt - 13.257 * t2 + 0.011 * t3) * ARCSEC_TO_RAD,
            297.85036306 * deg + (1602961601.3280 * t_tt - 6.891 * t2 + 0.019 * t3) * ARCSEC_TO_RAD,
            125.04452222 * deg + (-6962890.5390 * t_tt + 7.455 * t2 + 0.008 * t3) * ARCSEC_TO_RAD,
        ]
    )
    return np.fmod(args, TWO_PI)


def nutation_1980(t_tt: float, dpsi_corr: float = 0.0, deps_corr: float = 0.0) -> tuple[float, float, float]:
    """``(dpsi, deps, eps_bar)`` in radians; corrections are in radians."""

    mult, coef = nutation_table()
    arg = mult @ fundamental_arguments_1980(t_tt)
    dpsi = float(np.sum((coef[:, 0] + coef[:, 1] * t_tt) * np.sin(arg))) * ARCSEC_TO_RAD
    deps = float(np.sum((coef[:, 2] + coef[:, 3] * t_tt) * np.cos(arg))) * ARCSEC_TO_RAD
    return dpsi + dpsi_corr, deps + deps_corr, mean_obliquity(t_tt)


def nutation_matrix(dpsi: float, deps: float, eps_bar: float) -> np.ndarray:
    return rot1(-(eps_bar + deps)) @ rot3(-dpsi) @ rot1(eps_bar)


def gmst_1982(ut1: Epoch) -> float:
    """Greenwich mean sidereal time (IAU 1982) in radians, from a UT1 epoch."""

    if ut1.scale != "UT1":
        raise ValueError("GMST requires a UT1 epoch")
    t = ut1.centuries_since_j2000()
    daily = math.fmod(ut1.sec - 43200.0, SECONDS_PER_DAY)  # 86400 * frac(JD_UT1 - 2451545.0)
    seconds = 67310.54841 + 8640184.812866 * t + 0.093104 * t * t - 6.2e-6 * t * t * t + daily
    return math.fmod(seconds, SECONDS_PER_DAY) / SECONDS_PER_DAY * TWO_PI % TWO_PI


def equation_of_equinoxes(dpsi: float, eps_bar: float, omega: float, jd_tt: float) -> float:
    value = dpsi * math.cos(eps_bar)
    if jd_tt > 2450449.5:  # IAU 1994 resolution C7, from 1997-01-01
        value += (0.00264 * math.sin(omega) + 0.000063 * math.sin(2.0 * omega)) * ARCSEC_TO_RAD
    return value


def polar_motion_matrix(xp: float, yp: float) -> np.ndarray:
    """PM maps pseudo-Earth-fixed to ITRF; angles in radians."""

    return rot2(-xp) @ rot1(-yp)


@dataclass(frozen=True)
class FrameRotation:
    """All factors of the MJ2000Eq -> EarthFixed rotation at one instant."""

    precession: np.ndarray
    nutation: np.ndarray
    sidereal: np.ndarray
    polar: np.ndarray
    theta_ast: float
    omega_e: float
    dpsi: float
    deps: float
    eps_bar: float
    gmst: float

    @property
    def matrix(self) -> np.ndarray:
        """MJ2000Eq -> EarthFixed (ITRF)."""

        return self.polar @ self.sidereal @ self.nutation @ self.precession

    def inertial_to_fixed(self, r, v=None):
        r = np.asarray(r, dtype=float)
        tod = self.nutation @ (self.precession @ r)
        pef = self.sidereal @ tod
        r_fixed = self.polar @ pef
        if v is None:
            return r_fixed
        w = np.array([0.0, 0.0, self.omega_e])
        v_pef = self.sidereal @ (self.nutation @ (self.precession @ np.asarray(v, dtype=float))) - np.cross(
            w, pef
        )
        return r_fixed, self.polar @ v_pef

    def fixed_to_inertial(self, r, v=None):
        r = np.asarray(r, dtype=float)
        pef = self.polar.T @ r
        r_inertial = self.precession.T @ (self.nutation.T @ (self.sidereal.T @ pef))
        if v is None:
            return r_inertial
        w = np.array([0.0, 0.0, self.omega_e])
        v_pef = self.polar.T @ np.asarray(v, dtype=float) + np.cross(w, pef)
        return r_inertial, self.precession.T @ (self.nutation.T @ (self.sidereal.T @ v_pef))


class EarthOrientation:
    """FK5 Earth orientation evaluated at TT epochs, with optional GMAT-style caching."""

    def __init__(self, eop, *, nutation_corrections: bool = False, nutation_interval_s: float = 0.0):
        if nutation_interval_s < 0:
            raise ValueError("nutation_interval_s must be non-negative")
        self.eop = eop
        self.nutation_corrections = nutation_corrections
        self.nutation_interval_s = float(nutation_interval_s)
        self._last_nut: tuple[Epoch, tuple[float, float, float], np.ndarray, np.ndarray, float] | None = None

    def describe(self) -> dict:
        return {
            "theory": "IAU-1976 precession, IAU-1980 nutation (106 terms), IAU-1982 GMST, linear EOP",
            "nutation_corrections": self.nutation_corrections,
            "nutation_interval_s": self.nutation_interval_s,
            "eop": self.eop.describe(),
        }

    def at(self, tt: Epoch) -> FrameRotation:
        if tt.scale != "TT":
            tt = tt.to("TT", self.eop)
        utc = tt.to("UTC")
        ut1 = tt.to("UT1", self.eop)
        t_tt = tt.centuries_since_j2000()
        cached = self._last_nut
        if (
            cached is not None
            and self.nutation_interval_s > 0
            and abs(tt.seconds_since(cached[0])) < self.nutation_interval_s
        ):
            _, (dpsi, deps, eps_bar), prec, nut, omega = cached
        else:
            corr = (0.0, 0.0)
            if self.nutation_corrections:
                dpsi_c, deps_c = self.eop.nutation_corrections(utc)
                corr = (dpsi_c * ARCSEC_TO_RAD, deps_c * ARCSEC_TO_RAD)
            dpsi, deps, eps_bar = nutation_1980(t_tt, *corr)
            prec = precession_matrix(t_tt)
            nut = nutation_matrix(dpsi, deps, eps_bar)
            omega = float(fundamental_arguments_1980(t_tt)[4])
            self._last_nut = (tt, (dpsi, deps, eps_bar), prec, nut, omega)
        gmst = gmst_1982(ut1)
        jd_tt = sum(tt.jd())
        theta = gmst + equation_of_equinoxes(dpsi, eps_bar, omega, jd_tt)
        xp, yp = self.eop.polar_motion(utc)
        omega_e = EARTH_ROTATION_RATE * (1.0 - self.eop.lod(utc) / SECONDS_PER_DAY)
        return FrameRotation(
            precession=prec,
            nutation=nut,
            sidereal=rot3(theta),
            polar=polar_motion_matrix(xp * ARCSEC_TO_RAD, yp * ARCSEC_TO_RAD),
            theta_ast=theta,
            omega_e=omega_e,
            dpsi=dpsi,
            deps=deps,
            eps_bar=eps_bar,
            gmst=gmst,
        )


def geodetic_to_ecef(lat_deg: float, lon_deg: float, height_km: float, radius: float, flattening: float):
    """Station position on an oblate reference ellipsoid (geodetic latitude)."""

    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    e2 = flattening * (2.0 - flattening)
    n = radius / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return np.array(
        [
            (n + height_km) * math.cos(lat) * math.cos(lon),
            (n + height_km) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - e2) + height_km) * math.sin(lat),
        ]
    )
