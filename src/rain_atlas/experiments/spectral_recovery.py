"""Phase 10 reference experiment: recover and validate tone frequencies.

Question: can a multi-agent scientific system independently recover and
validate the dominant frequencies of a noisy synthetic signal?

Every number in the outcome comes from a recorded skill run. This module only
sequences the roles, applies the preregistered decision rules, and checks the
preregistered acceptance criteria against recorded values.
"""

from __future__ import annotations

import math
import secrets
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..agents.disagreement import verdict as decide
from ..agents.lab import Budget, Engineer, Lab, author
from ..agents.roles import ComputationalScientist, PrincipalInvestigator, Skeptic
from ..canonical import from_jsonable
from ..exec import environment
from ..exec.policy import HostPolicy
from ..ledger.store import Entry, Ledger
from ..skills.registry import Registry

PROTOCOL = "rain-atlas/spectral-recovery/v1"
VERDICT_RULE = (
    "rain-atlas/verdict/v1: supported = independent estimator corroborates AND replicate test corroborates AND "
    "the primary run reproduces exactly; contradicted = either check contradicts; otherwise unresolved"
)
QUESTION = (
    "Can a multi-agent scientific system independently recover and validate the dominant frequencies of a "
    "noisy synthetic signal?"
)
STAGES = ("seal", "generate", "analyse", "challenge", "reproduce", "decide", "unseal", "score", "interpret", "report")
AMPLITUDES = (1.0, 0.6, 0.35)
FIXED_FREQUENCIES_HZ = (47.3, 123.9, 311.6)
FIXED_BASE_SEED = 20261030
CAPABILITIES = {
    "generate": "signal.generate-tones",
    "primary": "spectral.peak-frequencies",
    "independent": "spectral.sinusoid-fit",
    "agreement": "evaluation.method-agreement",
    "falsify": "statistics.tone-presence-test",
    "score": "evaluation.recovery-score",
    "spectrum_figure": "visualization.spectrum-figure",
    "line_figure": "visualization.line-figure",
}
ACCEPTANCE = (
    {"id": "A1", "text": "In every tone-bearing dataset with SNR_ref >= 0 dB, the primary method recovers each true "
                         "tone within the tolerance in at least 95% of realizations, and each true tone has a "
                         "'supported' finding."},
    {"id": "A2", "text": "At the highest SNR_ref, each tone's primary-method |bias| and RMSE are below 0.05 Hz; at "
                         "every SNR_ref >= 0 dB the independent estimator's standard deviation is within a factor "
                         "of 2 of the Cramér-Rao bound."},
    {"id": "A3", "text": "In the noise-only control, at most 15% of realizations contain any primary detection and "
                         "no finding is 'supported'."},
    {"id": "A4", "text": "Predicted negative result: at the lowest SNR_ref (-30 dB) recovery fails (all tones "
                         "recovered together in fewer than 50% of realizations), the report lists it as a "
                         "negative result, and no finding there is 'supported'."},
    {"id": "A5", "text": "Every 'supported' finding lies within the tolerance of a true tone."},
    {"id": "A6", "text": "Every primary analysis run and every data-generating run reproduces byte-identically."},
    {"id": "A7", "text": "The ledger verifies: hash chain, object hashes, record rules and the seal/unseal "
                         "commitment."},
)


class ExperimentAborted(RuntimeError):
    pass


def noise_std(snr_ref_db: float) -> float:
    """SNR_ref = 10 log10((A_ref^2 / 2) / sigma^2) with A_ref = 1."""

    return math.sqrt(0.5 / 10 ** (snr_ref_db / 10.0))


