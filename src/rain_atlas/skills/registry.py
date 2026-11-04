"""Skill registry: built-in catalog plus versioned local installs.

Installed skills live under ``<home>/registry/skills/<name>/<version>/<name>/``
(the innermost directory keeps the skill's own name, as the skill format
requires) and are never overwritten: reinstalling identical content is a
no-op, different content under an existing version is refused, upgrades add a
directory, and removal moves the version directory to
``<home>/registry/trash/``.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..canonical import tree_hash
from ..exec.runner import SkillRef
from .catalog import SkillSource, load_catalog, load_source
from .versions import format_version, parse_version, satisfies

TRUST_LEVELS = ("builtin", "local", "untrusted")
INDEX_SCHEMA = "atlas.registry/v1"


class RegistryError(RuntimeError):
    pass


def default_builtin_root() -> Path:
    env = os.environ.get("ATLAS_BUILTIN_SKILLS")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "skills"


def default_home() -> Path:
    return Path(os.environ.get("ATLAS_HOME", Path.home() / ".rain-atlas"))


@dataclass
class Listing:
    name: str
    version: str
    trust: str
    path: Path
    content_hash: str | None
    enabled: bool
    active: bool
    approved: bool
    problems: list[str] = field(default_factory=list)
    capabilities: tuple[str, ...] = ()
    domain: str | None = None
    summary: str = ""


class Registry:
    def __init__(self, home: Path | None = None, builtin_root: Path | None = None):
        self.home = Path(home) if home else default_home()
        self.builtin_root = Path(builtin_root) if builtin_root else default_builtin_root()
        self.root = self.home / "registry"
        self.index_path = self.root / "index.json"
        self._builtin: list[SkillSource] | None = None

    def _version_dir(self, name: str, version: str) -> Path:
        return self.root / "skills" / name / version

    def _skill_dir(self, name: str, version: str) -> Path:
        return self._version_dir(name, version) / name

    # index ------------------------------------------------------------------
    def _read_index(self) -> dict:
        if not self.index_path.exists():
            return {"schema": INDEX_SCHEMA, "disabled": [], "installed": {}}
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        if data.get("schema") != INDEX_SCHEMA:
            raise RegistryError(f"unexpected registry index schema {data.get('schema')!r}")
        return data

    def _write_index(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.index_path)

    # catalog --------------------------------------------------------------
    def builtin(self) -> list[SkillSource]:
        if self._builtin is None:
            self._builtin = load_catalog(self.builtin_root) if self.builtin_root.is_dir() else []
        return self._builtin

    def listings(self) -> list[Listing]:
        index = self._read_index()
        disabled = set(index["disabled"])
        out = []
        for src in self.builtin():
            out.append(self._listing(src, "builtin", src.name not in disabled, True, True))
        for name, info in sorted(index["installed"].items()):
            for version, meta in sorted(info["versions"].items(), key=lambda kv: parse_version(kv[0])):
                src = load_source(self._skill_dir(name, version))
                if src.content_hash != meta["content_hash"]:
                    src.problems.append("installed files no longer match the recorded content hash")
                out.append(
                    self._listing(
                        src,
                        meta["trust"],
                        name not in disabled,
                        version == info["active"],
                        meta.get("approved", meta["trust"] != "untrusted"),
                    )
                )
        return out

    @staticmethod
    def _listing(src: SkillSource, trust: str, enabled: bool, active: bool, approved: bool) -> Listing:
        m = src.manifest
        return Listing(
            name=src.name,
            version=m.version if m else "?",
            trust=trust,
            path=src.path,
            content_hash=src.content_hash,
            enabled=enabled,
            active=active,
            approved=approved,
            problems=list(src.problems),
            capabilities=m.capabilities if m else (),
            domain=m.domain if m else None,
            summary=m.summary if m else "",
        )

    def _ref(self, listing: Listing) -> SkillRef:
        src = load_source(listing.path)
        if src.problems or not src.manifest:
            raise RegistryError(f"{listing.name}@{listing.version} is invalid: {'; '.join(src.problems)}")
        if src.content_hash != listing.content_hash:
            raise RegistryError(f"{listing.name}@{listing.version} changed on disk")
        return SkillRef(
            src.name, src.manifest.version, src.path, src.manifest, src.content_hash, listing.trust
        )

    def get(self, name: str, version: str | None = None) -> SkillRef:
        candidates = [
            item
            for item in self.listings()
            if item.name == name and (item.version == version if version else item.active)
        ]
        if not candidates:
            raise RegistryError(f"skill {name}{'@' + version if version else ''} is not available")
        item = candidates[0]
        if not item.enabled:
            raise RegistryError(f"skill {name} is disabled")
        if not item.approved:
            raise RegistryError(f"skill {name}@{item.version} is untrusted and not approved")
        return self._ref(item)

    # selection --------------------------------------------------------------
    def select(
        self, capability: str, *, allow_trust: tuple[str, ...] = ("builtin", "local")
    ) -> list[SkillRef]:
        """Enabled, approved, valid skills providing *capability*, best first.

        Ranking: trust (builtin before local before untrusted), then
        deterministic before seeded before stochastic, then name. Keyword
        search is never used to choose a method of record.
        """

        det_rank = {"deterministic": 0, "seeded": 1, "stochastic": 2}
        items = [
            item
            for item in self.listings()
            if capability in item.capabilities
            and item.enabled
            and item.active
            and item.approved
            and not item.problems
            and item.trust in allow_trust
        ]
        refs = [self._ref(item) for item in items]
        refs.sort(key=lambda r: (TRUST_LEVELS.index(r.trust), det_rank[r.manifest.determinism], r.name))
        return refs

    def resolve_dependencies(self, skill: SkillRef) -> list[SkillRef]:
        """Topologically ordered dependencies satisfying every version range."""

        order: list[SkillRef] = []
        visiting: set[str] = set()

        def visit(ref: SkillRef, chain: tuple[str, ...]) -> None:
            for dep, spec in ref.manifest.requires.get("skills", {}).items():
                if dep in chain:
                    raise RegistryError(f"dependency cycle: {' -> '.join(chain + (dep,))}")
                options = [
                    item
                    for item in self.listings()
                    if item.name == dep
                    and item.enabled
                    and item.approved
                    and not item.problems
                    and satisfies(parse_version(item.version), spec)
                ]
                if not options:
                    raise RegistryError(f"{ref.name} needs {dep} {spec}, which is not available")
                best = max(options, key=lambda item: parse_version(item.version))
                chosen = self._ref(best)
                if dep not in visiting:
                    visiting.add(dep)
                    visit(chosen, chain + (dep,))
                    order.append(chosen)

        visit(skill, (skill.name,))
        return order

    # mutation ---------------------------------------------------------------
    def install(self, source_dir: Path, *, trust: str = "local", source: str | None = None) -> str:
        if trust not in ("local", "untrusted"):
            raise RegistryError("only 'local' or 'untrusted' skills can be installed")
        src = load_source(Path(source_dir))
        if src.problems or not src.manifest:
            raise RegistryError("skill does not validate: " + "; ".join(src.problems))
        name, version = src.manifest.name, src.manifest.version
        if any(b.name == name for b in self.builtin()):
            raise RegistryError(f"{name!r} is a built-in skill name and cannot be installed over")
        index = self._read_index()
        entry = index["installed"].get(name)
        if entry and version in entry["versions"]:
            if entry["versions"][version]["content_hash"] == src.content_hash:
                return f"{name}@{version} is already installed with identical content"
            raise RegistryError(
                f"{name}@{version} is already installed with different content; bump the version to upgrade"
            )
        version_dir = self._version_dir(name, version)
        if version_dir.exists():
            raise RegistryError(f"{version_dir} exists but is not in the index; refusing to overwrite it")
        target = self._skill_dir(name, version)
        target.parent.mkdir(parents=True)
        shutil.copytree(src.path, target, ignore=shutil.ignore_patterns("__pycache__"))
        copied = tree_hash(target)
        if copied != src.content_hash:
            shutil.rmtree(version_dir)
            raise RegistryError("copied files do not match the source hash (source changed during install?)")
        entry = index["installed"].setdefault(name, {"active": None, "versions": {}})
        entry["versions"][version] = {
            "content_hash": copied,
            "trust": trust,
            "source": source or str(Path(source_dir).resolve()),
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "approved": trust != "untrusted",
        }
        if entry["active"] is None:
            entry["active"] = version
        self._write_index(index)
        return f"installed {name}@{version} ({trust})"

    def approve(self, name: str, version: str, hash_prefix: str) -> str:
        index = self._read_index()
        meta = index["installed"].get(name, {}).get("versions", {}).get(version)
        if meta is None:
            raise RegistryError(f"{name}@{version} is not installed")
        digest = meta["content_hash"].split(":", 1)[1]
        if len(hash_prefix) < 8 or not digest.startswith(hash_prefix.lower()):
            raise RegistryError(
                "give at least the first 8 hex digits of the skill's content hash to approve it"
            )
        meta["approved"] = True
        self._write_index(index)
        return f"approved {name}@{version} pinned to {meta['content_hash']}"

    def set_enabled(self, name: str, enabled: bool) -> str:
        if not any(item.name == name for item in self.listings()):
            raise RegistryError(f"no skill named {name!r}")
        index = self._read_index()
        disabled = set(index["disabled"])
        (disabled.discard if enabled else disabled.add)(name)
        index["disabled"] = sorted(disabled)
        self._write_index(index)
        return f"{'enabled' if enabled else 'disabled'} {name}"

    def upgrade(
        self, source_dir: Path, *, check: Callable[[SkillRef], list[str]] | None = None, trust: str = "local"
    ) -> str:
        """Install a newer version, run *check* on it, then make it active."""

        src = load_source(Path(source_dir))
        if not src.manifest:
            raise RegistryError("skill does not validate: " + "; ".join(src.problems))
        name, version = src.manifest.name, src.manifest.version
        index = self._read_index()
        entry = index["installed"].get(name)
        if not entry:
            raise RegistryError(f"{name} is not installed; use install")
        if parse_version(version) <= parse_version(entry["active"]):
            raise RegistryError(f"{version} is not newer than the active version {entry['active']}")
        message = self.install(source_dir, trust=trust)
        if check is not None:
            problems = check(
                self.get(name, version)
                if trust != "untrusted"
                else self._ref(next(i for i in self.listings() if i.name == name and i.version == version))
            )
            if problems:
                return f"{message}; NOT activated because its examples failed: {'; '.join(problems)}"
        index = self._read_index()
        index["installed"][name]["active"] = version
        self._write_index(index)
        return f"{message}; active version is now {version} (previous versions kept)"

    def remove(
        self, name: str, version: str, *, referenced: Callable[[str], bool] | None = None, force: bool = False
    ) -> str:
        index = self._read_index()
        entry = index["installed"].get(name)
        if not entry or version not in entry["versions"]:
            raise RegistryError(
                f"{name}@{version} is not installed (built-in skills cannot be removed; disable them)"
            )
        content_hash = entry["versions"][version]["content_hash"]
        if referenced and referenced(content_hash) and not force:
            raise RegistryError(
                f"{name}@{version} is cited by ledger records; pass force to move it to the trash anyway"
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        trash = self.root / "trash" / stamp / name / version
        trash.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self._version_dir(name, version)), str(trash))
        del entry["versions"][version]
        if not entry["versions"]:
            del index["installed"][name]
        elif entry["active"] == version:
            entry["active"] = format_version(max(parse_version(v) for v in entry["versions"]))
        self._write_index(index)
        return f"moved {name}@{version} to {trash}"
