# BLACK GLASS | Native routine reconstruction

This document records a **real** native-software analysis: genuine
disassembler/decompiler output from a licensed binary, an original clean-room
re-implementation of each identified routine, and a validation of that
re-implementation against the public standard — with every statement tagged by
how strongly it is established.

It does **not** execute the analysed binary, copy its decompiled source into the
repository, or claim runtime behaviour. The DSM image that motivated BLACK GLASS
is encrypted and was not opened; see
[`BLACK_GLASS_DSM_RESEARCH.md`](BLACK_GLASS_DSM_RESEARCH.md). The demonstration
substrate is a freely-licensed binary of exactly the kind firmware ships.

## Provenance levels

Every claim is one of four levels, each strictly stronger than the last:

| Level | Meaning | Here |
|---|---|---|
| **Observed** | A fact read from the binary by a disassembler/decompiler, re-checkable by re-running the same tool on the same hash-bound ELF. | Function entry, size, basic-block count, call targets, referenced constants and strings, emitted by the read-only Ghidra script. |
| **Reconstructed** | An analyst's interpretation of what the routine does, inferred from the observed facts. | "This routine initialises MD5 state / is SHA-1 / encodes base64." |
| **Implemented** | An original, clean-room re-implementation written from the *standard*, not from decompiled source. | `md5_hex`, `sha1_hex`, `base64_encode` in `reconstructions.py`. |
| **Validated** | The implementation reproduces reference vectors from the public standard, and the binary exhibits the standard's defining evidence. | RFC 1321 / FIPS 180-1 / RFC 4648 vectors pass; the binary shows each algorithm's defining constants/alphabet. |

The decompiled C is **evidence held locally** (`~/bg-research/busybox/reconstruct/*.c`);
only its SHA-256 digest and non-copyrightable derived facts enter the repository.

## Reference binary

| Field | Value |
|---|---|
| Binary | BusyBox (the canonical embedded userland), x86-64, static, stripped |
| Path analysed | `bin/busybox` |
| SHA-256 | `6e123e7f3202a8c1e9b1f94d8941580a25135382b99e8d3e34fb858bba311348` |
| Tool | Ghidra 12.1.4 headless auto-analysis |
| License | GPL-2.0 (public source available for ground-truth comparison) |

BusyBox is used because it is (a) freely licensed, (b) structurally identical to
firmware userland, and (c) backed by public source, so a reconstruction can be
checked against ground truth. The binary itself is **not committed**.

## Observed → Validated, per routine

The committed facts for each routine are under
`src/rain_atlas/blackglass/reconstruction_data/*.busybox.json`. They are produced
from the Ghidra document by the Native Routine Explorer and carry only derived
facts.

### MD5 state initialisation

* **Observed** — the routine stores the 64-bit immediates `0xefcdab8967452301`
  and `0x1032547698badcfe` into the hash state and no fifth word, then installs a
  transform callback. (Decompiled form, held locally:
  `*(u64*)(s+0x50)=0xefcdab8967452301; *(u64*)(s+0x58)=0x1032547698badcfe;`.)
* **Reconstructed** — these are exactly MD5's initial chaining values
  A=`0x67452301`, B=`0xefcdab89`, C=`0x98badcfe`, D=`0x10325476` (RFC 1321 §3.3),
  little-endian packed. Four words, no fifth → MD5, not SHA-1.
* **Implemented** — `md5_hex`, written from RFC 1321.
* **Validated** — reproduces the RFC 1321 appendix A.5 vectors and agrees with
  `hashlib.md5` on 200 random inputs; the binary exhibits MD5's IV.

### SHA-1 state initialisation

* **Observed** — the same four words **plus** a fifth, `0xc3d2e1f0`, then a
  different transform callback.
* **Reconstructed** — MD5's four words plus `0xc3d2e1f0` is exactly SHA-1's
  five-word IV (FIPS 180-1 §5). The fifth word is what distinguishes SHA-1 from
  MD5 in the binary.
* **Implemented** — `sha1_hex`, written from FIPS 180-1 / RFC 3174.
* **Validated** — reproduces the RFC 3174 vectors and agrees with `hashlib.sha1`
  on 200 random inputs; the binary exhibits SHA-1's full IV including `0xc3d2e1f0`.

### base64 encoding

* **Observed** — the routine references a 64-byte table of printable characters,
  `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/`.
* **Reconstructed** — that is the RFC 4648 §4 standard base64 alphabet; the
  routine maps 6-bit groups through it.
* **Implemented** — `base64_encode`, written from RFC 4648.
* **Validated** — reproduces the RFC 4648 §10 vectors and agrees with
  `base64.b64encode` on 200 random inputs; the binary exhibits the alphabet.

## What this does and does not establish

**Does:** that the binary statically contains routines whose defining
constants/alphabet are exactly those of MD5, SHA-1 and base64; and that a
validated clean-room model of each reproduces the public standard. Two
independent lines of evidence — the standard-defined constants in the bytes, and
a model that matches the standard — agree.

**Does not:** that the routines were executed, that they are reached at runtime,
or that the binary's transform code is bitwise-identical to the standard beyond
the observed constants. Software agreeing with a standard is **not** a physical
measurement; it is an agreement between a reconstruction and a specification,
reported as such.

## Reproducing

```sh
# 1. Observe (needs Ghidra 12; writes decompiled C + reconstruction.json locally).
"$GHIDRA/support/analyzeHeadless" /tmp/bg BG \
  -import /path/to/busybox -scriptPath rain-atlas/scripts \
  -postScript BlackglassReconstruct.java bin/busybox /path/to/busybox \
    /out/reconstruct 0x4b4c00 0x4b4cb6 0x40a567 -deleteProject

# 2. Explore the derived facts (no tool needed).
uv run atlas firmware routines /out/reconstruct/reconstruction.json

# 3. Validate the clean-room models against vectors + observed evidence,
#    and record the reconstruction into a ledger.
uv run atlas firmware reconstruct --root atlas-data/busybox-native
uv run atlas ledger verify atlas-data/busybox-native/ledger
```

The committed facts let step 2–3 run in CI with no analysis tool; step 1 is how
those facts were produced and can be re-run by anyone with the binary and Ghidra.
