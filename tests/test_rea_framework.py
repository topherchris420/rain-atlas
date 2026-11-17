"""Tests for the REA replication framework.

The framework (manifests, evidence classifications, packages, conformance
harness, registry) is exercised with constructed fixtures; it carries no
built-in target data.
"""

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
from rain_atlas.rea.models import EvidenceItem, Investigation, ReplicaSpec, TargetManifest


def demo_investigation() -> Investigation:
    """A sound, reusable investigation used across the tests."""

    return Investigation(
        manifest=TargetManifest(
            target_id="T00-demo",
            name="Demo",
            organization="DemoOrg",
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
                target_id="T00-demo",
                module="rain_atlas.demomod",
                integration_status="integrated",
                features=[],
            )
        ],
        conformance=[
            # added by callers that need a passed case
        ],
        confidence="low",
    )


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
    def test_valid_package_builds_and_serializes(self):
        package = EvidencePackage.build(demo_investigation())
        payload = json.loads(package.to_bytes().decode("utf-8"))
        assert payload["investigation"]["manifest"]["target_id"] == "T00-demo"
        assert package.render_markdown().startswith("# REA investigation: Demo")
        digest_a = package.digest()
        digest_b = EvidencePackage.build(demo_investigation()).digest()
        assert digest_a == digest_b

    def test_inferred_as_observed_is_rejected(self):
        inv = demo_investigation()
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
        inv = demo_investigation()
        inv.observed_functionality.append(
            EvidenceItem(id="t1", classification="OBSERVED", statement="dup", sources=["docs"])
        )
        assert any("duplicate" in p for p in package_problems(inv))

    def test_integrated_with_deviations_requires_gate(self):
        inv = demo_investigation()
        inv.replicas[0].deviations = ["known deviation"]
        assert any("gated" in p for p in package_problems(inv))

    def test_derives_from_unknown_evidence_rejected(self):
        inv = demo_investigation()
        inv.observed_functionality.append(
            EvidenceItem(
                id="t3",
                classification="INFERRED",
                statement="derived",
                sources=["docs"],
                derives_from=["no-such-item"],
            )
        )
        assert any("unknown evidence" in p for p in package_problems(inv))

    def test_verified_features_require_tests_and_conformance(self):
        inv = demo_investigation()
        inv.replicas[0].features = [ReplicaSpec(replica_id="R00", target_id="T00-demo", module="m").features]
        from rain_atlas.rea.models import Feature

        inv.replicas[0].features = [Feature(name="f1", description="d", status="verified", test_names=["t"])]
        problems = package_problems(inv)
        assert any("no recorded conformance" in p for p in problems)

    def test_write_package(self, tmp_path):
        package = EvidencePackage.build(demo_investigation())
        from rain_atlas.rea.package import write_package

        path = write_package(package, tmp_path / "out")
        assert path.exists()
        assert (tmp_path / "out" / "package.md").exists()


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

    def test_predicate_comparator(self):
        comparator = Comparator(strategy="predicate", predicate=lambda a, b: a > b)
        passed, _ = comparator.compare(2, 1)
        assert passed

    def test_unknown_strategy(self):
        comparator = Comparator(strategy="nonsense")
        passed, details = comparator.compare(1, 1)
        assert not passed and "unknown comparator" in details

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
        registry = ReplicaRegistry()
        registry.register(demo_investigation())
        assert registry_problems(registry) == []

    def test_registering_invalid_investigation_raises(self):
        inv = Investigation(
            manifest=TargetManifest(target_id="T1", name="A", organization="O"),
            observed_functionality=[EvidenceItem(id="x", classification="INFERRED", statement="s")],
        )
        registry = ReplicaRegistry()
        with pytest.raises(ValueError, match="does not validate"):
            registry.register(inv)

    def test_registry_lookup_and_projection(self):
        registry = ReplicaRegistry()
        registry.register(demo_investigation())
        entry = registry.get("R00")
        assert entry is not None and entry.replica.module == "rain_atlas.demomod"
        assert registry.by_target("T00-demo")
        assert registry.integrated()
        summary = registry.to_dict()
        assert "R00" in summary and summary["R00"]["integration_status"] == "integrated"

    def test_round_trip_through_json(self):
        package = EvidencePackage.build(demo_investigation())
        payload = json.loads(package.to_bytes().decode("utf-8"))
        restored = Investigation.from_dict(payload["investigation"])
        assert package_problems(restored) == []
        registry = ReplicaRegistry()
        registry.register(restored)
        assert registry_problems(registry) == []
