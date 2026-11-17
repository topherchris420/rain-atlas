# Changelog

All notable changes are recorded here. Versions follow semantic versioning.

## 0.1.0 — unreleased

First end-to-end slice.

### Added (REA replication framework and unified R.A.I.N. architecture, 2026-11-16)

- New package `rain_atlas.rea`: the Recursive Engineering & Analysis
  framework — typed investigation manifests, evidence items with enforced
  OBSERVED/COMPUTED/INFERRED/UNKNOWN classifications, evidence-package
  validation and rendering, a reference-versus-replica conformance harness
  with structural comparators (exact/keys/sequence/predicate; no arbitrary
  similarity scores), and a replica registry with integration gates.
- Nine recorded investigations (`rain_atlas.rea.investigations`) covering
  Mem0, Langfuse, Browser Use, Omnara, RunAnywhere, Epicenter, Maxxwell,
  Arga Labs and Infera, each with pinned reference commits or fetched
  documentation, licenses, honest evidence classifications and open questions.
  Closed-source references claim no parity; their runtime behavior is
  recorded as unknown.
- Eight independently implemented replicas:
  - `rain_atlas.memory` — Scientific Memory Engine (Mem0-inspired):
    mem0-compatible API shape (add/search/get/get_all/update/delete/
    delete_all/history) with deterministic rule-based inference, scope
    filters, append-only supersession history and recorded contradictions.
  - `rain_atlas.observability` — observability engine (Langfuse-inspired):
    traces with hierarchical SPAN/GENERATION/EVENT/TOOL observations,
    levels, usage/cost rollups, scores, eval datasets and run comparisons;
    exports into the evidence ledger.
  - `rain_atlas.mission` — Research Mission Controller (Omnara/Maxxwell-
    inspired): persistent task state machine, delegation, approval gates
    that pause agents, bounded retries, supervision (cancel/takeover),
    generation labeling (scripted/model/human) on every transition.
  - `rain_atlas.protocol` — Scientific Protocol Compiler (Infera-inspired):
    hypotheses compile to validated specs with lexicon bounds, simulated
    instruments only, ordered steps and preregistered acceptance; physical
    actuation is forbidden by construction.
  - `rain_atlas.simulation` — stateful service twin (Arga-inspired):
    deterministic instrument twin with hidden ground truth, scenario
    seeding, snapshot/reset/replay, fault injection and an evidence log.
  - `rain_atlas.inference` — local inference abstraction (RunAnywhere-
    inspired): provider interface, deterministic MockProvider, optional
    Ollama/llama.cpp HTTP providers, model discovery, schema-validated
    structured outputs.
  - `rain_atlas.knowledge` — local-first knowledge store (Epicenter-
    inspired): versioned documents, append-only history, portable
    export/import, explicit conflict resolution retaining both branches.
  - `rain_atlas.browser` — research browser adapter (Browser Use-inspired):
    structured page observations with provenance (content hash, fetch time)
    and content verification; stdlib-only, offline-testable.
- Differential conformance against the real reference: twelve tests run the
  mem0ai 2.2.1 SDK locally (in-memory qdrant, deterministic fake embedder,
  `infer=False`) and the replica through identical scenarios, comparing
  documented behavioral invariants. All twelve pass; the module skips when
  the reference SDK is not installed.
- Unified R.A.I.N. package `rain_atlas.rain`:
  - `atlas rain slice` runs the integrated vertical slice — hypothesis
    proposal (model-labeled), protocol compilation, approval gate,
    twin-based experiments with memory recall, preregistered evaluation,
    held-out replication by a skeptic agent, ledger export.
  - `atlas rain central` runs the central scientific experiment comparing
    four arms (adaptive+memory, adaptive no-memory, grid, random) over
    programs of sequential missions with held-out replications; preregistered
    hypotheses H1–H3 are evaluated with claims, challenges and verdicts in
    the ledger. Recorded outcome: all three held (68% experiment reduction
    from persistent memory; no false conclusions; adaptive arms below grid
    and random), bounded to the synthetic discrimination problem.
- New CLI group `atlas rea {list,show,export}`; documentation in
  `docs/REA.md`.
