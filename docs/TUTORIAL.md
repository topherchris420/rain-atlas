# From a question to inspectable evidence

Use a source checkout, Python 3.11 or 3.12 and `uv`. From the repository root,
`uv sync --locked --python 3.12` installs the Python development environment.
The source checkout supplies the built-in skill catalog. Standalone wheel
installation without a separately supplied catalog is not yet supported.
No model, Node server, cloud account or external service is needed to run ATLAS.

## Run a known-reference experiment

```sh
uv run atlas skills inspect synchronization-sweep
uv run atlas skills test synchronization-sweep synchronization-measure
uv run atlas experiment run synchronization --root atlas-data/sync-001 --replicates 12
uv run atlas ledger verify atlas-data/sync-001/ledger
```

The experiment first records its hypothesis, null, controls, resource budget,
thresholds and analytical reference. It then runs 30 combinations of coupling,
noise and phase lag, each with 12 independent initial-condition/noise streams.
A skeptic checks relative-frequency drift; fresh data challenge the phase
measurement; exact reruns check reproducibility. The analytical reference is
only used for deterministic cases away from the threshold. Noisy/critical truth
remains unavailable for binary error scoring.

Open `atlas-data/sync-001/observatory/index.html` directly. Select a claim in
Evidence explorer to inspect the contributing runs and challenges. Timeline
shows the actual ordered records. Reports retain all conditions, including
contradictions and unresolved findings. PNG and SVG scientific figures and the
original Markdown report are under `reports/`; PNGs and review reports are
downloadable from the offline viewer. Its skill test status says unknown unless
the export actually has such evidence; recorded run counts are separate.

The command refuses an existing ledger. Use a new root for an independent run.
Interrupted runs remain visible; automatic experiment resume is planned.

## Trace and search

```sh
uv run atlas ledger show atlas-data/sync-001/ledger --kind run --full
uv run atlas ledger search atlas-data/sync-001/ledger synchronization --kind claim
uv run atlas env
```

Every new engineered run carries code and skill snapshots, input/output hashes,
environment and a dependency lockfile when run from a checkout. The ledger
verifier checks referenced artifacts as well as the chain. The SQLite search
index is disposable and never the authority. Integrity is not external
authentication and does not make a scientific claim true.

## Compose a proposal without executing it

In the viewer's Composer, specify the question, H0/H1, controls, thresholds,
methods and budget. Download the JSON, then inspect and register it:

```sh
uv run atlas proposal inspect atlas-data/proposal.json
uv run atlas proposal register atlas-data/proposal.json --ledger atlas-data/proposed/ledger
```

Registration prints the preregistration digest. To attest approval, explicitly
provide that full digest and at least its first eight hexadecimal digits:

```sh
uv run atlas approve atlas-data/proposed/ledger sha256:FULL_DIGEST --digest FIRST_8_HEX --operator researcher
```

Approval is a local attestation, not verified identity. These commands never
execute the proposal. A generic proposal scheduler is planned; implemented
experiments use explicit Python orchestration through `Engineer.execute`.
For offline model proposals, set `generation: model` and include model identity,
allowed generation parameters and prompt hash; validation records the proposal
hash. Neither confidence text nor a proposed conclusion is evidence.

## Measure failure

```sh
uv run atlas benchmark --root atlas-data/bench-001 --trials 12
```

Read `benchmark.json` and its observatory. Compare false detections, missed
tones, sample sizes and Wilson intervals. Do not interpret the conditional
frequency RMSE without the detection rates: it excludes misses. Chirp cases
retain outputs but do not pretend to have stationary-tone truth.

## Share and recover deliberately

`atlas observatory export LEDGER --out NEW_DIRECTORY` creates a reviewed-data
projection with no vault/raw-input/log export. It can still contain sensitive
scientific free text and figures. Inspect `review-data.json` before sharing.
The existing spectral research bundle excludes the sealed vault; it is a fuller
scientific artifact and can contain deliberately unsealed truth and local
metadata. Do not confuse it with the privacy-reduced viewer.

`atlas ledger recover BROKEN_LEDGER --out NEW_LEDGER` only recovers a torn,
unterminated final JSON append with a valid complete prefix. It never edits the
original, never repairs tampered completed records and never unblinds a vault.
The new recovery record retains source and discarded-tail hashes. Operator
inspection is still required before continuing scientific work.
