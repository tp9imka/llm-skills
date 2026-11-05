#!/usr/bin/env python3
"""style.py - the measurable layer of a persistent writing-style profile (English).

Profile lifecycle:
  init    - create a profile folder (manifest, templates, default ban list).
  add     - add texts to the profile corpus (files / folders / flat file /
            Telegram export), skipping duplicates already in the profile.
  build   - recompute metrics.json from the whole corpus, archive the previous
            version and report drift and ban-list conflicts.
  status  - show what the profile holds and what is stale.

Using a profile:
  check   - compare a draft against the profile: per-feature ranges, function-word
            distance (Burrows' Delta), banned phrases, unresolved [fill: ...] gaps.
  metrics - one-off measurement of any files or folders, no profile needed.

Standard library only. Python 3.9+.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import statistics
import sys
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = 2
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BANS = SKILL_DIR / "assets" / "default-bans.txt"
TEMPLATES = {
    "portrait.md": SKILL_DIR / "assets" / "portrait-template.md",
    "rules.md": SKILL_DIR / "assets" / "rules-template.md",
}
DEFAULT_REGISTER = "general"

# Thresholds shared by several commands.
MIN_CORPUS_CHARS = 20_000       # below this the portrait is unstable
BAND_MIN_WORDS = 80             # a text must be this long to contribute to bands
BAND_MIN_TEXTS = 8              # bands need at least this many long-enough texts
SHORT_DRAFT_WORDS = 120         # below this `check` ratios are noisy
UNSPLIT_FILE_CHARS = 20_000     # warn when a large single file could not be split
MATTR_WINDOW = 500
SHORT_SENTENCE_WORDS = 7
LONG_SENTENCE_WORDS = 25
DRIFT_RELATIVE = 0.20           # build: median moved more than this => drift
FOREIGN_RATIO = 2               # check: draft rate this many times the profile max => foreign
WEAK_TELL_CLUSTER = 3           # check: weak tells count only from this many per draft
DELTA_MIN_WORDS = 80            # Delta is not measured below this many words
WINDOW_WORDS = 150              # rolling Delta window size in words
FOREIGN_SORT_KEY = 10 ** 6

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
URL = re.compile(r"https?://\S+")
NUMBER = re.compile(r"\b\d[\d.,%]*")
CAPS_WORD = re.compile(r"\b[A-Z]{4,}\b")
PLACEHOLDER = re.compile(r"\[fill:[^\]]*\]", re.I)
CONTRACTION = re.compile(
    r"\b[A-Za-z]+(?:n['’]t|['’](?:re|ve|ll|m|d))\b"
    r"|\b(?:it|that|there|here|what|who|he|she|let|where|how)['’]s\b", re.I)

# Abbreviations whose trailing period must not end a sentence.
ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.", "dr.", "prof.",
                 "st.", "jr.", "sr.", "inc.", "ltd.", "co.", "approx.", "fig.", "no.",
                 "u.s.", "u.k.", "a.m.", "p.m.")
ABBREV_RE = re.compile("|".join(re.escape(a) for a in ABBREVIATIONS), re.I)
ABBREV_MARK = "\u0000"
SENT_SPLIT = re.compile(r"(?<=[.!?…])[\"')”’]*\s+(?=[\"'(“‘]*[A-Z0-9])")

GROUPS = {
    "pronouns_1sg": "i, me, my, mine, myself",
    "pronouns_1pl": "we, us, our, ours, ourselves",
    "pronouns_2": "you, your, yours, yourself, yourselves",
    "fillers": "just, actually, basically, literally, simply, pretty much, kind of, "
               "sort of, you know, i mean, anyway",
    "discourse_markers": "so, however, therefore, thus, meanwhile, in fact, for example, "
                         "for instance, that said, in other words, on the other hand, "
                         "by the way, first, second, finally, besides, moreover, "
                         "furthermore, instead, otherwise, still, after all, in short",
    "hedges": "maybe, perhaps, probably, possibly, likely, apparently, arguably, "
              "roughly, somewhat, seems, seem, seemed, i think, i guess, i suspect, "
              "in general, generally, usually, tends to, more or less, as far as i know",
    "boosters": "clearly, obviously, definitely, certainly, absolutely, totally, "
                "really, truly, indeed, of course, undoubtedly, extremely, incredibly, "
                "completely, entirely, very, always, never",
    "obligation": "must, should, need to, needs to, have to, has to, had to, "
                  "ought to, required, necessary, got to",
    "officialese": "utilize, utilise, leverage, facilitate, in order to, with regard to, "
                   "with respect to, in terms of, prior to, subsequent to, "
                   "in the event that, at this point in time, going forward, "
                   "moving forward, stakeholders, it should be noted, "
                   "it is important to note, aforementioned, herein, pursuant to",
}

# Topic-independent function words for Burrows' Delta. Function words are a more
# stable authorship signal than content words.
FUNCTION_WORDS = (
    "the a an and or but if of in on at to for with from by about as into than then "
    "that this these those it its is are was were be been being have has had do does "
    "did not no so there here what which who when where why how all any some more most "
    "can could will would should may might must i me my we us our you your he she they "
    "them their his her one up out also only even still now too because while after "
    "before over again both each other such own same between through without against "
    "under until yet though although whether just very really much many well"
).split()


def _group_pattern(phrases):
    alts = sorted((p.strip() for p in phrases.split(",") if p.strip()), key=len, reverse=True)
    # Apostrophe is allowed after a match so "I'm" counts as "I" and "you're" as "you".
    return re.compile(r"(?<![\w'’-])(" + "|".join(re.escape(a) for a in alts)
                      + r")(?![\w-])(?!\.\w)", re.I)


GROUP_PATTERNS = {name: _group_pattern(phrases) for name, phrases in GROUPS.items()}


def info(msg):
    print(f"[i] {msg}", file=sys.stderr)


def warn(msg):
    print(f"[!] {msg}", file=sys.stderr)


def today():
    return dt.date.today().isoformat()


# ---------------------------------------------------------------- sources

def tg_text(msg):
    t = msg.get("text")
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        return "".join(x if isinstance(x, str) else x.get("text", "") for x in t)
    return ""


def from_telegram(path, keep_forwards=False, min_chars=0):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "chats" in data:
        data = data["chats"]["list"][0]
        warn(f"full-account export detected, only the first chat is used: {data.get('name')}")
    msgs = data.get("messages", [])
    items, fwd, short = [], 0, 0
    for m in msgs:
        if m.get("type") != "message":
            continue
        if m.get("forwarded_from") and not keep_forwards:
            fwd += 1
            continue
        txt = tg_text(m).strip()
        if not txt or len(txt) < min_chars:
            short += 1
            continue
        items.append((f"telegram:{m.get('id')}", (m.get("date") or "")[:10], txt))
    info(f"{data.get('name')}: {len(msgs)} messages, {len(items)} own texts kept, "
         f"{fwd} forwards dropped, {short} empty/short dropped")
    return items


def from_files(paths, min_chars=0):
    items = []
    for p in paths:
        p = Path(p)
        files = (sorted(p.rglob("*.md")) + sorted(p.rglob("*.txt"))) if p.is_dir() else [p]
        for f in files:
            txt = f.read_text(encoding="utf-8").strip()
            chunks = [strip_frontmatter(txt).strip()]
            single_file = len(paths) == 1 and len(files) == 1
            if single_file:
                if re.search(r"^### ", txt, flags=re.M):
                    chunks = split_corpus(txt)
                else:
                    chunks = split_flat(txt)
                    if len(chunks) > 1:
                        info(f"{f.name}: flat file split into {len(chunks)} texts")
                    elif not chunks and txt:
                        warn(f"{f.name}: only separators, no text found - file skipped")
                if len(chunks) == 1 and len(txt) > UNSPLIT_FILE_CHARS:
                    warn(f"{f.name}: no separators found, the file is one text")
                    warn("    separate texts with a '---' line or two blank lines, "
                         "or put one text per file in a folder")
            for k, chunk in enumerate(chunks, 1):
                if not chunk or len(chunk) < min_chars:
                    continue
                ref = str(f) if len(chunks) == 1 else f"{f}#{k}"
                items.append((ref, "", chunk))
    info(f"texts collected: {len(items)}")
    return items


def collect(args):
    if getattr(args, "telegram", None):
        return from_telegram(args.telegram, args.keep_forwards, args.min_chars)
    if not args.paths:
        sys.exit("give files/folders or --telegram EXPORT.json")
    return from_files(args.paths, args.min_chars)


FLAT_RULE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|={3,}|_{3,})[ \t]*$", flags=re.M)
FLAT_BLANKS = re.compile(r"\n[ \t]*\n[ \t]*\n+")
FRONTMATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*\n?", flags=re.S)


def strip_frontmatter(raw):
    """Drop leading YAML frontmatter: it is note metadata, not text."""
    return FRONTMATTER.sub("", raw, count=1) if raw.startswith("---") else raw


def split_flat(raw):
    """Split a flat file into texts.

    Separator lines (---, ***, ===, ___) win; otherwise two or more blank lines.
    A single blank line never splits: inside a text it separates paragraphs.
    Frontmatter goes first, or its closing '---' would act as a separator.
    """
    raw = strip_frontmatter(raw)
    parts = FLAT_RULE.split(raw) if FLAT_RULE.search(raw) else FLAT_BLANKS.split(raw)
    return [p.strip() for p in parts if p.strip()]


def split_corpus(raw):
    parts = re.split(r"^### .*$", raw, flags=re.M)
    out = [p.strip() for p in parts if p.strip()]
    return out or ([raw.strip()] if raw.strip() else [])


# --------------------------------------------------------------- features

def sentences(text):
    """A line break is a sentence boundary: posts and lists often skip the period."""
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        protected = ABBREV_RE.sub(lambda m: m.group(0).replace(".", ABBREV_MARK), line)
        out += [s.replace(ABBREV_MARK, ".") for s in SENT_SPLIT.split(protected) if s.strip()]
    return out


def words(text):
    return WORD.findall(text)


def syllables(word):
    w = word.lower().strip("'’-")
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups) - (1 if w.endswith("e") and not w.endswith("le") and len(groups) > 1 else 0)
    return max(1, n)


def per1000(count, total_words):
    return round(1000 * count / total_words, 2) if total_words else 0.0


def first_line(text):
    return text.split("\n")[0].strip()


def analyze(texts):
    body = "\n\n".join(texts)
    clean = URL.sub(" ", body)                 # links must not distort the lexicon
    raw_toks = words(clean)
    toks = [w.lower() for w in raw_toks]
    n = len(toks)
    sents = [s for t in texts for s in sentences(t)]
    slen = [len(words(s)) for s in sents] or [0]
    paras = [p for t in texts for p in t.split("\n\n") if p.strip()]
    plen = [len(words(p)) for p in paras] or [0]
    tlen = [len(t) for t in texts]

    mean_s = statistics.mean(slen)
    std_s = statistics.pstdev(slen) if len(slen) > 1 else 0.0
    share = lambda pred: round(sum(1 for x in slen if pred(x)) / len(slen), 2)
    flesch = (206.835 - 1.015 * (n / max(1, len(sents)))
              - 84.6 * (sum(syllables(w) for w in raw_toks) / n)) if n else 0.0

    return {
        "meta": {
            "texts": len(texts),
            "chars": sum(tlen),
            "words": n,
            "sentences": len(sents),
        },
        "geometry": {
            "text_chars_median": int(statistics.median(tlen)),
            "text_chars_mean": int(statistics.mean(tlen)),
            "sentence_words_mean": round(mean_s, 1),
            "sentence_words_median": statistics.median(slen),
            "sentence_words_sd": round(std_s, 1),
            "burstiness": round(std_s / mean_s, 2) if mean_s else 0.0,
            "share_sentences_le7": share(lambda x: x <= SHORT_SENTENCE_WORDS),
            "share_sentences_8_24": share(
                lambda x: SHORT_SENTENCE_WORDS < x < LONG_SENTENCE_WORDS),
            "share_sentences_ge25": share(lambda x: x >= LONG_SENTENCE_WORDS),
            "paragraph_words_mean": round(statistics.mean(plen), 1),
            "paragraph_sentences_mean": round(len(sents) / len(paras), 1) if paras else 0,
        },
        "lexicon": {
            "ttr_raw": round(len(set(toks)) / n, 3) if n else 0,
            "mattr_500": mattr(toks, MATTR_WINDOW),
            "hapax_share": round(
                sum(1 for c in Counter(toks).values() if c == 1) / max(1, len(set(toks))), 3),
            "word_length_mean": round(statistics.mean(len(t) for t in toks), 2) if n else 0,
            "flesch_reading_ease": round(flesch, 1),
            "numbers_per_1000": per1000(len(NUMBER.findall(clean)), n),
            "contractions_per_1000": per1000(len(CONTRACTION.findall(clean)), n),
        },
        "markers_per_1000": {
            name: per1000(len(pat.findall(clean)), n) for name, pat in GROUP_PATTERNS.items()
        },
        "punctuation_per_1000": {
            "em_dash": per1000(body.count("—"), n),
            "en_dash": per1000(len(re.findall(r"(?<=\s)–(?=\s)", body)), n),
            "hyphen_as_dash": per1000(len(re.findall(r"(?<=\s)-(?=\s)|(?<=\w)--(?=\w)", body)), n),
            "ellipsis": per1000(len(re.findall(r"\.\.\.|…", body)), n),
            "parenthetical": per1000(len(re.findall(r"\([^)]{5,}\)", body)), n),
            "question": per1000(body.count("?"), n),
            "exclamation": per1000(body.count("!"), n),
            "colon": per1000(len(re.findall(r":(?!//)", body)), n),
            "semicolon": per1000(body.count(";"), n),
            "quotes_curly": per1000(body.count("“"), n),
            "quotes_straight": per1000(body.count('"') / 2, n),
            "emoji": per1000(len(EMOJI.findall(body)), n),
            "caps_words": per1000(len(CAPS_WORD.findall(clean)), n),
            "arrows": per1000(len(re.findall(r"→|=>|->", body)), n),
        },
        "formatting_per_text": {
            "bullet_items": round(len(re.findall(r"(?:^|\n)\s*[-•*]\s", body)) / len(texts), 2),
            "numbered_items": round(len(re.findall(r"(?:^|\n)\s*\d+[.)]\s", body)) / len(texts), 2),
            "markdown_headings": round(len(re.findall(r"(?:^|\n)#{1,6}\s", body)) / len(texts), 2),
            "links": round(len(URL.findall(body)) / len(texts), 2),
            "bold_italic": round(len(re.findall(r"\*\*[^*]+\*\*|__[^_]+__", body)) / len(texts), 2),
            "first_line_no_period": round(
                sum(1 for t in texts if first_line(t) and not first_line(t).endswith("."))
                / len(texts), 2),
            "first_line_chars": int(statistics.mean(len(first_line(t)) for t in texts)),
        },
    }


def mattr(toks, window):
    """Moving-average type-token ratio over fixed windows, stable across corpus length.

    Gotcha: on a text shorter than the window there is nothing to average, so the raw
    TTR is returned. Bands measure single texts, and a typical 100-400 word post
    always lands here, so per-text `mattr_500` bands partly track text length.
    """
    if len(toks) < window:
        return round(len(set(toks)) / len(toks), 3) if toks else 0
    vals = [len(set(toks[i:i + window])) / window
            for i in range(0, len(toks) - window + 1, max(1, window // 5))]
    return round(statistics.mean(vals), 3)


def fw_freqs(text):
    toks = [w.lower() for w in words(URL.sub(" ", text))]
    if not toks:
        return {}
    c = Counter(t for t in toks if t in FUNCTION_WORDS)
    return {f: c[f] / len(toks) for f in FUNCTION_WORDS}


def delta(freqs, mu, sd):
    zs = [abs((freqs.get(f, 0) - mu[f]) / sd[f]) for f in mu if sd.get(f)]
    return round(statistics.mean(zs), 3) if zs else None


def quantiles(vals):
    vals = sorted(vals)
    q = lambda f: vals[min(len(vals) - 1, int(f * (len(vals) - 1)))]
    return {"p10": round(q(0.10), 3), "median": round(q(0.5), 3), "p90": round(q(0.90), 3)}


def delta_model(texts):
    """Function-word mean/sd per word plus the author's own leave-one-out Delta band."""
    freqs = [fw_freqs(t) for t in texts]
    if len(freqs) < BAND_MIN_TEXTS:
        return None
    n = len(freqs)
    mu = {f: statistics.mean(x[f] for x in freqs) for f in FUNCTION_WORDS}
    sd = {f: statistics.pstdev([x[f] for x in freqs]) for f in FUNCTION_WORDS}
    loo = []
    for i, x in enumerate(freqs):
        rest = freqs[:i] + freqs[i + 1:]
        m = {f: (mu[f] * n - x[f]) / (n - 1) for f in FUNCTION_WORDS}
        s = {f: statistics.pstdev([r[f] for r in rest]) for f in FUNCTION_WORDS}
        d = delta(x, m, s)
        if d is not None:
            loo.append(d)
    return {"mu": {f: round(v, 6) for f, v in mu.items()},
            "sd": {f: round(v, 6) for f, v in sd.items()},
            "band": quantiles(loo) if loo else None}


