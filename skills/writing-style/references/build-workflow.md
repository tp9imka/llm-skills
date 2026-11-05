# Build workflow - create a profile from a corpus

Result: a complete `profiles/<who>/` folder that any later session can write from.
`<who>` is a short slug (`ivan`, `acme-blog`). `$S` is the absolute path to
`scripts/style.py`.

## Step 1 - Create the folder

```bash
python3 "$S" init profiles/<who> --name "<Display Name>"
```

Put `profiles/` where the author's material lives or at the project root. One author
per profile. A brand or a team voice is fine as long as the texts are written as it.

## Step 2 - Add the corpus, by register

A **register** is a kind of text with its own norms: `posts`, `articles`,
`review-comments`, `status-updates`, `emails`, `chat`. The same person writes a code
review differently from a LinkedIn post. Add each kind separately:

```bash
python3 "$S" add profiles/<who> posts/      --register posts    --describe "LinkedIn posts"
python3 "$S" add profiles/<who> reviews.md  --register review-comments --describe "PR review comments"
python3 "$S" add profiles/<who> --telegram result.json --register chat
```

| Source | How it is read |
|---|---|
| folder | every `.md` / `.txt` file is one text |
| one flat file | split on `---` / `***` / `===` / `___` lines, else on two blank lines; YAML frontmatter dropped |
| file with `### ` lines | split on those lines |
| `--telegram result.json` | one channel/chat export, forwards dropped (`--keep-forwards` to keep) |

`--min-chars 200` drops short replies. Duplicates (same text, whitespace-insensitive)
are skipped automatically, so re-adding a folder is safe.

Before adding, remove what is not the author's voice: guest posts, long quotes,
reposted announcements. Keep the counts of what you dropped for the portrait header.

How much is enough: 20 000+ characters overall, and at least 8 texts of 80+ words per
register for that register to get its own bands. Less still works, but `build` warns
and the portrait must say the data is thin.

## Step 3 - Measure

```bash
python3 "$S" build profiles/<who> --ngrams 25 --openers 10
```

Read the output:

- `corpus under 20000 chars` => note "portrait unstable" in the header.
- `bands not built ... for register X` => that register falls back to the overall
  bands. Note it.
- `ban conflicts` => phrases in `bans.txt` that the author actually uses. Delete those
  lines from `bans.txt` (or keep one with a comment explaining why). The author wins.
- `top_ngrams` / `top_openers` in `metrics.json` point at verbal formulas and ritual
  openings - verify each by reading, it may be topic.

## Step 4 - Read the corpus

Read `corpus/<register>/` in chunks, not all at once. Numbers capture geometry and
frequencies; reading captures what they miss:

- macro structure: how texts open, develop, end
- humor and its type, or its absence
- references: personal experience, data, other authors
- attitude to the reader: peer, student, customer, opponent
- how difficulty, mistakes and other people are framed
- how claims are supported and what counts as proof
- honesty markers: admitted gaps, open questions, "no number yet"
- ritual formulas, sign-offs, catchphrases
- the author's language level: an L2 writer's plain English is part of the voice, do
  not polish past it

## Step 5 - Write `portrait.md` (layer B)

Fill the template the script created. Every item carries `evidence:` (a metric or an
anonymized technique) and `confidence:` (`high` most texts / `medium` some / `low`
isolated). Fill "Anchor quotes" with 5-10 short verbatim passages that show technique,
not topic. List what you checked and did not find under "Absent".

## Step 6 - Write `rules.md` (layer C)

The voice card the writer reads before every text. Operational, not adjectival: not
"energetic and authoritative" but "open with the result in under 12 words; one long
sentence, then two short ones; end on what is still open". Numeric targets are copied
from `metrics.json`, not estimated. Add one block per register with only what differs.
Keep it under ~80 lines.

## Step 7 - Seed `exemplars/`

3-8 passages per register, chosen for coverage of different moves (an opening, an
explanation, an admission, an ending), not for recency. Optionally add anti-exemplars:
rejected drafts or texts that look close but are wrong. Format: one file each,

```markdown
---
kind: exemplar        # or: anti
register: posts
shows: [opening, short-long rhythm]
---
<verbatim passage, 1-6 sentences>

**Why:** <2-3 lines linking the passage to measured traits, e.g. "first line 9 words,
no period - first_line_no_period 0.8">
```

## Step 8 - Validate

1. **Held-out check.** Before Step 2, keep 2-3 of the author's texts aside (don't
   `add` them). Run
   `check` on them now: few deviations and a Delta inside the author's band are
   expected. Run `check` on one deliberately foreign text (corporate boilerplate):
   many deviations expected. Report both numbers.
2. **Blind write.** Have a fresh subagent (or a new session) write a short text from
   `rules.md` alone, then run `check` on it. Failures show which rule is missing.
3. **Author test.** If the author is the user, ask "does this sound like you?" and turn
   every "no, I'd never say X" into a `rules.md` line or a `bans.txt` entry.

## Step 9 - Finish

- Replace the last line of the `CHANGELOG.md` entry with what you wrote.
- `python3 "$S" status profiles/<who>` must show no template placeholders.
- Report: texts and chars per register, what was dropped, caveats, validation numbers.

## Common mistakes

| Mistake | Instead |
|---|---|
| Mixing registers in one bucket | `--register` per kind of text; a blended profile flattens all of them |
| Writing the portrait without reading the corpus | Numbers don't show humor, structure or attitude |
| Topics and names in the portrait | Technique yes, content no |
| Empty `evidence` | A claim without a number or technique doesn't count |
| Keeping bans the author violates | `build` lists them - the author's habits win |
| A profile from three posts with no caveat | Say the data is thin and lower confidence |
