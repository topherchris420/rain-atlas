# ADR 0001: Skill format — Agent Skills `SKILL.md` plus a typed `skill.json`

Status: accepted (2026-10-30)

## Context

Skills must be readable by agents that understand the open Agent Skills format,
and executable with typed, validated inputs and outputs. The Agent Skills
frontmatter allows only six keys, so typed interfaces cannot live there without
breaking compatibility.

## Decision

Each skill is a directory with `SKILL.md` (strict Agent Skills frontmatter and
human-readable method notes) and `skill.json` (`atlas.skill/v1`: version, kind,
domain, capabilities, JSON-Schema inputs/outputs, permissions, limits,
requirements, examples, references, limitations). Executable skills define
`run(inputs, ctx)` in a Python entrypoint and must ship at least one example
with an independently known expected output.

## Consequences

- Any Agent Skills tool can read the guidance; only ATLAS executes it.
- Validation is strict (unknown frontmatter keys, tabs, BOM and unquoted
  `": "` are errors), which rejects some files other tools tolerate.
- A small built-in JSON Schema subset validator avoids a dependency but
  refuses unsupported keywords (`$ref`, `if`), so manifests must stay simple.
