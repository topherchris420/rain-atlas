"""End-to-end BLACK GLASS analysis: ingest → analyse → record → observatory.

This is the firmware counterpart of the numerical experiments in
``rain_atlas.experiments``: it runs the pipeline against a fresh ledger, writes
the Markdown report, the graph (DOT + SVG) and the canonical analysis JSON,
exports the offline observatory, and evaluates preregistered acceptance checks —
including an independent reproducibility check that re-ingests the image and
confirms the analysis is byte-identical.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from ..canonical import sha256_json
from ..ledger.store import Ledger
from ..observatory.export import export
from . import PROTOCOL
from .analyze import analyze, render_graphs
from .ingest import ingest
from .ledger_bridge import record_analysis
from .model import VerificationResult
from .report import render_markdown
from .verification import (
    load_manifest,
    unverifiable,
    verify_hash_manifest,
    verify_signature_files,
)


def _collect_verification(image, args: dict) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    manifest_path = args.get("manifest")
    if manifest_path:
        results.append(verify_hash_manifest(image, load_manifest(Path(manifest_path))))
    sig = args.get("signature")
    pub = args.get("public_key")
    target = args.get("signed_target")
    if sig and pub and target:
        results.append(
            verify_signature_files(
                Path(target), Path(sig), Path(pub), algorithm=args.get("algorithm", "ed25519")
            )
        )
    if not results:
        results.append(unverifiable(image.label, "no trust anchor (manifest or signature) supplied"))
    return results


def run(
    source: Path,
    root: Path,
    *,
    label: str | None = None,
    trust: dict | None = None,
    progress: Callable[[str], None] | None = None,
    native_snapshots: list[Path] | None = None,
) -> dict:
    """Analyse *source* into a fresh ledger under *root* and return a summary."""

    source = Path(source)
    root = Path(root).resolve()
    say = progress or (lambda _msg: None)
    ledger = Ledger(root / "ledger")
    if ledger.log_path.exists():
        raise ValueError("root already contains a ledger; use a fresh directory")

    say("stage: ingest")
    image = ingest(source, root / "work", label=label)

    say("stage: verify trust anchors")
    verification = _collect_verification(image, trust or {})

    say("stage: analyse")
    report = analyze(
        image,
        parameters={"source": source.name, "trust": sorted((trust or {}).keys())},
        verification=verification,
        native_snapshots=native_snapshots,
    )

    say("stage: record")
    refs = record_analysis(ledger, report)
    if refs["problems"]:
        raise ValueError("ledger verification failed: " + "; ".join(refs["problems"][:8]))

    # artifacts
    exp12 = refs["experiment"].split(":", 1)[1][:12]
    report_dir = root / "reports" / exp12
    report_dir.mkdir(parents=True, exist_ok=True)
    graphs = render_graphs(report)
    (report_dir / "graph.dot").write_text(graphs["dot"], encoding="utf-8", newline="\n")
    (report_dir / "graph.svg").write_text(graphs["svg"], encoding="utf-8", newline="\n")
    (report_dir / "analysis.json").write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    markdown = render_markdown(report, graph_files={"dot": "graph.dot", "svg": "graph.svg"})
    (report_dir / "report.md").write_text(markdown, encoding="utf-8", newline="\n")

    say("stage: reproducibility check")
    with tempfile.TemporaryDirectory() as tmp:
        repro_image = ingest(source, Path(tmp) / "work", label=label)
        repro_report = analyze(
            repro_image,
            parameters=report.parameters,
            verification=verification,
            native_snapshots=native_snapshots,
        )
        reproducible = sha256_json(asdict(repro_report)) == refs["analysis_object"]

    acceptance = _acceptance(report, refs, reproducible)

    say("stage: observatory")
    observatory = export(root / "ledger", root / "observatory")

    summary = {
        "protocol": PROTOCOL,
        "experiment": refs["experiment"],
        "image": report.image,
        "counts": report.counts,
        "verdicts": {
            v: sum(1 for f in refs["findings"] if f["verdict"] == v)
            for v in ("supported", "unresolved", "contradicted")
        },
        "acceptance": acceptance,
        "report_path": str(report_dir / "report.md"),
        "analysis_path": str(report_dir / "analysis.json"),
        "graph_paths": {"dot": str(report_dir / "graph.dot"), "svg": str(report_dir / "graph.svg")},
        "observatory_path": str(observatory),
        "ledger": str(root / "ledger"),
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    say(summary["counts"].__repr__())
    return summary


def _acceptance(report, refs, reproducible: bool) -> list[dict]:
    findings = report.findings
    network_inferences = [
        f for f in findings if f.kind == "network" and f.subject.endswith(("httpd", "telnetd"))
    ]
    socket_symbol_findings = [f for f in findings if f.kind == "network" and "imports" in f.statement]
    verification_findings = [f for f in findings if f.kind in ("integrity", "signature")]
    return [
        {
            "id": "F1",
            "passed": not refs["problems"],
            "criterion": "ledger verifies: chain, object hashes and record rules",
        },
        {
            "id": "F2",
            "passed": reproducible,
            "criterion": "reproducible: a fresh ingest + analysis is byte-identical to the recorded artifact",
        },
        {
            "id": "F3",
            "passed": all(f.evidence and f.crosscheck for f in findings),
            "criterion": "every finding carries evidence and an independent cross-check",
        },
        {
            "id": "F4",
            "passed": all(f.confidence != "verified" for f in socket_symbol_findings),
            "criterion": "socket-symbol capabilities are inferences (never 'verified')",
            "detail": f"{len(socket_symbol_findings)} socket-symbol finding(s)",
        },
        {
            "id": "F5",
            "passed": bool(verification_findings)
            and all(f.confidence in ("verified", "unverifiable", "low") for f in verification_findings),
            "criterion": "an integrity/signature result is recorded and correctly typed",
        },
        {
            "id": "F6",
            "passed": bool(network_inferences),
            "criterion": "known network-facing daemons in the image are surfaced",
        },
    ]
