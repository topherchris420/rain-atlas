"""Record a BLACK GLASS analysis into an ATLAS evidence ledger.

BLACK GLASS adds **no new record kinds**: an analysis is written with the
existing ``preregistration`` → ``dataset`` → ``run`` → ``claim`` → ``challenge``
→ ``verdict`` → ``report`` vocabulary, so ``atlas ledger verify`` checks it with
the same rules as any experiment and the existing observatory renders it with no
changes. Each finding becomes a COMPUTED claim citing the recorded analysis run;
its independent cross-check becomes a challenge; and the pair resolves to a
verdict:

* ``supported`` — the statement is ``verified`` and its cross-check corroborated;
* ``contradicted`` — the cross-check contradicted it;
* ``unresolved`` — a static inference, an inconclusive cross-check, or an
  unverifiable integrity/signature result.

The full, canonically-ordered analysis (every component, edge and piece of
evidence) is stored as a content-addressed JSON artifact the run points to, so
the ledger stays legible while nothing is lost.
"""

from __future__ import annotations

import platform
from dataclasses import asdict

from .. import __version__ as atlas_version
from ..ledger.store import Ledger
from ..provenance import engine_root, source_snapshot
from . import PROTOCOL
from .analyze import ENGINE_VERSION
from .model import AnalysisReport

_ROLE_ANALYST = {"role": "firmware-analyst", "generation": "scripted"}
_ROLE_SKEPTIC = {"role": "firmware-skeptic", "generation": "scripted"}
_ROLE_PI = {"role": "principal-investigator", "generation": "scripted"}


def _verdict_for(confidence: str, crosscheck: dict | None) -> tuple[str, list[str]]:
    outcome = (crosscheck or {}).get("outcome")
    if outcome == "contradicted":
        return "contradicted", ["cross-check contradicted the statement"]
    if confidence == "verified" and outcome == "corroborated":
        return "supported", ["verified fact; independent cross-check corroborated"]
    reasons = [f"confidence={confidence}"]
    if outcome:
        reasons.append(f"cross-check {outcome}")
    return "unresolved", reasons


