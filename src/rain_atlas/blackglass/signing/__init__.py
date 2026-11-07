"""Signature backends for BLACK GLASS update verification.

The default backend is the dependency-free Ed25519 reference in
:mod:`.ed25519_ref`. When the ``cryptography`` package is importable, it is
preferred for Ed25519 (and is the only way to verify RSA/ECDSA), but BLACK
GLASS never requires it: absence of a backend yields an explicit
``unsupported`` verification result, never a false ``verified``.
"""

from __future__ import annotations

from . import ed25519_ref

__all__ = ["ed25519_ref", "has_cryptography"]


def has_cryptography() -> bool:
    import importlib.util

    return importlib.util.find_spec("cryptography") is not None
