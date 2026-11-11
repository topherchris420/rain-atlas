"""Gravitational force models for an Earth-centred spacecraft state.

Every term returns the acceleration in the MJ2000Eq frame (km/s^2) at time t
(seconds of TT since the model epoch) and its gradient d a / d r (1/s^2) for
state-transition-matrix propagation.

Terms
-----
``PointMass(mu)``
    a = -mu r / |r|^3;  G = mu/|r|^3 (3 r_hat r_hat^T - I).

``ZonalJ2(mu, radius, j2, pole)``
    Closed form of the second zonal harmonic (Vallado 2013, eq. 8-30),
        a_b = -(3/2) J2 mu R^2 / r^5 [x(1-5z^2/r^2), y(1-5z^2/r^2), z(3-5z^2/r^2)],
    evaluated in body axes and rotated back. ``pole="inertial"`` fixes the
    body z axis to MJ2000Eq z (energy and h_z are then exact integrals);
    ``pole="earth-fixed"`` uses the FK5 EarthFixed axes (as GMAT does). The
    gradient is analytic.

``SphericalHarmonics(mu, radius, C, S, degree, order)``
    Full geopotential to (degree, order) including the central term, from fully
    normalized coefficients, by the V/W recursions of Montenbruck & Gill (2000,
    section 3.2.4-3.2.5) in EarthFixed axes. Gradient by central differences
    (h = 1e-3 km), documented as numerical.

``ThirdBody(body, mu, ephemeris)``
    Point-mass perturbation relative to the accelerating Earth centre,
        a = mu_b ((r_b - r)/|r_b - r|^3 - r_b/|r_b|^3),
    with r_b from the ephemeris at TDB (geometric, no light time), rotated from
    ICRF to MJ2000Eq by the configured frame tie (see ephemeris.FrameTie). This
    is the form GMAT's PointMassForce uses; no Battin f(q) rewriting is applied.

Not modelled (deliberately, and recorded in every configuration): atmospheric
drag, solar radiation pressure, solid and ocean tides, relativistic
corrections, thrust, Earth albedo, and the constant IERS 2003 frame-bias matrix.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .constants import A1_MINUS_TAI_S, TT_MINUS_TAI_S
from .ephemeris import Ephemeris, FrameTie, body_id
from .frames import EarthOrientation
from .timescales import Epoch, tdb_minus_tt

DATA = Path(__file__).resolve().parent / "data"
_I3 = np.eye(3)

NOT_MODELLED = [
    "atmospheric drag",
    "solar radiation pressure",
    "solid-Earth and ocean tides",
    "general-relativistic corrections",
    "thrust (impulses are applied separately as instantaneous velocity changes)",
    "Earth albedo and infrared radiation",
    "the constant IERS 2003 frame-bias matrix (the ICRF-to-MJ2000Eq tie is configurable: GMAT's table or none)",
]


def point_mass_jacobian(mu: float, r: np.ndarray) -> np.ndarray:
    rm2 = float(r @ r)
    rm = math.sqrt(rm2)
    return mu / (rm2 * rm) * (3.0 * np.outer(r, r) / rm2 - _I3)


@dataclass
class PointMass:
    mu: float
    kind: str = "point-mass"

    def accel(self, ctx, r):
        rm2 = float(r @ r)
        return -self.mu * r / (rm2 * math.sqrt(rm2))

    def evaluate(self, ctx, r):
        return self.accel(ctx, r), point_mass_jacobian(self.mu, r)

    def potential(self, ctx, r) -> float:
        return -self.mu / math.sqrt(float(r @ r))

    def describe(self) -> dict:
        return {"term": self.kind, "mu_km3_s2": self.mu}


def j2_body(
    mu: float, radius: float, j2: float, rb: np.ndarray, gradient: bool = True
) -> tuple[np.ndarray, np.ndarray | None]:
    x, y, z = rb
    r2 = float(rb @ rb)
    r = math.sqrt(r2)
    c = -1.5 * j2 * mu * radius * radius
    r5 = r2 * r2 * r
    s = z * z / r2
    acc = c / r5 * np.array([x * (1.0 - 5.0 * s), y * (1.0 - 5.0 * s), z * (3.0 - 5.0 * s)])
    if not gradient:
        return acc, None
    r7 = r5 * r2
    r9 = r7 * r2
    f = 1.0 / r5 - 5.0 * z * z / r7
    zhat = np.array([0.0, 0.0, 1.0])
    grad = c * (
        f * _I3
        + (-5.0 / r7 + 35.0 * z * z / r9) * np.outer(rb, rb)
        - 10.0 * z / r7 * (np.outer(rb, zhat) + np.outer(zhat, rb))
        + 2.0 / r5 * np.outer(zhat, zhat)
    )
    return acc, grad


@dataclass
class ZonalJ2:
    mu: float
    radius: float
    j2: float
    pole: str = "earth-fixed"
    kind: str = "zonal-j2"

    def __post_init__(self):
        if self.pole not in ("inertial", "earth-fixed"):
            raise ValueError("pole must be 'inertial' or 'earth-fixed'")

    def accel(self, ctx, r):
        if self.pole == "inertial":
            return j2_body(self.mu, self.radius, self.j2, r, gradient=False)[0]
        m = ctx.rotation().matrix
        return m.T @ j2_body(self.mu, self.radius, self.j2, m @ r, gradient=False)[0]

    def evaluate(self, ctx, r):
        if self.pole == "inertial":
            return j2_body(self.mu, self.radius, self.j2, r)
        m = ctx.rotation().matrix
        acc_b, grad_b = j2_body(self.mu, self.radius, self.j2, m @ r)
        return m.T @ acc_b, m.T @ grad_b @ m

    def potential(self, ctx, r) -> float | None:
        if self.pole != "inertial":
            return None
        r2 = float(r @ r)
        rm = math.sqrt(r2)
        return self.mu * self.j2 * self.radius**2 * (3.0 * r[2] ** 2 / r2 - 1.0) / (2.0 * rm**3)

    def describe(self) -> dict:
        return {
            "term": self.kind,
            "mu_km3_s2": self.mu,
            "radius_km": self.radius,
            "j2": self.j2,
            "pole": self.pole,
        }


def load_gravity_field(name: str = "jgm3_8x8") -> dict:
    payload = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
    nmax = max(t["n"] for t in payload["terms"])
    cbar = np.zeros((nmax + 1, nmax + 1))
    sbar = np.zeros((nmax + 1, nmax + 1))
    cbar[0, 0] = 1.0
    for t in payload["terms"]:
        cbar[t["n"], t["m"]] = t["C"]
        sbar[t["n"], t["m"]] = t["S"]
    return {
        "mu": payload["mu_km3_s2"],
        "radius": payload["radius_km"],
        "C": cbar,
        "S": sbar,
        "source": payload["source"],
        "name": name,
    }


def unnormalize(cbar: np.ndarray, sbar: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n_max = cbar.shape[0] - 1
    c = np.zeros_like(cbar)
    s = np.zeros_like(sbar)
    for n in range(n_max + 1):
        for m in range(n + 1):
            factor = math.sqrt(
                (1.0 if m == 0 else 2.0) * (2 * n + 1) * math.factorial(n - m) / math.factorial(n + m)
            )
            c[n, m] = cbar[n, m] * factor
            s[n, m] = sbar[n, m] * factor
    return c, s


def harmonic_acceleration(mu, radius, c, s, degree, order, rb):
    """Body-frame acceleration of the geopotential (Montenbruck & Gill 2000, eq. 3.33)."""

    x, y, z = (float(q) for q in rb)
    r2 = x * x + y * y + z * z
    rho = radius * radius / r2
    x0, y0, z0 = radius * x / r2, radius * y / r2, radius * z / r2
    size = degree + 2
    v = [[0.0] * (size + 1) for _ in range(size + 1)]
    w = [[0.0] * (size + 1) for _ in range(size + 1)]
    v[0][0] = radius / math.sqrt(r2)
    v[1][0] = z0 * v[0][0]
    for n in range(2, size + 1):
        v[n][0] = ((2 * n - 1) * z0 * v[n - 1][0] - (n - 1) * rho * v[n - 2][0]) / n
    for m in range(1, size + 1):
        v[m][m] = (2 * m - 1) * (x0 * v[m - 1][m - 1] - y0 * w[m - 1][m - 1])
        w[m][m] = (2 * m - 1) * (x0 * w[m - 1][m - 1] + y0 * v[m - 1][m - 1])
        if m + 1 <= size:
            v[m + 1][m] = (2 * m + 1) * z0 * v[m][m]
            w[m + 1][m] = (2 * m + 1) * z0 * w[m][m]
        for n in range(m + 2, size + 1):
            v[n][m] = ((2 * n - 1) * z0 * v[n - 1][m] - (n + m - 1) * rho * v[n - 2][m]) / (n - m)
            w[n][m] = ((2 * n - 1) * z0 * w[n - 1][m] - (n + m - 1) * rho * w[n - 2][m]) / (n - m)
    ax = ay = az = 0.0
    for n in range(degree + 1):
        vn, wn = v[n + 1], w[n + 1]
        for m in range(min(n, order) + 1):
            cnm, snm = c[n][m], s[n][m]
            if m == 0:
                ax -= cnm * vn[1]
                ay -= cnm * wn[1]
                az -= (n + 1) * cnm * vn[0]
            else:
                fac = (n - m + 1) * (n - m + 2)
                ax += 0.5 * ((-cnm * vn[m + 1] - snm * wn[m + 1]) + fac * (cnm * vn[m - 1] + snm * wn[m - 1]))
                ay += 0.5 * (
                    (-cnm * wn[m + 1] + snm * vn[m + 1]) + fac * (-cnm * wn[m - 1] + snm * vn[m - 1])
                )
                az += (n - m + 1) * (-cnm * vn[m] - snm * wn[m])
    return mu / (radius * radius) * np.array([ax, ay, az])


@dataclass
class SphericalHarmonics:
    mu: float
    radius: float
    cbar: np.ndarray
    sbar: np.ndarray
    degree: int
    order: int
    field_name: str = "custom"
    kind: str = "spherical-harmonics"
    fd_step_km: float = 1e-3
    _c: list = field(init=False, repr=False)
    _s: list = field(init=False, repr=False)

    def __post_init__(self):
        if not (0 <= self.order <= self.degree <= self.cbar.shape[0] - 1):
            raise ValueError("require 0 <= order <= degree <= available degree")
        c, s = unnormalize(self.cbar, self.sbar)
        self._c, self._s = c.tolist(), s.tolist()

    def _acc(self, m, r):
        return m.T @ harmonic_acceleration(
            self.mu, self.radius, self._c, self._s, self.degree, self.order, m @ r
        )

    def accel(self, ctx, r):
        return self._acc(ctx.rotation().matrix, r)

    def evaluate(self, ctx, r):
        m = ctx.rotation().matrix
        acc = self._acc(m, r)
        grad = np.empty((3, 3))
        h = self.fd_step_km
        for k in range(3):
            dr = np.zeros(3)
            dr[k] = h
            grad[:, k] = (self._acc(m, r + dr) - self._acc(m, r - dr)) / (2.0 * h)
        return acc, grad

    def describe(self) -> dict:
        return {
            "term": self.kind,
            "field": self.field_name,
            "degree": self.degree,
            "order": self.order,
            "mu_km3_s2": self.mu,
            "radius_km": self.radius,
            "includes_central_term": True,
            "gradient": f"central differences, h = {self.fd_step_km} km",
        }


@dataclass
class ThirdBody:
    body: str
    mu: float
    ephemeris: Ephemeris
    center: str = "earth"
    frame_tie: FrameTie | None = None
    kind: str = "third-body"

    def position(self, ctx) -> np.ndarray:
        rb = self.ephemeris.position(body_id(self.body), body_id(self.center), ctx.et())
        return rb if self.frame_tie is None or self.frame_tie.mode == "none" else ctx.tie(self.frame_tie) @ rb

    def accel(self, ctx, r):
        rb = self.position(ctx)
        d = rb - r
        d2 = float(d @ d)
        rb2 = float(rb @ rb)
        return self.mu * (d / (d2 * math.sqrt(d2)) - rb / (rb2 * math.sqrt(rb2)))

    def evaluate(self, ctx, r):
        rb = self.position(ctx)
        d = rb - r
        d2 = float(d @ d)
        dm = math.sqrt(d2)
        rb2 = float(rb @ rb)
        rbm = math.sqrt(rb2)
        acc = self.mu * (d / (d2 * dm) - rb / (rb2 * rbm))
        grad = self.mu / (d2 * dm) * (3.0 * np.outer(d, d) / d2 - _I3)
        return acc, grad

    def describe(self) -> dict:
        return {
            "term": self.kind,
            "body": self.body,
            "mu_km3_s2": self.mu,
            "ephemeris": self.ephemeris.source.get("name", self.ephemeris.source.get("file", "custom")),
            "frame_tie": self.frame_tie.describe() if self.frame_tie else FrameTie("none").describe(),
        }


class _EvalContext:
    """Lazily computed per-time quantities shared by all terms in one evaluation."""

    __slots__ = ("model", "t", "_rot", "_et", "_tie")

    def __init__(self, model: ForceModel, t: float):
        self.model = model
        self.t = t
        self._rot = None
        self._et = None
        self._tie = None

    def tie(self, frame_tie: FrameTie) -> np.ndarray:
        """ICRF-to-MJ2000Eq matrix at this time (argument: GMAT A1 Modified Julian Date)."""

        if self._tie is None:
            tt = self.model.epoch.plus_seconds(self.t)
            a1 = tt.gmat_modjulian() - (TT_MINUS_TAI_S - A1_MINUS_TAI_S) / 86400.0
            self._tie = frame_tie.matrix(a1)
        return self._tie

    def rotation(self):
        if self._rot is None:
            if self.model.orientation is None:
                raise ValueError("this force term needs an EarthOrientation model")
            self._rot = self.model.orientation.at(self.model.epoch.plus_seconds(self.t))
        return self._rot

    def et(self) -> float:
        if self._et is None:
            tt_seconds = self.model.tt_j2000_seconds + self.t
            tt = self.model.epoch.plus_seconds(self.t)
            self._et = tt_seconds + tdb_minus_tt(tt)
        return self._et


class ForceModel:
    """Sum of force terms with a TT reference epoch (t = 0)."""

    def __init__(self, terms: list, epoch: Epoch, orientation: EarthOrientation | None = None):
        if not terms:
            raise ValueError("a force model needs at least one term")
        self.terms = list(terms)
        self.epoch = epoch if epoch.scale == "TT" else epoch.to("TT")
        self.orientation = orientation
        self.tt_j2000_seconds = (self.epoch.mjd - 51544) * 86400.0 + (self.epoch.sec - 43200.0)
        self.evaluations = 0

    def evaluate(self, t: float, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ctx = _EvalContext(self, t)
        acc = np.zeros(3)
        grad = np.zeros((3, 3))
        for term in self.terms:
            a, g = term.evaluate(ctx, r)
            acc += a
            grad += g
        self.evaluations += 1
        return acc, grad

    def acceleration(self, t: float, r) -> np.ndarray:
        ctx = _EvalContext(self, t)
        r = np.asarray(r, dtype=float)
        acc = np.zeros(3)
        for term in self.terms:
            acc += term.accel(ctx, r)
        self.evaluations += 1
        return acc

    def rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        return np.concatenate([y[3:6], self.acceleration(t, y[:3])])

    def rhs_stm(self, t: float, y: np.ndarray) -> np.ndarray:
        """Orbit state plus row-major 6x6 STM: dPhi/dt = A Phi, A = [[0, I], [G, 0]]."""

        acc, grad = self.evaluate(t, y[:3])
        phi = y[6:42].reshape(6, 6)
        dphi = np.empty((6, 6))
        dphi[:3] = phi[3:]
        dphi[3:] = grad @ phi[:3]
        return np.concatenate([y[3:6], acc, dphi.ravel()])

    def energy(self, t: float, y: np.ndarray) -> float | None:
        """Specific mechanical energy when every term is conservative and time-independent."""

        ctx = _EvalContext(self, t)
        total = 0.5 * float(y[3:6] @ y[3:6])
        for term in self.terms:
            pot = getattr(term, "potential", None)
            value = pot(ctx, y[:3]) if pot else None
            if value is None:
                return None
            total += value
        return total

    def describe(self) -> dict:
        return {
            "epoch_tt": self.epoch.iso(9),
            "terms": [t.describe() for t in self.terms],
            "earth_orientation": self.orientation.describe() if self.orientation else None,
            "frame": "MJ2000Eq (IAU-1976/FK5 mean equator and equinox of J2000.0)",
            "not_modelled": NOT_MODELLED,
        }
