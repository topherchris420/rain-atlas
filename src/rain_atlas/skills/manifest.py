"""The ``skill.json`` manifest (schema ``atlas.skill/v1``)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import jsonschema_lite
from .versions import parse_range, parse_version

SCHEMA_ID = "atlas.skill/v1"
CAPABILITY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$")
DOMAINS = (
    "mathematics",
    "signal-processing",
    "computational-physics",
    "dynamical-systems",
    "neuroscience",
    "literature",
    "statistics",
    "visualization",
    "simulation",
    "evaluation",
    "resonance",
    "astrodynamics",
)
READ_SCOPES = frozenset({"inputs", "skill", "system-fonts"})
WRITE_SCOPES = frozenset({"outputs"})

MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema",
        "name",
        "version",
        "kind",
        "domain",
        "capabilities",
        "permissions",
        "limits",
        "requires",
    ],
    "additionalProperties": False,
    "properties": {
        "schema": {"const": SCHEMA_ID},
        "name": {"type": "string", "pattern": r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 64},
        "version": {"type": "string"},
        "kind": {"enum": ["executable", "guidance"]},
        "domain": {"enum": list(DOMAINS)},
        "summary": {"type": "string", "maxLength": 300},
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "entrypoint": {"type": "string"},
        "determinism": {"enum": ["deterministic", "seeded", "stochastic"]},
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "permissions": {
            "type": "object",
            "additionalProperties": False,
            "required": ["network", "subprocess", "read", "write"],
            "properties": {
                "network": {"type": "boolean"},
                "subprocess": {"type": "boolean"},
                "read": {"type": "array", "items": {"enum": sorted(READ_SCOPES)}},
                "write": {"type": "array", "items": {"enum": sorted(WRITE_SCOPES)}},
            },
        },
        "limits": {
            "type": "object",
            "additionalProperties": False,
            "required": ["timeout_s", "memory_mb"],
            "properties": {
                "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": 86400},
                "memory_mb": {"type": "integer", "minimum": 64, "maximum": 262144},
            },
        },
        "requires": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "python": {"type": "string"},
                "packages": {"type": "object", "additionalProperties": {"type": "string"}},
                "skills": {"type": "object", "additionalProperties": {"type": "string"}},
            },
        },
        "examples": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9-]*$"},
                    "seed": {"type": "integer"},
                    "tolerance": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "abs": {"type": "number", "minimum": 0},
                            "rel": {"type": "number", "minimum": 0},
                        },
                    },
                },
            },
        },
        "references": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    kind: str
    domain: str
    capabilities: tuple[str, ...]
    permissions: dict[str, Any]
    limits: dict[str, Any]
    requires: dict[str, Any]
    entrypoint: str | None = None
    determinism: str = "deterministic"
    summary: str = ""
    inputs: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    outputs: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    examples: tuple[dict[str, Any], ...] = ()
    references: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


def manifest_problems(data: Any) -> list[str]:
    """Return every problem with a manifest document (empty when valid)."""

    problems = jsonschema_lite.validate(data, MANIFEST_SCHEMA, "skill.json")
    if problems:
        return problems
    try:
        parse_version(data["version"])
    except ValueError as exc:
        problems.append(f"skill.json.version: {exc}")
    for cap in data["capabilities"]:
        if not CAPABILITY_RE.match(cap):
            problems.append(f"skill.json.capabilities: {cap!r} must look like 'area.capability-name'")
    if data["kind"] == "executable":
        for key in ("entrypoint", "inputs", "outputs", "determinism"):
            if key not in data:
                problems.append(f"skill.json: executable skills need {key!r}")
        if not data.get("examples"):
            problems.append("skill.json: executable skills need at least one example")
        if not data["capabilities"]:
            problems.append("skill.json: executable skills must declare at least one capability")
    elif data.get("capabilities"):
        problems.append("skill.json: guidance skills cannot declare executable capabilities")
    for key in ("inputs", "outputs"):
        if key in data:
            try:
                jsonschema_lite.check_schema(data[key], f"skill.json.{key}")
            except jsonschema_lite.SchemaError as exc:
                problems.append(str(exc))
    for name, spec in data["requires"].get("skills", {}).items():
        try:
            parse_range(spec)
        except ValueError as exc:
            problems.append(f"skill.json.requires.skills.{name}: {exc}")
    for name, spec in data["requires"].get("packages", {}).items():
        try:
            parse_range(spec)
        except ValueError as exc:
            problems.append(f"skill.json.requires.packages.{name}: {exc}")
    if "python" in data["requires"]:
        try:
            parse_range(data["requires"]["python"])
        except ValueError as exc:
            problems.append(f"skill.json.requires.python: {exc}")
    return problems


def load_manifest(path: Path) -> Manifest:
    """Load and validate ``skill.json``; raises ``ValueError`` listing all problems."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"skill.json is not valid JSON: {exc}") from exc
    problems = manifest_problems(data)
    if problems:
        raise ValueError("; ".join(problems))
    return Manifest(
        name=data["name"],
        version=data["version"],
        kind=data["kind"],
        domain=data["domain"],
        capabilities=tuple(data["capabilities"]),
        permissions=dict(data["permissions"]),
        limits=dict(data["limits"]),
        requires=dict(data["requires"]),
        entrypoint=data.get("entrypoint"),
        determinism=data.get("determinism", "deterministic"),
        summary=data.get("summary", ""),
        inputs=data.get("inputs", {"type": "object"}),
        outputs=data.get("outputs", {"type": "object"}),
        examples=tuple(data.get("examples", ())),
        references=tuple(data.get("references", ())),
        limitations=tuple(data.get("limitations", ())),
        raw=data,
    )
