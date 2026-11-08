"""Behavioural reconstruction model for BLACK GLASS native analysis.

The firmware-metadata pipeline (`analyze.py`) answers *what is in the image*.
This module answers *what a native routine does*, and it does so with four
provenance levels, each a strictly stronger claim than the last. The level is
recorded on every statement so a reader never mistakes an interpretation for a
fact:

* **observed** — a fact read straight from the binary by a disassembler or
  decompiler (REA/Ghidra), re-checkable by re-running the same tool on the same
  hash-bound ELF. Example: "the function at 0x4011a0 calls ``strtol`` and
  references the format string ``%d``." A tool observation, not runtime truth.
* **reconstructed** — an analyst's model of *what the routine does*, inferred
  from the observed disassembly. An interpretation, open to challenge.
* **implemented** — an original, clean-room re-implementation of the
  reconstructed behaviour. No decompiled source is copied; the implementation is
  written from the behavioural specification. It is executable and testable.
* **validated** — the implementation reproduces a *reference* behaviour on
  concrete vectors. The reference is a public standard, the behaviour contract of
  the GPL source the vendor shipped, or input/output pairs derived during
  analysis — never the output of executing the proprietary binary. Disagreements
  are recorded, never hidden.

Decompiled proprietary source is **evidence held locally**; only its digest and
non-copyrightable *derived facts* (names, addresses, sizes, call targets,
referenced library symbols, string references, control-flow metrics) enter the
model and the ledger. The clean-room implementation and the test vectors are
original work and are the only executable parts committed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .model import Evidence

# Strongest claim last; the index is the ordinal strength.
PROVENANCE = ("observed", "reconstructed", "implemented", "validated")

# Kinds of fact a disassembler/decompiler can assert about a routine. Each is a
# non-copyrightable observation about the binary, not a copy of its code.
FACT_KINDS = (
    "call",  # calls a named function / library symbol
    "import-symbol",  # references an imported dynamic symbol
    "string-ref",  # references a string literal (recorded by content or digest)
    "constant",  # uses a notable immediate constant
    "syscall",  # issues a named syscall
    "cfg-metric",  # a control-flow metric (basic blocks, loops, branches)
    "stack-frame",  # frame size / argument count as recovered
    "signature",  # a recognised library/compiler signature (e.g. FLIRT/known-func)
)

VECTOR_SOURCES = ("standard", "gpl-source", "derived")


@dataclass(frozen=True)
class ObservedFact:
    """One re-checkable disassembler observation about a routine."""

    kind: str  # one of FACT_KINDS
    detail: str  # human-readable specifics, e.g. "calls strtol"
    address: str | None = None  # hex locus within the routine, when applicable
    target: str | None = None  # call/import target name, when applicable

    def __post_init__(self) -> None:
        if self.kind not in FACT_KINDS:
            raise ValueError(f"fact kind must be one of {FACT_KINDS}")


@dataclass(frozen=True)
class RoutineObservation:
    """Observed-level facts about one native routine, bound to the exact ELF.

    ``decompilation_sha256`` is the digest of the local decompiled text; the text
    itself is **not** stored here (it is proprietary evidence kept offline). The
    facts are what a second analyst could independently re-derive from the same
    bytes with the same tool.
    """

    binary: str  # relative POSIX path within the firmware tree
    binary_sha256: str  # sha256:<hex> of the ELF the observation is bound to
    entry: str  # hex entry address of the routine
    name: str  # recovered or assigned name
    size: int  # routine size in bytes, as recovered
    architecture: str  # e.g. "x86-64", "aarch64"
    tool: str  # "rea/ghidra", "rea/decompiler", "ghidra-headless", ...
    tool_version: str
    settings: str  # analysis settings that affect recovery (recorded, not trusted)
    facts: tuple[ObservedFact, ...] = ()
    decompilation_sha256: str | None = None  # digest of the local decompiled text
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.binary_sha256.startswith("sha256:"):
            raise ValueError("binary_sha256 must be a 'sha256:<hex>' digest")

    def call_targets(self) -> frozenset[str]:
        return frozenset(f.target for f in self.facts if f.kind in ("call", "import-symbol") and f.target)

    @staticmethod
    def from_dict(data: dict) -> "RoutineObservation":
        return RoutineObservation(
            binary=data["binary"],
            binary_sha256=data["binary_sha256"],
            entry=data["entry"],
            name=data["name"],
            size=int(data["size"]),
            architecture=data["architecture"],
            tool=data["tool"],
            tool_version=data["tool_version"],
            settings=data.get("settings", ""),
            facts=tuple(
                ObservedFact(f["kind"], f["detail"], f.get("address"), f.get("target"))
                for f in data.get("facts", ())
            ),
            decompilation_sha256=data.get("decompilation_sha256"),
            notes=data.get("notes", ""),
        )

    @staticmethod
    def load(path: Path) -> "RoutineObservation":
        return RoutineObservation.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return {
            "binary": self.binary,
            "binary_sha256": self.binary_sha256,
            "entry": self.entry,
            "name": self.name,
            "size": self.size,
            "architecture": self.architecture,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "settings": self.settings,
            "facts": [
                {
                    k: v
                    for k, v in (
                        ("kind", f.kind),
                        ("detail", f.detail),
                        ("address", f.address),
                        ("target", f.target),
                    )
                    if v is not None
                }
                for f in self.facts
            ],
            "decompilation_sha256": self.decompilation_sha256,
            "notes": self.notes,
        }

    def evidence(self) -> Evidence:
        """An observed-level evidence item pointing back at the bytes."""

        return Evidence(
            locus=f"{self.binary}:{self.entry} ({self.name})",
            method=f"{self.tool} {self.tool_version} [{self.settings}]",
            detail=f"{len(self.facts)} recovered facts; size {self.size} B; {self.architecture}",
            confidence="high",  # a tool observation is re-checkable but not runtime truth
            component=self.binary,
            sha256=self.binary_sha256,
        )


@dataclass(frozen=True)
class BehaviorSpec:
    """A reconstructed-level model of what a routine does. An interpretation."""

    name: str
    summary: str
    inputs: str  # prose or typed description of the inputs
    outputs: str  # prose or typed description of the outputs
    steps: tuple[str, ...]  # the reconstructed algorithm, step by step
    preconditions: tuple[str, ...] = ()
    references: tuple[str, ...] = ()  # standard / GPL source the reconstruction leans on
    relies_on_calls: tuple[str, ...] = ()  # library calls the behaviour depends on
    # Binary evidence the reconstruction *predicts* the routine must exhibit. The
    # comparison laboratory checks these against the observation: a reconstruction
    # of MD5 predicts its sine-table constants; of base64, its alphabet. A match is
    # independent corroboration that the bytes really do implement the claimed
    # algorithm; a miss contradicts the reconstruction.
    expects_constants: tuple[str, ...] = ()  # e.g. ("0xd76aa478",)
    expects_strings: tuple[str, ...] = ()  # substrings expected among referenced literals
    provenance: str = "reconstructed"


@dataclass(frozen=True)
class BehaviorVector:
    """One input/expected-output pair with a stated reference source."""

    name: str
    arguments: dict
    expected: object
    source: str  # one of VECTOR_SOURCES
    note: str = ""

    def __post_init__(self) -> None:
        if self.source not in VECTOR_SOURCES:
            raise ValueError(f"vector source must be one of {VECTOR_SOURCES}")


@dataclass(frozen=True)
class ReconstructedRoutine:
    """Bundles the four levels for one routine: observation, spec, model, vectors.

    ``model`` is the clean-room implementation — a pure function from an argument
    dict to a result. It is original code written from ``spec``; it never copies
    decompiled source.
    """

    observation: RoutineObservation
    spec: BehaviorSpec
    model: Callable[..., object]
    vectors: tuple[BehaviorVector, ...]


@dataclass(frozen=True)
class VectorOutcome:
    name: str
    source: str
    passed: bool
    expected: object
    actual: object


@dataclass(frozen=True)
class ValidationResult:
    """Validated-level result: the implementation against its reference vectors."""

    routine: str
    binary: str
    binary_sha256: str
    outcomes: tuple[VectorOutcome, ...]
    behaviour_consistent: bool  # every relied-on call is present in the observation
    consistency_detail: str

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def validated(self) -> bool:
        return self.total > 0 and self.passed == self.total and self.behaviour_consistent

    def crosscheck(self) -> dict:
        """Map to the ledger's cross-check vocabulary (corroborated/contradicted/inconclusive)."""

        if self.total == 0:
            outcome = "inconclusive"
        elif self.passed == self.total and self.behaviour_consistent:
            outcome = "corroborated"
        elif self.passed < self.total:
            outcome = "contradicted"
        else:
            outcome = "inconclusive"
        return {
            "method": "clean-room behaviour model vs reference vectors + observation consistency",
            "outcome": outcome,
            "detail": f"{self.passed}/{self.total} vectors; {self.consistency_detail}",
        }
