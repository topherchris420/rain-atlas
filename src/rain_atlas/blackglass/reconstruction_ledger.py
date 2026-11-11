"""Record a BLACK GLASS behavioural reconstruction into an ATLAS ledger.

Like the firmware-analysis bridge, this adds **no new record kinds**. Each
routine becomes a COMPUTED claim citing the recorded reconstruction run; the
comparison laboratory's evidence cross-check becomes a challenge; and the pair
resolves to a verdict under an explicit, honest rule:

* ``supported`` — the clean-room model reproduces every reference vector **and**
  the binary exhibits the algorithm's predicted defining evidence (constants /
  alphabet). The claim is scoped to *static* identity and a *validated model*;
  runtime behaviour is never executed and is recorded as a limitation.
* ``contradicted`` — the predicted evidence is absent, or a vector fails.
* ``unresolved`` — nothing was predicted to check, or the check was inconclusive.
"""

from __future__ import annotations

import platform

from .. import __version__ as atlas_version
from ..ledger.store import Ledger
from ..provenance import engine_root, source_snapshot
from . import PROTOCOL
from .analyze import ENGINE_VERSION
from .behavior import validate
from .comparison import compare_spec_to_observation
from .routines import ReconstructedRoutine

_ROLE_ANALYST = {"role": "firmware-analyst", "generation": "scripted"}
_ROLE_SKEPTIC = {"role": "firmware-skeptic", "generation": "scripted"}
_ROLE_PI = {"role": "principal-investigator", "generation": "scripted"}

LIMITATIONS = [
    "The proprietary binary is never executed; runtime behaviour is not observed. Claims are scoped to the "
    "statically recovered structure and to a clean-room model validated against the public standard.",
    "The reconstruction is an interpretation of disassembly/decompilation; a different analyst or tool version "
    "could recover a different structure. The decompiled text is held locally and referenced only by digest.",
    "Reference vectors come from the published standard, not from the binary; agreement shows the model matches "
    "the standard, and the observed constants show the binary exhibits that standard's defining values.",
    "Evidence consistency binds a reconstruction to the exact ELF by hash; it does not prove the routine is "
    "reached at runtime or that indirect control flow was fully recovered.",
]


def _verdict_for(crosscheck: dict, vectors_passed: bool, vectors_total: int) -> tuple[str, list[str]]:
    outcome = crosscheck.get("outcome")
    if outcome == "contradicted" or (vectors_total and not vectors_passed):
        return "contradicted", [
            f"predicted evidence {outcome}" if outcome == "contradicted" else "a reference vector failed"
        ]
    if outcome == "corroborated" and vectors_passed and vectors_total:
        return "supported", [
            "clean-room model reproduced every reference vector",
            "binary exhibits the standard's predicted defining evidence",
            "scope: static identity + validated model; runtime not executed",
        ]
    return "unresolved", [f"evidence cross-check {outcome}", f"vectors passed={vectors_passed}"]


