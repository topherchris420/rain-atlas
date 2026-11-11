"""A held-out calibration benchmark for searches across a frequency band."""

from __future__ import annotations

import json

import numpy as np
from scipy import signal

from ..science.spectral import detect_peaks, hann, welch_psd
from ..science.uncertainty import wilson

PROTOCOL = "atlas.spectral-calibration/v1"
SEED = 20261110
DEFAULT_TRIALS = 128
MAX_TRIALS = 1024
ALPHA = 0.05
FS = 128
SAMPLES = 1024
SEGMENT = 256
OVERLAP = SEGMENT // 2
FMIN = 1.0
FMAX = FS / 2
TONE_HZ = 12.25
TOLERANCE_HZ = 0.5
AR1_RHO = 0.95
OSCILLATORY_RADIUS = 0.97
TEMPLATE_WINDOWS = 32
CALIBRATION_WINDOWS = 99
WINDOW = hann(SEGMENT)
FREQUENCIES = np.fft.rfftfreq(SEGMENT, 1 / FS)
BAND = (FREQUENCIES > FMIN) & (FREQUENCIES < FMAX)
MODELS = ("white", "ar1")
METHODS = ("welch-white-threshold", "white-reference", "ar1-reference", "reference-panel")
CASES = (
    ("white-null", "white", 0.0),
    ("ar1-null", "ar1", 0.0),
    ("oscillatory-null", "oscillatory", 0.0),
    ("ar1-weak-tone", "ar1", 0.12),
    ("ar1-intermediate-tone", "ar1", 0.25),
    ("ar1-strong-tone", "ar1", 0.75),
)
LIMITATIONS = [
    "The 5% bound concerns any declaration in one all-noise window under an exchangeable reference model.",
    "The bound is marginal over the rank reference bank and conditional on the independent template.",
    "The benchmark redraws references per trial. Reusing one bank does not justify these binomial intervals.",
    "A reference panel can lose power, and the oscillatory null deliberately falls outside the panel.",
    "Target-band declarations measure chance hits under the null and localization for one injected frequency.",
    "Overlapping windows, repeated scans, hardware noise and other distribution shifts require separate validation.",
]


def design(trials: int, seed: int) -> dict:
    if not 3 <= trials <= MAX_TRIALS:
        raise ValueError(f"trials must be between 3 and {MAX_TRIALS} for spectral calibration")
    return {
        "protocol": PROTOCOL,
        "trials_per_case": trials,
        "seed": seed,
        "alpha": ALPHA,
        "sample_rate_hz": FS,
        "window_samples": SAMPLES,
        "welch_segment_samples": SEGMENT,
        "welch_overlap_samples": OVERLAP,
        "search_band_hz_exclusive": [FMIN, FMAX],
        "target_frequency_hz": TONE_HZ,
        "localization_tolerance_hz": TOLERANCE_HZ,
        "template_windows_per_model_per_trial": TEMPLATE_WINDOWS,
        "calibration_windows_per_model_per_trial": CALIBRATION_WINDOWS,
        "noise_models": [
            {"name": "white", "marginal_sd": 1},
            {"name": "ar1", "rho": AR1_RHO, "marginal_sd": 1},
            {
                "name": "oscillatory",
                "pole_radius": OSCILLATORY_RADIUS,
                "center_hz": TONE_HZ,
                "marginal_sd": 1,
            },
        ],
        "reference_models": list(MODELS),
        "methods": list(METHODS),
        "cases": [
            {
                "name": name,
                "noise": noise,
                "tone_hz": TONE_HZ if amplitude else None,
                "tone_amplitude": amplitude,
            }
            for name, noise, amplitude in CASES
        ],
    }


def max_rank_pvalues(scores: np.ndarray, null_maxima: np.ndarray) -> np.ndarray:
    """Compare each bin with held-out whole-band maxima, counting ties against rejection."""
    scores = np.asarray(scores, dtype=float)
    maxima = np.asarray(null_maxima, dtype=float)
    if scores.ndim != 1 or maxima.ndim != 1 or not scores.size or not maxima.size:
        raise ValueError("scores and null maxima must be nonempty vectors")
    if not np.isfinite(scores).all() or not np.isfinite(maxima).all():
        raise ValueError("scores and null maxima must be finite")
    at_least_as_large = maxima.size - np.searchsorted(np.sort(maxima), scores, side="left")
    return (1 + at_least_as_large) / (1 + maxima.size)


