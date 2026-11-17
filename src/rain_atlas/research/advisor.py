"""Advisors: method survey and hypothesis suggestions. Never evidence, never decisions.

An advisor may *suggest*: which catalogued methods bear on a question, which
grammar terms might explain a diagnostic flag, what a conclusion may have
missed. Every suggestion is validated by deterministic code (only catalogued
methods, only grammar terms, through the scope guard) and recorded with its
generation label. Acceptance, evidence and verdicts never depend on an
advisor's text.

* :class:`ScriptedAdvisor` (default) -- transparent retrieval: Okapi BM25 over
  a curated method catalog and the installed skill catalog, plus a cue table
  that splits the question into sub-questions. Labeled ``scripted``. It is
  retrieval over known methods, not open-ended literature research.
* :class:`OllamaAdvisor` -- an optional local model through the existing
  :class:`~rain_atlas.inference.OllamaProvider`; its JSON is schema-checked and
  unknown methods or terms are discarded (or escalated by the loop). Labeled
  ``model``. If the model is unavailable the scripted advisor answers instead,
  and the record says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..inference import OllamaProvider, ProviderError
from ..inference.structured import StructuredOutputError, extract_structured
from ..memory.search import okapi_bm25
from .oscillator import EXPANSION, LIBRARY, TERM_MEANING

SUBQUESTIONS = (
    ("detect-change", ("detect", "change", "unknown"), "Has the system changed, and when?"),
    ("attribute-change", ("what", "changed", "determine"), "Which part of the dynamics changed?"),
    (
        "explain",
        ("explanatory", "model", "develop", "better"),
        "Which model structure explains the observations?",
    ),
    (
        "efficiency",
        ("fewer", "experiments", "conventional"),
        "Does adaptive selection need fewer experiments than conventional designs?",
    ),
    (
        "noise",
        ("noisy", "noise", "uncertain"),
        "How much of the variation is noise, and is the noise model right?",
    ),
)

METHODS: tuple[dict, ...] = (
    {
        "id": "nig-evidence",
        "name": "Exact Bayesian model evidence (Normal-Inverse-Gamma linear regression)",
        "answers": ["explain", "efficiency"],
        "implemented_by": "rain_atlas.research.inference",
        "text": "compare competing model structures explanation evidence marginal likelihood bayes factor regression",
    },
    {
        "id": "change-point-evidence",
        "name": "Bayesian change-point and attribution hypotheses",
        "answers": ["detect-change", "attribute-change"],
        "implemented_by": "rain_atlas.research.inference",
        "text": "detect unknown change shift abrupt changed coefficients when what changed segment",
    },
    {
        "id": "sequential-design",
        "name": "Sequential Bayesian experimental design (expected information gain)",
        "answers": ["efficiency"],
        "implemented_by": "rain_atlas.research.planner",
        "text": "choose next experiment fewer experiments adaptive design information gain discriminate",
    },
    {
        "id": "lagrange-multiplier-test",
        "name": "Score (Lagrange-multiplier) test for omitted terms",
        "answers": ["explain"],
        "implemented_by": "rain_atlas.research.critic",
        "text": "model inadequacy missing term omitted variable residual unfamiliar dynamics new term",
    },
    {
        "id": "ljung-box",
        "name": "Ljung-Box residual whiteness test",
        "answers": ["explain"],
        "implemented_by": "rain_atlas.research.critic",
        "text": "residual autocorrelation unexplained dynamics model inadequate white noise",
    },
    {
        "id": "kurtosis-test",
        "name": "Kurtosis test of the Gaussian-noise assumption",
        "answers": ["noise"],
        "implemented_by": "rain_atlas.research.critic",
        "text": "noise assumption heavy tailed outliers gaussian noisy observations incorrect assumption",
    },
    {
        "id": "huber-irls",
        "name": "Huber M-estimation (robust regression)",
        "answers": ["noise", "explain"],
        "implemented_by": "rain_atlas.research.critic",
        "text": "robust estimator outliers heavy tails independent estimator noisy",
    },
    {
        "id": "cross-validation",
        "name": "Leave-experiments-out cross-validated prediction",
        "answers": ["explain"],
        "implemented_by": "rain_atlas.research.critic",
        "text": "independent check out of sample prediction held out better model",
    },
    {
        "id": "chow-test",
        "name": "Chow test for coefficient equality across segments",
        "answers": ["detect-change", "attribute-change"],
        "implemented_by": "rain_atlas.research.critic",
        "text": "classical change test coefficients differ before after segment structural break",
    },
    {
        "id": "d-optimal-design",
        "name": "Sequential D-optimal design under the prior (open loop)",
        "answers": ["efficiency"],
        "implemented_by": "rain_atlas.research.planner",
        "text": "conventional optimal experimental design precomputed fixed schedule baseline fewer experiments",
    },
    {
        "id": "stepped-sine-sweep",
        "name": "Stepped-sine frequency sweep (fixed schedule)",
        "answers": ["efficiency"],
        "implemented_by": "rain_atlas.research.planner",
        "text": "conventional frequency sweep fixed schedule baseline method resonance",
    },
    {
        "id": "linear-least-squares",
        "name": "Linear least-squares system identification (conventional model)",
        "answers": ["explain"],
        "implemented_by": "rain_atlas.research.benchmark",
        "text": "conventional linear model system identification baseline explanatory",
    },
)

PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["terms", "rationale"],
    "properties": {
        "terms": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 4},
        "rationale": {"type": "string", "maxLength": 2000},
    },
}
SURVEY_SCHEMA = {
    "type": "object",
    "required": ["methods", "rationale"],
    "properties": {
        "methods": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 12},
        "rationale": {"type": "string", "maxLength": 3000},
    },
}


@dataclass
class _Doc:
    id: str
    content: str


def decompose(question: str) -> list[dict]:
    words = set(question.lower().replace("?", " ").replace(",", " ").split())
    out = []
    for key, cues, text in SUBQUESTIONS:
        hits = sorted(words & set(cues))
        if hits:
            out.append({"id": key, "question": text, "cues": hits})
    return out


class ScriptedAdvisor:
    generation = "scripted"
    name = "scripted retrieval"

    def __init__(self, skills: list[dict] | None = None):
        self.skills = skills or []

    def survey(self, question: str) -> dict:
        parts = decompose(question)
        docs = [_Doc(m["id"], m["name"] + " " + m["text"]) for m in METHODS]
        docs += [
            _Doc(
                "skill:" + s["name"],
                s["name"] + " " + s.get("summary", "") + " " + " ".join(s.get("capabilities", [])),
            )
            for s in self.skills
        ]
        scores = okapi_bm25(question, docs)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        relevant_skills = [
            {"skill": k.split(":", 1)[1], "score": round(v, 3)}
            for k, v in ranked
            if k.startswith("skill:") and v > 0
        ][:6]
        chosen = []
        for m in METHODS:
            covers = [p["id"] for p in parts if p["id"] in m["answers"]]
            if covers:
                chosen.append(
                    {
                        "method": m["id"],
                        "name": m["name"],
                        "answers": covers,
                        "implemented_by": m["implemented_by"],
                        "retrieval_score": round(scores.get(m["id"], 0.0), 3),
                    }
                )
        return {
            "generation": self.generation,
            "advisor": self.name,
            "subquestions": parts,
            "methods": chosen,
            "related_skills": relevant_skills,
            "note": "retrieval over a curated method catalog and the installed skill catalog; "
            "not open-ended literature research",
        }

    def propose_terms(self, context: dict) -> dict:
        lm = context.get("diagnostics", {}).get("lm_tests", [])
        terms = [r["term"] for r in lm if r.get("p", 1.0) < 0.05][:2]
        return {
            "terms": terms,
            "generation": self.generation,
            "rationale": "terms whose score test is nominally significant (p < 0.05)",
        }


class OllamaAdvisor:
    """A local language model as advisor; validated, labeled, replaceable by the scripted advisor."""

    generation = "model"

    def __init__(
        self, url: str, model: str, *, fallback: ScriptedAdvisor | None = None, timeout_s: float = 30.0
    ):
        self.provider = OllamaProvider(url, timeout_s=timeout_s)
        self.model = model
        self.fallback = fallback or ScriptedAdvisor()
        self.name = f"ollama:{model}"
        self.failures: list[str] = []

    def _ask(self, prompt: str, schema: dict) -> tuple[dict | None, str]:
        try:
            result = self.provider.complete(prompt, model=self.model)
        except ProviderError as exc:
            self.failures.append(str(exc))
            return None, f"provider unavailable: {exc}"
        try:
            return extract_structured(result, schema), ""
        except StructuredOutputError as exc:
            self.failures.append(str(exc))
            return None, f"invalid structured output: {exc}"

    def survey(self, question: str) -> dict:
        base = self.fallback.survey(question)
        catalog = "\n".join(f"- {m['id']}: {m['name']}" for m in METHODS)
        prompt = (
            "You advise a research system. Choose the methods from this catalog that bear on the question. "
            'Answer only JSON: {"methods": [ids], "rationale": "..."}\n'
            f"Question: {question}\nCatalog:\n{catalog}\n"
        )
        answer, problem = self._ask(prompt, SURVEY_SCHEMA)
        if answer is None:
            base["model"] = {"used": False, "reason": problem}
            return base
        known = {m["id"] for m in METHODS}
        base["model"] = {
            "used": True,
            "generation": "model",
            "model": self.model,
            "suggested": [m for m in answer["methods"] if m in known],
            "discarded": [m for m in answer["methods"] if m not in known],
            "rationale": answer["rationale"],
        }
        return base

    def propose_terms(self, context: dict) -> dict:
        grammar = "\n".join(f"- {t}: {TERM_MEANING[t]}" for t in LIBRARY if t in EXPANSION)
        prompt = (
            "A dynamical model fails a diagnostic. Suggest at most two terms from the grammar that could "
            'explain the misfit. Answer only JSON: {"terms": [...], "rationale": "..."}\n'
            f"Leading model: {context.get('leading')}\nDiagnostics: {context.get('diagnostics')}\n"
            f"Grammar:\n{grammar}\n"
        )
        answer, problem = self._ask(prompt, PROPOSAL_SCHEMA)
        if answer is None:
            out = self.fallback.propose_terms(context)
            out["rationale"] = f"model unavailable ({problem}); scripted fallback: {out['rationale']}"
            return out
        return {"terms": list(answer["terms"]), "generation": "model", "rationale": answer["rationale"]}


def make_advisor(charter: dict, skills: list[dict] | None = None) -> Any:
    provider = charter["environment"]["model_provider"]
    scripted = ScriptedAdvisor(skills)
    if provider and provider.get("kind") == "ollama":
        return OllamaAdvisor(provider["url"], provider["model"], fallback=scripted)
    return scripted
