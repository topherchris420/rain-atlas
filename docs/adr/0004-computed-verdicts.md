# ADR 0004: Verdicts are computed from independent evidence, never voted

Status: accepted (2026-10-30)

## Context

Multi-agent systems tend to reach "consensus" by agreement between agents that
share the same blind spots. A scientific platform needs disagreement to be
visible and resolved by evidence.

## Decision

Each finding gets a `verdict` record computed by a fixed rule
(`rain-atlas/verdict/v1`): **supported** only when an independent estimator
corroborates it, a falsification test on independent replicate data
corroborates it, and the primary computation reproduces byte for byte;
**contradicted** when an independent check contradicts it; **unresolved**
otherwise. Lines found only by the independent method are recorded as their
own claims and stay unresolved. Verdicts are recorded before ground truth is
unsealed.

## Consequences

- Agreement between roles counts for nothing unless the methods differ and the
  data are independent.
- Some true effects remain *unresolved* (for example when only one method sees
  them); the report lists them rather than hiding them.
