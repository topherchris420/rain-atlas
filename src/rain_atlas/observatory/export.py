"""Export a verified ledger to an offline observatory, without executing code.

This is a derived review view, not a replacement ledger or an authenticity
certificate. Raw inputs, logs, vaults, operators and interpreter paths are
excluded. Scientific free text can itself be sensitive: review before sharing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..ledger.store import Ledger, LedgerError
from ..skills.registry import Registry

FIELDS = {
    "preregistration": (
        "title",
        "question",
        "hypothesis",
        "null_hypothesis",
        "acceptance",
        "design",
        "parent_experiment",
    ),
    "note": ("text", "stage"),
    "dataset": ("name", "origin", "media_type", "object"),
    "run": (
        "run_id",
        "skill",
        "status",
        "seed",
        "inputs_hash",
        "wall_s",
        "peak_memory_mb",
        "peak_memory_note",
        "purpose",
        "engine_source_hash",
        "engine_source_object",
        "skill_source_object",
        "lockfile_object",
    ),
    "claim": ("category", "statement", "value", "unit", "uncertainty", "evidence", "method", "label"),
    "challenge": ("target", "method", "outcome", "reasoning", "evidence"),
    "verdict": ("target", "verdict", "reasons", "evidence", "rule"),
    "reproduction": ("original_run", "reproduction_run", "outputs_match", "artifacts_match"),
    "report": ("findings", "limitations", "acceptance", "negative_results", "conclusion"),
    "revision": ("supersedes", "replacement", "reason"),
    "approval": ("scope", "attestation", "identity_verified"),
    "seal": ("label", "commitment"),
    # Even published truth is deliberately absent from the review projection.
    "unseal": ("commitment", "after"),
}


def _review(value: Any) -> Any:
    """Remove host-specific paths from free text in the derived view only."""
    if isinstance(value, str):
        value = re.sub(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"<>]+", "[local path]", value)
        return re.sub(r"/(?:home|Users|tmp|private|var)/[^\s\"<>]+", "[local path]", value)
    if isinstance(value, list):
        return [_review(v) for v in value]
    if isinstance(value, dict):
        return {
            k: _review(v)
            for k, v in value.items()
            if k not in {"operator", "executable", "prompt", "token", "password", "api_key", "salt"}
        }
    return value


def snapshot(ledger: Ledger, registry: Registry | None = None) -> dict:
    """Construct a field-allowlisted snapshot; refuse broken evidence."""
    problems = ledger.verify()
    if problems:
        raise LedgerError("export refused: " + "; ".join(problems[:8]))
    records = []
    for entry, record in ledger.records():
        experiment = record.get("experiment", record.get("context", {}).get("experiment"))
        if entry.kind == "preregistration":
            experiment = entry.object
        fields = {key: record[key] for key in FIELDS.get(entry.kind, ()) if key in record}
        if entry.kind == "run":
            env = record.get("environment", {})
            fields["environment"] = {
                k: env.get(k) for k in ("python", "os", "packages", "atlas_commit", "atlas_source_hash")
            }
            fields["artifact_hashes"] = {k: v["sha256"] for k, v in record.get("artifacts", {}).items()}
        records.append(
            {
                "id": entry.object,
                "seq": entry.seq,
                "at": entry.at,
                "kind": entry.kind,
                "experiment": experiment,
                "role": record.get("author", {}).get("role", record.get("role")),
                "generation": record.get("author", record.get("created_by", {})).get(
                    "generation", "scripted"
                ),
                "data": _review(fields),
            }
        )
    skills = []
    if registry:
        from ..skills.catalog import load_source

        for item in registry.listings():
            source = load_source(item.path)
            if not source.manifest:
                continue
            manifest = source.manifest
            matching = [
                r
                for r in records
                if r["kind"] == "run" and r["data"]["skill"].get("content_hash") == item.content_hash
            ]
            skills.append(
                {
                    "name": item.name,
                    "version": item.version,
                    "domain": item.domain,
                    "summary": item.summary,
                    "content_hash": item.content_hash,
                    "enabled": item.enabled,
                    "approved": item.approved,
                    "trust": item.trust,
                    "capabilities": list(item.capabilities),
                    "inputs": manifest.inputs,
                    "outputs": manifest.outputs,
                    "permissions": manifest.permissions,
                    "requires": manifest.requires,
                    "limits": manifest.limits,
                    "limitations": list(manifest.limitations),
                    "examples": len(manifest.examples),
                    "validation": "valid" if not item.problems else "invalid",
                    "test_status": "unknown: examples not executed by export",
                    "recorded_runs": len(matching),
                    "successful_runs": sum(r["data"]["status"] == "ok" for r in matching),
                }
            )
    entries = list(ledger.entries())
    return {
        "schema": "atlas.observatory/v1",
        "records": records,
        "skills": _review(skills),
        "source_head": entries[-1].hash if entries else None,
        "snapshot_at": entries[-1].at if entries else None,
        "integrity": "source chain and referenced artifacts verified at export",
        "privacy": "Derived view: raw inputs, logs, vault, operator and host paths omitted. Review scientific free text before sharing.",
        "authenticity": "Hashes establish internal consistency, not external authenticity or scientific truth.",
    }


def export(ledger_path: Path, destination: Path, *, registry: Registry | None = None) -> Path:
    """Write a new directory containing a self-contained HTML review view."""
    ledger_path, destination = Path(ledger_path).resolve(), Path(destination).resolve()
    if not (ledger_path / "log.jsonl").is_file():
        raise ValueError("source is not a ledger (missing log.jsonl)")
    if destination == ledger_path or ledger_path in destination.parents:
        raise ValueError("export must be outside the source ledger")
    if destination.exists():
        raise ValueError("export directory already exists; choose a new snapshot directory")
    ledger = Ledger(ledger_path)
    data = snapshot(ledger, registry)
    # Only recorded PNG figures are previewed. SVG/HTML from arbitrary skills
    # are not active documents in the viewer.
    figures = []
    for entry, record in ledger.records("report"):
        for name, formats in record.get("figure_objects", {}).items():
            if "png" not in formats:
                continue
            raw = ledger.get_bytes(formats["png"])
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 20 * 1024 * 1024:
                raise ValueError("report figure is not a bounded PNG")
            figures.append(
                {
                    "name": str(name),
                    "experiment": record["experiment"],
                    "hash": formats["png"],
                    "url": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                }
            )
    data["figures"] = figures
    directory = Path(__file__).parent
    js = (directory / "viewer.js").read_text(encoding="utf-8")
    css = (directory / "viewer.css").read_text(encoding="utf-8")
    template = (directory / "viewer.html").read_text(encoding="utf-8")
    encoded = (
        json.dumps(data, ensure_ascii=True, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    def digest(content):
        return base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()

    csp = (
        f"default-src 'none'; script-src 'sha256-{digest(js)}'; style-src 'sha256-{digest(css)}'; "
        "img-src data:; connect-src 'none'; font-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"
    )
    # A single substitution pass keeps literal template markers in evidence
    # from being reinterpreted as executable viewer source.
    substitutions = {"CSP": csp, "CSS": css, "DATA": encoded, "JS": js}
    html = re.sub(r"\{\{(CSP|CSS|DATA|JS)\}\}", lambda match: substitutions[match[1]], template)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "index.html").write_text(html, encoding="utf-8", newline="\n")
    (destination / "review-data.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n"
    )
    return destination / "index.html"
