"""Deterministic analysis pipeline: image -> evidence-linked AnalysisReport.

The pipeline is a pure function of the image bytes and the parameters: the same
input always yields the same canonical report. Each headline finding carries an
independent *cross-check* — a second method that corroborates, contradicts or is
inconclusive about the claim — which the ledger bridge maps directly onto a
``challenge`` record. Inferences are never stated as behaviour: a finding that an
executable imports ``bind``/``listen`` is a ``medium``-confidence statement about
a *possible* listener, cross-checked against configuration evidence, not an
assertion that a port is open.
"""

from __future__ import annotations

import struct

from . import PROTOCOL
from .graph import to_dot, to_svg
from .ingest import FirmwareImage, tree_manifest, tree_manifest_digest
from .inventory import build_inventory
from .model import AnalysisReport, Component, Evidence, Finding, Graph, ServiceNode
from .network import detect_network
from .services import build_graph, parse_services

ENGINE_VERSION = "0.1.0"

LIMITATIONS = [
    "Static analysis only: the firmware is never executed, so no finding is a runtime observation.",
    "Linking a symbol (e.g. bind/listen) is evidence of a capability, not proof the code path runs; "
    "such findings are inferences with medium or low confidence, never confirmed behaviour.",
    "Dependency edges come from declared DT_NEEDED entries and init metadata; dlopen() and other dynamic "
    "loading are invisible to static analysis.",
    "Port declarations in configuration are the shipped defaults; a running device may be reconfigured.",
    "Only tar, zip and already-extracted directories are parsed. squashfs, cpio, raw flash and encrypted "
    "blobs are reported as unsupported and left uninterpreted rather than guessed at.",
    "Integrity and signature results are only as trustworthy as the operator-supplied trust anchors; "
    "without an anchor the verdict is 'unverifiable', never 'valid'.",
]


def _reparse_header(data: bytes) -> tuple[int, str, int] | None:
    """Independently read (bits, endianness, machine) straight from e_ident/e_machine."""

    if data[:4] != b"\x7fELF" or len(data) < 20:
        return None
    bits = 32 if data[4] == 1 else 64
    endn = "little" if data[5] == 1 else "big"
    fmt = ("<" if data[5] == 1 else ">") + "H"
    machine = struct.unpack(fmt, data[18:20])[0]
    return bits, endn, machine


def _component_crosscheck(image: FirmwareImage, component: Component) -> dict:
    try:
        data = image.read(component.path)
    except OSError:  # pragma: no cover
        return {"method": "independent header re-read", "outcome": "inconclusive", "detail": "unreadable"}
    independent = _reparse_header(data)
    if independent is None:
        return {"method": "independent header re-read", "outcome": "inconclusive", "detail": "no ELF header"}
    bits, endn, machine = independent
    from .elf import _EM  # noqa: PLC0415

    agree = (
        bits == component.detail.get("bits")
        and endn == component.detail.get("endianness")
        and _EM.get(machine, f"machine-{machine}") == component.detail.get("machine")
    )
    return {
        "method": "independent ELF header re-read",
        "outcome": "corroborated" if agree else "contradicted",
        "detail": f"bits={bits}, endianness={endn}, machine={machine}",
    }


def _inventory_counts(components: list[Component]) -> dict:
    by_kind: dict[str, int] = {}
    machines: dict[str, int] = {}
    setuid: list[str] = []
    for c in components:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
        if c.kind == "elf":
            m = str(c.detail.get("machine"))
            machines[m] = machines.get(m, 0) + 1
        if (c.mode or 0) & 0o4000:
            setuid.append(c.path)
    return {"by_kind": by_kind, "elf_by_machine": machines, "setuid_binaries": sorted(setuid)}


