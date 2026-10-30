import json
import shutil

import pytest

from rain_atlas.skills.catalog import discover, load_catalog, load_source
from rain_atlas.skills.frontmatter import FrontmatterError, parse_skill_md, spec_problems
from rain_atlas.skills.manifest import DOMAINS, manifest_problems
from rain_atlas.skills.versions import parse_version, satisfies

from conftest import BUILTIN, FIXTURES

GOOD = """---
name: demo-skill
description: Does a demo thing. Use when testing.
license: MIT
metadata:
  version: "1.0.0"
---
# Demo
"""


def test_parse_valid_frontmatter():
    doc = parse_skill_md(GOOD)
    assert doc.name == "demo-skill"
    assert doc.metadata == {"version": "1.0.0"}
    assert doc.body.strip() == "# Demo"
    assert spec_problems(doc, "demo-skill") == []


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("﻿" + GOOD, "byte-order"),
        (GOOD.replace("license: MIT", "version: 1"), "not one of"),
        (GOOD.replace("license: MIT", "license: MIT\nlicense: MIT"), "duplicate"),
        (GOOD.replace('  version: "1.0.0"', '\tversion: "1.0.0"'), "tab"),
        (GOOD.replace("Use when testing.", "Use: when testing."), "quote"),
        ("# no frontmatter\n", "start with"),
        (GOOD.replace("description: Does a demo thing. Use when testing.\n", ""), "description"),
    ],
)
def test_frontmatter_rejections(text, fragment):
    with pytest.raises(FrontmatterError) as info:
        parse_skill_md(text)
    assert fragment in str(info.value)


def test_name_must_match_directory():
    doc = parse_skill_md(GOOD)
    assert any("directory" in p for p in spec_problems(doc, "other-name"))


def test_versions_and_ranges():
    assert parse_version("1.2.3") == (1, 2, 3)
    with pytest.raises(ValueError):
        parse_version("1.2")
    assert satisfies((1, 4, 0), ">=1.2, <2.0.0")
    assert not satisfies((2, 0, 0), ">=1.2, <2.0.0")
    assert satisfies((1, 0, 0), "==1.0.0")
    assert not satisfies((1, 0, 1), "==1.0.0")


def test_builtin_catalog_is_valid_and_covers_domains():
    catalog = load_catalog(BUILTIN)
    assert catalog, "no built-in skills found"
    for src in catalog:
        assert src.ok, (src.name, src.problems)
        assert src.manifest.domain in DOMAINS
        assert src.manifest.examples, f"{src.name} has no examples"
    names = {src.name for src in catalog}
    assert {"synthetic-tones", "spectral-peaks", "sinusoid-fit", "tone-presence-test", "method-agreement",
            "recovery-score", "scientific-figure"} <= names


def test_manifest_problems_reported():
    data = json.loads((FIXTURES / "echo" / "skill.json").read_text(encoding="utf-8"))
    assert manifest_problems(data) == []
    broken = dict(data, version="1.0", capabilities=["NotACapability"])
    problems = manifest_problems(broken)
    assert problems
    no_examples = dict(data, examples=[])
    assert any("example" in p for p in manifest_problems(no_examples))


def test_catalog_flags_missing_entrypoint_and_bad_example(tmp_path):
    target = tmp_path / "echo"
    shutil.copytree(FIXTURES / "echo", target)
    (target / "run.py").write_text("def not_run(inputs, ctx):\n    return {}\n", encoding="utf-8")
    (target / "examples" / "three.input.json").write_text('{"values": "nope"}', encoding="utf-8")
    src = load_source(target)
    assert not src.ok
    joined = " ".join(src.problems)
    assert "run(inputs, ctx)" in joined
    assert "three" in joined


def test_discovery_skips_hidden_and_underscore(tmp_path):
    for name in ("visible", ".hidden", "_private"):
        shutil.copytree(FIXTURES / "echo", tmp_path / name / "echo")
    found = discover(tmp_path)
    assert [p.parent.name for p in found] == ["visible"]
