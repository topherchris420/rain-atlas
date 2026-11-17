# The central experiment

**Question.** Does combining adaptive experiment selection with persistent
scientific memory let a research system reach correct decisions with fewer
experiments, without more false conclusions, including when the world
changes after the memory was written?

```sh
uv run atlas rain central --root atlas-data/rain-central          # protocol v2 (default)
uv run atlas ledger verify atlas-data/rain-central/ledger
uv run atlas rain central --protocol v1 --root atlas-data/rain-v1  # the superseded protocol, reproduced exactly
```

The run takes a few seconds on a laptop CPU and is deterministic for its
base seed. The recorded output is
[`demonstration/central-experiment-v2.json`](demonstration/central-experiment-v2.json).

## Result (protocol v2, recorded 2026-11-17)

150 programs per regime × 4 missions; every arm runs the same twins.
Intervals are 98.75 % (Bonferroni over four hypotheses) from a paired,
regime-stratified bootstrap over programs. For rates, the interval is the
union with Newcombe's score interval.

| Hypothesis | Measured | Interval | Verdict |
|---|---|---|---|
| **H1** In stationary worlds, verified memory needs ≥25 % fewer experiments than no memory | 26.9 % fewer (3.17 vs 4.34 per mission) | [24.3 %, 29.5 %] | **unresolved** |
| **H2** In shifting worlds, verified memory adds ≤5 pp false conclusions | +0.5 pp (0.5 % vs 0.0 %) | [−0.6, +1.9] pp | **supported** |
| **H3** In shifting worlds, naive memory adds >5 pp false conclusions | +43.5 pp (43.5 % vs 0.0 %) | [+38.4, +48.6] pp | **supported** |
| **H4** Maximum-disagreement selection beats the ascending sweep and random selection | −2.64 and −1.32 experiments per mission | [−2.82, −2.47] and [−1.48, −1.15] | **supported** |
| *Ordering control* | 1200 of 1200 missions identical to a fixed high-to-low sweep | — | the H4 advantage is ordering, not adaptivity |

What this says, within the limits below:

* **Memory that must be confirmed is safe and saves about a quarter of the
  experiments.** Its stationary-world saving (26.9 %) clears the 25 % bar
  as a point estimate, but the interval includes values below it, so H1 is
  unresolved rather than supported. Verified memory also left fewer
  missions undecided (30 vs 66 of 600) and still saved 17 % in shifting
  worlds.
* **Memory that is trusted blindly is fast and wrong after the world
  changes.** Naive memory, the architecture protocol v1 credited with a
  68 % saving, needs only 1.14 experiments per mission in stationary
  worlds. After a regime change it reached a false conclusion in 261 of
  288 missions (91 %), usually without running a single experiment.
* **Verification catches change.** Verified memory quarantined stale
  memories 151 times across the 150 shifting programs, erring in 3 of 288
  post-change missions, and quarantined needlessly 7 times in stationary
  worlds.
* **"Adaptive" selection is an ordering effect here.** The disagreement
  between the two candidate models does not depend on the observations, so
  the maximum-disagreement policy is a fixed high-to-low sweep. A fixed
  design that uses no model knowledge matched it on every mission. H4 is
  real, but it is not evidence that adaptivity helps.

| Arm | Stationary exp./mission | Shifting exp./mission | False (stationary) | False (shifting) | Undecided (of 1200) |
|---|---:|---:|---:|---:|---:|
| verified-memory | 3.17 | 3.52 | 1 / 600 | 3 / 600 | 88 |
| naive-memory | 1.14 | 1.25 | 0 / 600 | 261 / 600 | 45 |
| no-memory | 4.34 | 4.26 | 1 / 600 | 0 / 600 | 146 |
| grid-descending (control) | 4.34 | 4.26 | 1 / 600 | 0 / 600 | 146 |
| random | 5.64 | 5.59 | 0 / 600 | 1 / 600 | 250 |
| grid-ascending | 6.96 | 6.93 | 0 / 600 | 0 / 600 | 378 |

## Design

