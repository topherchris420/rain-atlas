---
name: orbit-determination
description: Batch least-squares orbit determination from synthetic tracking. Use for orbit-determination tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Orbit Determination

Recovers an epoch state from range and range-rate tracking by iterated batch least squares with the state-transition matrix from the force model. On noiseless data this is an identical-twin experiment: the estimate must return to the truth to the numerical floor.

## Limitations

- Needs an observable arc; a short single-station arc leaves a weakly observed direction.
- The dynamics used to simulate and to estimate are the same (a closed experiment).
