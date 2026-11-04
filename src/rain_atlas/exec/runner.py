"""Run one skill invocation in a bounded child process."""

from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from .. import jsonschema_lite
from ..canonical import from_jsonable, sha256_file, sha256_json, to_jsonable
from ..skills.manifest import Manifest
from ..skills.versions import loose_version, satisfies
from . import environment
from .context import RESULT_FILE, valid_artifact_name
from .policy import HostPolicy, Policy, PolicyRefused, effective_policy

CHILD_SCRIPT = Path(__file__).with_name("child.py")
TAIL_CHARS = 4000


@dataclass(frozen=True)
class SkillRef:
    """Everything the executor needs to know about the skill it runs."""

    name: str
    version: str
    path: Path
    manifest: Manifest
    content_hash: str
    trust: str = "builtin"

    def describe(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "content_hash": self.content_hash,
            "trust": self.trust,
            "determinism": self.manifest.determinism,
        }


@dataclass
class RunResult:
    run_id: str
    skill: dict
    status: str
    seed: int
    inputs: Any
    inputs_hash: str
    policy: dict | None
    started_at: str
    ended_at: str
    wall_s: float
    run_dir: Path
    outputs: Any = None
    error: dict | None = None
    log: list[str] = field(default_factory=list)
    artifacts: dict[str, dict] = field(default_factory=dict)
    exit_code: int | None = None
    peak_memory_mb: float | None = None
    peak_memory_note: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    policy_denials: list[str] = field(default_factory=list)
    environment: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def record(self) -> dict:
        """The ledger form of this run (paths are relative to the run directory)."""

        return to_jsonable(
            {
                "run_id": self.run_id,
                "skill": self.skill,
                "status": self.status,
                "seed": self.seed,
                "inputs_hash": self.inputs_hash,
                "policy": self.policy,
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "wall_s": round(self.wall_s, 4),
                "outputs": self.outputs,
                "error": self.error,
                "log": self.log,
                "artifacts": self.artifacts,
                "exit_code": self.exit_code,
                "peak_memory_mb": None if self.peak_memory_mb is None else round(self.peak_memory_mb, 1),
                "peak_memory_note": self.peak_memory_note,
                "stdout_tail": self.stdout_tail,
                "stderr_tail": self.stderr_tail,
                "policy_denials": self.policy_denials,
                "environment": self.environment,
            }
        )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _artifact_refs(value: Any) -> list[dict]:
    refs: list[dict] = []
    if isinstance(value, dict):
        if "$artifact" in value:
            refs.append(value)
        else:
            for item in value.values():
                refs.extend(_artifact_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_artifact_refs(item))
    return refs


def requirement_problems(manifest: Manifest) -> list[str]:
    """Check Python and package requirements against the running environment."""

    problems: list[str] = []
    python_spec = manifest.requires.get("python")
    if python_spec and not satisfies(loose_version(platform.python_version()), python_spec):
        problems.append(f"Python {platform.python_version()} does not satisfy {python_spec}")
    for package, spec in manifest.requires.get("packages", {}).items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            problems.append(f"package {package} is not installed (needs {spec})")
            continue
        if not satisfies(loose_version(installed), spec):
            problems.append(f"package {package} {installed} does not satisfy {spec}")
    return problems


def _interpreter() -> str:
    base = getattr(sys, "_base_executable", None)
    return base if base and os.path.exists(base) else sys.executable


def _prefixes() -> list[str]:
    return sorted({sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix})


def _under(path: str, roots: list[str]) -> bool:
    real = os.path.normcase(os.path.realpath(path))
    for root in roots:
        base = os.path.normcase(os.path.realpath(root))
        if real == base or real.startswith(base.rstrip(os.sep) + os.sep):
            return True
    return False


def _child_sys_path() -> list[str]:
    """Import path for the child: interpreter directories plus the rain_atlas package root.

    Other host entries, notably the working directory that ``python -m``
    prepends, are dropped: every import-path entry is also a readable root.
    """

    package_root = str(Path(__file__).resolve().parents[2])
    allowed = _prefixes() + [package_root]
    entries = [p for p in sys.path if p and _under(p, allowed)]
    if not any(_under(package_root, [p]) for p in entries):
        entries.append(package_root)
    return entries


def _interpreter_roots() -> list[str]:
    return sorted(set(_prefixes()) | set(_child_sys_path()))


