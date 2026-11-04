import json
import zipfile
from pathlib import Path

import pytest

from conftest import fixture_ref
from rain_atlas.exec.context import valid_artifact_name
from rain_atlas.exec.runner import run_skill
from rain_atlas.experiments.spectral_recovery import _bundle
from rain_atlas.ledger.store import Ledger, LedgerError
from test_ledger import prereg


@pytest.mark.parametrize("name", ["../secret", "..\\secret", "/etc/passwd", "C:\\x", "x:y", "NUL", "con.txt", "x.", "", ".."])
def test_portable_artifact_names(name):
    assert not valid_artifact_name(name)


def test_untrusted_backend_refuses_before_execution(tmp_path):
    result = run_skill(fixture_ref("echo", "untrusted"), {"values": [1]}, seed=0, runs_dir=tmp_path)
    assert result.status == "refused"
    assert not result.run_dir.exists()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_limits_refused(tmp_path, timeout):
    result = run_skill(fixture_ref("echo"), {"values": [1]}, seed=0, runs_dir=tmp_path, timeout_s=timeout)
    assert result.status == "refused"


def test_missing_and_tampered_artifact_are_detected(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    artifact = ledger.put_bytes(b"data")
    ledger.append("dataset", {"experiment": exp, "name": "sample", "origin": "synthetic",
                             "media_type": "text/plain", "object": artifact, "provenance": {}})
    assert ledger.verify() == []
    ledger._object_path(artifact).write_bytes(b"edited")
    assert any("hash check" in p for p in ledger.verify())
    ledger._object_path(artifact).unlink()
    assert any("not found" in p for p in ledger.verify())


def test_malformed_chain_is_diagnosed_without_rewrite(tmp_path):
    ledger = Ledger(tmp_path)
    prereg(ledger)
    with ledger.log_path.open("ab") as fh:
        fh.write(b'{"seq":')
    before = ledger.log_path.read_bytes()
    assert "malformed log line" in " ".join(ledger.verify())
    assert ledger.log_path.read_bytes() == before


def test_hash_reference_rejects_traversal(tmp_path):
    with pytest.raises(LedgerError):
        Ledger(tmp_path).get_bytes("sha256:" + "../" * 21 + "x")


def test_bundle_omits_unopened_truth(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    ledger.seal("unopened", {"secret": "never-export"})
    report = tmp_path / "reports"
    report.mkdir()
    bundle = _bundle(tmp_path, report, exp)
    with zipfile.ZipFile(bundle) as zf:
        assert not any("vault" in Path(n).parts for n in zf.namelist())
        assert not any(b"never-export" in zf.read(n) for n in zf.namelist())
