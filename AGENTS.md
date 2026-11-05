# AGENTS.md

Rules for agents editing this repository. Users of the skills read `README.md`.

## Layout

- `skills/<name>/` - one folder per skill, Agent Skills format (agentskills.io).
- `.claude-plugin/marketplace.json` - one plugin entry per skill (`source: "./"`,
  `strict: false`, `skills: ["./skills/<name>"]`). No per-skill `plugin.json`.
- `tests/` - stdlib `unittest`, one file per skill.

## Rules

- `SKILL.md` frontmatter uses standard fields only: `name`, `description`, `license`,
  `compatibility`, `metadata` (string values). `name` equals the folder name.
- Keep `SKILL.md` a short router; detail goes to `references/`, one level deep.
- Scripts are standard library only unless the skill's `compatibility` says otherwise.
  Name thresholds as constants; status to stderr with `[i]` / `[!]`, data to stdout.
- All content in English. Plain hyphens in prose, no em dashes outside code that
  counts them.
- A new or changed skill updates the README catalog, the marketplace entry and its tests.

## Verify before committing

```bash
python3 -m unittest discover tests -v
claude plugin validate .
```
