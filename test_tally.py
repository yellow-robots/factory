"""What a version took, derived: what `tally.py` gives `gate.py numbers`.

    uv run python -m unittest test_tally -v

Written from docs/seeds/the-loop-in-numbers.md before the code, over the gate tests' own fixture
advanced two versions, a fixture store of records, and two review notes; amended after the first
build's own answer showed the version's runs must come from the store and not from git alone.
Nothing of this repository is named here: no seed, no version, no stamp of the real store.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gate import IDENTITY, STAMP, git, make_repo, run, write

import repo
import tally

COLUMNS = (
    "version", "seeds", "runs", "builds", "green", "red", "capped", "unrecorded", "cost_usd",
    "requests", "reviews", "findings", "defects", "judged_test", "judged_seed", "judged_case",
    "judged_none", "commits", "by_hand",
)  # fmt: skip
STAMP_0 = "20260916T235959Z"  # a red run whose tree was never pushed: in the store, not in git
STAMP_2 = "20260917T000001Z"
STAMP_3 = "20260917T000002Z"  # a build git holds whose record the store never got
STAMP_D = "20260915T000000Z"  # the first version's one run
REVIEW_OF_TWO = (
    f"---\ncreated: 2026-09-17\ntype: review\nruns: {STAMP} {STAMP_2}\nreviewer: a cold session\n---\n"
    "\n## Findings\n\n"
    "### The first thing misses an edge\n\nseverity: defect\nverified: yes\njudged: test test_d, seed a\n\nReproduced.\n\n"
    "### A name could be shorter\n\nseverity: smell\nverified: no\n\nNot reproduced.\n\n"
    "### A line nobody reads\n\nseverity: smell\nverified: yes\njudged: none: not worth a test\n\nReproduced, left.\n"
)
REVIEW_OF_THE_RED_RUN = (
    f"---\ncreated: 2026-09-17\ntype: review\nruns: {STAMP_0}\nreviewer: a cold session\n---\n"
    "\n## Findings\n\n"
    "### The red run read everything first\n\nseverity: smell\nverified: no\n\nWhat happened.\n\n"
    "### Two tests for one finding\n\nseverity: smell\nverified: yes\njudged: test test_d, test test_b\n\nOnce under test.\n"
)


class TallyBase(unittest.TestCase):
    """The fixture: v0.1 tagged with seed d done in one commit and one run in the store; v0.2 in
    flight with seed b, the changelog's commit, the opening commit, a red run the store holds and
    git does not, three builds -- one green, one landed by the soft cap and red, one whose record
    the store never got -- two reviews and one commit by hand; and a record of the evaluation set
    naming no seed, which belongs to no version."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, IDENTITY))
        self.root = make_repo(Path(self.tmp.name))
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## v0.1: the start\n")
        self.commit("CHANGELOG.md rendered for v0.1")
        write(self.root, "opened.txt", "v0.2 opens\n")
        self.commit("v0.2 opens")
        write(self.root, "f.txt", "x\n")
        self.commit(f"b\n\nBuilt-By: factory at v0.1, run {STAMP}")
        write(self.root, "f.txt", "y\n")
        self.commit(f"b\n\nBuilt-By: factory at v0.1, run {STAMP_2}")
        write(self.root, "f.txt", "z\n")
        self.commit(f"b\n\nBuilt-By: factory at v0.1, run {STAMP_3}")
        write(self.root, f"docs/reviews/{STAMP}.md", REVIEW_OF_TWO)
        self.commit("the review of two builds, judged")
        write(self.root, f"docs/reviews/{STAMP_0}.md", REVIEW_OF_THE_RED_RUN)
        self.commit("the review of the red run")
        self.store = Path(self.tmp.name) / "store"
        self.record(STAMP_D, {"seed": "d", "check": "green", "stopped": "answer", "cap": "", "cost_usd": 0.25, "requests": 10})
        self.record(STAMP_0, {"seed": "b", "check": "red", "stopped": "answer", "cap": "", "cost_usd": 0.125, "requests": 15},
                    "error: cap reached (0.125 USD spent); report now")  # fmt: skip
        self.record(STAMP, {"seed": "b", "check": "green", "stopped": "answer", "cap": "", "cost_usd": 0.5, "requests": 20})
        self.record(STAMP_2, {"seed": "b", "check": "red", "stopped": "answer", "cap": "", "cost_usd": 0.125, "requests": 30},
                    "error: cap reached (0.125 USD spent); report now")  # fmt: skip
        self.record("20260917T000009Z", {"seed": None, "check": "green", "stopped": "answer", "cost_usd": 0.01, "requests": 5})
        self.configure(self.store)

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def record(self, stamp: str, numbers: dict, *returns: str) -> None:
        d = self.store / stamp
        d.mkdir(parents=True)
        (d / "numbers.json").write_text(json.dumps(numbers, indent=1) + "\n")
        (d / "messages.json").write_text(
            json.dumps([{"parts": [{"part_kind": "tool-return", "content": c}]} for c in returns])
        )

    def configure(self, store: Path | None) -> None:
        config = Path(self.tmp.name) / "instance.toml"
        config.write_text(f'records = "{store}"\n' if store is not None else "work = \"/w\"\n")
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(config)}))

    def row(self, tally_: tally.Tally, version: str) -> tuple:
        row = next(r for r in tally_.rows if r.version == version)
        return tuple(getattr(row, column) for column in COLUMNS)


