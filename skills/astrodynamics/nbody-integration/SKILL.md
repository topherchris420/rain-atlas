---
name: nbody-integration
description: Integrate a self-gravitating N-body system (figure-eight choreography or a DE421 subset). Use for nbody tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Nbody Integration

Integrates a self-gravitating system of point masses. The `figure-eight` system is the Chenciner-Montgomery equal-mass three-body choreography, whose return to its initial configuration after one period and conservation of energy, momentum and barycentre are exacting tests. The `de421` system integrates the major bodies from JPL DE421 initial conditions and compares back against the ephemeris.

## Limitations

- Newtonian point masses; no relativity, oblateness or asteroid perturbations (the DE421 residual).
- `return_error` is defined only for a whole number of periods.
