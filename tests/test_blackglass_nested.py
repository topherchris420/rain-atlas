"""Real tar-within-tar extraction and malicious-container negative controls."""

from __future__ import annotations

import io
import json
import tarfile

import pytest

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.analyze import analyze
from rain_atlas.blackglass.errors import IngestError, UnsupportedInput
from rain_atlas.blackglass.ingest import ingest
from rain_atlas.blackglass.nested import unpack_member
from rain_atlas.cli import main


def _archives(tmp_path):
    root = fixtures.build_image(tmp_path / "example-root")
    nested = fixtures.pack_tar(root, tmp_path / "hda1.tgz")
    outer = tmp_path / "example.pat"
    with tarfile.open(outer, "w") as tar:
        tar.add(nested, arcname="hda1.tgz")
    return outer, root


def test_nested_pat_style_container_is_usable_for_full_analysis(tmp_path):
    outer, _ = _archives(tmp_path)
    output = tmp_path / "unpacked"
    manifest = unpack_member(outer, "hda1.tgz", output)
    assert manifest["schema"] == "blackglass.nested-provenance/v1"
    assert manifest["outer_digest"].startswith("sha256:")
    assert manifest["member_sha256"].startswith("sha256:")
    assert manifest["file_count"] > 0
    assert manifest["attestation"].startswith("SHA-256 observations only")
    assert json.loads((output / "provenance.json").read_text()) == manifest
    report = analyze(ingest(output / "root"))
    assert any(c.path == "usr/sbin/httpd" and c.kind == "elf" for c in report.components)


def test_nested_command_reports_provenance(tmp_path, capsys):
    outer, _ = _archives(tmp_path)
    output = tmp_path / "expanded"
    assert main(["firmware", "unpack", str(outer), "--member", "hda1.tgz",
                 "--out", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["output"] == "root"
    assert (output / "root" / "usr" / "sbin" / "httpd").is_file()


def test_nested_fails_closed_on_nonarchives_and_repeated_outputs(tmp_path):
    outer, _ = _archives(tmp_path)
    with pytest.raises(IngestError, match="not found"):
        unpack_member(outer, "missing.tgz", tmp_path / "nope")
    with pytest.raises(IngestError, match="canonical relative"):
        unpack_member(outer, "../hda1.tgz", tmp_path / "out2")
    with pytest.raises(IngestError, match="destination must not exist"):
        unpack_member(outer, "hda1.tgz", tmp_path)
    # A named payload is not assumed to be an archive solely from its suffix.
    with tarfile.open(tmp_path / "not-archive.pat", "w") as tar:
        info = tarfile.TarInfo("hda1.tgz")
        payload = b"encrypted-or-opaque"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(UnsupportedInput):
        unpack_member(tmp_path / "not-archive.pat", "hda1.tgz", tmp_path / "bad")


def test_inner_archive_traversal_is_rejected(tmp_path):
    root = tmp_path / "payload.tar"
    with tarfile.open(root, "w") as tar:
        info = tarfile.TarInfo("../../escape")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    outer = tmp_path / "outer.tar"
    with tarfile.open(outer, "w") as tar:
        tar.add(root, arcname="hda1.tgz")
    with pytest.raises(IngestError, match="escapes the root"):
        unpack_member(outer, "hda1.tgz", tmp_path / "out")
    assert not (tmp_path / "escape").exists()
