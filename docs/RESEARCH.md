# Autonomous research: `rain_atlas.research`

ATLAS can now run an investigation, not just an experiment. Given a question
and a human-approved charter, the research loop forms competing hypotheses,
chooses experiments **because of what earlier experiments showed**, notices
when its own model is wrong, revises or rejects hypotheses, challenges its
conclusions with fresh data and an independent method, stops for a stated
reason, and reports what it could not establish. Every step is in the evidence
ledger and can be replayed exactly.

What it is not: open-ended literature research, a language-model agent, or a
claim about physical systems. Numerical methods and deterministic code decide
everything that counts; a local model may only suggest, and its suggestions
are validated and labeled.

```sh
uv run atlas research demo --root atlas-data/research     # default charter, labeled proxy approval, full run
uv run atlas ledger verify atlas-data/research/ledger
```

Open `atlas-data/research/reports/dossier.html` (offline, no scripts) or
`observatory/index.html`. The recorded held-out run is in
[docs/demonstration/research/](demonstration/research/).

With a real operator instead of the demonstration proxy:

```sh
uv run atlas research init --root atlas-data/my-study            # writes charter.json for review
uv run atlas research approve --root atlas-data/my-study --operator "Ada Lovelace"
uv run atlas research run --root atlas-data/my-study
uv run atlas research status --root atlas-data/my-study           # missions, verdicts, pending escalations
uv run atlas research authorize --root atlas-data/my-study --request <id> --operator "Ada Lovelace" --experiments 8
uv run atlas research resume --root atlas-data/my-study           # verified replay, then continue
```

## The loop

```
charter (human-approved) ─► scope guard ─► research loop ─► ledger journal
                                              │
   method survey ◄── advisor (scripted retrieval | local model, labeled)
                                              ▼
   plan ─► predict ─► execute ─► analyze ─► critique ─► revise
     ▲                                                    │
     └── stop?  decision ▸ challenge ▸ independent check ▸ verdict
                budget exhausted ▸ escalation request · futility
```

| Requirement | Where it happens |
|---|---|
| Investigate the question, identify methods | `advisor.ScriptedAdvisor.survey`: cue-table decomposition + BM25 over a curated method catalog and the skill catalog |
| Competing falsifiable hypotheses | program level H1–H7 with nulls; mission level: model structures from the charter's grammar, change and attribution hypotheses (`inference.Hypothesis`) |
| Experiments that discriminate | `planner.ClosedLoop`: expected information about hypotheses **and** coefficients |
| Skills and baselines | the survey selects methods and catalogued skills; five baseline designs and a linear least-squares model |
| Preregistration | `preregistration` ledger record before any experiment, with sealed truths, rules and source hash |
| Execute within budgets | `governance.ScopeGuard` checks every design, experiment, model call and term |
| Analyze, quantify uncertainty | exact Normal-Inverse-Gamma evidence; Student-t predictives; posterior over hypotheses |
| Contradictions, inadequacy | `critic`: prequential surprise, score tests, whiteness, noise-assumption test |
| Next experiment from what was learned | contenders and parameter posteriors come from the data, so does the choice |
| Challenge with fresh data and an independent method | novel-condition and sentinel challenges (prediction recorded first) + cross-validated robust check |
| Revise or reject | `revision` events: admitted terms, revised assumptions, rejected hypotheses, quarantined memory |
| Stop | challenged decision, budget exhausted (with an escalation request), or futility |
| Report, including failures | `report.py`: Markdown, JSON, offline dossier, observatory |

## Hypotheses and evidence

The domain is a noisy driven oscillator, simulated by semi-implicit Euler with
process noise; the full state is observed, so the one-step regression
`(v[t+1] − v[t]) / dt = θ · φ(x, v, u) + ε` is linear-Gaussian and the
evidence of every hypothesis is exact (tests check it against brute-force
quadrature and stacked regression). Terms: core `x, v, u`; anticipated
`x^3, 1`; unanticipated `x^2, x^2*v, v*|v|, x*u, v^3` (only the critic can bring
these in).

