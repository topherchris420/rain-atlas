"""Target 03: Browser Use — autonomous browser interaction."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

BROWSER_USE_COMMIT = "4b5b1b0aa0ab45a1d6a2a31984d37d3e748c0134"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T03-browser-use",
        name="Browser Use",
        organization="Browser Use",
        urls={
            "repository": "https://github.com/browser-use/browser-use",
            "documentation": "https://docs.browser-use.com",
        },
        reference_version="repository main at investigation date",
        reference_commit=BROWSER_USE_COMMIT,
        license="MIT",
        license_notes="MIT permits reconstruction; no Browser Use source is included.",
        scope="Browser state observation, structured navigation, tool-based "
        "interaction, page understanding, action verification, authorized "
        "research retrieval.",
    )
    observed = [
        EvidenceItem(
            id="bu-obs-1",
            classification="OBSERVED",
            statement=(
                "The reference observes pages as structured state (DOM snapshot, "
                "interactive elements with indices) and emits structured actions "
                "(click by index, type, scroll, navigate) rather than raw clicks; "
                "an LLM agent loop maps goals to those actions."
            ),
            sources=[
                "browser_use/ package structure and agent loop at commit " + BROWSER_USE_COMMIT,
            ],
            captured_at="2026-11-16",
        ),
        EvidenceItem(
            id="bu-obs-2",
            classification="OBSERVED",
            statement=(
                "Sessions persist state (cookies, tabs, history) across actions, "
                "and the library ships with evaluation tooling for browser tasks."
            ),
            sources=["repository tests/ and docs at commit " + BROWSER_USE_COMMIT],
            captured_at="2026-11-16",
        ),
    ]
    interface = [
        EvidenceItem(
            id="bu-if-1",
            classification="COMPUTED",
            statement=(
                "The replica fetches authorized URLs and returns structured page "
                "observations (title, text, links) with provenance (content hash, "
                "fetch time) and optional content verification; verified by 6 "
                "executed tests including file:// and local HTTP."
            ),
            sources=["tests/test_replica_modules.py::TestBrowserSession"],
            derives_from=["bu-obs-1"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="bu-fail-1",
            classification="INFERRED",
            statement=(
                "JavaScript-rendered pages cannot be observed by the replica's "
                "stdlib fetch; the reference's real-browser driver handles them. "
                "The replica's observation failures raise BrowserError instead."
            ),
            derives_from=["bu-obs-1"],
            sources=["rain_atlas/browser/__init__.py"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R03-browser-adapter",
        target_id="T03-browser-use",
        module="rain_atlas.browser",
        integration_status="integrated",
        integration_notes=(
            "Authorized public retrieval with provenance capture; used to record "
            "reference evidence into scientific memory during investigations."
        ),
        features=[
            Feature(
                name="structured-observation",
                description="title/text/links extraction from fetched pages, scripts skipped",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestBrowserSession::test_observes_structured_state",
                    "bu/structured-observation",
                ],
                deviations=["stdlib HTML parsing instead of a real browser DOM"],
            ),
            Feature(
                name="action-verification",
                description="expect_text turns fetches into verified observations",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestBrowserSession::test_verification_flag"],
            ),
            Feature(
                name="provenance-capture",
                description="url, fetch time, content hash per observation",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestBrowserSession::test_history_recorded"],
            ),
            Feature(
                name="session-history",
                description="all observations retained and exportable",
                status="verified",
                test_names=["tests/test_replica_modules.py::TestBrowserSession::test_history_recorded"],
            ),
            Feature(
                name="agent-loop",
                description="LLM-driven goal-to-action mapping over live pages",
                status="unverified",
                test_names=[],
                coverage="deliberately out of scope: the ATLAS adapter is deterministic and model-optional",
            ),
            Feature(
                name="dom-interaction",
                description="clicking, typing and scrolling in a real browser",
                status="unverified",
                test_names=[],
                coverage="not reconstructed; the research adapter only reads authorized pages",
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="bu/structured-observation",
            status="passed",
            reference="Browser Use structured-state concept (repository inspection)",
            comparator="predicate",
            details="pages are observed as structured state rather than raw HTML",
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
            "How much agent-loop capability matters for scientific retrieval "
            "remains unmeasured; the adapter covers fetch-verify-record flows.",
        ],
        confidence="moderate",
    )
