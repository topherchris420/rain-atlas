---
name: spectral-peaks
description: Estimate a power spectral density with Welch's method and detect spectral lines above a white-noise floor with a family-wise false-alarm rate. Use when you need the dominant frequencies of a sampled signal and a statistically controlled detection decision.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: signal-processing
---
# Spectral peaks (Welch + chi-square detection)

1. Welch PSD: periodic Hann window, mean-detrended segments, configurable
   overlap. The equivalent degrees of freedom `edof` account for overlap.
2. Noise floor: `median(PSD) / (median(chi2_edof) / edof)` (robust to a few lines).
3. Threshold: Bonferroni over the searched bins, so pure white noise produces
   any false line with probability ≈ `alpha`.
4. Local maxima above threshold, separated by `min_separation_hz`, refined by
   parabolic interpolation of the log-PSD.

Accepts a `(realizations, n)` array artifact and returns peaks per realization
plus the mean PSD (artifact) for plotting.

## Limitations

- Assumes locally white noise around each line; coloured noise inflates false
  alarms where the PSD is high.
- Lines closer than about two frequency bins (`2 fs / nperseg`) merge.
- Parabolic interpolation has a small bias (well under 0.1 bin for a Hann window).
