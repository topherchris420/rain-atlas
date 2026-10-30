---
name: pendulum-period
description: Integrate the nonlinear (optionally damped) pendulum equation and measure its oscillation period and energy drift. Use when you need a numerically verified period at large amplitude, where the small-angle formula fails.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: computational-physics
---
# Pendulum period

Solves `θ'' = -(g/L) sin θ - γ θ'` from rest at `θ0` with an explicit
8th-order Runge-Kutta method (`scipy.integrate.solve_ivp`, DOP853, tight
tolerances). The period is the mean spacing of successive downward zero
crossings of θ, located by the solver's event detection. Also reported:

- the small-angle period `2π √(L/g)` for comparison;
- for an undamped pendulum, the relative energy drift over the run (a check on
  the integration, not a physical effect).

## Limitations

- Requires at least two full oscillations within `t_max`.
- `θ0` must be in (0, π); at π the period diverges.
- With damping the "period" is the mean zero-crossing spacing, which is the
  damped quasi-period.
