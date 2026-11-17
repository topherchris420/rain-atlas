"""The preregistered benchmark: does observation-dependent selection help?

Every arm runs the same analysis, critic, stopping rule and challenge
protocol on the same problems; arms differ in how experiments are chosen
(and, for ``legacy-atlas`` and the ablations, in the components named by
:data:`rain_atlas.research.engine.ARMS`). Scores are computed against the
hidden ground truth *after* each mission ends; no mission can see them.

Definitions (per arm and problem)
---------------------------------

* **asserted** -- the arm states a conclusion: for arms with the challenge
  protocol, a *supported* verdict; for ``legacy-atlas`` and
  ``closed-loop-no-challenge``, its own decision rule firing.
* **correct** -- asserted, the stated structure equals the structure active at
  the end of the mission, and the change status is right: no change detected
  when none happened; when one happened, a change detected within one
  experiment of the true point with the true set of changed terms.
* **false conclusion** -- asserted with a wrong structure, a false alarm, or a
  wrong change location or attribution. "No change detected" is not a claim
  that nothing changed: a missed change makes the conclusion incomplete (not
  correct) but not false, and is counted separately.
* **efficiency** -- experiments used if correct, otherwise the full budget
  (censored experiments-to-correct-conclusion; lower is better).
* **change identified** -- at the stop, P(change) >= 0.95, location within one
  experiment and attribution equal to the truth (regardless of assertion).
* **discovery** -- for ``unfamiliar`` problems: correct, so the unanticipated
  term is part of the asserted structure.
* **coverage / regret** -- one-step 90 % predictive interval coverage and mean
  log-predictive regret (nats per row, versus the true model) on six unseen
  conditions per problem, some beyond the approved amplitude range;
  ``linear_regret`` is the same score for a conventional linear least-squares
  model (core terms only) fitted to the same arm's data.
* **confident error / recovery** -- at some step the leading structure had
  posterior >= 0.9 and was wrong; recovered when the mission still did not end
  in a false conclusion.
"""

from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from scipy import stats as sps

from ..canonical import sha256_json
from .charter import default_charter
from .engine import ARMS, ResearchEngine, rounded
from .inference import Fit
from .oscillator import (
    CORE,
    FAMILIES,
    INDEX,
    LIBRARY,
    STEPS,
    Design,
    Problem,
    coefficient_vector,
    make_problem,
    regression_data,
    simulate,
    structure_of,
)
from .stats import PairedBootstrap, combine, proportion_interval, three_valued

ARM_ORDER = (
    "closed-loop",
    "yoked",
    "open-loop-optimal",
    "fixed-sweep",
    "random",
    "legacy-atlas",
    "closed-loop-no-critic",
    "closed-loop-no-challenge",
)
CONVENTIONAL = ("open-loop-optimal", "fixed-sweep", "random", "legacy-atlas")
ALPHA = 0.05
FAMILY_SIZE = 7
BOOTSTRAP_SEED = 20261117
REPRODUCTION_PROBLEMS = 2  # per family, every arm, run twice

HYPOTHESES = {
    "H1": "Observation dependence: on held-out problems the closed loop reaches correct conclusions with fewer "
    "experiments (censored efficiency) than the yoked control, which replays the closed loop's own designs "
    "from a different problem.",
    "H2": "Against conventional selection: the closed loop's censored efficiency is better than each of the "
    "open-loop D-optimal design, the fixed stepped-sine sweep, random designs and the existing ATLAS rule.",
    "H3": "Safety: the closed loop's false-conclusion rate is at most 5 %.",
    "H4": "Change: in hidden-change problems the closed loop identifies the change (location and attribution) "
    "more often than the fixed sweep.",
    "H5": "Unanticipated dynamics: in unfamiliar problems the closed loop reaches the correct conclusion, "
    "including the unanticipated term, more often than the fixed sweep.",
    "H6": "Calibration: the closed loop's one-step 90 % predictive intervals cover between 85 % and 95 % of "
    "held-out rows on unseen conditions.",
    "H7": "Explanatory model: the closed loop's final model has lower held-out predictive regret than a "
    "conventional linear least-squares model fitted to the same data.",
}


@dataclass(frozen=True)
class Task:
    arm: str
    split: str
    family: str
    index: int
    donor: tuple[tuple[float, float, float], ...] = ()
    donor_id: str = ""


