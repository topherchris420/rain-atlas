"""Reports for an investigation: Markdown, JSON and an offline dossier.

Everything shown is read from the mission records, the benchmark results and
the ledger; nothing is restated by hand. The dossier is a single HTML file
with inline SVG figures, no scripts and no external assets.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ..canonical import sha256_json
from ..ledger.store import Ledger
from .benchmark import ARM_ORDER, CONVENTIONAL, HYPOTHESES
from .oscillator import Design
from .stats import combine

PARTS = (
    (
        "observation-dependence",
        "Do observation-dependent decisions themselves help (closed loop vs yoked control)?",
        "H1",
    ),
    ("fewer-experiments", "Fewer experiments than conventional methods?", "H2"),
    ("detect-and-determine-change", "Detect previously unknown changes and determine what changed?", "H4"),
    ("better-model", "Develop a better explanatory model?", "H7"),
)
ARM_LABEL = {
    "closed-loop": "ATLAS closed loop",
    "yoked": "Yoked control (same designs, other problem)",
    "open-loop-optimal": "Open-loop D-optimal design",
    "fixed-sweep": "Fixed stepped-sine sweep",
    "random": "Random designs",
    "legacy-atlas": "Existing ATLAS rule (rain central v2, ported)",
    "closed-loop-no-critic": "Ablation: no critic",
    "closed-loop-no-challenge": "Ablation: no challenge",
}


def _f(v: Any, digits: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _ci(iv) -> str:
    return f"[{iv[0]:.3f}, {iv[1]:.3f}]"


def answer(bench: dict | None) -> dict:
    if bench is None:
        return {"verdict": "unresolved", "parts": [], "summary": "the held-out benchmark has not been run"}
    h = bench["hypotheses"]
    parts = [
        {"part": p, "question": q, "hypothesis": hid, "verdict": h[hid]["verdict"]} for p, q, hid in PARTS
    ]
    verdict = combine([p["verdict"] for p in parts])
    supported = [p["question"] for p in parts if p["verdict"] == "supported"]
    other = [f"{p['question']} ({p['verdict']})" for p in parts if p["verdict"] != "supported"]
    summary = ("Supported: " + "; ".join(supported) + ". " if supported else "") + (
        "Not established: " + "; ".join(other) + "." if other else ""
    )
    return {
        "verdict": verdict,
        "parts": parts,
        "summary": summary.strip(),
        "safety": {"H3": h["H3"]["verdict"], "H6": h["H6"]["verdict"]},
    }


# -- mission digests -----------------------------------------------------------


def mission_view(result: Any) -> dict:
    """Experiment-by-experiment view of one mission from its events."""

    rows: dict[int, dict] = {}
    analyses = []
    revisions = []
    challenges = []
    for e in result.events:
        kind = e["event"]
        if kind == "plan":
            c = e["choice"]
            rows[e["index"]] = {
                "index": e["index"] + 1,
                "purpose": c["purpose"],
                "design": c["design"],
                "reason": c["reason"],
                "utility": c.get("utility_nats"),
                "predicted": (e.get("prediction") or {}).get("interval_90"),
                "predicted_under": e.get("predicted_under"),
            }
        elif kind == "challenge-registered":
            rows.setdefault(e["index"], {})["kind"] = e["kind"]
        elif kind == "observation":
            r = rows.setdefault(e["index"], {})
            r["observed"] = e.get("amplitude")
            r["surprise"] = (e.get("surprise") or {}).get("z")
            r["within_90"] = e.get("within_predicted_90")
        elif kind == "analysis":
            d = e["decision"]
            analyses.append(
                {
                    "after": e["after_experiments"],
                    "structure": d["structure"],
                    "p_structure": d["p_structure"],
                    "p_change": d["p_change"],
                    "blockers": d["blockers"],
                    "information": e.get("information_realized_nats"),
                }
            )
            if e["after_experiments"] - 1 in rows:
                rows[e["after_experiments"] - 1]["information_realized"] = e.get("information_realized_nats")
                rows[e["after_experiments"] - 1]["leading_after"] = d["structure"]
                rows[e["after_experiments"] - 1]["p_after"] = d["p_structure"]
        elif kind == "revision":
            revisions.append(
                {
                    "seq": e["seq"],
                    "after": len([a for a in analyses]),
                    "kind": e["kind"],
                    "summary": e["summary"],
                }
            )
        elif kind == "challenge":
            challenges.append(
                {
                    "index": e["index"] + 1,
                    "kind": e.get("kind"),
                    "outcome": e["outcome"],
                    "z": e.get("z"),
                    "amplitude": e.get("amplitude"),
                    "chow_p": (e.get("chow") or {}).get("p"),
                    "target": e["target"],
                }
            )
    return {
        "experiments": [rows[i] for i in sorted(rows)],
        "analyses": analyses,
        "revisions": revisions,
        "challenges": challenges,
    }


# -- SVG figures ----------------------------------------------------------------


def svg_mission(view: dict, title: str) -> str:
    W, H = 760, 300
    left, right, top = 52, 16, 24
    plot_w = W - left - right
    exps = view["experiments"]
    n = max(len(exps), 1)
    x = lambda i: left + (i - 0.5) * plot_w / n  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}" class="fig">']
    # panel 1: probabilities
    p_top, p_h = top, 110
    out.append(
        f'<text x="{left}" y="{p_top - 8}" class="axis">leading-structure probability (teal) · P(change) (amber)</text>'
    )
    for v in (0.0, 0.5, 0.95, 1.0):
        y = p_top + p_h * (1 - v)
        out.append(
            f'<line x1="{left}" x2="{W - right}" y1="{y:.1f}" y2="{y:.1f}" class="grid{" dec" if v == 0.95 else ""}"/>'
        )
        out.append(f'<text x="{left - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{v:g}</text>')
    pts_s, pts_c = [], []
    for a in view["analyses"]:
        if a["after"] == 0:
            continue
        xi = x(a["after"])
        pts_s.append(f"{xi:.1f},{p_top + p_h * (1 - a['p_structure']):.1f}")
        pts_c.append(f"{xi:.1f},{p_top + p_h * (1 - a['p_change']):.1f}")
    if pts_s:
        out.append(f'<polyline points="{" ".join(pts_s)}" class="ln teal"/>')
        out.append(f'<polyline points="{" ".join(pts_c)}" class="ln amber"/>')
    # panel 2: predicted vs observed amplitude
    a_top, a_h = p_top + p_h + 42, 100
    amps = [r.get("observed") or 0 for r in exps] + [r["predicted"][1] for r in exps if r.get("predicted")]
    amax = max(amps + [1e-6]) * 1.1
    out.append(
        f'<text x="{left}" y="{a_top - 8}" class="axis">response amplitude: predicted 90% interval (bar) vs observed (dot)</text>'
    )
    for v in (0, amax / 2, amax):
        y = a_top + a_h * (1 - v / amax)
        out.append(f'<line x1="{left}" x2="{W - right}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{left - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{v:.2f}</text>')
    for i, r in enumerate(exps, start=1):
        xi = x(i)
        if r.get("predicted"):
            lo, hi = r["predicted"]
            out.append(
                f'<line x1="{xi:.1f}" x2="{xi:.1f}" y1="{a_top + a_h * (1 - lo / amax):.1f}" '
                f'y2="{a_top + a_h * (1 - hi / amax):.1f}" class="bar"/>'
            )
        if r.get("observed") is not None:
            cls = "hit" if r.get("within_90") in (True, None) else "miss"
            yv = a_top + a_h * (1 - r["observed"] / amax)
            shape = r.get("purpose", "explore")
            if shape == "challenge" and r.get("kind") == "sentinel":
                out.append(f'<rect x="{xi - 4:.1f}" y="{yv - 4:.1f}" width="8" height="8" class="{cls}"/>')
            elif shape == "challenge":
                out.append(
                    f'<path d="M{xi:.1f} {yv - 5:.1f} L{xi + 5:.1f} {yv:.1f} L{xi:.1f} {yv + 5:.1f} '
                    f'L{xi - 5:.1f} {yv:.1f}Z" class="{cls}"/>'
                )
            else:
                out.append(f'<circle cx="{xi:.1f}" cy="{yv:.1f}" r="4" class="{cls}"/>')
        out.append(f'<text x="{xi:.1f}" y="{a_top + a_h + 16}" class="tick" text-anchor="middle">{i}</text>')
    out.append(
        f'<text x="{W - right}" y="{H - 4}" class="tick" text-anchor="end">experiment · ● explore ◆ challenge ■ sentinel · red = outside the predicted 90%</text>'
    )
    out.append("</svg>")
    return "".join(out)


def svg_arms(summary: dict) -> str:
    arms = [a for a in ARM_ORDER if a in summary]
    W, row = 760, 30
    H = 40 + row * len(arms)
    left, right = 300, 70
    lo_all = 0.0
    hi_all = max(summary[a]["efficiency"]["interval"][1] for a in arms) * 1.08
    x = lambda v: left + (v - lo_all) / (hi_all - lo_all) * (W - left - right)  # noqa: E731
    out = [
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="censored experiments to a correct conclusion by arm" class="fig">'
    ]
    out.append(
        f'<text x="{left}" y="14" class="axis">censored experiments to a correct conclusion (lower is better), 95% interval</text>'
    )
    for k, a in enumerate(arms):
        y = 34 + k * row
        e = summary[a]["efficiency"]
        cls = "teal" if a == "closed-loop" else "muted"
        out.append(
            f'<text x="{left - 10}" y="{y + 4}" class="lab" text-anchor="end">{html.escape(ARM_LABEL.get(a, a))}</text>'
        )
        out.append(
            f'<line x1="{x(e["interval"][0]):.1f}" x2="{x(e["interval"][1]):.1f}" y1="{y}" y2="{y}" class="ci {cls}"/>'
        )
        out.append(f'<circle cx="{x(e["mean"]):.1f}" cy="{y}" r="5" class="pt {cls}"/>')
        out.append(f'<text x="{W - right + 8}" y="{y + 4}" class="tick">{e["mean"]:.2f}</text>')
    out.append("</svg>")
    return "".join(out)


# -- writers ---------------------------------------------------------------------


def _design(d: dict) -> str:
    return Design.from_dict(d).label()


def markdown(
    charter: dict,
    design: dict,
    missions: list[dict],
    bench: dict | None,
    evaluation: list[dict],
    ans: dict,
    pending: list[dict],
    prereg_ref: str,
) -> str:
    L: list[str] = []
    w = L.append
    w(f"# {charter['title']}\n")
    w(f"> **Question.** {charter['question']}\n")
    w(f"**Answer: {ans['verdict'].upper()}.** {ans['summary']}\n")
    if ans["parts"]:
        w("| Part of the question | Preregistered test | Verdict |\n|---|---|---|")
        for p in ans["parts"]:
            w(f"| {p['question']} | {p['hypothesis']} | **{p['verdict']}** |")
        w("")
    w(
        "This is a computational investigation of a simulated apparatus. Verdicts are bounded to the simulated "
        "oscillator family, the approved design space and the stated priors; they are not claims about physical "
        "systems.\n"
    )
    w("## Scope approved by the operator\n")
    b = charter["budgets"]
    w(
        f"- Experiments per mission: {b['experiments_per_mission']}; featured missions: {b['featured_missions']}; "
        f"benchmark problems per family: {b['benchmark_problems_per_family']}; model calls: {b['model_calls']}."
    )
    w(
        f"- Environment: {charter['environment']['executor']}; network {charter['environment']['network']}; hardware "
        f"control {charter['environment']['hardware_control']}; untrusted code {charter['environment']['untrusted_code']}; "
        f"model provider {charter['environment']['model_provider'] or 'none'}."
    )
    w(
        f"- Design space: {json.dumps(charter['design_space'])}. Hypothesis grammar: core {charter['hypothesis_grammar']['core']}, "
        f"anticipated {charter['hypothesis_grammar']['optional']}, admissible by the critic {charter['hypothesis_grammar']['expansion']}."
    )
    w(f"- Stopping rule: {json.dumps(charter['stopping'])}.\n")
    s = design["method_survey"]
    w("## 1. Investigating the question: methods and baselines\n")
    w(f"Advisor: {s['advisor']} ({s['generation']}). {s['note']}.\n")
    w("| Sub-question | Cues |\n|---|---|")
    for p in s["subquestions"]:
        w(f"| {p['question']} | {', '.join(p['cues'])} |")
    w("\n| Method | Answers | Implemented by |\n|---|---|---|")
    for m in s["methods"]:
        w(f"| {m['name']} | {', '.join(m['answers'])} | `{m['implemented_by']}` |")
    if s.get("related_skills"):
        w(
            "\nRelated catalogued skills (retrieval score): "
            + ", ".join(f"`{k['skill']}` ({k['score']})" for k in s["related_skills"])
            + "."
        )
    if s.get("model"):
        w(f"\nModel advisor: {json.dumps(s['model'])}")
    w("\n## 2. Competing hypotheses\n")
    w("| | Hypothesis | Null |\n|---|---|---|")
    for h in design["program_hypotheses"]:
        w(f"| {h['id']} | {h['hypothesis']} | {h['null']} |")
    mh = design["mission_hypotheses"]
    w(
        f"\nWithin each mission the competing explanations are model structures: anticipated "
        f"{', '.join('{' + ', '.join(s_) + '}' for s_ in mh['anticipated'])}; unanticipated terms the critic may admit: "
        f"{', '.join(mh['unanticipated_terms_admissible_by_the_critic'])}; and change hypotheses ({mh['change']}).\n"
    )
    w(
        f"## 3. Preregistration\n\nRecorded as `{prereg_ref}` before any experiment, with research source hash "
        f"`{design['research_source_hash']}`. The featured apparatus parameters were sealed first "
        f"({len(design['featured'])} commitments). Held-out split seed {design['benchmark']['split_seed']}, "
        f"{design['benchmark']['problems_per_family']} problems per family, arms {', '.join(design['benchmark']['arms'])}; "
        f"Bonferroni α = 0.05/{design['benchmark']['hypotheses_in_family']}.\n"
    )
    w("## 4. Featured investigations\n")
    w(
        "Five apparatus fixed before the investigation ran, chosen to exercise each mechanism. Their outcomes are "
        "reported as they happened; the benchmark below, not these five, is the evidence for the program-level claims.\n"
    )
    evals = {e["mission"]: e for e in evaluation}
    for m in missions:
        f, r = m["featured"], m["result"]
        v = mission_view(r)
        c = r.conclusion
        w(f"### {f.mission} — {f.story}\n")
        w(
            f"Apparatus `{f.apparatus}`. Stopped: **{r.stop_reason}** after {r.experiments} experiments. "
            f"Verdict: **{c['verdict']}** — {'; '.join(c['reasons'])}.\n"
        )
        w(
            "| # | Purpose | Design | Why | Predicted 90% | Observed | Surprise z | Info gained (nats) |\n|---|---|---|---|---|---|---|---|"
        )
        for row in v["experiments"]:
            purpose = row.get("purpose", "")
            if row.get("kind") == "sentinel":
                purpose = "challenge (sentinel)"
            pred = "—" if not row.get("predicted") else f"{row['predicted'][0]:.2f}–{row['predicted'][1]:.2f}"
            reason = str(row.get("reason", "")).replace("|", "/")
            w(
                f"| {row.get('index')} | {purpose} | {_design(row['design']) if row.get('design') else ''} | "
                f"{reason} | {pred} | {_f(row.get('observed'), 2)}"
                f"{'' if row.get('within_90') in (True, None) else ' ✗'} | {_f(row.get('surprise'), 1)} | "
                f"{_f(row.get('information_realized'), 2)} |"
            )
        if v["revisions"]:
            w("\nWhere the understanding changed:\n")
            for rv in v["revisions"]:
                w(f"- *{rv['kind']}* — {rv['summary']}")
        if v["challenges"]:
            w("\nChallenges (prediction recorded before each ran):\n")
            for ch in v["challenges"]:
                w(
                    f"- experiment {ch['index']} ({ch['kind']}): **{ch['outcome']}** (z = {_f(ch['z'], 2)}, "
                    f"Chow p = {_f(ch['chow_p'], 3)})"
                )
        coeffs = ", ".join(f"{t} = {x['mean']:+.3f} ± {x['sd']:.3f}" for t, x in c["coefficients"].items())
        w(
            f"\nConclusion: structure {{{', '.join(c['structure'])}}} (P = {c['p_structure']:.3f}); {coeffs}; "
            f"P(change) = {c['p_change']:.3f}"
            + (
                f"; change before experiment {c['change']['change_at'] + 1} in "
                f"{', '.join(c['change']['changed'])}"
                if c["change"]
                else ""
            )
            + f". Memory: {c['memory_state']}."
        )
        e = evals.get(f.mission, {})
        if "true_structure" in e:
            w(
                f"\nRevealed truth: {e['truth']}"
                + (
                    f"; change before experiment {e['true_change']['before_experiment']}"
                    if e.get("true_change")
                    else ""
                )
                + f". Structure {'correct' if e['structure_correct'] else '**incorrect**'}."
            )
        if r.escalation:
            w(
                f"\nEscalation pending: `{r.escalation['request_id']}` — {r.escalation['reason']}. "
                f"Authorize with `atlas research authorize --root <root> --request {r.escalation['request_id']} "
                f"--operator NAME`, then `atlas research resume --root <root>`."
            )
        w("")
    if bench is not None:
        sm, hy = bench["summary"], bench["hypotheses"]
        w("## 5. Benchmark on held-out problems\n")
        w(
            "| Arm | Censored experiments | Experiments used | Correct | False | Unresolved | Coverage 90% | Regret (nats/row) |\n|---|---|---|---|---|---|---|---|"
        )
        for a in ARM_ORDER:
            if a not in sm:
                continue
            e = sm[a]
            w(
                f"| {ARM_LABEL[a]} | {e['efficiency']['mean']:.2f} {_ci(e['efficiency']['interval'])} | "
                f"{e['experiments']['mean']:.2f} | {e['correct']['rate']:.2f} | {e['false']['rate']:.3f} | "
                f"{e['unresolved']['rate']:.2f} | {e['coverage90']['mean']:.3f} | {e['regret']['mean']:.3f} |"
            )
        w(
            "\nBy family (closed loop vs the strongest conventional design, open-loop D-optimal; censored experiments):\n"
        )
        w(
            "| Family | Closed loop | Yoked | Open-loop D-optimal | Fixed sweep | Change identified (CL) | Discovery (CL) |\n|---|---|---|---|---|---|---|"
        )
        for fam, e in sm["closed-loop"]["by_family"].items():
            w(
                f"| {fam} | {e['efficiency']:.2f} | {sm['yoked']['by_family'][fam]['efficiency']:.2f} | "
                f"{sm['open-loop-optimal']['by_family'][fam]['efficiency']:.2f} | {sm['fixed-sweep']['by_family'][fam]['efficiency']:.2f} | "
                f"{e['change_identified']:.2f} | {e['discovery']:.2f} |"
            )
        w("\n### Preregistered hypotheses\n")
        w("| | Hypothesis | Estimate | Adjusted interval | Verdict |\n|---|---|---|---|---|")
        for hid in HYPOTHESES:
            h = hy[hid]
            if hid == "H2":
                for p in h["parts"]:
                    w(
                        f"| H2 vs {p['versus']} | closed loop − {p['versus']} (censored experiments) | {p['difference']:+.2f} | "
                        f"{_ci(p['interval'])} | {p['verdict']} |"
                    )
                w(f"| **H2** | {HYPOTHESES[hid]} | | | **{h['verdict']}** |")
                continue
            est = h.get("difference", h.get("rate", h.get("mean")))
            w(f"| **{hid}** | {HYPOTHESES[hid]} | {est:+.3f} | {_ci(h['interval'])} | **{h['verdict']}** |")
        cl = sm["closed-loop"]
        w(
            f"\nFalse alarms on problems without a change: {cl['false_alarm']['count']}/{cl['false_alarm']['of']}. "
            f"Stale memories quarantined: {cl['memory']['stale_quarantined']}; correct memories kept: {cl['memory']['correct_kept']}. "
            f"Confident errors (posterior ≥ 0.9 on a wrong structure at some step): {cl['confident_error']['count']}, "
            f"recovered without a false conclusion: {cl['recovered']['count']}. Brier score of the reported structure "
            f"probability: {cl['brier_structure']:.3f}. Mean wall time per mission: {cl['wall_s']['mean']:.2f} s "
            f"(conventional arms {sm['fixed-sweep']['wall_s']['mean']:.2f} s)."
        )
        rp = bench["reproduction"]
        w(f"\nReproduction: {rp['identical']}/{rp['missions']} rerun missions produced identical digests.\n")
        w("### Ablations\n")
        for a in ("closed-loop-no-critic", "closed-loop-no-challenge"):
            e = sm[a]
            w(
                f"- {ARM_LABEL[a]}: censored experiments {e['efficiency']['mean']:.2f}, false conclusions "
                f"{e['false']['rate']:.3f}, unfamiliar-family correct {e['by_family']['unfamiliar']['correct']:.2f} "
                f"(full closed loop {cl['by_family']['unfamiliar']['correct']:.2f})."
            )
        w("")
    w("## 6. What failed, and what remains unknown\n")
    w(unknowns(missions, bench))
    w("\n## 7. Reproduce\n")
    w(
        "```sh\nuv run atlas research demo --root atlas-data/research\nuv run atlas ledger verify atlas-data/research/ledger\n```\n"
    )
    w(
        "Every mission can be replayed from its ledger (`atlas research resume`); replay verifies each regenerated "
        "event against the record. Open `observatory/index.html` and `reports/dossier.html` offline."
    )
    if pending:
        w(
            f"\nPending escalations: {', '.join(p['request_id'] + ' (' + p['kind'] + ', ' + p['mission'] + ')' for p in pending)}."
        )
    return "\n".join(L) + "\n"


def unknowns(missions: list[dict], bench: dict | None) -> str:
    items = []
    for m in missions:
        r = m["result"]
        if r.conclusion["verdict"] != "supported":
            items.append(
                f"- {m['featured'].mission}: not established — {'; '.join(r.conclusion['reasons'])}."
            )
    if bench is not None:
        sm, hy = bench["summary"], bench["hypotheses"]
        for hid in HYPOTHESES:
            if hy[hid]["verdict"] != "supported":
                items.append(f"- {hid} is **{hy[hid]['verdict']}**: {HYPOTHESES[hid]}")
        cl = sm["closed-loop"]
        items.append(
            f"- The closed loop reached no supported conclusion in {cl['unresolved']['rate']:.0%} of held-out "
            f"missions within {16} experiments, and made {cl['false']['count']} false conclusions "
            f"({cl['false']['rate']:.1%})."
        )
        missed = sum(r["missed_change"] for r in bench["results"] if r["arm"] == "closed-loop")
        items.append(
            f"- Changes that went undetected but were not claimed absent (incomplete conclusions): {missed}."
        )
    items += [
        "- Generality: one domain is implemented. The loop is written against the domain's interfaces, but no second "
        "domain has been run through it, so generality is designed, not demonstrated.",
        "- The analysis assumes at most one change per mission, process noise only (no sensor noise on the state) "
        "and a term grammar fixed by the charter; dynamics outside the grammar can be flagged but not explained.",
        "- Robust (Huber-weighted) evidence after the Gaussian assumption fails is an approximation, not an exact "
        "heavy-tailed likelihood.",
        "- No live language model ran in the recorded investigation; the model-advisor path is tested with a "
        "simulated local server only.",
    ]
    return "\n".join(items)


CSS = """:root{color-scheme:light dark;--bg:#f6f8f7;--panel:#fff;--line:#d4dedd;--text:#132022;--muted:#56686a;--teal:#0b7d6e;--amber:#a76b06;--red:#b42318}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#091617;--panel:#102224;--line:#284044;--text:#e3eeee;--muted:#a0b7b9;--teal:#65d6c0;--amber:#e4be7a;--red:#f09890}}
:root[data-theme=dark]{--bg:#091617;--panel:#102224;--line:#284044;--text:#e3eeee;--muted:#a0b7b9;--teal:#65d6c0;--amber:#e4be7a;--red:#f09890}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;line-height:1.25;margin:4px 0 12px}h2{margin-top:40px;font-size:20px;border-top:1px solid var(--line);padding-top:24px}h3{font-size:16px;margin-top:28px}
.eyebrow{font:11px/1.6 ui-monospace,monospace;letter-spacing:.16em;color:var(--teal);text-transform:uppercase}
.q{font-size:17px;border-left:3px solid var(--teal);padding:6px 14px;background:var(--panel)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:14px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
.v{display:inline-block;padding:1px 8px;border-radius:999px;font:12px ui-monospace,monospace;border:1px solid currentColor}
.v.supported{color:var(--teal)}.v.contradicted{color:var(--red)}.v.unresolved{color:var(--amber)}
.muted{color:var(--muted)}.fig{width:100%;height:auto;display:block}
.fig .grid{stroke:var(--line);stroke-width:1}.fig .grid.dec{stroke-dasharray:4 3}.fig .tick,.fig .axis,.fig .lab{fill:var(--muted);font:11px ui-monospace,monospace}.fig .lab{font:12px system-ui;fill:var(--text)}
.fig .ln{fill:none;stroke-width:2}.fig .teal{stroke:var(--teal)}.fig .amber{stroke:var(--amber)}.fig .bar{stroke:var(--muted);stroke-width:5;stroke-linecap:round;opacity:.45}
.fig .hit{fill:var(--teal)}.fig .miss{fill:var(--red)}.fig .ci{stroke-width:3}.fig .ci.muted{stroke:var(--muted)}.fig .pt.teal{fill:var(--teal);stroke:none}.fig .pt.muted{fill:var(--muted)}
code{font:12px ui-monospace,monospace;overflow-wrap:anywhere}li{margin:4px 0}"""


def dossier(
    charter: dict,
    design: dict,
    missions: list[dict],
    bench: dict | None,
    evaluation: list[dict],
    ans: dict,
    pending: list[dict],
    prereg_ref: str,
) -> str:
    e = html.escape
    P: list[str] = []
    w = P.append
    w(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    )
    w(
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:\">"
    )
    w(f"<title>ATLAS research dossier</title><style>{CSS}</style></head><body><main>")
    w('<p class="eyebrow">R.A.I.N. ATLAS · autonomous investigation · offline record</p>')
    w(f'<h1>{e(charter["title"])}</h1><p class="q">{e(charter["question"])}</p>')
    w(
        f'<div class="card"><p><b>Answer:</b> <span class="v {ans["verdict"]}">{ans["verdict"]}</span> {e(ans["summary"])}</p>'
    )
    if ans["parts"]:
        w("<table><tr><th>Part of the question</th><th>Test</th><th>Verdict</th></tr>")
        for p in ans["parts"]:
            w(
                f'<tr><td>{e(p["question"])}</td><td>{p["hypothesis"]}</td><td><span class="v {p["verdict"]}">{p["verdict"]}</span></td></tr>'
            )
        w("</table>")
    w(
        '<p class="muted">Computational investigation of a simulated apparatus; verdicts are bounded to the simulated '
        "family, the approved design space and the stated priors.</p></div>"
    )
    if bench is not None:
        sm, hy = bench["summary"], bench["hypotheses"]
        w("<h2>Benchmark on held-out problems</h2>")
        w(f'<div class="card">{svg_arms(sm)}</div>')
        w(
            '<div class="card"><table><tr><th></th><th>Hypothesis</th><th>Estimate</th><th>Adjusted interval</th><th>Verdict</th></tr>'
        )
        for hid in HYPOTHESES:
            h = hy[hid]
            if hid == "H2":
                est = "; ".join(
                    f"{p['versus']}: {p['difference']:+.2f} {_ci(p['interval'])}" for p in h["parts"]
                )
                w(
                    f'<tr><td>{hid}</td><td>{e(HYPOTHESES[hid])}</td><td colspan="2">{e(est)}</td><td><span class="v {h["verdict"]}">{h["verdict"]}</span></td></tr>'
                )
                continue
            est = h.get("difference", h.get("rate", h.get("mean")))
            w(
                f'<tr><td>{hid}</td><td>{e(HYPOTHESES[hid])}</td><td>{est:+.3f}</td><td>{_ci(h["interval"])}</td><td><span class="v {h["verdict"]}">{h["verdict"]}</span></td></tr>'
            )
        w("</table></div>")
        w(
            '<div class="card"><table><tr><th>Arm</th><th>Correct</th><th>False</th><th>Unresolved</th><th>Coverage 90%</th><th>Regret</th><th>s / mission</th></tr>'
        )
        for a in ARM_ORDER:
            if a in sm:
                x = sm[a]
                w(
                    f"<tr><td>{e(ARM_LABEL[a])}</td><td>{x['correct']['rate']:.2f}</td><td>{x['false']['rate']:.3f}</td>"
                    f"<td>{x['unresolved']['rate']:.2f}</td><td>{x['coverage90']['mean']:.3f}</td><td>{x['regret']['mean']:.3f}</td>"
                    f"<td>{x['wall_s']['mean']:.2f}</td></tr>"
                )
        w(
            f'</table><p class="muted">Reproduction: {bench["reproduction"]["identical"]}/{bench["reproduction"]["missions"]} '
            "rerun missions identical. Conventional designs: "
            + ", ".join(ARM_LABEL[a] for a in CONVENTIONAL)
            + ".</p></div>"
        )
    w(
        '<h2>Featured investigations</h2><p class="muted">Fixed before the run to exercise each mechanism; outcomes as they happened.</p>'
    )
    evals = {x["mission"]: x for x in evaluation}
    for m in missions:
        f, r = m["featured"], m["result"]
        v = mission_view(r)
        c = r.conclusion
        w(f'<h3>{e(f.mission)} — {e(f.story)}</h3><div class="card">')
        w(
            f'<p>Stopped: <b>{e(r.stop_reason)}</b> after {r.experiments} experiments · verdict <span class="v {c["verdict"]}">{c["verdict"]}</span> · '
            f"structure {{{e(', '.join(c['structure']))}}} (P = {c['p_structure']:.3f}) · P(change) = {c['p_change']:.3f} · memory {e(c['memory_state'])}</p>"
        )
        w(svg_mission(v, f.mission))
        if v["revisions"]:
            w(
                "<p><b>Where the understanding changed</b></p><ul>"
                + "".join(f"<li><i>{e(x['kind'])}</i> — {e(x['summary'])}</li>" for x in v["revisions"])
                + "</ul>"
            )
        w(
            "<table><tr><th>#</th><th>Purpose</th><th>Design</th><th>Why</th><th>Pred. 90%</th><th>Obs.</th><th>z</th></tr>"
        )
        for row in v["experiments"]:
            pred = "—" if not row.get("predicted") else f"{row['predicted'][0]:.2f}–{row['predicted'][1]:.2f}"
            purpose = "sentinel" if row.get("kind") == "sentinel" else row.get("purpose", "")
            w(
                f"<tr><td>{row.get('index')}</td><td>{e(purpose)}</td><td>{e(_design(row['design'])) if row.get('design') else ''}</td>"
                f"<td>{e(str(row.get('reason', '')))}</td><td>{pred}</td><td>{_f(row.get('observed'), 2)}</td><td>{_f(row.get('surprise'), 1)}</td></tr>"
            )
        w("</table>")
        x = evals.get(f.mission, {})
        if "true_structure" in x:
            w(
                f'<p class="muted">Revealed truth: {e(x["truth"])}. Structure {"correct" if x["structure_correct"] else "incorrect"}.</p>'
            )
        if r.escalation:
            w(
                f"<p><b>Escalation pending</b> <code>{e(r.escalation['request_id'])}</code>: {e(r.escalation['reason'])}</p>"
            )
        w("</div>")
    w('<h2>What failed, and what remains unknown</h2><div class="card"><ul>')
    for line in unknowns(missions, bench).splitlines():
        w(f"<li>{e(line.lstrip('- ').replace('**', ''))}</li>")
    w("</ul></div>")
    w(
        f'<p class="muted">Preregistration <code>{e(prereg_ref)}</code> · research source <code>{e(design["research_source_hash"])}</code>. '
        "Integrity of the ledger does not establish real-world validity.</p></main></body></html>"
    )
    return "".join(P)


def write_reports(
    root: Path,
    ledger: Ledger,
    prereg_ref: str,
    charter: dict,
    design: dict,
    missions: list[dict],
    bench: dict | None,
    evaluation: list[dict],
    pending: list[dict],
) -> dict:
    root = Path(root)
    out = root / "reports"
    out.mkdir(parents=True, exist_ok=True)
    ans = answer(bench)
    md = markdown(charter, design, missions, bench, evaluation, ans, pending, prereg_ref)
    page = dossier(charter, design, missions, bench, evaluation, ans, pending, prereg_ref)
    summary = {
        "question": charter["question"],
        "answer": ans,
        "missions": [
            {
                "mission": m["featured"].mission,
                "apparatus": m["featured"].apparatus,
                **m["result"].summary(),
                "view": mission_view(m["result"]),
            }
            for m in missions
        ],
        "evaluation": evaluation,
        "benchmark": None
        if bench is None
        else {
            "summary": bench["summary"],
            "hypotheses": bench["hypotheses"],
            "reproduction": bench["reproduction"],
        },
        "pending_escalations": pending,
        "preregistration": prereg_ref,
    }
    (out / "research-report.md").write_text(md, encoding="utf-8", newline="\n")
    (out / "dossier.html").write_text(page, encoding="utf-8", newline="\n")
    (out / "research-summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    report_ref = ledger.put_bytes(md.encode("utf-8"))
    digest = sha256_json({"report": report_ref, "answer": ans})
    existing = [(e.object, r) for e, r in ledger.records("report") if r.get("stage") == "investigation"]
    if not existing or existing[-1][1].get("digest") != digest:
        findings = []
        for vref_entry, vrec in ledger.records("verdict"):
            if vrec.get("label") in HYPOTHESES:
                findings.append({"claim": vrec["target"], "verdict": vrec["verdict"], "label": vrec["label"]})
        for m in missions:
            findings.append(
                {
                    "claim": m["claims"]["claim"],
                    "verdict": m["claims"]["verdict_value"],
                    "label": m["featured"].mission,
                }
            )
        entry = ledger.append(
            "report",
            {
                "experiment": prereg_ref,
                "stage": "investigation",
                "digest": digest,
                "findings": findings,
                "conclusion": ans,
                "limitations": unknowns(missions, bench).splitlines(),
                "reproduction": "atlas research demo / resume; atlas ledger verify",
                "report_object": report_ref,
                "author": {"role": "principal-investigator", "generation": "scripted"},
            },
        )
        if existing:
            ledger.append(
                "revision",
                {
                    "supersedes": existing[-1][0],
                    "replacement": entry.object,
                    "reason": "the investigation continued; this report replaces the earlier one",
                    "author": {"role": "principal-investigator", "generation": "scripted"},
                },
            )
    try:
        from ..observatory.export import export

        export(ledger.root, root / "observatory")
    except Exception as exc:  # noqa: BLE001 - the report must not fail because the viewer export failed
        (out / "observatory-export-error.txt").write_text(str(exc), encoding="utf-8", newline="\n")
    return {
        "answer": ans,
        "paths": {
            "markdown": str(out / "research-report.md"),
            "dossier": str(out / "dossier.html"),
            "summary": str(out / "research-summary.json"),
            "observatory": str(root / "observatory" / "index.html"),
        },
    }
