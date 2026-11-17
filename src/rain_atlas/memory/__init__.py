"""Scientific Memory Engine: persistent research context.

A local-first memory layer for scientific work, with a familiar
SDK-shaped API::

    add(messages, *, user_id, agent_id, run_id, metadata, infer=True)
        -> {"results": [{"id", "memory", "event": "ADD"|"UPDATE"|"DELETE"|"NONE"}]}
    search(query, *, filters, top_k=20, threshold=0.1)
        -> {"results": [{"id", "memory", "score"}]}
    get(memory_id) -> {"id", "memory", "metadata", ...}
    get_all(*, filters) -> {"results": [...]}
    update(memory_id, data) -> {"id", "memory", "event": "UPDATE"}
    delete(memory_id) -> {"id", ...}
    delete_all(*, filters)
    history(memory_id) -> [{"memory_id", "prev_value", "new_value", "event", ...}]

Design choices:

* fact extraction is rule-based and deterministic (no model required);
* memory ids are content-derived, so runs are reproducible;
* every memory is content-hashed with SHA-256;
* scoping accepts one of ``user_id``/``agent_id``/``run_id``;
* scientific ``kind`` labels and contradiction records are first-class.

Scientific memory preserves research decisions, prior experimental results,
rejected hypotheses and evidence-backed corrections. Contradictions are
recorded, never silently resolved: a contradicting update supersedes the old
value but keeps it retrievable through history.
"""

from .engine import ScientificMemory
from .models import Contradiction, MemoryEvent, MemoryRecord
from .store import MemoryStore

__all__ = [
    "Contradiction",
    "MemoryEvent",
    "MemoryRecord",
    "MemoryStore",
    "ScientificMemory",
]