BAND_SECTIONS = ("geometry", "lexicon", "markers_per_1000", "punctuation_per_1000")


def bands(texts, min_words=BAND_MIN_WORDS, min_texts=BAND_MIN_TEXTS):
    """Per-text spread of each feature: p10 / median / p90.

    `check` flags what falls outside the author's own range, not every difference
    from the corpus mean. Returns (bands, diagnostics).
    """
    per_text = [analyze([t]) for t in texts if len(words(t)) >= min_words]
    diag = {"total": len(texts), "used": len(per_text), "need": min_texts}
    if len(per_text) < min_texts:
        return {}, diag
    out = {}
    for section in BAND_SECTIONS:
        for key in per_text[0].get(section, {}):
            vals = [r[section][key] for r in per_text
                    if isinstance(r[section].get(key), (int, float))]
            if vals:
                out.setdefault(section, {})[key] = quantiles(vals)
    out["_texts_used"] = len(per_text)
    return out, diag


def measure(texts, ngrams=0, ngram_size=3, openers=0):
    """Full layer A for a set of texts: averages, bands, Delta model, formulas."""
    res = analyze(texts)
    res["bands"], diag = bands(texts)
    long_texts = [t for t in texts if len(words(t)) >= BAND_MIN_WORDS]
    res["function_words"] = delta_model(long_texts)
    if ngrams:
        res["top_ngrams"] = top_ngrams(texts, ngram_size, ngrams)
    if openers:
        res["top_openers"] = top_openers(texts, openers)
    return res, diag


