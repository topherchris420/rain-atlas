---
name: method-agreement
description: Compare frequency estimates from two independent methods realization by realization and decide, item by item, whether they agree within a tolerance. Use when a skeptic needs a computed (not voted) cross-method verdict.
license: MIT
compatibility: Requires Python 3.11+ with numpy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: evaluation
---
# Method agreement

Clusters method A's estimates across realizations, then for each cluster
measures how often method B reports a value within `tolerance_hz` in the
same realization. An item `agrees` when that fraction is at least
`min_fraction`. Unmatched estimates from either method are listed, never
dropped.

This is a computation over recorded outputs: it does not count agents and it
does not average opinions.
