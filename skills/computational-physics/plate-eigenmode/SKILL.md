---
name: plate-eigenmode
description: Simply supported rectangular thin-plate eigenmodes with material-derived frequencies. Use for reproducible numerical studies.
license: MIT
---

# plate-eigenmode

Simply supported rectangular thin-plate eigenmodes with material-derived frequencies.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test plate-eigenmode`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Kirchhoff-Love thin, homogeneous isotropic plate; small displacement, simply supported edges.
- Not free-edge Chladni plates, fluid cymatics, granular transport, damping or nonlinear response. Nodal plots alone do not validate those phenomena.

No calibrated uncertainty or empirical validation is implied by a plot.
