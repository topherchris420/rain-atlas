"""Identify *statically declared* network capabilities, with calibrated confidence.

Three independent kinds of static evidence are collected and kept distinct:

* ``socket-symbol`` — an executable imports socket-API functions (``bind``,
  ``listen``, ``connect`` ...). The import itself is a *verified* fact; the
  inference that the program opens a socket at run time is only ``medium`` (a
  server-shaped pair ``bind`` + ``listen``) or ``low`` (client calls). Linking a
  symbol is not proof it is reached.
* ``port-declared`` — a configuration file names a listening port (``Listen``,
  ``Port`` ...). This is a ``high``-confidence *declaration*, still not a runtime
  observation.
* ``service-port`` — a systemd ``[Socket]`` unit declares ``ListenStream``.

Nothing here asserts that a port is actually open on a running device; BLACK
GLASS has not run the firmware and says so.
"""

from __future__ import annotations

import re

from .ingest import FirmwareImage
from .model import Component, Evidence, NetworkCapability, ServiceNode

# socket-layer imports grouped by the strength of the inference they support
_LISTEN_SYMBOLS = {"bind", "listen", "accept", "accept4"}
_CLIENT_SYMBOLS = {"connect", "getaddrinfo", "gethostbyname", "SSL_connect"}
_IO_SYMBOLS = {"socket", "recv", "recvfrom", "send", "sendto", "sendmsg", "recvmsg", "SSL_new", "SSL_read"}
_ALL_NET = _LISTEN_SYMBOLS | _CLIENT_SYMBOLS | _IO_SYMBOLS

# "Directive <port>" and "key=port" shapes seen across common config dialects
_PORT_PATTERNS = (
    re.compile(r"^\s*Listen(?:Stream|Datagram)?\s*=?\s*(?:[\w.\-:\[\]]*:)?(\d{1,5})\b", re.IGNORECASE),
    re.compile(r"^\s*Port\s*=?\s*(\d{1,5})\b", re.IGNORECASE),
    re.compile(r"^\s*(?:bind|listen)\s+(?:[\w.\-]*:)?(\d{1,5})\b", re.IGNORECASE),
)


def _read_text(image: FirmwareImage, rel: str, cap: int = 1 << 20) -> str:
    try:
        return image.read(rel, cap).decode("utf-8", "replace")
    except OSError:  # pragma: no cover
        return ""


def _symbol_capabilities(components: list[Component]) -> list[NetworkCapability]:
    out: list[NetworkCapability] = []
    for c in components:
        if c.kind != "elf":
            continue
        symbols = set(c.detail.get("imported_symbols") or [])
        hits = sorted(symbols & _ALL_NET)
        if not hits:
            continue
        if not c.detail.get("section_headers_present", True):
            # symbols were unavailable; nothing to infer, and we do not guess
            continue
        listens = bool(symbols & _LISTEN_SYMBOLS)
        confidence = "medium" if listens else "low"
        detail = "imports " + ", ".join(hits)
        out.append(
            NetworkCapability(
                component=c.path,
                kind="socket-symbol",
                detail=detail + ("; bind+listen suggests a server" if listens else "; client-side calls"),
                port=None,
                protocol=None,
                evidence=Evidence(
                    locus="ELF .dynsym (undefined imports)",
                    method="elf.imported_symbols",
                    detail=detail,
                    confidence="verified",
                    component=c.path,
                    sha256=c.sha256,
                ),
                confidence=confidence,
            )
        )
    return out


def _config_ports(image: FirmwareImage, components: list[Component]) -> list[NetworkCapability]:
    out: list[NetworkCapability] = []
    for c in components:
        if c.kind not in ("config", "package-manifest") and not c.path.endswith(
            (".conf", ".service", ".socket")
        ):
            continue
        text = _read_text(image, c.path)
        if not text:
            continue
        is_socket_unit = c.path.endswith(".socket")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("#", ";")):
                continue
            for pattern in _PORT_PATTERNS:
                m = pattern.match(line)
                if not m:
                    continue
                port = int(m.group(1))
                if not 0 < port <= 65535:
                    continue
                out.append(
                    NetworkCapability(
                        component=c.path,
                        kind="service-port" if is_socket_unit else "port-declared",
                        detail=f"declares port {port}: {line.strip()[:80]}",
                        port=port,
                        protocol=None,
                        evidence=Evidence(
                            locus=f"{c.path}:line {lineno}",
                            method="network.port_directive",
                            detail=line.strip()[:120],
                            confidence="verified",
                            component=c.path,
                            sha256=c.sha256,
                        ),
                        confidence="high",
                    )
                )
                break
    return out


def detect_network(
    image: FirmwareImage, components: list[Component], services: list[ServiceNode]
) -> list[NetworkCapability]:
    """Return the statically identified network capabilities, canonically ordered."""

    capabilities = _symbol_capabilities(components) + _config_ports(image, components)
    capabilities.sort(key=lambda n: (n.component, n.kind, n.port or 0, n.detail))
    return capabilities
