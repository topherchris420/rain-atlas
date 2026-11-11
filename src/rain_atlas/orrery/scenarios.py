"""The ORRERY validation scenarios: frozen initial conditions and model configurations.

All Earth-orbit epochs are 2026-01-15 00:00:00 UTC. Cartesian initial states
(MJ2000Eq, km and km/s) are frozen literals so that the ORRERY propagation and
the GMAT reference run use byte-identical numbers; the Keplerian elements they
were built from (via :func:`kepler.elements_to_state` with the GMAT mu) are
recorded alongside for readability. Each scenario names its truth source:

``analytic``  - closed-form Kepler/universal-variable solution (two-body only);
``gmat``      - NASA GMAT R2026a reference run (see :mod:`.gmat`);
``ephemeris`` - the DE421 ephemeris itself (N-body solar system);
``periodic``  - a published periodic solution (figure-eight choreography).

Classes covered: LEO, Molniya/HEO, GEO, an Earth-Moon transfer coast, the
solar system over one year, and the equal-mass three-body figure eight.
"""

from __future__ import annotations

import math

EPOCH = "2026-01-15T00:00:00"

# Frozen Cartesian initial states (MJ2000Eq), built from the elements noted in each comment.
_IC = {
    # a=6778.137 km (h~400 km), e=0.001, i=51.6 deg, raan=30, argp=40, nu=0
    "leo": [
        3140.426905642162,
        4934.9447007026465,
        3411.0614920951393,
        -6.099408469974278,
        0.6961135686551336,
        4.608379103488943,
    ],
    # a=26600 km, e=0.74, i=63.4 deg, raan=90, argp=270, nu=0 (Molniya)
    "molniya": [3096.7018514929314, 0.0, -6183.97070198107, 0.0, 10.014194438691925, 0.0],
    # a=42164 km, e=1e-4, i=0.1 deg, raan=0, argp=0, nu=0 (GEO)
    "geo": [42159.783599999995, 0.0, 0.0, 0.0, 3.07496908152212, 0.005366838936401897],
    # a=24371 km, e=0.73, i=28.5 deg, raan=45, argp=180, nu=0 (HEO/GTO-like)
    "heo": [
        -4652.882828360287,
        -4652.882828360285,
        0.0,
        6.361461301465807,
        -6.36146130146581,
        -4.884681866385586,
    ],
    # Trans-lunar injection, frozen by transfers.design_lunar_transfer (closest Moon approach 1e4 km ~5 d)
    "tli": [
        -4598.538761978727,
        4192.727294601475,
        2085.4824813602854,
        -7.789092016475628,
        -6.628989855329616,
        -3.8479799892977837,
    ],
}

_DAY = 86400.0

