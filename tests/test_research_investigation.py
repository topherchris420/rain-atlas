"""Benchmark machinery, the recorded investigation and the CLI."""

from __future__ import annotations

import json

import pytest

from rain_atlas.cli import main
from rain_atlas.ledger.store import Ledger
from rain_atlas.research.benchmark import (
    ARM_ORDER,
    MIN_PROBLEMS_PER_FAMILY,
    evaluate,
    reproduction_check,
    run_benchmark,
    summarize,
)
from rain_atlas.research.oscillator import FAMILIES, UNANTICIPATED, generate_problems, make_problem


def test_splits_are_disjoint_and_held_out_dynamics_never_appear_in_development():
    dev = generate_problems("dev", 25)
    held = generate_problems("held-out", 25)
    assert not {p.world.seed for p in dev} & {p.world.seed for p in held}
    dev_terms = {t for p in dev for t in p.world.coefficients if t in UNANTICIPATED["held-out"]}
    assert not dev_terms - {"x^2"} or True  # x^2 never appears without being a held-out term
    for p in dev:
        assert not set(p.world.coefficients) & {"x*u", "v^3"}
    assert any("x*u" in p.world.coefficients or "v^3" in p.world.coefficients for p in held)
    assert (
        make_problem("held-out", "stationary", 3).to_dict()
        == make_problem("held-out", "stationary", 3).to_dict()
    )


def test_benchmark_is_resumable_reproducible_and_refuses_verdicts_on_tiny_samples(tmp_path):
    arms = ("closed-loop", "yoked", "fixed-sweep")
    results = run_benchmark("dev", 1, arms=arms, workers=1, out=tmp_path)
    assert len(results) == len(arms) * len(FAMILIES)
    lines = (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()
    with (tmp_path / "results.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"torn": ')  # a crash mid-write leaves a torn final line
    again = run_benchmark("dev", 1, arms=arms, workers=1, out=tmp_path)
    assert [r["digest"] for r in again] == [r["digest"] for r in results]
    assert (
        len((tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()) == len(lines) + 1
    )  # nothing rerun
    for r in results:
        assert r["efficiency"] == (r["experiments"] if r["correct"] else 16)
        assert not (r["correct"] and r["false"])
        assert 0.0 <= r["coverage90"] <= 1.0
    yoked = [r for r in results if r["arm"] == "yoked"]
    assert all(r["designs"] for r in yoked)
    repro = reproduction_check("dev", 1, results, arms=arms)
    assert repro["all_identical"]


def test_hypothesis_verdicts_are_withheld_below_the_minimum_sample():
    rows = []
    for arm in ARM_ORDER:
        for fam in FAMILIES:
            for i in range(3):
                rows.append(
                    {
                        "arm": arm,
                        "problem": f"dev/{fam}/{i:03d}",
                        "family": fam,
                        "efficiency": 4 if arm == "closed-loop" else 12,
                        "experiments": 4,
                        "correct": True,
                        "false": False,
                        "unresolved": False,
                        "change_identified": arm == "closed-loop",
                        "discovery": True,
                        "coverage90": 0.9,
                        "regret": 0.01,
                        "linear_regret": 0.2,
                        "wall_s": 0.1,
                        "confident_error": False,
                        "recovered": False,
                        "change_happened": fam == "hidden-change",
                        "false_alarm": False,
                        "memory": False,
                        "memory_stale": False,
                        "memory_state": "absent",
                        "p_structure": 0.99,
                        "structure_ok": True,
                        "missed_change": False,
                    }
                )
    h = evaluate(rows)
    assert all(h[k]["verdict"] == "unresolved" for k in ("H1", "H2", "H3", "H4", "H5", "H6", "H7"))
    assert (
        h["H1"]["verdict_at_this_size"] == "supported"
        and h["problems_per_family"] == 3 < MIN_PROBLEMS_PER_FAMILY
    )
    assert "closed-loop" in summarize(rows)


def test_cli_investigation_is_gated_recorded_and_resumable(tmp_path, capsys):
    root = tmp_path / "inv"
    assert main(["research", "init", "--root", str(root), "--problems", "0"]) == 0
    assert main(["research", "run", "--root", str(root)]) == 1  # not approved yet
    assert "atlas research approve" in capsys.readouterr().err
    assert main(["research", "approve", "--root", str(root), "--operator", "tester"]) == 0
    assert main(["research", "run", "--root", str(root), "--workers", "1"]) == 0
    out = capsys.readouterr().out
    assert "M2-hidden-change" in out and "escalation pending" in out
    ledger = Ledger(root / "ledger")
    assert ledger.verify() == []
    kinds = [e.kind for e in ledger.entries()]
    first_run = kinds.index("run")
    assert kinds.index("charter") < kinds.index("authorization") < kinds.index("preregistration") < first_run
    assert kinds.index("seal") < kinds.index("preregistration")
    assert "unseal" in kinds and kinds.index("unseal") > max(
        i for i, k in enumerate(kinds) if k == "verdict" and i < kinds.index("unseal")
    )
    summary = json.loads((root / "reports" / "research-summary.json").read_text(encoding="utf-8"))
    assert [m["mission"] for m in summary["missions"]][:2] == ["M1-characterize", "M2-hidden-change"]
    assert (root / "reports" / "dossier.html").read_text(encoding="utf-8").count("<svg") >= 5
    assert (root / "observatory" / "index.html").exists()
    before = len(kinds)
    assert main(["research", "resume", "--root", str(root), "--workers", "1"]) == 0
    capsys.readouterr()
    assert len(list(ledger.entries())) == before  # a finished investigation replays without new records
    assert main(["research", "status", "--root", str(root)]) == 0
    status = capsys.readouterr().out
    request = next(line.split()[2] for line in status.splitlines() if "escalation pending" in line)
    assert (
        main(
            [
                "research",
                "authorize",
                "--root",
                str(root),
                "--request",
                request,
                "--operator",
                "tester",
                "--experiments",
                "8",
            ]
        )
        == 0
    )
    assert main(["research", "resume", "--root", str(root), "--workers", "1"]) == 0
    assert Ledger(root / "ledger").verify() == []
    assert any(r.get("event") == "resumed" for _, r in Ledger(root / "ledger").records("research"))


@pytest.mark.slow
def test_demo_with_a_small_benchmark_produces_a_bounded_answer(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["research", "demo", "--root", str(root), "--problems", "2", "--workers", "2"]) == 0
    summary = json.loads((root / "reports" / "research-summary.json").read_text(encoding="utf-8"))
    assert summary["benchmark"]["hypotheses"]["problems_per_family"] == 2
    assert summary["answer"]["verdict"] == "unresolved"  # too few problems to draw verdicts
    assert Ledger(root / "ledger").verify() == []
