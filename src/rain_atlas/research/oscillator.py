"""The first research domain: a noisy, driven, possibly nonlinear oscillator.

The world is a stochastic difference equation (semi-implicit Euler)::

    v[t+1] = v[t] + dt * f(x[t], v[t], u[t]) + s * sqrt(dt) * eps[t]
    x[t+1] = x[t] + dt * v[t+1]
    u[t]   = A * sin(Omega * t * dt)

with ``f = sum_j theta_j * phi_j`` over a fixed *term grammar*. Because the full
state is observed and the noise enters the velocity update, the one-step
regression ``(v[t+1] - v[t]) / dt = theta . phi(x[t], v[t], u[t]) + noise`` is
exactly linear-Gaussian (for Gaussian noise), so model evidence can be
computed in closed form and checked against brute-force integration.

The hidden truth lives only in :class:`Instrument`. Research code receives
:class:`Observation` objects and nothing else; tests assert this boundary.

Problem families (see :func:`generate_problems`):

* ``stationary`` -- structure inside the anticipated grammar, no change; a
  quarter of the problems come with a *correct* memory of a previous
  characterization;
* ``hidden-change`` -- coefficients shift, or a term appears, at an
  unannounced experiment;
* ``unfamiliar`` -- one term outside the anticipated grammar;
* ``wrong-assumptions`` -- either the remembered characterization is stale
  (the apparatus changed since) or the noise is heavy-tailed while the
  analysis assumes Gaussian noise.

The ``held-out`` split differs from ``dev`` in seeds, in a wider stiffness
range, and in its unanticipated terms, which never occur in development.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..canonical import sha256_json

DT = 0.05
STEPS = 300

CORE = ("x", "v", "u")
OPTIONAL = ("x^3", "1")
EXPANSION = ("x^2", "x^2*v", "v*|v|", "x*u", "v^3")
LIBRARY = CORE + OPTIONAL + EXPANSION
INDEX = {term: i for i, term in enumerate(LIBRARY)}
L = len(LIBRARY)

TERM_MEANING = {
    "x": "linear stiffness",
    "v": "linear damping",
    "u": "drive coupling",
    "x^3": "cubic (Duffing) stiffness",
    "1": "constant offset",
    "x^2": "quadratic (asymmetric) stiffness",
    "x^2*v": "amplitude-dependent (Van der Pol type) damping",
    "v*|v|": "quadratic drag",
    "x*u": "parametric excitation",
    "v^3": "cubic damping",
}

DEFAULT_SPACE = {"amplitude": (0.0, 1.5), "frequency": (0.3, 2.5), "x0": (-1.0, 1.0)}

FAMILIES = ("stationary", "hidden-change", "unfamiliar", "wrong-assumptions")
SPLITS = ("dev", "held-out", "demo")
UNANTICIPATED = {"dev": ("x^2*v", "v*|v|"), "held-out": ("x*u", "x^2", "v^3"), "demo": ("x^2*v", "x*u")}
STIFFNESS = {"dev": (0.6, 2.0), "held-out": (0.5, 2.6), "demo": (0.6, 2.0)}
NOISE_LEVELS = (0.15, 0.3, 0.5)
SPLIT_SEEDS = {"dev": 7_310_001, "held-out": 9_920_417, "demo": 4_100_023}


def features(x: np.ndarray, v: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Library features, last axis ordered as :data:`LIBRARY`."""

    x2 = x * x
    return np.stack([x, v, u, x2 * x, np.ones_like(x), x2, x2 * v, v * np.abs(v), x * u, v * v * v], axis=-1)


def accelerations(theta: np.ndarray, x: np.ndarray, v: np.ndarray, u: np.ndarray) -> np.ndarray:
    """``f`` for a batch: *theta* (B, L), states (B,)."""

    x2 = x * x
    return (
        theta[:, 0] * x
        + theta[:, 1] * v
        + theta[:, 2] * u
        + theta[:, 3] * x2 * x
        + theta[:, 4]
        + theta[:, 5] * x2
        + theta[:, 6] * x2 * v
        + theta[:, 7] * v * np.abs(v)
        + theta[:, 8] * x * u
        + theta[:, 9] * v * v * v
    )


