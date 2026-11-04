"""Record kinds, evidence categories and the rules ``Ledger.verify`` enforces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..canonical import canonical_bytes, sha256_bytes

if TYPE_CHECKING:
    from .store import Entry, Ledger

CATEGORIES = ("OBSERVED", "COMPUTED", "INTERPRETED")
ORIGINS = ("synthetic", "empirical", "derived", "external")
OUTCOMES = ("corroborated", "contradicted", "inconclusive")
VERDICTS = ("supported", "contradicted", "unresolved")
GENERATIONS = ("scripted", "model", "human")

REQUIRED = {
    "recovery": ("source_log_hash", "discarded_tail_hash", "recovered_records", "reason", "author"),
    "preregistration": (
        "title",
        "question",
        "hypothesis",
        "null_hypothesis",
        "design",
        "acceptance",
        "created_by",
    ),
    "seal": ("label", "commitment"),
    "unseal": ("commitment", "salt", "value", "after"),
    "dataset": ("experiment", "name", "origin", "media_type", "object", "provenance"),
    "run": ("run_id", "skill", "status", "seed", "inputs_hash", "experiment", "role"),
    "claim": ("experiment", "category", "statement", "evidence", "author"),
    "challenge": ("experiment", "target", "method", "evidence", "outcome", "reasoning", "author"),
    "revision": ("supersedes", "reason", "replacement", "author"),
    "approval": ("experiment", "scope", "operator", "attestation", "identity_verified", "digest_prefix"),
    "report": ("experiment", "findings", "limitations", "reproduction", "author"),
    "note": ("experiment", "text", "author"),
    "reproduction": (
        "experiment",
        "original_run",
        "reproduction_run",
        "outputs_match",
        "artifacts_match",
        "author",
    ),
    "verdict": ("experiment", "target", "verdict", "reasons", "evidence", "author"),
}


def _refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def record_problems(ledger: "Ledger", entry: "Entry", record: dict, seq_of: dict[str, int]) -> list[str]:
    """Rules for one record; *seq_of* holds objects appended before *entry*."""

    problems: list[str] = []
    kind = entry.kind
    required = REQUIRED.get(kind)
    if required is None:
        return [f"unknown record kind {kind!r}"]
    missing = [field for field in required if field not in record]
    if missing:
        return [f"missing fields {missing}"]

    def earlier(ref: str, label: str) -> dict | None:
        if ref not in seq_of:
            problems.append(f"{label} {ref} does not precede this record")
            return None
        return ledger.get_json(ref)

    # Object dependencies are distinct from record references: artifacts need
    # not have a log entry, but their bytes must exist and match their address.
    from .store import LedgerError

    def verify_object(ref: str, label: str) -> None:
        try:
            ledger.get_bytes(ref)
        except (LedgerError, OSError) as exc:
            problems.append(f"{label}: {exc}")

    if kind == "dataset":
        verify_object(record["object"], "dataset artifact")
    if kind == "run":
        for field in ("engine_source_object", "skill_source_object", "lockfile_object"):
            if record.get(field):
                verify_object(record[field], field)
        if "inputs_object" in record:
            verify_object(record["inputs_object"], "inputs")
            if record["inputs_object"] != record["inputs_hash"]:
                problems.append("inputs object differs from inputs_hash")

            def check_input(value):
                if isinstance(value, dict):
                    if "$artifact" in value and "sha256" in value:
                        verify_object(value["sha256"], "input artifact")
                    for child in value.values():
                        check_input(child)
                elif isinstance(value, list):
                    for child in value:
                        check_input(child)

            check_input(ledger.get_json(record["inputs_object"]))
        if record.get("sealed", {}).get("public_object"):
            verify_object(record["sealed"]["public_object"], "sealed public inputs")
        for name, meta in record.get("artifacts", {}).items():
            verify_object(meta.get("object", meta["sha256"]), f"artifact {name}")
            if meta.get("object", meta["sha256"]) != meta["sha256"]:
                problems.append(f"artifact {name}: object/hash disagreement")
    if kind == "report":
        if record.get("report_object"):
            verify_object(record["report_object"], "report")
        for formats in record.get("figure_objects", {}).values():
            for ref in formats.values():
                verify_object(ref, "figure")

    if "experiment" in record and kind not in {"preregistration", "seal", "unseal"}:
        prereg = earlier(record["experiment"], "experiment")
        if prereg is not None and "hypothesis" not in prereg:
            problems.append("experiment reference is not a preregistration")

    if kind == "reproduction":
        for key in ("original_run", "reproduction_run"):
            run = earlier(record[key], key)
            if run is not None and "run_id" not in run:
                problems.append(f"{key} is not a run record")

    if kind == "run" and record.get("sealed"):
        commitment = record["sealed"].get("commitment")
        seals = [ledger.get_json(e.object) for e in ledger.entries("seal") if e.object in seq_of]
        if not any(s["commitment"] == commitment for s in seals):
            problems.append("sealed run cites a commitment with no earlier seal")

    if kind == "verdict":
        target = earlier(record["target"], "target")
        if target is not None and "category" not in target:
            problems.append("verdict target is not a claim")
        if record["verdict"] not in VERDICTS:
            problems.append(f"verdict must be one of {VERDICTS}")
        for ref in _refs(record["evidence"]):
            earlier(ref, "evidence")

    if kind in {"claim", "challenge", "note", "report", "revision", "reproduction", "verdict"}:
        author = record["author"]
        if (
            not isinstance(author, dict)
            or author.get("generation") not in GENERATIONS
            or not author.get("role")
        ):
            problems.append("author must give a role and generation (scripted|model|human)")

    if kind == "dataset" and record["origin"] not in ORIGINS:
        problems.append(f"origin must be one of {ORIGINS}")

    if kind == "claim":
        category = record["category"]
        evidence = [earlier(ref, "evidence") for ref in _refs(record["evidence"])]
        evidence = [e for e in evidence if e is not None]
        if category not in CATEGORIES:
            problems.append(f"category must be one of {CATEGORIES}")
        elif category == "COMPUTED":
            if not any(e.get("run_id") and e.get("status") == "ok" for e in evidence):
                problems.append("COMPUTED claims must cite at least one successful run")
        elif category == "OBSERVED":
            if any(e.get("origin") == "synthetic" for e in evidence):
                problems.append("OBSERVED claims may not rest on synthetic data")
            if not any(e.get("origin") == "empirical" or e.get("run_id") for e in evidence):
                problems.append("OBSERVED claims must cite an empirical dataset or a run measurement")
        elif category == "INTERPRETED":
            if not any(e.get("category") in {"COMPUTED", "OBSERVED"} for e in evidence):
                problems.append("INTERPRETED claims must cite at least one COMPUTED or OBSERVED claim")

    if kind == "challenge":
        target = earlier(record["target"], "target")
        if target is not None and "category" not in target:
            problems.append("challenge target is not a claim")
        if record["outcome"] not in OUTCOMES:
            problems.append(f"outcome must be one of {OUTCOMES}")
        for ref in _refs(record["evidence"]):
            earlier(ref, "evidence")

    if kind == "revision":
        earlier(record["supersedes"], "superseded record")
        earlier(record["replacement"], "replacement record")

    if kind == "unseal":
        seals = [ledger.get_json(e.object) for e in ledger.entries("seal") if e.object in seq_of]
        if not any(s["commitment"] == record["commitment"] for s in seals):
            problems.append("unseal has no earlier matching seal")
        recomputed = sha256_bytes(record["salt"].encode("ascii") + canonical_bytes(record["value"]))
        if recomputed != record["commitment"]:
            problems.append("unsealed value does not match the commitment")
        for ref in _refs(record["after"]):
            earlier(ref, "analysis record")

    if kind == "approval":
        if record["identity_verified"] is not False or record["attestation"] != "local-operator":
            problems.append("approvals must be attestation 'local-operator' with identity_verified false")

    if kind == "report":
        for finding in record["findings"]:
            if finding.get("verdict") not in VERDICTS:
                problems.append(f"finding verdict must be one of {VERDICTS}")
            for ref in _refs(finding.get("claims", [])):
                earlier(ref, "finding claim")
    return problems