def top_ngrams(texts, size, limit):
    body = URL.sub(" ", "\n".join(texts)).lower()
    toks = re.findall(r"[a-z][a-z'’]*", body)
    grams = Counter(" ".join(toks[i:i + size]) for i in range(len(toks) - size + 1))
    return [{"phrase": g, "count": c} for g, c in grams.most_common(limit) if c > 1]


def top_openers(texts, limit):
    heads = Counter(" ".join(first_line(t).split()[:3]).lower() for t in texts if t.strip())
    return [{"opener": h, "count": c} for h, c in heads.most_common(limit) if c > 1]


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + " / "))
        else:
            out[key] = v
    return out


def warn_no_bands(diag, label=""):
    warn(f"bands not built{label}: {diag['used']} of {diag['total']} texts are "
         f"{BAND_MIN_WORDS}+ words, need {diag['need']}")
    warn("    without bands, check compares against the mean and flags normal variation")


# ---------------------------------------------------------------- profile

class Profile:
    """A profile folder. The corpus on disk is the source of truth; the ledger only
    remembers hashes so `add` can skip texts it has already seen."""

    def __init__(self, root):
        self.root = Path(root)
        self.manifest_path = self.root / "profile.json"
        self.ledger_path = self.root / "sources.jsonl"
        self.metrics_path = self.root / "metrics.json"
        self.corpus_dir = self.root / "corpus"
        self.history_dir = self.root / "history"
        self.bans_path = self.root / "bans.txt"
        self.changelog_path = self.root / "CHANGELOG.md"

    def exists(self):
        return self.manifest_path.exists()

    def manifest(self):
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def save_manifest(self, m):
        self.manifest_path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")

    def ledger(self):
        if not self.ledger_path.exists():
            return []
        return [json.loads(l) for l in self.ledger_path.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    def texts(self, register=None):
        """{register: [text, ...]} from corpus/<register>/*.md."""
        out = {}
        if not self.corpus_dir.exists():
            return out
        for d in sorted(p for p in self.corpus_dir.iterdir() if p.is_dir()):
            if register and d.name != register:
                continue
            ts = [f.read_text(encoding="utf-8").strip() for f in sorted(d.glob("*.md"))]
            ts = [t for t in ts if t]
            if ts:
                out[d.name] = ts
        return out

    def bans(self):
        return load_bans(self.bans_path)


def require_profile(path):
    p = Profile(path)
    if not p.exists():
        sys.exit(f"no profile at {path} (missing profile.json) - run: style.py init {path}")
    return p


def text_hash(text):
    norm = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


TIERS = ("strong", "weak", "regex")


def load_bans(path):
    """Ban list: '[strong]' phrases flag alone, '[weak]' only in clusters, '[regex]' are
    strong patterns. Lines before any section are strong. ' #' starts a comment."""
    if not Path(path).exists():
        return []
    out, tier = [], "strong"
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"\[(\w+)\]", line):
            tier = line[1:-1]
            if tier not in TIERS:
                sys.exit(f"{path}: unknown section [{tier}], use one of {TIERS}")
            continue
        out.append((tier, line))
    return out


