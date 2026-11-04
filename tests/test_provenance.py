import io
import json
import zipfile

import pytest
from conftest import fixture_ref
from test_ledger import prereg

from rain_atlas.agents.lab import Engineer, Lab
from rain_atlas.canonical import tree_hash
from rain_atlas.ledger.store import Ledger
from rain_atlas.provenance import source_snapshot


def test_snapshot_is_deterministic_inspectable_and_changes_with_bytes(tmp_path):
    (tmp_path / "code.py").write_bytes(b"x = 1\n")
    archive, digest = source_snapshot(tmp_path)
    assert source_snapshot(tmp_path) == (archive, digest)
    assert digest == tree_hash(tmp_path)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.namelist() == ["code.py"]
        assert z.read("code.py") == b"x = 1\n"
    (tmp_path / "code.py").write_bytes(b"x = 2\n")
    assert source_snapshot(tmp_path)[1] != digest


def test_run_preserves_exact_source_and_refuses_changed_engine(tmp_path, registry, monkeypatch):
    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    lab = Lab(ledger, registry, tmp_path / "runs")
    lab.approve(exp, "tester", "echo")
    engineer = Engineer(lab)
    entry, result = engineer.execute(
        exp, fixture_ref("echo"), {"values": [1, 2]}, seed=1, purpose="provenance"
    )
    assert result.ok
    record = ledger.get_json(entry.object)
    assert ledger.get_bytes(record["engine_source_object"]).startswith(b"PK")
    assert ledger.get_bytes(record["lockfile_object"])
    monkeypatch.setattr(registry, "get", lambda *args: fixture_ref("echo"))
    monkeypatch.setattr("rain_atlas.provenance.source_snapshot", lambda *args: (b"", "changed"))
    with pytest.raises(ValueError, match="engine source changed"):
        engineer.reproduce(exp, entry)
    assert ledger.verify() == []
    ledger._object_path(record["engine_source_object"]).unlink()
    assert any("engine_source_object" in p for p in ledger.verify())


def test_sealed_failure_diagnostics_are_withheld(tmp_path, registry):
    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    secret = "PRIVATE-TRUTH-987654"
    _, seal = ledger.seal("parameters", {"target": secret})
    lab = Lab(ledger, registry, tmp_path / "runs")
    lab.approve(exp, "tester", "naughty")
    _, result = Engineer(lab).execute(
        exp,
        fixture_ref("naughty"),
        {"mode": "read-outside", "target": secret},
        seed=0,
        purpose="sealed failure",
        sealed={"commitment": seal, "public": {"mode": "read-outside"}},
    )
    assert not result.ok
    assert secret not in json.dumps([r for _, r in ledger.records()])
    assert not (result.run_dir / "stderr.txt").exists()
    assert not (result.run_dir / "output" / "_result.json").exists()
