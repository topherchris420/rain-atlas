"""Tests for the BLACK GLASS native behavioural-reconstruction subsystem.

These exercise the model, comparison laboratory, reconstruction engine, native
routine explorer and evolution analyzer with synthetic observations, plus the
clean-room models against the standard library. The end-to-end test over the
*committed* BusyBox observations lives in
``test_blackglass_busybox_reconstruction.py`` and needs no analysis tool at test
time (it reads the committed derived facts).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random

import pytest

from rain_atlas.blackglass.behavior import validate
from rain_atlas.blackglass.comparison import compare_spec_to_observation
from rain_atlas.blackglass.evolution import analyze_evolution
from rain_atlas.blackglass.explorer import load_reconstruction, observations_from_document, select, summary
from rain_atlas.blackglass.reconstructions import base64_encode, md5_hex, sha1_hex
from rain_atlas.blackglass.routines import (
    BehaviorSpec,
    BehaviorVector,
    ObservedFact,
    ReconstructedRoutine,
    RoutineObservation,
)

SHA = "sha256:" + "a" * 64


def _obs(name="f", entry="0x1000", *, size=64, facts=(), binary="bin/x", sha=SHA):
    return RoutineObservation(
        binary=binary,
        binary_sha256=sha,
        entry=entry,
        name=name,
        size=size,
        architecture="x86-64",
        tool="ghidra-headless",
        tool_version="12.1.4",
        settings="default",
        facts=tuple(facts),
    )


def test_clean_room_models_match_stdlib():
    random.seed(7)
    for _ in range(200):
        b = os.urandom(random.randint(0, 160))
        assert md5_hex(b.hex()) == hashlib.md5(b).hexdigest()
        assert sha1_hex(b.hex()) == hashlib.sha1(b).hexdigest()
        assert base64_encode(b.hex()) == base64.b64encode(b).decode()


def test_observed_fact_rejects_unknown_kind():
    with pytest.raises(ValueError):
        ObservedFact("not-a-kind", "detail")


def test_routine_observation_requires_sha_prefix():
    with pytest.raises(ValueError):
        _obs(sha="deadbeef")


def test_compare_spec_corroborates_when_constant_present():
    spec = BehaviorSpec(
        name="md5",
        summary="",
        inputs="",
        outputs="",
        steps=(),
        expects_constants=("0xd76aa478",),
    )
    obs = _obs(facts=[ObservedFact("constant", "uses constant 0xd76aa478", target="0xd76aa478")])
    result = compare_spec_to_observation(spec, obs)
    assert result["outcome"] == "corroborated"
    assert result["constants_present"] == ["0xd76aa478"]


def test_compare_spec_contradicts_when_constant_absent():
    spec = BehaviorSpec(
        name="md5", summary="", inputs="", outputs="", steps=(), expects_constants=("0xd76aa478",)
    )
    obs = _obs(facts=[ObservedFact("constant", "uses constant 0x12345678", target="0x12345678")])
    result = compare_spec_to_observation(spec, obs)
    assert result["outcome"] == "contradicted"
    assert result["constants_missing"] == ["0xd76aa478"]


def test_compare_spec_inconclusive_when_nothing_predicted():
    spec = BehaviorSpec(name="x", summary="", inputs="", outputs="", steps=())
    assert compare_spec_to_observation(spec, _obs())["outcome"] == "inconclusive"


def test_compare_spec_string_substring_match():
    spec = BehaviorSpec(
        name="base64",
        summary="",
        inputs="",
        outputs="",
        steps=(),
        expects_strings=("ABCDEFGHIJKLMNOP",),
    )
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    obs = _obs(facts=[ObservedFact("string-ref", "references", target=alphabet)])
    assert compare_spec_to_observation(spec, obs)["outcome"] == "corroborated"


def test_validate_requires_both_vectors_and_evidence():
    # A correct model whose predicted evidence is present → validated.
    spec = BehaviorSpec(name="id", summary="", inputs="", outputs="", steps=(), expects_constants=("0x5",))
    obs = _obs(facts=[ObservedFact("constant", "uses constant 0x5", target="0x5")])
    good = ReconstructedRoutine(
        observation=obs,
        spec=spec,
        model=lambda x: x,
        vectors=(BehaviorVector("v", {"x": 3}, 3, "standard"),),
    )
    result = validate(good)
    assert result.validated and result.passed == 1

    # Same model but the predicted constant is missing → not validated.
    obs_missing = _obs(facts=[ObservedFact("constant", "c", target="0x9")])
    bad_ev = ReconstructedRoutine(
        observation=obs_missing,
        spec=spec,
        model=lambda x: x,
        vectors=(BehaviorVector("v", {"x": 3}, 3, "standard"),),
    )
    assert not validate(bad_ev).validated

    # A model that disagrees with its vector → not validated.
    wrong = ReconstructedRoutine(
        observation=obs,
        spec=spec,
        model=lambda x: x + 1,
        vectors=(BehaviorVector("v", {"x": 3}, 3, "standard"),),
    )
    r = validate(wrong)
    assert not r.validated and r.passed == 0


def _doc():
    return {
        "schema": "blackglass.native-reconstruction/v1",
        "tool": "ghidra-headless",
        "tool_version": "12.1.4",
        "binary": "bin/busybox",
        "sha256": SHA,
        "architecture": "x86",
        "routines": [
            {
                "entry": "0x4b4cb6",
                "name": "FUN_004b4cb6",
                "size": 52,
                "basic_blocks": 1,
                "callees": [],
                "string_refs": [],
                "constants": ["0xc3d2e1f0", "0x1032547698badcfe"],
                "decompilation_sha256": "sha256:" + "b" * 64,
            },
            {
                "entry": "0x40a567",
                "name": "FUN_0040a567",
                "size": 267,
                "basic_blocks": 22,
                "callees": ["FUN_004047d3"],
                "string_refs": ["ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"],
                "constants": [],
                "decompilation_sha256": None,
            },
        ],
    }


def test_explorer_parses_document_sorted_by_entry():
    obs = observations_from_document(_doc())
    assert [o.entry for o in obs] == ["0x40a567", "0x4b4cb6"]
    sha1 = select(obs, "FUN_004b4cb6")
    assert any(f.kind == "constant" and f.target == "0xc3d2e1f0" for f in sha1.facts)
    assert summary(obs)["routine_count"] == 2


def test_explorer_rejects_wrong_schema():
    with pytest.raises(ValueError):
        observations_from_document({"schema": "other", "routines": []})


def test_explorer_load_from_file(tmp_path):
    p = tmp_path / "reconstruction.json"
    p.write_text(json.dumps(_doc()), encoding="utf-8")
    assert len(load_reconstruction(p)) == 2


def test_evolution_detects_changes():
    base = [
        _obs("md5", "0x100", size=45, facts=[ObservedFact("constant", "c", target="0x1032547698badcfe")]),
        _obs("gone", "0x200", size=10),
    ]
    target = [
        _obs(
            "md5",
            "0x100",
            size=49,
            sha="sha256:" + "c" * 64,
            facts=[
                ObservedFact("constant", "c", target="0x1032547698badcfe"),
                ObservedFact("constant", "c2", target="0xdeadbeef"),
            ],
        ),
        _obs("added", "0x300", size=20, sha="sha256:" + "c" * 64),
    ]
    result = analyze_evolution(base, target, base_label="v1", target_label="v2")
    assert result["added_routines"] == ["added"]
    assert result["removed_routines"] == ["gone"]
    assert result["changed_routines"] == 1
    delta = result["routine_deltas"][0]
    assert delta["size_delta"] == 4
    assert delta["constants_added"] == ["0xdeadbeef"]
    assert not delta["identical_bytes"]
