"""The committed ORRERY celestial lab is self-contained, CSP-safe and carries only
engine-computed data. Guards against hand-edited numbers and a broken CSP that
would stop the page rendering offline. Regenerate with
``uv run python scripts/make_orrery_lab.py --gmat``.
"""

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1] / "docs" / "orrery-lab.html"
pytestmark = pytest.mark.skipif(not LAB.exists(), reason="lab not built")


def _html() -> str:
    return LAB.read_text(encoding="utf-8")


def _data(html: str) -> dict:
    raw = re.search(r'<script id="orrery-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    return json.loads(raw.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))


def test_is_lf_only_and_offline():
    html = _html()
    assert "\r" not in html
    assert "connect-src 'none'" in html
    assert "http://" not in html and "https://" not in html


def test_csp_hashes_match_inline_assets():
    html = _html()
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    script = re.search(r"</script><script>(.*?)</script></body>", html, re.S).group(1)

    def digest(text: str) -> str:
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()

    assert f"'sha256-{digest(style)}'" in csp
    assert f"'sha256-{digest(script)}'" in csp


def test_data_is_physical():
    data = _data(_html())
    assert len(data["orbits"]) == 4
    assert len(data["propagators"]["series"]) == 4
    # LEO(400km) -> GEO Hohmann total dv is ~3.9 km/s (Vallado); tof is half the GTO period.
    assert 3.8 < data["transfer"]["total_dv_km_s"] < 3.95
    assert 5.0 < data["transfer"]["tof_hours"] < 5.6
    # If the GMAT drift panel is present, every committed max error is within the experiment tolerance.
    for d in data["drift"]:
        assert d["max_error_m"] < 10.0
        assert len(d["error_m"]) == len(d["hours"])
