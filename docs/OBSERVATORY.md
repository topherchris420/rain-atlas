# Offline scientific observatory

```sh
uv run atlas observatory export atlas-data/spectral-recovery/ledger --out atlas-data/view-001
```

Open `atlas-data/view-001/index.html` directly. No server, JavaScript package
installation, model, external font, network request or execution API is needed.
The deep teal interface includes experiment selection and search, a claim to
evidence explorer, the recorded scientific timeline, the skill catalog, reports
with PNG downloads, and a local proposal composer. Keyboard navigation and
small-screen layouts are supported. Motion respects reduced-motion settings.

The source ledger and its referenced artifacts must verify before export.
Each export uses a new directory and records the source head. Historical
records are never rewritten. The snapshot is **derived**, not the original
ledger, and does not itself assert cryptographic authenticity. It does not
poll for live processes: an experiment without a report is labelled incomplete
in the snapshot. Re-export to another directory after a local run progresses.

Only explicit, allowlisted scientific fields enter the projection. Raw inputs,
execution logs, environment paths, operator identity and sealed values are
omitted. PNGs referenced by reports are the only previewable image type.
Untrusted text uses text nodes; embedded JSON escapes HTML delimiters. A hash
based Content Security Policy blocks connections, forms and external assets.
**Review scientific text and figures before sharing**: they can contain private
research. This projection is privacy-conscious, not an automatic declassifier.
Full original reproducibility bundles still contain environment details.

Skill execution counts refer only to selected recorded runs with matching
content hashes. A declared example is not a passing test: test status remains
unknown when no test result accompanies the export.

The composer creates `atlas.proposal/v1` JSON. It does not approve or execute.
Inspect with `atlas proposal inspect proposal.json`; optionally register a
preregistration with `atlas proposal register proposal.json --ledger PATH`.
Skill versions/hashes, declared budgets and a closed schema are checked again
by Python. Generic proposal execution is planned; use the tested experiment
commands for actual work. An offline model may emit the same schema with
`generation: model` plus identity, prompt hash and generation parameters.
That records provenance of a proposal, never experimental evidence.
