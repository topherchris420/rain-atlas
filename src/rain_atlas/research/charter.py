"""The research charter: the scope a human approves before ATLAS acts.

A charter names the question, the domain, the design space ATLAS may explore,
the hypothesis grammar it may use, the methods and skills it may run, its
budgets, the execution environment and the preregistered stopping rule.
Within that scope the research loop decides on its own; anything beyond it is
an escalation (:mod:`rain_atlas.research.governance`).

The charter digest is what an operator approves; changing any field changes
the digest and voids the approval.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..canonical import sha256_json
from ..jsonschema_lite import validate
from .oscillator import CORE, DEFAULT_SPACE, EXPANSION, LIBRARY, OPTIONAL

SCHEMA_ID = "atlas.research-charter/v1"

QUESTION = (
    "Can an intelligent experimental system detect previously unknown changes in a noisy dynamical "
    "system, determine what changed, and develop a better explanatory model using fewer experiments "
    "than conventional methods?"
)

POLICIES = (
    "closed-loop",
    "yoked",
    "open-loop-optimal",
    "fixed-sweep",
    "random",
    "legacy-atlas",
    "closed-loop-no-critic",
    "closed-loop-no-challenge",
)

ANALYSES = (
    "nig-evidence",
    "change-point-evidence",
    "lagrange-multiplier-test",
    "ljung-box",
    "kurtosis-test",
    "huber-irls",
    "chow-test",
    "linear-least-squares-baseline",
)

NUMBER = {"type": "number"}
RANGE = {"type": "array", "items": NUMBER, "minItems": 2, "maxItems": 2}
TERMS = {"type": "array", "items": {"enum": list(LIBRARY)}, "maxItems": len(LIBRARY)}
POSITIVE_INT = {"type": "integer", "minimum": 1}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema",
        "title",
        "question",
        "domain",
        "design_space",
        "hypothesis_grammar",
        "methods",
        "budgets",
        "environment",
        "stopping",
        "priors",
    ],
    "properties": {
        "schema": {"const": SCHEMA_ID},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "question": {"type": "string", "minLength": 10, "maxLength": 2000},
        "domain": {"const": "noisy-driven-oscillator/v1"},
        "design_space": {
            "type": "object",
            "additionalProperties": False,
            "required": list(DEFAULT_SPACE),
            "properties": {k: RANGE for k in DEFAULT_SPACE},
        },
        "hypothesis_grammar": {
            "type": "object",
            "additionalProperties": False,
            "required": ["core", "optional", "expansion", "max_expansions", "max_changes_per_mission"],
            "properties": {
                "core": TERMS,
                "optional": TERMS,
                "expansion": TERMS,
                "max_expansions": {"type": "integer", "minimum": 0, "maximum": 3},
                "max_changes_per_mission": {"const": 1},
            },
        },
        "methods": {
            "type": "object",
            "additionalProperties": False,
            "required": ["design_policies", "analyses", "skills"],
            "properties": {
                "design_policies": {"type": "array", "items": {"enum": list(POLICIES)}, "minItems": 1},
                "analyses": {"type": "array", "items": {"enum": list(ANALYSES)}, "minItems": 1},
                "skills": {"type": "array", "items": {"type": "string"}, "maxItems": 40},
            },
        },
        "budgets": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "experiments_per_mission",
                "featured_missions",
                "benchmark_problems_per_family",
                "wall_seconds",
                "model_calls",
                "max_extension_per_request",
            ],
            "properties": {
                "experiments_per_mission": {"type": "integer", "minimum": 4, "maximum": 64},
                "featured_missions": {"type": "integer", "minimum": 0, "maximum": 12},
                "benchmark_problems_per_family": {"type": "integer", "minimum": 0, "maximum": 500},
                "wall_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 86400},
                "model_calls": {"type": "integer", "minimum": 0, "maximum": 1000},
                "max_extension_per_request": {"type": "integer", "minimum": 0, "maximum": 32},
            },
        },
        "environment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["executor", "network", "hardware_control", "untrusted_code", "model_provider"],
            "properties": {
                "executor": {"enum": ["in-process-simulation"]},
                "network": {"const": False},
                "hardware_control": {"const": False},
                "untrusted_code": {"const": False},
                "model_provider": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["kind", "url", "model"],
                            "properties": {
                                "kind": {"enum": ["ollama"]},
                                "url": {
                                    "type": "string",
                                    "pattern": "^http://(localhost|127\\.0\\.0\\.1)(:[0-9]+)?$",
                                },
                                "model": {"type": "string", "minLength": 1, "maxLength": 200},
                            },
                        },
                    ]
                },
            },
        },
        "stopping": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "decision_probability",
                "attribution_probability",
                "challenge_experiments",
                "futility_nats",
                "futility_patience",
                "futility_min_experiments",
                "min_experiments",
            ],
            "properties": {
                "decision_probability": {"type": "number", "minimum": 0.5, "maximum": 0.9999},
                "attribution_probability": {"type": "number", "minimum": 0.5, "maximum": 0.9999},
                "challenge_experiments": {"type": "integer", "minimum": 0, "maximum": 6},
                "futility_nats": {"type": "number", "minimum": 0, "maximum": 1},
                "futility_patience": POSITIVE_INT,
                "futility_min_experiments": POSITIVE_INT,
                "min_experiments": POSITIVE_INT,
            },
        },
        "priors": {
            "type": "object",
            "additionalProperties": False,
            "required": ["noise_sd", "coefficient_sd", "change_hazard", "change_sd", "memory_validity"],
            "properties": {
                "noise_sd": {"type": "number", "exclusiveMinimum": 0},
                "change_sd": {"type": "number", "exclusiveMinimum": 0},
                "coefficient_sd": {"type": "number", "exclusiveMinimum": 0},
                "change_hazard": {"type": "number", "minimum": 0, "maximum": 0.5},
                "memory_validity": {"type": "number", "minimum": 0.01, "maximum": 0.99},
            },
        },
    },
}


class CharterError(ValueError):
    pass


DEFAULT = {
    "schema": SCHEMA_ID,
    "title": "Detecting and explaining hidden change in a noisy driven oscillator",
    "question": QUESTION,
    "domain": "noisy-driven-oscillator/v1",
    "design_space": {k: list(v) for k, v in DEFAULT_SPACE.items()},
    "hypothesis_grammar": {
        "core": list(CORE),
        "optional": list(OPTIONAL),
        "expansion": list(EXPANSION),
        "max_expansions": 2,
        "max_changes_per_mission": 1,
    },
    "methods": {
        "design_policies": list(POLICIES),
        "analyses": list(ANALYSES),
        "skills": ["fir-identification", "cross-spectral", "spectral-peaks"],
    },
    "budgets": {
        "experiments_per_mission": 16,
        "featured_missions": 5,
        "benchmark_problems_per_family": 50,
        "wall_seconds": 7200,
        "model_calls": 40,
        "max_extension_per_request": 8,
    },
    "environment": {
        "executor": "in-process-simulation",
        "network": False,
        "hardware_control": False,
        "untrusted_code": False,
        "model_provider": None,
    },
    "stopping": {
        "decision_probability": 0.95,
        "attribution_probability": 0.9,
        "challenge_experiments": 2,
        "futility_nats": 0.005,
        "futility_patience": 3,
        "futility_min_experiments": 8,
        "min_experiments": 2,
    },
    "priors": {
        "noise_sd": 2.5,
        "coefficient_sd": 2.0,
        "change_hazard": 0.08,
        "change_sd": 0.5,
        "memory_validity": 0.8,
    },
}


def default_charter(**overrides: Any) -> dict:
    charter = copy.deepcopy(DEFAULT)
    for path, value in overrides.items():
        node = charter
        keys = path.split(".")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return charter


def problems(charter: dict) -> list[str]:
    found = validate(charter, SCHEMA)
    if found:
        return found
    grammar = charter["hypothesis_grammar"]
    if set(grammar["core"]) != set(CORE):
        found.append("hypothesis_grammar.core must be the oscillator core terms x, v, u")
    overlap = set(grammar["core"]) & set(grammar["optional"]) | set(grammar["optional"]) & set(
        grammar["expansion"]
    )
    if overlap:
        found.append(f"grammar groups overlap: {sorted(overlap)}")
    for key, (lo, hi) in charter["design_space"].items():
        if not lo < hi:
            found.append(f"design_space.{key} must be an increasing range")
    if charter["design_space"]["amplitude"][0] < 0:
        found.append("design_space.amplitude must be nonnegative")
    stop = charter["stopping"]
    if (
        stop["challenge_experiments"] + stop["min_experiments"]
        > charter["budgets"]["experiments_per_mission"]
    ):
        found.append("the experiment budget cannot cover the minimum experiments plus the challenge")
    return found


def check(charter: dict) -> dict:
    found = problems(charter)
    if found:
        raise CharterError("; ".join(found))
    return charter


def digest(charter: dict) -> str:
    return sha256_json(check(charter))


def load(path: Path) -> dict:
    return check(json.loads(Path(path).read_text(encoding="utf-8")))


def save(charter: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(check(charter), indent=2) + "\n", encoding="utf-8")


def space_of(charter: dict) -> dict:
    return {k: tuple(v) for k, v in charter["design_space"].items()}
