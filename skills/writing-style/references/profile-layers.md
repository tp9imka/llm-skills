# The three layers of a style profile

Mixing the layers in one flat document does harm: they have a different nature, a
different author, and are verified differently.

| Layer | Filled by | File | Verified by |
|---|---|---|---|
| A. Measured | `style.py build` | `metrics.json` | recomputation, `style.py check` |
| B. Voice map | the agent, from the corpus | `portrait.md` | evidence and confidence on every item |
| C. Generation rules | the agent, from A and B | `rules.md`, `bans.txt`, `exemplars/` | the text written from them |

**Layer A** is objective: lengths, shares, rates per 1000 words, punctuation,
formatting, readability, and a function-word model. Each feature has a per-text band
(p10 / median / p90), the author's natural spread, overall and per register.

**Layer B** interprets what a counter cannot see: persona, attitude, humor, rhetoric,
composition, framing. Each item has `evidence` and `confidence`:
`high` - most texts, `medium` - some, `low` - isolated, read with a caveat.

**Layer C** is what the writer reads: `rules.md` (always / do / avoid / template /
numeric targets / per-register differences), `bans.txt` (what never appears), and
`exemplars/` (what it looks like done right, and wrong).

## Why the split into files

- `rules.md` is short and read **every time** before writing - the voice card. A long
  evidence document read every time gets skimmed; a short card gets applied.
- `portrait.md` holds the evidence. It is read when building, updating, or when a rule
  is unclear. Rules without evidence drift into opinion; evidence without rules never
  reaches the text.
- `bans.txt` is machine-checked, so it must be a plain list, not prose.
- `exemplars/` shows instead of describing. "Why" notes tie each passage to measured
  traits, so the writer copies the move, not the words.

## Registers

One person writes differently by occasion: a code review comment, a status update and a
public post have different norms. Registers keep these apart: texts are added with
`--register`, `build` measures each register separately (when it has 8+ texts of 80+
words), `check --register` compares against the right bands, and `rules.md` keeps one
block per register with only what differs from the shared rules.

## Field guide

The templates `assets/portrait-template.md` and `assets/rules-template.md` are copied
into a new profile by `init`.

- **Header** - sources, texts and chars per register, what was dropped, version, the
  author's language level, caveats.
- **Register** - formality, distance, vocabulary level and polish, switches.
- **Persona and attitude** - person (I / we / impersonal), how categorical, attitude
  to topic and reader, how difficulty and other people are framed, humor.
- **Rhetoric** - how claims are supported, recurring moves, reader address, honesty
  markers.
- **Composition** - macro structure, paragraphs, openings, endings, rituals.
- **Surface habits** - dashes, arrows, quotes, emoji, lists, bold - copied from metrics.
- **Anchor quotes** - 5-10 short verbatim passages that show technique.
- **Content leakage** - topic-bound traits that must not transfer.
- **Absent** - checked and not found, so nobody invents them later.

## Where each section comes from

| Profile part | Tradition |
|---|---|
| geometry, lexicon, function words, punctuation | stylometry: features by linguistic level |
| function-word Delta | Burrows' Delta, authorship attribution |
| readability | Flesch reading ease |
| register, distance, switching | sociolinguistics, the notion of register |
| persona, attitude, humor | pragmatics and tone analysis |
| rhetoric, discourse moves | classical rhetoric and discourse moves |
| generation rules | applied style transfer as controlled generation |
| tiered tells | Wikipedia "Signs of AI writing"; humanizer tooling |

## References

- Troiano et al. **From theories on styles to their transfer in text: bridging the gap
  with a hierarchical survey** - style and content cannot be fully separated, hence
  "Content leakage". https://www.cambridge.org/core/journals/natural-language-engineering/article/from-theories-on-styles-to-their-transfer-in-text-bridging-the-gap-with-a-hierarchical-survey/C2C386DEEB83B6281280ACD899AA1A3F
- Jin et al. **Deep Learning for Text Style Transfer: A Survey** - style as controllable
  attributes. https://arxiv.org/abs/2011.00416
- **A Survey on Representing Linguistic Style** - interpretable features by level.
  https://openreview.net/pdf/4d8862ca474d173a3753a4cec2566124ae57495e.pdf
- **Analyzing Writing Styles of Bloggers with Different Opinions** - applied blog
  stylometry. https://pweb.fbe.hku.hk/~mchau/papers/Blog_WITS2009.pdf
- Burrows, J. **'Delta': a Measure of Stylistic Difference and a Guide to Likely
  Authorship** (2002). Implementations: faststylometry
  (https://github.com/fastdatascience/faststylometry), stylo
  (https://github.com/computationalstylistics/stylo), whose rolling analysis inspired
  the per-passage Delta.
- **Wikipedia: Signs of AI writing** - tells as clues, not proof; tells date with model
  generations. https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- antislop-sampler / slop-forensics by Sam Paech - over-represented LLM phrases and
  contrast-pattern regexes. https://github.com/sam-paech/antislop-sampler
