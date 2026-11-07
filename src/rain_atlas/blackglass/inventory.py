"""Classify every file in a firmware image into a typed software component.

Classification is conservative and evidence-preserving: a file is only called
an ELF when it parses as one, a script when it carries a shebang, key material
when it carries a PEM header, and so on. A file that merely *starts* with the
ELF magic but does not parse is recorded as opaque ``data`` with the parse error
attached, never as a half-understood binary. The result is a deterministic,
canonically-ordered inventory keyed by relative path.
"""

from __future__ import annotations

from .elf import ElfFormatError, is_elf, parse
from .ingest import FirmwareImage
from .model import Component

# leading-byte signatures for common compressed/container formats
_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"\x1f\x8b", "gzip"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"BZh", "bzip2"),
    (b"PK\x03\x04", "zip"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"hsqs", "squashfs-le"),
    (b"sqsh", "squashfs-be"),
    (b"\x85\x19", "jffs2-le"),
    (b"\xd0\x0d\xfe\xed", "uimage"),  # not exact, placeholder family
    (b"070701", "cpio-newc"),
    (b"ustar", "tar"),
)

_PEM_TYPES = (
    (b"-----BEGIN CERTIFICATE-----", "certificate"),
    (b"-----BEGIN PRIVATE KEY-----", "private-key"),
    (b"-----BEGIN RSA PRIVATE KEY-----", "rsa-private-key"),
    (b"-----BEGIN EC PRIVATE KEY-----", "ec-private-key"),
    (b"-----BEGIN PUBLIC KEY-----", "public-key"),
    (b"-----BEGIN OPENSSH PRIVATE KEY-----", "openssh-private-key"),
)

_CONFIG_SUFFIXES = (
    ".conf",
    ".cfg",
    ".ini",
    ".json",
    ".xml",
    ".toml",
    ".yaml",
    ".yml",
    ".service",
    ".socket",
    ".target",
    ".mount",
    ".timer",
    ".rules",
    ".policy",
)

_SHEBANG_LANG = {
    "sh": "shell",
    "bash": "shell",
    "dash": "shell",
    "ash": "shell",
    "python": "python",
    "python3": "python",
    "perl": "perl",
    "lua": "lua",
    "node": "javascript",
    "awk": "awk",
}

_PARSE_CAP = 128 * 1024 * 1024  # do not read absurdly large files fully into RAM


def _is_text(sample: bytes) -> bool:
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _archive_format(head: bytes) -> str | None:
    for magic, name in _MAGICS:
        if head.startswith(magic):
            return name
    if head[257:262] == b"ustar":  # tar magic lives at offset 257
        return "tar"
    return None


def _shebang(head: bytes) -> dict | None:
    if not head.startswith(b"#!"):
        return None
    line = head.split(b"\n", 1)[0].decode("utf-8", "replace").rstrip()
    tokens = line[2:].strip().split()
    if not tokens:
        return None
    interp = tokens[0]
    if interp.rsplit("/", 1)[-1] == "env" and len(tokens) > 1:
        interp_name = tokens[1].rsplit("/", 1)[-1]
    else:
        interp_name = interp.rsplit("/", 1)[-1]
    return {
        "shebang": line,
        "interpreter": interp,
        "language": _SHEBANG_LANG.get(interp_name, "unknown"),
    }


def _parse_dpkg_status(text: str) -> list[dict]:
    packages = []
    for block in text.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line and not line.startswith(" ") and ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip().lower()] = value.strip()
        if "package" in fields:
            packages.append(
                {k: fields[k] for k in ("package", "version", "architecture", "depends") if k in fields}
            )
    return packages


def classify(image: FirmwareImage, rel: str, path, size: int) -> tuple[str, dict]:
    """Return ``(kind, detail)`` for one file, reading only what is needed."""

    with path.open("rb") as fh:
        head = fh.read(4096)

    if is_elf(head):
        if size > _PARSE_CAP:
            return "data", {"note": "ELF too large to parse within the memory cap", "elf": False}
        try:
            info = parse(path.read_bytes())
        except ElfFormatError as exc:
            return "data", {"elf_error": str(exc), "note": "ELF magic but could not be parsed"}
        if info is not None:
            detail = {
                "bits": info.bits,
                "endianness": info.endianness,
                "machine": info.machine,
                "elf_type": info.type,
                "osabi": info.osabi,
                "interpreter": info.interpreter,
                "needed": info.needed,
                "soname": info.soname,
                "rpath": info.rpath,
                "runpath": info.runpath,
                "pie": info.pie,
                "shared_object": info.shared_object,
                "nx": info.nx,
                "relro": info.relro,
                "stack_canary": info.stack_canary,
                "fortify": info.fortify,
                "section_headers_present": info.section_headers_present,
                "imported_symbols": info.imported_symbols,
            }
            return "elf", detail

    shebang = _shebang(head)
    if shebang is not None:
        return "script", shebang

    for marker, pem_type in _PEM_TYPES:
        if marker in head:
            return "key-material", {"pem_type": pem_type}

    fmt = _archive_format(head)
    if fmt is not None:
        return "archive", {"format": fmt}

    lower = rel.lower()
    name = rel.rsplit("/", 1)[-1]
    if lower.endswith("dpkg/status") or name in ("control", "INFO") or "/opkg/" in lower:
        detail: dict = {"manifest_kind": "dpkg" if "dpkg" in lower else "opkg/control"}
        if size < 4 * 1024 * 1024:
            try:
                detail["packages"] = _parse_dpkg_status(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:  # pragma: no cover
                pass
        return "package-manifest", detail

    if lower.endswith(_CONFIG_SUFFIXES) or rel.startswith("etc/"):
        if _is_text(head):
            return "config", {}

    return ("data", {}) if not _is_text(head) else ("config", {"text": True})


def build_inventory(image: FirmwareImage) -> list[Component]:
    """Classify every regular file, returning components in canonical order."""

    from ..canonical import sha256_file

    components: list[Component] = []
    for rel, path in image.iter_files():
        size = path.stat().st_size
        kind, detail = classify(image, rel, path, size)
        components.append(
            Component(
                path=rel,
                size=size,
                sha256=sha256_file(path),
                kind=kind,
                mode=image.modes.get(rel),
                detail=detail,
            )
        )
    return components
