"""The repository's reader and writer, apart: what `repo.py` gives the gate and the loop.

    uv run python -m unittest test_repo -v

Written from docs/seeds/the-gate-in-three.md before the code, over the gate tests' own fixtures.
One shape for a command's answer, and a reader that needs git to have answered raises rather
than answering with nothing.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_gate import IDENTITY, TEST_RED_B, git, make_repo, write

import repo


class RepoTest(unittest.TestCase):
    """seed: the-gate-in-three. `git(root, *args)` never raises and answers `Result(code, out,
    err)`; a reader that needs git to have answered -- the tags, the listing, the builds, the
    trailers, a tag's date, a short hash -- raises `RepoError` naming the command and git's words,
    never an empty answer that reads as nothing to report."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, IDENTITY))
        self.root = make_repo(Path(self.tmp.name))

    def copy_without_git(self) -> Path:
        copy = Path(self.tmp.name) / "copy"
        shutil.copytree(self.root, copy, ignore=shutil.ignore_patterns(".git"))
        return copy

    def test_git_answers_with_one_shape_and_never_raises(self):
        done = repo.git(self.root, "rev-parse", "HEAD")
        self.assertEqual(done.code, 0, done.err)
        self.assertEqual(len(done.out.strip()), 40)
        self.assertEqual(done.err, "")
        gone = repo.git(Path(self.tmp.name) / "gone", "status")
        self.assertNotEqual(gone.code, 0)
        self.assertTrue(gone.err)

    def test_a_reader_that_needs_git_raises_naming_the_command_and_gits_words(self):
        copy = self.copy_without_git()
        with self.assertRaises(repo.RepoError) as raised:
            repo.tags(copy)
        self.assertIn("tag", raised.exception.command)
        self.assertTrue(raised.exception.err)
        self.assertIn("tag", str(raised.exception))
        with self.assertRaises(repo.RepoError) as raised:
            repo.builds(copy, None)
        self.assertIn("rev-list", raised.exception.command)
        for read in (
            lambda: repo.trailers(copy, "HEAD"),
            lambda: repo.tag_date(copy, "v0.1"),
            lambda: repo.short_hash(copy, "0123456789abcdef0123456789abcdef01234567"),
        ):
            with self.assertRaises(repo.RepoError):
                read()

    def test_the_tags_the_highest_of_them_and_the_date_of_one(self):
        self.assertEqual(repo.tags(self.root), {"v0.1"})
        self.assertEqual(repo.highest({"v0.1", "v0.10", "v0.2", "other"}), "v0.10")
        self.assertIsNone(repo.highest(set()))
        self.assertRegex(repo.tag_date(self.root, "v0.1"), r"^\d{4}-\d{2}-\d{2}$")

    def test_the_builds_since_a_tag_their_trailers_and_their_short_hashes(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(repo.builds(self.root, None), [head])
        self.assertEqual(repo.builds(self.root, "v0.1"), [])
        write(self.root, "f.txt", "x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "b\n\nBuilt-By: factory at v0.1, run 20260917T000000Z")
        built = git(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(repo.builds(self.root, "v0.1"), [built])
        self.assertEqual(repo.trailers(self.root, built), ["Built-By: factory at v0.1, run 20260917T000000Z"])
        self.assertEqual(repo.trailers(self.root, head), [])
        short = repo.short_hash(self.root, built)
        self.assertTrue(built.startswith(short))
        self.assertGreaterEqual(len(short), 7)

    def test_the_listing_is_gits_and_none_where_git_answers_for_nobody(self):
        listing = repo.listing(self.root, self.root / "docs")
        self.assertIn("docs/seeds/a.md", listing.listed)
        self.assertEqual(listing.ignored, set())
        copy = self.copy_without_git()
        self.assertIsNone(repo.listing(copy, copy / "docs"))
        real = subprocess.run

        def failing(argv, *args, **kwargs):
            if "ls-files" in argv:
                raise OSError("git died")
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", failing):  # git failing inside a checkout
            with self.assertRaises(repo.RepoError) as raised:
                repo.listing(self.root, self.root / "docs")
        self.assertIn("ls-files", raised.exception.command)

    def test_the_tests_of_the_root_are_read_once_with_their_names_and_docstrings(self):
        found = repo.tests(self.root)
        self.assertIn(repo.Test("test_d", "seed: d. The first thing holds."), found)
        self.assertIn("RepoTest", [test.name for test in found])
        write(self.root, "test_bad.py", "def (\n")
        with self.assertRaises(repo.RepoError) as raised:
            repo.tests(self.root)
        self.assertIn("test_bad.py", str(raised.exception))

    def test_the_suite_says_which_of_four_things_it_was(self):
        self.assertEqual(repo.suite(self.root), "green")
        write(self.root, "test_repo.py", TEST_RED_B)
        self.assertEqual(repo.suite(self.root), "red")
        with mock.patch.object(subprocess, "run", side_effect=OSError("no interpreter")):
            self.assertEqual(repo.suite(self.root), "could not run")
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("unittest", 300)):
            self.assertEqual(repo.suite(self.root), "timed out")

    def test_a_tag_is_cut_by_git_and_its_answer_returned(self):
        done = repo.tag(self.root, "v0.2", "the message")
        self.assertEqual(done.code, 0, done.err)
        self.assertEqual(git(self.root, "cat-file", "-t", "v0.2").strip(), "tag")
        again = repo.tag(self.root, "v0.2", "again")
        self.assertNotEqual(again.code, 0)
        self.assertIn("already exists", again.err)

    def test_the_wheels_of_a_directory_and_one_that_cannot_be_read(self):
        dist = self.root / "dist"
        dist.mkdir()
        (dist / "a.whl").write_text("")
        (dist / "b.txt").write_text("")
        self.assertEqual(repo.wheels(dist), {"a.whl"})
        self.assertEqual(repo.wheels(self.root / "nowhere"), set())  # no directory is no wheel
        dist.chmod(0)
        self.addCleanup(dist.chmod, 0o755)
        with self.assertRaises(repo.RepoError):  # a directory that cannot be read is not empty
            repo.wheels(dist)


if __name__ == "__main__":
    unittest.main()