@dataclass(frozen=True)
class Settings:
    mode: str = "fixed"  # "fixed": regression truth published in source; "blinded": truth drawn from OS entropy
    fs: float = 1000.0
    n: int = 8192
    realizations: int = 20
    replicates: int = 10
    snr_levels_db: tuple[float, ...] = (20.0, 0.0, -10.0, -20.0, -30.0)
    control_snr_db: float = 0.0
    nperseg: int = 2048
    overlap: float = 0.5
    alpha: float = 0.01
    tolerance_hz: float = 0.25
    claim_fraction: float = 0.5
    agreement_fraction: float = 0.8
    falsification_fraction: float = 0.8
    fmin_hz: float = 2.0
    max_tones: int = 6
    figures: bool = True
    bundle: bool = True

    def design(self, base_seed: int) -> dict:
        if self.mode not in ("fixed", "blinded"):
            raise ValueError("mode must be 'fixed' or 'blinded'")
        levels = list(self.snr_levels_db) + [self.control_snr_db]
        datasets = [
            {
                "label": f"D{k}",
                "snr_ref_db": snr,
                "noise_std": noise_std(snr),
                "realizations": self.realizations,
                "replicates": self.replicates,
                "seed": base_seed + 1000 * k,
                "replicate_seed": base_seed + 1000 * k + 500,
            }
            for k, snr in enumerate(levels, start=1)
        ]
        truth_statement = (
            "three cosines with amplitudes 1.0, 0.6 and 0.35 at sealed frequencies and sealed phases"
            if self.mode == "blinded"
            else "three cosines with amplitudes 1.0, 0.6 and 0.35 at the fixed regression frequencies published in "
                 "the source code (47.3, 123.9, 311.6 Hz) with phases from the base seed; sealed for protocol "
                 "uniformity, but NOT blind"
        )
        return {
            "protocol": PROTOCOL,
            "mode": self.mode,
            "base_seed": base_seed,
            "fs": self.fs,
            "n": self.n,
            "snr_definition": "SNR_ref = 10 log10((A_ref^2/2) / sigma^2) with A_ref = 1; noise is white Gaussian",
            "signal_model": truth_statement,
            "frequency_prior": "uniform in [20, 480] Hz, pairwise separation >= 15 Hz (blinded mode)",
            "control": f"exactly one of the datasets with snr_ref_db == {self.control_snr_db} is noise only; "
                       "which one is sealed",
            "datasets": datasets,
            "methods": {
                "primary": {"capability": CAPABILITIES["primary"], "nperseg": self.nperseg, "overlap": self.overlap,
                            "alpha": self.alpha, "fmin_hz": self.fmin_hz, "min_separation_hz": 2.0},
                "independent": {"capability": CAPABILITIES["independent"], "max_tones": self.max_tones, "pad": 8,
                                "fmin_hz": self.fmin_hz},
                "agreement": {"capability": CAPABILITIES["agreement"], "tolerance_hz": self.tolerance_hz,
                              "min_fraction": self.agreement_fraction},
                "falsification": {"capability": CAPABILITIES["falsify"], "alpha": self.alpha,
                                  "min_fraction": self.falsification_fraction, "data": "independent replicates"},
                "scoring": {"capability": CAPABILITIES["score"], "tolerance_hz": self.tolerance_hz},
            },
            "decision_rules": {
                "claim": f"a line is claimed when the primary method detects it in at least "
                         f"{self.claim_fraction:.0%} of a dataset's realizations",
                "verdict": VERDICT_RULE,
            },
        }


def draw_truth(settings: Settings, design: dict) -> dict:
    candidates = [d["label"] for d in design["datasets"] if d["snr_ref_db"] == settings.control_snr_db]
    if settings.mode == "fixed":
        rng = np.random.default_rng([design["base_seed"], 1])
        freqs = list(FIXED_FREQUENCIES_HZ)
        control = candidates[-1]
    else:
        rng = np.random.default_rng(secrets.randbits(128))
        while True:
            freqs = sorted(float(round(f, 3)) for f in rng.uniform(20.0, 480.0, len(AMPLITUDES)))
            if min(np.diff(freqs)) >= 15.0:
                break
        freqs = [float(f) for f in rng.permutation(freqs)]
        control = candidates[int(rng.integers(len(candidates)))]
    phases = rng.uniform(0.0, 2.0 * math.pi, len(AMPLITUDES))
    tones = [
        {"frequency_hz": float(f), "amplitude": a, "phase_rad": float(p)}
        for f, a, p in zip(freqs, AMPLITUDES, phases)
    ]
    return {"tones": tones, "control_dataset": control}


def tones_for(truth: dict, label: str) -> list[dict]:
    return [] if label == truth["control_dataset"] else truth["tones"]


@dataclass
class DatasetState:
    spec: dict
    data: dict = field(default_factory=dict)  # part -> {"ref", "run", "dataset", "public"}
    primary: dict | None = None
    independent: list[list[float]] | None = None
    independent_run: Entry | None = None
    agreement: dict = field(default_factory=dict)
    falsification: dict = field(default_factory=dict)
    unclaimed: list = field(default_factory=list)
    reproduced: bool | None = None
    verdicts: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    score_claims: list = field(default_factory=list)


class _Stages:
    def __init__(self, lab: Lab, experiment: str, say: Callable[[str], None]):
        self.lab, self.experiment, self.say, self.index = lab, experiment, say, -1

    def __call__(self, name: str) -> None:
        index = STAGES.index(name)
        if index <= self.index:
            raise RuntimeError(f"stage {name!r} cannot follow {STAGES[self.index]!r}")
        self.index = index
        self.lab.note(self.experiment, "principal-investigator", f"stage: {name}", stage=name)
        self.say(f"stage: {name}")


