"""Replica registry and integration readiness gates.

The registry holds every REA replica known to this ATLAS installation. A
replica may only reach ``integrated`` status when:

* all of its verified features record passing conformance cases;
* its investigation package validates;
* any behavioral deviations are explicitly accepted (recorded, not silent).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Investigation, ReplicaSpec
from .package import package_problems


@dataclass
class RegisteredReplica:
    replica: ReplicaSpec
    investigation: Investigation

    @property
    def replica_id(self) -> str:
        return self.replica.replica_id


@dataclass
class ReplicaRegistry:
    """In-process registry; persistence is derived from investigation packages."""

    replicas: dict[str, RegisteredReplica] = field(default_factory=dict)

    def register(self, investigation: Investigation) -> RegisteredReplica:
        problems = package_problems(investigation)
        if problems:
            raise ValueError(
                f"investigation for {investigation.manifest.target_id} does not validate: "
                + "; ".join(problems)
            )
        for replica in investigation.replicas:
            entry = RegisteredReplica(replica=replica, investigation=investigation)
            self.replicas[replica.replica_id] = entry
        # Re-register the target even when it has no replicas yet.
        if not investigation.replicas:
            entry = RegisteredReplica(
                replica=ReplicaSpec(
                    replica_id=f"{investigation.manifest.target_id}-none",
                    target_id=investigation.manifest.target_id,
                    module="",
                    integration_status="planned",
                ),
                investigation=investigation,
            )
            self.replicas[entry.replica_id] = entry
        return next(iter(self.replicas.values())) if investigation.replicas else entry

    def get(self, replica_id: str) -> RegisteredReplica | None:
        return self.replicas.get(replica_id)

    def by_target(self, target_id: str) -> list[RegisteredReplica]:
        return [r for r in self.replicas.values() if r.replica.target_id == target_id]

    def integrated(self) -> list[RegisteredReplica]:
        return [r for r in self.replicas.values() if r.replica.integration_status == "integrated"]

    def to_dict(self) -> dict:
        return {
            replica_id: {
                "target_id": entry.replica.target_id,
                "module": entry.replica.module,
                "integration_status": entry.replica.integration_status,
                "features": {feature.name: feature.status for feature in entry.replica.features},
            }
            for replica_id, entry in sorted(self.replicas.items())
        }


def registry_problems(registry: ReplicaRegistry) -> list[str]:
    """Gates that must all pass before the registry is internally consistent.

    One module may reconstruct capabilities from several references (the
    synthesis objective encourages this); what is forbidden is the same
    replica id registered twice.
    """

    problems: list[str] = []
    for replica_id, entry in sorted(registry.replicas.items()):
        problems.extend(
            problem.replace("replica", f"replica {replica_id}")
            for problem in package_problems(entry.investigation)
        )
    return problems