def _true_logpdf(problem: Problem, resid: np.ndarray, sd: float) -> np.ndarray:
    if problem.world.noise == "student-t3":
        scale = sd / math.sqrt(3.0)
        return sps.t.logpdf(resid, 3, scale=scale)
    return sps.norm.logpdf(resid, scale=sd)


def heldout_scores(
    problem: Problem, fit: Fit, rows: Sequence[tuple[np.ndarray, np.ndarray]], end: int
) -> dict:
    """Coverage and regret of *fit* and of a linear baseline on unseen conditions."""

    truth = problem.truth(end)
    theta = coefficient_vector(truth)
    designs = problem.heldout_designs
    rng = np.random.default_rng([problem.world.seed, 6007])
    eps = rng.standard_normal((len(designs), STEPS))
    if problem.world.noise == "student-t3":
        eps = rng.standard_t(3, size=(len(designs), STEPS)) / math.sqrt(3.0)
    x, v, u = simulate(
        np.tile(theta, (len(designs), 1)),
        np.array([d.amplitude for d in designs]),
        np.array([d.frequency for d in designs]),
        np.array([d.x0 for d in designs]),
        np.full(len(designs), problem.world.noise_scale),
        eps,
    )
    phi, y = regression_data(x, v, u)
    phi = phi.reshape(-1, len(LIBRARY))
    y = y.reshape(-1)
    noise_sd = problem.world.noise_scale / math.sqrt(0.05)
    true_lp = _true_logpdf(problem, y - phi @ theta, noise_sd)
    mean, scale, dof = fit.predictive(phi)
    lp = sps.t.logpdf(y, dof, loc=mean, scale=scale)
    lo, hi = sps.t.interval(0.9, dof, loc=mean, scale=scale)
    coverage = float(np.mean((y >= lo) & (y <= hi)))
    # Conventional baseline: linear least squares on the core terms over all of the arm's data.
    cols = [INDEX[t] for t in CORE]
    X = np.vstack([r[0][:, cols] for r in rows]) if rows else np.zeros((1, len(cols)))
    Y = np.concatenate([r[1] for r in rows]) if rows else np.zeros(1)
    beta = np.linalg.lstsq(X, Y, rcond=None)[0]
    resid_sd = float(np.sqrt(np.mean((Y - X @ beta) ** 2))) or 1.0
    lin_lp = sps.norm.logpdf(y, loc=phi[:, cols] @ beta, scale=resid_sd)
    return {
        "coverage90": coverage,
        "regret": float(np.mean(true_lp - lp)),
        "linear_regret": float(np.mean(true_lp - lin_lp)),
    }


def changed_terms(problem: Problem) -> tuple[str, ...]:
    if problem.world.change_at is None or not problem.world.changed_coefficients:
        return ()
    pre, post = problem.world.coefficients, problem.world.changed_coefficients
    return tuple(t for t in LIBRARY if abs(pre.get(t, 0.0) - post.get(t, 0.0)) > 1e-12)


def score(problem: Problem, arm: str, result: Any, engine: ResearchEngine, budget: int) -> dict:
    c = result.conclusion
    end = result.experiments - 1
    truth_now = structure_of(problem.truth(end))
    change_at = problem.world.change_at
    change_happened = change_at is not None and change_at <= end
    true_changed = set(changed_terms(problem))
    claimed = c.get("change")
    structure_ok = tuple(c["structure"]) == truth_now

    def change_ok(claim: dict | None) -> bool:
        if not change_happened:
            return claim is None
        return (
            claim is not None
            and abs(claim["change_at"] - change_at) <= 1
            and set(claim["changed"]) == true_changed
        )

    asserted = bool(c["asserted"])
    # "No change detected" is not a claim that nothing changed: a missed change
    # leaves the conclusion incomplete (not correct), while a false alarm or a
    # wrong location/attribution is a false conclusion.
    change_claim_wrong = claimed is not None and not change_ok(claimed)
    correct = asserted and structure_ok and change_ok(claimed)
    false = asserted and (not structure_ok or change_claim_wrong)
    detection = c["p_change"] >= 0.95 and claimed is not None
    identified = change_happened and detection and change_ok(claimed)
    confident_error = False
    for e in result.events:
        if e["event"] == "analysis" and e["after_experiments"] > 0:
            d = e["decision"]
            truth_then = structure_of(problem.truth(e["after_experiments"] - 1))
            if d["p_structure"] >= 0.9 and tuple(d["structure"]) != truth_then:
                confident_error = True
                break
    held = heldout_scores(
        problem,
        result.final_fit,
        [r for r, o in zip(engine.rows, engine.observations) if o.status == "ok"],
        end,
    )
    unanticipated = [t for t in truth_now if t not in ("x", "v", "u", "x^3", "1")]
    return rounded(
        {
            "problem": problem.problem_id,
            "family": problem.family,
            "split": problem.split,
            "variant": problem.variant,
            "arm": arm,
            "experiments": result.experiments,
            "stop": result.stop_reason,
            "asserted": asserted,
            "correct": correct,
            "false": false,
            "missed_change": asserted and change_happened and claimed is None,
            "unresolved": not asserted,
            "structure_ok": structure_ok,
            "efficiency": result.experiments if correct else budget,
            "change_happened": change_happened,
            "change_detected": bool(detection),
            "change_identified": bool(identified),
            "false_alarm": (not change_happened) and bool(detection),
            "discovery": bool(correct and unanticipated),
            "unanticipated": unanticipated,
            "p_structure": c["p_structure"],
            "confident_error": confident_error,
            "recovered": confident_error and not false,
            "memory": problem.memory is not None,
            "memory_stale": problem.memory is not None and "stale" in problem.variant,
            "memory_state": result.memory_state,
            "wall_s": result.wall_s,
            "hypotheses_evaluated": result.counters["hypotheses_evaluated"],
            "digest": result.digest,
            "designs": [[d.amplitude, d.frequency, d.x0] for d in result.designs],
            **held,
        }
    )


