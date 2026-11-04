import pytest
from test_ledger import AUTHOR, prereg

from rain_atlas.ledger.index import search
from rain_atlas.ledger.recovery import recover
from rain_atlas.ledger.store import Ledger, LedgerError


def test_index_refreshes_and_never_trusts_tampered_source(tmp_path):
    ledger = Ledger(tmp_path)
    exp = prereg(ledger)
    one = ledger.append("note", {"experiment": exp, "text": "resonance first", "author": AUTHOR})
    assert len(search(ledger, "resonance")) == 1
    ledger.append("note", {"experiment": exp, "text": "resonance second", "author": AUTHOR})
    assert len(search(ledger, "resonance", kind="note")) == 2
    assert search(ledger, "%") == []
    ledger._object_path(one.object).write_bytes(b"edited")
    with pytest.raises(LedgerError):
        search(ledger, "resonance")


def test_recovery_preserves_original_and_never_opens_vault(tmp_path):
    source = tmp_path / "source"
    ledger = Ledger(source)
    prereg(ledger)
    ledger.seal("blind", {"secret": 123})
    with ledger.log_path.open("ab") as fh:
        fh.write(b'{"seq":')
    original = ledger.log_path.read_bytes()
    result = recover(source, tmp_path / "recovered")
    assert result.verify() == []
    assert ledger.log_path.read_bytes() == original
    assert not result.vault.exists()
    assert list(result.entries())[-1].kind == "recovery"
    with pytest.raises(ValueError):
        recover(source, tmp_path / "recovered")


def test_recovery_refuses_complete_or_tampered_history(tmp_path):
    ledger = Ledger(tmp_path / "source")
    prereg(ledger)
    with pytest.raises(ValueError):
        recover(ledger.root, tmp_path / "clean")
    raw = ledger.log_path.read_bytes()
    ledger.log_path.write_bytes(raw.rstrip(b"\n"))
    with pytest.raises(ValueError):
        recover(ledger.root, tmp_path / "complete")
