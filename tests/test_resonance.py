import numpy as np
import pytest
from scipy import signal
from scipy.integrate import solve_ivp

from rain_atlas.science.resonance import (
    cross_spectrum,
    identify_fir,
    kuramoto,
    lms,
    morlet_cwt,
    order_parameter,
    phase_locking,
    plate_mode,
    stft,
)


@pytest.mark.parametrize("nperseg", [63, 64])
def test_stft_parseval_and_independent_scipy(nperseg):
    x = np.random.default_rng(4).normal(size=512)
    actual = stft(x, 128, nperseg, 20)
    f, _, psd = signal.spectrogram(
        x, 128, window="hann", nperseg=nperseg, noverlap=nperseg - 20, detrend=False, scaling="density"
    )
    np.testing.assert_allclose(actual.power_density, psd, atol=1e-15)
    np.testing.assert_allclose(actual.frequency_hz, f)
    w = signal.windows.hann(nperseg, sym=False)
    frames = np.lib.stride_tricks.sliding_window_view(x, nperseg)[::20]
    np.testing.assert_allclose(
        actual.power_density.sum(axis=0) * 128 / nperseg,
        np.sum((frames * w) ** 2, axis=1) / np.sum(w * w),
        atol=1e-14,
    )


def test_time_frequency_tracks_chirp_and_null():
    fs = 256
    t = np.arange(2048) / fs
    x = signal.chirp(t, f0=10, t1=t[-1], f1=50)
    tf = stft(x, fs, 128, 32)
    ridge = tf.frequency_hz[np.argmax(tf.power_density, axis=0)]
    assert np.max(np.abs(ridge - (10 + 40 * tf.time_s / t[-1]))) < 2
    assert np.all(stft(np.zeros(512), 128).power_density == 0)


def test_wavelet_tone_edge_mask_and_translation():
    fs = 128
    t = np.arange(2048) / fs
    x = np.cos(2 * np.pi * 12 * t)
    result = morlet_cwt(x, fs, [6, 12, 24])
    power = [np.mean(np.abs(c[m]) ** 2) for c, m in zip(result.coefficients, result.edge_valid)]
    assert np.argmax(power) == 1
    assert not result.edge_valid[:, 0].any() and result.edge_valid[:, 1024].all()
    shifted = morlet_cwt(np.roll(x, 20), fs, [12])
    np.testing.assert_allclose(
        np.abs(shifted.coefficients[0, 200:-200]), np.abs(result.coefficients[1, 200:-200]), atol=1e-7
    )
    assert np.max(np.abs(morlet_cwt(np.zeros(256), fs, [12]).coefficients)) == 0


def test_plv_analytical_positive_negative_and_false_causal_inference():
    theta = np.arange(1024) * 2 * np.pi / 1024
    np.testing.assert_allclose(phase_locking(np.column_stack([theta, theta + 1])), 1, atol=1e-14)
    assert phase_locking(np.column_stack([theta, 2 * theta]))[0, 1] < 1e-14
    # PLV=1 does not imply coupling: equal frequency but offset, K=0.
    path = kuramoto([1, 1], [0, 1], 0, dt=0.02, steps=500)
    assert phase_locking(path)[0, 1] > 1 - 1e-12
    np.testing.assert_allclose(order_parameter([[0, np.pi]]), 0, atol=1e-15)


def test_kuramoto_uncoupled_exact_and_pair_locked_reference():
    t = np.arange(1001) * 0.02
    path = kuramoto([-0.5, 0.5], [0.2, 0.7], 0, dt=0.02, steps=1000)
    np.testing.assert_allclose(path, np.array([0.2, 0.7]) + t[:, None] * [-0.5, 0.5], atol=2e-12)
    coupled = kuramoto([-0.5, 0.5], [0, 0.1], 2, dt=0.02, steps=2000)
    assert abs((coupled[-1, 1] - coupled[-1, 0]) - np.arcsin(0.5)) < 1e-10
    assert abs(order_parameter(coupled)[-1] - np.sqrt((1 + np.sqrt(1 - 0.5**2)) / 2)) < 1e-12


def test_rk4_converges_against_independent_adaptive_solver():
    def rhs(t, y):
        return [-0.5 + np.sin(y[1] - y[0]), 0.5 + np.sin(y[0] - y[1])]

    ref = solve_ivp(rhs, [0, 1], [0, 1.2], rtol=1e-12, atol=1e-13).y[:, -1]
    errors = [
        np.linalg.norm(kuramoto([-0.5, 0.5], [0, 1.2], 2, dt=d, steps=round(1 / d))[-1] - ref)
        for d in [0.1, 0.05, 0.025]
    ]
    assert errors[0] / errors[1] > 12 and errors[1] / errors[2] > 12


def test_stochastic_increment_convergence_and_seed_reproduction():
    rng = np.random.default_rng(11)
    fine_dw = rng.normal(size=(2000, 2)) * np.sqrt(0.001)
    fine = kuramoto([-0.5, 0.5], [0, 1], 1, dt=0.001, steps=2000, diffusion=0.1, increments=fine_dw)
    coarse = kuramoto(
        [-0.5, 0.5],
        [0, 1],
        1,
        dt=0.002,
        steps=1000,
        diffusion=0.1,
        increments=fine_dw.reshape(1000, 2, 2).sum(axis=1),
    )
    assert np.max(np.abs(fine[::2] - coarse)) < 0.01
    a = kuramoto([0, 1], [0, 1], 1, dt=0.01, steps=100, diffusion=0.2, seed=2)
    b = kuramoto([0, 1], [0, 1], 1, dt=0.01, steps=100, diffusion=0.2, seed=2)
    np.testing.assert_array_equal(a, b)


