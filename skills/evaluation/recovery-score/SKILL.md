---
name: recovery-score
description: Score per-realization frequency estimates against known true frequencies (recovery rate, bias, standard deviation, RMSE, false detections). Use only after ground truth has been unsealed, to measure how well an analysis recovered it.
license: MIT
compatibility: Requires Python 3.11+ with numpy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: evaluation
---
# Recovery score

Greedy one-to-one matching of estimates to true frequencies within
`tolerance_hz`, per realization. Reports per tone: recovery rate, bias, sample
standard deviation, RMSE and maximum absolute error; and overall: the fraction
of realizations with every tone recovered and the number of false detections.

Optionally, given the true `amplitudes`, `noise_std`, `n` and `fs`, it adds
the Cramér-Rao lower bound on each frequency's standard deviation (Rife &
Boorstyn 1974, single tone in white Gaussian noise) and the ratio of the
observed standard deviation to that bound.

Use after the truth is published (`unseal`) so that analysis could not have
seen it.
