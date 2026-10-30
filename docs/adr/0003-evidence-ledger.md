# ADR 0003: Content-addressed, hash-chained evidence ledger with sealed truth

Status: accepted (2026-10-30)

## Context

Results must be traceable to the exact code, inputs and seeds that produced
them; history must not be silently editable; and ground truth for validation
must be fixed before analysis without being visible to it.

## Decision

Store every record and artifact as an immutable object addressed by the
SHA-256 of its canonical bytes, and append one line per record to a
hash-chained log. `verify()` recomputes the chain, every object hash, and
record rules (references precede, category rules, seal/unseal commitments,
approval attestations, verdict targets). Ground truth is sealed as
`sha256(salt ‖ canonical(value))`; the salt and value stay in a vault until an
`unseal` record that must follow the analysis records it names.

## Consequences

- Any edit, deletion or reordering of history is detected.
- A digest is not a signature: verification proves internal consistency, not
  authorship. Approvals say `identity_verified: false`.
- Sealing proves commitment, not secrecy from the host process. Secrecy from
  analysis comes from the executor guard and from roles that never read the
  vault.
