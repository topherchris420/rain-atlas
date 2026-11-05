"""Child-process bootstrap for one skill invocation.

Started by :mod:`rain_atlas.exec.runner` as ``python -I -B child.py spec.json``.
Only the standard library is imported before the guard is installed; the
skill's code is imported after it, so every file, network and process
operation the skill performs through Python passes the guard.

The guard is a ``sys.addaudithook`` policy layer. It is not a hard security
boundary: native code can bypass audit hooks. OS-level limits (memory, process
count, tree kill) are applied by the parent.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
import urllib.parse

_NETWORK_EVENTS = frozenset(
    {
        "socket.__new__",
        "socket.bind",
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        "socket.getnameinfo",
        "socket.sendto",
        "socket.sendmsg",
        "urllib.Request",
        "http.client.connect",
        "ftplib.connect",
        "smtplib.connect",
    }
)
_PROCESS_EVENTS = frozenset(
    {
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.spawn",
        "os.startfile",
        "os.fork",
        "os.forkpty",
        "os.kill",
        "os.killpg",
        "pty.spawn",
        "_winapi.CreateProcess",
    }
)
# event -> indices of path arguments that must lie inside a write root
_WRITE_PATH_EVENTS = {
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.mkdir": (0,),
    "os.rename": (0, 1),
    "os.replace": (0, 1),
    "os.link": (0, 1),
    "os.symlink": (0, 1),
    "os.chmod": (0,),
    "os.chown": (0,),
    "os.truncate": (0,),
    "os.utime": (0,),
    "os.setxattr": (0,),
    "os.removexattr": (0,),
    "os.chflags": (0,),
    "shutil.rmtree": (0,),
    "shutil.move": (0, 1),
    "shutil.copyfile": (1,),
    "shutil.copymode": (1,),
    "shutil.copystat": (1,),
    "shutil.copytree": (1,),
}
_READ_PATH_EVENTS = {
    "os.listdir": (0,),
    "os.scandir": (0,),
    "glob.glob": (0,),
    "os.getxattr": (0,),
    "os.listxattr": (0,),
}
# SQLite opens files natively, so the ``open`` event never sees them.
_SQLITE_NATIVE_CODE = frozenset({"sqlite3.enable_load_extension", "sqlite3.load_extension"})
_REGISTRY_WRITES = frozenset(
    {"winreg.CreateKey", "winreg.DeleteKey", "winreg.DeleteValue", "winreg.SetValue", "winreg.SaveKey"}
)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


class Guard:
    def __init__(self, policy: dict, read_roots: list[str], write_roots: list[str]):
        self.network = bool(policy["network"])
        self.subprocess = bool(policy["subprocess"])
        self.read_roots = [self._norm(p) for p in read_roots + write_roots]
        self.write_roots = [self._norm(p) for p in write_roots]
        self.denials: list[str] = []
        self._local = threading.local()

    @staticmethod
    def _norm(path: str) -> str:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))

    @staticmethod
    def _inside(path: str, roots: list[str]) -> bool:
        return any(path == root or path.startswith(root.rstrip(os.sep) + os.sep) for root in roots)

    def _path_ok(self, raw: object, roots: list[str]) -> bool:
        if raw is None or isinstance(raw, int):
            return True  # file descriptors were opened under the guard already
        if isinstance(raw, bytes):
            raw = os.fsdecode(raw)
        if not isinstance(raw, (str, os.PathLike)):
            return True
        return self._inside(self._norm(os.fspath(raw)), roots)

    def _deny(self, message: str) -> None:
        self.denials.append(message)
        raise PermissionError(f"ATLAS policy: {message}")

    def __call__(self, event: str, args: tuple) -> None:
        if getattr(self._local, "busy", False):
            return
        self._local.busy = True
        try:
            self._check(event, args)
        finally:
            self._local.busy = False

    def _check(self, event: str, args: tuple) -> None:
        if not self.network and event in _NETWORK_EVENTS:
            self._deny(f"network access ({event}) is not permitted")
        if not self.subprocess and event in _PROCESS_EVENTS:
            self._deny(f"starting or signalling processes ({event}) is not permitted")
        if event in _REGISTRY_WRITES:
            self._deny(f"registry writes ({event}) are not permitted")
        if event == "sqlite3.connect":
            self._check_sqlite(args[0] if args else None)
            return
        if event in _SQLITE_NATIVE_CODE and (event == "sqlite3.load_extension" or (args[1:] and args[1])):
            self._deny("loading native SQLite extensions is not permitted")
        if event == "open":
            path, mode, flags = (list(args) + [None, None, None])[:3]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & _WRITE_FLAGS
            )
            roots = self.write_roots if writing else self.read_roots
            if not self._path_ok(path, roots):
                kind = "write to" if writing else "read"
                self._deny(f"{kind} {path!r} is outside the permitted directories")
            return
        if event in _WRITE_PATH_EVENTS:
            for index in _WRITE_PATH_EVENTS[event]:
                if index < len(args) and not self._path_ok(args[index], self.write_roots):
                    self._deny(f"{event} on {args[index]!r} is outside the output directory")
        if event in _READ_PATH_EVENTS:
            for index in _READ_PATH_EVENTS[event]:
                if index < len(args) and not self._path_ok(args[index] or ".", self.read_roots):
                    self._deny(f"{event} on {args[index]!r} is outside the permitted directories")

    def _check_sqlite(self, database: object) -> None:
        """In-memory databases anywhere; files only in the output or temp directories.

        A ``file:`` URI is checked both as a URI and as a literal relative name,
        because the audit event does not say which one ``connect`` will use.
        Read-only (``mode=ro`` or ``immutable=1``) URIs may also use read roots.
        """
        if isinstance(database, bytes):
            database = os.fsdecode(database)
        if isinstance(database, os.PathLike):
            database = os.fspath(database)
        if not isinstance(database, str):
            self._deny("unrecognized SQLite database argument")
        if database in ("", ":memory:"):
            return
        roots, candidates = self.write_roots, [database]
        if database.startswith("file:"):
            uri = urllib.parse.urlsplit(database)
            query = urllib.parse.parse_qs(uri.query)
            if "vfs" in query or uri.netloc not in ("", "localhost"):
                self._deny("SQLite URIs may not name a VFS or a remote authority")
            if query.get("mode") == ["memory"]:
                return
            path = urllib.parse.unquote(uri.path)
            candidates.append(path[1:] if re.match(r"/[A-Za-z]:", path) else path)
            if query.get("mode") == ["ro"] or query.get("immutable") == ["1"]:
                roots = self.read_roots
        for candidate in candidates:
            if not self._path_ok(candidate, roots):
                self._deny(f"SQLite database {database!r} is outside the permitted directories")


def _system_font_dirs() -> list[str]:
    if sys.platform == "win32":
        windir = os.environ.get("SYSTEMROOT", r"C:\Windows")
        local = os.environ.get("LOCALAPPDATA")
        dirs = [os.path.join(windir, "Fonts")]
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        return dirs
    if sys.platform == "darwin":
        return ["/Library/Fonts", "/System/Library/Fonts"]
    return ["/usr/share/fonts", "/usr/local/share/fonts"]


def _open_own_status() -> int | None:
    """Open /proc/self/status before any barrier, so it stays readable later."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        return os.open("/proc/self/status", os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        return None


