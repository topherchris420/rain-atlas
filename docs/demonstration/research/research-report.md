# Detecting and explaining hidden change in a noisy driven oscillator

> **Question.** Can an intelligent experimental system detect previously unknown changes in a noisy dynamical system, determine what changed, and develop a better explanatory model using fewer experiments than conventional methods?

**Answer: SUPPORTED (with conditions).** Supported: Do observation-dependent decisions themselves help (closed loop vs yoked control)?; Fewer experiments than conventional methods?; Detect previously unknown changes and determine what changed?; Develop a better explanatory model?.  Conditions: safety (H3) is unresolved: 10 false conclusions (5.0%, adjusted interval 1.5%–10.9%) against a 5 % bound. Bounded to the simulated oscillator family, the approved design space and the stated priors.

| Part of the question | Preregistered test | Verdict |
|---|---|---|
| Do observation-dependent decisions themselves help (closed loop vs yoked control)? | H1 | **supported** |
| Fewer experiments than conventional methods? | H2 | **supported** |
| Detect previously unknown changes and determine what changed? | H4 | **supported** |
| Develop a better explanatory model? | H7 | **supported** |

This is a computational investigation of a simulated apparatus. Verdicts are bounded to the simulated oscillator family, the approved design space and the stated priors; they are not claims about physical systems.

## Scope approved by the operator

- Experiments per mission: 16; featured missions: 5; benchmark problems per family: 50; model calls: 40.
- Environment: in-process-simulation; network False; hardware control False; untrusted code False; model provider none.
- Design space: {"amplitude": [0.0, 1.5], "frequency": [0.3, 2.5], "x0": [-1.0, 1.0]}. Hypothesis grammar: core ['x', 'v', 'u'], anticipated ['x^3', '1'], admissible by the critic ['x^2', 'x^2*v', 'v*|v|', 'x*u', 'v^3'].
- Stopping rule: {"attribution_probability": 0.9, "challenge_experiments": 2, "decision_probability": 0.95, "futility_min_experiments": 8, "futility_nats": 0.005, "futility_patience": 3, "min_experiments": 2}.

## 1. Investigating the question: methods and baselines

Advisor: scripted retrieval (scripted). retrieval over a curated method catalog and the installed skill catalog; not open-ended literature research.

| Sub-question | Cues |
|---|---|
| Has the system changed, and when? | detect, unknown |
| Which part of the dynamics changed? | changed, determine, what |
| Which model structure explains the observations? | better, develop, explanatory, model |
| Does adaptive selection need fewer experiments than conventional designs? | conventional, experiments, fewer |
| How much of the variation is noise, and is the noise model right? | noisy |

| Method | Answers | Implemented by |
|---|---|---|
| Exact Bayesian model evidence (Normal-Inverse-Gamma linear regression) | explain, efficiency | `rain_atlas.research.inference` |
| Bayesian change-point and attribution hypotheses | detect-change, attribute-change | `rain_atlas.research.inference` |
| Sequential Bayesian experimental design (expected information gain) | efficiency | `rain_atlas.research.planner` |
| Score (Lagrange-multiplier) test for omitted terms | explain | `rain_atlas.research.critic` |
| Ljung-Box residual whiteness test | explain | `rain_atlas.research.critic` |
| Kurtosis test of the Gaussian-noise assumption | noise | `rain_atlas.research.critic` |
| Huber M-estimation (robust regression) | explain, noise | `rain_atlas.research.critic` |
| Leave-experiments-out cross-validated prediction | explain | `rain_atlas.research.critic` |
| Chow test for coefficient equality across segments | detect-change, attribute-change | `rain_atlas.research.critic` |
| Sequential D-optimal design under the prior (open loop) | efficiency | `rain_atlas.research.planner` |
| Stepped-sine frequency sweep (fixed schedule) | efficiency | `rain_atlas.research.planner` |
| Linear least-squares system identification (conventional model) | explain | `rain_atlas.research.benchmark` |

Related catalogued skills (retrieval score): `fir-identification` (3.333), `lyapunov-exponent` (2.355), `nbody-integration` (2.097), `sinusoid-fit` (1.808).

