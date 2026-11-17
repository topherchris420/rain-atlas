"""Target 07: Maxxwell (Rindler) — agent fleet command center."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

DOCS_URL = "https://docs.maxxwell.dev/"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T07-maxxwell",
        name="Maxxwell by Rindler",
        organization="Rindler",
        urls={
            "website": "https://maxxwell.dev",
            "documentation": DOCS_URL,
            "ycombinator": "https://www.ycombinator.com/companies/rindler",
        },
        reference_version="public documentation, early access product (2026-11-16)",
        reference_commit="",
        license="Proprietary product; documentation publicly accessible",
        license_notes=(
            "Behavior reconstructed only from public documentation. The docs "
            "explicitly separate what ships today from product direction."
        ),
        scope="Multiple concurrent agent sessions, session supervision, task "
        "ownership, fleet monitoring, human interruption and takeover, progress "
        "visibility, task status and recovery.",
    )
    observed = [
        EvidenceItem(
            id="mx-obs-1",
            classification="OBSERVED",
            statement=(
                "What ships today (per the documentation): a desktop app and "
                "standalone maxxwell CLI; a local interactive session driven by "
                "an installed Claude Code or Codex CLI or a configured provider "
                "API key; a read-only fleet surface for existing local fleet "
                "records; session inventory, morning-page, remote, worktree and "
                "setup commands; no required account or hosted control plane."
            ),
            sources=[DOCS_URL + " (Introduction, 'What ships today')"],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mx-obs-2",
            classification="OBSERVED",
            statement=(
                "The documentation states that automatically auditing goals, "
                "correcting drift and restarting bloated sessions are product "
                "direction, NOT claims about the current downloadable release."
            ),
            sources=[DOCS_URL + " (Introduction, early-access note)"],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mx-obs-3",
            classification="OBSERVED",
            statement=(
                "BYOK: the coding tool keeps its own sign-in and credentials "
                "stay on the user's machine; morning page documents what the "
                "'morning' command can and cannot prove."
            ),
            sources=[DOCS_URL + "concepts/morning-page, " + DOCS_URL + "guides/byok"],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="mx-obs-4",
            classification="OBSERVED",
            statement=(
                "What Rindler sells (per its YC company page, fetched "
                "2026-11-17): two products. (1) Maxxwell, 'The IDE for "
                "Tokenmaxxers' — a desktop app for people running several "
                "coding agents at once: every session in one window marked "
                "working, idle or waiting-on-you, with an orchestrator on "
                "top — 'a real coding-agent session of its own that reads "
                "the others and reports back' — while every worker is the "
                "user's own unmodified tool (Claude Code, Codex, Cursor "
                "Agent) in real terminal sessions that can be attached to "
                "and taken over at any point. (2) Rindler's launch "
                "product: turning websites into deterministic APIs for AI "
                "agents — sites mapped once into screens, actions and "
                "structured outputs, served through a remote MCP endpoint "
                "that handles popups, bot defenses and authenticated "
                "flows. The replica reconstructs Maxxwell's fleet "
                "supervision concepts (status, takeover, "
                "waiting-on-you); the orchestrator-over-workers and "
                "website-to-API products are recorded as open scope."
            ),
            sources=["https://www.ycombinator.com/companies/rindler (fetched 2026-11-17)"],
            captured_at="2026-11-17",
        ),
    ]
    interface = [
        EvidenceItem(
            id="mx-if-1",
            classification="COMPUTED",
            statement=(
                "The replica's mission controller provides the fleet-supervision "
                "concepts applicable to research missions: per-task status, "
                "progress through recorded transitions, human interruption "
                "(takeover), cancellation and recovery; verified by the mission "
                "controller test suite."
            ),
            sources=["tests/test_mission_controller.py::TestSupervision"],
            derives_from=["mx-obs-1", "mx-obs-3"],
            captured_at="2026-11-16",
        ),
    ]
    failures = []
    replica = ReplicaSpec(
        replica_id="R07-mission-fleet",
        target_id="T07-maxxwell",
        module="rain_atlas.mission",
        integration_status="integrated",
        integration_notes=(
            "The same mission controller used for the Omnara replica provides "
            "Maxxwell's fleet-supervision concepts for research missions."
        ),
        features=[
            Feature(
                name="session-supervision",
                description="inspect every task, its status, history and evidence",
                status="verified",
                test_names=["tests/test_mission_controller.py::TestLifecycle", "mx/session-supervision"],
            ),
            Feature(
                name="human-takeover",
                description="interruption: reassign or cancel non-terminal tasks",
                status="verified",
                test_names=["tests/test_mission_controller.py::TestSupervision::test_takeover_reassigns"],
            ),
            Feature(
                name="progress-visibility",
                description="recorded transitions with actor and generation labels",
                status="verified",
                test_names=["tests/test_mission_controller.py::TestIntegrationHooks"],
            ),
            Feature(
                name="morning-page",
                description="summarized fleet status and what it can prove",
                status="planned",
                test_names=[],
                coverage="future work: a rendered mission digest view",
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="mx/session-supervision",
            status="passed",
            reference="Maxxwell documentation (what ships today)",
            comparator="predicate",
            details="task status and transitions inspectable for supervision",
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
            "The downloadable release was not executed; runtime behavior beyond "
            "the documentation is UNKNOWN. Announced-but-unshipped capabilities "
            "are excluded from the replica scope.",
        ],
        confidence="moderate",
    )
