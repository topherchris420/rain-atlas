---
name: spike-train-statistics
description: Compute standard descriptive statistics of neuronal spike trains (firing rate, inter-spike-interval mean and coefficient of variation, Fano factor of spike counts, refractory violations). Use for quality control and description of recorded or simulated spike times; it makes no physiological or clinical inference.
license: MIT
compatibility: Requires Python 3.11+ with numpy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: neuroscience
---
# Spike-train statistics

For each train (spike times in seconds within `[0, duration_s]`):

- mean rate `n / duration`;
- inter-spike intervals (ISI): mean, coefficient of variation `CV = std/mean`
  (≈ 1 for a Poisson process, 0 for a perfectly regular train);
- Fano factor of spike counts in windows of `window_s` (≈ 1 for Poisson);
- refractory violations: ISIs shorter than `refractory_s` (a common
  spike-sorting quality check).

These are descriptive statistics of the input numbers. They do not identify
cell types, diagnose anything, or say anything about cognition.

## Limitations

- Assumes stationarity within the recording.
- CV and Fano factor are biased for short trains (few spikes).
