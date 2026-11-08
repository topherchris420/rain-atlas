# Changelog

All notable changes are recorded here. Versions follow semantic versioning.

## 0.1.0 — unreleased

First end-to-end slice.

### Added (BLACK GLASS firmware intelligence subsystem, 2026-11-07)

- New isolated package `rain_atlas.blackglass`: an offline, read-only,
  vendor-neutral static-analysis instrument for embedded operating systems. It
  imports operator-supplied firmware (tar/zip/extracted directory), builds a
  deterministic, evidence-linked model — component inventory, service and
  library dependency graph, static network surface, integrity and signature
  verification against trust anchors, and version diffs — and records it into
  the evidence ledger using only existing record kinds, so the ledger and
  observatory are unchanged.
- Dependency-free building blocks: a bounds-checked ELF reader
  (ELF32/64, little/big-endian; `DT_NEEDED`/`SONAME`/`RPATH`, imports, PIE/NX/
  RELRO/canary), a safe archive ingest (path-traversal, symlink and
  decompression-bomb defences), and an RFC 8032 Ed25519 verifier pinned by the
  official known-answer vectors (`cryptography` used as an optional backend when
  present, for Ed25519 and for RSA/ECDSA).
- Every finding carries evidence (file, digest, locus, method), a confidence
  level (`verified`/`high`/`medium`/`low`/`unverifiable`) and an independent
  cross-check; static inferences (e.g. linking `bind`/`listen`) are never
  promoted to confirmed runtime behaviour.
- New CLI group `atlas firmware {analyze,inventory,diff,verify,report,inspect}`,
  a reproducible demonstration (`scripts/make_blackglass_fixtures.py`, committed
  outputs under `docs/demonstration/blackglass/`), `docs/BLACK_GLASS.md`, and a
  test suite covering the ELF reader (vs `readelf`), ingest defences, Ed25519
  vectors, verification, pipeline accuracy/false-positive/determinism checks,
  ledger integration and the CLI. No new runtime dependencies.

### Added (BLACK GLASS native routine reconstruction, 2026-11-08)

- New native-reconstruction extension that advances BLACK GLASS from firmware
  metadata to working native-software analysis, with four explicit provenance
  levels — **Observed** (disassembler facts), **Reconstructed** (interpretation),
  **Implemented** (clean-room code), **Validated** (reproduces the public
  standard's vectors and the binary exhibits that standard's defining evidence).
  The analysed binary is never executed and no decompiled source is committed
  (only its SHA-256 digest and non-copyrightable derived facts).
- Modules: `routines.py` (the four-level model), `comparison.py` (the Behavioural
  Comparison Laboratory), `behavior.py` (the Subsystem Reconstruction Engine),
  `explorer.py` (the Native Routine Explorer over the Ghidra document),
  `reconstructions.py` (clean-room MD5/SHA-1/base64 written from RFC 1321 /
  FIPS 180-1 / RFC 4648), `evolution.py` (the Firmware Evolution Analyzer) and
  `reconstruction_ledger.py` (records the reconstruction with no new record
  kinds; each routine is a claim, its evidence cross-check a challenge, resolved
  to a verdict scoped to static identity, never runtime).
- A read-only `scripts/BlackglassReconstruct.java` Ghidra exporter (Ghidra 12
  dropped Jython; this runs on the bundled JDK, needs no Python) that refuses on
  a hash mismatch and emits only derived facts plus a digest of the local
  decompilation.
- **Empirical demonstration** on a licensed BusyBox ELF: MD5 and SHA-1 state
  initialisation and base64 encoding are identified from their standard-defined
  constants (`0xefcdab8967452301`/`0x1032547698badcfe`; plus `0xc3d2e1f0` for
  SHA-1) and alphabet, re-implemented clean-room (agreeing with `hashlib`/`base64`
  on 200+ random inputs and the RFC vectors), and recorded into a verifying
  ledger. The DSM image was downloaded and found **encrypted**, so its binaries
  were not opened (reported honestly, not worked around).
