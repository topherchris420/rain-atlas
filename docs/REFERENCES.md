# References and lessons

ATLAS studied these public projects. No code was copied from them unless a
row says so. ATLAS is not affiliated with or endorsed by any of them.

## Genesis Skills (github.com/AI-ModCon/genesis-skills; read-only mirror at gitlab.osti.gov/genesis/genesis-skills)

BSD-2-Clause catalog of 36 Agent Skills for science and engineering, studied
at commit `70dce5a` (2026-10-30). Structure: `skills/<domain>/<skill>/SKILL.md`,
a flattening installer (`unpack.sh`), a `skill-search` meta-skill with
deterministic keyword ranking and progressive disclosure, a 208-rule
five-client frontmatter validator, a repo-policy checker and CI.

Lessons taken (ideas, not code):

1. **Keep `SKILL.md` to the six spec keys.** Most of Genesis' validator exists
   because clients parse frontmatter differently. ATLAS puts everything else in
   `skill.json`, which only ATLAS reads.
2. **Discovery stops at the first `SKILL.md`** and skill names must be unique
   catalog-wide, or flattened installs collide.
3. **Clients discover only direct children** of a skills directory, so nested
   catalogs need either flattening or a discovery meta-skill. ATLAS's registry
   installs into its own versioned store and can export a flattened copy.
4. **Prompt-only skills cannot be tested for scientific correctness.** Genesis
   skills are mostly instructions plus helper scripts with few output tests.
   ATLAS requires typed interfaces and known-answer examples for executable
   skills and labels prompt-only skills `kind: guidance`.
5. **Windows realities.** Symlink creation needs privileges, `core.autocrlf`
   breaks shell scripts, and long paths exceed MAX_PATH. ATLAS installs by copy,
   ships `.gitattributes` with LF, and keeps paths short.
6. **Generated inventories drift.** Genesis checks that README tables match the
   tree; ATLAS generates its skills table from the registry instead.

## R.A.I.N. Lab (lop-nur-twin; archived james_library)

Vers3Dynamics prior work. See [`INTEGRATION.md`](INTEGRATION.md). Conventions
adopted: preregistration before execution, closed action vocabularies, models
propose while deterministic code decides, digest-prefix operator approval,
`identity_verified: false`, explicit `generation` labels, "a digest is not a
signature".

## Agent Skills specification (agentskills.io)

`SKILL.md` frontmatter rules (name format, description length, optional keys)
are implemented independently in `rain_atlas.skills.frontmatter`.
