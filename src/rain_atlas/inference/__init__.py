"""Local Inference Engine: replaceable model providers.

Capabilities:

* replaceable model providers behind one interface
  (:class:`InferenceProvider`);
* deterministic :class:`MockProvider` used by tests and demonstrations --
  no model account, no network, no GPU;
* optional local HTTP providers (Ollama / llama.cpp-compatible OpenAI
  endpoints) that are exercised only when their server is reachable;
* structured outputs: JSON constrained to a declared schema
  (validated with the engine's lightweight JSON-Schema subset);
* tool-calling declarations;
* every generation is separable from deterministic execution evidence:
  the provider records usage that the observability layer attaches to
  GENERATION observations, so nondeterministic model output is never
  confused with computed results.
"""

from .providers import (
    InferenceProvider,
    LlamaCppProvider,
    MockProvider,
    OllamaProvider,
    ProviderError,
    discover_providers,
)
from .structured import extract_structured

__all__ = [
    "InferenceProvider",
    "LlamaCppProvider",
    "MockProvider",
    "OllamaProvider",
    "ProviderError",
    "discover_providers",
    "extract_structured",
]
