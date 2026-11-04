"""Spectral estimation, peak detection and sinusoid fitting.

Original implementations on top of numpy/scipy primitives. Where a textbook
result is used it is named in the docstring so it can be checked.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, stats


def hann(n: int) -> np.ndarray:
    """Periodic Hann window (the form used for spectral analysis)."""

    k = np.arange(n)
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * k / n)


@dataclass(frozen=True)
class WelchResult:
    freqs: np.ndarray
    psd: np.ndarray
    segments: int
    nperseg: int
    step: int
    edof: float
    resolution_hz: float
    enbw_hz: float


def welch_psd(x: np.ndarray, fs: float, nperseg: int, overlap: float = 0.5) -> WelchResult:
    """One-sided Welch PSD (density, units²/Hz) with a periodic Hann window.

    Segments are mean-detrended. ``edof`` is the equivalent degrees of freedom
    of each PSD ordinate for white noise, accounting for segment overlap
    (Welch 1967; Percival & Walden 1993, eq. 292b):
    ``edof = 2K / (1 + 2 sum_{j=1}^{K-1} (1 - j/K) rho(j*step))`` with
    ``rho(d) = (sum w_n w_{n+d})^2 / (sum w_n^2)^2``.
    """

    x = np.asarray(x, dtype=float)
    if x.ndim != 1:
        raise ValueError("x must be one-dimensional")
    if not 8 <= nperseg <= x.size:
        raise ValueError("nperseg must be between 8 and len(x)")
    if not 0.0 <= overlap < 1.0:
        raise ValueError("overlap must be in [0, 1)")
    step = max(1, int(round(nperseg * (1.0 - overlap))))
    starts = np.arange(0, x.size - nperseg + 1, step)
    w = hann(nperseg)
    scale = 1.0 / (fs * np.sum(w**2))
    acc = np.zeros(nperseg // 2 + 1)
    for start in starts:
        seg = x[start : start + nperseg]
        spec = np.fft.rfft((seg - seg.mean()) * w)
        acc += np.abs(spec) ** 2
    psd = acc * scale / starts.size
    if nperseg % 2 == 0:
        psd[1:-1] *= 2.0
    else:
        psd[1:] *= 2.0
    k = starts.size
    rho_sum = 0.0
    denom = np.sum(w**2) ** 2
    for j in range(1, k):
        shift = j * step
        if shift >= nperseg:
            break
        rho = np.sum(w[: nperseg - shift] * w[shift:]) ** 2 / denom
        rho_sum += (1.0 - j / k) * rho
    edof = 2.0 * k / (1.0 + 2.0 * rho_sum)
    return WelchResult(
        freqs=np.fft.rfftfreq(nperseg, d=1.0 / fs),
        psd=psd,
        segments=int(k),
        nperseg=int(nperseg),
        step=int(step),
        edof=float(edof),
        resolution_hz=float(fs / nperseg),
        enbw_hz=float(fs * np.sum(w**2) / np.sum(w) ** 2),
    )


@dataclass(frozen=True)
class Peak:
    frequency_hz: float
    bin: int
    psd: float
    snr_db: float
    threshold: float


def detect_peaks(
    welch: WelchResult,
    alpha: float = 0.01,
    min_separation_hz: float | None = None,
    fmin: float = 0.0,
    fmax: float | None = None,
) -> tuple[list[Peak], dict]:
    """Detect spectral lines above a white-noise floor.

    Under the white-noise null each ordinate is ``floor * chi2(edof)/edof``.
    The floor is estimated robustly as ``median(psd) / (median(chi2_edof)/edof)``
    and the per-bin threshold uses a Bonferroni correction over the searched
    bins, so the probability of any false line in pure white noise is about
    ``alpha``. Peak frequencies are refined by parabolic interpolation of the
    log-PSD around the local maximum.
    """

    freqs, psd = welch.freqs, welch.psd
    fmax = freqs[-1] if fmax is None else fmax
    band = np.flatnonzero((freqs > fmin) & (freqs < fmax))
    band = band[(band > 0) & (band < freqs.size - 1)]
    nu = welch.edof
    floor = float(np.median(psd[band]) / (stats.chi2.median(nu) / nu))
    factor = float(stats.chi2.isf(alpha / band.size, nu) / nu)
    threshold = floor * factor
    sep_bins = max(1, int(np.ceil((min_separation_hz or 2.0 * welch.resolution_hz) / welch.resolution_hz)))

    candidates = [i for i in band if psd[i] > threshold and psd[i] >= psd[i - 1] and psd[i] >= psd[i + 1]]
    candidates.sort(key=lambda i: psd[i], reverse=True)
    kept: list[int] = []
    for i in candidates:
        if all(abs(i - j) >= sep_bins for j in kept):
            kept.append(i)
    peaks = []
    for i in sorted(kept):
        a, b, c = np.log(psd[i - 1]), np.log(psd[i]), np.log(psd[i + 1])
        denom = a - 2.0 * b + c
        delta = 0.5 * (a - c) / denom if denom < 0 else 0.0
        delta = float(np.clip(delta, -0.5, 0.5))
        peaks.append(
            Peak(
                frequency_hz=float(freqs[i] + delta * welch.resolution_hz),
                bin=int(i),
                psd=float(psd[i]),
                snr_db=float(10.0 * np.log10(psd[i] / floor)),
                threshold=float(threshold),
            )
        )
    meta = {
        "noise_floor": floor,
        "threshold": threshold,
        "threshold_factor": factor,
        "alpha": alpha,
        "bins_searched": int(band.size),
        "edof": nu,
        "resolution_hz": welch.resolution_hz,
    }
    return peaks, meta


def zero_padded_periodogram(x: np.ndarray, fs: float, pad: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Full-length Hann-windowed periodogram, zero-padded by *pad* for a fine grid."""

    x = np.asarray(x, dtype=float)
    n = x.size
    w = hann(n)
    nfft = int(2 ** np.ceil(np.log2(n * pad)))
    spec = np.abs(np.fft.rfft((x - x.mean()) * w, n=nfft)) ** 2
    return np.fft.rfftfreq(nfft, d=1.0 / fs), spec


