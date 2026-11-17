# REA: Recursive Engineering & Analysis

**Status:** implemented and tested. This document describes the REA
replication framework, the nine recorded investigations, and the unified
R.A.I.N. demonstrations built from their replicas.

REA is the Vers3Dynamics research method for investigating reference
systems and independently reconstructing selected capabilities:

**Discover → Investigate → Reconstruct → Verify → Integrate → Experiment → Improve**

The framework lives in `rain_atlas.rea`; the nine investigations live in
`rain_atlas.rea.investigations`; the reconstructed capabilities live in
their own modules (`rain_atlas.memory`, `rain_atlas.observability`, …).

## The evidence rules

Every statement in an investigation package carries one of four
classifications, enforced at package-build time:

| Classification | Meaning |
|---|---|
| **OBSERVED** | Directly examined in an authorized environment (pinned source commit, executed reference SDK, or fetched public documentation). |
| **COMPUTED** | Produced by a recorded, reproducible calculation or software execution. |
| **INFERRED** | Derived from cited evidence but not directly observed. Must list its basis. |
| **UNKNOWN** | Insufficient evidence; may not cite sources it cannot assess. |

Presenting inferred behavior as observed is the primary failure mode the
rules exist to prevent. Closed-source references (Maxxwell, Arga Labs,
Infera) are recorded with INFERRED evidence and explicit open questions;
their replicas claim no parity with products that were not executed.

## The nine targets

| Target | Reference | License | Replica module | Confidence |
|---|---|---|---|---|
| T01 Mem0 | mem0ai 2.2.1, commit `f1791da` | Apache-2.0 | `rain_atlas.memory` | high |
| T02 Langfuse | commit `01e7f5f` | MIT (core) | `rain_atlas.observability` | high |
| T03 Browser Use | commit `4b5b1b0` | MIT | `rain_atlas.browser` | moderate |
| T04 Omnara | commit `f7d05d0` | Apache-2.0 | `rain_atlas.mission` | high |
| T05 RunAnywhere | commit `87865ea` | own license; reference-only | `rain_atlas.inference` | moderate |
| T06 Epicenter | commit `206ca98` | AGPL-3.0; reference-only | `rain_atlas.knowledge` | moderate |
| T07 Maxxwell | docs.maxxwell.dev (2026-11-16) | proprietary; docs only | `rain_atlas.mission` | moderate |
| T08 Arga Labs | argalabs.com docs (2026-11-16) | proprietary; docs only | `rain_atlas.simulation` | moderate |
| T09 Infera | infera.bio (2026-11-16) | proprietary; docs only | `rain_atlas.protocol` | low |

License posture: no reference source is included, linked or copied into
this repository. Epicenter (AGPL) and RunAnywhere (own terms) are treated
as reference-only; the Maxxwell documentation explicitly separates what
ships today from announced direction, and the investigation records only
the former as reference behavior.

## What they actually sell

Each investigation records the company's commercial product (per its YC
company page or launch materials, fetched 2026-11-17) as OBSERVED
evidence, and states explicitly which parts of the sold product are beyond
the replica's scope. The reconstructions target the *sold capabilities*
that survive local-first scientific use, not the business:

| Company | What they sell (as recorded) | Replica reconstructs |
|---|---|---|
| Mem0 | Hosted memory platform (app.mem0.ai) + OSS SDK; graph+vector+KV hybrid datastores; $24M raised | The memory-layer capability, locally; graph tier out of scope |
| Langfuse | Langfuse Cloud / self-host / enterprise LLM engineering platform; 50k+ companies; acquired by ClickHouse (Jan 2026) | The tracing/eval data model, in-process; hosted UI out of scope |
| Browser Use | Browser Use Cloud: hosted web agents with proxy rotation, persistent logins, parallel browsers ($30/mo; $17M raised) | Authorized structured observation with provenance; hosted fleet out of scope |
| Omnara | Model-agnostic agent control plane; self-host or managed cloud; BYO-computer and BYO-model | Mission task/approval/supervision semantics, in-process |
| RunAnywhere | Wally: fastest inference for open frontier models (OpenAI-compatible API); on-device SDKs; trnRT/MetalRT engines | The OpenAI-compatible provider abstraction; serving stack out of scope |
| Epicenter | Local-first open-source app ecosystem sharing one plain-text+SQLite memory (Whispering first app; MIT) | The shared local-first store with conflict resolution |
| Rindler | Maxxwell (multi-agent IDE with orchestrator-on-top, takeover) + Rindler (websites as deterministic APIs over MCP) | Fleet supervision: status, waiting-on-you, takeover; orchestrator and website-API out of scope |
| Arga Labs | Twin Runs, Scenarios, Test Runs: stateful twins of 33 services, 100k+ instances run | The stateful twin/scenario/fault concepts for instruments |
| Infera | Project IO protocol compiler (plain English → instrument instructions, digital-twin verification, human approval) + BioBase | The compile-validate-approve loop for simulated instruments |


