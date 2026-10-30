import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

INK = "#222320"
ACCENT = "#3156a3"
MUTED = "#8a8778"
PALETTE = ["#3156a3", "#b4552d", "#2f7d5b", "#7a4fa0", "#8a8778"]
STYLES = {"solid": "-", "dashed": "--", "dotted": ":"}


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "axes.linewidth": 0.8,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.hashsalt": "rain-atlas",
        "svg.fonttype": "none",
    })


def _spectrum(ax, inputs, ctx):
    data = ctx.load_array(inputs["psd"])
    freqs, psd = data[0], data[1]
    fmax = inputs.get("fmax", float(freqs[-1]))
    keep = freqs <= fmax
    ax.semilogy(freqs[keep], psd[keep], color=INK, lw=0.7, label="mean Welch PSD")
    for k, marker in enumerate(inputs.get("markers", [])):
        color = PALETTE[(k + 1) % len(PALETTE)]
        for j, f in enumerate(marker["frequencies_hz"]):
            ax.axvline(f, color=color, lw=0.9, ls=STYLES[marker.get("style", "dashed")],
                       label=marker["label"] if j == 0 else None)
    ax.set_xlabel(inputs.get("xlabel", "Frequency (Hz)"))
    ax.set_ylabel(inputs.get("ylabel", "PSD (units²/Hz)"))


def _lines(ax, inputs):
    for k, s in enumerate(inputs.get("series", [])):
        x = np.asarray(s["x"], dtype=float)
        y = np.asarray([np.nan if v is None else v for v in s["y"]], dtype=float)
        yerr = s.get("yerr")
        color = PALETTE[k % len(PALETTE)]
        if yerr is not None:
            err = np.asarray([np.nan if v is None else v for v in yerr], dtype=float)
            ax.errorbar(x, y, yerr=err, color=color, lw=1.0, marker="o", ms=3, capsize=2, label=s["label"])
        else:
            ax.plot(x, y, color=color, lw=1.0, marker="o", ms=3, label=s["label"])
    if inputs.get("ylog"):
        ax.set_yscale("log")
    ax.set_xlabel(inputs.get("xlabel", "x"))
    ax.set_ylabel(inputs.get("ylabel", "y"))


def run(inputs, ctx):
    _style()
    fig, ax = plt.subplots(figsize=(6.4, 3.6), layout="constrained")
    if inputs["kind"] == "spectrum":
        if "psd" not in inputs:
            raise ValueError("spectrum figures need a 'psd' artifact")
        _spectrum(ax, inputs, ctx)
    else:
        if not inputs.get("series"):
            raise ValueError("line figures need at least one series")
        _lines(ax, inputs)
    ax.set_title(inputs["title"], loc="left", color=INK, fontsize=10)
    ax.grid(True, color="#d9d5ca", lw=0.5)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, fontsize=8)
    outputs = {"caption": inputs.get("caption", inputs["title"])}
    for fmt, kwargs in (("png", {"dpi": 300, "metadata": {"Software": None}}), ("svg", {"metadata": {"Date": None, "Creator": None}})):
        buffer = io.BytesIO()
        fig.savefig(buffer, format=fmt, **kwargs)
        outputs[fmt] = ctx.write_bytes(f"{inputs['name']}.{fmt}", buffer.getvalue())
    plt.close(fig)
    ctx.log(f"rendered {inputs['kind']} figure {inputs['name']}")
    return outputs
