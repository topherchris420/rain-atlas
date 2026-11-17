"""Persistent missions: the ledger is the journal; resume is verified replay.

Every event the research loop emits becomes a ``research`` record in the
evidence ledger, and every observation becomes a ``run`` record whose data is a
content-addressed object. A mission is a deterministic function of its
charter, seeds and observations, so resuming after a crash means running the
loop again against the recorded observations:

* each regenerated event must equal the recorded one (canonical hash); any
  difference -- changed code, changed data, a tampered record -- stops the
  resume with :class:`ResumeError` instead of silently forking history;
* recorded observations are returned instead of re-running the instrument
  (an experiment that was planned but never recorded is executed);
* recorded model-advisor answers are replayed, because a model need not
  answer the same way twice;
* once replay reaches the end of the record, new events are appended.

After a human authorization (for example a budget extension) the recorded
terminal events of a stopped mission -- escalation, conclusion, stop -- may be
superseded; a ``resumed`` event marks the point. Nothing recorded is edited.
"""

from __future__ import annotations

from typing import Any

from ..canonical import sha256_json
from ..ledger.store import Entry, Ledger
from .oscillator import Design, Observation

AUTHOR = {"role": "research-loop", "generation": "scripted"}
TERMINAL = ("escalation", "conclusion", "stop")
INSTRUMENT_SKILL = "atlas-research/oscillator-instrument"


class ResumeError(RuntimeError):
    """Replay diverged from the recorded mission."""


def mission_records(ledger: Ledger, mission: str, kind: str = "research") -> list[tuple[Entry, dict]]:
    return [(e, r) for e, r in ledger.records(kind) if r.get("mission") == mission]


def mission_events(ledger: Ledger, mission: str) -> list[dict]:
    return [r["payload"] for _, r in mission_records(ledger, mission) if r["event"] != "resumed"]


def mission_runs(ledger: Ledger, mission: str) -> dict[int, tuple[str, dict]]:
    out = {}
    for entry, record in mission_records(ledger, mission, "run"):
        if "index" in record and "observation_object" in record:
            out[int(record["index"])] = (entry.object, record)
    return out


def summarize_event(event: dict) -> str:
    kind = event["event"]
    if kind == "plan":
        c = event["choice"]
        return f"experiment {event['index'] + 1} ({c['purpose']}): {Design.from_dict(c['design']).label()} — {c['reason']}"
    if kind == "observation":
        return f"experiment {event['index'] + 1} observed: amplitude {event.get('amplitude')}"
    if kind == "analysis":
        d = event["decision"]
        return (
            f"after {event['after_experiments']} experiments: leading structure {d['structure']} "
            f"(P = {d['p_structure']:.3f}), P(change) = {d['p_change']:.3f}"
        )
    if kind in ("revision", "note"):
        return str(event.get("summary", kind))
    if kind == "challenge":
        return f"challenge at experiment {event['index'] + 1}: {event['outcome']}"
    if kind == "conclusion":
        return f"conclusion: {event['verdict']} — structure {event['structure']}"
    if kind == "stop":
        return f"stopped: {event['reason']} after {event['experiments']} experiments"
    return kind