def run_task(task: Task, charter: dict | None = None) -> dict:
    charter = charter or default_charter()
    problem = make_problem(task.split, task.family, task.index)
    donor = [Design(*d) for d in task.donor] if task.donor else None
    engine = ResearchEngine(
        charter,
        problem.instrument(),
        mission_id=problem.problem_id,
        seed=problem.world.seed,
        arm=task.arm,
        memory=problem.memory,
        donor=donor,
        donor_id=task.donor_id,
    )
    result = engine.run()
    return score(problem, task.arm, result, engine, int(charter["budgets"]["experiments_per_mission"]))


def _run_many(tasks: list[Task], workers: int, charter: dict, sink: Callable[[dict], None]) -> list[dict]:
    if workers <= 1:
        out = []
        for t in tasks:
            r = run_task(t, charter)
            sink(r)
            out.append(r)
        return out
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_task, t, charter) for t in tasks]
        out = []
        for f in futures:
            r = f.result()
            sink(r)
            out.append(r)
        return out


def config_digest(split: str, per_family: int, arms: Sequence[str], charter: dict) -> str:
    return sha256_json(
        {
            "split": split,
            "per_family": per_family,
            "arms": list(arms),
            "charter": charter,
            "arm_configs": {a: ARMS[a].to_dict() for a in arms},
        }
    )


