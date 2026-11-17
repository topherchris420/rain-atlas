"""The :class:`ScientificMemory` engine.

Implements the reference API surface (``add``, ``search``, ``get``,
``get_all``, ``update``, ``delete``, ``delete_all``, ``history``) with
deterministic rule-based inference and append-only history.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .extract import ExtractedStatement, extract_statements, predicate_of
from .models import (
    SCOPES,
    Contradiction,
    MemoryEvent,
    MemoryRecord,
    memory_id_for,
)
from .search import LexicalIndex, normalize
from .store import MemoryStore

_DUPLICATE_THRESHOLD = 0.92
_RELATED_THRESHOLD = 0.34


def _now(clock) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))


class ScientificMemory:
    """Persistent scientific memory with a mem0-compatible API shape."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        clock: Any | None = None,
    ) -> None:
        self.store = MemoryStore(root)
        self._clock = clock or (lambda: time.time())
        self._sequence_offset = 0

    # -- scope handling --------------------------------------------------

    @staticmethod
    def _scope_from(
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, str]:
        scope = {
            "user_id": user_id or "",
            "agent_id": agent_id or "",
            "run_id": run_id or "",
        }
        if not any(scope.values()):
            raise ValueError("at least one of user_id, agent_id or run_id must be provided")
        return {key: value for key, value in scope.items() if value}

    @staticmethod
    def _scope_from_filters(filters: dict[str, Any] | None) -> dict[str, str]:
        filters = dict(filters or {})
        if not any(key in filters and filters[key] for key in SCOPES):
            raise ValueError("filters must contain at least one of user_id, agent_id, run_id")
        return {key: str(filters.pop(key)) for key in SCOPES if filters.get(key)}

    # -- add ----------------------------------------------------------------

    def add(
        self,
        messages: str | list[dict[str, str]],
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
    ) -> dict:
        """Store memories; returns ``{"results": [{"id", "memory", "event"}]}``.

        With ``infer=True`` (the default) statements are extracted and each
        one becomes an ADD, UPDATE, DELETE or NONE decision, mirroring the
        reference SDK's memory pipeline. With ``infer=False`` each message is
        stored verbatim, also mirroring the reference.
        """

        scope = self._scope_from(user_id=user_id, agent_id=agent_id, run_id=run_id)
        if not infer:
            return self._add_raw(messages, scope, metadata)
        results = []
        for statement in extract_statements(messages):
            results.append(self._add_statement(statement, scope, metadata))
        return {"results": results}

    def _add_raw(
        self,
        messages: str | list[dict[str, str]],
        scope: dict[str, str],
        metadata: dict[str, Any] | None,
    ) -> dict:
        if isinstance(messages, str):
            items = [{"role": "user", "content": messages}]
        elif isinstance(messages, dict):
            items = [messages]
        else:
            items = list(messages)
        results = []
        for message in items:
            if not isinstance(message, dict) or not message.get("content"):
                continue
            if message.get("role") == "system":
                continue
            record = self._create_record(
                content=str(message["content"]),
                scope=scope,
                kind="fact",
                metadata={**(metadata or {}), "role": message.get("role", "user")},
            )
            results.append({"id": record.id, "memory": record.content, "event": "ADD"})
        self.store.flush()
        return {"results": results}

    def _add_statement(
        self,
        statement: ExtractedStatement,
        scope: dict[str, str],
        metadata: dict[str, Any] | None,
    ) -> dict:
        candidates = self._search_scope(statement.content, scope)
        for scored in candidates:
            record = scored.record
            if normalize(record.content) == normalize(statement.content):
                return {"id": record.id, "memory": record.content, "event": "NONE"}
        for scored in candidates:
            record = scored.record
            if scored.score < _RELATED_THRESHOLD:
                continue
            if self._is_contradiction(record, statement):
                return self._apply_contradiction(record, statement, scope, metadata)
            if statement.subject and self._same_subject(record, statement):
                return self._apply_update(record, statement, scope, metadata)
        record = self._create_record(
            content=statement.content,
            scope=scope,
            kind=statement.kind,
            metadata=metadata,
        )
        return {"id": record.id, "memory": record.content, "event": "ADD"}

    def _create_record(
        self,
        content: str,
        scope: dict[str, str],
        kind: str,
        metadata: dict[str, Any] | None,
    ) -> MemoryRecord:
        sequence = self.store.next_sequence()
        record = MemoryRecord(
            id=memory_id_for(scope, content, sequence),
            content=content,
            scope=scope,
            kind=kind,
            metadata=dict(metadata or {}),
            created_at=_now(self._clock),
            updated_at=_now(self._clock),
        )
        self.store.put(record)
        self.store.append_event(
            MemoryEvent(
                memory_id=record.id,
                event="ADD",
                prev_value=None,
                new_value=content,
                timestamp=_now(self._clock),
            )
        )
        self.store.flush()
        return record

    # -- decisions -----------------------------------------------------------

    @staticmethod
    def _same_subject(record: MemoryRecord, statement: ExtractedStatement) -> bool:
        """True when an existing memory makes a claim about the same subject."""

        subject, _value, _neg = predicate_of(record.content)
        return (
            subject is not None
            and statement.subject is not None
            and normalize(subject) == normalize(statement.subject)
        )

    @staticmethod
    def _is_contradiction(record: MemoryRecord, statement: ExtractedStatement) -> bool:
        """A direct negation or an opposite predicate value on the same subject."""

        subject, value, negated = predicate_of(record.content)
        if subject is None or value is None:
            return False
        if normalize(subject) != normalize(statement.subject or ""):
            return False
        if statement.negated != negated:
            return True
        return normalize(value) != normalize(statement.value or "")

    def _apply_contradiction(
        self,
        record: MemoryRecord,
        statement: ExtractedStatement,
        scope: dict[str, str],
        metadata: dict[str, Any] | None,
    ) -> dict:
        """Supersede with history + contradiction record; never silent."""

        replacement = self._create_record(
            content=statement.content,
            scope=scope,
            kind=statement.kind if statement.kind != "fact" else "correction",
            metadata=metadata,
        )
        replacement.supersedes = record.id
        self.store.replace(replacement)
        record.status = "superseded"
        record.superseded_by = replacement.id
        record.updated_at = _now(self._clock)
        self.store.replace(record)
        self.store.append_event(
            MemoryEvent(
                memory_id=record.id,
                event="UPDATE",
                prev_value=record.content,
                new_value=statement.content,
                timestamp=_now(self._clock),
                reason="superseded by contradicting memory",
            )
        )
        self.store.add_contradiction(
            Contradiction(
                id=f"{record.id[:8]}:{replacement.id[:8]}",
                new_memory_id=replacement.id,
                old_memory_id=record.id,
                statement=statement.content,
                detected_at=_now(self._clock),
            )
        )
        self.store.flush()
        return {
            "id": replacement.id,
            "memory": replacement.content,
            "event": "UPDATE",
            "supersedes": record.id,
        }

    def _apply_update(
        self,
        record: MemoryRecord,
        statement: ExtractedStatement,
        scope: dict[str, str],
        metadata: dict[str, Any] | None,
    ) -> dict:
        replacement = self._create_record(
            content=statement.content,
            scope=scope,
            kind=statement.kind,
            metadata=metadata,
        )
        replacement.supersedes = record.id
        self.store.replace(replacement)
        record.status = "superseded"
        record.superseded_by = replacement.id
        record.updated_at = _now(self._clock)
        self.store.replace(record)
        self.store.append_event(
            MemoryEvent(
                memory_id=record.id,
                event="UPDATE",
                prev_value=record.content,
                new_value=statement.content,
                timestamp=_now(self._clock),
                reason="same subject, new value",
            )
        )
        self.store.flush()
        return {
            "id": replacement.id,
            "memory": replacement.content,
            "event": "UPDATE",
            "supersedes": record.id,
        }

    # -- retrieval -----------------------------------------------------------

    def _search_scope(self, query: str, scope: dict[str, str]) -> list:
        index = LexicalIndex(
            [
                record
                for record in self.store.active_records()
                if all(record.scope.get(key) == value for key, value in scope.items())
            ]
        )
        return index.search(query, scope=scope, top_k=5, threshold=_RELATED_THRESHOLD)

    def search(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 20,
        threshold: float = 0.1,
    ) -> dict:
        """Semantic-style retrieval: ``{"results": [{"id", "memory", "score"}]}``."""

        scope = self._scope_from_filters(filters)
        remaining = {key: value for key, value in (filters or {}).items() if key not in SCOPES}
        index = LexicalIndex(
            [
                record
                for record in self.store.active_records()
                if all(record.scope.get(key) == value for key, value in scope.items())
            ]
        )
        scored = index.search(query, scope=scope, top_k=top_k, threshold=threshold, filters=remaining)
        return {"results": [item.public_view() for item in scored]}

    def get(self, memory_id: str) -> dict:
        record = self.store.get(memory_id)
        if record is None:
            raise KeyError(f"memory {memory_id} does not exist")
        return record.public_view()

    def get_all(self, *, filters: dict[str, Any] | None = None, limit: int | None = None) -> dict:
        scope = self._scope_from_filters(filters)
        remaining = {key: value for key, value in (filters or {}).items() if key not in SCOPES}
        from .search import metadata_filter_matches

        records = [
            record
            for record in self.store.active_records()
            if all(record.scope.get(key) == value for key, value in scope.items())
            and metadata_filter_matches(record.metadata, remaining)
        ]
        if limit is not None:
            records = records[:limit]
        return {"results": [record.public_view() for record in records]}

    # -- mutation ------------------------------------------------------------

    def update(self, memory_id: str, data: str) -> dict:
        """Explicit update: supersede content, preserve history."""

        record = self.store.get(memory_id)
        if record is None:
            raise KeyError(f"memory {memory_id} does not exist")
        if record.status != "active":
            raise ValueError(f"memory {memory_id} is {record.status}; update the successor")
        previous = record.content
        replacement = self._create_record(
            content=data, scope=record.scope, kind=record.kind, metadata=record.metadata
        )
        replacement.supersedes = record.id
        self.store.replace(replacement)
        record.status = "superseded"
        record.superseded_by = replacement.id
        record.updated_at = _now(self._clock)
        self.store.replace(record)
        self.store.append_event(
            MemoryEvent(
                memory_id=record.id,
                event="UPDATE",
                prev_value=previous,
                new_value=data,
                timestamp=_now(self._clock),
                reason="explicit update",
            )
        )
        self.store.flush()
        return {"id": replacement.id, "memory": data, "event": "UPDATE"}

    def delete(self, memory_id: str) -> dict:
        record = self.store.get(memory_id)
        if record is None:
            raise KeyError(f"memory {memory_id} does not exist")
        record.status = "deleted"
        record.updated_at = _now(self._clock)
        self.store.replace(record)
        self.store.append_event(
            MemoryEvent(
                memory_id=record.id,
                event="DELETE",
                prev_value=record.content,
                new_value=None,
                timestamp=_now(self._clock),
            )
        )
        self.store.flush()
        return {"id": record.id, "memory": record.content, "event": "DELETE"}

    def delete_all(self, *, filters: dict[str, Any] | None = None) -> dict:
        from .search import metadata_filter_matches

        scope = self._scope_from_filters(filters)
        remaining = {key: value for key, value in (filters or {}).items() if key not in SCOPES}
        removed = 0
        for record in self.store.active_records():
            if all(
                record.scope.get(key) == value for key, value in scope.items()
            ) and metadata_filter_matches(record.metadata, remaining):
                record.status = "deleted"
                record.updated_at = _now(self._clock)
                self.store.replace(record)
                self.store.append_event(
                    MemoryEvent(
                        memory_id=record.id,
                        event="DELETE",
                        prev_value=record.content,
                        new_value=None,
                        timestamp=_now(self._clock),
                    )
                )
                removed += 1
        self.store.flush()
        return {"deleted": removed}

    def history(self, memory_id: str) -> list[dict]:
        """Change history for one memory: ADD/UPDATE/DELETE events in order."""

        return [event.to_dict() for event in self.store.history(memory_id)]

    def contradictions(self) -> list[dict]:
        return [c.to_dict() for c in self.store.contradictions()]

    def statistics(self) -> dict:
        records = list(self.store.iter_records())
        return {
            "total": len(records),
            "active": sum(1 for r in records if r.status == "active"),
            "superseded": sum(1 for r in records if r.status == "superseded"),
            "deleted": sum(1 for r in records if r.status == "deleted"),
            "contradictions": len(self.store.contradictions()),
            "events": len(self.store.all_events()),
        }
