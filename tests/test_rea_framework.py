"""Tests for the REA replication framework and the nine investigation packages."""

from __future__ import annotations

import json

import pytest

from rain_atlas.rea import (
    CLASSIFICATIONS,
    Comparator,
    ConformanceCase,
    ConformanceHarness,
    EvidencePackage,
    ReplicaRegistry,
    classification_rules,
    package_problems,
    registry_problems,
    validate_classification,
)
from rain_atlas.rea.investigations import TARGET_ORDER, all_investigations, investigation
from rain_atlas.rea.models import EvidenceItem, Investigation, ReplicaSpec, TargetManifest


class TestClassification:
    def test_all_four_classifications_exist(self):
        assert set(CLASSIFICATIONS) == {"OBSERVED", "COMPUTED", "INFERRED", "UNKNOWN"}

    def test_inferred_requires_derivation(self):
        problems = validate_classification(
            "INFERRED", {"statement": "x", "sources": ["doc"], "derives_from": []}
        )
        assert any("derives from" in p for p in problems)

    def test_observed_requires_sources(self):
        problems = validate_classification("OBSERVED", {"statement": "x"})
        assert any("source" in p for p in problems)

    def test_unknown_must_not_cite(self):
        problems = validate_classification("UNKNOWN", {"statement": "x", "sources": ["doc"]})
        assert any("must not cite" in p for p in problems)

    def test_invalid_rejected(self):
        assert validate_classification("GUESSED", {}) != []

    def test_rules_documented(self):
        rules = classification_rules()
        assert set(rules) == set(CLASSIFICATIONS)


class TestEvidencePackage:
    def _minimal_investigation(self) -> Investigation:
        return Investigation(
            manifest=TargetManifest(
                target_id="T00-test",
                name="Test",
                organization="TestOrg",
                reference_commit="abc123",
                license="MIT",
            ),
            observed_functionality=[
                EvidenceItem(
                    id="t1",
                    classification="OBSERVED",
                    statement="the thing works",
                    sources=["repo/file.py:1"],
                )
            ],
            replicas=[
                ReplicaSpec(
                    replica_id="R00",
                    target_id="T00-test",
                    module="rain_atlas.testmod",
                    integration_status="integrated",
                    features=[],
                )
            ],
            conformance=[],
            confidence="low",
        )

    def test_valid_package_builds_and_serializes(self):
        package = EvidencePackage.build(self._minimal_investigation())
        payload = json.loads(package.to_bytes().decode("utf-8"))
        assert payload["investigation"]["manifest"]["target_id"] == "T00-test"
        assert package.render_markdown().startswith("# REA investigation: Test")
        digest_a = package.digest()
        digest_b = EvidencePackage.build(self._minimal_investigation()).digest()
        assert digest_a == digest_b

    def test_inferred_as_observed_is_rejected(self):
        inv = self._minimal_investigation()
        inv.observed_functionality.append(
            EvidenceItem(
                id="t2",
                classification="INFERRED",
                statement="probably also works",
                sources=["docs"],
                derives_from=[],
            )
        )
        assert any("derives from" in p for p in package_problems(inv))

    def test_duplicate_evidence_ids_rejected(self):
        inv = self._minimal_investigation()
        inv.observed_functionality.append(
            EvidenceItem(
                id="t1",
                classification="OBSERVED",
                statement="duplicate",
                sources=["docs"],
            )
        )
        assert any("duplicate" in p for p in package_problems(inv))

    def test_integrated_with_deviations_requires_gate(self):
        inv = self._minimal_investigation()
        inv.replicas[0].deviations = ["known deviation"]
        assert any("gated" in p for p in package_problems(inv))


class TestConformanceHarness:
    def test_exact_comparator(self):
        comparator = Comparator(strategy="exact")
        passed, _ = comparator.compare({"a": 1}, {"a": 1})
        assert passed

    def test_keys_comparator(self):
        comparator = Comparator(strategy="keys", keys=["event", "memory"])
        passed, _ = comparator.compare(
            {"event": "ADD", "memory": "x", "extra": 1},
            {"event": "ADD", "memory": "x", "other": 2},
        )
        assert passed
        failed, details = comparator.compare(
            {"event": "ADD", "memory": "x"}, {"event": "UPDATE", "memory": "x"}
        )
        assert not failed and "mismatches" in details
        missing, missing_details = comparator.compare({"event": "ADD", "memory": "x"}, {"event": "ADD"})
        assert not missing and "missing" in missing_details

    def test_sequence_comparator(self):
        comparator = Comparator(strategy="sequence")
        passed, _ = comparator.compare([{"e": "ADD"}, {"e": "UPDATE"}], [{"e": "ADD"}, {"e": "UPDATE"}])
        assert passed
        failed, details = comparator.compare([{"e": "ADD"}], [{"e": "ADD"}, {"e": "DELETE"}])
        assert not failed and "length" in details

    def test_harness_records_failures_and_errors(self):
        harness = ConformanceHarness(reference_label="doc")
        failing = ConformanceCase(
            name="case-fail",
            description="d",
            run=lambda: {"reference": 1, "replica": 2},
            comparator=Comparator(strategy="exact"),
        )
        erroring = ConformanceCase(
            name="case-error",
            description="d",
            run=lambda: 1 / 0,
            comparator=Comparator(strategy="exact"),
        )
        results = harness.run_all([failing, erroring])
        assert [r.status for r in results] == ["failed", "errored"]
        assert harness.summary() == {"failed": 1, "errored": 1}
        record = harness.records[0]
        assert record.case == "case-fail" and record.status == "failed"