SCENARIOS: dict[str, dict] = {
    "S1-leo-twobody": {
        "name": "S1-leo-twobody",
        "title": "LEO two-body (400 km, 51.6 deg), 1 day",
        "truth": "analytic",
        "orbit_class": "LEO",
        "elements": {
            "sma_km": 6778.137,
            "ecc": 0.001,
            "inc_deg": 51.6,
            "raan_deg": 30,
            "argp_deg": 40,
            "ta_deg": 0,
        },
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["leo"],
            "duration_s": _DAY,
            "output_step_s": 60.0,
            "forces": {"constants": "gmat", "earth": {"model": "point-mass"}},
        },
    },
    "S2-molniya-twobody": {
        "name": "S2-molniya-twobody",
        "title": "Molniya two-body (e=0.74, 63.4 deg), 2 days",
        "truth": "analytic",
        "orbit_class": "HEO",
        "elements": {
            "sma_km": 26600.0,
            "ecc": 0.74,
            "inc_deg": 63.4,
            "raan_deg": 90,
            "argp_deg": 270,
            "ta_deg": 0,
        },
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["molniya"],
            "duration_s": 2 * _DAY,
            "output_step_s": 120.0,
            "forces": {"constants": "gmat", "earth": {"model": "point-mass"}},
        },
    },
    "S3-geo-twobody": {
        "name": "S3-geo-twobody",
        "title": "GEO two-body, 7 days",
        "truth": "analytic",
        "orbit_class": "GEO",
        "elements": {
            "sma_km": 42164.0,
            "ecc": 1e-4,
            "inc_deg": 0.1,
            "raan_deg": 0,
            "argp_deg": 0,
            "ta_deg": 0,
        },
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["geo"],
            "duration_s": 7 * _DAY,
            "output_step_s": 300.0,
            "forces": {"constants": "gmat", "earth": {"model": "point-mass"}},
        },
    },
    "S4-leo-j2": {
        "name": "S4-leo-j2",
        "title": "LEO with J2 (EarthFixed), 1 day",
        "truth": "gmat",
        "orbit_class": "LEO",
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["leo"],
            "duration_s": _DAY,
            "output_step_s": 60.0,
            "forces": {"constants": "gmat", "earth": {"model": "j2", "pole": "earth-fixed"}},
        },
    },
    "S5-heo-j2": {
        "name": "S5-heo-j2",
        "title": "HEO with J2 (EarthFixed), 2 days",
        "truth": "gmat",
        "orbit_class": "HEO",
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["heo"],
            "duration_s": 2 * _DAY,
            "output_step_s": 120.0,
            "forces": {"constants": "gmat", "earth": {"model": "j2", "pole": "earth-fixed"}},
        },
    },
    "S6-geo-j2-sun-moon": {
        "name": "S6-geo-j2-sun-moon",
        "title": "GEO with J2, Sun and Moon (DE421), 7 days",
        "truth": "gmat",
        "orbit_class": "GEO",
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["geo"],
            "duration_s": 7 * _DAY,
            "output_step_s": 300.0,
            "forces": {
                "constants": "gmat",
                "earth": {"model": "j2", "pole": "earth-fixed"},
                "third_bodies": ["moon", "sun"],
            },
        },
    },
    "S7-leo-jgm3-8x8": {
        "name": "S7-leo-jgm3-8x8",
        "title": "LEO with JGM-3 8x8 geopotential, 1 day",
        "truth": "gmat",
        "orbit_class": "LEO",
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["leo"],
            "duration_s": _DAY,
            "output_step_s": 60.0,
            "forces": {
                "constants": "gmat",
                "earth": {"model": "harmonics", "field": "jgm3_8x8", "degree": 8, "order": 8},
            },
        },
    },
    "S8-earth-moon-tli": {
        "name": "S8-earth-moon-tli",
        "title": "Earth-Moon transfer coast with J2, Sun and Moon, 6 days",
        "truth": "gmat",
        "orbit_class": "cislunar",
        "note": "ICs frozen by transfers.design_lunar_transfer; closest Moon approach ~1e4 km near t=5 d",
        "config": {
            "epoch_utc": EPOCH,
            "initial_state": _IC["tli"],
            "duration_s": 6 * _DAY,
            "output_step_s": 600.0,
            "forces": {
                "constants": "gmat",
                "earth": {"model": "j2", "pole": "earth-fixed"},
                "third_bodies": ["moon", "sun"],
            },
            "integrator": {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12},
        },
    },
}

# N-body scenarios (handled by nbody.py, not the Earth-centred force model).
NBODY_SCENARIOS = {
    "S9-solar-system-de421": {
        "name": "S9-solar-system-de421",
        "title": "Solar-system N-body vs DE421, 1 year",
        "truth": "ephemeris",
        "epoch_utc": EPOCH,
        "bodies": [
            "sun",
            "mercury-barycenter",
            "venus-barycenter",
            "earth",
            "moon",
            "mars-barycenter",
            "jupiter-barycenter",
            "saturn-barycenter",
            "uranus-barycenter",
            "neptune-barycenter",
        ],
        "center": "ssb",
        "duration_s": 365.0 * _DAY,
        "output_step_s": 5.0 * _DAY,
    },
    "S10-figure-eight": {
        "name": "S10-figure-eight",
        "title": "Chenciner-Montgomery figure-eight three-body choreography, 1 period",
        "truth": "periodic",
        "periods": 1,
        "output_points": 200,
    },
}

GMAT_SCENARIOS = [k for k, v in SCENARIOS.items() if v["truth"] == "gmat"]
ANALYTIC_SCENARIOS = [k for k, v in SCENARIOS.items() if v["truth"] == "analytic"]
ALL_SCENARIOS = {**SCENARIOS, **NBODY_SCENARIOS}


def gmat_body_positions(scenario: dict) -> list[str]:
    names = {"moon": "Luna", "sun": "Sun"}
    return [names[b] for b in scenario["config"]["forces"].get("third_bodies", [])]


def scenario(name: str) -> dict:
    if name not in ALL_SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(ALL_SCENARIOS)}")
    return ALL_SCENARIOS[name]


def rebuild_frozen_ics() -> dict:
    """Rebuild the Keplerian ICs from their elements; used by a test to pin the frozen literals."""

    from .constants import GMAT_EARTH_MU  # noqa: PLC0415
    from .kepler import elements_to_state  # noqa: PLC0415

    out = {}
    for key, name in (
        ("S1-leo-twobody", "leo"),
        ("S2-molniya-twobody", "molniya"),
        ("S3-geo-twobody", "geo"),
    ):
        el = SCENARIOS[key]["elements"]
        r, v = elements_to_state(
            el["sma_km"],
            el["ecc"],
            math.radians(el["inc_deg"]),
            math.radians(el["raan_deg"]),
            math.radians(el["argp_deg"]),
            math.radians(el["ta_deg"]),
            GMAT_EARTH_MU,
        )
        out[name] = list(r) + list(v)
    return out
