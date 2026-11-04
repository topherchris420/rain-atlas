# Changelog

All notable changes are recorded here. Versions follow semantic versioning.

## 0.1.0 — unreleased

First end-to-end slice.

### Added

- Skill format: Agent Skills `SKILL.md` plus typed `skill.json`
  (`atlas.skill/v1`), strict validators, catalog discovery, content hashing.
- Registry: built-in catalog plus versioned local installs that are never
  overwritten; hash-pinned approval for untrusted installs; enable/disable;
  upgrade that activates only after examples pass; removal to a trash folder;
  dependency resolution; capability selection.
- Bounded executor: separate process per run, Windows job object or POSIX
  rlimits, timeout and cancellation, audit-hook guard for network, subprocess,
  reads and writes; full run records including failures.
- Evidence ledger: content-addressed objects, hash-chained log, sealed values,
  record rules for OBSERVED / COMPUTED / INTERPRETED claims, challenges,
  verdicts, reproductions, approvals and reports.
- Research roles (scripted): principal investigator, computational scientist,
  scientific skeptic, experimental engineer; computed verdicts.
- Eleven built-in skills covering the ten Phase 1 domains.
- Phase 10 reference experiment `spectral-recovery` with preregistered
  acceptance criteria, Markdown report, figures and a reproduction bundle.
- CLI `atlas` (skills, run, experiment, ledger, env).
- Documentation, ADRs, security and responsible-use notes, CycloneDX SBOM
  (`sbom.cdx.json`), CI workflow (not yet run on a hosted runner).
- `py.typed` marker and `Typing :: Typed` / Python version classifiers.
- `.github/dependabot.yml`: monthly grouped updates for the pinned CI actions.

### Changed

- mypy checks the whole `rain_atlas` package (49 modules) instead of two
  scientific modules, with `strict_equality`, `warn_redundant_casts` and
  `warn_unused_ignores`. `scripts/check.py` type-checks with every CI Python
  version in throwaway environments built from `uv.lock`.
- CI: actions pinned to commit SHAs on Node 24 releases; checkout no longer
  persists credentials; superseded pull-request runs are cancelled; Python
  3.13 added on Linux. The acceptance job no longer repeats the slow tests
  already run in every test job. It now verifies each ledger the CLI writes
  and uploads the synchronization and benchmark outputs as well.

### Fixed

- CI failed on Python 3.11 (Linux and Windows) at `mypy`: under NumPy 2.4.6,
  the version the lock resolves for 3.11, `np.fft.rfftfreq` is typed
  `floating[Any]`, not `float64`. `stft` now builds its frequency axis as an
  explicit float64 array.
- Typing problems found by whole-package checking, none of which changed a
  tested result: the executor refuses an executable skill with no
  entrypoint instead of failing later; a skill entrypoint that cannot be
  loaded raises `ImportError` instead of `AttributeError`; process cleanup
  without a job object no longer calls POSIX-only `os.killpg` on Windows;
  output artifact references whose name is not a string fail the hash check
  explicitly; A5's acceptance text no longer reuses a variable from A1.
