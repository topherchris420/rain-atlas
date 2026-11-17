"""Target 02: Langfuse — scientific observability and evaluation."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

LANGFUSE_COMMIT = "01e7f5f746b15493d18fe06b24ae06ac08d5ae74"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T02-langfuse",
        name="Langfuse",
        organization="Langfuse (ClickHouse, Inc.)",
        urls={
            "repository": "https://github.com/langfuse/langfuse",
            "documentation": "https://langfuse.com/docs",
        },
        reference_version="repository main at investigation date",
        reference_commit=LANGFUSE_COMMIT,
        license="MIT (core); ee/ directories under a separate commercial license",
        license_notes=(
            "Only core API definitions (fern/) were inspected. No Langfuse source "
            "is included; the replica is an independent local-first implementation."
        ),
        scope="Structured execution tracing, hierarchical observation spans, "
        "model/tool-call recording, usage and cost measurement, latency, "
        "evaluation datasets and experiment comparisons.",
    )
    observed = [
        EvidenceItem(
            id="lf-obs-1",
            classification="OBSERVED",
            statement=(
                "Observations carry id, traceId, parentObservationId, type, name, "
                "startTime, endTime, level, statusMessage, version, input, output, "
                "metadata, model, modelParameters, usageDetails, costDetails, "
                "latency and prompt fields; types include SPAN, GENERATION, EVENT, "
                "TOOL, RETRIEVER, EVALUATOR, EMBEDDING and GUARDRAIL; levels are "
                "DEBUG, DEFAULT, WARNING and ERROR."
            ),
            sources=[
                "fern/apis/server/definition/observations.yml at commit " + LANGFUSE_COMMIT,
            ],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="lf-obs-2",
            classification="OBSERVED",
            statement=(
                "Observations form hierarchies through parentObservationId; a trace "
                "aggregates its observations with scores attached at trace or "
                "observation level."
            ),
            sources=["fern/apis/server/definition/observations.yml, trace.yml, scores.yml"],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="lf-obs-3",
            classification="OBSERVED",
            statement=(
                "The product separates datasets, dataset items and dataset runs for "
                "evaluation, with experiment-level comparisons between runs."
            ),
            sources=["fern/apis/server/definition/datasets.yml, dataset-items.yml, experiments.yml"],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="lf-obs-4",
            classification="OBSERVED",
            statement=(
                "REA tool inspection (morluto/rea) of the compiled Langfuse "
                "Python SDK 5.2.0 client (98 code objects) confirms the "
                "observation model surface: typed start_observation overloads "
                "for span/generation/event creation, update_current_span and "
                "update_current_generation, create_event, create_score, "
                "score_current_span/score_current_trace, get_dataset and "
                "create_dataset_item, run_experiment and "
                "run_batched_evaluation, and prompt management; module names "
                "include ObservationLevel, SpanLevel, ScoreDataType and the "
                "LangfuseEvent/LangfuseGeneration/LangfuseSpan stateful "
                "client classes."
            ),
            sources=[
                "morluto/rea inspect_python_pyc on langfuse 5.2.0 site-packages (CPython 3.12 bytecode)",
                "executed 2026-11-17",
            ],
            artifact_hashes={
                "langfuse_client_pyc": (
                    "sha256:fbb240100117fe0de621b83638966ff7405d7c0ff8196d9d58da4d638dd3726f"
                ),
                "langfuse_types_pyc": (
                    "sha256:4652b679b5a6d6e28c58d7c6d7787ecd77903be01d690a1de2db09cc50a7575f"
                ),
            },
            captured_at="2026-11-17",
        ),
    ]
    interface = [
        EvidenceItem(
            id="lf-if-1",
            classification="COMPUTED",
            statement=(
                "The replica reproduces the observation model field-for-field where "
                "it is in scope (trace id, hierarchy, types, levels, timing, "
                "usage, cost, model parameters) and validates type/level enums, "
                "verified by 14 executed tests."
            ),
            sources=["tests/test_observability.py"],
            derives_from=["lf-obs-1", "lf-obs-2", "lf-obs-3"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="lf-fail-1",
            classification="OBSERVED",
            statement=(
                "The reference is a client-server application: ingestion goes through "
                "an HTTP API with batching and eventual consistency. The replica is "
                "in-process, which changes failure modes (no network errors, no "
                "async flush)."
            ),
            sources=["fern/apis/server/definition/ingestion.yml (WIP batch endpoints)"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R02-observability",
        target_id="T02-langfuse",
        module="rain_atlas.observability",
        integration_status="integrated",
        integration_notes=(
            "Every mission transition and twin execution is traced; traces export "
            "into the ATLAS evidence ledger; the central experiment attaches "
            "scores to traces."
        ),
        features=[
            Feature(
                name="trace-hierarchy",
                description="nested spans/generations/events/tools with parent ids",
                status="verified",
                test_names=["tests/test_observability.py::TestTracing", "lf/trace-hierarchy"],
            ),
            Feature(
                name="usage-and-cost",
                description="usageDetails/costDetails per generation with rollups",
                status="verified",
                test_names=["tests/test_observability.py::TestTracing::test_usage_and_cost_rollup"],
            ),
            Feature(
                name="latency-and-levels",
                description="computed latency from injectable clocks; DEBUG..ERROR levels",
                status="verified",
                test_names=["tests/test_observability.py::TestTracing::test_latency_from_injected_clock"],
                deviations=["deterministic injected clocks instead of wall time (reproducibility)"],
            ),
            Feature(
                name="error-capture",
                description="exceptions inside spans record ERROR level and status message",
                status="verified",
                test_names=[
                    "tests/test_observability.py::TestTracing::test_exceptions_recorded_as_error_level"
                ],
            ),
            Feature(
                name="scores",
                description="named scores with comments attached to traces",
                status="verified",
                test_names=["tests/test_observability.py::TestTracing::test_scores_on_trace"],
            ),
            Feature(
                name="eval-datasets",
                description="named case datasets, scored runs, experiment comparison",
                status="verified",
                test_names=["tests/test_observability.py::TestEvals"],
                deviations=["in-process comparison objects instead of hosted experiments"],
            ),
            Feature(
                name="ledger-export",
                description="traces stored as ledger objects with note records",
                status="verified",
                test_names=["tests/test_observability.py::TestLedgerExport"],
                deviations=["ATLAS-native export instead of an ingestion API"],
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="lf/trace-hierarchy",
            status="passed",
            reference="Langfuse observation API model (fern definitions) at commit " + LANGFUSE_COMMIT,
            comparator="keys",
            details="observation dicts carry traceId/parentObservationId/type/level per the API model",
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
            "Batching, retention and multi-project organization are reference "
            "concerns not yet relevant to the replica's in-process use.",
        ],
        confidence="high",
    )
