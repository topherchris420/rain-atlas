import math

import numpy as np
from scipy.integrate import solve_ivp


def run(inputs, ctx):
    theta0 = float(inputs["theta0_rad"])
    g = float(inputs.get("g", 9.81))
    length = float(inputs.get("length_m", 1.0))
    gamma = float(inputs.get("damping_per_s", 0.0))
    periods = int(inputs.get("periods", 20))
    omega0 = math.sqrt(g / length)
    small = 2 * math.pi / omega0

    def rhs(_t, y):
        return [y[1], -(omega0**2) * math.sin(y[0]) - gamma * y[1]]

    def downward_zero(_t, y):
        return y[0]

    downward_zero.direction = -1
    # The large-amplitude period can be several times the small-angle one.
    t_max = (periods + 2) * small * 4
    sol = solve_ivp(rhs, (0.0, t_max), [theta0, 0.0], method="DOP853", rtol=float(inputs.get("rtol", 1e-11)),
                    atol=1e-12, events=downward_zero, dense_output=True)
    crossings = sol.t_events[0][: periods + 1]
    if crossings.size < 3:
        raise ValueError("fewer than two full oscillations were observed; increase periods or check damping")
    spacing = np.diff(crossings)
    drift = None
    if gamma == 0.0:
        energy = 0.5 * sol.y[1] ** 2 + omega0**2 * (1 - np.cos(sol.y[0]))
        e0 = omega0**2 * (1 - math.cos(theta0))
        drift = float(np.max(np.abs(energy - e0)) / e0)
    ctx.log(f"{spacing.size} period(s) measured; solver status {sol.status}")
    return {
        "period_s": float(spacing.mean()),
        "period_std_s": float(spacing.std()),
        "small_angle_period_s": small,
        "crossings": int(crossings.size),
        "relative_energy_drift": drift,
    }
