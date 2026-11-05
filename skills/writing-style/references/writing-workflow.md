# Writing workflow - write or rewrite text in a profiled voice

The profile is a specification: `rules.md` drives the writing, `metrics.json` and
`bans.txt` check the result. `$S` is the absolute path to `scripts/style.py`.

## Step 0 - Find the profile and the register

```bash
ls profiles/ 2>/dev/null && python3 "$S" status profiles/<who>
```

| What exists | What to do |
|---|---|
| a built profile | full workflow |
| profile with `pending_build` texts | run `build` first, it's cheap |
| `rules.md` but no `metrics.json` | write, tell the user no machine check ran |
| nothing | offer the build workflow; don't imitate a voice from two samples |

Pick the register that matches the requested text (a post, a review comment, a status
update). If none fits, use the overall rules and say which register you used.

## Step 1 - Lock the facts

Write down what must be said: claims, numbers, names, links, conditions, the level of
certainty ("probably", "measured", "not yet"). This list does not change during
styling. Anything the text needs but the input lacks becomes a visible
`[fill: what is missing]`. Input may be in any language; the output is in the profile's
language.

## Step 2 - Load the voice

Read, fresh, in this order: `rules.md` (all of it, plus the register block),
`bans.txt`, and the `exemplars/` for that register (anti-exemplars too). Read
`portrait.md` only if a rule is unclear.

## Step 3 - Lay out

Put the facts into the text template from `rules.md`. The template sets the order, not
the count: drop blocks you have nothing for, don't invent new ones. One idea per text
unless the register says otherwise.

## Step 4 - Write by `do`

Keep the numeric targets in mind from the first sentence - rewriting long periods into
short ones afterwards costs more. Borrow structure and moves from exemplars, never their
words.

## Step 5 - Proofread by `avoid`

One pass per `avoid` line, not one overall impression.

## Step 6 - Check by machine

```bash
python3 "$S" check profiles/<who> draft.md --register <register>
```

Fix in this order:

1. `banned phrases` - always rewrite.
2. `- not in profile ... foreign` - traits the author doesn't have at all.
3. `weak tells: N - cluster` - rewrite until below the cluster threshold.
4. `function-word delta ... further than the author's own texts` and the `passages
   furthest from the author` it lists - rework those passages first.
5. `past edge` lines with the largest percentages.
6. `unresolved placeholders` - leave them visible and list them for the user; never fill
   with a guess.

Under 120 words the script warns: only large deviations mean anything. Fix the text,
never the thresholds. If the script can't run, compare with the numeric targets by hand
and say no machine check ran.

## Step 7 - Fact-lock pass

Compare the draft with the Step 1 list: every claim, number, condition and certainty
level is still there and unchanged; nothing new appeared. A hedge turned into a
certainty is a changed fact.

## Step 8 - Report

Give the full text (never a sentence-level diff - style is visible only on the whole),
then the final `out of tolerance: X of Y` line, the Delta line, any deviation kept on
purpose with the reason, and the `[fill: ...]` gaps.

If the user rejects a draft, offer to save it to `exemplars/` as `kind: anti` with the
reason - rejected drafts are the cheapest way to sharpen a profile.

## Rewriting an existing text

Facts, numbers, links and the order of ideas stay. What changes: sentence and paragraph
length, connectives, punctuation, formatting, how the reader is addressed, the opening
and the ending. If the source was machine-written, strip generic slop first, then apply
the voice, then check - styling first and cleaning after would strip the author's own
traits as if they were tells.

## Do not

| Temptation | Why not |
|---|---|
| Borrow a joke, example or nickname from the corpus | Technique transfers, content doesn't - borrowed specifics read as plagiarism |
| Bend the text to hit numbers and break meaning | Metrics are a signal, not a goal |
| Polish past the author's level | An L2 writer's plain phrasing is part of the voice |
| Ignore "Content leakage" | It lists what must not transfer |
| Write in someone else's voice under your own name | Reads as parody at best, forgery at worst |
| Treat a pass on a 60-word text as proof | Short texts are noise; say so |
