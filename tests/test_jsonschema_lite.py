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


@pytest.mark.parametrize(
    "value,schema,valid",
    [
        # JSON equality: booleans are never numbers, although True == 1 in Python.
        (1, {"const": True}, False),
        (1.0, {"const": True}, False),
        (True, {"const": True}, True),
        (True, {"const": 1}, False),
        (1.0, {"const": 1}, True),  # numbers compare mathematically
        (False, {"enum": [0, 1]}, False),
        (0, {"enum": [0, 1]}, True),
        ([1, True], {"const": [1, True]}, True),
        ([1, 1], {"const": [1, True]}, False),
        ({"a": 1}, {"const": {"a": True}}, False),
        # ECMA-262 anchors: "$" ends the input; Python's also allowed a final "\n".
        ("abc\n", {"pattern": "^[a-z]+$"}, False),
        ("abc", {"pattern": "^[a-z]+$"}, True),
        ("x$", {"pattern": r"\$$"}, True),
        ("x$\n", {"pattern": r"\$$"}, False),
        ("$", {"pattern": "^[$]$"}, True),
        ("]$", {"pattern": "^[]$]+$"}, True),
    ],
)
def test_equality_and_anchors_follow_json_schema(value, schema, valid):
    assert (validate(value, schema) == []) is valid


def test_proposal_hashes_reject_a_trailing_newline():
    from rain_atlas.agents.proposals import HASH

    assert validate("sha256:" + "a" * 64, HASH) == []
    assert validate("sha256:" + "a" * 64 + "\n", HASH)
