"""Read-only intake of Luca observatory summaries into a fresh quarantine.

No paths in imported JSON are opened. No external project state is written.
Shape validation does not authenticate measurements or promote them to evidence.
"""

import json
from pathlib import Path

from ..canonical import sha256_bytes

SOURCE_COMMIT = "cef9276538807043a91e5b4c44c12309ad47d0c7"
RESULT_SCHEMA = "luca.observatory.experiments/1"


def quarantine(source: Path, destination: Path) -> Path:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Luca record exceeds 8 MiB")
    if destination.exists():
        raise ValueError("quarantine destination must be new")
    if source.parent == destination or source.parent in destination.parents:
        raise ValueError("quarantine must be outside the source directory")
    raw = source.read_bytes()
    try:
        data = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        shaped = (
            isinstance(data, dict)
            and data.get("schema") == RESULT_SCHEMA
            and isinstance(data.get("experiments"), dict)
            and data.get("synthetic") is False
            and isinstance(data.get("manifest"), dict)
            and isinstance(data.get("preregistration"), dict)
        )
    except (ValueError, UnicodeError):
        shaped = False
    status = {
        "schema": "atlas.quarantine/v1",
        "status": "quarantined",
        "source_hash": sha256_bytes(raw),
        "adapter_version": "1.0.0",
        "external_source_commit": SOURCE_COMMIT,
        "recognized_shape": shaped,
        "external_schema": RESULT_SCHEMA,
        "reason": "External measurement authenticity and referenced artifacts have not been independently verified; not admitted as scientific evidence.",
        "paths_followed": False,
        "code_executed": False,
    }
    destination.mkdir(parents=True)
    (destination / "record.json.bin").write_bytes(raw)
    (destination / "review.json").write_text(json.dumps(status, indent=2), encoding="utf-8", newline="\n")
    return destination / "review.json"
