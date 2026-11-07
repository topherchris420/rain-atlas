"""Import firmware archives and extracted trees safely and read-only.

Downloaded firmware is untrusted data. The ingest stage never trusts an
archive's member names or sizes: it refuses absolute paths, ``..`` escapes and
path traversal, never creates symlinks or device nodes on disk (their targets
are recorded as metadata instead), and enforces caps on entry count, per-entry
size and total extracted bytes to bound decompression bombs. Supported
containers are directories (already-extracted root filesystems), ``tar`` (any
compression ``tarfile`` supports, which includes the common firmware and
package layouts) and ``zip``. Anything else is reported as an
:class:`~rain_atlas.blackglass.errors.UnsupportedInput`, with guidance to
extract it with a dedicated tool and pass the resulting directory — BLACK GLASS
never guesses at a format it does not understand.
"""

from __future__ import annotations

import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..canonical import sha256_bytes, sha256_file
from .errors import IngestError, UnsupportedInput

DEFAULT_MAX_FILES = 200_000
DEFAULT_MAX_ENTRY_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_CHUNK = 1 << 20


@dataclass
class FirmwareImage:
    """A safely-imported, read-only firmware root plus container metadata."""

    root: Path
    label: str
    source_kind: str  # "directory" | "tar" | "zip"
    source_digest: str | None  # sha256 of the original archive, when ingested from one
    modes: dict[str, int] = field(default_factory=dict)  # relpath -> perm bits (0o7777)
    symlinks: dict[str, str] = field(default_factory=dict)  # relpath -> recorded target
    warnings: list[str] = field(default_factory=list)

    def iter_files(self) -> list[tuple[str, Path]]:
        """Regular files as ``(relative POSIX path, absolute path)``, canonical order."""

        found: list[tuple[str, Path]] = []
        for path in self.root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            found.append((rel, path))
        found.sort(key=lambda item: item[0])
        return found

    def read(self, rel: str, limit: int | None = None) -> bytes:
        target = (self.root / rel).resolve()
        if self.root.resolve() not in target.parents:
            raise IngestError(f"refusing to read outside the image root: {rel}")
        with target.open("rb") as fh:
            return fh.read() if limit is None else fh.read(limit)


def _safe_relpath(name: str) -> PurePosixPath | None:
    """Return a normalised, contained relative path, or ``None`` to skip."""

    cleaned = name.replace("\\", "/").strip()
    if not cleaned or cleaned in (".", "./"):
        return None
    pure = PurePosixPath(cleaned)
    if pure.is_absolute() or (len(cleaned) >= 2 and cleaned[1] == ":"):
        raise IngestError(f"archive member has an absolute path: {name!r}")
    parts = [p for p in pure.parts if p not in ("",)]
    if any(p == ".." for p in parts):
        raise IngestError(f"archive member escapes the root with '..': {name!r}")
    return PurePosixPath(*[p for p in parts if p != "."])


def _target(root: Path, rel: PurePosixPath) -> Path:
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise IngestError(f"archive member resolves outside the root: {rel}")
    return target


def _copy_capped(fileobj, target: Path, cap: int, name: str) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("wb") as out:
        while True:
            chunk = fileobj.read(min(_CHUNK, cap - written + 1))
            if not chunk:
                break
            written += len(chunk)
            if written > cap:
                out.close()
                target.unlink(missing_ok=True)
                raise IngestError(f"entry {name!r} exceeds the per-entry cap of {cap} bytes")
            out.write(chunk)
    return written


def _ingest_tar(source: Path, root: Path, caps: tuple[int, int, int]) -> FirmwareImage:
    max_files, max_entry, max_total = caps
    modes: dict[str, int] = {}
    symlinks: dict[str, str] = {}
    warnings: list[str] = []
    count = 0
    total = 0
    with tarfile.open(source, "r:*") as tf:
        for member in tf:
            rel = _safe_relpath(member.name)
            if rel is None:
                continue
            if member.isdir():
                _target(root, rel).mkdir(parents=True, exist_ok=True)
                continue
            if member.issym() or member.islnk():
                symlinks[rel.as_posix()] = member.linkname
                continue
            if member.ischr() or member.isblk() or member.isfifo() or member.isdev():
                warnings.append(f"skipped device/special node {rel.as_posix()}")
                continue
            if not member.isreg():
                continue
            count += 1
            if count > max_files:
                raise IngestError(f"archive exceeds the entry cap of {max_files}")
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            target = _target(root, rel)
            written = _copy_capped(extracted, target, max_entry, member.name)
            total += written
            if total > max_total:
                raise IngestError(f"archive exceeds the total-size cap of {max_total} bytes")
            modes[rel.as_posix()] = member.mode & 0o7777
    return FirmwareImage(root, source.name, "tar", sha256_file(source), modes, symlinks, warnings)


