"""BLACK GLASS: an offline, read-only firmware static-analysis instrument.

BLACK GLASS imports firmware archives or extracted root filesystems that the
operator is authorised to analyse, builds a reproducible, evidence-linked model
of their software (component inventory, service and library dependency graphs,
statically identifiable network capabilities, integrity and signature
verification against operator-supplied trust anchors, and version diffs), and
records the result into the ATLAS evidence ledger so other researchers can
re-run and challenge every finding.

It is vendor-neutral by construction: it reads structural metadata defined by
open formats (ELF, init/supervision definitions, configuration files) and never
disassembles, decompiles or reconstructs proprietary logic. Every statement it
makes carries evidence (file, digest, locus, method) and a confidence level,
and inferences about *possible* behaviour are never promoted to confirmed
behaviour.
"""

from __future__ import annotations

PROTOCOL = "blackglass.firmware-analysis/v1"

__all__ = ["PROTOCOL"]
