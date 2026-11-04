"""Strict proposal intake: human or model text is never experimental evidence.

This offline adapter consumes JSON from any operator-chosen model. It neither
contacts models nor executes proposed actions. Registering a design is separate
from approval; arbitrary tools, shell commands and self-approval are rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..canonical import sha256_json
from ..jsonschema_lite import validate
from ..ledger.store import Ledger
from ..skills.registry import Registry
from .lab import author

TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
HASH = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema",
        "action",
        "generation",
        "question",
        "hypothesis",
        "null_hypothesis",
        "controls",
        "criteria",
        "skills",
        "budget",
        "approval_required",
    ],
    "properties": {
        "schema": {"const": "atlas.proposal/v1"},
        "action": {"const": "propose_experiment"},
        "generation": {"enum": ["human", "scripted", "model"]},
        **{k: TEXT for k in ("question", "hypothesis", "null_hypothesis", "controls", "criteria")},
        "approval_required": {"const": True},
        "skills": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "version", "content_hash"],
                "properties": {"name": TEXT, "version": TEXT, "content_hash": HASH},
            },
        },
        "budget": {
            "type": "object",
            "additionalProperties": False,
            "required": ["max_runs", "max_seconds"],
            "properties": {
                "max_runs": {"type": "integer", "minimum": 1, "maximum": 200},
                "max_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
            },
        },
        "model": {
            "type": "object",
            "additionalProperties": False,
            "required": ["identity", "parameters", "prompt_hash"],
            "properties": {
                "identity": TEXT,
                "prompt_hash": HASH,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                        "seed": {"type": "integer"},
                        "top_p": {"type": "number", "minimum": 0, "maximum": 1},
                        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 100000},
                    },
                },
            },
        },
        "parent_experiment": HASH,
    },
}


def load_proposal(path: Path, registry: Registry) -> dict:
    """Load bounded JSON, reject non-finite values, then check hashes and policy."""
    if path.stat().st_size > 128 * 1024:
        raise ValueError("proposal exceeds 128 KiB")

    def invalid(value):
        raise ValueError("non-finite JSON number: " + value)

    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)
    validate_proposal(data, registry)
    return data


def validate_proposal(data: dict, registry: Registry) -> str:
    problems = validate(data, SCHEMA)
    if problems:
        raise ValueError("invalid proposal: " + "; ".join(problems))
    if data["generation"] == "model" and "model" not in data:
        raise ValueError("model proposals require identity, generation parameters and prompt hash")
    if data["generation"] != "model" and "model" in data:
        raise ValueError("model metadata requires generation=model")
    seen = set()
    for proposed in data["skills"]:
        ref = registry.get(proposed["name"], proposed["version"])
        if ref.content_hash != proposed["content_hash"]:
            raise ValueError("proposed skill content hash is stale")
        if ref.name in seen:
            raise ValueError("duplicate skill")
        seen.add(ref.name)
        if (
            ref.trust != "builtin"
            or ref.manifest.permissions["network"]
            or ref.manifest.permissions["subprocess"]
        ):
            raise ValueError(
                "proposal intake currently supports local built-in methods without network or subprocess only"
            )
        if ref.manifest.limits["timeout_s"] > data["budget"]["max_seconds"]:
            raise ValueError("budget cannot reserve even one invocation of the selected skill")
    return sha256_json(data)


def register(data: dict, ledger: Ledger, registry: Registry) -> str:
    """Append an unapproved preregistration; does not run or approve anything."""
    digest = validate_proposal(data, registry)
    if ledger.verify():
        raise ValueError("cannot register into a broken ledger")
    if data.get("parent_experiment"):
        parent = ledger.find(data["parent_experiment"])
        if parent is None or parent.kind != "preregistration":
            raise ValueError("parent experiment is not in this ledger")
    proposal_object = ledger.put_json(data)
    record = {
        "title": data["question"],
        "question": data["question"],
        "hypothesis": data["hypothesis"],
        "null_hypothesis": data["null_hypothesis"],
        "design": {"controls": data["controls"], "skills": data["skills"], "budget": data["budget"]},
        "acceptance": [data["criteria"]],
        "proposal_hash": digest,
        "proposal_object": proposal_object,
        "created_by": author(
            "principal-investigator",
            data["generation"],
            **({"model": data["model"]} if "model" in data else {}),
        ),
        "approval_required": True,
    }
    if data.get("parent_experiment"):
        record["parent_experiment"] = data["parent_experiment"]
    return ledger.append("preregistration", record).object
