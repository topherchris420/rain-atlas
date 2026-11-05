import math

import numpy as np
import pytest

from rain_atlas.canonical import (
    canonical_bytes,
    from_jsonable,
    sha256_json,
    to_jsonable,
    tree_files,
    tree_hash,
)


def test_canonical_bytes_sorted_and_compact():
    assert canonical_bytes({"b": 1, "a": [1, 2], "é": "ü"}) == '{"a":[1,2],"b":1,"é":"ü"}'.encode("utf-8")


def test_hash_independent_of_key_order():
    assert sha256_json({"x": 1, "y": 2}) == sha256_json({"y": 2, "x": 1})
    assert sha256_json({"x": 1}).startswith("sha256:")


def test_non_finite_floats_round_trip():
    value = {"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf"), "ok": 1.5}
    encoded = to_jsonable(value)
    canonical_bytes(encoded)  # must not raise: no bare NaN in JSON
    decoded = from_jsonable(encoded)
    assert math.isnan(decoded["nan"]) and decoded["inf"] == math.inf and decoded["ninf"] == -math.inf
    assert decoded["ok"] == 1.5


def test_numpy_values_become_plain_json():
    encoded = to_jsonable({"a": np.float64(2.5), "b": np.int64(3), "c": np.array([1.0, 2.0])})
    assert encoded == {"a": 2.5, "b": 3, "c": [1.0, 2.0]}


def test_nan_is_encoded_not_emitted_bare():
    assert canonical_bytes(float("nan")) == b'{"$float":"nan"}'


def test_tree_hash_ignores_pycache_and_tracks_content(tmp_path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    first = tree_hash(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"\0")
    assert tree_hash(tmp_path) == first
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    assert tree_hash(tmp_path) != first
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    assert tree_hash(tmp_path) != first


MIXED_CASE_TREE = {
    "SKILL.md": b"# skill\n",
    "Zeta.txt": b"z\n",
    "alpha/beta.txt": b"b\n",
    "alpha-gamma.txt": b"g\n",
    "examples/a.json": b"{}\n",
    "run.py": b"def run(i, c):\n    return {}\n",
}


def _write_tree(root, files):
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)


def test_tree_order_is_code_point_order_of_components_on_every_os(tmp_path):
    # Regression: sorting Path objects is case-insensitive on Windows only, so
    # every skill (all contain SKILL.md) hashed differently on Windows and POSIX.
    _write_tree(tmp_path, MIXED_CASE_TREE)
    assert [name for name, _ in tree_files(tmp_path)] == [
        "SKILL.md",
        "Zeta.txt",
        "alpha/beta.txt",
        "alpha-gamma.txt",
        "examples/a.json",
        "run.py",
    ]


def test_tree_hash_is_pinned_across_platforms(tmp_path):
    # Golden value computed independently from the ordering rule above. A
    # platform that orders or encodes differently fails here, before its
    # hashes reach a ledger, an approval pin or a proposal.
    _write_tree(tmp_path, MIXED_CASE_TREE)
    assert tree_hash(tmp_path) == "sha256:35934484e1c5fe5888c9a9fe5fddafb25909d91395334fe481c7cef111a920c0"


def test_tree_hash_refuses_symlinks(tmp_path):
    (tmp_path / "real.txt").write_text("x", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    except OSError:
        pytest.skip("creating symlinks needs extra privileges on this system")
    with pytest.raises(ValueError):
        tree_hash(tmp_path)
