"""What a version took, derived: what `tally.py` gives `gate.py numbers`.

    uv run python -m unittest test_tally -v

Written from docs/seeds/the-loop-in-numbers.md before the code, over the gate tests' own fixture
advanced two versions, a fixture store of records, and a review note. Nothing of this repository
is named here: no seed, no version, no stamp of the real store.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gate import IDENTITY, STAMP, git, make_repo, run, write

import tally

COLUMNS = (
    "version", "seeds", "builds", "green", "red", "capped", "unrecorded", "cost_usd", "requests",
    "reviews", "findings", "defects", "judged_test", "judged_seed", "judged_case", "judged_none",
    "commits", "by_hand",
)  # fmt: skip
STAMP_2 = "20260917T000001Z"
STAMP_3 = "20260917T000002Z"
REVIEW_OF_TWO = (
    f"---\ncreated: 2026-09-17\ntype: review\nruns: {STAMP} {STAMP_2}\nreviewer: a cold session\n---\n"
    "\n## Findings\n\n"
    "### The first thing misses an edge\n\nseverity: defect\nverified: yes\njudged: test test_d, seed a\n\nReproduced.\n\n"
    "### A name could be shorter\n\nseverity: smell\nverified: no\n\nNot reproduced.\n\n"
    "### A line nobody reads\n\nseverity: smell\nverified: yes\njudged: none: not worth a test\n\nReproduced, left.\n"
)


class TallyBase(unittest.TestCase):
    """The fixture: v0.1 tagged with seed d done in one commit; v0.2 in flight with seed b, the
    changelog's commit, the opening commit, three builds -- one green, one landed by the soft cap
    and red, one whose record the store never got -- and one commit by hand; a review of the
    first two builds with three findings."""

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
        write(self.root, "docs/reviews" + f"/{STAMP}.md", REVIEW_OF_TWO)
        self.commit("the review of two builds, judged")
        self.store = Path(self.tmp.name) / "store"
        self.record(STAMP, {"check": "green", "stopped": "answer", "cap": "", "cost_usd": 0.05, "requests": 20})
        self.record(STAMP_2, {"check": "red", "stopped": "answer", "cap": "", "cost_usd": 0.13, "requests": 30},
                    "error: cap reached (0.125 USD spent); report now")  # fmt: skip
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
        """seed: the-loop-in-numbers. Oldest first, the version in flight last; a build without a
        record counts and adds nothing; a review naming two of the version's builds is one
        review; a finding judged under two kinds counts once under each; a run landed by the soft
        cap is capped though it answered."""
        found = tally.gather(self.root)
        self.assertEqual([r.version for r in found.rows], ["v0.1", "v0.2"])
        self.assertEqual(found.unknown, ())
        self.assertEqual(self.row(found, "v0.1"), ("v0.1", 1, 0, 0, 0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1))
        self.assertEqual(
            self.row(found, "v0.2"),
            ("v0.2", 1, 3, 1, 1, 1, 1, 0.18, 50, 1, 3, 1, 1, 1, 0, 1, 6, 3),
        )

    def test_the_table_is_tab_separated_with_money_to_four_decimals(self):
        """seed: the-loop-in-numbers. One header, one row per version, the columns in the Goal's
        order, cost to four decimals as runs.py prints it, nothing after the table when nothing
        is unknown."""
        text = tally.render(tally.gather(self.root))
        lines = text.splitlines()
        self.assertEqual(lines[0].split("\t"), list(COLUMNS))
        self.assertEqual(lines[1].split("\t"), ["v0.1", "1", "0", "0", "0", "0", "0", "0.0000", "0", "0", "0", "0", "0", "0", "0", "0", "1", "1"])
        self.assertEqual(lines[2].split("\t")[:9], ["v0.2", "1", "3", "1", "1", "1", "1", "0.1800", "50"])
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
        self.assertEqual(row[:3], ("v0.2", 1, 3))
        self.assertEqual(row[3:9], (None, None, None, None, None, None))
        self.assertEqual(row[9:], (1, 3, 1, 1, 1, 0, 1, 6, 3))
        self.configure(Path(self.tmp.name) / "nowhere")
        found = tally.gather(self.root)
        self.assertEqual(len(found.unknown), 1)
        self.assertTrue(found.unknown[0].startswith("store: "), found.unknown)
        self.assertEqual(self.row(found, "v0.2")[3:9], (None, None, None, None, None, None))
        text = tally.render(found)
        self.assertEqual(text.splitlines()[2].split("\t")[3:9], [""] * 6)
        self.assertTrue(text.splitlines()[-1].startswith("unknown: store: "), text)

    def test_a_record_whose_numbers_cannot_be_read_is_unrecorded(self):
        """seed: the-loop-in-numbers. A record on disk whose numbers.json is not JSON counts as a
        build and as unrecorded, and its messages are not read for a cap."""
        (self.store / STAMP / "numbers.json").write_text("{not json\n")
        found = tally.gather(self.root)
        self.assertEqual(found.unknown, ())
        self.assertEqual(self.row(found, "v0.2")[2:9], (3, 0, 1, 1, 2, 0.13, 30))


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
        self.assertEqual(lines[1].split("\t")[:3], ["v0.2", "1", "3"])
        self.assertEqual(len(lines), 2)
        code, out, err = run(self.root, "numbers", "v0.1")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[1].split("\t")[0], "v0.1")

    def test_a_version_that_is_none_is_a_usage_error(self):
        code, out, err = run(self.root, "numbers", "v0.9")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage", err)
        code, out, err = run(self.root, "numbers", "v0.2", "extra")
        self.assertEqual((code, out), (2, ""))


if __name__ == "__main__":
    unittest.main()
