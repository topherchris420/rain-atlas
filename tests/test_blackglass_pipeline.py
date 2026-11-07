"""Scientific validation of the analysis pipeline against known ground truth.

The synthetic image is fully specified, so these tests measure component
identification accuracy, dependency-reconstruction accuracy, the network-surface
false-positive rate, run-to-run consistency and version-diff sensitivity against
an exact baseline — the Phase-5 checks a reviewer can re-run.
"""

from __future__ import annotations

import dataclasses

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.analyze import analyze
from rain_atlas.blackglass.diff import diff_reports
from rain_atlas.blackglass.ingest import ingest
from rain_atlas.canonical import canonical_bytes, sha256_bytes

GROUND_TRUTH_ELF = {
    "bin/busybox",
    "lib/libc.so.6",
    "lib/libssl.so.1",
    "usr/bin/config-helper",
    "usr/sbin/httpd",
    "usr/sbin/telnetd",
}
GROUND_TRUTH_SERVICES = {"systemd:httpd.service", "systemd:config.service", "sysv:telnetd"}
GROUND_TRUTH_LISTENERS = {"usr/sbin/httpd", "usr/sbin/telnetd"}  # import bind+listen
NON_NETWORK_BINARIES = {"bin/busybox", "lib/libc.so.6", "usr/bin/config-helper"}
GROUND_TRUTH_PORTS = {22, 8080, 8443}


def _analyze(tmp_path, variant="v1"):
    return analyze(ingest(fixtures.build_image(tmp_path / variant, variant=variant)))


def test_component_identification_accuracy(tmp_path):
    report = _analyze(tmp_path)
    found = {c.path for c in report.components if c.kind == "elf"}
    # perfect precision and recall against the known ELF set
    assert found == GROUND_TRUTH_ELF
    machines = {c.detail["machine"] for c in report.components if c.kind == "elf"}
    assert machines == {"x86-64"}


def test_service_dependency_reconstruction(tmp_path):
    report = _analyze(tmp_path)
    assert {s.id for s in report.services} == GROUND_TRUTH_SERVICES
    httpd = next(s for s in report.services if s.name == "httpd.service")
    assert httpd.exec_component == "usr/sbin/httpd"
    assert "config.service" in httpd.requires
    # the library dependency edge httpd -> libssl is reconstructed from DT_NEEDED
    link_edges = {(e.src, e.dst) for e in report.graph.edges if e.kind == "links"}
    assert ("exe:usr/sbin/httpd", "exe:lib/libssl.so.1") in link_edges
    assert ("exe:usr/sbin/httpd", "exe:lib/libc.so.6") in link_edges
    assert report.counts["unresolved_libraries"] == []


def test_network_surface_and_false_positive_rate(tmp_path):
    report = _analyze(tmp_path)
    listeners = {
        n.component for n in report.network if n.kind == "socket-symbol" and n.confidence == "medium"
    }
    assert GROUND_TRUTH_LISTENERS <= listeners
    # false-positive control: non-network binaries are never flagged as listeners
    assert not (NON_NETWORK_BINARIES & listeners)
    assert set(report.counts["listening_ports"]) == GROUND_TRUTH_PORTS
    # inference discipline: no socket-symbol finding is 'verified'
    for n in report.network:
        if n.kind == "socket-symbol":
            assert n.confidence in ("medium", "low")


def test_results_are_consistent_across_runs(tmp_path):
    a = sha256_bytes(canonical_bytes(dataclasses.asdict(_analyze(tmp_path / "a"))))
    b = sha256_bytes(canonical_bytes(dataclasses.asdict(_analyze(tmp_path / "b"))))
    assert a == b


def test_diff_detects_meaningful_changes(tmp_path):
    v1 = _analyze(tmp_path, "v1")
    v2 = _analyze(tmp_path, "v2")
    diff = diff_reports(v1, v2)
    assert "systemd:mqtt.service" in diff.services_added
    assert "sysv:telnetd" in diff.services_removed
    changed = {c["path"] for c in diff.changed}
    assert "usr/sbin/httpd" in changed
    httpd_change = next(c for c in diff.changed if c["path"] == "usr/sbin/httpd")
    assert "SSL_new" in httpd_change["imports_added"]
    new_ports = {n.get("port") for n in diff.network_added}
    assert 1883 in new_ports  # the new MQTT broker port


def test_findings_all_have_evidence_and_crosscheck(tmp_path):
    report = _analyze(tmp_path)
    assert report.findings
    for f in report.findings:
        assert f.evidence, f.id
        assert f.crosscheck and f.crosscheck["outcome"] in ("corroborated", "contradicted", "inconclusive")


def test_unknown_content_is_not_misclassified(tmp_path):
    # random bytes are opaque data, never a parsed ELF or a fabricated component
    root = fixtures.build_image(tmp_path / "fw")
    (root / "opt").mkdir(parents=True, exist_ok=True)
    (root / "opt/blob.bin").write_bytes(bytes(range(256)) * 8)
    report = analyze(ingest(root))
    blob = next(c for c in report.components if c.path == "opt/blob.bin")
    assert blob.kind == "data"
