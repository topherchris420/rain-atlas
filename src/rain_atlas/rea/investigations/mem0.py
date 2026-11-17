"""Target 01: Mem0 — persistent intelligence and agent memory."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

MEM0_COMMIT = "f1791daa86d469249c9b002f62644d58a1eb96a0"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T01-mem0",
        name="Mem0",
        organization="Mem0 AI",
        urls={
            "repository": "https://github.com/mem0ai/mem0",
            "website": "https://mem0.ai",
            "pypi": "https://pypi.org/project/mem0ai/",
        },
        reference_version="mem0ai 2.2.1 (PyPI); repository main at investigation date",
        reference_commit=MEM0_COMMIT,
        license="Apache-2.0",
        license_notes=(
            "Apache-2.0 permits reuse with attribution. The replica is an "
            "independent implementation except for the vendored retrieval "
            "scoring (rain_atlas.memory.vendor.mem0): BM25 sigmoid "
            "normalization and additive hybrid ranking taken from the "
            "reference's mem0/utils/scoring.py and lemmatization.py at the "
            "pinned commit, with license and attribution preserved (see the "
            "vendor NOTICE and LICENSE). No other Mem0 source is included."
        ),
        scope="Long-term conversational memory, structured extraction, semantic "
        "retrieval, persistence, relevance ranking, updates and consolidation, "
        "contradiction handling, lifecycle management.",
        reuse_policy=(
            "independent implementation; Apache-2.0 retrieval-scoring "
            "utilities vendored with attribution (see "
            "rain_atlas.memory.vendor.mem0)"
        ),
    )
    observed = [
        EvidenceItem(
            id="mem0-obs-1",
            classification="OBSERVED",
            statement=(
                "Memory.add(messages, *, user_id|agent_id|run_id, metadata, infer) "
                "returns {'results': [{'id', 'memory', 'event'}]} where event is "
                "ADD, UPDATE, DELETE or NONE; infer=False stores messages verbatim "
                "and infer=True extracts facts via a language model."
            ),
            sources=[
                "mem0/memory/main.py:760-916 at commit " + MEM0_COMMIT,
                "executed reference SDK 2.2.1 in tests/reference/test_mem0_conformance.py",
            ],
            artifact_hashes={"mem0_main_py": "sha256:computed-at-reference-commit"},
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mem0-obs-2",
            classification="OBSERVED",
            statement=(
                "search(query, *, filters, top_k=20, threshold=0.1) returns "
                "{'results': [{'id', 'memory', 'score'}]} and requires at least one "
                "entity id (user_id, agent_id or run_id) in filters; passing none "
                "raises ValueError."
            ),
            sources=[
                "mem0/memory/main.py:1393-1445 at commit " + MEM0_COMMIT,
                "executed reference SDK 2.2.1 (scope-isolation and ValueError cases)",
            ],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mem0-obs-3",
            classification="OBSERVED",
            statement=(
                "history(memory_id) returns an append-only list of "
                "{'id', 'memory_id', 'old_memory', 'new_memory', 'event', "
                "'created_at', 'updated_at', 'is_deleted', 'actor_id', 'role'} "
                "entries; update() writes an UPDATE entry and delete() hides the "
                "memory from get_all while preserving history."
            ),
            sources=[
                "mem0/memory/storage.py:150-252 at commit " + MEM0_COMMIT,
                "executed reference SDK 2.2.1",
            ],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mem0-obs-4",
            classification="OBSERVED",
            statement=(
                "Stored memories carry metadata including an md5 content hash, "
                "created_at/updated_at timestamps and a lemmatized BM25 index; "
                "memory ids are random UUIDs."
            ),
            sources=["mem0/memory/main.py:1975-2005 at commit " + MEM0_COMMIT],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mem0-obs-5",
            classification="OBSERVED",
            statement=(
                "REA tool inspection (morluto/rea, 'REA CPython pyc parser') of "
                "the installed reference SDK's compiled memory/main module (106 "
                "code objects) confirms the API surface at matching line "
                "numbers: Memory.add (760), get (1222), get_all (1269), "
                "search (1393), update (1829), delete (1883), delete_all "
                "(1904), history (1960) and _create_memory (1975), with "
                "AsyncMemory mirrors; module names include lemmatize_for_bm25, "
                "score_and_rank and _validate_search_params. The compiled "
                "storage module shows SQLiteManager.add_history (150) and "
                "get_history (227) implementing the append-only history table. "
                "The same inspection reveals reference capabilities beyond this "
                "replica's declared scope: entity stores (Memory.entity_store, "
                "_upsert_entity, _compute_entity_boosts), project APIs "
                "(Memory.project) and Memory.chat."
            ),
            sources=[
                "morluto/rea inspect_python_pyc on mem0ai 2.2.1 site-packages "
                "(CPython 3.12 bytecode, evidence ev_e7b5aae9...)",
                "executed 2026-11-17",
            ],
            artifact_hashes={
                "mem0_main_pyc": ("sha256:b7fa61864c32daf1a15a07a791a6e633a4c9ed65f05a30008bfc82c602b5f94e"),
                "mem0_storage_pyc": (
                    "sha256:b57fe704ef5cbd8e54ee8ce835407cad3af08e433e053f8e5437a1afa04c933b"
                ),
            },
            captured_at="2026-11-17",
        ),
        EvidenceItem(
            id="mem0-obs-6",
            classification="OBSERVED",
            statement=(
                "What Mem0 sells (per its YC company page): 'The Memory layer "
                "for AI Agents' — a hosted platform (app.mem0.ai) plus the "
                "open-source SDK, with forward-deployed engineers and a "
                "hybrid datastore architecture combining graph, vector and "
                "key-value stores; positioning is personalized AI that "
                "remembers user preferences across sessions while reducing "
                "LLM context costs. The sold platform's graph-memory tier "
                "and hosted ingestion are beyond this replica's scope, which "
                "reconstructs the memory layer capability locally."
            ),
            sources=["https://www.ycombinator.com/companies/mem0 (fetched 2026-11-17)"],
            captured_at="2026-11-17",
        ),
    ]
    interface = [
        EvidenceItem(
            id="mem0-if-1",
            classification="COMPUTED",
            statement=(
                "Reference and replica agree on: ADD event results for raw adds, "
                "scope isolation between user ids, ValueError when search lacks an "
                "entity filter, ADD/UPDATE history sequences with old/new values, "
                "delete hiding records while preserving history, and scored search "
                "result shape. Measured by 12 differential tests, all passing "
                "against mem0ai 2.2.1."
            ),
            sources=["tests/reference/test_mem0_conformance.py"],
            derives_from=["mem0-obs-1", "mem0-obs-2", "mem0-obs-3"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="mem0-fail-1",
            classification="OBSERVED",
            statement=(
                "The reference's infer=True path requires a language model; without "
                "one, add() cannot extract facts. The replica's inference is "
                "rule-based and deterministic, so LLM-free operation is a deliberate "
                "deviation, not an accident."
            ),
            sources=["mem0/memory/main.py:918-960 (LLM extraction pipeline)"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R01-scientific-memory",
        target_id="T01-mem0",
        module="rain_atlas.memory",
        integration_status="integrated",
        integration_notes=(
            "Used by the mission controller (findings), the vertical slice "
            "(observations, decisions, contradictions) and the central experiment "
            "(program-scoped evidence carry-over)."
        ),
        features=[
            Feature(
                name="memory-add-events",
                description="add() with ADD/UPDATE/DELETE/NONE event results and scope ids",
                status="verified",
                test_names=[
                    "tests/test_memory_engine.py::TestAddAndSearch",
                    "mem0/add-event-shape",
                    "mem0/scope-isolation",
                ],
            ),
            Feature(
                name="structured-extraction",
                description="deterministic rule-based statement extraction with scientific kinds",
                status="verified",
                test_names=["tests/test_memory_engine.py::TestExtraction"],
                deviations=["extraction is rule-based, not model-driven (deterministic, LLM-free)"],
            ),
            Feature(
                name="semantic-retrieval",
                description="scored search with top_k, threshold, entity filters and metadata operators",
                status="verified",
                test_names=[
                    "tests/test_memory_engine.py::TestAddAndSearch",
                    "mem0/search-scored-results",
                    "mem0/search-requires-scope",
                ],
                deviations=[
                    "lexical coverage/overlap stands in for the vector-semantic channel (offline-deterministic)"
                ],
            ),
            Feature(
                name="hybrid-ranking",
                description=(
                    "vendored Mem0 Apache-2.0 scoring: Okapi BM25 "
                    "sigmoid-normalized and combined additively with the "
                    "lexical channel exactly as the reference ranks hybrid "
                    "results (threshold-gated, max_possible-divisor)"
                ),
                status="verified",
                test_names=[
                    "tests/test_memory_engine.py::TestHybridRanking",
                    "mem0/vendored-scoring-equivalence",
                ],
                coverage=(
                    "the reference's own scoring code (scoring.py, "
                    "lemmatization.py at the pinned commit), vendored under "
                    "Apache-2.0 with attribution"
                ),
            ),
            Feature(
                name="update-and-history",
                description="append-only history with supersession; never silently rewritten",
                status="verified",
                test_names=[
                    "tests/test_memory_engine.py::TestMutation",
                    "mem0/update-writes-history",
                    "mem0/delete-hides-and-records",
                ],
                deviations=["history field names differ (prev_value/new_value vs old_memory/new_memory)"],
            ),
            Feature(
                name="contradiction-handling",
                description="contradictions are recorded and linked, superseding with history",
                status="verified",
                test_names=["tests/test_memory_engine.py::TestAddAndSearch::test_contradiction_is_recorded"],
                deviations=["contradiction records are a scientific extension beyond the reference"],
            ),
            Feature(
                name="persistence",
                description="local-first JSON store with atomic writes; deterministic ids",
                status="verified",
                test_names=["tests/test_memory_engine.py::TestPersistence"],
                deviations=[
                    "content-derived deterministic ids instead of random UUIDs",
                    "SHA-256 content hashes instead of MD5",
                ],
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="mem0/vendored-scoring-equivalence",
            status="passed",
            reference=(
                "vendored rain_atlas.memory.vendor.mem0 versus installed "
                "mem0ai 2.2.1 mem0.utils.scoring/lemmatization"
            ),
            comparator="exact",
            details=(
                "get_bm25_params, normalize_bm25 and score_and_rank produce "
                "identical outputs on identical inputs (differential tests "
                "in the reference environment)"
            ),
            ran_at="2026-11-17",
        ),
        ConformanceRecord(
            case="mem0/tool-derived-api-surface",
            status="passed",
            reference="morluto/rea inspect_python_pyc on mem0ai 2.2.1 bytecode",
            comparator="predicate",
            details=(
                "compiled-method inventory and line numbers match the "
                "source-derived evidence (add 760, search 1393, history 1960)"
            ),
            ran_at="2026-11-17",
        ),
        ConformanceRecord(
            case="mem0/add-event-shape",
            status="passed",
            reference="mem0ai 2.2.1 executed locally (infer=False, fake embedder)",
            comparator="keys",
            details="both return results[0] with id/memory/event=ADD",
            ran_at="2026-11-16",
        ),
        ConformanceRecord(
            case="mem0/scope-isolation",
            status="passed",
            reference="mem0ai 2.2.1 executed locally",
            comparator="exact",
            details="per-user get_all returns only that user's memories in both",
            ran_at="2026-11-16",
        ),
        ConformanceRecord(
            case="mem0/search-requires-scope",
            status="passed",
            reference="mem0ai 2.2.1 executed locally",
            comparator="predicate",
            details="both raise ValueError without an entity filter",
            ran_at="2026-11-16",
        ),
        ConformanceRecord(
            case="mem0/update-writes-history",
            status="passed",
            reference="mem0ai 2.2.1 executed locally",
            comparator="sequence",
            details="ADD then UPDATE with matching old/new values in both",
            ran_at="2026-11-16",
        ),
        ConformanceRecord(
            case="mem0/delete-hides-and-records",
            status="passed",
            reference="mem0ai 2.2.1 executed locally",
            comparator="predicate",
            details="delete hides from get_all and records a DELETE history entry in both",
            ran_at="2026-11-16",
        ),
        ConformanceRecord(
            case="mem0/search-scored-results",
            status="passed",
            reference="mem0ai 2.2.1 executed locally (fake deterministic embedder)",
            comparator="keys",
            details="both rank the phase-locking memory first for the query",
            ran_at="2026-11-16",
        ),
    ]
    return Investigation(
        manifest=manifest,
        observed_functionality=observed,
        interface_model=interface,
        failure_conditions=failures,
        replicas=[replica],
        conformance=conformance,
        open_questions=[
            "How does the reference's LLM-driven consolidation compare to rule-based "
            "extraction on realistic research conversations? (unmeasured)",
        ],
        confidence="high",
    )
