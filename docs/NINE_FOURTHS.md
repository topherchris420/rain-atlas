# Project Nine Fourths: computational research

Inspired by OpenAI, *The matrix multiplication exponent is nine fourths* (24 November 2026), sections 1 and 3. Its asymptotic arithmetic claim is not a practical BLAS replacement. We investigate contraction structure, not a claimed n^2.25 algorithm.

## Important finding

The historical planner uses einsum("ij,kl,blm,nm->bin", V,M,G,M). Indices j and k are separately reduced rather than joined. For V=M=I and G=diag(2,3), the legacy result has identical rows [2,3], not diag(2,3). Thus its score need not be the documented Gaussian coefficient information. This does not by itself establish that historical mission verdicts changed, but the interpretation of that planner term must be qualified.

The opt-in `parameter_information(..., method="factorized")` computes the intended 0.5 log det(I + P^-1 M G M^T) using the SPD determinant ratio and Cholesky. The historical default remains unchanged solely to preserve deterministic evidence replay. Do not use the legacy score as exact parameter information. Before migrating the live policy, version the policy and run a new preregistered held-out comparison including the original baseline and safety metrics. Preserve old records.

## Reproduce

```sh
uv run python -m rain_atlas.research.nine_fourths
uv run pytest tests/test_nine_fourths.py
```

The benchmark uses seeded positive-definite precision and Gram matrices, compares an independent direct solve baseline against a factorized batched Cholesky implementation, alternates timing order, and checks numerical agreement before recording medians. Timings are hardware-specific. PSD is a caller contract; inputs come from Gram construction. No policy or ledger default changes.

A local equivalent-kernel pilot with NumPy and OPENBLAS_NUM_THREADS=1 showed maximum absolute discrepancy below 5e-14; smaller shapes sped up, while the largest tested shape was slightly slower. No general speed claim or autonomous mission gain follows. The benchmark includes validation cost.