## Tool-derived evidence (morluto/rea)

The morluto/rea reverse-engineering tool was executed against real reference
artifacts to produce tool-derived OBSERVED evidence, pinned by artifact
digests inside the investigation packages (T01 `mem0-obs-5`, T02
`lf-obs-4`, T03 `bu-obs-3`):

| Target | Artifact inspected | Tool | Key findings |
|---|---|---|---|
| T01 Mem0 | `memory/__pycache__/main.cpython-312.pyc` + `storage...pyc` of the installed mem0ai 2.2.1 (sha256 `b7fa6186…`, `b57fe704…`) | `inspect_python_pyc` (REA CPython pyc parser) | 106 code objects; full method inventory at matching line numbers (add 760, search 1393, history 1960, `_create_memory` 1975; `SQLiteManager.add_history` 150 / `get_history` 227); also reveals out-of-scope reference capabilities (entity stores, project APIs, chat) |
| T02 Langfuse | `_client/__pycache__/client.cpython-312.pyc` of langfuse SDK 5.2.0 (sha256 `fbb24010…`) | `inspect_python_pyc` | 98 code objects; `start_observation` overloads, `create_event`, `create_score`, `score_current_span/trace`, dataset/experiment methods, `ObservationLevel`/`SpanLevel`/`ScoreDataType` and the `LangfuseEvent/Generation/Span` clients |
| T03 Browser Use | `agent/…/service.cpython-312.pyc` + `browser/…/browser.cpython-312.pyc` compiled from the pinned commit (sha256 `835789ab…`, `66ada273…`) | `inspect_python_pyc` | 43 + 64 code objects; the agent loop with `_judge` success evaluation and the browser lifecycle with CDP screenshots, tabs and downloads |

The pyc inspections never executed reference code; they parse compiled
bytecode read-only. Digests are pinned so the analyzed artifacts are
reproducibly identified, and a regression test
(`test_tool_derived_evidence_pinned`) enforces that the tool-derived
evidence items cite the tool and pin their digests.

## Vendored reference code (license-permitted reuse)

Where a permissive license allows it, the replicas now include proven
reference code rather than re-implementations:

* `rain_atlas.memory.vendor.mem0` — Mem0's retrieval scoring
  (Apache-2.0, from `mem0/utils/scoring.py` and `lemmatization.py` at the
  pinned commit): BM25 sigmoid normalization and additive hybrid ranking.
  The memory engine's default `ranking="hybrid"` path feeds standard
  Okapi BM25 through the vendored sigmoid and combines it with the lexical
  channel exactly as the reference ranks hybrid results. License, NOTICE
  and attribution are preserved in the vendor directory. A differential
  test in the reference environment verifies the vendored functions
  produce identical outputs to the installed mem0ai 2.2.1 (the released
  package names explain-detail keys differently than the pinned commit;
  ranking scores and order are identical — that deviation is recorded in
  the investigation).

This is the extent of intentional reuse: all other replicas remain
independent implementations, and AGPL (Epicenter) and closed-source
references remain untouched.

## Conformance evidence

### Differential conformance (reference executed)

For Mem0, the reference SDK itself was executed locally and compared with
the replica:

