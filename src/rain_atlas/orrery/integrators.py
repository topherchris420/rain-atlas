"""Numerical integrators with explicit, recorded error control.

Embedded Runge-Kutta pairs (original implementations from the published
Butcher tableaux; both propagate the higher-order solution, i.e. local
extrapolation, and use the lower-order solution only for the error estimate):

* ``dp54``  - Dormand & Prince (1980) 5(4), 7 stages, first-same-as-last.
* ``rkf78`` - Fehlberg (1968, NASA TR R-287) 7(8), 13 stages; error estimate
  41/840 (k1 + k11 - k12 - k13) h.

Fixed-step methods (for drift studies and as independent checks); passing
``step`` with ``dp54`` or ``rkf78`` runs that tableau at a fixed step:

* ``rk4``      - classical 4th-order Runge-Kutta.
* ``verlet``   - velocity Verlet (kick-drift-kick), 2nd-order symplectic.
* ``yoshida4`` - Yoshida (1990) 4th-order symplectic triple-jump composition.
  Symplectic only for time-independent, separable, conservative forces; with
  third-body ephemerides or a rotating Earth field it is merely 4th order.

Independent library check:

* ``scipy-dop853`` - SciPy's Hairer-Wanner DOP853 (``solve_ivp``); outputs at
  requested times come from its dense-output interpolant.

Error norms for the adaptive pairs (``error_norm``):

``mixed`` (default)
    err = RMS_i( d_i / (atol + rtol * max(|y_i|, |y_new_i|)) ); accept if err <= 1;
    h_new = h * min(fac_max, max(fac_min, safety * err^(-1/(q+1)))), q = lower order
    (Hairer, Norsett & Wanner 1993, section II.4).

``gmat-rss-step``
    The default of NASA GMAT R2026a (``ODEModel::EstimateError``, normType 2):
    for each position/velocity triple, err = |d| / |y_new - y_old| when
    |y_new - y_old|^2 > 0.1, else |d|; err = max over triples; accept if
    err <= accuracy. h_new = 0.9 h (accuracy/err)^(1/m) on acceptance and
    0.9 h (accuracy/err)^(1/(m-1)) on rejection, m = method order, with no growth
    cap other than ``hmax`` (``RungeKutta::AdaptStep``).

Only components in ``error_slice`` enter the norm (by default the 6 orbit
components; an appended state-transition matrix is integrated but not
error-controlled, which is recorded in every result). Output epochs are hit
exactly by shortening the step that would cross them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction as F
from typing import Callable

import numpy as np

Rhs = Callable[[float, np.ndarray], np.ndarray]
Accel = Callable[[float, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class Tableau:
    name: str
    c: np.ndarray
    a: np.ndarray  # strictly lower triangular [s, s]
    b: np.ndarray  # propagated (higher-order) weights
    e: np.ndarray  # error weights: b - b_hat
    order: int  # propagated order
    error_order: int  # lower order of the pair
    fsal: bool
    reference: str


def _tableau(name, c, rows, b, b_hat, order, error_order, fsal, reference) -> Tableau:
    s = len(c)
    a = np.zeros((s, s))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            a[i, j] = float(value)
    b = np.array([float(x) for x in b])
    b_hat = np.array([float(x) for x in b_hat])
    if any(abs(float(sum(row, F(0))) - float(ci)) > 1e-15 for row, ci in zip(rows, c) if row):
        raise ValueError(f"{name}: tableau rows violate c_i = sum_j a_ij")
    return Tableau(
        name, np.array([float(x) for x in c]), a, b, b - b_hat, order, error_order, fsal, reference
    )


DP54 = _tableau(
    "dp54",
    [F(0), F(1, 5), F(3, 10), F(4, 5), F(8, 9), F(1), F(1)],
    [
        [],
        [F(1, 5)],
        [F(3, 40), F(9, 40)],
        [F(44, 45), F(-56, 15), F(32, 9)],
        [F(19372, 6561), F(-25360, 2187), F(64448, 6561), F(-212, 729)],
        [F(9017, 3168), F(-355, 33), F(46732, 5247), F(49, 176), F(-5103, 18656)],
        [F(35, 384), F(0), F(500, 1113), F(125, 192), F(-2187, 6784), F(11, 84)],
    ],
    [F(35, 384), F(0), F(500, 1113), F(125, 192), F(-2187, 6784), F(11, 84), F(0)],
    [F(5179, 57600), F(0), F(7571, 16695), F(393, 640), F(-92097, 339200), F(187, 2100), F(1, 40)],
    5,
    4,
    True,
    "Dormand & Prince, J. Comput. Appl. Math. 6 (1980) 19-26",
)

RKF78 = _tableau(
    "rkf78",
    [
        F(0),
        F(2, 27),
        F(1, 9),
        F(1, 6),
        F(5, 12),
        F(1, 2),
        F(5, 6),
        F(1, 6),
        F(2, 3),
        F(1, 3),
        F(1),
        F(0),
        F(1),
    ],
    [
        [],
        [F(2, 27)],
        [F(1, 36), F(1, 12)],
        [F(1, 24), F(0), F(1, 8)],
        [F(5, 12), F(0), F(-25, 16), F(25, 16)],
        [F(1, 20), F(0), F(0), F(1, 4), F(1, 5)],
        [F(-25, 108), F(0), F(0), F(125, 108), F(-65, 27), F(125, 54)],
        [F(31, 300), F(0), F(0), F(0), F(61, 225), F(-2, 9), F(13, 900)],
        [F(2), F(0), F(0), F(-53, 6), F(704, 45), F(-107, 9), F(67, 90), F(3)],
        [F(-91, 108), F(0), F(0), F(23, 108), F(-976, 135), F(311, 54), F(-19, 60), F(17, 6), F(-1, 12)],
        [
            F(2383, 4100),
            F(0),
            F(0),
            F(-341, 164),
            F(4496, 1025),
            F(-301, 82),
            F(2133, 4100),
            F(45, 82),
            F(45, 164),
            F(18, 41),
        ],
        [F(3, 205), F(0), F(0), F(0), F(0), F(-6, 41), F(-3, 205), F(-3, 41), F(3, 41), F(6, 41), F(0)],
        [
            F(-1777, 4100),
            F(0),
            F(0),
            F(-341, 164),
            F(4496, 1025),
            F(-289, 82),
            F(2193, 4100),
            F(51, 82),
            F(33, 164),
            F(12, 41),
            F(0),
            F(1),
        ],
    ],
    [F(0)] * 5 + [F(34, 105), F(9, 35), F(9, 35), F(9, 280), F(9, 280), F(0), F(41, 840), F(41, 840)],
    [F(41, 840)]
    + [F(0)] * 4
    + [F(34, 105), F(9, 35), F(9, 35), F(9, 280), F(9, 280), F(41, 840), F(0), F(0)],
    8,
    7,
    False,
    "Fehlberg, NASA TR R-287 (1968), Table X",
)

TABLEAUX = {"dp54": DP54, "rkf78": RKF78}
FIXED = ("rk4", "verlet", "yoshida4")
METHODS = (*TABLEAUX, *FIXED, "scipy-dop853")


@dataclass
class IntegrationResult:
    times: np.ndarray
    states: np.ndarray
    method: str
    settings: dict
    accepted: int = 0
    rejected: int = 0
    nfev: int = 0
    step_times: list[float] = field(default_factory=list)
    step_sizes: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def stats(self) -> dict:
        h = np.abs(np.asarray(self.step_sizes)) if self.step_sizes else np.array([np.nan])
        return {
            "accepted_steps": self.accepted,
            "rejected_steps": self.rejected,
            "function_evaluations": self.nfev,
            "min_step_s": float(np.min(h)),
            "max_step_s": float(np.max(h)),
            "median_step_s": float(np.median(h)),
            "warnings": list(self.warnings),
        }


def _error(norm: str, delta, y_old, y_new, rtol, atol, sl) -> float:
    d, yo, yn = delta[sl], y_old[sl], y_new[sl]
    if norm == "mixed":
        scale = atol + rtol * np.maximum(np.abs(yo), np.abs(yn))
        return float(np.sqrt(np.mean((d / scale) ** 2)))
    if norm == "gmat-rss-step":
        worst = 0.0
        for k in range(0, d.size - d.size % 3, 3):
            step = yn[k : k + 3] - yo[k : k + 3]
            mag = float(step @ step)
            err = float(d[k : k + 3] @ d[k : k + 3])
            err = math.sqrt(err / mag) if mag > 0.1 else math.sqrt(err)
            worst = max(worst, err)
        return worst
    raise ValueError(f"unknown error norm {norm!r}")


def integrate(
    rhs: Rhs,
    t0: float,
    y0,
    t_eval,
    *,
    method: str = "rkf78",
    rtol: float = 1e-12,
    atol: float = 1e-12,
    error_norm: str = "mixed",
    accuracy: float | None = None,
    h0: float | None = None,
    hmin: float = 1e-6,
    hmax: float = math.inf,
    step: float | None = None,
    safety: float = 0.9,
    fac_min: float = 0.2,
    fac_max: float = 5.0,
    max_steps: int = 2_000_000,
    error_slice: slice = slice(0, 6),
    accel: Accel | None = None,
    record_steps: bool = True,
) -> IntegrationResult:
    """Integrate ``dy/dt = rhs(t, y)`` from ``t0`` and return states at ``t_eval``."""

    y0 = np.asarray(y0, dtype=float)
    t_eval = np.asarray(t_eval, dtype=float)
    if t_eval.ndim != 1 or t_eval.size == 0:
        raise ValueError("t_eval must be a non-empty 1-D array")
    direction = 1.0 if t_eval[-1] >= t0 else -1.0
    if np.any(direction * np.diff(np.concatenate([[t0], t_eval])) < 0):
        raise ValueError("t_eval must be monotonic and start at or after t0 in the integration direction")
    settings = {
        "method": method,
        "rtol": rtol,
        "atol": atol,
        "error_norm": error_norm,
        "accuracy": accuracy,
        "h0": h0,
        "hmin": hmin,
        "hmax": hmax,
        "step": step,
        "safety": safety,
        "fac_min": fac_min,
        "fac_max": fac_max,
        "error_components": [error_slice.start, error_slice.stop],
    }
    if method in TABLEAUX and step is not None:
        if step <= 0:
            raise ValueError("step must be positive")
        settings["mode"] = "fixed step (higher-order weights, no error control)"
        return _fixed(rhs, accel, t0, y0, t_eval, method, settings, record_steps)
    if method in TABLEAUX:
        settings["mode"] = "adaptive"
        return _adaptive(rhs, t0, y0, t_eval, TABLEAUX[method], settings, max_steps, direction, record_steps)
    if method in FIXED:
        if step is None or step <= 0:
            raise ValueError(f"{method} needs a positive fixed step")
        return _fixed(rhs, accel, t0, y0, t_eval, method, settings, record_steps)
    if method == "scipy-dop853":
        return _scipy(rhs, t0, y0, t_eval, settings)
    raise ValueError(f"unknown method {method!r}; available: {METHODS}")


def _adaptive(rhs, t0, y0, t_eval, tab: Tableau, s: dict, max_steps, direction, record) -> IntegrationResult:
    norm = s["error_norm"]
    sl = slice(*s["error_components"])
    if norm == "gmat-rss-step":
        tol = s["accuracy"] if s["accuracy"] is not None else 1e-11
        inc, dec = 1.0 / tab.order, 1.0 / (tab.order - 1)
    else:
        tol = 1.0
        inc = dec = 1.0 / (tab.error_order + 1)
    n_stages = len(tab.c)
    out = np.empty((t_eval.size, y0.size))
    res = IntegrationResult(t_eval.copy(), out, tab.name, s)
    t, y = float(t0), y0.copy()
    k = np.empty((n_stages, y0.size))
    k0 = rhs(t, y)
    res.nfev += 1
    h = s["h0"] if s["h0"] else _initial_step(rhs, t, y, k0, tab.order, s, res)
    h = direction * min(abs(h), s["hmax"])
    steps = 0
    for idx, t_target in enumerate(t_eval):
        while direction * (t_target - t) > 0:
            if steps >= max_steps:
                raise RuntimeError(f"{tab.name}: exceeded {max_steps} steps")
            h_try = h
            clipped = direction * (t + h_try - t_target) > 0
            if clipped:
                h_try = t_target - t
            while True:
                k[0] = k0
                for i in range(1, n_stages):
                    k[i] = rhs(t + tab.c[i] * h_try, y + h_try * (tab.a[i, :i] @ k[:i]))
                res.nfev += n_stages - 1
                y_new = y + h_try * (tab.b @ k)
                delta = h_try * (tab.e @ k)
                err = _error(norm, delta, y, y_new, s["rtol"], s["atol"], sl)
                if err <= tol or abs(h_try) <= s["hmin"]:
                    if err > tol:
                        res.warnings.append(f"accepted step at hmin={s['hmin']} with error {err:.3e}")
                    break
                res.rejected += 1
                factor = s["safety"] * (tol / err) ** dec if err > 0 else s["fac_max"]
                if norm == "mixed":
                    factor = max(s["fac_min"], min(1.0, factor))
                h_try = direction * max(abs(h_try) * factor, s["hmin"])
                clipped = False
            t_new = t_target if clipped else t + h_try
            if tab.fsal:  # last stage is f(t + h, y_new) for any h, clipped or not
                k0 = k[n_stages - 1].copy()
            else:
                k0 = rhs(t_new, y_new)
                res.nfev += 1
            if record:
                res.step_times.append(t)
                res.step_sizes.append(h_try)
            res.accepted += 1
            steps += 1
            # Step-size proposal for the next step (unaffected by output clipping).
            if err > 0:
                factor = s["safety"] * (tol / err) ** inc
            else:
                factor = s["fac_max"]
            if norm == "mixed":
                factor = max(s["fac_min"], min(s["fac_max"], factor))
            proposal = abs(h_try) * factor
            if clipped:
                proposal = max(proposal, abs(h))
            h = direction * min(max(proposal, s["hmin"]), s["hmax"])
            t, y = t_new, y_new
        out[idx] = y
    return res


def _initial_step(rhs, t, y, f0, order, s, res) -> float:
    """Hairer-Wanner starting step estimate (algorithm in HNW I, II.4)."""

    sl = slice(*s["error_components"])
    scale = s["atol"] + s["rtol"] * np.abs(y[sl]) if s["error_norm"] == "mixed" else 1e-3 + np.abs(y[sl])
    d0 = float(np.sqrt(np.mean((y[sl] / scale) ** 2)))
    d1 = float(np.sqrt(np.mean((f0[sl] / scale) ** 2)))
    h0 = 1e-6 if d0 < 1e-5 or d1 < 1e-5 else 0.01 * d0 / d1
    f1 = rhs(t + h0, y + h0 * f0)
    res.nfev += 1
    d2 = float(np.sqrt(np.mean(((f1[sl] - f0[sl]) / scale) ** 2))) / h0
    h1 = max(1e-6, h0 * 1e-3) if max(d1, d2) <= 1e-15 else (0.01 / max(d1, d2)) ** (1.0 / (order + 1))
    return min(100.0 * h0, h1, s["hmax"])


_YOSHIDA_W1 = 1.0 / (2.0 - 2.0 ** (1.0 / 3.0))
_YOSHIDA_W0 = -(2.0 ** (1.0 / 3.0)) * _YOSHIDA_W1


def _fixed(rhs, accel, t0, y0, t_eval, method, s, record) -> IntegrationResult:
    if method in ("verlet", "yoshida4") and accel is None:
        raise ValueError(f"{method} requires an acceleration function accel(t, r)")
    if method in ("verlet", "yoshida4") and y0.size != 6:
        raise ValueError(f"{method} integrates a 6-component (r, v) state only")
    out = np.empty((t_eval.size, y0.size))
    res = IntegrationResult(t_eval.copy(), out, method, s)
    t, y = float(t0), y0.copy()
    for idx, t_target in enumerate(t_eval):
        span = t_target - t
        n = max(1, math.ceil(abs(span) / s["step"] - 1e-9)) if span != 0 else 0
        h = span / n if n else 0.0
        for _ in range(n):
            if method in TABLEAUX:
                tab = TABLEAUX[method]
                k = np.empty((len(tab.c), y.size))
                for i in range(len(tab.c)):
                    k[i] = rhs(t + tab.c[i] * h, y + h * (tab.a[i, :i] @ k[:i]) if i else y)
                y = y + h * (tab.b @ k)
                res.nfev += len(tab.c)
            elif method == "rk4":
                k1 = rhs(t, y)
                k2 = rhs(t + h / 2, y + h / 2 * k1)
                k3 = rhs(t + h / 2, y + h / 2 * k2)
                k4 = rhs(t + h, y + h * k3)
                y = y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
                res.nfev += 4
            else:
                weights = (1.0,) if method == "verlet" else (_YOSHIDA_W1, _YOSHIDA_W0, _YOSHIDA_W1)
                r, v, tt = y[:3].copy(), y[3:].copy(), t
                for w in weights:
                    hw = w * h
                    v = v + 0.5 * hw * accel(tt, r)
                    r = r + hw * v
                    tt += hw
                    v = v + 0.5 * hw * accel(tt, r)
                    res.nfev += 2
                y = np.concatenate([r, v])
            if record:
                res.step_times.append(t)
                res.step_sizes.append(h)
            t += h
            res.accepted += 1
        t = float(t_target)
        out[idx] = y
    return res


def _scipy(rhs, t0, y0, t_eval, s) -> IntegrationResult:
    from scipy.integrate import solve_ivp  # noqa: PLC0415

    sol = solve_ivp(
        rhs,
        (float(t0), float(t_eval[-1])),
        y0,
        method="DOP853",
        t_eval=t_eval,
        rtol=s["rtol"],
        atol=s["atol"],
        max_step=s["hmax"] if math.isfinite(s["hmax"]) else np.inf,
    )
    if not sol.success:
        raise RuntimeError(f"scipy DOP853 failed: {sol.message}")
    res = IntegrationResult(t_eval.copy(), sol.y.T.copy(), "scipy-dop853", s)
    res.nfev = int(sol.nfev)
    res.accepted = int(len(sol.t))
    res.warnings.append("outputs interpolated with SciPy's DOP853 dense output; step history not exposed")
    return res
