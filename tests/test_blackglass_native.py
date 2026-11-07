"""Independent checks for hash-bound native call graph imports.

These fixtures exercise the importer and ledger, not Ghidra's accuracy.
A genuine Ghidra run is still needed to substantiate any real call edges.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.analyze import analyze
from rain_atlas.blackglass.ingest import ingest
from rain_atlas.blackglass.inventory import build_inventory
from rain_atlas.blackglass.native import load_snapshot
from rain_atlas.canonical import sha256_json
from rain_atlas.cli import main
from rain_atlas.ledger.store import Ledger


def _case(tmp_path):
    root = fixtures.build_image(tmp_path / "firmware", variant="v1")
    image = ingest(root)
    elf = next(c for c in build_inventory(image) if c.path == "usr/sbin/httpd")
    document = {
        "schema": "blackglass.native-calls/v1",
        "tool": "ghidra",
        "binary": elf.path,
        "sha256": elf.sha256,
        "functions": [
            {"entry": "0x401000", "name": "entry", "size": 48, "calls": ["0x401050", "0x401900"]},
            {"entry": "0x401050", "name": "helper", "size": 24, "calls": []},
        ],
    }
    export = tmp_path / "calls.json"
    export.write_text(json.dumps(document), encoding="utf-8")
    return image, export, document


def test_import_calls_attaches_evidence_without_promoting_static_inference(tmp_path):
    image, export, _ = _case(tmp_path)
    report = analyze(image, native_snapshots=[export])
    edges = {(e.src, e.dst, e.kind) for e in report.graph.edges}
    assert (
        "function:usr/sbin/httpd:0x401000",
        "function:usr/sbin/httpd:0x401050",
        "calls",
    ) in edges
    assert (
        "function:usr/sbin/httpd:0x401000",
        "unresolved-call:usr/sbin/httpd:0x401900",
        "calls",
    ) in edges
    assert report.counts["native_functions"] == 2
    assert report.counts["native_resolved_calls"] == 1
    assert report.counts["native_unresolved_calls"] == 1
    observations = [f for f in report.findings if f.kind == "native-call"]
    assert len(observations) == 2
    assert all(f.confidence == "high" and f.crosscheck["outcome"] == "inconclusive" for f in observations)
    assert all(f.evidence[0].sha256 == report.parameters.get("bogus", f.evidence[0].sha256)
               for f in observations)
    assert report.parameters["native_evidence"][0]["snapshot_sha256"].startswith("sha256:")


def test_native_graph_is_deterministic_for_shuffled_export(tmp_path):
    image, export, doc = _case(tmp_path)
    first = analyze(image, native_snapshots=[export])
    doc["functions"].reverse()
    doc["functions"][1]["calls"].reverse()
    export.write_text(json.dumps(doc), encoding="utf-8")
    second = analyze(image, native_snapshots=[export])
    assert [e for e in first.graph.edges] == [e for e in second.graph.edges]
    # The canonical reports correctly differ because the evidence-file SHA differs.
    assert sha256_json(asdict(first)) != sha256_json(asdict(second))
    assert first.counts == second.counts


@pytest.mark.parametrize("mutation", [
    {"sha256": "sha256:" + "0" * 64},
    {"binary": "../usr/sbin/httpd"},
    {"binary": "/usr/sbin/httpd"},
    {"tool": "unknown"},
    {"schema": "unspecified"},
])
def test_refuses_unbound_or_unrecognised_native_input(tmp_path, mutation):
    image, export, doc = _case(tmp_path)
    doc.update(mutation)
    export.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        load_snapshot(export, build_inventory(image))


def test_refuses_duplicate_entries_and_excessive_snapshots(tmp_path):
    image, export, doc = _case(tmp_path)
    doc["functions"].append(dict(doc["functions"][0]))
    export.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate native function"):
        load_snapshot(export, build_inventory(image))
    export.write_bytes(b" " * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="input cap"):
        load_snapshot(export, build_inventory(image))


def test_cli_native_evidence_is_recorded_in_existing_ledger(tmp_path, capsys):
    image, export, _ = _case(tmp_path)
    output = tmp_path / "report"
    assert main([
        "firmware", "analyze", str(image.root), "--root", str(output),
        "--native-snapshot", str(export),
    ]) == 0, capsys.readouterr()
    assert Ledger(output / "ledger").verify() == []
    analysis = next(output.rglob("analysis.json"))
    data = json.loads(analysis.read_text(encoding="utf-8"))
    assert data["counts"]["native_functions"] == 2
    assert any(f["kind"] == "native-call" for f in data["findings"])
    assert (output / "observatory" / "index.html").exists()
