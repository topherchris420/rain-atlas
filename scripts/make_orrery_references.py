"""Run the ORRERY GMAT reference scenarios and commit their trajectories.

Usage::

    uv run python scripts/make_orrery_references.py --gmat-root PATH/TO/GMAT [--only S4-leo-j2 ...]

For each ``truth == "gmat"`` scenario this generates a GMAT script, runs
``GmatConsole --run``, parses the ReportFile and writes a reference record to
``src/rain_atlas/orrery/reference/gmat-R2026a/<scenario>.json`` (script text,
executable and data-file hashes, console build date, and the reported
trajectory). These committed records are what the test suite compares against,
so GMAT is needed only to regenerate them.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rain_atlas.orrery import gmat, scenarios  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--gmat-root", required=True, type=Path)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--workdir", type=Path, default=None)
    args = parser.parse_args()
    names = args.only or scenarios.GMAT_SCENARIOS
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="orrery-gmat-"))
    print(f"work directory: {workdir}")
    for name in names:
        scenario = scenarios.scenario(name)
        bodies = scenarios.gmat_body_positions(scenario)
        print(f"running {name} ({scenario['title']})...", flush=True)
        record = gmat.run(scenario, args.gmat_root, workdir / name, bodies)
        path = gmat.write_reference(record)
        rows = len(record["rows"])
        print(f"  {rows} report rows, {record['run']['wall_seconds']} s -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
