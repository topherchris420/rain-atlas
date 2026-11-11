"""Time-scale conversions against documented offsets and round trips."""

import pytest

from rain_atlas.orrery.timescales import Epoch, gregorian_to_mjd, mjd_to_gregorian

SCALES = ["UTC", "TAI", "TT", "TDB", "A1"]


def _offset(a, b):
    """Reading of epoch a minus epoch b (s), kept exact via the day split for close MJDs."""

    return (a.mjd - b.mjd) * 86400.0 + (a.sec - b.sec)


def _utc_diff(a, b):
    """Elapsed seconds between two UTC epochs, counting any leap second in between."""

    return _offset(a.to("TAI"), b.to("TAI"))


def test_tt_tai_offset_is_exact():
    tai = Epoch.from_iso("TAI", "2026-01-15T00:00:00")
    assert _offset(tai.to("TT"), tai) == pytest.approx(32.184, abs=1e-9)


def test_a1_tai_offset_is_exact():
    tai = Epoch.from_iso("TAI", "2026-01-15T00:00:00")
    assert _offset(tai.to("A1"), tai) == pytest.approx(0.0343817, abs=1e-9)


def test_leap_seconds_2026_is_37():
    # TAI - UTC = 37 s since 2017-01-01; no leap second has been added since.
    utc = Epoch.from_iso("UTC", "2026-01-15T00:00:00")
    assert _offset(utc.to("TAI"), utc) == pytest.approx(37.0, abs=1e-9)


def test_tdb_tt_offset_is_sub_millisecond():
    tt = Epoch.from_iso("TT", "2026-01-15T00:00:00")
    assert abs(_offset(tt.to("TDB"), tt)) < 2e-3


@pytest.mark.parametrize("scale", SCALES)
def test_round_trip_through_tai(scale):
    base = Epoch.from_iso("UTC", "2026-01-15T12:34:56.789")
    back = base.to(scale).to("UTC")
    assert abs(_utc_diff(back, base)) < 1e-6


def test_gregorian_mjd_round_trip():
    for y, mo, d in [(2000, 1, 1), (2026, 1, 15), (2004, 4, 6), (1962, 1, 1)]:
        mjd = gregorian_to_mjd(y, mo, d)
        assert mjd_to_gregorian(mjd) == (y, mo, d)


def test_centuries_since_j2000_matches_vallado():
    # Vallado 2013 example 3-15: 2004-04-06 07:51:28.386009 UTC, dUT1 given.
    # T_TT = 0.0426236319 (published).
    tt = Epoch.from_iso("UTC", "2004-04-06T07:51:28.386009").to("TT")
    assert tt.centuries_since_j2000() == pytest.approx(0.0426236319, abs=5e-10)


def test_gmat_gregorian_format():
    assert Epoch.from_iso("UTC", "2026-01-15T00:00:00").gmat_gregorian() == "15 Jan 2026 00:00:00.000"


def test_gmat_modjulian_round_trip():
    e = Epoch.from_iso("TAI", "2026-01-15T06:00:00")
    back = Epoch.from_gmat_modjulian("TAI", e.gmat_modjulian())
    assert back.seconds_since(e) == pytest.approx(0.0, abs=1e-6)


def test_ut1_round_trip_with_eop():
    from rain_atlas.orrery.eop import EopTable

    eop = EopTable.load("eop_c04_2026")
    base = Epoch.from_iso("UTC", "2026-01-15T12:34:56.789")
    back = base.to("UT1", eop).to("UTC", eop)
    assert abs(_utc_diff(back, base)) < 1e-6