## 2. Competing hypotheses

| | Hypothesis | Null |
|---|---|---|
| H1 | Observation dependence: on held-out problems the closed loop reaches correct conclusions with fewer experiments (censored efficiency) than the yoked control, which replays the closed loop's own designs from a different problem. | Selection that depends on this problem's observations is no better than the same designs replayed from another problem. |
| H2 | Against conventional selection: the closed loop's censored efficiency is better than each of the open-loop D-optimal design, the fixed stepped-sine sweep, random designs and the existing ATLAS rule. | The closed loop is no more efficient than at least one conventional design. |
| H3 | Safety: the closed loop's false-conclusion rate is at most 5 %. | The closed loop's false-conclusion rate exceeds 5 %. |
| H4 | Change: in hidden-change problems the closed loop identifies the change (location and attribution) more often than the fixed sweep. | The closed loop identifies changes no more often than the fixed sweep. |
| H5 | Unanticipated dynamics: in unfamiliar problems the closed loop reaches the correct conclusion, including the unanticipated term, more often than the fixed sweep. | The closed loop finds unanticipated terms no more often than the fixed sweep. |
| H6 | Calibration: the closed loop's one-step 90 % predictive intervals cover between 85 % and 95 % of held-out rows on unseen conditions. | The closed loop's predictive intervals are miscalibrated on unseen conditions. |
| H7 | Explanatory model: the closed loop's final model has lower held-out predictive regret than a conventional linear least-squares model fitted to the same data. | The closed loop's model predicts unseen conditions no better than a linear least-squares model. |

Within each mission the competing explanations are model structures: anticipated {x, v, u}, {x, v, u, x^3}, {x, v, u, 1}, {x, v, u, x^3, 1}; unanticipated terms the critic may admit: x^2, x^2*v, v*|v|, x*u, v^3; and change hypotheses (at most one change per mission: a shift of any term, a joint shift, or the onset of an anticipated term).

## 3. Preregistration

Recorded as `sha256:f070910723bad579b137154fc2b46425412681c4c737e7c7e467f2ec7ea4f48d` before any experiment, with research source hash `sha256:c579a025c22aff2ad5e8fe9b075e91efd3c83aa36f903223c4e5724628f12703`. The featured apparatus parameters were sealed first (5 commitments). Held-out split seed 5380771, 50 problems per family, arms closed-loop, yoked, open-loop-optimal, fixed-sweep, random, legacy-atlas, closed-loop-no-critic, closed-loop-no-challenge; Bonferroni α = 0.05/7.

## 4. Featured investigations

Five apparatus fixed before the investigation ran, chosen to exercise each mechanism. Their outcomes are reported as they happened; the benchmark below, not these five, is the evidence for the program-level claims.

### M1-characterize — first characterization of an unfamiliar apparatus

Apparatus `bench-A`. Stopped: **decision-challenged** after 4 experiments. Verdict: **supported** — independent estimator agrees; replicate test rejects absence; reproduced exactly.

| # | Purpose | Design | Why | Predicted 90% | Observed | Surprise z | Info gained (nats) |
|---|---|---|---|---|---|---|---|
| 1 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.000 nats about 4 competing explanations + 6.481 nats about their coefficients; candidate origin: pool | — | 0.97 | — | 0.88 |
| 2 | explore | A=1.31, Ω=1.52, x0=-0.12 | maximizes expected information: 0.138 nats about 3 competing explanations + 1.974 nats about their coefficients; candidate origin: pool | 1.61–2.09 | 1.76 | -1.5 | 0.03 |
| 3 | challenge | A=1.36, Ω=2.17, x0=+0.52 | unvisited condition where the leading explanation and its neighbours disagree most (0.709 nats with rivals weighted equally) | 0.36–0.80 | 0.45 | 0.5 | -0.16 |
| 4 | challenge | A=1.41, Ω=0.87, x0=-0.76 | sentinel: re-measures the first experiment's condition to test that the system has not changed during the mission | 0.75–1.01 | 0.82 | -0.4 | -0.01 |

Challenges (prediction recorded before each ran):

