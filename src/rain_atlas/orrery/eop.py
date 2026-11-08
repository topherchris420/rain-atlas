"""Earth orientation parameters (EOP).

Values come from the IERS EOP 20 C04 series (daily, 0h UTC), as distributed in
the ``eopc04_08.62-now`` file shipped with GMAT R2026a. ORRERY stores
hash-pinned excerpts (``data/eop_*.json``) produced by
``scripts/make_orrery_data.py``; the full source file is never required.

Interpolation is linear between daily values, matching GMAT R2026a
(``EopFile.cpp``). GMAT indexes UT1-UTC by TAI MJD and polar motion by UTC MJD;
ORRERY indexes both by UTC MJD. The 37 s argument difference changes UT1-UTC by
about 4e-7 s (0.2 mm of Earth rotation at the equator), which is documented
rather than emulated. Linear interpolation across a leap-second day would be
wrong for UT1-UTC; the excerpt builder refuses windows that contain one.

Epochs outside the table raise an error: ORRERY never extrapolates EOP silently.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class EopTable:
    mjd: tuple[float, ...]
    x_arcsec: tuple[float, ...]
    y_arcsec: tuple[float, ...]
    ut1_utc_s: tuple[float, ...]
    lod_s: tuple[float, ...]
    dpsi_arcsec: tuple[float, ...]
    deps_arcsec: tuple[float, ...]
    source: dict

    @staticmethod
    def from_rows(rows: list[dict], source: dict | None = None) -> EopTable:
        rows = sorted(rows, key=lambda r: r["mjd"])
        if len(rows) < 2:
            raise ValueError("an EOP table needs at least two daily rows")
        steps = [b["mjd"] - a["mjd"] for a, b in zip(rows, rows[1:])]
        if any(s <= 0 for s in steps):
            raise ValueError("EOP rows must have strictly increasing MJD")
        return EopTable(
            tuple(float(r["mjd"]) for r in rows),
            tuple(float(r["x_arcsec"]) for r in rows),
            tuple(float(r["y_arcsec"]) for r in rows),
            tuple(float(r["ut1_utc_s"]) for r in rows),
            tuple(float(r["lod_s"]) for r in rows),
            tuple(float(r.get("dpsi_arcsec", 0.0)) for r in rows),
            tuple(float(r.get("deps_arcsec", 0.0)) for r in rows),
            dict(source or {}),
        )

    @staticmethod
    def load(name: str) -> EopTable:
        payload = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
        return EopTable.from_rows(payload["rows"], payload.get("source"))

    @staticmethod
    def zero(mjd_start: float, mjd_end: float) -> EopTable:
        """A table of zeros, for experiments that deliberately ignore EOP."""

        rows = [
            {"mjd": m, "x_arcsec": 0.0, "y_arcsec": 0.0, "ut1_utc_s": 0.0, "lod_s": 0.0}
            for m in (float(mjd_start), float(mjd_end))
        ]
        return EopTable.from_rows(rows, {"name": "zero", "note": "EOP deliberately set to zero"})

    def _interp(self, values: tuple[float, ...], mjd: float) -> float:
        if not self.mjd[0] <= mjd <= self.mjd[-1]:
            raise ValueError(
                f"EOP requested at MJD {mjd:.6f}, outside the table [{self.mjd[0]}, {self.mjd[-1]}]"
            )
        i = min(bisect.bisect_right(self.mjd, mjd) - 1, len(self.mjd) - 2)
        ratio = (mjd - self.mjd[i]) / (self.mjd[i + 1] - self.mjd[i])
        return values[i] + ratio * (values[i + 1] - values[i])

    @staticmethod
    def _utc_mjd(utc) -> float:
        return utc.mjd + min(utc.sec, 86400.0) / 86400.0

    def ut1_minus_utc(self, utc) -> float:
        return self._interp(self.ut1_utc_s, self._utc_mjd(utc))

    def polar_motion(self, utc) -> tuple[float, float]:
        m = self._utc_mjd(utc)
        return self._interp(self.x_arcsec, m), self._interp(self.y_arcsec, m)

    def lod(self, utc) -> float:
        return self._interp(self.lod_s, self._utc_mjd(utc))

    def nutation_corrections(self, utc) -> tuple[float, float]:
        """IERS celestial-pole offsets (dPsi, dEps) to IAU-1980 nutation, arcsec."""

        m = self._utc_mjd(utc)
        return self._interp(self.dpsi_arcsec, m), self._interp(self.deps_arcsec, m)

    def describe(self) -> dict:
        return {"first_mjd": self.mjd[0], "last_mjd": self.mjd[-1], "rows": len(self.mjd), **self.source}