def ban_pattern(tier, phrase):
    if tier == "regex":
        return re.compile(phrase, re.I | re.M)
    if re.fullmatch(r"[\w' -]+", phrase):
        return re.compile(r"(?<![\w'])" + re.escape(phrase) + r"(?![\w'])", re.I)
    return re.compile(re.escape(phrase), re.I)


def cmd_init(args):
    p = Profile(args.profile)
    if p.exists():
        sys.exit(f"profile already exists: {p.root}")
    p.root.mkdir(parents=True, exist_ok=True)
    (p.corpus_dir / DEFAULT_REGISTER).mkdir(parents=True, exist_ok=True)
    (p.root / "exemplars").mkdir(exist_ok=True)
    p.history_dir.mkdir(exist_ok=True)
    name = args.name or p.root.name
    p.save_manifest({
        "schema_version": SCHEMA_VERSION, "name": name, "language": "en",
        "created": today(), "updated": today(), "version": 0,
        "registers": {DEFAULT_REGISTER: "default register"},
    })
    p.ledger_path.touch()
    shutil.copy(DEFAULT_BANS, p.bans_path)
    for fname, src in TEMPLATES.items():
        (p.root / fname).write_text(
            src.read_text(encoding="utf-8").replace("<who>", name), encoding="utf-8")
    p.changelog_path.write_text(f"# {name} - profile changelog\n\n", encoding="utf-8")
    info(f"profile created: {p.root}")
    info(f"next: style.py add {p.root} <texts> [--register NAME], then style.py build {p.root}")


