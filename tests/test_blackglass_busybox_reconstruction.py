"""End-to-end validation over the committed BusyBox observations.

This needs **no analysis tool at test time**: it reads the committed derived
facts (`reconstruction_data/*.busybox.json`), runs each clean-room model against
its reference vectors, cross-checks the reconstruction's predicted evidence
against the observed facts, and records the whole reconstruction into a fresh
ledger that must verify clean with every routine `supported`.
"""

from __future__ import annotations

import pytest

from rain_atlas.blackglass.behavior import validate
from rain_atlas.blackglass.comparison import compare_spec_to_observation
from rain_atlas.blackglass.reconstructions import available, reconstructed
from rain_atlas.ledger.store import Ledger

BUSYBOX_SHA = "sha256:6e123e7f3202a8c1e9b1f94d8941580a25135382b99e8d3e34fb858bba311348"


@pytest.mark.parametrize("name", available())
def test_committed_routine_validates(name):
    bundle = reconstructed(name)
    # The observation is bound to the exact analysed ELF.
    assert bundle.observation.binary_sha256 == BUSYBOX_SHA
    assert bundle.observation.binary == "bin/busybox"
    # The reconstruction's predicted evidence is present in the binary.
    crosscheck = compare_spec_to_observation(bundle.spec, bundle.observation)
    assert crosscheck["outcome"] == "corroborated", crosscheck
    # The clean-room model reproduces every reference vector, and evidence is consistent.
    result = validate(bundle)
    assert result.validated, [o for o in result.outcomes if not o.passed]
    assert result.total >= 2


def test_reconstruction_records_to_ledger(tmp_path):
    from rain_atlas.blackglass.reconstruction_ledger import record_reconstruction

    ledger = Ledger(tmp_path / "ledger")
    bundles = [reconstructed(n) for n in available()]
    refs = record_reconstruction(ledger, bundles)
    assert refs["problems"] == []
    verdicts = [f["verdict"] for f in refs["findings"]]
    assert verdicts and all(v == "supported" for v in verdicts), verdicts
    # The ledger re-verifies independently.
    assert Ledger(tmp_path / "ledger").verify() == []


def test_md5_and_sha1_are_distinguished_in_the_binary():
    """The fifth IV word is what separates SHA-1 from MD5 in the bytes."""

    md5 = reconstructed("md5").observation
    sha1 = reconstructed("sha1").observation
    md5_consts = {f.target for f in md5.facts if f.kind == "constant"}
    sha1_consts = {f.target for f in sha1.facts if f.kind == "constant"}
    assert "0xc3d2e1f0" in sha1_consts  # SHA-1's H4
    assert "0xc3d2e1f0" not in md5_consts  # absent from MD5 init
