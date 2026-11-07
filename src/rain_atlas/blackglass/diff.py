"""Detect noteworthy changes between two analysed firmware images.

The diff is computed from two :class:`~rain_atlas.blackglass.model.AnalysisReport`
objects (or their serialised dicts), so it is independent of how either image was
obtained and is fully deterministic. It highlights changes that matter for a
security or systems review: components added, removed or altered (with ELF
dependency deltas), services appearing or disappearing, and new or removed
network surface.
"""

from __future__ import annotations

from dataclasses import asdict

from . import PROTOCOL
from .analyze import ENGINE_VERSION
from .model import AnalysisReport, DiffReport


def _as_dict(report: AnalysisReport | dict) -> dict:
    return report if isinstance(report, dict) else asdict(report)


def _component_index(report: dict) -> dict[str, dict]:
    return {c["path"]: c for c in report["components"]}


def _network_key(n: dict) -> tuple:
    return (n["component"], n["kind"], n.get("port") or 0, n["detail"])


def diff_reports(base: AnalysisReport | dict, target: AnalysisReport | dict) -> DiffReport:
    base_d, target_d = _as_dict(base), _as_dict(target)
    b_comp, t_comp = _component_index(base_d), _component_index(target_d)

    added, removed, changed = [], [], []
    for path in sorted(set(t_comp) - set(b_comp)):
        c = t_comp[path]
        added.append({"path": path, "kind": c["kind"], "sha256": c["sha256"]})
    for path in sorted(set(b_comp) - set(t_comp)):
        c = b_comp[path]
        removed.append({"path": path, "kind": c["kind"], "sha256": c["sha256"]})
    for path in sorted(set(b_comp) & set(t_comp)):
        a, c = b_comp[path], t_comp[path]
        if a["sha256"] == c["sha256"]:
            continue
        entry = {
            "path": path,
            "kind": c["kind"],
            "old_sha256": a["sha256"],
            "new_sha256": c["sha256"],
            "size_delta": c["size"] - a["size"],
        }
        if a["kind"] == "elf" and c["kind"] == "elf":
            old_needed, new_needed = (
                set(a["detail"].get("needed") or []),
                set(c["detail"].get("needed") or []),
            )
            entry["needed_added"] = sorted(new_needed - old_needed)
            entry["needed_removed"] = sorted(old_needed - new_needed)
            old_imp, new_imp = (
                set(a["detail"].get("imported_symbols") or []),
                set(c["detail"].get("imported_symbols") or []),
            )
            entry["imports_added"] = sorted(new_imp - old_imp)
            entry["imports_removed"] = sorted(old_imp - new_imp)
        changed.append(entry)

    b_services = {s["id"] for s in base_d["services"]}
    t_services = {s["id"] for s in target_d["services"]}
    services_added = sorted(t_services - b_services)
    services_removed = sorted(b_services - t_services)

    b_net = {_network_key(n): n for n in base_d["network"]}
    t_net = {_network_key(n): n for n in target_d["network"]}
    network_added = [t_net[k] for k in sorted(set(t_net) - set(b_net))]
    network_removed = [b_net[k] for k in sorted(set(b_net) - set(t_net))]

    notable = []
    new_ports = sorted({n.get("port") for n in network_added if n.get("port")})
    if new_ports:
        notable.append(f"new declared ports: {new_ports}")
    if services_added:
        notable.append(f"new services: {services_added}")
    if services_removed:
        notable.append(f"removed services: {services_removed}")
    new_setuid = sorted(
        set(target_d["counts"].get("setuid_binaries", [])) - set(base_d["counts"].get("setuid_binaries", []))
    )
    if new_setuid:
        notable.append(f"new setuid binaries: {new_setuid}")

    return DiffReport(
        protocol=PROTOCOL,
        engine_version=ENGINE_VERSION,
        base_label=base_d["image"]["label"],
        target_label=target_d["image"]["label"],
        added=added,
        removed=removed,
        changed=changed,
        services_added=services_added,
        services_removed=services_removed,
        network_added=network_added,
        network_removed=network_removed,
        summary={
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "services_added": len(services_added),
            "services_removed": len(services_removed),
            "network_added": len(network_added),
            "network_removed": len(network_removed),
            "notable": notable,
        },
    )
