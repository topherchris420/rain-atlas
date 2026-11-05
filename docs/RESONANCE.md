# Resonance methods and the synchronization protocol

The eight general capabilities and two experiment capabilities are executable
skills. Each has a closed typed input/output manifest, a reproducible example,
units, limitations and an entrypoint run by the existing bounded executor.
`tests/test_resonance.py` checks analytical answers, independent SciPy
comparisons, negative controls and convergence. These are numerical checks,
not empirical validation of physical or biological claims.

| Capability | Definition / units | Numerical check | Failure conditions |
|---|---|---|---|
| STFT | Periodic Hann, complete frames, one-sided density in input²/Hz; no detrending or padding | SciPy spectrogram, Parseval, even/odd frames, chirp ridge and zero control | Irregular sampling, aliasing, insufficient duration; resolution is not zero-padding spacing |
| Morlet CWT | Corrected complex Morlet, discrete L2 unit norm, nominal f=omega0 fs/(2 pi scale) | Known tone, translation, zero control, explicit edge mask; a tone's modulus ridge lies at f·2ω0/(ω0+√(ω0²+2)) (1.35% low at ω0=6), as L2 normalization predicts | Zero-extension edges; fs/4 ceiling; scalogram is not PSD or significance; nominal centers are not ridge frequencies |
| PLV | abs(mean(exp(i phase difference))) over time; dimensionless | Constant offset=1, full-circle drift=0 | Finite-sample bias, autocorrelation, ambiguous broadband phase, common drive; PLV is not causality |
| Kuramoto | All-to-all K/N, self excluded; omega,K rad/s, D rad²/s | Exact uncoupled solution, pair fixed point, RK4 order against DOP853-style adaptive reference, coupled Wiener refinement | Phase-only reduction; no delays/amplitude physics; stiffness/coarse dt; finite N |
| LMS / NLMS | Causal FIR adaptation w+=mu e x (NLMS normalized by input energy) | Known FIR weights, residual reduction | Plain LMS step bound depends on input covariance; divergence rejected; adaptive cancellation can remove desired signal |
| FIR identification | Least squares; coefficient covariance conditional on IID output residuals and noise-free input | Known coefficients, unrelated-output control, rank-deficiency refusal | Errors in variables, coloured residuals, nonlinearity, insufficient excitation |
| Plate eigenmode | Simply supported rectangular Kirchhoff–Love sin(m pi x/a) sin(n pi y/b), material-derived Hz | Boundary zeros, thickness scaling, second-order spatial convergence | Not a free-edge Chladni plate; no sand, fluid, damping or nonlinear response |
| Cross spectra | Welch CSD conj(X)Y in input²/Hz; magnitude-squared coherence | Independent SciPy agreement and unrelated-noise negative control; at least three segments enforced for odd and even nperseg | <3 segments (independent noise then averages about 0.5 coherence; refused), zero power (mask), nonstationarity, common input, bias |

Arrays are float64/complex128. Kernel precision is tested to stated tolerances,
not advertised as arbitrary precision. Where uncertainty is absent, outputs
are numerical estimates without calibrated intervals. FIR covariance is
model-conditional. The synchronization study estimates uncertainty across
independent trajectories, never by counting correlated time points as samples.

## Reproducible synchronization demonstration

```sh
uv run atlas experiment run synchronization --replicates 12 --root atlas-data/sync-001
uv run atlas ledger verify atlas-data/sync-001/ledger
```

Open `atlas-data/sync-001/observatory/index.html`. Original report, summary and
300-dpi PNG/vector SVG figures are under `reports/`; raw trajectories, seeds,
parameters, code identities and run environments are in the ledger. The
command refuses an existing ledger so a rerun cannot silently overwrite it.

For two oscillators with natural angular frequencies -0.5 and +0.5 rad/s,
the phase difference obeys

`delta' = 1 - K cos(lag) sin(delta)` when D=0.

The stable locked fixed point exists when `K cos(lag)>1`. With lag=0,
`delta*=asin(1/K)` and `R*=sqrt((1+sqrt(1-1/K²))/2)`. The analytical threshold
is **not fitted to simulation output**. At the threshold and under noise we
do not assign a binary asymptotic reference truth.

The preregistration fixes K={0,0.6,1,1.4,2}, D={0,0.08,0.5}, lag={0,0.6},
60 s trajectories, 20 s burn-in, dt=0.04 s, and 12 independent trajectories
per condition (CLI `--replicates 12`). Primary and replication ensembles use
disjoint seeded streams. Phase-lag variation deliberately tests a model whose
threshold differs from the zero-lag model. The study is explicitly **not blind**.

- Primary: lower simultaneous interval for mean temporal PLV >0.90.
- Skeptic: upper interval for mean absolute relative frequency <0.05 rad/s,
  using OLS slopes in eight disjoint temporal blocks.
- Independent-data challenge: same primary threshold on new trajectories.
- Reproduction: exact outputs and artifact hashes for generator and analysis.
- Supported requires every gate. Strong disagreement contradicts the
  operational claim; intermediate evidence remains unresolved.

Student-t intervals are approximate, with Bonferroni correction across
conditions and the two metric families. They may extend outside physical PLV
bounds; this is shown, not silently clipped. The two methods are distinct
observables of the same phase data, not independent instruments. New-data
replication is independent of the discovery data. Initial phases and noise
are random; system parameters are fixed. A test explicitly shows the
high-PLV false-causality case of uncoupled identical-frequency oscillators.

The report retains every condition, including negative results, disagreements,
truth-unavailable cases and discrepancies between finite-window criteria and
the asymptotic reference. The report does not equate lack of support with
proof of no synchronization of any kind.

## Independent references

- [SciPy signal documentation](https://docs.scipy.org/doc/scipy/reference/signal.html):
  documented STFT, Welch and CSD conventions used for numerical comparisons.
- [SciPy CSD definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.csd.html):
  conjugation convention and normalization.
- Aydore, Pantazis & Leahy, [A note on the phase locking value and its properties](https://pmc.ncbi.nlm.nih.gov/articles/PMC3674231/):
  finite-sample bias and interpretation of PLV.
- Dörfler & Bullo, [On the critical coupling for Kuramoto oscillators](https://arxiv.org/abs/1011.3878):
  finite versus infinite-dimensional locking conditions. The pair formula
  above follows directly by subtracting the two ODEs.

These references motivate algorithms and caveats; passing tests of our code
does not reproduce every claim in those papers.