- experiment 3 (novel-condition): **corroborated** (z = 0.55, Chow p = 0.366)
- experiment 4 (sentinel): **corroborated** (z = -0.42, Chow p = 0.574)

Conclusion: structure {x, v, u, x^3} (P = 0.984); x = -1.362 ± 0.072, v = -0.164 ± 0.028, u = +0.940 ± 0.048, x^3 = -0.371 ± 0.019; P(change) = 0.090. Memory: absent.

Revealed truth: f = -1.3·x -0.16·v +1·u -0.4·x^3. Structure correct.

### M2-hidden-change — a stiffness drop at an unannounced experiment

Apparatus `bench-B`. Stopped: **decision-challenged** after 6 experiments. Verdict: **supported** — independent estimator agrees; replicate test rejects absence; reproduced exactly.

| # | Purpose | Design | Why | Predicted 90% | Observed | Surprise z | Info gained (nats) |
|---|---|---|---|---|---|---|---|
| 1 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.000 nats about 4 competing explanations + 6.481 nats about their coefficients; candidate origin: pool | — | 2.70 | — | 0.53 |
| 2 | explore | A=1.5, Ω=1.04, x0=+0 | maximizes expected information: 0.513 nats about 4 competing explanations + 1.990 nats about their coefficients; candidate origin: estimated resonance | 2.37–3.55 | 3.28 | -0.9 | 0.48 |
| 3 | challenge | A=0.984, Ω=0.707, x0=-0.28 | unvisited condition where the leading explanation and its neighbours disagree most (0.694 nats with rivals weighted equally) | 1.03–1.83 | 3.23 ✗ | 4.7 | 0.04 |
| 4 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.193 nats about 3 competing explanations + 1.893 nats about their coefficients; candidate origin: pool | 3.37–4.48 | 3.58 | -1.4 | 0.05 |
| 5 | challenge | A=0.562, Ω=0.789, x0=-0.52 | unvisited condition where the leading explanation and its neighbours disagree most (0.885 nats with rivals weighted equally) | 1.27–2.27 | 1.33 | 0.2 | 0.01 |
| 6 | challenge | A=1.41, Ω=0.87, x0=-0.76 | sentinel: re-measures the first experiment's condition to test that the system has not changed during the mission | 3.37–4.37 | 3.60 | -0.9 | -0.00 |

Where the understanding changed:

- *hypothesis-rejected* — challenge at experiment 3 contradicted {x, v, u, 1}; returning to exploration with the new data

Challenges (prediction recorded before each ran):

- experiment 3 (novel-condition): **contradicted** (z = 4.66, Chow p = 0.000)
- experiment 5 (novel-condition): **corroborated** (z = 0.20, Chow p = 0.120)
- experiment 6 (sentinel): **corroborated** (z = -0.86, Chow p = 0.459)

Conclusion: structure {x, v, u, 1} (P = 0.998); x = -0.712 ± 0.016, v = -0.259 ± 0.033, u = +1.024 ± 0.084, 1 = +0.273 ± 0.033; P(change) = 1.000; change before experiment 3 in x. Memory: absent.

Revealed truth: f = -0.72·x -0.2·v +0.9·u +0.25·1; change before experiment 3. Structure correct.

### M3-unanticipated — dynamics outside the anticipated hypotheses

Apparatus `bench-C`. Stopped: **decision-challenged** after 5 experiments. Verdict: **supported** — independent estimator agrees; replicate test rejects absence; reproduced exactly.

| # | Purpose | Design | Why | Predicted 90% | Observed | Surprise z | Info gained (nats) |
|---|---|---|---|---|---|---|---|
| 1 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.000 nats about 4 competing explanations + 6.481 nats about their coefficients; candidate origin: pool | — | 1.85 | — | 0.83 |
| 2 | explore | A=0.984, Ω=0.707, x0=-0.28 | maximizes expected information: 0.015 nats about 4 competing explanations + 1.875 nats about their coefficients; candidate origin: pool | 1.12–1.55 | 1.39 | 0.8 | -0.13 |
| 3 | explore | A=1.12, Ω=0.544, x0=+0.2 | maximizes expected information: 0.039 nats about 4 competing explanations + 1.165 nats about their coefficients; candidate origin: pool | 1.01–1.56 | 1.20 | 0.8 | 0.00 |
| 4 | challenge | A=1.31, Ω=1.52, x0=-0.12 | unvisited condition where the leading explanation and its neighbours disagree most (0.985 nats with rivals weighted equally) | 0.63–1.07 | 0.79 | -0.5 | 0.01 |
| 5 | challenge | A=1.41, Ω=0.87, x0=-0.76 | sentinel: re-measures the first experiment's condition to test that the system has not changed during the mission | 1.66–1.94 | 1.82 | -0.4 | 0.01 |