```bash
# One-time reference environment (see below for what is installed):
uv venv <path> --python 3.12
uv pip install --python <path>/Scripts/python.exe mem0ai pytest numpy scipy matplotlib
uv pip install --python <path>/Scripts/python.exe -e . --no-deps

<path>/Scripts/python.exe -m pytest tests/reference/test_mem0_conformance.py
```

The reference runs with the default in-memory qdrant vector store, a
deterministic fake embedding function and `infer=False` (the documented
raw-add path that does not call a language model). Twelve differential
tests compare documented behavioral invariants: ADD event results, scope
isolation, ValueError when search lacks an entity filter, ADD/UPDATE
history sequences with old/new values, delete hiding records while
preserving history, and scored search result shape. All twelve passed
against mem0ai 2.2.1 (recorded 2026-11-16).

The standard ATLAS suite never requires mem0: the module skips when the
package is not installed.

### Behavioral-spec conformance

For the remaining targets the references were not executed (proprietary
products) or were verified at the source/documentation level. Their
conformance records compare the replica against the recorded reference
model with structural comparators, and each replica feature names its
tests. Nothing is claimed as OBSERVED that was not directly examined.

## The unified demonstrations

### The vertical slice

```bash
uv run atlas rain slice --root atlas-data/rain-slice --seed 7
uv run atlas ledger verify atlas-data/rain-slice/ledger
```

One complete scientific mission through every replica: a hypothesis is
proposed through the inference provider (labeled `model` generation), the
protocol compiler validates it, an approval gate pauses execution until an
honestly-labeled operator proxy resolves it, agents select and run
experiments on the simulation twin while consulting scientific memory, the
evaluator applies the preregistered decision rule, the skeptic replicates
on a held-out condition, and the traces export into a verified ATLAS
ledger. Every action records its generation (scripted/model/human).

### The central scientific experiment

```bash
uv run atlas rain central --root atlas-data/rain-central
uv run atlas ledger verify atlas-data/rain-central/ledger
```

Research question: *does combining reconstructed capabilities (adaptive
selection + persistent scientific memory) design and execute experiments
more effectively than simpler baseline architectures?*

Four arms share the same decision book, twin family and budget; they
differ only in selection policy and persistent memory. Preregistered
hypotheses (H1: ≥25% experiment reduction from memory; H2: no
false-conclusion increase beyond +5pp; H3: adaptive arms beat grid and
random) are evaluated against recorded runs, with claims, challenges and
verdicts appended to the ledger.

**Recorded outcome (2026-11-16, this repository, 6 programs × 3
missions):** H1, H2 and H3 all held — the memory arm used 6 total
experiments versus 19 without memory (68% reduction), adaptive arms
decided in fewer mean experiments per mission than grid (3.17) and
random (1.44), and no arm produced a false conclusion (a weak test at
this noise level; the limitation is recorded in the ledger report).
Replication succeeded in 6/6 programs per arm. All policies are
deterministic scripted code — no language model participates in any arm.

A negative result was acceptable by design; this one happened to be
positive. The claims are bounded to this synthetic discrimination problem
and are recorded with their limitations in the ledger.

## CLI

```bash
uv run atlas rea list            # the nine investigations and their replicas
uv run atlas rea show T01-mem0   # one evidence package, rendered
uv run atlas rea export --out docs/rea-packages  # JSON + markdown for all nine
uv run atlas rain slice --root atlas-data/rain-slice
uv run atlas rain central --root atlas-data/rain-central
```

## Limitations and open questions

- The replicas reconstruct *capability subsets*, not products. Every
  deviation is recorded in the investigation packages.
- Maxxwell, Arga Labs and Infera were investigated from public
  documentation only; their runtime behavior is UNKNOWN and no parity is
  claimed.
- The central experiment's discrimination problem is synthetic and
  moderately easy at its noise level; harder regimes (model
  misspecification, changing ground truth across programs) are future work.
- The browser adapter observes fetched HTML; it does not drive a real
  browser or execute page JavaScript.
- Streaming generation and tool calling are declared in the inference
  provider interface but not yet exercised by an integrated flow.