class TallyTest(TallyBase):
    """seed: the-loop-in-numbers. What a version took, its builds and their cost, the reviews and
    what they found, and who made each commit, is counted by hand for every version note; git,
    the store and the review notes hold all of it, and `gather` reads them once."""

    def test_every_column_over_the_tagged_version_and_the_one_in_flight(self):
        """seed: the-loop-in-numbers. Oldest first, the version in flight last. The runs are the
        store's, by the seed each record names, so a red run whose tree was never pushed counts
        and is paid for; the builds are git's, by trailer; a build without a record counts under
        both builds and unrecorded and adds nothing; a review naming two of the version's runs is
        one review and one naming the unpushed run is another; a finding judged under two kinds
        counts once under each; a run landed by the soft cap is capped though it answered; a
        record naming no seed belongs to no version."""
        found = tally.gather(self.root)
        self.assertEqual([r.version for r in found.rows], ["v0.1", "v0.2"])
        self.assertEqual(found.unknown, ())
        self.assertEqual(self.row(found, "v0.1"), ("v0.1", 1, 1, 0, 1, 0, 0, 0, 0.25, 10, 0, 0, 0, 0, 0, 0, 0, 1, 1))
        self.assertEqual(
            self.row(found, "v0.2"),
            ("v0.2", 1, 3, 3, 1, 2, 2, 1, 0.75, 65, 2, 5, 1, 2, 1, 0, 1, 7, 4),
        )  # judged_test 2: one finding judged `test a, seed b`, one judged by two tests, once each

    def test_the_table_is_tab_separated_with_money_to_four_decimals(self):
        """seed: the-loop-in-numbers. One header, one row per version, the columns in the Goal's
        order, cost to four decimals as runs.py prints it, nothing after the table when nothing
        is unknown."""
        text = tally.render(tally.gather(self.root))
        lines = text.splitlines()
        self.assertEqual(lines[0].split("\t"), list(COLUMNS))
        self.assertEqual(
            lines[1].split("\t"),
            ["v0.1", "1", "1", "0", "1", "0", "0", "0", "0.2500", "10", "0", "0", "0", "0", "0", "0", "0", "1", "1"],
        )
        self.assertEqual(lines[2].split("\t")[:10], ["v0.2", "1", "3", "3", "1", "2", "2", "1", "0.7500", "65"])
        self.assertEqual(len(lines), 3)

    def test_a_store_that_cannot_be_read_is_unknown_and_the_rows_stand(self):
        """seed: the-loop-in-numbers. A configuration naming no store, and a store that is no
        directory, each leave the store's columns None with one line, and git's and the vault's
        columns as read; a value that means something else is never answered."""
        self.configure(None)
        found = tally.gather(self.root)
        self.assertEqual([r.version for r in found.rows], ["v0.1", "v0.2"])
        self.assertEqual(len(found.unknown), 1)
        self.assertTrue(found.unknown[0].startswith("store: "), found.unknown)
        row = self.row(found, "v0.2")
        self.assertEqual((row[0], row[1], row[3]), ("v0.2", 1, 3))
        self.assertEqual((row[2],) + row[4:10], (None,) * 7)
        self.assertEqual(row[10:], (2, 5, 1, 2, 1, 0, 1, 7, 4))
        self.configure(Path(self.tmp.name) / "nowhere")
        found = tally.gather(self.root)
        self.assertEqual(len(found.unknown), 1)
        self.assertTrue(found.unknown[0].startswith("store: "), found.unknown)
        self.assertEqual((self.row(found, "v0.2")[2],) + self.row(found, "v0.2")[4:10], (None,) * 7)
        text = tally.render(found)
        cells = text.splitlines()[2].split("\t")
        self.assertEqual([cells[2]] + cells[4:10], [""] * 7)
        self.assertTrue(text.splitlines()[-1].startswith("unknown: store: "), text)

    def test_a_record_whose_numbers_cannot_be_read_is_no_run_and_its_build_is_unrecorded(self):
        """seed: the-loop-in-numbers. A record on disk whose numbers.json is not JSON names no
        seed, so it is no version's run; its build, which git holds, counts as unrecorded; and
        its messages are not read for a cap."""
        (self.store / STAMP / "numbers.json").write_text("{not json\n")
        found = tally.gather(self.root)
        self.assertEqual(found.unknown, ())
        self.assertEqual(self.row(found, "v0.2")[2:10], (2, 3, 0, 2, 2, 2, 0.25, 45))

    def test_a_review_note_that_cannot_be_read_is_unknown(self):
        """seed: the-loop-in-numbers. From the first build's review: a note the vault could not
        read was dropped without a line and the count shrank. The review columns are None on
        every row, with one line naming the note; git's and the store's columns stand."""
        note = self.root / "docs" / "reviews" / f"{STAMP}.md"
        note.chmod(0)
        self.addCleanup(note.chmod, 0o644)
        found = tally.gather(self.root)
        self.assertEqual(len(found.unknown), 1)
        self.assertIn(f"docs/reviews/{STAMP}.md", found.unknown[0])
        for version in ("v0.1", "v0.2"):
            self.assertEqual(self.row(found, version)[10:17], (None,) * 7, version)
        self.assertEqual(self.row(found, "v0.2")[:10], ("v0.2", 1, 3, 3, 1, 2, 2, 1, 0.75, 65))
        self.assertEqual(self.row(found, "v0.2")[17:], (7, 4))

    def test_two_version_notes_that_are_no_tag_are_unknown(self):
        """seed: the-loop-in-numbers. From the first build's review: two untagged notes gave an
        empty table with no reason. The loop says `in_flight: ...` for the same facts; so does
        the tally, and the tags' rows stand."""
        write(self.root, "docs/versions/v0.3.md", "---\ntype: version\n---\n\n# v0.3: another\n\nAnother.\n\n## Changelog\n\n-\n")
        self.commit("a second note that is no tag")
        found = tally.gather(self.root)
        self.assertEqual([r.version for r in found.rows], ["v0.1"])
        self.assertEqual(len(found.unknown), 1)
        self.assertTrue(found.unknown[0].startswith("in_flight: "), found.unknown)
        self.assertEqual(self.row(found, "v0.1")[:4], ("v0.1", 1, 1, 0))

    def test_a_git_that_cannot_read_a_trailer_leaves_builds_empty(self):
        """seed: the-loop-in-numbers. From the first build's review: a git failing mid-gather
        printed zero builds beside three commits, which reads as three by hand. The columns git
        could not answer are None, rendered empty, and the line says so."""

        def dead(root, commit):
            raise repo.RepoError("git log -1", "git died")

        with mock.patch.object(repo, "trailers", dead):
            found = tally.gather(self.root)
        row = self.row(found, "v0.2")
        self.assertEqual(row[17], 7)  # the commits were listed
        self.assertEqual((row[3], row[7], row[18]), (None, None, None))  # builds, unrecorded, by_hand
        self.assertTrue(any(line.startswith("builds of v0.2: ") for line in found.unknown), found.unknown)
        cells = tally.render(found).splitlines()[2].split("\t")
        self.assertEqual((cells[3], cells[7], cells[18]), ("", "", ""))


