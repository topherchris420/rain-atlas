# ORRERY — validation record

This is what was **actually executed** for the `rain_atlas.orrery` engine, with
measured numbers. Agreement between ORRERY and GMAT is code-to-code
**consistency between two independent implementations**, not physical validation
against tracking data. Only the two-body scenarios (S1–S3) are checked against a
genuine analytic truth (the closed-form Kepler solution).

## Environment

- Host: Windows 11 (win32, arm64 laptop), local developer machine.
- Interpreter: CPython **3.12.15**, **NumPy 2.5.4**, **SciPy 1.18.1** (from the
  committed `uv.lock`).
- GMAT reference: **GMAT R2026a** (`gmat-win-R2026a.zip`, SourceForge, MD5
  `e6248b1a776c952c3dda0bedda7f1f19`), build date Mar 26 2026. Binary SHA-256
  digests and each run's script/report SHA-256 are recorded inside every file
  under `src/rain_atlas/orrery/reference/gmat-R2026a/`.

## Reference data provenance

| Data | Source | Licence / status |
|---|---|---|
| Sun/Moon ephemeris | JPL **DE421** excerpt around 2026-01-15 | U.S. Government work, public domain |
| ICRF→FK5 frame tie | GMAT R2026a `ICRF_Table.txt` | GMAT (Apache-2.0) data table |
| Earth orientation | IERS **EOP C04** excerpt | IERS, freely redistributable |
| Geopotential | **JGM-3** to 8×8 | public gravity model |
| GMAT reference trajectories | `GmatConsole.exe --run` on each scenario | regenerable; provenance in each file |

## Scenario agreement (from `atlas experiment run orrery`)

Primary integrator RKF7(8), rtol = atol = 1e-12; the independent-integrator
challenge is SciPy DOP853 at the same tolerance. "Max position error" is the
largest position difference over the whole arc against the scenario's reference.

| Scenario | Reference | Max position error | Preregistered tol | Verdict |
|---|---|---|---|---|
| S1 LEO, two-body | analytic Kepler | 6.2 × 10⁻⁵ m | 1 mm | supported |
| S2 Molniya, two-body (e = 0.74) | analytic Kepler | 2.0 × 10⁻² m | 5 cm | supported |
| S3 GEO, two-body | analytic Kepler | 7.2 × 10⁻⁶ m | 1 cm | supported |
| S4 LEO + J2 | GMAT R2026a | 2.3 × 10⁻² m | 0.5 m | supported |
| S5 HEO + J2 | GMAT R2026a | 8.4 × 10⁻¹ m | 5 m | supported |
| S6 GEO + J2 + Sun + Moon | GMAT R2026a | 2.1 × 10⁻¹ m | 2 m | supported |
| S7 LEO + JGM-3 8×8 | GMAT R2026a | 2.6 × 10⁻² m | 0.5 m | supported |
| S8 Earth–Moon TLI | GMAT R2026a | 5.2 × 10⁻² m | 1 m | supported |
| S10 figure-eight (N-body) | periodic solution | 7.5 × 10⁻⁸ (return) | 1 × 10⁻⁵ | supported |

All nine scenarios were corroborated under both integrators; every primary run
reproduced exactly and the experiment ledger verified with no problems. The run
writes a report, a figure and an offline-observatory export.

### Other measured properties

- **Frame tie.** With the GMAT ICRF table enabled, ORRERY reproduces GMAT's
  Sun/Moon MJ2000Eq positions to the micrometre; the IAU-76/80 ITRF↔GCRF
  transform matches Vallado's worked example to the published digits.
- **N-body DE421 subset.** Tracks the ephemeris to < 1 km over 30 days with
  machine-precision energy conservation.
- **Orbit determination.** A noiseless 12-hour, three-station arc recovers the
  truth epoch state to sub-metre; a 6-hour single-station arc is correctly
  reported as rank-deficient.
- **Covariance.** For a small initial uncertainty the linear STM envelope is
  χ²-consistent with the Kepler Monte-Carlo cloud (≈ 95 % inside the 95 %
  ellipsoid); a large uncertainty shows the expected nonlinearity.

## Test execution

Run on the host above on 2026-11-07:

| Suite | Result |
|---|---|
| `pytest -m "not slow"` (full repository) | **437 passed, 7 skipped, 20 deselected**, 107.9 s |
| `pytest -m slow` (ORRERY GMAT, N-body, OD, acceptance) | **12 passed**, 345.1 s |
| `ruff check` + `ruff format --check` (src, tests, scripts) | clean, 150 files |
| `mypy` (configured scientific modules) | no issues |
| `atlas skills validate skills` | **30 skills valid** (8 new astrodynamics) |
| 8 astrodynamics skill examples in the bounded executor | all **PASS** |
| ORRERY celestial lab (`docs/orrery-lab.html`) | 6 views render in Chromium with CSP active; CSP SHA-256 pins match the inline script and style; no console errors |

**Not executed in this session:** the complete slow suite on both interpreters
(only the ORRERY slow subset was run here, alongside the full non-slow suite),
the Linux/POSIX paths, and hosted CI. The prior full-suite record is in
[VALIDATION.md](VALIDATION.md).

## Regenerating the GMAT references (needs a licensed GMAT R2026a)

```sh
# with GmatConsole.exe on PATH or at ~/tools/gmat-R2026a/GMAT/bin/
uv run python scripts/make_orrery_references.py
uv run python scripts/make_orrery_data.py          # DE421, EOP, ICRF table, JGM-3
uv run pytest -m slow tests/test_orrery_gmat.py    # re-check agreement
```

## Reproducing the experiment

```sh
uv run atlas experiment run orrery --root atlas-data/new-orrery
uv run atlas ledger verify atlas-data/new-orrery/ledger
```
