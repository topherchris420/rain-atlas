# Integration with existing Vers3Dynamics projects

Phase 0 audit, 2026-10-30. Sources were read without modifying them:
lop-nur-twin `origin/main` @ `0ad3609`, james_library (archived, GitHub), James
(`main` lineage), Jasmine, Luca, rain-pipeline, dynamic-resonance-rooting,
vers3dynamics-cymatics and james-library-showcase. "Read" means confirmed in
source; "inferred" means a design conclusion, not a fact about those projects.

**Status (v0.1): no adapter is implemented yet.** Everything below is the
audit and the plan; `rain_atlas.adapters` is an empty package. ATLAS does not
read from, write to, or call any of these projects today.

Rules for every adapter:

* optional module under `rain_atlas.adapters`, never imported by the core;
* reads documented interfaces or files only; never writes another project's
  state directories, registries, memories, prompts, ledgers or localStorage;
* ships with a contract test that skips cleanly when the external system is
  absent;
* records the external system's version/commit it was tested against.

## 1. R.A.I.N. Lab (lop-nur-twin)

What exists (read):

* Runtime moved from james_library to lop-nur-twin on 2026-10-06
  (`docs/RAIN_MIGRATION.md`). Browser → `/api/rain/*` (`server/rain/handler.ts`)
  → `src/rain/runtime.ts`.
* Experiment registry `src/rain/experiments/registry.ts`: once-only writes,
  `rain-experiment/v1` definitions with `runner: {kind: "builtin"|"external"}`,
  `evidence_class: measured|simulated|model_inferred`, runs as
  `rain-experiment-run/v1`, research revisions hash-chained by
  `previous_sha256`. JSON Schemas in `src/rain/experiments/schemas/` are the
  declared language-neutral interface.
* Authorization: `bethesda-experiment-authorization/v1` — the operator types
  the first 8 hex digits of the definition digest; `identity_verified: false`.
* Closed autonomy vocabulary (`src/rain/autonomy/actions.ts`):
  `propose_experiment, inspect_result, inspect_design, stop, record_analysis`;
  readings `supports|contradicts|inconclusive`. The autonomy **critic seat is
  unassigned**.
* Perspectives (`src/rain/meeting/perspectives.ts`): James (Lead
  Scientist/Technician), Jasmine (Hardware Architect, skeptic), Luca (Field
  Topographer/Theorist), Elena (Quantum Information Theorist). They are personas
  inside one meeting, not separate services.
* HTTP routes answer 403 unless same-origin; submissions must carry
  `evidence_class: "simulated"`.

Integration plan (inferred):

1. **ATLAS as an external runner (first adapter).** ATLAS emits a draft
   `rain-experiment/v1` definition with `runner: {kind: "external",
   repository: "rain-atlas", adapter: "atlas-cli"}` and, after execution, a
   `rain-experiment-submission/v1` file validated against lop-nur-twin's own
   schema. Only `simulated` ATLAS results map onto that route. The R.A.I.N.
   registry, not ATLAS, decides its own verdict. ATLAS writes the files into
   its own export directory; the operator submits them.
2. **Read-only ingest.** `atlas ingest rain <dir>` imports R.A.I.N. registry
   records as `dataset` objects with `origin: external`, verifying
   `record_sha256` and the revision chain, quarantined until verified.
3. **Critic seat.** ATLAS's skeptic role can serve the unassigned critic seat
   through the closed vocabulary (`record_analysis` with a reading) once the
   seat's contract is published; until then this is a design target only.
4. **Shared conventions adopted in ATLAS:** digest-prefix approval
   (`atlas approve <first 8 hex>`), `identity_verified: false` attestation,
   `generation: scripted|model` labels on every role output, "a digest is not a
   signature" in docs.

Evidence vocabulary mapping (ATLAS → R.A.I.N. `evidence_class`):

| ATLAS claim | Data origin | R.A.I.N. |
|---|---|---|
| COMPUTED | synthetic | `simulated` |
| OBSERVED / COMPUTED | empirical | `measured` (not accepted by the HTTP submission route) |
| INTERPRETED (model) | any | `model_inferred` |
| INTERPRETED (deterministic rule) | any | not mapped; exported as an annotation |

