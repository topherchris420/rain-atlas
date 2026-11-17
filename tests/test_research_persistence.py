"""Crash recovery, verified resume, memory safeguards, advisors and ledger rules."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rain_atlas.ledger.store import Ledger
from rain_atlas.research.advisor import OllamaAdvisor, ScriptedAdvisor
from rain_atlas.research.charter import QUESTION, default_charter
from rain_atlas.research.engine import ResearchEngine
from rain_atlas.research.governance import ScopeGuard
from rain_atlas.research.investigation import (
    approve_charter,
    authorize,
    featured_missions,
    pending_escalations,
    record_charter,
    record_mission_claims,
    run_featured,
)
from rain_atlas.research.journal import LedgerJournal, RecordingInstrument, ResumeError, mission_events
from rain_atlas.research.memory_bridge import open_memory, quarantine, recall, remember
from rain_atlas.research.oscillator import Instrument, World

CHARTER = default_charter()


class Crash(RuntimeError):
    pass


class CrashingInstrument:
    def __init__(self, live, at):
        self.live, self.at = live, at

    def run(self, design, index):
        if index == self.at:
            raise Crash(f"power lost during experiment {index + 1}")
        return self.live.run(design, index)


def _prereg(ledger):
    ref = record_charter(ledger, CHARTER, created_by={"role": "operator", "generation": "scripted"})
    approve_charter(ledger, ref, operator="test", generation="scripted")
    return ref, ledger.append(
        "preregistration",
        {
            "title": "t",
            "question": QUESTION,
            "hypothesis": "h",
            "null_hypothesis": "n",
            "design": {"charter": ref},
            "acceptance": [],
            "created_by": {"role": "pi", "generation": "scripted"},
        },
    ).object


def _engine(
    ledger, prereg, world, mission, *, crash_at=None, charter=CHARTER, allow_supersede=False, guard=None
):
    live = Instrument(world)
    if crash_at is not None:
        live = CrashingInstrument(live, crash_at)
    return ResearchEngine(
        charter,
        RecordingInstrument(live, ledger, prereg, mission),
        mission_id=mission,
        seed=world.seed,
        emit=LedgerJournal(ledger, prereg, mission, allow_supersede=allow_supersede),
        guard=guard,
    )


WORLD = featured_missions()[1].world  # the hidden-change apparatus


def test_a_crashed_mission_resumes_to_the_uninterrupted_result(tmp_path):
    reference = ResearchEngine(CHARTER, Instrument(WORLD), mission_id="m", seed=WORLD.seed).run()
    ledger = Ledger(tmp_path / "ledger")
    _, prereg = _prereg(ledger)
    with pytest.raises(Crash):
        _engine(ledger, prereg, WORLD, "m", crash_at=3).run()
    partial = mission_events(ledger, "m")
    assert partial and partial[-1]["event"] == "plan" and partial[-1]["index"] == 3
    resumed = _engine(ledger, prereg, WORLD, "m").run()
    assert resumed.digest == reference.digest
    assert mission_events(ledger, "m") == reference.events
    assert ledger.verify() == []
    # a second resume of a finished mission appends nothing
    count = len(list(ledger.entries()))
    again = _engine(ledger, prereg, WORLD, "m").run()
    assert again.digest == reference.digest and len(list(ledger.entries())) == count


def test_resume_refuses_a_diverging_replay(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    _, prereg = _prereg(ledger)
    with pytest.raises(Crash):
        _engine(ledger, prereg, WORLD, "m", crash_at=4).run()
    changed = default_charter(**{"stopping.decision_probability": 0.99})
    with pytest.raises(ResumeError):
        _engine(ledger, prereg, WORLD, "m", charter=changed).run()


def test_authorized_extension_supersedes_only_terminal_events(tmp_path):
    item = featured_missions()[4]  # noise-limited: ends with a budget request
    ledger = Ledger(tmp_path / "ledger")
    charter_ref, prereg = _prereg(ledger)
    first, _ = run_featured(ledger, prereg, charter_ref, CHARTER, item, 4, tmp_path, None)
    record_mission_claims(ledger, prereg, charter_ref, item, first)
    pending = pending_escalations(ledger)
    assert [p["mission"] for p in pending] == [item.mission]
    authorize(ledger, pending[0]["request_id"], operator="op", decision="approve", experiments=8)
    second, _ = run_featured(ledger, prereg, charter_ref, CHARTER, item, 4, tmp_path, None)
    record_mission_claims(ledger, prereg, charter_ref, item, second)
    assert second.experiments > first.experiments
    kinds = [r["event"] for _, r in ledger.records("research") if r["mission"] == item.mission]
    assert "resumed" in kinds
    assert any(r.get("reason", "").startswith("the mission continued") for _, r in ledger.records("revision"))
    assert ledger.verify() == []


def test_ledger_rules_enforce_the_charter_approval(tmp_path):
    ledger = Ledger(tmp_path / "ledger")
    ref = record_charter(ledger, CHARTER, created_by={"role": "operator", "generation": "human"})
    ledger.append(
        "preregistration",
        {
            "title": "t",
            "question": "q",
            "hypothesis": "h",
            "null_hypothesis": "n",
            "design": {"charter": ref},
            "acceptance": [],
            "created_by": {"role": "pi", "generation": "scripted"},
        },
    )
    assert any("no earlier approving authorization" in p for p in ledger.verify())
    other = Ledger(tmp_path / "other")
    bad = dict(CHARTER, title="edited after approval")
    other.append(
        "charter",
        {
            "title": "t",
            "question": "q",
            "charter": bad,
            "digest": record_charter.__globals__["sha256_json"](CHARTER),
            "created_by": {"role": "operator", "generation": "human"},
        },
    )
    assert any("digest does not match" in p for p in other.verify())
    third = Ledger(tmp_path / "third")
    ref = record_charter(third, CHARTER, created_by={"role": "operator", "generation": "human"})
    third.append(
        "authorization",
        {
            "charter": ref,
            "decision": "approve",
            "scope": "charter",
            "operator": "x",
            "attestation": "signed",
            "identity_verified": True,
        },
    )
    assert any("local-operator" in p for p in third.verify())


def test_memory_bridge_recalls_quarantines_and_sets_aside_contradictions(tmp_path):
    store = open_memory(tmp_path)
    conclusion = {
        "structure": ["x", "v", "u", "x^3"],
        "noise_sd": 1.3,
        "coefficients": {
            t: {"mean": m, "sd": 0.02} for t, m in (("x", -1.3), ("v", -0.16), ("u", 1.0), ("x^3", -0.4))
        },
    }
    remember(store, "bench-A", conclusion, mission="M1", claim="sha256:" + "0" * 64, mission_index=0)
    prior, note = recall(store, "bench-A")
    assert note["status"] == "recalled" and prior.structure == ("x", "v", "u", "x^3")
    quarantine(store, "bench-A", {"summary": "stale"}, mission="M4")
    assert recall(store, "bench-A")[0] is None
    assert store.history(note["memory"])  # history retained
    remember(store, "bench-B", conclusion, mission="M1", claim="c", mission_index=0)
    remember(
        store,
        "bench-B",
        dict(conclusion, structure=["x", "v", "u"]),
        mission="M2",
        claim="c",
        mission_index=1,
    )
    prior, note = recall(store, "bench-B")
    assert prior is None and note["status"] == "contradictory"


class _Advisor:
    generation = "model"

    def __init__(self, terms):
        self.terms = terms
        self.calls = 0

    def propose_terms(self, context):
        self.calls += 1
        return {"terms": list(self.terms), "generation": "model", "rationale": "stub"}


def test_model_advice_is_validated_and_out_of_scope_terms_escalate():
    charter = default_charter(
        **{"environment.model_provider": {"kind": "ollama", "url": "http://localhost:1", "model": "m"}}
    )
    world = featured_missions()[2].world  # has an unanticipated term, so the critic consults the advisor
    advisor = _Advisor(["sin(x)", "x*u"])
    result = ResearchEngine(charter, Instrument(world), mission_id="m", seed=1, advisor=advisor).run()
    assert advisor.calls >= 1
    advice = [e for e in result.events if e["event"] == "advisor"]
    assert advice and advice[0]["generation"] == "model" and "sin(x)" not in advice[0]["accepted"]
    escalations = [e for e in result.events if e["event"] == "escalation"]
    assert any(e["kind"] == "untrusted-code" for e in escalations)
    # advice never decides: the evidence still finds the true unanticipated term
    assert "x^2*v" in result.conclusion["structure"]


def test_advisor_calls_are_bounded_by_the_charter():
    charter = default_charter(
        **{
            "environment.model_provider": {"kind": "ollama", "url": "http://localhost:1", "model": "m"},
            "budgets.model_calls": 0,
        }
    )
    world = featured_missions()[2].world
    advisor = _Advisor(["x*u"])
    result = ResearchEngine(charter, Instrument(world), mission_id="m", seed=1, advisor=advisor).run()
    assert advisor.calls == 0
    assert any(e["event"] == "escalation" and e["kind"] == "budget-extension" for e in result.events)


def test_scripted_survey_maps_the_question_to_catalogued_methods():
    s = ScriptedAdvisor().survey(QUESTION)
    ids = {m["method"] for m in s["methods"]}
    assert {
        "change-point-evidence",
        "sequential-design",
        "lagrange-multiplier-test",
        "d-optimal-design",
    } <= ids
    assert {p["id"] for p in s["subquestions"]} >= {"detect-change", "explain", "efficiency"}
    assert s["generation"] == "scripted"


class _Fake(BaseHTTPRequestHandler):
    reply = "{}"

    def do_POST(self):  # noqa: N802
        body = json.dumps({"response": type(self).reply, "prompt_eval_count": 3, "eval_count": 5}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_ollama():
    server = HTTPServer(("127.0.0.1", 0), _Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def test_ollama_advisor_validates_answers_and_falls_back(fake_ollama):
    url = f"http://127.0.0.1:{fake_ollama.server_address[1]}"
    advisor = OllamaAdvisor(url, "test-model")
    _Fake.reply = 'Sure: {"methods": ["chow-test", "telepathy"], "rationale": "r"}'
    s = advisor.survey(QUESTION)
    assert (
        s["model"]["used"]
        and s["model"]["suggested"] == ["chow-test"]
        and s["model"]["discarded"] == ["telepathy"]
    )
    _Fake.reply = '{"terms": ["x*u"], "rationale": "parametric"}'
    assert advisor.propose_terms({"leading": "{x}", "diagnostics": {}})["terms"] == ["x*u"]
    _Fake.reply = "no json at all"
    out = advisor.propose_terms({"diagnostics": {"lm_tests": [{"term": "v^3", "p": 0.01}]}})
    assert out["generation"] == "scripted" and "fallback" in out["rationale"]
    dead = OllamaAdvisor("http://127.0.0.1:9", "m", timeout_s=0.5)
    assert dead.survey(QUESTION)["model"]["used"] is False


def test_guard_with_authorized_design_space_accepts_the_wider_design():
    from rain_atlas.research.oscillator import Design

    auth = {
        "mission": "m",
        "decision": "approve",
        "kind": "design-space",
        "granted": {"design_space": {"amplitude": [0.0, 2.0]}},
    }
    ScopeGuard(CHARTER, "m", [auth]).check_design(Design(1.9, 1.0, 0.0))
    _ = World  # imported for clarity of the domain under test