Where the understanding changed:

- *hypothesis-expansion* — admitted unanticipated term v*|v| alongside x^2*v so evidence can separate them
- *hypothesis-expansion* — admitted unanticipated term x^2*v into the working hypotheses

Challenges (prediction recorded before each ran):

- experiment 4 (novel-condition): **corroborated** (z = -0.54, Chow p = 0.394)
- experiment 5 (sentinel): **corroborated** (z = -0.38, Chow p = 0.486)

Conclusion: structure {x, v, u, x^2*v} (P = 0.972); x = -1.025 ± 0.027, v = -0.067 ± 0.043, u = +1.100 ± 0.056, x^2*v = -0.328 ± 0.019; P(change) = 0.070. Memory: absent.

Revealed truth: f = -1·x -0.12·v +1.1·u -0.3·x^2*v. Structure correct.

### M4-returning — bench-A again, after an unrecorded repair

Apparatus `bench-A`. Stopped: **decision-challenged** after 6 experiments. Verdict: **supported** — independent estimator agrees; replicate test rejects absence; reproduced exactly.

| # | Purpose | Design | Why | Predicted 90% | Observed | Surprise z | Info gained (nats) |
|---|---|---|---|---|---|---|---|
| 1 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.000 nats about 4 competing explanations + 6.481 nats about their coefficients; candidate origin: pool | — | 1.04 | — | 1.11 |
| 2 | explore | A=0.75, Ω=1.03, x0=-0.6 | maximizes expected information: 0.003 nats about 2 competing explanations + 1.034 nats about their coefficients; candidate origin: pool | 0.90–1.31 | 1.08 | 2.0 | -0.11 |
| 3 | challenge | A=1.5, Ω=1.04, x0=+1 | unvisited condition where the leading explanation and its neighbours disagree most (0.856 nats with rivals weighted equally) | 1.21–1.43 | 1.29 | -0.4 | -0.02 |
| 4 | challenge | A=1.41, Ω=0.87, x0=-0.76 | sentinel: re-measures the first experiment's condition to test that the system has not changed during the mission | 0.89–1.10 | 1.14 ✗ | -0.6 | -0.25 |
| 5 | challenge | A=1.45, Ω=1.3, x0=-0.504 | unvisited condition where the leading explanation and its neighbours disagree most (0.868 nats with rivals weighted equally) | 1.40–1.60 | 1.44 | 2.3 | 0.05 |
| 6 | challenge | A=1.41, Ω=0.87, x0=-0.76 | sentinel: re-measures the first experiment's condition to test that the system has not changed during the mission | 0.96–1.11 | 1.08 | 0.5 | -0.04 |

Where the understanding changed:

- *memory-quarantine* — fresh evidence contradicts the remembered characterization of bench-A: v (remembered -0.164, fresh -0.391); it no longer informs this mission

Challenges (prediction recorded before each ran):

- experiment 3 (novel-condition): **corroborated** (z = -0.41, Chow p = 0.833)
- experiment 4 (sentinel): **inconclusive** (z = -0.61, Chow p = 0.275)
- experiment 5 (novel-condition): **corroborated** (z = 2.29, Chow p = 0.990)
- experiment 6 (sentinel): **corroborated** (z = 0.46, Chow p = 0.735)

Conclusion: structure {x, v, u, x^3} (P = 0.985); x = -1.012 ± 0.081, v = -0.395 ± 0.037, u = +1.110 ± 0.076, x^3 = -0.403 ± 0.023; P(change) = 0.089. Memory: quarantined.

