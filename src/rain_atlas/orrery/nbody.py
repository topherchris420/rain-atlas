"""Self-gravitating N-body integration (Newtonian point masses).

Used for two independent checks of the integrator and dynamics that do not go
through the Earth-centred force model:

* the Chenciner-Montgomery (2000) figure-eight choreography, a periodic
  three-body solution with equal masses in G = 1 units, whose return to its
  initial configuration after one period is a demanding closed-form test;
* the DE421 planetary ephemeris, integrated from DE421 initial conditions in a
  heliocentric or barycentric frame and compared against the ephemeris itself.

The acceleration on body i is a_i = sum_{j != i} G m_j (r_j - r_i)/|r_j - r_i|^3
(softening = 0). The system is integrated as one state vector [r_1..r_N, v_1..v_N]
so any integrator in :mod:`.integrators` applies. Conserved quantities (total
energy, linear and angular momentum, barycentre drift) are returned for drift
diagnostics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .integrators import integrate

# Chenciner & Montgomery figure-eight (Montgomery 2001; Simo's refined data), G = m = 1.
FIGURE_EIGHT = {
    "G": 1.0,
    "masses": [1.0, 1.0, 1.0],
    "period": 6.32591398,
    "positions": [[0.97000436, -0.24308753, 0.0], [-0.97000436, 0.24308753, 0.0], [0.0, 0.0, 0.0]],
    "velocities": None,  # filled below from the published v3
    "reference": "Chenciner & Montgomery, Ann. Math. 152 (2000) 881; Simo initial data",
}
_V3 = np.array([-0.93240737, -0.86473146, 0.0])
FIGURE_EIGHT["velocities"] = [(-_V3 / 2).tolist(), (-_V3 / 2).tolist(), _V3.tolist()]


@dataclass
class NBodySystem:
    masses: np.ndarray
    g: float = 1.0

    @property
    def n(self) -> int:
        return len(self.masses)

    def accelerations(self, pos: np.ndarray) -> np.ndarray:
        n = self.n
        acc = np.zeros((n, 3))
        for i in range(n):
            for j in range(i + 1, n):
                d = pos[j] - pos[i]
                r2 = float(d @ d)
                inv = 1.0 / (r2 * math.sqrt(r2))
                acc[i] += self.g * self.masses[j] * inv * d
                acc[j] -= self.g * self.masses[i] * inv * d
        return acc

    def rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        n = self.n
        pos = y[: 3 * n].reshape(n, 3)
        vel = y[3 * n :].reshape(n, 3)
        return np.concatenate([vel.ravel(), self.accelerations(pos).ravel()])

    def energy(self, y: np.ndarray) -> float:
        n = self.n
        pos = y[: 3 * n].reshape(n, 3)
        vel = y[3 * n :].reshape(n, 3)
        kinetic = 0.5 * float(np.sum(self.masses * np.sum(vel * vel, axis=1)))
        potential = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                potential -= self.g * self.masses[i] * self.masses[j] / np.linalg.norm(pos[j] - pos[i])
        return kinetic + potential

    def momentum(self, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = self.n
        pos = y[: 3 * n].reshape(n, 3)
        vel = y[3 * n :].reshape(n, 3)
        linear = np.sum(self.masses[:, None] * vel, axis=0)
        angular = np.sum(np.cross(pos, self.masses[:, None] * vel), axis=0)
        barycentre = np.sum(self.masses[:, None] * pos, axis=0) / np.sum(self.masses)
        return linear, angular, barycentre

    def state_vector(self, positions, velocities) -> np.ndarray:
        return np.concatenate([np.asarray(positions, float).ravel(), np.asarray(velocities, float).ravel()])


def integrate_system(system: NBodySystem, y0: np.ndarray, times, **kwargs) -> dict:
    kwargs.setdefault("method", "rkf78")
    kwargs.setdefault("rtol", 1e-13)
    kwargs.setdefault("atol", 1e-13)
    kwargs["error_slice"] = slice(0, y0.size)
    res = integrate(system.rhs, 0.0, y0, np.asarray(times, float), **kwargs)
    energies = np.array([system.energy(s) for s in res.states])
    momenta = [system.momentum(s) for s in res.states]
    lin = np.array([m[0] for m in momenta])
    ang = np.array([m[1] for m in momenta])
    bary = np.array([m[2] for m in momenta])
    return {
        "times": res.times,
        "states": res.states,
        "energy": energies,
        "relative_energy_drift": float(np.max(np.abs((energies - energies[0]) / energies[0]))),
        "linear_momentum_drift": float(np.max(np.abs(lin - lin[0]))),
        "angular_momentum_drift": float(np.max(np.linalg.norm(ang - ang[0], axis=1))),
        "barycentre_drift": float(np.max(np.linalg.norm(bary - bary[0], axis=1))),
        "stats": res.stats(),
    }


def figure_eight_system() -> tuple[NBodySystem, np.ndarray]:
    system = NBodySystem(np.array(FIGURE_EIGHT["masses"], dtype=float), g=FIGURE_EIGHT["G"])
    y0 = system.state_vector(FIGURE_EIGHT["positions"], FIGURE_EIGHT["velocities"])
    return system, y0


def de421_nbody_gm(de421_gm: dict) -> dict:
    """Map N-body body names to DE421 GM values (inner planets use the barycenter GM)."""

    return {
        "sun": de421_gm["sun"],
        "mercury-barycenter": de421_gm["mercury"],
        "venus-barycenter": de421_gm["venus"],
        "earth": de421_gm["earth"],
        "moon": de421_gm["moon"],
        "mars-barycenter": de421_gm["mars-barycenter"],
        "jupiter-barycenter": de421_gm["jupiter-barycenter"],
        "saturn-barycenter": de421_gm["saturn-barycenter"],
        "uranus-barycenter": de421_gm["uranus-barycenter"],
        "neptune-barycenter": de421_gm["neptune-barycenter"],
    }


def solar_system_from_ephemeris(ephemeris, bodies: list[str], gm: dict, et: float, center: str = "ssb"):
    """Build an N-body system and initial state from an ephemeris at epoch ``et``."""

    masses = np.array([gm[b] for b in bodies], dtype=float)  # GM values; G folded in (g=1)
    positions, velocities = [], []
    for b in bodies:
        r, v = ephemeris.state(b, center, et)
        positions.append(r)
        velocities.append(v)
    system = NBodySystem(masses, g=1.0)
    return system, system.state_vector(positions, velocities)
