"""Provider abstraction: deterministic mock plus optional local HTTP engines."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """A provider failed to answer; deterministic execution continues."""


@dataclass
class GenerationResult:
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    structured: Any = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "structured": self.structured,
        }


class InferenceProvider:
    """Interface every provider implements."""

    name = "abstract"

    def complete(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> GenerationResult:
        raise NotImplementedError

    def discover(self) -> list[dict[str, Any]]:
        """Report available models (model discovery)."""

        raise NotImplementedError


class MockProvider(InferenceProvider):
    """Deterministic rule-based provider: tests and offline demonstrations.

    Answers follow a small transparent grammar:

    * ``propose: <lexicon phrase>`` → a hypothesis proposal among known terms;
    * ``classify: <statement>`` → labels a statement hypothesis/finding/…;
    * anything else is echoed with a ``mock:`` prefix.

    Determinism: the same prompt always returns the same text.
    """

    name = "mock"

    def __init__(self, vocabulary: list[str] | None = None) -> None:
        self.vocabulary = list(vocabulary or [])
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> GenerationResult:
        self.calls.append(prompt)
        text = self._answer(prompt)
        words = len(prompt.split()) + len(text.split())
        return GenerationResult(
            text=text,
            model=model or "mock-reasoner-1",
            provider=self.name,
            usage={"input": len(prompt.split()), "output": len(text.split()), "total": words},
        )

    def _answer(self, prompt: str) -> str:
        prompt = prompt.strip()
        if prompt.startswith("propose:"):
            if self.vocabulary:
                # Deterministic pick: the vocabulary term with the most
                # character overlap with the prompt context.
                context = prompt[len("propose:") :].lower()
                best = max(
                    self.vocabulary,
                    key=lambda term: len(set(term.split()) & set(context.split())) or -len(term),
                )
                return f"Hypothesis: increasing {best} improves phase locking."
            return "Hypothesis: increasing coupling strength improves phase locking."
        if prompt.startswith("classify:"):
            statement = prompt[len("classify:") :].strip().lower()
            for kind, cues in (
                ("hypothesis", ("hypothes", "predict", "expect", "propose")),
                ("finding", ("found", "observed", "result", "measurement")),
                ("decision", ("decided", "choose", "select")),
                ("rejection", ("reject", "discard", "refuted")),
            ):
                if any(cue in statement for cue in cues):
                    return kind
            return "fact"
        return f"mock: {prompt}"

    def discover(self) -> list[dict[str, Any]]:
        return [{"model": "mock-reasoner-1", "provider": "mock", "local": True}]


class _HttpJsonProvider(InferenceProvider):
    """Shared HTTP behavior for local OpenAI-compatible endpoints."""

    def __init__(self, base_url: str, *, timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ProviderError(f"{self.name} at {self.base_url} unavailable: {exc}") from exc

    def _get(self, path: str) -> Any:
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ProviderError(f"{self.name} at {self.base_url} unavailable: {exc}") from exc


class OllamaProvider(_HttpJsonProvider):
    """Optional local Ollama runtime (http://localhost:11434 by default)."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)

    def complete(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> GenerationResult:
        model = model or "llama3.2"
        payload = self._post(
            "/api/generate",
            {"model": model, "prompt": prompt, "stream": False},
        )
        text = str(payload.get("response", ""))
        return GenerationResult(
            text=text,
            model=model,
            provider=self.name,
            usage={
                "input": int(payload.get("prompt_eval_count", 0)),
                "output": int(payload.get("eval_count", 0)),
                "total": int(payload.get("prompt_eval_count", 0)) + int(payload.get("eval_count", 0)),
            },
        )

    def discover(self) -> list[dict[str, Any]]:
        payload = self._get("/api/tags")
        return [
            {"model": entry.get("name", ""), "provider": "ollama", "local": True}
            for entry in payload.get("models", [])
        ]


class LlamaCppProvider(_HttpJsonProvider):
    """Optional llama.cpp OpenAI-compatible server (http://localhost:8080)."""

    name = "llamacpp"

    def __init__(self, base_url: str = "http://localhost:8080", **kwargs: Any) -> None:
        super().__init__(base_url + "/v1", **kwargs)

    def complete(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> GenerationResult:
        payload = self._post(
            "/chat/completions",
            {
                "model": model or "local-model",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        choices = payload.get("choices") or [{}]
        text = str((choices[0].get("message") or {}).get("content", ""))
        usage = payload.get("usage") or {}
        return GenerationResult(
            text=text,
            model=model or "local-model",
            provider=self.name,
            usage={
                "input": int(usage.get("prompt_tokens", 0)),
                "output": int(usage.get("completion_tokens", 0)),
                "total": int(usage.get("total_tokens", 0)),
            },
        )

    def discover(self) -> list[dict[str, Any]]:
        payload = self._get("/models")
        return [
            {"model": entry.get("id", ""), "provider": "llamacpp", "local": True}
            for entry in payload.get("data", [])
        ]


def discover_providers(*, include_http: bool = True, http_timeout_s: float = 0.5) -> list[dict[str, Any]]:
    """Model discovery across providers. HTTP providers are probed briefly.

    Returns the models of every reachable provider; the mock provider is
    always present, keeping scientific evaluations reproducible without a
    model. Unreachable providers are simply absent, never errors.
    """

    found: list[dict[str, Any]] = MockProvider().discover()
    if include_http:
        for provider in (
            OllamaProvider(timeout_s=http_timeout_s),
            LlamaCppProvider(timeout_s=http_timeout_s),
        ):
            try:
                found.extend(provider.discover())
            except ProviderError:
                continue
    return found
