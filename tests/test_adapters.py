import json
from pathlib import Path

import jsonschema
import pytest
from test_ledger import AUTHOR, prereg

from rain_atlas.adapters.luca import RESULT_SCHEMA, quarantine
from rain_atlas.adapters.rain import SCHEMA_BLOB, export, submission
from rain_atlas.ledger.store import Ledger


def study(root):
    ledger = Ledger(root)
    exp = prereg(ledger)
    ledger.append(
        "dataset",
        {
            "experiment": exp,
            "name": "synthetic",
            "origin": "synthetic",
            "media_type": "text/plain",
            "object": ledger.put_bytes(b"1"),
            "provenance": {},
        },
    )
    ledger.append(
        "run",
        {
            "experiment": exp,
            "run_id": "fixture",
            "skill": {"name": "fixture"},
            "status": "ok",
            "seed": 42,
            "inputs_hash": "sha256:" + "0" * 64,
            "role": "experimental-engineer",
            "started_at": "2026-11-04T00:00:00.000Z",
            "ended_at": "2026-11-04T00:01:00.000Z",
            "environment": {"atlas_commit": "a" * 40},
            "wall_s": 60,
            "artifacts": {},
        },
    )
    ledger.append(
        "report",
        {
            "experiment": exp,
            "findings": [],
            "limitations": ["Contract fixture, not an executed study."],
            "reproduction": {},
            "author": AUTHOR,
        },
    )
    return ledger, exp


def test_rain_export_matches_verified_upstream_contract_and_is_local(tmp_path):
    ledger, exp = study(tmp_path / "ledger")
    before = ledger.log_path.read_bytes()
    result = submission(ledger, exp, "V3D-EXP-0001", 1)
    schema = json.loads((Path(__file__).parent / "contracts/rain-submission.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(result)
    assert result["provenance"]["external_schema_blob"] == SCHEMA_BLOB
    assert result["evidence_class"] == "simulated" and "verdict" not in result and "status" not in result
    out = export(ledger, exp, "V3D-EXP-0001", 1, tmp_path / "submission.json")
    assert json.loads(out.read_text()) == result
    with pytest.raises(FileExistsError):
        export(ledger, exp, "V3D-EXP-0001", 1, out)
    assert ledger.log_path.read_bytes() == before
    with pytest.raises(ValueError):
        submission(ledger, exp, "arbitrary", 1)
    with pytest.raises(ValueError, match="outside"):
        export(ledger, exp, "V3D-EXP-0001", 1, ledger.root / "submission.json")


@pytest.mark.parametrize(
    "record,recognized",
    [
        (
            {
                "schema": RESULT_SCHEMA,
                "experiments": {},
                "synthetic": False,
                "manifest": {},
                "preregistration": {},
                "evidence_dir": "../../PRIVATE",
            },
            True,
        ),
        ({"run": "unknown"}, False),
    ],
)
def test_luca_intake_quarantines_without_following_paths(tmp_path, record, recognized):
    source = tmp_path / "external" / "result.json"
    source.parent.mkdir()
    source.write_text(json.dumps(record))
    raw = source.read_bytes()
    review = quarantine(source, tmp_path / "quarantine")
    status = json.loads(review.read_text())
    assert status["status"] == "quarantined" and status["recognized_shape"] == recognized
    assert not status["paths_followed"] and not status["code_executed"]
    assert source.read_bytes() == raw
    assert (review.parent / "record.json.bin").read_bytes() == raw
    with pytest.raises(ValueError, match="new"):
        quarantine(source, review.parent)
