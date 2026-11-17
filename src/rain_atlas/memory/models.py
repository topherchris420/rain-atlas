"""Memory records, events and contradictions."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from ..canonical import canonical_bytes, sha256_bytes

# Scientific memory kinds supported by the extraction rules.
KINDS = ("fact", "hypothesis", "finding", "decision", "rejection", "correction")

EVENTS = ("ADD", "UPDATE", "DELETE")

SCOPES = ("user_id", "agent_id", "run_id")


def memory_id_for(scope: dict[str, str], content: str, sequence: int) -> str:
    """Deterministic memory id: same inputs always produce the same id.

    The reference SDK uses random UUIDs; reproducibility requires
    content-derived ids. A sequence number separates identical content added
    more than once within one process lifetime.
    """

    return sha256_bytes(canonical_bytes({"scope": scope, "content": content, "sequence": sequence}))[:20]


@dataclass
class MemoryRecord:
    """One stored memory with immutable provenance and mutable status."""

    id: str
    content: str
    scope: dict[str, str]
    kind: str = "fact"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    hash: str = ""
    status: str = "active"  # active | superseded | deleted
    supersedes: str | None = None
    superseded_by: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = sha256_bytes(self.content.encode("utf-8"))
        if self.kind not in KINDS:
            raise ValueError(f"unknown memory kind {self.kind!r}; expected one of {KINDS}")

    def to_dict(self) -> dict:
        # Hand-written (not dataclasses.asdict): the store serializes every
        # record on each commit, and asdict's recursive deep copy dominated.
        return {
            "id": self.id,
            "content": self.content,
            "scope": dict(self.scope),
            "kind": self.kind,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "hash": self.hash,
            "status": self.status,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        return cls(**data)

    def public_view(self) -> dict:
        """The search/get projection: content, scope and metadata."""

        view = {
            "id": self.id,
            "memory": self.content,
            "hash": self.hash,
            "kind": self.kind,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        metadata = dict(self.metadata)
        metadata.update({key: value for key, value in self.scope.items() if value})
        view["metadata"] = metadata
        return view


@dataclass
class MemoryEvent:
    """One append-only history entry for a memory (never rewrites history)."""

    memory_id: str
    event: str
    prev_value: str | None
    new_value: str | None
    timestamp: str = ""
    reason: str = ""
    actor: str = "memory-engine"

    def __post_init__(self) -> None:
        if self.event not in EVENTS:
            raise ValueError(f"unknown memory event {self.event!r}; expected one of {EVENTS}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEvent":
        return cls(**data)


@dataclass
class Contradiction:
    """A recorded conflict between two memories.

    The engine never resolves a contradiction silently: both memories remain
    retrievable, the newer one supersedes the older with an UPDATE event,
    and this record links them for later review.
    """

    id: str
    new_memory_id: str
    old_memory_id: str
    statement: str
    detected_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Contradiction":
        return cls(**data)
