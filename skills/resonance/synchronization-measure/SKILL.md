---
name: synchronization-measure
description: Two-oscillator synchronization measurement with independent replicate intervals. Use for the preregistered synchronization experiment.
license: MIT
---

# synchronization-measure

Typed inputs and outputs are in skill.json. Run the known-answer example with
`atlas skills test synchronization-measure`. Methods, convergence checks and limitations are
in docs/RESONANCE.md and tests/test_synchronization.py.

- Two phase oscillators, synthetic data only; finite-window locking, not a thermodynamic phase transition.
- Approximate Student-t intervals over independent simulations; no calibrated probability of physical truth.
- PLV and time-domain frequency analysis share raw data; replication uses new seeded trajectories.
