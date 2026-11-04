"""Simulation and independent analysis entrypoints for the synchronization study."""

from __future__ import annotations

import itertools
import math

import numpy as np

from .resonance import kuramoto, order_parameter
from .uncertainty import mean_interval


def simulate(inputs: dict, ctx) -> dict:
    dt = inputs["dt"]
    duration = inputs["duration_s"]
    reps = inputs["replicates"]
    steps = round(duration / dt)
    conditions = [
        {"coupling": float(k), "diffusion": float(d), "phase_lag": float(lag)}
        for lag, d, k in itertools.product(inputs["phase_lags"], inputs["diffusions"], inputs["couplings"])
    ]
    if not math.isclose(steps * dt, duration, abs_tol=1e-9):
        raise ValueError("duration must be a multiple of dt")
    if len(conditions) * reps * (steps + 1) * 2 > 12_000_000:
        raise ValueError("sweep exceeds 12 million scalar samples")
    rng = ctx.rng()
    paths = []
    for index, c in enumerate(conditions):
        initial = rng.uniform(-np.pi, np.pi, size=(reps, 2))
        paths.append(
            kuramoto(
                [-0.5, 0.5],
                initial,
                c["coupling"],
                dt=dt,
                steps=steps,
                diffusion=c["diffusion"],
                phase_lag=c["phase_lag"],
                seed=ctx.seed + index * 997,
            )
        )
    return {
        "phases": ctx.save_array("synchronization-phases.npy", np.asarray(paths)),
        "conditions": conditions,
        "dt": dt,
        "duration_s": duration,
        "replicates": reps,
        "omega_rad_s": [-0.5, 0.5],
        "unit": "rad",
        "integrator": "RK4 when D=0; Euler-Maruyama otherwise",
    }


def measure(inputs: dict, ctx) -> dict:
    paths = ctx.load_array(inputs["phases"])
    if (
        paths.ndim != 4
        or paths.shape[-1] != 2
        or paths.shape[0] != len(inputs["conditions"])
        or not np.isfinite(paths).all()
    ):
        raise ValueError("expected finite (condition, replicate, time, 2) phases")
    dt = inputs["dt"]
    start = round(inputs["burn_s"] / dt)
    if start < 0 or paths.shape[2] - start < 80 or paths.shape[1] < 3:
        raise ValueError("need >=80 post-burn samples and >=3 independent replicates")
    alpha = 0.05 / (len(inputs["conditions"]) * 2)  # two families: primary and independent metrics
    rows = []
    for condition, path in zip(inputs["conditions"], paths):
        tail = path[:, start:]
        delta = tail[:, :, 1] - tail[:, :, 0]
        if inputs["method"] == "phase":
            values = np.abs(np.mean(np.exp(1j * delta), axis=1))
            interval = mean_interval(values, alpha)
            outcome = (
                "corroborated"
                if interval["low"] > 0.9
                else "contradicted"
                if interval["high"] < 0.5
                else "inconclusive"
            )
            metric = "temporal PLV"
            unit = "dimensionless"
        elif inputs["method"] == "frequency":
            # OLS slopes in 8 disjoint windows; mean absolute relative angular
            # velocity is an independent time-domain observable, not PLV.
            size = delta.shape[1] // 8
            blocks = delta[:, : size * 8].reshape(delta.shape[0], 8, size)
            t = np.arange(size) * dt
            t = t - t.mean()
            slopes = np.einsum("rbt,t->rb", blocks, t) / float(t @ t)
            values = np.mean(np.abs(slopes), axis=1)
            interval = mean_interval(values, alpha)
            outcome = (
                "corroborated"
                if interval["high"] < 0.05
                else "contradicted"
                if interval["low"] > 0.15
                else "inconclusive"
            )
            metric = "mean absolute blockwise relative frequency"
            unit = "rad/s"
        else:
            raise ValueError("unknown analysis method")
        rows.append(
            {
                "condition": condition,
                "metric": metric,
                "unit": unit,
                "interval": interval,
                "values": values.tolist(),
                "outcome": outcome,
                "mean_order": float(order_parameter(tail).mean()),
            }
        )
    return {
        "rows": rows,
        "method": inputs["method"],
        "interval_assumption": "approximate Student-t intervals over independent trajectories; Bonferroni across conditions and two metric families",
        "samples_per_replicate": paths.shape[2] - start,
        "replicates": paths.shape[1],
    }