def _challenges_for(ledger: Ledger, claim: str) -> list[str]:
    return [e.object for e, r in ledger.records("challenge") if r["target"] == claim]


def run(
    root: Path,
    settings: Settings | None = None,
    *,
    registry: Registry | None = None,
    host: HostPolicy | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Execute the whole protocol under *root*; returns a JSON-able summary."""

    settings = settings or Settings()
    say = progress or (lambda _message: None)
    clock = time.monotonic()
    root = Path(root)
    ledger = Ledger(root / "ledger")
    lab = Lab(ledger, registry or Registry(), root / "runs", host=host or HostPolicy(),
              budget=Budget(max_runs=600, max_seconds=6 * 3600))
    engineer = Engineer(lab)
    pi = PrincipalInvestigator(lab)
    scientist = ComputationalScientist(lab, engineer)
    skeptic = Skeptic(lab, engineer)

    base_seed = FIXED_BASE_SEED if settings.mode == "fixed" else secrets.randbits(31)
    design = settings.design(base_seed)
    prereg = pi.preregister({
        "title": "Blind recovery and validation of tone frequencies in noise",
        "question": QUESTION,
        "hypothesis": "Down to SNR_ref = 0 dB the roles recover all three tones and the evidence rules mark each "
                      "as supported; recovery degrades as SNR falls, weakest tone first, and fails at -30 dB.",
        "null_hypothesis": "Supported findings do not coincide with the true tones within the tolerance more often "
                           "than spurious lines do.",
        "design": design,
        "acceptance": list(ACCEPTANCE),
        "instance": secrets.token_hex(8),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    })
    experiment = prereg.object
    say(f"experiment {experiment[7:19]} preregistered ({settings.mode} mode)")
    stage = _Stages(lab, experiment, say)
    skills = {key: pi.select(experiment, capability) for key, capability in CAPABILITIES.items()}
    fs, n, tol = settings.fs, settings.n, settings.tolerance_hz
    states = {d["label"]: DatasetState(d) for d in design["datasets"]}
    failures: list[dict] = []

    def abort(message: str, run_entry: Entry | None = None) -> None:
        lab.note(experiment, "principal-investigator", f"experiment aborted: {message}",
                 run=run_entry.object if run_entry else None)
        raise ExperimentAborted(message)

    # Ground truth is committed before any data exists.
    stage("seal")
    truth = draw_truth(settings, design)
    _, commitment = ledger.seal("ground truth: tone parameters and control assignment", truth,
                                context={"experiment": experiment, "protocol": PROTOCOL})

    stage("generate")
    for label, st in states.items():
        for part, seed_key, count_key in (("analysis", "seed", "realizations"), ("replicate", "replicate_seed", "replicates")):
            public = {"fs": fs, "n": n, "noise_std": st.spec["noise_std"], "realizations": st.spec[count_key]}
            run_entry, result = engineer.execute(
                experiment, skills["generate"], {**public, "tones": tones_for(truth, label)},
                seed=st.spec[seed_key], purpose=f"generate {label} {part} signals",
                sealed={"commitment": commitment, "public": public},
            )
            if not result.ok:
                abort(f"data generation failed for {label} {part}: {result.status}", run_entry)
            ref = from_jsonable(result.outputs)["signals"]
            dataset = ledger.append("dataset", {
                "experiment": experiment,
                "name": f"{label}-{part}",
                "origin": "synthetic",
                "media_type": "application/x-npy",
                "object": ref["sha256"],
                "shape": [st.spec[count_key], n],
                "provenance": {"run": run_entry.object, "generator": f"{skills['generate'].name}@"
                               f"{skills['generate'].version}", "seed": st.spec[seed_key]},
            })
            st.data[part] = {"ref": ref, "run": run_entry, "dataset": dataset, "public": public}

    stage("analyse")
    primary_params = {"fs": fs, "nperseg": settings.nperseg, "overlap": settings.overlap, "alpha": settings.alpha,
                      "min_separation_hz": 2.0, "fmin": settings.fmin_hz}
    for label, st in states.items():
        st.primary = scientist.detect_lines(
            experiment, skills["primary"], st.data["analysis"]["ref"], primary_params, seed=0, label=label,
            claim_fraction=settings.claim_fraction, cluster_tolerance=tol,
        )
        if st.primary["estimates"] is None:
            failures.append({"dataset": label, "stage": "analyse", "status": st.primary["result"].status})
        say(f"  {label}: {len(st.primary['claims'])} claim(s)")

    stage("challenge")
    for label, st in states.items():
        if st.primary["estimates"] is None:
            continue
        run_entry, result, estimates = skeptic.independent_estimates(
            experiment, skills["independent"], st.data["analysis"]["ref"],
            {"fs": fs, "max_tones": settings.max_tones, "pad": 8, "fmin": settings.fmin_hz}, seed=0, label=label,
        )
        st.independent_run, st.independent = run_entry, estimates
        if estimates is None:
            failures.append({"dataset": label, "stage": "challenge", "status": result.status})
        claims = st.primary["claims"]
        if estimates is not None and claims:
            st.agreement = skeptic.compare(
                experiment, skills["agreement"], st.primary["estimates"], estimates, claims, tolerance=tol,
                min_fraction=settings.agreement_fraction, seed=0, label=label, independent_run=run_entry,
            )
        if claims:
            st.falsification = skeptic.falsify(
                experiment, skills["falsify"], st.data["replicate"]["ref"], claims, fs=fs, alpha=settings.alpha,
                min_fraction=settings.falsification_fraction, seed=0, label=label,
            )
        if estimates is not None:
            st.unclaimed = skeptic.unclaimed_lines(
                experiment, estimates, claims, run_entry, tolerance=tol, claim_fraction=settings.claim_fraction,
                label=label,
            )
        say(f"  {label}: challenged {len(claims)} claim(s); {len(st.unclaimed)} independent-only line(s)")

    stage("reproduce")
    for label, st in states.items():
        if st.primary["result"].ok:
            _, st.reproduced = engineer.reproduce(experiment, st.primary["run"])

    stage("decide")
    for label, st in states.items():
        reproduction = [e.object for e, r in ledger.records("reproduction")
                        if r["original_run"] == st.primary["run"].object]
        for claim_entry, _ in st.primary["claims"]:
            obj = claim_entry.object
            outcome, reasons = decide(st.agreement.get(obj), st.falsification.get(obj), st.reproduced)
            entry = ledger.append("verdict", {
                "experiment": experiment, "target": obj, "verdict": outcome, "reasons": reasons,
                "evidence": _challenges_for(ledger, obj) + reproduction, "rule": VERDICT_RULE,
                "author": author("principal-investigator"),
            })
            st.verdicts[obj] = (outcome, reasons, entry)
        for claim_entry, _ in st.unclaimed:
            reasons = ["found only by the independent estimator; v1 has no third method to adjudicate it"]
            entry = ledger.append("verdict", {
                "experiment": experiment, "target": claim_entry.object, "verdict": "unresolved", "reasons": reasons,
                "evidence": [claim_entry.object], "rule": VERDICT_RULE, "author": author("principal-investigator"),
            })
            st.verdicts[claim_entry.object] = ("unresolved", reasons, entry)

    # Truth is published only after every claim, challenge and verdict exists.
    stage("unseal")
    after = [e.object for e, r in ledger.records()
             if e.kind in {"claim", "challenge", "verdict", "reproduction"} and r.get("experiment") == experiment]
    unseal_entry, value = ledger.unseal(commitment, after=after)
    if value != truth:
        abort("unsealed value differs from the sealed truth")

    stage("score")
    generator_reproduced: dict[str, bool] = {}
    for label, st in states.items():
        for part, item in st.data.items():
            _, match = engineer.reproduce(experiment, item["run"],
                                          inputs={**item["public"], "tones": tones_for(value, label)})
            generator_reproduced[f"{label}-{part}"] = match
    for label, st in states.items():
        tones = tones_for(value, label)
        for method, estimates in (("primary", st.primary["estimates"]), ("independent", st.independent)):
            if estimates is None:
                continue
            run_entry, result = engineer.execute(
                experiment, skills["score"],
                {"estimates": estimates, "truth_hz": [t["frequency_hz"] for t in tones], "tolerance_hz": tol,
                 "amplitudes": [t["amplitude"] for t in tones], "noise_std": st.spec["noise_std"], "n": n, "fs": fs},
                seed=0, purpose=f"score {method} estimates against the unsealed truth ({label})",
            )
            if not result.ok:
                failures.append({"dataset": label, "stage": f"score-{method}", "status": result.status})
                continue
            score = from_jsonable(result.outputs)
            st.scores[method] = score
            per_tone = ", ".join(f"{t['truth_hz']:g} Hz: {t['recovery_rate']:.0%}" for t in score["tones"]) or "none"
            claim = ledger.append("claim", {
                "experiment": experiment,
                "category": "COMPUTED",
                "statement": f"{label} (SNR_ref {st.spec['snr_ref_db']:+g} dB): the {method} method recovered every "
                             f"true tone together in {score['all_recovered_rate']:.0%} of realizations "
                             f"(per tone {per_tone}); {score['false_detections_total']} false detection(s) in "
                             f"{score['realizations_with_false_detection']} realization(s).",
                "label": label,
                "method": method,
                "value": score["all_recovered_rate"],
                "evidence": [run_entry.object, unseal_entry.object],
                "author": author("experimental-engineer"),
            })
            st.score_claims.append(claim)

    summary = _summarise(settings, design, experiment, value, states, generator_reproduced, failures)

    stage("interpret")
    interpretations = []
    for ds in summary["datasets"]:
        st = states[ds["label"]]
        if not st.score_claims:
            continue
        entry = ledger.append("claim", {
            "experiment": experiment,
            "category": "INTERPRETED",
            "statement": ds["interpretation"],
            "label": ds["label"],
            "evidence": [c.object for c in st.score_claims],
            "author": author("principal-investigator"),
        })
        interpretations.append(entry.object)
    answer = ledger.append("claim", {
        "experiment": experiment,
        "category": "INTERPRETED",
        "statement": summary["answer"],
        "evidence": [c.object for st in states.values() for c in st.score_claims],
        "author": author("principal-investigator"),
    })
    summary["answer_claim"] = answer.object

    report_dir = root / "reports" / experiment[7:19]
    if report_dir.exists():
        abort(f"{report_dir} already exists; refusing to overwrite an earlier report")
    figures_dir = report_dir / "figures"
    figures_dir.mkdir(parents=True)
    summary["figures"] = _figures(lab, engineer, experiment, skills, states, summary, figures_dir) if settings.figures else []

    stage("report")
    summary["acceptance"] = evaluate_acceptance(summary, ledger.verify())
    summary["environment"] = environment.describe()
    summary["elapsed_s"] = round(time.monotonic() - clock, 1)
    summary["runs"] = sum(1 for e, r in ledger.records("run") if r["experiment"] == experiment)
    from ..report.markdown import render  # noqa: PLC0415

    summary["ledger_head"] = list(ledger.entries())[-1].hash
    markdown = render(summary)
    report_path = report_dir / "report.md"
    report_path.write_text(markdown, encoding="utf-8", newline="\n")
    findings = [
        {"claims": [f["claim"]], "verdict": f["verdict"], "dataset": ds["label"], "value_hz": f["value_hz"],
         "matches_truth": f["matches_truth"]}
        for ds in summary["datasets"] for f in ds["findings"]
    ]
    report_entry = pi.report(
        experiment,
        findings=findings,
        answer=answer.object,
        interpretations=interpretations,
        acceptance=summary["acceptance"],
        negative_results=summary["negative_results"],
        limitations=LIMITATIONS,
        reproduction={
            "mode": settings.mode,
            "base_seed": design["base_seed"],
            "commands": [
                f"atlas ledger verify {root / 'ledger'}",
                f"atlas experiment run spectral-recovery --mode {settings.mode} --root <new directory>",
            ],
            "note": "fixed mode reproduces every number exactly; blinded mode draws a new truth each time",
        },
        report_object=ledger.put_file(report_path),
        figure_objects={f["name"]: f["objects"] for f in summary["figures"]},
    )
    summary["report_record"] = report_entry.object
    summary["report_path"] = str(report_path)
    summary["ledger_problems"] = ledger.verify()
    if settings.bundle:
        summary["bundle_path"] = str(_bundle(root, report_dir, experiment))
    (report_dir / "summary.json").write_text(_json(summary), encoding="utf-8", newline="\n")
    say(f"report: {report_path}")
    return summary


LIMITATIONS = [
    "Synthetic data only: white Gaussian noise, ideal sampling, stationary tones; nothing here is evidence about "
    "physical or biological signals.",
    "In fixed mode the truth is published in the source code; only blinded mode is blind.",
    "Sealing proves the truth was committed before analysis. The analysis roles are deterministic code that never "
    "reads the vault, and skills run under an audit-hook guard that blocks reads outside their inputs; the guard "
    "is policy enforcement, not an operating-system sandbox.",
    "The roles are scripted policies, not language models; 'multi-agent' here means separated responsibilities "
    "with independent methods, recorded in the ledger.",
    "Approvals and digests are local attestations, not signatures; identity is not verified.",
    "Two estimators and one replicate test are a narrow method family; coloured noise, close tones and "
    "non-stationary signals are untested.",
]


def _nearest(value: float, truth_hz: list[float]) -> float | None:
    return min(truth_hz, key=lambda f: abs(f - value)) if truth_hz else None


def _summarise(settings: Settings, design: dict, experiment: str, truth: dict, states: dict[str, DatasetState],
               generator_reproduced: dict[str, bool], failures: list[dict]) -> dict:
    datasets = []
    negative = []
    for label, st in states.items():
        tones = tones_for(truth, label)
        truth_hz = [t["frequency_hz"] for t in tones]
        findings = []
        for origin, items in (("primary", st.primary["claims"]), ("independent-only", st.unclaimed)):
            for claim_entry, c in items:
                outcome, reasons, verdict_entry = st.verdicts[claim_entry.object]
                nearest = _nearest(c["frequency_hz"], truth_hz)
                findings.append({
                    "claim": claim_entry.object,
                    "verdict_record": verdict_entry.object,
                    "origin": origin,
                    "value_hz": c["frequency_hz"],
                    "spread_hz": c["spread_hz"],
                    "detection_fraction": c["fraction"],
                    "independent": st.agreement.get(claim_entry.object),
                    "falsification": st.falsification.get(claim_entry.object),
                    "reproduced": st.reproduced,
                    "verdict": outcome,
                    "reasons": reasons,
                    "nearest_truth_hz": nearest,
                    "error_hz": None if nearest is None else c["frequency_hz"] - nearest,
                    "matches_truth": nearest is not None and abs(c["frequency_hz"] - nearest) <= settings.tolerance_hz,
                })
        estimates = st.primary["estimates"] or []
        any_detection = sum(1 for row in estimates if row) / len(estimates) if estimates else None
        supported_true = sorted({f["nearest_truth_hz"] for f in findings
                                 if f["verdict"] == "supported" and f["matches_truth"]})
        is_control = label == truth["control_dataset"]
        primary_score = st.scores.get("primary")
        if is_control:
            interpretation = (
                f"{label} was the noise-only control (SNR_ref {st.spec['snr_ref_db']:+g} dB noise): "
                f"{0 if any_detection is None else any_detection:.0%} of realizations contained any primary "
                f"detection and {sum(f['verdict'] == 'supported' for f in findings)} finding(s) were supported."
            )
        else:
            interpretation = (
                f"At SNR_ref {st.spec['snr_ref_db']:+g} dB ({label}) {len(supported_true)} of {len(tones)} true "
                f"tones were recovered and validated (a supported finding within {settings.tolerance_hz} Hz of the "
                f"tone)"
                + (f"; all tones were recovered together in {primary_score['all_recovered_rate']:.0%} of "
                   f"realizations by the primary method." if primary_score else ".")
            )
        if not is_control and primary_score and primary_score["all_recovered_rate"] < 0.5:
            negative.append({
                "dataset": label, "snr_ref_db": st.spec["snr_ref_db"],
                "result": f"recovery failed: all tones recovered together in "
                          f"{primary_score['all_recovered_rate']:.0%} of realizations; {len(supported_true)} of "
                          f"{len(tones)} tones validated",
            })
        for f in findings:
            if f["verdict"] == "supported" and not f["matches_truth"]:
                negative.append({"dataset": label, "snr_ref_db": st.spec["snr_ref_db"],
                                 "result": f"false supported finding at {f['value_hz']:.3f} Hz"})
            if f["verdict"] == "contradicted":
                negative.append({"dataset": label, "snr_ref_db": st.spec["snr_ref_db"],
                                 "result": f"claimed line at {f['value_hz']:.3f} Hz was contradicted: "
                                           f"{'; '.join(f['reasons'])}"})
        datasets.append({
            "label": label,
            "snr_ref_db": st.spec["snr_ref_db"],
            "noise_std": st.spec["noise_std"],
            "is_control": is_control,
            "truth": tones,
            "findings": findings,
            "primary_any_detection_fraction": any_detection,
            "reproduced": st.reproduced,
            "generator_reproduced": {part: generator_reproduced.get(f"{label}-{part}") for part in st.data},
            "scores": st.scores,
            "primary_run": st.primary["run"].object,
            "independent_run": st.independent_run.object if st.independent_run else None,
            "datasets": {part: item["dataset"].object for part, item in st.data.items()},
            "supported_true_tones_hz": supported_true,
            "interpretation": interpretation,
        })
    tone_sets = sorted((d for d in datasets if not d["is_control"]), key=lambda d: -d["snr_ref_db"])
    full = [d["snr_ref_db"] for d in tone_sets if len(d["supported_true_tones_hz"]) == len(d["truth"])]
    partial = [d["snr_ref_db"] for d in tone_sets if 0 < len(d["supported_true_tones_hz"]) < len(d["truth"])]
    none = [d["snr_ref_db"] for d in tone_sets if not d["supported_true_tones_hz"]]
    false_supported = sum(1 for d in datasets for f in d["findings"] if f["verdict"] == "supported"
                          and not f["matches_truth"])

    def levels(values: list[float]) -> str:
        return ", ".join(f"{v:+g} dB" for v in values) or "none"

    answer = (
        f"For this synthetic signal model ({'blinded' if settings.mode == 'blinded' else 'fixed, non-blind'} "
        f"truth), the roles recovered and validated all {len(AMPLITUDES)} tones at SNR_ref {levels(full)}; "
        f"only some tones at {levels(partial)}; none at {levels(none)}. "
        f"{false_supported} supported finding(s) were false. This answers the question for white Gaussian noise "
        f"and well-separated stationary tones only."
    )
    return {
        "protocol": PROTOCOL,
        "experiment": experiment,
        "mode": settings.mode,
        "question": QUESTION,
        "design": design,
        "truth": truth,
        "datasets": datasets,
        "answer": answer,
        "negative_results": negative,
        "failures": failures,
        "limitations": LIMITATIONS,
        "acceptance_criteria": list(ACCEPTANCE),
    }


def evaluate_acceptance(summary: dict, ledger_problems: list[str]) -> list[dict]:
    datasets = summary["datasets"]
    tone_sets = [d for d in datasets if not d["is_control"]]
    top = max(d["snr_ref_db"] for d in tone_sets)
    bottom = min(d["snr_ref_db"] for d in tone_sets)
    results = []

    def add(cid: str, passed: bool, detail: str) -> None:
        text = next(a["text"] for a in ACCEPTANCE if a["id"] == cid)
        results.append({"id": cid, "criterion": text, "passed": bool(passed), "detail": detail})

    details, ok = [], True
    for d in (d for d in tone_sets if d["snr_ref_db"] >= 0):
        score = d["scores"].get("primary")
        for j, tone in enumerate(d["truth"]):
            rate = score["tones"][j]["recovery_rate"] if score else 0.0
            supported = tone["frequency_hz"] in d["supported_true_tones_hz"]
            ok &= rate >= 0.95 and supported
            details.append(f"{d['label']} {tone['frequency_hz']:g} Hz: rate {rate:.0%}, supported {supported}")
    add("A1", ok, "; ".join(details))

    details, ok = [], True
    for d in tone_sets:
        if d["snr_ref_db"] == top and d["scores"].get("primary"):
            for t in d["scores"]["primary"]["tones"]:
                good = t["bias_hz"] is not None and abs(t["bias_hz"]) < 0.05 and t["rmse_hz"] < 0.05
                ok &= good
                details.append(f"{d['label']} {t['truth_hz']:g} Hz: bias {t['bias_hz']:+.4f}, rmse {t['rmse_hz']:.4f}"
                               if t["bias_hz"] is not None else f"{d['label']} {t['truth_hz']:g} Hz: not recovered")
        if d["snr_ref_db"] >= 0:
            score = d["scores"].get("independent")
            for t in (score or {}).get("tones", []):
                ratio = t.get("std_over_crlb")
                ok &= ratio is not None and 0.5 <= ratio <= 2.0
                details.append(f"{d['label']} {t['truth_hz']:g} Hz: std/CRLB "
                               f"{'n/a' if ratio is None else f'{ratio:.2f}'}")
            if score is None:
                ok = False
                details.append(f"{d['label']}: no independent score")
    add("A2", ok, "; ".join(details))

    control = [d for d in datasets if d["is_control"]]
    ok = bool(control) and all(
        (d["primary_any_detection_fraction"] or 0.0) <= 0.15 and not any(f["verdict"] == "supported" for f in d["findings"])
        for d in control
    )
    add("A3", ok, "; ".join(f"{d['label']}: any-detection {d['primary_any_detection_fraction'] or 0.0:.0%}, "
                            f"supported {sum(f['verdict'] == 'supported' for f in d['findings'])}" for d in control))

    lowest = [d for d in tone_sets if d["snr_ref_db"] == bottom]
    listed = {n["dataset"] for n in summary["negative_results"]}
    ok = all(
        d["scores"].get("primary") and d["scores"]["primary"]["all_recovered_rate"] < 0.5 and d["label"] in listed
        and not any(f["verdict"] == "supported" for f in d["findings"])
        for d in lowest
    )
    add("A4", ok, "; ".join(
        f"{d['label']}: all-recovered {d['scores']['primary']['all_recovered_rate']:.0%}, listed {d['label'] in listed}"
        if d["scores"].get("primary") else f"{d['label']}: not scored" for d in lowest))

    supported = [f for d in datasets for f in d["findings"] if f["verdict"] == "supported"]
    false = [f for f in supported if not f["matches_truth"]]
    add("A5", not false, f"{len(supported)} supported finding(s), {len(false)} not within tolerance of a true tone")

    primary_ok = [d["reproduced"] for d in datasets]
    generator_ok = [v for d in datasets for v in d["generator_reproduced"].values()]
    add("A6", all(v is True for v in primary_ok + generator_ok),
        f"primary runs reproduced {sum(v is True for v in primary_ok)}/{len(primary_ok)}; generator runs "
        f"{sum(v is True for v in generator_ok)}/{len(generator_ok)}")

    add("A7", not ledger_problems, "no problems" if not ledger_problems else "; ".join(ledger_problems[:5]))
    return results


def _figures(lab: Lab, engineer: Engineer, experiment: str, skills: dict, states: dict[str, DatasetState],
             summary: dict, out_dir: Path) -> list[dict]:
    figures = []
    tone_sets = sorted((d for d in summary["datasets"] if not d["is_control"]), key=lambda d: -d["snr_ref_db"])
    if not tone_sets:
        return figures
    best = tone_sets[0]
    st = states[best["label"]]
    if st.primary["result"].ok:
        psd_ref = from_jsonable(st.primary["result"].outputs)["mean_psd"]
        staged, files = lab.stage(psd_ref)
        supported = [f["value_hz"] for f in best["findings"] if f["verdict"] == "supported"]
        inputs = {
            "kind": "spectrum",
            "name": "spectrum-" + best["label"].lower(),
            "title": f"{best['label']}: mean Welch PSD, SNR_ref {best['snr_ref_db']:+g} dB",
            "psd": staged[0],
            "markers": [
                {"label": "supported findings", "frequencies_hz": supported, "style": "dashed"},
                {"label": "true tones (unsealed)", "frequencies_hz": [t["frequency_hz"] for t in best["truth"]],
                 "style": "dotted"},
            ],
            "caption": f"Mean of {len(st.primary['estimates'])} Welch PSDs ({best['label']}). Dashed: supported "
                       "findings. Dotted: true tone frequencies, drawn only after unsealing.",
        }
        figures.append(_figure(engineer, experiment, skills["spectrum_figure"], inputs, files, out_dir))
    series = []
    for j in range(len(AMPLITUDES)):
        x, y = [], []
        for d in tone_sets:
            score = d["scores"].get("primary")
            if score:
                x.append(d["snr_ref_db"])
                y.append(score["tones"][j]["recovery_rate"])
        tone = tone_sets[0]["truth"][j]
        series.append({"label": f"{tone['frequency_hz']:g} Hz (A = {tone['amplitude']:g})", "x": x, "y": y})
    inputs = {
        "kind": "lines",
        "name": "recovery-vs-snr",
        "title": "Primary-method recovery rate by tone and SNR_ref",
        "series": series,
        "xlabel": "SNR_ref (dB)",
        "ylabel": "Recovery rate (within tolerance)",
        "caption": "Fraction of realizations in which the primary method reported a line within the tolerance of "
                   "each true tone, scored after unsealing.",
    }
    figures.append(_figure(engineer, experiment, skills["line_figure"], inputs, {}, out_dir))
    return figures


def _figure(engineer: Engineer, experiment: str, skill, inputs: dict, files: dict, out_dir: Path) -> dict:
    entry, result = engineer.execute(experiment, skill, inputs, seed=0, files=files,
                                     purpose=f"render figure {inputs['name']}")
    out = {"name": inputs["name"], "run": entry.object, "status": result.status, "caption": inputs["caption"],
           "files": {}, "objects": {}}
    if result.ok:
        record = result.record()
        for fmt in ("png", "svg"):
            ref = from_jsonable(result.outputs)[fmt]
            target = out_dir / ref["$artifact"]
            shutil.copyfile(result.run_dir / "output" / ref["$artifact"], target)
            out["files"][fmt] = f"figures/{ref['$artifact']}"
            out["objects"][fmt] = record["artifacts"][ref["$artifact"]]["sha256"]
    return out


def _bundle(root: Path, report_dir: Path, experiment: str) -> Path:
    path = report_dir / f"bundle-{experiment[7:19]}.zip"
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as zf:
        for base in (root / "ledger", report_dir):
            for file in sorted(base.rglob("*")):
                if file.is_file() and file != path and file.name != "log.lock":
                    zf.write(file, file.relative_to(root).as_posix())
    return path


def _json(value: Any) -> str:
    import json  # noqa: PLC0415

    from ..canonical import to_jsonable  # noqa: PLC0415

    return json.dumps(to_jsonable(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
