import hashlib

import numpy as np


def run(inputs, ctx):
    fs, n, reps = float(inputs["fs"]), int(inputs["n"]), int(inputs["realizations"])
    # Errors must not echo tone parameters: inputs may be sealed ground truth.
    if any(tone["frequency_hz"] >= fs / 2 for tone in inputs["tones"]):
        raise ValueError(f"a tone is at or above the Nyquist frequency ({fs / 2} Hz)")
    t = np.arange(n) / fs
    clean = np.zeros(n)
    for tone in inputs["tones"]:
        clean += tone["amplitude"] * np.cos(2 * np.pi * tone["frequency_hz"] * t + tone["phase_rad"])
    signals = np.empty((reps, n))
    for r in range(reps):
        signals[r] = clean + ctx.rng(r).normal(0.0, inputs["noise_std"], n)
    ctx.log(f"generated {reps} realization(s) of {n} samples at {fs} Hz")
    return {
        "signals": ctx.save_array("signals.npy", signals),
        "fs": fs,
        "n": n,
        "realizations": reps,
        "sha256_per_realization": ["sha256:" + hashlib.sha256(row.tobytes()).hexdigest() for row in signals],
    }
