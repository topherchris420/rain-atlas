---
name: synthetic-tones
description: Generate reproducible multi-tone signals with Gaussian noise for spectral-analysis experiments. Use when an experiment needs a signal with known (and optionally sealed) frequencies, amplitudes and phases at controlled noise levels.
license: MIT
compatibility: Requires Python 3.11+ with numpy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: simulation
---
# Synthetic tones

Generates `realizations` independent signals

    x_r[n] = sum_i A_i cos(2 pi f_i n / fs + phi_i) + e_r[n],   e_r ~ N(0, sigma^2)

and returns them as one `(realizations, n)` float64 array artifact. Noise for
realization `r` comes from `SeedSequence([seed, r])`, so the same seed always
reproduces the same bytes.

The output deliberately does **not** repeat the tone parameters: an experiment
can seal them (store only a salted commitment) and give analysts only the
signal.

## Inputs

- `fs` sampling rate (Hz), `n` samples per realization
- `tones`: list of `{frequency_hz, amplitude, phase_rad}` (may be empty for a
  noise-only negative control)
- `noise_std`, `realizations`

## Limitations

- White Gaussian noise only; no drift, coloured noise or quantisation.
- Ideal sampling (no jitter, no anti-alias filter).
