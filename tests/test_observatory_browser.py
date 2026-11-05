"""The exported observatory in a real browser, with its CSS and CSP active.

The jsdom tests in tests/web strip both, so until these tests a stylesheet
hash mismatch, a layout overflow or a network request could ship unnoticed.
Skipped unless Node.js can load Playwright with an installed Chromium.
"""

import io
import json
import shutil
import subprocess

import pytest
from conftest import REPO
from test_ledger import AUTHOR, ok_run, prereg

from rain_atlas.ledger.store import Ledger
from rain_atlas.observatory.export import export

CHECKER = REPO / "tests" / "web" / "browser-check.cjs"
DEMONSTRATION = REPO / "docs" / "demonstration" / "index.html"


def _browser_available() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    probe = "require('playwright').chromium.launch().then(b => b.close())"
    try:
        return (
            subprocess.run(
                [node, "-e", probe], cwd=CHECKER.parent, capture_output=True, timeout=60
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not _browser_available(), reason="Node.js with Playwright and Chromium required"
)


def _check(index) -> dict:
    out = subprocess.run(
        ["node", str(CHECKER), str(index)], cwd=CHECKER.parent, capture_output=True, text=True, timeout=300
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _png() -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    figure = Figure(figsize=(4, 2.5), dpi=80)
    figure.add_subplot().plot([0, 1, 2], [0, 1, 0])
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()


def test_fresh_export_renders_every_view_offline_at_desktop_and_phone_width(tmp_path, registry):
    ledger = Ledger(tmp_path / "ledger")
    exp = prereg(ledger)
    run = ok_run(ledger, exp)
    claim = ledger.append(
        "claim",
        {
            "experiment": exp,
            "category": "COMPUTED",
            "statement": "Locking at K=1",
            "evidence": [run],
            "author": AUTHOR,
        },
    ).object
    ledger.append(
        "challenge",
        {
            "experiment": exp,
            "target": claim,
            "method": "independent replicate",
            "evidence": [run],
            "outcome": "corroborated",
            "reasoning": "new seeds agree",
            "author": AUTHOR,
        },
    )
    ledger.append(
        "verdict",
        {
            "experiment": exp,
            "target": claim,
            "verdict": "supported",
            "reasons": ["corroborated"],
            "evidence": [run],
            "author": AUTHOR,
        },
    )
    unbroken = "sha256:" + "f" * 600  # regression: raw structured items overflowed the page
    ledger.append(
        "report",
        {
            "experiment": exp,
            "findings": [{"claims": [claim], "verdict": "supported"}],
            "acceptance": [{"id": "A1", "criterion": "controls behave", "passed": True, "detail": unbroken}],
            "negative_results": [
                {"claim": claim, "verdict": "contradicted", "note": unbroken},
                {"opaque": unbroken},
            ],
            "limitations": [unbroken],
            "reproduction": {},
            "figure_objects": {"transition": {"png": ledger.put_bytes(_png())}},
            "author": AUTHOR,
        },
    )
    report = _check(export(ledger.root, tmp_path / "view", registry=registry))
    assert report["problems"] == []
    for viewport in report["viewports"].values():
        assert viewport["network_probe"] == "refused"
        assert viewport["views"]["reports"]["figures"] == [True]


@pytest.mark.skipif(not DEMONSTRATION.is_file(), reason="no published demonstration")
def test_published_demonstration_renders_offline():
    assert _check(DEMONSTRATION)["problems"] == []