Revealed truth: f = -0.92·x -0.34·v +1·u -0.4·x^3. Structure correct.

### M5-noise-limited — a small offset under heavy noise

Apparatus `bench-D`. Stopped: **budget-exhausted** after 14 experiments. Verdict: **unresolved** — stopped without a decision (budget-exhausted); leading structure probability 0.623 < 0.95; possible change under investigation (P(change) = 0.375).

| # | Purpose | Design | Why | Predicted 90% | Observed | Surprise z | Info gained (nats) |
|---|---|---|---|---|---|---|---|
| 1 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.000 nats about 4 competing explanations + 6.481 nats about their coefficients; candidate origin: pool | — | 1.48 | — | 0.11 |
| 2 | explore | A=1.5, Ω=1.53, x0=+0 | maximizes expected information: 0.780 nats about 4 competing explanations + 2.694 nats about their coefficients; candidate origin: estimated resonance | 0.84–5.32 | 1.81 | -0.8 | 0.31 |
| 3 | explore | A=1.45, Ω=1.3, x0=-0.504 | maximizes expected information: 0.255 nats about 4 competing explanations + 0.910 nats about their coefficients; candidate origin: pool | 0.82–1.93 | 1.17 | -0.4 | -0.12 |
| 4 | explore | A=1.45, Ω=1.3, x0=-0.504 | maximizes expected information: 0.068 nats about 4 competing explanations + 0.686 nats about their coefficients; candidate origin: pool | 0.81–1.79 | 1.38 | -1.0 | -0.09 |
| 5 | explore | A=1.5, Ω=1.27, x0=+0 | maximizes expected information: 0.094 nats about 4 competing explanations + 0.576 nats about their coefficients; candidate origin: estimated resonance | 0.62–1.82 | 0.72 | 2.2 | -0.30 |
| 6 | explore | A=1.45, Ω=1.3, x0=-0.504 | maximizes expected information: 0.525 nats about 4 competing explanations + 0.528 nats about their coefficients; candidate origin: pool | 0.77–1.69 | 1.16 | -1.8 | -0.18 |
| 7 | explore | A=1.5, Ω=1.27, x0=+0 | maximizes expected information: 0.317 nats about 4 competing explanations + 0.416 nats about their coefficients; candidate origin: replication (change sentinel) | 0.66–1.53 | 1.17 | 1.2 | 0.08 |
| 8 | explore | A=1.5, Ω=1.27, x0=+0 | maximizes expected information: 0.377 nats about 4 competing explanations + 0.371 nats about their coefficients; candidate origin: replication (change sentinel) | 0.88–1.57 | 1.05 | -0.7 | 0.25 |
| 9 | explore | A=1.5, Ω=1.32, x0=+1 | maximizes expected information: 0.179 nats about 4 competing explanations + 0.301 nats about their coefficients; candidate origin: estimated resonance, displaced | 0.80–1.70 | 1.18 | -1.3 | 0.12 |
| 10 | explore | A=1.5, Ω=1.27, x0=+0 | maximizes expected information: 0.035 nats about 4 competing explanations + 0.295 nats about their coefficients; candidate origin: replication (change sentinel) | 0.73–1.41 | 1.16 | 1.0 | -0.26 |
| 11 | explore | A=1.41, Ω=0.87, x0=-0.76 | maximizes expected information: 0.182 nats about 4 competing explanations + 0.196 nats about their coefficients; candidate origin: pool | 0.59–1.11 | 1.09 | 1.3 | -0.06 |
| 12 | explore | A=1.5, Ω=1.36, x0=+0 | maximizes expected information: 0.101 nats about 4 competing explanations + 0.273 nats about their coefficients; candidate origin: estimated resonance | 0.81–1.45 | 1.90 ✗ | 0.0 | -0.06 |
| 13 | explore | A=1.5, Ω=1.36, x0=+0 | maximizes expected information: 0.000 nats about 4 competing explanations + 0.315 nats about their coefficients; candidate origin: replication (change sentinel) | 1.01–1.75 | 0.86 ✗ | -1.2 | 0.02 |
| 14 | explore | A=1.31, Ω=1.52, x0=-0.12 | maximizes expected information: 0.125 nats about 4 competing explanations + 0.209 nats about their coefficients; candidate origin: pool | 0.84–1.81 | 1.90 ✗ | -0.4 | -0.02 |