def test_lms_and_identification_recover_known_fir():
    x = np.random.default_rng(8).normal(size=4000)
    h = [0.7, -0.2, 0.1]
    y = signal.lfilter(h, [1], x)
    _, e, w = lms(x, y, 3, 0.05)
    np.testing.assert_allclose(w, h, atol=1e-9)
    assert np.mean(e[-1000:] ** 2) < 1e-14
    fit = identify_fir(x, y, 3)
    np.testing.assert_allclose(fit["coefficients"], h, atol=1e-14)
    assert fit["residual_variance"] < 1e-28
    with pytest.raises(ValueError, match="exciting"):
        identify_fir(np.ones(100), np.ones(100), 3)
    independent = np.random.default_rng(9).normal(size=4000)
    assert np.linalg.norm(identify_fir(x, independent, 3)["coefficients"]) < 0.1


def test_plate_boundary_frequency_scaling_and_spatial_convergence():
    base = plate_mode(1, 2)
    twice = plate_mode(1, 2, thickness_m=0.002)
    assert twice["frequency_hz"] == pytest.approx(2 * base["frequency_hz"])
    np.testing.assert_allclose(np.asarray(base["displacement"])[[0, -1]], 0, atol=1e-14)
    # Discrete Laplacian eigenvalue converges to -5*pi² for the unit square.
    errors = []
    for grid in [33, 65, 129]:
        u = np.array(plate_mode(1, 2, grid=grid)["displacement"])
        dx = 1 / (grid - 1)
        lap = (u[1:-1, 2:] + u[1:-1, :-2] + u[2:, 1:-1] + u[:-2, 1:-1] - 4 * u[1:-1, 1:-1]) / dx**2
        errors.append(np.max(np.abs(lap + 5 * np.pi**2 * u[1:-1, 1:-1])))
    assert errors[0] / errors[1] > 3.9 and errors[1] / errors[2] > 3.9


def test_coherence_and_cross_phase_against_scipy():
    rng = np.random.default_rng(2)
    x = rng.normal(size=8192)
    y = np.roll(x, 2) + rng.normal(size=x.size) * 0.1
    result = cross_spectrum(np.column_stack([x, y]), 128, 256)
    f, c = signal.coherence(x, y, 128, nperseg=256)
    np.testing.assert_allclose(np.asarray(result["coherence"])[0, 1], c, atol=2e-15)
    neg = cross_spectrum(rng.normal(size=(8192, 2)), 128, 128)
    assert np.mean(np.asarray(neg["coherence"])[0, 1]) < 0.05


@pytest.mark.parametrize("nperseg", [8, 9, 64, 65])
def test_coherence_requires_three_segments_for_odd_and_even_lengths(nperseg):
    # Regression: n >= 2*nperseg was accepted as "three segments", but odd
    # nperseg yields two, where the coherence of independent noise is ~0.5.
    rng = np.random.default_rng(nperseg)
    step = nperseg - nperseg // 2
    shortest = nperseg + 2 * step
    assert cross_spectrum(rng.normal(size=(shortest, 2)), 1.0, nperseg)["segments"] == 3
    with pytest.raises(ValueError, match="three"):
        cross_spectrum(rng.normal(size=(shortest - 1, 2)), 1.0, nperseg)
    f, _ = signal.coherence(*rng.normal(size=(2, shortest)), 1.0, nperseg=nperseg)
    assert f.size == nperseg // 2 + 1


@pytest.mark.parametrize("omega0", [6.0, 8.0])
def test_wavelet_ridge_follows_the_l2_normalization_relation(omega0):
    # The documented nominal centers are not ridge frequencies: under L2
    # normalization a tone's modulus ridge sits at f*2w0/(w0+sqrt(w0^2+2)).
    fs, tone = 200.0, 10.0
    x = np.cos(2 * np.pi * tone * np.arange(4000) / fs)
    nominal = np.linspace(9.0, 11.0, 2001)
    ridge = nominal[np.argmax(np.abs(morlet_cwt(x, fs, nominal, omega0).coefficients[:, 2000]))]
    expected = tone * 2 * omega0 / (omega0 + np.sqrt(omega0**2 + 2))
    assert abs(ridge - expected) <= 0.002  # grid spacing 0.001 Hz
    assert ridge < tone


@pytest.mark.parametrize(
    "call",
    [
        lambda: stft([1, np.nan] * 100, 128),
        lambda: stft([1] * 200, 0),
        lambda: morlet_cwt([1] * 100, 128, [64]),
        lambda: phase_locking([[1, 2]]),
        lambda: kuramoto([0, 1], [0, 1], 1, dt=10, steps=2),
        lambda: plate_mode(1, 1, thickness_m=0.2),
        lambda: cross_spectrum(np.ones((128, 2)), 128, 128),
    ],
)
def test_invalid_domains_are_rejected(call):
    with pytest.raises(ValueError):
        call()
