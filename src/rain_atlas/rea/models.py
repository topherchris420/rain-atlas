"""Typed models for REA investigations.

All models are plain dataclasses serialisable to canonical JSON so that an
investigation can be stored in the ATLAS evidence ledger, diffed between
versions and rendered offline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..canonical import canonical_bytes, sha256_bytes
from .classification import CLASSIFICATIONS


def _content_digest(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


@dataclass
class EvidenceItem:
    """One classified statement about a reference system."""

    id: str
    classification: str
    statement: str
    sources: list[str] = field(default_factory=list)
    derives_from: list[str] = field(default_factory=list)
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    captured_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceItem":
        return cls(**data)

    def digest(self) -> str:
        return _content_digest(self.to_dict())


@dataclass
class Feature:
    """One reconstructed capability and its verification status."""

    name: str
    description: str
    status: str = "planned"  # verified | partial | planned | unverified
    coverage: str = ""
    test_names: list[str] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Feature":
        return cls(**data)


@dataclass
class ReplicaSpec:
    """An independent implementation of a reference subset."""

    replica_id: str
    target_id: str
    module: str
    features: list[Feature] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)
    integration_status: str = "planned"  # integrated | gated | planned
    integration_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ReplicaSpec":
        data = dict(data)
        data["features"] = [Feature.from_dict(f) for f in data.get("features", [])]
        return cls(**data)

    def verified_features(self) -> list[Feature]:
        return [f for f in self.features if f.status == "verified"]

    def feature(self, name: str) -> Feature | None:
        return next((f for f in self.features if f.name == name), None)


@dataclass
class ConformanceRecord:
    """The recorded outcome of one reference-versus-replica comparison."""

    case: str
    status: str  # passed | failed | skipped
    reference: str  # what provided reference behavior
    comparator: str
    details: str = ""
    ran_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ConformanceRecord":
        return cls(**data)


@dataclass
class TargetManifest:
    """Identity and provenance of the reference system under investigation."""

    target_id: str
    name: str
    organization: str
    urls: dict[str, str] = field(default_factory=dict)
    reference_version: str = ""
    reference_commit: str = ""
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    license: str = ""
    license_notes: str = ""
    scope: str = ""
    reuse_policy: str = "independent implementation; no code reuse"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TargetManifest":
        return cls(**data)

    def digest(self) -> str:
        return _content_digest(self.to_dict())


@dataclass
class Investigation:
    """A complete research record for one reference target."""

    manifest: TargetManifest
    observed_functionality: list[EvidenceItem] = field(default_factory=list)
    interface_model: list[EvidenceItem] = field(default_factory=list)
    failure_conditions: list[EvidenceItem] = field(default_factory=list)
    replicas: list[ReplicaSpec] = field(default_factory=list)
    conformance: list[ConformanceRecord] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence: str = "low"  # low | moderate | high

    def all_evidence(self) -> list[EvidenceItem]:
        return [*self.observed_functionality, *self.interface_model, *self.failure_conditions]

    def evidence_by_id(self, evidence_id: str) -> EvidenceItem | None:
        return next((e for e in self.all_evidence() if e.id == evidence_id), None)

    def replica(self, replica_id: str) -> ReplicaSpec | None:
        return next((r for r in self.replicas if r.replica_id == replica_id), None)

    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest.to_dict(),
            "observed_functionality": [e.to_dict() for e in self.observed_functionality],
            "interface_model": [e.to_dict() for e in self.interface_model],
            "failure_conditions": [e.to_dict() for e in self.failure_conditions],
            "replicas": [r.to_dict() for r in self.replicas],
            "conformance": [c.to_dict() for c in self.conformance],
            "open_questions": list(self.open_questions),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Investigation":
        data = dict(data)
        return cls(
            manifest=TargetManifest.from_dict(data["manifest"]),
            observed_functionality=[
                EvidenceItem.from_dict(e) for e in data.get("observed_functionality", [])
            ],
            interface_model=[EvidenceItem.from_dict(e) for e in data.get("interface_model", [])],
            failure_conditions=[EvidenceItem.from_dict(e) for e in data.get("failure_conditions", [])],
            replicas=[ReplicaSpec.from_dict(r) for r in data.get("replicas", [])],
            conformance=[ConformanceRecord.from_dict(c) for c in data.get("conformance", [])],
            open_questions=list(data.get("open_questions", [])),
            confidence=data.get("confidence", "low"),
        )

    def digest(self) -> str:
        return _content_digest(self.to_dict())


def classifications_in_use(investigation: Investigation) -> set[str]:
    used = {e.classification for e in investigation.all_evidence()}
    return used & set(CLASSIFICATIONS)
