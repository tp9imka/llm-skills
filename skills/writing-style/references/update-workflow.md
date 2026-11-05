# Update workflow - grow an existing profile with new texts

Profiles get better with data and voices change over time. An update adds texts,
re-measures, shows what moved, and revises the portrait only where the evidence
changed. `$S` is the absolute path to `scripts/style.py`.

## Step 1 - See what is there

```bash
python3 "$S" status profiles/<who>
```

It prints the version, texts and chars per register, exemplar and ban counts, texts
added since the last build, and files still holding template placeholders.

## Step 2 - Add the new texts

```bash
python3 "$S" add profiles/<who> new-posts/ --register posts
python3 "$S" add profiles/<who> notes.md --register status-updates --describe "weekly status updates"
```

- Already-seen texts are skipped by content hash, so you can pass a whole folder again.
- A new `--register` name creates a new register.
- Same filtering rule as the first build: only the author's own voice.
- To remove a text that should not be there, delete its file under `corpus/` (the
  ledger line in `sources.jsonl` can stay; the corpus on disk is the source of truth)
  and rebuild.

## Step 3 - Rebuild

```bash
python3 "$S" build profiles/<who> --ngrams 25 --openers 10
```

The previous `metrics.json` is archived to `history/metrics-v<N>.json`, the version is
bumped, and a `CHANGELOG.md` entry is appended. Read the report:

- **`drift vs v<N>`** - features whose median moved past the old p10-p90 band or by
  more than 20%. Each is a question: did the voice change, or did the new texts bring a
  different register or topic? Decide per feature:
  - new texts are a different kind of writing => move them to their own register and
    rebuild;
  - the voice genuinely changed (newer texts are the author now) => update the portrait
    and rules;
  - noise from a small batch => note it, change nothing.
- **`no drift`** - the new texts confirm the profile. Raise confidence on portrait
  items the new texts support.
- **`ban conflicts`** - new texts use something banned. Same rule: the author wins.

## Step 4 - Revise the portrait and rules

Read the new texts only (their files are listed in `sources.jsonl` with today's
`added` date). For each portrait item:

- confirmed by the new texts => keep, maybe raise confidence;
- contradicted => rewrite the item with the new evidence, or lower confidence;
- new technique not in the portrait => add it with evidence.

Then update `rules.md` numeric targets from the new `metrics.json` and any rule whose
portrait item changed. Add exemplars that cover moves the old set lacked; retire ones
the voice no longer uses.

## Step 5 - Record

Replace the last line of the new `CHANGELOG.md` entry with what changed and why, for
example:

```
- portrait/rules: hedges medium => high confidence (12 new posts); rules: sentence
  median 11 => 9 words; register status-updates added; exemplar 04 retired
```

If nothing changed: `reviewed, unchanged`. Report the version, the drift you found and
what you did about it.

## Comparing any two versions

`history/metrics-v1.json` and `metrics.json` have the same shape. To see how far a
voice moved over a year, diff the `overall.bands` medians of two versions.
