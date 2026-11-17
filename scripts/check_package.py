"""Build the distribution and prove the installed wheel works outside the checkout.

A source checkout hides packaging mistakes: the code finds ``skills/``,
data files and the lockfile next to it. This check builds the sdist and
wheel, installs the wheel into a fresh virtual environment, and runs the
CLI from an unrelated directory, so anything the wheel forgot fails here.

Usage: ``uv run python scripts/check_package.py [--dist DIR]`` (needs ``uv``
on PATH). With ``--dist`` it checks already-built distributions instead of
building, so a release publishes exactly the files that were checked.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_SKILLS = 31


def run(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    print("+", " ".join(args), flush=True)
    result = subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, help="check these built distributions instead of building")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="atlas-package-") as tmp:
        work = Path(tmp)
        if args.dist:
            dist = args.dist.resolve()
        else:
            dist = work / "dist"
            run("uv", "build", "--out-dir", str(dist), cwd=ROOT)
        assert len(list(dist.glob("rain_atlas-*.tar.gz"))) == 1, f"expected one sdist in {dist}"
        wheel = next(dist.glob("rain_atlas-*.whl"))
        names = zipfile.ZipFile(wheel).namelist()
        manifests = [
            n for n in names if n.startswith("rain_atlas/builtin_skills/") and n.endswith("skill.json")
        ]
        assert len(manifests) >= MIN_SKILLS, f"wheel carries {len(manifests)} skills, expected {MIN_SKILLS}"
        assert not [n for n in names if "__pycache__" in n], "wheel contains bytecode caches"
        for required in (
            "rain_atlas/observatory/viewer.html",
            "rain_atlas/orrery/data/de421_2026.json",
            "rain_atlas/memory/vendor/mem0/LICENSE",
        ):
            assert required in names, f"wheel is missing {required}"
        # PyPI rejects or mis-renders bad metadata; check it exactly as PyPI will.
        run("uvx", "twine", "check", "--strict", *(str(p) for p in sorted(dist.glob("rain_atlas-*"))))
        metadata = zipfile.ZipFile(wheel).read(f"{wheel.name.split('-py3')[0]}.dist-info/METADATA").decode()
        description = metadata.split("\n\n", 1)[1]
        assert re.search(r"\]\((?!https?://|#|mailto:)[^)\s]+\)", description) is None, (
            "PyPI description still has relative links"
        )

        venv = work / "venv"
        run("uv", "venv", "--quiet", str(venv))
        env = {**os.environ, "VIRTUAL_ENV": str(venv)}
        env.pop("ATLAS_BUILTIN_SKILLS", None)
        run("uv", "pip", "install", "--quiet", str(wheel), env=env)
        bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
        atlas = str(bindir / ("atlas.exe" if sys.platform == "win32" else "atlas"))
        outside = work / "outside"
        outside.mkdir()
        env["ATLAS_HOME"] = str(work / "home")

        print(run(atlas, "--version", cwd=outside, env=env).strip())
        listed = [line for line in run(atlas, "skills", "list", cwd=outside, env=env).splitlines() if line]
        assert len(listed) >= MIN_SKILLS, f"installed atlas lists {len(listed)} skills"
        run(atlas, "skills", "test", cwd=outside, env=env)
        run(atlas, "rain", "slice", "--root", str(outside / "slice"), cwd=outside, env=env)
        run(atlas, "ledger", "verify", str(outside / "slice" / "ledger"), cwd=outside, env=env)
        print(f"ok: {wheel.name} installs and runs outside the checkout ({len(listed)} skills)")


if __name__ == "__main__":
    main()
