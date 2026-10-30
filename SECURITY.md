# Security

## What the executor does and does not protect against

ATLAS runs each skill in a separate Python process with:

- a wall-clock timeout and cancellation that kill the whole process tree;
- a memory cap (Windows job object; `RLIMIT_AS` on POSIX);
- on Windows, an active-process limit of 1 unless the skill was granted
  subprocesses, enforced by the operating system (it also stops process
  creation through `ctypes`, which is tested);
- a Python audit-hook guard that denies network access, subprocess creation,
  writes outside the run's output and temp directories, and reads outside the
  skill directory, the run's inputs, the interpreter's directories and the
  `rain_atlas` package (plus system fonts when a skill declares it);
- a minimal environment with no inherited secrets.

**The audit-hook guard is policy enforcement, not a sandbox.** Native code
(C extensions, `ctypes`) can bypass audit hooks. On POSIX there is no process
limit in v0.1, so native code could start processes. Network isolation for
native code is not provided on any platform. Do not run skills you would not
run as your own user. Untrusted installs must be approved with a hash-pinned
`atlas skills approve` after reading their code; a container backend for
untrusted skills is planned (see `docs/STATUS.md`).

## Data and credentials

- Ledgers, run directories and bundles can contain local paths (for example
  the Python executable path in each run's environment record). Review a
  bundle before sharing it.
- ATLAS never reads credentials and does not need any. Skills receive no
  environment variables beyond the allowlist in `exec/runner.py`.
- Approvals record `attestation: local-operator` and
  `identity_verified: false`. Hashes prove integrity of the history, not who
  wrote it.

## Web interface

There is no web interface in v0.1. The planned public site is a static,
read-only export with no execution endpoints; a local composer would bind to
`127.0.0.1` with a per-session token.

## Reporting a vulnerability

Please report security problems privately to the maintainers through the
repository's private vulnerability reporting (GitHub Security Advisories)
rather than in a public issue. Include the ATLAS version, platform, and a
minimal reproduction. We will acknowledge reports and credit reporters who
wish to be named.
