---
name: fir-identification
description: Least-squares FIR system identification, residual diagnostics and conditional covariance. Use for reproducible numerical studies.
license: MIT
---

# fir-identification

Least-squares FIR system identification, residual diagnostics and conditional covariance.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test fir-identification`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Linear time-invariant causal FIR, persistently exciting noise-free input; IID response residuals for covariance.
- Rank deficiency and condition number >1e10 are rejected; errors in variables and colored residuals invalidate covariance.

No calibrated uncertainty or empirical validation is implied by a plot.
