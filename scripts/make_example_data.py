"""Regenerate the .npy files used by built-in skill examples.

Run from the repository root: ``python scripts/make_example_data.py``.
Expected outputs in ``examples/*.expected.json`` are the *true* parameters of
these signals, not values copied from a skill's output.
"""

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FS, N = 1000.0, 4096
TONES = [(50.0, 1.0, 0.3), (137.5, 0.5, 1.7)]  # (frequency Hz, amplitude, phase rad)


def tones(rng_seed: int, reps: int, noise_std: float) -> np.ndarray:
    t = np.arange(N) / FS
    clean = sum(a * np.cos(2 * np.pi * f * t + p) for f, a, p in TONES)
    rng = np.random.default_rng(rng_seed)
    return np.vstack([clean + rng.normal(0.0, noise_std, N) for _ in range(reps)])


def save(skill: str, example: str, name: str, array: np.ndarray) -> None:
    target = next(ROOT.glob(f"skills/*/{skill}")) / "examples" / f"{example}.files"
    target.mkdir(parents=True, exist_ok=True)
    np.save(target / name, array, allow_pickle=False)
    print("wrote", (target / name).relative_to(ROOT))


if __name__ == "__main__":
    two = tones(20261030, 1, 0.3)
    save("spectral-peaks", "two-tones", "signals.npy", two)
    save("sinusoid-fit", "two-tones", "signals.npy", two)
    save("tone-presence-test", "present-and-absent", "signals.npy", tones(20261031, 5, 0.3))
