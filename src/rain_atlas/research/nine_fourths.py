"""Experimental numerical kernels; legacy evidence replay is unchanged."""

from __future__ import annotations

import json
import platform
from time import perf_counter

import numpy as np


def parameter_gain(precision: np.ndarray, mapping: np.ndarray, grams: np.ndarray) -> np.ndarray:
    """Return 0.5 log det(I + precision^-1 M G M.T) for a batch.

    Inputs are real SPD precision, a finite feature map and symmetric PSD
    Gram matrices. Use the determinant ratio instead of forming an inverse.
    """
    p, m, g = (np.asarray(a, dtype=float) for a in (precision, mapping, grams))
    if p.ndim != 2 or p.shape[0] != p.shape[1] or not p.size:
        raise ValueError("precision must be square and nonempty")
    if m.ndim != 2 or m.shape[0] != p.shape[0] or not m.shape[1]:
        raise ValueError("mapping shape mismatch")
    if g.ndim != 3 or g.shape[1:] != (m.shape[1], m.shape[1]) or not len(g):
        raise ValueError("Gram batch shape mismatch")
    if not all(np.isfinite(a).all() for a in (p, m, g)):
        raise ValueError("nonfinite input")
    if not np.allclose(p, p.T, rtol=1e-10, atol=1e-12):
        raise ValueError("precision must be symmetric")
    if not np.allclose(g, g.swapaxes(-1, -2), rtol=1e-10, atol=1e-12):
        raise ValueError("Gram matrices must be symmetric")
    # Gram PSD is a caller contract. The update must remain SPD.
    base = np.linalg.cholesky(p)
    update = (m @ g) @ m.T
    updated = np.linalg.cholesky(p + update)
    return np.log(np.diagonal(updated, axis1=-2, axis2=-1)).sum(axis=-1) - np.log(np.diag(base)).sum()


def reference_gain(precision: np.ndarray, mapping: np.ndarray, grams: np.ndarray) -> np.ndarray:
    """Correct, independently written direct solve baseline for valid inputs."""
    result = []
    for gram in grams:
        projected = mapping @ gram @ mapping.T
        sign, logdet = np.linalg.slogdet(np.eye(len(precision)) + np.linalg.solve(precision, projected))
        if sign <= 0:
            raise ValueError("nonpositive determinant")
        result.append(0.5 * logdet)
    return np.asarray(result)


def benchmark(seed: int = 42, repeats: int = 7) -> dict:
    """Timing and numerical parity; no hardware-independent speed claim."""
    if repeats < 3 or repeats > 100:
        raise ValueError("repeats must be between 3 and 100")
    rng = np.random.default_rng(seed)
    cases = []
    for batch, width, rank in ((32, 10, 5), (64, 32, 16), (128, 64, 24)):
        x = rng.normal(size=(batch, 64, width))
        g = x.swapaxes(-1, -2) @ x
        m = rng.normal(size=(rank, width))
        q = rng.normal(size=(rank, rank))
        p = q @ q.T + np.eye(rank)
        expected = reference_gain(p, m, g)
        actual = parameter_gain(p, m, g)
        np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)
        times: dict[str, list[float]] = {"reference": [], "factorized": []}
        methods = (("reference", reference_gain), ("factorized", parameter_gain))
        for i in range(repeats):
            for name, method in methods if i % 2 == 0 else methods[::-1]:
                start = perf_counter()
                method(p, m, g)
                times[name].append(perf_counter() - start)
        cases.append(
            {
                "shape": [batch, width, rank],
                "max_absolute_error": float(np.max(np.abs(expected - actual))),
                "median_seconds": {name: float(np.median(values)) for name, values in times.items()},
            }
        )
    return {
        "seed": seed,
        "repeats": repeats,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "cases": cases,
        "scope": "isolated synthetic kernel; not end-to-end mission speed",
    }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
