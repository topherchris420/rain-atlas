"""Scope guard: autonomy inside the approved charter, escalation outside it.

Every action the research loop takes passes through :class:`ScopeGuard`.
Inside the charter the guard simply allows it. Outside, it raises
:class:`ScopeViolation` carrying an *escalation request*; the loop records the
request and pauses. Only a separate human authorization (an ``authorization``
ledger record naming the request) can widen the scope, and only for the kinds
of change this build can actually perform:

* more experiments for one mission (bounded by the charter's per-request cap);
* a wider design space for one mission;
* additional hypothesis-grammar terms (from the fixed term library).

Hardware control, untrusted code execution and unapproved network access have
no execution path in this build. Requests for them are recorded and can be
answered, but an approval changes nothing and the guard keeps refusing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import sha256_json
from .oscillator import DEFAULT_SPACE, LIBRARY, Design

GRANTABLE = ("budget-extension", "design-space", "grammar-term")
NOT_GRANTABLE = ("hardware-control", "untrusted-code", "network", "skill-install")


@dataclass
class EscalationRequest:
    kind: str
    mission: str
    reason: str
    requested: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def request_id(self) -> str:
        return sha256_json({"kind": self.kind, "mission": self.mission, "requested": self.requested})[7:23]

    @property
    def grantable(self) -> bool:
        return self.kind in GRANTABLE

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "kind": self.kind,
            "mission": self.mission,
            "reason": self.reason,
            "requested": self.requested,
            "evidence": self.evidence,
            "grantable": self.grantable,
        }


class ScopeViolation(Exception):
    def __init__(self, request: EscalationRequest):
        super().__init__(f"{request.kind}: {request.reason}")
        self.request = request


class ScopeGuard:
    """Checks actions against a charter plus any human authorizations."""

    def __init__(self, charter: dict, mission: str, authorizations: list[dict] | None = None):
        self.charter = charter
        self.mission = mission
        self.authorizations = [
            a
            for a in (authorizations or [])
            if a.get("mission") == mission and a.get("decision") == "approve"
        ]
        self.denials: list[str] = []
        self.model_calls = 0

    # -- budgets ----------------------------------------------------------------
    def experiment_budget(self) -> int:
        base = int(self.charter["budgets"]["experiments_per_mission"])
        extra = sum(
            int(a["granted"].get("experiments", 0))
            for a in self.authorizations
            if a["kind"] == "budget-extension"
        )
        return base + extra

    def check_experiment(self, used: int) -> None:
        budget = self.experiment_budget()
        if used >= budget:
            raise ScopeViolation(
                EscalationRequest(
                    "budget-extension",
                    self.mission,
                    f"all {budget} approved experiments are used",
                    {"experiments": int(self.charter["budgets"]["max_extension_per_request"])},
                )
            )

    # -- design space -----------------------------------------------------------
    def space(self) -> dict:
        space = {k: tuple(v) for k, v in self.charter["design_space"].items()}
        for a in self.authorizations:
            if a["kind"] == "design-space":
                for key, (lo, hi) in a["granted"].get("design_space", {}).items():
                    if key in DEFAULT_SPACE:
                        space[key] = (min(space[key][0], lo), max(space[key][1], hi))
        return space

    def check_design(self, design: Design) -> None:
        if not design.within(self.space()):
            raise ScopeViolation(
                EscalationRequest(
                    "design-space",
                    self.mission,
                    f"design {design.label()} is outside the approved design space",
                    {"design": design.to_dict()},
                )
            )

    # -- hypothesis grammar -----------------------------------------------------
    def grammar_terms(self) -> tuple[str, ...]:
        g = self.charter["hypothesis_grammar"]
        terms = set(g["core"]) | set(g["optional"]) | set(g["expansion"])
        for a in self.authorizations:
            if a["kind"] == "grammar-term":
                terms |= set(a["granted"].get("terms", []))
        return tuple(t for t in LIBRARY if t in terms)

    def check_term(self, term: str) -> None:
        if term not in LIBRARY:
            raise ScopeViolation(
                EscalationRequest(
                    "untrusted-code",
                    self.mission,
                    f"proposed term {term!r} is not in the term library; executing it would require new code",
                    {"term": term},
                )
            )
        if term not in self.grammar_terms():
            raise ScopeViolation(
                EscalationRequest(
                    "grammar-term",
                    self.mission,
                    f"term {term!r} is outside the approved grammar",
                    {"terms": [term]},
                )
            )

    # -- environment ------------------------------------------------------------
    def check_model_call(self) -> None:
        provider = self.charter["environment"]["model_provider"]
        if provider is None:
            raise ScopeViolation(
                EscalationRequest("network", self.mission, "no model provider is approved in this charter")
            )
        if self.model_calls >= int(self.charter["budgets"]["model_calls"]):
            raise ScopeViolation(
                EscalationRequest(
                    "budget-extension",
                    self.mission,
                    "the approved model-call budget is used",
                    {"model_calls": 10},
                )
            )
        self.model_calls += 1

    def check_hardware(self, action: str) -> None:
        raise ScopeViolation(
            EscalationRequest(
                "hardware-control",
                self.mission,
                f"{action}: this build has no actuator path; physical control cannot be authorized here",
                {"action": action},
            )
        )

    def check_code(self, description: str) -> None:
        raise ScopeViolation(
            EscalationRequest(
                "untrusted-code",
                self.mission,
                f"{description}: arbitrary code is never executed by the research loop",
                {"description": description},
            )
        )


def authorization_record(
    request: dict, *, operator: str, decision: str, granted: dict | None = None, comment: str = ""
) -> dict:
    """The body of an ``authorization`` ledger record answering *request*."""

    if decision not in ("approve", "deny"):
        raise ValueError("decision must be approve or deny")
    granted = (
        granted if granted is not None else (request.get("requested", {}) if decision == "approve" else {})
    )
    if request["kind"] == "budget-extension" and decision == "approve":
        cap = request.get("cap")
        if cap is not None and int(granted.get("experiments", 0)) > int(cap):
            raise ValueError(f"an extension may add at most {cap} experiments")
    return {
        "request_id": request["request_id"],
        "mission": request["mission"],
        "kind": request["kind"],
        "decision": decision,
        "granted": granted if decision == "approve" and request["kind"] in GRANTABLE else {},
        "effective": decision == "approve" and request["kind"] in GRANTABLE,
        "operator": operator,
        "attestation": "local-operator",
        "identity_verified": False,
        "comment": comment,
    }
