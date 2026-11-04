# Contributing

Thank you for helping. ATLAS values verifiable behaviour over features, so
every contribution needs tests that actually run.

## Setup

```sh
uv sync --locked --python 3.12 # one-command development setup
uv run python scripts/check.py # lint, formatting, scientific API types, manifests, full tests
uv run pytest -m "not slow"
uv run pytest -m slow      # Phase 10 acceptance (several minutes)
```

For offline viewer interaction tests (Node 24; test-only dependency):

```sh
npm ci --prefix tests/web
npm test --prefix tests/web
```

Use [docs/TUTORIAL.md](docs/TUTORIAL.md) for the scientific workflow and
[docs/SKILL_AUTHORING.md](docs/SKILL_AUTHORING.md) for a tested reusable template.

## Adding a skill

1. Create `skills/<domain>/<name>/` with `SKILL.md` (Agent Skills
   frontmatter, only the six spec keys), `skill.json` (`atlas.skill/v1`),
   `run.py` defining `run(inputs, ctx)`, and at least one example:
   `examples/<example>.input.json` + `<example>.expected.json` (+ optional
   `<example>.files/`).
2. Expected outputs must be known answers derived independently of the skill
   (for example the true parameters of a synthetic signal), never values
   copied from the skill's own output.
3. Declare the least permissions the skill needs. Network and subprocess
   access are denied by default and require operator approval.
4. State limitations in both `SKILL.md` and `skill.json`.
5. `uv run atlas skills validate skills` and `uv run atlas skills test <name>`
   must pass.

## Code

- Small, tested components; match the surrounding style.
- Never weaken a ledger rule or executor check to make a test pass.
- Never edit recorded results; corrections are new `revision` records.
- Keep failures visible: failed runs and negative results are data.

## Commits and licensing

Contributions are accepted under the MIT License. Only submit code you wrote
or code whose license is compatible and attributed in `NOTICE.md`.