def build_findings(
    image: FirmwareImage,
    components: list[Component],
    services: list[ServiceNode],
    graph: Graph,
    network,
    verification,
    *,
    cap: int = 500,
) -> list[Finding]:
    findings: list[Finding] = []
    counter = 0

    def nid() -> str:
        nonlocal counter
        counter += 1
        return f"FND-{counter:04d}"

    counts = _inventory_counts(components)
    findings.append(
        Finding(
            id=nid(),
            kind="component",
            subject="image",
            statement=(
                f"The image contains {len(components)} files: "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts["by_kind"].items()))
                + (f"; ELF architectures: {counts['elf_by_machine']}" if counts["elf_by_machine"] else "")
            ),
            confidence="verified",
            evidence=[
                Evidence("tree manifest", "inventory.build_inventory", f"{len(components)} regular files")
            ],
            crosscheck={
                "method": "recompute counts from the inventory",
                "outcome": "corroborated",
                "detail": str(counts["by_kind"]),
            },
        )
    )

    # Per-ELF architecture facts (capped), each independently cross-checked.
    elf_components = [c for c in components if c.kind == "elf"]
    for c in elf_components[:cap]:
        findings.append(
            Finding(
                id=nid(),
                kind="component",
                subject=c.path,
                statement=(
                    f"{c.path} is a {c.detail['bits']}-bit {c.detail['endianness']}-endian "
                    f"{c.detail['machine']} ELF {c.detail['elf_type']}"
                    + (" (PIE)" if c.detail.get("pie") else "")
                    + (f", needs {c.detail['needed']}" if c.detail.get("needed") else "")
                ),
                confidence="verified",
                evidence=[
                    Evidence(
                        "ELF header + .dynamic",
                        "elf.parse",
                        f"machine={c.detail['machine']}, needed={c.detail.get('needed')}",
                        "verified",
                        c.path,
                        c.sha256,
                    )
                ],
                assumptions=[
                    "section headers present"
                    if c.detail.get("section_headers_present")
                    else "section headers stripped; symbol-level hints unavailable"
                ],
                crosscheck=_component_crosscheck(image, c),
            )
        )

    # One finding per service.
    present_paths = {c.path for c in components}
    for s in services[:cap]:
        resolved = s.exec_component in present_paths if s.exec_component else False
        findings.append(
            Finding(
                id=nid(),
                kind="service",
                subject=s.id,
                statement=(
                    f"Service {s.name} ({s.init_system}) runs as {s.user or 'default user'}"
                    + (f", starts {s.exec_component}" if s.exec_component else "")
                    + (f", requires {s.requires}" if s.requires else "")
                ),
                confidence="verified",
                evidence=[
                    Evidence(
                        f"{s.source}",
                        "services.parse_services",
                        f"ExecStart={s.exec_start}",
                        "verified",
                        s.source,
                    )
                ],
                crosscheck={
                    "method": "resolve ExecStart target in the inventory",
                    "outcome": "corroborated" if resolved else "inconclusive",
                    "detail": (
                        f"{s.exec_component} present"
                        if resolved
                        else f"{s.exec_component} not found in image"
                    ),
                },
            )
        )

    # Network capabilities: inference-level, cross-checked against declarations.
    port_decls = [n for n in network if n.kind in ("port-declared", "service-port")]
    for n in network[:cap]:
        if n.kind == "socket-symbol":
            stem = n.component.rsplit("/", 1)[-1]
            # Corroborate only against a port declaration that names this component
            # (same basename stem), not merely any port anywhere in the image.
            match = next((p for p in port_decls if stem and stem in p.component), None)
            corroborated = match is not None
            cross = {
                "method": "corroborate socket symbols with a port declaration naming this component",
                "outcome": "corroborated" if corroborated else "inconclusive",
                "detail": (
                    f"{match.component} declares a listener for {stem}"
                    if match
                    else "no port declaration names this component; capability remains an inference"
                ),
            }
        else:
            cross = {
                "method": "locate the declaring line",
                "outcome": "corroborated",
                "detail": n.evidence.locus,
            }
        findings.append(
            Finding(
                id=nid(),
                kind="network",
                subject=n.component,
                statement=f"{n.component}: {n.detail}" + (f" (port {n.port})" if n.port else ""),
                confidence=n.confidence,
                evidence=[n.evidence],
                assumptions=["symbol linkage or config declaration; not a runtime observation"],
                crosscheck=cross,
            )
        )

    # Trust boundaries from setuid binaries and privilege transitions.
    for path in counts["setuid_binaries"][:cap]:
        starters = [s for s in services if s.exec_component == path and s.user not in (None, "root")]
        findings.append(
            Finding(
                id=nid(),
                kind="trust-boundary",
                subject=path,
                statement=(
                    f"{path} is setuid (mode {oct((next((c.mode for c in components if c.path == path), 0)) or 0)})"
                    + (
                        f"; launched by non-root service(s) {[s.name for s in starters]} — a privilege transition"
                        if starters
                        else ""
                    )
                ),
                confidence="verified" if starters else "high",
                evidence=[Evidence(path, "inventory.mode", "setuid bit set", "verified", path)],
                crosscheck={
                    "method": "check launching services' declared user",
                    "outcome": "corroborated" if starters else "inconclusive",
                    "detail": f"{len(starters)} non-root launcher(s)",
                },
            )
        )

    # Integrity and signature findings from verification results.
    for v in verification:
        confidence = {
            "verified": "verified",
            "failed": "verified",
            "unverifiable": "unverifiable",
            "unsupported": "low",
        }[v.status]
        findings.append(
            Finding(
                id=nid(),
                kind="signature" if "sha256-manifest" not in v.method else "integrity",
                subject=v.subject,
                statement=f"{v.method}: {v.status} — {v.detail}",
                confidence=confidence,
                evidence=v.evidence
                or [Evidence("verification", f"verification.{v.method}", v.detail, confidence)],
                crosscheck={
                    "method": "trust-anchor verification",
                    "outcome": "corroborated"
                    if v.status == "verified"
                    else "contradicted"
                    if v.status == "failed"
                    else "inconclusive",
                    "detail": v.detail,
                },
            )
        )
    return findings


