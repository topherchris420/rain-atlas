---
name: tone-presence-test
description: Test whether sinusoids at pre-specified frequencies are present in independent replicate signals using a regression F-test with Bonferroni correction. Use to try to falsify claimed spectral lines on data that was not used to find them.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: statistics
---
# Tone presence test (falsification)

For each claimed frequency `f` and each replicate signal:

- H0: offset + the other claimed tones;
- H1: H0 + cosine and sine at `f`;
- `F = ((RSS0 - RSS1) / 2) / (RSS1 / (n - p1))`, p-value from `F(2, n - p1)`.

A claim is **corroborated** when the Bonferroni-corrected test rejects H0 in at
least `min_fraction` of replicates, **contradicted** when it rejects in fewer
than `max_fraction_contradict`, and **inconclusive** otherwise.

Valid only when the frequencies were chosen without using these replicates.

## Limitations

- Assumes white Gaussian residuals.
- A frequency error larger than about `fs / (2 n)` reduces power.