def coefficient_vector(coefficients: dict[str, float]) -> np.ndarray:
    theta = np.zeros(L)
    for term, value in coefficients.items():
        theta[INDEX[term]] = float(value)
    return theta


def structure_of(coefficients: dict[str, float]) -> tuple[str, ...]:
    return tuple(t for t in LIBRARY if abs(coefficients.get(t, 0.0)) > 0.0)


@dataclass(frozen=True)
class Design:
    """One experiment: drive amplitude, drive frequency, initial displacement."""

    amplitude: float
    frequency: float
    x0: float

    def to_dict(self) -> dict:
        return {"amplitude": self.amplitude, "frequency": self.frequency, "x0": self.x0}

    @classmethod
    def from_dict(cls, data: dict) -> "Design":
        return cls(float(data["amplitude"]), float(data["frequency"]), float(data["x0"]))

    def rounded(self) -> "Design":
        return Design(round(self.amplitude, 4), round(self.frequency, 4), round(self.x0, 4))

    def normalized(self, space: dict) -> np.ndarray:
        values = (self.amplitude, self.frequency, self.x0)
        return np.array(
            [(v - lo) / (hi - lo) for v, (lo, hi) in zip(values, (space[k] for k in DEFAULT_SPACE))]
        )

    def within(self, space: dict, tol: float = 1e-9) -> bool:
        values = (self.amplitude, self.frequency, self.x0)
        return all(
            lo - tol <= v <= hi + tol for v, (lo, hi) in zip(values, (space[k] for k in DEFAULT_SPACE))
        )

    def label(self) -> str:
        return f"A={self.amplitude:.3g}, Ω={self.frequency:.3g}, x0={self.x0:+.3g}"


def _radical_inverse(index: int, base: int) -> float:
    result, f = 0.0, 1.0 / base
    while index > 0:
        result += f * (index % base)
        index //= base
        f /= base
    return result


def halton(count: int, *, offset: int = 1, bases: tuple[int, ...] = (2, 3, 5)) -> np.ndarray:
    """Deterministic low-discrepancy points in the unit cube."""

    return np.array([[_radical_inverse(i, b) for b in bases] for i in range(offset, offset + count)])


def design_pool(space: dict, count: int = 32, *, offset: int = 1) -> list[Design]:
    """A fixed quasi-random candidate pool covering the approved design space."""

    pts = halton(count, offset=offset)
    (a0, a1), (w0, w1), (x0, x1) = (space[k] for k in DEFAULT_SPACE)
    return [
        Design(a0 + p[0] * (a1 - a0), w0 + p[1] * (w1 - w0), x0 + p[2] * (x1 - x0)).rounded() for p in pts
    ]


