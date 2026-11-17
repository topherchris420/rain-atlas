"""The oscillator-bench service twin and its stateful simulation.

The scientific domain reused here is the same one ATLAS already studies:
two coupled oscillators. The twin owns a *hidden* ground truth: which of
two candidate coupling models generates its observations.

* Model ``linear``: coherence ``1 - exp(-3 k)`` at coupling ``k``.
* Model ``damped``: amplitude-dependent damping reduces the effective
  coupling to ``k * (1 - 0.45 * a^2)`` with amplitude ``a = 0.5 + 0.5 k``,
  so coherence flattens at high coupling.

An agent that runs experiments on the twin is *discriminating between the
models*: at high coupling the two models produce measurably different phase
coherence statistics. Each replicate adds Gaussian noise with standard
deviation ``hidden_parameters["observation_sigma"]`` (default 0.06). The twin
is deterministic given (seed, conditions), so experiments are exactly
repeatable.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from ..canonical import canonical_bytes, sha256_bytes

MODELS = ("linear", "damped")
DEFAULT_OBSERVATION_SIGMA = 0.06


class ObservationFault(Exception):
    """Raised when the twin intentionally drops an observation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class FaultProfile:
    """Injected observation faults; deterministic given the twin seed."""

    drop_probability: float = 0.0
    noise_sigma: float = 0.0
    bias: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FaultProfile":
        return cls(**data)


@dataclass
class Scenario:
    """A deterministic starting state for one or more twins."""

    seed: int
    true_model: str  # which model the twin generates data from
    hidden_parameters: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.true_model not in MODELS:
            raise ValueError(f"true_model must be one of {MODELS}")

    def to_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        return sha256_bytes(canonical_bytes(self.to_dict()))


@dataclass
class TwinRun:
    """Captured evidence across one sequence of twin operations."""

    operations: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        operation: str,
        *,
        request: dict[str, Any],
        response: dict[str, Any] | None,
        state_version: int,
        faulted: bool = False,
    ) -> dict[str, Any]:
        entry = {
            "operation": operation,
            "request": request,
            "response": response,
            "state_version": state_version,
            "faulted": faulted,
        }
        self.operations.append(entry)
        return entry

    def to_dict(self) -> dict:
        return {"operations": list(self.operations)}


class ServiceTwin:
    """A stateful twin of an oscillator bench instrument."""

    def __init__(
        self,
        scenario: Scenario,
        *,
        fault_profile: FaultProfile | None = None,
        name: str = "oscillator-bench",
    ) -> None:
        self.name = name
        self.scenario = scenario
        self.fault_profile = fault_profile or FaultProfile()
        self.state_version = 0
        self.run_log = TwinRun()
        self.executed_conditions: list[dict[str, Any]] = []
        self._rng = random.Random(scenario.seed)

    # -- state management -----------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Capture the complete state for later reset (deterministic replay)."""

        return {
            "scenario": self.scenario.to_dict(),
            "fault_profile": self.fault_profile.to_dict(),
            "state_version": self.state_version,
            "executed_conditions": [dict(c) for c in self.executed_conditions],
            "rng_state": self._rng.getstate(),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.scenario = Scenario(**snapshot["scenario"])
        self.fault_profile = FaultProfile.from_dict(snapshot["fault_profile"])
        self.state_version = snapshot["state_version"]
        self.executed_conditions = [dict(c) for c in snapshot["executed_conditions"]]
        self._rng.setstate(snapshot["rng_state"])

    def reset(self) -> None:
        """Reset to the scenario's initial state (fresh replay)."""

        self.state_version = 0
        self.executed_conditions = []
        self.run_log = TwinRun()
        self._rng = random.Random(self.scenario.seed)

    # -- the instrument -------------------------------------------------------

    def run_experiment(self, coupling: float, *, replicates: int = 8) -> dict[str, Any]:
        """Run one condition; returns the observed phase-coherence statistic.

        This is the twin's *provider-compatible endpoint*: same inputs, same
        seed, same output. Observation faults may drop or perturb the result.
        """

        request = {"coupling": coupling, "replicates": replicates}
        coherence = self._simulate(coupling, replicates)
        self.state_version += 1
        self.executed_conditions.append(
            {"coupling": coupling, "replicates": replicates, "coherence": coherence}
        )

        faulted = False
        if self._rng.random() < self.fault_profile.drop_probability:
            entry = self.run_log.record(
                "run_experiment",
                request=request,
                response=None,
                state_version=self.state_version,
                faulted=True,
            )
            raise ObservationFault(f"observation dropped: {entry['request']}")
        if self.fault_profile.noise_sigma > 0:
            coherence += self._rng.gauss(0.0, self.fault_profile.noise_sigma)
            faulted = True
        if self.fault_profile.bias:
            coherence += self.fault_profile.bias
            faulted = True
        response = {"coherence": round(max(0.0, min(1.0, coherence)), 6), "model_hidden": True}
        self.run_log.record(
            "run_experiment",
            request=request,
            response=response,
            state_version=self.state_version,
            faulted=faulted,
        )
        return response

    def _simulate(self, coupling: float, replicates: int) -> float:
        """Deterministic ensemble mean of phase coherence under the true model.

        Linear model: coherence saturates smoothly with coupling.
        Damped model: the nonlinear term reduces effective coupling at high
        amplitude, producing a characteristic flattening.
        """

        sigma = float(self.scenario.hidden_parameters.get("observation_sigma", DEFAULT_OBSERVATION_SIGMA))
        truth = []
        for rep in range(replicates):
            rng = random.Random(f"{self.scenario.seed}:{round(coupling, 6)}:{rep}")
            base = 1.0 - math.exp(-3.0 * coupling)
            if self.scenario.true_model == "damped":
                # amplitude-dependent damping: effective coupling reduced
                amplitude = 0.5 + 0.5 * coupling
                effective = coupling * (1.0 - 0.45 * amplitude * amplitude)
                base = 1.0 - math.exp(-3.0 * effective)
            sample = base + rng.gauss(0.0, sigma)
            truth.append(sample)
        return sum(truth) / len(truth)

    def true_model(self) -> str:
        """Operator-only accessor: hidden ground truth for evaluation."""

        return self.scenario.true_model

    def evidence(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scenario_digest": self.scenario.digest(),
            "state_version": self.state_version,
            "executed_conditions": len(self.executed_conditions),
            "operations": len(self.run_log.operations),
            "faulted_operations": sum(1 for op in self.run_log.operations if op.get("faulted")),
        }
