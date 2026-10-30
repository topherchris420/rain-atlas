import numpy as np

from rain_atlas.science.spectral import detect_peaks, welch_psd


def run(inputs, ctx):
    signals = np.atleast_2d(ctx.load_array(inputs["signals"]))
    fs = float(inputs["fs"])
    nperseg = int(inputs["nperseg"])
    overlap = float(inputs.get("overlap", 0.5))
    alpha = float(inputs.get("alpha", 0.01))
    all_peaks, psds, meta = [], [], None
    for row in signals:
        welch = welch_psd(row, fs, nperseg, overlap)
        peaks, meta = detect_peaks(
            welch,
            alpha=alpha,
            min_separation_hz=inputs.get("min_separation_hz"),
            fmin=float(inputs.get("fmin", 0.0)),
            fmax=inputs.get("fmax"),
        )
        psds.append(welch.psd)
        all_peaks.append([
            {"frequency_hz": p.frequency_hz, "snr_db": p.snr_db, "psd": p.psd} for p in peaks
        ])
    freqs = welch.freqs
    mean_psd = np.vstack([freqs, np.mean(psds, axis=0)])
    detection = dict(meta)
    detection.update({"segments": welch.segments, "nperseg": nperseg, "overlap": overlap,
                      "enbw_hz": welch.enbw_hz, "method": "welch-hann + chi2 Bonferroni threshold"})
    ctx.log(f"analysed {signals.shape[0]} realization(s); detections per realization: "
            f"{[len(p) for p in all_peaks][:20]}")
    return {"peaks": all_peaks, "detection": detection, "mean_psd": ctx.save_array("mean_psd.npy", mean_psd)}