def cmd_add(args):
    p = require_profile(args.profile)
    reg = args.register
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", reg):
        sys.exit("register name: lowercase letters, digits and hyphens")
    items = collect(args)
    seen = {e["hash"] for e in p.ledger()}
    target = p.corpus_dir / reg
    target.mkdir(parents=True, exist_ok=True)
    added, dup = [], 0
    with p.ledger_path.open("a", encoding="utf-8") as ledger:
        for ref, date, text in items:
            h = text_hash(text)
            if h in seen:
                dup += 1
                continue
            seen.add(h)
            (target / f"{h[:12]}.md").write_text(text + "\n", encoding="utf-8")
            entry = {"hash": h, "file": f"corpus/{reg}/{h[:12]}.md", "register": reg,
                     "source": ref, "date": date, "added": today(), "chars": len(text)}
            ledger.write(json.dumps(entry, ensure_ascii=False) + "\n")
            added.append(entry)
    m = p.manifest()
    m["registers"].setdefault(reg, args.describe or "")
    if args.describe:
        m["registers"][reg] = args.describe
    m["updated"] = today()
    m["pending_build"] = m.get("pending_build", 0) + len(added)
    p.save_manifest(m)
    info(f"{reg}: {len(added)} new texts added, {dup} duplicates skipped "
         f"({sum(e['chars'] for e in added)} chars)")
    if added:
        info(f"next: style.py build {p.root}")


def drift_report(old, new):
    """Features whose median moved outside the old band or by more than DRIFT_RELATIVE."""
    rows = []
    ob, nb = old.get("bands", {}), new.get("bands", {})
    for section in BAND_SECTIONS:
        for key, band in nb.get(section, {}).items():
            prev = ob.get(section, {}).get(key)
            if not prev:
                continue
            a, b = prev["median"], band["median"]
            rel = (b - a) / abs(a) if a else (1.0 if b else 0.0)
            outside = not (prev["p10"] <= b <= prev["p90"])
            if outside or abs(rel) > DRIFT_RELATIVE:
                rows.append((key, a, b, rel, outside))
    rows.sort(key=lambda r: -abs(r[3]))
    return rows


