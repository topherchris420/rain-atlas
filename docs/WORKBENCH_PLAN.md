# Scientific workbench implementation

The existing registry, bounded executor, append-only ledger and four scripted
roles remain the core. Numerical methods remain ordinary Python functions.
No hosted service, model, paid dependency or replacement orchestration layer
is needed.

## Reviewable stages

1. Audit and integrity repair: `exec/{context,runner,child,policy}.py`,
   `ledger/{store,records}.py`, spectral bundle export, regression tests and
   CI configuration. Reproduce the baseline before editing.
2. Observatory: `observatory/export.py` and packaged HTML/CSS/JS;
   verified, explicitly selected ledger export, experiment/evidence/timeline/
   skills/report views and a browser-only proposal composer. No execution
   endpoint. Export tests include injection, missing data and sealed truth.
3. Resonance: `science/resonance.py`, executable skills and known answers;
   `experiments/synchronization.py` composes existing roles and executor.
   Validate analytical cases, convergence, independent estimators, noise,
   independent seeds and model misspecification before interpreting results.
4. Skepticism and reproducibility: `science/uncertainty.py`, benchmark runs,
   evidence dependencies, derived local search index, proposal validation,
   documentation, full regressions and an actual end-to-end demonstration.

## Domain and role contracts

| Caller | Callee / action | Input → output |
|---|---|---|
| Operator | PI.preregister | Question, H0/H1, controls, thresholds, budget → immutable experiment |
| PI | Registry.select | Capability → enabled, policy-compatible SkillRef |
| Scientist / skeptic | Engineer.execute | Experiment, skill, inputs, seed → recorded RunResult |
| Scientist | Ledger.append(claim) | Successful run references, units, uncertainty → computed claim |
| Skeptic | Ledger.append(challenge) | Different method / independent data → explicit outcome |
| Engineer | Engineer.reproduce | Original run → output/artifact comparison |
| PI | disagreement.verdict / report | Challenges + reproduction → computed verdict and limitations |
| Operator | Observatory export | Verified ledger → offline review snapshot |

The engineer alone executes skills. The skeptic owns challenges. The PI owns
preregistration and reporting. Model text, when imported, is only a proposal;
it cannot count as evidence or approve execution.

## Acceptance

- Full `pytest` retains spectral-recovery acceptance and adds numerical,
  integrity, proposal and export adversarial tests.
- `atlas experiment run synchronization` exits within a declared budget,
  records primary and independent runs, challenges and reproduction, then
  verifies its ledger and writes reports and scientific figures.
- `atlas observatory export …` opens directly as a local HTML file; no
  requests, external assets or execution routes; all displayed results come
  from recorded data. Missing results and test status remain unknown.
- Formatting, lint and whole-package type checks run in CI. Hosted
  matrix results are reported only if the jobs actually execute.

## Initial environment evidence

Baseline commit: `0b4568259a12540d93c6d0f72f1c315518755aa4`.
Local Windows x64 Python 3.12.15 (ARM64 host), NumPy 2.5.4, SciPy 1.18.1,
Matplotlib 3.11.2: baseline non-slow tests **112 passed, 1 skipped,
7 deselected, 83.90 s**. The skip is Windows symlink privilege.

GitHub Actions run `41103222445`: all four jobs failed **before starting**.
Check annotations explicitly report an account payment/spending-limit block.
Logs do not exist. This is not evidence of a Python test failure. Billing and
repository visibility will not be changed; hosted results remain blocked.