def record_analysis(
    ledger: Ledger,
    report: AnalysisReport,
    *,
    title: str | None = None,
    max_claims: int | None = None,
) -> dict:
    """Append *report* to *ledger* and return the created record references."""

    data = asdict(report)
    label = report.image["label"]

    prereg = ledger.append(
        "preregistration",
        {
            "title": title or f"BLACK GLASS static analysis of {label}",
            "question": "What software, services, dependencies, network surface and integrity can be "
            "established statically from this firmware image, and with what confidence?",
            "hypothesis": "Static evidence (ELF metadata, init definitions, configuration, operator trust "
            "anchors) supports a reproducible model of the image; capability inferences remain inferences.",
            "null_hypothesis": "No reproducible structural model can be recovered from the image.",
            "design": {
                "protocol": PROTOCOL,
                "engine_version": report.engine_version,
                "parameters": report.parameters,
                "pipeline": ["ingest", "inventory", "services", "graph", "network", "verification"],
                "confidence_levels": ["verified", "high", "medium", "low", "unverifiable"],
            },
            "acceptance": [
                "every finding carries evidence and an independent cross-check",
                "integrity/signature results are verified, failed, unsupported or unverifiable — never assumed",
                "the ledger verifies and each artifact is content-addressed",
                "the analysis is reproducible: identical inputs yield an identical analysis object",
            ],
            "created_by": _ROLE_ANALYST,
        },
    )
    exp = prereg.object

    # dataset: a verifiable manifest of the image's files (the raw evidence).
    manifest = {
        "label": label,
        "source_kind": report.image["source_kind"],
        "source_digest": report.image["source_digest"],
        "tree_manifest_sha256": report.image["tree_manifest_sha256"],
        "files": [[c.path, c.sha256, c.size] for c in report.components],
    }
    manifest_ref = ledger.put_json(manifest)
    ledger.append(
        "dataset",
        {
            "experiment": exp,
            "name": f"firmware image {label}",
            "origin": "external",
            "media_type": "application/vnd.blackglass.tree+json",
            "object": manifest_ref,
            "provenance": {
                "protocol": PROTOCOL,
                "source_kind": report.image["source_kind"],
                "source_digest": report.image["source_digest"],
                "engine_version": report.engine_version,
                "note": "operator-supplied firmware analysed offline and read-only",
            },
        },
    )

    # run: the deterministic in-process analysis pass. Provenance ties it to the
    # exact engine source, exactly as a sandboxed skill run would.
    engine_bytes, engine_hash = source_snapshot(engine_root())
    engine_object = ledger.put_bytes(engine_bytes)
    analysis_object = ledger.put_json(data)
    inputs = {"image": report.image, "parameters": report.parameters, "protocol": PROTOCOL}
    inputs_object = ledger.put_json(inputs)
    run_record = {
        "run_id": f"blackglass-{analysis_object[7:19]}",
        "skill": {
            "name": "blackglass-analyze",
            "version": report.engine_version,
            "content_hash": engine_hash,
        },
        "status": "ok",
        "seed": 0,
        "inputs_hash": inputs_object,
        "inputs_object": inputs_object,
        "experiment": exp,
        "role": "experimental-engineer",
        "purpose": "deterministic static firmware analysis",
        "executor": "blackglass-inprocess (read-only; no firmware code executed)",
        "determinism": "deterministic",
        "wall_s": 0.0,
        "environment": {
            "python": platform.python_version(),
            "os": platform.system(),
            "packages": {"rain-atlas": atlas_version, "blackglass": ENGINE_VERSION},
            "atlas_source_hash": engine_hash,
        },
        "engine_source_object": engine_object,
        "engine_source_hash": engine_hash,
        "artifacts": {
            "analysis.json": {
                "sha256": analysis_object,
                "object": analysis_object,
                "media_type": "application/json",
            }
        },
    }
    lockfile = engine_root().parents[1] / "uv.lock"
    if lockfile.is_file():
        run_record["lockfile_object"] = ledger.put_file(lockfile)
    run_entry = ledger.append("run", run_record)
    run_ref = run_entry.object

    findings = report.findings if max_claims is None else report.findings[:max_claims]
    report_findings = []
    claim_refs = []
    for f in findings:
        claim = ledger.append(
            "claim",
            {
                "experiment": exp,
                "category": "COMPUTED",
                "statement": f.statement,
                "label": f.id,
                "finding_kind": f.kind,
                "subject": f.subject,
                "confidence": f.confidence,
                "method": "blackglass-analyze",
                "finding_evidence": [asdict(e) for e in f.evidence],
                "assumptions": f.assumptions,
                "analysis_object": analysis_object,
                "evidence": [run_ref],
                "author": _ROLE_ANALYST,
            },
        )
        challenge_ref = None
        if f.crosscheck:
            challenge = ledger.append(
                "challenge",
                {
                    "experiment": exp,
                    "target": claim.object,
                    "method": f.crosscheck["method"],
                    "evidence": [run_ref],
                    "outcome": f.crosscheck["outcome"],
                    "reasoning": f.crosscheck["detail"],
                    "author": _ROLE_SKEPTIC,
                },
            )
            challenge_ref = challenge.object
        decision, reasons = _verdict_for(f.confidence, f.crosscheck)
        evidence = [run_ref] + ([challenge_ref] if challenge_ref else [])
        ledger.append(
            "verdict",
            {
                "experiment": exp,
                "target": claim.object,
                "verdict": decision,
                "reasons": reasons,
                "evidence": evidence,
                "rule": "supported iff verified and cross-check corroborated; contradicted iff cross-check "
                "contradicted; otherwise unresolved",
                "author": _ROLE_PI,
            },
        )
        claim_refs.append(claim.object)
        report_findings.append(
            {
                "claim": claim.object,
                "claims": [claim.object],
                "verdict": decision,
                "finding": f.id,
                "kind": f.kind,
                "confidence": f.confidence,
                "statement": f.statement,
            }
        )

    report_entry = ledger.append(
        "report",
        {
            "experiment": exp,
            "findings": report_findings,
            "limitations": report.limitations,
            "reproduction": {
                "protocol": PROTOCOL,
                "engine_version": report.engine_version,
                "engine_source_hash": engine_hash,
                "tree_manifest_sha256": report.image["tree_manifest_sha256"],
                "source_digest": report.image["source_digest"],
            },
            "conclusion": (
                f"{sum(r['verdict'] == 'supported' for r in report_findings)} supported, "
                f"{sum(r['verdict'] == 'unresolved' for r in report_findings)} unresolved, "
                f"{sum(r['verdict'] == 'contradicted' for r in report_findings)} contradicted "
                f"across {len(report_findings)} findings."
            ),
            "analysis_object": analysis_object,
            "author": _ROLE_PI,
        },
    )

    problems = ledger.verify()
    return {
        "experiment": exp,
        "dataset": manifest_ref,
        "run": run_ref,
        "analysis_object": analysis_object,
        "claims": claim_refs,
        "report": report_entry.object,
        "findings": report_findings,
        "problems": problems,
    }
