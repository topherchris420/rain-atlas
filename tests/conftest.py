from pathlib import Path

import pytest

from rain_atlas.exec.runner import SkillRef
from rain_atlas.skills.catalog import load_source
from rain_atlas.skills.registry import Registry

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "skills"
BUILTIN = REPO / "skills"


def fixture_ref(name: str, trust: str = "local") -> SkillRef:
    src = load_source(FIXTURES / name)
    assert src.ok, src.problems
    return SkillRef(src.name, src.manifest.version, src.path, src.manifest, src.content_hash, trust)


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    return path


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(home=tmp_path / "home", builtin_root=BUILTIN)
