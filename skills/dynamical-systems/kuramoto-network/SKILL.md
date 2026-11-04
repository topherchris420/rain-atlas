---
name: kuramoto-network
description: Globally coupled phase oscillators with RK4 or additive-noise Euler-Maruyama integration. Use for reproducible numerical studies.
license: MIT
---

# kuramoto-network

Globally coupled phase oscillators with RK4 or additive-noise Euler-Maruyama integration.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test kuramoto-network`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- All-to-all K/N coupling excluding self; frequencies and K in rad/s, diffusion in rad squared/s.
- No amplitude dynamics, delays or inferred causal coupling. Finite populations and time windows cannot establish a thermodynamic transition.
- Stochastic convergence requires coupled Wiener increments; fixed seed alone is not a convergence test.

No calibrated uncertainty or empirical validation is implied by a plot.
