---
name: morlet-wavelet
description: Corrected complex Morlet multiscale analysis with explicit edge mask. Use for reproducible numerical studies.
license: MIT
---

# morlet-wavelet

Corrected complex Morlet multiscale analysis with explicit edge mask.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test morlet-wavelet`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Coefficients use discrete L2 normalization, not a PSD. Frequencies are nominal centers.
- Zero extension biases edges; mask excludes sqrt(2) scales. Reject frequencies above fs/4.

No calibrated uncertainty or empirical validation is implied by a plot.
