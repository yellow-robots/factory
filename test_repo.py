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
        self.assertIn(repo.Test("test_repo.RepoTest.test_d", "test_d", "seed: d. The first thing holds."), found.found)
        self.assertIn(("test_repo.RepoTest", "RepoTest"), [(test.id, test.name) for test in found.found])
        self.assertEqual(found.unparseable, ())
        write(self.root, "test_bad.py", "def (\n")
        found = repo.tests(self.root)  # from the second review: a typed value, not a smuggling error
        self.assertIn("test_d", [test.name for test in found.found])
        self.assertEqual([path for path, _ in found.unparseable], ["test_bad.py"])
        self.assertIn("does not parse", found.unparseable[0][1])
        self.assertNotIn(str(self.root), found.unparseable[0][1])

    def test_the_status_a_diff_since_a_tag_and_a_commits_message_raise_when_git_cannot_answer(self):
        """seed: the-gate-in-three. From the review: the release read `git status` and `git diff`
        through raw calls that ignored the code, and a build's message the same way."""
        self.assertEqual(repo.status(self.root), ())
        write(self.root, "AGENTS.md", "changed\n")
        self.assertEqual(repo.status(self.root), ("AGENTS.md",))
        self.assertFalse(repo.changed_since(self.root, "v0.1", "AGENTS.md"))  # not committed yet
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "a\n\nBuilt-By: factory at v0.1, run 20260917T000000Z")
        self.assertTrue(repo.changed_since(self.root, "v0.1", "AGENTS.md"))
        head = git(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(repo.message(self.root, head), "a\n\nBuilt-By: factory at v0.1, run 20260917T000000Z\n")
        copy = self.copy_without_git()
        for read in (
            lambda: repo.status(copy),
            lambda: repo.changed_since(copy, "v0.1", "AGENTS.md"),
            lambda: repo.message(copy, head),
        ):
            with self.assertRaises(repo.RepoError):
                read()

    def test_gits_words_are_one_line(self):
        """seed: the-gate-in-three. From the review: stderr was kept as git wrote it, newlines and
        advice included, so a problem built from it ran to nine lines."""
        done = repo.git(Path(self.tmp.name) / "gone", "status")
        self.assertNotIn("\n", done.err)
        self.assertTrue(done.err)
        copy = self.copy_without_git()
        with self.assertRaises(repo.RepoError) as raised:
            repo.tags(copy)
        self.assertNotIn("\n", raised.exception.err)
        self.assertNotIn("  ", raised.exception.err)

    def test_the_readers_the_loop_needs_of_the_head_the_branches_a_subject_and_a_distance(self):
        """seed: the-step-nobody-noticed. From the loop's first review: it ran nine raw git
        commands of its own; these are their homes."""
        head = git(self.root, "rev-parse", "HEAD").strip()
        current = git(self.root, "branch", "--show-current").strip()
        self.assertEqual(repo.toplevel(self.root), self.root.resolve())
        self.assertEqual(repo.head(self.root), head)
        self.assertEqual(repo.branch(self.root), current)
        self.assertEqual(repo.branches_at(self.root, head), (current,))
        self.assertEqual(repo.subject(self.root, head), "one")
        self.assertEqual(repo.distance(self.root, "v0.1", head), 0)
        write(self.root, "f.txt", "x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "two")
        two = git(self.root, "rev-parse", "HEAD").strip()
        self.assertEqual(repo.distance(self.root, "v0.1", two), 1)
        self.assertIsNone(repo.distance(self.root, two, "v0.1"))  # not an ancestor
        git(self.root, "switch", "-q", "--detach")
        self.assertIsNone(repo.branch(self.root))
        self.assertEqual(repo.branches_at(self.root, two), (current,))
        copy = self.copy_without_git()
        self.assertIsNone(repo.toplevel(copy))
        for read in (
            lambda: repo.head(copy),
            lambda: repo.branch(copy),
            lambda: repo.branches_at(copy, head),
            lambda: repo.subject(copy, head),
            lambda: repo.distance(copy, "v0.1", head),
        ):
            with self.assertRaises(repo.RepoError):
                read()

    def test_a_remote_is_asked_with_a_timeout_and_raises_when_it_cannot_answer(self):
        """seed: the-step-nobody-noticed."""
        head = git(self.root, "rev-parse", "HEAD").strip()
        with self.assertRaises(repo.RepoError):
            repo.ls_remote(self.root, "origin", "main", timeout=5)  # no origin
        bare = Path(self.tmp.name) / "bare.git"
        git(self.root, "clone", "-q", "--bare", str(self.root), str(bare))
        git(self.root, "remote", "add", "origin", str(bare))
        current = git(self.root, "branch", "--show-current").strip()
        self.assertEqual(repo.ls_remote(self.root, "origin", current, timeout=5), head)
        calls = []
        real = subprocess.run

        def recording(argv, *args, **kwargs):
            calls.append((list(argv), kwargs))
            return real(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", recording):
            repo.ls_remote(self.root, "origin", current, timeout=7)
        remote = [kwargs for argv, kwargs in calls if "ls-remote" in argv]
        self.assertEqual([kwargs.get("timeout") for kwargs in remote], [7])

    def test_a_seeds_tests_are_run_alone_and_a_run_that_could_not_happen_raises(self):
        """seed: the-step-nobody-noticed."""
        self.assertEqual(repo.run_tests(self.root, ("test_repo.RepoTest.test_d",), timeout=60), "green")
        write(self.root, "test_repo.py", TEST_RED_B)
        self.assertEqual(repo.run_tests(self.root, ("test_repo.RepoTest.test_b",), timeout=60), "red")
        self.assertEqual(repo.run_tests(self.root, ("test_repo.RepoTest.test_d",), timeout=60), "green")
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("unittest", 60)):
            with self.assertRaises(repo.RepoError) as raised:
                repo.run_tests(self.root, ("test_repo.RepoTest.test_b",), timeout=60)
        self.assertIn("unittest", raised.exception.command)

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
