import pytest

from rain_atlas.jsonschema_lite import SchemaError, check_schema, validate

SCHEMA = {
    "type": "object",
    "required": ["n", "tag"],
    "additionalProperties": False,
    "properties": {
        "n": {"type": "integer", "minimum": 1, "maximum": 10},
        "x": {"type": "number", "exclusiveMinimum": 0},
        "tag": {"enum": ["a", "b"]},
        "name": {"type": "string", "pattern": "^[a-z]+$", "maxLength": 5},
        "items": {"type": "array", "minItems": 1, "items": {"type": "number"}},
        "either": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        "one": {"oneOf": [{"type": "integer"}, {"type": "number", "minimum": 100}]},
    },
}


def test_valid_document():
    assert (
        validate(
            {"n": 3, "tag": "a", "x": 0.5, "name": "abc", "items": [1, 2.5], "either": 4, "one": 7}, SCHEMA
        )
        == []
    )


@pytest.mark.parametrize(
    "doc, fragment",
    [
        ({"tag": "a"}, "n"),
        ({"n": 0, "tag": "a"}, "minimum"),
        ({"n": 2.5, "tag": "a"}, "integer"),
        ({"n": True, "tag": "a"}, "integer"),
        ({"n": 2, "tag": "c"}, "one of"),
        ({"n": 2, "tag": "a", "extra": 1}, "extra"),
        ({"n": 2, "tag": "a", "x": 0}, "exclusive"),
        ({"n": 2, "tag": "a", "name": "ABC"}, "does not match"),
        ({"n": 2, "tag": "a", "name": "abcdef"}, "longer than"),
        ({"n": 2, "tag": "a", "items": []}, "items"),
        ({"n": 2, "tag": "a", "items": ["x"]}, "number"),
        ({"n": 2, "tag": "a", "either": 1.5}, "anyOf"),
        ({"n": 2, "tag": "a", "one": 150}, "oneOf"),
    ],
)
def test_invalid_documents(doc, fragment):
    problems = validate(doc, SCHEMA)
    assert problems, doc
    assert any(fragment.lower() in p.lower() for p in problems), problems


def test_unsupported_keywords_are_rejected():
    check_schema(SCHEMA)
    with pytest.raises(SchemaError):
        check_schema({"type": "object", "if": {"type": "object"}})
    with pytest.raises(SchemaError):
        check_schema({"type": "object", "properties": {"a": {"$ref": "#/defs/x"}}})
