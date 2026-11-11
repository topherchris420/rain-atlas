"""Time scales and epochs.

An :class:`Epoch` is an instant on a named scale, stored as an integer Modified
Julian Day and seconds since 0h of that day. Seconds of day are kept separate
from the day count so that a double carries ~1e-11 s resolution instead of the
~1e-5 s a single Julian-date double would give.

Scales and the relations used (all documented in docs/ORRERY.md, section 2):

* ``TAI`` - International Atomic Time; the uniform base scale.
* ``UTC`` - TAI - DeltaAT, with DeltaAT from the IERS/USNO table
  (``data/leap_seconds.json``, generated from the ``tai-utc.dat`` file shipped
  with GMAT R2026a). Before 1972 the table's linear drift terms are applied.
  A UTC epoch may carry ``sec`` in [86400, 86401) during an inserted leap second.
* ``TT``  - TAI + 32.184 s (IAU 1991).
* ``A1``  - TAI + 0.0343817 s (USNO A.1; GMAT's internal scale).
* ``TDB`` - TT + 0.001658 sin(M) + 0.00001385 sin(2M), M = 357.5277233 deg +
  35999.05034 deg * T_TT. This is the two-term approximation GMAT R2026a uses
  (TimeSystemConverter.cpp); its error against the full Fairhead-Bretagnon
  series is a few tens of microseconds. TDB -> TT inverts it by fixed-point
  iteration.
* ``UT1`` - UTC + (UT1-UTC) from an :class:`~rain_atlas.orrery.eop.EopTable`.

Arithmetic (``plus_seconds``) is defined only on uniform scales; UTC is
converted through TAI so leap seconds are never lost.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .constants import (
    A1_MINUS_TAI_S,
    DAYS_PER_JULIAN_CENTURY,
    GMAT_MODJULIAN_OFFSET,
    MJD_OFFSET,
    SECONDS_PER_DAY,
    TT_MINUS_TAI_S,
)

SCALES = ("UTC", "TAI", "TT", "TDB", "A1", "UT1")
UNIFORM = ("TAI", "TT", "TDB", "A1", "UT1")
MJD_J2000 = 51544  # integer part; J2000.0 is MJD 51544.5 TT
DATA = Path(__file__).resolve().parent / "data"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@lru_cache(maxsize=1)
def leap_second_table() -> tuple[tuple[int, float, float, float], ...]:
    """Rows ``(utc_mjd_start, offset_s, reference_mjd, rate_s_per_day)``, ascending."""

    payload = json.loads((DATA / "leap_seconds.json").read_text(encoding="utf-8"))
    rows = tuple(
        (int(r["utc_mjd"]), float(r["offset_s"]), float(r["ref_mjd"]), float(r["rate_s_per_day"]))
        for r in payload["rows"]
    )
    if list(rows) != sorted(rows):
        raise ValueError("leap-second table is not sorted")
    return rows


def delta_at(utc_mjd: int, utc_sec: float = 0.0) -> float:
    """TAI - UTC in seconds at a UTC instant (table rows start at 0h UTC)."""

    rows = leap_second_table()
    if utc_mjd < rows[0][0]:
        raise ValueError("epoch precedes the first TAI-UTC table entry (1961-01-01)")
    row = rows[0]
    for candidate in rows:
        if candidate[0] <= utc_mjd:
            row = candidate
        else:
            break
    _, offset, ref, rate = row
    return offset + (utc_mjd + min(utc_sec, SECONDS_PER_DAY) / SECONDS_PER_DAY - ref) * rate


def gregorian_to_mjd(year: int, month: int, day: int) -> int:
    """Integer MJD of 0h on a proleptic Gregorian date (Fliegel-Van Flandern algorithm)."""

    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn - 2400001


def mjd_to_gregorian(mjd: int) -> tuple[int, int, int]:
    jdn = mjd + 2400001
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


@dataclass(frozen=True)
class Epoch:
    """An instant on ``scale``: integer MJD day plus seconds since 0h of that day."""

    scale: str
    mjd: int
    sec: float

    def __post_init__(self):
        if self.scale not in SCALES:
            raise ValueError(f"unknown time scale {self.scale!r}; expected one of {SCALES}")
        limit = SECONDS_PER_DAY + (1.0 if self.scale == "UTC" else 0.0)
        if not (0.0 <= self.sec < limit) or not math.isfinite(self.sec):
            raise ValueError("seconds of day out of range; use Epoch.normalized")

    # construction -------------------------------------------------------
    @staticmethod
    def normalized(scale: str, mjd: int, sec: float) -> Epoch:
        if scale == "UTC" and 0.0 <= sec < SECONDS_PER_DAY + 1.0:
            return Epoch(scale, int(mjd), float(sec))
        days = math.floor(sec / SECONDS_PER_DAY)
        sec = sec - days * SECONDS_PER_DAY
        if sec >= SECONDS_PER_DAY:  # rounding at the boundary
            sec -= SECONDS_PER_DAY
            days += 1
        return Epoch(scale, int(mjd) + int(days), float(sec))

    @staticmethod
    def from_calendar(
        scale: str, year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: float = 0.0
    ) -> Epoch:
        return Epoch(scale, gregorian_to_mjd(year, month, day), hour * 3600.0 + minute * 60.0 + second)

    @staticmethod
    def from_iso(scale: str, text: str) -> Epoch:
        """Parse ``YYYY-MM-DDTHH:MM:SS(.fff)``."""

        date, _, clock = text.strip().partition("T")
        y, mo, d = (int(x) for x in date.split("-"))
        hh, mm, ss = (clock or "00:00:00").split(":")
        return Epoch.from_calendar(scale, y, mo, d, int(hh), int(mm), float(ss))

    @staticmethod
    def from_jd(scale: str, jd1: float, jd2: float = 0.0) -> Epoch:
        mjd_whole = math.floor(jd1 - MJD_OFFSET)
        frac = (jd1 - MJD_OFFSET - mjd_whole) + jd2
        return Epoch.normalized(scale, mjd_whole, frac * SECONDS_PER_DAY)

    @staticmethod
    def from_gmat_modjulian(scale: str, value: float) -> Epoch:
        """GMAT ModJulian = JD - 2430000.0 (day boundary at 12:00)."""

        return Epoch.from_jd(scale, GMAT_MODJULIAN_OFFSET, value)

    # representation -----------------------------------------------------
    def jd(self) -> tuple[float, float]:
        """Two-part Julian date ``(whole + 0.5 offset, fraction)``."""

        return self.mjd + MJD_OFFSET, self.sec / SECONDS_PER_DAY

    def mjd_float(self) -> float:
        return self.mjd + self.sec / SECONDS_PER_DAY

    def gmat_modjulian(self) -> float:
        return (self.mjd + MJD_OFFSET - GMAT_MODJULIAN_OFFSET) + self.sec / SECONDS_PER_DAY

    def centuries_since_j2000(self) -> float:
        """Julian centuries from J2000.0 on this epoch's own scale."""

        return ((self.mjd - MJD_J2000) + (self.sec / SECONDS_PER_DAY - 0.5)) / DAYS_PER_JULIAN_CENTURY

    def calendar(self) -> tuple[int, int, int, int, int, float]:
        y, mo, d = mjd_to_gregorian(self.mjd)
        sec = self.sec
        if sec >= SECONDS_PER_DAY:  # UTC leap second shown as 23:59:60.x
            return y, mo, d, 23, 59, 60.0 + (sec - SECONDS_PER_DAY)
        hour = int(sec // 3600)
        minute = int((sec - hour * 3600) // 60)
        return y, mo, d, hour, minute, sec - hour * 3600 - minute * 60

    def iso(self, digits: int = 6) -> str:
        y, mo, d, h, mi, s = self.calendar()
        width = 3 + digits if digits else 2
        return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:0{width}.{digits}f}"

    def gmat_gregorian(self) -> str:
        """GMAT's Gregorian epoch string, e.g. ``15 Jan 2026 00:00:00.000``."""

        y, mo, d, h, mi, s = self.calendar()
        return f"{d:02d} {_MONTHS[mo - 1]} {y:04d} {h:02d}:{mi:02d}:{s:06.3f}"

    # arithmetic ---------------------------------------------------------
    def plus_seconds(self, seconds: float) -> Epoch:
        if self.scale not in UNIFORM:
            raise ValueError("arithmetic on UTC is ambiguous across leap seconds; convert to TAI first")
        whole = math.floor(seconds)
        return Epoch.normalized(self.scale, self.mjd, (self.sec + (seconds - whole)) + whole)

    def seconds_since(self, other: Epoch) -> float:
        if self.scale != other.scale or self.scale not in UNIFORM:
            raise ValueError("differences require two epochs on the same uniform scale")
        return (self.mjd - other.mjd) * SECONDS_PER_DAY + (self.sec - other.sec)

    # conversion ---------------------------------------------------------
    def to(self, scale: str, eop=None) -> Epoch:
        if scale == self.scale:
            return self
        return _from_tai(_to_tai(self, eop), scale, eop)


def tdb_minus_tt(tt: Epoch) -> float:
    """GMAT R2026a two-term TDB - TT approximation (seconds)."""

    t = tt.centuries_since_j2000()
    m = math.radians(357.5277233 + 35999.05034 * t)
    return 0.001658 * math.sin(m) + 0.00001385 * math.sin(2.0 * m)


def _shift(epoch: Epoch, scale: str, seconds: float) -> Epoch:
    return Epoch.normalized(scale, epoch.mjd, epoch.sec + seconds)


def _to_tai(epoch: Epoch, eop) -> Epoch:
    s = epoch.scale
    if s == "TAI":
        return epoch
    if s == "TT":
        return _shift(epoch, "TAI", -TT_MINUS_TAI_S)
    if s == "A1":
        return _shift(epoch, "TAI", -A1_MINUS_TAI_S)
    if s == "TDB":
        tt = Epoch("TT", epoch.mjd, epoch.sec)
        for _ in range(4):  # fixed point: |d(TDB-TT)/dt| ~ 3e-10
            tt = _shift(epoch, "TT", -tdb_minus_tt(tt))
        return _to_tai(tt, eop)
    if s == "UTC":
        return Epoch.normalized("TAI", epoch.mjd, epoch.sec + delta_at(epoch.mjd, epoch.sec))
    if s == "UT1":
        if eop is None:
            raise ValueError("UT1 conversions require Earth orientation parameters")
        utc = Epoch.normalized("UTC", epoch.mjd, epoch.sec)
        for _ in range(4):
            utc = Epoch.normalized("UTC", epoch.mjd, epoch.sec - eop.ut1_minus_utc(utc))
        return _to_tai(utc, eop)
    raise AssertionError(s)


def _tai_to_utc(tai: Epoch) -> Epoch:
    rows = leap_second_table()
    seconds = tai.mjd * SECONDS_PER_DAY + tai.sec
    # Integer-offset era (from 1972): each row begins at 0h UTC of its day.
    for i in range(len(rows) - 1, -1, -1):
        start_mjd, offset, _, rate = rows[i]
        if rate != 0.0:
            break
        if seconds >= start_mjd * SECONDS_PER_DAY + offset:
            return Epoch.normalized("UTC", tai.mjd, tai.sec - offset)
        previous = rows[i - 1][1] if i > 0 and rows[i - 1][3] == 0.0 else None
        if previous is not None and seconds >= start_mjd * SECONDS_PER_DAY + previous:
            # Inside the inserted second: show it as 23:59:60.x of the previous day.
            return Epoch(
                "UTC", start_mjd - 1, SECONDS_PER_DAY + (seconds - start_mjd * SECONDS_PER_DAY - previous)
            )
    # Drift era (1961-1971): iterate UTC = TAI - DeltaAT(UTC).
    utc = Epoch.normalized("UTC", tai.mjd, tai.sec - 10.0)
    for _ in range(6):
        utc = Epoch.normalized("UTC", tai.mjd, tai.sec - delta_at(utc.mjd, utc.sec))
    return utc


def _from_tai(tai: Epoch, scale: str, eop) -> Epoch:
    if scale == "TAI":
        return tai
    if scale == "TT":
        return _shift(tai, "TT", TT_MINUS_TAI_S)
    if scale == "A1":
        return _shift(tai, "A1", A1_MINUS_TAI_S)
    if scale == "TDB":
        tt = _shift(tai, "TT", TT_MINUS_TAI_S)
        return _shift(tt, "TDB", tdb_minus_tt(tt))
    if scale == "UTC":
        return _tai_to_utc(tai)
    if scale == "UT1":
        if eop is None:
            raise ValueError("UT1 conversions require Earth orientation parameters")
        utc = _tai_to_utc(tai)
        return Epoch.normalized("UT1", utc.mjd, min(utc.sec, SECONDS_PER_DAY) + eop.ut1_minus_utc(utc))
    raise ValueError(f"unknown time scale {scale!r}")
