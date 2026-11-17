"""Crash-safe file primitives shared by the local-first stores.

* :func:`atomic_write` -- write to a temporary sibling, ``fsync`` it, then
  ``os.replace`` it over the target. Readers observe either the old or the new
  file, never a torn one.
* :func:`exclusive_lock` -- an OS advisory lock (``fcntl.flock`` on POSIX,
  ``msvcrt.locking`` on Windows). The operating system releases it when the
  holder exits, so a crashed writer cannot leave a store permanently locked
  (unlike an ``O_EXCL`` marker file).
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator


def atomic_write(path: Path, data: bytes) -> None:
    """Durably replace *path* with *data*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with tmp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def append_durably(path: Path, data: bytes) -> None:
    """Append *data* to *path* and ``fsync`` before returning."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def exclusive_lock(
    path: Path,
    *,
    timeout_s: float = 30.0,
    error: Callable[[str], Exception] = RuntimeError,
) -> Iterator[None]:
    """Hold an exclusive advisory lock on *path* for the duration of the block."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt  # noqa: PLC0415

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl  # noqa: PLC0415

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise error(f"could not lock {path} within {timeout_s}s") from None
                time.sleep(0.01)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt  # noqa: PLC0415

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
