"""Matching and scoring of frequency estimates (used by evaluation skills)."""

from __future__ import annotations

import numpy as np


def match(
    a: list[float], b: list[float], tolerance: float
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Greedy one-to-one matching of the closest pairs within *tolerance*."""

    pairs = sorted(
        ((abs(x - y), i, j) for i, x in enumerate(a) for j, y in enumerate(b) if abs(x - y) <= tolerance),
        key=lambda item: item[0],
    )
    used_a: set[int] = set()
    used_b: set[int] = set()
    matched = []
    for _, i, j in pairs:
        if i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
            matched.append((i, j))
    return (
        sorted(matched),
        [i for i in range(len(a)) if i not in used_a],
        [j for j in range(len(b)) if j not in used_b],
    )


def cluster(estimates: list[list[float]], tolerance: float) -> list[dict]:
    """Group per-realization estimates into frequency clusters.

    Returns clusters sorted by frequency with the median frequency, the
    fraction of realizations containing the cluster and the member values.
    """

    values = sorted((f, r) for r, row in enumerate(estimates) for f in row)
    clusters: list[list[tuple[float, int]]] = []
    for f, r in values:
        if clusters and f - np.median([v for v, _ in clusters[-1]]) <= tolerance:
            clusters[-1].append((f, r))
        else:
            clusters.append([(f, r)])
    reps = max(1, len(estimates))
    out = []
    for members in clusters:
        freqs = [v for v, _ in members]
        out.append(
            {
                "frequency_hz": float(np.median(freqs)),
                "fraction": len({r for _, r in members}) / reps,
                "count": len(members),
                "spread_hz": float(np.std(freqs)) if len(freqs) > 1 else 0.0,
            }
        )
    return out


def agreement(a: list[list[float]], b: list[list[float]], tolerance: float, min_fraction: float) -> dict:
    """Compare two independent methods realization by realization."""

    if len(a) != len(b):
        raise ValueError("both methods must report the same number of realizations")
    per_realization = []
    for row_a, row_b in zip(a, b):
        matched, only_a, only_b = match(row_a, row_b, tolerance)
        per_realization.append(
            {
                "matched": [[row_a[i], row_b[j]] for i, j in matched],
                "only_a": [row_a[i] for i in only_a],
                "only_b": [row_b[j] for j in only_b],
            }
        )
    items = []
    for c in cluster(a, tolerance):
        detected = agreed = 0
        diffs = []
        for row_a, row_b in zip(a, b):
            near = [f for f in row_a if abs(f - c["frequency_hz"]) <= tolerance]
            if not near:
                continue
            detected += 1
            fa = min(near, key=lambda f: abs(f - c["frequency_hz"]))
            close = [g for g in row_b if abs(g - fa) <= tolerance]
            if close:
                agreed += 1
                diffs.append(min(close, key=lambda g: abs(g - fa)) - fa)
        fraction = agreed / detected if detected else 0.0
        items.append(
            {
                "frequency_hz": c["frequency_hz"],
                "detected_by_a_fraction": c["fraction"],
                "agreement_fraction": fraction,
                "mean_difference_hz": float(np.mean(diffs)) if diffs else None,
                "max_abs_difference_hz": float(np.max(np.abs(diffs))) if diffs else None,
                "agrees": fraction >= min_fraction,
            }
        )
    return {
        "per_realization": per_realization,
        "items": items,
        "tolerance_hz": tolerance,
        "min_fraction": min_fraction,
    }


def recovery(
    estimates: list[list[float]],
    truth: list[float],
    tolerance: float,
    *,
    amplitudes: list[float] | None = None,
    noise_std: float | None = None,
    n: int | None = None,
    fs: float | None = None,
) -> dict:
    """Score estimates against known frequencies.

    With *amplitudes*, *noise_std*, *n* and *fs* each tone also gets the
    Cramér-Rao bound on the frequency standard deviation and the ratio of the
    observed standard deviation to it (1 means an efficient estimator).
    """

    reps = len(estimates)
    errors: dict[int, list[float]] = {i: [] for i in range(len(truth))}
    false_per_rep = []
    all_found = 0
    for row in estimates:
        matched, only_est, _ = match(row, truth, tolerance)
        for i, j in matched:
            errors[j].append(row[i] - truth[j])
        false_per_rep.append(len(only_est))
        all_found += len(matched) == len(truth)
    bound_inputs: tuple[list[float], float, int, float] | None = None
    if amplitudes is not None and noise_std is not None and n is not None and fs is not None:
        if len(amplitudes) != len(truth):
            raise ValueError("amplitudes must be parallel to truth")
        bound_inputs = (amplitudes, noise_std, n, fs)
    tones = []
    for j, f in enumerate(truth):
        e = np.array(errors[j])
        tone = {
            "truth_hz": f,
            "recovery_rate": len(e) / reps if reps else 0.0,
            "bias_hz": float(e.mean()) if e.size else None,
            "std_hz": float(e.std(ddof=1)) if e.size > 1 else None,
            "rmse_hz": float(np.sqrt(np.mean(e**2))) if e.size else None,
            "max_abs_error_hz": float(np.max(np.abs(e))) if e.size else None,
        }
        if bound_inputs is not None:
            from .spectral import crlb_frequency_std_hz  # noqa: PLC0415

            amps, sigma, n_samples, rate = bound_inputs
            bound = crlb_frequency_std_hz(amps[j], sigma, n_samples, rate) if sigma > 0 else 0.0
            tone["crlb_std_hz"] = float(bound)
            tone["std_over_crlb"] = (
                (tone["std_hz"] / bound) if tone["std_hz"] is not None and bound > 0 else None
            )
        tones.append(tone)
    return {
        "realizations": reps,
        "tolerance_hz": tolerance,
        "tones": tones,
        "all_recovered_rate": all_found / reps if reps else 0.0,
        "false_detections_total": int(sum(false_per_rep)),
        "realizations_with_false_detection": int(sum(1 for count in false_per_rep if count)),
    }
