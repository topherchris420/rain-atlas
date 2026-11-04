"""Resonance primitives with explicit units and conservative domain checks.

All arrays use float64 / complex128. These functions do not turn a numerical
quantity into a scientific claim. See docs/RESONANCE.md for assumptions and
failure conditions; tests compare independent formulas and SciPy primitives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import signal

FloatArray = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]


def _array(x: ArrayLike, ndim: int | None = None) -> FloatArray:
    a = np.asarray(x, dtype=np.float64)
    if a.size == 0 or not np.isfinite(a).all() or (ndim is not None and a.ndim != ndim):
        raise ValueError("expected a nonempty finite array with the declared dimensions")
    return a


def _positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class TimeFrequency:
    time_s: FloatArray
    frequency_hz: FloatArray
    power_density: FloatArray
    resolution_hz: float


def stft(x: ArrayLike, fs: float, nperseg: int = 128, hop: int = 64) -> TimeFrequency:
    """One-sided Hann STFT density [input units²/Hz], no padding or detrend.

    Columns are complete frames, timestamps their sample-center times.
    Integrating a column over frequency equals its window-weighted mean square.
    Frequency spacing is fs/nperseg, not an assertion of resolving power.
    """
    a = _array(x, 1)
    _positive(fs, "fs")
    if (
        not isinstance(nperseg, int)
        or not isinstance(hop, int)
        or not 4 <= nperseg <= a.size
        or not 1 <= hop <= nperseg
    ):
        raise ValueError("require 4 <= nperseg <= len(x) and 1 <= hop <= nperseg")
    starts = np.arange(0, a.size - nperseg + 1, hop)
    window = signal.windows.hann(nperseg, sym=False)
    frames = np.lib.stride_tricks.sliding_window_view(a, nperseg)[::hop]
    spectrum = np.fft.rfft(frames * window, axis=-1)
    density = np.abs(spectrum) ** 2 / (fs * np.sum(window**2))
    density[:, 1 : -1 if nperseg % 2 == 0 else None] *= 2
    return TimeFrequency(
        np.asarray((starts + (nperseg - 1) / 2) / fs, dtype=np.float64),
        np.fft.rfftfreq(nperseg, 1 / fs),
        density.T,
        fs / nperseg,
    )


@dataclass(frozen=True)
class WaveletResult:
    coefficients: ComplexArray
    frequency_hz: FloatArray
    edge_valid: NDArray[np.bool_]
    scales_samples: FloatArray


def morlet_cwt(x: ArrayLike, fs: float, frequencies_hz: ArrayLike, omega0: float = 6.0) -> WaveletResult:
    """Corrected complex Morlet correlation, discrete L2 unit-norm kernels.

    Scale = omega0*fs/(2*pi*f). Frequencies are nominal center frequencies;
    coefficients are not a PSD. Zero extension biases edges; mask excludes
    sqrt(2)*scale from each edge (Gaussian e-folding cone). No significance
    inference is supplied. Frequencies above fs/4 are rejected for sampling.
    """
    a, frequencies = _array(x, 1), _array(frequencies_hz, 1)
    _positive(fs, "fs")
    if (
        not math.isfinite(omega0)
        or not 5 <= omega0 <= 12
        or np.any(frequencies <= 0)
        or np.any(frequencies > fs / 4)
    ):
        raise ValueError("require 5 <= omega0 <= 12 and 0 < frequencies <= fs/4")
    scales = omega0 * fs / (2 * np.pi * frequencies)
    if np.any(12 * scales > 1_000_000):
        raise ValueError("wavelet kernel exceeds sample budget")
    rows, masks = [], []
    for scale in scales:
        half = int(math.ceil(6 * scale))
        u = np.arange(-half, half + 1) / scale
        wave = (np.exp(1j * omega0 * u) - np.exp(-(omega0**2) / 2)) * np.exp(-u * u / 2)
        wave /= np.linalg.norm(wave)
        rows.append(signal.fftconvolve(a, np.conj(wave[::-1]), mode="same"))
        distance = np.minimum(np.arange(a.size), np.arange(a.size)[::-1])
        masks.append(distance >= math.ceil(math.sqrt(2) * scale))
    return WaveletResult(np.asarray(rows), frequencies, np.asarray(masks), scales)


def phase_locking(phases_rad: ArrayLike) -> FloatArray:
    """Pairwise temporal PLV [0,1] for (time, channels), radians.

    Constant phase offsets give one, including uncoupled equal-frequency
    oscillators. Finite-sample bias and autocorrelation preclude treating this
    as a p-value, probability, or evidence of causal coupling.
    """
    phases = _array(phases_rad, 2)
    if phases.shape[0] < 2:
        raise ValueError("at least two time samples required")
    z = np.exp(1j * phases)
    return np.clip(np.abs(z.T @ z.conj()) / phases.shape[0], 0, 1)


def order_parameter(phases_rad: ArrayLike) -> FloatArray:
    """Instantaneous Kuramoto order magnitude across the last (oscillator) axis."""
    phases = _array(phases_rad)
    if phases.ndim < 1:
        raise ValueError("oscillator axis required")
    return np.asarray(np.abs(np.mean(np.exp(1j * phases), axis=-1)))


def kuramoto(
    omega_rad_s: ArrayLike,
    theta0_rad: ArrayLike,
    coupling: float,
    *,
    dt: float,
    steps: int,
    diffusion: float = 0.0,
    phase_lag: float = 0.0,
    seed: int = 0,
    increments: ArrayLike | None = None,
) -> FloatArray:
    """Globally coupled phase oscillators; output (..., time, oscillator).

    dtheta_i = [omega_i + K/N sum_{j!=i} sin(theta_j-theta_i-lag)]dt
              + sqrt(2D)dW_i.
    omega and K: rad/s; dt: s; D: rad²/s. Deterministic RK4, stochastic
    Euler-Maruyama. Initial phases may be (N,) or (replicate,N). Angles remain
    unwrapped. Optional Wiener increments [steps,...,N] enable coupled-grid
    convergence checks. No claim of an infinite-population transition.
    """
    omega, state = _array(omega_rad_s, 1), _array(theta0_rad).copy()
    _positive(dt, "dt")
    if state.ndim not in (1, 2) or state.shape[-1] != omega.size or omega.size < 2:
        raise ValueError("initial phases must end in the same >=2 oscillator axis as omega")
    if not isinstance(steps, int) or not 1 <= steps <= 100_000 or (steps + 1) * state.size > 20_000_000:
        raise ValueError("trajectory exceeds the declared sample budget")
    if not all(math.isfinite(v) for v in (coupling, diffusion, phase_lag)) or coupling < 0 or diffusion < 0:
        raise ValueError("K and D must be finite and nonnegative; lag finite")
    if dt * (float(np.max(np.abs(omega))) + coupling) > 0.5:
        raise ValueError("time step too coarse; require dt*(max|omega|+K) <= 0.5")
    noise = None if increments is None else _array(increments)
    if noise is not None and noise.shape != (steps, *state.shape):
        raise ValueError("Wiener increment shape mismatch")
    rng = np.random.default_rng(seed)
    path = np.empty((steps + 1, *state.shape), dtype=float)
    path[0] = state

    def rhs(theta: FloatArray) -> FloatArray:
        z = np.mean(np.exp(1j * theta), axis=-1, keepdims=True)
        return omega + coupling * (
            np.imag(z * np.exp(-1j * (theta + phase_lag))) + np.sin(phase_lag) / omega.size
        )

    for i in range(steps):
        k1 = rhs(state)
        if diffusion:
            dw = rng.normal(size=state.shape) * math.sqrt(dt) if noise is None else noise[i]
            state = state + dt * k1 + math.sqrt(2 * diffusion) * dw
        else:
            k2 = rhs(state + dt * k1 / 2)
            k3 = rhs(state + dt * k2 / 2)
            k4 = rhs(state + dt * k3)
            state = state + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        path[i + 1] = state
    return np.moveaxis(path, 0, -2)


def lms(
    reference: ArrayLike, desired: ArrayLike, taps: int, step_size: float, *, normalized: bool = False
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Causal LMS/NLMS FIR adaptation: y=w·x, e=d-y, w+=mu*e*x.

    Returns prediction, a-priori error and final weights. NLMS divides update
    by squared regressor norm (floor 1e-12); 0<mu<2. Plain LMS stability
    depends on the input covariance and is not guaranteed by this check.
    """
    x, d = _array(reference, 1), _array(desired, 1)
    if x.shape != d.shape or not isinstance(taps, int) or not 1 <= taps <= min(x.size, 1024):
        raise ValueError("equal signal lengths and 1 <= taps <= min(n,1024) required")
    if not math.isfinite(step_size) or not 0 < step_size < 2:
        raise ValueError("step_size must be in (0,2)")
    padded = np.pad(x, (taps - 1, 0))
    w, y, e = np.zeros(taps), np.zeros_like(x), np.zeros_like(x)
    for n in range(x.size):
        u = padded[n : n + taps][::-1]
        y[n] = w @ u
        e[n] = d[n] - y[n]
        w += step_size * e[n] * u / (max(1e-12, float(u @ u)) if normalized else 1)
        if not np.isfinite(w).all() or np.max(np.abs(w)) > 1e12:
            raise ValueError("LMS diverged; reduce step_size or normalize the input")
    return y, e, w


