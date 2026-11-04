# Executed validation — 2026-11-04

Implementation tested: `77b98c5`; the later `f59cb67` changes only generated
report reproduction commands to use a portable destination and recorded
replicate count. A fresh complete synchronization demonstration exercises that
report fix. `d83cd72` subsequently fixes single-pass export templating so literal
markers in scientific text cannot corrupt the snapshot. The focused export and
synchronization regression suite passed **6 tests** on Python 3.12 (15.26 s)
and **6 tests** on Python 3.11 (15.98 s).
Subsequent changes are documentation and recorded review artifacts.

| Environment / check | Actual result |
|---|---|
| Local Windows, CPython 3.11.9 x64 | Full pytest: **194 passed, 1 skipped**, 280.38 s |
| Local Windows, CPython 3.12.15 x64 | Full pytest: **194 passed, 1 skipped**, 322.02 s |
| Local Linux x86_64, CPython 3.11.18 | Full pytest: **194 passed, 1 skipped**, 143.27 s (after the 3.11 type fix) |
| Local Linux x86_64, CPython 3.12.3 | Full pytest: **194 passed, 1 skipped**, 143.83 s |
| Local Linux x86_64, CPython 3.13.18 | Full pytest: **194 passed, 1 skipped**, 146.15 s |
| Node 24.22.1, jsdom | **3 interaction tests passed**, six viewer sections, filters, safe text rendering, proposal/report downloads |
| Ruff | Lint and formatting passed, 79 Python files formatted consistently |
| mypy | Whole package (49 modules): passed on Python 3.11, 3.12 and 3.13 for the `linux`, `win32` and `darwin` platform targets. Before the type fix, 3.11 failed (see below) |
| Hosted Linux 3.12 / Windows 3.12 | Run `41914048887` at `8978d26`: **passed** every step including the full suite |
| Hosted Linux 3.11 / Windows 3.11 | Run `41914048887`: **failed at mypy** (`np.fft.rfftfreq` typed `floating[Any]` under NumPy 2.4.6); tests did not run. Fixed in the follow-up |
| Linux acceptance commands | Local dry run of the CI acceptance job: spectral A1–A7 7/7, synchronization S1–S5 pass, three ledgers verified |
| Linux vs Windows benchmark | 12-trial benchmark: identical counts and intervals to the committed Windows result; NLS/BIC RMSE within 1.4×10⁻¹⁰ Hz |
| Interactive browser visual/CSP enforcement | **Not executed**: CUA providers unavailable |

The single Windows skip requires symlink privileges absent from the account.
Tests ran on an ARM64 Windows host using x64 interpreters. NumPy/SciPy were
2.4.6/1.17.1 on Python 3.11 and 2.5.4/1.18.1 on Python 3.12. Both used the
committed uv lockfile. No Linux, POSIX isolation or cross-platform equality
claim follows from the Windows results. The numerical figure was inspected
as an actual generated artifact; the UI has DOM tests, not a visual screenshot.

Original GitHub workflow run [41103222445](https://github.com/topherchris420/rain-atlas/actions/runs/41103222445)
never started any matrix job. The later run
[41914048887](https://github.com/topherchris420/rain-atlas/actions/runs/41914048887)
executed; its only failure was the Python 3.11 type check described above. Check annotations identify the account-level
block; missing logs are not Python errors. Billing was not changed. The revised
workflow runs full tests on the four declared environments, uploads JUnit,
checks lint/format/types, exercises the viewer and runs demonstrations when
runners are available.

## Synchronization study

```sh
uv sync --locked --python 3.12
uv run atlas experiment run synchronization --root atlas-data/reproduce-sync --replicates 12
uv run atlas ledger verify atlas-data/reproduce-sync/ledger
```

30 combinations of K={0,0.6,1,1.4,2} rad/s, D={0,0.08,0.5} rad²/s and
lag={0,0.6} rad; 12 independent trajectories per condition and a separate
12-trajectory replication ensemble; duration 60 s, burn-in 20 s, dt=0.04 s.

**5 supported, 10 unresolved, 15 contradicted** finite-window locking claims.
All five preregistered acceptance checks passed: positive control supported,
uncoupled negative controls never supported, exact generator and primary
analysis reproduction, complete ledger/artifact verification, and negative or
unresolved results retained. No model participated. This is a two-oscillator
simulation, not physical evidence or an infinite-population transition.

Independent phase/frequency observables share raw trajectories; new-data
replication is separately seeded. Approximate Student-t intervals use
independent replicate summaries and Bonferroni correction across conditions
and two metric families. Critical and noisy conditions have no assigned binary
asymptotic truth. Full per-condition values, provenance and limitations are in
the [review snapshot](demonstration/index.html) and
[review data](demonstration/review-data.json). Download/open the HTML locally;
GitHub's source view does not execute it.

## Spectral stress benchmark

Executed at `77b98c5`, seed 20261104, 12 independent trials per case:

```sh
uv run atlas benchmark --root atlas-data/reproduce-benchmark --trials 12
```

| Case | Welch: trials missing ≥1 tone | NLS/BIC: trials missing ≥1 tone | Welch / NLS false-positive trials |
|---|---:|---:|---:|
| separated tones | 0/12 | 0/12 | 0/12, 0/12 |
| close tones | 12/12 | 5/12 | 1/12, 5/12 |
| white-noise null | not applicable | not applicable | 0/12, 0/12 |
| colored-noise null | not applicable | not applicable | **12/12, 12/12** |
| nonstationary chirp | truth unavailable | truth unavailable | truth unavailable |
| amplitude modulation | 12/12 | 0/12 | 0/12, 1/12 |

95% Wilson intervals: 0/12 = [0, 0.2425]; 12/12 = [0.7575, 1];
1/12 = [0.0149, 0.3539]; 5/12 = [0.1933, 0.6805]. Zero observed errors
therefore does **not** establish a negligible population error rate. Both
classical baselines fail under colored noise; the result diagnoses their
misspecified null model and is not hidden behind aggregate accuracy.

The [complete measured benchmark](demonstration/benchmark.json) retains
counts, intervals, conditional matched-tone RMSE, timings, configurations and
unknown-truth values. Process memory is in the local ledger. This fixed small
suite is not a population reliability or calibrated-confidence evaluation.

## Reproducibility and remaining boundaries

Source/skill snapshots, lockfile and input/output artifacts are recorded in
the local append-only ledgers. Sharing projections does not silently change
those records. Review JSON and figures can still carry sensitive scientific
information. No external authenticity is claimed by a content hash.

R.A.I.N. export passes the inspected upstream JSON Schema on fixture and
executed-study data. It has not been submitted to a live host. Luca intake is
quarantine only. Live model providers, hardened containers, generic proposal
execution, automatic resume and broader calibration/power studies remain
planned; see [WORKBENCH_LIMITATIONS.md](WORKBENCH_LIMITATIONS.md).
