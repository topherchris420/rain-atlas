import numpy as np

from rain_atlas.science.spectral import bic_sinusoid_search


def run(inputs, ctx):
    signals = np.atleast_2d(ctx.load_array(inputs["signals"]))
    fs = float(inputs["fs"])
    fits = []
    for row in signals:
        fit, path = bic_sinusoid_search(
            row, fs, max_tones=int(inputs.get("max_tones", 8)), pad=int(inputs.get("pad", 8)),
            fmin=float(inputs.get("fmin", 0.0)),
        )
        fits.append({
            "frequencies_hz": fit.frequencies_hz.tolist(),
            "frequency_se_hz": fit.frequency_se_hz.tolist(),
            "amplitudes": fit.amplitudes.tolist(),
            "phases_rad": fit.phases_rad.tolist(),
            "residual_std": fit.residual_std,
            "converged": fit.converged,
            "bic_path": path,
        })
    ctx.log(f"fitted {len(fits)} realization(s); tones per realization: {[len(f['frequencies_hz']) for f in fits][:20]}")
    return {"fits": fits}
