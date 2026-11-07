"""Safe ingest: archives, traversal defences, caps and unsupported formats."""

from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.errors import IngestError, UnsupportedInput
from rain_atlas.blackglass.ingest import ingest, tree_manifest, tree_manifest_digest


def test_directory_ingest(tmp_path):
    root = fixtures.build_image(tmp_path / "fw", variant="v1")
    image = ingest(root)
    assert image.source_kind == "directory"
    paths = {rel for rel, _ in image.iter_files()}
    assert "usr/sbin/httpd" in paths and "etc/httpd/httpd.conf" in paths


def test_tar_and_zip_ingest(tmp_path):
    root = fixtures.build_image(tmp_path / "fw", variant="v1")
    tar = fixtures.pack_tar(root, tmp_path / "fw.tar.gz")
    image = ingest(tar, tmp_path / "ws-tar")
    assert image.source_kind == "tar" and image.source_digest
    assert image.modes.get("usr/bin/config-helper", 0) & 0o4000  # setuid survives in metadata

    zpath = tmp_path / "fw.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for rel, path in sorted((p.relative_to(root).as_posix(), p) for p in root.rglob("*") if p.is_file()):
            zf.writestr(rel, path.read_bytes())
    zimage = ingest(zpath, tmp_path / "ws-zip")
    assert zimage.source_kind == "zip"
    assert {rel for rel, _ in zimage.iter_files()} == {rel for rel, _ in image.iter_files()}


def test_path_traversal_is_refused(tmp_path):
    bad = tmp_path / "evil.tar"
    with tarfile.open(bad, "w") as tf:
        data = b"pwned"
        info = tarfile.TarInfo("../../escape.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    with pytest.raises(IngestError):
        ingest(bad, tmp_path / "ws")
    assert not (tmp_path / "escape.txt").exists()


def test_symlinks_recorded_not_created(tmp_path):
    arc = tmp_path / "links.tar"
    with tarfile.open(arc, "w") as tf:
        reg = tarfile.TarInfo("etc/real.conf")
        payload = b"Port 80\n"
        reg.size = len(payload)
        tf.addfile(reg, io.BytesIO(payload))
        link = tarfile.TarInfo("etc/link.conf")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../../../etc/passwd"
        tf.addfile(link)
    image = ingest(arc, tmp_path / "ws")
    assert image.symlinks.get("etc/link.conf") == "../../../../etc/passwd"
    assert not (image.root / "etc/link.conf").exists()


def test_entry_size_cap(tmp_path):
    arc = tmp_path / "big.tar"
    with tarfile.open(arc, "w") as tf:
        info = tarfile.TarInfo("big.bin")
        info.size = 4096
        tf.addfile(info, io.BytesIO(b"\x00" * 4096))
    with pytest.raises(IngestError):
        ingest(arc, tmp_path / "ws", max_entry_bytes=1024)


def test_unsupported_container(tmp_path):
    blob = tmp_path / "rootfs.squashfs"
    blob.write_bytes(b"hsqs" + b"\x00" * 512)  # squashfs magic, unsupported here
    with pytest.raises(UnsupportedInput):
        ingest(blob, tmp_path / "ws")


def test_tree_manifest_is_deterministic(tmp_path):
    root = fixtures.build_image(tmp_path / "fw", variant="v1")
    a = ingest(root)
    assert tree_manifest(a) == tree_manifest(ingest(root))
    assert tree_manifest_digest(a).startswith("sha256:")
