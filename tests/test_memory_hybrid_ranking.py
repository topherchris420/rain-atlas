"""Hybrid ranking tests: vendored Mem0 Apache-2.0 scoring in the engine.

The vendored module (rain_atlas.memory.vendor.mem0) is the reference's own
scoring code; these tests verify it behaves as documented (sigmoid bounds,
query-length parameter tiers, threshold gating, adaptive max_possible divisor)
and that the engine's hybrid search path ranks and gates correctly.
"""

from __future__ import annotations

import math

import pytest

from rain_atlas.memory import ScientificMemory
from rain_atlas.memory.search import okapi_bm25
from rain_atlas.memory.vendor.mem0 import (
    ENTITY_BOOST_WEIGHT,
    get_bm25_params,
    lemmatize_for_bm25,
    normalize_bm25,
    score_and_rank,
)


class TestVendoredScoring:
    def test_sigmoid_bounds_and_midpoint(self):
        assert normalize_bm25(0.0, 5.0, 0.7) == pytest.approx(1.0 / (1.0 + math.exp(3.5)))
        assert normalize_bm25(5.0, 5.0, 0.7) == 0.5
        assert 0.0 < normalize_bm25(100.0, 5.0, 0.7) <= 1.0  # saturates at 1.0 in float

    def test_query_length_tiers(self):
        assert get_bm25_params("one two three") == (5.0, 0.7)
        assert get_bm25_params("one two three four five") == (7.0, 0.6)
        assert get_bm25_params(" ".join(["w"] * 8)) == (9.0, 0.5)
        assert get_bm25_params(" ".join(["w"] * 14)) == (10.0, 0.5)
        assert get_bm25_params(" ".join(["w"] * 20)) == (12.0, 0.5)

    def test_lemmatization_falls_back_without_spacy(self):
        # spaCy is not a dependency; the vendored function must fall back
        # to the original text rather than fail.
        assert lemmatize_for_bm25("the memories are attending") == "the memories are attending"

    def test_score_and_rank_threshold_gates(self):
        results = [
            {"id": "a", "score": 0.05, "payload": {"x": 1}},
            {"id": "b", "score": 0.9, "payload": {"x": 2}},
        ]
        ranked = score_and_rank(results, {"b": 0.8}, {}, threshold=0.1, top_k=10)
        assert [item["id"] for item in ranked] == ["b"]

    def test_score_and_rank_divisors(self):
        base = [{"id": "a", "score": 1.0, "payload": {}}]
        semantic_only = score_and_rank(base, {}, {}, 0.0, 10)[0]["score"]
        with_bm25 = score_and_rank(base, {"a": 1.0}, {}, 0.0, 10)[0]["score"]
        with_entity = score_and_rank(base, {"a": 1.0}, {"a": 0.5}, 0.0, 10)[0]["score"]
        assert semantic_only == 1.0
        assert with_bm25 == 1.0  # (1 + 1) / 2
        assert with_entity == pytest.approx(2.5 / (2.0 + ENTITY_BOOST_WEIGHT))

    def test_score_and_rank_explain_details(self):
        ranked = score_and_rank(
            [{"id": "a", "score": 0.5, "payload": {}}],
            {"a": 0.25},
            {},
            0.1,
            10,
            explain=True,
        )
        assert ranked[0]["score_details"]["bm25"] == 0.25
        assert ranked[0]["score_details"]["max_possible"] == 2.0

    def test_bm25_prefers_repeated_query_terms(self):
        from rain_atlas.memory.models import MemoryRecord

        records = [
            MemoryRecord(id="r1", content="phase locking phase locking phase", scope={"user_id": "u"}),
            MemoryRecord(id="r2", content="spectral estimation of tones", scope={"user_id": "u"}),
        ]
        scores = okapi_bm25("phase locking", records)
        assert scores["r1"] > scores["r2"]


class TestHybridEngineSearch:
    def test_hybrid_is_default_and_ranks_relevant_first(self, tmp_path):
        memory = ScientificMemory(root=tmp_path / "mem", clock=lambda: 1760000000.0)
        assert memory.ranking == "hybrid"
        memory.add(
            [
                {"role": "user", "content": "phase locking in coupled oscillators"},
                {"role": "user", "content": "spectral estimation of tones"},
                {"role": "user", "content": "completely unrelated note about gardening"},
            ],
            user_id="u1",
            infer=False,
        )
        result = memory.search("phase locking oscillators", filters={"user_id": "u1"})
        assert result["results"][0]["memory"] == "phase locking in coupled oscillators"
        for item in result["results"]:
            assert 0.0 <= item["score"] <= 1.0

    def test_hybrid_respects_threshold_and_top_k(self, tmp_path):
        memory = ScientificMemory(root=tmp_path / "mem", clock=lambda: 1760000000.0)
        memory.add(
            [
                {"role": "user", "content": "alpha beta gamma"},
                {"role": "user", "content": "alpha delta"},
                {"role": "user", "content": "unrelated words"},
            ],
            user_id="u1",
            infer=False,
        )
        result = memory.search("alpha", filters={"user_id": "u1"}, top_k=1)
        assert len(result["results"]) == 1
        weak = memory.search("zzz absent terms", filters={"user_id": "u1"}, threshold=0.6)
        assert weak["results"] == []

    def test_lexical_mode_still_available(self, tmp_path):
        memory = ScientificMemory(root=tmp_path / "mem", clock=lambda: 1760000000.0, ranking="lexical")
        memory.add("phase locking in coupled oscillators", user_id="u1", infer=False)
        result = memory.search("phase locking", filters={"user_id": "u1"})
        assert result["results"][0]["score"] > 0

    def test_invalid_ranking_rejected(self):
        with pytest.raises(ValueError, match="ranking"):
            ScientificMemory(ranking="cosmic")

    def test_hybrid_deterministic_across_engines(self, tmp_path):
        a = ScientificMemory(root=tmp_path / "a", clock=lambda: 1.0)
        b = ScientificMemory(root=tmp_path / "b", clock=lambda: 1.0)
        for memory in (a, b):
            memory.add(["phase locking oscillators", "spectral estimation"], user_id="u1", infer=False)
        ra = a.search("phase locking", filters={"user_id": "u1"})
        rb = b.search("phase locking", filters={"user_id": "u1"})
        assert ra == rb