def _peak_rss_kib(fd: int | None) -> int | None:
    """This process's RSS high-water mark since exec (VmHWM), in KiB.

    The host cannot use wait4's ru_maxrss for this: Linux folds the pre-exec
    address space's high-water mark (the host's, after fork/vfork) into it,
    so a 10 MB skill started by a 400 MB host reports 400 MB.
    """
    if fd is None:
        return None
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        text = os.read(fd, 1 << 16).decode("ascii", "replace")
    except OSError:
        return None
    match = re.search(r"^VmHWM:\s+(\d+) kB$", text, re.MULTILINE)
    return int(match[1]) if match else None


def main(spec_path: str) -> int:
    status_fd = _open_own_status()
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    sys.path[:] = spec["sys_path"]
    sys.dont_write_bytecode = True

    policy = spec["policy"]
    if sys.platform != "win32":
        # Apply in the fresh interpreter, never in preexec_fn (unsafe with
        # threaded hosts). These are resource bounds, not syscall isolation.
        import math
        import resource

        memory = policy["memory_mb"] * 1024 * 1024
        cpu = max(1, math.ceil(policy["timeout_s"]))
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    read_roots = [spec["skill_dir"], spec["input_dir"]] + spec["interpreter_roots"]
    if "system-fonts" in policy["read"]:
        read_roots += _system_font_dirs()
    write_roots = [spec["output_dir"], spec["tmp_dir"]]

    # Import trusted host modules before the guard, the skill only after it.
    from rain_atlas.exec.context import SkillContext, finish  # noqa: PLC0415

    guard = Guard(policy, read_roots, write_roots)
    sys.addaudithook(guard)
    sys.path.insert(0, spec["skill_dir"])

    ctx = SkillContext(
        seed=spec["seed"],
        skill_dir=spec["skill_dir"],
        input_dir=spec["input_dir"],
        output_dir=spec["output_dir"],
        tmp_dir=spec["tmp_dir"],
    )
    try:
        import importlib.util  # noqa: PLC0415

        module_spec = importlib.util.spec_from_file_location("atlas_skill_entry", spec["entrypoint"])
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        with open(spec["inputs_path"], encoding="utf-8") as fh:
            inputs = json.load(fh)
        outputs = module.run(inputs, ctx)
    except BaseException as exc:  # noqa: BLE001 - every failure is recorded
        return finish(
            ctx,
            status="error",
            error={
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=20),
                "policy_denials": guard.denials,
            },
            measure=lambda: _peak_rss_kib(status_fd),
        )
    return finish(
        ctx,
        status="ok",
        outputs=outputs,
        extra={"policy_denials": guard.denials},
        measure=lambda: _peak_rss_kib(status_fd),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
