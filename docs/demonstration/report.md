# Synchronization under noise and model uncertainty

5 of 30 conditions supported operational locking; 10 unresolved. This establishes only finite-window behavior of the specified synthetic model.

Protocol: atlas.synchronization/v1. Preregistration: sha256:f23353ad3b7ac5c9da44fef9cb79342ba7d0944592595c09aba95af6c6984770.

## Preregistered design

```json
{
  "replicates": 12,
  "dt": 0.04,
  "duration_s": 60,
  "burn_s": 20,
  "seed": 20261104,
  "figures": true,
  "couplings": [
    0,
    0.6,
    1.0,
    1.4,
    2.0
  ],
  "diffusions": [
    0,
    0.08,
    0.5
  ],
  "phase_lags": [
    0,
    0.6
  ],
  "protocol": "atlas.synchronization/v1",
  "budget": {
    "max_runs": 20,
    "max_seconds": 3600
  },
  "reference": "delta'=1-K*cos(lag)*sin(delta); asymptotic deterministic locking iff K*cos(lag)>1",
  "decision": "Primary PLV lower simultaneous CI >0.90; independent block-frequency upper CI <0.05 rad/s; new-data replicate PLV lower CI >0.90; exact reproduction required",
  "negative": "PLV upper CI <0.50 or independent drift lower CI >0.15 rad/s contradicts operational locking; intermediate evidence unresolved",
  "intervals": "two metric families, Bonferroni across all conditions; Student-t across independent trajectories",
  "controls": "K=0 negative, D=0 and K=2 positive; phase lag and D>0 challenge model assumptions",
  "replicate_seed": 20361104
}
```

## Findings

| K (rad/s) | D (rad²/s) | lag (rad) | PLV [simultaneous CI] | drift rad/s | verdict | reference |
|---|---|---|---|---|---|---|
| 0.0 | 0.0 | 0.0 | 0.0460 [0.0460, 0.0460] | 1.0000 | contradicted | False |
| 0.6 | 0.0 | 0.0 | 0.3406 [0.3281, 0.3532] | 0.7928 | contradicted | False |
| 1.0 | 0.0 | 0.0 | 0.9998 [0.9998, 0.9999] | 0.0017 | supported | None |
| 1.4 | 0.0 | 0.0 | 1.0000 [1.0000, 1.0000] | 0.0000 | supported | True |
| 2.0 | 0.0 | 0.0 | 1.0000 [1.0000, 1.0000] | 0.0000 | supported | True |
| 0.0 | 0.08 | 0.0 | 0.0714 [0.0221, 0.1207] | 0.9883 | contradicted | None |
| 0.6 | 0.08 | 0.0 | 0.3296 [0.2194, 0.4397] | 0.7661 | contradicted | None |
| 1.0 | 0.08 | 0.0 | 0.6061 [0.4720, 0.7403] | 0.4830 | unresolved | None |
| 1.4 | 0.08 | 0.0 | 0.8829 [0.7945, 0.9714] | 0.1561 | unresolved | None |
| 2.0 | 0.08 | 0.0 | 0.9453 [0.9277, 0.9629] | 0.0854 | unresolved | None |
| 0.0 | 0.5 | 0.0 | 0.0960 [0.0057, 0.1863] | 1.0825 | contradicted | None |
| 0.6 | 0.5 | 0.0 | 0.1901 [0.0900, 0.2901] | 0.9646 | contradicted | None |
| 1.0 | 0.5 | 0.0 | 0.3129 [0.1313, 0.4946] | 0.9439 | contradicted | None |
| 1.4 | 0.5 | 0.0 | 0.4169 [0.2501, 0.5838] | 0.7308 | unresolved | None |
| 2.0 | 0.5 | 0.0 | 0.6264 [0.5300, 0.7227] | 0.5003 | unresolved | None |
| 0.0 | 0.0 | 0.6 | 0.0460 [0.0460, 0.0460] | 1.0000 | contradicted | False |
| 0.6 | 0.0 | 0.6 | 0.2302 [0.1949, 0.2655] | 0.8980 | contradicted | False |
| 1.0 | 0.0 | 0.6 | 0.5252 [0.4635, 0.5869] | 0.5649 | unresolved | False |
| 1.4 | 0.0 | 0.6 | 1.0000 [1.0000, 1.0000] | 0.0000 | supported | True |
| 2.0 | 0.0 | 0.6 | 1.0000 [1.0000, 1.0000] | 0.0000 | supported | True |
| 0.0 | 0.08 | 0.6 | 0.0661 [0.0325, 0.0997] | 1.0122 | contradicted | None |
| 0.6 | 0.08 | 0.6 | 0.2499 [0.1979, 0.3019] | 0.8778 | contradicted | None |
| 1.0 | 0.08 | 0.6 | 0.5001 [0.3698, 0.6305] | 0.6290 | unresolved | None |
| 1.4 | 0.08 | 0.6 | 0.7346 [0.5846, 0.8847] | 0.3118 | unresolved | None |
| 2.0 | 0.08 | 0.6 | 0.9182 [0.8730, 0.9633] | 0.1127 | unresolved | None |
| 0.0 | 0.5 | 0.6 | 0.1124 [0.0425, 0.1822] | 1.1342 | contradicted | None |
| 0.6 | 0.5 | 0.6 | 0.1706 [0.0744, 0.2667] | 0.9721 | contradicted | None |
| 1.0 | 0.5 | 0.6 | 0.2995 [0.1381, 0.4608] | 0.8536 | contradicted | None |
| 1.4 | 0.5 | 0.6 | 0.3402 [0.1892, 0.4912] | 0.8641 | contradicted | None |
| 2.0 | 0.5 | 0.6 | 0.5589 [0.4361, 0.6817] | 0.5213 | unresolved | None |

## Limitations and negative results

- Synthetic two-oscillator phase model, not physical evidence or an infinite-population phase transition.
- Fixed, published parameters; this study is NOT blinded. The separate spectral experiment retains sealed-truth evaluation.
- PLV is not causal coupling. Equal-frequency uncoupled oscillators can have PLV=1; a known-answer test demonstrates this failure.
- Phase and frequency methods share raw trajectories; independent replication uses different initial conditions and noise seeds, not a different physical model.
- Intervals use independent replicate summaries with approximate Student-t assumptions and Bonferroni correction. No posterior confidence or calibrated probability of truth is claimed.
- Stochastic trajectories use Euler-Maruyama. Numerical convergence tests bound selected cases; this experiment does not prove convergence at every noise level.
- Only deterministic cases away from the analytical threshold have a binary reference truth. Noisy and critical cases remain truth-unavailable for error-rate scoring.
- Thresholds define finite-window operational locking. Failure to meet them may be unresolved and is not proof of an absence of all synchronization.

## Reproduce

```sh
uv run atlas experiment run synchronization --root atlas-data/new-sync --replicates 12
uv run atlas ledger verify atlas-data/new-sync/ledger
```

Each finding's full evidence references and intervals are in summary.json and the ledger. A hash chain establishes internal integrity, not authenticity or truth.
