"""Permission and resource policy for one skill invocation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from ..skills.manifest import Manifest


class PolicyRefused(PermissionError):
    """The skill asks for more than the host policy grants."""


@dataclass(frozen=True)
class HostPolicy:
    """What the operator allows any skill to receive on this machine."""

    allow_network: bool = False
    allow_subprocess: bool = False
    allow_system_fonts: bool = True
    max_timeout_s: float = 900.0
    max_memory_mb: int = 4096
    threads: int = 1


@dataclass(frozen=True)
class Policy:
    """The effective policy for one run (recorded verbatim in the ledger)."""

    network: bool
    subprocess: bool
    read: tuple[str, ...]
    write: tuple[str, ...]
    timeout_s: float
    memory_mb: int
    threads: int

    def to_dict(self) -> dict:
        data = asdict(self)
        data["read"] = list(self.read)
        data["write"] = list(self.write)
        return data


def effective_policy(
    manifest: Manifest,
    host: HostPolicy,
    *,
    timeout_s: float | None = None,
    memory_mb: int | None = None,
) -> Policy:
    """Combine a manifest's request with the host's grant, refusing escalation."""

    perms = manifest.permissions
    if perms["network"] and not host.allow_network:
        raise PolicyRefused(f"{manifest.name} requests network access, which the host policy denies")
    if perms["subprocess"] and not host.allow_subprocess:
        raise PolicyRefused(f"{manifest.name} requests subprocesses, which the host policy denies")
    read = tuple(sorted(set(perms["read"]) | {"skill"}))
    if "system-fonts" in read and not host.allow_system_fonts:
        raise PolicyRefused(f"{manifest.name} requests system fonts, which the host policy denies")
    timeout = float(timeout_s if timeout_s is not None else manifest.limits["timeout_s"])
    memory = int(memory_mb if memory_mb is not None else manifest.limits["memory_mb"])
    if not math.isfinite(timeout) or timeout <= 0 or memory < 64 or host.threads < 1:
        raise PolicyRefused("limits require a finite positive timeout, memory >= 64 MB and threads >= 1")
    if timeout > host.max_timeout_s:
        raise PolicyRefused(f"timeout {timeout}s exceeds the host maximum {host.max_timeout_s}s")
    if memory > host.max_memory_mb:
        raise PolicyRefused(f"memory {memory} MB exceeds the host maximum {host.max_memory_mb} MB")
    return Policy(
        network=bool(perms["network"]),
        subprocess=bool(perms["subprocess"]),
        read=read,
        write=tuple(sorted(set(perms["write"]))),
        timeout_s=timeout,
        memory_mb=memory,
        threads=host.threads,
    )
