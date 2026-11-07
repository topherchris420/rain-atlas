"""A compact, dependency-free Ed25519 implementation (RFC 8032).

This exists so BLACK GLASS can *verify* update signatures with no third-party
dependency, which keeps the reproducible demonstration and the test suite
self-contained. It is a straightforward transcription of the RFC 8032 reference
algorithm using extended coordinates.

Scope and caveats, stated plainly:

* It is used for **verification** (and for generating demo fixtures). Signature
  verification is a public operation, so the constant-time concerns that apply
  to secret-key operations do not apply to the verification path.
* It is **not** a hardened, side-channel-resistant signing library. For
  production signing, or for RSA/ECDSA, install ``cryptography``; BLACK GLASS
  prefers that backend automatically when it is importable.
* Correctness is pinned by the official RFC 8032 known-answer vectors in the
  test suite, so a regression here fails CI even without ``cryptography``.
"""

from __future__ import annotations

import hashlib

p = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493


def _modp_inv(x: int) -> int:
    return pow(x, p - 2, p)


_d = (-121665 * _modp_inv(121666)) % p
_sqrt_m1 = pow(2, (p - 1) // 4, p)


def _recover_x(y: int, sign: int) -> int | None:
    if y >= p:
        return None
    x2 = (y * y - 1) * _modp_inv(_d * y * y + 1) % p
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * _sqrt_m1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_g_y = (4 * _modp_inv(5)) % p
_g_x = _recover_x(_g_y, 0)
_G = (_g_x, _g_y, 1, _g_x * _g_y % p)


def _point_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * _d % p
    D = 2 * P[2] * Q[2] % p
    E, F, Gg, Hh = B - A, D - C, D + C, B + A
    return (E * F % p, Gg * Hh % p, F * Gg % p, E * Hh % p)


def _point_mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _point_add(Q, P)
        P = _point_add(P, P)
        s >>= 1
    return Q


def _point_equal(P, Q) -> bool:
    if (P[0] * Q[2] - Q[0] * P[2]) % p != 0:
        return False
    if (P[1] * Q[2] - Q[1] * P[2]) % p != 0:
        return False
    return True


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _sha512_modL(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little") % L


def _point_compress(P) -> bytes:
    zinv = _modp_inv(P[2])
    x = P[0] * zinv % p
    y = P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _point_decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % p)


def _secret_expand(secret: bytes) -> tuple[int, bytes]:
    if len(secret) != 32:
        raise ValueError("Ed25519 secret seed must be 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    """Derive the 32-byte public key from a 32-byte secret seed."""

    a, _ = _secret_expand(secret)
    return _point_compress(_point_mul(a, _G))


def sign(secret: bytes, msg: bytes) -> bytes:
    """Return the 64-byte Ed25519 signature of *msg* under secret seed *secret*."""

    a, prefix = _secret_expand(secret)
    a_pub = _point_compress(_point_mul(a, _G))
    r = _sha512_modL(prefix + msg)
    big_r = _point_mul(r, _G)
    rs = _point_compress(big_r)
    k = _sha512_modL(rs + a_pub + msg)
    s = (r + k * a) % L
    return rs + int.to_bytes(s, 32, "little")


def verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    """Return ``True`` iff *signature* is a valid Ed25519 signature of *msg*."""

    if len(public) != 32 or len(signature) != 64:
        return False
    a_point = _point_decompress(public)
    if a_point is None:
        return False
    rs = signature[:32]
    big_r = _point_decompress(rs)
    if big_r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    k = _sha512_modL(rs + public + msg)
    s_b = _point_mul(s, _G)
    k_a = _point_mul(k, a_point)
    return _point_equal(s_b, _point_add(big_r, k_a))
