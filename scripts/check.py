"""Run required developer checks with the current uv-managed interpreter.

Type checks also run once per Python version in the CI matrix, each in a
throwaway environment built from the lockfile. The lock resolves different
NumPy/SciPy releases per Python version (NumPy 2.4 on 3.11, 2.5 on 3.12+) and
their type stubs differ, so passing on one interpreter does not imply passing
on another.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Keep in sync with the test matrix in .github/workflows/ci.yml.
CI_PYTHONS = ("3.11", "3.12", "3.13")


def _run(args: list[str]) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("uv is required on PATH: https://docs.astral.sh/uv/")
    _run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
    _run([sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"])
    for version in CI_PYTHONS:
        _run([uv, "run", "--isolated", "--locked", "--python", version, "mypy"])
    _run([sys.executable, "-m", "rain_atlas.cli", "skills", "validate", "skills"])
    _run([sys.executable, "-m", "pytest", *sys.argv[1:]])


if __name__ == "__main__":
    main()
