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
