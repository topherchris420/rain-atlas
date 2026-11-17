"""Vendored Mem0 retrieval scoring (Apache-2.0).

Source: https://github.com/mem0ai/mem0 (commit f1791da86d469249c9b002f62644d58a1eb96a0)
Files: mem0/utils/scoring.py, mem0/utils/lemmatization.py

Adaptations (recorded per the REA investigation T01):
* absolute imports on ``mem0.*`` replaced with local relative imports;
* ``mem0.utils.spacy_models`` replaced by a direct optional spaCy import;
* the ``explain`` score_details branch is preserved unchanged.

The scoring logic itself is the reference implementation, preserved so the
replica's hybrid ranking is the reference's math, not a re-implementation.
"""

from .lemmatization import lemmatize_for_bm25
from .scoring import ENTITY_BOOST_WEIGHT, get_bm25_params, normalize_bm25, score_and_rank

__all__ = [
    "ENTITY_BOOST_WEIGHT",
    "get_bm25_params",
    "lemmatize_for_bm25",
    "normalize_bm25",
    "score_and_rank",
]
