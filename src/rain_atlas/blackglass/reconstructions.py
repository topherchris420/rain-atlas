"""Clean-room behaviour models for the reconstructed BusyBox routines.

Each model is an *original* implementation written from the public standard the
routine implements (RFC 1321 for MD5, FIPS 180-1 / RFC 3174 for SHA-1, RFC 4648
for base64). No decompiled source is copied. The ``expects_constants`` /
``expects_strings`` on each spec are the algorithm's defining values **as the
standard specifies them** — the comparison laboratory then checks that the
analysed binary actually contains them, which is independent corroboration that
the bytes implement the claimed algorithm.

The ``RoutineObservation`` for each routine is loaded from a committed facts file
under ``reconstruction_data/`` (derived facts only: names, addresses, sizes,
callees, string and constant references — never decompiled text, which is kept
locally as evidence and referenced by digest).
"""

from __future__ import annotations

import struct
from pathlib import Path

from .routines import BehaviorSpec, BehaviorVector, ReconstructedRoutine, RoutineObservation

DATA_DIR = Path(__file__).parent / "reconstruction_data"


def _rotl32(value: int, count: int) -> int:
    value &= 0xFFFFFFFF
    return ((value << count) | (value >> (32 - count))) & 0xFFFFFFFF


# --- MD5 (RFC 1321) ---------------------------------------------------------

_MD5_S = (
    7,
    12,
    17,
    22,
    7,
    12,
    17,
    22,
    7,
    12,
    17,
    22,
    7,
    12,
    17,
    22,
    5,
    9,
    14,
    20,
    5,
    9,
    14,
    20,
    5,
    9,
    14,
    20,
    5,
    9,
    14,
    20,
    4,
    11,
    16,
    23,
    4,
    11,
    16,
    23,
    4,
    11,
    16,
    23,
    4,
    11,
    16,
    23,
    6,
    10,
    15,
    21,
    6,
    10,
    15,
    21,
    6,
    10,
    15,
    21,
    6,
    10,
    15,
    21,
)
# T[i] = floor(2**32 * abs(sin(i+1))); RFC 1321 section 3.4.
_MD5_T = tuple(
    (
        0xD76AA478,
        0xE8C7B756,
        0x242070DB,
        0xC1BDCEEE,
        0xF57C0FAF,
        0x4787C62A,
        0xA8304613,
        0xFD469501,
        0x698098D8,
        0x8B44F7AF,
        0xFFFF5BB1,
        0x895CD7BE,
        0x6B901122,
        0xFD987193,
        0xA679438E,
        0x49B40821,
        0xF61E2562,
        0xC040B340,
        0x265E5A51,
        0xE9B6C7AA,
        0xD62F105D,
        0x02441453,
        0xD8A1E681,
        0xE7D3FBC8,
        0x21E1CDE6,
        0xC33707D6,
        0xF4D50D87,
        0x455A14ED,
        0xA9E3E905,
        0xFCEFA3F8,
        0x676F02D9,
        0x8D2A4C8A,
        0xFFFA3942,
        0x8771F681,
        0x6D9D6122,
        0xFDE5380C,
        0xA4BEEA44,
        0x4BDECFA9,
        0xF6BB4B60,
        0xBEBFBC70,
        0x289B7EC6,
        0xEAA127FA,
        0xD4EF3085,
        0x04881D05,
        0xD9D4D039,
        0xE6DB99E5,
        0x1FA27CF8,
        0xC4AC5665,
        0xF4292244,
        0x432AFF97,
        0xAB9423A7,
        0xFC93A039,
        0x655B59C3,
        0x8F0CCC92,
        0xFFEFF47D,
        0x85845DD1,
        0x6FA87E4F,
        0xFE2CE6E0,
        0xA3014314,
        0x4E0811A1,
        0xF7537E82,
        0xBD3AF235,
        0x2AD7D2BB,
        0xEB86D391,
    )
)


def md5_hex(message_hex: str) -> str:
    """MD5 of the message given as a hex string; returns the lowercase hex digest."""

    msg = bytes.fromhex(message_hex)
    a0, b0, c0, d0 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    bit_len = (len(msg) * 8) & 0xFFFFFFFFFFFFFFFF
    msg += b"\x80"
    while len(msg) % 64 != 56:
        msg += b"\x00"
    msg += struct.pack("<Q", bit_len)
    for off in range(0, len(msg), 64):
        m = struct.unpack("<16I", msg[off : off + 64])
        a, b, c, d = a0, b0, c0, d0
        for i in range(64):
            if i < 16:
                f = (b & c) | (~b & 0xFFFFFFFF & d)
                g = i
            elif i < 32:
                f = (d & b) | (~d & 0xFFFFFFFF & c)
                g = (5 * i + 1) % 16
            elif i < 48:
                f = b ^ c ^ d
                g = (3 * i + 5) % 16
            else:
                f = c ^ (b | (~d & 0xFFFFFFFF))
                g = (7 * i) % 16
            f = (f + a + _MD5_T[i] + m[g]) & 0xFFFFFFFF
            a, d, c = d, c, b
            b = (b + _rotl32(f, _MD5_S[i])) & 0xFFFFFFFF
        a0 = (a0 + a) & 0xFFFFFFFF
        b0 = (b0 + b) & 0xFFFFFFFF
        c0 = (c0 + c) & 0xFFFFFFFF
        d0 = (d0 + d) & 0xFFFFFFFF
    return struct.pack("<4I", a0, b0, c0, d0).hex()


