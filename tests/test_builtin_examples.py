"""Every built-in skill's declared examples pass in the bounded executor."""

import pytest

from rain_atlas.skills.catalog import load_catalog
from rain_atlas.skills.examples import compare, run_example
from rain_atlas.skills.registry import Registry

from conftest import BUILTIN

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
