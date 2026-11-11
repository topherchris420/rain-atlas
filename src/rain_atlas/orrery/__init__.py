"""PROJECT ORRERY: an independently verified orbital-dynamics instrument for ATLAS.

ORRERY propagates spacecraft and celestial-body states with documented force
models, numerical integrators, time scales and reference frames, and records
how far every prediction is from an independent reference: an analytical
solution, a published reference trajectory (JPL DE421), a published worked
example, or a NASA GMAT R2026a run.

Agreement with GMAT is cross-implementation agreement, never physical
validation. Each module documents its mathematical assumptions in its own
docstring and in ``docs/ORRERY.md``; measured agreement and every known
deviation are recorded in ``docs/ORRERY_VALIDATION.md``.

Units throughout: kilometres, kilometres per second, seconds, radians, unless a
name says otherwise (``_deg``, ``_arcsec``, ``_m``).
"""

from __future__ import annotations

PROTOCOL = "orrery.orbital-dynamics/v1"
ENGINE_VERSION = "1.0.0"

__all__ = ["ENGINE_VERSION", "PROTOCOL"]
