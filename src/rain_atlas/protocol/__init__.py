"""Scientific Protocol Compiler: an Infera-inspired replica.

Target: Infera (closed source; behavior reconstructed from public
documentation only), reconstructed by Recursive Engineering & Analysis.
See ``rain_atlas.rea.investigations.infera`` for the recorded evidence.

The reference's "Project IO" converts a plain-English workflow into
instrument instructions, validates it on digital twins and requires human
approval before execution. This replica compiles a research question and a
hypothesis into an explicit, validated :class:`ProtocolSpec`:

* variables with bounds and instruments are extracted from a declared
  lexicon (deterministic template matching, not a language model);
* every step references a declared simulated instrument;
* acceptance criteria are preregistered before execution;
* safety constraints forbid physical actuation: only simulated
  instruments may appear in a protocol.
"""

from .compiler import ProtocolCompiler, ProtocolSpec, ProtocolStep, ValidationError

__all__ = ["ProtocolCompiler", "ProtocolSpec", "ProtocolStep", "ValidationError"]
