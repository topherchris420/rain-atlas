"""Investigation evidence packages: validation, serialisation, ledger export.

An :class:`EvidencePackage` wraps one :class:`~rain_atlas.rea.models.Investigation`
and enforces the REA fidelity rules:

* every evidence item carries a valid classification;
* INFERRED evidence cites the evidence it derives from and those items exist;
* replicas that claim verified features name conformance records and tests;
* integrated replicas have no unresolved deviations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..canonical import canonical_bytes, sha256_bytes
from .classification import validate_classification
from .models import Investigation

if TYPE_CHECKING:
    from ..ledger.store import Ledger

_FEATURE_STATUSES = {"verified", "partial", "planned", "unverified"}
_INTEGRATION_STATUSES = {"integrated", "gated", "planned"}
_CONFORMANCE_STATUSES = {"passed", "failed", "skipped"}


def package_problems(investigation: Investigation) -> list[str]:
    """Validate one investigation; return an empty list when it is sound."""

    problems: list[str] = []
    evidence_ids = {e.id for e in investigation.all_evidence()}

    seen_ids: set[str] = set()
    for item in investigation.all_evidence():
        if item.id in seen_ids:
            problems.append(f"duplicate evidence id {item.id!r}")
        seen_ids.add(item.id)
        problems.extend(validate_classification(item.classification, item.to_dict()))
        if not item.statement.strip():
            problems.append(f"evidence {item.id!r} has an empty statement")
        for derived in item.derives_from:
            if derived not in evidence_ids:
                problems.append(f"evidence {item.id!r} derives from unknown evidence {derived!r}")

    for replica in investigation.replicas:
        if replica.target_id != investigation.manifest.target_id:
            problems.append(
                f"replica {replica.replica_id!r} targets {replica.target_id!r}, "
                f"not {investigation.manifest.target_id!r}"
            )
        if replica.integration_status not in _INTEGRATION_STATUSES:
            problems.append(f"replica {replica.replica_id!r} has invalid integration status")
        if replica.integration_status == "integrated" and replica.deviations:
            problems.append(
                f"replica {replica.replica_id!r} is integrated but documents deviations; "
                "use status 'gated' until deviations are accepted"
            )
        conformance_names = {c.case for c in investigation.conformance}
        has_verified = any(f.status == "verified" for f in replica.features)
        if has_verified and not conformance_names:
            problems.append(
                f"replica {replica.replica_id!r} has verified features but no recorded conformance cases"
            )
        for feature in replica.features:
            if feature.status not in _FEATURE_STATUSES:
                problems.append(f"feature {feature.name!r} has invalid status {feature.status!r}")
            if feature.status in {"verified", "partial"} and not feature.test_names:
                problems.append(f"feature {feature.name!r} is {feature.status} but names no tests")
            if feature.status == "verified" and not feature.test_names:
                problems.append(f"feature {feature.name!r} claims verification without tests")

    for record in investigation.conformance:
        if record.status not in _CONFORMANCE_STATUSES:
            problems.append(f"conformance case {record.case!r} has invalid status {record.status!r}")
        if record.status == "passed" and not record.reference:
            problems.append(f"conformance case {record.case!r} passed without a reference source")

    if investigation.confidence not in {"low", "moderate", "high"}:
        problems.append(f"invalid confidence {investigation.confidence!r}")
    return problems


@dataclass
class EvidencePackage:
    """A validated investigation ready for storage and rendering."""

    investigation: Investigation
    framework_version: str = "1"

    @classmethod
    def build(cls, investigation: Investigation) -> "EvidencePackage":
        problems = package_problems(investigation)
        if problems:
            raise ValueError("; ".join(problems))
        return cls(investigation=investigation)

    def digest(self) -> str:
        payload = {
            "framework_version": self.framework_version,
            "investigation": self.investigation.to_dict(),
        }
        return sha256_bytes(canonical_bytes(payload))

    def to_bytes(self) -> bytes:
        payload = {
            "framework_version": self.framework_version,
            "investigation": self.investigation.to_dict(),
        }
        return canonical_bytes(payload)

    def render_markdown(self) -> str:
        inv = self.investigation
        m = inv.manifest
        lines = [
            f"# REA investigation: {m.name}",
            "",
            f"* Target ID: `{m.target_id}`",
            f"* Organization: {m.organization}",
            f"* Reference version: {m.reference_version or 'unrecorded'}",
            f"* Reference commit: `{m.reference_commit or 'unrecorded'}`"
            if m.reference_commit
            else "* Reference commit: unrecorded",
            f"* License: {m.license or 'unrecorded'}",
            f"* Reuse policy: {m.reuse_policy}",
            f"* Confidence: {inv.confidence}",
            f"* Package digest: `{self.digest()}`",
            "",
        ]
        if m.urls:
            lines.append("## Reference URLs")
            lines.extend(f"* {name}: {url}" for name, url in sorted(m.urls.items()))
            lines.append("")
        if m.artifact_hashes:
            lines.append("## Artifact hashes")
            lines.extend(f"* `{name}`: `{digest}`" for name, digest in sorted(m.artifact_hashes.items()))
            lines.append("")

        for title, section in (
            ("Observed functionality", inv.observed_functionality),
            ("Interface model", inv.interface_model),
            ("Failure conditions and edge cases", inv.failure_conditions),
        ):
            if not section:
                continue
            lines.append(f"## {title}")
            for item in section:
                lines.append(f"* **[{item.classification}]** `{item.id}` — {item.statement}")
                if item.derives_from:
                    lines.append(f"  * derives from: {', '.join(item.derives_from)}")
                if item.sources:
                    lines.append(f"  * sources: {', '.join(item.sources)}")
                if item.artifact_hashes:
                    for name, digest in sorted(item.artifact_hashes.items()):
                        lines.append(f"  * artifact `{name}`: `{digest}`")
                if item.notes:
                    lines.append(f"  * {item.notes}")
            lines.append("")

        if inv.replicas:
            lines.append("## Replicas")
            for replica in inv.replicas:
                lines.append(f"* `{replica.replica_id}` in `{replica.module}` — {replica.integration_status}")
                for feature in replica.features:
                    tests = f"; tests: {', '.join(feature.test_names)}" if feature.test_names else ""
                    lines.append(f"  * {feature.status}: {feature.name} — {feature.description}{tests}")
                    for deviation in feature.deviations:
                        lines.append(f"    * deviation: {deviation}")
                for deviation in replica.deviations:
                    lines.append(f"  * deviation: {deviation}")
            lines.append("")

        if inv.conformance:
            lines.append("## Conformance records")
            for record in inv.conformance:
                lines.append(
                    f"* {record.status}: {record.case} (reference: {record.reference}) — {record.details}"
                )
            lines.append("")

        if inv.open_questions:
            lines.append("## Open questions")
            lines.extend(f"* {question}" for question in inv.open_questions)
            lines.append("")
        return "\n".join(lines)

    def export_to_ledger(self, ledger: "Ledger") -> str:
        """Store the package as a ledger object and append a note record.

        Returns the object reference. The note record references the target
        experiment if one is supplied through *experiment*; by default the
        package is recorded under its own target id namespace.
        """

        ref = ledger.put_json(
            {
                "framework_version": self.framework_version,
                "investigation": self.investigation.to_dict(),
            }
        )
        return ref


def write_package(package: EvidencePackage, out_dir: Path) -> Path:
    """Write ``package.json`` and ``package.md`` into *out_dir*; return the JSON path."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "package.json"
    md_path = out_dir / "package.md"
    json_path.write_bytes(package.to_bytes())
    md_path.write_text(package.render_markdown(), encoding="utf-8", newline="\n")
    return json_path
