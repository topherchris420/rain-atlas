---
name: orbit-propagation
description: Propagate an Earth orbit under configurable gravity and report conservation diagnostics. Use for orbit-propagation tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Orbit Propagation

Numerically integrates an Earth-centred orbit (MJ2000Eq) under a configurable force model (point mass, closed-form J2, or JGM-3 spherical harmonics, with optional Sun and Moon third bodies from DE421) using an embedded Runge-Kutta pair with error control. Reports the final state, step statistics and relative drift of the two-body energy and angular momentum. With `compare_analytic`, a two-body run is also compared against the exact Kepler solution.

## Limitations

- Earth-centred orbits only; drag, SRP, tides and relativity are not modelled.
- `compare_analytic` is meaningful only for a point-mass (two-body) configuration.