class LedgerJournal:
    """The loop's ``emit`` hook: verify against the record, then append."""

    def __init__(self, ledger: Ledger, experiment: str, mission: str, *, allow_supersede: bool = False):
        self.ledger = ledger
        self.experiment = experiment
        self.mission = mission
        self.recorded = mission_events(ledger, mission)
        self.position = 0
        self.allow_supersede = allow_supersede
        self.replayed = 0
        self.appended = 0
        self.superseded = 0

    def __call__(self, event: dict) -> None:
        if self.position < len(self.recorded):
            expected = self.recorded[self.position]
            if sha256_json(event) == sha256_json(expected):
                self.position += 1
                self.replayed += 1
                return
            remaining = self.recorded[self.position :]
            if self.allow_supersede and all(e["event"] in TERMINAL for e in remaining):
                self.superseded = len(remaining)
                self.ledger.append(
                    "research",
                    {
                        "experiment": self.experiment,
                        "mission": self.mission,
                        "event": "resumed",
                        "summary": f"{len(remaining)} recorded terminal events superseded after a human authorization",
                        "payload": {"superseded": [e["seq"] for e in remaining]},
                        "author": AUTHOR,
                    },
                )
                self.position = len(self.recorded)
            else:
                raise ResumeError(
                    f"mission {self.mission}: regenerated event {event['seq']} ({event['event']}) differs from the "
                    f"recorded event {expected['seq']} ({expected['event']}); the code, data or record changed"
                )
        self.ledger.append(
            "research",
            {
                "experiment": self.experiment,
                "mission": self.mission,
                "event": event["event"],
                "seq": event["seq"],
                "summary": summarize_event(event),
                "payload": event,
                "author": AUTHOR,
            },
        )
        self.appended += 1


class RecordingInstrument:
    """Wraps the live instrument: replays recorded observations, records new ones."""

    def __init__(self, live: Any, ledger: Ledger, experiment: str, mission: str):
        self.live = live
        self.ledger = ledger
        self.experiment = experiment
        self.mission = mission
        self.recorded = mission_runs(ledger, mission)
        self.run_refs: dict[int, str] = {i: ref for i, (ref, _) in self.recorded.items()}
        self.kind = getattr(live, "kind", "instrument")

    def run(self, design: Design, index: int) -> Observation:
        if index in self.recorded:
            _, record = self.recorded[index]
            if Design.from_dict(record["design"]) != design:
                raise ResumeError(
                    f"mission {self.mission}: experiment {index + 1} was recorded with a different design"
                )
            obs = Observation.from_dict(self.ledger.get_json(record["observation_object"]))
            if obs.digest() != record["observation_digest"]:
                raise ResumeError(
                    f"mission {self.mission}: recorded observation {index + 1} fails its digest"
                )
            return obs
        obs = self.live.run(design, index)
        data = obs.to_dict()
        ref = self.ledger.put_json(data)
        entry = self.ledger.append(
            "run",
            {
                "run_id": f"{self.mission}/experiment-{index + 1:02d}",
                "skill": INSTRUMENT_SKILL,
                "status": "ok" if obs.status == "ok" else "failed",
                "seed": index,
                "inputs_hash": sha256_json(
                    {"mission": self.mission, "index": index, "design": design.to_dict()}
                ),
                "experiment": self.experiment,
                "role": "instrument",
                "purpose": "experiment chosen by the research loop",
                "mission": self.mission,
                "index": index,
                "design": design.to_dict(),
                "observation_object": ref,
                "observation_digest": obs.digest(),
                "artifacts": {"observation.json": {"sha256": ref, "object": ref}},
                "executor": f"{self.kind}; hidden parameters stay inside the instrument and are sealed in this ledger",
            },
        )
        self.run_refs[index] = entry.object
        return obs


class ReplayAdvisor:
    """Returns recorded advisor answers in order, then defers to the live advisor."""

    def __init__(self, live: Any, recorded_events: list[dict]):
        self.live = live
        self.answers = [e for e in recorded_events if e["event"] == "advisor"]
        self.calls = 0

    def propose_terms(self, context: dict) -> dict:
        if self.calls < len(self.answers):
            e = self.answers[self.calls]
            self.calls += 1
            return {
                "terms": list(e["proposed"]),
                "generation": e["generation"],
                "rationale": e.get("rationale", ""),
            }
        self.calls += 1
        if self.live is None:
            return {"terms": [], "generation": "scripted", "rationale": "no advisor"}
        return self.live.propose_terms(context)


def recorded_memory(ledger: Ledger, mission: str) -> tuple[bool, dict | None]:
    """The memory the mission started with, if the mission has started."""

    events = mission_events(ledger, mission)
    if events and events[0]["event"] == "mission-start":
        return True, events[0].get("memory")
    return False, None