class TestRegistry:
    def test_registry_validates_on_register(self):
        inv = Investigation(
            manifest=TargetManifest(target_id="T9", name="N", organization="O"),
        )
        registry = ReplicaRegistry()
        registry.register(inv)  # registers the placeholder no-replica entry
        assert registry_problems(registry) == []

    def test_registering_invalid_investigation_raises(self):
        inv = Investigation(
            manifest=TargetManifest(target_id="T1", name="A", organization="O"),
            observed_functionality=[
                EvidenceItem(id="x", classification="INFERRED", statement="s")  # no derivation
            ],
        )
        registry = ReplicaRegistry()
        with pytest.raises(ValueError, match="does not validate"):
            registry.register(inv)


class TestNineInvestigations:
    def test_all_nine_targets_present(self):
        assert len(TARGET_ORDER) == 9
        assert TARGET_ORDER[0] == "T01-mem0"
        assert TARGET_ORDER[-1] == "T09-infera"

    @pytest.mark.parametrize("target_id", TARGET_ORDER)
    def test_every_package_validates(self, target_id):
        inv = investigation(target_id)
        problems = package_problems(inv)
        assert problems == [], f"{target_id}: {problems}"

    @pytest.mark.parametrize("target_id", TARGET_ORDER)
    def test_every_package_builds_and_round_trips(self, target_id):
        package = EvidencePackage.build(investigation(target_id))
        payload = json.loads(package.to_bytes().decode("utf-8"))
        restored = Investigation.from_dict(payload["investigation"])
        assert package_problems(restored) == []

    def test_no_inferred_statement_is_presented_as_observed(self):
        for inv in all_investigations():
            for item in inv.all_evidence():
                if item.classification == "OBSERVED":
                    assert item.sources, f"{inv.manifest.target_id}/{item.id} cites no source"

    def test_closed_source_targets_are_honest(self):
        for target_id in ("T07-maxxwell", "T08-arga-labs", "T09-infera"):
            inv = investigation(target_id)
            assert inv.manifest.reference_commit == ""
            assert any(
                "UNKNOWN" in q or "not executed" in q or "UNKNOWN" in q.lower() for q in inv.open_questions
            ), f"{target_id} must record what remains unverified"

    def test_reference_commits_recorded_for_open_source_targets(self):
        for target_id in (
            "T01-mem0",
            "T02-langfuse",
            "T03-browser-use",
            "T04-omnara",
            "T05-runanywhere",
            "T06-epicenter",
        ):
            inv = investigation(target_id)
            assert inv.manifest.reference_commit, f"{target_id} lacks a pinned commit"

    def test_mem0_differential_conformance_recorded(self):
        inv = investigation("T01-mem0")
        cases = {c.case: c for c in inv.conformance}
        assert cases["mem0/add-event-shape"].status == "passed"
        assert "mem0ai 2.2.1" in cases["mem0/add-event-shape"].reference

    @pytest.mark.parametrize(
        "target_id,evidence_id",
        [
            ("T01-mem0", "mem0-obs-5"),
            ("T02-langfuse", "lf-obs-4"),
            ("T03-browser-use", "bu-obs-3"),
        ],
    )
    def test_tool_derived_evidence_pinned(self, target_id, evidence_id):
        """morluto/rea tool-derived observations carry pinned artifact digests."""
        inv = investigation(target_id)
        item = inv.evidence_by_id(evidence_id)
        assert item is not None, f"{target_id} lacks {evidence_id}"
        assert item.classification == "OBSERVED"
        assert any("morluto/rea" in source for source in item.sources), (
            f"{evidence_id} must cite the REA tool as its source"
        )
        assert item.artifact_hashes, f"{evidence_id} must pin artifact digests"
        for digest in item.artifact_hashes.values():
            assert digest.startswith("sha256:") and len(digest) == 71

    def test_registry_registers_all_nine(self):
        registry = ReplicaRegistry()
        for inv in all_investigations():
            registry.register(inv)
        assert registry_problems(registry) == []
        integrated = registry.integrated()
        assert len(integrated) >= 9  # every target has at least one replica
        summary = registry.to_dict()
        assert "R01-scientific-memory" in summary
        # One module may reconstruct capabilities from multiple references.
        assert (
            registry.by_target("T04-omnara")[0].replica.module
            == registry.by_target("T07-maxxwell")[0].replica.module
            == "rain_atlas.mission"
        )

    def test_unknown_target_rejected(self):
        with pytest.raises(KeyError):
            investigation("T99-nope")
