import numpy as np


def _stats(times, duration, window, refractory):
    t = np.sort(np.asarray(times, dtype=float))
    if t.size and (t[0] < 0 or t[-1] > duration):
        raise ValueError("spike times must lie within [0, duration_s]")
    isi = np.diff(t)
    edges = np.arange(0.0, duration + 1e-12, window)
    counts = np.histogram(t, bins=edges)[0] if edges.size > 1 else np.array([t.size])
    count_mean = float(counts.mean())
    return {
        "spikes": int(t.size),
        "rate_hz": float(t.size / duration),
        "isi_mean_s": float(isi.mean()) if isi.size else None,
        "isi_cv": float(isi.std(ddof=1) / isi.mean()) if isi.size > 1 and isi.mean() > 0 else None,
        "fano_factor": float(counts.var(ddof=1) / count_mean) if counts.size > 1 and count_mean > 0 else None,
        "windows": int(counts.size),
        "refractory_violations": int(np.sum(isi < refractory)),
        "refractory_violation_fraction": float(np.mean(isi < refractory)) if isi.size else 0.0,
    }


def run(inputs, ctx):
    trains = inputs["trains"]
    if isinstance(trains, dict):
        array = ctx.load_array(trains)
        trains = [row[~np.isnan(row)] for row in np.atleast_2d(array)]
    duration = float(inputs["duration_s"])
    window = float(inputs.get("window_s", 1.0))
    refractory = float(inputs.get("refractory_s", 0.002))
    results = [_stats(times, duration, window, refractory) for times in trains]
    ctx.log(f"summarised {len(results)} spike train(s)")
    return {"trains": results}
