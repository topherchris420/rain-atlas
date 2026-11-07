# BLACK GLASS firmware analysis — ExampleOS-v1

Protocol `blackglass.firmware-analysis/v1`, engine `0.1.0`. Source tar, digest `c5e0fff111bd`, tree manifest `b2c61b9cba49`.

Confidence legend: **verified** = independently re-checkable (hash, signature, re-parse); **high/medium/low** = static inference about a *possible* capability; **unverifiable** = evidence to decide was absent. A static analyser never observes runtime behaviour.

## Inventory

14 files — config: 5, elf: 6, key-material: 1, package-manifest: 1, script: 1. ELF architectures: {'x86-64': 6}.

Setuid binaries: ['usr/bin/config-helper'].

## Services

| service | init | runs as | starts | requires |
|---|---|---|---|---|
| config.service | systemd | root | usr/bin/config-helper | — |
| httpd.service | systemd | www | usr/sbin/httpd | config.service |
| telnetd | sysv | (default) | usr/sbin/telnetd | $network |

## Network surface (static)

| component | kind | port | confidence | evidence |
|---|---|---|---|---|
| etc/dropbear/dropbear.conf | port-declared | 22 | high | etc/dropbear/dropbear.conf:line 1 |
| etc/httpd/httpd.conf | port-declared | 8080 | high | etc/httpd/httpd.conf:line 2 |
| etc/httpd/httpd.conf | port-declared | 8443 | high | etc/httpd/httpd.conf:line 5 |
| usr/sbin/httpd | socket-symbol | — | medium | ELF .dynsym (undefined imports) |
| usr/sbin/telnetd | socket-symbol | — | medium | ELF .dynsym (undefined imports) |

## Integrity & signatures

| subject | method | status | detail |
|---|---|---|---|
| ExampleOS-v1 | sha256-manifest | verified | 14 baseline entries: 14 matched, 0 mismatched, 0 missing, 0 unlisted file(s) present |
| fw-v1.tar.gz | ed25519/ed25519_ref | verified | signature valid |

## Findings

18 findings; each links to evidence and a cross-check.

| id | kind | confidence | statement | cross-check | evidence |
|---|---|---|---|---|---|
| FND-0001 | component | verified | The image contains 14 files: config=5, elf=6, key-material=1, package-manifest=1, script=1; ELF architectures: {'x86-64': 6} | corroborated | tree manifest — |
| FND-0002 | component | verified | bin/busybox is a 64-bit little-endian x86-64 ELF DYN (PIE), needs ['libc.so.6'] | corroborated | ELF header + .dynamic `a807d9873334` |
| FND-0003 | component | verified | lib/libc.so.6 is a 64-bit little-endian x86-64 ELF DYN | corroborated | ELF header + .dynamic `789a1c989e92` |
| FND-0004 | component | verified | lib/libssl.so.1 is a 64-bit little-endian x86-64 ELF DYN, needs ['libc.so.6'] | corroborated | ELF header + .dynamic `041db5c5dccd` |
| FND-0005 | component | verified | usr/bin/config-helper is a 64-bit little-endian x86-64 ELF DYN (PIE), needs ['libc.so.6'] | corroborated | ELF header + .dynamic `55c55a24b77a` |
| FND-0006 | component | verified | usr/sbin/httpd is a 64-bit little-endian x86-64 ELF DYN (PIE), needs ['libc.so.6', 'libssl.so.1'] | corroborated | ELF header + .dynamic `ac65a81499bd` |
| FND-0007 | component | verified | usr/sbin/telnetd is a 64-bit little-endian x86-64 ELF DYN (PIE), needs ['libc.so.6'] | corroborated | ELF header + .dynamic `3c6aade923f1` |
| FND-0008 | service | verified | Service config.service (systemd) runs as root, starts usr/bin/config-helper | corroborated | etc/systemd/system/config.service — |
| FND-0009 | service | verified | Service httpd.service (systemd) runs as www, starts usr/sbin/httpd, requires ['config.service'] | corroborated | etc/systemd/system/httpd.service — |
| FND-0010 | service | verified | Service telnetd (sysv) runs as default user, starts usr/sbin/telnetd, requires ['$network'] | corroborated | etc/init.d/telnetd — |
| FND-0011 | network | high | etc/dropbear/dropbear.conf: declares port 22: Port 22 (port 22) | corroborated | etc/dropbear/dropbear.conf:line 1 `483cc024c3fc` |
| FND-0012 | network | high | etc/httpd/httpd.conf: declares port 8080: Listen 8080 (port 8080) | corroborated | etc/httpd/httpd.conf:line 2 `b1c6b82aca45` |
| FND-0013 | network | high | etc/httpd/httpd.conf: declares port 8443: Listen 8443 (port 8443) | corroborated | etc/httpd/httpd.conf:line 5 `b1c6b82aca45` |
| FND-0014 | network | medium | usr/sbin/httpd: imports accept, bind, listen, socket; bind+listen suggests a server | corroborated | ELF .dynsym (undefined imports) `ac65a81499bd` |
| FND-0015 | network | medium | usr/sbin/telnetd: imports bind, listen, socket; bind+listen suggests a server | inconclusive | ELF .dynsym (undefined imports) `3c6aade923f1` |
| FND-0016 | trust-boundary | high | usr/bin/config-helper is setuid (mode 0o4755) | inconclusive | usr/bin/config-helper — |
| FND-0017 | integrity | verified | sha256-manifest: verified — 14 baseline entries: 14 matched, 0 mismatched, 0 missing, 0 unlisted file(s) present | corroborated | verification — |
| FND-0018 | signature | verified | ed25519/ed25519_ref: verified — signature valid | corroborated | signature over fw-v1.tar.gz `c5e0fff111bd` |

## Service / dependency graph

- DOT: `graph.dot`
- SVG: `graph.svg`

## Limitations

- Static analysis only: the firmware is never executed, so no finding is a runtime observation.
- Linking a symbol (e.g. bind/listen) is evidence of a capability, not proof the code path runs; such findings are inferences with medium or low confidence, never confirmed behaviour.
- Dependency edges come from declared DT_NEEDED entries and init metadata; dlopen() and other dynamic loading are invisible to static analysis.
- Port declarations in configuration are the shipped defaults; a running device may be reconfigured.
- Only tar, zip and already-extracted directories are parsed. squashfs, cpio, raw flash and encrypted blobs are reported as unsupported and left uninterpreted rather than guessed at.
- Integrity and signature results are only as trustworthy as the operator-supplied trust anchors; without an anchor the verdict is 'unverifiable', never 'valid'.

## Reproduce

```sh
uv run atlas firmware analyze <image> --root atlas-data/firmware --label ExampleOS-v1
uv run atlas ledger verify atlas-data/firmware/ledger
```

A hash chain establishes internal integrity, not authenticity or truth. Every finding above can be re-derived from the recorded image bytes.
