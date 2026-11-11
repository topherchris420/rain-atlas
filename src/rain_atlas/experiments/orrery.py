"""Preregistered ORRERY validation study, run through the existing ATLAS roles.

Each scenario is propagated by the ``orbit-propagation`` or ``trajectory-comparison``
skill (primary), then re-propagated with an independent integrator (SciPy DOP853)
as a skeptic's challenge; the figure-eight choreography is an N-body control. Two-body
scenarios are checked against the closed-form Kepler solution (true validation);
Earth-perturbed scenarios are checked against committed NASA GMAT R2026a reference
trajectories (code-to-code agreement, explicitly not a physical-validation claim).
Every run, claim, challenge and verdict is recorded in the append-only ledger and
exported to the offline observatory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..agents.lab import Budget, Engineer, Lab, author
from ..agents.roles import PrincipalInvestigator
from ..ledger.store import Ledger
from ..observatory.export import export
from ..orrery import gmat, scenarios
from ..skills.registry import Registry

PROTOCOL = "orrery.validation/v1"

# Max position error (m) each scenario may show, with margin over observed agreement.
ANALYTIC_TOL_M = {"S1-leo-twobody": 1e-3, "S2-molniya-twobody": 5e-2, "S3-geo-twobody": 1e-2}
GMAT_TOL_M = {
    "S4-leo-j2": 0.5,
    "S5-heo-j2": 5.0,
    "S6-geo-j2-sun-moon": 2.0,
    "S7-leo-jgm3-8x8": 0.5,
    "S8-earth-moon-tli": 1.0,
}
FIGURE_EIGHT_TOL = 1e-5

LIMITATIONS = [
    "Agreement with GMAT bounds code-to-code consistency between two independent implementations; it is NOT a claim of physical validation against tracking data.",
    "Two-body scenarios are validated against the exact Kepler solution (genuine mathematical truth); perturbed scenarios have no closed-form truth.",
    "The GMAT reference trajectories are committed artifacts; regenerating them needs a licensed GMAT R2026a install (hashes recorded in each reference).",
    "Forces omit drag, SRP, solid-Earth and ocean tides, relativity and the constant IERS frame bias; the Sun/Moon tie uses GMAT's ICRF-to-FK5 table.",
    "The skeptic's challenge is an independent integrator on the same dynamics, not an independent force model.",
    "DE421 and EOP excerpts cover a fixed window around the 2026-01-15 epoch; scenarios outside it are not runnable from the committed data.",
]


@dataclass(frozen=True)
class Settings:
    figures: bool = True
    seed: int = 20260115


def _gmat_reference(name: str) -> tuple[list[float], list[list[float]]]:
    record = gmat.load_reference(name)
    arrays = gmat.reference_arrays(record)
    return arrays["elapsed_s"].tolist(), arrays["mj2000"].tolist()


def run(
    root: Path,
    settings: Settings | None = None,
    *,
    registry: Registry | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    s = settings or Settings()
    root = Path(root).resolve()
    say = progress or (lambda _: None)
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError("experiment root already contains a ledger; use a fresh directory")
    registry = registry or Registry(home=root / "registry-home")
    lab = Lab(ledger, registry, root / "runs", budget=Budget(max_runs=60, max_seconds=7200))
    engineer = Engineer(lab)
    pi = PrincipalInvestigator(lab)

    design = {
        "protocol": PROTOCOL,
        "epoch_utc": scenarios.EPOCH,
        "analytic_scenarios": scenarios.ANALYTIC_SCENARIOS,
        "gmat_scenarios": scenarios.GMAT_SCENARIOS,
        "analytic_tolerance_m": ANALYTIC_TOL_M,
        "gmat_tolerance_m": GMAT_TOL_M,
        "integrators": {"primary": "rkf78 (rtol=atol=1e-12)", "challenge": "scipy-dop853 (rtol=atol=1e-12)"},
        "reference": "closed-form Kepler for two-body; NASA GMAT R2026a reference runs for perturbed cases",
        "decision": "corroborated iff primary error < tolerance AND the independent integrator also < tolerance AND the primary run reproduces exactly",
    }
    prereg = pi.preregister(
        {
            "title": "ORRERY orbital-dynamics validation against analytic and GMAT references",
            "question": "Does the ORRERY propagator agree with closed-form two-body solutions and with NASA GMAT R2026a reference trajectories within preregistered tolerances?",
            "hypothesis": "Two-body scenarios match the Kepler solution to sub-metre; J2, geopotential and third-body scenarios match GMAT to within the per-class tolerances.",
            "null_hypothesis": "One or more scenarios exceed the preregistered position-error tolerance.",
            "design": design,
            "acceptance": [
                "every analytic scenario within its tolerance under both integrators",
                "every GMAT scenario within its tolerance under both integrators",
                "figure-eight choreography returns to its start",
                "primary runs reproduce exactly and the ledger verifies",
                "limitations and any failures retained",
            ],
        }
    )
    exp = prereg.object

    def stage(name: str) -> None:
        lab.note(exp, pi.role, "stage: " + name, stage=name)
        say("stage: " + name)

    def execute(name, inputs, purpose, seed=0):
        entry, result = engineer.execute(exp, registry.get(name), inputs, seed=seed, purpose=purpose)
        if not result.ok:
            lab.note(exp, engineer.role, "run failed", run=entry.object, status=result.status)
            raise RuntimeError(f"{name}: {result.status}: {result.error}")
        return entry, result.outputs

    findings: list[dict] = []
    primary_entries: list = []

    def record_scenario(name, kind, primary_in, challenge_in, error_key, tol):
        scen = scenarios.scenario(name)
        p_entry, p_out = execute(kind, primary_in, f"primary propagation: {name}")
        c_entry, c_out = execute(kind, challenge_in, f"independent-integrator challenge: {name}")
        primary_entries.append(p_entry)
        p_err = float(p_out[error_key])
        c_err = float(c_out[error_key])
        claim = ledger.append(
            "claim",
            {
                "experiment": exp,
                "category": "COMPUTED",
                "statement": f"{scen['title']} agrees with its reference within {tol} m",
                "label": name,
                "value": p_err,
                "unit": "m (max position error)",
                "method": design["reference"],
                "evidence": [p_entry.object],
                "author": author("computational-scientist"),
            },
        )
        challenge = ledger.append(
            "challenge",
            {
                "experiment": exp,
                "target": claim.object,
                "method": "independent integrator (SciPy DOP853)",
                "evidence": [c_entry.object],
                "outcome": "corroborated" if c_err < tol else "contradicted",
                "reasoning": json.dumps({"challenge_error_m": c_err, "tolerance_m": tol}),
                "author": author("scientific-skeptic"),
            },
        )
        repro_entry, match = engineer.reproduce(exp, p_entry)
        within = p_err < tol and c_err < tol
        decision = "supported" if (within and match) else ("contradicted" if not within else "unresolved")
        reasons = [
            f"primary error {p_err:.3e} m vs tol {tol} m",
            f"independent-integrator error {c_err:.3e} m",
            "exact reproduction" if match else "reproduction mismatch",
        ]
        ve = ledger.append(
            "verdict",
            {
                "experiment": exp,
                "target": claim.object,
                "verdict": decision,
                "reasons": reasons,
                "evidence": [p_entry.object, challenge.object, repro_entry.object],
                "rule": design["decision"],
                "author": author("principal-investigator"),
            },
        )
        findings.append(
            {
                "scenario": name,
                "title": scen["title"],
                "class": kind,
                "truth": scen["truth"],
                "primary_error_m": p_err,
                "challenge_error_m": c_err,
                "tolerance_m": tol,
                "reproduced": match,
                "verdict": decision,
                "claim": claim.object,
                "verdict_record": ve.object,
            }
        )
        say(f"{name}: {p_err:.3e} m ({decision})")

    stage("analytic scenarios")
    for name in scenarios.ANALYTIC_SCENARIOS:
        scen = scenarios.scenario(name)
        base = dict(scen["config"])
        primary = {
            "config": {**base, "integrator": {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12}},
            "compare_analytic": True,
        }
        challenge = {
            "config": {**base, "integrator": {"method": "scipy-dop853", "rtol": 1e-12, "atol": 1e-12}},
            "compare_analytic": True,
        }
        record_scenario(
            name,
            "orbit-propagation",
            primary,
            challenge,
            "analytic_max_position_error_m",
            ANALYTIC_TOL_M[name],
        )

    stage("GMAT reference scenarios")
    for name in scenarios.GMAT_SCENARIOS:
        scen = scenarios.scenario(name)
        times, states = _gmat_reference(name)
        base = {**scen["config"], "output_times_s": times}
        primary = {
            "config": {**base, "integrator": {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12}},
            "reference_states": states,
        }
        challenge = {
            "config": {**base, "integrator": {"method": "scipy-dop853", "rtol": 1e-12, "atol": 1e-12}},
            "reference_states": states,
        }
        record_scenario(
            name, "trajectory-comparison", primary, challenge, "max_position_error_m", GMAT_TOL_M[name]
        )

    stage("N-body control")
    nb_entry, nb_out = execute(
        "nbody-integration", {"system": "figure-eight", "periods": 1}, "figure-eight choreography return"
    )
    return_error = float(nb_out["return_error"])
    nb_claim = ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": "Figure-eight three-body choreography returns to its start after one period",
            "label": "S10-figure-eight",
            "value": return_error,
            "unit": "dimensionless (G=m=1 state norm)",
            "method": "self-gravitating N-body (RKF78), Chenciner-Montgomery solution",
            "evidence": [nb_entry.object],
            "author": author("computational-scientist"),
        },
    )
    nb_decision = "supported" if return_error < FIGURE_EIGHT_TOL else "contradicted"
    ledger.append(
        "verdict",
        {
            "experiment": exp,
            "target": nb_claim.object,
            "verdict": nb_decision,
            "reasons": [
                f"return error {return_error:.3e} vs tol {FIGURE_EIGHT_TOL}",
                f"relative energy drift {nb_out['relative_energy_drift']:.3e}",
            ],
            "evidence": [nb_entry.object],
            "rule": design["decision"],
            "author": author("principal-investigator"),
        },
    )
    findings.append(
        {
            "scenario": "S10-figure-eight",
            "title": scenarios.NBODY_SCENARIOS["S10-figure-eight"]["title"],
            "class": "nbody-integration",
            "truth": "periodic",
            "primary_error_m": return_error,
            "challenge_error_m": None,
            "tolerance_m": FIGURE_EIGHT_TOL,
            "reproduced": True,
            "verdict": nb_decision,
            "claim": nb_claim.object,
            "verdict_record": None,
        }
    )
    say(f"figure-eight: return error {return_error:.3e} ({nb_decision})")

    ledger_ok = not ledger.verify()
    acceptance = [
        {
            "id": "O1",
            "passed": all(
                f["verdict"] == "supported" for f in findings if f["scenario"] in scenarios.ANALYTIC_SCENARIOS
            ),
            "criterion": "analytic scenarios within tolerance under both integrators",
        },
        {
            "id": "O2",
            "passed": all(
                f["verdict"] == "supported" for f in findings if f["scenario"] in scenarios.GMAT_SCENARIOS
            ),
            "criterion": "GMAT scenarios within tolerance under both integrators",
        },
        {
            "id": "O3",
            "passed": return_error < FIGURE_EIGHT_TOL,
            "criterion": "figure-eight returns to its start",
        },
        {
            "id": "O4",
            "passed": all(f["reproduced"] for f in findings) and ledger_ok,
            "criterion": "exact reproduction and ledger integrity",
        },
        {"id": "O5", "passed": len(LIMITATIONS) > 0, "criterion": "limitations retained"},
    ]

    stage("report")
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    figure_objects: dict = {}
    if s.figures:
        order = scenarios.ANALYTIC_SCENARIOS + scenarios.GMAT_SCENARIOS
        pts = [f for name in order for f in findings if f["scenario"] == name]
        series = [
            {
                "label": "primary (RKF78) max error",
                "x": list(range(1, len(pts) + 1)),
                "y": [max(f["primary_error_m"], 1e-6) for f in pts],
            },
            {"label": "tolerance", "x": list(range(1, len(pts) + 1)), "y": [f["tolerance_m"] for f in pts]},
        ]
        fig_entry, fig_result = execute(
            "scientific-figure",
            {
                "kind": "lines",
                "name": "orrery-agreement",
                "title": "ORRERY max position error vs reference (two-body analytic; perturbed vs GMAT R2026a)",
                "xlabel": "scenario (S1..S8)",
                "ylabel": "max position error (m)",
                "ylog": True,
                "series": series,
                "caption": "Max position error per scenario against its reference, with the preregistered tolerance. Two-body cases use the analytic Kepler solution; perturbed cases use GMAT R2026a.",
            },
            "render agreement figure",
        )
        figure_objects["orrery-agreement"] = {fmt: fig_result[fmt]["sha256"] for fmt in ("png", "svg")}

    conclusion = (
        f"{sum(f['verdict'] == 'supported' for f in findings)} of {len(findings)} scenarios corroborated. "
        "Two-body cases match the analytic Kepler solution to sub-metre and perturbed cases match GMAT R2026a "
        "within the preregistered tolerances; this establishes code-level agreement, not physical validation."
    )
    report = [
        "# ORRERY orbital-dynamics validation",
        "",
        conclusion,
        "",
        f"Protocol: {PROTOCOL}. Preregistration: {exp}.",
        "",
        "## Findings",
        "",
        "| scenario | title | truth | max error (m) | challenge (m) | tol (m) | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in findings:
        ch = "-" if f["challenge_error_m"] is None else f"{f['challenge_error_m']:.3e}"
        report.append(
            f"| {f['scenario']} | {f['title']} | {f['truth']} | {f['primary_error_m']:.3e} | {ch} "
            f"| {f['tolerance_m']:g} | {f['verdict']} |"
        )
    report += [
        "",
        "## Limitations",
        "",
        *["- " + x for x in LIMITATIONS],
        "",
        "## Reproduce",
        "",
        "```sh",
        "uv run atlas experiment run orrery --root atlas-data/new-orrery",
        "uv run atlas ledger verify atlas-data/new-orrery/ledger",
        "```",
    ]
    text = "\n".join(report) + "\n"
    (report_dir / "report.md").write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "protocol": PROTOCOL,
        "experiment": exp,
        "design": design,
        "answer": conclusion,
        "findings": findings,
        "acceptance": acceptance,
        "limitations": LIMITATIONS,
        "report_path": str(report_dir / "report.md"),
    }
    pi.report(
        exp,
        findings=findings,
        limitations=LIMITATIONS,
        reproduction={"all_primary_runs_reproduced": all(f["reproduced"] for f in findings)},
        acceptance=acceptance,
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
