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

## Held-out spectral calibration

The stress benchmark's colored-noise failure motivates a separate experiment.
Can independent blank windows control whole-band false alarms, and what does
that cost in tone sensitivity?

```sh
uv run atlas benchmark --protocol spectral-calibration \
  --root atlas-data/calibration-512 --trials 512
uv run atlas ledger verify atlas-data/calibration-512/ledger
```

The CLI preregisters the design, runs the skill, records an exact same-seed
replay, verifies the ledger and exports `benchmark.json` and
`observatory/index.html`. The protocol defaults to 128 trials per case. Each
trial uses a fresh evaluation window and fresh reference banks.

### What is calibrated

All methods scan the same 1–64 Hz band, excluding both endpoints, in 8-second
windows sampled at 128 Hz. They use Welch spectra with a periodic Hann window,
256 samples per segment and 50% overlap. The existing Welch baseline estimates a
single white-noise floor and applies its nominal 5% threshold.

For each reference model, 32 independent noise-only windows estimate a mean
spectrum. The detector divides each of 99 separate calibration spectra and the
evaluation spectrum by that same template, bin by bin. Each calibration window
contributes its largest standardized bin. For an evaluation bin with
standardized power `s`, the rank p-value is
`(1 + number of calibration maxima >= s) / 100`.

Conditional on the independent template, if the evaluation window and the
calibration windows are exchangeable under the null, the evaluation maximum has
a uniform rank among the 100 maxima in the absence of ties. Counting ties
against rejection makes the test conservative. A declaration anywhere in the
band then occurs in at most five of the 100 possible ranks. The panel requires
both the white and AR(1) tests to declare the **same bin**. For either reference
model, a panel declaration implies a declaration by that model, so the 5% bound
holds if either model is exchangeable with the evaluation window. No assumption
of independence between frequency bins or between the two decisions is needed.

The two references are unit-variance Gaussian white noise and stationary Gaussian
AR(1) noise with coefficient 0.95. The out-of-panel control is the real part of
a stationary complex AR(1) with pole radius 0.97 and center frequency 12.25 Hz.
It has a stochastic spectral peak with no deterministic sinusoid. The
injected-tone cases add a random-phase 12.25 Hz sinusoid to AR(1) noise at three
amplitudes. A tone counts as localized when a declared frequency falls within
0.5 Hz of the injection.

The rank bound is marginal over fresh calibration windows. The 95% Wilson
intervals apply to independent benchmark trials with fresh banks. A fixed bank
reused in production, overlapping windows, repeated scans and hardware noise
require separate validation. The tone cases measure localization at one
frequency. They do not establish per-bin false alarm control in the presence
of real tones.

### Recorded result

512 independent trials per case, using seed 20261110. Null rows count trials
with a declaration anywhere in the search band. Tone rows count trials with a
declaration within 0.5 Hz of the injected frequency.

| Case | Welch threshold | White reference | AR(1) reference | Reference panel |
|---|---:|---:|---:|---:|
| White noise only | 34/512 | 29/512 | 512/512 | 27/512 |
| AR(1) noise only | 512/512 | 512/512 | 25/512 | 2/512 |
| Oscillatory noise only | 512/512 | 512/512 | 512/512 | 512/512 |
| AR(1) + weak tone (amplitude 0.12) | 506/512 | 0/512 | 199/512 | 0/512 |
| AR(1) + intermediate tone (0.25) | 512/512 | 42/512 | 512/512 | 42/512 |
| AR(1) + strong tone (0.75) | 512/512 | 512/512 | 512/512 | 512/512 |

The panel's AR(1) false-alarm estimate was **0.39%** (95% Wilson interval
**0.11%–1.41%**). Its white-noise estimate was **5.27%** (interval
**3.65%–7.56%**). The 5% bound concerns the underlying rejection probability
under exchangeability. A finite observed proportion can exceed it.

The matched AR(1) reference localized 199 weak tones while declaring near the
same frequency in only 1 of 512 AR(1) null trials. The Welch baseline reported
506 weak-tone hits and declared near that frequency in 276 null trials. The
panel traded weak-tone sensitivity for protection across both reference
models. It declared near the target in every oscillatory null trial, showing
how a stochastic peak can defeat both models.

[Recorded JSON with both rates and confidence intervals](demonstration/spectral-calibration.json)

The recorded run used Linux, Python 3.12.14, NumPy 2.5.4 and SciPy 1.18.1.
The six-record ledger verified, and the replay matched both output and artifact
hashes. The recorded JSON has SHA-256
`10fe01f5a897cd05012e506cc24297bdbeddfa537f7f9571bad27031bbf1c52a`.
