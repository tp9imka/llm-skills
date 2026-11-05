"""Tests for skills/writing-style/scripts/style.py. Run: python3 -m unittest discover tests"""
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/writing-style/scripts/style.py"
spec = importlib.util.spec_from_file_location("style", SCRIPT)
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)

SHORT = ["I shipped it.", "That's the point.", "We tried. It broke.",
         "Honestly? I don't know.", "Here's the thing."]
LONG = [
    "So we spent two weeks moving the job queue off cron and onto a worker, and I think "
    "the result is maybe the most boring change we've made all year, which is what I wanted.",
    "The first version leaked connections because every retry opened a new pool, e.g. after "
    "a timeout, and nobody noticed until the database refused clients at 3 a.m. on a Sunday.",
    "You don't need a framework for this; a loop, a lock, and a clear rule about who owns "
    "the row are enough for most teams I've worked with.",
]
FORMAL = [
    "The organization has determined that the proposed initiative requires additional "
    "review by the relevant committees prior to any implementation activities.",
    "Accordingly, all departments are requested to submit their assessments in accordance "
    "with the established procedures and within the designated timeframe.",
    "Compliance with these requirements is mandatory and will be monitored on a "
    "continuous basis by the designated oversight function.",
]
OFFICIALESE = (
    "It is important to note that, in order to facilitate the utilization of our platform, "
    "stakeholders must leverage the aforementioned capabilities going forward. Furthermore, "
    "prior to deployment, the team should ensure that all requirements are satisfied with "
    "regard to compliance; moreover, subsequent to the deployment, monitoring is required.\n\n"
    "In the event that issues arise, the responsible party shall escalate pursuant to the "
    "established procedure. Moving forward, it should be noted that comprehensive "
    "documentation is necessary in terms of operational readiness and maintainability."
)


def posts(count, seed=1, pool=None):
    rnd = random.Random(seed)
    pool = pool or SHORT + LONG
    return ["\n\n".join(" ".join(rnd.choice(pool) for _ in range(3)) for _ in range(4))
            for _ in range(count)]


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


def write_texts(folder, texts, prefix="p"):
    folder.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(texts):
        (folder / f"{prefix}{i:02}.md").write_text(t)
    return folder


def deviations(out):
    line = next(l for l in out.splitlines() if l.startswith("out of tolerance"))
    bad, total = (int(x) for x in line.split(":")[1].split(" of "))
    return bad, total


