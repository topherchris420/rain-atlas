import numpy as np

from rain_atlas.science.spectral import tone_f_test


def run(inputs, ctx):
    signals = np.atleast_2d(ctx.load_array(inputs["signals"]))
    fs = float(inputs["fs"])
    freqs = [float(f) for f in inputs["frequencies_hz"]]
    alpha = float(inputs.get("alpha", 0.01))
    corrected = alpha / max(1, len(freqs))
    hi, lo = float(inputs.get("min_fraction", 0.8)), float(inputs.get("max_fraction_contradict", 0.2))
    tests = []
    for i, f in enumerate(freqs):
        nuisance = np.array([g for j, g in enumerate(freqs) if j != i])
        pvals = [tone_f_test(row, fs, f, nuisance)["p_value"] for row in signals]
        fraction = float(np.mean(np.array(pvals) < corrected))
        outcome = "corroborated" if fraction >= hi else "contradicted" if fraction < lo else "inconclusive"
        tests.append({
            "frequency_hz": f,
            "p_values": pvals,
            "alpha_corrected": corrected,
            "fraction_significant": fraction,
            "outcome": outcome,
        })
    ctx.log(f"tested {len(freqs)} frequency claim(s) on {signals.shape[0]} replicate(s)")
    return {"tests": tests}