def identify_fir(reference: ArrayLike, response: ArrayLike, taps: int) -> dict:
    """Least-squares causal FIR identification with IID residual covariance.

    Discards startup rows. Requires persistently exciting input and an
    approximately linear time-invariant system. Covariance is conditional on
    a noise-free input; coloured residuals and errors in input invalidate it.
    """
    x, y = _array(reference, 1), _array(response, 1)
    if x.shape != y.shape or not isinstance(taps, int) or not 1 <= taps <= 1024 or x.size < 2 * taps + 1:
        raise ValueError("equal lengths, 1<=taps<=1024 and n>=2*taps+1 required")
    design = np.lib.stride_tricks.sliding_window_view(x, taps)[:, ::-1]
    weights, _, rank, singular = np.linalg.lstsq(design, y[taps - 1 :], rcond=None)
    condition = float(singular[0] / singular[-1]) if singular[-1] else math.inf
    if rank < taps or condition > 1e10:
        raise ValueError(
            "input is not sufficiently exciting; FIR design is rank deficient or ill-conditioned"
        )
    residual = y[taps - 1 :] - design @ weights
    variance = float(residual @ residual / (design.shape[0] - taps))
    cov = variance * np.linalg.inv(design.T @ design)
    return {
        "coefficients": weights.tolist(),
        "covariance": cov.tolist(),
        "residual_variance": variance,
        "condition_number": condition,
        "residuals": residual.tolist(),
        "dof": design.shape[0] - taps,
    }


