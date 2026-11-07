# BLACK GLASS demonstration

These artifacts are the recorded output of analysing a **self-generated,
legally-redistributable** synthetic firmware image — no proprietary firmware, no
network download and no compiler are involved. Everything here is reproducible
from the repository with:

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

| File | What it is |
|---|---|
| [`report.md`](report.md) | Evidence-linked Markdown report for the v1 image |
| [`analysis.json`](analysis.json) | The canonical, machine-readable analysis (every component, edge and piece of evidence) |
| [`graph.svg`](graph.svg) | Service / dependency / trust-boundary graph (self-contained SVG) |
| [`graph.dot`](graph.dot) | The same graph as Graphviz DOT (`dot -Tsvg graph.dot`) |
| [`diff.md`](diff.md) | Noteworthy changes from v1 → v2 (new MQTT service and port, removed telnet, changed `httpd`) |

The synthetic image is fully specified, which is what lets the test suite
measure component-identification accuracy, dependency reconstruction, the
network false-positive rate, run-to-run determinism and diff sensitivity against
exact ground truth. Running `atlas firmware analyze` locally additionally writes
the offline observatory (`atlas-data/bg-001/observatory/index.html`); it is not
committed here because the recorded run carries an engine-source provenance hash
that changes with every edit to the engine, whereas the files above are stable.
