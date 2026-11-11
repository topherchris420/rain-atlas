"""The committed reference-data excerpts load and carry source provenance."""

import json
from pathlib import Path

import pytest

from rain_atlas.orrery.eop import EopTable
from rain_atlas.orrery.ephemeris import Ephemeris, FrameTie
from rain_atlas.orrery.forces import load_gravity_field

DATA = Path(__file__).resolve().parents[1] / "src" / "rain_atlas" / "orrery" / "data"
DATA_FILES = [
    "leap_seconds.json",
    "nutation_iau1980.json",
    "eop_c04_2026.json",
    "jgm3_8x8.json",
    "de421_2026.json",
    "icrf_fk5_gmat_2026.json",
]


@pytest.mark.parametrize("name", DATA_FILES)
def test_data_file_is_lf_utf8_json(name):
    raw = (DATA / name).read_bytes()
    assert b"\r" not in raw
    json.loads(raw.decode("utf-8"))


@pytest.mark.parametrize("name", ["eop_c04_2026", "jgm3_8x8", "de421_2026", "icrf_fk5_gmat_2026"])
def test_source_provenance_recorded(name):
    payload = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
    source = payload["source"]
    assert source["sha256"].startswith("sha256:")
    assert "GMAT R2026a" in source["distribution"]


def test_gravity_field_loads():
    field = load_gravity_field("jgm3_8x8")
    assert field["C"][2, 0] < 0  # oblate Earth
    assert field["C"].shape[0] >= 9


def test_ephemeris_covers_epoch():
    eph = Ephemeris.load("de421_2026")
    cov = eph.coverage()
    assert cov is not None


def test_eop_and_icrf_tables_load():
    assert len(EopTable.load("eop_c04_2026").mjd) > 30
    assert FrameTie("gmat-icrf-table").source is not None
