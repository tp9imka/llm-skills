# Metrics reference - `scripts/style.py`

Standard library only, Python 3.9+, English word lists. `python3 style.py -h` and
`python3 style.py <command> -h` list every flag. Status lines go to stderr with `[i]`
(info) and `[!]` (warning); tables go to stdout.

## Commands

| Command | Does |
|---|---|
| `init <profile> [--name N]` | create the folder: manifest, empty ledger, `corpus/general/`, `exemplars/`, `history/`, `bans.txt` (copy of the default list), `portrait.md` and `rules.md` templates, `CHANGELOG.md` |
| `add <profile> <sources> [--register R] [--describe D]` | add texts to `corpus/<R>/`, skip duplicates by content hash, record each in `sources.jsonl` |
| `build <profile> [--ngrams N] [--ngram-size K] [--openers N]` | measure everything, archive the previous `metrics.json` to `history/`, bump the version, report drift and ban conflicts, append to `CHANGELOG.md` |
| `status <profile>` | version, texts per register, exemplars, bans, pending texts, unfilled templates |
| `check <profile> <draft> [--register R] [--strict] [--min-expected N]` | compare a draft to the profile |
| `metrics <sources> [--json F]` | one-off measurement of any texts, no profile |

Sources (`add`, `metrics`): files, folders (every `.md`/`.txt`), one flat file (split
on `---`/`***`/`===`/`___` lines or two blank lines, frontmatter dropped), a file with
`### ` lines, or `--telegram result.json` (one chat; forwards dropped unless
`--keep-forwards`). `--min-chars N` drops short texts.

Registers: lowercase letters, digits, hyphens. Default `general`.

## Features (layer A)

Text is tokenized on English words (apostrophes and hyphens kept inside a word). A line
break always ends a sentence. Common abbreviations (e.g., i.e., etc., Mr., a.m.) do not.
URLs are removed before counting words.

### `geometry`
| Key | Meaning |
|---|---|
| `text_chars_median`, `text_chars_mean` | text length in characters |
| `sentence_words_mean`, `_median`, `_sd` | sentence length in words |
| `burstiness` | sd / mean of sentence length - rhythm variation |
| `share_sentences_le7`, `_8_24`, `_ge25` | short / medium / long sentence shares |
| `paragraph_words_mean`, `paragraph_sentences_mean` | paragraph size |

### `lexicon`
| Key | Meaning |
|---|---|
| `ttr_raw` | unique / total words, length-dependent |
| `mattr_500` | moving-average TTR over 500-word windows; under 500 words falls back to raw TTR, so per-text bands partly track length |
| `hapax_share` | share of vocabulary used once |
| `word_length_mean` | characters per word |
| `flesch_reading_ease` | 206.835 - 1.015 x words/sentence - 84.6 x syllables/word (heuristic syllables) |
| `numbers_per_1000`, `contractions_per_1000` | numerals; don't / it's / we've / I'm |

### `markers_per_1000`
| Group | Examples |
|---|---|
| `pronouns_1sg` / `_1pl` / `_2` | I, me, my / we, us, our / you, your |
| `fillers` | just, actually, basically, kind of, I mean |
| `discourse_markers` | so, however, therefore, in fact, for example, that said |
| `hedges` | maybe, probably, seems, I think, usually, more or less |
| `boosters` | clearly, definitely, really, very, of course, always, never |
| `obligation` | must, should, need to, have to, required |
| `officialese` | utilize, leverage, in order to, with regard to, going forward |

Full lists: the `GROUPS` dict in `style.py`.

### `punctuation_per_1000`
`em_dash` (any `—`), `en_dash` (spaced `–` only, ranges excluded), `hyphen_as_dash`
(spaced ` - ` or `--` between words), `ellipsis`, `parenthetical` (5+ chars), `question`,
`exclamation`, `colon` (not `://`), `semicolon`, `quotes_curly`, `quotes_straight`
(pairs), `emoji`, `caps_words` (4+ capitals), `arrows` (`→`, `=>`, `->`).

### `formatting_per_text`
`bullet_items`, `numbered_items`, `markdown_headings`, `links`, `bold_italic`,
`first_line_no_period` (share), `first_line_chars` (mean).

### `bands`
p10 / median / p90 per feature across individual texts of 80+ words; built when there
are at least 8 such texts. `_texts_used` records how many.

