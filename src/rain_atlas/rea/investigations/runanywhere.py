"""Target 05: RunAnywhere — local AI inference infrastructure."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

RUNANYWHERE_COMMIT = "87865ea825d131498cf255b129ae81f26449e637"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T05-runanywhere",
        name="RunAnywhere",
        organization="RunAnywhere AI",
        urls={
            "repository": "https://github.com/RunanywhereAI/runanywhere-sdks",
            "website": "https://runanywhere.ai",
        },
        reference_version="repository main at investigation date",
        reference_commit=RUNANYWHERE_COMMIT,
        license="Proprietary-friendly repository layout; see license notes",
        license_notes=(
            "The runanywhere-sdks repository carries its own LICENSE file. "
            "No RunAnywhere source is included or reused in this replica; only "
            "publicly documented capability categories (runtime selection, "
            "on-device inference, structured outputs, tool calling) were "
            "consulted. Verify the repository license before any source reuse."
        ),
        scope="On-device inference, model discovery, runtime selection, streaming "
        "generation, structured outputs, tool calling, hardware-aware execution.",
    )
    observed = [
        EvidenceItem(
            id="ra-obs-1",
            classification="OBSERVED",
            statement=(
                "The reference SDK repository is organized around engines, "
                "runtimes, an IDL, bindings and a core, consistent with "
                "pluggable local inference runtimes behind a common interface."
            ),
            sources=["repository tree at commit " + RUNANYWHERE_COMMIT],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="ra-obs-2",
            classification="OBSERVED",
            statement=(
                "Compatible local inference engines such as Ollama and llama.cpp "
                "expose documented HTTP APIs (Ollama /api/generate, /api/tags; "
                "llama.cpp OpenAI-compatible /v1/chat/completions, /v1/models)."
            ),
            sources=[
                "https://github.com/ollama/ollama/blob/main/docs/api.md",
                "https://github.com/ggml-org/llama.cpp/tree/master/tools/server",
            ],
            captured_at="2026-11-16",
        ),
    ]
    interface = [
        EvidenceItem(
            id="ra-if-1",
            classification="COMPUTED",
            statement=(
                "The replica provides replaceable providers behind one interface, a "
                "deterministic MockProvider, optional Ollama and llama.cpp HTTP "
                "providers with usage accounting, model discovery that tolerates "
                "unavailable servers, and schema-validated structured outputs; "
                "verified by 7 executed tests (including a local HTTP stub)."
            ),
            sources=["tests/test_replica_modules.py::TestInference"],
            derives_from=["ra-obs-1", "ra-obs-2"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="ra-fail-1",
            classification="COMPUTED",
            statement=(
                "When a local HTTP provider is unreachable, ProviderError is raised "
                "and discover_providers() omits the provider instead of failing; "
                "deterministic execution continues with the mock provider."
            ),
            sources=[
                "tests/test_replica_modules.py::TestInference::test_unreachable_provider_raises_provider_error"
            ],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R05-inference",
        target_id="T05-runanywhere",
        module="rain_atlas.inference",
        integration_status="integrated",
        integration_notes=(
            "The vertical slice's proposer agent generates hypotheses through the "
            "provider abstraction (mock by default); every generation is separable "
            "from deterministic evidence."
        ),
        features=[
            Feature(
                name="provider-abstraction",
                description="one interface for mock, Ollama and llama.cpp providers",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestInference", "ra/provider-abstraction"],
            ),
            Feature(
                name="model-discovery",
                description="discover models across providers; unreachable ones omitted",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestInference::test_discovery_includes_mock_without_network"
                ],
            ),
            Feature(
                name="structured-outputs",
                description="schema-validated JSON extraction from provider text",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestInference::test_structured_extraction_validates"
                ],
            ),
            Feature(
                name="local-http-providers",
                description="Ollama and llama.cpp HTTP adapters with usage accounting",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestInference::test_ollama_provider_http"],
                deviations=["HTTP adapters tested against local stubs; no live server required"],
            ),
            Feature(
                name="deterministic-mock",
                description="rule-based provider keeping evaluations model-free",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestInference::test_mock_provider_deterministic"],
            ),
            Feature(
                name="hardware-aware-execution",
                description="device-specific model placement and scheduling",
                status="unverified",
                test_names=[],
                coverage="out of scope: the replica delegates hardware concerns to the local engines",
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="ra/provider-abstraction",
            status="passed",
            reference="RunAnywhere capability categories + documented Ollama/llama.cpp APIs",
            comparator="predicate",
            details="providers interchangeable behind one complete() contract",
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
            "Streaming generation and tool calling over the provider interface "
            "are declared but not yet exercised by an integrated flow.",
        ],
        confidence="moderate",
    )
