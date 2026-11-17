# Autonomous, evidence-driven research loop — design

Status: approved for build by the project owner (2026-11-17), who delegated the
architecture ("you have creative freedom ... proceed with the build"). Every
choice below that is not quoted from the request is the builder's call and is
marked as such where it matters.

## Intent

Turn R.A.I.N. ATLAS from a set of hand-wired demonstrations into a research
system that, inside a human-approved scope, can take an unfamiliar question
about a noisy dynamical system, form competing falsifiable hypotheses, choose
experiments **because of what earlier experiments showed**, notice when its own
model is wrong, revise or reject hypotheses, challenge its conclusions with
fresh data and an independent method, and stop for a stated reason, reporting
failures and unknowns.

The owner's acceptance test: open ATLAS and find a completed or clearly bounded
investigation of

> Can an intelligent experimental system detect previously unknown changes in a
> noisy dynamical system, determine what changed, and develop a better
> explanatory model using fewer experiments than conventional methods?

and a preregistered benchmark proving (or failing to prove) that
observation-dependent decisions beat conventional selection on held-out
problems.

## Goals, non-goals, anti-goals

Goals
- One general research loop (`rain_atlas.research`) driven by a `Domain`
  interface; one fully implemented domain (a noisy driven nonlinear
  oscillator) that contains hidden changes, unanticipated dynamics, wrong
  assumptions and noise.
- Deterministic numerical methods decide everything that counts: evidence,
  classification, execution policy, acceptance. Models (Ollama) may only
  propose, interpret and critique, and their output is labeled `model`.
- Charter-scoped autonomy with escalation for anything outside scope.
- Persistent mission state, crash recovery and resume; scientific memory with
  safeguards against stale and contradictory knowledge.
- A preregistered benchmark with development and held-out splits.

Non-goals
- Open-ended literature research, real instruments, hardware actuation,
  arbitrary code generation, live hosted models.
- Replacing the existing ledger, executor, skills, observatory or experiments.

Anti-goals (a technically working build that would still be a failure)
- A fixed experiment sequence presented as adaptive reasoning.
- Treating LLM output, or the number of agreeing agents, as evidence.
- A report that celebrates success when the benchmark is inconclusive.
- Tuning on the problems used to make the claim.

## Constraints (from the request)

- The human approves the mission charter: question, permitted methods,
  budgets and execution environment.
- Inside that scope ATLAS proposes, executes, analyzes, challenges and revises
  computational experiments without per-step approval.
- Expanding permissions, untrusted code, unauthorized resources, hardware
  control or exceeding budget require separate human authorization.
- The evidence ledger, immutable history, verdicts and provenance safeguards
  stay as they are.

## Approaches considered

1. **LLM-orchestrated agent team** (a model plans, calls tools, decides). Rejected:
   it makes the scientific engine depend on a model, decisions are not
   reproducible, and the request forbids model output deciding acceptance.
2. **Generalize the existing `MissionController` task DAG.** Rejected as the
   core: research is a sequential decision process whose next step depends on
   the last observation, not a dependency graph fixed in advance. The DAG
   would hide exactly the property the owner asked to see.
