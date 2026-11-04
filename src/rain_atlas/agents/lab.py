"""Shared services for the research roles: ledger, registry, budget, approvals.

The experimental engineer is the only role that executes skills. Every
execution, successful or not, becomes a ``run`` record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..canonical import from_jsonable, sha256_json
from ..exec.policy import HostPolicy
from ..exec.runner import RunResult, SkillRef, run_skill
from ..ledger.store import Entry, Ledger
from ..skills.registry import Registry

SCRIPTED = "scripted"


class BudgetExceeded(RuntimeError):
    pass


class ApprovalRequired(RuntimeError):
    def __init__(self, experiment: str, reason: str):
        prefix = experiment.split(":", 1)[1][:8]
        super().__init__(
            f"{reason}. Inspect the proposal, then use: atlas approve LEDGER {experiment} --digest {prefix} --operator NAME"
        )
        self.experiment = experiment
        self.prefix = prefix


@dataclass
class Budget:
    max_runs: int = 200
    max_seconds: float = 3600.0
    runs: int = 0
    seconds: float = 0.0

    def check(self, timeout_s: float) -> None:
        if self.runs + 1 > self.max_runs:
            raise BudgetExceeded(f"run budget exhausted ({self.max_runs} runs)")
        if self.seconds + timeout_s > self.max_seconds:
            raise BudgetExceeded(
                f"compute budget would be exceeded ({self.seconds:.0f}s used + {timeout_s:.0f}s timeout "
                f"> {self.max_seconds:.0f}s)"
            )

    def charge(self, result: RunResult) -> None:
        self.runs += 1
        self.seconds += result.wall_s


def author(role: str, generation: str = SCRIPTED, **extra: Any) -> dict:
    return {"role": role, "generation": generation, **extra}


@dataclass
class Lab:
    ledger: Ledger
    registry: Registry
    runs_dir: Path
    host: HostPolicy = field(default_factory=HostPolicy)
    budget: Budget = field(default_factory=Budget)
    approval_mode: str = "auto-builtin"  # or "require"

    def approved(self, experiment: str, skill: str | None = None) -> bool:
        return any(
            r["experiment"] == experiment
            and r.get("attestation") == "local-operator"
            and r.get("identity_verified") is False
            and (skill is None or r["scope"] in {"all", skill})
            for _, r in self.ledger.records("approval")
        )

    def approve(self, experiment: str, operator: str, scope: str) -> Entry:
        return self.ledger.append(
            "approval",
            {
                "experiment": experiment,
                "scope": scope,
                "operator": operator,
                "attestation": "local-operator",
                "identity_verified": False,
                "digest_prefix": experiment.split(":", 1)[1][:8],
            },
        )

    def needs_approval(self, skill: SkillRef) -> str | None:
        if self.approval_mode == "require":
            return "this lab requires operator approval before any execution"
        if skill.trust != "builtin":
            return f"{skill.name} is not a built-in skill"
        perms = skill.manifest.permissions
        if perms["network"] or perms["subprocess"]:
            return f"{skill.name} requests network or subprocess permissions"
        return None

    def note(self, experiment: str, role: str, text: str, **data: Any) -> Entry:
        return self.ledger.append(
            "note", {"experiment": experiment, "text": text, "author": author(role), **data}
        )

    def artifact_path(self, ref: dict) -> Path:
        return self.ledger._object_path(ref["sha256"])

    def stage(self, *refs: dict) -> tuple[list[dict], dict[str, Path]]:
        """Give each ledger artifact a unique input name for the next run."""

        staged, files = [], {}
        for ref in refs:
            hex_ = ref["sha256"].split(":", 1)[1]
            suffix = Path(ref["$artifact"]).suffix
            name = f"{hex_[:20]}{suffix}"
            staged.append({"$artifact": name, "sha256": ref["sha256"]})
            files[name] = self.artifact_path(ref)
        return staged, files


class Engineer:
    """Executes approved invocations and records everything about them."""

    role = "experimental-engineer"

    def __init__(self, lab: Lab):
        self.lab = lab

    def execute(
        self,
        experiment: str,
        skill: SkillRef,
        inputs: dict,
        *,
        seed: int,
        purpose: str,
        files: dict[str, Path] | None = None,
        sealed: dict | None = None,
    ) -> tuple[Entry, RunResult]:
        """Run *skill* and append a ``run`` record, whatever the outcome.

        *sealed* is ``{"commitment": ..., "public": {...}}`` when part of the
        inputs is sealed ground truth: the record then stores only the public
        part and the commitment, and the run's input copy is deleted.
        """

        prereg = self.lab.ledger.get_json(experiment)
        reason = (
            "this proposal requires operator approval"
            if prereg.get("approval_required")
            else self.lab.needs_approval(skill)
        )
        if reason and not self.lab.approved(experiment, skill.name):
            raise ApprovalRequired(experiment, reason)
        declared = prereg.get("design", {}).get("budget")
        if declared:
            previous = [r for _, r in self.lab.ledger.records("run") if r["experiment"] == experiment]
            committed = Budget(
                max_runs=declared["max_runs"],
                max_seconds=declared["max_seconds"],
                runs=len(previous),
                seconds=sum(r.get("wall_s", 0) for r in previous),
            )
            committed.check(float(skill.manifest.limits["timeout_s"]))
        self.lab.budget.check(float(skill.manifest.limits["timeout_s"]))
        from ..provenance import capture

        provenance = capture(self.lab.ledger, skill)
        result = run_skill(
            skill, inputs, seed=seed, runs_dir=self.lab.runs_dir, host=self.lab.host, files=files
        )
        self.lab.budget.charge(result)
        record = result.record()
        record.update(provenance)
        record["environment"]["atlas_source_hash"] = provenance["engine_source_hash"]
        for name, meta in record["artifacts"].items():
            meta["object"] = self.lab.ledger.put_file(result.run_dir / "output" / name)
        record.update(
            {
                "experiment": experiment,
                "role": self.role,
                "purpose": purpose,
                "approval": "operator" if reason else self.lab.approval_mode,
            }
        )
        if sealed:
            # Tracebacks and logs can echo private generator parameters.
            record.update(log=[], stdout_tail="", stderr_tail="", policy_denials=[])
            result.log, result.stdout_tail, result.stderr_tail, result.policy_denials = [], "", "", []
            if result.error:
                result.error = {
                    "type": result.status,
                    "message": "sealed run failed; private diagnostics withheld",
                }
                record["error"] = result.error
            for name in ("stdout.txt", "stderr.txt", "output/_result.json"):
                (result.run_dir / name).unlink(missing_ok=True)
            record["inputs_hash"] = sha256_json(
                {"commitment": sealed["commitment"], "public": sealed["public"]}
            )
            record["sealed"] = {
                "commitment": sealed["commitment"],
                "public_object": self.lab.ledger.put_json(sealed["public"]),
            }
            (result.run_dir / "input" / "_inputs.json").unlink(missing_ok=True)
        else:
            record["inputs_object"] = self.lab.ledger.put_json(result.inputs)
        entry = self.lab.ledger.append("run", record)
        return entry, result

    def reproduce(self, experiment: str, original: Entry, inputs: dict | None = None) -> tuple[Entry, bool]:
        """Re-run a recorded run with identical inputs and seed and compare outputs.

        Sealed runs need *inputs* reconstructed from the unsealed value; their
        public part must equal what was recorded.
        """

        record = self.lab.ledger.get_json(original.object)
        skill = self.lab.registry.get(record["skill"]["name"], record["skill"]["version"])
        if skill.content_hash != record["skill"]["content_hash"]:
            raise ValueError(
                "the skill's files changed since the original run; reproduction would not be exact"
            )
        if record.get("engine_source_hash"):
            from ..provenance import engine_root, source_snapshot

            if source_snapshot(engine_root())[1] != record["engine_source_hash"]:
                raise ValueError("engine source changed since the original run; use a linked reanalysis")
        if record.get("sealed"):
            if inputs is None:
                raise ValueError("sealed runs are reproduced after unsealing, from the unsealed value")
            public = self.lab.ledger.get_json(record["sealed"]["public_object"])
            if any(inputs.get(k) != v for k, v in public.items()):
                raise ValueError("reconstructed inputs do not match the recorded public inputs")
        else:
            inputs = from_jsonable(self.lab.ledger.get_json(record["inputs_object"]))
        refs = _artifact_refs(inputs)
        files = {ref["$artifact"]: self.lab.ledger._object_path(ref["sha256"]) for ref in refs}
        entry, result = self.execute(
            experiment,
            skill,
            inputs,
            seed=record["seed"],
            files=files,
            purpose=f"reproduction of run {record['run_id']}",
        )
        same_outputs = result.ok and sha256_json(result.outputs) == sha256_json(record["outputs"])
        same_artifacts = {k: v["sha256"] for k, v in result.record()["artifacts"].items()} == {
            k: v["sha256"] for k, v in record["artifacts"].items()
        }
        match = bool(same_outputs and same_artifacts)
        rec = self.lab.ledger.append(
            "reproduction",
            {
                "experiment": experiment,
                "original_run": original.object,
                "reproduction_run": entry.object,
                "outputs_match": bool(same_outputs),
                "artifacts_match": bool(same_artifacts),
                "author": author(self.role),
            },
        )
        return rec, match


def _artifact_refs(value: Any) -> list[dict]:
    if isinstance(value, dict):
        if "$artifact" in value:
            return [value]
        return [ref for item in value.values() for ref in _artifact_refs(item)]
    if isinstance(value, list):
        return [ref for item in value for ref in _artifact_refs(item)]
    return []
