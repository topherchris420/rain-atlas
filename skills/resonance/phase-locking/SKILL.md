---
name: phase-locking
description: Pairwise temporal phase-locking values and instantaneous Kuramoto order. Use for reproducible numerical studies.
license: MIT
---

# phase-locking

Pairwise temporal phase-locking values and instantaneous Kuramoto order.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test phase-locking`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Requires meaningful input phases in radians. No phase extraction from arbitrary broadband signals.
- PLV is biased with finite samples and autocorrelation; common drive and identical uncoupled frequencies give high PLV.

No calibrated uncertainty or empirical validation is implied by a plot.
