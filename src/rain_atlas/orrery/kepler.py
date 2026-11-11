"""Two-body (Keplerian) motion: elements, Kepler's equation and analytical propagation.

Two independent analytical propagators are provided so that each can check the
other and both can check numerical integration:

``kepler_propagate`` (elliptic orbits only)
    Difference form of Kepler's equation (Battin 1999, section 4.5),
        n dt = dE + sigma0/sqrt(a) (1 - cos dE) - (1 - r0/a) sin dE,
    with sigma0 = r0.v0/sqrt(mu), solved by Newton iteration after reducing
    n dt modulo 2 pi so that multi-revolution arcs lose no precision; the state
    follows from Lagrange's f and g functions. No orbital elements are formed,
    so circular and equatorial orbits are not singular.

``universal_propagate`` (any conic)
    Universal-variable formulation with Stumpff functions C(z), S(z)
    (Vallado 2013, algorithm 8; Bate, Mueller & White 1971), solved by Newton
    iteration on chi; series expansions are used for |z| < 1e-3.

Element conversions follow Vallado (2013, algorithms 9 and 10). The angles of
circular or equatorial orbits are undefined; ``state_to_elements`` reports the
conventional substitutes (argument of latitude, true longitude) and says so.
"""

from __future__ import annotations

import math

import numpy as np

TWO_PI = 2.0 * math.pi


def solve_kepler(mean_anomaly: float, e: float, tol: float = 1e-15) -> float:
    """Eccentric anomaly E for M = E - e sin E (0 <= e < 1)."""

    if not 0.0 <= e < 1.0:
        raise ValueError("solve_kepler handles elliptic orbits only")
    m = math.fmod(mean_anomaly, TWO_PI)
    big_e = m + e * math.sin(m) if e < 0.8 else math.pi
    for _ in range(60):
        f = big_e - e * math.sin(big_e) - m
        step = f / (1.0 - e * math.cos(big_e))
        big_e -= step
        if abs(step) < tol:
            return big_e
    raise RuntimeError("Kepler's equation did not converge")


