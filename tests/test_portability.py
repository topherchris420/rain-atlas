"""Evidence must hash identically on every operating system.

Two defects reached the published demonstration before these tests existed:
skill hashes depended on how the host OS sorts paths, and generator scripts
wrote CRLF files on Windows while git committed LF, so no checkout could
reproduce the recorded hashes.
"""

import ast
import io
import zipfile
from pathlib import Path

import pytest
from conftest import BUILTIN, REPO

from rain_atlas.canonical import tree_files, tree_hash
from rain_atlas.provenance import engine_root, source_snapshot

TEXT_SUFFIXES = {".py", ".json", ".md", ".txt", ".html", ".js", ".css", ".toml", ".bib", ".csv", ".yml"}
BUILTIN_SKILLS = sorted(path.parent for path in BUILTIN.rglob("SKILL.md"))


@pytest.mark.parametrize("skill", BUILTIN_SKILLS, ids=lambda p: p.name)
def test_snapshot_digest_and_archive_order_match_the_content_hash(skill):
    archive, digest = source_snapshot(skill)
    assert digest == tree_hash(skill)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.namelist() == [name for name, _ in tree_files(skill)]


@pytest.mark.parametrize("root", [BUILTIN, engine_root()], ids=["skills", "engine"])
def test_hashed_trees_hold_committed_lf_bytes(root):
    # Hashes cover exact bytes. A CRLF working copy (for example a generator
    # script run on Windows without newline="\n") would record hashes that
    # no clean checkout can reproduce, because .gitattributes commits LF.
    crlf = [
        name for name, path in tree_files(root) if path.suffix in TEXT_SUFFIXES and b"\r" in path.read_bytes()
    ]
    assert crlf == []


def _text_writes_without_newline(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        keywords = {k.arg for k in node.keywords}
        if name == "write_text":
            writes = True
        elif name == "open":
            owner = (
                func.value.id
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                else None
            )
            if owner == "os":
                continue  # fd-level API with integer flags: bytes only, no newline translation
            # Path.open(mode) has the mode first; open/io.open(file, mode) second.
            index = 0 if isinstance(func, ast.Attribute) and owner not in {"io", "codecs"} else 1
            mode = node.args[index] if len(node.args) > index else None
            if mode is None:
                mode = next((k.value for k in node.keywords if k.arg == "mode"), None)
            text = mode.value if isinstance(mode, ast.Constant) and isinstance(mode.value, str) else ""
            writes = any(c in text for c in "wxa") and "b" not in text
        else:
            continue
        if writes and "newline" not in keywords:
            found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return found


def test_engine_and_generators_pin_text_line_endings():
    # Text mode translates "\n" to os.linesep on Windows only, so an unpinned
    # write produces different evidence bytes there than on POSIX.
    sources = sorted((REPO / "src" / "rain_atlas").rglob("*.py")) + sorted((REPO / "scripts").glob("*.py"))
    offenders = [hit for path in sources for hit in _text_writes_without_newline(path)]
    assert offenders == []
