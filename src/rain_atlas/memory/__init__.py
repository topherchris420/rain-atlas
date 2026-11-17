"""Scientific Memory Engine: a Mem0-inspired replica for research context.

Target: Mem0 (Apache-2.0), reconstructed by Recursive Engineering & Analysis.
See ``rain_atlas.rea.investigations.mem0`` for the recorded investigation.

Reference API shape (v1.1+ of the reference SDK)::

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

Deliberate deviations (all recorded in the investigation package):

* fact extraction is rule-based and deterministic, not model-driven;
* memory ids are content-derived (reproducible), not random UUIDs;
* every memory is content-hashed with SHA-256, not MD5;
* scoping accepts one of ``user_id``/``agent_id``/``run_id`` exactly like the
  reference, but adds a scientific ``kind`` and contradiction records.

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
