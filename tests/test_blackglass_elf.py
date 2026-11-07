"""The pure-Python ELF reader against the fixture builder and real toolchains."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from rain_atlas.blackglass import elf, fixtures


def test_parses_64bit_little_endian():
    data = fixtures.build_elf(
        bits=64,
        endianness="little",
        machine=fixtures.EM_X86_64,
        needed=("libc.so.6", "libssl.so.1"),
        imports=("socket", "bind", "listen", "__stack_chk_fail"),
    )
    info = elf.parse(data)
    assert info is not None
    assert (info.bits, info.endianness, info.machine, info.type) == (64, "little", "x86-64", "DYN")
    assert info.needed == ["libc.so.6", "libssl.so.1"]
    assert info.pie is True and info.nx is True and info.relro == "full"
    assert info.stack_canary is True
    assert {"socket", "bind", "listen"} <= set(info.imported_symbols)


@pytest.mark.parametrize(
    "bits,endn,machine",
    [(64, "little", fixtures.EM_X86_64), (32, "little", fixtures.EM_ARM), (64, "big", 8)],
)
def test_parses_all_widths_and_endianness(bits, endn, machine):
    data = fixtures.build_elf(bits=bits, endianness=endn, machine=machine, imports=("connect",))
    info = elf.parse(data)
    assert info.bits == bits and info.endianness == endn and info.machine_id == machine
    assert info.needed == ["libc.so.6"]
    assert "connect" in info.imported_symbols


def test_soname_and_shared_object():
    data = fixtures.build_elf(soname="libc.so.6", needed=(), interp=None)
    info = elf.parse(data)
    assert info.soname == "libc.so.6"
    assert info.shared_object is True
    assert info.interpreter is None


def test_not_an_elf_returns_none():
    assert elf.parse(b"not an elf at all, just text") is None
    assert elf.parse(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64) is None


def test_truncated_elf_raises():
    data = fixtures.build_elf()
    with pytest.raises(elf.ElfFormatError):
        elf.parse(data[:40])  # header claims structures past the end
    with pytest.raises(elf.ElfFormatError):
        elf.parse(b"\x7fELF")  # magic only


def test_deterministic_build():
    kw = dict(needed=("libc.so.6",), imports=("bind", "listen"))
    assert fixtures.build_elf(**kw) == fixtures.build_elf(**kw)


@pytest.mark.skipif(not (shutil.which("gcc") and shutil.which("readelf")), reason="needs gcc + readelf")
def test_matches_readelf_oracle(tmp_path):
    src = tmp_path / "p.c"
    src.write_text(
        "#include <sys/socket.h>\nint main(void){int f=socket(2,1,0);return bind(f,0,0)+listen(f,1);}\n"
    )
    binary = tmp_path / "p"
    subprocess.run(["gcc", "-O1", "-o", str(binary), str(src)], check=True)
    info = elf.parse(binary.read_bytes())
    needed_oracle = {
        line.split("[", 1)[1].split("]", 1)[0]
        for line in subprocess.run(
            ["readelf", "-d", str(binary)], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        if "(NEEDED)" in line
    }
    assert set(info.needed) == needed_oracle
    assert "bind" in info.imported_symbols and "listen" in info.imported_symbols
