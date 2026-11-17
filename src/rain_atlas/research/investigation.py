"""An end-to-end investigation of a research question, recorded in the ledger.

Stages (each idempotent, so an interrupted investigation resumes)::

    charter + human approval      atlas research approve
    method survey                 advisor (scripted retrieval, or a local model) -> methods, baselines, skills
    competing hypotheses          program level (H1-H7, each with its null) and mission level (term grammar)
    sealed truths                 the featured apparatus parameters, committed before anything runs
    preregistration               hypotheses, metrics, stopping rules, arms, held-out split, source hash
    featured missions             the research loop on five apparatus, every step in the ledger
    held-out benchmark            all arms on problems never used in development
    reproduction                  a subset rerun; mission digests must match
    claims and verdicts           one per hypothesis, three-valued, from the preregistered rule
    unseal and evaluate           featured conclusions scored against the revealed truth
    report                        Markdown, JSON, an offline dossier and the observatory

The featured missions illustrate the mechanisms; they were fixed before the
investigation ran and their outcomes are reported as they happened. The
benchmark is the evidence for the program-level claims.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..canonical import sha256_json
from ..ledger.store import Ledger, LedgerError
from ..provenance import engine_root, source_snapshot
from . import charter as charter_mod
from .advisor import ScriptedAdvisor, make_advisor
from .benchmark import (
    ALPHA,
    ARM_ORDER,
    FAMILY_SIZE,
    HYPOTHESES,
    config_digest,
    evaluate,
    reproduction_check,
    run_benchmark,
    summarize,
)
from .engine import MissionResult, ResearchEngine
from .governance import ScopeGuard
from .journal import (
    AUTHOR,
    LedgerJournal,
    RecordingInstrument,
    ReplayAdvisor,
    mission_records,
    recorded_memory,
)
from .memory_bridge import open_memory, quarantine, recall, remember
from .oscillator import FAMILIES, SPLIT_SEEDS, Instrument, MemoryPrior, World, describe_truth, structure_of

PI = {"role": "principal-investigator", "generation": "scripted"}
NULLS = {
    "H1": "Selection that depends on this problem's observations is no better than the same designs replayed "
    "from another problem.",
    "H2": "The closed loop is no more efficient than at least one conventional design.",
    "H3": "The closed loop's false-conclusion rate exceeds 5 %.",
    "H4": "The closed loop identifies changes no more often than the fixed sweep.",
    "H5": "The closed loop finds unanticipated terms no more often than the fixed sweep.",
    "H6": "The closed loop's predictive intervals are miscalibrated on unseen conditions.",
    "H7": "The closed loop's model predicts unseen conditions no better than a linear least-squares model.",
}


@dataclass(frozen=True)
class Featured:
    mission: str
    apparatus: str
    story: str
    world: World
    remember_after: bool = True


def featured_missions() -> list[Featured]:
    """Five illustrative apparatus, fixed in advance (see module docstring)."""

    duffing = {"x": -1.3, "v": -0.16, "u": 1.0, "x^3": -0.4}
    aged = dict(duffing, x=-0.92, v=-0.34)  # what bench-A became between missions 1 and 4
    return [
        Featured(
            "M1-characterize",
            "bench-A",
            "first characterization of an unfamiliar apparatus",
            World(duffing, noise_scale=0.3, seed=910_001),
        ),
        Featured(
            "M2-hidden-change",
            "bench-B",
            "a stiffness drop at an unannounced experiment",
            World(
                {"x": -1.1, "v": -0.2, "u": 0.9, "1": 0.25},
                noise_scale=0.3,
                change_at=2,
                changed_coefficients={"x": -0.72, "v": -0.2, "u": 0.9, "1": 0.25},
                seed=910_002,
            ),
        ),
        Featured(
            "M3-unanticipated",
            "bench-C",
            "dynamics outside the anticipated hypotheses",
            World({"x": -1.0, "v": -0.12, "u": 1.1, "x^2*v": -0.3}, noise_scale=0.3, seed=910_003),
        ),
        Featured(
            "M4-returning",
            "bench-A",
            "bench-A again, after an unrecorded repair",
            World(aged, noise_scale=0.3, seed=910_004),
        ),
        Featured(
            "M5-noise-limited",
            "bench-D",
            "a small offset under heavy noise",
            World({"x": -1.6, "v": -0.3, "u": 0.8, "x^3": -0.2, "1": 0.08}, noise_scale=1.0, seed=910_005),
            remember_after=False,
        ),
    ]


class InvestigationError(RuntimeError):
    pass


def research_source_hash() -> str:
    return source_snapshot(engine_root())[1]


def _find(ledger: Ledger, kind: str, predicate: Callable[[dict], bool]) -> tuple[str, dict] | None:
    for entry, record in ledger.records(kind):
        if predicate(record):
            return entry.object, record
    return None


def record_charter(ledger: Ledger, charter: dict, *, created_by: dict) -> str:
    charter_mod.check(charter)
    digest = sha256_json(charter)
    existing = _find(ledger, "charter", lambda r: r["digest"] == digest)
    if existing:
        return existing[0]
    return ledger.append(
        "charter",
        {
            "title": charter["title"],
            "question": charter["question"],
            "charter": charter,
            "digest": digest,
            "created_by": created_by,
        },
    ).object


def approve_charter(
    ledger: Ledger, charter_ref: str, *, operator: str, generation: str = "human", comment: str = ""
) -> str:
    existing = _find(
        ledger,
        "authorization",
        lambda r: r["charter"] == charter_ref and r["scope"] == "charter" and r["decision"] == "approve",
    )
    if existing:
        return existing[0]
    return ledger.append(
        "authorization",
        {
            "charter": charter_ref,
            "decision": "approve",
            "scope": "charter",
            "operator": operator,
            "generation": generation,
            "attestation": "local-operator",
            "identity_verified": False,
            "comment": comment
            or "approves the question, methods, budgets and execution environment in the charter",
        },
    ).object


def approved_charter(ledger: Ledger) -> tuple[str, dict]:
    charters = list(ledger.records("charter"))
    if not charters:
        raise InvestigationError(
            "no charter in this ledger; run `atlas research init` and `atlas research approve`"
        )
    for entry, record in reversed(charters):
        ok = _find(
            ledger,
            "authorization",
            lambda r, ref=entry.object: (
                r["charter"] == ref and r["scope"] == "charter" and r["decision"] == "approve"
            ),
        )
        if ok:
            return entry.object, record["charter"]
    raise InvestigationError(
        "the charter has not been approved; run `atlas research approve --operator NAME`"
    )


def authorizations(ledger: Ledger) -> list[dict]:
    out = []
    for _, r in ledger.records("authorization"):
        if r.get("scope") == "escalation":
            out.append(r)
    return out


def pending_escalations(ledger: Ledger) -> list[dict]:
    answered = {r.get("request_id") for r in authorizations(ledger)}
    out = []
    for entry, r in ledger.records("escalation"):
        if r["request"]["request_id"] not in answered:
            out.append({"ref": entry.object, **r["request"]})
    return out


def authorize(
    ledger: Ledger,
    request_id: str,
    *,
    operator: str,
    decision: str,
    experiments: int | None = None,
    comment: str = "",
) -> str:
    from .governance import authorization_record

    charter_ref, charter = approved_charter(ledger)
    match = [
        (e.object, r) for e, r in ledger.records("escalation") if r["request"]["request_id"] == request_id
    ]
    if not match:
        raise InvestigationError(f"no escalation request {request_id}")
    ref, rec = match[-1]
    request = dict(rec["request"])
    request["cap"] = int(charter["budgets"]["max_extension_per_request"])
    granted = None
    if experiments is not None and decision == "approve":
        granted = {"experiments": int(experiments)}
    body = authorization_record(
        request, operator=operator, decision=decision, granted=granted, comment=comment
    )
    return ledger.append(
        "authorization", {**body, "charter": charter_ref, "scope": "escalation", "request": ref}
    ).object


# -- mission execution -------------------------------------------------------------


def run_featured(
    ledger: Ledger,
    experiment: str,
    charter_ref: str,
    charter: dict,
    item: Featured,
    index: int,
    memory_root: Path,
    advisor: Any | None,
) -> tuple[MissionResult, ResearchEngine]:
    store = open_memory(memory_root)
    started, recorded = recorded_memory(ledger, item.mission)
    if started:
        memory = MemoryPrior.from_dict(recorded) if recorded else None
        recall_note = None
    else:
        memory, recall_note = recall(store, item.apparatus)
    auths = [a for a in authorizations(ledger) if a.get("mission") == item.mission]
    # Recorded terminal events may be superseded only by an authorization newer than the mission's own records.
    last_event = max(
        (e.seq for e, r in _mission_entries(ledger, item.mission) if e.kind != "authorization"), default=-1
    )
    newer_auth = any(
        e.seq > last_event
        for e, r in ledger.records("authorization")
        if r.get("mission") == item.mission and r.get("decision") == "approve"
    )
    journal = LedgerJournal(ledger, experiment, item.mission, allow_supersede=newer_auth)
    if recall_note and recall_note["status"] == "contradictory":
        ledger.append(
            "note",
            {
                "experiment": experiment,
                "text": recall_note["summary"],
                "author": AUTHOR,
                "mission": item.mission,
                "memory": recall_note,
            },
        )
    instrument = RecordingInstrument(Instrument(item.world), ledger, experiment, item.mission)
    events_so_far = journal.recorded
    replay_advisor = ReplayAdvisor(advisor, events_so_far) if advisor is not None else None

    def on_memory(kind: str, details: dict) -> None:
        if kind == "quarantine":
            outcome = quarantine(store, item.apparatus, details, mission=item.mission)
            details["store"] = outcome

    engine = ResearchEngine(
        charter,
        instrument,
        mission_id=item.mission,
        seed=item.world.seed + 17,
        arm="closed-loop",
        memory=memory,
        guard=ScopeGuard(charter, item.mission, auths),
        emit=journal,
        advisor=replay_advisor,
        on_memory=on_memory,
    )
    result = engine.run()
    result.run_refs = dict(instrument.run_refs)  # type: ignore[attr-defined]
    return result, engine


def _mission_entries(ledger: Ledger, mission: str):
    return [(e, r) for e, r in ledger.records() if isinstance(r, dict) and r.get("mission") == mission]


def record_mission_claims(
    ledger: Ledger, experiment: str, charter_ref: str, item: Featured, result: MissionResult
) -> dict:
    """Claim, challenges and verdict for one mission (idempotent per result digest)."""

    existing = _find(
        ledger, "verdict", lambda r: r.get("mission") == item.mission and r.get("digest") == result.digest
    )
    if existing:
        claim = ledger.get_json(existing[1]["target"])
        return {
            "claim": existing[1]["target"],
            "verdict": existing[0],
            "statement": claim["statement"],
            "verdict_value": existing[1]["verdict"],
        }
    c = result.conclusion
    runs = [ref for _, ref in sorted(result.run_refs.items())]  # type: ignore[attr-defined]
    terms = ", ".join(f"{t} = {v['mean']:+.3f} ± {v['sd']:.3f}" for t, v in c["coefficients"].items())
    change = c.get("change_claim")
    change_text = ""
    if change and c["change"]:
        change_text = f"; a change before experiment {c['change']['change_at'] + 1} ({', '.join(c['change']['changed'])})"
    statement = (
        f"{item.apparatus}: the current dynamics are explained by terms {{{', '.join(c['structure'])}}} "
        f"(posterior {c['p_structure']:.3f}){change_text}; coefficients {terms}"
    )
    claim = ledger.append(
        "claim",
        {
            "experiment": experiment,
            "category": "COMPUTED",
            "statement": statement,
            "value": {"structure": c["structure"], "coefficients": c["coefficients"], "change": c["change"]},
            "uncertainty": {"p_structure": c["p_structure"], "p_change": c["p_change"]},
            "evidence": runs,
            "method": "exact NIG evidence over the working hypotheses; see the mission's research records",
            "mission": item.mission,
            "author": AUTHOR,
        },
    ).object
    challenge_refs = []
    for _, r in mission_records(ledger, item.mission):
        if r["event"] == "challenge":
            p = r["payload"]
            idx = p["index"]
            challenge_refs.append(
                ledger.append(
                    "challenge",
                    {
                        "experiment": experiment,
                        "target": claim,
                        "method": f"fresh {p['kind']} experiment with a prediction recorded before it ran",
                        "evidence": [result.run_refs[idx]] if idx in result.run_refs else [],  # type: ignore[attr-defined]
                        "outcome": {"corroborated": "corroborated", "contradicted": "contradicted"}.get(
                            p["outcome"], "inconclusive"
                        ),
                        "reasoning": f"z = {p['z']}, amplitude {p['amplitude']} against the recorded predictive interval; "
                        f"Chow p = {(p.get('chow') or {}).get('p')}",
                        "mission": item.mission,
                        "author": {"role": "skeptic", "generation": "scripted"},
                    },
                ).object
            )
    ind = c.get("independent_detail") or {}
    if c.get("independent"):
        challenge_refs.append(
            ledger.append(
                "challenge",
                {
                    "experiment": experiment,
                    "target": claim,
                    "method": ind.get("method", "cross-validated prediction"),
                    "evidence": runs,
                    "outcome": c["independent"],
                    "reasoning": f"{len(ind.get('comparisons', []))} neighbouring structures compared on "
                    f"{ind.get('rows', 0)} held-out rows",
                    "mission": item.mission,
                    "author": {"role": "skeptic", "generation": "scripted"},
                },
            ).object
        )
    verdict = ledger.append(
        "verdict",
        {
            "experiment": experiment,
            "target": claim,
            "verdict": c["verdict"],
            "reasons": c["reasons"],
            "evidence": challenge_refs,
            "rule": "supported only when the fresh-data challenges, the independent check and exact re-analysis agree",
            "mission": item.mission,
            "digest": result.digest,
            "author": AUTHOR,
        },
    ).object
    previous = [
        e.object
        for e, r in ledger.records("verdict")
        if r.get("mission") == item.mission and e.object != verdict
    ]
    if previous:
        ledger.append(
            "revision",
            {
                "supersedes": previous[-1],
                "replacement": verdict,
                "reason": "the mission continued after a human authorization; this verdict replaces the earlier one",
                "author": AUTHOR,
            },
        )
    if result.escalation and not _find(
        ledger, "escalation", lambda r: r["request"]["request_id"] == result.escalation["request_id"]
    ):
        ledger.append(
            "escalation",
            {"charter": charter_ref, "mission": item.mission, "request": result.escalation, "author": AUTHOR},
        )
    return {"claim": claim, "verdict": verdict, "statement": statement, "verdict_value": c["verdict"]}


# -- the investigation -----------------------------------------------------------


def _skill_listing() -> list[dict]:
    try:
        from ..skills.registry import Registry

        return [
            {"name": i.name, "summary": i.summary, "capabilities": list(i.capabilities)}
            for i in Registry().listings()
        ]
    except Exception:  # noqa: BLE001 - the survey must work without an installed catalog
        return []


def program_hypotheses() -> list[dict]:
    return [{"id": h, "hypothesis": HYPOTHESES[h], "null": NULLS[h]} for h in HYPOTHESES]


def mission_hypothesis_space(charter: dict) -> dict:
    g = charter["hypothesis_grammar"]
    return {
        "anticipated": [g["core"], *[[*g["core"], t] for t in g["optional"]], [*g["core"], *g["optional"]]],
        "unanticipated_terms_admissible_by_the_critic": g["expansion"],
        "change": "at most one change per mission: a shift of any term, a joint shift, or the onset of an anticipated term",
        "falsifiable_by": "every structure predicts each new experiment before it runs; challenges record predictions",
    }


def investigate(
    root: Path,
    *,
    per_family: int | None = None,
    workers: int | None = None,
    progress: Callable[[str], None] | None = None,
    skip_benchmark: bool = False,
) -> dict:
    root = Path(root)
    say = progress or (lambda message: None)
    ledger = Ledger(root / "ledger")
    problems = ledger.verify()
    if problems:
        raise InvestigationError(
            "the ledger does not verify; recover it before resuming: " + "; ".join(problems[:4])
        )
    charter_ref, charter = approved_charter(ledger)
    per_family = int(
        per_family if per_family is not None else charter["budgets"]["benchmark_problems_per_family"]
    )
    featured = featured_missions()[: int(charter["budgets"]["featured_missions"])]
    started = time.perf_counter()

    # 1-5: survey, hypotheses, sealed truths, preregistration -- once.
    prereg = _find(ledger, "preregistration", lambda r: r.get("design", {}).get("charter") == charter_ref)
    if prereg is None:
        say("method survey and competing hypotheses")
        advisor = make_advisor(charter, _skill_listing())
        survey = advisor.survey(charter["question"])
        commitments = {}
        for item in featured:
            _, commitment = ledger.seal(
                f"hidden parameters of {item.mission}",
                item.world.to_dict(),
                context={"mission": item.mission},
            )
            commitments[item.mission] = commitment
        arms = list(ARM_ORDER)
        design = {
            "charter": charter_ref,
            "method_survey": survey,
            "program_hypotheses": program_hypotheses(),
            "mission_hypotheses": mission_hypothesis_space(charter),
            "stopping_rule": charter["stopping"],
            "featured": [
                {
                    "mission": f.mission,
                    "apparatus": f.apparatus,
                    "story": f.story,
                    "commitment": commitments[f.mission],
                }
                for f in featured
            ],
            "benchmark": {
                "split": "held-out",
                "split_seed": SPLIT_SEEDS["held-out"],
                "problems_per_family": per_family,
                "families": list(FAMILIES),
                "arms": arms,
                "config_digest": config_digest("held-out", per_family, arms, charter),
                "alpha_family": ALPHA,
                "hypotheses_in_family": FAMILY_SIZE,
                "development_split_never_scored_here": "dev",
            },
            "research_source_hash": research_source_hash(),
            "true_parameters_hidden_from_the_loop": True,
        }
        prereg_ref = ledger.append(
            "preregistration",
            {
                "title": charter["title"],
                "question": charter["question"],
                "hypothesis": "; ".join(f"{h['id']}: {h['hypothesis']}" for h in program_hypotheses()),
                "null_hypothesis": "; ".join(f"{h['id']}: {h['null']}" for h in program_hypotheses()),
                "design": design,
                "acceptance": [
                    "every hypothesis is judged by its preregistered rule on held-out problems only",
                    "family-wise alpha 0.05 (Bonferroni over seven hypotheses), paired family-stratified bootstrap",
                    "featured mission truths are sealed before any experiment and revealed after the verdicts",
                    "a negative or unresolved result is recorded and reported as such",
                ],
                "created_by": PI,
            },
        ).object
    else:
        prereg_ref = prereg[0]
        design = prereg[1]["design"]
        if design["benchmark"]["problems_per_family"] != per_family:
            raise InvestigationError(
                f"this investigation was preregistered with {design['benchmark']['problems_per_family']} problems per "
                f"family; use a fresh root to change the scale"
            )
    advisor = make_advisor(charter)
    advisor_for_missions = advisor if not isinstance(advisor, ScriptedAdvisor) else None

    # 6: featured missions.
    missions = []
    memory_root = root
    for i, item in enumerate(featured):
        say(f"mission {item.mission}: {item.story}")
        result, engine = run_featured(
            ledger, prereg_ref, charter_ref, charter, item, i, memory_root, advisor_for_missions
        )
        claims = record_mission_claims(ledger, prereg_ref, charter_ref, item, result)
        if item.remember_after and result.conclusion["verdict"] == "supported":
            store = open_memory(memory_root)
            known = store.get_all(filters={"agent_id": item.apparatus, "kind": "characterization"})["results"]
            if not any(k["metadata"].get("mission") == item.mission for k in known):
                remember(
                    store,
                    item.apparatus,
                    result.conclusion,
                    mission=item.mission,
                    claim=claims["claim"],
                    mission_index=i,
                )
        missions.append({"featured": item, "result": result, "engine": engine, "claims": claims})

    # 7-9: benchmark, reproduction, hypothesis verdicts.
    bench = None
    if not skip_benchmark and per_family > 0:
        say(f"held-out benchmark: {per_family} problems per family x {len(ARM_ORDER)} arms")
        results = run_benchmark(
            "held-out", per_family, workers=workers, out=root / "benchmark", charter=charter, progress=None
        )
        summary = summarize(results)
        hypotheses = evaluate(results)
        repro = reproduction_check("held-out", per_family, results, charter, workers=workers or 1)
        bench = {"results": results, "summary": summary, "hypotheses": hypotheses, "reproduction": repro}
        _record_benchmark(ledger, prereg_ref, charter, per_family, bench)

    # 10: unseal featured truths after every verdict, then evaluate.
    truths = _unseal(ledger, prereg_ref, design)
    evaluation = [_evaluate_featured(m, truths.get(m["featured"].mission)) for m in missions]
    if not _find(ledger, "note", lambda r: r.get("stage") == "featured-evaluation"):
        ledger.append(
            "note",
            {
                "experiment": prereg_ref,
                "stage": "featured-evaluation",
                "text": "featured conclusions scored against the revealed simulation truth "
                "(possible only because these are simulations)",
                "evaluation": evaluation,
                "author": AUTHOR,
            },
        )

    from .report import write_reports

    say("report")
    report = write_reports(
        root, ledger, prereg_ref, charter, design, missions, bench, evaluation, pending_escalations(ledger)
    )
    problems = ledger.verify()
    return {
        "root": str(root),
        "preregistration": prereg_ref,
        "missions": [
            {
                "mission": m["featured"].mission,
                "verdict": m["result"].conclusion["verdict"],
                "stop": m["result"].stop_reason,
                "experiments": m["result"].experiments,
            }
            for m in missions
        ],
        "benchmark": None
        if bench is None
        else {k: v["verdict"] for k, v in bench["hypotheses"].items() if k.startswith("H")},
        "answer": report["answer"],
        "pending_escalations": pending_escalations(ledger),
        "ledger_problems": problems,
        "elapsed_s": time.perf_counter() - started,
        "reports": report["paths"],
    }


def _record_benchmark(ledger: Ledger, experiment: str, charter: dict, per_family: int, bench: dict) -> None:
    if _find(ledger, "run", lambda r: r.get("stage") == "benchmark"):
        return
    lines = "".join(
        json.dumps({k: v for k, v in r.items() if k != "designs"}, sort_keys=True) + "\n"
        for r in bench["results"]
    )
    results_ref = ledger.put_bytes(lines.encode("utf-8"))
    summary_ref = ledger.put_json({"summary": bench["summary"], "hypotheses": bench["hypotheses"]})
    engine_bytes, engine_hash = source_snapshot(engine_root())
    run = ledger.append(
        "run",
        {
            "run_id": "held-out-benchmark",
            "skill": "atlas-research/benchmark",
            "status": "ok",
            "seed": SPLIT_SEEDS["held-out"],
            "inputs_hash": config_digest("held-out", per_family, list(ARM_ORDER), charter),
            "experiment": experiment,
            "role": "benchmark",
            "stage": "benchmark",
            "purpose": "preregistered held-out benchmark of every arm",
            "engine_source_object": ledger.put_bytes(engine_bytes),
            "engine_source_hash": engine_hash,
            "artifacts": {
                "results.jsonl": {"sha256": results_ref, "object": results_ref},
                "summary.json": {"sha256": summary_ref, "object": summary_ref},
            },
            "metrics": {"missions": len(bench["results"])},
        },
    ).object
    repro = bench["reproduction"]
    rerun = ledger.append(
        "run",
        {
            "run_id": "held-out-benchmark-reproduction",
            "skill": "atlas-research/benchmark",
            "status": "ok",
            "seed": SPLIT_SEEDS["held-out"],
            "inputs_hash": sha256_json({"subset": "first problems of every family and arm"}),
            "experiment": experiment,
            "role": "engineer",
            "stage": "benchmark-reproduction",
            "metrics": repro,
        },
    ).object
    ledger.append(
        "reproduction",
        {
            "experiment": experiment,
            "original_run": run,
            "reproduction_run": rerun,
            "outputs_match": bool(repro["all_identical"]),
            "artifacts_match": bool(repro["all_identical"]),
            "detail": f"{repro['identical']}/{repro['missions']} mission digests identical",
            "author": {"role": "experimental-engineer", "generation": "scripted"},
        },
    )
    for hid in HYPOTHESES:
        h = bench["hypotheses"][hid]
        claim = ledger.append(
            "claim",
            {
                "experiment": experiment,
                "category": "COMPUTED",
                "statement": f"{hid}: {HYPOTHESES[hid]}",
                "value": {k: v for k, v in h.items() if k != "verdict"},
                "evidence": [run],
                "method": "paired family-stratified bootstrap over held-out problems, Bonferroni 0.05/7",
                "label": hid,
                "author": PI,
            },
        ).object
        ledger.append(
            "verdict",
            {
                "experiment": experiment,
                "target": claim,
                "verdict": h["verdict"],
                "reasons": [f"preregistered interval rule on {per_family} problems per family"],
                "evidence": [run],
                "rule": "supported if the whole adjusted interval satisfies the hypothesis, contradicted if the whole "
                "interval violates it, unresolved otherwise",
                "label": hid,
                "author": PI,
            },
        )


def _unseal(ledger: Ledger, experiment: str, design: dict) -> dict[str, dict]:
    out = {}
    unsealed = {r["commitment"]: r["value"] for _, r in ledger.records("unseal")}
    after = [e.object for e, _ in ledger.records("verdict")]
    for item in design["featured"]:
        c = item["commitment"]
        if c in unsealed:
            out[item["mission"]] = unsealed[c]
            continue
        try:
            _, value = ledger.unseal(c, after=after[-1:])
        except LedgerError:
            continue
        out[item["mission"]] = value
    return out


def _evaluate_featured(mission: dict, truth: dict | None) -> dict:
    result: MissionResult = mission["result"]
    c = result.conclusion
    out = {
        "mission": mission["featured"].mission,
        "verdict": c["verdict"],
        "structure": c["structure"],
        "stop": result.stop_reason,
        "experiments": result.experiments,
    }
    if truth is None:
        out["truth"] = "sealed (not revealed)"
        return out
    world = World(
        coefficients=truth["coefficients"],
        noise_scale=truth["noise_scale"],
        noise=truth["noise"],
        change_at=truth["change_at"],
        changed_coefficients=truth["changed_coefficients"],
        seed=truth["seed"],
    )
    current = world.active(result.experiments - 1)
    out.update(
        {
            "truth": describe_truth(current),
            "true_structure": list(structure_of(current)),
            "structure_correct": tuple(c["structure"]) == structure_of(current),
            "true_change": None if world.change_at is None else {"before_experiment": world.change_at + 1},
            "claimed_change": None
            if not c["change"]
            else {"before_experiment": c["change"]["change_at"] + 1, "changed": c["change"]["changed"]},
        }
    )
    return out
