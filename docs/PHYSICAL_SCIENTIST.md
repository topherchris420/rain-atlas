# ATLAS Physical Scientist: evidence-first vertical slice

> **Status: software prototype only.** No PCB, firmware, hardware driver, enclosure,
> synchronized DAQ, electrical validation, physical bring-up, or physical experiment
> is provided here. A simulated three-act narrative is **not** a physical discovery,
> and this code does not implement autonomous language-model-driven science.

## First research question

Can a sequential experiment selector distinguish preregistered competing
single-mode resonator transfer functions when it must predict measurements
before learning their values?

The initial model is the damped harmonic-oscillator frequency response:

\[
A(f; f_0,Q,g) = \frac{g}{\sqrt{(1-(f/f_0)^2)^2 + (f/(Qf_0))^2}} .
\]

This is an intentionally modest **reduced-order surrogate**. It is not a
plate-bending FEM, not a spatial mode predictor, and not a calibrated sensor
model. A prediction concerns one normalized response measurement at one
frequency, not a camera image or Chladni pattern.

The deterministic Experimentalist selects a frequency maximizing weighted
between-model predictive variance divided by assumed noise variance. **This
is a discrimination proxy, not exact expected information gain.** The
Statistician uses frozen Gaussian likelihoods to update weights. Assumed
noise, fixed model class and unmodeled effects limit its validity.

## Run: reproducible simulation

From the checked-out repository:

~~~sh
uv sync --locked
uv run python scripts/physical_scientist.py demo --root atlas-data/physical-demo --seed 7
uv run atlas ledger verify atlas-data/physical-demo/ledger
~~~