def plate_mode(
    m: int,
    n: int,
    *,
    a_m: float = 1.0,
    b_m: float = 1.0,
    thickness_m: float = 0.001,
    young_pa: float = 2e11,
    density_kg_m3: float = 7800,
    poisson: float = 0.3,
    grid: int = 65,
) -> dict:
    """Simply supported rectangular Kirchhoff-Love plate eigenmode.

    Displacement is dimensionless sin(m*pi*x/a)sin(n*pi*y/b); amplitude is
    arbitrary. omega=sqrt(B/(rho*h))*[(m*pi/a)^2+(n*pi/b)^2],
    B=E*h^3/[12(1-nu²)]. Linear thin isotropic homogeneous plate, small
    deflection, no damping or granular dynamics. Not a free-edge Chladni plate.
    """
    for v, name in ((a_m, "a"), (b_m, "b"), (thickness_m, "h"), (young_pa, "E"), (density_kg_m3, "rho")):
        _positive(v, name)
    if (
        not isinstance(m, int)
        or not isinstance(n, int)
        or min(m, n) < 1
        or not isinstance(grid, int)
        or not 8 <= grid <= 512
    ):
        raise ValueError("positive integer mode indices and 8<=grid<=512 required")
    if not -1 < poisson < 0.5 or thickness_m / min(a_m, b_m) > 0.05 or grid < 4 * max(m, n) + 1:
        raise ValueError("thin-plate, stable isotropic material and >=4 samples per modal half-wave required")
    x, y = np.linspace(0, a_m, grid), np.linspace(0, b_m, grid)
    shape = np.sin(n * np.pi * y[:, None] / b_m) * np.sin(m * np.pi * x[None, :] / a_m)
    rigidity = young_pa * thickness_m**3 / (12 * (1 - poisson**2))
    omega = math.sqrt(rigidity / (density_kg_m3 * thickness_m)) * (
        (m * np.pi / a_m) ** 2 + (n * np.pi / b_m) ** 2
    )
    return {
        "x_m": x.tolist(),
        "y_m": y.tolist(),
        "displacement": shape.tolist(),
        "frequency_hz": omega / (2 * np.pi),
        "rigidity_nm": rigidity,
    }


def cross_spectrum(channels: ArrayLike, fs: float, nperseg: int = 128) -> dict:
    """Welch cross PSD and magnitude-squared coherence for (time,channel).

    At least three complete overlapping segments are required. CSD uses
    conj(X)*Y, units input²/Hz. Coherence has finite-sample upward bias;
    common drive, leakage and nonstationarity can mimic coupling.
    """
    x = _array(channels, 2)
    _positive(fs, "fs")
    if (
        not isinstance(nperseg, int)
        or nperseg < 8
        or x.shape[0] < 2 * nperseg
        or x.shape[1] < 2
        or x.shape[1] > 32
    ):
        raise ValueError("require nperseg>=8, n>=2*nperseg and 2..32 channels")
    spectra = []
    for i in range(x.shape[1]):
        row = []
        for j in range(x.shape[1]):
            f, p = signal.csd(
                x[:, i],
                x[:, j],
                fs=fs,
                window="hann",
                nperseg=nperseg,
                noverlap=nperseg // 2,
                detrend="constant",
            )
            row.append(p)
        spectra.append(row)
    cs = np.asarray(spectra)
    autos = np.asarray([cs[i, i].real for i in range(x.shape[1])])
    denom = autos[:, None, :] * autos[None, :, :]
    coherence = np.divide(np.abs(cs) ** 2, denom, out=np.zeros_like(denom), where=denom > 0)
    return {
        "frequency_hz": f.tolist(),
        "cross_real": cs.real.tolist(),
        "cross_imag": cs.imag.tolist(),
        "coherence": np.clip(coherence, 0, 1).tolist(),
        "undefined_bins": (denom <= 0).tolist(),
        "segments": 1 + (x.shape[0] - nperseg) // (nperseg - nperseg // 2),
    }