def ban_conflicts(bans, texts):
    """Banned items the author actually uses. Strong items conflict on any use in the
    corpus; weak ones only when the author uses them at least once per 3 texts."""
    out = []
    for tier, phrase in bans:
        hits = [len(ban_pattern(tier, phrase).findall(t)) for t in texts]
        n, used_in = sum(hits), sum(1 for h in hits if h)
        if n and (tier != "weak" or used_in * 3 >= len(texts)):
            out.append((phrase, n, used_in))
    return out


def cmd_build(args):
    p = require_profile(args.profile)
    corpus = p.texts()
    if not corpus:
        sys.exit("profile corpus is empty - run style.py add first")
    m = p.manifest()
    all_texts = [t for ts in corpus.values() for t in ts]
    chars = sum(len(t) for t in all_texts)
    overall, diag = measure(all_texts, args.ngrams, args.ngram_size, args.openers)
    if not overall["bands"]:
        warn_no_bands(diag)
    registers = {}
    for reg, ts in corpus.items():
        if len(corpus) == 1:
            break
        r, rdiag = measure(ts)
        registers[reg] = r
        if not r["bands"]:
            warn_no_bands(rdiag, f" for register '{reg}' (check falls back to overall)")
    version = m.get("version", 0) + 1
    result = {"schema_version": SCHEMA_VERSION, "profile": m["name"], "version": version,
              "built": today(), "language": "en",
              "corpus": {"texts": len(all_texts), "chars": chars,
                         "per_register": {r: len(ts) for r, ts in corpus.items()}},
              "overall": overall, "registers": registers}

    old = None
    if p.metrics_path.exists():
        old = json.loads(p.metrics_path.read_text(encoding="utf-8"))
        p.history_dir.mkdir(exist_ok=True)
        shutil.copy(p.metrics_path, p.history_dir / f"metrics-v{old.get('version', 0)}.json")
    p.metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    drift = drift_report(old["overall"], overall) if old and "overall" in old else []
    conflicts = ban_conflicts(p.bans(), all_texts)
    prev_texts = old["corpus"]["texts"] if old else 0

    print(f"profile {m['name']} v{version}: {len(all_texts)} texts (+{len(all_texts) - prev_texts}), "
          f"{chars} chars, registers: {', '.join(f'{r}={len(ts)}' for r, ts in corpus.items())}")
    if chars < MIN_CORPUS_CHARS:
        print(f"[!] corpus under {MIN_CORPUS_CHARS} chars: portrait is unstable, say so in portrait.md")
    if old:
        if drift:
            print(f"\ndrift vs v{old.get('version', 0)} (median moved past the old band or >"
                  f"{int(DRIFT_RELATIVE * 100)}%):")
            for key, a, b, rel, outside in drift:
                print(f"  {key:<28} {a:>9} => {b:<9} {rel * 100:+.0f}%"
                      f"{'  outside old band' if outside else ''}")
        else:
            print(f"\nno drift vs v{old.get('version', 0)}: medians stayed inside the old bands")
    if conflicts:
        print("\nban conflicts - phrases in bans.txt the author actually uses "
              "(the profile wins: remove them from bans.txt or justify):")
        for phrase, n, used_in in conflicts:
            print(f"  {phrase!r}: {n}x in {used_in} of {len(all_texts)} texts")

    entry = [f"## v{version} - {today()}",
             f"- corpus: {len(all_texts)} texts (+{len(all_texts) - prev_texts}), {chars} chars",
             f"- drift: {', '.join(r[0] for r in drift) if drift else ('none' if old else 'first build')}"]
    if conflicts:
        entry.append(f"- ban conflicts: {', '.join(c[0] for c in conflicts)}")
    entry.append("- portrait/rules: <update what changed, or 'reviewed, unchanged'>")
    with p.changelog_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry) + "\n\n")
    m.update(version=version, updated=today(), last_build=today(), pending_build=0)
    p.save_manifest(m)
    info(f"metrics written: {p.metrics_path}; changelog entry added - fill in its last line")


def cmd_status(args):
    p = require_profile(args.profile)
    m = p.manifest()
    corpus = p.texts()
    ex = list((p.root / "exemplars").glob("*.md")) if (p.root / "exemplars").exists() else []
    print(f"profile: {m['name']}  version: v{m.get('version', 0)}  "
          f"last build: {m.get('last_build', 'never')}")
    for reg, desc in m.get("registers", {}).items():
        ts = corpus.get(reg, [])
        print(f"  register {reg:<14} {len(ts):>4} texts {sum(len(t) for t in ts):>8} chars  {desc}")
    print(f"exemplars: {len(ex)}  bans: {len(p.bans())}")
    if m.get("pending_build"):
        print(f"[!] {m['pending_build']} texts added since the last build - run style.py build")
    for fname in TEMPLATES:
        f = p.root / fname
        if not f.exists() or "<fill" in f.read_text(encoding="utf-8"):
            print(f"[!] {fname} still has template placeholders")


# ---------------------------------------------------------------- check

