"""Scientific Protocol Compiler.

Converts a research question and a hypothesis into an explicit, validated
:class:`ProtocolSpec` (mirroring the compile-validate-approve discipline):

* variables with bounds and instruments are extracted from a declared
  lexicon (deterministic template matching, not a language model);
* every step references a declared simulated instrument;
* acceptance criteria are preregistered before execution;
* safety constraints forbid physical actuation: only simulated
  instruments may appear in a protocol.
"""

from .compiler import ProtocolCompiler, ProtocolSpec, ProtocolStep, ValidationError

__all__ = ["ProtocolCompiler", "ProtocolSpec", "ProtocolStep", "ValidationError"]