def simulate(
    theta: np.ndarray,
    amplitude: np.ndarray,
    frequency: np.ndarray,
    x0: np.ndarray,
    noise_sd: np.ndarray,
    eps: np.ndarray,
    *,
    steps: int = STEPS,
    dt: float = DT,
    clip: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized simulation of B trajectories; returns x, v (B, steps+1) and u (B, steps).

    *clip* bounds the state for planning simulations of hypothetical
    (possibly unstable) posterior draws; the instrument never clips.
    """

    theta = np.atleast_2d(np.asarray(theta, dtype=float))
    batch = theta.shape[0]
    t = np.arange(steps) * dt
    u = np.asarray(amplitude, dtype=float).reshape(batch, 1) * np.sin(
        np.asarray(frequency, dtype=float).reshape(batch, 1) * t[None, :]
    )
    x = np.empty((batch, steps + 1))
    v = np.empty((batch, steps + 1))
    x[:, 0] = np.asarray(x0, dtype=float).reshape(batch)
    v[:, 0] = 0.0
    scale = np.asarray(noise_sd, dtype=float).reshape(batch) * math.sqrt(dt)
    with np.errstate(over="ignore", invalid="ignore"):
        for i in range(steps):
            acc = accelerations(theta, x[:, i], v[:, i], u[:, i])
            vn = v[:, i] + dt * acc + scale * eps[:, i]
            xn = x[:, i] + dt * vn
            if clip is not None:
                vn = np.clip(np.nan_to_num(vn), -4 * clip, 4 * clip)
                xn = np.clip(np.nan_to_num(xn), -clip, clip)
            v[:, i + 1] = vn
            x[:, i + 1] = xn
    return x, v, u


def regression_data(
    x: np.ndarray, v: np.ndarray, u: np.ndarray, dt: float = DT
) -> tuple[np.ndarray, np.ndarray]:
    """One-step regression rows: features (…, T, L) and targets (…, T)."""

    y = (v[..., 1:] - v[..., :-1]) / dt
    return features(x[..., :-1], v[..., :-1], u), y


def response_amplitude(x: np.ndarray) -> np.ndarray:
    """RMS displacement over the second half of a trajectory (human-readable observable)."""

    half = x.shape[-1] // 2
    return np.sqrt(np.mean(np.square(x[..., half:]), axis=-1))


@dataclass
class Observation:
    """What an experiment returns. Contains no hidden parameters."""

    index: int
    design: Design
    x: np.ndarray
    v: np.ndarray
    u: np.ndarray
    status: str = "ok"

    def regression(self) -> tuple[np.ndarray, np.ndarray]:
        return regression_data(self.x, self.v, self.u)

    def amplitude(self) -> float:
        return float(response_amplitude(self.x))

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "design": self.design.to_dict(),
            "status": self.status,
            "x": [float(a) for a in self.x],
            "v": [float(a) for a in self.v],
            "u": [float(a) for a in self.u],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Observation":
        return cls(
            index=int(data["index"]),
            design=Design.from_dict(data["design"]),
            x=np.asarray(data["x"], dtype=float),
            v=np.asarray(data["v"], dtype=float),
            u=np.asarray(data["u"], dtype=float),
            status=str(data["status"]),
        )

    def digest(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True)
class World:
    """Hidden ground truth. Only the instrument and the scorer may read it."""

    coefficients: dict[str, float]
    noise_scale: float
    noise: str = "gaussian"  # gaussian | student-t3
    change_at: int | None = None
    changed_coefficients: dict[str, float] | None = None
    seed: int = 0

    def active(self, index: int) -> dict[str, float]:
        if self.change_at is not None and index >= self.change_at and self.changed_coefficients:
            return dict(self.changed_coefficients)
        return dict(self.coefficients)

    def to_dict(self) -> dict:
        return {
            "coefficients": dict(sorted(self.coefficients.items())),
            "noise_scale": self.noise_scale,
            "noise": self.noise,
            "change_at": self.change_at,
            "changed_coefficients": dict(sorted((self.changed_coefficients or {}).items())) or None,
            "seed": self.seed,
        }


class Instrument:
    """A simulated apparatus. Seeds depend only on (problem seed, experiment index)."""

    kind = "in-process simulated oscillator"

    def __init__(self, world: World, *, dt: float = DT, steps: int = STEPS):
        self._world = world
        self.dt = dt
        self.steps = steps
        self.executed: list[int] = []

    def noise(self, index: int, steps: int) -> np.ndarray:
        rng = np.random.default_rng([self._world.seed, 7919, index])
        if self._world.noise == "student-t3":
            return rng.standard_t(3, size=steps) / math.sqrt(3.0)
        return rng.standard_normal(steps)

    def run(self, design: Design, index: int) -> Observation:
        self.executed.append(index)
        theta = coefficient_vector(self._world.active(index))[None, :]
        eps = self.noise(index, self.steps)[None, :]
        x, v, u = simulate(
            theta,
            np.array([design.amplitude]),
            np.array([design.frequency]),
            np.array([design.x0]),
            np.array([self._world.noise_scale]),
            eps,
            steps=self.steps,
            dt=self.dt,
        )
        status = "ok" if np.all(np.isfinite(x)) and np.max(np.abs(x)) < 1e3 else "aborted"
        if status != "ok":
            x = np.zeros_like(x)
            v = np.zeros_like(v)
        return Observation(index=index, design=design, x=x[0], v=v[0], u=u[0], status=status)


@dataclass(frozen=True)
class MemoryPrior:
    """What a previous characterization of this apparatus recorded."""

    apparatus: str
    structure: tuple[str, ...]
    mean: dict[str, float]
    sd: dict[str, float]
    noise_sd: float
    age: int = 1
    source: str = "memory"
    reference: str = ""

    def to_dict(self) -> dict:
        return {
            "apparatus": self.apparatus,
            "structure": list(self.structure),
            "mean": dict(sorted(self.mean.items())),
            "sd": dict(sorted(self.sd.items())),
            "noise_sd": self.noise_sd,
            "age": self.age,
            "source": self.source,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryPrior":
        return cls(
            apparatus=str(data["apparatus"]),
            structure=tuple(data["structure"]),
            mean={k: float(v) for k, v in data["mean"].items()},
            sd={k: float(v) for k, v in data["sd"].items()},
            noise_sd=float(data["noise_sd"]),
            age=int(data.get("age", 1)),
            source=str(data.get("source", "memory")),
            reference=str(data.get("reference", "")),
        )


@dataclass(frozen=True)
class Problem:
    """A benchmark or demonstration problem: hidden world plus what the mission may know."""

    problem_id: str
    split: str
    family: str
    index: int
    world: World
    memory: MemoryPrior | None = None
    variant: str = ""
    heldout_designs: tuple[Design, ...] = field(default_factory=tuple)

    def instrument(self) -> Instrument:
        return Instrument(self.world)

    def truth(self, index: int) -> dict[str, float]:
        """Active coefficients for experiment *index* (for scoring only)."""

        return self.world.active(index)

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "split": self.split,
            "family": self.family,
            "index": self.index,
            "variant": self.variant,
            "world": self.world.to_dict(),
            "memory": self.memory.to_dict() if self.memory else None,
            "heldout_designs": [d.to_dict() for d in self.heldout_designs],
        }


def _base_coefficients(rng: np.random.Generator, split: str, structure: str) -> dict[str, float]:
    lo, hi = STIFFNESS[split]
    omega2 = rng.uniform(lo, hi)
    zeta = rng.uniform(0.04, 0.15)
    coeffs = {"x": -omega2, "v": -2.0 * zeta * math.sqrt(omega2), "u": rng.uniform(0.6, 1.4)}
    if "duffing" in structure:
        coeffs["x^3"] = -rng.uniform(0.15, 0.6)
    if "bias" in structure:
        coeffs["1"] = float(rng.choice([-1, 1])) * rng.uniform(0.12, 0.3)
    return {k: float(round(v, 6)) for k, v in coeffs.items()}


def _pick_structure(rng: np.random.Generator) -> str:
    return str(rng.choice(["linear", "duffing", "linear+bias", "duffing+bias"], p=[0.35, 0.35, 0.15, 0.15]))


def _apply_change(rng: np.random.Generator, split: str, coeffs: dict[str, float]) -> tuple[dict, str]:
    kinds = ["stiffness", "damping", "gain", "onset-x^3"]
    if split == "held-out":
        kinds.append("onset-1")
    kind = str(rng.choice(kinds))
    new = dict(coeffs)
    if kind == "onset-x^3" and "x^3" in coeffs:
        kind = "stiffness"
    if kind == "onset-1" and "1" in coeffs:
        kind = "damping"
    if kind == "stiffness":
        factor = rng.uniform(0.6, 0.8) if rng.random() < 0.5 else rng.uniform(1.25, 1.5)
        new["x"] = coeffs["x"] * factor
    elif kind == "damping":
        new["v"] = coeffs["v"] * rng.uniform(2.0, 3.0)
    elif kind == "gain":
        new["u"] = coeffs["u"] * rng.uniform(0.5, 0.7)
    elif kind == "onset-x^3":
        new["x^3"] = -rng.uniform(0.2, 0.5)
    else:
        new["1"] = float(rng.choice([-1, 1])) * rng.uniform(0.15, 0.3)
    return {k: float(round(v, 6)) for k, v in new.items()}, kind


def _unanticipated(rng: np.random.Generator, split: str, coeffs: dict[str, float]) -> tuple[dict, str]:
    term = str(rng.choice(UNANTICIPATED[split]))
    new = dict(coeffs)
    if term == "x^2*v":
        new[term] = -rng.uniform(0.15, 0.4)
    elif term == "v*|v|":
        new[term] = -rng.uniform(0.15, 0.4)
    elif term == "x*u":
        new[term] = float(rng.choice([-1, 1])) * rng.uniform(0.25, 0.5)
        new.setdefault("x^3", -rng.uniform(0.15, 0.4))
    elif term == "x^2":
        new[term] = float(rng.choice([-1, 1])) * rng.uniform(0.2, 0.4)
        new["x^3"] = -rng.uniform(0.3, 0.6)  # bounded potential
    else:  # v^3
        new[term] = -rng.uniform(0.08, 0.2)
    return {k: float(round(v, 6)) for k, v in new.items()}, term


def remembered(
    coeffs: dict[str, float], noise_sd: float, rng: np.random.Generator, apparatus: str, age: int = 1
):
    """A plausible stored characterization: true values plus estimation error."""

    structure = structure_of(coeffs)
    sd = {t: 0.03 + 0.03 * abs(coeffs[t]) for t in structure}
    mean = {t: float(round(coeffs[t] + rng.normal(0.0, sd[t] / 2), 6)) for t in structure}
    return MemoryPrior(
        apparatus=apparatus,
        structure=structure,
        mean=mean,
        sd={k: float(round(v, 6)) for k, v in sd.items()},
        noise_sd=float(round(noise_sd / math.sqrt(DT), 6)),
        age=age,
    )


def heldout_designs(rng_seed: int, count: int = 6) -> tuple[Design, ...]:
    """Unseen scoring conditions, including amplitudes beyond the permitted design space."""

    pts = halton(count, offset=101 + rng_seed % 997, bases=(7, 11, 13))
    return tuple(Design(0.2 + p[0] * 1.8, 0.3 + p[1] * 2.2, -1.2 + p[2] * 2.4).rounded() for p in pts)


def make_problem(split: str, family: str, index: int, *, base_seed: int | None = None) -> Problem:
    if split not in SPLITS or family not in FAMILIES:
        raise ValueError(f"unknown split/family {split}/{family}")
    base = SPLIT_SEEDS[split] if base_seed is None else base_seed
    seed = int(np.random.SeedSequence([base, FAMILIES.index(family), index]).generate_state(1)[0])
    rng = np.random.default_rng(seed)
    noise_scale = float(rng.choice(NOISE_LEVELS))
    structure = _pick_structure(rng)
    coeffs = _base_coefficients(rng, split, structure)
    apparatus = f"{split}-{family}-{index:03d}"
    memory = None
    variant = structure
    change_at = None
    changed = None
    noise = "gaussian"
    if family == "stationary":
        if rng.random() < 0.25:
            memory = remembered(coeffs, noise_scale, rng, apparatus)
            variant += " · correct memory"
    elif family == "hidden-change":
        changed, kind = _apply_change(rng, split, coeffs)
        change_at = int(rng.integers(1, 4))  # second to fourth experiment: inside every mission
        variant += f" · change {kind} at experiment {change_at + 1}"
    elif family == "unfamiliar":
        coeffs, term = _unanticipated(rng, split, coeffs)
        variant = f"{structure} + {term}"
    else:  # wrong-assumptions
        if rng.random() < 0.5:
            old = dict(coeffs)
            coeffs, kind = _apply_change(rng, split, coeffs)
            wrong_noise = noise_scale * float(rng.choice([0.5, 2.0]))
            memory = remembered(old, wrong_noise, rng, apparatus, age=int(rng.integers(1, 4)))
            variant += f" · stale memory ({kind} changed since)"
        else:
            noise = "student-t3"
            variant += " · heavy-tailed noise"
    world = World(
        coefficients=coeffs,
        noise_scale=noise_scale,
        noise=noise,
        change_at=change_at,
        changed_coefficients=changed,
        seed=seed,
    )
    return Problem(
        problem_id=f"{split}/{family}/{index:03d}",
        split=split,
        family=family,
        index=index,
        world=world,
        memory=memory,
        variant=variant,
        heldout_designs=heldout_designs(seed),
    )


def generate_problems(split: str, count: int, families: tuple[str, ...] = FAMILIES) -> list[Problem]:
    return [make_problem(split, family, i) for family in families for i in range(count)]


def describe_truth(coefficients: dict[str, Any]) -> str:
    terms = [f"{coefficients[t]:+.3g}·{t}" for t in LIBRARY if t in coefficients]
    return "f = " + " ".join(terms)