# (section, key, relative tolerance used only when there are no bands)
CHECK_KEYS = [
    ("geometry", "sentence_words_median", 0.25),
    ("geometry", "sentence_words_mean", 0.25),
    ("geometry", "burstiness", 0.30),
    ("geometry", "share_sentences_le7", 0.30),
    ("geometry", "share_sentences_ge25", 0.50),
    ("geometry", "paragraph_words_mean", 0.35),
    ("lexicon", "mattr_500", 0.15),
    ("lexicon", "word_length_mean", 0.15),
    ("lexicon", "flesch_reading_ease", 0.25),
    ("lexicon", "numbers_per_1000", 0.50),
    ("lexicon", "contractions_per_1000", 0.50),
]
CHECK_GROUPS = [
    ("markers_per_1000", 0.60),
    ("punctuation_per_1000", 0.60),
]


def load_reference(path, register):
    """Return (reference metrics, bans, label) from a profile dir or a metrics.json."""
    path = Path(path)
    bans = []
    if path.is_dir():
        p = require_profile(path)
        if not p.metrics_path.exists():
            sys.exit(f"profile has no metrics yet - run: style.py build {path}")
        data = json.loads(p.metrics_path.read_text(encoding="utf-8"))
        bans = p.bans()
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if "overall" not in data:                      # one-off `metrics --json` output
        return data, bans, "metrics file"
    if register:
        reg = data.get("registers", {}).get(register)
        if reg and reg.get("bands"):
            return reg, bans, f"register '{register}'"
        if register not in data.get("corpus", {}).get("per_register", {}):
            sys.exit(f"unknown register '{register}'")
        print(f"[!] register '{register}' has no bands, using the overall profile")
    return data["overall"], bans, "overall profile"


def cmd_check(args):
    ref, bans, label = load_reference(args.profile, args.register)
    draft = Path(args.draft).read_text(encoding="utf-8").strip()
    if not draft:
        sys.exit("draft is empty")
    got = analyze([draft])
    dwords = got["meta"]["words"]
    rows, thin, bad = [], 0, 0
    band_all = ref.get("bands", {})

    def compare(section, key, tol, per_thousand):
        nonlocal bad, thin
        want = ref.get(section, {}).get(key)
        have = got.get(section, {}).get(key)
        if not isinstance(want, (int, float)) or not isinstance(have, (int, float)):
            return
        band = band_all.get(section, {}).get(key)
        hi = band["p90"] if band else want
        # A rare feature is not expected in a draft this short: only flag it when the
        # draft uses it far more than the author ever does.
        if per_thousand and hi * dwords / 1000 < args.min_expected:
            if have > 0 and (max(hi, want) == 0 or have > FOREIGN_RATIO * max(hi, want)):
                shown = f"{band['p10']}-{band['p90']}" if band else want
                rows.append((FOREIGN_SORT_KEY, False, key + " - not in profile", shown, have,
                             "foreign"))
                bad += 1
            else:
                thin += 1
            return
        if band:
            lo = band["p10"]
            ok = lo <= have <= hi
            dev = 0
            if not ok:
                bad += 1
                edge = lo if have < lo else hi
                dev = (have - edge) / abs(edge) if edge else 1
            rows.append((abs(dev), ok, key, f"{lo}-{hi}", have,
                         "in range" if ok else f"{dev * 100:+.0f}% past edge"))
            return
        if want == 0 and have == 0:
            return
        dev = (have - (want or 1e-9)) / abs(want or 1e-9)
        ok = abs(dev) <= tol
        if not ok:
            bad += 1
        rows.append((abs(dev), ok, key, want, have, f"{dev * 100:+.0f}% vs mean"))

    for section, key, tol in CHECK_KEYS:
        compare(section, key, tol, per_thousand="1000" in key)
    for section, tol in CHECK_GROUPS:
        for key in ref.get(section, {}):
            compare(section, key, tol, per_thousand=True)

    rows.sort(key=lambda r: (r[1], -r[0]))        # deviations first, largest on top
    width = max((len(r[2]) for r in rows), default=10) + 3
    print(f"draft: {dwords} words, {got['meta']['sentences']} sentences - against {label}")
    if not band_all:
        print("[!] reference has no bands: comparing against the mean")
    print(f"\n{'feature'.ljust(width)}{'profile':>12}{'draft':>10}   deviation")
    for _, ok, key, want, have, dev in rows:
        print(f"{(('ok ' if ok else '!! ') + key).ljust(width)}{str(want):>12}{have:>10}   {dev}")
    print(f"\nout of tolerance: {bad} of {len(rows)}")
    if thin:
        print(f"skipped as not significant at this length: {thin} "
              f"(--min-expected {args.min_expected})")

    fw = ref.get("function_words")
    if not (fw and fw.get("band")):
        print("function-word delta: not measured (profile has no Delta model)")
    elif dwords < DELTA_MIN_WORDS:
        print(f"function-word delta: not measured (draft under {DELTA_MIN_WORDS} words)")
    else:
        d = delta(fw_freqs(draft), fw["mu"], fw["sd"])
        b = fw["band"]
        far = d > b["p90"]
        verdict = "further than the author's own texts" if far else "within the author's own texts"
        print(f"function-word delta: {d} (author's own texts {b['p10']}-{b['p90']}) - {verdict}")
        bad += far
        if dwords >= 2 * WINDOW_WORDS:
            drifting = rolling_delta(draft, fw, b["p90"])
            if drifting:
                print("  passages furthest from the author (rolling windows):")
                for d_w, line_no, head in drifting:
                    print(f"    line {line_no}: delta {d_w} - {head!r}")

    strong, weak = [], []
    for tier, phrase in bans:
        pat = ban_pattern(tier, phrase)
        for i, line in enumerate(draft.splitlines(), 1):
            for _ in pat.finditer(line):
                (weak if tier == "weak" else strong).append((i, phrase))
    if strong:
        print(f"\nbanned phrases: {len(strong)}")
        for i, phrase in strong:
            print(f"  line {i}: {phrase!r}")
        bad += len(strong)
    if weak:
        clustered = len(weak) >= WEAK_TELL_CLUSTER
        print(f"\nweak tells: {len(weak)}"
              f"{' - cluster, rewrite these' if clustered else ' - below cluster threshold, informational'}")
        for i, phrase in weak:
            print(f"  line {i}: {phrase!r}")
        bad += len(weak) if clustered else 0
    gaps = PLACEHOLDER.findall(draft)
    if gaps:
        print(f"\nunresolved placeholders: {len(gaps)} - {'; '.join(gaps)}")
    if dwords < SHORT_DRAFT_WORDS:
        print(f"[!] draft is under {SHORT_DRAFT_WORDS} words: trust only large deviations")
    sys.exit(1 if bad and args.strict else 0)


