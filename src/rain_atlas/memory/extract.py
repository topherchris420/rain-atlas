"""Deterministic structured extraction of scientific memories.

The reference SDK asks a language model to extract facts from messages and
decide between ADD / UPDATE / DELETE. This replica makes the same decisions
with transparent rules so that scientific memory behavior is reproducible and
testable without a model:

* messages are split into candidate statements (sentences, list items,
  labeled lines such as ``Hypothesis:`` or ``Finding:``);
* each statement is classified into a scientific kind by cue phrases;
* subject/predicate statements of the form ``<subject> is <value>`` support
  update-in-place decisions and contradiction detection.

Everything here is deterministic: the same input always yields the same
extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import KINDS

_LABEL_RE = re.compile(
    r"^\s*(hypothesis|finding|decision|rejection|correction|fact)\s*[:\-]\s*(.+)$", re.IGNORECASE
)
_CUE_RE = re.compile(
    r"\b(we hypothesiz|our hypothesis|hypothesis is|we found|we observed|results? show|"
    r"the result is|we (?:decided|conclude)|we reject|correct(?:ion|ed)|previously)"
)
_LIST_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PREDICATE_RE = re.compile(r"^(?P<subject>.+?)\s+(?:is|are|was|were|equals|=)\s+(?P<value>.+)$")
_NEGATION_RE = re.compile(
    r"\b(is not|are not|was not|were not|does not|do not|isn't|aren't|never|no longer)\b",
    re.IGNORECASE,
)

_KIND_CUES = {
    "hypothesis": ("we hypothesiz", "our hypothesis", "hypothesis is", "we predict", "we expect"),
    "finding": ("we found", "we observed", "results show", "the result is", "measurement shows"),
    "decision": ("we decided", "we choose", "we select", "decision is"),
    "rejection": ("we reject", "rejected hypothesis", "we discard"),
    "correction": ("we correct", "correction:", "corrected:", "we revise", "previously believed"),
}


@dataclass
class ExtractedStatement:
    content: str
    kind: str
    subject: str | None = None
    value: str | None = None
    negated: bool = False


def _classify(text: str) -> str:
    lowered = text.lower()
    for kind, cues in _KIND_CUES.items():
        if any(cue in lowered for cue in cues):
            return kind
    return "fact"


def _predicate(content: str) -> tuple[str | None, str | None, bool]:
    match = _PREDICATE_RE.match(content.strip())
    negated = bool(_NEGATION_RE.search(content))
    if match:
        return match.group("subject").strip(), match.group("value").strip(), negated
    return None, None, negated


def predicate_of(content: str) -> tuple[str | None, str | None, bool]:
    """Split a statement into ``(subject, value, negated)`` when possible."""

    match = _PREDICATE_RE.match(content.strip())
    negated = bool(_NEGATION_RE.search(content))
    if match:
        return match.group("subject").strip(), match.group("value").strip(), negated
    return None, None, negated


def extract_statements(messages: str | list[dict[str, str]]) -> list[ExtractedStatement]:
    """Extract candidate memories from a message or message list.

    Accepts the reference SDK's message shapes: a plain string, a single
    ``{"role", "content"}`` dict-like message, or a list of them.
    """

    if isinstance(messages, str):
        texts = [messages]
    elif isinstance(messages, dict):
        texts = [str(messages.get("content", ""))]
    elif isinstance(messages, list):
        texts = []
        for message in messages:
            if isinstance(message, dict):
                if message.get("role") == "system":
                    continue  # system messages are context, not memory (reference behavior)
                texts.append(str(message.get("content", "")))
            elif isinstance(message, str):
                texts.append(message)
    else:
        raise ValueError("messages must be a string, a message dict, or a list of message dicts")

    statements: list[ExtractedStatement] = []
    for text in texts:
        for chunk in _split_text(text):
            content = chunk.strip()
            if not content:
                continue
            label = _LABEL_RE.match(content)
            if label:
                kind = label.group(1).lower()
                if kind not in KINDS:
                    kind = "fact"
                content = label.group(2).strip()
            else:
                kind = _classify(content)
            subject, value, negated = _predicate(content)
            statements.append(
                ExtractedStatement(
                    content=content,
                    kind=kind,
                    subject=subject,
                    value=value,
                    negated=negated,
                )
            )
    return statements


def _split_text(text: str) -> list[str]:
    chunks: list[str] = []
    for line in text.splitlines():
        listed = _LIST_RE.match(line)
        if listed:
            chunks.append(listed.group(1))
        elif line.strip():
            chunks.extend(part for part in _SENTENCE_SPLIT_RE.split(line) if part.strip())
    return chunks
