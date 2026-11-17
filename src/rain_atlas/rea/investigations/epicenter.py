"""Target 06: Epicenter — local-first scientific knowledge."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

EPICENTER_COMMIT = "206ca98824fe1861c311395e47f55501cba6d5e8"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T06-epicenter",
        name="Epicenter",
        organization="Epicenter HQ",
        urls={
            "repository": "https://github.com/EpicenterHQ/epicenter",
            "website": "https://epicenter.so",
        },
        reference_version="repository main at investigation date",
        reference_commit=EPICENTER_COMMIT,
        license="AGPL-3.0-or-later (packages/ and apps/)",
        license_notes=(
            "AGPL-3.0 is why this target is reference-only: no Epicenter source "
            "is included, linked or derived from. The replica is an independent "
            "implementation of local-first concepts (user-owned state, "
            "portability, explicit conflict resolution)."
        ),
        scope="Local-first architecture, user-owned data, persistent structured "
        "state, synchronization, conflict resolution, portable application state.",
    )
    observed = [
        EvidenceItem(
            id="ep-obs-1",
            classification="OBSERVED",
            statement=(
                "The reference is a local-first monorepo (apps/, packages/, "
                "specs/, ops/) where packages and apps are AGPL-3.0-or-later; "
                "its LICENSE index states every package declares AGPL in its "
                "package manifest."
            ),
            sources=["LICENSE and repository tree at commit " + EPICENTER_COMMIT],
            captured_at="2026-11-16",
        ),
    ]
    interface = [
        EvidenceItem(
            id="ep-if-1",
            classification="COMPUTED",
            statement=(
                "The replica implements local-first versioned documents with "
                "append-only history, portable export/import as canonical JSON, "
                "divergence detection between stores and resolution that keeps "
                "both branches; verified by 5 executed tests."
            ),
            sources=["tests/test_replica_modules.py::TestKnowledgeStore"],
            derives_from=["ep-obs-1"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="ep-fail-1",
            classification="INFERRED",
            statement=(
                "Importing a state file with an unknown version is rejected with "
                "ValueError; stores with different state versions cannot merge."
            ),
            derives_from=["ep-if-1"],
            sources=["tests/test_replica_modules.py::TestKnowledgeStore::test_bad_state_version_rejected"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R06-knowledge-store",
        target_id="T06-epicenter",
        module="rain_atlas.knowledge",
        integration_status="integrated",
        integration_notes=(
            "The vertical slice records its experiment records in the knowledge "
            "store alongside the ATLAS ledger."
        ),
        features=[
            Feature(
                name="local-first-documents",
                description="versioned documents as files under user control",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestKnowledgeStore::test_put_get_and_history",
                    "ep/local-first-documents",
                ],
            ),
            Feature(
                name="portable-state",
                description="canonical-JSON export and import",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestKnowledgeStore::test_export_import_round_trip"
                ],
            ),
            Feature(
                name="conflict-resolution",
                description="divergence detection with both-branch retention and resolution records",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestKnowledgeStore::test_conflict_detection_and_resolution"
                ],
                deviations=["explicit both-branch merge with recorded resolutions instead of CRDTs"],
            ),
            Feature(
                name="persistence",
                description="directory-backed store surviving restart",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestKnowledgeStore::test_persistence_across_restart"
                ],
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="ep/local-first-documents",
            status="passed",
            reference="Epicenter local-first concept (repository inspection; no code reuse)",
            comparator="predicate",
            details="documents stored locally with append-only history",
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
            "The reference's synchronization transport and CRDT behavior, if any, "
            "are unexamined; the replica covers explicit merge flows only.",
        ],
        confidence="moderate",
    )
