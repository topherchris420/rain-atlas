# Preregistration: autonomous research benchmark (held-out)

Frozen on 2026-11-17, before any result was seen on the held-out seed below.
The commit that adds this file fixes the code that will be run; the
investigation also records the research source hash in its ledger
preregistration record, before any experiment.

## Question

> Can an intelligent experimental system detect previously unknown changes in a
> noisy dynamical system, determine what changed, and develop a better
> explanatory model using fewer experiments than conventional methods?

The question is answered for a simulated noisy driven oscillator family
(`rain_atlas.research.oscillator`) within the default charter
(`rain_atlas.research.charter.DEFAULT`): 16 experiments per mission, design
space A ∈ [0, 1.5], Ω ∈ [0.3, 2.5], x0 ∈ [−1, 1], two challenge experiments,
decision probability 0.95, attribution probability 0.9.

## Problems

* Split `held-out`, seed **5 380 771**, 50 problems in each of four families
  (`stationary`, `hidden-change`, `unfamiliar`, `wrong-assumptions`), 200
  problems in all.
* The held-out split differs from development in seeds, in a wider stiffness
  range (ω0² ∈ [0.5, 2.6] versus [0.6, 2.0]), in an additional change kind
  (offset onset) and in its unanticipated terms (`x*u`, `x^2`, `v^3`), none of
  which occurs in any development problem.
* Disclosure: integration tests exercised the pipeline on two problems per
  family under the previous held-out seed (9 920 417). No setting was changed
  in response to those outcomes except the minimum-sample rule below, which
  does not depend on the direction of any result. The seed was then replaced so
  that no held-out outcome has been seen.

## Arms

All arms share the analysis, critic, stopping rule and challenge protocol,
except where named. `closed-loop` (the system under test); `yoked` (replays
the closed loop's designs from problem i+1 of the same family);
`open-loop-optimal` (sequential D-optimal under the prior nominal model);
`fixed-sweep`; `random`; `legacy-atlas` (the `rain central` v2 decision rule
ported to this domain: fixed hypotheses, maximum disagreement, 5-nat Bayes
factor, verified memory, no change monitoring, no challenge); ablations
`closed-loop-no-critic` and `closed-loop-no-challenge`.

## Metrics (defined in `rain_atlas.research.benchmark`)

Censored experiments-to-correct-conclusion (`efficiency`: experiments used if
correct, else 16); correct, false and unresolved rates; change identified
(P(change) ≥ 0.95, location ±1, correct attribution); false alarms; discovery of
unanticipated terms; one-step 90 % predictive coverage and log-predictive
regret on six unseen conditions per problem (some beyond the approved
amplitude); regret of a linear least-squares model on the same data;
confident errors and recovery; wall time; exact reproduction of a
preregistered subset (first two problems of every family and arm).

"No change detected" is not a claim of absence: a missed change makes a
conclusion incomplete (not correct) but not false.

## Hypotheses and decision rules

Family-wise α = 0.05, Bonferroni over seven hypotheses (0.05/7 each); paired
bootstrap over problems stratified by family (10 000 resamples, seed
20 261 117); proportions use the union with a Wilson interval. *Supported* if
the whole adjusted interval satisfies the hypothesis, *contradicted* if it
violates it everywhere, *unresolved* otherwise. With fewer than 10 problems per
family no hypothesis may be supported or contradicted.

| | Hypothesis | Test statistic | Supported when |
|---|---|---|---|
| H1 | Observation dependence | efficiency(closed-loop) − efficiency(yoked) | interval < 0 |
| H2 | Fewer experiments than conventional designs | the same difference against open-loop-optimal, fixed-sweep, random, legacy-atlas | every part < 0 |
| H3 | Safety | false-conclusion rate of the closed loop | interval ≤ 0.05 |
| H4 | Change detection and attribution | change-identified rate, closed loop − fixed sweep, hidden-change family | interval > 0 |
| H5 | Unanticipated dynamics | discovery rate, closed loop − fixed sweep, unfamiliar family | interval > 0 |
| H6 | Calibration | closed-loop 90 % coverage on unseen conditions | interval ⊂ [0.85, 0.95] |
| H7 | Better explanatory model | regret(closed loop) − regret(linear least squares) | interval < 0 |

The answer to the question combines H1, H2, H4 and H7 (supported only if all
are supported); H3 and H6 are reported as conditions on that answer.

## What was tuned, on development data only

Noise levels, change timing, the change hazard (0.08 per experiment) and
change-size prior (sd 0.5), score-test level, challenge criteria (z,
amplitude interval, Chow test), the sentinel challenge, the cross-validated
independent check with Bonferroni across neighbours, the total-information
design utility, the memory conflict threshold (|z| > 3.5) and the futility
rule (three steps below 0.005 nats after at least eight experiments). The last
development run (20 problems per family, 640 missions) before the freeze gave:

| Arm | Censored experiments | Correct | False |
|---|---|---|---|
| closed loop | 9.22 | 0.64 | 0.025 |
| yoked | 9.46 | 0.64 | 0.000 |
| open-loop D-optimal | 9.29 | 0.62 | 0.025 |
| fixed sweep | 12.75 | 0.30 | 0.013 |
| random | 13.34 | 0.24 | 0.038 |
| legacy ATLAS | 12.06 | 0.36 | 0.075 |
| no critic | 10.21 | 0.54 | 0.100 |
| no challenge | 5.59 | 0.78 | 0.088 |

## Prediction made before the held-out run

From the development data I expect the closed loop to beat the fixed sweep,
random designs and the legacy rule clearly, but **not** to separate from the
yoked control or from the open-loop D-optimal design: H1 and therefore H2 are
expected to be unresolved, and the overall answer is expected to be
unresolved. If that happens it is the result and will be reported as such.