Conclusion: structure {x, v, u, x^3, 1} (P = 0.623); x = -1.775 ± 0.119, v = -0.354 ± 0.049, u = +0.857 ± 0.098, x^3 = -0.199 ± 0.026, 1 = +0.225 ± 0.068; P(change) = 0.375. Memory: absent.

Revealed truth: f = -1.6·x -0.3·v +0.8·u -0.2·x^3 +0.08·1. Structure correct.

Escalation pending: `1c18a7c0bbaed1b4` — the experiment budget ended before the stopping rule was met; the best remaining design was still expected to yield 0.334 nats. Authorize with `atlas research authorize --root <root> --request 1c18a7c0bbaed1b4 --operator NAME`, then `atlas research resume --root <root>`.

## 5. Benchmark on held-out problems

| Arm | Censored experiments | Experiments used | Correct | False | Unresolved | Coverage 90% | Regret (nats/row) |
|---|---|---|---|---|---|---|---|
| ATLAS closed loop | 9.26 [8.660, 9.865] | 8.03 | 0.65 | 0.050 | 0.30 | 0.894 | 0.050 |
| Yoked control (same designs, other problem) | 10.39 [9.715, 11.070] | 9.11 | 0.52 | 0.035 | 0.45 | 0.894 | 0.050 |
| Open-loop D-optimal design | 10.11 [9.500, 10.745] | 8.75 | 0.57 | 0.045 | 0.37 | 0.894 | 0.050 |
| Fixed stepped-sine sweep | 13.06 [12.495, 13.655] | 11.13 | 0.28 | 0.025 | 0.67 | 0.894 | 0.052 |
| Random designs | 12.77 [12.140, 13.390] | 11.01 | 0.30 | 0.025 | 0.66 | 0.894 | 0.052 |
| Existing ATLAS rule (rain central v2, ported) | 13.26 [12.620, 13.900] | 11.67 | 0.29 | 0.110 | 0.49 | 0.904 | 0.055 |
| Ablation: no critic | 10.41 [9.915, 10.940] | 9.03 | 0.55 | 0.045 | 0.41 | 0.904 | 0.043 |
| Ablation: no challenge | 6.16 [5.480, 6.860] | 4.28 | 0.74 | 0.110 | 0.12 | 0.896 | 0.045 |

By family (closed loop vs the strongest conventional design, open-loop D-optimal; censored experiments):

| Family | Closed loop | Yoked | Open-loop D-optimal | Fixed sweep | Change identified (CL) | Discovery (CL) |
|---|---|---|---|---|---|---|
| hidden-change | 12.32 | 13.38 | 12.82 | 15.28 | 0.64 | 0.00 |
| stationary | 6.48 | 7.96 | 7.14 | 11.14 | 0.00 | 0.00 |
| unfamiliar | 12.12 | 13.08 | 13.90 | 15.60 | 0.00 | 0.36 |
| wrong-assumptions | 6.10 | 7.16 | 6.58 | 10.24 | 0.00 | 0.00 |

### Preregistered hypotheses

