# ORRERY — orbital-dynamics engine

`rain_atlas.orrery` is an isolated, original orbital-mechanics engine for ATLAS.
It propagates Earth-centred and N-body trajectories, transforms between the
standard reference frames and time scales, estimates orbits from tracking,
propagates covariance, and checks itself against two independent references: the
closed-form two-body (Kepler) solution, and NASA **GMAT R2026a** reference runs.

This document states the **mathematical assumptions behind every capability** so
that a result can be read with its model in view. Measured agreement is in
[ORRERY_VALIDATION.md](ORRERY_VALIDATION.md). Two independent programs agreeing
is code-to-code *consistency*, **not** physical validation; only the two-body
cases have a genuine analytic truth.

## Scope and conventions

- **Frames.** Inertial states are in **MJ2000Eq** (the mean equator and mean
  equinox of J2000, GMAT's default, treated as coincident with GCRF to within
  the constant frame bias, which is **not** applied unless the ICRF tie is
  enabled). Earth-fixed states are in **ITRF** via the IAU-76/80 FK5 reduction.
- **Time.** Integration is carried in **TT seconds** from the epoch; the
  ephemeris is evaluated at **TDB**, approximated by TT (GMAT's approximation;
  the TT−TDB periodic difference is ≤ 1.7 ms and enters only third-body
  positions). Time scales TAI, TT, UTC (with leap seconds), UT1 (with ΔUT1 from
  EOP), TDB and A.1 are converted in `timescales.py`.
- **Units.** Kilometres, kilometres per second, seconds; angles in radians
  internally. Gravitational parameters μ = GM in km³/s².
- **Constants.** `constants.py` pins the GMAT R2026a values (μ⊕, R⊕, J2, Earth
  rotation rate, flattening) so the comparison is like-for-like; the source is
  recorded in `GMAT_CONSTANTS["source"]`.

## 1. Two-body motion (`kepler.py`)

Exact solution of the Kepler problem ÿr = −μ **r**/r³ by the **universal-variable
formulation** (Stumpff functions C(z), S(z)), advancing the universal anomaly χ
with a safeguarded Newton/bisection iteration on the Kepler equation in χ. The
classical elements (a, e, i, Ω, ω, ν) are recovered from the state via the
eccentricity and node vectors.

- **Assumes:** a single point mass; no perturbations. For a bound orbit this is
  the analytic truth and is used as such in the benchmarks.
- **Numerics:** the iteration brackets the root (the Kepler function is strictly
  increasing because its derivative ≥ 1 − e > 0 for e < 1), so it converges for
  all eccentricities exercised, including e = 0.74 (Molniya).

## 2. Force models (`forces.py`)

Each term supplies an acceleration and, where needed, its gradient ∂**a**/∂**r**
(for the state-transition matrix). The total right-hand side is assembled by
`ForceModel`.

- **Point mass** — −μ **r**/r³, with the exact Jacobian.
- **Oblateness J2** — the closed-form zonal-J2 acceleration in the body frame,
  with gradient. Assumes an axisymmetric second-zonal field only.
- **Spherical harmonics (JGM-3)** — the normalised geopotential to degree/order
  n×n evaluated by the **Montenbruck–Gill V/W recursion** in the Earth-fixed
  frame, rotated in from the inertial frame. The committed field is JGM-3 to
  8×8. Assumes the gravity coefficients are exact and static (no time-variable
  gravity, no tides).
- **Third bodies (Sun, Moon)** — the standard difference form
  μ_b( (**r**_b−**r**)/|**r**_b−**r**|³ − **r**_b/r_b³ ), with the perturbing
  body position from the DE421 excerpt (see §5). Assumes point-mass third
  bodies at their ephemeris positions.

Not modelled (named explicitly in `forces.NOT_MODELLED`): atmospheric drag,
solar-radiation pressure, solid-Earth and ocean tides, general-relativistic
corrections, Earth albedo/IR, continuous thrust, and the constant IERS frame
bias. Omitting these bounds the physical fidelity; it does **not** affect the
code-to-code comparison, which uses the same force set on both sides.

## 3. Numerical integration (`integrators.py`)

Explicit Runge–Kutta with embedded error estimate and PI/elementary step
control. Two embedded pairs are implemented from their published Butcher
tableaux — **Dormand–Prince 5(4)** and **Runge–Kutta–Fehlberg 7(8)** — plus
fixed-step classical RK4, and symplectic Störmer–Verlet and Yoshida-4 for the
conservative N-body checks. SciPy's DOP853 is available as an independent
cross-check integrator. The initial step follows Hairer's heuristic; the error
norm offers a mixed abs/rel RMS and GMAT's RSS-step form.

- **Assumes:** a smooth, non-stiff right-hand side (true for gravitational
  orbits). The empirical convergence order of each method is pinned by a test
  (RK4 → 4.1, DP54 → 4.9, RKF78 → 8.2, Verlet → 2.0, Yoshida-4 → 4.0).
