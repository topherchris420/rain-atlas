"""Derive the committed BusyBox routine-observation files from a Ghidra document.

Given the ``reconstruction.json`` emitted by ``BlackglassReconstruct.java`` and a
mapping of reconstruction name -> routine entry address, this writes one
``reconstruction_data/<name>.busybox.json`` per routine, containing only the
non-copyrightable derived facts (the Native Routine Explorer's output). It copies
no decompiled text; the decompilation is referenced by digest only.

    uv run python scripts/make_blackglass_observations.py <reconstruction.json>

The committed files are the artifact CI uses; this script records how they were
produced from a local Ghidra run (the binary and its decompilation are not
committed). Re-running it on the same binary + tool version reproduces the files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rain_atlas.blackglass.explorer import load_reconstruction, select  # noqa: E402

# reconstruction name -> the routine entry address that carries its defining evidence.
NAME_TO_ENTRY = {
    "md5": "0x4b4c00",  # MD5 state init: stores MD5's 4-word IV, no fifth word
    "sha1": "0x4b4cb6",  # SHA-1 state init: the same four words plus H4 = 0xc3d2e1f0
    "base64": "0x40a567",  # references the RFC 4648 alphabet
}

DATA_DIR = ROOT / "src" / "rain_atlas" / "blackglass" / "reconstruction_data"


def main(doc_path: str) -> int:
    observations = load_reconstruction(Path(doc_path))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, entry in NAME_TO_ENTRY.items():
        obs = select(observations, entry)
        obs_dict = obs.to_dict()
        obs_dict["notes"] = (
            f"BusyBox routine carrying the defining evidence of {name.upper()}; "
            "derived facts only, decompilation referenced by digest."
        )
        out = DATA_DIR / f"{name}.busybox.json"
        text = json.dumps(obs_dict, indent=2, ensure_ascii=True) + "\n"
        out.write_text(text, encoding="utf-8", newline="\n")
        consts = [f.target for f in obs.facts if f.kind == "constant"]
        print(
            f"wrote {out.relative_to(ROOT)}  ({obs.name} @ {obs.entry}, {len(obs.facts)} facts, consts={consts})"
        )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
