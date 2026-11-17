"""Target 04: Omnara — persistent research-agent orchestration."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

OMNARA_COMMIT = "f7d05d06c1aa3fe50cee90e1e7ff1e843df0f947"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T04-omnara",
        name="Omnara",
        organization="Omnara AI",
        urls={
            "repository": "https://github.com/omnara-ai/omnara",
            "website": "https://omnara.com",
        },
        reference_version="repository main at investigation date",
        reference_commit=OMNARA_COMMIT,
        license="Apache-2.0",
        license_notes="Apache-2.0; no Omnara source is included in the replica.",
        scope="Persistent agent tasks, delegation, concurrent execution, session "
        "state, human-agent communication, approval workflows, failure recovery, "
        "execution supervision.",
    )
    observed = [
        EvidenceItem(
            id="om-obs-1",
            classification="OBSERVED",
            statement=(
                "The reference's public API is organized around agent sessions whose "
                "approvals and questions pause an agent until a human resolves "
                "them ('List and resolve the approvals and questions that pause "
                "an agent'), with interactions resolved through option indices."
            ),
            sources=[
                "api/openapi/openapi.yaml at commit " + OMNARA_COMMIT,
            ],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="om-obs-2",
            classification="OBSERVED",
            statement=(
                "The reference runs agents as local processes managed per machine "
                "and project, with agent configs compiled from MCP servers, tools "
                "and credentials; interactions, processes and machines are "
                "separate resources."
            ),
            sources=[
                "internal/ package layout (agentconfig, agentconfigcompile, "
                "daemonprotocol, cronschedule) at commit " + OMNARA_COMMIT,
            ],
            captured_at="2026-11-16",
        ),
    ]
    interface = [
        EvidenceItem(
            id="om-if-1",
            classification="COMPUTED",
            statement=(
                "The replica provides persistent tasks with an explicit state "
                "machine (pending/running/awaiting_approval/approved/completed/"
                "failed/cancelled), agents that pause themselves for approval, "
                "human resolution, bounded retries, cancellation and takeover; "
                "verified by 17 executed tests."
            ),
            sources=["tests/test_mission_controller.py"],
            derives_from=["om-obs-1", "om-obs-2"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="om-fail-1",
            classification="INFERRED",
            statement=(
                "If an agent requests approval while the operator is absent, the "
                "mission blocks until resolution; the replica records this as "
                "BLOCKED status rather than timing out."
            ),
            derives_from=["om-obs-1"],
            sources=["rain_atlas/mission/controller.py"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R04-mission-controller",
        target_id="T04-omnara",
        module="rain_atlas.mission",
        integration_status="integrated",
        integration_notes=(
            "The vertical slice runs a five-agent mission with an approval gate; "
            "every transition is traced and written to scientific memory."
        ),
        features=[
            Feature(
                name="persistent-tasks",
                description="task state machine with recorded transitions and dependencies",
                status="verified",
                test_names=["tests/test_mission_controller.py::TestLifecycle", "om/lifecycle"],
            ),
            Feature(
                name="approval-workflows",
                description="agents pause for approval; humans resolve; rejection cancels",
                status="verified",
                test_names=[
                    "tests/test_mission_controller.py::TestApprovals",
                    "om/approval-pauses",
                ],
            ),
            Feature(
                name="failure-recovery",
                description="bounded retries with recorded reasons",
                status="verified",
                test_names=[
                    "tests/test_mission_controller.py::TestLifecycle::test_failure_retry_then_success"
                ],
            ),
            Feature(
                name="supervision",
                description="cancel and human takeover of non-terminal tasks",
                status="verified",
                test_names=["tests/test_mission_controller.py::TestSupervision"],
            ),
            Feature(
                name="generation-labeling",
                description="every action records scripted/model/human generation",
                status="verified",
                test_names=[
                    "tests/test_mission_controller.py::TestIntegrationHooks::test_model_generation_distinguished_from_scripted"
                ],
                deviations=["in-process deterministic execution instead of managed OS processes"],
            ),
            Feature(
                name="concurrent-execution",
                description="parallel agent processes across machines",
                status="partial",
                test_names=[
                    "tests/test_mission_controller.py::TestLifecycle::test_dependencies_are_respected"
                ],
                coverage="step-driven interleaving is deterministic; no parallel OS processes",
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="om/lifecycle",
            status="passed",
            reference="Omnara OpenAPI task/session model at commit " + OMNARA_COMMIT,
            comparator="predicate",
            details="tasks complete in dependency order with recorded transitions",
            ran_at="2026-11-16",
        ),
        ConformanceRecord(
            case="om/approval-pauses",
            status="passed",
            reference="Omnara 'approvals and questions that pause an agent' API model",
            comparator="predicate",
            details="approval request pauses the task; resolution resumes or cancels it",
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
            "MCP-based agent configs and machine pools are reference concepts not "
            "yet needed by the replica's in-process agents.",
        ],
        confidence="high",
    )
