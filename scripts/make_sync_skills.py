"""Build typed sweep and measurement manifests without running experiments.

Committed outputs are canonical; see make_resonance_skills.py on regenerating.
"""

import json
from pathlib import Path

from make_resonance_skills import ARRAY, ART, N, S, schema

ROOT = Path(__file__).resolve().parents[1]
CONDITION = schema({"coupling": N, "diffusion": N, "phase_lag": N})
conditions = {"type": "array", "minItems": 1, "maxItems": 64, "items": CONDITION}
interval = schema(
    {"mean": N, "low": N, "high": N, "se": N, "n": {"type": "integer"}, "alpha": N, "method": S}
)
row = schema(
    {
        "condition": CONDITION,
        "metric": S,
        "unit": S,
        "interval": interval,
        "values": ARRAY,
        "outcome": {"enum": ["corroborated", "contradicted", "inconclusive"]},
        "mean_order": N,
    }
)
specs = [
    (
        "synchronization-sweep",
        "simulate",
        "resonance.synchronization-sweep",
        schema(
            {
                "couplings": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {**N, "minimum": 0, "maximum": 10},
                },
                "diffusions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {**N, "minimum": 0, "maximum": 2},
                },
                "phase_lags": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {**N, "minimum": 0, "maximum": 1},
                },
                "dt": {**N, "minimum": 0.001, "maximum": 0.1},
                "duration_s": {**N, "minimum": 1, "maximum": 200},
                "replicates": {"type": "integer", "minimum": 3, "maximum": 40},
            }
        ),
        schema(
            {
                "phases": ART,
                "conditions": conditions,
                "dt": N,
                "duration_s": N,
                "replicates": {"type": "integer"},
                "omega_rad_s": ARRAY,
                "unit": S,
                "integrator": S,
            }
        ),
        {
            "couplings": [0],
            "diffusions": [0],
            "phase_lags": [0],
            "dt": 0.05,
            "duration_s": 1,
            "replicates": 3,
        },
        {"omega_rad_s": [-0.5, 0.5], "unit": "rad", "replicates": 3},
    ),
    (
        "synchronization-measure",
        "measure",
        "resonance.synchronization-measure",
        schema(
            {
                "phases": ART,
                "conditions": conditions,
                "dt": {**N, "exclusiveMinimum": 0},
                "burn_s": {**N, "minimum": 0},
                "method": {"enum": ["phase", "frequency"]},
            }
        ),
        schema(
            {
                "rows": {"type": "array", "items": row},
                "method": S,
                "interval_assumption": S,
                "samples_per_replicate": {"type": "integer"},
                "replicates": {"type": "integer"},
            }
        ),
        {
            "phases": {"$artifact": "phases.npy", "sha256": "REPLACE"},
            "conditions": [{"coupling": 2, "diffusion": 0, "phase_lag": 0}],
            "dt": 0.1,
            "burn_s": 0,
            "method": "phase",
        },
        {"rows": [{"outcome": "corroborated", "interval": {"mean": 1}, "mean_order": 1}], "method": "phase"},
    ),
]


def main():
    import hashlib
    import io

    import numpy as np

    for name, method, cap, inp, out, example, expected in specs:
        path = ROOT / "skills" / "resonance" / name
        (path / "examples").mkdir(parents=True, exist_ok=True)
        if method == "measure":
            # Analytical fixture: 3 identical trajectories, 2 equal phases.
            data = np.broadcast_to((np.arange(100) * 0.1)[None, None, :, None], (1, 3, 100, 2)).copy()
            stream = io.BytesIO()
            np.save(stream, data, allow_pickle=False)
            raw = stream.getvalue()
            files = path / "examples" / "analytical.files"
            files.mkdir(exist_ok=True)
            (files / "phases.npy").write_bytes(raw)
            example["phases"]["sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        m = {
            "schema": "atlas.skill/v1",
            "name": name,
            "version": "1.0.0",
            "kind": "executable",
            "domain": "resonance",
            "summary": "Two-oscillator synchronization "
            + (
                "simulation sweep."
                if method == "simulate"
                else "measurement with independent replicate intervals."
            ),
            "capabilities": [cap],
            "entrypoint": "run.py",
            "determinism": "seeded" if method == "simulate" else "deterministic",
            "inputs": inp,
            "outputs": out,
            "permissions": {"network": False, "subprocess": False, "read": ["inputs"], "write": ["outputs"]},
            "limits": {"timeout_s": 180, "memory_mb": 1024},
            "requires": {
                "python": ">=3.11",
                "packages": {"numpy": ">=2.0", "scipy": ">=1.13", "rain-atlas": ">=0.1"},
            },
            "examples": [{"name": "analytical", "seed": 17, "tolerance": {"abs": 1e-10}}],
            "limitations": [
                "Two phase oscillators, synthetic data only; finite-window locking, not a thermodynamic phase transition.",
                "Approximate Student-t intervals over independent simulations; no calibrated probability of physical truth.",
                "PLV and time-domain frequency analysis share raw data; replication uses new seeded trajectories.",
            ],
            "references": ["docs/RESONANCE.md"],
        }
        for file, data in [
            ("skill.json", m),
            ("examples/analytical.input.json", example),
            ("examples/analytical.expected.json", expected),
        ]:
            (path / file).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        (path / "run.py").write_text(
            f"from rain_atlas.science.synchronization import {method}\n\n\ndef run(inputs, ctx):\n    return {method}(inputs, ctx)\n",
            encoding="utf-8",
            newline="\n",
        )
        (path / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {m['summary']} Use for the preregistered synchronization experiment.\nlicense: MIT\n---\n\n# {name}\n\nTyped inputs and outputs are in skill.json. Run the known-answer example with\n`atlas skills test {name}`. Methods, convergence checks and limitations are\nin docs/RESONANCE.md and tests/test_synchronization.py.\n\n"
            + "\n".join("- " + x for x in m["limitations"])
            + "\n",
            encoding="utf-8",
            newline="\n",
        )


if __name__ == "__main__":
    main()