- Tool-derived evidence from the morluto/rea reverse-engineering tool
  (2026-11-17): `inspect_python_pyc` runs against the installed mem0ai 2.2.1
  bytecode, the langfuse 5.2.0 SDK bytecode and the browser-use reference
  compiled at its pinned commit produced pinned-digest OBSERVED evidence items
  (T01 `mem0-obs-5`, T02 `lf-obs-4`, T03 `bu-obs-3`) corroborating the
  recorded API surfaces at matching line numbers, plus one tool-derived
  conformance record; a regression test pins the tool citations and digests.
- Commercial-product evidence (2026-11-17): every investigation now records
  what the company actually sells per its YC company page or launch
  materials — including significant updates: Langfuse was acquired by
  ClickHouse (Jan 2026), RunAnywhere now sells Wally (fast inference for
  open frontier models), Rindler sells both Maxxwell (multi-agent IDE with
  an orchestrator over workers) and a website-to-API product, and Browser
  Use's commercial product is Browser Use Cloud — with each replica's scope
  boundaries stated explicitly; a regression test enforces the recording.
- Vendored Mem0 retrieval scoring (Apache-2.0, license-preserving, in
  `rain_atlas.memory.vendor.mem0`): the memory engine's default
  `ranking="hybrid"` path now runs standard Okapi BM25 through the
  reference's own sigmoid normalization and additive hybrid ranking; a
  differential test in the reference environment verifies the vendored
  functions match the installed mem0ai 2.2.1 outputs (explain-detail key
  names differ between the pinned commit and the release; ranking scores and
  order are identical — recorded as a deviation).
- 177 new tests across seven test modules plus the optional 13-test
  differential reference suite (skips when the reference SDK is absent).

### Added (held-out spectral calibration)

- `atlas benchmark --protocol spectral-calibration` compares a white-noise
  Welch threshold with rank tests calibrated on independent blank windows.
  It records white and AR(1) nulls, an out-of-panel oscillatory null and three
  injected-tone amplitudes, with Wilson intervals for whole-window detection
  and tone localization.
- The protocol records the complete design before execution, then reruns the
  seeded skill and compares output and artifact hashes. The JSON and offline
  observatory preserve all cases.

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

### Added (ORRERY orbital-dynamics subsystem, 2026-11-07)

- New isolated package `rain_atlas.orrery`: an original, high-fidelity orbital-
  mechanics engine. Universal-variable two-body motion; point-mass, closed-form
  zonal-J2, JGM-3 spherical-harmonic (Montenbruck–Gill V/W recursion) and
  third-body (Sun/Moon) force models with analytic gradients; embedded
  Runge–Kutta integration (Dormand–Prince 5(4), Runge–Kutta–Fehlberg 7(8),
  classical RK4, symplectic Störmer–Verlet and Yoshida-4) with PI step control
  and a 6+36 state-transition matrix; the IAU-76/80 FK5 frame reduction
  (precession, 106-term nutation, GMST, polar motion, EOP); JPL DE421
  ephemerides tied to MJ2000Eq by GMAT's ICRF-to-FK5 table; N-body dynamics
  with conserved-integral diagnostics; batch-least-squares orbit determination;
  STM covariance propagation with a Monte-Carlo consistency check; and
  Hohmann/lunar transfers.
- Validated against two independent references: the closed-form Kepler solution
  (genuine analytic truth for the two-body cases) and **NASA GMAT R2026a**
  reference runs (code-to-code consistency — explicitly *not* a claim of
  physical validation). Measured agreement over multi-day arcs: two-body to
  sub-millimetre, LEO/HEO/GEO + J2/geopotential/third-body to GMAT within
  2 cm–0.84 m, Earth–Moon TLI 5 cm, figure-eight choreography return 7.5e-8.
  Committed GMAT reference trajectories (with version, distribution MD5 and
  binary/report SHA-256 provenance) let the comparison run without GMAT.
- Integrates only at the edges: eight new `astrodynamics` skills (orbit
  propagation, Kepler reference, trajectory comparison, Earth orientation,
  tracking simulation, orbit determination, covariance propagation, N-body
  integration), a preregistered `atlas experiment run orrery` study that records
  claims, independent-integrator (SciPy DOP853) challenges and verdicts through
  the existing ledger vocabulary and exports to the offline observatory, and a
  self-contained, CSP-locked celestial lab (`docs/orrery-lab.html`) rendering
  only engine-computed data. Added the `astrodynamics` skill domain. No engine,
  ledger or executor module changed; no new runtime dependencies.
- Docs: `docs/ORRERY.md` (the mathematical assumptions behind every capability)
  and `docs/ORRERY_VALIDATION.md` (the measured validation record).

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