def _child_env(tmp: Path, threads: int) -> dict[str, str]:
    env = {
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "TMPDIR": str(tmp),
        "HOME": str(tmp),
        "MPLCONFIGDIR": str(tmp / "mpl"),
        "MPLBACKEND": "Agg",
        "SOURCE_DATE_EPOCH": "0",
    }
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[var] = str(threads)
    if sys.platform == "win32":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env.update(
            {
                "SYSTEMROOT": system_root,
                "WINDIR": system_root,
                "PATH": os.pathsep.join(
                    [str(Path(_interpreter()).parent), os.path.join(system_root, "System32")]
                ),
                "USERPROFILE": str(tmp),
                "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", str(tmp)),
            }
        )
    else:
        env.update({"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    return env


def _tail(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as fh:
        fh.seek(max(0, path.stat().st_size - TAIL_CHARS * 4))
        return fh.read().decode("utf-8", errors="replace")[-TAIL_CHARS:]


def run_skill(
    skill: SkillRef,
    inputs: dict,
    *,
    seed: int,
    runs_dir: Path,
    host: HostPolicy | None = None,
    files: dict[str, Path] | None = None,
    timeout_s: float | None = None,
    memory_mb: int | None = None,
    cancel: threading.Event | None = None,
) -> RunResult:
    """Execute *skill* on *inputs*; every outcome, including failures, is returned."""

    host = host or HostPolicy()
    inputs = to_jsonable(inputs)
    started = _now()
    clock = time.monotonic()
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{skill.name}-{secrets.token_hex(4)}"
    run_dir = Path(runs_dir).resolve() / run_id  # the child runs in its own cwd, so paths must be absolute
    base = RunResult(
        run_id=run_id,
        skill=skill.describe(),
        status="pending",
        seed=int(seed),
        inputs=inputs,
        inputs_hash=sha256_json(inputs),
        policy=None,
        started_at=started,
        ended_at=started,
        wall_s=0.0,
        run_dir=run_dir,
        environment=environment.describe(),
    )

    def refuse(status: str, message: str, **details: Any) -> RunResult:
        base.status = status
        base.error = {"type": status, "message": message, **details}
        base.ended_at = _now()
        base.wall_s = time.monotonic() - clock
        return base

    if skill.manifest.kind != "executable":
        return refuse("refused", f"{skill.name} is a guidance skill and cannot be executed")
    entrypoint = skill.manifest.entrypoint
    if not entrypoint:
        return refuse("refused", f"{skill.name} declares no entrypoint")
    if skill.trust == "untrusted":
        return refuse(
            "refused", "untrusted code requires a hardened executor; this backend is policy enforcement only"
        )
    problems = requirement_problems(skill.manifest)
    if problems:
        return refuse("refused", "environment does not meet the skill's requirements", problems=problems)
    errors = jsonschema_lite.validate(inputs, skill.manifest.inputs, "inputs")
    if errors:
        return refuse("invalid-input", "inputs do not match the skill's input schema", problems=errors)
    try:
        policy: Policy = effective_policy(skill.manifest, host, timeout_s=timeout_s, memory_mb=memory_mb)
    except PolicyRefused as exc:
        return refuse("refused", str(exc))
    base.policy = policy.to_dict()

    input_dir, output_dir, tmp_dir = run_dir / "input", run_dir / "output", run_dir / "tmp"
    for directory in (input_dir, output_dir, tmp_dir / "mpl"):
        directory.mkdir(parents=True, exist_ok=False)
    for name, source in (files or {}).items():
        if not valid_artifact_name(name):
            return refuse("invalid-input", f"input file name {name!r} may not contain directories")
        shutil.copyfile(source, input_dir / name)
    for ref in _artifact_refs(inputs):
        if not valid_artifact_name(ref["$artifact"]):
            return refuse("invalid-input", "artifact must have a portable single-file name")
        target = input_dir / ref["$artifact"]
        if not target.is_file():
            return refuse("invalid-input", f"artifact {ref['$artifact']!r} was not supplied")
        if "sha256" in ref and sha256_file(target) != ref["sha256"]:
            return refuse("invalid-input", f"artifact {ref['$artifact']!r} does not match its hash")
    inputs_path = input_dir / "_inputs.json"
    inputs_path.write_text(json.dumps(inputs, allow_nan=False), encoding="utf-8")

    spec = {
        "sys_path": _child_sys_path(),
        "interpreter_roots": _interpreter_roots(),
        "skill_dir": str(Path(skill.path).resolve()),
        "entrypoint": str((Path(skill.path) / entrypoint).resolve()),
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "tmp_dir": str(tmp_dir.resolve()),
        "inputs_path": str(inputs_path.resolve()),
        "seed": int(seed),
        "policy": base.policy,
    }
    spec_path = run_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    cmd = [_interpreter(), "-s", "-P", "-B", "-X", "utf8", str(CHILD_SCRIPT), str(spec_path)]
    env = _child_env(tmp_dir.resolve(), policy.threads)
    stdout_path, stderr_path = run_dir / "stdout.txt", run_dir / "stderr.txt"
    job = None
    status = "running"
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        if sys.platform == "win32":
            from .winjob import Job  # noqa: PLC0415

            job = Job(memory_mb=policy.memory_mb, max_processes=None if policy.subprocess else 1)
            proc = job.start(cmd, stdout=out, stderr=err, stdin=subprocess.DEVNULL, cwd=tmp_dir, env=env)
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=err,
                stdin=subprocess.DEVNULL,
                cwd=tmp_dir,
                env=env,
                start_new_session=True,
            )
        deadline = clock + policy.timeout_s
        try:
            while True:
                try:
                    proc.wait(timeout=0.05)
                    break
                except subprocess.TimeoutExpired:
                    if cancel is not None and cancel.is_set():
                        status = "cancelled"
                    elif time.monotonic() >= deadline:
                        status = "timeout"
                    else:
                        continue
                    _kill(proc, job)
                    break
        except BaseException:
            _kill(proc, job)
            raise
        finally:
            if job is not None:
                base.peak_memory_mb = job.peak_memory_mb()
                base.peak_memory_note = "Windows job object peak committed memory (all processes)"
                job.close()
            else:
                # Also reap descendants when the main child exits normally.
                _kill(proc, None)
    if sys.platform != "win32":
        import resource  # noqa: PLC0415

        rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        base.peak_memory_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
        base.peak_memory_note = "max RSS over all children of this host process so far (upper bound)"

    base.exit_code = proc.returncode
    base.stdout_tail = _tail(stdout_path)
    base.stderr_tail = _tail(stderr_path)
    base.ended_at = _now()
    base.wall_s = time.monotonic() - clock

    if status in {"timeout", "cancelled"}:
        base.status = status
        base.error = {
            "type": status,
            "message": f"run {status} after {base.wall_s:.1f}s (limit {policy.timeout_s}s); process tree killed",
        }
        return _collect_artifacts(base, output_dir)

    result_path = output_dir / RESULT_FILE
    if not result_path.is_file():
        base.status = "crashed"
        base.error = {
            "type": "crashed",
            "message": f"child exited with code {proc.returncode} without a result",
        }
        return _collect_artifacts(base, output_dir)
    if result_path.is_symlink() or result_path.stat().st_size > 16 * 1024 * 1024:
        return refuse("invalid-output", "result must be a regular file no larger than 16 MiB")
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("result is not an object")
    except (ValueError, UnicodeError) as exc:
        return refuse("invalid-output", str(exc))
    base.log = payload.get("log", [])
    base.policy_denials = payload.get("policy_denials") or (payload.get("error") or {}).get(
        "policy_denials", []
    )
    if payload.get("status") != "ok":
        base.status = "error"
        base.error = payload.get("error")
        return _collect_artifacts(base, output_dir)
    outputs = payload.get("outputs")
    errors = jsonschema_lite.validate(from_jsonable(outputs), skill.manifest.outputs, "outputs")
    base.outputs = outputs
    if errors:
        base.status = "invalid-output"
        base.error = {
            "type": "invalid-output",
            "message": "outputs do not match the output schema",
            "problems": errors,
        }
    else:
        base.status = "ok"
    return _collect_artifacts(base, output_dir)


def _kill(proc: subprocess.Popen, job) -> None:
    if job is not None:
        job.kill()
    elif sys.platform == "win32":
        proc.kill()
    else:
        import signal  # noqa: PLC0415

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _collect_artifacts(result: RunResult, output_dir: Path) -> RunResult:
    for path in sorted(output_dir.iterdir()) if output_dir.exists() else []:
        if path.is_symlink() or (path.name != RESULT_FILE and not valid_artifact_name(path.name)):
            result.status = "invalid-output"
            result.error = {"type": "invalid-output", "message": "unsafe output artifact"}
            continue
        if path.is_file() and path.name != RESULT_FILE:
            result.artifacts[path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    if result.ok:
        for ref in _artifact_refs(result.outputs):
            name = ref.get("$artifact")
            meta = result.artifacts.get(name) if isinstance(name, str) else None
            if not meta or ref.get("sha256") != meta["sha256"]:
                result.status = "invalid-output"
                result.error = {
                    "type": "invalid-output",
                    "message": "output artifact missing or hash mismatch",
                }
                break
    return result
