"""Render an experiment summary as a Markdown report.

Every statement is labelled with its evidence category, and every number
carries the short hash of the ledger record it came from.
"""

from __future__ import annotations

from typing import Any


def short(ref: str | None) -> str:
    return "—" if not ref else f"`{ref.split(':', 1)[1][:12]}`"


def _num(value: Any, fmt: str = ".4f") -> str:
    return "—" if value is None else format(value, fmt)


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows]
    return out


def render(summary: dict) -> str:
    design = summary["design"]
    exp = summary["experiment"]
    passed = sum(a["passed"] for a in summary["acceptance"])
    lines = [
        f"# Spectral recovery — experiment {exp.split(':', 1)[1][:12]}",
        "",
        f"Protocol `{summary['protocol']}`, **{summary['mode']} mode**. Experiment id (preregistration hash): "
        f"`{exp}`. Ledger head at report time: `{summary['ledger_head']}`.",
        "",
        "Labels: **[COMPUTED]** = output of a recorded skill run; **[INTERPRETED]** = a statement derived from "
        "COMPUTED claims; **[GROUND TRUTH]** = the sealed generator parameters, published after every claim, "
        "challenge and verdict was recorded. All data are synthetic.",
        "",
    ]
    if summary["mode"] == "fixed":
        lines += [
            "> Fixed mode uses regression frequencies that are published in the source code. It tests the "
            "machinery and is exactly reproducible, but it is **not blind**. Run `--mode blinded` for a blind run.",
            "",
        ]
    lines += [
        "## Question and answer",
        "",
        f"**Question.** {summary['question']}",
        "",
        f"**[INTERPRETED]** {summary['answer']} (record {short(summary.get('answer_claim'))})",
        "",
        f"## Preregistered acceptance criteria — {passed}/{len(summary['acceptance'])} met",
        "",
    ]
    lines += _table(
        ["id", "criterion", "result", "detail"],
        [[a["id"], a["criterion"], "PASS" if a["passed"] else "**FAIL**", a["detail"]]
         for a in summary["acceptance"]],
    )
    lines += ["", "## Findings and verdicts", "",
              "Verdicts were computed and recorded before the truth was unsealed; the truth columns were filled "
              "in afterwards.", ""]
    rows = []
    for d in summary["datasets"]:
        for f in d["findings"]:
            rows.append([
                d["label"], f"{d['snr_ref_db']:+g}", f"**[COMPUTED]** {f['value_hz']:.3f} Hz ({f['origin']})",
                f"{f['detection_fraction']:.0%}", f["independent"] or "—", f["falsification"] or "—",
                "yes" if f["reproduced"] else "no" if f["reproduced"] is False else "—",
                f"**{f['verdict']}**", _num(f["nearest_truth_hz"], ".3f"),
                "yes" if f["matches_truth"] else "**no**", short(f["claim"]),
            ])
    lines += _table(["dataset", "SNR_ref dB", "claim", "detected in", "independent", "replicate test",
                     "reproduced", "verdict", "nearest true Hz", "within tol.", "record"], rows) if rows else [
        "No lines were claimed."]
    lines += ["", "Reasons for verdicts other than *supported*:", ""]
    reasons = [f"- {d['label']} {f['value_hz']:.3f} Hz — {f['verdict']}: {'; '.join(f['reasons'])}"
               for d in summary["datasets"] for f in d["findings"] if f["verdict"] != "supported"]
    lines += reasons or ["- none"]

    lines += ["", "## Recovery against the unsealed truth", ""]
    truth_rows = []
    for d in summary["datasets"]:
        for t in d["truth"]:
            truth_rows.append([d["label"], f"{t['frequency_hz']:g}", f"{t['amplitude']:g}", f"{t['phase_rad']:.4f}"])
        if d["is_control"]:
            truth_rows.append([d["label"], "noise only (control)", "—", "—"])
    lines += ["**[GROUND TRUTH]**", ""] + _table(["dataset", "frequency Hz", "amplitude", "phase rad"], truth_rows)
    lines += [""]
    rows = []
    for d in summary["datasets"]:
        for method in ("primary", "independent"):
            score = d["scores"].get(method)
            if not score:
                continue
            for t in score["tones"]:
                rows.append([
                    d["label"], f"{d['snr_ref_db']:+g}", method, f"{t['truth_hz']:g}", f"{t['recovery_rate']:.0%}",
                    _num(t["bias_hz"], "+.4f"), _num(t["rmse_hz"]), _num(t.get("std_hz")),
                    _num(t.get("crlb_std_hz"), ".5f"), _num(t.get("std_over_crlb"), ".2f"),
                ])
            rows.append([d["label"], f"{d['snr_ref_db']:+g}", method, "all", f"{score['all_recovered_rate']:.0%}",
                         "", "", "", "", f"false detections: {score['false_detections_total']}"])
    lines += ["**[COMPUTED]** (scored by `recovery-score` runs after unsealing; CRLB = Cramér-Rao bound for a "
              "single tone in white noise)", ""]
    lines += _table(["dataset", "SNR_ref dB", "method", "true Hz", "recovered", "bias Hz", "RMSE Hz", "std Hz",
                     "CRLB Hz", "std/CRLB"], rows)

    lines += ["", "**[INTERPRETED]** per dataset:", ""]
    lines += [f"- {d['interpretation']}" for d in summary["datasets"]]

    lines += ["", "## Negative results and failures", ""]
    negatives = [f"- {n['dataset']} ({n['snr_ref_db']:+g} dB): {n['result']}" for n in summary["negative_results"]]
    failures = [f"- {f['dataset']}: {f['stage']} run ended with status `{f['status']}`" for f in summary["failures"]]
    lines += negatives or ["- No negative results."]
    if failures:
        lines += ["", "Run failures:", ""] + failures

    if summary.get("figures"):
        lines += ["", "## Figures", ""]
        for fig in summary["figures"]:
            if fig["files"]:
                lines += [f"![{fig['caption']}]({fig['files']['png']})", "",
                          f"*{fig['caption']}* (run {short(fig['run'])}; SVG: `{fig['files']['svg']}`)", ""]
            else:
                lines += [f"- Figure {fig['name']} failed to render (status `{fig['status']}`).", ""]

    lines += ["", "## Methods", ""]
    for key, method in design["methods"].items():
        params = ", ".join(f"{k}={v}" for k, v in method.items() if k != "capability")
        lines.append(f"- **{key}**: capability `{method['capability']}`; {params}")
    lines += [
        f"- Data: {len(design['datasets'])} datasets, fs = {design['fs']:g} Hz, N = {design['n']} samples; "
        f"{design['snr_definition']}.",
        f"- Signal model: {design['signal_model']}.",
        f"- Control: {design['control']}.",
        f"- Claim rule: {design['decision_rules']['claim']}.",
        f"- Verdict rule: {design['decision_rules']['verdict']}.",
        "",
    ]
    lines += _table(["dataset", "SNR_ref dB", "noise std", "realizations", "replicates", "seed", "replicate seed"],
                    [[d["label"], f"{d['snr_ref_db']:+g}", f"{d['noise_std']:.5f}", str(d["realizations"]),
                      str(d["replicates"]), str(d["seed"]), str(d["replicate_seed"])] for d in design["datasets"]])

    lines += ["", "## Limitations", ""] + [f"- {item}" for item in summary["limitations"]]
    env = summary.get("environment", {})
    packages = ", ".join(f"{k} {v}" for k, v in sorted((env.get("packages") or {}).items()))
    lines += [
        "",
        "## Reproduction",
        "",
        f"- Base seed `{design['base_seed']}`; per-dataset seeds are in the table above.",
        f"- Environment: rain-atlas {env.get('atlas_version')} (commit {env.get('atlas_commit') or 'not in a git checkout'}), Python "
        f"{env.get('python')}, {env.get('os')}; {packages}.",
        f"- Skill runs in this experiment: {summary.get('runs')}; wall time {summary.get('elapsed_s')} s.",
        "- Verify the evidence: `atlas ledger verify <root>/ledger` (recomputes the hash chain, every object hash, "
        "the record rules and the seal commitment).",
        f"- Re-run: `atlas experiment run spectral-recovery --mode {summary['mode']} --root <new directory>`"
        + (" reproduces every number in this report." if summary["mode"] == "fixed" else
           " draws a new blinded truth; numbers will differ within sampling error."),
        "",
    ]
    return "\n".join(lines)
