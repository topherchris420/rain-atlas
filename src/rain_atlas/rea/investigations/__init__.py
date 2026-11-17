"""Recorded REA investigations of the nine research targets.

Each module returns an :class:`~rain_atlas.rea.models.Investigation` built
from recorded evidence. Evidence classifications are enforced at package
build time; inferred behavior is never presented as observed.

Reference snapshots (cloned under authorized terms, 2026-11-16):

* mem0 — commit ``f1791daa86d469249c9b002f62644d58a1eb96a0`` (Apache-2.0)
* langfuse — commit ``01e7f5f746b15493d18fe06b24ae06ac08d5ae74`` (MIT core)
* browser-use — commit ``4b5b1b0aa0ab45a1d6a2a31984d37d3e748c0134`` (MIT)
* omnara — commit ``f7d05d06c1aa3fe50cee90e1e7ff1e843df0f947`` (Apache-2.0)
* runanywhere-sdks — commit ``87865ea825d131498cf255b129ae81f26449e637``
* epicenter — commit ``206ca98824fe1861c311395e47f55501cba6d5e8`` (AGPL-3.0-or-later)
* maxxwell — public documentation site (docs.maxxwell.dev, fetched 2026-11-16)
* arga labs — public website and documentation (argalabs.com, fetched 2026-11-16)
* infera — public website (infera.bio, fetched 2026-11-16)
"""

from __future__ import annotations

from ..models import Investigation
from . import (
    arga,
    browser_use,
    epicenter,
    infera,
    langfuse,
    maxxwell,
    mem0,
    omnara,
    runanywhere,
)

_MODULES = {
    "T01-mem0": mem0,
    "T02-langfuse": langfuse,
    "T03-browser-use": browser_use,
    "T04-omnara": omnara,
    "T05-runanywhere": runanywhere,
    "T06-epicenter": epicenter,
    "T07-maxxwell": maxxwell,
    "T08-arga-labs": arga,
    "T09-infera": infera,
}

TARGET_ORDER = tuple(_MODULES)


def investigation(target_id: str) -> Investigation:
    """Return the recorded investigation for one target."""

    try:
        module = _MODULES[target_id]
    except KeyError:
        raise KeyError(f"unknown target {target_id!r}; expected one of {TARGET_ORDER}") from None
    return module.investigation()


def all_investigations() -> list[Investigation]:
    return [investigation(target_id) for target_id in TARGET_ORDER]


__all__ = ["TARGET_ORDER", "all_investigations", "investigation"]
