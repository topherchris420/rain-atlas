"""Thin artifact-aware entrypoints for resonance skill manifests."""

from __future__ import annotations

import numpy as np

from . import resonance as r


def run_method(method: str, inputs: dict, ctx) -> dict:
    if method == "stft":
        result = r.stft(**inputs)
        power = result.power_density.mean(axis=1)
        return {
            "power": ctx.save_array("stft-density.npy", result.power_density),
            "frequency_hz": result.frequency_hz.tolist(),
            "time_s": result.time_s.tolist(),
            "peak_hz": float(result.frequency_hz[np.argmax(power)]) if np.any(power > 0) else None,
            "unit": "input units squared / Hz",
            "resolution_hz": result.resolution_hz,
        }
    if method == "morlet_cwt":
        result = r.morlet_cwt(**inputs)
        power = [
            float(np.mean(np.abs(c[m]) ** 2)) if m.any() else 0
            for c, m in zip(result.coefficients, result.edge_valid)
        ]
        return {
            "coefficients": ctx.save_array("morlet-coefficients.npy", result.coefficients),
            "edge_valid": ctx.save_array("morlet-edge-mask.npy", result.edge_valid),
            "dominant_hz": float(result.frequency_hz[np.argmax(power)]) if max(power) > 0 else None,
            "frequency_hz": result.frequency_hz.tolist(),
            "unit": "L2 normalized coefficient; not PSD",
        }
    if method == "phase_locking":
        phases = np.asarray(inputs["phases_rad"])
        return {
            "plv": r.phase_locking(phases).tolist(),
            "mean_order": float(r.order_parameter(phases).mean()),
            "unit": "dimensionless",
        }
    if method == "kuramoto":
        path = r.kuramoto(**inputs, seed=ctx.seed)
        return {
            "phases": ctx.save_array("phases.npy", path),
            "end_order": float(r.order_parameter(path)[-1]),
            "final_phases_rad": path[-1].tolist(),
            "unit": "rad",
        }
    if method == "lms":
        y, e, w = r.lms(**inputs)
        return {
            "coefficients": w.tolist(),
            "mse": float(np.mean(e**2)),
            "prediction": ctx.save_array("prediction.npy", y),
            "errors": ctx.save_array("errors.npy", e),
            "unit": "response units; MSE in response units squared",
        }
    if method == "identify_fir":
        out = r.identify_fir(**inputs)
        residuals = out.pop("residuals")
        return {**out, "residuals": ctx.save_array("residuals.npy", residuals), "unit": "response / input"}
    if method == "plate_mode":
        out = r.plate_mode(**inputs)
        shape = out.pop("displacement")
        return {
            **out,
            "displacement": ctx.save_array("plate-mode.npy", shape),
            "unit": "dimensionless displacement; Hz frequency",
        }
    if method == "cross_spectrum":
        out = r.cross_spectrum(**inputs)
        cs = np.array(out["cross_real"]) + 1j * np.array(out["cross_imag"])
        index = int(np.argmax(cs[0, 0].real))
        return {
            "cross_psd": ctx.save_array("cross-psd.npy", cs),
            "coherence": ctx.save_array("coherence.npy", out["coherence"]),
            "undefined_bins": ctx.save_array("undefined-bins.npy", out["undefined_bins"]),
            "frequency_hz": out["frequency_hz"],
            "peak_hz": out["frequency_hz"][index],
            "peak_coherence": out["coherence"][0][1][index],
            "segments": out["segments"],
            "unit": "input units squared / Hz; coherence dimensionless",
        }
    raise ValueError("unknown resonance method")