def _ingest_zip(source: Path, root: Path, caps: tuple[int, int, int]) -> FirmwareImage:
    max_files, max_entry, max_total = caps
    modes: dict[str, int] = {}
    symlinks: dict[str, str] = {}
    warnings: list[str] = []
    count = 0
    total = 0
    with zipfile.ZipFile(source) as zf:
        for info in zf.infolist():
            if info.filename.endswith("/"):
                rel = _safe_relpath(info.filename)
                if rel is not None:
                    _target(root, rel).mkdir(parents=True, exist_ok=True)
                continue
            rel = _safe_relpath(info.filename)
            if rel is None:
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                symlinks[rel.as_posix()] = zf.read(info).decode("utf-8", "replace")
                continue
            count += 1
            if count > max_files:
                raise IngestError(f"archive exceeds the entry cap of {max_files}")
            target = _target(root, rel)
            with zf.open(info) as src:
                written = _copy_capped(src, target, max_entry, info.filename)
            total += written
            if total > max_total:
                raise IngestError(f"archive exceeds the total-size cap of {max_total} bytes")
            modes[rel.as_posix()] = (mode & 0o7777) or 0o644
    return FirmwareImage(root, source.name, "zip", sha256_file(source), modes, symlinks, warnings)


def _ingest_directory(source: Path) -> FirmwareImage:
    modes: dict[str, int] = {}
    symlinks: dict[str, str] = {}
    root = source.resolve()
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            try:
                symlinks[rel] = str(path.readlink())
            except OSError:  # pragma: no cover - platform dependent
                symlinks[rel] = "?"
            continue
        if path.is_file():
            try:
                modes[rel] = stat.S_IMODE(path.stat().st_mode)
            except OSError:  # pragma: no cover
                modes[rel] = 0o644
    return FirmwareImage(root, source.name, "directory", None, modes, symlinks, [])


def ingest(
    source: Path,
    workspace: Path | None = None,
    *,
    label: str | None = None,
    max_files: int = DEFAULT_MAX_FILES,
    max_entry_bytes: int = DEFAULT_MAX_ENTRY_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> FirmwareImage:
    """Import *source* (directory, tar or zip) into *workspace*, safely.

    A directory is used in place (read-only); an archive is extracted into a new
    ``root`` directory under *workspace* (which must not already exist). The
    returned :class:`FirmwareImage` records the container kind, the archive
    digest, per-file mode bits and any recorded symlink targets.
    """

    source = Path(source)
    if not source.exists():
        raise IngestError(f"source does not exist: {source}")
    caps = (max_files, max_entry_bytes, max_total_bytes)
    if source.is_dir():
        image = _ingest_directory(source)
    else:
        if workspace is None:
            raise IngestError("ingesting an archive requires a workspace directory")
        root = Path(workspace) / "root"
        if root.exists():
            raise IngestError(f"workspace root already exists: {root}")
        root.mkdir(parents=True)
        if tarfile.is_tarfile(source):
            image = _ingest_tar(source, root, caps)
        elif zipfile.is_zipfile(source):
            image = _ingest_zip(source, root, caps)
        else:
            head = source.read_bytes()[:4]
            raise UnsupportedInput(
                f"{source.name}: unsupported container (leading bytes {head!r}). "
                "Extract it with a dedicated tool (e.g. binwalk, unsquashfs, cpio) "
                "and pass the resulting directory to BLACK GLASS."
            )
    if label:
        image.label = label
    return image


def tree_manifest(image: FirmwareImage) -> list[list]:
    """Canonical ``[path, sha256, size]`` rows for every regular file, sorted."""

    return [[rel, sha256_file(path), path.stat().st_size] for rel, path in image.iter_files()]


def tree_manifest_digest(image: FirmwareImage) -> str:
    from ..canonical import canonical_bytes

    return sha256_bytes(canonical_bytes(tree_manifest(image)))
