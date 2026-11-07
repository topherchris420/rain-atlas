"""Typed, JSON-serialisable data model for BLACK GLASS.

The model is deliberately plain: dataclasses whose fields are scalars, lists and
dicts, so :func:`dataclasses.asdict` yields canonical-JSON-safe values that the
ATLAS ledger can content-address without a custom encoder.

Two ideas run through the whole model and are the reason it exists:

* **Evidence.** Nothing is asserted without an :class:`Evidence` item that names
  the file, its digest, the exact locus (section, offset, line) and the method
  used. A reader can go back to the bytes and check.
* **Confidence.** Every statement carries a :data:`CONFIDENCE` level.
  ``verified`` means independently re-checkable (a hash match, a signature, a
  re-parse). ``high``/``medium``/``low`` are *static inferences* about possible
  behaviour. ``unverifiable`` means the evidence to decide was absent. BLACK
  GLASS never promotes an inference to a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ordered strongest-to-weakest; `verified` is the only re-checkable level.
CONFIDENCE = ("verified", "high", "medium", "low", "unverifiable")

COMPONENT_KINDS = (
    "elf",
    "script",
    "shared-object-link",
    "config",
    "package-manifest",
    "key-material",
    "archive",
    "data",
    "unknown",
)

FINDING_KINDS = (
    "component",
    "service",
    "dependency",
    "network",
    "integrity",
    "signature",
    "trust-boundary",
    "difference",
    "native-call",
)

# How a static finding is cross-checked by an independent method. Mirrors the
# ledger's challenge outcomes so the ledger bridge can map them 1:1.
CROSSCHECK_OUTCOMES = ("corroborated", "contradicted", "inconclusive")


@dataclass(frozen=True)
class Evidence:
    """One re-checkable observation underpinning a statement."""

    locus: str  # e.g. "ELF .dynamic", "systemd [Unit] After", "config:line 12"
    method: str  # how it was obtained, e.g. "elf.dynamic_entries"
    detail: str  # human-readable specifics
    confidence: str = "verified"
    component: str | None = None  # relative POSIX path of the subject file
    sha256: str | None = None  # digest of the subject file (sha256:...)
    offset: int | None = None  # byte offset within the file, when applicable

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {CONFIDENCE}")


@dataclass
class Component:
    """One file in the firmware tree, classified with type-specific metadata."""

    path: str  # relative POSIX path from the image root
    size: int
    sha256: str
    kind: str  # one of COMPONENT_KINDS
    mode: int | None = None  # archive/file mode bits (e.g. setuid), when known
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in COMPONENT_KINDS:
            raise ValueError(f"component kind must be one of {COMPONENT_KINDS}")


@dataclass
class ServiceNode:
    """A background service parsed from an init/supervision definition."""

    id: str  # stable id, e.g. "systemd:sshd.service"
    name: str
    init_system: str  # "systemd" | "sysv" | "busybox-inittab" | "procd" | ...
    source: str  # relative POSIX path of the definition file
    exec_start: str | None = None  # raw command line, as written
    exec_component: str | None = None  # resolved component path, if found
    user: str | None = None  # declared run-as user, if any
    enabled: bool | None = None  # start-at-boot, when determinable
    requires: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    wants: list[str] = field(default_factory=list)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # "requires" | "after" | "wants" | "starts" | "links" | "crosses"


@dataclass
class Graph:
    """A directed graph of services, executables and trust boundaries."""

    nodes: list[dict] = field(default_factory=list)  # {id, label, type, attrs}
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node_id: str, label: str, node_type: str, **attrs: object) -> None:
        if not any(n["id"] == node_id for n in self.nodes):
            self.nodes.append({"id": node_id, "label": label, "type": node_type, "attrs": dict(attrs)})

    def add_edge(self, src: str, dst: str, kind: str) -> None:
        if not any(e.src == src and e.dst == dst and e.kind == kind for e in self.edges):
            self.edges.append(Edge(src, dst, kind))


@dataclass
class NetworkCapability:
    """A statically identified network capability — never a runtime observation."""

    component: str  # relative POSIX path
    kind: str  # "socket-symbol" | "port-declared" | "service-port"
    detail: str
    port: int | None
    protocol: str | None
    evidence: Evidence
    confidence: str

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {CONFIDENCE}")


@dataclass
class Finding:
    """A single evidence-linked statement with a confidence and a cross-check."""

    id: str
    kind: str  # one of FINDING_KINDS
    subject: str  # what the finding is about (a path, a service id, "image")
    statement: str
    confidence: str
    evidence: list[Evidence] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    crosscheck: dict | None = None  # {"method", "outcome", "detail"}

    def __post_init__(self) -> None:
        if self.kind not in FINDING_KINDS:
            raise ValueError(f"finding kind must be one of {FINDING_KINDS}")
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {CONFIDENCE}")
        if self.crosscheck is not None and self.crosscheck.get("outcome") not in CROSSCHECK_OUTCOMES:
            raise ValueError(f"crosscheck outcome must be one of {CROSSCHECK_OUTCOMES}")


@dataclass
class VerificationResult:
    """Outcome of an integrity or signature check against a supplied trust anchor."""

    subject: str
    method: str  # "sha256-manifest" | "ed25519" | "rsa-pss" | ...
    status: str  # "verified" | "failed" | "unverifiable" | "unsupported"
    detail: str
    evidence: list[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in ("verified", "failed", "unverifiable", "unsupported"):
            raise ValueError("status must be verified|failed|unverifiable|unsupported")


@dataclass
class AnalysisReport:
    """The complete, deterministic result of analysing one firmware image."""

    engine_version: str
    protocol: str
    image: dict  # {label, source_digest, tree_manifest_sha256, file_count, total_bytes}
    parameters: dict
    components: list[Component] = field(default_factory=list)
    services: list[ServiceNode] = field(default_factory=list)
    graph: Graph = field(default_factory=Graph)
    network: list[NetworkCapability] = field(default_factory=list)
    verification: list[VerificationResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    counts: dict = field(default_factory=dict)


@dataclass
class DiffReport:
    """Noteworthy changes between two analysed firmware images."""

    protocol: str
    engine_version: str
    base_label: str
    target_label: str
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)
    services_added: list[str] = field(default_factory=list)
    services_removed: list[str] = field(default_factory=list)
    network_added: list[dict] = field(default_factory=list)
    network_removed: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
