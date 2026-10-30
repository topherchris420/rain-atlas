"""Run a skill's declared examples and compare outputs with expectations.

Expected files list only what they assert:

* plain keys: compared with the outputs (dicts by subset, lists by length and
  element, numbers within tolerance);
* ``$arrays``: ``{output_key: nested list}`` compared with the ``.npy``
  artifact that output references;
* ``$files``: ``{output_key: {min_bytes, magic, contains}}`` checks on an
  artifact's bytes;
* ``$tolerance``: overrides the manifest example tolerance.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from ..canonical import from_jsonable
from ..exec.policy import HostPolicy
from ..exec.runner import RunResult, SkillRef, run_skill


def _close(actual: float, expected: float, tol: dict) -> bool:
    if math.isnan(expected):
        return math.isnan(actual)
    return abs(actual - expected) <= max(tol.get("abs", 0.0), tol.get("rel", 0.0) * abs(expected))


def compare(actual: Any, expected: Any, tol: dict, path: str = "$") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected an object"]
        problems = []
        for key, value in expected.items():
            if key.startswith("$"):
                continue
            if key not in actual:
                problems.append(f"{path}.{key}: missing")
            else:
                problems.extend(compare(actual[key], value, tol, f"{path}.{key}"))
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected a list"]
        if len(actual) != len(expected):
            return [f"{path}: expected {len(expected)} items, got {len(actual)}"]
        problems = []
        for i, (a, e) in enumerate(zip(actual, expected)):
            problems.extend(compare(a, e, tol, f"{path}[{i}]"))
        return problems
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        return [] if actual == expected else [f"{path}: expected {expected!r}, got {actual!r}"]
    if isinstance(expected, (int, float)):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return [f"{path}: expected a number, got {actual!r}"]
        return [] if _close(float(actual), float(expected), tol) else [f"{path}: expected {expected} ± {tol}, got {actual}"]
    return [f"{path}: unsupported expectation {expected!r}"]


def run_example(skill: SkillRef, example: dict, runs_dir: Path, host: HostPolicy | None = None) -> tuple[RunResult, list[str]]:
    stem = Path(skill.path) / "examples" / example["name"]
    inputs = json.loads(stem.with_name(stem.name + ".input.json").read_text(encoding="utf-8"))
    expected = json.loads(stem.with_name(stem.name + ".expected.json").read_text(encoding="utf-8"))
    files_dir = stem.with_name(stem.name + ".files")
    files = {p.name: p for p in sorted(files_dir.iterdir())} if files_dir.is_dir() else {}
    result = run_skill(skill, inputs, seed=int(example.get("seed", 0)), runs_dir=runs_dir, host=host, files=files)
    if not result.ok:
        return result, [f"run status {result.status}: {(result.error or {}).get('message')}"]
    tol = expected.get("$tolerance", example.get("tolerance", {"abs": 0.0}))
    outputs = from_jsonable(result.outputs)
    problems = compare(outputs, expected, tol)
    out_dir = result.run_dir / "output"
    for key, array in expected.get("$arrays", {}).items():
        ref = outputs.get(key) if isinstance(outputs, dict) else None
        if not isinstance(ref, dict) or "$artifact" not in ref:
            problems.append(f"$arrays.{key}: output is not an artifact reference")
            continue
        got = np.load(io.BytesIO((out_dir / ref["$artifact"]).read_bytes()), allow_pickle=False)
        want = np.asarray(array, dtype=float)
        if got.shape != want.shape:
            problems.append(f"$arrays.{key}: shape {got.shape} != {want.shape}")
        elif not np.allclose(got, want, atol=tol.get("abs", 0.0), rtol=tol.get("rel", 0.0)):
            problems.append(f"$arrays.{key}: max difference {float(np.max(np.abs(got - want)))}")
    for key, checks in expected.get("$files", {}).items():
        ref = outputs.get(key) if isinstance(outputs, dict) else None
        if not isinstance(ref, dict) or "$artifact" not in ref:
            problems.append(f"$files.{key}: output is not an artifact reference")
            continue
        data = (out_dir / ref["$artifact"]).read_bytes()
        if len(data) < checks.get("min_bytes", 0):
            problems.append(f"$files.{key}: only {len(data)} bytes")
        if "magic" in checks and not data.startswith(bytes.fromhex(checks["magic"])):
            problems.append(f"$files.{key}: wrong file signature")
        for needle in checks.get("contains", []):
            if needle.encode("utf-8") not in data:
                problems.append(f"$files.{key}: does not contain {needle!r}")
    return result, problems