def record_reconstruction(
    ledger: Ledger,
    routines: list[ReconstructedRoutine],
    *,
    title: str | None = None,
) -> dict:
    """Append a behavioural reconstruction of one binary's routines to *ledger*."""

    if not routines:
        raise ValueError("no routines to record")
    binary = routines[0].observation.binary
    binary_sha = routines[0].observation.binary_sha256
    arch = routines[0].observation.architecture

    prereg = ledger.append(
        "preregistration",
        {
            "title": title or f"BLACK GLASS behavioural reconstruction of {binary}",
            "question": "What do selected native routines in this binary do, and does a clean-room model of "
            "each reproduce the public standard while the binary exhibits that standard's defining evidence?",
            "hypothesis": "Each routine's static structure and constants identify a known standard algorithm; "
            "a validated clean-room model reproduces it. Runtime behaviour is not claimed.",
            "null_hypothesis": "The routines cannot be identified, or the models disagree with the standard.",
            "design": {
                "protocol": PROTOCOL,
                "binary": binary,
                "binary_sha256": binary_sha,
                "architecture": arch,
                "provenance_levels": ["observed", "reconstructed", "implemented", "validated"],
                "routines": [r.spec.name for r in routines],
                "decision": "supported iff the clean-room model reproduces every reference vector and the "
                "binary exhibits the predicted constants/alphabet; contradicted on a missing prediction or a "
                "failed vector; scope is static identity plus a validated model, never executed runtime.",
            },
            "acceptance": [
                "every routine carries observed facts bound to the ELF by hash",
                "every claim is scoped to static identity and a validated clean-room model",
                "runtime behaviour is listed as a limitation, never asserted",
                "the ledger verifies and the reconstruction is content-addressed",
            ],
            "created_by": _ROLE_ANALYST,
        },
    )
    exp = prereg.object

    observations = {
        r.spec.name: {
            "observation": r.observation.to_dict(),
            "spec": {
                "summary": r.spec.summary,
                "steps": list(r.spec.steps),
                "references": list(r.spec.references),
                "expects_constants": list(r.spec.expects_constants),
                "expects_strings": list(r.spec.expects_strings),
            },
        }
        for r in routines
    }
    recon_object = ledger.put_json({"binary": binary, "binary_sha256": binary_sha, "routines": observations})

    engine_bytes, engine_hash = source_snapshot(engine_root())
    engine_object = ledger.put_bytes(engine_bytes)
    run_entry = ledger.append(
        "run",
        {
            "run_id": f"blackglass-recon-{recon_object[7:19]}",
            "skill": {
                "name": "blackglass-reconstruct",
                "version": ENGINE_VERSION,
                "content_hash": engine_hash,
            },
            "status": "ok",
            "seed": 0,
            "inputs_hash": recon_object,
            "inputs_object": recon_object,
            "experiment": exp,
            "role": "experimental-engineer",
            "purpose": "clean-room behavioural reconstruction and validation",
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
                "reconstruction.json": {
                    "sha256": recon_object,
                    "object": recon_object,
                    "media_type": "application/json",
                }
            },
        },
    )
    run_ref = run_entry.object

    report_findings = []
    claim_refs = []
    for r in routines:
        result = validate(r)
        crosscheck = compare_spec_to_observation(r.spec, r.observation)
        decision, reasons = _verdict_for(crosscheck, result.validated, result.total)
        claim = ledger.append(
            "claim",
            {
                "experiment": exp,
                "category": "COMPUTED",
                "statement": f"The routine '{r.observation.name}' at {r.observation.entry} in {binary} "
                f"statically exhibits the defining evidence of {r.spec.name.upper()} ({', '.join(r.spec.references)}); "
                f"a clean-room model reproduces {result.passed}/{result.total} published vectors. "
                "Runtime behaviour is not executed.",
                "label": f"recon:{r.spec.name}",
                "finding_kind": "native-call",
                "subject": f"{binary}:{r.observation.entry}",
                "confidence": "high",
                "method": "clean-room reconstruction + evidence cross-check",
                "finding_evidence": [
                    {
                        "locus": r.observation.evidence().locus,
                        "method": r.observation.evidence().method,
                        "detail": r.observation.evidence().detail,
                        "confidence": "high",
                        "component": binary,
                        "sha256": binary_sha,
                    }
                ],
                "observed_facts": [
                    {"kind": f.kind, "detail": f.detail, "target": f.target} for f in r.observation.facts
                ],
                "decompilation_sha256": r.observation.decompilation_sha256,
                "vectors": [
                    {"name": o.name, "source": o.source, "passed": o.passed} for o in result.outcomes
                ],
                "reconstruction_object": recon_object,
                "evidence": [run_ref],
                "author": _ROLE_ANALYST,
            },
        )
        challenge = ledger.append(
            "challenge",
            {
                "experiment": exp,
                "target": claim.object,
                "method": crosscheck["method"],
                "evidence": [run_ref],
                "outcome": crosscheck["outcome"],
                "reasoning": crosscheck["detail"],
                "author": _ROLE_SKEPTIC,
            },
        )
        ledger.append(
            "verdict",
            {
                "experiment": exp,
                "target": claim.object,
                "verdict": decision,
                "reasons": reasons,
                "evidence": [run_ref, challenge.object],
                "rule": "supported iff clean-room model reproduces every vector and the binary exhibits the "
                "predicted defining evidence; contradicted on a missing prediction or failed vector; scope is "
                "static identity plus validated model, never executed runtime",
                "author": _ROLE_PI,
            },
        )
        claim_refs.append(claim.object)
        report_findings.append(
            {
                "claim": claim.object,
                "claims": [claim.object],
                "verdict": decision,
                "routine": r.spec.name,
                "entry": r.observation.entry,
                "vectors": f"{result.passed}/{result.total}",
                "evidence_consistent": result.behaviour_consistent,
            }
        )

    report_entry = ledger.append(
        "report",
        {
            "experiment": exp,
            "findings": report_findings,
            "limitations": LIMITATIONS,
            "reproduction": {
                "protocol": PROTOCOL,
                "engine_version": ENGINE_VERSION,
                "engine_source_hash": engine_hash,
                "binary": binary,
                "binary_sha256": binary_sha,
            },
            "conclusion": (
                f"{sum(r['verdict'] == 'supported' for r in report_findings)} supported, "
                f"{sum(r['verdict'] == 'unresolved' for r in report_findings)} unresolved, "
                f"{sum(r['verdict'] == 'contradicted' for r in report_findings)} contradicted "
                f"across {len(report_findings)} reconstructed routines (static identity + validated models; "
                "runtime not executed)."
            ),
            "reconstruction_object": recon_object,
            "author": _ROLE_PI,
        },
    )

    return {
        "experiment": exp,
        "run": run_ref,
        "reconstruction_object": recon_object,
        "claims": claim_refs,
        "report": report_entry.object,
        "findings": report_findings,
        "problems": ledger.verify(),
    }
