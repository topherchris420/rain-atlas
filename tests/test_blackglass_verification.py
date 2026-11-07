"""Integrity (hash-manifest) and signature verification, including honest gaps."""

from __future__ import annotations

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.ingest import ingest
from rain_atlas.blackglass.signing import ed25519_ref as ed
from rain_atlas.blackglass.verification import (
    unverifiable,
    verify_hash_manifest,
    verify_signature,
)
from rain_atlas.canonical import sha256_file


def _manifest(image):
    return {rel: sha256_file(path) for rel, path in image.iter_files()}


def test_hash_manifest_match(tmp_path):
    image = ingest(fixtures.build_image(tmp_path / "fw"))
    result = verify_hash_manifest(image, _manifest(image))
    assert result.status == "verified"


def test_hash_manifest_detects_tamper_and_missing(tmp_path):
    image = ingest(fixtures.build_image(tmp_path / "fw"))
    manifest = _manifest(image)
    manifest["usr/sbin/httpd"] = "sha256:" + "0" * 64  # wrong digest
    manifest["ghost/file"] = "sha256:" + "1" * 64  # not present
    result = verify_hash_manifest(image, manifest)
    assert result.status == "failed"
    assert "mismatched" in result.detail and "missing" in result.detail


def test_signature_valid_and_invalid(tmp_path):
    payload = tmp_path / "update.bin"
    payload.write_bytes(b"firmware update metadata")
    seed = bytes(range(32))
    pub = ed.public_key(seed)
    sig = ed.sign(seed, payload.read_bytes())
    good = verify_signature(payload, sig, pub, algorithm="ed25519")
    assert good.status == "verified"
    bad = verify_signature(payload, bytes(64), pub, algorithm="ed25519")
    assert bad.status == "failed"


def test_unsupported_algorithm_without_backend(tmp_path):
    payload = tmp_path / "u.bin"
    payload.write_bytes(b"x")
    # rsa-pss requires the optional cryptography backend; absent it is 'unsupported',
    # never a false 'verified'.
    from rain_atlas.blackglass.signing import has_cryptography

    result = verify_signature(payload, b"sig", b"key", algorithm="rsa-pss")
    assert result.status in ({"failed", "verified"} if has_cryptography() else {"unsupported"})
    assert verify_signature(payload, b"sig", b"key", algorithm="made-up").status == "unsupported"


def test_unverifiable_without_anchor():
    result = unverifiable("image", "no trust anchor supplied")
    assert result.status == "unverifiable" and result.method == "none"
