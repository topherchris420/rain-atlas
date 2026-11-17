"""Versioned, local-first documents with explicit conflict resolution."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..canonical import canonical_bytes, sha256_bytes

STATE_VERSION = 1


@dataclass
class DocumentVersion:
    """One immutable version of a document's content."""

    version: int
    content: dict[str, Any]
    author: str = ""
    timestamp_ms: float = 0.0
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = sha256_bytes(canonical_bytes(self.content))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Document:
    """A document with append-only history; the current version is last."""

    id: str
    kind: str = "note"
    versions: list[DocumentVersion] = field(default_factory=list)

    @property
    def current(self) -> DocumentVersion | None:
        return self.versions[-1] if self.versions else None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "versions": [version.to_dict() for version in self.versions],
        }


@dataclass
class Conflict:
    """A divergence between two lineages of the same document."""

    document_id: str
    left_hash: str
    right_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Resolution:
    """The recorded outcome of resolving a conflict."""

    document_id: str
    strategy: str  # keep-left | keep-right | merged
    chosen_hash: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class KnowledgeStore:
    """Directory-backed, local-first, versioned document store."""

    STATE_VERSION = STATE_VERSION

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else None
        self.documents: dict[str, Document] = {}
        self.resolutions: list[Resolution] = []
        if self.root is not None and (self.root / "documents.json").exists():
            self._load()

    # -- documents -----------------------------------------------------------

    def put(
        self,
        document_id: str,
        content: dict[str, Any],
        *,
        kind: str = "note",
        author: str = "",
        timestamp_ms: float = 0.0,
    ) -> DocumentVersion:
        document = self.documents.get(document_id)
        if document is None:
            document = Document(id=document_id, kind=kind)
            self.documents[document_id] = document
        version = DocumentVersion(
            version=len(document.versions) + 1,
            content=copy.deepcopy(dict(content)),
            author=author,
            timestamp_ms=timestamp_ms,
        )
        document.versions.append(version)
        return version

    def get(self, document_id: str) -> DocumentVersion | None:
        document = self.documents.get(document_id)
        return document.current if document else None

    def history(self, document_id: str) -> list[DocumentVersion]:
        document = self.documents.get(document_id)
        return list(document.versions) if document else []

    def ids(self) -> list[str]:
        return sorted(self.documents)

    # -- portability -----------------------------------------------------------

    def export_state(self) -> bytes:
        return canonical_bytes(
            {
                "state_version": self.STATE_VERSION,
                "documents": [doc.to_dict() for doc in self.documents.values()],
                "resolutions": [r.to_dict() for r in self.resolutions],
            }
        )

    def import_state(self, data: bytes) -> None:
        payload = json.loads(data.decode("utf-8"))
        if payload.get("state_version") != self.STATE_VERSION:
            raise ValueError(f"unsupported state version {payload.get('state_version')!r}")
        for doc_data in payload.get("documents", []):
            document = Document(id=doc_data["id"], kind=doc_data.get("kind", "note"))
            document.versions = [DocumentVersion(**v) for v in doc_data.get("versions", [])]
            existing = self.documents.get(document.id)
            if existing is None:
                self.documents[document.id] = document
            else:
                merged = self.merge_document(existing, document)
                self.documents[document.id] = merged
        for resolution in payload.get("resolutions", []):
            self.resolutions.append(Resolution(**resolution))

    def merge_document(self, left: Document, right: Document) -> Document:
        """Union of both version histories, ordered by (version, hash).

        Divergent histories keep both branches; a resolution record is added
        when the two current versions differ.
        """

        merged = Document(id=left.id, kind=left.kind or right.kind)
        # Revisions are identified by (version, hash), not content alone, so
        # reverted content (A -> B -> A) keeps every revision.
        seen: set[tuple[int, str]] = set()
        for version in [*left.versions, *right.versions]:
            key = (version.version, version.hash)
            if key in seen:
                continue
            seen.add(key)
            merged.versions.append(version)
        left_current = left.current.hash if left.current else ""
        right_current = right.current.hash if right.current else ""
        divergent = bool(left_current and right_current and left_current != right_current)
        # Order by version; on ties keep the incoming (right) branch last so it
        # becomes current, matching the recorded resolution.
        right_keys = {(v.version, v.hash) for v in right.versions}
        merged.versions.sort(key=lambda v: (v.version, (v.version, v.hash) in right_keys, v.hash))
        if divergent and merged.current and merged.current.hash != right_current:
            # Right's head has a lower version: append it as an explicit resolution revision.
            head = right.current
            assert head is not None
            merged.versions.append(
                DocumentVersion(
                    version=merged.versions[-1].version + 1,
                    content=copy.deepcopy(head.content),
                    author=head.author,
                    timestamp_ms=head.timestamp_ms,
                )
            )
        if divergent:
            self.resolutions.append(
                Resolution(
                    document_id=left.id,
                    strategy="keep-right",
                    chosen_hash=merged.current.hash if merged.current else right_current,
                    note="divergent histories imported; both versions retained",
                )
            )
        return merged

    def detect_conflicts(self, other: "KnowledgeStore") -> list[Conflict]:
        conflicts = []
        for document_id in sorted(set(self.documents) & set(other.documents)):
            left = self.documents[document_id].current
            right = other.documents[document_id].current
            if left and right and left.hash != right.hash:
                conflicts.append(
                    Conflict(
                        document_id=document_id,
                        left_hash=left.hash,
                        right_hash=right.hash,
                    )
                )
        return conflicts

    # -- persistence -----------------------------------------------------------

    def flush(self) -> None:
        if self.root is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "documents.json").write_bytes(self.export_state())

    def _load(self) -> None:
        self.import_state((self.root / "documents.json").read_bytes())
