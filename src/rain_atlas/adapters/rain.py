"""Local export against a verified R.A.I.N. contract; never submits to a runtime."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..ledger.store import Ledger

SCHEMA_BLOB = "f4e3c298713efe6d8269e42a3e52e591cb5f926e"
CONTRACT = "https://github.com/topherchris420/lop-nur-twin/blob/main/src/rain/experiments/schemas/submission.schema.json"


def submission(ledger: Ledger, experiment: str, experiment_id: str, version: int) -> dict:
    """Project a completed synthetic study. The host owns its registered verdict.

    Includes aggregate measurements and artifact digests, no local paths, raw
    inputs, vault, model prompts, or operator identity. Free text still needs
    operator privacy review. Registration IDs and versions are operator supplied.
    """
    if not re.fullmatch(r"V3D-EXP-[0-9]{4,}", experiment_id) or type(version) is not int or version < 1:
        raise ValueError("provide an existing R.A.I.N. experiment ID (V3D-EXP-0001) and positive version")
    problems = ledger.verify()
    if problems:
        raise ValueError("source ledger failed verification: " + "; ".join(problems[:3]))
    records = [(e, r) for e, r in ledger.records() if r.get("experiment") == experiment]
    runs = [r for e, r in records if e.kind == "run"]
    datasets = [r for e, r in records if e.kind == "dataset"]
    reports = [r for e, r in records if e.kind == "report"]
    prereg = ledger.get_json(experiment)
    protocol = prereg.get("design", {}).get("protocol")
    if not datasets or any(d["origin"] != "synthetic" for d in datasets):
        raise ValueError("adapter only exports explicitly synthetic studies")
    if not runs or not reports:
        raise ValueError("completed runs and a report are required")
    commit = runs[0].get("environment", {}).get("atlas_commit") or ""
    if not re.fullmatch(r"[0-9a-f]{7,64}(?:-dirty)?", commit):
        raise ValueError("a recorded source commit is required for R.A.I.N. provenance")
    artifacts = {}
    for r in runs:
        for name, meta in r.get("artifacts", {}).items():
            digest = meta["sha256"][7:]
            artifacts[digest] = {
                "name": "artifact-" + digest[:16] + Path(name).suffix[:16],
                "sha256": digest,
                "bytes": meta["bytes"],
                "kind": "simulated-output",
            }
    if len(artifacts) > 256:
        raise ValueError("more than 256 artifacts; select a smaller experiment")
    replications = [r for e, r in records if e.kind == "reproduction"]
    measurements = {
        "recorded_runs": len(runs),
        "successful_runs": sum(r["status"] == "ok" for r in runs),
        "total_runtime_s": sum(r.get("wall_s", 0) for r in runs),
        "exact_reproductions": sum(r["outputs_match"] and r["artifacts_match"] for r in replications),
        "recorded_claims": sum(e.kind == "claim" for e, _ in records),
    }
    result = {
        "schema_version": "rain-experiment-submission/v1",
        "experiment_id": experiment_id,
        "experiment_version": version,
        "evidence_class": "simulated",
        "started_at": runs[0]["started_at"],
        "finished_at": runs[-1]["ended_at"],
        "seed": runs[0]["seed"],
        "parameters": {"atlas_protocol": protocol},
        "inputs": {"atlas_preregistration": experiment},
        "measurements": measurements,
        "series": {},
        "observations": [
            "ATLAS exports measurements only; the receiving host evaluates its own registered criteria."
        ],
        "limitations": [
            "Export-only adapter; no HTTP submission or external runtime acceptance has been demonstrated.",
            "Aggregate measurements are not a substitute for domain-specific host criteria.",
        ]
        + reports[-1]["limitations"],
        "artifacts": list(artifacts.values()),
        "models": [],
        "provenance": {
            "producer": "R.A.I.N. ATLAS / Vers3Dynamics",
            "repository": "https://github.com/topherchris420/rain-atlas",
            "commit": commit.removesuffix("-dirty"),
            "dirty": commit.endswith("-dirty"),
            "atlas_experiment": experiment,
            "source_head": list(ledger.entries())[-1].hash,
            "adapter_version": "1.0.0",
            "external_schema_blob": SCHEMA_BLOB,
            "engine_source_hashes": sorted({r.get("engine_source_hash", "unrecorded") for r in runs}),
        },
    }
    if len(result["limitations"]) > 100 or any(
        not isinstance(v, str) or not 1 <= len(v) <= 2000 for v in result["limitations"]
    ):
        raise ValueError("limitations exceed the verified R.A.I.N. schema bounds")
    if type(result["seed"]) is not int or not 0 <= result["seed"] <= 4294967295:
        raise ValueError("seed outside the R.A.I.N. contract")
    json.dumps(result, allow_nan=False)
    return result


def export(ledger: Ledger, experiment: str, experiment_id: str, version: int, destination: Path) -> Path:
    data = submission(ledger, experiment, experiment_id, version)
    target = Path(destination).resolve()
    if target == ledger.root.resolve() or ledger.root.resolve() in target.parents:
        raise ValueError("export destination must be outside the source ledger")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
    return target
