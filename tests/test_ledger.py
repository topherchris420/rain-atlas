import json

import pytest

from rain_atlas.ledger.store import Ledger, LedgerError

AUTHOR = {"role": "tester", "generation": "scripted"}


def prereg(ledger: Ledger) -> str:
    return ledger.append(
        "preregistration",
        {
            "title": "t",
            "question": "q",
            "hypothesis": "h",
            "null_hypothesis": "h0",
            "design": {},
            "acceptance": [],
            "created_by": AUTHOR,
        },
    ).object


def ok_run(ledger: Ledger, experiment: str, status: str = "ok") -> str:
    return ledger.append(
        "run",
        {
            "run_id": "r1",
            "skill": {"name": "x"},
            "status": status,
            "seed": 0,
            "inputs_hash": "sha256:" + "1" * 64,
            "experiment": experiment,
            "role": "experimental-engineer",
        },
    ).object


def test_append_and_verify(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    run = ok_run(ledger, exp)
    ledger.append(
        "claim",
        {"experiment": exp, "category": "COMPUTED", "statement": "s", "evidence": [run], "author": AUTHOR},
    )
    assert ledger.verify() == []
    assert [e.seq for e in ledger.entries()] == [0, 1, 2]


def test_objects_are_content_addressed(tmp_path):
    ledger = Ledger(tmp_path)
    ref = ledger.put_json({"a": 1})
    assert ledger.put_json({"a": 1}) == ref
    assert ledger.get_json(ref) == {"a": 1}


def test_edited_log_line_is_detected(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    ok_run(ledger, exp)
    lines = ledger.log_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["at"] = "2000-01-01T00:00:00.000000Z"
    lines[0] = json.dumps(first, separators=(",", ":"), sort_keys=True)
    ledger.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert any("hash mismatch" in p for p in ledger.verify())


def test_deleted_log_line_is_detected(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    ok_run(ledger, exp)
    ok_run(ledger, exp, status="error")
    lines = ledger.log_path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    ledger.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    problems = ledger.verify()
    assert any("prev" in p for p in problems) and any("expected seq" in p for p in problems)


def test_modified_object_is_detected(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    run = ok_run(ledger, exp)
    path = ledger._object_path(run)
    path.write_bytes(path.read_bytes().replace(b'"ok"', b'"no"'))
    assert any("hash check" in p for p in ledger.verify())
    with pytest.raises(LedgerError):
        ledger.get_json(run)


def test_category_rules(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    failed = ok_run(ledger, exp, status="error")
    synthetic = ledger.append(
        "dataset",
        {
            "experiment": exp,
            "name": "d",
            "origin": "synthetic",
            "media_type": "application/x-npy",
            "object": failed,
            "provenance": {},
        },
    ).object
    ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": "from a failed run",
            "evidence": [failed],
            "author": AUTHOR,
        },
    )
    ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "OBSERVED",
            "statement": "observed synthetic",
            "evidence": [synthetic],
            "author": AUTHOR,
        },
    )
    note = ledger.append("note", {"experiment": exp, "text": "n", "author": AUTHOR}).object
    ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "INTERPRETED",
            "statement": "from a note",
            "evidence": [note],
            "author": AUTHOR,
        },
    )
    problems = " ".join(ledger.verify())
    assert "successful run" in problems
    assert "synthetic" in problems
    assert "INTERPRETED" in problems


def test_references_must_precede(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    future = ledger.put_json({"run_id": "later", "status": "ok"})
    ledger.append(
        "claim",
        {"experiment": exp, "category": "COMPUTED", "statement": "s", "evidence": [future], "author": AUTHOR},
    )
    assert any("does not precede" in p for p in ledger.verify())


def test_author_generation_is_required(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    ledger.append("note", {"experiment": exp, "text": "t", "author": {"role": "x", "generation": "magic"}})
    assert any("generation" in p for p in ledger.verify())


def test_seal_and_unseal(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    _, commitment = ledger.seal("truth", {"f": [1.5, 2.5]}, context={"experiment": exp})
    seal_record = next(r for _, r in ledger.records("seal"))
    assert "1.5" not in json.dumps(seal_record)
    claim = ledger.append("note", {"experiment": exp, "text": "analysis", "author": AUTHOR}).object
    _, value = ledger.unseal(commitment, after=[claim])
    assert value == {"f": [1.5, 2.5]}
    assert ledger.verify() == []


def test_tampered_unseal_is_detected(tmp_path):
    ledger = Ledger(tmp_path)
    _, commitment = ledger.seal("truth", {"f": 1})
    ledger.append("unseal", {"commitment": commitment, "salt": "00" * 32, "value": {"f": 2}, "after": []})
    assert any("does not match the commitment" in p for p in ledger.verify())


def test_sealed_run_needs_earlier_seal(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    ledger.append(
        "run",
        {
            "run_id": "r",
            "skill": {},
            "status": "ok",
            "seed": 0,
            "inputs_hash": "x",
            "experiment": exp,
            "role": "e",
            "sealed": {"commitment": "sha256:" + "2" * 64},
        },
    )
    assert any("no earlier seal" in p for p in ledger.verify())


def test_approval_must_not_claim_verified_identity(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    ledger.append(
        "approval",
        {
            "experiment": exp,
            "scope": "all",
            "operator": "me",
            "attestation": "signed",
            "identity_verified": True,
            "digest_prefix": exp[7:15],
        },
    )
    assert any("local-operator" in p for p in ledger.verify())


def test_verdict_rules(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    run = ok_run(ledger, exp)
    claim = ledger.append(
        "claim",
        {"experiment": exp, "category": "COMPUTED", "statement": "s", "evidence": [run], "author": AUTHOR},
    ).object
    ledger.append(
        "verdict",
        {
            "experiment": exp,
            "target": claim,
            "verdict": "supported",
            "reasons": [],
            "evidence": [],
            "author": AUTHOR,
        },
    )
    assert ledger.verify() == []
    ledger.append(
        "verdict",
        {
            "experiment": exp,
            "target": run,
            "verdict": "majority",
            "reasons": [],
            "evidence": [],
            "author": AUTHOR,
        },
    )
    problems = " ".join(ledger.verify())
    assert "not a claim" in problems and "verdict must be one of" in problems