- New CLI commands `atlas firmware {routines,reconstruct,evolution}`; docs
  `docs/BLACK_GLASS_NATIVE.md` and an updated `docs/BLACK_GLASS_DSM_RESEARCH.md`
  recording the encryption finding. Tests cover the model, comparison, engine,
  explorer, evolution, the clean-room models and the end-to-end committed
  BusyBox validation. No new runtime dependencies.

### Fixed (ledger corruption handling, 2026-11-05)

- Ledger verification rejects non-object records, including JSON `null`, which
  previously passed without scientific record checks.
- Log metadata now validates sequence types, record kinds and digest references;
  malformed values and duplicate JSON keys produce verification diagnostics.
- An unterminated final record blocks further appends even when its JSON is
  complete. Previously, the next append could concatenate two records and
  corrupt the log. Failed parsing leaves both history and objects unchanged.
- Added 22 regression cases for malformed metadata, non-object records,
  interrupted appends, duplicate keys and empty-ledger compatibility.

### Fixed (follow-up review and module audit, 2026-11-05)

- **Peak memory missed result serialization.** `VmHWM` was read before the
  outputs were converted and encoded. It is now read after encoding, and the
  reading is written without copying the payload. For a probe returning 3e6
  zeros, the recorded excess rose from 22.9 to 63.0 MiB, the predicted total.
- **The SQLite extension test failed on CPython builds without loadable
  extension support.** It now skips there and keeps its assertion elsewhere.
- **`Registry.get` returned installed skills whose files changed after
  installation**, so `atlas run` could execute them. `select` already refused
  them; `get` now does too.
- **The R.A.I.N. export took its commit and dirty flag from the first run
  only.** A study continued from a modified tree was exported as clean. Every
  run now counts, and runs from different commits are refused.
- **The schema validator followed Python semantics, not JSON Schema's.**
  `enum`/`const` treated `true` as `1`, and `pattern`'s `$` also matched before
  a final newline, so `^sha256:…$` admitted `"sha256:…\n"`. Both now follow
  JSON Schema.
- **Example comparison:** an infinite expected value never matched itself,
  `1` satisfied an expected `true`, and canonical `{"$float": …}` expectations
  were not decoded.
- **The skeptic paired falsification tests with claims by position.** A
  reordered response from a capability-selected skill would have attached
  verdicts to the wrong claims, and a short one left claims unchallenged.
  Tests are now matched by the frequency they report.

### Fixed (first Linux validation, 2026-11-05)

- **Skill and evidence hashes now match on every OS.** Content hashes and
  source snapshots sorted `pathlib.Path` objects, which Windows compares
  case-insensitively. Generated skills were also hashed with CRLF bytes that
  git never committed. As a result, no hash in the Windows-recorded
  demonstration matched a checkout, Linux refused to reproduce Windows runs, and
  approvals and proposals did not carry across platforms. Canonical
  code-point ordering (`canonical.tree_files`) and pinned LF writes fix this.
  POSIX hashes are unchanged; Windows hashes change to agree with them.
- **Per-run peak memory on POSIX.** Records used `RUSAGE_CHILDREN`, a running
  maximum over all children, so later runs inherited earlier peaks. `wait4`
  alone still includes the host's RSS at spawn, which Linux folds into the
  child's `maxrss`. Runs now report the child's own `VmHWM`, checked against the
  `wait4` bound.
- **Guard bypasses through the standard library.** `sqlite3` could create
  files anywhere and read databases outside the read roots, native SQLite
  extensions could load, and extended attributes outside the run could be
  changed.
- **Coherence with too few segments.** `cross_spectrum` accepted two Welch
  segments for odd `nperseg`, where independent noise averages about 0.5
  coherence. At least three are now enforced, as documented.
- **Observatory reports.** Structured acceptance and negative-result items
  were raw JSON, which overflowed the page (by up to 949 px on a phone). They
  are now readable summaries, with the full record under "Inspect".

### Added (2026-11-05)

- Real-browser verification of exported observatories in Chromium, with CSS
  and CSP active (`tests/web/browser-check.cjs`).
- Portability tests: a golden mixed-case tree hash, snapshot/content-hash
  agreement, LF-only hashed trees, and pinned line endings for text writes.
- Documented Morlet ridge relation `f·2ω0/(ω0+√(ω0²+2))`, with a test.
- Linux validation record and a demonstration regenerated on Linux.

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
