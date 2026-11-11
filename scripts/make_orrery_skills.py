"""Generate the astrodynamics skills from a single specification.

Usage::

    uv run python scripts/make_orrery_skills.py

Writes ``skills/astrodynamics/<name>/`` (SKILL.md, skill.json, run.py and one
example each) for the eight ORRERY skills. Each skill's ``run.py`` is a thin
wrapper over ``rain_atlas.orrery.skill_api``; each example's expected output is
derived independently of the skill (analytic formula, mathematical identity, a
published reference value, or a statistical property), never by recording the
skill's own result. Re-run after changing the API or examples; the committed
files are the reference.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from rain_atlas.orrery import skill_api  # noqa: E402
from rain_atlas.orrery.constants import GMAT_CONSTANTS as C  # noqa: E402
from rain_atlas.orrery.kepler import elements_to_state  # noqa: E402


def _floats(seq) -> list[float]:
    return [float(x) for x in np.asarray(seq, dtype=float).ravel()]


OUT = ROOT / "skills" / "astrodynamics"
MU = C["earth_mu_km3_s2"]
EPOCH = "2026-01-15T00:00:00"
LEO = [
    3140.426905642162,
    4934.9447007026465,
    3411.0614920951393,
    -6.099408469974278,
    0.6961135686551336,
    4.608379103488943,
]
VC7000 = math.sqrt(MU / 7000.0)
_r, _v = elements_to_state(
    6878.0, 0.01, math.radians(51.6), math.radians(30), math.radians(40), math.radians(10), MU
)
OD_TRUTH = _floats([_r, _v])
_rs = _floats(skill_api.station_inertial_position(35.0, -116.0, 0.0, EPOCH))
_rsn = math.sqrt(sum(x * x for x in _rs))
_up = [x / _rsn for x in _rs]
_sat = [_rs[i] + _up[i] * 1000.0 for i in range(3)]
_t = [-_up[1], _up[0], 0.0]
_tn = math.sqrt(sum(x * x for x in _t))
_satn = math.sqrt(sum(x * x for x in _sat))
_vmag = math.sqrt(MU / _satn)
TRACK_STATE = _floats(_sat + [_t[0] / _tn * _vmag, _t[1] / _tn * _vmag, 0.0])

VALLADO_EOP = [
    {
        "mjd": m,
        "x_arcsec": -0.140682,
        "y_arcsec": 0.333309,
        "ut1_utc_s": -0.4399619,
        "lod_s": 0.0015563,
        "dpsi_arcsec": -0.052195,
        "deps_arcsec": -0.003875,
    }
    for m in (53099, 53100, 53101, 53102, 53103)
]

LICENSE = "MIT"
COMPAT = "Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor)."
GMAT_REFS = [
    "Vallado, D. A. (2013). Fundamentals of Astrodynamics and Applications, 4th ed. Microcosm Press.",
    "Montenbruck, O. & Gill, E. (2000). Satellite Orbits. Springer.",
]

SKILLS: list[dict] = [
    {
        "name": "orbit-propagation",
        "summary": "Propagate an Earth orbit under configurable gravity and report conservation diagnostics.",
        "capabilities": ["astro.orbit-propagation", "astro.numerical-integration"],
        "body": (
            "Numerically integrates an Earth-centred orbit (MJ2000Eq) under a configurable force model "
            "(point mass, closed-form J2, or JGM-3 spherical harmonics, with optional Sun and Moon third "
            "bodies from DE421) using an embedded Runge-Kutta pair with error control. Reports the final "
            "state, step statistics and relative drift of the two-body energy and angular momentum. With "
            "`compare_analytic`, a two-body run is also compared against the exact Kepler solution.\n\n"
            "## Limitations\n\n"
            "- Earth-centred orbits only; drag, SRP, tides and relativity are not modelled.\n"
            "- `compare_analytic` is meaningful only for a point-mass (two-body) configuration."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "config": {"type": "object"},
                "elements": {"type": "object"},
                "compare_analytic": {"type": "boolean", "default": False},
            },
        },
        "outputs": {
            "type": "object",
            "required": ["final_state_km_kms", "relative_two_body_energy_drift"],
            "properties": {
                "final_state_km_kms": {"type": "array"},
                "relative_two_body_energy_drift": {"type": "number"},
                "analytic_max_position_error_m": {"type": "number"},
            },
        },
        "example": {
            "name": "leo-two-body-vs-analytic",
            "comment": "A point-mass LEO run must match the exact Kepler solution to sub-millimetre.",
            "input": {
                "config": {
                    "epoch_utc": EPOCH,
                    "initial_state": LEO,
                    "duration_s": 5400.0,
                    "output_step_s": 60.0,
                    "forces": {"earth": {"model": "point-mass"}},
                },
                "compare_analytic": True,
            },
            "expected": {"analytic_max_position_error_m": 0.0},
            "tolerance": {"abs": 0.01},
        },
        "refs": GMAT_REFS,
        "limitations": ["Earth-centred only", "no drag/SRP/tides/relativity"],
        "timeout_s": 120,
    },
    {
        "name": "kepler-reference",
        "summary": "Closed-form two-body propagation and the classical elements of the result.",
        "capabilities": ["astro.two-body", "astro.analytic-reference"],
        "body": (
            "Propagates a two-body state by the universal-variable / difference-form Kepler solution (exact, "
            "no numerical integration) and returns the resulting state and its classical orbital elements. "
            "Serves as the analytic truth other skills check against.\n\n"
            "## Limitations\n\n"
            "- Bound (elliptic) orbits; parabolic and hyperbolic arcs use the universal formulation but are "
            "not exercised here.\n- Point-mass gravity only, by definition."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "state_km_kms": {"type": "array"},
                "elements": {"type": "object"},
                "dt_s": {"type": "number"},
                "mu_km3_s2": {"type": "number"},
            },
            "required": ["dt_s"],
        },
        "outputs": {
            "type": "object",
            "required": ["final_state_km_kms", "sma_km", "eccentricity"],
            "properties": {
                "final_state_km_kms": {"type": "array"},
                "sma_km": {"type": "number"},
                "eccentricity": {"type": "number"},
                "inclination_deg": {"type": "number"},
            },
        },
        "example": {
            "name": "circular-quarter-period",
            "comment": "A circular orbit advanced a quarter period rotates 90 deg: (a,0,0) -> (0,a,0).",
            "input": {
                "state_km_kms": [7000.0, 0.0, 0.0, 0.0, VC7000, 0.0],
                "dt_s": 0.25 * 2 * math.pi * math.sqrt(7000.0**3 / MU),
            },
            "expected": {
                "final_state_km_kms": [0.0, 7000.0, 0.0, -VC7000, 0.0, 0.0],
                "sma_km": 7000.0,
                "eccentricity": 0.0,
            },
            "tolerance": {"abs": 1e-5},
        },
        "refs": GMAT_REFS,
        "limitations": ["Elliptic orbits", "point-mass gravity"],
        "timeout_s": 60,
    },
    {
        "name": "trajectory-comparison",
        "summary": "Position/velocity and radial-transverse-normal error statistics against a reference trajectory.",
        "capabilities": ["astro.trajectory-comparison"],
        "body": (
            "Propagates an orbit and reports position and velocity error norms, and the radial/transverse/"
            "normal breakdown, against a reference trajectory sampled at the same times. The reference may be "
            "an explicit array or `self` (an identity check that must return exactly zero).\n\n"
            "## Limitations\n\n"
            "- The reference must be sampled at the configuration's output times.\n"
            "- Agreement between two models is consistency, not physical validation."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "config": {"type": "object"},
                "reference": {"type": "string"},
                "reference_states": {"type": "array"},
            },
            "required": ["config"],
        },
        "outputs": {
            "type": "object",
            "required": ["max_position_error_m", "final_position_error_m"],
            "properties": {
                "max_position_error_m": {"type": "number"},
                "final_position_error_m": {"type": "number"},
                "max_velocity_error_m_s": {"type": "number"},
            },
        },
        "example": {
            "name": "identity-is-zero",
            "comment": "Comparing a trajectory with itself is the identity: every error is exactly zero.",
            "input": {
                "config": {
                    "epoch_utc": EPOCH,
                    "initial_state": LEO,
                    "duration_s": 5400.0,
                    "output_step_s": 60.0,
                    "forces": {"earth": {"model": "j2"}},
                },
                "reference": "self",
            },
            "expected": {
                "max_position_error_m": 0.0,
                "final_position_error_m": 0.0,
                "max_velocity_error_m_s": 0.0,
            },
            "tolerance": {"abs": 1e-12},
        },
        "refs": GMAT_REFS,
        "limitations": ["Reference sampled at output times", "consistency is not validation"],
        "timeout_s": 120,
    },
    {
        "name": "earth-orientation",
        "summary": "Rotate a state between MJ2000Eq and EarthFixed with the IAU-76/80 FK5 reduction.",
        "capabilities": ["astro.earth-orientation", "astro.reference-frames"],
        "body": (
            "Applies the IAU-1976 precession, IAU-1980 nutation (106 terms), IAU-1982 GMST and polar motion "
            "to rotate a state between the MJ2000Eq (GCRF/J2000) and EarthFixed (ITRF) frames at an epoch, "
            "using supplied Earth-orientation parameters. Reproduces Vallado's worked reduction.\n\n"
            "## Limitations\n\n"
            "- EOP must be supplied as daily rows spanning the epoch.\n"
            "- The 23 mas constant frame bias (ICRF vs FK5) is not applied; nutation corrections are optional."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "epoch_utc": {"type": "string"},
                "position_km": {"type": "array"},
                "velocity_km_s": {"type": ["array", "null"]},
                "eop_rows": {"type": "array"},
                "direction": {"type": "string"},
                "nutation_corrections": {"type": "boolean"},
            },
            "required": ["epoch_utc", "position_km", "eop_rows"],
        },
        "outputs": {
            "type": "object",
            "required": ["position_km", "gmst_deg"],
            "properties": {
                "position_km": {"type": "array"},
                "velocity_km_s": {"type": ["array", "null"]},
                "gmst_deg": {"type": "number"},
            },
        },
        "example": {
            "name": "vallado-itrf-to-j2000",
            "comment": "Vallado 2013 example: 2004-04-06 07:51:28.386009 UTC, ITRF -> GCRF/J2000 (published).",
            "input": {
                "epoch_utc": "2004-04-06T07:51:28.386009",
                "position_km": [-1033.4793830, 7901.2952754, 6380.3565958],
                "velocity_km_s": [-3.225636520, -2.872451450, 5.531924446],
                "eop_rows": VALLADO_EOP,
                "direction": "fixed_to_inertial",
                "nutation_corrections": True,
            },
            "expected": {
                "position_km": [5102.508959, 6123.011403, 6378.136925],
                "velocity_km_s": [-4.743220156, 0.790536497, 5.533755728],
                "gmst_deg": 312.8098943,
            },
            "tolerance": {"rel": 1e-7},
        },
        "refs": GMAT_REFS,
        "limitations": ["EOP must be supplied", "no constant frame bias"],
        "timeout_s": 60,
    },
    {
        "name": "tracking-simulation",
        "summary": "Synthetic range and range-rate of an orbit from ground stations.",
        "capabilities": ["astro.tracking-simulation", "astro.measurements"],
        "body": (
            "Generates noiseless range and range-rate observations of an orbit from ground stations above a "
            "minimum elevation, using the station's inertial position and velocity (Earth rotation). The "
            "measurement geometry follows Vallado chapter 4.\n\n"
            "## Limitations\n\n"
            "- Range and range-rate only (no angles); light-time and tropospheric effects are not modelled.\n"
            "- Visibility uses a simple elevation mask."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "initial_state_km_kms": {"type": "array"},
                "stations": {"type": "array"},
                "times_s": {"type": "array"},
                "model": {"type": "string"},
            },
            "required": ["initial_state_km_kms", "stations", "times_s"],
        },
        "outputs": {
            "type": "object",
            "required": ["num_observations"],
            "properties": {
                "num_observations": {"type": "integer"},
                "first_range_km": {"type": ["number", "null"]},
                "first_range_rate_km_s": {"type": ["number", "null"]},
            },
        },
        "example": {
            "name": "overhead-pass",
            "comment": "A satellite 1000 km radially above a station with tangential velocity: "
            "range = altitude (1000 km) exactly and range-rate = 0, independent of the frame.",
            "input": {
                "model": "point-mass",
                "initial_state_km_kms": TRACK_STATE,
                "stations": [{"name": "s", "lat_deg": 35.0, "lon_deg": -116.0, "height_km": 0.0}],
                "times_s": [0.0],
            },
            "expected": {"num_observations": 1, "first_range_km": 1000.0, "first_range_rate_km_s": 0.0},
            "tolerance": {"abs": 1e-6},
        },
        "refs": GMAT_REFS,
        "limitations": ["Range and range-rate only", "simple elevation mask"],
        "timeout_s": 60,
    },
    {
        "name": "orbit-determination",
        "summary": "Batch least-squares orbit determination from synthetic tracking.",
        "capabilities": ["astro.orbit-determination", "astro.estimation"],
        "body": (
            "Recovers an epoch state from range and range-rate tracking by iterated batch least squares with "
            "the state-transition matrix from the force model. On noiseless data this is an identical-twin "
            "experiment: the estimate must return to the truth to the numerical floor.\n\n"
            "## Limitations\n\n"
            "- Needs an observable arc; a short single-station arc leaves a weakly observed direction.\n"
            "- The dynamics used to simulate and to estimate are the same (a closed experiment)."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "truth_state_km_kms": {"type": "array"},
                "stations": {"type": "array"},
                "times_s": {"type": "array"},
                "sigma": {"type": "array"},
                "noisy": {"type": "boolean"},
                "model": {"type": "string"},
            },
            "required": ["truth_state_km_kms", "stations", "times_s"],
        },
        "outputs": {
            "type": "object",
            "required": ["converged", "position_error_m"],
            "properties": {
                "converged": {"type": "boolean"},
                "position_error_m": {"type": "number"},
                "velocity_error_m_s": {"type": "number"},
            },
        },
        "example": {
            "name": "noiseless-recovery",
            "comment": "Noiseless identical-twin data over a 12-hour, three-station arc recovers the truth "
            "state to well under a metre.",
            "input": {
                "model": "j2",
                "truth_state_km_kms": OD_TRUTH,
                "stations": [
                    {"name": "g", "lat_deg": 35.3, "lon_deg": -116.9, "height_km": 1.0},
                    {"name": "c", "lat_deg": -35.4, "lon_deg": 149.0, "height_km": 0.7},
                    {"name": "m", "lat_deg": 40.4, "lon_deg": -4.2, "height_km": 0.8},
                ],
                "times_s": list(range(0, 12 * 3600 + 1, 60)),
                "noisy": False,
            },
            "expected": {"converged": True, "position_error_m": 0.0},
            "tolerance": {"abs": 0.5},
        },
        "refs": GMAT_REFS,
        "limitations": ["Needs an observable arc", "closed identical-twin experiment"],
        "timeout_s": 300,
    },
    {
        "name": "covariance-propagation",
        "summary": "Propagate a state covariance through the STM and check it against a Monte-Carlo cloud.",
        "capabilities": ["astro.covariance-propagation", "astro.uncertainty"],
        "body": (
            "Maps an initial covariance to a later time through the state-transition matrix and compares it "
            "against a cloud of samples propagated by the analytic Kepler solution. For a small (near-linear) "
            "initial uncertainty the chi-square consistency fraction should sit near 0.95.\n\n"
            "## Limitations\n\n"
            "- The linear map is first-order; large uncertainties show nonlinearity (lower consistency).\n"
            "- Point-mass dynamics for the Monte-Carlo cloud."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "state_km_kms": {"type": "array"},
                "elements": {"type": "object"},
                "sigma0": {"type": "array"},
                "dt_s": {"type": "number"},
                "samples": {"type": "integer"},
                "seed": {"type": "integer"},
            },
            "required": ["sigma0", "dt_s"],
        },
        "outputs": {
            "type": "object",
            "required": ["chi2_95_inside_fraction"],
            "properties": {
                "chi2_95_inside_fraction": {"type": "number"},
                "position_block_rel_diff": {"type": "number"},
                "mean_offset_m": {"type": "number"},
            },
        },
        "example": {
            "name": "small-uncertainty-consistency",
            "comment": "A small covariance mapped linearly through the STM is chi-square consistent with a "
            "Kepler Monte-Carlo cloud (~95% of samples inside the 95% ellipsoid).",
            "input": {
                "state_km_kms": [7000.0, 0.0, 0.0, 0.0, VC7000 * 0.99, VC7000 * 0.14],
                "sigma0": [0.1, 0.1, 0.1, 1e-4, 1e-4, 1e-4],
                "dt_s": 3000.0,
                "samples": 2000,
                "seed": 7,
            },
            "expected": {"chi2_95_inside_fraction": 0.95},
            "tolerance": {"abs": 0.04},
        },
        "refs": GMAT_REFS,
        "limitations": ["First-order linear map", "point-mass Monte-Carlo"],
        "timeout_s": 120,
    },
    {
        "name": "nbody-integration",
        "summary": "Integrate a self-gravitating N-body system (figure-eight choreography or a DE421 subset).",
        "capabilities": ["astro.nbody", "astro.numerical-integration"],
        "body": (
            "Integrates a self-gravitating system of point masses. The `figure-eight` system is the "
            "Chenciner-Montgomery equal-mass three-body choreography, whose return to its initial "
            "configuration after one period and conservation of energy, momentum and barycentre are exacting "
            "tests. The `de421` system integrates the major bodies from JPL DE421 initial conditions and "
            "compares back against the ephemeris.\n\n"
            "## Limitations\n\n"
            "- Newtonian point masses; no relativity, oblateness or asteroid perturbations (the DE421 "
            "residual).\n- `return_error` is defined only for a whole number of periods."
        ),
        "inputs": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "system": {"type": "string"},
                "periods": {"type": "number"},
                "bodies": {"type": "array"},
                "duration_s": {"type": "number"},
            },
        },
        "outputs": {
            "type": "object",
            "required": ["relative_energy_drift"],
            "properties": {
                "return_error": {"type": ["number", "null"]},
                "relative_energy_drift": {"type": "number"},
                "angular_momentum_drift": {"type": "number"},
            },
        },
        "example": {
            "name": "figure-eight-one-period",
            "comment": "After one period the figure-eight returns to its start and conserves energy and "
            "angular momentum (a published periodic solution).",
            "input": {"system": "figure-eight", "periods": 1},
            "expected": {"return_error": 0.0, "relative_energy_drift": 0.0, "angular_momentum_drift": 0.0},
            "tolerance": {"abs": 1e-5},
        },
        "refs": [
            "Chenciner, A. & Montgomery, R. (2000). A remarkable periodic solution of the three-body problem. "
            "Ann. Math. 152, 881-901.",
            "Standish, E. M. (2009). JPL planetary ephemeris DE421. JPL IOM 343R-08-003.",
        ],
        "limitations": ["Newtonian point masses", "return_error needs whole periods"],
        "timeout_s": 120,
    },
]

RUN_PY = '''"""Astrodynamics skill: {name} (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: {name}")
    return DISPATCH["{name}"](inputs)
'''


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8", newline="\n")


def skill_md(spec: dict) -> str:
    return (
        "---\n"
        f"name: {spec['name']}\n"
        f"description: {spec['summary']} Use for {spec['capabilities'][0].split('.')[-1]} tasks in the "
        "ORRERY orbital-dynamics engine.\n"
        f"license: {LICENSE}\n"
        f"compatibility: {COMPAT}\n"
        "metadata:\n"
        '  version: "1.0.0"\n'
        "  domain: astrodynamics\n"
        "---\n"
        f"# {spec['name'].replace('-', ' ').title()}\n\n"
        f"{spec['body']}\n"
    )


def skill_json(spec: dict) -> str:
    ex = spec["example"]
    payload = {
        "schema": "atlas.skill/v1",
        "name": spec["name"],
        "version": "1.0.0",
        "kind": "executable",
        "domain": "astrodynamics",
        "summary": spec["summary"],
        "capabilities": spec["capabilities"],
        "entrypoint": "run.py",
        "determinism": "deterministic",
        "inputs": spec["inputs"],
        "outputs": spec["outputs"],
        "permissions": {"network": False, "subprocess": False, "read": ["inputs"], "write": ["outputs"]},
        "limits": {"timeout_s": spec["timeout_s"], "memory_mb": 2048},
        "requires": {
            "python": ">=3.11",
            "packages": {"numpy": ">=2.0", "scipy": ">=1.13", "rain-atlas": ">=0.1"},
        },
        "examples": [{"name": ex["name"], "tolerance": ex["tolerance"]}],
        "references": spec["refs"],
        "limitations": spec["limitations"],
    }
    return json.dumps(payload, indent=2)


def main() -> None:
    for spec in SKILLS:
        base = OUT / spec["name"]
        write(base / "SKILL.md", skill_md(spec))
        write(base / "skill.json", skill_json(spec))
        write(base / "run.py", RUN_PY.format(name=spec["name"]))
        ex = spec["example"]
        write(base / "examples" / f"{ex['name']}.input.json", json.dumps(ex["input"], indent=2))
        expected = {"$comment": ex["comment"], **ex["expected"]}
        write(base / "examples" / f"{ex['name']}.expected.json", json.dumps(expected, indent=2))
        print(f"wrote skills/astrodynamics/{spec['name']}")


if __name__ == "__main__":
    main()