A hypothesis is a structure plus, optionally, a change point and the terms
that changed (a *shift* of an existing term or the *onset* of a new one).
Priors: a complexity penalty (log 3 per anticipated term, log 20 per
unanticipated term), a per-experiment change hazard of 0.08 (at most one change
per mission), change sizes with sd 0.5. Sufficient statistics and prefix sums
make several hundred hypotheses cost milliseconds.

**No change detected is not a claim that nothing changed.** A change is
asserted only at P(change) ≥ 0.95; below 0.2 the mission reports "no change
detected" with its probability; in between it keeps investigating.

## Choosing the next experiment

The closed loop maximizes the total expected information
`I(Y; H, θ) = I(Y; H) + Σ_h P(h) I(Y; θ_h | h)`:

* `I(Y; H)` by simulating each contender's posterior predictive at each
  candidate (common random numbers) and scoring every simulated experiment
  with the exact incremental evidence of every contender. The strongest change
  hypothesis always has a seat, so the planner keeps asking whether the system
  changed.
* `I(Y; θ | h) = ½ log det(I + V G)` on each contender's encompassing
  structure, evaluated on a trajectory of the current posterior-mean model.

Candidates: a fixed quasi-random pool plus observation-derived ones (the
estimated resonance, twice it when parametric excitation is in play,
replications of earlier conditions). Every choice records the five best
candidates, their utilities split into hypothesis and parameter information,
and the competing explanations.

## The critic: diagnostics propose, evidence decides

* **Prequential surprise** of each experiment under the predictive fixed
  before it was analyzed (a robust version after the noise assumption fails).
* **Score (Lagrange-multiplier) tests** for every admissible missing term,
  Bonferroni 0.001. Every significant term enters the working set together,
  so near-collinear rivals (`v^3` versus `v*|v|`) are separated by evidence,
  not by which was proposed first.
* **Ljung–Box** whiteness of the newest residuals; a failure blocks a decision.
* **Kurtosis test** of the Gaussian-noise assumption; on failure the analysis
  switches to Huber-weighted statistics (an approximation, recorded as a
  revision).

## Challenges and verdicts

When the leading explanation reaches the decision level, the loop challenges
it before concluding:

1. a **novel condition** chosen where the leading explanation and its
   neighbours (one term more, one fewer, or a swapped unanticipated term)
   disagree most, rivals weighted equally;
2. a **sentinel** that re-measures the first experiment's condition to test
   stationarity.

Each challenge's predicted amplitude interval is in the ledger before it
runs. Outcomes combine the one-step surprise, the amplitude against the
128-draw predictive interval, and a Chow test of coefficient equality. A
contradiction sends the loop back to exploration with the new data. After two
corroborations an **independent check** (leave-experiments-out cross-validated
prediction against every one-term variant over the full grammar, least squares
or Huber, Bonferroni) must corroborate too. The verdict uses the existing rule
(`agents.disagreement.verdict`): supported only when the falsification test,
the independent check and exact re-analysis agree.

## Governance

The charter (`charter.DEFAULT`, schema `atlas.research-charter/v1`) states
the question, design space, grammar, permitted policies, analyses and skills,
budgets (experiments per mission, featured missions, benchmark size, wall
time, model calls, maximum extension per request), the environment
(in-process simulation, no network, no hardware control, no untrusted code,
optionally one local Ollama URL) and the stopping rule. Its digest is what the
operator approves; ledger verification rejects a preregistration that cites a
charter without an earlier approving `authorization`.

Inside the charter the loop needs no permission. Outside it raises an
**escalation** and stops that mission: more experiments, a wider design space
or extra grammar terms can be authorized (`atlas research authorize`, a local
attestation, not an identity proof); hardware control, untrusted code and
unapproved network access have no execution path, so an approval of them
changes nothing.

## Persistence, crash recovery and resume

