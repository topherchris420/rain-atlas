"""Semantic versions and version ranges (``>=1.2,<2``)."""

from __future__ import annotations

import re

_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_LOOSE_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_CLAUSE_RE = re.compile(r"^(>=|<=|==|!=|>|<)?\s*([0-9][0-9.]*)$")

Version = tuple[int, int, int]


def parse_version(text: str) -> Version:
    """Parse a strict ``MAJOR.MINOR.PATCH`` version."""

    match = _VERSION_RE.match(text.strip())
    if not match:
        raise ValueError(f"{text!r} is not MAJOR.MINOR.PATCH")
    return (int(match[1]), int(match[2]), int(match[3]))


def loose_version(text: str) -> Version:
    """Parse the numeric prefix of a package version (``2.5.4``, ``1.18.1rc1``)."""

    match = _LOOSE_RE.match(text.strip())
    if not match:
        raise ValueError(f"cannot read a version from {text!r}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def parse_range(text: str) -> list[tuple[str, Version]]:
    """Parse a comma-separated range; an empty string or ``*`` matches anything."""

    text = text.strip()
    if text in {"", "*"}:
        return []
    clauses = []
    for part in text.split(","):
        match = _CLAUSE_RE.match(part.strip())
        if not match:
            raise ValueError(f"invalid version clause {part.strip()!r}")
        clauses.append((match[1] or "==", loose_version(match[2])))
    return clauses


def satisfies(version: Version, spec: str) -> bool:
    for op, bound in parse_range(spec):
        if op == ">=" and not version >= bound:
            return False
        if op == ">" and not version > bound:
            return False
        if op == "<=" and not version <= bound:
            return False
        if op == "<" and not version < bound:
            return False
        if op == "==" and version != bound:
            return False
        if op == "!=" and version == bound:
            return False
    return True


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)
