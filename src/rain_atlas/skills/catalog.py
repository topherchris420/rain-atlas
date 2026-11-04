"""Discover skill directories and validate them."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import jsonschema_lite
from ..canonical import tree_hash
from .frontmatter import FrontmatterError, SkillDoc, parse_skill_md, spec_problems
from .manifest import Manifest, load_manifest

SKILL_FILE = "SKILL.md"
MANIFEST_FILE = "skill.json"


@dataclass
class SkillSource:
    """A skill directory as found on disk, with everything validation learned."""

    path: Path
    doc: SkillDoc | None = None
    manifest: Manifest | None = None
    content_hash: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        if self.manifest:
            return self.manifest.name
        if self.doc:
            return self.doc.name
        return self.path.name

    @property
    def ok(self) -> bool:
        return not self.problems


def discover(root: Path) -> list[Path]:
    """Return skill directories under *root* in sorted order.

    A directory that contains ``SKILL.md`` is a skill and is not descended
    into. Hidden directories are skipped. Symlinked directories are refused
    rather than followed, so discovery never leaves *root*.
    """

    root = Path(root)
    if (root / SKILL_FILE).is_file():
        return [root]
    found: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if child.is_symlink():
            raise ValueError(f"symlinked catalog directory: {child}")
        if (child / SKILL_FILE).is_file():
            found.append(child)
        else:
            found.extend(discover(child))
    return found


def _entrypoint_problems(skill_dir: Path, manifest: Manifest) -> list[str]:
    entry = skill_dir / (manifest.entrypoint or "")
    if not manifest.entrypoint or not entry.is_file():
        return [f"entrypoint {manifest.entrypoint!r} not found"]
    if entry.resolve().parent != skill_dir.resolve() and skill_dir.resolve() not in entry.resolve().parents:
        return ["entrypoint must be inside the skill directory"]
    try:
        tree = ast.parse(entry.read_text(encoding="utf-8"), filename=str(entry))
    except SyntaxError as exc:
        return [f"entrypoint does not parse: {exc}"]
    has_run = any(isinstance(node, ast.FunctionDef) and node.name == "run" for node in tree.body)
    return [] if has_run else ["entrypoint must define a top-level run(inputs, ctx) function"]


def _example_problems(skill_dir: Path, manifest: Manifest) -> list[str]:
    problems: list[str] = []
    for example in manifest.examples:
        stem = skill_dir / "examples" / example["name"]
        inp = stem.with_name(stem.name + ".input.json")
        exp = stem.with_name(stem.name + ".expected.json")
        for path, schema, label in ((inp, manifest.inputs, "input"), (exp, manifest.outputs, "expected")):
            if not path.is_file():
                problems.append(f"example {example['name']!r}: missing {path.name}")
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                problems.append(f"example {example['name']!r}: {path.name} is not JSON ({exc})")
                continue
            if label == "expected":
                # Expected files may list only the fields they assert on.
                continue
            problems.extend(
                f"example {example['name']!r}: {err}" for err in jsonschema_lite.validate(data, schema)
            )
    return problems


def load_source(skill_dir: Path) -> SkillSource:
    """Parse and validate one skill directory; never raises for skill content."""

    skill_dir = Path(skill_dir)
    source = SkillSource(path=skill_dir)
    try:
        source.doc = parse_skill_md((skill_dir / SKILL_FILE).read_text(encoding="utf-8"))
        source.problems.extend(f"SKILL.md: {p}" for p in spec_problems(source.doc, skill_dir.name))
    except (OSError, UnicodeDecodeError, FrontmatterError) as exc:
        source.problems.append(f"SKILL.md: {exc}")
    manifest_path = skill_dir / MANIFEST_FILE
    if not manifest_path.is_file():
        source.problems.append("skill.json is missing")
    else:
        try:
            source.manifest = load_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            source.problems.append(str(exc))
    if source.manifest:
        if source.doc and source.doc.name != source.manifest.name:
            source.problems.append("SKILL.md name and skill.json name differ")
        if source.manifest.kind == "executable":
            source.problems.extend(_entrypoint_problems(skill_dir, source.manifest))
            source.problems.extend(_example_problems(skill_dir, source.manifest))
    try:
        source.content_hash = tree_hash(skill_dir)
    except ValueError as exc:
        source.problems.append(str(exc))
    return source


def load_catalog(root: Path) -> list[SkillSource]:
    """Load every skill under *root*; duplicate names are reported on each copy."""

    sources = [load_source(path) for path in discover(root)]
    by_name: dict[str, list[SkillSource]] = {}
    for source in sources:
        by_name.setdefault(source.name, []).append(source)
    for name, group in by_name.items():
        if len(group) > 1:
            where = ", ".join(str(s.path) for s in group)
            for source in group:
                source.problems.append(f"duplicate skill name {name!r} ({where})")
    return sources
