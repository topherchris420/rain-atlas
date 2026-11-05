"""Generate a typed stress-benchmark skill and analytic configuration fixture.

Committed outputs are canonical; see make_resonance_skills.py on regenerating.
"""

import json
from pathlib import Path

from make_resonance_skills import ART, N, S, schema

ROOT = Path(__file__).resolve().parents[1]
INTEGER = {"type": "integer"}
ARRAY = {"type": "array", "items": N}
STRINGS = {"type": "array", "items": S}
RATE = schema({"rate": N, "low": N, "high": N, "n": INTEGER, "successes": INTEGER, "alpha": N, "method": S})
NULL_RATE = {"anyOf": [RATE, {"type": "null"}]}
METHOD = schema(
    {
        "false_positive_trial_rate": NULL_RATE,
        "false_negative_trial_rate": NULL_RATE,
        "all_recovered_rate": NULL_RATE,
        "conditional_matched_rmse_hz": {"type": ["number", "null"]},
        "matched_samples": INTEGER,
        "detection_counts": ARRAY,
        "runtime_total_s": N,
        "runtime_median_s": N,
    }
)
ROW = schema(
    {
        "case": S,
        "truth_hz": {"type": ["array", "null"], "items": N},
        "truth_status": S,
        "methods": schema({"welch": METHOD, "nls-bic": METHOD}),
        "method_disagreement": RATE,
    }
)
RESULT = schema(
    {
        "protocol": S,
        "trials_per_case": INTEGER,
        "seed": INTEGER,
        "fs": N,
        "n": INTEGER,
        "nperseg": INTEGER,
        "tolerance_hz": N,
        "alpha": N,
        "rows": {"type": "array", "items": ROW},
        "calibration": S,
        "limitations": STRINGS,
    }
)


def main():
    path = ROOT / "skills" / "evaluation" / "spectral-stress-benchmark"
    (path / "examples").mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "atlas.skill/v1",
        "name": path.name,
        "version": "1.0.0",
        "kind": "executable",
        "domain": "evaluation",
        "summary": "Measure classical spectral failure rates under violated assumptions.",
        "capabilities": ["benchmark.spectral-stress"],
        "entrypoint": "run.py",
        "determinism": "stochastic",
        "inputs": schema({"trials": {"type": "integer", "minimum": 3, "maximum": 200}}),
        "outputs": schema({"results": RESULT, "artifact": ART}),
        "permissions": {"network": False, "subprocess": False, "read": ["inputs"], "write": ["outputs"]},
        "limits": {"timeout_s": 600, "memory_mb": 1024},
        "requires": {
            "python": ">=3.11",
            "packages": {"numpy": ">=2.0", "scipy": ">=1.13", "rain-atlas": ">=0.1"},
        },
        "examples": [{"name": "configuration", "seed": 42, "tolerance": {"abs": 1e-12}}],
        "limitations": [
            "Seeded scientific quantities; runtime measurements are intentionally nondeterministic.",
            "Small fixed synthetic suite; intervals concern trial events, not calibrated physical truth.",
            "A chirp has no stationary tone truth; its detections are explicitly unscored.",
        ],
        "references": ["docs/BENCHMARKS.md"],
    }
    for name, value in [
        ("skill.json", manifest),
        ("examples/configuration.input.json", {"trials": 3}),
        (
            "examples/configuration.expected.json",
            {"results": {"protocol": "atlas.spectral-stress/v1", "fs": 128, "n": 1024, "trials_per_case": 3}},
        ),
    ]:
        (path / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    (path / "run.py").write_text(
        "from rain_atlas.bench.spectral import run as evaluate\n\n\ndef run(inputs, ctx):\n    return evaluate(inputs, ctx)\n",
        encoding="utf-8",
        newline="\n",
    )
    (path / "SKILL.md").write_text(
        "---\nname: spectral-stress-benchmark\ndescription: Measure false detections and missed tones with classical baselines. Use for diagnostic stress evaluation.\nlicense: MIT\n---\n\n# Spectral stress benchmark\n\nRun `atlas skills test spectral-stress-benchmark`. The example checks configuration;\n`tests/test_bench.py` checks errors, null controls and unknown-truth treatment.\nSee docs/BENCHMARKS.md for rates, assumptions and failure conditions.\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