class Tokenizing(unittest.TestCase):
    def test_abbreviations_do_not_split_sentences(self):
        self.assertEqual(len(style.sentences("Use a pool, e.g. pgbouncer. Then measure.")), 2)

    def test_line_break_is_a_boundary(self):
        self.assertEqual(len(style.sentences("first item\nsecond item")), 2)

    def test_contractions_and_pronouns(self):
        text = "I'm sure you're right, but it's not what we've seen."
        self.assertEqual(len(style.CONTRACTION.findall(text)), 4)
        self.assertEqual(len(style.GROUP_PATTERNS["pronouns_1sg"].findall(text)), 1)
        self.assertEqual(len(style.GROUP_PATTERNS["pronouns_2"].findall(text)), 1)

    def test_ie_is_not_a_pronoun(self):
        self.assertEqual(style.GROUP_PATTERNS["pronouns_1sg"].findall("one thing, i.e. this"), [])

    def test_split_flat_ignores_frontmatter(self):
        raw = "---\ntitle: x\n---\nfirst post\n\n---\n\nsecond post"
        self.assertEqual(style.split_flat(raw), ["first post", "second post"])

    def test_split_flat_by_double_blank(self):
        self.assertEqual(style.split_flat("a\n\nstill a\n\n\nb"), ["a\n\nstill a", "b"])

    def test_ban_tiers(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "bans.txt"
            f.write_text("top\n[weak]\nrobust  # comment\n[regex]\n\\bnot just \\w+, but\n")
            self.assertEqual(style.load_bans(f),
                             [("strong", "top"), ("weak", "robust"), ("regex", r"\bnot just \w+, but")])


class Bands(unittest.TestCase):
    def test_bands_need_enough_long_texts(self):
        b, diag = style.bands(posts(5))
        self.assertEqual(b, {})
        self.assertEqual(diag["used"], 5)

    def test_bands_built(self):
        b, _ = style.bands(posts(12))
        band = b["geometry"]["sentence_words_mean"]
        self.assertLessEqual(band["p10"], band["median"])
        self.assertLessEqual(band["median"], band["p90"])

    def test_delta_model_separates_authors(self):
        model = style.delta_model(posts(12))
        own = style.delta(style.fw_freqs(posts(1, seed=99)[0]), model["mu"], model["sd"])
        other = style.delta(style.fw_freqs(posts(1, seed=99, pool=FORMAL)[0]),
                            model["mu"], model["sd"])
        self.assertLess(own, other)


class ProfileLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.profile = self.tmp / "profiles" / "me"
        self.posts = write_texts(self.tmp / "posts", posts(12))
        self.assertEqual(run("init", self.profile).returncode, 0)
        self.assertEqual(run("add", self.profile, self.posts).returncode, 0)
        r = run("build", self.profile)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_init_layout(self):
        for name in ("profile.json", "sources.jsonl", "bans.txt", "portrait.md", "rules.md",
                     "CHANGELOG.md", "metrics.json"):
            self.assertTrue((self.profile / name).exists(), name)
        self.assertTrue((self.profile / "exemplars").is_dir())

    def test_add_skips_duplicates(self):
        r = run("add", self.profile, self.posts)
        self.assertIn("0 new texts added, 12 duplicates skipped", r.stderr)

    def test_update_archives_and_versions(self):
        write_texts(self.tmp / "more", posts(4, seed=7), prefix="m")
        self.assertIn("4 new texts added", run("add", self.profile, self.tmp / "more").stderr)
        out = run("build", self.profile).stdout
        self.assertIn("v2: 16 texts (+4)", out)
        self.assertTrue((self.profile / "history" / "metrics-v1.json").exists())
        self.assertEqual(json.loads((self.profile / "metrics.json").read_text())["version"], 2)
        self.assertIn("## v2", (self.profile / "CHANGELOG.md").read_text())

    def test_drift_reported_when_style_changes(self):
        write_texts(self.tmp / "formal", posts(30, seed=3, pool=FORMAL), prefix="f")
        run("add", self.profile, self.tmp / "formal")
        out = run("build", self.profile).stdout
        self.assertIn("drift vs v1", out)
        self.assertIn("contractions_per_1000", out)

    def test_ban_conflict_when_author_uses_banned_word(self):
        robust = [t + "\n\nThe robust option won again." for t in posts(10, seed=11)]
        write_texts(self.tmp / "robust", robust, prefix="r")
        run("add", self.profile, self.tmp / "robust")
        out = run("build", self.profile).stdout
        self.assertIn("ban conflicts", out)
        self.assertIn("'robust'", out)

    def test_registers_built_and_used(self):
        write_texts(self.tmp / "formal", posts(10, seed=3, pool=FORMAL), prefix="f")
        run("add", self.profile, self.tmp / "formal", "--register", "memo")
        run("build", self.profile)
        data = json.loads((self.profile / "metrics.json").read_text())
        self.assertEqual(set(data["registers"]), {"general", "memo"})
        draft = write_texts(self.tmp / "d", posts(1, seed=5, pool=FORMAL), prefix="d") / "d00.md"
        as_memo = deviations(run("check", self.profile, draft, "--register", "memo").stdout)
        as_general = deviations(run("check", self.profile, draft, "--register", "general").stdout)
        self.assertLess(as_memo[0], as_general[0])

    def test_status(self):
        out = run("status", self.profile).stdout
        self.assertIn("register general", out)
        self.assertIn("rules.md still has template placeholders", out)


class Check(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.profile = cls.tmp / "me"
        run("init", cls.profile)
        run("add", cls.profile, write_texts(cls.tmp / "posts", posts(12)))
        run("build", cls.profile)

    def draft(self, text, name="draft.md"):
        p = self.tmp / name
        p.write_text(text)
        return p

    def test_own_text_beats_foreign_text(self):
        own = run("check", self.profile, self.draft(posts(1, seed=42)[0], "own.md")).stdout
        foreign = run("check", self.profile, self.draft(OFFICIALESE, "foreign.md")).stdout
        self.assertIn("officialese - not in profile", foreign)
        (ob, ot), (fb, ft) = deviations(own), deviations(foreign)
        self.assertGreater(fb / ft, ob / ot)

    def test_strict_exit_code(self):
        d = self.draft(OFFICIALESE)
        self.assertEqual(run("check", self.profile, d, "--strict").returncode, 1)
        self.assertEqual(run("check", self.profile, d).returncode, 0)

    def test_bans_tells_and_placeholders(self):
        text = posts(1, seed=42)[0] + "\n\nLet's delve in. Crucial, robust, seamless.\n\n[fill: p95 latency]"
        out = run("check", self.profile, self.draft(text)).stdout
        self.assertIn("banned phrases: 1", out)
        self.assertIn("weak tells: 3 - cluster", out)
        self.assertIn("unresolved placeholders: 1", out)

    def test_delta_not_measured_on_short_draft(self):
        out = run("check", self.profile, self.draft("Short one. I ship daily.")).stdout
        self.assertIn("function-word delta: not measured", out)

    def test_rolling_windows_point_at_foreign_passage(self):
        text = "\n\n".join(posts(1, seed=8)) + "\n\n" + "\n\n".join(posts(1, seed=9, pool=FORMAL))
        out = run("check", self.profile, self.draft(text)).stdout
        self.assertIn("passages furthest from the author", out)

    def test_metrics_command_without_profile(self):
        r = run("metrics", self.tmp / "posts")
        self.assertEqual(r.returncode, 0)
        self.assertIn("geometry / burstiness", r.stdout)


if __name__ == "__main__":
    unittest.main()
