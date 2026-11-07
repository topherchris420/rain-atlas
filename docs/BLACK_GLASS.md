# BLACK GLASS — firmware intelligence subsystem

**An offline, read-only, vendor-neutral static-analysis instrument for embedded
operating systems, built as an isolated extension of R.A.I.N. ATLAS.**

BLACK GLASS imports a firmware archive or an extracted root filesystem that you
are authorised to analyse, builds a reproducible, evidence-linked model of the
software it contains, and records that model into the ATLAS evidence ledger so
other researchers can re-run and challenge every finding. It reads structural
metadata defined by open formats — ELF headers, init/supervision definitions,
configuration files — and **never disassembles, decompiles, executes, or
reconstructs proprietary logic**.

- [Scope and ethics](#scope-and-ethics)
- [What it produces](#what-it-produces)
- [Architecture](#architecture)
- [The evidence and confidence model](#the-evidence-and-confidence-model)
- [Command-line interface](#command-line-interface)
- [Ledger integration](#ledger-integration)
- [Scientific validation](#scientific-validation)
- [Limitations](#limitations)
- [Reproducible demonstration](#reproducible-demonstration)
- [Analysing your own firmware](#analysing-your-own-firmware)

## Scope and ethics

BLACK GLASS is a **defensive and research** instrument. It is designed to help
you understand embedded software you have a legitimate reason to examine: your
own devices, images released under licences that permit analysis, open-source
firmware, or images provided under an authorised engagement.

It deliberately does **not**:

- fetch or bundle any vendor's proprietary firmware;
- disassemble or decompile binaries, or reconstruct a product's internal
  security logic (for example, how a specific device validates an update);
- target, probe or communicate with any live device — it runs fully offline and
  opens no sockets;
- circumvent, or help circumvent, any technological protection measure.

Analysis is read-only: the only bytes BLACK GLASS writes are its own output
directory (ledger, report, graph). It reads the firmware you point it at and
nothing else. You are responsible for holding the rights to analyse a given
image; BLACK GLASS neither acquires images nor assumes you may analyse one.

## What it produces

1. A **component inventory**: every file classified (ELF, script, shared
   object, configuration, package manifest, key material, archive, data) with
   type-specific metadata and a SHA-256 digest.
2. A **service and dependency graph**: services parsed from init/supervision
   definitions, the executables they launch, the shared libraries each
   executable declares (`DT_NEEDED`), and trust-boundary annotations (run-as
   user, setuid, privilege transitions). Rendered as Graphviz **DOT** and a
   self-contained **SVG**.
3. A **static network surface**: socket-API imports and configuration/port
   declarations, each with a calibrated confidence (see below).
4. **Integrity and signature verification** against operator-supplied trust
   anchors (a known-good hash manifest and/or a detached signature with a public
   key). Ed25519 works with no external dependency; RSA/ECDSA use the optional
   `cryptography` backend.
5. A **version diff**: components added/removed/changed (with ELF dependency and
   import deltas), services and network surface appearing or disappearing.
6. **Evidence-linked reports** (Markdown + canonical JSON) where every statement
   carries its evidence, confidence, and an independent cross-check.
7. The results exposed through the existing ATLAS **observatory** and a
   **read-only inspection API** for scientific agents.

## Architecture

BLACK GLASS is a self-contained package, `rain_atlas.blackglass`, that adds **no
new ledger record kinds** and modifies nothing in the existing engine. It plugs
in only at two seams: the CLI (`atlas firmware …`) and the evidence ledger
(through existing `preregistration`/`dataset`/`run`/`claim`/`challenge`/
`verdict`/`report` records).

```
            firmware archive / extracted root filesystem (operator-supplied)
                                   │
                    ┌──────────────▼───────────────┐
                    │ ingest  (safe, read-only)     │  tar / zip / directory
                    │  · path-traversal defence     │  caps + symlink recording
                    └──────────────┬───────────────┘
                                   │ FirmwareImage
        ┌──────────────┬───────────┼───────────────┬──────────────────┐
        ▼              ▼           ▼                ▼                  ▼
   inventory       services     network       verification         (elf reader)
   classify      init + graph  static surface  hash + signature    pure-Python
   components    DT_NEEDED      + confidence    (trust anchors)     ELF metadata
        └──────────────┴───────────┬───────────────┴──────────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │ analyze  → AnalysisReport     │  deterministic; findings
                    │  each finding + cross-check   │  carry evidence+confidence
                    └──────────────┬───────────────┘
                 ┌─────────────────┼──────────────────┬─────────────┐
                 ▼                 ▼                  ▼             ▼
            report (md)     ledger_bridge          diff        inspect
            graph (dot/svg)  prereg→dataset→run    v1 ↔ v2    read-only
                             →claim→challenge                 agent API
                             →verdict→report
                                 │
                                 ▼
                         ATLAS evidence ledger ── observatory (existing viewer)
```

Modules (`src/rain_atlas/blackglass/`):

| module | responsibility |
|---|---|
| `errors.py` | typed failures: `IngestError`, `UnsupportedInput` |
| `model.py` | typed, JSON-serialisable data model (Evidence, Component, Finding, …) |
| `ingest.py` | safe import of tar/zip/directory; traversal, symlink and bomb defences |
| `elf.py` | dependency-free ELF reader (header, dynamic section, imports, hardening) |
| `inventory.py` | file classification into typed components |
| `services.py` | init/supervision parsing, dependency and trust-boundary graph |
| `network.py` | static network-surface detection with calibrated confidence |
| `verification.py` | hash-manifest and signature verification against trust anchors |
| `signing/ed25519_ref.py` | dependency-free RFC 8032 Ed25519 (verify/sign/keygen) |
| `graph.py` | deterministic DOT and SVG renderers |
| `analyze.py` | the deterministic pipeline → `AnalysisReport` with cross-checks |
| `diff.py` | noteworthy changes between two analyses |
| `report.py` | evidence-linked Markdown rendering |
| `inspect.py` | read-only query interface for agents |
| `ledger_bridge.py` | record an analysis into the ATLAS ledger (existing kinds only) |
| `experiment.py` | end-to-end orchestration + preregistered acceptance checks |
| `fixtures.py` | self-generated, redistributable fixtures for the demo and tests |

## The evidence and confidence model

Every statement BLACK GLASS makes is an `Evidence`-backed `Finding` with one of
five confidence levels:

| level | meaning | example |
|---|---|---|
| `verified` | independently re-checkable now | "this file is a 64-bit x86-64 ELF" (re-parsed), a hash match, a valid signature |
| `high` | an explicit declaration, not a runtime observation | a config line `Listen 8080` |
| `medium` | a static inference about a *likely* capability | a binary imports `bind` **and** `listen` |
| `low` | a weaker static inference | a binary imports only client-side calls |
| `unverifiable` | the evidence to decide was absent | integrity with no trust anchor supplied |

The cardinal rule: **an inference is never promoted to a fact.** Importing a
socket symbol is verified evidence that the binary *links* that symbol; it is
only `medium`/`low` evidence that a socket is opened at run time, because BLACK
GLASS has not run the firmware. Integrity and signatures are `verified`,
`failed`, `unsupported` or `unverifiable` — never assumed.

Each finding also carries an **independent cross-check** (a second method), which
the ledger records as a `challenge`. The verdict is then:

- **supported** — the statement is `verified` *and* its cross-check corroborated;
- **contradicted** — the cross-check contradicted it;
- **unresolved** — a static inference, an inconclusive cross-check, or an
  unverifiable result.

## Command-line interface

```sh
# Full analysis into a fresh ledger + observatory, with trust anchors:
uv run atlas firmware analyze IMAGE --root atlas-data/fw-001 --label Device-1.2.3 \
    --manifest known-good.json \
    --signature update.sig --public-key vendor.pub --signed-target IMAGE

uv run atlas ledger verify atlas-data/fw-001/ledger
# open atlas-data/fw-001/observatory/index.html

# Component inventory (no ledger):
uv run atlas firmware inventory IMAGE [--json]

# Noteworthy changes between two releases:
uv run atlas firmware diff OLD_IMAGE NEW_IMAGE [--json]

# Verify integrity and/or a signature against trust anchors:
uv run atlas firmware verify IMAGE --manifest known-good.json
uv run atlas firmware verify IMAGE --signature update.sig --public-key vendor.pub --signed-target IMAGE

# Render / query a stored analysis:
uv run atlas firmware report  atlas-data/fw-001/reports/<id>/analysis.json
uv run atlas firmware inspect atlas-data/fw-001/reports/<id>/analysis.json findings --kind network
```

`IMAGE` is a `.tar`/`.tar.gz`/`.zip` archive, or a directory holding an
already-extracted root filesystem. Formats BLACK GLASS does not parse
(squashfs, cpio, raw flash) are reported as unsupported with guidance to extract
them with a dedicated tool and pass the resulting directory.

## Ledger integration

An analysis is recorded with the **existing** ATLAS vocabulary, so
`atlas ledger verify` checks it with the same rules as any experiment and the
existing observatory renders it unchanged:

- `preregistration` — the analysis plan, question and acceptance criteria;
- `dataset` — a verifiable manifest of the image's files (`origin: external`);
- `run` — the deterministic in-process analysis pass, with engine-source
  provenance and the full canonical analysis stored as a content-addressed
  artifact the run points to;
- `claim` → `challenge` → `verdict` — one per finding, as described above;
- `report` — the assembled findings, limitations and reproduction metadata.

## Scientific validation

`tests/test_blackglass_pipeline.py` evaluates the Phase-5 criteria against the
fully-specified synthetic image (exact ground truth):

- **component identification accuracy** — the detected ELF set equals the known
  set (perfect precision and recall on the fixture);
- **service-dependency reconstruction** — services, `ExecStart` resolution and
  `DT_NEEDED` library edges match ground truth, with no unresolved libraries;
- **network false-positive rate** — non-network binaries (`busybox`, `libc`,
  `config-helper`) are never flagged as listeners; socket-symbol findings are
  never `verified`;
- **run-to-run consistency** — two independent ingests of the same image produce
  byte-identical canonical analyses;
- **version-diff sensitivity** — the v1→v2 diff detects the new service, the
  removed service, the changed binary's new `SSL_new` import, and the new port;
- **negative controls** — random bytes are classified as opaque `data`, not a
  fabricated ELF; a truncated ELF raises rather than inventing fields; signature
  and integrity checks fail closed.

The Ed25519 implementation is pinned by the official RFC 8032 known-answer
vectors (`tests/test_blackglass_signing.py`) and, where `cryptography` is
installed, cross-checked against it. The ELF reader is cross-checked against
`readelf` when a toolchain is present.

## Limitations

- Static analysis only; no finding is a runtime observation.
- Linking a symbol is evidence of a capability, not proof the code path runs.
- `dlopen()` and other dynamic loading are invisible to static analysis.
- Configuration ports are shipped defaults; a device may be reconfigured.
- Only tar, zip and extracted directories are parsed; other on-disk formats are
  reported as unsupported, not guessed.
- Integrity/signature results are only as trustworthy as the trust anchors you
  supply; with none, the verdict is `unverifiable`.
- The bundled `ed25519_ref` is for verification and demo fixtures; for production
  signing or RSA/ECDSA, install `cryptography`.

## Reproducible demonstration

The demonstration uses only self-generated, redistributable fixtures — no
proprietary firmware, no compiler, no network:

```sh
uv run python scripts/make_blackglass_fixtures.py --out atlas-data/bg-fixtures
uv run atlas firmware analyze atlas-data/bg-fixtures/fw-v1.tar.gz \
    --root atlas-data/bg-001 --label ExampleOS-v1 \
    --manifest atlas-data/bg-fixtures/manifest-v1.json \
    --signature atlas-data/bg-fixtures/fw-v1.tar.gz.sig \
    --public-key atlas-data/bg-fixtures/ed25519.pub \
    --signed-target atlas-data/bg-fixtures/fw-v1.tar.gz
uv run atlas ledger verify atlas-data/bg-001/ledger
uv run atlas firmware diff atlas-data/bg-fixtures/fw-v1.tar.gz atlas-data/bg-fixtures/fw-v2.tar.gz
```

Pre-generated outputs are committed under
[`docs/demonstration/blackglass/`](demonstration/blackglass/): the Markdown
report, the canonical `analysis.json`, the service graph (DOT + SVG) and the
version diff.

## Analysing your own firmware

Point BLACK GLASS at a directory you extracted yourself, or at a tar/zip you are
authorised to analyse:

```sh
# e.g. extract a squashfs root with unsquashfs, then:
uv run atlas firmware analyze ./extracted-rootfs --root atlas-data/mydevice --label MyDevice-fw
```

Supply your own trust anchors (a known-good hash manifest, or the vendor's
public key and a detached signature) to turn integrity and signature findings
from `unverifiable` into `verified`/`failed`. BLACK GLASS neither obtains images
nor assumes you are permitted to analyse one — that judgement is yours.
