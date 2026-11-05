---
name: writing-style
description: Build a persistent, measurable portrait of an author's writing style (tone of voice) from their texts, keep it updated as new texts arrive, and write or rewrite text in that voice with a machine check against the author's own measured range. Use when asked to "profile my writing style", "capture our tone of voice", "learn how I write", "add these posts to my style profile", "update my voice profile", "write this in my voice", "rewrite this in our style", "does this sound like me", or when given a channel export, a folder of posts or a set of articles as a voice sample. Also use whenever a profiles/<who>/ folder exists and a text must match it. English texts.
license: MIT
compatibility: Requires python3 (3.9+), standard library only, and shell access to run scripts/style.py.
metadata:
  version: "2.0.0"
  origin: "Builds on style-skills by Vyacheslav Startsev (MIT)"
---

# writing-style

A **profile** is a folder that outlives the conversation: measured metrics, an evidence
map of the voice, generation rules, banned phrases, exemplars and a changelog. Build it
once, grow it with every batch of new texts, and write from it any time.

| Job | When | Read next |
|---|---|---|
| **Build** a new profile | sample texts, no `profiles/<who>/` yet | `references/build-workflow.md` |
| **Update** an existing profile | new texts for an author who has a profile | `references/update-workflow.md` |
| **Write** or rewrite in a voice | a profile exists and a text is needed | `references/writing-workflow.md` |
| Just **check** a draft | "does this sound like me?" | Write workflow, step 6 only |

Pick the job, open its reference file and follow it step by step. Do not work from this
page alone. No profile and the user wants text in a voice => offer to build one; never
imitate a voice from two samples.

## The profile folder

```
profiles/<who>/
├── profile.json      manifest: name, version, registers           (script)
├── sources.jsonl     ledger: one line per text, content hash      (script)
├── corpus/<register>/<hash>.md   the author's texts               (script)
├── metrics.json      layer A: features, p10/median/p90 bands,
│                     function-word Delta model, per register      (script)
├── history/          metrics of every previous version            (script)
├── CHANGELOG.md      one entry per build: texts, drift, edits     (script + agent)
├── portrait.md       layer B: voice map with evidence             (agent)
├── rules.md          layer C: the voice card read before writing  (agent)
├── bans.txt          banned phrases and AI tells, tiered          (agent edits)
└── exemplars/        good and anti passages with "why"            (agent)
```

Layer details and what goes in each field: `references/profile-layers.md`.

## The script

`scripts/style.py`, called by absolute path - `${CLAUDE_SKILL_DIR}` in Claude Code, the
directory this file was loaded from elsewhere:

```bash
S="${CLAUDE_SKILL_DIR:-<this skill's directory>}/scripts/style.py"
python3 "$S" init   profiles/<who>
python3 "$S" add    profiles/<who> <files|folders|flat file> [--register posts] [--telegram result.json]
python3 "$S" build  profiles/<who> --ngrams 25 --openers 10
python3 "$S" status profiles/<who>
python3 "$S" check  profiles/<who> draft.md [--register posts] [--strict]
```

Every feature, threshold and output line: `references/metrics-reference.md`.

## Non-negotiable rules

1. **Only the author's voice in the corpus.** Forwards, guest posts, quotes - out.
2. **Technique, not content.** Topics, names, products, one-off jokes never enter the
   portrait. Topic-bound traits go to "Content leakage".
3. **Measured or marked absent.** Every portrait claim rests on a metric or a passage
   actually read. Not seen => "not shown in corpus".
4. **The profile beats generic rules.** If the author uses a "tell" (dashes, lists,
   "robust"), it stays allowed; `build` lists such ban conflicts.
5. **Facts are locked.** Style changes form only. A missing fact becomes a visible
   `[fill: ...]`, never a plausible guess.
6. **Fix the text, not the thresholds.** Never edit `metrics.json` or loosen bands to
   pass a check. If no check ran, say so.
7. **Read `rules.md` fresh** before every writing task. Never from memory.
