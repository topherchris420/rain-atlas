"""Recording an analysis into the evidence ledger and reading it back."""

from __future__ import annotations

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.analyze import analyze
from rain_atlas.blackglass.ingest import ingest
from rain_atlas.blackglass.inspect import Inspector
from rain_atlas.blackglass.ledger_bridge import record_analysis
from rain_atlas.blackglass.verification import verify_hash_manifest
from rain_atlas.canonical import sha256_file
from rain_atlas.ledger.store import Ledger
from rain_atlas.observatory.export import export


def _report(tmp_path):
    image = ingest(fixtures.build_image(tmp_path / "fw", variant="v1"))
    manifest = {rel: sha256_file(path) for rel, path in image.iter_files()}
    verification = [verify_hash_manifest(image, manifest)]
    return analyze(image, verification=verification)


def test_record_analysis_verifies(tmp_path):
    report = _report(tmp_path)
    ledger = Ledger(tmp_path / "ledger")
    refs = record_analysis(ledger, report)
    assert refs["problems"] == []
    # an independent verifier agrees
    assert Ledger(tmp_path / "ledger").verify() == []
    # every finding produced a claim and a verdict
    kinds = {}
    for entry in ledger.entries():
        kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
    assert kinds["claim"] == len(report.findings)
    assert kinds["verdict"] == len(report.findings)
    assert kinds["preregistration"] == 1 and kinds["run"] == 1 and kinds["report"] == 1


def test_verified_integrity_yields_supported_verdict(tmp_path):
    report = _report(tmp_path)
    ledger = Ledger(tmp_path / "ledger")
    refs = record_analysis(ledger, report)
    integrity = [f for f in refs["findings"] if f["kind"] == "integrity"]
    assert integrity and integrity[0]["verdict"] == "supported"


def test_observatory_export_from_blackglass_ledger(tmp_path):
    report = _report(tmp_path)
    ledger = Ledger(tmp_path / "ledger")
    record_analysis(ledger, report)
    out = export(tmp_path / "ledger", tmp_path / "observatory")
    assert out.exists()
    html = (tmp_path / "observatory" / "index.html").read_text(encoding="utf-8")
    assert "blackglass-analyze" in html or "firmware" in html.lower()


def test_inspector_is_read_only(tmp_path):
    import dataclasses

    report = _report(tmp_path)
    insp = Inspector(dataclasses.asdict(report))
    assert {c["path"] for c in insp.components("elf")} >= {"usr/sbin/httpd"}
    httpd_findings = insp.findings(kind="network")
    assert httpd_findings
    first = insp.findings()[0]
    assert insp.evidence_for(first["id"])
    neighbors = insp.graph_neighbors("exe:usr/sbin/httpd")
    assert any("links" in edge for edge in neighbors["out"])
    # queries never mutate: a fresh inspector sees the same thing
    assert insp.query("counts")["files"] == report.counts["files"]
