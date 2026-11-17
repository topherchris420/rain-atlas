"""Simulation and Environment Engine: an Arga Labs-inspired replica.

Target: Arga Labs (closed source; behavior reconstructed from public
documentation), reconstructed by Recursive Engineering & Analysis.
See ``rain_atlas.rea.investigations.arga`` for the recorded evidence.

The reference provides *stateful digital twins* of external services with
deterministic scenario seeding, fault simulation and evidence capture. This
replica provides the same concepts for scientific instruments:

* :class:`ServiceTwin` -- a stateful, in-process twin of a scientific
  instrument (an oscillator bench). It owns hidden ground-truth state (which
  of two candidate models generated the data), executes seeded experiment
  runs, and records every operation;
* :class:`Scenario` -- a deterministic seed and initial state that can be
  snapshotted, reset and replayed exactly;
* :class:`FaultProfile` -- injected observation faults (noise, dropped
  measurements, bias) so agents can be evaluated under degraded conditions;
* :class:`TwinRun` -- captured evidence: every call, response and state
  change across a run.

The twin never contacts a network and never mutates anything outside its
own state. No production credentials or live data are involved.
"""

from .twin import FaultProfile, ObservationFault, Scenario, ServiceTwin, TwinRun

__all__ = [
    "FaultProfile",
    "ObservationFault",
    "Scenario",
    "ServiceTwin",
    "TwinRun",
]
