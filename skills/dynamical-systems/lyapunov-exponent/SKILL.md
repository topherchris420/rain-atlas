---
name: lyapunov-exponent
description: Estimate the Lyapunov exponent of the logistic map (or the largest exponent of the Lorenz system) to tell chaotic from regular dynamics. Use when you need a quantitative chaos indicator with known-answer checks.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: dynamical-systems
---
# Lyapunov exponent

- **logistic** `x → r x (1 - x)`: average of `ln |r (1 - 2x)|` along the orbit
  after a transient. Known values: `ln 2` at r = 4; `½ ln |4 + 2r - r²|` on the
  stable 2-cycle (e.g. ≈ -0.9163 at r = 3.2).
- **lorenz** (σ, ρ, β): largest exponent by the two-trajectory renormalisation
  method (Benettin et al.) with an RK45 integrator. Reference value at the
  classic parameters is about 0.906 (literature estimates vary in the third
  digit).

Positive exponents indicate sensitive dependence on initial conditions.

## Limitations

- Finite-time estimates converge slowly (error roughly ∝ 1/√steps for chaotic
  orbits).
- In floating point, the r = 4 logistic orbit is a pseudo-orbit; its average
  still matches ln 2 to about two decimals for 10⁵ steps.
- The Lorenz estimate depends on the renormalisation interval and duration.
