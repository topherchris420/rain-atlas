---
name: adaptive-filter
description: Causal LMS and normalized LMS adaptive filtering with recorded residuals. Use for reproducible numerical studies.
license: MIT
---

# adaptive-filter

Causal LMS and normalized LMS adaptive filtering with recorded residuals.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test adaptive-filter`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Plain LMS stability depends on input covariance and step size; correlated references can remove desired signal.
- Weights are estimates, not calibrated uncertainties. Divergence is an explicit error.

No calibrated uncertainty or empirical validation is implied by a plot.