def run_benchmark(
    split: str,
    per_family: int,
    *,
    arms: Sequence[str] = ARM_ORDER,
    workers: int | None = None,
    out: Path | None = None,
    charter: dict | None = None,
    families: Sequence[str] = FAMILIES,
    progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Run (or resume) the benchmark; one fsynced JSON line per (arm, problem)."""

    charter = charter or default_charter()
    workers = workers if workers is not None else max(1, min(4, os.cpu_count() or 1))
    digest = config_digest(split, per_family, arms, charter)
    done: dict[tuple[str, str], dict] = {}
    path = None
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "results.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn final line from a crash; the task is simply rerun
                if row.get("config") == digest:
                    done[(row["arm"], row["problem"])] = row

    def sink(row: dict) -> None:
        row["config"] = digest
        if path is not None:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        if progress:
            progress(
                f"{row['arm']:<26} {row['problem']:<30} n={row['experiments']:>2} "
                f"{'correct' if row['correct'] else 'FALSE' if row['false'] else 'unresolved'}"
            )

    first = [a for a in arms if a != "yoked"]
    tasks = [
        Task(a, split, f, i)
        for a in first
        for f in families
        for i in range(per_family)
        if (a, f"{split}/{f}/{i:03d}") not in done
    ]
    results = list(done.values())
    results += _run_many(tasks, workers, charter, sink)
    if "yoked" in arms:
        if "closed-loop" not in arms:
            raise ValueError("the yoked control needs the closed-loop arm")
        by_problem = {r["problem"]: r for r in results if r["arm"] == "closed-loop"}
        yoked = []
        for f in families:
            for i in range(per_family):
                pid = f"{split}/{f}/{i:03d}"
                if ("yoked", pid) in done:
                    continue
                donor_id = f"{split}/{f}/{(i + 1) % per_family:03d}" if per_family > 1 else pid
                donor = tuple(tuple(d) for d in by_problem[donor_id]["designs"])
                yoked.append(Task("yoked", split, f, i, donor, donor_id))
        results += _run_many(yoked, workers, charter, sink)
    order = {a: k for k, a in enumerate(ARM_ORDER)}
    results.sort(key=lambda r: (order.get(r["arm"], 99), r["problem"]))
    return results


def _table(results: list[dict], arm: str, key: str) -> np.ndarray:
    rows = sorted((r for r in results if r["arm"] == arm), key=lambda r: r["problem"])
    return np.array([float(r[key]) for r in rows])


def summarize(results: list[dict], arms: Sequence[str] = ARM_ORDER) -> dict:
    """Per-arm descriptive statistics with 95 % intervals."""

    arms = [a for a in arms if any(r["arm"] == a for r in results)]
    ref = sorted((r for r in results if r["arm"] == arms[0]), key=lambda r: r["problem"])
    boot = PairedBootstrap([r["family"] for r in ref], seed=BOOTSTRAP_SEED, resamples=4000)
    out: dict[str, Any] = {}
    for arm in arms:
        rows = sorted((r for r in results if r["arm"] == arm), key=lambda r: r["problem"])
        entry: dict[str, Any] = {"missions": len(rows)}
        for key in ("efficiency", "experiments", "coverage90", "regret", "linear_regret", "wall_s"):
            v = np.array([float(r[key]) for r in rows])
            entry[key] = {"mean": float(v.mean()), "interval": list(boot.interval(v, 0.05))}
        for key in ("correct", "false", "unresolved", "confident_error", "recovered"):
            v = np.array([float(r[key]) for r in rows])
            entry[key] = {
                "rate": float(v.mean()),
                "count": int(v.sum()),
                "interval": list(proportion_interval(boot, v, 0.05)),
            }
        by_family: dict[str, Any] = {}
        for fam in sorted({r["family"] for r in rows}):
            fr = [r for r in rows if r["family"] == fam]
            by_family[fam] = {
                "missions": len(fr),
                "efficiency": float(np.mean([r["efficiency"] for r in fr])),
                "experiments": float(np.mean([r["experiments"] for r in fr])),
                "correct": float(np.mean([r["correct"] for r in fr])),
                "false": float(np.mean([r["false"] for r in fr])),
                "unresolved": float(np.mean([r["unresolved"] for r in fr])),
                "change_identified": float(np.mean([r["change_identified"] for r in fr])),
                "false_alarm": float(np.mean([r["false_alarm"] for r in fr])),
                "discovery": float(np.mean([r["discovery"] for r in fr])),
            }
        entry["by_family"] = by_family
        nonchange = [r for r in rows if not r["change_happened"]]
        entry["false_alarm"] = {
            "rate": float(np.mean([r["false_alarm"] for r in nonchange])) if nonchange else 0.0,
            "count": int(sum(r["false_alarm"] for r in nonchange)),
            "of": len(nonchange),
        }
        stale = [r for r in rows if r["memory_stale"]]
        good = [r for r in rows if r["memory"] and not r["memory_stale"]]
        entry["memory"] = {
            "stale_quarantined": f"{sum(r['memory_state'] == 'quarantined' for r in stale)}/{len(stale)}",
            "correct_kept": f"{sum(r['memory_state'] in ('confirmed', 'active') for r in good)}/{len(good)}",
        }
        brier = [(r["p_structure"] - float(r["structure_ok"])) ** 2 for r in rows]
        entry["brier_structure"] = float(np.mean(brier))
        out[arm] = entry
    return out


def evaluate(results: list[dict]) -> dict:
    """The seven preregistered hypotheses, Bonferroni-adjusted (alpha = 0.05 / 7)."""

    alpha = ALPHA / FAMILY_SIZE
    ref = sorted((r for r in results if r["arm"] == "closed-loop"), key=lambda r: r["problem"])
    families = [r["family"] for r in ref]
    boot = PairedBootstrap(families, seed=BOOTSTRAP_SEED, resamples=10_000)
    cl = _table(results, "closed-loop", "efficiency")
    out: dict[str, Any] = {"alpha_family": ALPHA, "alpha_each": alpha}

    def diff(arm: str, key: str, mask: np.ndarray | None = None) -> dict:
        a, b = _table(results, "closed-loop", key), _table(results, arm, key)
        d = a - b
        if mask is not None:
            sub = PairedBootstrap(
                [f for f, m in zip(families, mask) if m], seed=BOOTSTRAP_SEED, resamples=10_000
            )
            d = d[mask]
            interval = sub.interval(d, alpha)
        else:
            interval = boot.interval(d, alpha)
        return {"versus": arm, "difference": float(d.mean()), "interval": list(interval), "n": int(len(d))}

    h1 = diff("yoked", "efficiency")
    h1["verdict"] = three_valued(tuple(h1["interval"]), lambda v: v < 0)
    out["H1"] = h1
    parts = [diff(a, "efficiency") for a in CONVENTIONAL]
    for p in parts:
        p["verdict"] = three_valued(tuple(p["interval"]), lambda v: v < 0)
    out["H2"] = {"parts": parts, "verdict": combine([p["verdict"] for p in parts])}
    false = _table(results, "closed-loop", "false")
    interval = proportion_interval(boot, false, alpha)
    out["H3"] = {
        "rate": float(false.mean()),
        "count": int(false.sum()),
        "interval": list(interval),
        "verdict": three_valued(interval, lambda v: v <= 0.05),
    }
    change = np.array([f == "hidden-change" for f in families])
    h4 = diff("fixed-sweep", "change_identified", change)
    h4["closed_loop_rate"] = float(_table(results, "closed-loop", "change_identified")[change].mean())
    h4["fixed_sweep_rate"] = float(_table(results, "fixed-sweep", "change_identified")[change].mean())
    h4["verdict"] = three_valued(tuple(h4["interval"]), lambda v: v > 0)
    out["H4"] = h4
    unfamiliar = np.array([f == "unfamiliar" for f in families])
    h5 = diff("fixed-sweep", "discovery", unfamiliar)
    h5["closed_loop_rate"] = float(_table(results, "closed-loop", "discovery")[unfamiliar].mean())
    h5["fixed_sweep_rate"] = float(_table(results, "fixed-sweep", "discovery")[unfamiliar].mean())
    h5["verdict"] = three_valued(tuple(h5["interval"]), lambda v: v > 0)
    out["H5"] = h5
    cov = _table(results, "closed-loop", "coverage90")
    lo, hi = boot.interval(cov, alpha)
    verdict = (
        "supported"
        if 0.85 <= lo and hi <= 0.95
        else "contradicted"
        if hi < 0.85 or lo > 0.95
        else "unresolved"
    )
    out["H6"] = {"mean": float(cov.mean()), "interval": [lo, hi], "verdict": verdict}
    reg = _table(results, "closed-loop", "regret") - _table(results, "closed-loop", "linear_regret")
    interval = boot.interval(reg, alpha)
    out["H7"] = {
        "difference": float(reg.mean()),
        "interval": list(interval),
        "closed_loop_regret": float(cl.size and _table(results, "closed-loop", "regret").mean()),
        "linear_regret": float(_table(results, "closed-loop", "linear_regret").mean()),
        "verdict": three_valued(interval, lambda v: v < 0),
    }
    return out


def reproduction_check(
    split: str,
    per_family: int,
    results: list[dict],
    charter: dict | None = None,
    arms: Sequence[str] = ARM_ORDER,
    workers: int = 1,
) -> dict:
    """Rerun the first problems of every family and arm; mission digests must match exactly."""

    charter = charter or default_charter()
    by_key = {(r["arm"], r["problem"]): r for r in results}
    tasks = []
    for arm in arms:
        for fam in FAMILIES:
            for i in range(min(REPRODUCTION_PROBLEMS, per_family)):
                pid = f"{split}/{fam}/{i:03d}"
                original = by_key.get((arm, pid))
                if original is None:
                    continue
                donor = ()
                donor_id = ""
                if arm == "yoked":
                    donor_id = f"{split}/{fam}/{(i + 1) % per_family:03d}" if per_family > 1 else pid
                    donor = tuple(tuple(d) for d in by_key[("closed-loop", donor_id)]["designs"])
                tasks.append((Task(arm, split, fam, i, donor, donor_id), original["digest"]))
    started = time.perf_counter()
    reruns = _run_many([t for t, _ in tasks], workers, charter, lambda r: None)
    matches = [r["digest"] == d for r, (_, d) in zip(reruns, tasks)]
    return {
        "missions": len(tasks),
        "identical": int(sum(matches)),
        "all_identical": all(matches),
        "wall_s": time.perf_counter() - started,
    }
