"""Malformed persisted evidence must fail closed without changing history."""

import json

import pytest
from test_ledger import prereg

from rain_atlas.canonical import canonical_bytes, sha256_json
from rain_atlas.ledger.store import Ledger, LedgerError


def rewrite_entry(ledger, **updates):
    entry = json.loads(ledger.log_path.read_bytes())
    entry.update(updates)
    entry.pop("hash")
    entry["hash"] = sha256_json(entry)
    ledger.log_path.write_bytes(canonical_bytes(entry) + b"\n")


@pytest.mark.parametrize(
    "field,value",
    [
        ("seq", True),
        ("seq", 0.0),
        ("seq", -1),
        ("seq", []),
        ("at", None),
        ("at", {}),
        ("kind", []),
        ("kind", ""),
        ("object", []),
        ("object", "not-a-digest"),
        ("prev", {}),
        ("hash", []),
    ],
)
def test_malformed_metadata_is_reported_even_when_rehashed(tmp_path, field, value):
    ledger = Ledger(tmp_path)
    prereg(ledger)
    rewrite_entry(ledger, **{field: value})
    if field == "hash":
        entry = json.loads(ledger.log_path.read_bytes())
        entry["hash"] = value
        ledger.log_path.write_bytes(canonical_bytes(entry) + b"\n")
    before = ledger.log_path.read_bytes()
    assert "malformed log line 1" in "; ".join(ledger.verify())
    assert ledger.log_path.read_bytes() == before


@pytest.mark.parametrize("value", [None, [], 1, "record", True])
def test_non_object_records_cannot_verify_or_be_appended(tmp_path, value):
    ledger = Ledger(tmp_path)
    prereg(ledger)
    before = ledger.log_path.read_bytes()
    with pytest.raises(LedgerError, match="JSON object"):
        ledger.append("note", value)
    assert ledger.log_path.read_bytes() == before
    rewrite_entry(ledger, object=ledger.put_json(value))
    assert "record must be a JSON object" in "; ".join(ledger.verify())


@pytest.mark.parametrize("tail", [b"", b'{"seq":', b"\xff"])
def test_unterminated_log_cannot_be_extended(tmp_path, tail):
    ledger = Ledger(tmp_path)
    prereg(ledger)
    raw = ledger.log_path.read_bytes()
    ledger.log_path.write_bytes(raw.rstrip(b"\n") if not tail else raw + tail)
    before = ledger.log_path.read_bytes()
    objects = set(ledger.objects.rglob("*"))
    assert ledger.verify()
    with pytest.raises((LedgerError, UnicodeError)):
        ledger.append("note", {"text": "must not be written"})
    assert ledger.log_path.read_bytes() == before
    assert set(ledger.objects.rglob("*")) == objects


def test_duplicate_metadata_keys_are_rejected(tmp_path):
    ledger = Ledger(tmp_path)
    prereg(ledger)
    raw = ledger.log_path.read_bytes()
    ledger.log_path.write_bytes(b'{"seq":999,' + raw[1:])
    assert "malformed log line 1" in "; ".join(ledger.verify())


def test_empty_log_remains_appendable(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.log_path.touch()
    prereg(ledger)
    assert ledger.verify() == []