The ledger is the journal: every event is a `research` record and every
observation a `run` record with a content-addressed data object. Resume runs
the loop again against the recorded observations and checks each regenerated
event against the record; any difference (changed code, changed data, a
tampered record) raises `ResumeError` instead of forking history. An
experiment that was planned but not recorded is executed; recorded model
answers are replayed. After an authorization, only the recorded terminal
events (escalation, conclusion, stop) may be superseded, marked by a
`resumed` event and a `revision` of the verdict. The benchmark writes one
fsynced line per mission and skips completed lines on restart (a torn final
line is ignored). A torn ledger line is handled by the existing
`atlas ledger recover`.

## Memory and its safeguards

Supported characterizations are remembered with their claim. A recalled
memory becomes a **tempered prior** (widened with age), never evidence: its
validity is a hypothesis (prior 0.8, memory-valid versus memory-stale
regimes), and each remembered coefficient is checked against a fit to fresh
data alone (|z| > 3.5 is a conflict). Stale or conflicting memory is
quarantined: deleted from the active set with history retained, and a
contradiction recorded. Two contradictory memories of one apparatus are both
set aside. The featured run shows this on `bench-A`: characterized in M1,
repaired off the record, recalled in M4, contradicted, quarantined and
re-characterized.

## The model advisor

`atlas research init --ollama-model llama3.2` allows a local Ollama model. It
can suggest methods during the survey and terms when the critic flags
inadequacy. Its JSON is schema-checked; unknown methods are discarded, terms
outside the grammar are escalated (as untrusted code if they are not in the
term library), every call counts against the charter's model-call budget, and
when the model is unavailable the scripted advisor answers and the record
says so. Model text never counts as evidence and never decides a verdict. No
live model ran in the recorded investigation; tests use a simulated local
server.

## The benchmark

See [research/PREREGISTRATION.md](research/PREREGISTRATION.md) for the
frozen design, committed and pushed before the held-out run, and
[demonstration/research/](demonstration/research/) for the result. Eight
arms share everything except selection (and the named components for the
legacy rule and the ablations). The **yoked** control replays the closed
loop's own designs from a different problem: same design distribution,
dependence on this problem's observations removed. It is the direct test of
whether observation-dependent decisions matter.

## Development record: where the design was wrong

The configuration was tuned on the development split only. Problems found and
fixed on the way, in order:

1. Changes placed late in a mission were never tested by fast arms; changes now
   occur at the 2nd–4th experiment.
2. Heavy-tailed noise made every challenge "contradicted": the challenge
   statistic assumed Gaussian residuals; a robust statistic replaced it.
3. A stale memory was reported "confirmed" because the global validity test
   passed when only one coefficient had changed; per-coefficient conflict
   checks were added, and an early bug compared remembered terms against terms
   absent from the fresh fit.
4. The independent check on two challenge experiments could not confirm small
   terms; cross-validation over all experiments replaced it.
5. Changes were missed because the omnibus surprise statistic has little power
   against a single parameter shift and the first designs were poor baselines;
   the sentinel, the Chow test and total-information design addressed this.
6. A per-experiment hazard prior made "no change" unprovable (a change just
   before the last experiment can never be excluded), collapsing correct
   conclusions from 61 % to 12 %; the fix was conceptual: report "no change
   detected" instead of asserting absence.
7. Futility stopped a mission after two experiments while a change question was
   still open; futility now needs three uninformative steps after eight
   experiments.
8. With two problems per family the bootstrap declared H1 "supported"; verdicts
   are now withheld below ten problems per family.

## Limitations

* One domain. The loop is written against domain interfaces (designs,
  instrument, term grammar), but generality is designed, not demonstrated.
* At most one change per mission; process noise only (no sensor noise on the
  state); dynamics outside the grammar can be flagged but not explained.
* Huber-weighted evidence is an approximation of a heavy-tailed likelihood.
* Simulated apparatus: verdicts are about the simulated family, the approved
  design space and the stated priors. Agreement with the hidden truth is
  possible to score only because the apparatus is simulated.
* The in-process instrument is not a sandbox; the research loop never executes
  model text or code.