Open the printed \`observatory/index.html\` directly in a browser. The
existing verified offline exporter displays preregistered candidate
predictions, observed values labeled **synthetic**, revised weights,
negative results and a one-point holdout comparison. The resulting
directories are new and never overwritten.

Three acts: preregister a contested prediction; observe simulated
contradiction and select a new frequency; preregister and measure a
previously withheld frequency, then compare original and revised
squared error. The 187 Hz holdout is fixed in source code; it does
**not** establish apparatus-configuration generalization. An
\`improved: false\` outcome is preserved as data, not suppressed.

For sensitivity and negative controls, change \`--truth-hz\` and use a
fresh output root. Simulated ground truth is known to the demo operator
and is **not independently blinded** to the process.

## Manual measurements: operator-attested only

No device is operated by this software. The user must obtain and
calibrate a measurement **outside** ATLAS and explicitly attest its
provenance. Acquisition hardware, calibration references, and timestamps
are not cryptographically authenticated.

~~~sh
uv run python scripts/physical_scientist.py plan \
  --ledger atlas-data/manual-ledger \
  --models "low:170" "high:190" --weights 0.5 0.5 \
  --sigma 1.5 --candidates 165 170 175 180 185 190 195
~~~

Record the printed experiment hash. The operator's CSV must contain
exactly one row, with the preregistered frequency and one **normalized**
response in compatible units:

~~~csv
frequency_hz,response
190,8.41
~~~

**Do not treat that example value as an actual observation.** It is a
format illustration only. Import real data only when independently
acquired:

~~~sh
uv run python scripts/physical_scientist.py observe \
  --ledger atlas-data/manual-ledger --experiment sha256:EXPERIMENT \
  --csv measurement.csv --operator OPERATOR_NAME \
  --instrument-id INSTRUMENT_ID --calibration-ref CALIBRATION_SHA \
  --acquired-at-utc 2026-11-14T12:00:00Z

uv run python scripts/physical_scientist.py evaluate \
  --ledger atlas-data/manual-ledger --experiment sha256:EXPERIMENT \
  --observation sha256:OBSERVATION

uv run python scripts/physical_scientist.py export \
  --ledger atlas-data/manual-ledger --out atlas-data/manual-review
~~~

The importer enforces exact preregistration frequency, finite bounded
values, a single observation per experiment, raw-byte preservation,
source-specific provenance, and ledger verification. Hash chaining
detects modifications **within the record**, not a dishonest operator
or incorrectly calibrated instrument.

### Evidence classes

| Level | Evidence | Present? |
|---|---|---|
| S0 | Numerical reduced-order simulation, reproducible code | **Implementation added; execution/CI to verify** |
| S1 | Electrical schematic review, ERC/DRC, fault analysis | Not provided |
| S2 | Mechanical drawings, fit, thermal and assembly verification | Not provided |
| S3 | PCB/firmware bring-up, logged interlock and watchdog tests | Not provided |
| S4 | Calibrated, time-synchronized real vibration and video | Not provided |
| S5 | Independent physical replication vs baselines | Not provided |

## Proposed hardware, not an approved wiring design

The smallest proposed bench comprises a Raspberry Pi 5 host, a
Raspberry Pi Pico 2 (RP2350) microcontroller for deterministic
acquisition and watchdog supervision, a low-power I2S amplifier
driving a properly matched miniature exciter, a contact accelerometer,
and an overhead Camera Module 3. The Linux host must **not** be
trusted to enforce actuator safety. Physical E-stop and watchdog
cutoff must remove amplifier power independently.

| Candidate | Source | Public price reference* | Engineering caveat |
|---|---|---:|---|
| Raspberry Pi 5, 2 GB | https://www.raspberrypi.com/products/raspberry-pi-5/ | $77.50 list price, Nov 2026 brief | Use appropriate **5 V, 5 A USB-C** supply; separate actuator rail |
| Pico 2, RP2350 | https://www.raspberrypi.com/products/raspberry-pi-pico-2/ | from $5 | Prototype module, **not** a custom instrumentation PCB |
| MAX98357A mono I2S amp | https://www.adafruit.com/product/3006 | $5.95 | 5 V, 3.2 W at 4 ohm **10% THD**; output not a precision actuator voltage |
| ADXL345 digital accelerometer | https://learn.adafruit.com/adxl345-digital-accelerometer/overview | $17.50 | Requires sensitivity, ODR and mounting calibration |
| Camera Module 3 | https://www.raspberrypi.com/products/camera-module-3/ | from $25 | Rolling shutter and timestamps need characterization |
| Exciter, plate, frame, supply, interlock, connectors | **Not selected** | TBD | Electrical/structural design and procurement required |

*Public listed/reference prices inspected November 2026, not vendor quotes.
The listed electronics subtotal is **about $131**, excluding actuator,
mechanics, power, interlocks, sensors beyond one accelerometer,
PCB, cables, taxes and shipping. There is no costed build-ready BOM yet.

Reference electrical sources:
- Pi 5 supply: https://www.raspberrypi.com/products/raspberry-pi-5/
- Pico 2 board: https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html
- Amplifier and thermal limits: https://www.adafruit.com/product/3006

**Hard safety gate:** No MCU firmware, actuator pin mapping, power
distribution PCB or enclosure is supplied. All GPIO and amplifier
connections are explicitly **TBD**, and no one should wire an actuator
from this document. Proposed future controller shall require explicit
human class authorization, bounded setpoints, independent watchdog,
latched E-stop, overtemperature and current faults, load-disconnect,
and fail-closed startup. Those protections must be tested at S3.
Changing experimental class or bounds requires operator approval.

## Next experiments and falsifiable gates

1. **Replicate S0** across seeds and truth models, preserve negative
   results, and benchmark against random, uniform sweep, exact Bayesian
   design and classical system identification at matched measurements,
   energy, and false-identification probability.
2. **Build S1/S2**: revised electrical block diagram, real parts/footprints,
   KiCad schematic/PCB, harness pinout, enclosure CAD, ERC/DRC, tolerance,
   EMI, power and thermal review. Never label unbuilt files fabrication-ready.
3. **Build S3**: independent cutoff circuit, MCU DAQ firmware, signed
   calibration manifests, timestamp synchronizer and device API. Hardware
   commands disabled until monitored interlocks pass on the actual board.
4. **Reach S4**: independently calibrated sensor response, camera-vibration
   correspondence, repeated membrane modes, model discrepancy and
   cross-configuration holdouts, including failures.
5. **Reach S5**: blind evaluation across distinct plates, baselines and
   adversarial nuisance changes, with prespecified sample efficiency,
   calibration, predictive score and uncertainty.

## Seven-lens technical review (not a review by Anthropic personnel)

| Lens | What this slice achieves | Blocking weakness |
|---|---|---|
| Originality | Falsifiable, immutable competing predictions | No demonstrated discovery beyond standard system identification |
| Method | Ledger and precommitted decision rule | One synthetic holdout; no physical replication |
| AI capability | Deterministic adaptive selector baseline | No language model integrations; no comparison advantage shown |
| Alignment | No physical command path or network authority | Hardware safety not designed or tested |
| Interpretability | Frozen model parameters, selection rule, posterior and residual | No validated mechanistic explanation of a real plate |
| Engineering | Reproducible offline Python test path | No KiCad, Gerber, mechanical CAD, firmware or assembly instructions |
| Long-term value | Ledger and observatory can house verified physical runs | Need modality-neutral signed acquisition and independent verification |

**Decision:** Software prototype only; **not** approved for physical
actuation, publication of scientific performance claims or
manufacture. A failed physical experiment should be retained unchanged
alongside the model revision it motivates.
