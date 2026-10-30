"""Describe the compute environment a run used (recorded with every run)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from .. import __version__

TRACKED_PACKAGES = ("numpy", "scipy", "matplotlib")


def _git_commit(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    if out.returncode != 0 or not commit:
        return None
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, timeout=10, check=False,
    ).stdout.strip()
    return commit + ("-dirty" if dirty else "")


@lru_cache(maxsize=1)
def describe() -> dict:
    packages = {}
    for name in TRACKED_PACKAGES:
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    repo_root = Path(__file__).resolve().parents[3]
    return {
        "atlas_version": __version__,
        "atlas_commit": _git_commit(repo_root),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "interpreter_machine": platform.machine(),
        "os": platform.platform(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "packages": packages,
        "accelerator": None,
        "accelerator_note": "CPU execution; no accelerator backend was requested",
        "executable": sys.executable,
    }
