---
name: trajectory-comparison
description: Position/velocity and radial-transverse-normal error statistics against a reference trajectory. Use for trajectory-comparison tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Trajectory Comparison

Propagates an orbit and reports position and velocity error norms, and the radial/transverse/normal breakdown, against a reference trajectory sampled at the same times. The reference may be an explicit array or `self` (an identity check that must return exactly zero).

## Limitations

- The reference must be sampled at the configuration's output times.
- Agreement between two models is consistency, not physical validation.
