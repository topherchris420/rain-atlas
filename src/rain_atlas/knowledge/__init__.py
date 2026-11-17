"""Local-First Knowledge Store: an Epicenter-inspired replica.

Target: Epicenter (AGPL-3.0-or-later), reconstructed *without* reusing its
source. See ``rain_atlas.rea.investigations.epicenter`` for the recorded
evidence and licensing rationale.

Reconstructed capabilities:

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
