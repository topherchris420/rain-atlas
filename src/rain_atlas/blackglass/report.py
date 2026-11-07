"""Render an :class:`AnalysisReport` or :class:`DiffReport` as Markdown.

Every statement in the report is traceable: findings carry their confidence, an
evidence locus and the digest of the file the evidence came from, and the
independent cross-check outcome. The reader can go from any line back to the
bytes in the ledger.
"""

from __future__ import annotations

from dataclasses import asdict

from .model import AnalysisReport, DiffReport


def _short(ref: str | None) -> str:
    return "—" if not ref else f"`{ref.split(':', 1)[-1][:12]}`"


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[object]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out


def render_markdown(report: AnalysisReport | dict, *, graph_files: dict | None = None) -> str:
    d = report if isinstance(report, dict) else asdict(report)
    image = d["image"]
    counts = d["counts"]
    lines = [
        f"# BLACK GLASS firmware analysis — {image['label']}",
        "",
        f"Protocol `{d['protocol']}`, engine `{d['engine_version']}`. "
        f"Source {image['source_kind']}, digest {_short(image['source_digest'])}, "
        f"tree manifest {_short(image['tree_manifest_sha256'])}.",
        "",
        "Confidence legend: **verified** = independently re-checkable (hash, signature, re-parse); "
        "**high/medium/low** = static inference about a *possible* capability; "
        "**unverifiable** = evidence to decide was absent. A static analyser never observes runtime behaviour.",
        "",
        "## Inventory",
        "",
        f"{counts['files']} files — "
        + ", ".join(f"{k}: {v}" for k, v in sorted(counts["by_kind"].items()))
        + (f". ELF architectures: {counts['elf_by_machine']}." if counts.get("elf_by_machine") else "."),
        "",
    ]
    if counts.get("setuid_binaries"):
        lines += [f"Setuid binaries: {counts['setuid_binaries']}.", ""]
    if counts.get("unresolved_libraries"):
        lines += [f"Unresolved (external) libraries: {counts['unresolved_libraries']}.", ""]

    lines += ["## Services", ""]
    if d["services"]:
        lines += _table(
            ["service", "init", "runs as", "starts", "requires"],
            [
                [
                    s["name"],
                    s["init_system"],
                    s["user"] or "(default)",
                    s["exec_component"] or "—",
                    ", ".join(s["requires"]) or "—",
                ]
                for s in d["services"]
            ],
        )
    else:
        lines.append("_No service definitions were found._")
    lines.append("")

    lines += ["## Network surface (static)", ""]
    if d["network"]:
        lines += _table(
            ["component", "kind", "port", "confidence", "evidence"],
            [
                [n["component"], n["kind"], n.get("port") or "—", n["confidence"], n["evidence"]["locus"]]
                for n in d["network"]
            ],
        )
    else:
        lines.append("_No statically identifiable network capabilities._")
    lines += ["", "## Integrity & signatures", ""]
    if d["verification"]:
        lines += _table(
            ["subject", "method", "status", "detail"],
            [[v["subject"], v["method"], v["status"], v["detail"]] for v in d["verification"]],
        )
    else:
        lines.append(
            "_No trust anchor supplied; integrity and signatures are **unverifiable** (not 'valid')._"
        )
    lines.append("")

    lines += [
        "## Findings",
        "",
        f"{len(d['findings'])} findings; each links to evidence and a cross-check.",
        "",
    ]
    lines += _table(
        ["id", "kind", "confidence", "statement", "cross-check", "evidence"],
        [
            [
                f["id"],
                f["kind"],
                f["confidence"],
                f["statement"],
                (f["crosscheck"]["outcome"] if f["crosscheck"] else "—"),
                "; ".join(f"{e['locus']} {_short(e.get('sha256'))}" for e in f["evidence"][:2]),
            ]
            for f in d["findings"]
        ],
    )
    lines.append("")

    if graph_files:
        lines += ["## Service / dependency graph", ""]
        for kind, path in sorted(graph_files.items()):
            lines.append(f"- {kind.upper()}: `{path}`")
        lines.append("")

    lines += ["## Limitations", ""] + [f"- {x}" for x in d["limitations"]] + [""]
    lines += [
        "## Reproduce",
        "",
        "```sh",
        f"uv run atlas firmware analyze <image> --root atlas-data/firmware --label {image['label']}",
        "uv run atlas ledger verify atlas-data/firmware/ledger",
        "```",
        "",
        "A hash chain establishes internal integrity, not authenticity or truth. Every finding above can be "
        "re-derived from the recorded image bytes.",
    ]
    return "\n".join(lines) + "\n"


def render_diff_markdown(diff: DiffReport | dict) -> str:
    d = diff if isinstance(diff, dict) else asdict(diff)
    s = d["summary"]
    lines = [
        f"# BLACK GLASS firmware diff — {d['base_label']} → {d['target_label']}",
        "",
        f"Protocol `{d['protocol']}`, engine `{d['engine_version']}`.",
        "",
        f"**{s['added']} added, {s['removed']} removed, {s['changed']} changed** components; "
        f"services +{s['services_added']}/−{s['services_removed']}; "
        f"network +{s['network_added']}/−{s['network_removed']}.",
        "",
    ]
    if s["notable"]:
        lines += ["## Noteworthy", ""] + [f"- {n}" for n in s["notable"]] + [""]
    if d["changed"]:
        lines += ["## Changed components", ""]
        lines += _table(
            ["path", "kind", "size Δ", "imports +", "imports −", "needed +"],
            [
                [
                    c["path"],
                    c["kind"],
                    c.get("size_delta", "—"),
                    ", ".join(c.get("imports_added", [])) or "—",
                    ", ".join(c.get("imports_removed", [])) or "—",
                    ", ".join(c.get("needed_added", [])) or "—",
                ]
                for c in d["changed"]
            ],
        )
        lines.append("")
    for title, key in (("Added components", "added"), ("Removed components", "removed")):
        if d[key]:
            lines += [f"## {title}", ""]
            lines += _table(["path", "kind"], [[c["path"], c["kind"]] for c in d[key]])
            lines.append("")
    if d["network_added"] or d["network_removed"]:
        lines += ["## Network surface changes", ""]
        rows = [["+", n["component"], n["kind"], n.get("port") or "—"] for n in d["network_added"]]
        rows += [["−", n["component"], n["kind"], n.get("port") or "—"] for n in d["network_removed"]]
        lines += _table(["Δ", "component", "kind", "port"], rows)
        lines.append("")
    return "\n".join(lines) + "\n"
