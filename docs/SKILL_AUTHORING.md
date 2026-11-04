# Writing and testing a scientific skill

Use an existing small skill as a working template. For scalar numerical
methods, copy `skills/computational-physics/pendulum-period/`; for array-in /
artifact-out methods, copy `skills/signal-processing/stft-analysis/`. These
are executable, known-answer-tested examples, not placeholder scaffolds.
Keep your new directory outside the built-in catalog until reviewed.

1. Rename the directory and the `name` in `SKILL.md` and `skill.json`; give it
   a new version and capability. The manifest's domain must be one of the
   declared schema domains. Never change an installed historical version.
2. Declare closed typed input/output schemas, units, dimensions, finite-value
   requirements, allowed ranges and workload bounds. Request only input reads
   and output writes. Supply package/version requirements and timeout/memory
   limits. Resource limits do not prove safe isolation.
3. Implement a pure typed numerical function, then a thin `run(inputs, ctx)`
   wrapper. Use `ctx.rng()` for seeded randomness, `ctx.load_array()` for
   hash-checked inputs, and `ctx.save_array()` / `ctx.save_text()` for artifacts.
   Return artifact references with matching hashes; the parent verifies them.
4. Derive expected answers independently: analytical identities, hand-computed
   fixtures or a separately implemented reference. Never copy the function's
   output into its expected file. Add positive, null and failure controls,
   precision checks and appropriate temporal/spatial convergence checks.
5. Document assumptions, uncertainty interpretation, numerical instability,
   invalid inputs, physical boundary conditions and cases where the method
   cannot establish a conclusion. A pleasing figure is not a validation test.

```sh
uv run atlas skills validate PATH_TO_NEW_SKILL
uv run atlas skills test PATH_TO_NEW_SKILL --runs-dir atlas-data/new-skill-tests
uv run pytest tests/test_your_numerical_method.py
```

`skills test PATH` is an explicit local-code execution request. Review the code
first. External unreviewed code should be installed with `--untrusted`; this
backend refuses to execute it, including after registry approval, until an
appropriate hardened executor exists. Do not relabel code merely to bypass
that refusal.

For larger manifests, `scripts/make_resonance_skills.py` demonstrates reusable
closed-schema helpers and analytically derived fixtures. Generation only writes
definitions and inputs; it never learns expected answers from a run. Existing
skills remain the canonical inspectable files and are versioned in Git.

The public scientific APIs are documented by docstrings and
`docs/RESONANCE.md`. mypy checks the whole `rain_atlas` package (with
`check_untyped_defs`, not `--strict`) on every CI Python version and on both
Linux and Windows. Fully annotated signatures (`--strict`) remain planned.