- **Tolerances:** benchmark runs use rtol = atol = 1e-12. The error estimate is
  on the position/velocity slice, not on the 36 STM components.

## 4. Reference frames and time (`frames.py`, `timescales.py`, `eop.py`)

The MJ2000Eq ↔ ITRF transform is the **IAU-76 precession, IAU-80 nutation (106
terms), IAU-82 GMST, and polar motion** chain, with Earth-orientation
parameters (ΔUT1, polar motion x_p/y_p, LOD, nutation corrections) interpolated
from the committed IERS C04 excerpt. The velocity transform includes the Earth
rotation term **ω⊕ × r**.

- **Assumes:** the supplied EOP series spans the epoch; the constant frame bias
  between ICRF and FK5 (≈ 23 mas) is omitted. Validated against **Vallado's
  worked ITRF↔GCRF example** to the published digits (see the frames test).

## 5. Ephemerides and the frame tie (`ephemeris.py`)

Sun and Moon positions come from a **JPL DE421** excerpt resampled around the
2026-01-15 epoch (`data/de421_2026.json`). To reproduce GMAT's inertial
positions exactly, the Sun/Moon vectors are rotated from the DE421 ICRF frame to
MJ2000Eq by GMAT's own **ICRF-to-FK5 table** (`ICRF_Table.txt`, order-9 Lagrange
interpolation of daily Euler vectors, applied as an axis–angle rotation). The
tie is configurable: `"gmat-icrf-table"` (default, reproduces GMAT to µm) or
`"none"`.

- **Assumes:** the DE421 excerpt and the tie table are the authoritative body
  positions; TDB ≈ TT.

## 6. N-body dynamics (`nbody.py`)

Direct summation of pairwise Newtonian gravity for N point masses, with total
energy, linear and angular momentum and the barycentre as conserved diagnostics.
Two systems: the **Chenciner–Montgomery figure-eight** equal-mass choreography
(a published periodic solution; its return to the initial configuration after
one period and its conserved integrals are exacting tests), and a **DE421-seeded
Solar System** subset compared back against the ephemeris.

- **Assumes:** Newtonian point masses; no relativity, oblateness or minor
  bodies (the measured DE421 residual).

## 7. Orbit determination (`od.py`)

Iterated **batch least squares**. Ground stations produce range and range-rate
(and elevation for visibility) from the station's inertial position and velocity;
the measurement partials and the force-model state-transition matrix (integrated
as the 6+36 variational state) form the normal equations, solved with an
optional a-priori. A noiseless identical-twin arc recovers the truth state to the
numerical floor; a consistency study reports the normalized error (NEES) against
χ²(6).

- **Assumes:** Gaussian measurement noise, an observable arc (a short single
  station leaves a weakly observed direction — a rank check guards this), and
  the same dynamics in simulation and estimation (a closed experiment).

## 8. Covariance propagation (`covariance.py`)

A state covariance is mapped through the state-transition matrix,
**P(t) = Φ(t,t₀) P₀ Φᵀ**, and checked against a Monte-Carlo cloud propagated by
the exact Kepler flow. For a small (near-linear) initial uncertainty the 95 %
ellipsoid should contain ≈ 95 % of the samples; a large uncertainty exposes the
nonlinearity (lower consistency), which is reported rather than hidden.

- **Assumes:** the linear (first-order) map is adequate over the interval; the
  Monte-Carlo truth uses point-mass dynamics.

## 9. Transfers (`transfers.py`)

Closed-form **Hohmann** two-burn transfer between coplanar circular orbits
(Δv₁, Δv₂, time of flight) and a bisection search for a lunar free-return-style
transfer that targets a chosen closest approach, propagated with the full force
model. Impulses are instantaneous velocity changes.

## 10. Scenarios and GMAT bridge (`scenarios.py`, `gmat.py`)

`scenarios.py` fixes the frozen initial states and configurations for the
validation set: analytic two-body cases **S1 LEO / S2 Molniya / S3 GEO**, and
perturbed cases **S4 LEO+J2 / S5 HEO+J2 / S6 GEO+J2+Sun+Moon / S7 LEO+JGM-3 8×8
/ S8 Earth–Moon TLI**, plus N-body **S9/S10**. `gmat.py` generates the GMAT
`.script` for each scenario, runs `GmatConsole.exe`, parses the report, and
stores the reference trajectory with full provenance (GMAT version, distribution
MD5, binary SHA-256, script/report SHA-256). The committed references under
`reference/gmat-R2026a/` let the comparison run without a GMAT install; see the
validation document for how to regenerate them.

## What this engine does not claim

- It is **not** validated against real tracking data or flown missions.
- Agreement with GMAT is bounded by the shared assumptions above; both programs
  omit the same unmodelled forces in each scenario.
- Only the two-body scenarios have an analytic truth. Everything else is
  consistency between two independent implementations, reported with its
  tolerance.
