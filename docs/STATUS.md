# Current workbench status — 2026-11-05

This update supersedes the historical v0.1 status retained below. The complete
specification is **not** claimed complete. See [WORKBENCH_LIMITATIONS.md](WORKBENCH_LIMITATIONS.md)
for implemented boundaries and explicitly planned work.

| Priority | Implemented and exercised |
|---|---|
| Audit / CI repair | Reproduced baseline, inspected workflow annotations, repaired artifact/ledger/process handling; pinned four-job matrix with JUnit artifacts |
| Offline observatory | Experiment/evidence/timeline/skill/report/composer views, standalone CSP-restricted HTML, source verification, privacy projection; Python, DOM and real-browser (Chromium, CSS/CSP active) tests |
| Resonance | STFT, Morlet CWT, PLV/order parameter, noisy Kuramoto, LMS/NLMS, FIR identification, supported thin-plate modes, multichannel cross spectra; 30 total executable skills (8 astrodynamics) |
| Demonstration | Two-oscillator synchronization sweep with analytical reference, new-data replication, independent phase/frequency observables, exact reproduction, reports and figures |
| Scientific skepticism | Noise/phase-lag shifts, independent replicate intervals, Bonferroni and Holm utilities, Wilson error-rate intervals, exact-identity leakage check, preserved unknown truth |
| Evidence | Exact engine/skill source snapshots, lockfile, dependency verification, derived SQLite search, fresh-store torn-tail recovery; no historical record changes |
| Proposals | Strict closed action schema, offline model identity/parameters/prompt and proposal hashes, approval gate, persistent registered budgets; no live model provider |
| Integrations | R.A.I.N. local submission export against inspected schema; Luca records always quarantined, no path following or external state writes |
| Benchmark | Welch versus NLS/BIC on separated/close tones, white/colored nulls, chirp and amplitude modulation |
| Developer experience | Locked setup, tutorial, working skill templates, lint/format, targeted scientific API typing, adversarial and regression tests |
| ORRERY orbital dynamics | Original two-body/perturbed/N-body engine, IAU-76/80 frames, DE421 ephemerides, orbit determination, covariance; validated against the analytic Kepler solution and NASA GMAT R2026a (consistency, not physical validation); 8 astrodynamics skills, a preregistered experiment, and a CSP-locked celestial lab |

## Validation record

- **BLACK GLASS native reconstruction, 2026-11-08, Windows Python 3.12.15:** the
  non-slow suite passed (461 tests collected, exit 0), including 17 new tests for
  the model, comparison laboratory, reconstruction engine, native routine
  explorer, evolution analyzer and the end-to-end committed-BusyBox validation;
  ruff, format, mypy and `atlas skills validate` clean. A real Ghidra 12.1.4
  headless run on a licensed BusyBox ELF
  (`6e123e7f…48`) recovered the routine facts; the three clean-room models (MD5,
  SHA-1, base64) agree with `hashlib`/`base64` on 200+ random inputs and all RFC
  vectors, and `atlas firmware reconstruct` records a reconstruction whose ledger
  verifies clean (12 records, every routine `supported`). The binary is never
  executed; agreement is between a reconstruction and a published standard, not a
  physical measurement. The official DSM image was downloaded and found encrypted
  (8.0 bits/byte, magic `bf ad be ef`), so its binaries were not opened.
- **Linux, 2026-11-05, first POSIX execution** at `3e770cb`: full suites
  **235 passed, 1 skipped** on CPython 3.12.3 (207.46 s) and on CPython 3.11.18
  (202.10 s), including all slow acceptance tests. Lint, format, types and skill
  validation pass. Chromium renders the fresh and published observatories with
  CSS and CSP active, with no console messages, network requests or overflow.
  This execution found and fixed five defects: OS-dependent skill hashes,
  inherited POSIX peak memory, SQLite and extended-attribute guard gaps,
  two-segment coherence, and report overflow. The regenerated demonstration
  reaches the same 30 verdicts as Windows, with byte-identical reports. See
  [VALIDATION.md](VALIDATION.md).
