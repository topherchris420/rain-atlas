"""BM25 lemmatization for consistent keyword matching.

Vendored from Mem0 (Apache-2.0), commit f1791da86d469249c9b002f62644d58a1eb96a0,
``mem0/utils/lemmatization.py``. Adaptation: the ``mem0.utils.spacy_models``
loader is replaced by a direct optional spaCy import with the same fallback
(returns the original text when spaCy is unavailable). Logic preserved.

Uses spaCy's lemmatizer for better handling of:
- Verb forms: attending/attends/attended -> attend
- Comparatives/superlatives: older/oldest -> old
- Plurals: memories -> memory
- Avoids over-stemming: organization != organize

Also includes original -ing forms alongside lemmas to handle cases
where spaCy's context-dependent lemmatization produces inconsistent
results (e.g., "meeting" as noun vs verb -> different lemmas).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def lemmatize_for_bm25(text: str) -> str:
    """Lemmatize text for BM25 matching.

    Returns space-joined lemmas for full-text search. Falls back to
    the original text if spaCy is unavailable.
    """
    try:
        import spacy  # noqa: PLC0415 - optional dependency

        nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
    except Exception:  # noqa: BLE001 - spaCy or the model may be absent
        return text

    doc = nlp(text.lower())
    tokens = []

    for token in doc:
        if token.is_punct or token.is_stop:
            continue

        lemma = token.lemma_
        if lemma.isalnum():
            tokens.append(lemma)

        # Also add original if it ends in -ing and differs from lemma.
        # This handles noun/verb ambiguity (meeting/meet, attending/attend).
        if token.text.endswith("ing") and token.text != lemma and token.text.isalnum():
            tokens.append(token.text)

    return " ".join(tokens)
