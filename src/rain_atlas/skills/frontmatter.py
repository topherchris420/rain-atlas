"""Strict parser for the portable ``SKILL.md`` frontmatter subset.

ATLAS accepts only what every Agent Skills client reads the same way:

* top-level ``key: value`` scalars (plain, single- or double-quoted);
* folded (``>``) and literal (``|``) block scalars;
* one ``metadata:`` mapping whose values are scalars.

Flow collections, anchors, tabs, duplicate keys and nested structures are
rejected with a line number, because different clients parse them
differently. Keys are limited to the six specification keys.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

SPEC_KEYS = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BLOCK_RE = re.compile(r"^[>|][+-]?$")


class FrontmatterError(ValueError):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


@dataclass
class SkillDoc:
    """Parsed ``SKILL.md``: frontmatter fields plus the Markdown body."""

    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    body: str = ""


def _scalar(raw: str, line: int) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] in "[{&*!%@`":
        raise FrontmatterError(f"unsupported YAML construct {raw[0]!r}; quote the value", line)
    if raw[0] in "\"'":
        if len(raw) < 2 or raw[-1] != raw[0]:
            raise FrontmatterError("unterminated quoted string", line)
        if raw[0] == '"':
            try:
                return str(ast.literal_eval(raw))
            except (SyntaxError, ValueError) as exc:
                raise FrontmatterError(f"invalid double-quoted string: {exc}", line) from exc
        return raw[1:-1].replace("''", "'")
    if ": " in raw or raw.endswith(":") or " #" in raw:
        raise FrontmatterError("plain value contains ': ' or ' #'; quote it", line)
    return raw


def _block(lines: list[str], start: int, indicator: str) -> tuple[str, int]:
    block: list[str] = []
    index = start
    while index < len(lines):
        raw = lines[index]
        if raw.strip() and not raw.startswith((" ", "\t")):
            break
        block.append(raw)
        index += 1
    while block and not block[-1].strip():
        block.pop()
    indents = [len(b) - len(b.lstrip(" ")) for b in block if b.strip()]
    cut = min(indents) if indents else 0
    stripped = [b[cut:] if b.strip() else "" for b in block]
    if indicator.startswith("|"):
        return "\n".join(stripped).strip(), index
    paragraphs: list[str] = []
    current: list[str] = []
    for piece in stripped:
        if piece:
            current.append(piece.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs).strip(), index


def parse_skill_md(text: str) -> SkillDoc:
    """Parse ``SKILL.md`` text, raising :class:`FrontmatterError` on any problem."""

    if text.startswith("﻿"):
        raise FrontmatterError("file starts with a byte-order mark", 1)
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        raise FrontmatterError("SKILL.md must start with '---'", 1)
    try:
        close = next(i for i in range(1, len(lines)) if lines[i].rstrip() == "---")
    except StopIteration:
        raise FrontmatterError("frontmatter is not closed with '---'") from None
    fm = lines[1:close]
    body = "\n".join(lines[close + 1 :]).strip()

    values: dict[str, object] = {}
    index = 0
    while index < len(fm):
        raw = fm[index]
        lineno = index + 2
        index += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise FrontmatterError("tab indentation", lineno)
        if raw.startswith(" "):
            raise FrontmatterError("unexpected indented line", lineno)
        key, sep, rest = raw.partition(":")
        key = key.strip()
        if not sep:
            raise FrontmatterError("expected 'key: value'", lineno)
        if key not in SPEC_KEYS:
            raise FrontmatterError(
                f"key {key!r} is not one of the Agent Skills keys {SPEC_KEYS}; "
                "put ATLAS fields in skill.json",
                lineno,
            )
        if key in values:
            raise FrontmatterError(f"duplicate key {key!r}", lineno)
        rest = rest.strip()
        if key == "metadata":
            if rest:
                raise FrontmatterError("metadata must be a block mapping", lineno)
            mapping: dict[str, str] = {}
            while index < len(fm) and (fm[index].startswith("  ") or not fm[index].strip()):
                child = fm[index]
                child_line = index + 2
                index += 1
                if not child.strip():
                    continue
                if child.startswith("    "):
                    raise FrontmatterError("metadata values must be scalars", child_line)
                ckey, csep, cval = child.strip().partition(":")
                if not csep or not ckey:
                    raise FrontmatterError("expected 'key: value' inside metadata", child_line)
                if ckey in mapping:
                    raise FrontmatterError(f"duplicate metadata key {ckey!r}", child_line)
                if _BLOCK_RE.match(cval.strip()):
                    raise FrontmatterError("block scalars are not allowed inside metadata", child_line)
                mapping[ckey.strip()] = _scalar(cval, child_line)
            values[key] = mapping
        elif _BLOCK_RE.match(rest):
            values[key], index = _block(fm, index, rest)
        else:
            values[key] = _scalar(rest, lineno)

    for required in ("name", "description"):
        if not values.get(required):
            raise FrontmatterError(f"missing required key {required!r}")
    return SkillDoc(
        name=str(values["name"]),
        description=str(values["description"]),
        license=values.get("license"),  # type: ignore[arg-type]
        compatibility=values.get("compatibility"),  # type: ignore[arg-type]
        allowed_tools=values.get("allowed-tools"),  # type: ignore[arg-type]
        metadata=values.get("metadata", {}),  # type: ignore[arg-type]
        body=body,
    )


def spec_problems(doc: SkillDoc, directory_name: str) -> list[str]:
    """Agent Skills specification checks on an already-parsed document."""

    problems: list[str] = []
    if len(doc.name) > 64:
        problems.append("name is longer than 64 characters")
    if not NAME_RE.match(doc.name):
        problems.append("name must be lowercase letters, digits and single hyphens")
    if doc.name != directory_name:
        problems.append(f"name {doc.name!r} does not match directory {directory_name!r}")
    if len(doc.description) > 1024:
        problems.append("description is longer than 1024 characters")
    if doc.compatibility is not None and not 1 <= len(doc.compatibility) <= 500:
        problems.append("compatibility must be 1-500 characters")
    if len(doc.body.splitlines()) > 500:
        problems.append("SKILL.md body is longer than 500 lines; move detail to references/")
    return problems
