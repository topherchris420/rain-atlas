---
name: kepler-reference
description: Closed-form two-body propagation and the classical elements of the result. Use for two-body tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Kepler Reference

Propagates a two-body state by the universal-variable / difference-form Kepler solution (exact, no numerical integration) and returns the resulting state and its classical orbital elements. Serves as the analytic truth other skills check against.

## Limitations

- Bound (elliptic) orbits; parabolic and hyperbolic arcs use the universal formulation but are not exercised here.
- Point-mass gravity only, by definition.
