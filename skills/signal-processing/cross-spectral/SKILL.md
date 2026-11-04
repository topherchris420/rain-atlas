---
name: cross-spectral
description: Welch multichannel cross PSD and magnitude-squared coherence with undefined-bin mask. Use for reproducible numerical studies.
license: MIT
---

# cross-spectral

Welch multichannel cross PSD and magnitude-squared coherence with undefined-bin mask.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test cross-spectral`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Stationary uniformly sampled channels and >=3 segments; coherence has finite-sample bias.
- CSD convention conj(X)*Y. Common drive and leakage are not causal interaction; zero-power bins are explicitly undefined.

No calibrated uncertainty or empirical validation is implied by a plot.
