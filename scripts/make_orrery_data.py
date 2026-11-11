"""Build ORRERY's hash-pinned reference-data excerpts from documented source files.

Usage::

    uv run python scripts/make_orrery_data.py --gmat-root PATH/TO/GMAT

``PATH/TO/GMAT`` is an extracted NASA GMAT R2026a release (``gmat-win-R2026a.zip``,
MD5 e6248b1a776c952c3dda0bedda7f1f19 as published by SourceForge). The script
reads only data files from it:

* ``data/time/tai-utc.dat``                 -> data/leap_seconds.json
* ``data/planetary_coeff/NUTATION.DAT``     -> data/nutation_iau1980.json (1980 section)
* ``data/planetary_coeff/eopc04_08.62-now`` -> data/eop_c04_2026.json (excerpt)
* ``data/gravity/earth/JGM3.cof``           -> data/jgm3_8x8.json (degree/order <= 8)
* ``data/planetary_ephem/spk/de421.bsp``    -> data/de421_2026.json (one-year excerpt)
* ``data/icrf/ICRF_Table.txt``              -> data/icrf_fk5_gmat_2026.json (excerpt)

Each output records the SHA-256 of its source file. Committed outputs are the
reference; regenerating them is only needed when a window changes, and the
tests compare a fresh build against the committed bytes when GMAT is present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rain_atlas.orrery.ephemeris import SpkFile, et_from_epoch  # noqa: E402
from rain_atlas.orrery.timescales import Epoch, gregorian_to_mjd  # noqa: E402

OUT = ROOT / "src" / "rain_atlas" / "orrery" / "data"
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
FLOAT = re.compile(r"[-+]?\d+\.\d+(?:[eEdD][-+]?\d+)?")
EOP_WINDOW = ("2025-12-20", "2026-02-20")
DE_WINDOW = ("2026-01-10T00:00:00", "2027-01-25T00:00:00")
DE_TARGETS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 301, 399]
SH_MAX = 8


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, payload: dict, compact: bool = False) -> None:
    text = json.dumps(payload, separators=(",", ":")) if compact else json.dumps(payload, indent=1)
    (OUT / name).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {name} ({len(text) + 1} bytes)")


def source(path: Path, gmat_root: Path, note: str) -> dict:
    return {
        "file": path.relative_to(gmat_root).as_posix(),
        "sha256": sha256(path),
        "distribution": "NASA GMAT R2026a gmat-win-R2026a.zip (MD5 e6248b1a776c952c3dda0bedda7f1f19)",
        "note": note,
    }


def leap_seconds(gmat_root: Path) -> None:
    path = gmat_root / "data" / "time" / "tai-utc.dat"
    rows = []
    for line in path.read_text(encoding="ascii").splitlines():
        if "TAI-UTC" not in line:
            continue
        parts = line.split()
        year, month, day = int(parts[0]), MONTHS[parts[1]], int(parts[2])
        offset = float(line.split("TAI-UTC=")[1].split("S")[0])
        ref = float(line.split("(MJD -")[1].split(")")[0].rstrip("."))
        rate = float(line.split(" X ")[1].split("S")[0])
        rows.append(
            {
                "utc_date": f"{year:04d}-{month:02d}-{day:02d}",
                "utc_mjd": gregorian_to_mjd(year, month, day),
                "offset_s": offset,
                "ref_mjd": ref,
                "rate_s_per_day": rate,
            }
        )
    write(
        "leap_seconds.json",
        {
            "description": "TAI-UTC = offset_s + (MJD - ref_mjd) * rate_s_per_day from utc_mjd onward (USNO/IERS)",
            "source": source(path, gmat_root, "USNO tai-utc.dat as distributed with GMAT"),
            "rows": rows,
        },
    )


def nutation(gmat_root: Path) -> None:
    path = gmat_root / "data" / "planetary_coeff" / "NUTATION.DAT"
    lines = path.read_text(encoding="ascii").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("xx 1980 IAU"))
    rows = []
    for line in lines[start + 2 :]:
        if line.startswith("xx"):
            break
        parts = line.split()
        if len(parts) < 10:
            continue
        rows.append(
            {
                "multipliers": [int(x) for x in parts[:5]],
                "A_B_C_D": [float(x) for x in parts[5:9]],
                "index": int(parts[9]),
            }
        )
    if len(rows) != 106:
        raise SystemExit(f"expected 106 IAU 1980 terms, found {len(rows)}")
    write(
        "nutation_iau1980.json",
        {
            "description": "IAU 1980 nutation: dpsi = sum (A + B T) sin(arg), deps = sum (C + D T) cos(arg), "
            "arg = multipliers . (l, l', F, D, Omega)",
            "unit_arcsec": 1.0e-4,
            "source": source(path, gmat_root, "1980 IAU Theory of Nutation (106 term) section"),
            "rows": rows,
        },
    )


def eop(gmat_root: Path) -> None:
    path = gmat_root / "data" / "planetary_coeff" / "eopc04_08.62-now"
    lo = gregorian_to_mjd(*(int(x) for x in EOP_WINDOW[0].split("-")))
    hi = gregorian_to_mjd(*(int(x) for x in EOP_WINDOW[1].split("-")))
    rows = []
    for line in path.read_text(encoding="ascii").splitlines():
        parts = line.split()
        if len(parts) < 14 or not parts[3].isdigit():
            continue
        mjd = int(parts[3])
        if lo <= mjd <= hi:
            rows.append(
                {
                    "mjd": mjd,
                    "x_arcsec": float(parts[4]),
                    "y_arcsec": float(parts[5]),
                    "ut1_utc_s": float(parts[6]),
                    "lod_s": float(parts[7]),
                    "dpsi_arcsec": float(parts[8]),
                    "deps_arcsec": float(parts[9]),
                }
            )
    if len(rows) != hi - lo + 1:
        raise SystemExit("EOP excerpt is incomplete")
    jumps = [b["ut1_utc_s"] - a["ut1_utc_s"] for a, b in zip(rows, rows[1:])]
    if any(abs(j) > 0.5 for j in jumps):
        raise SystemExit("EOP window contains a leap second; linear interpolation would be invalid")
    write(
        "eop_c04_2026.json",
        {
            "description": "IERS EOP 20 C04 daily values at 0h UTC (x, y, dPsi, dEps arcsec; UT1-UTC, LOD s)",
            "source": source(path, gmat_root, f"excerpt {EOP_WINDOW[0]} to {EOP_WINDOW[1]}")
            | {"name": "eop_c04_2026"},
            "rows": rows,
        },
    )


def jgm3(gmat_root: Path) -> None:
    path = gmat_root / "data" / "gravity" / "earth" / "JGM3.cof"
    mu = radius = None
    terms = []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("POTFIELD"):
            values = FLOAT.findall(line)
            mu, radius = float(values[0]) / 1e9, float(values[1]) / 1e3  # m^3/s^2 -> km^3/s^2, m -> km
        elif line.startswith("RECOEF"):
            match = re.match(r"^RECOEF\s+(\d+)\s+(\d+)(.*)$", line)
            if match is None:
                raise SystemExit(f"unparsed coefficient line: {line!r}")
            n, m = int(match.group(1)), int(match.group(2))
            if n > SH_MAX:
                continue
            values = [float(v) for v in FLOAT.findall(match.group(3))]
            terms.append({"n": n, "m": m, "C": values[0], "S": values[1] if len(values) > 1 else 0.0})
    write(
        "jgm3_8x8.json",
        {
            "description": "JGM-3 fully normalized Stokes coefficients, degree and order <= 8 (Tapley et al. 1996)",
            "normalization": "4-pi fully normalized (Kaula)",
            "mu_km3_s2": mu,
            "radius_km": radius,
            "source": source(path, gmat_root, f"JGM-03 70x70 file, truncated to {SH_MAX}x{SH_MAX}"),
            "terms": terms,
        },
    )


def de421(gmat_root: Path) -> None:
    path = gmat_root / "data" / "planetary_ephem" / "spk" / "de421.bsp"
    spk = SpkFile(path)
    et0 = et_from_epoch(Epoch.from_iso("TDB", DE_WINDOW[0]))
    et1 = et_from_epoch(Epoch.from_iso("TDB", DE_WINDOW[1]))
    eph = spk.ephemeris(DE_TARGETS, et0, et1)
    payload = eph.to_json()
    payload["source"] = source(
        path, gmat_root, f"NAIF de421.bsp, TDB window {DE_WINDOW[0]} to {DE_WINDOW[1]}"
    ) | {
        "name": "de421_2026",
        "constants": "JPL header.421 (see rain_atlas.orrery.constants)",
        "frame": "J2000 (ICRF axes)",
    }
    write("de421_2026.json", payload, compact=True)


def icrf_table(gmat_root: Path) -> None:
    path = gmat_root / "data" / "icrf" / "ICRF_Table.txt"
    # GMAT ModJulian (A1) window: DE excerpt window with ten days of margin for order-9 interpolation.
    lo = Epoch.from_iso("TDB", DE_WINDOW[0]).gmat_modjulian() - 10.0
    hi = Epoch.from_iso("TDB", DE_WINDOW[1]).gmat_modjulian() + 10.0
    rows = []
    for line in path.read_text(encoding="ascii").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            continue
        t = float(parts[0])
        if lo <= t <= hi:
            rows.append([t, float(parts[1]), float(parts[2]), float(parts[3])])
    if any(abs(b[0] - a[0] - 1.0) > 1e-9 for a, b in zip(rows, rows[1:])):
        raise SystemExit("ICRF table excerpt is not a contiguous daily series")
    write(
        "icrf_fk5_gmat_2026.json",
        {
            "description": (
                "GMAT ICRF-to-FK5 (MJ2000Eq) Euler rotation vectors (rad) by A1 Modified Julian Date "
                "(JD - 2430000); GMAT interpolates them with a 10-point (order-9) Lagrange polynomial"
            ),
            "columns": ["a1_gmat_modjulian", "rx_rad", "ry_rad", "rz_rad"],
            "source": source(path, gmat_root, "excerpt covering the DE421 window +/- 10 days")
            | {"name": "icrf_fk5_gmat_2026"},
            "rows": rows,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--gmat-root", required=True, type=Path)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    root = args.gmat_root.resolve()
    leap_seconds(root)
    nutation(root)
    eop(root)
    jgm3(root)
    de421(root)
    icrf_table(root)


if __name__ == "__main__":
    main()
