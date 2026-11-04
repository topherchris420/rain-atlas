# Workbench audit — 2026-11-04

## Executive summary

The existing architecture is a credible small scientific instrument: 11
executable skills, separate scripted research roles, a bounded process executor,
sealed synthetic truth and an append-only ledger. It should be extended, not
replaced. Baseline non-slow tests passed locally. GitHub's four failed checks
never started: account payment/spending-limit annotations explain the failure.
No hosted test result can be inferred from those checks.

The uncertainty posture is **partial**. Independent frequency estimators,
replicate F-tests, multiplicity correction, uncertainty and failure reporting
exist for one narrow synthetic model. Agent agreement is not evidence. There
is no general confidence calibration or demonstrated general scientific agent.

## Evidence-based findings

| Area / evidence | Assessment | Finding and action |
|---|---|---|
| `src/rain_atlas/agents/`, `tests/test_lab.py` | Implemented | PI, scientist, skeptic and engineer separation; budgets and approval gates. Preserve these interfaces. |
| `science/spectral.py`, `experiments/spectral_recovery.py` | Implemented, narrow | Welch, NLS/BIC and independent replicate regression tests; white-noise stationary separated-tone assumptions. Add deliberate misspecification benchmarks. |
| `ledger/store.py`, `ledger/records.py` | Partial | Chain and record hashes checked; referenced dataset/run/report bytes were not comprehensively checked. Add dependency verification and malformed-log diagnostics. |
| spectral `_bundle` | Defect, repaired | Recursively copied the vault, including unopened truth from aborted experiments. Exclude every vault path and symlink; regression checks no secret enters archive. |
| `exec/runner.py`, `exec/context.py` | Defect, repaired | Host-side artifact paths lacked portable validation; log tails read entire files. Reject traversal, Windows streams/devices and output symlinks; bound log reads. |
| `exec/child.py` | Partial, improved | Move POSIX rlimits out of thread-unsafe preexec_fn; add CPU and per-file size limits; kill remaining process-group descendants after normal exit too. POSIX validation requires an available Linux environment. |
| registry untrusted execution | Defect, repaired | Approval of content was being treated as enough to run untrusted code under audit hooks. The default executor now refuses trust=untrusted even if hash-approved; hardened isolation remains planned. |
| `bench/`, `adapters/` | Initially empty | No benchmark or external compatibility claims were supported. Implement only measurable benchmarks and verified contracts. |
| `docs/ARCHITECTURE.md`, ADRs | Useful design, partly aspirational | Separate design from implementation status. No replacement runtime or personas. |
| `.github/workflows/ci.yml` | Blocked externally | Pin OS versions, run the full suite on all four targets, retain JUnit results and allow manual dispatch. Billing is unchanged. |

The complete tracked inventory was inspected by package, skill manifests and
entrypoints, tests, architecture/status/integration documents, workflow and
security controls. Local historical experiment directories were retained;
no other project's runtime, memories or history were changed.

## Recommended approaches implemented in this branch

1. Analytical reference cases and independent numerical comparisons before
   interpreting resonance plots. Report discretization error separately from
   uncertainty across independent simulation replicates.
2. A verified static evidence projection, with explicit unknowns, source hashes,
   limitations and no execution surface. Test injection and privacy boundaries.
3. Evaluate errors under distribution shift and model misspecification; expose
   unsupported cases instead of interpreting every high PLV as causal coupling.

## Tooling and operational guidance

Keep NumPy/SciPy/Matplotlib and the current Python roles. No agent framework is
introduced. Use independent replicate summaries for intervals; temporal samples
are autocorrelated and must not masquerade as independent replicates. Refuse
invalid input, missing dependencies and stale proposal hashes. Unknown evidence
or failed reproduction yields unresolved results. A model may submit an action
schema, never observations, verdicts or its own approval.

## Unknowns and assumptions

- Audit hooks are policy enforcement, not secure isolation. No hardened
  container or native syscall barrier is implemented.
- Hash chains show internal integrity, not external authenticity or truth;
  deletion of a suffix requires a separately retained head to detect.
- Finite synthetic examples do not validate claims about biology, materials,
  causal coupling or arbitrary data. No calibrated posterior is supplied.
- Account billing prevents hosted CI. Linux results must remain unverified
  unless independently executed; this branch never increases a spending limit.

## Repair-stage validation

Windows, x64 CPython 3.12.15 on an ARM64 host: full suite after integrity
repairs **138 passed, 1 skipped, 887.71 s**. Includes all seven original slow
spectral acceptance tests. JUnit: local `atlas-data/validation/stage1-py312.xml`.
The skip requires Windows symlink privilege. Python 3.11 and final-branch
results are recorded in `STATUS.md` after execution completes.
