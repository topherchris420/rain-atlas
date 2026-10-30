import math

import numpy as np
from scipy.integrate import solve_ivp


def _logistic(inputs):
    r = float(inputs["r"])
    x = float(inputs.get("x0", 0.2))
    for _ in range(int(inputs.get("transient", 1000))):
        x = r * x * (1 - x)
    steps = int(inputs.get("steps", 100000))
    total = 0.0
    running = []
    checkpoints = {int(steps * f) for f in (0.1, 0.25, 0.5, 1.0)}
    for i in range(1, steps + 1):
        x = r * x * (1 - x)
        total += math.log(max(abs(r * (1 - 2 * x)), 1e-300))
        if i in checkpoints:
            running.append([i, total / i])
    return total / steps, running


def _lorenz(inputs):
    s, rho, b = float(inputs.get("sigma", 10.0)), float(inputs.get("rho", 28.0)), float(inputs.get("beta", 8 / 3))

    def rhs(_t, v):
        x, y, z = v
        return [s * (y - x), x * (rho - z) - y, x * y - b * z]

    state = solve_ivp(rhs, (0, 20), [1.0, 1.0, 1.0], rtol=1e-10, atol=1e-12).y[:, -1]
    d0 = 1e-8
    other = state + np.array([d0, 0.0, 0.0])
    tau = float(inputs.get("renormalize_every", 1.0))
    intervals = int(float(inputs.get("duration", 200.0)) / tau)
    total = 0.0
    running = []
    for k in range(1, intervals + 1):
        state = solve_ivp(rhs, (0, tau), state, rtol=1e-10, atol=1e-12).y[:, -1]
        other = solve_ivp(rhs, (0, tau), other, rtol=1e-10, atol=1e-12).y[:, -1]
        d = np.linalg.norm(other - state)
        total += math.log(d / d0)
        other = state + (other - state) * (d0 / d)
        if k % max(1, intervals // 4) == 0:
            running.append([k * tau, total / (k * tau)])
    return total / (intervals * tau), running


def run(inputs, ctx):
    system = inputs["system"]
    if system == "logistic":
        if "r" not in inputs:
            raise ValueError("the logistic map needs r")
        exponent, running = _logistic(inputs)
    else:
        exponent, running = _lorenz(inputs)
    ctx.log(f"{system}: exponent {exponent:.6f}")
    return {"system": system, "exponent": float(exponent), "running": running}
