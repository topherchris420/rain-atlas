"""Planetary and lunar ephemerides from JPL SPK (NAIF DAF) Chebyshev data.

ORRERY reads SPK type 2 (position Chebyshev, velocity by differentiation) and
type 3 (position and velocity Chebyshev) segments directly from a NAIF DAF
file, following the published NAIF "DAF Required Reading" and "SPK Required
Reading" layouts. No NAIF/CSPICE code is used.

Evaluation for a record with midpoint ``MID`` and half-length ``RADIUS``
(seconds of TDB past J2000, "ET"):

    tau = (et - MID) / RADIUS,   x(et) = sum_k c_k T_k(tau),
    dx/dt = sum_k c_k T_k'(tau) / RADIUS,

with the Chebyshev recurrences T_k = 2 tau T_{k-1} - T_{k-2} and
T_k' = 2 T_{k-1} + 2 tau T_{k-1}' - T_{k-2}'.

States are geometric (no light time or aberration), in km and km/s, in the SPK
frame (J2000/ICRF axes for DE421). Bodies are composed through the solar-system
barycentre (NAIF id 0). Requests outside the available records raise an error.

``data/de421_*.json`` holds hash-pinned excerpts of ``de421.bsp`` (the NAIF
file shipped with GMAT R2026a) made by ``scripts/make_orrery_data.py``; any
complete SPK file can be used instead through :class:`SpkFile`.

Frame tie. ORRERY integrates in MJ2000Eq (FK5, the frame its IAU-1976/1980
Earth-orientation chain is referred to), while DE421 axes are ICRF. The two
differ by tens of milliarcseconds (46.6 mas on 2026-01-15: 58 m at lunar
distance, 15 km at 1 au). :class:`FrameTie` with ``"gmat-icrf-table"``
applies GMAT R2026a's own ICRF-to-FK5 rotation (``data/icrf/ICRF_Table.txt``:
daily Euler rotation vectors by A1 date, 10-point Lagrange interpolation,
axis-angle matrix, as in ``ICRFFile::RotationMatrixFromICRFToFK5``);
``"none"`` treats ICRF axes as MJ2000Eq. The constant IERS 2003 frame-bias
matrix is not implemented.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .timescales import Epoch

DATA = Path(__file__).resolve().parent / "data"
BODY_IDS = {
    "ssb": 0,
    "mercury-barycenter": 1,
    "venus-barycenter": 2,
    "earth-moon-barycenter": 3,
    "mars-barycenter": 4,
    "jupiter-barycenter": 5,
    "saturn-barycenter": 6,
    "uranus-barycenter": 7,
    "neptune-barycenter": 8,
    "pluto-barycenter": 9,
    "sun": 10,
    "mercury": 199,
    "venus": 299,
    "moon": 301,
    "earth": 399,
    "mars": 499,
}


def et_from_epoch(epoch: Epoch) -> float:
    """Seconds of TDB past J2000.0 (JD 2451545.0 TDB)."""

    tdb = epoch if epoch.scale == "TDB" else epoch.to("TDB")
    return (tdb.mjd - 51544) * 86400.0 + (tdb.sec - 43200.0)


def body_id(body) -> int:
    if isinstance(body, int):
        return body
    try:
        return BODY_IDS[body]
    except KeyError:
        raise ValueError(f"unknown body {body!r}; known: {sorted(BODY_IDS)}") from None


def chebyshev(coeffs: np.ndarray, tau: float, radius: float) -> tuple[np.ndarray, np.ndarray]:
    """Value and time derivative of Chebyshev series; ``coeffs`` is [components, degree+1]."""

    n = coeffs.shape[1]
    t = np.empty(n)
    d = np.empty(n)
    t[0], d[0] = 1.0, 0.0
    if n > 1:
        t[1], d[1] = tau, 1.0
    for k in range(2, n):
        t[k] = 2.0 * tau * t[k - 1] - t[k - 2]
        d[k] = 2.0 * t[k - 1] + 2.0 * tau * d[k - 1] - d[k - 2]
    return coeffs @ t, (coeffs @ d) / radius


@dataclass
class ChebyshevSegment:
    target: int
    center: int
    frame: int
    data_type: int
    init: float
    intlen: float
    rsize: int
    first_index: int
    records: np.ndarray  # [n, rsize]

    @property
    def start(self) -> float:
        return self.init + self.first_index * self.intlen

    @property
    def stop(self) -> float:
        return self.start + len(self.records) * self.intlen

    def state(self, et: float) -> tuple[np.ndarray, np.ndarray]:
        if not self.start <= et <= self.stop:
            raise ValueError(
                f"ephemeris for body {self.target} wrt {self.center} not available at ET {et:.3f} "
                f"(have [{self.start:.1f}, {self.stop:.1f}])"
            )
        index = min(int((et - self.start) // self.intlen), len(self.records) - 1)
        rec = self.records[index]
        mid, radius = rec[0], rec[1]
        tau = (et - mid) / radius
        if self.data_type == 2:
            ncoef = (self.rsize - 2) // 3
            return chebyshev(rec[2:].reshape(3, ncoef), tau, radius)
        if self.data_type == 3:
            ncoef = (self.rsize - 2) // 6
            pos, _ = chebyshev(rec[2 : 2 + 3 * ncoef].reshape(3, ncoef), tau, radius)
            vel, _ = chebyshev(rec[2 + 3 * ncoef :].reshape(3, ncoef), tau, radius)
            return pos, vel
        raise ValueError(f"unsupported SPK data type {self.data_type}")

    def to_json(self) -> dict:
        return {
            "target": self.target,
            "center": self.center,
            "frame": self.frame,
            "data_type": self.data_type,
            "init": self.init,
            "intlen": self.intlen,
            "rsize": self.rsize,
            "first_index": self.first_index,
            "records": self.records.tolist(),
        }

    @staticmethod
    def from_json(item: dict) -> ChebyshevSegment:
        records = np.asarray(item["records"], dtype=float)
        if records.ndim != 2 or records.shape[1] != item["rsize"]:
            raise ValueError("malformed ephemeris excerpt records")
        return ChebyshevSegment(
            int(item["target"]),
            int(item["center"]),
            int(item["frame"]),
            int(item["data_type"]),
            float(item["init"]),
            float(item["intlen"]),
            int(item["rsize"]),
            int(item["first_index"]),
            records,
        )


class Ephemeris:
    """A set of Chebyshev segments with body-chain composition through the SSB."""

    def __init__(self, segments: list[ChebyshevSegment], source: dict | None = None):
        self.segments = {seg.target: seg for seg in segments}
        if len(self.segments) != len(segments):
            raise ValueError("duplicate target bodies in ephemeris")
        self.source = dict(source or {})

    def _to_ssb(self, target: int, et: float) -> tuple[np.ndarray, np.ndarray]:
        pos = np.zeros(3)
        vel = np.zeros(3)
        body = target
        guard = 0
        while body != 0:
            seg = self.segments.get(body)
            if seg is None:
                raise ValueError(f"ephemeris has no segment for body {body}")
            p, v = seg.state(et)
            pos += p
            vel += v
            body = seg.center
            guard += 1
            if guard > 8:
                raise ValueError("ephemeris body chain does not reach the barycentre")
        return pos, vel

    def state(self, target, center, et: float) -> tuple[np.ndarray, np.ndarray]:
        """Geometric state of ``target`` relative to ``center`` (km, km/s)."""

        t, c = body_id(target), body_id(center)
        # Short chains for the common Earth-Moon pair avoid catastrophic cancellation.
        if c == 399 and t == 301:
            pm, vm = self.segments[301].state(et)
            pe, ve = self.segments[399].state(et)
            return pm - pe, vm - ve
        pt, vt = self._to_ssb(t, et)
        pc, vc = self._to_ssb(c, et)
        return pt - pc, vt - vc

    def position(self, target, center, et: float) -> np.ndarray:
        return self.state(target, center, et)[0]

    def coverage(self) -> dict:
        return {str(k): [s.start, s.stop] for k, s in sorted(self.segments.items())}

    def to_json(self) -> dict:
        return {"source": self.source, "segments": [s.to_json() for s in self.segments.values()]}

    @staticmethod
    def from_json(payload: dict) -> Ephemeris:
        return Ephemeris([ChebyshevSegment.from_json(s) for s in payload["segments"]], payload.get("source"))

    @staticmethod
    def load(name: str) -> Ephemeris:
        return Ephemeris.from_json(json.loads((DATA / f"{name}.json").read_text(encoding="utf-8")))


class FrameTie:
    """Rotation from ephemeris (ICRF) axes to MJ2000Eq axes."""

    MODES = ("none", "gmat-icrf-table")

    def __init__(self, mode: str = "gmat-icrf-table", table: str = "icrf_fk5_gmat_2026"):
        if mode not in self.MODES:
            raise ValueError(f"frame tie must be one of {self.MODES}")
        self.mode = mode
        self.table_name = table if mode != "none" else None
        self._t = self._v = None
        self.source: dict | None = None
        if mode == "gmat-icrf-table":
            payload = json.loads((DATA / f"{table}.json").read_text(encoding="utf-8"))
            rows = np.asarray(payload["rows"], dtype=float)
            self._t, self._v = rows[:, 0], rows[:, 1:]
            self.source = payload["source"]

    def rotation_vector(self, a1_gmat_modjulian: float, order: int = 9) -> np.ndarray:
        t = self._t
        if t is None or self._v is None:
            return np.zeros(3)
        if not (t[0] <= a1_gmat_modjulian <= t[-1]):
            raise ValueError(f"epoch A1 {a1_gmat_modjulian} outside the ICRF table excerpt [{t[0]}, {t[-1]}]")
        # GMAT's bisection, including its use of the last midpoint visited (ICRFFile.cpp).
        start, end, mid = 0, len(t) - 1, -1
        while start < end - 1:
            mid = (start + end) // 2
            if a1_gmat_modjulian > t[mid]:
                start = mid
            else:
                end = mid
        begin = max(0, mid - order // 2)
        end = min(len(t) - 1, begin + order)
        begin = max(0, end - order)
        xs, ys = t[begin : end + 1], self._v[begin : end + 1]
        out = np.zeros(3)
        for i in range(xs.size):
            others = np.delete(xs, i)
            out += np.prod((a1_gmat_modjulian - others) / (xs[i] - others)) * ys[i]
        return out

    def matrix(self, a1_gmat_modjulian: float) -> np.ndarray:
        if self.mode == "none":
            return np.eye(3)
        vec = self.rotation_vector(a1_gmat_modjulian)
        angle = float(np.linalg.norm(vec))
        if angle == 0.0:
            return np.eye(3)
        a = vec / angle
        c, s = math.cos(angle), math.sin(angle)
        rot = np.array(
            [
                [
                    c + a[0] * a[0] * (1 - c),
                    a[0] * a[1] * (1 - c) + a[2] * s,
                    a[0] * a[2] * (1 - c) - a[1] * s,
                ],
                [
                    a[0] * a[1] * (1 - c) - a[2] * s,
                    c + a[1] * a[1] * (1 - c),
                    a[1] * a[2] * (1 - c) + a[0] * s,
                ],
                [
                    a[0] * a[2] * (1 - c) + a[1] * s,
                    a[1] * a[2] * (1 - c) - a[0] * s,
                    c + a[2] * a[2] * (1 - c),
                ],
            ]
        )
        return rot.T

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "table": self.table_name,
            "source": self.source,
            "note": "ICRF axes treated as MJ2000Eq"
            if self.mode == "none"
            else "GMAT R2026a ICRF-to-FK5 rotation",
        }


class SpkFile:
    """Read-only access to Chebyshev segments of a NAIF SPK (DAF) file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with self.path.open("rb") as fh:
            record = fh.read(1024)
        if record[:7] not in (b"DAF/SPK", b"NAIF/DA"):
            raise ValueError("not a NAIF DAF/SPK file")
        fmt = record[88:96]
        if fmt.startswith(b"LTL-IEEE"):
            self.endian = "<"
        elif fmt.startswith(b"BIG-IEEE"):
            self.endian = ">"
        else:
            raise ValueError("unsupported DAF binary format")
        self.nd, self.ni = struct.unpack(self.endian + "ii", record[8:16])
        if (self.nd, self.ni) != (2, 6):
            raise ValueError("SPK files must have ND=2, NI=6")
        self.fward = struct.unpack(self.endian + "i", record[76:80])[0]
        self.summaries = list(self._read_summaries())

    def _read_doubles(self, fh, first_address: int, count: int) -> np.ndarray:
        fh.seek((first_address - 1) * 8)
        raw = fh.read(count * 8)
        if len(raw) != count * 8:
            raise ValueError("truncated SPK file")
        return np.frombuffer(raw, dtype=self.endian + "f8", count=count).astype(float)

    def _read_summaries(self):
        size = self.nd + (self.ni + 1) // 2
        with self.path.open("rb") as fh:
            rec = self.fward
            while rec:
                fh.seek((rec - 1) * 1024)
                block = fh.read(1024)
                nxt, _, n = struct.unpack(self.endian + "ddd", block[:24])
                for i in range(int(n)):
                    off = 24 + i * size * 8
                    et0, et1 = struct.unpack(self.endian + "dd", block[off : off + 16])
                    target, center, frame, dtype, start, end = struct.unpack(
                        self.endian + "6i", block[off + 16 : off + 40]
                    )
                    yield {
                        "target": target,
                        "center": center,
                        "frame": frame,
                        "data_type": dtype,
                        "start_et": et0,
                        "stop_et": et1,
                        "start_address": start,
                        "end_address": end,
                    }
                rec = int(nxt)

    def segment(self, target: int, et0: float | None = None, et1: float | None = None) -> ChebyshevSegment:
        matches = [s for s in self.summaries if s["target"] == target and s["data_type"] in (2, 3)]
        if not matches:
            raise ValueError(f"no type 2/3 segment for body {target}")
        if et0 is not None:
            matches = [s for s in matches if s["start_et"] <= et0 and (et1 or et0) <= s["stop_et"]]
            if not matches:
                raise ValueError(f"no segment for body {target} covers the requested window")
        summary = matches[-1]  # later segments take precedence (NAIF convention)
        with self.path.open("rb") as fh:
            init, intlen, rsize, n = self._read_doubles(fh, summary["end_address"] - 3, 4)
            rsize_i, n_i = int(rsize), int(n)
            lo, hi = 0, n_i
            if et0 is not None:
                lo = max(0, int(math.floor((et0 - init) / intlen)))
                hi = min(n_i, int(math.floor(((et1 if et1 is not None else et0) - init) / intlen)) + 1)
            data = self._read_doubles(fh, summary["start_address"] + lo * rsize_i, (hi - lo) * rsize_i)
        return ChebyshevSegment(
            summary["target"],
            summary["center"],
            summary["frame"],
            summary["data_type"],
            float(init),
            float(intlen),
            rsize_i,
            lo,
            data.reshape(hi - lo, rsize_i),
        )

    def ephemeris(self, targets: list[int], et0: float | None = None, et1: float | None = None) -> Ephemeris:
        return Ephemeris([self.segment(t, et0, et1) for t in targets], {"file": self.path.name})
