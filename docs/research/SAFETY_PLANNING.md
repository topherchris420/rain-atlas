# Plan power for a fresh false-conclusion study

**Design guidance, not a reanalysis or a new result.** The archived
[research benchmark](../demonstration/research/README.md) recorded 10 false
conclusions in 200 closed-loop missions; its adjusted interval was 1.5%–10.9%,
so it did not establish the 5% ceiling. That benchmark and its decision rule
are unchanged.

## Give the next safety question its own design

For one new prespecified test, define a mission-level binary event: a mission
ends with a false conclusion under independently checked hidden truth. Use
**all completed study missions** in the denominator, not only missions that
made a conclusion. Freeze the handling of missing runs and classify unresolved
missions separately. Also freeze a minimum correct-conclusion rate or a
tolerable loss of correct conclusions against the original closed loop. A
policy that always abstains cannot pass the overall study by making no errors.

For a new fixed sample of independent missions drawn from an identical,
preregistered generator mixture, the [one-sided exact binomial
test](https://doi.org/10.1093/biomet/26.4.404) is a transparent planning option.
Choose the largest count whose lower tail under the error ceiling is no more
than the per-test alpha. At a proposed *true* error rate, that same tail is the
probability of passing. Both the cutoff and the power are computed before
running any missions.

```sh
uv run python scripts/plan_research_safety.py \
  --missions 200 400 600 800 --ceiling 0.05 --alpha 0.05 \
  --true-rates 0.02 0.03 0.04
```

| Fixed independent missions | Most errors that pass | Power at true 2% | Power at true 3% | Power at true 4% |
| ---: | ---: | ---: | ---: | ---: |
| 200 | 4 | 62.9% | 28.1% | 9.5% |
| 400 | 12 | 93.8% | 57.6% | 18.8% |
| 600 | 20 | 98.9% | 73.3% | 23.8% |
| 800 | 29 | 99.9% | 87.1% | 33.4% |

These numbers assume one primary test at one-sided alpha 0.05. If alpha is
allocated across comparisons, pass the actual per-test budget. Power changes
in steps as the allowed error count changes; do not extrapolate it linearly.
A `null` cutoff means even zero observed errors would not meet the rule.

Do not use this calculator to reinterpret the archived stratified benchmark,
pool fixed per-family allocations as IID, count trajectories within a mission
as separate trials, or check repeatedly and stop after a passing result. For
fixed quotas or paired policy comparisons, plan using the actual structure.
Report error, correct conclusion, and abstention rates separately by family,
including designs where no candidate adequately describes the oscillator.
