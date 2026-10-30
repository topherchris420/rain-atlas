# ADR 0002: Bounded execution with OS limits plus an audit-hook guard

Status: accepted (2026-10-30)

## Context

Skills are arbitrary Python. The platform must run on a laptop (including
Windows on ARM, where containers are often unavailable) and still bound time,
memory, processes, file access and network access.

## Decision

Run every invocation in a fresh child process of the base interpreter with a
minimal environment. Bound it with OS mechanisms (Windows job object: memory,
kill-on-close, active-process limit; POSIX: `setrlimit` and a process group)
and a wall-clock timeout. Inside the child, install a `sys.addaudithook` guard
before importing the skill to deny network, subprocess, out-of-scope writes and
out-of-scope reads. The child's import path is filtered so that the host's
working directory is not readable.

## Consequences

- Works without containers and is fast enough for the reference experiment
  (about 60 runs).
- The audit-hook layer is policy enforcement, not a sandbox: native code can
  bypass it. This is stated in `SECURITY.md`; untrusted skills need hash-pinned
  approval, and a container backend is planned.
- Starting a fresh interpreter per run costs about 1–4 s on this hardware
  (x64 Python emulated on ARM64), dominated by importing SciPy.
