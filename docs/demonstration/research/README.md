# Recorded investigation: autonomous research on held-out problems

This folder holds the outputs of the preregistered run of

```sh
uv run atlas research demo --root atlas-data/research --workers 4
```

on 2026-11-17, Linux x86-64, CPython 3.12.3, NumPy 2.5.4, SciPy 1.18.1, four
workers, 389 s. The charter was approved by a scripted proxy, labeled as such
in the ledger; a real study uses `atlas research approve --operator NAME`.

| File | Contents |
|---|---|
| [dossier.html](dossier.html) | Offline dossier: the answer, the benchmark, and every featured mission with its figures (open locally) |
| [research-report.md](research-report.md) | The full report: survey, hypotheses, preregistration, missions, benchmark, failures, unknowns |
| [research-summary.json](research-summary.json) | Structured summary, including every mission's experiment-by-experiment view |
| [benchmark-results.jsonl](benchmark-results.jsonl) | One line per arm and held-out problem (1 600 missions), with digests |
| [charter.json](charter.json) | The approved charter |

## Provenance

* Preregistration frozen in [../../research/PREREGISTRATION.md](../../research/PREREGISTRATION.md),
  committed and pushed (`cad3c64`) before the run.
* Ledger preregistration record `sha256:f070910723bad579…48d`, written at
  19:24:05 UTC before any experiment, research source hash
  `sha256:c579a025c22a…12703`.
* Ledger: 250 records, tip `sha256:993c3c09a3e2…5bf5`; `atlas ledger verify`
  reports the chain, object hashes and record rules verified. The ledger
  itself (5.9 MB, mostly raw trajectories) is not committed; rerun the command
  above to regenerate it.
* After the run, the report generator was amended (to list the failures by
  family, term and memory state, and to qualify the headline with its
  conditions) and the reports were regenerated with `atlas research resume`.
  That resume replayed and verified every mission against the record. The
  amended reports are new `report` records, each superseding its predecessor
  through a `revision`; no decision logic changed after the run.

## Prediction versus outcome

Before the run the preregistration predicted that H1 (observation
dependence) and therefore H2 would be **unresolved**, because on the
development split the closed loop was only 0.24 experiments better than the
yoked control. On the held-out split the difference was **−1.14 [−1.85,
−0.45]** (Bonferroni-adjusted) and the closed loop was better than the yoked
control in every family. A plausible reason, not tested here, is that the
held-out split is more heterogeneous (a wider stiffness range and
unanticipated terms never seen in development), so designs chosen for one
problem transfer worse to another. The margin over the open-loop D-optimal
design is small (−0.85 [−1.65, −0.10]).

## Result in brief

**Answer: supported, with conditions.** H1, H2, H4, H5, H6 and H7 are
supported; **H3 (false conclusions ≤ 5 %) is unresolved**: 10 of 200
closed-loop missions (5.0 %, adjusted interval 1.5 %–10.9 %) ended in a false
conclusion. They concentrate where the system is weakest:

* the held-out-only term `v^3` (cubic damping) was never identified correctly
  (0 correct, 6 false, 15 unresolved). It was either crowded out of the
  working set by the near-collinear `v*|v|` under the charter's cap of two
  admitted terms, or absorbed into linear damping without the score test
  firing, so the posterior, conditional on a working set that lacked the true
  term, was confidently wrong;
* three hidden-change problems with a change at the second or last experiment;
* 6 of 19 stale memories were not quarantined (3 wrongly marked confirmed),
  although all six missions still reached the correct structure;
* the critic does not improve held-out regret in aggregate (no-critic ablation
  0.043 nats/row versus 0.050), because a wrongly admitted look-alike term
  extrapolates worse.

The featured missions behaved as intended: M1 characterized bench-A in four
experiments; M2 detected the stiffness change before experiment 3 and
attributed it correctly; M3 admitted and confirmed the unanticipated `x^2*v`;
M4 quarantined the stale memory of bench-A and re-characterized it; M5 ran
out of budget under heavy noise, reported its conclusion as unresolved, and
left a budget-extension request pending.

All of this concerns a simulated oscillator family within the approved design
space and priors; it is not evidence about physical systems.
