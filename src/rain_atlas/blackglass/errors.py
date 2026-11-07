"""Typed errors for the BLACK GLASS firmware-analysis subsystem.

Every failure mode the subsystem can reach has an explicit type so callers can
distinguish *unsupported input* (a limitation we state plainly) from *malformed
input* (a refusal) from an internal contract violation (a bug). BLACK GLASS
never silently degrades: an input it cannot analyse is reported, never guessed.
"""

from __future__ import annotations


class BlackGlassError(RuntimeError):
    """Base class for every BLACK GLASS failure."""


class IngestError(BlackGlassError):
    """A firmware archive or tree could not be imported safely.

    Raised for path traversal, symlink escape, oversized or over-populated
    archives, and other integrity problems in the *container*. It does not mean
    the firmware is malicious, only that we will not extract it blindly.
    """


class UnsupportedInput(BlackGlassError):
    """A recognised-but-unsupported input: a stated limitation, not a crash.

    Example: an on-disk format BLACK GLASS does not parse (squashfs, raw NAND),
    or an encrypted blob with no supplied key. Callers surface this to the
    operator with guidance; analysis continues for the parts that are supported.
    """
