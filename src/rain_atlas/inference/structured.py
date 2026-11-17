"""Structured outputs: constrain model text to a declared schema.

Uses the engine's lightweight JSON-Schema validator
(:mod:`rain_atlas.jsonschema_lite`) so provider results that claim to be
structured are actually validated against the declared shape.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..jsonschema_lite import validate
from .providers import GenerationResult


class StructuredOutputError(ValueError):
    """The model text did not contain valid schema-conforming JSON."""


def extract_structured(result: GenerationResult, schema: dict[str, Any]) -> Any:
    """Parse the first JSON object in *result.text* and validate it.

    Raises :class:`StructuredOutputError` when no JSON object is present or
    the object fails the schema. Deterministic: pure text processing.
    """

    match = re.search(r"\{.*\}", result.text, re.DOTALL)
    if not match:
        raise StructuredOutputError(f"no JSON object found in provider output: {result.text!r}")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"invalid JSON in provider output: {exc}") from exc
    problems = validate(value, schema)
    if problems:
        raise StructuredOutputError("; ".join(problems))
    return value
