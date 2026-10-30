---
name: sinusoid-fit
description: Estimate the number, frequencies, amplitudes and phases of sinusoids in a signal by nonlinear least squares with BIC model-order selection. Use as an independent check on periodogram-based frequency estimates, or when you need frequency standard errors.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: mathematics
---
# Sinusoid fit (variable-projection NLS + BIC)

Numerical optimisation of the model `c + sum_i a_i cos(2 pi f_i t + phi_i)`:

1. Candidate frequency from the largest peak of a zero-padded full-length
   periodogram of the current residual (not Welch, so the method is
   independent of `spectral-peaks`).
2. Joint refit of all frequencies with `scipy.optimize.least_squares`; linear
   weights solved exactly at each step (variable projection).
3. Add tones while the Bayesian information criterion decreases.

Returns per realization: frequencies, Gauss-Newton standard errors,
amplitudes, phases, residual standard deviation and the BIC path.

## Limitations

- Greedy order selection can miss a weak tone next to a strong one.
- BIC does not account for the search over frequency, so pure noise sometimes
  yields a spurious tone: 6 of 300 white-noise realizations (2.0%, N = 8192)
  in a development measurement. Require consistency across realizations
  before treating a line as real.
- Standard errors are asymptotic (accurate at moderate-to-high SNR); in a
  development check they matched the empirical spread and the Cramér-Rao
  bound to within about 15% at SNR_ref +20 and 0 dB.