_MD5_SPEC = BehaviorSpec(
    name="md5",
    summary="RFC 1321 MD5: a 128-bit cryptographic digest of an arbitrary byte string.",
    inputs="a message as a byte string (passed hex-encoded)",
    outputs="the 16-byte MD5 digest (hex)",
    steps=(
        "pad the message with 0x80, then zero bytes, to 56 mod 64, then append the 64-bit little-endian bit length",
        "initialise the state A,B,C,D to the RFC 1321 constants",
        "for each 64-byte block, run 64 operations over four nonlinear rounds using the sine-derived table T",
        "add the block result back into the state (Merkle-Damgård)",
        "emit the state little-endian",
    ),
    references=("RFC 1321 (The MD5 Message-Digest Algorithm)",),
    relies_on_calls=(),
    # The observed routine is MD5 state initialisation; it stores MD5's four
    # initial chaining values (RFC 1321 §3.3) as two little-endian-packed 64-bit
    # immediates: A||B = 0x67452301||0xefcdab89 and C||D = 0x98badcfe||0x10325476.
    # Four words and no fifth distinguishes MD5 from SHA-1 in the bytes.
    expects_constants=("0xefcdab8967452301", "0x1032547698badcfe"),
    expects_strings=(),
)

# RFC 1321 appendix A.5 test suite.
_MD5_VECTORS = (
    BehaviorVector("empty", {"message_hex": ""}, "d41d8cd98f00b204e9800998ecf8427e", "standard", "RFC 1321"),
    BehaviorVector(
        "abc", {"message_hex": "616263"}, "900150983cd24fb0d6963f7d28e17f72", "standard", "RFC 1321"
    ),
    BehaviorVector(
        "message-digest",
        {"message_hex": b"message digest".hex()},
        "f96b697d7cb7938d525a2f31aaf161d0",
        "standard",
        "RFC 1321",
    ),
    BehaviorVector(
        "alphabet",
        {"message_hex": b"abcdefghijklmnopqrstuvwxyz".hex()},
        "c3fcd3d76192e4007dfb496cca67e13b",
        "standard",
        "RFC 1321",
    ),
)


# --- SHA-1 (FIPS 180-1 / RFC 3174) ------------------------------------------


def sha1_hex(message_hex: str) -> str:
    msg = bytes.fromhex(message_hex)
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    bit_len = (len(msg) * 8) & 0xFFFFFFFFFFFFFFFF
    msg += b"\x80"
    while len(msg) % 64 != 56:
        msg += b"\x00"
    msg += struct.pack(">Q", bit_len)
    for off in range(0, len(msg), 64):
        w = list(struct.unpack(">16I", msg[off : off + 64]))
        for i in range(16, 80):
            w.append(_rotl32(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1))
        a, b, c, d, e = h
        for i in range(80):
            if i < 20:
                f = (b & c) | (~b & 0xFFFFFFFF & d)
                k = 0x5A827999
            elif i < 40:
                f = b ^ c ^ d
                k = 0x6ED9EBA1
            elif i < 60:
                f = (b & c) | (b & d) | (c & d)
                k = 0x8F1BBCDC
            else:
                f = b ^ c ^ d
                k = 0xCA62C1D6
            t = (_rotl32(a, 5) + f + e + k + w[i]) & 0xFFFFFFFF
            e, d, c, b, a = d, c, _rotl32(b, 30), a, t
        h = [
            (h[0] + a) & 0xFFFFFFFF,
            (h[1] + b) & 0xFFFFFFFF,
            (h[2] + c) & 0xFFFFFFFF,
            (h[3] + d) & 0xFFFFFFFF,
            (h[4] + e) & 0xFFFFFFFF,
        ]
    return struct.pack(">5I", *h).hex()


