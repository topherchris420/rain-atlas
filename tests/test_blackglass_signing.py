"""Ed25519 reference implementation: known-answer vectors, round trips, tamper."""

from __future__ import annotations

import importlib.util

import pytest

from rain_atlas.blackglass.signing import ed25519_ref as ed

# A known-answer vector validated against the `cryptography` library (an
# independent RFC 8032 implementation). Pins correctness with no dependency.
KAT_SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
KAT_PUB = bytes.fromhex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
KAT_MSG = b"BLACK GLASS firmware update manifest v1"
KAT_SIG = bytes.fromhex(
    "ba1971c0a1e43724cfa470d2f518fa7efe4bd1d798c7a80d5e1026bcd2df683a"
    "3c7694a910cf7daed223b4f323baf6fc70113217b03d32ca581f6f9b864e2903"
)


def test_known_answer_vector():
    assert ed.public_key(KAT_SEED) == KAT_PUB
    assert ed.sign(KAT_SEED, KAT_MSG) == KAT_SIG
    assert ed.verify(KAT_PUB, KAT_MSG, KAT_SIG) is True


def test_round_trip_and_tamper():
    seed = bytes(range(31, -1, -1))
    pub = ed.public_key(seed)
    msg = b"update payload v2"
    sig = ed.sign(seed, msg)
    assert ed.verify(pub, msg, sig)
    # flipped message byte
    assert not ed.verify(pub, b"update payload v3", sig)
    # flipped signature byte
    bad = bytearray(sig)
    bad[10] ^= 0x40
    assert not ed.verify(pub, msg, bytes(bad))
    # wrong key
    assert not ed.verify(ed.public_key(bytes(32)), msg, sig)


def test_rejects_malformed_inputs():
    assert ed.verify(b"short", KAT_MSG, KAT_SIG) is False
    assert ed.verify(KAT_PUB, KAT_MSG, b"short") is False


@pytest.mark.skipif(importlib.util.find_spec("cryptography") is None, reason="cryptography not installed")
def test_matches_cryptography():
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    for _ in range(10):
        seed = os.urandom(32)
        sk = Ed25519PrivateKey.from_private_bytes(seed)
        msg = os.urandom(37)
        assert ed.public_key(seed) == sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        assert ed.sign(seed, msg) == sk.sign(msg)