def _design(t: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    cols = [np.ones_like(t)]
    for f in freqs:
        arg = 2.0 * np.pi * f * t
        cols += [np.cos(arg), np.sin(arg)]
    return np.column_stack(cols)


@dataclass(frozen=True)
class SinusoidFit:
    frequencies_hz: np.ndarray
    amplitudes: np.ndarray
    phases_rad: np.ndarray
    frequency_se_hz: np.ndarray
    residual_std: float
    rss: float
    bic: float
    converged: bool


def fit_sinusoids(x: np.ndarray, fs: float, initial_hz: np.ndarray) -> SinusoidFit:
    """Nonlinear least-squares fit of ``c + sum a_i cos(2 pi f_i t + phi_i)``.

    Variable projection: frequencies are optimised by ``least_squares``; the
    offset and cosine/sine weights are solved linearly at each step. Standard
    errors come from the Gauss-Newton covariance ``s^2 (J^T J)^{-1}``.
    """

    x = np.asarray(x, dtype=float)
    n = x.size
    t = np.arange(n) / fs
    f0 = np.asarray(initial_hz, dtype=float)
    k = f0.size
    if k == 0:
        rss = float(np.sum((x - x.mean()) ** 2))
        return SinusoidFit(
            np.array([]),
            np.array([]),
            np.array([]),
            np.array([]),
            float(np.sqrt(rss / max(1, n - 1))),
            rss,
            n * np.log(rss / n) + np.log(n),
            True,
        )

    def residual(freqs: np.ndarray) -> np.ndarray:
        design = _design(t, freqs)
        coef, *_ = np.linalg.lstsq(design, x, rcond=None)
        return design @ coef - x

    step = fs / n
    result = optimize.least_squares(
        residual,
        f0,
        bounds=(np.maximum(f0 - 2 * step, 1e-9), np.minimum(f0 + 2 * step, fs / 2)),
        x_scale=step,
        xtol=1e-12,
        ftol=1e-12,
        method="trf",
    )
    freqs = result.x
    design = _design(t, freqs)
    coef, *_ = np.linalg.lstsq(design, x, rcond=None)
    res = design @ coef - x
    rss = float(res @ res)
    dof = max(1, n - (3 * k + 1))
    s2 = rss / dof
    jac = result.jac
    try:
        cov = s2 * np.linalg.inv(jac.T @ jac)
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)
    cos_w, sin_w = coef[1::2], coef[2::2]
    order = np.argsort(freqs)
    return SinusoidFit(
        frequencies_hz=freqs[order],
        amplitudes=np.hypot(cos_w, sin_w)[order],
        phases_rad=np.arctan2(-sin_w, cos_w)[order],
        frequency_se_hz=se[order],
        residual_std=float(np.sqrt(s2)),
        rss=rss,
        bic=float(n * np.log(rss / n) + (3 * k + 1) * np.log(n)),
        converged=bool(result.success),
    )


