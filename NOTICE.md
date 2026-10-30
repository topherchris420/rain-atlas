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

## Scientific methods

Algorithms are implemented from the published literature cited in each
skill's `skill.json` (`references`) and in the module docstrings, for example
Welch (1967), Percival & Walden (1993), Rife & Boorstyn (1974),
Schwarz (1978), and Golub & Pereyra (2003).
