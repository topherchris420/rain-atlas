"""Subsystem Reconstruction Engine: validate clean-room behaviour models.

A model is *validated* when (1) it reproduces every reference vector — vectors
drawn from a public standard, the GPL source contract, or analysis-derived
input/output pairs, never from executing the proprietary binary — and (2) the
reconstruction's predicted binary evidence is actually present in the
observation (the comparison-laboratory cross-check). Both must hold; either
failing is recorded, never hidden.
"""

from __future__ import annotations

from .comparison import compare_spec_to_observation
from .routines import ReconstructedRoutine, ValidationResult, VectorOutcome


def run_vectors(reconstructed: ReconstructedRoutine) -> list[VectorOutcome]:
    outcomes: list[VectorOutcome] = []
    for vector in reconstructed.vectors:
        try:
            actual = reconstructed.model(**vector.arguments)
        except Exception as exc:  # a model that raises on a reference input has failed
            actual = f"<raised {type(exc).__name__}: {exc}>"
        outcomes.append(
            VectorOutcome(
                name=vector.name,
                source=vector.source,
                passed=actual == vector.expected,
                expected=vector.expected,
                actual=actual,
            )
        )
    return outcomes


def validate(reconstructed: ReconstructedRoutine) -> ValidationResult:
    outcomes = run_vectors(reconstructed)
    crosscheck = compare_spec_to_observation(reconstructed.spec, reconstructed.observation)
    consistent = crosscheck["outcome"] == "corroborated"
    return ValidationResult(
        routine=reconstructed.spec.name,
        binary=reconstructed.observation.binary,
        binary_sha256=reconstructed.observation.binary_sha256,
        outcomes=tuple(outcomes),
        behaviour_consistent=consistent,
        consistency_detail=crosscheck["detail"],
    )
