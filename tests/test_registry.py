import json
import shutil

import pytest
from conftest import FIXTURES

from rain_atlas.skills.registry import RegistryError


def copy_skill(tmp_path, name="echo", version=None, tweak=None):
    target = tmp_path / "src" / f"{name}-{version or 'base'}-{tweak or 0}" / name
    shutil.copytree(FIXTURES / name, target)
    if version:
        path = target / "skill.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        path.write_text(json.dumps(data), encoding="utf-8")
    if tweak:
        with (target / "run.py").open("a", encoding="utf-8") as fh:
            fh.write(f"\n# change {tweak}\n")
    return target


def test_builtins_are_listed_and_selectable(registry):
    names = {item.name for item in registry.listings() if item.trust == "builtin"}
    assert "spectral-peaks" in names
    chosen = registry.select("spectral.peak-frequencies")
    assert chosen and chosen[0].name == "spectral-peaks"
    assert registry.select("no.such-capability") == []


def test_install_is_idempotent_and_never_overwrites(registry, tmp_path):
    src = copy_skill(tmp_path)
    assert "installed" in registry.install(src)
    assert "identical" in registry.install(src)
    changed = copy_skill(tmp_path, tweak=1)
    with pytest.raises(RegistryError, match="different content"):
        registry.install(changed)
    assert registry.get("echo").version == "1.0.0"


def test_builtin_names_cannot_be_shadowed(registry, tmp_path):
    target = tmp_path / "spectral-peaks"
    shutil.copytree(registry.builtin_root / "signal-processing" / "spectral-peaks", target)
    with pytest.raises(RegistryError, match="built-in"):
        registry.install(target)


def test_untrusted_skills_need_hash_pinned_approval(registry, tmp_path):
    registry.install(copy_skill(tmp_path), trust="untrusted")
    with pytest.raises(RegistryError, match="not approved"):
        registry.get("echo")
    assert registry.select("test.echo") == []
    listing = next(i for i in registry.listings() if i.name == "echo")
    with pytest.raises(RegistryError):
        registry.approve("echo", "1.0.0", "deadbeef")
    registry.approve("echo", "1.0.0", listing.content_hash.split(":")[1][:12])
    assert registry.get("echo").trust == "untrusted"


def test_disable_and_enable(registry):
    registry.set_enabled("spectral-peaks", False)
    with pytest.raises(RegistryError, match="disabled"):
        registry.get("spectral-peaks")
    assert registry.select("spectral.peak-frequencies") == []
    registry.set_enabled("spectral-peaks", True)
    assert registry.get("spectral-peaks").name == "spectral-peaks"


def test_upgrade_activates_only_after_checks(registry, tmp_path):
    registry.install(copy_skill(tmp_path))
    message = registry.upgrade(copy_skill(tmp_path, version="1.1.0"), check=lambda ref: ["example failed"])
    assert "NOT activated" in message
    assert registry.get("echo").version == "1.0.0"
    message = registry.upgrade(copy_skill(tmp_path, version="1.2.0"), check=lambda ref: [])
    assert registry.get("echo").version == "1.2.0"
    assert {i.version for i in registry.listings() if i.name == "echo"} == {"1.0.0", "1.1.0", "1.2.0"}
    with pytest.raises(RegistryError, match="not newer"):
        registry.upgrade(copy_skill(tmp_path, version="1.0.5"))


def test_remove_moves_to_trash_and_respects_citations(registry, tmp_path):
    registry.install(copy_skill(tmp_path))
    with pytest.raises(RegistryError, match="cited"):
        registry.remove("echo", "1.0.0", referenced=lambda h: True)
    message = registry.remove("echo", "1.0.0", referenced=lambda h: False)
    assert "trash" in message
    assert list((registry.root / "trash").rglob("skill.json"))
    with pytest.raises(RegistryError):
        registry.get("echo")
    with pytest.raises(RegistryError, match="built-in"):
        registry.remove("spectral-peaks", "1.0.0")


def test_tampered_install_is_flagged(registry, tmp_path):
    registry.install(copy_skill(tmp_path))
    installed = registry.root / "skills" / "echo" / "1.0.0" / "echo" / "run.py"
    installed.write_text(installed.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    listing = next(i for i in registry.listings() if i.name == "echo")
    assert any("no longer match" in p for p in listing.problems)
    assert registry.select("test.echo") == []
    # Regression: get() (used by `atlas run` and upgrade checks) re-hashed the
    # files and compared them with themselves, so it returned tampered code.
    with pytest.raises(RegistryError, match="no longer match"):
        registry.get("echo")


def test_dependency_resolution(registry, tmp_path):
    registry.install(copy_skill(tmp_path))
    dependent = copy_skill(tmp_path, name="naughty")
    path = dependent / "skill.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["requires"]["skills"] = {"echo": ">=1.0.0, <2.0.0"}
    path.write_text(json.dumps(data), encoding="utf-8")
    registry.install(dependent)
    deps = registry.resolve_dependencies(registry.get("naughty"))
    assert [d.name for d in deps] == ["echo"]
    data["version"] = "1.0.1"
    data["requires"]["skills"] = {"echo": ">=2.0.0"}
    path.write_text(json.dumps(data), encoding="utf-8")
    registry.upgrade(dependent)
    with pytest.raises(RegistryError, match="needs echo"):
        registry.resolve_dependencies(registry.get("naughty"))
