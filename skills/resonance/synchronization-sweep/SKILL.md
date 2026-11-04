---
name: synchronization-sweep
description: Two-oscillator synchronization simulation sweep. Use for the preregistered synchronization experiment.
license: MIT
---

# synchronization-sweep

Typed inputs and outputs are in skill.json. Run the known-answer example with
`atlas skills test synchronization-sweep`. Methods, convergence checks and limitations are
in docs/RESONANCE.md and tests/test_synchronization.py.

- Two phase oscillators, synthetic data only; finite-window locking, not a thermodynamic phase transition.
- Approximate Student-t intervals over independent simulations; no calibrated probability of physical truth.
- PLV and time-domain frequency analysis share raw data; replication uses new seeded trajectories.
