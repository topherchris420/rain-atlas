"""Target 08: Arga Labs — high-fidelity stateful simulation."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

ARGA_URL = "https://www.argalabs.com"
ARGA_DOCS = "https://docs.argalabs.com/"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T08-arga-labs",
        name="Arga Labs",
        organization="Arga Labs",
        urls={
            "website": ARGA_URL,
            "documentation": ARGA_DOCS,
            "ycombinator": "https://www.ycombinator.com/companies/arga-labs",
        },
        reference_version="public website and documentation (2026-11-16)",
        reference_commit="",
        license="Proprietary service; publicly documented behavior only",
        license_notes=(
            "The commercial reference is inaccessible to direct examination; "
            "functionality is described from public documentation. Claims about "
            "their twins are INFERRED or UNKNOWN, never presented as observed."
        ),
        scope="Service twins, stateful API replication, scenario seeding, "
        "deterministic replay, fault injection, concurrent test execution, "
        "integration validation, agent behavior evaluation.",
    )
    observed = [
        EvidenceItem(
            id="ar-obs-3",
            classification="OBSERVED",
            statement=(
                "What Arga Labs sells (per its YC company page): "
                "'Real-world sandboxes to test and train AI agents' — "
                "Twin Runs that provision stateful digital twins of "
                "third-party services (33 in the catalog at investigation "
                "date) and return the URLs, credentials and environment "
                "variables to use them; Scenarios that save seeded "
                "starting state for repeatable tests; Test Runs and PR "
                "Test Runs that exercise a URL in a browser and grade "
                "performance; customers have run 100,000+ twin "
                "instances. The sold product's twin catalog, hosted "
                "infrastructure and browser test runner are beyond this "
                "replica's scope, which reconstructs the stateful "
                "twin/scenario/fault concepts for scientific instruments."
            ),
            sources=["https://www.ycombinator.com/companies/arga-labs (fetched 2026-11-17)"],
            captured_at="2026-11-17",
        ),
        EvidenceItem(
            id="ar-obs-1",
            classification="OBSERVED",
            statement=(
                "Public documentation describes digital twins as stateful "
                "replicas of external services implementing provider-compatible "
                "endpoints, state transitions, webhooks, edge cases and error "
                "modes; scenarios save starting state so runs can be reset and "
                "repeated; twins support deterministic seeding."
            ),
            sources=[ARGA_DOCS + "concepts/digital-twins"],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="ar-obs-2",
            classification="OBSERVED",
            statement=(
                "Evidence capture records every provider call, response, latency, "
                "side effect and service-state change across a run; fault "
                "simulation covers failures, rate limits, permissions and quotas."
            ),
            sources=[ARGA_URL + " (product pages)", ARGA_DOCS],
            captured_at="2026-11-16",
        ),
    ]
    interface = [
        EvidenceItem(
            id="ar-if-1",
            classification="COMPUTED",
            statement=(
                "The replica provides a stateful in-process service twin of a "
                "scientific instrument with hidden ground truth, deterministic "
                "scenario seeding, snapshot/reset/replay, fault injection "
                "(dropped observations, noise, bias) and an operation log as "
                "captured evidence; verified by 8 executed tests."
            ),
            sources=["tests/test_replica_modules.py::TestServiceTwin"],
            derives_from=["ar-obs-1", "ar-obs-2"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="ar-fail-1",
            classification="COMPUTED",
            statement=(
                "With drop probability 1.0, run_experiment raises "
                "ObservationFault and the evidence log records the dropped "
                "response with faulted=true; deterministic replay after reset "
                "reproduces the drop at the same point."
            ),
            sources=["tests/test_replica_modules.py::TestServiceTwin::test_dropped_observations_raise"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R08-simulation-twin",
        target_id="T08-arga-labs",
        module="rain_atlas.simulation",
        integration_status="integrated",
        integration_notes=(
            "The vertical slice and central experiment run against the twin "
            "with hidden ground truth; no production service is contacted."
        ),
        features=[
            Feature(
                name="stateful-twin",
                description="in-process instrument twin with hidden ground truth and operation log",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestServiceTwin::test_hidden_truth_not_leaked_in_responses",
                    "ar/stateful-twin",
                ],
                deviations=["scientific-instrument twin instead of third-party SaaS API twins"],
            ),
            Feature(
                name="deterministic-replay",
                description="same seed and conditions reproduce the same observations",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestServiceTwin::test_deterministic_replay"],
            ),
            Feature(
                name="scenario-snapshots",
                description="snapshot, restore and reset for repeatable conditions",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestServiceTwin::test_snapshot_and_restore"],
            ),
            Feature(
                name="fault-injection",
                description="dropped observations, observation noise and bias",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestServiceTwin::test_noise_and_bias_are_recorded"
                ],
            ),
            Feature(
                name="webhooks",
                description="signed webhook deliveries and event replay",
                status="planned",
                test_names=[],
                coverage="future work; not needed for instrument twins",
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="ar/stateful-twin",
            status="passed",
            reference="Arga Labs public documentation (concepts; product not executed)",
            comparator="predicate",
            details="stateful, deterministic, fault-capable twin with evidence log",
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
            "Arga's commercial twins were not executed; their fidelity, webhook "
            "signing and multi-app scenario behavior remain UNKNOWN. The replica "
            "claims no parity with the commercial product.",
        ],
        confidence="moderate",
    )