_SHA1_SPEC = BehaviorSpec(
    name="sha1",
    summary="FIPS 180-1 / RFC 3174 SHA-1: a 160-bit cryptographic digest.",
    inputs="a message as a byte string (passed hex-encoded)",
    outputs="the 20-byte SHA-1 digest (hex)",
    steps=(
        "pad with 0x80, zero bytes to 56 mod 64, then the 64-bit big-endian bit length",
        "initialise H0..H4 to the standard constants",
        "expand each 64-byte block to 80 words and run 80 rounds with four round constants",
        "add the block result back into H0..H4",
        "emit H0..H4 big-endian",
    ),
    references=("FIPS 180-1", "RFC 3174 (US Secure Hash Algorithm 1)"),
    relies_on_calls=(),
    # The observed routine is SHA-1 state initialisation; it stores SHA-1's five
    # initial hash values (FIPS 180-1 §5): MD5's four packed words plus a fifth,
    # H4 = 0xc3d2e1f0. The fifth word is what tells SHA-1 from MD5 in the bytes.
    expects_constants=("0xefcdab8967452301", "0x1032547698badcfe", "0xc3d2e1f0"),
    expects_strings=(),
)

_SHA1_VECTORS = (
    BehaviorVector(
        "empty", {"message_hex": ""}, "da39a3ee5e6b4b0d3255bfef95601890afd80709", "standard", "FIPS 180-1"
    ),
    BehaviorVector(
        "abc", {"message_hex": "616263"}, "a9993e364706816aba3e25717850c26c9cd0d89d", "standard", "RFC 3174"
    ),
    BehaviorVector(
        "two-block",
        {"message_hex": b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq".hex()},
        "84983e441c3bd26ebaae4aa1f95129e5e54670f1",
        "standard",
        "RFC 3174",
    ),
)


# --- base64 (RFC 4648) ------------------------------------------------------

_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def base64_encode(data_hex: str) -> str:
    data = bytes.fromhex(data_hex)
    out = []
    for i in range(0, len(data), 3):
        chunk = data[i : i + 3]
        n = len(chunk)
        padded = chunk + b"\x00" * (3 - n)
        v = (padded[0] << 16) | (padded[1] << 8) | padded[2]
        quad = [
            _B64_ALPHABET[(v >> 18) & 0x3F],
            _B64_ALPHABET[(v >> 12) & 0x3F],
            _B64_ALPHABET[(v >> 6) & 0x3F],
            _B64_ALPHABET[v & 0x3F],
        ]
        if n == 1:
            quad[2] = quad[3] = "="
        elif n == 2:
            quad[3] = "="
        out.append("".join(quad))
    return "".join(out)


_B64_SPEC = BehaviorSpec(
    name="base64",
    summary="RFC 4648 base64 encoding with the standard alphabet and '=' padding.",
    inputs="raw bytes (passed hex-encoded)",
    outputs="the base64 text",
    steps=(
        "take the input three bytes at a time",
        "map each 6-bit group through the 64-character alphabet",
        "pad a final 1- or 2-byte group to a quad with '='",
    ),
    references=("RFC 4648 section 4",),
    relies_on_calls=(),
    expects_constants=(),
    expects_strings=("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",),
)

# RFC 4648 section 10 test vectors.
_B64_VECTORS = (
    BehaviorVector("empty", {"data_hex": ""}, "", "standard", "RFC 4648"),
    BehaviorVector("f", {"data_hex": b"f".hex()}, "Zg==", "standard", "RFC 4648"),
    BehaviorVector("fo", {"data_hex": b"fo".hex()}, "Zm8=", "standard", "RFC 4648"),
    BehaviorVector("foo", {"data_hex": b"foo".hex()}, "Zm9v", "standard", "RFC 4648"),
    BehaviorVector("foob", {"data_hex": b"foob".hex()}, "Zm9vYg==", "standard", "RFC 4648"),
    BehaviorVector("fooba", {"data_hex": b"fooba".hex()}, "Zm9vYmE=", "standard", "RFC 4648"),
    BehaviorVector("foobar", {"data_hex": b"foobar".hex()}, "Zm9vYmFy", "standard", "RFC 4648"),
)


_REGISTRY = {
    "md5": (_MD5_SPEC, md5_hex, _MD5_VECTORS),
    "sha1": (_SHA1_SPEC, sha1_hex, _SHA1_VECTORS),
    "base64": (_B64_SPEC, base64_encode, _B64_VECTORS),
}


def available() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def reconstructed(name: str, data_dir: Path | None = None) -> ReconstructedRoutine:
    """Bundle the observation, spec, clean-room model and vectors for one routine."""

    spec, model, vectors = _REGISTRY[name]
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    observation = RoutineObservation.load(root / f"{name}.busybox.json")
    return ReconstructedRoutine(observation=observation, spec=spec, model=model, vectors=vectors)
