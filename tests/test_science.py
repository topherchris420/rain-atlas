import numpy as np
import pytest
from scipy import signal as sps

from rain_atlas.agents.disagreement import verdict
from rain_atlas.science.evaluation import agreement, cluster, match, recovery
from rain_atlas.science.spectral import (
    bic_sinusoid_search,
    crlb_frequency_std_hz,
    detect_peaks,
    tone_f_test,
    welch_psd,
)

FS, N = 1000.0, 8192
T = np.arange(N) / FS


def tones(rng, sigma, spec=((47.3, 1.0, 0.4), (123.9, 0.6, 1.1))):
    return sum(a * np.cos(2 * np.pi * f * T + p) for f, a, p in spec) + rng.normal(0, sigma, N)


def test_welch_matches_scipy():
    x = np.random.default_rng(1).normal(size=N)
    ours = welch_psd(x, FS, 1024, 0.5)
    f, p = sps.welch(x, FS, window="hann", nperseg=1024, noverlap=512, detrend="constant", scaling="density")
    assert np.allclose(ours.freqs, f)
    assert np.max(np.abs(ours.psd - p) / p) < 1e-10


def test_detects_tones_with_small_error():
    x = tones(np.random.default_rng(2), 0.3)
    peaks, meta = detect_peaks(welch_psd(x, FS, 2048), alpha=0.01)
    found = sorted(p.frequency_hz for p in peaks)
    assert len(found) == 2
    assert abs(found[0] - 47.3) < 0.05 and abs(found[1] - 123.9) < 0.05
    assert meta["bins_searched"] > 0


def test_false_alarm_rate_is_controlled():
    rng = np.random.default_rng(3)
    trials = 200
    alarms = sum(
        bool(detect_peaks(welch_psd(rng.normal(size=N), FS, 2048), alpha=0.05)[0]) for _ in range(trials)
    )
    # Family-wise alpha 0.05: expect about 10 of 200; allow sampling error.
    assert alarms <= 22


def test_nls_finds_order_and_frequencies():
    x = tones(np.random.default_rng(4), 0.3)
    fit, path = bic_sinusoid_search(x, FS, max_tones=5)
    assert len(fit.frequencies_hz) == 2
    assert np.allclose(np.sort(fit.frequencies_hz), [47.3, 123.9], atol=0.005)
    assert len(path) >= 3


def test_nls_false_tone_rate_in_noise_is_low():
    # BIC ignores the search over frequency, so some false tones are expected:
    # 6 of 300 realizations (2.0%) when measured during development.
    trials = 40
    false = sum(
        len(
            bic_sinusoid_search(np.random.default_rng([5, r]).normal(size=N), FS, max_tones=3)[
                0
            ].frequencies_hz
        )
        > 0
        for r in range(trials)
    )
    assert false <= 5


def test_f_test_separates_present_from_absent():
    x = tones(np.random.default_rng(6), 1.0)
    assert tone_f_test(x, FS, 47.3, np.array([123.9]))["p_value"] < 1e-6
    assert tone_f_test(x, FS, 300.0, np.array([47.3, 123.9]))["p_value"] > 1e-3


def test_crlb_formula():
    # Kay (1993), Fundamentals of Statistical Signal Processing: Estimation Theory, ch. 3; in Hz for amplitude 1, sigma 1, N = 1000, fs = 1
    eta = 0.5
    expected = np.sqrt(12 / ((2 * np.pi) ** 2 * eta * 1000 * (1000**2 - 1)))
    assert crlb_frequency_std_hz(1.0, 1.0, 1000, 1.0) == pytest.approx(expected)


def test_match_is_one_to_one():
    matched, only_a, only_b = match([10.0, 10.05], [10.02], 0.1)
    assert matched == [(0, 0)] and only_a == [1] and only_b == []
    matched, only_a, only_b = match([10.0, 10.04], [10.035, 9.99], 0.1)
    assert matched == [(0, 1), (1, 0)] and only_a == [] and only_b == []


def test_cluster_fraction():
    clusters = cluster([[10.0, 50.0], [10.1], [9.9, 80.0]], 0.25)
    assert [round(c["frequency_hz"], 2) for c in clusters] == [10.0, 50.0, 80.0]
    assert clusters[0]["fraction"] == 1.0 and clusters[1]["fraction"] == pytest.approx(1 / 3)


def test_agreement_and_recovery():
    a = [[10.0, 50.0], [10.0, 50.0]]
    b = [[10.01], [10.02]]
    items = {round(i["frequency_hz"]): i for i in agreement(a, b, 0.1, 0.9)["items"]}
    assert items[10]["agrees"] and not items[50]["agrees"]
    score = recovery([[10.1], [9.9]], [10.0, 20.0], 0.5, amplitudes=[1.0, 1.0], noise_std=1.0, n=100, fs=1.0)
    assert score["tones"][0]["recovery_rate"] == 1.0 and score["tones"][1]["recovery_rate"] == 0.0
    assert score["tones"][0]["crlb_std_hz"] > 0 and score["tones"][1]["std_over_crlb"] is None


@pytest.mark.parametrize(
    "independent, falsification, reproduced, expected",
    [
        ("corroborated", "corroborated", True, "supported"),
        ("corroborated", "corroborated", False, "unresolved"),
        ("corroborated", "corroborated", None, "unresolved"),
        ("contradicted", "corroborated", True, "contradicted"),
        ("corroborated", "contradicted", True, "contradicted"),
        ("inconclusive", "corroborated", True, "unresolved"),
        (None, "corroborated", True, "unresolved"),
    ],
)
def test_verdict_rules(independent, falsification, reproduced, expected):
    assert verdict(independent, falsification, reproduced)[0] == expected
