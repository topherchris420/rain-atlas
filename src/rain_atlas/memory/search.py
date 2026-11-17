"""Deterministic lexical retrieval for the memory engine.

The reference SDK ranks memories by embedding-vector similarity and supports
rerankers. This replica ranks by a transparent BM25-style lexical score so
retrieval is exactly reproducible offline. Scores live in ``[0, 1]``:

* 1.0 -- identical normalized content;
* otherwise, the average of query-term coverage and idf-weighted overlap.

Filters mirror the reference's entity scoping (``user_id`` / ``agent_id`` /
``run_id``) plus a practical subset of its metadata operators
(``eq``, ``ne``, ``in``, ``contains``, ``icontains``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .models import MemoryRecord

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have if in into is it its
    of on or our so that the their there these this to was we were will with""".split()
)


def tokenize(text: str) -> list[str]:
    return [token for token in _WORD_RE.findall(text.lower()) if token not in _STOPWORDS]


def normalize(content: str) -> str:
    """Lowercase, tokenize, rejoin: the identity used for exact matches."""

    return " ".join(_WORD_RE.findall(content.lower()))


@dataclass
class ScoredMemory:
    record: MemoryRecord
    score: float

    def public_view(self) -> dict:
        view = self.record.public_view()
        view["score"] = round(self.score, 6)
        return view


def metadata_filter_matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Evaluate metadata filters in the reference's operator grammar subset."""

    for key, condition in filters.items():
        if key in {"user_id", "agent_id", "run_id"}:
            continue  # entity scoping is applied before metadata filtering
        value = metadata.get(key)
        if isinstance(condition, dict):
            for operator, operand in condition.items():
                if operator == "eq" and value != operand:
                    return False
                if operator == "ne" and value == operand:
                    return False
                if operator == "in" and value not in (operand or []):
                    return False
                if operator == "nin" and value in (operand or []):
                    return False
                if operator == "gt":
                    if not isinstance(value, (int, float)) or not value > operand:
                        return False
                if operator == "gte":
                    if not isinstance(value, (int, float)) or not value >= operand:
                        return False
                if operator == "lt":
                    if not isinstance(value, (int, float)) or not value < operand:
                        return False
                if operator == "lte":
                    if not isinstance(value, (int, float)) or not value <= operand:
                        return False
                if operator == "contains" and not (isinstance(value, str) and operand in value):
                    return False
                if operator == "icontains" and not (
                    isinstance(value, str) and operand.lower() in value.lower()
                ):
                    return False
                if operator == "*" and value is None:
                    return False
        elif condition != value:
            return False
    return True


class LexicalIndex:
    """Inverted index over active memories; rebuilt on demand (small scale)."""

    def __init__(self, records: list[MemoryRecord]) -> None:
        self.records = records
        self._doc_freq: dict[str, int] = {}
        self._doc_tokens: dict[str, list[str]] = {}
        for record in records:
            tokens = tokenize(record.content)
            self._doc_tokens[record.id] = tokens
            for token in set(tokens):
                self._doc_freq[token] = self._doc_freq.get(token, 0) + 1

    def _idf(self, token: str) -> float:
        df = self._doc_freq.get(token, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + len(self.records) / df)

    def score(self, query: str, record: MemoryRecord) -> float:
        normalized_query = normalize(query)
        normalized_content = normalize(record.content)
        if normalized_query and normalized_query == normalized_content:
            return 1.0
        query_tokens = tokenize(query)
        if not query_tokens:
            return 0.0
        doc_tokens = self._doc_tokens.get(record.id, [])
        doc_set = set(doc_tokens)
        coverage = sum(1 for token in query_tokens if token in doc_set) / len(query_tokens)
        overlap = sum(self._idf(token) for token in set(query_tokens) & doc_set)
        max_idf = sum(self._idf(token) for token in set(query_tokens)) or 1.0
        return 0.5 * coverage + 0.5 * (overlap / max_idf)

    def search(
        self,
        query: str,
        *,
        scope: dict[str, str],
        top_k: int = 20,
        threshold: float = 0.1,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredMemory]:
        filters = filters or {}
        scored = [
            ScoredMemory(record=record, score=self.score(query, record))
            for record in self.records
            if self._scope_matches(record, scope) and metadata_filter_matches(record.metadata, filters)
        ]
        scored = [item for item in scored if item.score >= threshold]
        scored.sort(key=lambda item: (-item.score, item.record.id))
        return scored[:top_k]

    @staticmethod
    def _scope_matches(record: MemoryRecord, scope: dict[str, str]) -> bool:
        return all(record.scope.get(key) == value for key, value in scope.items() if value)