**Problem.** Two coupled oscillators; the twin's phase coherence follows one
of two known surrogate models (`linear`, `damped`) hidden from the agents.
Each experiment runs 4 replicates at one coupling on a 10-point grid, with
Gaussian observation noise 0.15 per replicate. The decision rule is a
sequential Bayes-factor test: decide when the log Bayes factor reaches
5 nats. One experiment at the most informative coupling carries about
1.8 nats of expected evidence, so a mission needs several.

**Worlds.** A *program* is 4 missions on fresh twins. In *stationary*
programs the hidden model is fixed. In *shifting* programs it switches once,
at a mission drawn uniformly from 2–4, without notice. The first model is
drawn per program. Budget: 8 experiments per mission.

**Arms.**

| Arm | Selection | Memory and decision rule |
|---|---|---|
| `verified-memory` | maximum disagreement | Remembered evidence counts only once fresh evidence in this mission agrees with it at ≥3 nats; then decide on pooled evidence ≥5 nats (or fresh alone ≥5). Fresh evidence ≥3 nats *against* memory quarantines it: memories are deleted with history retained, a contradiction is recorded, and the mission continues on fresh evidence. |
| `naive-memory` | maximum disagreement | Pool remembered and fresh evidence; decide at ≥5 nats, possibly before any experiment (the v1 integrated arm). |
| `no-memory` | maximum disagreement | Fresh evidence only, ≥5 nats. |
| `grid-ascending` | fixed low-to-high sweep | Fresh evidence only. |
| `grid-descending` | fixed high-to-low sweep | Fresh evidence only; the ordering control. |
| `random` | seeded uniform choice | Fresh evidence only. |

Memory is a program-scoped `ScientificMemory`; observations are stored
verbatim. The 3-nat confirmation threshold was fixed *a priori* from the
sequential-test error bound: a stale memory survives one check with
probability about `1 / (1 + e^3)` ≈ 4.7 %. It was not tuned on results.

**Analysis.** Programs are the independent units. Missions within a program
are dependent through memory. Common random numbers pair the arms. The
bootstrap resamples programs within each regime (4000 resamples). Verdicts
are three-valued: *supported* when the whole interval satisfies the
hypothesis, *contradicted* when it wholly violates it, *unresolved*
otherwise. H4 tests both comparisons at α/2, and both must hold.

**Order of evidence.** The preregistration (complete design, hypotheses and
analysis plan, with a digest) is the first ledger record, written before
any twin runs. The protocol was also committed to the repository before its
first full-size run (commit `68c17e8`).

## Why protocol v1 was superseded

Protocol v1 (2026-11-16) recorded "H1/H2/H3 supported, 68 % experiment
reduction from persistent memory". Review found that the design could not
have produced any other answer:

1. The hidden model never changed, and the memory arm pooled the previous
   missions' observations. After mission 1, every mission was already
   decided before it ran: per-mission experiments were `1, 0, 0` in all six
   programs. The 68 % (6 vs 19 experiments) is `1 − 1/3` by construction.
2. One experiment at the most informative coupling carried about 11 nats
   against a 5-nat threshold, so the memoryless adaptive arm also nearly
   always decided in one experiment.
3. No arm ever made a false conclusion, so the safety hypothesis compared 0
   with 0.
4. "Adaptive" selection ignored the observations, and the ascending grid
   baseline started at the least informative conditions.
5. Six programs per arm were judged on point estimates with no uncertainty.

v1 remains in the code, unchanged, as `atlas rain central --protocol v1`.
A regression test pins its recorded numbers. The v1 claim about memory is
the one v2 tests directly: H3 shows that the same architecture, once the
world can change, reaches a false conclusion in 91 % of post-change
missions.

## Limitations

* The problem is synthetic: two known surrogate models with correctly
  specified Gaussian noise. A misspecified noise model would weaken every
  error bound above.
* Shifting programs change once, at an unannounced mission. Gradual drift,
  repeated changes and partial changes are untested.
* All policies are scripted. No language model participates in any arm.
* Repeating a condition is disallowed within a mission, so the optimal
  design for this problem (replicating the most informative condition) is
  not available to any arm.
