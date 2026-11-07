"""Generate BLACK GLASS demonstration fixtures (no compiler or network needed).

Writes two synthetic firmware images and their tar archives, a hash-manifest
trust baseline, and an Ed25519 key pair with a detached signature over the v1
archive. Everything is deterministic and self-generated, so it is freely
redistributable and the reproducible demonstration never depends on proprietary
firmware. Run with::

    uv run python scripts/make_blackglass_fixtures.py --out atlas-data/bg-fixtures
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rain_atlas.blackglass import fixtures
from rain_atlas.blackglass.signing import ed25519_ref
from rain_atlas.canonical import sha256_file

# A fixed seed keeps the demo key stable across runs. This is a DEMO key only;
# it signs nothing but the generated fixtures and is published with them.
DEMO_SEED = hashlib.sha256(b"blackglass-demonstration-signing-key/v1").digest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BLACK GLASS demo fixtures")
    parser.add_argument("--out", default="atlas-data/bg-fixtures")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    v1 = fixtures.build_image(out / "fw-v1", variant="v1")
    v2 = fixtures.build_image(out / "fw-v2", variant="v2")
    tar1 = fixtures.pack_tar(v1, out / "fw-v1.tar.gz")
    tar2 = fixtures.pack_tar(v2, out / "fw-v2.tar.gz")

    # Hash-manifest trust baseline for the v1 image (an operator "known good").
    manifest = {
        "files": {p.relative_to(v1).as_posix(): sha256_file(p) for p in sorted(v1.rglob("*")) if p.is_file()}
    }
    (out / "manifest-v1.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    # Ed25519 key pair + detached signature over the v1 archive.
    public = ed25519_ref.public_key(DEMO_SEED)
    signature = ed25519_ref.sign(DEMO_SEED, tar1.read_bytes())
    (out / "ed25519.pub").write_text(public.hex() + "\n", encoding="utf-8", newline="\n")
    (out / "ed25519.sec").write_text(DEMO_SEED.hex() + "\n", encoding="utf-8", newline="\n")  # demo only
    (out / "fw-v1.tar.gz.sig").write_text(signature.hex() + "\n", encoding="utf-8", newline="\n")

    print(f"wrote fixtures to {out}/")
    for item in (
        "fw-v1",
        "fw-v2",
        "fw-v1.tar.gz",
        "fw-v2.tar.gz",
        "manifest-v1.json",
        "ed25519.pub",
        "fw-v1.tar.gz.sig",
    ):
        print(f"  {item}")
    print(f"v1 archive digest: {sha256_file(tar1)}")
    print(f"v2 archive digest: {sha256_file(tar2)}")
    print(f"ed25519 public key: {public.hex()}")


if __name__ == "__main__":
    main()