Risks: same-origin-only API; a registry without `RAIN_REGISTRY_DIR` is a
scratch directory whose ids restart at `V3D-EXP-0001` (never match by id
alone); schemas move quickly (`bethesda-experiment-record/v3`); JS
`JSON.stringify` and Python `json.dumps` format some numbers differently
(`1.0` vs `1`), so cross-language hash checks must use the producer's number
formatting or avoid integral floats.

## 2. James (desktop assistant, Rust, MIT)

* No inbound API (read). Its Lab view is a read-only client that probes
  `127.0.0.1` ports 5173/5174/5175/4173 for `GET /api/rain/status`
  (`rain-bethesda/v2`) and `GET /api/rain/discovery`
  (`rain-discovery-view/v1`).
* Model backends: Ollama `:11434`, LM Studio / OpenAI-compatible `:1234`.
* Action model: every action carries an `Effect`; invocations pass `Policy`,
  `Approval::after_user_review` and a `Budget`.

Plan: ATLAS reaches James through lop-nur-twin (James already reads that). ATLAS
does not serve James's endpoints, to avoid colliding with lop-nur-twin's dev
ports. ATLAS reuses the same two local model endpoints for its optional model
backend.

## 3. Jasmine (workflow engine, TypeScript)

* `127.0.0.1:8787`; `POST /api/v1/flows/:flowId/execute`, `GET /api/v1/runs/:id`
  (+ `/trace`, `/cancel`), SSE `GET /api/runs/:id/events`; bearer or
  `x-api-key` auth (read).
* `package.json` says `UNLICENSED` and there is no LICENSE file.

Plan: an optional adapter may *call* a user-configured Jasmine flow as a model
backend (proposal text only, validated by ATLAS). No Jasmine code is copied
until its license is settled. In ATLAS terms Jasmine's code is a general
workflow engine; its persona is "Hardware Architect", so the
"computational scientist" role stays an ATLAS role, not a claim about Jasmine.

## 4. Luca (network forensics + eBPF observatory, Apache-2.0)

* Not an AI agent. Its observatory labels statements OBSERVED / CORRELATED /
  INFERRED / UNAVAILABLE and preregisters experiments
  (`observatory/experiments/preregistration.json`, results schema
  `luca.observatory.experiments/1`). No real result files are committed.

Plan: `atlas ingest luca <results.json>` as read-only empirical datasets
(`origin: empirical`, OBSERVED only where Luca says OBSERVED). Luca's
preregistration-with-amendments model informs ATLAS's revision records.

## 5. Other projects

| Project | Relevance | License |
|---|---|---|
| rain-pipeline | Closest prior art for the ledger (`rain-experiment-run/v1`, hash-bound data ledger, explore/register/run/verify CLI) | none found — design reference only |
| dynamic-resonance-rooting (`drr-framework`) | FFT/Welch/wavelet, phase synchronisation, recurrence, evidence cards | MIT — optional cross-check backend for the resonance module |
| vers3dynamics-cymatics | Chladni/eigenmode numerics (`physics.js`), dark design tokens | MIT per README metadata, no LICENSE file — reference only |
| james-library-showcase | React 18 + Vite + Tailwind; `DESIGN.md` "research field atlas" palette (paper `#f8f6f1`, graphite `#222320`, ink blue `#3156a3`; Fraunces / Instrument Sans / JetBrains Mono) | none found — palette used as design direction, no code copied |

## 6. Role targets versus current personas

| ATLAS role (brief) | Current persona in code | Mapping |
|---|---|---|
| Principal Investigator | James — Lead Scientist / Technician | closest match |
| Computational Scientist | Jasmine — Hardware Architect (skeptic, agreeableness 0.2) | mismatch |
| Scientific Skeptic | Elena — Quantum Information Theorist ("challenge hand-waving with math") | partial |
| Experimental Engineer | Luca — Field Topographer / Theorist | mismatch |

ATLAS therefore ships role implementations named by role. A user-editable
`roles.toml` may bind a role to a persona label for display, and an adapter
may route a role to an external agent. Neither changes those agents'
identities, prompts or memories.
