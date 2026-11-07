"""Unwrap one explicitly selected nested tar/zip member with a provenance chain.

Many firmware containers package an inner root filesystem separately. Nothing
is auto-detected beyond recognised open archive formats, and no archive member
is executed. Both extraction stages use the existing path/cap checks.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..canonical import sha256_file
from .errors import IngestError, UnsupportedInput
from .ingest import ingest, tree_manifest, tree_manifest_digest


def unpack_member(source: Path, member: str, destination: Path) -> dict:
    """Extract a selected supported inner archive into a *fresh* destination.

    Returns a content-addressed provenance manifest. Archive bytes are never
    committed to the repository or interpreted as executable instructions.
    """

    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise IngestError(f"destination must not exist: {destination}")
    if source.is_dir() and destination.is_relative_to(source):
        raise IngestError("destination must be outside the source firmware tree")
    if (
        not member
        or member.startswith("/")
        or "\\" in member
        or any(part in ("", ".", "..") for part in member.split("/"))
    ):
        raise IngestError("member must be a canonical relative POSIX path")
    with tempfile.TemporaryDirectory(prefix="blackglass-outer-") as temporary:
        outer = ingest(source, Path(temporary) / "outer")
        available = dict(outer.iter_files())
        payload = available.get(member)
        if payload is None:
            raise IngestError(f"nested member not found as a regular file: {member}")
        import tarfile
        import zipfile

        if not tarfile.is_tarfile(payload) and not zipfile.is_zipfile(payload):
            raise UnsupportedInput(
                f"{member} is not a supported tar/zip archive; use a documented "
                "external extractor and then analyse its output directory"
            )
        outer_digest = outer.source_digest or tree_manifest_digest(outer)
        payload_digest = sha256_file(payload)
        destination.mkdir(parents=True)
        inner = ingest(payload, destination)
        manifest = {
            "schema": "blackglass.nested-provenance/v1",
            "source_name": source.name,
            "outer_digest": outer_digest,
            "member": member,
            "member_sha256": payload_digest,
            "inner_format": inner.source_kind,
            "tree_manifest_sha256": tree_manifest_digest(inner),
            "file_count": len(tree_manifest(inner)),
            "output": "root",
            "attestation": (
                "SHA-256 observations only. Official origin and publisher signatures "
                "are not independently authenticated."
            ),
        }
        (destination / "provenance.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return manifest
