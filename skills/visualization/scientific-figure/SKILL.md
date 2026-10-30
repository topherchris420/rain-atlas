---
name: scientific-figure
description: Render publication-style spectrum or line/error-bar figures (PNG and SVG) from recorded numerical outputs. Use when a report needs a figure whose every plotted value comes from a hashed artifact or recorded result.
license: MIT
compatibility: Requires Python 3.11+ with numpy, matplotlib and the rain-atlas package (ATLAS executor). Reads installed system fonts.
metadata:
  version: "1.0.0"
  domain: visualization
---
# Scientific figure

Two figure types, both drawn with matplotlib's Agg backend and saved as PNG
(300 dpi) and SVG with fixed metadata so identical inputs give identical SVG
bytes:

- `spectrum`: a PSD array artifact (`[freqs, psd]`), log-scaled, with optional
  vertical markers for detected lines and (after unsealing) true lines.
- `lines`: x/y series with optional symmetric error bars, for sweeps such as
  recovery rate versus SNR.

The figure caption states what each marker means; nothing is drawn that is not
in the inputs.
