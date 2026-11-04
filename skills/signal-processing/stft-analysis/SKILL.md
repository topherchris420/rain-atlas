---
name: stft-analysis
description: Hann short-time Fourier power density with complete frames and explicit resolution. Use for reproducible numerical studies.
license: MIT
---

# stft-analysis

Hann short-time Fourier power density with complete frames and explicit resolution.

Inputs and outputs are typed in `skill.json`. Run the analytical example with
`atlas skills test stft-analysis`. Precision and convergence tests are in
`tests/test_resonance.py`; methods, units and independent references are in
`docs/RESONANCE.md`. Arrays are reproducible artifacts with SHA-256 digests.

## Assumptions and failure conditions

- Uniform sampling; no padding or detrending. Window length trades temporal and spectral resolution.
- Density units are input units squared/Hz; visual ridges are not significance tests.

No calibrated uncertainty or empirical validation is implied by a plot.
