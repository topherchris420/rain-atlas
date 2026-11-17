"""Differential conformance: the real Mem0 SDK versus the ATLAS replica.

Reference: mem0ai 2.2.1 (Apache-2.0) executed locally with:

* the default in-memory qdrant vector store (no server);
* a deterministic fake embedding function (no network, no API key use);
* ``infer=False`` -- the reference's documented raw-add path that does not
  call a language model.

The replica (``rain_atlas.memory.ScientificMemory``) runs the same
scenarios. We compare *documented behavioral invariants*, not incidental
details (the reference uses random UUIDs and wall-clock timestamps; the
replica is deterministic -- a recorded deviation).

This module skips when ``mem0`` is not importable, so the standard ATLAS
suite never requires it. Run it in the reference environment recorded in
``docs/REA.md`` to execute the comparison.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from rain_atlas.memory import ScientificMemory

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mem0") is None,
    reason="mem0 reference SDK not installed in this environment",
)

MEM0_SPEC = importlib.util.find_spec("mem0") is not None


def _fake_embed(text, memory_action=None):
    """Deterministic embedding: hashed bag-of-words vector, unit-normalized."""

    import hashlib
    import math

    tokens = [t for t in __import__("re").findall(r"[a-z0-9]+", text.lower())]
    vector = [0.0] * 64
    for token in tokens:
        digest = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vector[digest % 64] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 8) for v in vector]


@pytest.fixture()
def reference_memory(tmp_path: Path):
    import os

    os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")
    os.environ.setdefault("MEM0_TELEMETRY", "False")
    from mem0 import Memory

    memory = Memory.from_config(
        {
            "embedder": {
                "provider": "openai",
                "config": {"embedding_dims": 64, "api_key": "offline-test-key"},
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "embedding_model_dims": 64,
                    "path": str(tmp_path / "qdrant"),
                },
            },
            "history_db_path": str(tmp_path / "history.db"),
        }
    )
    memory.embedding_model.embed = _fake_embed
    yield memory


@pytest.fixture()
def replica_memory(tmp_path: Path):
    return ScientificMemory(root=tmp_path / "replica", clock=lambda: 1760000000.0)


SCENARIOS = [
    {
        "name": "raw-add-events",
        "messages": [{"role": "user", "content": "The critical frequency is 440 Hz"}],
    },
    {
        "name": "raw-add-two-scopes",
        "messages": [{"role": "user", "content": "The sample is stable"}],
    },
]


class TestDifferentialConformance:
    def test_vendored_scoring_matches_installed_reference(self):
        """The vendored Apache-2.0 scoring must equal the installed reference."""

        from mem0.utils.lemmatization import (  # type: ignore[import-not-found]
            lemmatize_for_bm25 as ref_lemmatize,
        )
        from mem0.utils.scoring import (  # type: ignore[import-not-found]
            get_bm25_params as ref_params,
        )
        from mem0.utils.scoring import (
            normalize_bm25 as ref_normalize,
        )
        from mem0.utils.scoring import (
            score_and_rank as ref_rank,
        )

        from rain_atlas.memory.vendor.mem0 import (
            get_bm25_params,
            lemmatize_for_bm25,
            normalize_bm25,
            score_and_rank,
        )

        queries = [
            "",
            "one",
            "phase locking in coupled oscillators today",
            " ".join(f"term{i}" for i in range(20)),
        ]
        for query in queries:
            assert get_bm25_params(query) == ref_params(query)
            # Without spaCy both lemmatizers fall back to the original text.
            assert lemmatize_for_bm25(query) == ref_lemmatize(query)

        for raw in (0.0, 1.5, 5.0, 7.3, 12.0, 40.0):
            for midpoint, steepness in ((5.0, 0.7), (7.0, 0.6), (12.0, 0.5)):
                assert normalize_bm25(raw, midpoint, steepness) == ref_normalize(raw, midpoint, steepness)

        results = [
            {"id": "a", "score": 0.9, "payload": {"k": 1}},
            {"id": "b", "score": 0.05, "payload": {"k": 2}},
            {"id": "c", "score": 0.5, "payload": {"k": 3}},
        ]
        bm25 = {"a": 0.7, "b": 0.95, "c": 0.1}
        entity = {"c": 0.4}
        for threshold in (0.0, 0.1, 0.6):
            for top_k in (1, 3, 10):
                ours = score_and_rank(results, bm25, entity, threshold, top_k)
                theirs = ref_rank(results, bm25, entity, threshold, top_k)
                assert ours == theirs
                # The installed 2.2.1 release names explain-detail keys differently
                # than the pinned repository commit the vendored copy preserves
                # (semantic vs semantic_score, ...). Ranking scores and order
                # must still agree; that is the behavioral contract.
                ours_x = score_and_rank(results, bm25, entity, threshold, top_k, explain=True)
                theirs_x = ref_rank(results, bm25, entity, threshold, top_k, explain=True)
                assert [item["score"] for item in ours_x] == [item["score"] for item in theirs_x]
                assert [item["id"] for item in ours_x] == [item["id"] for item in theirs_x]

    def test_reference_add_returns_event_results(self, reference_memory):
        result = reference_memory.add(SCENARIOS[0]["messages"], user_id="scientist-1", infer=False)
        assert "results" in result
        entry = result["results"][0]
        assert {"id", "memory", "event"} <= set(entry)
        assert entry["event"] == "ADD"
        assert entry["memory"] == "The critical frequency is 440 Hz"

    def test_replica_matches_reference_add_shape(self, replica_memory):
        result = replica_memory.add(SCENARIOS[0]["messages"], user_id="scientist-1", infer=False)
        entry = result["results"][0]
        assert {"id", "memory", "event"} <= set(entry)
        assert entry["event"] == "ADD"
        assert entry["memory"] == "The critical frequency is 440 Hz"

    def test_reference_scope_isolation(self, reference_memory):
        reference_memory.add([{"role": "user", "content": "alpha fact"}], user_id="u1", infer=False)
        reference_memory.add([{"role": "user", "content": "beta fact"}], user_id="u2", infer=False)
        only_u1 = reference_memory.get_all(filters={"user_id": "u1"})
        only_u2 = reference_memory.get_all(filters={"user_id": "u2"})
        assert [r["memory"] for r in only_u1["results"]] == ["alpha fact"]
        assert [r["memory"] for r in only_u2["results"]] == ["beta fact"]

    def test_replica_scope_isolation_matches(self, replica_memory):
        replica_memory.add([{"role": "user", "content": "alpha fact"}], user_id="u1", infer=False)
        replica_memory.add([{"role": "user", "content": "beta fact"}], user_id="u2", infer=False)
        only_u1 = replica_memory.get_all(filters={"user_id": "u1"})
        only_u2 = replica_memory.get_all(filters={"user_id": "u2"})
        assert [r["memory"] for r in only_u1["results"]] == ["alpha fact"]
        assert [r["memory"] for r in only_u2["results"]] == ["beta fact"]

    def test_reference_requires_entity_scope_for_search(self, reference_memory):
        with pytest.raises(ValueError):
            reference_memory.search("fact")

    def test_replica_requires_entity_scope_for_search(self, replica_memory):
        with pytest.raises(ValueError):
            replica_memory.search("fact")

    def test_reference_update_writes_history(self, reference_memory):
        added = reference_memory.add(
            [{"role": "user", "content": "the threshold is 0.5"}],
            user_id="u9",
            infer=False,
        )
        memory_id = added["results"][0]["id"]
        reference_memory.update(memory_id, "the threshold is 0.7")
        history = reference_memory.history(memory_id)
        events = [entry["event"] for entry in history]
        assert events[0] == "ADD"
        assert "UPDATE" in events
        update_entry = next(e for e in history if e["event"] == "UPDATE")
        assert update_entry["old_memory"] == "the threshold is 0.5"
        assert update_entry["new_memory"] == "the threshold is 0.7"

    def test_replica_update_writes_equivalent_history(self, replica_memory):
        added = replica_memory.add(
            [{"role": "user", "content": "the threshold is 0.5"}],
            user_id="u9",
            infer=False,
        )
        memory_id = added["results"][0]["id"]
        replica_memory.update(memory_id, "the threshold is 0.7")
        history = replica_memory.history(memory_id)
        events = [entry["event"] for entry in history]
        assert events == ["ADD", "UPDATE"]
        update_entry = history[-1]
        assert update_entry["prev_value"] == "the threshold is 0.5"
        assert update_entry["new_value"] == "the threshold is 0.7"

    def test_reference_delete_hides_and_records(self, reference_memory):
        added = reference_memory.add([{"role": "user", "content": "temporary"}], user_id="u8", infer=False)
        memory_id = added["results"][0]["id"]
        reference_memory.delete(memory_id)
        remaining = reference_memory.get_all(filters={"user_id": "u8"})
        assert remaining["results"] == []
        history = reference_memory.history(memory_id)
        assert any(entry["event"] == "DELETE" for entry in history)

    def test_replica_delete_hides_and_records(self, replica_memory):
        added = replica_memory.add([{"role": "user", "content": "temporary"}], user_id="u8", infer=False)
        memory_id = added["results"][0]["id"]
        replica_memory.delete(memory_id)
        remaining = replica_memory.get_all(filters={"user_id": "u8"})
        assert remaining["results"] == []
        history = replica_memory.history(memory_id)
        assert any(entry["event"] == "DELETE" for entry in history)

    def test_reference_search_returns_scored_results(self, reference_memory):
        reference_memory.add(
            [
                {"role": "user", "content": "phase locking in coupled oscillators"},
                {"role": "user", "content": "spectral estimation of tones"},
            ],
            user_id="u7",
            infer=False,
        )
        found = reference_memory.search("phase locking oscillators", filters={"user_id": "u7"})
        assert found["results"]
        top = found["results"][0]
        assert {"id", "memory", "score"} <= set(top)
        assert top["memory"] == "phase locking in coupled oscillators"

    def test_replica_search_returns_scored_results(self, replica_memory):
        replica_memory.add(
            [
                {"role": "user", "content": "phase locking in coupled oscillators"},
                {"role": "user", "content": "spectral estimation of tones"},
            ],
            user_id="u7",
            infer=False,
        )
        found = replica_memory.search("phase locking oscillators", filters={"user_id": "u7"})
        assert found["results"]
        top = found["results"][0]
        assert {"id", "memory", "score"} <= set(top)
        assert top["memory"] == "phase locking in coupled oscillators"
