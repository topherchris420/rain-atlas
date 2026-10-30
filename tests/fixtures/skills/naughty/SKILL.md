---
name: naughty
description: Test fixture that attempts forbidden operations so ATLAS's tests can confirm the executor blocks them. Never install outside tests.
license: MIT
---
# Naughty (test fixture)

`mode` selects one forbidden action: network, subprocess, write-outside,
read-outside, sleep, memory, or ok.
