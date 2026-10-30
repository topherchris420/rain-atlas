# Responsible use and disclosure

## What ATLAS claims

- Every number in an ATLAS report comes from a recorded skill run whose
  inputs, code hash, seed, environment and outputs are in the ledger.
- Claims are labelled **OBSERVED** (empirical measurements), **COMPUTED**
  (outputs of recorded runs) or **INTERPRETED** (conclusions drawn from those).
  The ledger refuses claims whose evidence does not fit their label.
- Verdicts (*supported*, *contradicted*, *unresolved*) are computed from
  independent checks and reproduction, never by counting agreeing agents.

## What ATLAS does not claim

- The research roles in v0.1 are scripted policies, not language models and not
  autonomous scientists. "Multi-agent" means separated responsibilities and
  independent methods, recorded separately.
- A skill's description is not evidence that it works. Only its executed
  examples and tests are.
- The reference experiment uses synthetic data. Its results say nothing about
  physical, biological, neurological or medical signals, and nothing about
  consciousness. Skills in the neuroscience domain (planned) analyse data; they
  make no clinical claims.
- Benchmark or model-performance figures are reported only from executed runs,
  with sample sizes and failure rates.

## Named agents and existing projects

ATLAS roles are named by function (principal investigator, computational
scientist, scientific skeptic, experimental engineer). They do not replace or
impersonate any existing agent, persona, memory or prompt in other R.A.I.N. Lab
projects. Adapters to those projects are optional and read-only until their
interfaces are verified (`docs/INTEGRATION.md`).

## If a model is added

Model-generated records must say `generation: model` with the model
identifier, and model proposals must pass schema and policy checks before
anything runs. Model text is never counted as evidence on its own.
