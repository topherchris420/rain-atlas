import json

from conftest import BUILTIN

from rain_atlas.cli import main
from rain_atlas.ledger.store import Ledger


def test_validate_builtin_catalog(capsys):
    assert main(["skills", "validate", str(BUILTIN)]) == 0
    assert "INVALID" not in capsys.readouterr().out


def test_list_json(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "skills", "list", "--json"]) == 0
    names = {item["name"] for item in json.loads(capsys.readouterr().out)}
    assert {"spectral-peaks", "pendulum-period", "bibliography-audit"} <= names


def test_select_reports_missing_capability(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "skills", "select", "no.such-thing"]) == 1


def test_ledger_verify_detects_tampering(tmp_path, capsys):
    ledger = Ledger(tmp_path / "ledger")
    ledger.append("note", {"text": "x"})
    assert main(["ledger", "verify", str(tmp_path / "ledger")]) == 1  # a note needs an experiment and author
    good = Ledger(tmp_path / "good")
    good.seal("v", {"a": 1})
    assert main(["ledger", "verify", str(tmp_path / "good")]) == 0
    log = good.log_path.read_text(encoding="utf-8").replace('"seal"', '"note"')
    good.log_path.write_text(log, encoding="utf-8")
    assert main(["ledger", "verify", str(tmp_path / "good")]) == 1


def test_run_single_skill(tmp_path, capsys):
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"bibtex": "@misc{a, title = {T}, year = {2020}}"}), encoding="utf-8")
    code = main(
        [
            "--home",
            str(tmp_path / "home"),
            "run",
            "bibliography-audit",
            "--inputs",
            str(inputs),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )
    record = json.loads(capsys.readouterr().out)
    assert code == 0 and record["status"] == "ok"
    assert record["outputs"]["problems"][0]["kind"] == "missing-field"


def test_errors_are_reported_not_raised(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "skills", "remove", "spectral-peaks", "1.0.0"]) == 1
    assert "built-in" in capsys.readouterr().err


def test_torn_ledger_cli_reports_error_and_recovery_preserves_original(tmp_path, capsys):
    from test_ledger import prereg

    ledger = Ledger(tmp_path / "ledger")
    prereg(ledger)
    with ledger.log_path.open("ab") as f:
        f.write(b'{"incomplete":')
    original = ledger.log_path.read_bytes()
    assert main(["ledger", "verify", str(ledger.root)]) == 1
    assert "problem" in capsys.readouterr().out
    recovered = tmp_path / "recovered"
    assert main(["ledger", "recover", str(ledger.root), "--out", str(recovered)]) == 0
    assert Ledger(recovered).verify() == []
    assert ledger.log_path.read_bytes() == original


def test_operator_approval_requires_matching_reviewed_digest(tmp_path, capsys):
    from test_ledger import prereg

    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    command = [
        "--home",
        str(tmp_path / "home"),
        "approve",
        str(ledger.root),
        exp,
        "--operator",
        "tester",
        "--digest",
    ]
    assert main(command + ["00000000"]) == 1
    assert not list(ledger.entries("approval"))
    assert main(command + [exp[7:15]]) == 0
    assert not list(ledger.entries("run"))
    assert ledger.verify() == []
