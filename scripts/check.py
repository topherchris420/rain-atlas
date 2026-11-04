"""Run required developer checks with the current uv-managed interpreter."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    for args in [
        ["ruff", "check", "src", "tests", "scripts"],
        ["ruff", "format", "--check", "src", "tests", "scripts"],
        ["mypy"],
        ["rain_atlas.cli", "skills", "validate", "skills"],
        ["pytest"],
    ]:
        subprocess.run([sys.executable, "-m", *args], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
