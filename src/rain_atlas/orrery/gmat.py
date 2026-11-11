"""NASA GMAT R2026a reference runs: script generation, execution and report parsing.

GMAT (Apache-2.0, https://github.com/nasa/GMAT) is used only as an external,
independently developed reference program. ORRERY contains no GMAT code; this
module writes GMAT script text, runs ``GmatConsole --run`` when a local GMAT
installation is supplied, and parses the resulting ReportFile. The parsed
reference trajectories are committed under ``reference/gmat-R2026a/`` together
with the exact script text, the hashes of the GMAT executables and data files,
and the console banner, so a comparison can be re-checked without GMAT and the
reference can be regenerated with it.

Script conventions (chosen to make the two programs model the same physics):

* epoch in UTCGregorian; initial state in EarthMJ2000Eq Cartesian at 17
  significant digits (exact binary round trip);
* ``SolarSystem.EphemerisSource = 'SPICE'`` with ``de421.bsp`` (the file the
  ORRERY excerpt was made from); ``Earth.NutationUpdateInterval = 0`` (GMAT's
  documented high-fidelity setting; the default 60 s caches nutation);
* gravity from ``JGM3.cof`` at the configured degree/order (degree 0 for a
  point-mass Earth); third bodies as ``FM.PointMasses``; drag, SRP and
  relativistic correction off;
* ``RungeKutta89`` with ``Accuracy = 1e-13`` (RSSStep), so GMAT's own
  truncation error is small against the quantities compared;
* output by a loop of ``Propagate Prop(Sat) {Sat.ElapsedSecs = cadence}``
  followed by ``Report``. GMAT's stopping-condition solver lands within about
  1e-7 s of each requested time and the offset accumulates, so ORRERY is
  compared at the elapsed times GMAT actually reports.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .timescales import Epoch

REFERENCE_DIR = Path(__file__).resolve().parent / "reference" / "gmat-R2026a"
GMAT_VERSION = "R2026a"
DISTRIBUTION = "gmat-win-R2026a.zip (SourceForge, MD5 e6248b1a776c952c3dda0bedda7f1f19)"
STATE_COLUMNS = ["X", "Y", "Z", "VX", "VY", "VZ"]
TIME_COLUMNS = ["ElapsedSecs", "A1ModJulian", "TAIModJulian", "TTModJulian", "TDBModJulian", "UTCModJulian"]
HASHED_FILES = [
    "bin/GmatConsole.exe",
    "bin/libGmatBase.dll",
    "bin/libGmatUtil.dll",
    "bin/gmat_startup_file.txt",
    "data/gravity/earth/JGM3.cof",
    "data/planetary_ephem/spk/de421.bsp",
    "data/planetary_coeff/NUTATION.DAT",
    "data/planetary_coeff/eopc04_08.62-now",
    "data/time/tai-utc.dat",
    "data/icrf/ICRF_Table.txt",
]


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def columns(body_positions: list[str]) -> list[str]:
    cols = [f"Sat.{c}" for c in TIME_COLUMNS]
    cols += [f"Sat.EarthMJ2000Eq.{c}" for c in STATE_COLUMNS]
    cols += [f"Sat.EarthFixed.{c}" for c in STATE_COLUMNS]
    for body in body_positions:
        cols += [f"{body}.EarthMJ2000Eq.{c}" for c in ("X", "Y", "Z")]
    return cols


def _gravity_lines(earth: dict) -> list[str]:
    model = earth.get("model", "point-mass")
    if model == "point-mass":
        degree = order = 0
    elif model == "j2":
        if earth.get("pole", "earth-fixed") != "earth-fixed":
            raise ValueError("GMAT applies zonal harmonics in EarthFixed axes; use pole='earth-fixed'")
        degree, order = 2, 0
    elif model == "harmonics":
        if earth.get("field", "jgm3_8x8") != "jgm3_8x8":
            raise ValueError("GMAT reference runs use JGM3.cof")
        degree, order = int(earth["degree"]), int(earth["order"])
    else:
        raise ValueError(f"no GMAT mapping for Earth model {model!r}")
    return [
        "FM.PrimaryBodies = {Earth};",
        f"FM.GravityField.Earth.Degree = {degree};",
        f"FM.GravityField.Earth.Order = {order};",
        "FM.GravityField.Earth.PotentialFile = 'JGM3.cof';",
        "FM.GravityField.Earth.TideModel = 'None';",
    ]


def script(scenario: dict, report_path: str, body_positions: list[str] | None = None) -> str:
    """GMAT script text for one scenario (see module docstring for the conventions)."""

    cfg = scenario["config"]
    forces = cfg["forces"]
    if forces.get("constants", "gmat") != "gmat":
        raise ValueError("GMAT reference runs require the 'gmat' constants family")
    if cfg.get("maneuvers"):
        raise ValueError("GMAT reference scenarios are coast arcs")
    if cfg.get("frame_tie", "gmat-icrf-table") != "gmat-icrf-table" and forces.get("third_bodies"):
        raise ValueError("GMAT always applies its ICRF-to-FK5 table to ephemeris states")
    bodies = body_positions or []
    epoch = Epoch.from_iso("UTC", cfg["epoch_utc"])
    state = cfg["initial_state"]
    cadence = float(cfg["output_step_s"])
    n = int(round(float(cfg["duration_s"]) / cadence))
    names = {"moon": "Luna", "sun": "Sun"}
    third = [names[b] for b in forces.get("third_bodies", [])]
    prop = scenario.get("gmat_propagator", {})
    report = " ".join(columns(bodies))
    lines = [
        f"% ORRERY reference scenario {scenario['name']}: {scenario['title']}",
        "% Generated by rain_atlas.orrery.gmat; run with: GmatConsole --run <this file>",
        "SolarSystem.EphemerisSource = 'SPICE';",
        "SolarSystem.SPKFilename = 'de421.bsp';",
        "Earth.NutationUpdateInterval = 0;",
        "",
        "Create Spacecraft Sat;",
        "Sat.DateFormat = UTCGregorian;",
        f"Sat.Epoch = '{epoch.gmat_gregorian()}';",
        "Sat.CoordinateSystem = EarthMJ2000Eq;",
        "Sat.DisplayStateType = Cartesian;",
    ]
    lines += [f"Sat.{c} = {float(v)!r};" for c, v in zip(STATE_COLUMNS, state)]
    lines += ["", "Create ForceModel FM;", "FM.CentralBody = Earth;"]
    lines += _gravity_lines(forces.get("earth", {"model": "point-mass"}))
    lines += [
        f"FM.PointMasses = {{{', '.join(third)}}};" if third else "FM.PointMasses = {};",
        "FM.Drag.AtmosphereModel = None;",
        "FM.SRP = Off;",
        "FM.RelativisticCorrection = Off;",
        "FM.ErrorControl = RSSStep;",
        "",
        "Create Propagator Prop;",
        "Prop.FM = FM;",
        "Prop.Type = RungeKutta89;",
        f"Prop.InitialStepSize = {prop.get('initial_step_s', 60)};",
        f"Prop.Accuracy = {prop.get('accuracy', 1e-13)};",
        f"Prop.MinStep = {prop.get('min_step_s', 0.001)};",
        f"Prop.MaxStep = {prop.get('max_step_s', 2700)};",
        "Prop.MaxStepAttempts = 50;",
        "Prop.StopIfAccuracyIsViolated = true;",
        "",
        "Create ReportFile rf;",
        f"rf.Filename = '{report_path}';",
        "rf.Precision = 17;",
        "rf.WriteHeaders = false;",
        "rf.LeftJustify = On;",
        "rf.ZeroFill = Off;",
        "",
        "Create Variable I;",
        "",
        "BeginMissionSequence;",
        f"Report rf {report};",
        f"For I = 1:{n};",
        f"   Propagate Prop(Sat) {{Sat.ElapsedSecs = {cadence!r}}};",
        f"   Report rf {report};",
        "EndFor;",
        "",
    ]
    return "\n".join(lines)


def parse_report(text: str, cols: list[str]) -> np.ndarray:
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) != len(cols):
            raise ValueError(f"report row has {len(parts)} values, expected {len(cols)}")
        rows.append([float(p) for p in parts])
    return np.asarray(rows, dtype=float)


def installation(gmat_root: Path) -> dict:
    root = Path(gmat_root)
    return {
        "version": GMAT_VERSION,
        "distribution": DISTRIBUTION,
        "files": {name: sha256(root / name) for name in HASHED_FILES if (root / name).exists()},
    }


def run(scenario: dict, gmat_root: Path, workdir: Path, body_positions: list[str] | None = None) -> dict:
    """Run one scenario through GmatConsole and return the reference record."""

    gmat_root = Path(gmat_root).resolve()
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    report_path = workdir / f"{scenario['name']}.txt"
    script_path = workdir / f"{scenario['name']}.script"
    text = script(scenario, report_path.as_posix(), body_positions)
    script_path.write_text(text, encoding="utf-8", newline="\n")
    if report_path.exists():
        raise FileExistsError(f"{report_path} exists; use a fresh work directory")
    console = gmat_root / "bin" / "GmatConsole.exe"
    if not console.exists():
        console = gmat_root / "bin" / "GmatConsole"
    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        [str(console), "--run", str(script_path)],
        cwd=str(gmat_root / "bin"),
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    finished = datetime.now(timezone.utc)
    if proc.returncode != 0 or "successful" not in proc.stdout:
        raise RuntimeError(f"GMAT failed ({proc.returncode}):\n{proc.stdout[-3000:]}\n{proc.stderr[-2000:]}")
    cols = columns(body_positions or [])
    report_text = report_path.read_text(encoding="utf-8")
    data = parse_report(report_text, cols)
    banner = re.search(r"Build Date: ([^\n]+)", proc.stdout)
    return {
        "schema": "orrery.gmat-reference/v1",
        "scenario": scenario["name"],
        "title": scenario["title"],
        "configuration": scenario["config"],
        "gmat": installation(gmat_root) | {"build_date": banner.group(1).strip() if banner else None},
        "script": text,
        "script_sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "report_sha256": "sha256:" + hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
        "run": {
            "started_utc": started.isoformat(timespec="seconds"),
            "wall_seconds": round((finished - started).total_seconds(), 3),
            "host": f"{platform.system()} {platform.release()} {platform.machine()}",
        },
        "columns": cols,
        "rows": data.tolist(),
    }


def write_reference(record: dict) -> Path:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = REFERENCE_DIR / f"{record['scenario']}.json"
    path.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return path


def load_reference(name: str) -> dict:
    return json.loads((REFERENCE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def reference_arrays(record: dict) -> dict:
    """Split a reference record into named arrays (km, km/s, s)."""

    cols = record["columns"]
    data = np.asarray(record["rows"], dtype=float)

    def pick(prefix: str, names: list[str]) -> np.ndarray:
        return data[:, [cols.index(f"{prefix}.{n}") for n in names]]

    out = {
        "elapsed_s": data[:, cols.index("Sat.ElapsedSecs")],
        "mj2000": pick("Sat.EarthMJ2000Eq", STATE_COLUMNS),
        "earth_fixed": pick("Sat.EarthFixed", STATE_COLUMNS),
        "times": {c: data[:, cols.index(f"Sat.{c}")] for c in TIME_COLUMNS},
    }
    for body in ("Luna", "Sun"):
        if f"{body}.EarthMJ2000Eq.X" in cols:
            out[body.lower()] = pick(f"{body}.EarthMJ2000Eq", ["X", "Y", "Z"])
    return out
