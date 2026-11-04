# Scientific benchmark laboratory

`atlas benchmark --root atlas-data/bench-001 --trials 12` preregisters a fixed
protocol, executes `spectral-stress-benchmark` through the normal executor,
records its measured result, verifies artifacts and exports an observatory.
`benchmark.json` contains full configurations, seeds, counts and intervals.
No LLM participates and no unexecuted system is compared.

| Case | Known truth / violated assumption |
|---|---|
| separated | 12 and 28 Hz stationary sinusoids in white Gaussian noise |
| close | 12 and 12.125 Hz, beneath the 256-sample Welch segment spacing |
| white-null | No tones; tests the assumed noise null |
| colored-null | No tones; stationary AR(1), rho=0.95, with 2048-sample warmup |
| chirp | 10–30 Hz nonstationarity; stationary-tone truth unavailable |
| amplitude-modulated | Carrier 12 Hz and analytical sidebands at 11.5/12.5 Hz |

All cases use 128 Hz sampling, 1024 samples, independent seeded trials and
0.08 Hz matching tolerance. Baselines are the existing Welch detector
(256-sample Hann segments, nominal alpha 0.01) and NLS/BIC sinusoid search
(maximum four tones). These are transparent classical estimators with
different assumptions; their disagreement is measured, not voted away.

Reported per-case trial events: any false detection, any missed tone, all tones
recovered, and method disagreement. Rates have 95% Wilson intervals and explicit
sample sizes, including zero-event uncertainty. False-negative rates are null
when there are no true tones. Chirp error labels are null with a reason.
Matched-tone RMSE excludes misses and can be selection-biased; detection rates
are always reported alongside it. Runtime is measured per method; process
peak memory and environment are in the run record. POSIX peak RSS is a host
children upper bound, not isolated per-invocation memory.

Seeded scientific quantities reproduce; timings and peak memory do not promise
bit identity. The skill is therefore labelled stochastic. Its configuration
example is not evidence of accuracy; `tests/test_bench.py`, independent
numerical known answers and actual benchmark runs provide different checks.

This small synthetic suite diagnoses wrong answers, model misspecification and
unknown-truth cases. It does not establish general research reliability,
calibrated posterior probabilities, statistical power across applications,
semantic data-leakage detection or Linux/Windows consistency. Those broader
evaluations remain planned. See STATUS.md for executed results only.