- **ORRERY, 2026-11-07, Windows Python 3.12.15** (NumPy 2.5.4, SciPy 1.18.1):
  non-slow suite **437 passed, 7 skipped, 20 deselected** (107.9 s); the ORRERY
  slow subset (GMAT, N-body, OD, acceptance) **12 passed** (345.1 s); ruff,
  mypy and `atlas skills validate` (30 skills) clean; all 8 astrodynamics skill
  examples pass in the bounded executor. The preregistered experiment
  corroborates all 9 scenarios against the analytic Kepler solution and GMAT
  R2026a (two-body to sub-mm; perturbed cases to GMAT within 2 cm–0.84 m), with
  exact reproduction and a verifying ledger. Agreement with GMAT is code-to-code
  consistency, not physical validation. The full slow suite on both interpreters
  and the Linux/CI paths were not re-run. See
  [ORRERY_VALIDATION.md](ORRERY_VALIDATION.md).
- Baseline Windows Python 3.12: **112 passed, 1 skipped, 7 deselected** (non-slow).
- Repair-stage full suite: **138 passed, 1 skipped** on Windows Python 3.12.15
  (887.71 s) and **138 passed, 1 skipped** on Windows Python 3.11.9 (849.72 s).
- Expanded full suites at implementation `77b98c5`: **194 passed, 1 skipped**
  on Windows Python 3.12.15 (322.02 s) and **194 passed, 1 skipped** on Windows
  Python 3.11.9 (280.38 s). Both include all slow fixed/blinded spectral and
  synchronization acceptance tests. JUnit output is retained locally under
  `atlas-data/validation/final-py312.xml` and `final-py311.xml`.
- Numerical resonance checks: **18 passed**; independent formulas, SciPy
  comparisons, null controls and deterministic/stochastic convergence cases.
- Offline viewer DOM interactions: **3 passed**. Browser-rendered checks were
  added on 2026-11-05 (see the Linux record below).
- Ruff lint/format and mypy (two scientific API modules): exercised locally.
- Hosted matrix: **blocked before execution**. GitHub run `41103222445`
  annotations report failed account payments / spending limit. Logs do not
  exist. No hosted Python result is claimed; local Linux results are recorded
  below. Billing was not changed. Workflow corrections cannot repair an account-level block.

The Windows skip requires symlink privileges absent from this account. Local
interpreters are x64 on an ARM64 Windows host. Python 3.11 resolves NumPy 2.4.6 /
SciPy 1.17.1; Python 3.12 resolves NumPy 2.5.4 / SciPy 1.18.1 from the lockfile.

The first full synchronization demonstration executed 30 conditions with 12
replicates and produced **5 supported, 10 unresolved, 15 contradicted** operational
locking claims. All five acceptance checks passed, including exact generator
and analysis reproduction and ledger verification. This is synthetic evidence,
not a general synchronization or physical-validation claim. Final source-pinned
demonstration and benchmark results are recorded in [VALIDATION.md](VALIDATION.md).

## Historical status from 2026-10-30 (retained for context)

Last updated 2026-10-30 for v0.1.0 (unreleased). This page states what is
implemented and tested, what failed during development, and what remains.
Nothing here is claimed unless a test or a recorded run supports it.

## Phase status

| Phase | Status | Evidence |
|---|---|---|
| 0 Architecture | **Done** | `ARCHITECTURE.md` (planned parts marked), `INTEGRATION.md`, `REFERENCES.md`, ADRs 0001–0004 |
| 1 Skills engine | **Done for the slice** | Registry, validators and executor tests; 11 built-in skills, one or more per Phase 1 domain, each with passing known-answer examples |
| 2 Multi-agent | **Partial** | Four scripted roles and the computed-verdict engine, exercised end to end by the reference experiment; no language-model roles, no adapters |
| 3 Ledger | **Done for the slice** | Tamper, ordering, category, seal/unseal, approval and verdict rules tested. `revision` records are validated but no workflow writes them yet |
| 4 Workflow | **Partial** | Preregistration first, ordered stages, budgets and approval enforcement tested; no follow-up experiments or pause/resume for approval |
| 5 Resonance | **Not started** | — |
| 6 Web | **Not started** | No web interface exists; nothing is exposed on a network |
| 7 Compute | **Partial** | CPU path only; timeout, memory cap and cancellation tested; no accelerator backend, no checkpoint/resume |
| 8 Benchmarks | **Not started** | The acceptance suite is the only quantitative check; no benchmark suite and no model evaluations |
| 9 Open source | **Partial** | LICENSE, README, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, RESPONSIBLE_AI, NOTICE, CHANGELOG, SBOM, CI workflow file. CI has never run on a hosted runner; nothing is published or tagged |
| 10 Demonstration | **Done** | `atlas experiment run spectral-recovery` runs end to end; acceptance tests pass (see below) |

## Executed tests

