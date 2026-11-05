"""Preregistered, bounded synchronization study using the existing ATLAS roles."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from ..agents.disagreement import verdict
from ..agents.lab import Budget, Engineer, Lab, author
from ..agents.roles import PrincipalInvestigator
from ..canonical import from_jsonable
from ..ledger.store import Ledger
from ..observatory.export import export
from ..science.uncertainty import disjoint_samples
from ..skills.registry import Registry

PROTOCOL = "atlas.synchronization/v1"
LIMITATIONS = [
    "Synthetic two-oscillator phase model, not physical evidence or an infinite-population phase transition.",
    "Fixed, published parameters; this study is NOT blinded. The separate spectral experiment retains sealed-truth evaluation.",
    "PLV is not causal coupling. Equal-frequency uncoupled oscillators can have PLV=1; a known-answer test demonstrates this failure.",
    "Phase and frequency methods share raw trajectories; independent replication uses different initial conditions and noise seeds, not a different physical model.",
    "Intervals use independent replicate summaries with approximate Student-t assumptions and Bonferroni correction. No posterior confidence or calibrated probability of truth is claimed.",
    "Stochastic trajectories use Euler-Maruyama. Numerical convergence tests bound selected cases; this experiment does not prove convergence at every noise level.",
    "Only deterministic cases away from the analytical threshold have a binary reference truth. Noisy and critical cases remain truth-unavailable for error-rate scoring.",
    "Thresholds define finite-window operational locking. Failure to meet them may be unresolved and is not proof of an absence of all synchronization.",
]


@dataclass(frozen=True)
class Settings:
    replicates: int = 12
    dt: float = 0.04
    duration_s: float = 60
    burn_s: float = 20
    seed: int = 20261104
    figures: bool = True
    couplings: tuple[float, ...] = (0, 0.6, 1.0, 1.4, 2.0)
    diffusions: tuple[float, ...] = (0, 0.08, 0.5)
    phase_lags: tuple[float, ...] = (0, 0.6)


def run(
    root: Path,
    settings: Settings | None = None,
    *,
    registry: Registry | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Execute a fresh study; interrupted attempts remain append-only and visible."""
    s = settings or Settings()
    root = Path(root).resolve()
    say = progress or (lambda _: None)
    if not 3 <= s.replicates <= 40 or s.duration_s - s.burn_s < 80 * s.dt:
        raise ValueError("insufficient independent replicates or post-burn duration")
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError(
            "experiment root already contains a ledger; use a fresh directory for a linked follow-up"
        )
    registry = registry or Registry(home=root / "registry-home")
    lab = Lab(ledger, registry, root / "runs", budget=Budget(max_runs=20, max_seconds=3600))
    engineer = Engineer(lab)
    pi = PrincipalInvestigator(lab)
    design = {
        **asdict(s),
        "protocol": PROTOCOL,
        "budget": {"max_runs": 20, "max_seconds": 3600},
        "reference": "delta'=1-K*cos(lag)*sin(delta); asymptotic deterministic locking iff K*cos(lag)>1",
        "decision": "Primary PLV lower simultaneous CI >0.90; independent block-frequency upper CI <0.05 rad/s; new-data replicate PLV lower CI >0.90; exact reproduction required",
        "negative": "PLV upper CI <0.50 or independent drift lower CI >0.15 rad/s contradicts operational locking; intermediate evidence unresolved",
        "intervals": "two metric families, Bonferroni across all conditions; Student-t across independent trajectories",
        "controls": "K=0 negative, D=0 and K=2 positive; phase lag and D>0 challenge model assumptions",
        "replicate_seed": s.seed + 100000,
    }
    prereg = pi.preregister(
        {
            "title": "Synchronization under noise and model uncertainty",
            "question": "Can independent phase and frequency methods establish finite-window synchronization under increasing noise and phase-lag uncertainty?",
            "hypothesis": "At K=2, D=0 and lag=0, temporal phase locking is supported by both methods and independent replication; noise and misspecification may leave it unresolved.",
            "null_hypothesis": "No stable temporal locking meeting the preregistered phase and frequency thresholds.",
            "design": design,
            "acceptance": [
                "deterministic K=2, lag=0 supported",
                "K=0, D=0 never supported",
                "exact generator and analysis reproduction",
                "ledger and every artifact verify",
                "negative or unresolved results retained",
            ],
        }
    )
    exp = prereg.object

    def stage(name):
        lab.note(exp, pi.role, "stage: " + name, stage=name)
        say("stage: " + name)

    def execute(name, inputs, seed, purpose, files=None):
        entry, result = engineer.execute(
            exp, registry.get(name), inputs, seed=seed, purpose=purpose, files=files
        )
        if not result.ok:
            lab.note(
                exp,
                engineer.role,
                "experiment interrupted by failed run",
                run=entry.object,
                status=result.status,
            )
            raise RuntimeError(f"{name}: {result.status}: {result.error}")
        return entry, result, from_jsonable(result.outputs)

    sim_inputs = {
        "couplings": list(s.couplings),
        "diffusions": list(s.diffusions),
        "phase_lags": list(s.phase_lags),
        "dt": s.dt,
        "duration_s": s.duration_s,
        "replicates": s.replicates,
    }
    stage("execute")
    generated, _, data = execute(
        "synchronization-sweep", sim_inputs, s.seed, "primary synthetic trajectories"
    )
    rep_generated, _, rep_data = execute(
        "synchronization-sweep", sim_inputs, s.seed + 100000, "independent replicate trajectories"
    )
    disjoint_samples([data["phases"]["sha256"]], [rep_data["phases"]["sha256"]])
    for entry, dataset in ((generated, data), (rep_generated, rep_data)):
        ledger.append(
            "dataset",
            {
                "experiment": exp,
                "name": "trajectories " + entry.object[7:19],
                "origin": "synthetic",
                "media_type": "application/x-npy",
                "object": dataset["phases"]["sha256"],
                "provenance": {"generator": entry.object, "protocol": PROTOCOL},
            },
        )

    def analyse(dataset, method, purpose):
        refs, files = lab.stage(dataset["phases"])
        return execute(
            "synchronization-measure",
            {
                "phases": refs[0],
                "conditions": dataset["conditions"],
                "dt": s.dt,
                "burn_s": s.burn_s,
                "method": method,
            },
            0,
            purpose,
            files,
        )

    stage("analyse")
    primary, _, p = analyse(data, "phase", "computational-scientist: temporal phase concentration")
    stage("challenge")
    independent, _, q = analyse(data, "frequency", "scientific-skeptic: independent time-domain block slopes")
    replicate, _, r = analyse(rep_data, "phase", "scientific-skeptic: independent-data replication")
    stage("reproduce")
    repro_gen, gen_match = engineer.reproduce(exp, generated)
    repro, match = engineer.reproduce(exp, primary)
    findings = []
    claims = []
    verdicts = []
    stage("decide")
    for a, b, c in zip(p["rows"], q["rows"], r["rows"]):
        cond = a["condition"]
        label = f"K={cond['coupling']:g}, D={cond['diffusion']:g}, lag={cond['phase_lag']:g}"
        claim = ledger.append(
            "claim",
            {
                "experiment": exp,
                "category": "COMPUTED",
                "statement": "Operational stable-locking hypothesis at " + label,
                "label": label,
                "value": a["interval"]["mean"],
                "unit": "PLV (dimensionless)",
                "uncertainty": a["interval"],
                "method": "temporal PLV with preregistered thresholds",
                "evidence": [primary.object],
                "author": author("computational-scientist"),
            },
        )
        challenges = []
        for method, result, run_entry in (
            ("Independent block-frequency estimation", b, independent),
            ("Independent-data phase replication", c, replicate),
        ):
            ce = ledger.append(
                "challenge",
                {
                    "experiment": exp,
                    "target": claim.object,
                    "method": method,
                    "evidence": [run_entry.object],
                    "outcome": result["outcome"],
                    "reasoning": json.dumps({"interval": result["interval"], "unit": result["unit"]}),
                    "author": author("scientific-skeptic"),
                },
            )
            challenges.append(ce.object)
        decision, reasons = verdict(b["outcome"], c["outcome"], match and gen_match)
        if a["outcome"] != "corroborated":
            decision = (
                "contradicted" if a["outcome"] == "contradicted" and match and gen_match else "unresolved"
            )
            reasons = ["primary phase criterion " + a["outcome"], *reasons]
        ve = ledger.append(
            "verdict",
            {
                "experiment": exp,
                "target": claim.object,
                "verdict": decision,
                "reasons": reasons,
                "evidence": [primary.object, *challenges, repro.object, repro_gen.object],
                "rule": design["decision"],
                "author": author("principal-investigator"),
            },
        )
        product = cond["coupling"] * math.cos(cond["phase_lag"])
        truth = None if cond["diffusion"] > 0 or abs(product - 1) < 1e-8 else product > 1
        error = None if truth is None else (decision == "supported") != truth
        findings.append(
            {
                "claim": claim.object,
                "claims": [claim.object],
                "verdict": decision,
                "verdict_record": ve.object,
                "condition": cond,
                "phase": a["interval"],
                "frequency": b["interval"],
                "replicate": c["interval"],
                "reference_locked": truth,
                "error_vs_asymptotic_reference": error,
                "error_status": "truth unavailable"
                if truth is None
                else "detected disagreement"
                if a["outcome"] != b["outcome"]
                else "undetected error"
                if error
                else "no error detected",
                "note": "Finite-window criterion and asymptotic reference differ; discrepancy is retained.",
            }
        )
        claims.append(claim.object)
        verdicts.append(ve.object)
    acceptance = [
        {
            "id": "S1",
            "passed": any(
                f["condition"] == {"coupling": 2.0, "diffusion": 0.0, "phase_lag": 0.0}
                and f["verdict"] == "supported"
                for f in findings
            ),
            "criterion": "deterministic positive control supported",
        },
        {
            "id": "S2",
            "passed": all(
                f["verdict"] != "supported"
                for f in findings
                if f["condition"]["coupling"] == 0 and f["condition"]["diffusion"] == 0
            ),
            "criterion": "uncoupled negative controls never supported",
        },
        {"id": "S3", "passed": match and gen_match, "criterion": "exact primary and generator reproduction"},
        {"id": "S4", "passed": not ledger.verify(), "criterion": "evidence and artifact integrity"},
        {
            "id": "S5",
            "passed": any(f["verdict"] != "supported" for f in findings),
            "criterion": "negative or unresolved outcomes retained",
        },
    ]
    stage("report")
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    figure_objects = {}
    if s.figures:
        series = []
        for lag in s.phase_lags:
            for noise in s.diffusions:
                points = [
                    f
                    for f in findings
                    if f["condition"]["phase_lag"] == lag and f["condition"]["diffusion"] == noise
                ]
                series.append(
                    {
                        "label": f"D={noise:g}, lag={lag:g}",
                        "x": [f["condition"]["coupling"] for f in points],
                        "y": [f["phase"]["mean"] for f in points],
                        "yerr": [(f["phase"]["high"] - f["phase"]["low"]) / 2 for f in points],
                    }
                )
        fig_entry, fig_result, fig = execute(
            "scientific-figure",
            {
                "kind": "lines",
                "name": "synchronization-transition",
                "title": "Finite-window phase locking under noise and model uncertainty",
                "xlabel": "Coupling K (rad/s)",
                "ylabel": "Temporal PLV (dimensionless)",
                "series": series,
                "caption": "Independent trajectory means; approximate simultaneous Student-t intervals, Bonferroni across conditions and two metrics. Synthetic two-oscillator model.",
            },
            0,
            "render preregistered study figure",
        )
        figure_objects["synchronization-transition"] = {fmt: fig[fmt]["sha256"] for fmt in ("png", "svg")}
        for fmt in ("png", "svg"):
            shutil.copyfile(
                fig_result.run_dir / "output" / fig[fmt]["$artifact"], report_dir / fig[fmt]["$artifact"]
            )
    conclusion = f"{sum(f['verdict'] == 'supported' for f in findings)} of {len(findings)} conditions supported operational locking; {sum(f['verdict'] == 'unresolved' for f in findings)} unresolved. This establishes only finite-window behavior of the specified synthetic model."
    report = [
        "# Synchronization under noise and model uncertainty",
        "",
        conclusion,
        "",
        f"Protocol: {PROTOCOL}. Preregistration: {exp}.",
        "",
        "## Preregistered design",
        "",
        "```json",
        json.dumps(design, indent=2),
        "```",
        "",
        "## Findings",
        "",
        "| K (rad/s) | D (rad²/s) | lag (rad) | PLV [simultaneous CI] | drift rad/s | verdict | reference |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in findings:
        c = f["condition"]
        v = f["phase"]
        report.append(
            f"| {c['coupling']} | {c['diffusion']} | {c['phase_lag']} | {v['mean']:.4f} [{v['low']:.4f}, {v['high']:.4f}] | {f['frequency']['mean']:.4f} | {f['verdict']} | {f['reference_locked']} |"
        )
    report += [
        "",
        "## Limitations and negative results",
        "",
        *["- " + x for x in LIMITATIONS],
        "",
        "## Reproduce",
        "",
        "```sh",
        f"uv run atlas experiment run synchronization --root atlas-data/new-sync --replicates {s.replicates}",
        "uv run atlas ledger verify atlas-data/new-sync/ledger",
        "```",
        "",
        "Each finding's full evidence references and intervals are in summary.json and the ledger. A hash chain establishes internal integrity, not authenticity or truth.",
    ]
    text = "\n".join(report) + "\n"
    # LF on every OS: the file must hash to the report object recorded below.
    (report_dir / "report.md").write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "protocol": PROTOCOL,
        "experiment": exp,
        "question": ledger.get_json(exp)["question"],
        "design": design,
        "answer": conclusion,
        "findings": findings,
        "acceptance": acceptance,
        "limitations": LIMITATIONS,
        "negative_results": [f for f in findings if f["verdict"] != "supported"],
        "report_path": str(report_dir / "report.md"),
    }
    pi.report(
        exp,
        findings=findings,
        limitations=LIMITATIONS,
        reproduction={"settings": asdict(s), "generator_match": gen_match, "primary_match": match},
        acceptance=acceptance,
        negative_results=summary["negative_results"],
        conclusion=conclusion,
        report_object=ledger.put_bytes(text.encode()),
        figure_objects=figure_objects,
    )
    summary["ledger_problems"] = ledger.verify()
    if summary["ledger_problems"]:
        raise ValueError("final ledger verification failed: " + str(summary["ledger_problems"]))
    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary["observatory_path"] = str(export(root / "ledger", root / "observatory", registry=registry))
    say(conclusion)
    return summary
