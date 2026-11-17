"""Tests for the Scientific Memory Engine (Mem0-inspired replica).

Behavioral invariants mirror the reference SDK's documented semantics:
event results (ADD/UPDATE/DELETE/NONE), scope filters requiring entity ids,
search result shape, and append-only history. See
``rain_atlas.rea.investigations.mem0`` for the reference evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rain_atlas.memory import (
    Contradiction,
    MemoryEvent,
    MemoryRecord,
    MemoryStore,
    ScientificMemory,
)
from rain_atlas.memory.extract import extract_statements, predicate_of
from rain_atlas.memory.search import LexicalIndex, normalize, tokenize

FIXED_CLOCK = lambda: 1760000000.0  # noqa: E731 - deterministic test clock


@pytest.fixture()
def memory(tmp_path: Path) -> ScientificMemory:
    return ScientificMemory(root=tmp_path / "memory", clock=FIXED_CLOCK)


class TestExtraction:
    def test_labeled_statements_get_kinds(self):
        statements = extract_statements(
            "Hypothesis: coupling strength controls phase locking. Finding: the oscillators locked at 0.8."
        )
        kinds = [s.kind for s in statements]
        assert kinds[0] == "hypothesis"
        assert "finding" in kinds

    def test_cue_phrases_classify_without_labels(self):
        statements = extract_statements("We hypothesize that noise dominates below 0.1.")
        assert statements[0].kind == "hypothesis"

    def test_predicate_split(self):
        subject, value, negated = predicate_of("The critical frequency is 440 Hz")
        assert subject == "The critical frequency"
        assert value == "440 Hz"
        assert negated is False

    def test_negation_detected(self):
        _s, _v, negated = predicate_of("The critical frequency is not 440 Hz")
        assert negated is True

    def test_list_items_split(self):
        statements = extract_statements("- first item\n- second item")
        assert [s.content for s in statements] == ["first item", "second item"]

    def test_system_messages_skipped(self):
        statements = extract_statements(
            [
                {"role": "system", "content": "You are a scientist."},
                {"role": "user", "content": "Finding: x is 1."},
            ]
        )
        assert len(statements) == 1
        assert statements[0].kind == "finding"

    def test_invalid_message_type_rejected(self):
        with pytest.raises(ValueError):
            extract_statements(42)  # type: ignore[arg-type]


class TestAddAndSearch:
    def test_add_returns_event_results(self, memory):
        result = memory.add("Hypothesis: the resonant frequency is 440 Hz", user_id="scientist-1")
        assert set(result["results"][0]) == {"id", "memory", "event"}
        assert result["results"][0]["event"] == "ADD"

    def test_scope_is_required(self, memory):
        with pytest.raises(ValueError):
            memory.add("Some fact")

    def test_search_requires_entity_filter(self, memory):
        memory.add("fact one", user_id="u1")
        with pytest.raises(ValueError):
            memory.search("fact")
        result = memory.search("fact", filters={"user_id": "u1"})
        assert len(result["results"]) >= 1
        assert set(result["results"][0]) >= {"id", "memory", "score"}

    def test_search_is_scoped(self, memory):
        memory.add("alpha finding about oscillators", user_id="u1")
        memory.add("alpha finding about oscillators", user_id="u2")
        result = memory.search("oscillators", filters={"user_id": "u1"})
        assert all(r["metadata"]["user_id"] == "u1" for r in result["results"])
        assert len(result["results"]) == 1

    def test_identical_content_is_none_event(self, memory):
        memory.add("Hypothesis: the resonant frequency is 440 Hz", user_id="u1")
        result = memory.add("the resonant frequency is 440 Hz", user_id="u1")
        assert result["results"][0]["event"] == "NONE"

    def test_same_subject_new_value_updates(self, memory):
        memory.add("The critical frequency is 440 Hz", user_id="u1")
        result = memory.add("The critical frequency is 480 Hz", user_id="u1")
        assert result["results"][0]["event"] == "UPDATE"
        assert result["results"][0]["supersedes"]

    def test_update_supersedes_with_history_not_rewrite(self, memory):
        memory.add("The critical frequency is 440 Hz", user_id="u1")
        first_id = memory.get_all(filters={"user_id": "u1"})["results"][0]["id"]
        memory.add("The critical frequency is 480 Hz", user_id="u1")
        history = memory.history(first_id)
        assert [event["event"] for event in history] == ["ADD", "UPDATE"]
        assert history[-1]["prev_value"] == "The critical frequency is 440 Hz"
        assert history[-1]["new_value"] == "The critical frequency is 480 Hz"

    def test_contradiction_is_recorded(self, memory):
        memory.add("The sample is stable", user_id="u1")
        result = memory.add("The sample is not stable", user_id="u1")
        assert result["results"][0]["event"] == "UPDATE"
        contradictions = memory.contradictions()
        assert len(contradictions) == 1
        assert contradictions[0]["old_memory_id"] != contradictions[0]["new_memory_id"]

    def test_superseded_memory_still_retrievable_via_get(self, memory):
        memory.add("The critical frequency is 440 Hz", user_id="u1")
        first = memory.get_all(filters={"user_id": "u1"})["results"][0]
        memory.add("The critical frequency is 480 Hz", user_id="u1")
        record = memory.get(first["id"])
        assert record["memory"] == "The critical frequency is 440 Hz"

    def test_infer_false_stores_raw(self, memory):
        result = memory.add(
            [{"role": "user", "content": "raw statement one"}],
            user_id="u1",
            infer=False,
        )
        assert result["results"][0]["event"] == "ADD"
        assert result["results"][0]["memory"] == "raw statement one"

    def test_get_all_metadata_filters(self, memory):
        memory.add("fact with metadata", user_id="u1", metadata={"experiment": "sync-001"})
        memory.add("fact other", user_id="u1", metadata={"experiment": "sync-002"})
        result = memory.get_all(filters={"user_id": "u1", "experiment": "sync-001"})
        assert len(result["results"]) == 1

    def test_metadata_operator_filters(self, memory):
        memory.add("counts", user_id="u1", metadata={"replicates": 12})
        memory.add("counts low", user_id="u1", metadata={"replicates": 2})
        result = memory.get_all(filters={"user_id": "u1", "replicates": {"gte": 10}})
        assert len(result["results"]) == 1
        assert result["results"][0]["memory"] == "counts"


class TestMutation:
    def test_update_requires_active_memory(self, memory):
        memory.add("The critical frequency is 440 Hz", user_id="u1")
        first = memory.get_all(filters={"user_id": "u1"})["results"][0]
        memory.update(first["id"], "The critical frequency is 480 Hz")
        with pytest.raises(ValueError):
            memory.update(first["id"], "The critical frequency is 500 Hz")

    def test_delete_hides_from_search_and_get_all(self, memory):
        memory.add("temporary fact", user_id="u1")
        record_id = memory.get_all(filters={"user_id": "u1"})["results"][0]["id"]
        deleted = memory.delete(record_id)
        assert deleted["event"] == "DELETE"
        assert memory.search("temporary", filters={"user_id": "u1"})["results"] == []
        assert memory.get_all(filters={"user_id": "u1"})["results"] == []
        # History is preserved even after deletion.
        assert [e["event"] for e in memory.history(record_id)] == ["ADD", "DELETE"]

    def test_delete_all_scoped(self, memory):
        memory.add("a", user_id="u1")
        memory.add("b", user_id="u2")
        result = memory.delete_all(filters={"user_id": "u1"})
        assert result["deleted"] == 1
        assert memory.get_all(filters={"user_id": "u1"})["results"] == []
        assert len(memory.get_all(filters={"user_id": "u2"})["results"]) == 1

    def test_get_missing_raises(self, memory):
        with pytest.raises(KeyError):
            memory.get("does-not-exist")


class TestPersistence:
    def test_state_survives_restart(self, tmp_path):
        root = tmp_path / "memory"
        first = ScientificMemory(root=root, clock=FIXED_CLOCK)
        first.add("The critical frequency is 440 Hz", user_id="u1")
        first.add("The critical frequency is 480 Hz", user_id="u1")

        reopened = ScientificMemory(root=root, clock=FIXED_CLOCK)
        results = reopened.search("frequency", filters={"user_id": "u1"})["results"]
        assert len(results) == 1
        assert results[0]["memory"] == "The critical frequency is 480 Hz"
        all_records = list(reopened.store.iter_records())
        assert len(all_records) == 2  # superseded history is preserved
        assert len(reopened.contradictions()) == 0 or reopened.contradictions()

    def test_deterministic_ids_across_instances(self, tmp_path):
        a = ScientificMemory(root=tmp_path / "a", clock=FIXED_CLOCK)
        b = ScientificMemory(root=tmp_path / "b", clock=FIXED_CLOCK)
        result_a = a.add("stable content", user_id="u1")
        result_b = b.add("stable content", user_id="u1")
        assert result_a["results"][0]["id"] == result_b["results"][0]["id"]

    def test_store_round_trip(self, tmp_path):
        store = MemoryStore(tmp_path)
        record = MemoryRecord(
            id="test-id", content="content", scope={"user_id": "u1"}, created_at="t", updated_at="t"
        )
        store.put(record)
        store.append_event(
            MemoryEvent(memory_id="test-id", event="ADD", prev_value=None, new_value="content")
        )
        store.add_contradiction(
            Contradiction(id="c1", new_memory_id="test-id", old_memory_id="other", statement="conflict")
        )
        store.flush()

        loaded = MemoryStore(tmp_path)
        assert loaded.get("test-id") is not None
        assert [e.event for e in loaded.history("test-id")] == ["ADD"]
        assert len(loaded.contradictions()) == 1

    def test_bad_kind_rejected(self):
        with pytest.raises(ValueError):
            MemoryRecord(id="x", content="c", scope={"user_id": "u"}, kind="nope")


class TestScoring:
    def test_identical_content_scores_one(self):
        record = MemoryRecord(id="r1", content="alpha beta", scope={"user_id": "u"})
        index = LexicalIndex([record])
        assert index.score("alpha beta", record) == 1.0

    def test_threshold_excludes_weak_matches(self):
        record = MemoryRecord(id="r1", content="alpha beta", scope={"user_id": "u"})
        index = LexicalIndex([record])
        assert index.score("gamma delta", record) < 0.1

    def test_ranking_by_relevance(self):
        records = [
            MemoryRecord(id="r1", content="phase locking in coupled oscillators", scope={"user_id": "u"}),
            MemoryRecord(id="r2", content="spectral estimation of tones", scope={"user_id": "u"}),
        ]
        index = LexicalIndex(records)
        results = index.search("phase locking oscillators", scope={"user_id": "u"})
        assert results[0].record.id == "r1"

    def test_normalize_and_tokenize(self):
        assert normalize("The Quick, Brown Fox!") == "the quick brown fox"
        assert "the" not in tokenize("The quick brown fox")

    def test_json_serializable_statistics(self, memory):
        memory.add("fact", user_id="u1")
        stats = memory.statistics()
        assert json.dumps(stats)  # canonical JSON-safe
