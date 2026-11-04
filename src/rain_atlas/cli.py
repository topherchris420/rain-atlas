"""Command-line interface: ``atlas``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .canonical import from_jsonable, to_jsonable


def _print_json(value) -> None:
    print(json.dumps(to_jsonable(value), indent=2, ensure_ascii=False))


def _registry(args):
    from .skills.registry import Registry  # noqa: PLC0415

    return Registry(
        home=Path(args.home) if args.home else None, builtin_root=Path(args.builtin) if args.builtin else None
    )


def cmd_skills_list(args) -> int:
    items = _registry(args).listings()
    if args.json:
        _print_json([{**item.__dict__, "path": str(item.path)} for item in items])
        return 0
    for item in items:
        flags = []
        if not item.enabled:
            flags.append("disabled")
        if not item.active:
            flags.append("inactive")
        if not item.approved:
            flags.append("unapproved")
        if item.problems:
            flags.append(f"{len(item.problems)} problem(s)")
        print(
            f"{item.name:<22} {item.version:<8} {item.trust:<9} {item.domain or '-':<20} "
            f"{', '.join(item.capabilities)}{'  [' + ', '.join(flags) + ']' if flags else ''}"
        )
    return 0


def cmd_skills_inspect(args) -> int:
    reg = _registry(args)
    matches = [
        i
        for i in reg.listings()
        if i.name == args.name and (args.version is None or i.version == args.version)
    ]
    if not matches:
        print(f"no skill named {args.name}", file=sys.stderr)
        return 1
    from .skills.catalog import load_source  # noqa: PLC0415

    for item in matches:
        src = load_source(item.path)
        _print_json(
            {
                "name": item.name,
                "version": item.version,
                "trust": item.trust,
                "enabled": item.enabled,
                "active": item.active,
                "approved": item.approved,
                "path": str(item.path),
                "content_hash": item.content_hash,
                "problems": item.problems,
                "manifest": src.manifest.raw if src.manifest else None,
            }
        )
    return 0


def cmd_skills_validate(args) -> int:
    from .skills.catalog import load_catalog  # noqa: PLC0415

    bad = 0
    for path in args.paths:
        for src in load_catalog(Path(path)):
            status = "ok" if src.ok else "INVALID"
            print(f"{status:<8} {src.name} ({src.path})")
            for problem in src.problems:
                print(f"           - {problem}")
            bad += not src.ok
    return 1 if bad else 0


def _example_check(runs_dir: Path):
    from .skills.examples import run_example  # noqa: PLC0415

    def check(ref) -> list[str]:
        problems = []
        for example in ref.manifest.examples:
            result, found = run_example(ref, example, runs_dir)
            problems += [f"{example['name']}: {p}" for p in found]
        return problems

    return check


def cmd_skills_test(args) -> int:
    from .exec.runner import SkillRef  # noqa: PLC0415
    from .skills.catalog import load_source  # noqa: PLC0415
    from .skills.examples import run_example  # noqa: PLC0415

    reg = _registry(args)
    runs_dir = Path(args.runs_dir)
    targets = []
    for name in args.names or [i.name for i in reg.listings() if i.active]:
        path = Path(name)
        if path.is_dir():
            src = load_source(path)
            if not src.ok:
                print(f"INVALID {src.name}: {'; '.join(src.problems)}")
                return 1
            targets.append(
                SkillRef(src.name, src.manifest.version, src.path, src.manifest, src.content_hash, "local")
            )
        else:
            targets.append(reg.get(name))
    failed = 0
    for ref in targets:
        for example in ref.manifest.examples:
            result, problems = run_example(ref, example, runs_dir)
            print(
                f"{'PASS' if not problems else 'FAIL'} {ref.name}@{ref.version} {example['name']} "
                f"({result.status}, {result.wall_s:.1f}s)"
            )
            for problem in problems:
                print(f"     - {problem}")
            failed += bool(problems)
    return 1 if failed else 0


def cmd_skills_install(args) -> int:
    print(_registry(args).install(Path(args.path), trust="untrusted" if args.untrusted else "local"))
    return 0


def cmd_skills_upgrade(args) -> int:
    reg = _registry(args)
    print(
        reg.upgrade(
            Path(args.path),
            check=_example_check(Path(args.runs_dir)),
            trust="untrusted" if args.untrusted else "local",
        )
    )
    return 0


def cmd_skills_approve(args) -> int:
    print(_registry(args).approve(args.name, args.version, args.hash_prefix))
    return 0


def cmd_skills_enable(args) -> int:
    print(_registry(args).set_enabled(args.name, args.command == "enable"))
    return 0


def cmd_skills_remove(args) -> int:
    print(_registry(args).remove(args.name, args.version, force=args.force))
    return 0


def cmd_skills_select(args) -> int:
    refs = _registry(args).select(args.capability)
    if not refs:
        print(f"no enabled, approved skill provides {args.capability}")
        return 1
    for ref in refs:
        print(f"{ref.name}@{ref.version} ({ref.trust}, {ref.manifest.determinism})")
    return 0


def cmd_run(args) -> int:
    from .exec.runner import run_skill  # noqa: PLC0415

    reg = _registry(args)
    ref = reg.get(args.skill, args.version)
    inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    files = {}
    for item in args.file or []:
        name, _, path = item.partition("=")
        if not path:
            print("--file takes NAME=PATH", file=sys.stderr)
            return 2
        files[name] = Path(path)
    result = run_skill(ref, inputs, seed=args.seed, runs_dir=Path(args.runs_dir), files=files)
    record = result.record()
    record["run_dir"] = str(result.run_dir)
    _print_json(record)
    return 0 if result.ok else 1


def cmd_experiment_run(args) -> int:
    from .experiments import spectral_recovery  # noqa: PLC0415

    if args.name == "synchronization":
        from .experiments import synchronization

        summary = synchronization.run(
            Path(args.root),
            synchronization.Settings(
                replicates=args.replicates if args.replicates is not None else 12, figures=not args.no_figures
            ),
            registry=_registry(args),
            progress=lambda message: print(message, flush=True),
        )
        for item in summary["acceptance"]:
            print(f"{item['id']} {'PASS' if item['passed'] else 'FAIL'} {item['criterion']}")
        print(f"report: {summary['report_path']}")
        print(f"observatory: {summary['observatory_path']}")
        return 0 if all(a["passed"] for a in summary["acceptance"]) else 1
    if args.name != "spectral-recovery":
        print(
            f"unknown experiment {args.name!r}; available: spectral-recovery, synchronization",
            file=sys.stderr,
        )
        return 2
    settings = spectral_recovery.Settings(
        mode=args.mode,
        realizations=args.realizations,
        replicates=args.replicates if args.replicates is not None else 10,
        figures=not args.no_figures,
        bundle=not args.no_bundle,
    )
    summary = spectral_recovery.run(
        Path(args.root),
        settings,
        registry=_registry(args),
        progress=lambda message: print(message, flush=True),
    )
    print()
    print(summary["answer"])
    for item in summary["acceptance"]:
        print(f"  {item['id']} {'PASS' if item['passed'] else 'FAIL'}  {item['detail'][:160]}")
    print(f"report: {summary['report_path']}")
    if summary.get("bundle_path"):
        print(f"bundle: {summary['bundle_path']}")
    return 0 if all(item["passed"] for item in summary["acceptance"]) else 1


def cmd_ledger_verify(args) -> int:
    from .ledger.store import Ledger  # noqa: PLC0415

    path = Path(args.path)
    if not (path / "log.jsonl").exists():
        print(f"{path} is not a ledger (no log.jsonl)", file=sys.stderr)
        return 2
    ledger = Ledger(path)
    problems = ledger.verify()
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    count = sum(1 for _ in ledger.entries())
    print(f"ok: {count} record(s); chain, object hashes and record rules verified")
    return 0


def cmd_ledger_show(args) -> int:
    from .ledger.store import Ledger  # noqa: PLC0415

    ledger = Ledger(Path(args.path))
    entries = [e for e in ledger.entries(args.kind)]
    for entry in entries[-args.limit :] if args.limit else entries:
        record = ledger.get_json(entry.object)
        text = (
            record.get("statement")
            or record.get("text")
            or record.get("purpose")
            or record.get("label")
            or ""
        )
        print(f"{entry.seq:>5} {entry.kind:<15} {entry.object[7:19]}  {str(text)[:100]}")
        if args.full:
            _print_json(from_jsonable(record))
    return 0


def cmd_env(args) -> int:
    from .exec import environment  # noqa: PLC0415
    from .exec.policy import HostPolicy  # noqa: PLC0415

    _print_json(
        {
            "environment": environment.describe(),
            "host_policy": HostPolicy().__dict__,
            "isolation": "Windows job object" if sys.platform == "win32" else "setrlimit + process group",
            "guard": "Python audit hooks (policy enforcement, not an OS sandbox)",
        }
    )
    return 0


def cmd_observatory(args) -> int:
    from .observatory.export import export

    print(export(Path(args.ledger), Path(args.out), registry=_registry(args)))
    return 0


def cmd_proposal(args) -> int:
    from .agents.proposals import load_proposal, register, validate_proposal
    from .ledger.store import Ledger

    registry = _registry(args)
    data = load_proposal(Path(args.file), registry)
    if args.command == "inspect":
        _print_json(
            {
                "digest": validate_proposal(data, registry),
                "proposal": data,
                "execution": "none",
                "approval": "required",
            }
        )
    else:
        print(register(data, Ledger(Path(args.ledger)), registry))
        print("Registered only. No execution or approval has occurred.")
    return 0


def cmd_benchmark(args) -> int:
    from .bench.lab import run

    result = run(Path(args.root), args.trials, registry=_registry(args))
    print(result["path"])
    return 0


def cmd_ledger_search(args) -> int:
    from .ledger.index import search
    from .ledger.store import Ledger

    if not (Path(args.path) / "log.jsonl").is_file():
        raise ValueError("not a ledger (no log.jsonl)")
    _print_json(search(Ledger(Path(args.path)), args.query, kind=args.kind, limit=args.limit))
    return 0


def cmd_recover(args) -> int:
    from .ledger.recovery import recover

    print(recover(Path(args.path), Path(args.out)).root)
    return 0


def cmd_approve(args) -> int:
    from .agents.lab import Lab
    from .ledger.store import Ledger

    if not (Path(args.ledger) / "log.jsonl").is_file():
        raise ValueError("not a ledger (no log.jsonl)")
    ledger = Ledger(Path(args.ledger))
    if ledger.verify():
        raise ValueError("approval requires a verified ledger")
    if not any(e.object == args.experiment for e in ledger.entries("preregistration")):
        raise ValueError("experiment must identify a preregistration")
    if len(args.digest) < 8 or not args.experiment.removeprefix("sha256:").startswith(args.digest):
        raise ValueError("--digest must match at least 8 hex digits of the reviewed preregistration")
    if args.scope != "all":
        _registry(args).get(args.scope)
    print(
        Lab(ledger, _registry(args), ledger.root.parent / "runs")
        .approve(args.experiment, args.operator, args.scope)
        .object
    )
    return 0


def cmd_integration(args) -> int:
    if args.command == "luca-quarantine":
        from .adapters.luca import quarantine

        print(quarantine(Path(args.file), Path(args.out)))
    else:
        from .adapters.rain import export
        from .ledger.store import Ledger

        if not (Path(args.ledger) / "log.jsonl").is_file():
            raise ValueError("not a ledger (no log.jsonl)")
        print(
            export(
                Ledger(Path(args.ledger)), args.experiment, args.rain_id, args.rain_version, Path(args.out)
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="R.A.I.N. ATLAS: local-first scientific skills, "
        "bounded execution and an append-only evidence ledger.",
    )
    parser.add_argument("--version", action="version", version=f"rain-atlas {__version__}")
    parser.add_argument(
        "--home", help="ATLAS home for installed skills (default: $ATLAS_HOME or ~/.rain-atlas)"
    )
    parser.add_argument("--builtin", help="built-in skills directory (default: the repository's skills/)")
    sub = parser.add_subparsers(dest="group", required=True)

    p = sub.add_parser("benchmark", help="execute the classical spectral stress benchmark")
    p.add_argument("--root", required=True)
    p.add_argument("--trials", type=int, default=12)
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("approve", help="append a local operator attestation; never executes a proposal")
    p.add_argument("ledger")
    p.add_argument("experiment")
    p.add_argument("--digest", required=True)
    p.add_argument("--operator", required=True)
    p.add_argument("--scope", default="all")
    p.set_defaults(func=cmd_approve)

    adapters = sub.add_parser(
        "integration", help="local export or quarantine; never contacts external runtimes"
    )
    asub = adapters.add_subparsers(dest="command", required=True)
    p = asub.add_parser("rain-export")
    p.add_argument("ledger")
    p.add_argument("experiment")
    p.add_argument("--rain-id", required=True)
    p.add_argument("--rain-version", type=int, required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_integration)
    p = asub.add_parser("luca-quarantine")
    p.add_argument("file")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_integration)

    obs = sub.add_parser("observatory", help="export a verified offline read-only research view")
    osub = obs.add_subparsers(dest="command", required=True)
    p = osub.add_parser("export")
    p.add_argument("ledger", help="explicit source ledger directory")
    p.add_argument("--out", required=True, help="new output directory; never overwrites")
    p.set_defaults(func=cmd_observatory)

    proposal = sub.add_parser("proposal", help="inspect or register a proposal; never executes it")
    psub = proposal.add_subparsers(dest="command", required=True)
    for command in ("inspect", "register"):
        p = psub.add_parser(command)
        p.add_argument("file")
        if command == "register":
            p.add_argument("--ledger", required=True)
        p.set_defaults(func=cmd_proposal)

    skills = sub.add_parser("skills", help="list, validate, test, install and manage skills")
    ssub = skills.add_subparsers(dest="command", required=True)
    p = ssub.add_parser("list", help="list built-in and installed skills")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_skills_list)
    p = ssub.add_parser("inspect", help="show one skill's manifest and status")
    p.add_argument("name")
    p.add_argument("--version")
    p.set_defaults(func=cmd_skills_inspect)
    p = ssub.add_parser("validate", help="validate skill directories or catalogs")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_skills_validate)
    p = ssub.add_parser("test", help="run skills' examples in the bounded executor")
    p.add_argument("names", nargs="*", help="skill names or directories (default: all active skills)")
    p.add_argument("--runs-dir", default="atlas-data/example-runs")
    p.set_defaults(func=cmd_skills_test)
    p = ssub.add_parser("install", help="install a skill directory (never overwrites)")
    p.add_argument("path")
    p.add_argument("--untrusted", action="store_true", help="install as untrusted (needs approve before use)")
    p.set_defaults(func=cmd_skills_install)
    p = ssub.add_parser("upgrade", help="install a newer version; activate it only if its examples pass")
    p.add_argument("path")
    p.add_argument("--untrusted", action="store_true")
    p.add_argument("--runs-dir", default="atlas-data/example-runs")
    p.set_defaults(func=cmd_skills_upgrade)
    p = ssub.add_parser("approve", help="approve an untrusted install, pinned to its content hash")
    p.add_argument("name")
    p.add_argument("version")
    p.add_argument("hash_prefix", help="at least 8 hex digits of the skill's content hash")
    p.set_defaults(func=cmd_skills_approve)
    for name in ("enable", "disable"):
        p = ssub.add_parser(name, help=f"{name} a skill by name")
        p.add_argument("name")
        p.set_defaults(func=cmd_skills_enable)
    p = ssub.add_parser("remove", help="move an installed version to the registry trash")
    p.add_argument("name")
    p.add_argument("version")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_skills_remove)
    p = ssub.add_parser("select", help="show which skills provide a capability, best first")
    p.add_argument("capability")
    p.set_defaults(func=cmd_skills_select)

    p = sub.add_parser("run", help="run one skill on a JSON inputs file (not recorded in a ledger)")
    p.add_argument("skill")
    p.add_argument("--inputs", required=True)
    p.add_argument("--file", action="append", help="NAME=PATH to copy into the run's input directory")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--version")
    p.add_argument("--runs-dir", default="atlas-data/runs")
    p.set_defaults(func=cmd_run)

    exp = sub.add_parser("experiment", help="run registered experiments")
    esub = exp.add_subparsers(dest="command", required=True)
    p = esub.add_parser("run", help="execute an experiment end to end")
    p.add_argument("name", help="spectral-recovery or synchronization")
    p.add_argument("--mode", choices=("fixed", "blinded"), default="fixed")
    p.add_argument("--root", default="atlas-data/spectral-recovery")
    p.add_argument("--realizations", type=int, default=20)
    p.add_argument("--replicates", type=int, help="default: 10 spectral, 12 synchronization")
    p.add_argument("--no-figures", action="store_true")
    p.add_argument("--no-bundle", action="store_true")
    p.set_defaults(func=cmd_experiment_run)

    ledger = sub.add_parser("ledger", help="inspect and verify evidence ledgers")
    lsub = ledger.add_subparsers(dest="command", required=True)
    p = lsub.add_parser("search", help="search a verified ledger through a disposable local index")
    p.add_argument("path")
    p.add_argument("query")
    p.add_argument("--kind")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_ledger_search)
    p = lsub.add_parser("recover", help="recover a torn final append into a fresh ledger")
    p.add_argument("path")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_recover)
    p = lsub.add_parser("verify", help="recompute the hash chain, object hashes and record rules")
    p.add_argument("path")
    p.set_defaults(func=cmd_ledger_verify)
    p = lsub.add_parser("show", help="list records")
    p.add_argument("path")
    p.add_argument("--kind")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--full", action="store_true")
    p.set_defaults(func=cmd_ledger_show)

    p = sub.add_parser("env", help="describe the environment and isolation in use")
    p.set_defaults(func=cmd_env)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:  # noqa: BLE001 - report cleanly, keep a non-zero exit
        from .exec.policy import PolicyRefused  # noqa: PLC0415
        from .ledger.store import LedgerError  # noqa: PLC0415
        from .skills.registry import RegistryError  # noqa: PLC0415

        if isinstance(exc, (RegistryError, LedgerError, PolicyRefused, OSError, ValueError, RuntimeError)):
            print(f"error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
