"""A small, defensive, dependency-free ELF reader.

This is *metadata extraction*, the same information ``readelf -dh`` and
``lddtree`` report: class, endianness, machine, type, interpreter, the dynamic
``DT_NEEDED`` / ``DT_SONAME`` / ``DT_RPATH`` entries, imported symbol names and
the usual hardening flags (PIE, NX, RELRO, stack canary). It does **not**
disassemble, decompile or reconstruct proprietary logic; it reads structural
headers that the ELF specification defines.

Design choices that matter for real firmware:

* ``DT_NEEDED`` and friends are resolved through the ``PT_LOAD`` program-header
  mapping (virtual address -> file offset), so they are recovered even when the
  section headers have been stripped, which is common in shipped binaries.
* Imported symbols come from ``.dynsym`` via the section headers when those are
  present; when they are stripped, symbol-level hints are reported as
  unavailable rather than guessed.
* Every length and offset read from the file is bounds-checked. A file that
  starts with the ELF magic but is truncated or self-inconsistent raises
  :class:`ElfFormatError`; a file that is simply not an ELF yields ``None``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

ELF_MAGIC = b"\x7fELF"

# e_type
_ET = {0: "NONE", 1: "REL", 2: "EXEC", 3: "DYN", 4: "CORE"}

# e_machine (a pragmatic subset covering common desktop and embedded targets)
_EM = {
    0: "none",
    2: "SPARC",
    3: "x86",
    8: "MIPS",
    10: "MIPS-RS3000",
    20: "PPC",
    21: "PPC64",
    40: "ARM",
    42: "SuperH",
    50: "IA-64",
    62: "x86-64",
    183: "AArch64",
    243: "RISC-V",
}

_OSABI = {0: "SYSV", 3: "Linux", 9: "FreeBSD", 97: "ARM"}

# Program-header types
PT_LOAD = 1
PT_DYNAMIC = 2
PT_INTERP = 3
PT_GNU_STACK = 0x6474E551
PT_GNU_RELRO = 0x6474E552
PF_X = 0x1

# Section-header types
SHT_DYNSYM = 11
SHN_UNDEF = 0

# Dynamic tags
DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5
DT_STRSZ = 10
DT_SONAME = 14
DT_RPATH = 15
DT_FLAGS = 30
DT_RUNPATH = 29
DT_FLAGS_1 = 0x6FFFFFFB

DF_BIND_NOW = 0x8
DF_1_NOW = 0x1

# Hard caps: real binaries are far below these; the caps bound malformed input.
_MAX_PH = 4096
_MAX_SH = 8192
_MAX_DYN = 65536
_MAX_SYM = 1_000_000


class ElfFormatError(ValueError):
    """The bytes begin with the ELF magic but are not a valid ELF file."""


@dataclass
class ElfInfo:
    bits: int
    endianness: str  # "little" | "big"
    machine: str
    machine_id: int
    type: str  # NONE | REL | EXEC | DYN | CORE
    osabi: str
    interpreter: str | None = None
    needed: list[str] = field(default_factory=list)
    soname: str | None = None
    rpath: str | None = None
    runpath: str | None = None
    imported_symbols: list[str] = field(default_factory=list)
    pie: bool | None = None
    shared_object: bool = False
    nx: bool | None = None
    relro: str | None = None  # "full" | "partial" | None
    stack_canary: bool | None = None
    fortify: bool | None = None
    section_headers_present: bool = True


def is_elf(data: bytes) -> bool:
    return data[:4] == ELF_MAGIC


def _need(data: bytes, offset: int, size: int, what: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ElfFormatError(f"{what} runs past end of file (offset={offset}, size={size})")
    return data[offset : offset + size]


def _cstr(data: bytes, start: int) -> str:
    end = data.find(b"\x00", start)
    if end < 0:
        end = len(data)
    return data[start:end].decode("utf-8", "replace")


def parse(data: bytes) -> ElfInfo | None:
    """Parse *data* as an ELF file. Return ``None`` if it is not an ELF."""

    if not is_elf(data):
        return None
    if len(data) < 20:
        raise ElfFormatError("file too short to hold an ELF identification")
    ei_class, ei_data = data[4], data[5]
    if ei_class not in (1, 2):
        raise ElfFormatError(f"invalid EI_CLASS {ei_class}")
    if ei_data not in (1, 2):
        raise ElfFormatError(f"invalid EI_DATA {ei_data}")
    bits = 32 if ei_class == 1 else 64
    endn = "<" if ei_data == 1 else ">"
    endianness = "little" if ei_data == 1 else "big"
    osabi = _OSABI.get(data[7], f"osabi-{data[7]}")

    if bits == 32:
        fmt = endn + "HHIIIIIHHHHHH"
        hsize = struct.calcsize(fmt)
        (
            e_type,
            e_machine,
            _e_version,
            _e_entry,
            e_phoff,
            e_shoff,
            _e_flags,
            _e_ehsize,
            e_phentsize,
            e_phnum,
            e_shentsize,
            e_shnum,
            e_shstrndx,
        ) = struct.unpack(fmt, _need(data, 16, hsize, "ELF32 header"))
    else:
        fmt = endn + "HHIQQQIHHHHHH"
        hsize = struct.calcsize(fmt)
        (
            e_type,
            e_machine,
            _e_version,
            _e_entry,
            e_phoff,
            e_shoff,
            _e_flags,
            _e_ehsize,
            e_phentsize,
            e_phnum,
            e_shentsize,
            e_shnum,
            e_shstrndx,
        ) = struct.unpack(fmt, _need(data, 16, hsize, "ELF64 header"))

    info = ElfInfo(
        bits=bits,
        endianness=endianness,
        machine=_EM.get(e_machine, f"machine-{e_machine}"),
        machine_id=e_machine,
        type=_ET.get(e_type, f"type-{e_type}"),
        osabi=osabi,
    )

    program_headers = _program_headers(data, endn, bits, e_phoff, e_phentsize, e_phnum)
    loads = [ph for ph in program_headers if ph["type"] == PT_LOAD]

    def vaddr_to_offset(vaddr: int) -> int | None:
        for ph in loads:
            if ph["vaddr"] <= vaddr < ph["vaddr"] + ph["filesz"]:
                return ph["offset"] + (vaddr - ph["vaddr"])
        return None

    gnu_stack = next((ph for ph in program_headers if ph["type"] == PT_GNU_STACK), None)
    if gnu_stack is not None:
        info.nx = not (gnu_stack["flags"] & PF_X)
    has_relro = any(ph["type"] == PT_GNU_RELRO for ph in program_headers)
    info.shared_object = e_type == 3
    interp_ph = next((ph for ph in program_headers if ph["type"] == PT_INTERP), None)
    if interp_ph is not None and interp_ph["filesz"]:
        info.interpreter = _cstr(_need(data, interp_ph["offset"], interp_ph["filesz"], "PT_INTERP"), 0)
    # A PIE is a shared-object ELF that is nevertheless a program (has an interp).
    if e_type == 3:
        info.pie = info.interpreter is not None

    dyn_ph = next((ph for ph in program_headers if ph["type"] == PT_DYNAMIC), None)
    dt_flags = dt_flags_1 = 0
    if dyn_ph is not None and dyn_ph["filesz"]:
        needed_offsets, str_vaddr, str_size, soname_off, rpath_off, runpath_off, dt_flags, dt_flags_1 = (
            _dynamic(data, endn, bits, dyn_ph["offset"], dyn_ph["filesz"])
        )
        str_off = vaddr_to_offset(str_vaddr) if str_vaddr is not None else None
        if str_off is not None:
            limit = min(str_off + str_size, len(data)) if str_size else len(data)

            def read_str(rel: int) -> str | None:
                pos = str_off + rel
                if pos < 0 or pos >= limit:
                    return None
                return _cstr(data[:limit], pos)

            info.needed = [s for off in needed_offsets if (s := read_str(off))]
            if soname_off is not None:
                info.soname = read_str(soname_off)
            if rpath_off is not None:
                info.rpath = read_str(rpath_off)
            if runpath_off is not None:
                info.runpath = read_str(runpath_off)

    if has_relro:
        bind_now = bool(dt_flags & DF_BIND_NOW) or bool(dt_flags_1 & DF_1_NOW)
        info.relro = "full" if bind_now else "partial"

    # Imported symbols require section headers (.dynsym + its string table).
    info.section_headers_present = bool(e_shoff and e_shnum)
    if info.section_headers_present:
        symbols = _imported_symbols(data, endn, bits, e_shoff, e_shentsize, e_shnum, e_shstrndx)
        info.imported_symbols = symbols
        if symbols:
            info.stack_canary = "__stack_chk_fail" in symbols
            info.fortify = any(s.endswith("_chk") for s in symbols)
    return info


def _program_headers(data, endn, bits, phoff, phentsize, phnum):
    if not phoff or not phnum:
        return []
    if phnum > _MAX_PH:
        raise ElfFormatError(f"implausible program-header count {phnum}")
    out = []
    for i in range(phnum):
        base = phoff + i * phentsize
        if bits == 32:
            fields = struct.unpack(endn + "IIIIIIII", _need(data, base, 32, "ELF32 program header"))
            p_type, p_offset, p_vaddr, _p_paddr, p_filesz, _p_memsz, p_flags, _p_align = fields
        else:
            fields = struct.unpack(endn + "IIQQQQQQ", _need(data, base, 56, "ELF64 program header"))
            p_type, p_flags, p_offset, p_vaddr, _p_paddr, p_filesz, _p_memsz, _p_align = fields
        out.append(
            {"type": p_type, "offset": p_offset, "vaddr": p_vaddr, "filesz": p_filesz, "flags": p_flags}
        )
    return out


def _dynamic(data, endn, bits, offset, size):
    entry_fmt = endn + ("II" if bits == 32 else "qQ")
    entry_size = struct.calcsize(entry_fmt)
    count = min(size // entry_size, _MAX_DYN)
    needed: list[int] = []
    str_vaddr = str_size = soname = rpath = runpath = None
    flags = flags_1 = 0
    for i in range(count):
        tag, val = struct.unpack(entry_fmt, _need(data, offset + i * entry_size, entry_size, "DT entry"))
        tag &= 0xFFFFFFFFFFFFFFFF if bits == 64 else 0xFFFFFFFF
        if tag == DT_NULL:
            break
        if tag == DT_NEEDED:
            needed.append(val)
        elif tag == DT_STRTAB:
            str_vaddr = val
        elif tag == DT_STRSZ:
            str_size = val
        elif tag == DT_SONAME:
            soname = val
        elif tag == DT_RPATH:
            rpath = val
        elif tag == DT_RUNPATH:
            runpath = val
        elif tag == DT_FLAGS:
            flags = val
        elif tag == DT_FLAGS_1:
            flags_1 = val
    return needed, str_vaddr, str_size or 0, soname, rpath, runpath, flags, flags_1


def _imported_symbols(data, endn, bits, shoff, shentsize, shnum, shstrndx):
    if shnum > _MAX_SH:
        raise ElfFormatError(f"implausible section-header count {shnum}")
    sections = []
    for i in range(shnum):
        base = shoff + i * shentsize
        if bits == 32:
            f = struct.unpack(endn + "IIIIIIIIII", _need(data, base, 40, "ELF32 section header"))
            sh_name, sh_type, _fl, _ad, sh_offset, sh_size, sh_link, _in, _al, sh_entsize = f
        else:
            f = struct.unpack(endn + "IIQQQQIIQQ", _need(data, base, 64, "ELF64 section header"))
            sh_name, sh_type, _fl, _ad, sh_offset, sh_size, sh_link, _in, _al, sh_entsize = f
        sections.append(
            {
                "type": sh_type,
                "offset": sh_offset,
                "size": sh_size,
                "link": sh_link,
                "entsize": sh_entsize,
            }
        )
    dynsym = next((s for s in sections if s["type"] == SHT_DYNSYM), None)
    if dynsym is None or not dynsym["entsize"]:
        return []
    strtab = sections[dynsym["link"]] if dynsym["link"] < len(sections) else None
    if strtab is None:
        return []
    str_bytes = _need(data, strtab["offset"], strtab["size"], ".dynstr")
    sym_fmt = endn + ("IIIBBH" if bits == 32 else "IBBHQQ")
    count = min(dynsym["size"] // dynsym["entsize"], _MAX_SYM)
    names: set[str] = set()
    for i in range(count):
        raw = _need(data, dynsym["offset"] + i * dynsym["entsize"], struct.calcsize(sym_fmt), "symbol")
        if bits == 32:
            st_name, _val, _size, _info, _other, st_shndx = struct.unpack(sym_fmt, raw)
        else:
            st_name, _info, _other, st_shndx, _val, _size = struct.unpack(sym_fmt, raw)
        if st_shndx != SHN_UNDEF:
            continue  # only imports (undefined symbols) are of interest here
        if st_name and st_name < len(str_bytes):
            name = _cstr(str_bytes, st_name)
            if name:
                names.add(name)
    return sorted(names)