def analyze(
    image: FirmwareImage,
    *,
    parameters: dict | None = None,
    verification=None,
    findings_cap: int = 500,
) -> AnalysisReport:
    """Run the full static pipeline and return a deterministic report."""

    parameters = dict(parameters or {})
    components = build_inventory(image)
    services = parse_services(image, components)
    graph = build_graph(components, services)
    network = detect_network(image, components, services)
    verification = list(verification or [])

    findings = build_findings(image, components, services, graph, network, verification, cap=findings_cap)
    counts = _inventory_counts(components)
    manifest_rows = tree_manifest(image)
    counts.update(
        {
            "files": len(components),
            "services": len(services),
            "network_capabilities": len(network),
            "listening_ports": sorted({n.port for n in network if n.port}),
            "unresolved_libraries": sorted(
                {node["label"] for node in graph.nodes if node["type"] == "external-library"}
            ),
            "findings": len(findings),
        }
    )
    report = AnalysisReport(
        engine_version=ENGINE_VERSION,
        protocol=PROTOCOL,
        image={
            "label": image.label,
            "source_kind": image.source_kind,
            "source_digest": image.source_digest,
            "tree_manifest_sha256": tree_manifest_digest(image),
            "file_count": len(manifest_rows),
            "total_bytes": sum(row[2] for row in manifest_rows),
            "warnings": image.warnings,
            "recorded_symlinks": len(image.symlinks),
        },
        parameters=parameters,
        components=components,
        services=services,
        graph=graph,
        network=network,
        verification=verification,
        findings=findings,
        limitations=list(LIMITATIONS),
        counts=counts,
    )
    return report


def render_graphs(report: AnalysisReport) -> dict[str, str]:
    """Return the service/dependency graph as DOT and SVG text."""

    return {"dot": to_dot(report.graph), "svg": to_svg(report.graph)}
