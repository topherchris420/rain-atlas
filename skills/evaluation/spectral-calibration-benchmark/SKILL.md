---
name: spectral-calibration-benchmark
description: Measure whole-band spectral false alarms and tone localization using independent synthetic noise references.
license: MIT
---

# Spectral calibration benchmark

Run `atlas benchmark --protocol spectral-calibration --root atlas-data/calibration`
for preregistration, a seeded run, exact replay and ledger verification. The
skill compares a Welch threshold with white-only, AR(1)-only and combined
reference models. The examples check configuration. The benchmark reports
measured error rates, including an oscillatory null outside both models.

See [the benchmark protocol](../../../docs/BENCHMARKS.md#held-out-spectral-calibration)
for the rank argument, assumptions and observed limits.
