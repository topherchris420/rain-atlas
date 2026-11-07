"""Integrity and signature verification against operator-supplied trust anchors.

Two independent checks:

* **Hash-manifest integrity** compares every file against a baseline of expected
  SHA-256 digests the operator provides (a "known-good" manifest). Pure stdlib,
  fully deterministic.
* **Signature verification** checks a detached signature over a file using an
  operator-supplied public key — the genuine trust anchor. Ed25519 works with no
  dependency (via :mod:`.signing.ed25519_ref`); RSA/ECDSA require the optional
  ``cryptography`` backend.

The cardinal rule: with no trust anchor, the result is ``unverifiable``; with an
unsupported algorithm or missing backend, it is ``unsupported``. BLACK GLASS
never reports ``verified`` unless it actually checked a cryptographic fact.
"""

from __future__ import annotations

import binascii
import json
import re
from pathlib import Path

from ..canonical import sha256_bytes, sha256_file
from .ingest import FirmwareImage
from .model import Evidence, VerificationResult
from .signing import ed25519_ref, has_cryptography


def _normalise_digest(value: str) -> str:
    value = value.strip().lower()
    normal = value if value.startswith("sha256:") else "sha256:" + value
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", normal):
        raise ValueError("SHA-256 manifest entries must contain exactly 64 hexadecimal digits")
    return normal


def load_manifest(path: Path) -> dict[str, str]:
    """Load a hash manifest: ``{"files": {path: digest}}`` or a flat mapping."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    files = data.get("files", data) if isinstance(data, dict) else {}
    if not isinstance(files, dict):
        raise ValueError("manifest must be a JSON object of path -> sha256 digest")
    normalised = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not name or name.startswith("/") or ".." in name.split("/"):
            raise ValueError("manifest paths must be non-empty contained POSIX paths")
        normalised[name] = _normalise_digest(str(digest))
    return normalised


def verify_hash_manifest(image: FirmwareImage, manifest: dict[str, str]) -> VerificationResult:
    """Compare the image against an expected-digest baseline."""

    actual = {rel: sha256_file(path) for rel, path in image.iter_files()}
    mismatched: list[str] = []
    missing: list[str] = []
    evidence: list[Evidence] = []
    for rel, expected in sorted(manifest.items()):
        got = actual.get(rel)
        if got is None:
            missing.append(rel)
            evidence.append(
                Evidence("hash-manifest", "verification.sha256", f"{rel}: expected but absent", "high", rel)
            )
        elif got != expected:
            mismatched.append(rel)
            evidence.append(
                Evidence(
                    "hash-manifest",
                    "verification.sha256",
                    f"{rel}: expected {expected[:19]}… got {got[:19]}…",
                    "verified",
                    rel,
                    got,
                )
            )
    extra = sorted(set(actual) - set(manifest))
    complete = bool(manifest) and not extra
    failed = bool(mismatched or missing)
    detail = (
        f"{len(manifest)} baseline entries: {len(manifest) - len(mismatched) - len(missing)} matched, "
        f"{len(mismatched)} mismatched, {len(missing)} missing, {len(extra)} unlisted file(s) present"
        + ("; empty or incomplete baseline cannot attest to the entire image" if not complete else "")
    )
    return VerificationResult(
        subject=image.label,
        method="sha256-manifest",
        status="failed" if failed else "verified" if complete else "unverifiable",
        detail=detail,
        evidence=evidence[:200],
    )


def _load_ed25519_public(path: Path) -> bytes:
    raw = Path(path).read_bytes()
    if len(raw) == 32:
        return raw
    text = raw.decode("utf-8", "replace").strip()
    if text.startswith("-----BEGIN"):
        if not has_cryptography():
            raise ValueError("PEM public key needs the optional 'cryptography' backend")
        from cryptography.hazmat.primitives import serialization  # noqa: PLC0415

        key = serialization.load_pem_public_key(raw)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: PLC0415
            Ed25519PublicKey,
        )

        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("PEM key is not an Ed25519 public key")
        return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    try:
        decoded = binascii.unhexlify("".join(text.split()))
    except binascii.Error as exc:
        raise ValueError(f"unrecognised Ed25519 public key encoding: {exc}") from exc
    if len(decoded) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    return decoded


def _load_signature(path: Path) -> bytes:
    raw = Path(path).read_bytes()
    if len(raw) == 64:
        return raw
    try:
        decoded = binascii.unhexlify("".join(raw.decode("ascii", "replace").split()))
        if len(decoded) == 64:
            return decoded
    except binascii.Error:
        pass
    return raw


def verify_signature(
    target: Path,
    signature: bytes,
    public_key: bytes,
    *,
    algorithm: str = "ed25519",
) -> VerificationResult:
    """Verify a detached signature over *target* under *public_key*."""

    target = Path(target)
    data = target.read_bytes()
    digest = sha256_bytes(data)
    base_evidence = Evidence(
        locus=f"signature over {target.name}",
        method=f"verification.{algorithm}",
        detail=f"target digest {digest[:23]}…, key {sha256_bytes(public_key)[:19]}…",
        confidence="verified",
        sha256=digest,
    )
    algorithm = algorithm.lower()
    if algorithm == "ed25519":
        if has_cryptography():
            ok = _verify_ed25519_cryptography(public_key, data, signature)
            backend = "cryptography"
        else:
            ok = ed25519_ref.verify(public_key, data, signature)
            backend = "ed25519_ref"
        return VerificationResult(
            subject=target.name,
            method=f"ed25519/{backend}",
            status="verified" if ok else "failed",
            detail=("signature valid" if ok else "signature did NOT verify against the supplied key"),
            evidence=[base_evidence],
        )
    if algorithm in ("rsa-pss", "rsa", "ecdsa"):
        if not has_cryptography():
            return VerificationResult(
                subject=target.name,
                method=algorithm,
                status="unsupported",
                detail=f"{algorithm} verification needs the optional 'cryptography' backend",
                evidence=[base_evidence],
            )
        ok = _verify_asymmetric_cryptography(algorithm, public_key, data, signature)
        return VerificationResult(
            subject=target.name,
            method=algorithm,
            status="verified" if ok else "failed",
            detail=("signature valid" if ok else "signature did NOT verify"),
            evidence=[base_evidence],
        )
    return VerificationResult(
        subject=target.name,
        method=algorithm,
        status="unsupported",
        detail=f"unknown signature algorithm {algorithm!r}",
        evidence=[base_evidence],
    )


def _verify_ed25519_cryptography(public_key: bytes, data: bytes, signature: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: PLC0415

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, data)
        return True
    except (InvalidSignature, ValueError):
        return False


def _verify_asymmetric_cryptography(algorithm: str, public_key: bytes, data: bytes, signature: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec, padding  # noqa: PLC0415

    try:
        key = serialization.load_pem_public_key(public_key)
        if algorithm in ("rsa", "rsa-pss"):
            key.verify(
                signature,
                data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        else:
            key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_signature_files(
    target: Path, signature_path: Path, public_key_path: Path, *, algorithm: str = "ed25519"
) -> VerificationResult:
    """Convenience wrapper: load key + signature from files, then verify."""

    public = (
        _load_ed25519_public(public_key_path)
        if algorithm.lower() == "ed25519"
        else Path(public_key_path).read_bytes()
    )
    return verify_signature(target, _load_signature(signature_path), public, algorithm=algorithm)


def unverifiable(subject: str, reason: str) -> VerificationResult:
    """A verification that could not run because no trust anchor was supplied."""

    return VerificationResult(subject=subject, method="none", status="unverifiable", detail=reason)
