"""Every built-in skill's declared examples pass in the bounded executor."""

import json
import math

import pytest
from conftest import BUILTIN

from rain_atlas.skills.catalog import load_catalog
from rain_atlas.skills.examples import compare, run_example
from rain_atlas.skills.registry import Registry

CASES = [(src.name, ex["name"]) for src in load_catalog(BUILTIN) for ex in src.manifest.examples]


@pytest.mark.parametrize("skill, example", CASES)
def test_example(skill, example, tmp_path):
    registry = Registry(home=tmp_path / "home", builtin_root=BUILTIN)
    ref = registry.get(skill)
    spec = next(ex for ex in ref.manifest.examples if ex["name"] == example)
    result, problems = run_example(ref, spec, tmp_path / "runs")
    assert problems == [], (result.status, result.error)


def test_compare_semantics():
    tol = {"abs": 0.1}
    assert compare({"a": 1.05, "extra": 2}, {"a": 1.0}, tol) == []
    assert compare({"a": [1, 2]}, {"a": [1]}, tol)
    assert compare({"a": "x"}, {"a": "y"}, tol)
    assert compare({"a": 1.2}, {"a": 1.0}, tol)
    assert compare({"a": True}, {"a": 1}, tol)
    # Regressions: inf - inf is NaN, so an infinite expectation never matched,
    # and a boolean expectation accepted the number 1 (True == 1 in Python).
    assert compare(math.inf, math.inf, tol) == []
    assert compare(1e308, math.inf, tol) and compare(-math.inf, math.inf, tol)
    assert compare(1, True, tol) and compare(0, False, tol) and compare(True, True, tol) == []
    assert compare(0, None, tol) and compare(None, None, tol) == []


def test_expected_files_may_encode_non_finite_values(tmp_path):
    # Canonical JSON writes non-finite floats as {"$float": ...}; expected files
    # are decoded the same way as outputs instead of being compared as objects.
    from rain_atlas.canonical import to_jsonable
    from rain_atlas.skills.examples import load_expected

    path = tmp_path / "x.expected.json"
    path.write_text(json.dumps(to_jsonable({"v": math.inf, "w": [math.nan]})), encoding="utf-8")
    expected = load_expected(path)
    assert compare({"v": math.inf, "w": [math.nan]}, expected, {"abs": 0.0}) == []
    assert compare({"v": 1.0, "w": [0.0]}, expected, {"abs": 0.0})
