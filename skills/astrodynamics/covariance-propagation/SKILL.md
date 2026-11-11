---
name: covariance-propagation
description: Propagate a state covariance through the STM and check it against a Monte-Carlo cloud. Use for covariance-propagation tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Covariance Propagation

Maps an initial covariance to a later time through the state-transition matrix and compares it against a cloud of samples propagated by the analytic Kepler solution. For a small (near-linear) initial uncertainty the chi-square consistency fraction should sit near 0.95.

## Limitations

- The linear map is first-order; large uncertainties show nonlinearity (lower consistency).
- Point-mass dynamics for the Monte-Carlo cloud.