| | Hypothesis | Estimate | Adjusted interval | Verdict |
|---|---|---|---|---|
| **H1** | Observation dependence: on held-out problems the closed loop reaches correct conclusions with fewer experiments (censored efficiency) than the yoked control, which replays the closed loop's own designs from a different problem. | -1.140 | [-1.845, -0.450] | **supported** |
| H2 vs open-loop-optimal | closed loop − open-loop-optimal (censored experiments) | -0.85 | [-1.645, -0.095] | supported |
| H2 vs fixed-sweep | closed loop − fixed-sweep (censored experiments) | -3.81 | [-4.775, -2.875] | supported |
| H2 vs random | closed loop − random (censored experiments) | -3.51 | [-4.486, -2.555] | supported |
| H2 vs legacy-atlas | closed loop − legacy-atlas (censored experiments) | -4.00 | [-5.193, -2.729] | supported |
| **H2** | Against conventional selection: the closed loop's censored efficiency is better than each of the open-loop D-optimal design, the fixed stepped-sine sweep, random designs and the existing ATLAS rule. | | | **supported** |
| **H3** | Safety: the closed loop's false-conclusion rate is at most 5 %. | +0.050 | [0.015, 0.109] | **unresolved** |
| **H4** | Change: in hidden-change problems the closed loop identifies the change (location and attribution) more often than the fixed sweep. | +0.460 | [0.280, 0.640] | **supported** |
| **H5** | Unanticipated dynamics: in unfamiliar problems the closed loop reaches the correct conclusion, including the unanticipated term, more often than the fixed sweep. | +0.320 | [0.160, 0.500] | **supported** |
| **H6** | Calibration: the closed loop's one-step 90 % predictive intervals cover between 85 % and 95 % of held-out rows on unseen conditions. | +0.894 | [0.891, 0.896] | **supported** |
| **H7** | Explanatory model: the closed loop's final model has lower held-out predictive regret than a conventional linear least-squares model fitted to the same data. | -0.115 | [-0.188, -0.062] | **supported** |

False alarms on problems without a change: 0/150. Stale memories quarantined: 13/19; correct memories kept: 10/10. Confident errors (posterior ≥ 0.9 on a wrong structure at some step): 41, recovered without a false conclusion: 33. Brier score of the reported structure probability: 0.064. Mean wall time per mission: 1.87 s (conventional arms 0.54 s).

Reproduction: 64/64 rerun missions produced identical digests.

### Ablations

- Ablation: no critic: censored experiments 10.41, false conclusions 0.045, unfamiliar-family correct 0.00 (full closed loop 0.36).
- Ablation: no challenge: censored experiments 6.16, false conclusions 0.110, unfamiliar-family correct 0.44 (full closed loop 0.36).

## 6. What failed, and what remains unknown

- M5-noise-limited: not established — stopped without a decision (budget-exhausted); leading structure probability 0.623 < 0.95; possible change under investigation (P(change) = 0.375).
- H3 is **unresolved**: Safety: the closed loop's false-conclusion rate is at most 5 %.
- The closed loop reached no supported conclusion in 30% of held-out missions within 16 experiments, and made 10 false conclusions (5.0%).
- False conclusions in the hidden-change family: 3/50 (duffing · change onset-1 at experiment 4; duffing · change stiffness at experiment 2).
- False conclusions in the unfamiliar family: 7/50 (duffing + v^3; duffing + x^2; linear + v^3).
- Unanticipated terms, closed loop: `v^3` 0 correct, 6 false, 15 unresolved; `x*u` 11 correct, 0 false, 4 unresolved; `x^2` 7 correct, 1 false, 6 unresolved. A term that the score test never proposes is never in the working set, so the posterior (conditional on that set) can be confidently wrong; near-collinear terms can also crowd it out under the charter's cap of two admitted terms.
- Stale memories not quarantined: 6/19 (3 wrongly marked confirmed); 6 of those missions still reached the correct conclusion.
- Changes that went undetected but were not claimed absent (incomplete conclusions): 2.
- Generality: one domain is implemented. The loop is written against the domain's interfaces, but no second domain has been run through it, so generality is designed, not demonstrated.
- The analysis assumes at most one change per mission, process noise only (no sensor noise on the state) and a term grammar fixed by the charter; dynamics outside the grammar can be flagged but not explained.
- Robust (Huber-weighted) evidence after the Gaussian assumption fails is an approximation, not an exact heavy-tailed likelihood.
- No live language model ran in the recorded investigation; the model-advisor path is tested with a simulated local server only.

## 7. Reproduce

```sh
uv run atlas research demo --root atlas-data/research
uv run atlas ledger verify atlas-data/research/ledger
```

Every mission can be replayed from its ledger (`atlas research resume`); replay verifies each regenerated event against the record. Open `observatory/index.html` and `reports/dossier.html` offline.

Pending escalations: 1c18a7c0bbaed1b4 (budget-extension, M5-noise-limited).