def _noise(rng: np.random.Generator, model: str, windows: int) -> np.ndarray:
    innovations = rng.normal(size=(windows, SAMPLES))
    if model == "white":
        return innovations
    initial = rng.normal(size=(windows, 1))
    if model == "ar1":
        pole = AR1_RHO
    elif model == "oscillatory":
        pole = OSCILLATORY_RADIUS * np.exp(2j * np.pi * TONE_HZ / FS)
        innovations = innovations + 1j * rng.normal(size=innovations.shape)
        initial = initial + 1j * rng.normal(size=initial.shape)
    else:
        raise ValueError(f"unknown noise model: {model}")
    # Draw the state immediately preceding sample zero from its stationary law.
    samples, _ = signal.lfilter([np.sqrt(1 - abs(pole) ** 2)], [1, -pole], innovations, zi=pole * initial)
    return samples.real


def _band_psd(windows: np.ndarray) -> np.ndarray:
    _, psd = signal.welch(windows, fs=FS, window=WINDOW, noverlap=OVERLAP, detrend="constant")
    return psd[..., BAND]


def _reference_pvalues(rng: np.random.Generator, model: str, test_psd: np.ndarray) -> np.ndarray:
    # Use disjoint blank windows to estimate the shape and to calibrate the scan.
    psd = _band_psd(_noise(rng, model, TEMPLATE_WINDOWS + CALIBRATION_WINDOWS))
    template = psd[:TEMPLATE_WINDOWS].mean(axis=0)
    null_maxima = (psd[TEMPLATE_WINDOWS:] / template).max(axis=-1)
    return max_rank_pvalues(test_psd / template, null_maxima)


def _trial(
    seed: int, case_index: int, trial_index: int, noise: str, amplitude: float
) -> tuple[np.ndarray, ...]:
    test_rng, white_rng, ar1_rng = (
        np.random.default_rng(s) for s in np.random.SeedSequence([seed, case_index, trial_index]).spawn(3)
    )
    x = _noise(test_rng, noise, 1)[0]
    if amplitude:
        phase = test_rng.uniform(-np.pi, np.pi)
        x += amplitude * np.cos(2 * np.pi * TONE_HZ * np.arange(SAMPLES) / FS + phase)
    baseline, _ = detect_peaks(welch_psd(x, FS, SEGMENT), alpha=ALPHA, fmin=FMIN, fmax=FMAX)
    test_psd = _band_psd(x[np.newaxis, :])[0]
    white = _reference_pvalues(white_rng, "white", test_psd)
    ar1 = _reference_pvalues(ar1_rng, "ar1", test_psd)
    frequencies = FREQUENCIES[BAND]
    return (
        np.array([peak.frequency_hz for peak in baseline]),
        frequencies[white <= ALPHA],
        frequencies[ar1 <= ALPHA],
        frequencies[np.maximum(white, ar1) <= ALPHA],
    )


def evaluate(trials: int = DEFAULT_TRIALS, seed: int = SEED) -> dict:
    """Measure false alarms and localization with independent windows in every trial."""
    configuration = design(trials, seed)
    rows = []
    for case_index, (case, noise, amplitude) in enumerate(CASES):
        detections = dict.fromkeys(METHODS, 0)
        target_hits = dict.fromkeys(METHODS, 0)
        for trial_index in range(trials):
            for method, frequencies in zip(METHODS, _trial(seed, case_index, trial_index, noise, amplitude)):
                detections[method] += int(frequencies.size > 0)
                target_hits[method] += int(np.any(np.abs(frequencies - TONE_HZ) <= TOLERANCE_HZ))
        rows.append(
            {
                "case": case,
                "methods": {
                    method: {
                        "any_detection_rate": wilson(detections[method], trials),
                        "target_band_detection_rate": wilson(target_hits[method], trials),
                    }
                    for method in METHODS
                },
            }
        )
    return {"design": configuration, "rows": rows, "limitations": LIMITATIONS}


def run(inputs: dict, ctx) -> dict:
    results = evaluate(inputs["trials"], ctx.seed)
    return {
        "results": results,
        "artifact": ctx.save_text("spectral-calibration.json", json.dumps(results, indent=2) + "\n"),
    }
