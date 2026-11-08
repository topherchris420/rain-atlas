"""ORRERY vs committed NASA GMAT R2026a reference trajectories (code-to-code agreement).

These compare two independent implementations. Agreement bounds code-to-code
consistency; it is not a claim of physical validation (see docs/ORRERY_VALIDATION.md).
The reference records were produced by scripts/make_orrery_references.py and carry
the GMAT executable and data-file hashes used.
"""

import pytest

from rain_atlas.orrery import gmat, scenarios
from rain_atlas.orrery.propagate import position_velocity_errors, propagate

# Max position error (m) allowed vs GMAT, with margin over the observed agreement.
TOL_POS_M = {
    "S4-leo-j2": 0.5,
    "S5-heo-j2": 5.0,
    "S6-geo-j2-sun-moon": 2.0,
    "S7-leo-jgm3-8x8": 0.5,
    "S8-earth-moon-tli": 1.0,
}
AVAILABLE = [n for n in scenarios.GMAT_SCENARIOS if (gmat.REFERENCE_DIR / f"{n}.json").exists()]


def test_reference_files_present():
    assert set(AVAILABLE) == set(scenarios.GMAT_SCENARIOS), "run scripts/make_orrery_references.py"


@pytest.mark.slow
@pytest.mark.parametrize("name", AVAILABLE)
def test_matches_gmat_reference(name):
    record = gmat.load_reference(name)
    ref = gmat.reference_arrays(record)
    cfg = dict(scenarios.scenario(name)["config"])
    cfg["output_times_s"] = ref["elapsed_s"].tolist()
    cfg.setdefault("integrator", {"method": "rkf78", "rtol": 1e-12, "atol": 1e-12})
    traj = propagate(cfg)
    err = position_velocity_errors(traj.states, ref["mj2000"])
    assert err["max_position_error_m"] < TOL_POS_M[name]


@pytest.mark.parametrize("name", AVAILABLE)
def test_reference_records_carry_provenance(name):
    record = gmat.load_reference(name)
    assert record["gmat"]["version"] == "R2026a"
    assert any("de421" in k for k in record["gmat"]["files"])
    assert record["script_sha256"].startswith("sha256:")
    assert len(record["rows"]) > 0
