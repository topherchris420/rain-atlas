# Notices and attribution

R.A.I.N. ATLAS is original Vers3Dynamics work released under the MIT License
(see `LICENSE`). It contains no code copied from other projects.

## Independence

ATLAS is an independent Vers3Dynamics project. It is not affiliated with,
endorsed by, or a partner of the U.S. Department of Energy, the Genesis
Mission, OSTI, or any national laboratory. Design lessons from the public
Genesis Skills repository and from the open Agent Skills format are described
in `docs/REFERENCES.md`; no code was taken from them.

## Formats and specifications

- `SKILL.md` frontmatter follows the open Agent Skills format
  (agentskills.io). ATLAS adds its own `skill.json` manifest.

## Runtime dependencies (not vendored; installed by the package manager)

| Package | License |
|---|---|
| NumPy | BSD-3-Clause |
| SciPy | BSD-3-Clause |
| Matplotlib | Matplotlib License (PSF-based, BSD-compatible) |

## Development dependencies

| Package | License |
|---|---|
| pytest | MIT |
| uv / uv_build (build backend) | MIT or Apache-2.0 |

The exact resolved versions are pinned in `uv.lock`.

## Reference data (ORRERY orbital-dynamics subsystem)

The `rain_atlas.orrery` engine is original Vers3Dynamics code. It ships small
excerpts of public reference data, used for validation only and unmodified
except for resampling to the committed epoch window:

| Data | Origin | Status |
|---|---|---|
| JPL **DE421** planetary/lunar ephemeris excerpt | NASA JPL (Standish 2009) | U.S. Government work, public domain |
| **IERS EOP C04** Earth-orientation excerpt | IERS / Paris Observatory | freely redistributable with attribution |
| **JGM-3** geopotential coefficients (8×8) | NASA GSFC / UT-CSR (Tapley et al. 1996) | public gravity model |
| GMAT **ICRF-to-FK5** tie table and **GMAT R2026a** reference trajectories | NASA General Mission Analysis Tool | GMAT is Apache-2.0; the table is its data, reference runs are regenerable and carry provenance |

NASA GMAT (the General Mission Analysis Tool) is licensed under the Apache
License 2.0. ATLAS copies no GMAT source code; it generates GMAT scripts, runs a
local GMAT installation to produce reference trajectories, and stores those
trajectories with their provenance (GMAT version, distribution MD5, binary and
report SHA-256) for code-to-code comparison. ATLAS is not affiliated with or
endorsed by NASA or the GMAT project.

## Scientific methods

Algorithms are implemented from the published literature cited in each
skill's `skill.json` (`references`) and in the module docstrings, for example
Welch (1967), Percival & Walden (1993), Rife & Boorstyn (1974),
Schwarz (1978), and Golub & Pereyra (2003). The orbital-dynamics engine follows
Vallado (2013), Montenbruck & Gill (2000), Dormand & Prince (1980),
Fehlberg (1968), Chenciner & Montgomery (2000) and the IAU-76/80 conventions.
