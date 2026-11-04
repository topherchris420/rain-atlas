"""Transparent classical baselines under deliberately violated assumptions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from ..science.evaluation import match
from ..science.spectral import bic_sinusoid_search, detect_peaks, welch_psd
from ..science.uncertainty import wilson

CASES = ("separated", "close", "white-null", "colored-null", "chirp", "amplitude-modulated")


@dataclass
class _MethodTally:
    """Per-method event counts and samples accumulated over one case's trials."""

    false_trials: int = 0
    miss_trials: int = 0
    all_recovered: int = 0
    error_hz: list[float] = field(default_factory=list)
    runtime_s: list[float] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)


def evaluate(trials: int = 12, seed: int = 20261104) -> dict:
    """Evaluate frequency errors, false detections and disagreement by case.

    Trials use independent seeds; all configurations are declared in the output.
    Wilson intervals measure per-trial event rates, not calibrated confidence.
    Nonstationary chirps have no stationary-tone truth and are not scored as if
    they did. This deliberately measures failures of a white-noise null model.
    """
    if not 3 <= trials <= 200:
        raise ValueError("trials must be between 3 and 200")
    fs = 128.0
    n = 1024
    t = np.arange(n) / fs
    rows = []
    for case_index, case in enumerate(CASES):
        truth = {
            "separated": [12.0, 28.0],
            "close": [12.0, 12.125],
            "white-null": [],
            "colored-null": [],
            "chirp": None,
            "amplitude-modulated": [11.5, 12.0, 12.5],
        }[case]
        metrics = {method: _MethodTally() for method in ("welch", "nls-bic")}
        disagree = 0
        for trial in range(trials):
            rng = np.random.default_rng([seed, case_index, trial])
            noise = rng.normal(size=n) * 0.4
            if case == "colored-null":
                innovations = rng.normal(size=n + 2048)
                x = signal.lfilter([np.sqrt(1 - 0.95**2)], [1, -0.95], innovations)[2048:]
            elif case == "chirp":
                x = signal.chirp(t, 10, t[-1], 30) + noise
            elif case == "amplitude-modulated":
                x = (1 + 0.6 * np.cos(2 * np.pi * 0.5 * t)) * np.cos(2 * np.pi * 12 * t) + noise
            else:
                x = noise + sum(
                    (np.cos(2 * np.pi * f * t + rng.uniform(-np.pi, np.pi)) for f in truth or []),
                    start=np.zeros(n),
                )
            estimates: dict[str, list[float]] = {}
            for method in metrics:
                start = time.perf_counter()
                if method == "welch":
                    peaks, _ = detect_peaks(welch_psd(x, fs, 256), alpha=0.01, fmin=1)
                    est = [p.frequency_hz for p in peaks]
                else:
                    fit, _ = bic_sinusoid_search(x, fs, max_tones=4, fmin=1)
                    est = fit.frequencies_hz.tolist()
                m = metrics[method]
                m.runtime_s.append(time.perf_counter() - start)
                m.counts.append(len(est))
                estimates[method] = est
                if truth is not None:
                    pairs, extra, missing = match(est, truth, 0.08)
                    m.false_trials += bool(extra)
                    m.miss_trials += bool(missing)
                    m.all_recovered += not missing
                    m.error_hz.extend(est[i] - truth[j] for i, j in pairs)
            _, a, b = match(estimates["welch"], estimates["nls-bic"], 0.08)
            disagree += bool(a or b)
        output = {}
        for method, m in metrics.items():
            output[method] = {
                "false_positive_trial_rate": wilson(m.false_trials, trials) if truth is not None else None,
                "false_negative_trial_rate": wilson(m.miss_trials, trials) if truth else None,
                "all_recovered_rate": wilson(m.all_recovered, trials) if truth else None,
                "conditional_matched_rmse_hz": float(np.sqrt(np.mean(np.square(m.error_hz))))
                if m.error_hz
                else None,
                "matched_samples": len(m.error_hz),
                "detection_counts": m.counts,
                "runtime_total_s": sum(m.runtime_s),
                "runtime_median_s": float(np.median(m.runtime_s)),
            }
        rows.append(
            {
                "case": case,
                "truth_hz": truth,
                "truth_status": "unavailable for stationary-tone scoring"
                if truth is None
                else "known synthetic",
                "methods": output,
                "method_disagreement": wilson(disagree, trials),
            }
        )
    return {
        "protocol": "atlas.spectral-stress/v1",
        "trials_per_case": trials,
        "seed": seed,
        "fs": fs,
        "n": n,
        "nperseg": 256,
        "tolerance_hz": 0.08,
        "alpha": 0.01,
        "rows": rows,
        "calibration": "No calibrated posterior; nominal Welch alpha relies on white stationary noise and is stress-tested here.",
        "limitations": [
            "Fixed small synthetic suite, not a population benchmark.",
            "Conditional RMSE excludes misses; detection rates must be considered alongside it.",
            "Wilson intervals use independent trials within each case; no aggregation across heterogeneous cases.",
            "Truth-unavailable chirp cases retain detections without labelling them true or false.",
            "Both baselines are classical methods; no unexecuted external system or LLM comparison.",
            "Process peak memory and environment are recorded by the executor; POSIX memory is an upper bound over host children.",
        ],
    }


def run(inputs: dict, ctx) -> dict:
    result = evaluate(inputs["trials"], ctx.seed)
    return {
        "results": result,
        "artifact": ctx.save_text("spectral-stress.json", __import__("json").dumps(result, indent=2)),
    }
