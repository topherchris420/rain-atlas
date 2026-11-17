"""Recursive Engineering & Analysis (REA) replication framework.

Vers3Dynamics research method for investigating reference systems and
independently reconstructing selected capabilities.

The framework is deliberately small and dependency-free. It provides:

* :mod:`rain_atlas.rea.models` -- typed manifests, evidence items, replicas
  and conformance records.
* :mod:`rain_atlas.rea.package` -- building, validating and serialising an
  investigation evidence package.
* :mod:`rain_atlas.rea.conformance` -- a reference-versus-replica test
  harness with structural comparators.
* :mod:`rain_atlas.rea.registry` -- replica registration and integration
  readiness gates.
* :mod:`rain_atlas.rea.investigations` -- the recorded investigations of the
  nine Y Combinator research targets.
"""

from .classification import (
    CLASSIFICATIONS,
    UNKNOWN,
    classification_rules,
    validate_classification,
)
from .conformance import Comparator, ConformanceCase, ConformanceHarness, ConformanceResult
from .models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)
from .package import EvidencePackage, package_problems
from .registry import ReplicaRegistry, registry_problems

__all__ = [
    "CLASSIFICATIONS",
    "Comparator",
    "ConformanceCase",
    "ConformanceHarness",
    "ConformanceRecord",
    "ConformanceResult",
    "EvidenceItem",
    "EvidencePackage",
    "Feature",
    "Investigation",
    "ReplicaRegistry",
    "ReplicaSpec",
    "TargetManifest",
    "UNKNOWN",
    "classification_rules",
    "package_problems",
    "registry_problems",
    "validate_classification",
]
