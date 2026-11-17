"""Local-First Knowledge Store.

Capabilities:

* local-first storage: every document is a file under the user's control;
* append-only version history per document (nothing is silently overwritten);
* portable state: export and import complete stores as canonical JSON;
* conflict resolution across replicas of the same store: divergent edits
  are detected, and resolution keeps both versions in history with an
  explicit resolution record;
* provenance: every version records its author, timestamp and content hash.
"""

from .store import Conflict, Document, KnowledgeStore, Resolution

__all__ = ["Conflict", "Document", "KnowledgeStore", "Resolution"]
