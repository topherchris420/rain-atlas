"""A small, dependency-free validator for a documented JSON Schema subset.

Supported keywords (draft 2020-12 semantics): ``type`` (string or list),
``properties``, ``required``, ``additionalProperties`` (bool or schema),
``items``, ``prefixItems``, ``enum``, ``const``, ``minimum``, ``maximum``,
``exclusiveMinimum``, ``exclusiveMaximum``, ``minItems``, ``maxItems``,
``minLength``, ``maxLength``, ``pattern``, ``anyOf``, ``oneOf``. Annotation
keywords (``description``, ``title``, ``default``, ``examples``, ``$comment``,
``unit``) are accepted and ignored. Any other keyword is a schema error, so a
manifest can never rely on a check this validator silently skips.
"""

from __future__ import annotations

import re
from typing import Any

ANNOTATIONS = frozenset({"description", "title", "default", "examples", "$comment", "unit", "$schema", "$id"})
KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "prefixItems",
        "enum",
        "const",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "pattern",
        "anyOf",
        "oneOf",
    }
)
TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})


class SchemaError(ValueError):
    """The schema itself uses an unsupported or malformed construct."""


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool) or (
            isinstance(value, float) and value.is_integer()
        )
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    raise SchemaError(f"unknown type {expected!r}")


def check_schema(schema: Any, path: str = "#") -> None:
    """Raise :class:`SchemaError` if *schema* uses anything outside the subset."""

    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: a schema must be an object or boolean")
    for key, value in schema.items():
        if key in ANNOTATIONS:
            continue
        if key not in KEYWORDS:
            raise SchemaError(f"{path}: unsupported keyword {key!r}")
        if key == "type":
            names = value if isinstance(value, list) else [value]
            for name in names:
                if name not in TYPES:
                    raise SchemaError(f"{path}/type: unknown type {name!r}")
        elif key == "properties":
            if not isinstance(value, dict):
                raise SchemaError(f"{path}/properties must be an object")
            for name, sub in value.items():
                check_schema(sub, f"{path}/properties/{name}")
        elif key in {"items", "additionalProperties"}:
            check_schema(value, f"{path}/{key}")
        elif key in {"prefixItems", "anyOf", "oneOf"}:
            if not isinstance(value, list) or not value:
                raise SchemaError(f"{path}/{key} must be a non-empty array")
            for index, sub in enumerate(value):
                check_schema(sub, f"{path}/{key}/{index}")
        elif key == "required":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise SchemaError(f"{path}/required must be an array of strings")
        elif key == "enum":
            if not isinstance(value, list):
                raise SchemaError(f"{path}/enum must be an array")
        elif key == "pattern":
            try:
                re.compile(value)
            except re.error as exc:
                raise SchemaError(f"{path}/pattern: {exc}") from exc


def validate(value: Any, schema: Any, path: str = "$") -> list[str]:
    """Return a list of human-readable errors (empty when *value* is valid)."""

    if schema is True:
        return []
    if schema is False:
        return [f"{path}: no value is allowed here"]
    errors: list[str] = []

    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_matches(value, name) for name in names):
            return [f"{path}: expected {' or '.join(names)}, got {type(value).__name__}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(f"{path}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: does not match {schema['pattern']!r}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        prefix = schema.get("prefixItems", [])
        for index, item in enumerate(value):
            if index < len(prefix):
                errors.extend(validate(item, prefix[index], f"{path}[{index}]"))
            elif "items" in schema:
                errors.extend(validate(item, schema["items"], f"{path}[{index}]"))

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in properties:
                errors.extend(validate(item, properties[name], f"{path}.{name}"))
            elif extra is False:
                errors.append(f"{path}: unexpected property {name!r}")
            elif isinstance(extra, dict):
                errors.extend(validate(item, extra, f"{path}.{name}"))

    if "anyOf" in schema:
        if all(validate(value, sub, path) for sub in schema["anyOf"]):
            errors.append(f"{path}: matches none of anyOf")
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not validate(value, sub, path))
        if matches != 1:
            errors.append(f"{path}: matches {matches} of oneOf (exactly 1 required)")
    return errors