def bic_sinusoid_search(
    x: np.ndarray, fs: float, max_tones: int = 6, pad: int = 8, fmin: float = 0.0
) -> tuple[SinusoidFit, list[dict]]:
    """Greedy model-order selection by BIC.

    Adds one tone at a time at the largest residual periodogram peak, refits
    all tones jointly, and stops when BIC no longer decreases. Returns the best
    fit and the BIC path (for the record).
    """

    x = np.asarray(x, dtype=float)
    best = fit_sinusoids(x, fs, np.array([]))
    path = [{"tones": 0, "bic": best.bic}]
    current = np.array([])
    for k in range(1, max_tones + 1):
        design = _design(np.arange(x.size) / fs, current)
        coef, *_ = np.linalg.lstsq(design, x, rcond=None)
        resid = x - design @ coef
        freqs, spec = zero_padded_periodogram(resid, fs, pad)
        spec[freqs <= fmin] = 0.0
        for f in current:  # suppress already-fitted tones
            spec[np.abs(freqs - f) < 2.0 * fs / x.size] = 0.0
        candidate = freqs[int(np.argmax(spec))]
        fit = fit_sinusoids(x, fs, np.append(current, candidate))
        path.append({"tones": k, "bic": fit.bic})
        if fit.bic >= best.bic:
            break
        best, current = fit, fit.frequencies_hz
    return best, path


def tone_f_test(x: np.ndarray, fs: float, frequency_hz: float, nuisance_hz: np.ndarray | None = None) -> dict:
    """Regression F-test for a sinusoid at a *given* frequency.

    H0: offset plus nuisance tones; H1 adds cosine and sine at ``frequency_hz``.
    The frequency must be chosen without looking at *x* (for example from an
    independent replicate), otherwise the p-value is optimistic.
    """

    x = np.asarray(x, dtype=float)
    n = x.size
    t = np.arange(n) / fs
    nuisance = np.asarray(nuisance_hz if nuisance_hz is not None else [], dtype=float)
    d0 = _design(t, nuisance)
    d1 = _design(t, np.append(nuisance, frequency_hz))
    r0 = x - d0 @ np.linalg.lstsq(d0, x, rcond=None)[0]
    r1 = x - d1 @ np.linalg.lstsq(d1, x, rcond=None)[0]
    rss0, rss1 = float(r0 @ r0), float(r1 @ r1)
    df1, df2 = 2, n - d1.shape[1]
    f_stat = ((rss0 - rss1) / df1) / (rss1 / df2)
    return {
        "frequency_hz": float(frequency_hz),
        "F": float(f_stat),
        "df1": df1,
        "df2": int(df2),
        "p_value": float(stats.f.sf(f_stat, df1, df2)),
    }


def crlb_frequency_std_hz(amplitude: float, noise_std: float, n: int, fs: float) -> float:
    """Cramer-Rao bound on the std of a single-tone frequency estimate (Hz).

    Rife & Boorstyn (1974): ``var(f/fs) >= 12 / ((2 pi)^2 eta N (N^2 - 1))``
    with ``eta = A^2 / (2 sigma^2)``.
    """

    eta = amplitude**2 / (2.0 * noise_std**2)
    return float(fs * np.sqrt(12.0 / ((2.0 * np.pi) ** 2 * eta * n * (n**2 - 1))))