The final full run (`pytest`, slow tests included) was on 2026-10-30 at
13:46 −04:00, after all fixes below. Result: **120 collected, 119 passed,
0 failed, 1 skipped, 267 s.** The skipped test checks symlink refusal and
needs the Windows symlink privilege, which this account lacks.

| file | tests | seconds | covers |
|---|---|---|---|
| `test_acceptance_spectral_recovery.py` | 7 | 239.4 | Full fixed-mode experiment: A1–A7, numerical tolerances, evidence order, no truth before unseal, report and bundle, exact reproducibility; 8-replicate blinded run |
| `test_builtin_examples.py` | 13 | 11.9 | Every built-in skill's known-answer examples, run in the executor, plus catalog validity and Phase 1 domain coverage |
| `test_canonical.py` | 7 | 0.0 | Canonical JSON and hashing |
| `test_cli.py` | 6 | 0.5 | CLI validate, list, select, ledger verify (incl. tampering), single run, error reporting |
| `test_executor.py` | 13 | 7.2 | Network, subprocess, out-of-scope read and write denial; native process creation (Windows job object); timeout, cancellation, memory cap, determinism, relative paths |
| `test_jsonschema_lite.py` | 15 | 0.0 | Schema subset validator |
| `test_lab.py` | 6 | 2.4 | Approval modes, budgets, sealed runs, reproduction records |
| `test_ledger.py` | 13 | 0.3 | Hash chain, tamper detection, record rules, categories, seal/unseal |
| `test_registry.py` | 9 | 1.5 | Install without overwrite, hash-pinned approval, upgrade gating, removal to trash, selection |
| `test_science.py` | 17 | 2.2 | Matching, clustering, agreement, recovery scoring and CRLB against analytic values |
| `test_skill_format.py` | 14 | 0.1 | SKILL.md and skill.json validation |

The 11 built-in skills' known answers come from independent sources, not from
the skills themselves. For example, the pendulum period comes from the exact
elliptic-integral formula, the logistic-map exponents are ln 2 and ½ ln 0.16,
and the spike-train statistics were hand-computed.

**Not executed:** the CI workflow (hosted Linux and Windows runners), every
POSIX code path, and Python 3.11.

## Reference experiment results

Both modes were run from the CLI on 2026-10-30 with the registered design
(20 realizations and 10 replicates per dataset, 6 datasets). The output went
to `atlas-data/` (git-ignored, not committed). Here are the measured results.

| | fixed (`773d34c084b5`) | blinded (`45816aff462c`) |
|---|---|---|
| Truth (published after verdicts) | 47.3, 123.9, 311.6 Hz (in source; not blind) | 151.567, 300.105, 454.320 Hz (drawn from OS entropy, sealed) |
| Noise-only control | D6 | D2 |
| Acceptance A1–A7 | 7/7 pass | 7/7 pass |
| Tones validated at +20 / 0 / −10 / −20 / −30 dB | 3 / 3 / 3 / 1 / 0 | 3 / 3 / 3 / 1 / 0 |
| Supported findings not near a true tone | 0 of 10 | 0 of 10 |
| Control: realizations with any primary detection | 0% | 5% (1 of 20), no supported finding |
| Independent estimator std / CRLB, SNR_ref ≥ 0 dB | 0.80–1.19 | 0.70–1.18 |
| Primary (Welch peak) bias at +20 dB | −0.0075 to +0.0058 Hz | −0.0065 to +0.0056 Hz |
| Exact reproductions | primary 6/6, generator 12/12 | primary 6/6, generator 12/12 |
| Ledger verify | 193 records ok | 191 records ok |
| Wall time (x64 Python emulated on ARM64) | 96 s | 89 s |

The answer to the Phase 10 question **for this signal model** is yes down
to SNR_ref −10 dB. At −20 dB the roles validated only the strongest tone,
and at −30 dB they validated none. They recorded both as negative results
rather than as claims. The independent estimator (NLS) attains the
Cramér-Rao bound within sampling error. The primary Welch-peak estimator runs
about 2–7× the bound, which is expected because averaging reduces resolution.
Its high-SNR error is dominated by a small, systematic interpolation bias of
about 1–2% of a bin.

Each demonstration ledger also keeps the first, aborted attempt (failure 8
below). That attempt consists of a preregistration, a seal, one `crashed`
generator run and an "experiment aborted" note. The blinded attempt's seal was
never opened, so that truth stays sealed.

## Failures and corrections found during development