def rolling_delta(draft, fw, limit, top=3):
    """Delta over ~WINDOW_WORDS windows of whole lines; returns the worst windows above
    the author's p90 as (delta, first line number, opening words)."""
    lines = draft.splitlines()
    out, start = [], 0
    while start < len(lines):
        end, count = start, 0
        while end < len(lines) and count < WINDOW_WORDS:
            count += len(words(lines[end]))
            end += 1
        if count >= DELTA_MIN_WORDS:
            d = delta(fw_freqs("\n".join(lines[start:end])), fw["mu"], fw["sd"])
            if d is not None and d > limit:
                head = " ".join(" ".join(lines[start:end]).split()[:8])
                out.append((d, start + 1, head))
        start = max(start + 1, (start + end) // 2)  # half-window step
        if end >= len(lines):
            break
    return sorted(out, reverse=True)[:top]


def cmd_metrics(args):
    items = collect(args)
    texts = [t for _, _, t in items]
    if not texts:
        sys.exit("nothing to measure")
    res, diag = measure(texts, args.ngrams, args.ngram_size, args.openers)
    if not res["bands"]:
        warn_no_bands(diag)
    res.pop("function_words", None) if not args.json else None
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        info(f"metrics written: {args.json}")
    flat = flatten({k: v for k, v in res.items() if k != "function_words"})
    width = max(len(k) for k in flat)
    for k, v in flat.items():
        print(f"{k.ljust(width)}  {v}")


# ---------------------------------------------------------------- cli

def add_source_args(c):
    c.add_argument("paths", nargs="*", help=".md/.txt files or folders, or one flat file")
    c.add_argument("--telegram", metavar="EXPORT.json", help="Telegram Desktop result.json")
    c.add_argument("--keep-forwards", action="store_true", help="keep forwarded messages")
    c.add_argument("--min-chars", type=int, default=0, help="drop texts shorter than this")


def add_formula_args(c):
    c.add_argument("--ngrams", type=int, default=0, metavar="N", help="top N repeated phrases")
    c.add_argument("--ngram-size", type=int, default=3, help="words per phrase (default 3)")
    c.add_argument("--openers", type=int, default=0, metavar="N", help="top N text openers")


def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("init", help="create a profile folder")
    c.add_argument("profile", help="profile folder, e.g. profiles/ivan")
    c.add_argument("--name", help="display name (default: folder name)")
    c.set_defaults(func=cmd_init)

    c = sub.add_parser("add", help="add texts to a profile corpus (duplicates skipped)")
    c.add_argument("profile")
    add_source_args(c)
    c.add_argument("--register", default=DEFAULT_REGISTER,
                   help=f"register/genre of these texts (default {DEFAULT_REGISTER})")
    c.add_argument("--describe", help="one-line description of the register")
    c.set_defaults(func=cmd_add)

    c = sub.add_parser("build", help="recompute metrics, archive the old ones, report drift")
    c.add_argument("profile")
    add_formula_args(c)
    c.set_defaults(func=cmd_build)

    c = sub.add_parser("status", help="show profile contents and what needs attention")
    c.add_argument("profile")
    c.set_defaults(func=cmd_status)

    c = sub.add_parser("check", help="compare a draft against a profile")
    c.add_argument("profile", help="profile folder (or a metrics JSON file)")
    c.add_argument("draft", help="draft text file")
    c.add_argument("--register", help="compare against this register's bands")
    c.add_argument("--strict", action="store_true", help="exit 1 when anything deviates")
    c.add_argument("--min-expected", type=float, default=1.5, metavar="N",
                   help="skip a per-1000 feature the profile expects fewer than N times "
                        "in a draft of this length (default 1.5)")
    c.set_defaults(func=cmd_check)

    c = sub.add_parser("metrics", help="one-off measurement of texts, no profile")
    add_source_args(c)
    add_formula_args(c)
    c.add_argument("--json", metavar="FILE", help="also write the metrics JSON")
    c.set_defaults(func=cmd_metrics)
    return ap


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
