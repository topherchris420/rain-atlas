"""End-to-end CLI tests for the `atlas firmware` command group."""

from __future__ import annotations

import json

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.signing import ed25519_ref as ed
from rain_atlas.cli import main
from rain_atlas.ledger.store import Ledger


def _fixtures(tmp_path):
    v1 = fixtures.build_image(tmp_path / "fw-v1", variant="v1")
    v2 = fixtures.build_image(tmp_path / "fw-v2", variant="v2")
    tar1 = fixtures.pack_tar(v1, tmp_path / "fw-v1.tar.gz")
    tar2 = fixtures.pack_tar(v2, tmp_path / "fw-v2.tar.gz")
    seed = bytes(range(32))
    (tmp_path / "ed.pub").write_text(ed.public_key(seed).hex())
    (tmp_path / "fw-v1.sig").write_text(ed.sign(seed, tar1.read_bytes()).hex())
    return v1, v2, tar1, tar2


def test_cli_inventory_json(tmp_path, capsys):
    _fixtures(tmp_path)
    assert main(["firmware", "inventory", str(tmp_path / "fw-v1.tar.gz"), "--json"]) == 0
    items = json.loads(capsys.readouterr().out)
    assert any(i["path"] == "usr/sbin/httpd" and i["kind"] == "elf" for i in items)


def test_cli_analyze_and_verify_ledger(tmp_path, capsys):
    _fixtures(tmp_path)
    code = main(
        [
            "firmware",
            "analyze",
            str(tmp_path / "fw-v1.tar.gz"),
            "--root",
            str(tmp_path / "out"),
            "--label",
            "ExampleOS-v1",
            "--signature",
            str(tmp_path / "fw-v1.sig"),
            "--public-key",
            str(tmp_path / "ed.pub"),
            "--signed-target",
            str(tmp_path / "fw-v1.tar.gz"),
        ]
    )
    assert code == 0, capsys.readouterr()
    out = capsys.readouterr().out
    assert "F1 PASS" in out and "observatory" in out
    assert Ledger(tmp_path / "out" / "ledger").verify() == []
    assert (tmp_path / "out" / "observatory" / "index.html").exists()


def test_cli_diff(tmp_path, capsys):
    _fixtures(tmp_path)
    assert (
        main(["firmware", "diff", str(tmp_path / "fw-v1.tar.gz"), str(tmp_path / "fw-v2.tar.gz"), "--json"])
        == 0
    )
    diff = json.loads(capsys.readouterr().out)
    assert diff["summary"]["services_added"] >= 1


def test_cli_verify_signature(tmp_path, capsys):
    _fixtures(tmp_path)
    good = main(
        [
            "firmware",
            "verify",
            str(tmp_path / "fw-v1.tar.gz"),
            "--signature",
            str(tmp_path / "fw-v1.sig"),
            "--public-key",
            str(tmp_path / "ed.pub"),
            "--signed-target",
            str(tmp_path / "fw-v1.tar.gz"),
        ]
    )
    assert good == 0
    assert "VERIFIED" in capsys.readouterr().out


def test_cli_report_and_inspect_roundtrip(tmp_path, capsys):
    _fixtures(tmp_path)
    main(["firmware", "analyze", str(tmp_path / "fw-v1"), "--root", str(tmp_path / "out")])
    capsys.readouterr()
    # locate analysis.json
    analysis = next((tmp_path / "out" / "reports").rglob("analysis.json"))
    assert main(["firmware", "report", str(analysis)]) == 0
    assert "BLACK GLASS firmware analysis" in capsys.readouterr().out
    assert main(["firmware", "inspect", str(analysis), "findings", "--kind", "network"]) == 0
    findings = json.loads(capsys.readouterr().out)
    assert all(f["kind"] == "network" for f in findings)