These were found by the tests or by measurement and fixed. The original
behaviour is recorded here instead of being hidden.

1. **Registry install layout was invalid.** Installed skills were copied to
   `<name>/<version>/`, which fails the skill format's own name-equals-
   directory rule, so every installed skill was rejected. Found by
   `test_registry.py`; the layout is now `<name>/<version>/<name>/`.
2. **Read guard was too wide.** The child's readable roots included every host
   `sys.path` entry. Under `python -m pytest` that included the working
   directory (the repository root), so a skill could read `pyproject.toml`.
   Found by `test_reads_outside_the_skill_and_inputs_are_blocked`. The child's
   import path is now filtered to interpreter directories plus the
   `rain_atlas` package root.
3. **Markdown tables broke on `|` in cell text** (the A2 criterion contains
   `|bias|`). Found by reading a trial report; cells are now escaped.
4. **A2 looked like a failure in a 4-realization trial run**: independent
   estimator spread/CRLB ratios of 0.31–1.01. A separate 40-realization
   measurement gave 0.83–1.11 at +20 and 0 dB, so the low ratios were small-sample
   noise. The registered 20-realization design was kept unchanged.
5. **The NLS + BIC estimator reports spurious tones in pure noise** in 6 of 300
   white-noise realizations (2.0%), because BIC does not penalise the search
   over frequency. A unit test had assumed zero for one seed; it now bounds
   the rate statistically, and the limitation is in the skill's documentation.
   It cannot create a claim (claims need the line in ≥50% of realizations).
6. **The sealed-truth leak test was wrong at first**: it flagged generator
   *reproduction* runs, which legitimately hold the truth after unsealing.
   It now checks the original sealed runs, whose input copies are deleted.
7. **A synthetic-tones error message would have echoed a tone frequency**;
   it now omits parameters, because generator inputs may be sealed.
8. **The CLI experiment crashed with a relative `--root`.** Every test used
   absolute temporary paths, so this passed the full suite (113 tests) and
   failed on first real use: the child process received a relative spec path
   but runs in its own temp directory (`FileNotFoundError`, run status
   `crashed`, experiment aborted at the first generator run). The executor now
   resolves the runs directory; `test_relative_runs_dir_works` covers it. The
   aborted attempts remain in both demonstration ledgers (preregistration,
   seal, crashed run, "experiment aborted" note), followed by the successful
   runs.

## Known limitations

- **Isolation is policy enforcement, not a sandbox.** Native code can bypass
  the audit-hook guard. Windows blocks native process creation through the job
  object (tested); POSIX has no process limit in v0.1. See `SECURITY.md`.
- **Tested on one machine only:** Windows 11 on ARM64 with x64 Python 3.12.15
  under emulation. Linux and macOS code paths (rlimits, process groups) are
  written but have not been executed. The CI workflow has not run.
- **Roles are scripted policies.** No language model participates. The
  "multi-agent" property is separation of responsibilities and independent
  methods.
- **Fixed mode is not blind**; its truth is in the source code. Blinded mode
  is blind with respect to the roles, but sealing proves commitment, not
  secrecy from the host process.
- **Narrow science.** The reference experiment covers white Gaussian noise and
  well-separated stationary tones. Close tones, coloured noise and
  non-stationary signals are untested.
- **Process start-up cost:** each run starts a fresh interpreter (about 1–4 s
  here, mostly importing SciPy), and each figure run rebuilds matplotlib's font
  cache (about 15 s).
- Ledger records and bundles contain local paths, such as the Python
  executable path.
- Capability ranking ignores test status and precision so far.

## Remaining work

1. Resonance module (STFT, wavelets, Kuramoto, phase-locking value, LMS,
   system identification, Chladni patterns), each with known-answer tests.
2. Static, read-only web lab generated from ledgers (observatory, skills,
   evidence explorer, timeline, downloads); optional local composer bound to
   127.0.0.1 with a token.
3. Adapters, after their interfaces are verified: R.A.I.N. external runner
   and submission export, read-only Luca ingest (`INTEGRATION.md`).
4. Optional language-model roles behind the closed action vocabulary, recorded
   as `generation: model`.
5. Container backend for untrusted skills; POSIX process limits.
6. Accelerator backend with recorded fallback; checkpoint/resume.
7. Benchmark suite; follow-up experiments and pause/resume for approval;
   `revision` workflow; SQLite query index.
8. Run CI on hosted Linux and Windows runners; then release tagging (only with
   explicit authorization).
