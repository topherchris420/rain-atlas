"""Reconstruct services and the dependency graph from static definitions.

The graph has three kinds of node — services, executables and (unresolved)
external libraries — and typed edges between them: ``requires``/``after``/
``wants`` between services (from init metadata), ``starts`` from a service to
the executable it launches, and ``links`` from an executable to each shared
library it declares via ``DT_NEEDED``. Trust-boundary information (declared run
-as user, setuid bits, privilege transitions) is attached to nodes and edges so
the analyser can reason about where privilege changes hands. Every relationship
is derived from a parsed definition or an ELF dynamic entry, never from running
anything.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from .ingest import FirmwareImage
from .model import Component, Graph, ServiceNode


def _read_text(image: FirmwareImage, rel: str) -> str:
    try:
        return image.read(rel).decode("utf-8", "replace")
    except OSError:  # pragma: no cover
        return ""


def _parse_unit(text: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        sections[current].setdefault(key.strip(), []).append(value.strip())
    return sections


def _exec_target(exec_start: str) -> str | None:
    """Resolve the executable path a command line launches to a component path."""

    for token in exec_start.split():
        token = token.lstrip("-@+!")  # systemd ExecStart prefixes
        if token.startswith("/"):
            return token.lstrip("/")
        if "/" in token:
            return token
    return None


def _component_index(components: list[Component]) -> dict[str, Component]:
    return {c.path: c for c in components}


def _soname_index(components: list[Component]) -> dict[str, str]:
    index: dict[str, str] = {}
    for c in components:
        if c.kind != "elf":
            continue
        name = c.detail.get("soname") or c.path.rsplit("/", 1)[-1]
        index.setdefault(name, c.path)
        index.setdefault(c.path.rsplit("/", 1)[-1], c.path)
    return index


def _enabled(image: FirmwareImage, unit_name: str) -> bool | None:
    for target in image.symlinks.values():
        if target.rsplit("/", 1)[-1] == unit_name:
            return True
    for rel in image.symlinks:
        if rel.endswith(".wants/" + unit_name) or rel.rsplit("/", 1)[-1] == unit_name:
            return True
    return None


def _parse_systemd(image: FirmwareImage, components: list[Component]) -> list[ServiceNode]:
    services = []
    for c in components:
        if not (c.path.endswith(".service") and "systemd" in c.path):
            continue
        text = _read_text(image, c.path)
        unit = _parse_unit(text)
        name = c.path.rsplit("/", 1)[-1]
        service = unit.get("Service", {})
        exec_start = (service.get("ExecStart") or [None])[0]

        def _list(section: str, key: str) -> list[str]:
            return [v for value in unit.get(section, {}).get(key, []) for v in value.split()]

        services.append(
            ServiceNode(
                id=f"systemd:{name}",
                name=name,
                init_system="systemd",
                source=c.path,
                exec_start=exec_start,
                exec_component=_exec_target(exec_start) if exec_start else None,
                user=(service.get("User") or [None])[0],
                enabled=_enabled(image, name),
                requires=_list("Unit", "Requires"),
                after=_list("Unit", "After"),
                wants=_list("Unit", "Wants"),
            )
        )
    return services


_LSB_REQUIRED = re.compile(r"#\s*Required-Start:\s*(.*)")


def _parse_sysv(image: FirmwareImage, components: list[Component]) -> list[ServiceNode]:
    services = []
    for c in components:
        parts = PurePosixPath(c.path).parts
        if not (len(parts) >= 2 and parts[-2] == "init.d" and c.kind == "script"):
            continue
        text = _read_text(image, c.path)
        name = c.path.rsplit("/", 1)[-1]
        required: list[str] = []
        exec_start = None
        for line in text.splitlines():
            m = _LSB_REQUIRED.search(line)
            if m:
                required = [t for t in m.group(1).split() if t]
            if exec_start is None:
                hit = re.search(r"(/usr\S*|/s?bin/\S+)", line)
                if hit and not line.strip().startswith("#"):
                    exec_start = hit.group(1)
        services.append(
            ServiceNode(
                id=f"sysv:{name}",
                name=name,
                init_system="sysv",
                source=c.path,
                exec_start=exec_start,
                exec_component=_exec_target(exec_start) if exec_start else None,
                user=None,
                enabled=_enabled(image, name),
                requires=required,
                after=required,
            )
        )
    return services


def _parse_inittab(image: FirmwareImage, components: list[Component]) -> list[ServiceNode]:
    services = []
    for c in components:
        if c.path.rsplit("/", 1)[-1] != "inittab":
            continue
        text = _read_text(image, c.path)
        for idx, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            fields = line.split(":")
            if len(fields) < 4:
                continue
            command = fields[3].strip()
            if not command:
                continue
            services.append(
                ServiceNode(
                    id=f"inittab:{idx}",
                    name=command.split()[0].rsplit("/", 1)[-1],
                    init_system="busybox-inittab",
                    source=c.path,
                    exec_start=command,
                    exec_component=_exec_target(command),
                )
            )
    return services


def parse_services(image: FirmwareImage, components: list[Component]) -> list[ServiceNode]:
    services = (
        _parse_systemd(image, components) + _parse_sysv(image, components) + _parse_inittab(image, components)
    )
    services.sort(key=lambda s: s.id)
    return services


def build_graph(components: list[Component], services: list[ServiceNode]) -> Graph:
    graph = Graph()
    by_path = _component_index(components)
    sonames = _soname_index(components)
    service_by_name = {s.name: s for s in services}

    for s in services:
        privileged = s.user in (None, "root")
        graph.add_node(
            s.id,
            s.name,
            "service",
            init=s.init_system,
            user=s.user or "(default)",
            privileged=privileged,
            enabled=s.enabled,
        )

    # service -> service edges
    for s in services:
        for kind, names in (("requires", s.requires), ("after", s.after), ("wants", s.wants)):
            for target in names:
                dep = service_by_name.get(target)
                if dep is not None and dep.id != s.id:
                    graph.add_edge(s.id, dep.id, kind)

    # service -> executable, executable -> library
    def ensure_executable(path: str) -> str:
        node_id = f"exe:{path}"
        comp = by_path.get(path)
        if comp is not None:
            setuid = bool((comp.mode or 0) & 0o4000)
            graph.add_node(
                node_id,
                path,
                "executable",
                present=True,
                setuid=setuid,
                machine=comp.detail.get("machine"),
            )
        else:
            graph.add_node(node_id, path, "executable", present=False)
        return node_id

    for s in services:
        if not s.exec_component:
            continue
        node_id = ensure_executable(s.exec_component)
        comp = by_path.get(s.exec_component)
        graph.add_edge(s.id, node_id, "starts")
        # A non-root service that launches a setuid-root binary crosses a trust
        # boundary: privilege is gained at exec time.
        if comp is not None and (comp.mode or 0) & 0o4000 and s.user not in (None, "root"):
            graph.add_edge(s.id, node_id, "crosses")

    # link every ELF executable to its declared libraries
    for comp in components:
        if comp.kind != "elf" or not comp.detail.get("needed"):
            continue
        src = ensure_executable(comp.path)
        for soname in comp.detail["needed"]:
            target = sonames.get(soname)
            if target is not None:
                graph.add_edge(src, ensure_executable(target), "links")
            else:
                ext = f"lib:{soname}"
                graph.add_node(ext, soname, "external-library", resolved=False)
                graph.add_edge(src, ext, "links")
    return graph
