# R.A.I.N. ATLAS

[![ci](https://github.com/topherchris420/rain-atlas/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/topherchris420/rain-atlas/actions/workflows/ci.yml)

**The open scientific intelligence engine from Vers3Dynamics.** Local-first,
MIT-licensed.

ATLAS runs scientific skills (small, typed, tested programs) in a bounded
executor, records every run, claim, challenge and verdict in an append-only
evidence ledger, and has separate research roles check each other's work with
independent methods. It reports what it found, what failed, and how to
reproduce it.

> **Scientific workbench, v0.1 (unreleased).** Includes an offline observatory,
> 22 executable skills, synchronization and spectral experiments, a classical
> stress benchmark, source provenance and validated local proposal intake.
> See [`docs/STATUS.md`](docs/STATUS.md) for executed tests and remaining limits.
> The executor enforces policy; it is not a security sandbox.

ATLAS is an independent Vers3Dynamics project. It is not affiliated with or
endorsed by the U.S. Department of Energy or the Genesis Mission.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11, 3.12 or 3.13 (all
three are tested in CI on Linux; 3.11 and 3.12 also on Windows).

```sh
uv sync --locked --python 3.12                # one-command development setup from this checkout
uv run atlas skills list
uv run atlas skills test                      # run every skill's examples in the executor
uv run atlas experiment run spectral-recovery # the reference experiment (~10 min on a laptop)
uv run atlas ledger verify atlas-data/spectral-recovery/ledger
uv run atlas observatory export atlas-data/spectral-recovery/ledger --out atlas-data/spectral-view
```

The experiment writes `atlas-data/spectral-recovery/reports/<id>/report.md`,
figures (PNG and SVG), `summary.json` and a zip bundle of the ledger.

Open `atlas-data/spectral-view/index.html` directly. No server, account, model,
external assets or execution endpoint is required. The viewer contains six
views: experiments, claim dependencies, scientific timeline, skills, reports
and a proposal composer. Scientific free text must be reviewed before sharing.

For the new resonance demonstration and benchmark:

```sh
uv run atlas experiment run synchronization --root atlas-data/sync-001 --replicates 12
uv run atlas ledger verify atlas-data/sync-001/ledger
uv run atlas benchmark --root atlas-data/bench-001 --trials 12
```

Open `atlas-data/sync-001/observatory/index.html`. The study compares temporal
phase locking with relative-frequency drift, independent seeded replication,
and an analytical deterministic reference. Noise and phase-lag uncertainty
produce unresolved and negative results. This is simulated two-oscillator
locking, not experimental proof of a physical or infinite-population transition.

Start with the [end-to-end tutorial](docs/TUTORIAL.md),
[numerical methods and assumptions](docs/RESONANCE.md),
[benchmark protocol](docs/BENCHMARKS.md), and [offline viewer](docs/OBSERVATORY.md).

## The reference experiment

*Can a multi-agent scientific system independently recover and validate the
dominant frequencies of a noisy synthetic signal?*

1. The truth (three tone frequencies and phases, plus which dataset is a
   noise-only control) is **sealed** in the ledger before any data exist.
2. Signals are generated at SNR +20, 0, −10, −20 and −30 dB.
3. A computational-scientist role detects lines (Welch PSD, Bonferroni-
   controlled threshold) and records claims.
4. A skeptic role re-estimates them from the raw data with a different method
   (nonlinear least squares with BIC), and tests each claimed frequency on
   independent replicate data (regression F-test).
5. An engineer role reproduces every primary run byte for byte.
6. Verdicts are **computed** (supported / contradicted / unresolved) and
   recorded, and only then is the truth unsealed and the results scored.
7. Seven preregistered acceptance criteria are checked, including that the
   expected failure at −30 dB is reported as a failure.

`--mode fixed` (default) uses published regression frequencies and reproduces
exactly; it is not blind. `--mode blinded` draws a new truth from OS entropy.

## Built-in skills

| Skill | Domain | What it does |
|---|---|---|
| `synthetic-tones` | simulation | Seeded multi-tone signals in white noise |
| `spectral-peaks` | signal processing | Welch PSD + controlled line detection |
| `sinusoid-fit` | mathematics / optimization | NLS sinusoid estimation with BIC order selection |
| `tone-presence-test` | statistics | F-test for claimed tones on independent replicates |
| `method-agreement` | evaluation | Per-item agreement between two estimators |
| `recovery-score` | evaluation | Recovery, bias, RMSE and Cramér-Rao efficiency against truth |
| `scientific-figure` | visualization | Deterministic PNG/SVG figures from recorded data |
| `pendulum-period` | computational physics | Nonlinear pendulum period by 8th-order ODE integration |
| `lyapunov-exponent` | dynamical systems | Lyapunov exponents (logistic map, Lorenz system) |
| `spike-train-statistics` | neuroscience | Firing rate, ISI CV, Fano factor, refractory violations |
| `bibliography-audit` | literature | Offline BibTeX audit (fields, DOI/year syntax, duplicates) |
| `stft-analysis` | signal processing | Hann time-frequency density with explicit normalization |
| `morlet-wavelet` | signal processing | Multiscale complex Morlet transform and edge-validity mask |
| `phase-locking` | resonance | Multichannel temporal PLV and instantaneous order parameter |
| `kuramoto-network` | dynamics | RK4 / Euler-Maruyama coupled phase oscillators |
| `adaptive-filter` | signal processing | LMS / normalized LMS causal filtering |
| `fir-identification` | dynamics | FIR least squares with conditioning and residual uncertainty |
| `plate-eigenmode` | computational physics | Simply supported thin-plate modes; explicit physical assumptions |
| `cross-spectral` | signal processing | Welch cross-spectrum and magnitude-squared coherence |
| `synchronization-sweep` | resonance | Reproducible noisy phase-lag sweeps |
| `synchronization-measure` | resonance | Phase/frequency observables and replicate intervals |
| `spectral-stress-benchmark` | evaluation | False detections, misses, disagreement and unknown-truth cases |

Each skill has `SKILL.md` (Agent Skills format), `skill.json` (typed manifest,
permissions, limits) and examples with known answers.

## Evidence rules

- **OBSERVED** claims need empirical data; synthetic data is never OBSERVED.
- **COMPUTED** claims must cite a successful recorded run.
- **INTERPRETED** claims must cite COMPUTED or OBSERVED claims.
- `atlas ledger verify` recomputes the hash chain, every object hash and these
  rules.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): the design, with planned
  parts marked
- [`docs/STATUS.md`](docs/STATUS.md): what is implemented and tested, failures,
  limitations, remaining work
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md): how ATLAS will connect to other
  R.A.I.N. Lab projects, verified export contract and quarantined Luca intake
- [`docs/adr/`](docs/adr/): decision records
- [`SECURITY.md`](SECURITY.md), [`RESPONSIBLE_AI.md`](RESPONSIBLE_AI.md),
  [`CONTRIBUTING.md`](CONTRIBUTING.md), [`NOTICE.md`](NOTICE.md)

## License

MIT © 2026 Vers3Dynamics