3. **Bayesian sequential-design loop with an evidence-driven hypothesis
   grammar** (chosen, builder's call). Hypotheses are explicit model
   structures; exact closed-form evidence ranks them; diagnostics *propose*
   new hypotheses, evidence *decides* them; the next experiment maximizes
   expected information gain about whatever is currently in contention.
   Observation dependence is real and measurable (yoked and open-loop
   controls), every step is deterministic and replayable, and a model can be
   plugged in as an advisor without touching acceptance.

## Architecture (builder's calls)

```
charter (human-approved) ─► scope guard ─► research loop ─► recorder (ledger | memory)
                                              │
     method survey ◄─ advisor (scripted | Ollama, labeled) ─┤
                                              ▼
   plan ─► predict ─► execute (instrument) ─► analyze ─► critique ─► revise
     ▲                                                    │
     └──────── stop? (decision ▸ challenge ▸ verdict | budget | futility) ◄┘
```

Modules under `src/rain_atlas/research/`:

| module | responsibility |
|---|---|
| `charter.py` | charter schema, validation, digest, default charter for the challenge question |
| `governance.py` | scope guard over every action; budget meter; escalation requests |
| `oscillator.py` | domain: term grammar, features, hidden-world instrument, problem generator (dev / held-out / demo splits) |
| `inference.py` | exact Normal-Inverse-Gamma evidence from sufficient statistics; structure, change-point and attribution hypotheses; predictive distributions |
| `critic.py` | prequential surprise, omitted-term Lagrange-multiplier tests, residual whiteness, noise-assumption check, Huber robust refit |
| `planner.py` | closed-loop expected-information-gain design, falsification-seeking challenge design, and the baselines |
| `engine.py` | the loop, stopping rules, claims, verdicts (reuses `agents.disagreement.verdict`) |
| `journal.py` | recorders; resume by deterministic replay with verification |
| `memory_bridge.py` | scientific memory as a tempered prior; validity test; quarantine |
| `advisor.py` | method survey, term proposals, critiques; scripted default, Ollama optional |
| `benchmark.py`, `stats.py` | preregistered benchmark, paired bootstrap, three-valued verdicts |
| `report.py`, `investigation.py` | end-to-end investigation, Markdown/JSON report, offline dossier |

### Domain: noisy driven oscillator

Semi-implicit Euler, `dt = 0.05`, 300 steps per experiment, state observed:

    v[t+1] = v[t] + dt·f(x[t], v[t], u[t]) + s·√dt·ε[t]
    x[t+1] = x[t] + dt·v[t+1],    u[t] = A·sin(Ω·t·dt)

`f = Σ θ_j φ_j`. Term grammar: core `x, v, u` (charter assumption), optional
`x^3, 1` (anticipated), expansion `x^2, x^2*v, v*|v|, x*u, v^3`
(unanticipated; only the critic may introduce them). The one-step regression
`(v[t+1]-v[t])/dt = θ·φ + noise` is linear-Gaussian, so model evidence is exact.
An experiment is a design `(A, Ω, x0)` inside the approved design space.

Hidden truth lives only in the instrument. Changes happen at an unannounced
experiment index. Families: `stationary`, `hidden-change`, `unfamiliar`,
`wrong-assumptions` (stale memory prior or heavy-tailed noise). The held-out
split uses different seeds, a wider stiffness range and **unanticipated terms
never present in development** (`x*u, x^2, v^3` versus `x^2*v, v*|v|`).

### Hypotheses and evidence

A hypothesis is `(structure, change_at, changed_terms)`. Change hypotheses
place extra coefficients on post-change experiments; "onset" changes add a
term only after the change. Log evidence is assembled from per-experiment
sufficient statistics (`ΦᵀΦ, Φᵀy, yᵀy, n`) with prefix sums, batched by
dimension. Priors: complexity penalty per optional term (log 3) and a larger
one per unanticipated term (log 20); change prior 0.3 per mission spread over
possible change points; at most one change per mission (stated assumption).

### Critic: diagnostics propose, evidence decides

After each experiment: prequential surprise of the new data under the
pre-update predictive (flag at z > 4); Lagrange-multiplier tests for every
grammar term missing from the leading model (Bonferroni 0.01); Ljung–Box
whiteness; kurtosis test for the Gaussian-noise assumption (switches the
analysis to Huber-weighted statistics and requires the robust check). A
flagged term enters the working set as new structures; it is accepted only if
exact evidence prefers it.

### Planner

Closed loop: expected information gain about the hypotheses in contention,
estimated by simulating each leading hypothesis's posterior predictive at each
candidate (a fixed quasi-random pool plus observation-derived candidates such
as the estimated resonance and replications). Challenge: the design that best
separates the leading hypothesis from its structural neighbours, restricted to
conditions not yet visited; its predicted interval is recorded before it runs.

Baselines (all share the analysis, critic, stopping rule and challenge step so
only selection differs): `yoked` (replays the closed loop's designs from a
different problem: same design distribution, broken observation dependence),
`open-loop-optimal` (sequential D-optimal under the prior), `fixed-sweep`
(stepped-sine), `random`. `legacy-atlas` ports the existing `rain central`
decision logic (fixed hypothesis set, maximum-disagreement selection,
5-nat Bayes-factor decision, verified memory). Ablations: `no-critic`,
`no-challenge`.

### Stopping and verdicts

Decision: leading joint hypothesis ≥ 0.95 posterior, change question resolved,
no open critic flag. Then two fresh challenge experiments (reserved from the
budget). A claim is **supported** only when the challenge corroborates, the
independent robust out-of-sample check corroborates, and the analysis
reproduces exactly (existing `verdict` rule). Contradiction sends the loop back
to exploration with the challenge data included. Other stops: budget exhausted
(unresolved; escalation request when more data would still be informative) and
futility (no permitted design is expected to be informative).

### Governance

The charter lists question, domain, design space, hypothesis grammar, permitted
policies and skills, budgets (experiments, missions, wall time, model calls),
environment (in-process simulation, no network except an optional approved
local model URL, no hardware). New ledger kinds `charter`, `authorization` and
`escalation`; ledger verification requires an approving authorization before a
preregistration that cites the charter. Out-of-scope actions raise an
escalation and pause; `atlas research authorize` + `resume` continue.
Hardware control and untrusted code have no execution path even if authorized.

### Persistence and memory

Each mission is a deterministic function of its charter, seeds and
observations. Featured missions write every event to the ledger (`research`
kind). Resume re-runs the loop against the recorded observations, verifies
every regenerated event equals the recorded one, and continues live. Model
advisor outputs are replayed from the record. The benchmark appends one fsynced
result line per (arm, problem) and skips completed lines on restart.

Memory is a tempered prior, never evidence. Its validity is itself a
hypothesis (prior 0.8); fresh evidence that makes it stale at ≥ 0.95 quarantines
it (deleted with history, contradiction recorded) and the mission continues
on the default prior. Contradictory memories for one apparatus are both set
aside.

### Benchmark (preregistered)

Arms as above; held-out split sealed in the preregistration before it runs.
Metrics: censored experiments-to-correct-conclusion (failures count as the
budget), false conclusions, unresolved rate, change detection / attribution,
discovery of unanticipated terms, held-out predictive regret and 90 % interval
coverage on unseen (including extrapolated) conditions, recovery from
confident errors, wall time, exact reproduction. Seven hypotheses, Bonferroni
0.05/7, paired family-stratified bootstrap over problems, three-valued
verdicts. A negative result is recorded and reported as such.

## Left to the builder

Numerical constants are tuned on the development split only and frozen before
the held-out run; the report states which.