class NumbersCommandTest(TallyBase):
    """seed: the-loop-in-numbers. `gate.py numbers` prints the table and writes nothing; one
    version prints its row alone; a version that is neither a tag nor in flight is a usage error."""

    def test_numbers_prints_the_table_and_writes_nothing(self):
        before = git(self.root, "status", "--porcelain")
        code, out, err = run(self.root, "numbers")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, tally.render(tally.gather(self.root)))
        self.assertEqual(git(self.root, "status", "--porcelain"), before)
        self.assertEqual(before, "")

    def test_one_version_prints_its_row_alone(self):
        code, out, err = run(self.root, "numbers", "v0.2")
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0].split("\t"), list(COLUMNS))
        self.assertEqual(lines[1].split("\t")[:4], ["v0.2", "1", "3", "3"])
        self.assertEqual(len(lines), 2)
        code, out, err = run(self.root, "numbers", "v0.1")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[1].split("\t")[0], "v0.1")

    def test_one_version_keeps_the_unknown_lines(self):
        """seed: the-loop-in-numbers. From the first build's review: `numbers <version>` printed
        the row with empty cells and dropped the line that said why."""
        self.configure(None)
        code, out, err = run(self.root, "numbers", "v0.2")
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[2].startswith("unknown: store: "), out)

    def test_a_version_that_is_none_is_a_usage_error(self):
        code, out, err = run(self.root, "numbers", "v0.9")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage", err)
        code, out, err = run(self.root, "numbers", "v0.2", "extra")
        self.assertEqual((code, out), (2, ""))


if __name__ == "__main__":
    unittest.main()