def elements_to_state(a, e, i, raan, argp, nu, mu):
    """Classical elements (km, rad) -> inertial position and velocity."""

    p = a * (1.0 - e * e)
    if p <= 0:
        raise ValueError("semi-latus rectum must be positive")
    r_pf = p / (1.0 + e * math.cos(nu)) * np.array([math.cos(nu), math.sin(nu), 0.0])
    v_pf = math.sqrt(mu / p) * np.array([-math.sin(nu), e + math.cos(nu), 0.0])
    co, so = math.cos(raan), math.sin(raan)
    cw, sw = math.cos(argp), math.sin(argp)
    ci, si = math.cos(i), math.sin(i)
    q = np.array(
        [
            [co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
            [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
            [sw * si, cw * si, ci],
        ]
    )
    return q @ r_pf, q @ v_pf


def state_to_elements(r, v, mu) -> dict:
    """Inertial state -> classical elements, with explicit singular-case flags."""

    r = np.asarray(r, dtype=float)
    v = np.asarray(v, dtype=float)
    rm, vm = float(np.linalg.norm(r)), float(np.linalg.norm(v))
    h = np.cross(r, v)
    hm = float(np.linalg.norm(h))
    n = np.cross([0.0, 0.0, 1.0], h)
    nm = float(np.linalg.norm(n))
    evec = ((vm * vm - mu / rm) * r - float(r @ v) * v) / mu
    e = float(np.linalg.norm(evec))
    energy = vm * vm / 2.0 - mu / rm
    a = -mu / (2.0 * energy) if abs(e - 1.0) > 1e-12 else math.inf
    i = math.acos(max(-1.0, min(1.0, h[2] / hm)))
    eps = 1e-11
    circular, equatorial = e < eps, nm < eps * hm
    raan = 0.0 if equatorial else math.atan2(n[1], n[0]) % TWO_PI
    if circular:
        argp = 0.0
        ref = np.array([1.0, 0.0, 0.0]) if equatorial else n / nm
        nu = math.acos(max(-1.0, min(1.0, float(ref @ r) / rm)))
        if r[2] < 0 if not equatorial else r[1] < 0:
            nu = TWO_PI - nu
    else:
        if equatorial:
            argp = math.atan2(evec[1], evec[0]) % TWO_PI
            if h[2] < 0:
                argp = (TWO_PI - argp) % TWO_PI
        else:
            argp = math.acos(max(-1.0, min(1.0, float(n @ evec) / (nm * e))))
            if evec[2] < 0:
                argp = TWO_PI - argp
        nu = math.acos(max(-1.0, min(1.0, float(evec @ r) / (e * rm))))
        if float(r @ v) < 0:
            nu = TWO_PI - nu
    return {
        "a": a,
        "e": e,
        "i": i,
        "raan": raan,
        "argp": argp,
        "nu": nu,
        "energy": energy,
        "h": hm,
        "circular": circular,
        "equatorial": equatorial,
        "note": "for circular orbits nu is the argument of latitude (or true longitude if also equatorial)"
        if circular
        else "",
    }


def kepler_propagate(r0, v0, dt: float, mu: float, tol: float = 1e-15):
    """Elliptic two-body propagation by the difference form of Kepler's equation."""

    r0 = np.asarray(r0, dtype=float)
    v0 = np.asarray(v0, dtype=float)
    rm0 = math.sqrt(float(r0 @ r0))
    alpha = 2.0 / rm0 - float(v0 @ v0) / mu  # 1/a
    if alpha <= 0:
        raise ValueError("kepler_propagate requires an elliptic orbit; use universal_propagate")
    a = 1.0 / alpha
    n = math.sqrt(mu * alpha**3)
    sigma0 = float(r0 @ v0) / math.sqrt(mu)
    total = n * dt
    revs = math.floor(total / TWO_PI)
    dm = total - revs * TWO_PI  # reduced mean-anomaly change in [0, 2 pi)
    k1 = sigma0 / math.sqrt(a)
    k2 = 1.0 - rm0 / a
    # Solve F(dE) = dE + k1 (1 - cos dE) - k2 sin dE - dM = 0. With e = sqrt(k1^2 + k2^2) < 1,
    # F' = 1 + k1 sin dE - k2 cos dE >= 1 - e > 0, so F is strictly increasing: a safeguarded
    # Newton/bisection on the bracket [dM - c, dM + c] (c bounds |dE - dM|) converges globally.
    ecc = math.sqrt(k1 * k1 + k2 * k2)
    c = (2.0 * abs(k1) + abs(k2)) / max(1.0 - ecc, 1e-12) + 0.1

    def big_f(x: float) -> float:
        return x + k1 * (1.0 - math.cos(x)) - k2 * math.sin(x) - dm

    lo, hi = dm - c, dm + c
    de = dm
    for _ in range(100):
        fval = big_f(de)
        if fval > 0:
            hi = de
        else:
            lo = de
        fp = 1.0 + k1 * math.sin(de) - k2 * math.cos(de)
        step = fval / fp
        new = de - step
        if not (lo < new < hi):  # Newton left the bracket: bisect instead
            new = 0.5 * (lo + hi)
            step = de - new
        de = new
        if abs(step) < tol:
            break
    else:
        raise RuntimeError("difference-form Kepler equation did not converge")
    dt_reduced = dm / n
    cos_de, sin_de = math.cos(de), math.sin(de)
    f_ = 1.0 - a / rm0 * (1.0 - cos_de)
    g_ = dt_reduced - (de - sin_de) / n
    r = f_ * r0 + g_ * v0
    rm = math.sqrt(float(r @ r))
    fdot = -math.sqrt(mu * a) / (rm * rm0) * sin_de
    gdot = 1.0 - a / rm * (1.0 - cos_de)
    return r, fdot * r0 + gdot * v0


def stumpff(z: float) -> tuple[float, float]:
    """Stumpff functions C(z), S(z)."""

    if abs(z) < 1e-3:
        c = 0.5 - z / 24.0 + z * z / 720.0 - z**3 / 40320.0
        s = 1.0 / 6.0 - z / 120.0 + z * z / 5040.0 - z**3 / 362880.0
        return c, s
    if z > 0:
        sz = math.sqrt(z)
        return (1.0 - math.cos(sz)) / z, (sz - math.sin(sz)) / (sz**3)
    sz = math.sqrt(-z)
    return (math.cosh(sz) - 1.0) / (-z), (math.sinh(sz) - sz) / (sz**3)


def universal_propagate(r0, v0, dt: float, mu: float, tol: float = 1e-13, max_iter: int = 200):
    """Two-body propagation valid for elliptic, parabolic and hyperbolic orbits."""

    r0 = np.asarray(r0, dtype=float)
    v0 = np.asarray(v0, dtype=float)
    rm0 = math.sqrt(float(r0 @ r0))
    vr0 = float(r0 @ v0) / rm0
    alpha = 2.0 / rm0 - float(v0 @ v0) / mu
    smu = math.sqrt(mu)
    chi = smu * abs(alpha) * dt if alpha > 1e-12 else smu * dt / rm0
    for _ in range(max_iter):
        z = alpha * chi * chi
        c, s = stumpff(z)
        f = rm0 * vr0 / smu * chi * chi * c + (1.0 - alpha * rm0) * chi**3 * s + rm0 * chi - smu * dt
        fp = rm0 * vr0 / smu * chi * (1.0 - z * s) + (1.0 - alpha * rm0) * chi * chi * c + rm0
        step = f / fp
        chi -= step
        if abs(step) < tol * max(1.0, abs(chi)):
            break
    else:
        raise RuntimeError("universal Kepler equation did not converge")
    z = alpha * chi * chi
    c, s = stumpff(z)
    f_ = 1.0 - chi * chi / rm0 * c
    g_ = dt - chi**3 / smu * s
    r = f_ * r0 + g_ * v0
    rm = math.sqrt(float(r @ r))
    fdot = smu / (rm * rm0) * (z * s - 1.0) * chi
    gdot = 1.0 - chi * chi / rm * c
    return r, fdot * r0 + gdot * v0


def kepler_trajectory(r0, v0, times, mu: float) -> np.ndarray:
    """States [len(times), 6] from ``kepler_propagate`` (elliptic reference)."""

    out = np.empty((len(times), 6))
    for k, t in enumerate(times):
        r, v = kepler_propagate(r0, v0, float(t), mu)
        out[k, :3], out[k, 3:] = r, v
    return out


def orbital_period(a: float, mu: float) -> float:
    return TWO_PI * math.sqrt(a**3 / mu)
