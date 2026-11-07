"""A controlled, read-only interface for investigating a stored analysis.

Scientific agents (and people) query an :class:`AnalysisReport` through this
class without being able to mutate it. It loads the canonical analysis JSON
(as written by the CLI or stored in the ledger) and answers structured
questions — list components, resolve a finding to its evidence, walk the graph —
so investigation never changes the evidence it examines.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .model import CONFIDENCE, AnalysisReport


class Inspector:
    """Read-only view over an analysis report."""

    def __init__(self, data: dict | AnalysisReport):
        raw = asdict(data) if isinstance(data, AnalysisReport) else dict(data)
        # Expose an immutable mapping so callers cannot mutate the evidence.
        self._data = MappingProxyType(json.loads(json.dumps(raw)))

    @classmethod
    def from_json(cls, path: Path) -> "Inspector":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def image(self) -> dict:
        return dict(self._data["image"])

    @property
    def counts(self) -> dict:
        return dict(self._data["counts"])

    def components(self, kind: str | None = None) -> list[dict]:
        return [dict(c) for c in self._data["components"] if kind is None or c["kind"] == kind]

    def component(self, path: str) -> dict | None:
        return next((dict(c) for c in self._data["components"] if c["path"] == path), None)

    def services(self) -> list[dict]:
        return [dict(s) for s in self._data["services"]]

    def service(self, service_id: str) -> dict | None:
        return next((dict(s) for s in self._data["services"] if s["id"] == service_id), None)

    def _min_conf(self, confidence: str, floor: str) -> bool:
        return CONFIDENCE.index(confidence) <= CONFIDENCE.index(floor)

    def network(self, max_confidence: str | None = None) -> list[dict]:
        items = [dict(n) for n in self._data["network"]]
        if max_confidence is None:
            return items
        return [n for n in items if self._min_conf(n["confidence"], max_confidence)]

    def findings(self, kind: str | None = None, min_confidence: str | None = None) -> list[dict]:
        out = []
        for f in self._data["findings"]:
            if kind is not None and f["kind"] != kind:
                continue
            if min_confidence is not None and not self._min_conf(f["confidence"], min_confidence):
                continue
            out.append(dict(f))
        return out

    def finding(self, finding_id: str) -> dict | None:
        return next((dict(f) for f in self._data["findings"] if f["id"] == finding_id), None)

    def evidence_for(self, finding_id: str) -> list[dict]:
        f = self.finding(finding_id)
        return list(f["evidence"]) if f else []

    def graph_neighbors(self, node_id: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {"out": [], "in": []}
        for edge in self._data["graph"]["edges"]:
            if edge["src"] == node_id:
                out["out"].append(f"{edge['kind']}->{edge['dst']}")
            if edge["dst"] == node_id:
                out["in"].append(f"{edge['src']}-{edge['kind']}->")
        out["out"].sort()
        out["in"].sort()
        return out

    def query(self, question: str, **kwargs: Any) -> Any:
        """Dispatch a named read-only query. Unknown queries raise, never guess."""

        table = {
            "components": lambda: self.components(kwargs.get("kind")),
            "services": self.services,
            "network": lambda: self.network(kwargs.get("max_confidence")),
            "findings": lambda: self.findings(kwargs.get("kind"), kwargs.get("min_confidence")),
            "counts": lambda: self.counts,
            "image": lambda: self.image,
        }
        if question not in table:
            raise KeyError(f"unknown query {question!r}; available: {sorted(table)}")
        return table[question]()