### `function_words` (Burrows' Delta model)
Relative frequency of 117 topic-independent function words (the, of, but, I, would,
just...). Stores the per-word mean and sd across the author's texts, plus a `band`: the
p10/median/p90 of each text's leave-one-out Delta - how far the author's own texts sit
from the rest of their corpus. Function words are a stable authorship signal because
they don't depend on topic.

### `top_ngrams`, `top_openers`
Repeated phrases and first three words of texts. Pointers to read, not style by
themselves.

## `metrics.json` layout (from `build`)

```json
{
  "schema_version": 2, "profile": "ivan", "version": 3, "built": "2026-11-05",
  "corpus": {"texts": 64, "chars": 81234, "per_register": {"posts": 40, "review-comments": 24}},
  "overall":   { "meta": {}, "geometry": {}, "lexicon": {}, "markers_per_1000": {},
                 "punctuation_per_1000": {}, "formatting_per_text": {},
                 "bands": {}, "function_words": {} },
  "registers": { "posts": { "...same shape as overall..." } }
}
```

`registers` is empty when there is only one register.

## How `build` reports change

- **Drift**: for each banded feature, the new median is compared with the previous
  version's band. Reported when the new median is outside the old p10-p90 or moved more
  than 20%. Sorted by size.
- **Ban conflicts**: a `[strong]`/`[regex]` item found anywhere in the corpus, or a
  `[weak]` item used in at least one of every three texts. The author's habit wins -
  edit `bans.txt`.
- **CHANGELOG entry**: version, date, texts (+added), drift keys, conflicts, and a last
  line for the agent to fill with portrait/rules edits.

## How `check` decides

Reference: `--register R` uses that register's metrics if it has bands, otherwise the
overall profile (with a notice). A plain metrics JSON file also works as the reference
(no bans then).

1. **Rare-feature guard.** A per-1000 feature the profile's p90 predicts fewer than
   `--min-expected` (1.5) times at this draft length is skipped - unless the draft uses
   it more than 2x the profile maximum or the profile never uses it. Then:
   `<feature> - not in profile ... foreign`.
2. **With bands**: inside p10..p90 = `in range`; outside = `!!` with the distance past
   the nearest edge.
3. **Without bands**: relative difference from the mean against fixed tolerances
   (15-60%). Flags normal variation - build bands if you can.
4. **Function-word Delta**: the draft's Delta against the author's model. Above the
   author's own p90 => counts as a deviation. Not measured under 80 words. Drafts of
   300+ words also get **rolling windows** (~150 words, half-window step): up to three
   passages above the author's p90 are listed with their line number.
5. **Bans** (profile `bans.txt`): each `[strong]` or `[regex]` hit is a deviation, with
   its line. `[weak]` hits are listed; they count only when 3 or more appear (a
   cluster).
6. **Placeholders**: every `[fill: ...]` is listed as unresolved.

Summary line: `out of tolerance: X of Y` (features only); Delta, bans and weak clusters
are reported below it and also count for `--strict`. Exit 0 by default, 1 with
`--strict` when anything deviates. Under 120 words: "trust only large deviations".

## `bans.txt` format

```
# comment
[strong]
delve
[weak]            # count only in clusters of 3+
robust
[regex]           # Python regex, case-insensitive, multiline
\bnot (?:just|only) [^.,;!?\n]{1,40}, but\b
```

Lines before any section are strong. Plain phrases match whole words,
case-insensitively. The default list (`assets/default-bans.txt`) is dated; tells change
with model generations, so review it every few months.

## Thresholds

| Constant | Value | Effect |
|---|---|---|
| `MIN_CORPUS_CHARS` | 20 000 | below => "portrait unstable" |
| `BAND_MIN_WORDS` / `BAND_MIN_TEXTS` | 80 / 8 | bands and Delta need 8 texts of 80+ words |
| `SHORT_DRAFT_WORDS` | 120 | below => trust only large deviations |
| `DELTA_MIN_WORDS` | 80 | Delta not measured below |
| `WINDOW_WORDS` | 150 | rolling Delta window |
| `DRIFT_RELATIVE` | 0.20 | build drift threshold |
| `FOREIGN_RATIO` | 2 | foreign trait multiplier |
| `WEAK_TELL_CLUSTER` | 3 | weak tells count from this many |

## Limits

- English word lists; geometry, punctuation and formatting work for any language.
- No part-of-speech tagging: standard library only, by design.
- Delta and bands are calibrated on the author's own spread, not on other authors; they
  say "unlike this author", not "written by someone else".
- Genre transfers with style - use registers.
- Style and content can't be fully separated - "Content leakage".
