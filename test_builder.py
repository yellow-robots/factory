"""The builder's acceptance tests, written from the v0.3 plan (docs/versions/v0.3.md) before the code.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel or answered by a
mock transport, the sandbox is a fake that returns scripted check results, and docker is a
patched subprocess. The interface under test is the one the plan names.
"""

import asyncio
import contextlib
import gzip
import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import httpx2
from pydantic_ai import ModelAPIError, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

import builder
from builder import BuildReport, Tools, Sandbox, build_agent, render, run

models.ALLOW_MODEL_REQUESTS = False

REPORT = {
    "changed": ["f.py"],
    "did": ["f.py: changed x so the test passes"],
    "check": "green",
    "failing": [],
    "unsure": [],
}
ROLE_SHA256 = "97196fd3f141c915"  # v0.3 decision 10, one word changed in v0.5, search named in v0.7; changing the prompt is a version


class FakeSandbox:
    """Scripted check results, consumed in order; records every call."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def run(self, checkout, run_dir, n):
        self.calls.append((Path(checkout), Path(run_dir), n))
        return self.results.pop(0)


def parts_of(messages: list[ModelMessage]) -> list[str]:
    return [type(p).__name__ for m in messages for p in m.parts]


def returns_of(messages: list[ModelMessage]) -> list[str]:
    return [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def call(name: str, args: dict, cid: str) -> ToolCallPart:
    return ToolCallPart(name, args, tool_call_id=cid)


def scripted(*turns):
    """A FunctionModel that answers turn i with the i-th list of tool calls."""
    turns = list(turns)

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        parts = turns.pop(0) if turns else [call("final_result", REPORT, "end")]
        return ModelResponse(parts=list(parts))

    return FunctionModel(model)


def git(checkout: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=checkout, capture_output=True, text=True, check=True,
    )
    return out.stdout


def names_in(listing: str) -> list[str]:
    return [line.split("\t")[2] for line in listing.splitlines() if "\t" in line]


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.root.mkdir()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        (self.root / "a.txt").write_text("one\ntwo\nthree\n")
        (self.root / ".gitignore").write_text("runs/\n")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("".join(f"line {i}\n" for i in range(1, 1001)))
        for hidden in builder.HIDDEN:
            (self.root / hidden).mkdir()
            (self.root / hidden / "secret").write_text("the record\n")
        os.symlink("/etc/hostname", self.root / "escape")
        os.symlink("/etc", self.root / "outside_dir")
        for protected in ("test_x.py", "testfoo.py", "sub/test_y.py", "tests/a/b.py", "pyproject.toml", "uv.lock", "check.Dockerfile"):
            (self.root / protected).parent.mkdir(parents=True, exist_ok=True)
            (self.root / protected).write_text("keep\n")
        os.symlink("test_x.py", self.root / "alias.py")
        (self.root / "contest.py").write_text("free\n")
        (self.root / "tests_x.py").write_text("keep\n")  # test*.py: unittest would discover it
        (self.root / "attest.py").write_text("free\n")
        self.sandbox = FakeSandbox([])
        self.tools = Tools(self.root, self.run_dir, sandbox=self.sandbox)

    # carried over from v0.2

    def test_list_root_hides_the_record_and_shows_kinds(self):
        out = self.tools.list(".")
        self.assertIn("file\t14\ta.txt", out)
        self.assertIn("dir\t0\tsub", out)
        self.assertIn("link\t0\tescape", out)
        names = names_in(out)
        self.assertIn(".gitignore", names)
        for hidden in builder.HIDDEN:
            self.assertNotIn(hidden, names)

    def test_the_hidden_names_are_the_record_the_harness_the_caches_and_git(self):
        """seed: terms-checkout-and-tools. plans is gone from the checkout and from the list."""
        self.assertEqual(builder.HIDDEN, ("runs", ".claude", "__pycache__", ".venv", ".git"))  # cases is the harness's to add, since the v0.11 review

    def test_a_name_the_harness_adds_is_hidden_like_the_record(self):
        """seed: pass-rate-error. The evaluation set's cases, their goals and the word that says
        what a pass is, are the harness's: it names `cases` beside the builder's own hidden names
        and no tool lists, reads, searches, writes or edits it."""
        (self.root / "cases" / "alpha").mkdir(parents=True)
        (self.root / "cases" / "alpha" / "pass.txt").write_text("green\n")
        self.assertNotIn("cases", builder.HIDDEN)
        tools = Tools(self.root, self.run_dir, hidden=(*builder.HIDDEN, "cases"), sandbox=self.sandbox)
        self.assertNotIn("cases", names_in(tools.list(".")))
        self.assertIn("cases", names_in(self.tools.list(".")))  # the builder alone shows it
        self.assertTrue(tools.list("cases").startswith("error: not part of the checkout"))
        self.assertTrue(tools.read("cases/alpha/pass.txt").startswith("error: not part of the checkout"))
        self.assertTrue(tools.search("green").startswith("no matches"))
        self.assertTrue(tools.write("cases/alpha/pass.txt", "red\n").startswith("error:"))
        self.assertTrue(tools.edit("cases/alpha/pass.txt", "green", "red").startswith("error:"))
        self.assertEqual((self.root / "cases" / "alpha" / "pass.txt").read_text(), "green\n")
        self.assertEqual(tools.read_paths, [])

    def test_paths_cannot_leave_the_checkout(self):
        for bad in ("..", "../..", "/etc", "escape", "outside_dir/hostname", *(f"{h}/secret" for h in builder.HIDDEN)):
            self.assertTrue(self.tools.read(bad).startswith("error:"), bad)
        self.assertTrue(self.tools.list("..").startswith("error: outside the checkout"))
        self.assertTrue(self.tools.list(".claude").startswith("error: not part of the checkout"))
        self.assertTrue(self.tools.list(".git").startswith("error: not part of the checkout"))
        self.assertEqual(self.tools.read_paths, [])
        self.assertEqual(self.tools.listed, [])

    def test_read_numbers_lines_and_truncates_with_a_continuation(self):
        self.assertEqual(self.tools.read("a.txt"), "1\tone\n2\ttwo\n3\tthree")
        out = self.tools.read("sub/b.txt")
        self.assertTrue(out.startswith("1\tline 1\n"))
        self.assertIn(f"...\ttruncated; continue with start={builder.READ_LINES_CAP + 1}", out)
        out = self.tools.read("sub/b.txt", start=990)
        self.assertTrue(out.startswith("990\tline 990\n"))
        self.assertTrue(out.endswith("1000\tline 1000"))
        self.assertEqual(self.tools.lines_read, 3 + builder.READ_LINES_CAP + 11)

    def test_a_line_longer_than_the_byte_cap_is_cut_and_the_next_line_continues(self):
        (self.root / "wide.txt").write_text("x" * 40_000 + "\nshort\n")
        out = self.tools.read("wide.txt")
        self.assertTrue(out.startswith("1\t" + "x" * 100))
        self.assertIn(f"(line cut at {builder.READ_BYTES_CAP} bytes)", out)
        self.assertTrue(out.endswith("...\ttruncated; continue with start=2"))
        self.assertEqual(self.tools.read("wide.txt", start=2), "2\tshort")

    def test_wrong_kinds_missing_paths_and_symlink_loops_are_errors_not_crashes(self):
        os.symlink("loop", self.root / "loop")
        self.assertTrue(self.tools.list("a.txt").startswith("error: not a directory"))
        self.assertTrue(self.tools.read("sub").startswith("error: not a file"))
        self.assertTrue(self.tools.read("nope.txt").startswith("error: not a file"))
        self.assertTrue(self.tools.read("loop").startswith("error:"))
        self.assertTrue(self.tools.list("loop").startswith("error:"))

    def test_the_docstrings_state_the_caps(self):
        self.assertIn(str(builder.READ_LINES_CAP), Tools.read.__doc__)
        self.assertIn(str(builder.READ_BYTES_CAP), Tools.read.__doc__)
        self.assertIn(str(builder.CHECK_CAP), Tools.check.__doc__)
        self.assertIn(str(builder.SEARCH_LINES_CAP), Tools.search.__doc__)  # seed: codebase-context
        self.assertIn(str(builder.SEARCH_BYTES_CAP), Tools.search.__doc__)

    # v0.3: write

    def test_write_creates_with_parents_and_overwrites(self):
        self.assertEqual(self.tools.write("new/dir/f.txt", "a\nb\n"), "wrote new/dir/f.txt (2 lines)")
        self.assertEqual((self.root / "new" / "dir" / "f.txt").read_text(), "a\nb\n")
        self.assertEqual(self.tools.write("new/dir/f.txt", "c\n"), "wrote new/dir/f.txt (1 lines)")
        self.assertEqual((self.root / "new" / "dir" / "f.txt").read_text(), "c\n")
        self.assertEqual(self.tools.written, ["new/dir/f.txt", "new/dir/f.txt"])

    def test_write_and_edit_refuse_outside_hidden_and_protected_paths(self):
        outside = ("../x.txt", "/etc/x", "escape", "outside_dir/x")
        hidden = tuple(f"{h}/x" for h in builder.HIDDEN) + (".git/hooks/pre-commit",)
        protected = ("test_x.py", "testfoo.py", "tests_x.py", "sub/test_y.py", "tests/a/b.py", "pyproject.toml", "uv.lock", "check.Dockerfile", "alias.py")
        for bad in outside + hidden + protected:
            self.assertTrue(self.tools.write(bad, "x\n").startswith("error:"), bad)
            self.assertTrue(self.tools.edit(bad, "keep", "x").startswith("error:"), bad)
        for p in protected:
            self.assertIn("protected", self.tools.write(p, "x\n"), p)
            self.assertEqual((self.root / p).read_text(), "keep\n", p)
        self.assertFalse((self.root / "runs" / "x").exists())
        self.assertFalse((self.root / ".git" / "hooks").exists())
        self.assertFalse(Path("/etc/x").exists())
        self.assertEqual(self.tools.written, [])
        self.assertEqual(self.tools.edited, [])

    def test_names_that_only_resemble_protected_ones_are_free(self):
        self.assertTrue(self.tools.write("contest.py", "x\n").startswith("wrote contest.py"))
        self.assertTrue(self.tools.write("attest.py", "x\n").startswith("wrote attest.py"))
        self.assertTrue(self.tools.write("sub/pyproject.toml", "x\n").startswith("wrote sub/pyproject.toml"))
        self.assertTrue(self.tools.edit("contest.py", "x", "y").startswith("edited contest.py"))

    def test_git_attributes_and_ignore_files_are_protected(self):
        """seed: terms-checkout-and-tools. A .gitattributes or .gitignore the model wrote would
        change what git records of the run, a filter running on the host or a file hidden from
        the diff: both are protected at any depth, readable and listable still."""
        (self.root / "sub" / ".gitattributes").write_text("keep\n")
        for bad in (".gitattributes", ".gitignore", "sub/.gitignore", "sub/.gitattributes"):
            self.assertIn("protected", self.tools.write(bad, "x\n"), bad)
        self.assertIn("protected", self.tools.edit(".gitignore", "runs/", "x"))
        self.assertIn("protected", self.tools.edit("sub/.gitattributes", "keep", "x"))
        self.assertEqual((self.root / ".gitignore").read_text(), "runs/\n")
        self.assertEqual((self.root / "sub" / ".gitattributes").read_text(), "keep\n")
        self.assertEqual((self.tools.written, self.tools.edited), ([], []))
        self.assertIn("runs/", self.tools.read(".gitignore"))
        self.assertIn(".gitignore", self.tools.list("."))
        self.assertTrue(self.tools.write("gitattributes.txt", "x\n").startswith("wrote"))

    def test_a_dot_git_component_is_not_part_of_the_checkout_at_any_depth(self):
        """seed: record-hardening. sub/.git/x is git's and not the checkout's: no tool reads, lists,
        writes or edits it, and a listing does not show it, as with .git at the root."""
        (self.root / "sub" / ".git").mkdir()
        (self.root / "sub" / ".git" / "config").write_text("[core]\n")
        for path in ("sub/.git", "sub/.git/config", "sub/.git/hooks/pre-commit", "a/b/.git/x"):
            self.assertTrue(self.tools.write(path, "x\n").startswith("error: not part of the checkout"), path)
            self.assertTrue(self.tools.read(path).startswith("error: not part of the checkout"), path)
        self.assertTrue(self.tools.list("sub/.git").startswith("error: not part of the checkout"))
        self.assertTrue(self.tools.edit("sub/.git/config", "core", "x").startswith("error: not part of the checkout"))
        self.assertNotIn("sub/.git", names_in(self.tools.list("sub")))
        self.assertIn("sub/b.txt", names_in(self.tools.list("sub")))  # entries stay paths from the checkout root
        self.assertFalse((self.root / "a").exists())
        self.assertEqual((self.root / "sub" / ".git" / "config").read_text(), "[core]\n")
        self.assertEqual((self.tools.written, self.tools.edited), ([], []))

    def test_the_protected_refusal_names_the_real_reason(self):
        """seed: record-hardening. The model reads why a path is protected, and the reason covers
        every protected file, not only the tests and the toolchain."""
        reason = "(not the builder's to change: the tests, the toolchain, the vault and git's own files)"
        for path in (".gitignore", "test_x.py", "docs/x.md", "uv.lock"):
            self.assertEqual(self.tools.write(path, "x\n"), f"error: protected: {path} {reason}", path)

    def test_search_finds_lines_by_path_and_number_across_the_checkout(self):
        """seed: codebase-context. Plain-text, case-sensitive matches as path:line:text, files in
        list's order, hidden paths never searched, a path outside or hidden an error like read's,
        files that are not UTF-8 skipped and counted, an empty pattern an error, no match said so."""
        (self.root / "bin.dat").write_bytes(b"\xff\xfe two\n")
        self.assertEqual(self.tools.search("two"), "a.txt:2:two\n...\t1 files not searched")
        out = self.tools.search("line 99")
        self.assertEqual(out.splitlines()[0], "sub/b.txt:99:line 99")
        self.assertEqual(len(out.splitlines()), 12)  # 99 and 990 to 999, then the file not searched
        self.assertEqual(self.tools.search("record"), "no matches\n...\t1 files not searched")  # the hidden files hold "the record" and are not counted
        self.assertEqual(self.tools.search("TWO"), "no matches\n...\t1 files not searched")
        self.assertEqual(self.tools.search("keep", "sub"), "sub/test_y.py:1:keep")
        for bad in ("runs", ".git", ".claude"):
            self.assertTrue(self.tools.search("x", bad).startswith("error: not part of the checkout"), bad)
        self.assertTrue(self.tools.search("x", "..").startswith("error: outside the checkout"))
        self.assertTrue(self.tools.search("x", "escape").startswith("error:"))
        self.assertTrue(self.tools.search("").startswith("error:"))
        self.assertEqual(len(self.tools.searched), 5)

    def test_search_is_capped_by_lines_and_bytes_and_says_how_many_more(self):
        """seed: codebase-context."""
        (self.root / "many.txt").write_text("".join(f"needle {i}\n" for i in range(500)))
        out = self.tools.search("needle")
        lines = out.splitlines()
        self.assertEqual(len(lines), builder.SEARCH_LINES_CAP + 1)
        self.assertEqual(lines[0], "many.txt:1:needle 0")
        self.assertEqual(lines[-1], f"...\t{500 - builder.SEARCH_LINES_CAP} more matches not shown")
        (self.root / "wide.txt").write_text("".join("w" * 1000 + " needle\n" for _ in range(60)))
        out = self.tools.search("w" * 1000)  # 60 matches of a kilobyte each: the byte cap binds first
        self.assertLessEqual(len(out.encode()), builder.SEARCH_BYTES_CAP + 200)
        self.assertTrue(out.splitlines()[0].startswith("wide.txt:1:"))
        self.assertTrue(out.splitlines()[-1].startswith("...\t"))
        self.assertEqual(len(self.tools.searched), 2)

    def test_search_skips_files_over_a_size_cap_counts_the_files_it_skips_and_numbers_lines_like_read(self):
        """seed: codebase-context. A file larger than SEARCH_FILE_CAP bytes is not searched, like one
        that is not UTF-8; the result then ends with how many files were not searched, after the
        matches or after `no matches`; line numbers are read's, universal newlines, so a form feed
        inside a line starts no new line."""
        self.assertIn(str(builder.SEARCH_FILE_CAP), Tools.search.__doc__)
        (self.root / "big.txt").write_bytes(b"needle\n" + b"x" * builder.SEARCH_FILE_CAP)  # over the cap by a line
        (self.root / "fits.txt").write_bytes(b"needle\n" + b"x" * (builder.SEARCH_FILE_CAP - 7))  # exactly the cap
        (self.root / "bin.dat").write_bytes(b"\xff\xfe needle\n")
        self.assertEqual(self.tools.search("needle").splitlines(), ["fits.txt:1:needle", "...\t2 files not searched"])
        self.assertEqual(self.tools.search("nothing").splitlines(), ["no matches", "...\t2 files not searched"])
        self.assertEqual(self.tools.search("line 1000", "sub"), "sub/b.txt:1000:line 1000")  # nothing skipped under sub
        (self.root / "ff.txt").write_bytes(b"one\n\x0ctwo\nthree needle\n")
        self.assertIn("ff.txt:3:three needle", self.tools.search("needle"))
        self.assertIn("3\tthree needle", self.tools.read("ff.txt"))

    def test_search_shows_the_first_matches_and_cuts_a_lone_match_longer_than_the_cap(self):
        """seed: codebase-context. The matches shown are the first in order: the first match that
        does not fit in the bytes left ends the shown part, and the trailer counts exactly what
        follows; a match longer than the cap, when nothing was shown yet, is cut to fit and marked,
        like read's long line, so no match is out of reach."""
        lines = [("w" * 2000 if i % 2 == 0 else "s") + " needle" for i in range(80)]
        (self.root / "alt.txt").write_text("\n".join(lines) + "\n")
        out = self.tools.search("needle").splitlines()
        shown, trailer = out[:-1], out[-1]
        self.assertEqual(shown, [f"alt.txt:{i + 1}:{lines[i]}" for i in range(len(shown))])  # a prefix of the matches
        self.assertLess(len(shown), 80)
        self.assertEqual(trailer, f"...\t{80 - len(shown)} more matches not shown")
        (self.root / "alt.txt").unlink()
        (self.root / "long.txt").write_text("L" * 40_000 + " needle\n")
        out = self.tools.search("needle")
        self.assertTrue(out.startswith("long.txt:1:LLLL"))
        self.assertIn("cut", out)
        self.assertNotIn("more matches", out)
        self.assertLessEqual(len(out.encode()), builder.SEARCH_BYTES_CAP + 200)

    def test_search_counts_a_directory_it_cannot_list_and_refuses_a_pattern_with_a_newline(self):
        """seed: codebase-context. A directory that cannot be listed counts once among the entries
        not searched, since what is under it was not; a pattern with a newline in it is an error,
        since search matches one line at a time; the docstring says a lone long match is cut."""
        self.assertIn("cut", Tools.search.__doc__)
        self.assertTrue(self.tools.search("one\ntwo").startswith("error:"))
        self.assertTrue(self.tools.search("one\n").startswith("error:"))
        self.assertEqual(self.tools.search("one"), "a.txt:1:one")
        if os.geteuid() == 0:
            self.skipTest("root lists any directory")
        (self.root / "locked").mkdir()
        (self.root / "locked" / "t.txt").write_text("one\n")
        (self.root / "locked").chmod(0)
        self.addCleanup((self.root / "locked").chmod, 0o755)
        self.assertEqual(self.tools.search("one"), "a.txt:1:one\n...\t1 files not searched")
        self.assertTrue(self.tools.list("locked").startswith("error:"))

    def test_docs_are_readable_and_never_written(self):
        """seed: docs-protected. The seeds live in the checkout the builder reads: write and edit
        refuse anything under docs/ as protected, list and read still work there."""
        (self.root / "docs" / "seeds").mkdir(parents=True)
        (self.root / "docs" / "seeds" / "s.md").write_text("keep\n")
        for bad in ("docs/seeds/s.md", "docs/new.md", "docs/deeper/still/new.md"):
            self.assertTrue(self.tools.write(bad, "x\n").startswith("error:"), bad)
            self.assertIn("protected", self.tools.write(bad, "x\n"), bad)
        self.assertIn("protected", self.tools.edit("docs/seeds/s.md", "keep", "x"))
        self.assertEqual((self.root / "docs" / "seeds" / "s.md").read_text(), "keep\n")
        self.assertFalse((self.root / "docs" / "new.md").exists())
        self.assertEqual((self.tools.written, self.tools.edited), ([], []))
        self.assertIn("s.md", self.tools.list("docs/seeds"))
        self.assertIn("keep", self.tools.read("docs/seeds/s.md"))
        self.assertTrue(self.tools.write("docsx/free.md", "x\n").startswith("wrote docsx/free.md"))

    # v0.3: edit

    def test_edit_replaces_exactly_one_occurrence(self):
        self.assertEqual(self.tools.edit("a.txt", "two", "2"), "edited a.txt (3 -> 3 lines)")
        self.assertEqual((self.root / "a.txt").read_text(), "one\n2\nthree\n")
        self.assertEqual(self.tools.edit("a.txt", "2\n", "2\n2b\n"), "edited a.txt (3 -> 4 lines)")
        self.assertEqual(self.tools.edited, ["a.txt", "a.txt"])

    def test_edit_errors_on_zero_empty_and_many_occurrences_without_touching_the_file(self):
        (self.root / "dup.txt").write_text("x\nx\n")
        self.assertEqual(self.tools.edit("a.txt", "nope", "x"), "error: old text not found in a.txt")
        self.assertEqual(self.tools.edit("a.txt", "", "x"), "error: old text is empty")
        self.assertEqual(
            self.tools.edit("dup.txt", "x", "y"),
            "error: old text found 2 times in dup.txt; include more context",
        )
        self.assertEqual((self.root / "a.txt").read_text(), "one\ntwo\nthree\n")
        self.assertEqual((self.root / "dup.txt").read_text(), "x\nx\n")
        self.assertTrue(self.tools.edit("nope.txt", "a", "b").startswith("error: not a file"))
        self.assertTrue(self.tools.edit("sub", "a", "b").startswith("error: not a file"))
        self.assertEqual(self.tools.edited, [])

    def test_writes_and_edits_share_one_cap(self):
        for i in range(builder.WRITE_CAP - 1):
            self.assertTrue(self.tools.write(f"w{i}.txt", "x\n").startswith("wrote"))
        self.assertTrue(self.tools.edit("a.txt", "one", "1").startswith("edited"))
        cap = f"error: cap reached ({builder.WRITE_CAP} writes and edits); report now"
        self.assertEqual(self.tools.write("late.txt", "x\n"), cap)
        self.assertEqual(self.tools.edit("a.txt", "1", "one"), cap)
        self.assertFalse((self.root / "late.txt").exists())
        self.assertEqual(len(self.tools.written) + len(self.tools.edited), builder.WRITE_CAP)

    # v0.3: check

    def test_check_records_each_run_and_returns_the_exit_and_the_tail(self):
        first = "F\n" + "=" * 10 + "\nFAIL: test_a\nFAILED (failures=1)\n"
        self.sandbox.results = [(1, first), (0, "..\nOK\n")]
        out = self.tools.check()
        self.assertTrue(out.startswith("exit 1\n"), out)
        self.assertIn("FAILED (failures=1)", out)
        self.assertEqual((self.run_dir / "check-1.log").read_text(), first)
        self.assertTrue(self.tools.check().startswith("exit 0\n"))
        self.assertEqual((self.run_dir / "check-2.log").read_text(), "..\nOK\n")
        self.assertEqual([c["exit"] for c in self.tools.checks], [1, 0])
        self.assertTrue(all(isinstance(c["seconds"], (int, float)) for c in self.tools.checks))
        self.assertEqual([c[2] for c in self.sandbox.calls], [1, 2])
        self.assertEqual(self.sandbox.calls[0][0], self.root)
        self.assertEqual(self.sandbox.calls[0][1], self.run_dir)

    def test_check_tail_is_capped_by_lines_and_bytes_but_the_log_is_whole(self):
        long = "".join(f"l{i}\n" for i in range(200))
        self.sandbox.results = [(0, long), (0, "y" * 20_000 + "\nOK\n")]
        out = self.tools.check()
        body = out.split("\n", 1)[1]
        self.assertEqual(body.count("\n") + (0 if body.endswith("\n") else 1), 60)
        self.assertTrue(body.startswith("l140\n"))
        self.assertEqual((self.run_dir / "check-1.log").read_text(), long)
        out = self.tools.check()
        self.assertLessEqual(len(out.encode()) - len("exit 0\n"), 8000)
        self.assertTrue(out.rstrip().endswith("OK"))

    def test_check_without_a_sandbox_or_with_a_broken_one_is_an_error_not_a_crash(self):
        self.assertTrue(Tools(self.root, self.run_dir).check().startswith("error: no sandbox"))

        class Broken:
            def run(self, checkout, run_dir, n):
                raise RuntimeError("docker build failed (exit 1); see image-build.log")

        out = Tools(self.root, self.run_dir, sandbox=Broken()).check()
        self.assertEqual(out, "error: docker build failed (exit 1); see image-build.log")
        self.assertFalse((self.run_dir / "check-1.log").exists())

    def test_check_cap_stops_calling_the_sandbox(self):
        self.sandbox.results = [(0, "OK\n")] * builder.CHECK_CAP
        for _ in range(builder.CHECK_CAP):
            self.assertTrue(self.tools.check().startswith("exit 0"))
        self.assertEqual(self.tools.check(), f"error: cap reached ({builder.CHECK_CAP} checks); report now")
        self.assertEqual(len(self.sandbox.calls), builder.CHECK_CAP)
        self.assertEqual(len(self.tools.checks), builder.CHECK_CAP)


class SandboxTest(unittest.TestCase):
    """Docker is a patched subprocess: the argv is the security boundary and is fixed by the plan."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkout = Path(self.tmp.name) / "checkout"
        self.checkout.mkdir()
        (self.checkout / "uv.lock").write_text("lock\n")
        (self.checkout / "check.Dockerfile").write_text("FROM x\n")
        self.run_dir = Path(self.tmp.name) / "20260915T170000Z-2"
        self.run_dir.mkdir()
        self.image = "factory-check:" + hashlib.sha256(b"lock\n" + b"FROM x\n").hexdigest()[:12]

    def done(self, code=0, out=b"", err=b""):
        return subprocess.CompletedProcess([], code, out, err)

    def test_image_name_hashes_the_lock_and_the_dockerfile(self):
        self.assertEqual(Sandbox.image(self.checkout), self.image)
        (self.checkout / "uv.lock").write_text("other\n")
        self.assertNotEqual(Sandbox.image(self.checkout), self.image)

    def test_run_uses_the_existing_image_with_the_plan_argv(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw))
            if argv[:3] == ["docker", "image", "inspect"]:
                return self.done(0)
            return self.done(1, b"..F\n", b"FAILED (failures=1)\n")

        with mock.patch.object(builder.subprocess, "run", fake_run):
            code, output = Sandbox.run(self.checkout, self.run_dir, 1)
        self.assertEqual(code, 1)
        self.assertEqual(output, "..F\nFAILED (failures=1)\n")
        self.assertEqual(calls[0][0], ["docker", "image", "inspect", self.image])
        argv, kw = calls[1]
        self.assertEqual(
            argv,
            [
                "docker", "run", "--rm", "--name", f"factory-check-{self.run_dir.name}-1",
                "--network", "none",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "-e", "HOME=/tmp",
                "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-v", f"{self.checkout}:/w:ro", "-w", "/w",
                "--memory", "1g", "--cpus", "2", "--pids-limit", "256",
                self.image, "python", "-P", "-m", "unittest", "discover", "-q",
            ],
        )
        self.assertEqual(kw.get("timeout"), builder.CHECK_TIMEOUT)
        self.assertEqual(len(calls), 2)  # no build when the image exists

    def test_run_builds_a_missing_image_once_and_records_the_build(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw))
            if argv[:3] == ["docker", "image", "inspect"]:
                return self.done(1, b"", b"No such image")
            if argv[:2] == ["docker", "build"]:
                return self.done(0, b"built\n", b"")
            return self.done(0, b"OK\n", b"")

        with mock.patch.object(builder.subprocess, "run", fake_run):
            code, output = Sandbox.run(self.checkout, self.run_dir, 1)
        self.assertEqual((code, output), (0, "OK\n"))
        build, kw = calls[1]
        self.assertEqual(build, ["docker", "build", "-f", str(self.checkout / "check.Dockerfile"), "-t", self.image, str(self.checkout)])
        self.assertEqual(kw.get("timeout"), builder.IMAGE_TIMEOUT)
        self.assertEqual((self.run_dir / "image-build.log").read_bytes(), b"built\n")

    def test_a_failed_build_is_a_runtime_error_naming_the_log(self):
        def fake_run(argv, **kw):
            if argv[:3] == ["docker", "image", "inspect"]:
                return self.done(1)
            return self.done(2, b"", b"boom\n")

        with mock.patch.object(builder.subprocess, "run", fake_run):
            with self.assertRaises(RuntimeError) as ctx:
                Sandbox.run(self.checkout, self.run_dir, 1)
        self.assertIn("docker build failed (exit 2)", str(ctx.exception))
        self.assertIn("image-build.log", str(ctx.exception))
        self.assertEqual((self.run_dir / "image-build.log").read_bytes(), b"boom\n")

    def test_a_timed_out_check_kills_the_container_and_reports_124(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw))
            if argv[:3] == ["docker", "image", "inspect"]:
                return self.done(0)
            if argv[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
            return self.done(0)

        with mock.patch.object(builder.subprocess, "run", fake_run):
            code, output = Sandbox.run(self.checkout, self.run_dir, 3)
        self.assertEqual(code, 124)
        self.assertIn(f"timeout after {builder.CHECK_TIMEOUT} s", output)
        kill, kw = calls[-1]
        self.assertEqual(kill, ["docker", "kill", f"factory-check-{self.run_dir.name}-3"])
        self.assertEqual(kw.get("timeout"), 30)


class RenderTest(unittest.TestCase):
    def test_five_headings_in_order_with_bullets(self):
        out = render(BuildReport(**REPORT))
        self.assertEqual(
            [line for line in out.splitlines() if line.startswith("## ")],
            ["## Changed", "## Did", "## Check", "## Failing", "## Unsure"],
        )
        self.assertIn("- f.py\n", out)
        self.assertIn("- green\n", out)
        self.assertIn("## Failing\n- (none)\n", out)

    def test_a_red_report_lists_the_failing_tests(self):
        out = render(BuildReport(changed=[], did=[], check="red", failing=["test_a", "test_b"], unsure=[]))
        self.assertEqual(out.count("- (none)"), 3)
        self.assertIn("## Check\n- red\n", out)
        self.assertIn("## Failing\n- test_a\n- test_b\n", out)


class RoleTest(unittest.TestCase):
    def test_the_role_is_the_plan_text(self):
        """seed: terms-checkout-and-tools. The role says checkout where it said world; the hash
        pins every other character."""
        self.assertEqual(hashlib.sha256(builder.ROLE.encode()).hexdigest()[:16], ROLE_SHA256)
        self.assertIn("a goal and a checkout: a directory with code and tests", builder.ROLE)
        self.assertIn("explore it with `list`, `read` and `search`,", builder.ROLE)  # seed: codebase-context
        self.assertNotIn("world", builder.ROLE)
        self.assertTrue(builder.ROLE.startswith("You are the builder."))
        self.assertIn("Work in this order:", builder.ROLE)
        self.assertIn("Rules: change only what the goal needs;", builder.ROLE)


class SlowTools(Tools):
    """Tools whose edit takes a moment and notes when it started and ended."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spans: list[tuple[float, float]] = []

    def edit(self, path: str, old: str, new: str) -> str:
        start = time.monotonic()
        time.sleep(0.05)  # a window in which a second call could overlap this one
        try:
            return super().edit(path, old, new)
        finally:
            self.spans.append((start, time.monotonic()))


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.root.mkdir()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        (self.root / "f.py").write_text("x = 1\n")

    def tools(self, results):
        self.sandbox = FakeSandbox(results)
        return Tools(self.root, self.run_dir, sandbox=self.sandbox)

    def test_tool_calls_in_one_response_run_one_at_a_time_in_order(self):
        """seed: tool-calls-one-at-a-time. Two edits of one file in one response and a third on
        the text the first wrote: each starts after the one before it ended, all three land."""
        (self.root / "g.py").write_text("a = 1\nb = 1\n")
        tools = SlowTools(self.root, self.run_dir, sandbox=FakeSandbox([]))
        model = scripted([
            call("edit", {"path": "g.py", "old": "a = 1", "new": "a = 2"}, "e1"),
            call("edit", {"path": "g.py", "old": "b = 1", "new": "b = 2"}, "e2"),
            call("edit", {"path": "g.py", "old": "a = 2", "new": "a = 3"}, "e3"),
        ])
        report, messages, usage, stopped, detail = run(build_agent(tools, model=model), "goal")
        self.assertEqual(stopped, "answer", detail)
        self.assertEqual(returns_of(messages)[:3], ["edited g.py (2 -> 2 lines)"] * 3)
        self.assertEqual((self.root / "g.py").read_text(), "a = 3\nb = 2\n")
        self.assertEqual(len(tools.spans), 3)
        for (_, end), (start, _) in zip(tools.spans, tools.spans[1:]):
            self.assertGreaterEqual(start, end, tools.spans)

    def test_edit_check_edit_check_then_the_report_ends_the_run(self):
        tools = self.tools([(1, "FAIL: test_x\n"), (0, "OK\n")])
        model = scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("check", {}, "c2")],
            [call("edit", {"path": "f.py", "old": "x = 2", "new": "x = 3"}, "c3")],
            [call("check", {}, "c4")],
            [call("final_result", REPORT, "c5")],
        )
        report, messages, usage, stopped, detail = run(build_agent(tools, model=model), "goal")
        self.assertEqual((stopped, detail), ("answer", ""))
        self.assertIsInstance(report, BuildReport)
        self.assertEqual(report.check, "green")
        self.assertEqual((self.root / "f.py").read_text(), "x = 3\n")
        self.assertEqual(tools.edited, ["f.py", "f.py"])
        self.assertEqual([c["exit"] for c in tools.checks], [1, 0])
        self.assertEqual(usage.tool_calls, 4)
        self.assertEqual(
            parts_of(messages)[:10],
            ["UserPromptPart"] + ["ToolCallPart", "ToolReturnPart"] * 4 + ["ToolCallPart"],
        )
        returns = returns_of(messages)
        self.assertTrue(returns[0].startswith("edited f.py (1 -> 1 lines)"))
        self.assertTrue(returns[1].startswith("exit 1\n"))
        self.assertTrue(returns[3].startswith("exit 0\n"))

    def test_the_write_cap_reaches_the_model_as_an_error(self):
        tools = self.tools([])
        turns = [[call("write", {"path": f"w{i}.txt", "content": "x\n"}, f"w{i}")] for i in range(builder.WRITE_CAP + 1)]
        report, messages, usage, stopped, detail = run(build_agent(tools, model=scripted(*turns)), "goal")
        self.assertEqual(stopped, "answer")
        self.assertEqual(len(tools.written), builder.WRITE_CAP)
        # the last tool return is the library's own for final_result; the cap error precedes it
        self.assertEqual(returns_of(messages)[-2], f"error: cap reached ({builder.WRITE_CAP} writes and edits); report now")

    def test_a_model_that_never_stops_hits_the_tool_call_cap(self):
        tools = self.tools([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            # two calls per turn, so the tool-call cap binds before the request cap does
            return ModelResponse(parts=[call("list", {"path": "."}, "c1"), call("list", {"path": "."}, "c2")])

        report, messages, usage, stopped, detail = run(build_agent(tools, model=FunctionModel(model)), "goal", tools.budget)
        self.assertEqual(stopped, "cap")
        self.assertIsNone(report)
        self.assertEqual(len(tools.listed), tools.budget)
        self.assertIn("tool_calls_limit", detail)

    def test_a_model_that_never_stops_one_call_at_a_time_is_still_bound_by_the_calls(self):
        tools = self.tools([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[call("list", {"path": "."}, "c")])

        report, messages, usage, stopped, detail = run(build_agent(tools, model=FunctionModel(model)), "goal", tools.budget)
        self.assertEqual(stopped, "cap")
        self.assertIsNone(report)
        self.assertEqual(len(tools.listed), tools.budget)
        self.assertIn("tool_calls_limit", detail)
        self.assertNotIn("request_limit", detail)  # the requests outlast the calls, always

    def test_a_plain_text_answer_is_retried_by_the_library(self):
        tools = self.tools([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(parts=[TextPart("done")])
            return ModelResponse(parts=[call("final_result", REPORT, "c")])

        report, messages, usage, stopped, detail = run(build_agent(tools, model=FunctionModel(model)), "goal")
        self.assertEqual(stopped, "answer")
        self.assertIsInstance(report, BuildReport)
        retries = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
        self.assertEqual(len(retries), 1)
        self.assertIn("Fix the errors and try again", retries[0].model_response())

    def test_a_provider_error_stops_the_run_without_a_report(self):
        tools = self.tools([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        report, messages, usage, stopped, detail = run(build_agent(tools, model=FunctionModel(model)), "goal")
        self.assertEqual(stopped, "error")
        self.assertIsNone(report)
        self.assertIn("boom", detail)


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.checkout = base / "checkout"
        self.checkout.mkdir()
        (self.checkout / "f.py").write_text("x = 1\n")
        git(self.checkout, "init", "-q")  # a checkout is a git checkout; a plain directory is refused
        git(self.checkout, "add", "f.py")
        git(self.checkout, "commit", "-q", "-m", "start")
        self.key = base / "key"
        self.key.write_text("DEEPSEEK_API_KEY=not-a-key\n")
        self.runs = base / "runs"  # the instance's store, which its configuration names
        self.instance = base / "instance.toml"
        self.instance.write_text(f'records = "{self.runs}"\n' + self.builder_role())
        self.enterContext(mock.patch.dict(os.environ, {"FACTORY_INSTANCE": str(self.instance)}))

    def builder_role(self, key: Path | None = None) -> str:
        """The role a build runs as, for a configuration to hold: its model and the file its key is
        read from. The key's place is the instance's, not the program's, since v0.15."""
        return f'\n[roles.builder]\nmodel = "deepseek-flash"\nkey = "{key or self.key}"\n'

    def records(self) -> list[Path]:
        """The store's records in stamp order; the store's own `.git` is none."""
        return sorted(p for p in self.runs.iterdir() if p.is_dir() and p.name != ".git") if self.runs.exists() else []

    def main(self, model, sandbox, checkout=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(checkout or self.checkout), "make x bigger"], model=model, sandbox=sandbox)
        run_dirs = self.records()
        return code, out.getvalue().splitlines(), (run_dirs[0] if run_dirs else None)

    def test_the_harness_names_what_else_to_hide_for_a_run(self):
        """seed: pass-rate-error. From the review: the evaluation set's `cases/` is the harness's
        convention, not what running the program leaves behind, so the harness hides it for the
        runs it starts through `hidden` and the builder's own hidden names stay five."""
        (self.checkout / "cases" / "alpha").mkdir(parents=True)
        (self.checkout / "cases" / "alpha" / "pass.txt").write_text("green\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "a case")
        peek = [call("list", {"path": "."}, "c0"), call("read", {"path": "cases/alpha/pass.txt"}, "c1")]

        def returns(run_dir: Path) -> list[str]:
            return [p["content"] for m in json.loads((run_dir / "messages.json").read_text()) for p in m["parts"] if p.get("part_kind") == "tool-return"]

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(peek), sandbox=FakeSandbox([]), hidden=("cases",))
        self.assertEqual(code, 0)
        hidden = returns(self.records()[0])
        self.assertNotIn("cases", names_in(hidden[0]))
        self.assertTrue(hidden[1].startswith("error: not part of the checkout"), hidden[1])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(peek), sandbox=FakeSandbox([]))
        self.assertEqual(code, 0)
        shown = returns(self.records()[1])
        self.assertIn("cases", names_in(shown[0]))
        self.assertEqual(shown[1], "1\tgreen")

    def test_a_green_build_in_a_git_checkout_leaves_the_full_record_and_the_diff(self):
        """seed: terms-checkout-and-tools. The numbers name the checkout and its head."""
        model = scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("write", {"path": "new.txt", "content": "hello\nworld\n"}, "c2")],
            [call("check", {}, "c3")],
            [call("final_result", REPORT, "c4")],
        )
        code, lines, run_dir = self.main(model, FakeSandbox([(0, "..\nOK\n")]))
        self.assertEqual(code, 0)
        self.assertEqual(
            sorted(p.name for p in run_dir.iterdir()),
            ["check-1.log", "diff.patch", "goal.txt", "messages.json", "numbers.json", "report.json", "response.md", "wire.jsonl.gz"],
        )
        patch = (run_dir / "diff.patch").read_text()
        self.assertIn("+x = 2", patch)
        self.assertIn("-x = 1", patch)
        self.assertIn("new.txt", patch)
        self.assertIn("+hello", patch)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["head"], git(self.checkout, "rev-parse", "HEAD").strip())
        self.assertEqual(numbers["stopped"], "answer")
        self.assertEqual(numbers["check"], "green")
        self.assertEqual((numbers["checks"], numbers["writes"], numbers["edits"]), (1, 1, 1))
        self.assertEqual(numbers["files_changed"], 2)  # f.py, new.txt
        self.assertGreaterEqual(numbers["insertions"], 3)
        self.assertEqual(numbers["deletions"], 1)
        self.assertEqual(numbers["checkout"], str(self.checkout.resolve()))
        self.assertGreaterEqual(numbers["check_seconds"], 0)
        self.assertEqual(numbers["role"], ROLE_SHA256)
        self.assertEqual(len(numbers["wrapper"]), 16)
        self.assertNotIn("detail", numbers)
        self.assertEqual(BuildReport(**json.loads((run_dir / "report.json").read_text())).check, "green")
        self.assertTrue((run_dir / "response.md").read_text().startswith("## Changed\n"))
        self.assertEqual(lines[0], str(run_dir))
        self.assertIn("check=green", lines[1])
        self.assertIn("stopped=answer", lines[1])
        self.assertEqual(len(lines), 2)
        self.assertNotIn("not-a-key", (run_dir / "messages.json").read_text())

    def test_the_plane_records_red_when_the_report_claims_green(self):
        model = scripted([call("check", {}, "c1")], [call("final_result", REPORT, "c2")])
        code, lines, run_dir = self.main(model, FakeSandbox([(1, "FAIL: test_x\n")]))
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["check"], "red")
        self.assertEqual(json.loads((run_dir / "report.json").read_text())["check"], "green")
        self.assertIn("check=red", lines[1])

    def test_a_directory_without_git_is_a_usage_error(self):
        """seed: terms-checkout-and-tools. The checkout must be a git checkout: a plain directory
        is refused with a usage error naming git, exit 2, before any run directory exists."""
        plain = Path(self.tmp.name) / "plain"
        plain.mkdir()
        (plain / "f.py").write_text("x = 1\n")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(plain), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("usage", err.getvalue())
        self.assertIn("git", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_a_checkout_without_a_commit_or_with_a_stray_dot_git_is_refused(self):
        """seed: terms-checkout-and-tools. A git checkout with no commit has nothing to pin a run
        to, and a directory whose .git is not git's is no checkout: both are usage errors that
        say which, before any run directory exists."""
        fresh = Path(self.tmp.name) / "fresh"
        fresh.mkdir()
        git(fresh, "init", "-q")
        stray = Path(self.tmp.name) / "stray"
        stray.mkdir()
        (stray / ".git").write_text("not a gitdir pointer\n")
        for checkout, words in ((fresh, "no commit"), (stray, "not a git checkout")):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, checkout)
            self.assertIn("usage", err.getvalue())
            self.assertIn(words, err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_a_checkout_is_the_root_of_its_own_repository(self):
        """seed: terms-checkout-and-tools. A subdirectory of a repository, with or without a stray
        .git directory of its own, is not a checkout: git would answer for the repository above.
        Nor is a directory the environment points elsewhere with GIT_DIR. A worktree is one."""
        deep = self.checkout / "deep"
        deep.mkdir()
        (deep / "g.py").write_text("y = 1\n")
        bogus = self.checkout / "bogus"
        (bogus / ".git").mkdir(parents=True)
        (bogus / "h.py").write_text("z = 1\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "more")
        stray = Path(self.tmp.name) / "stray"
        stray.mkdir()
        (stray / ".git").write_text("not a gitdir pointer\n")
        refused = [(deep, {}), (bogus, {}), (stray, {"GIT_DIR": str(self.checkout / ".git")}), (stray, {"GIT_DIR": str(self.checkout / ".git"), "GIT_WORK_TREE": str(stray)})]
        for checkout, env in refused:
            err = io.StringIO()
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, (checkout, env))
            self.assertIn("not a git checkout", err.getvalue(), (checkout, env))
        self.assertFalse(self.runs.exists())
        worktree = Path(self.tmp.name) / "wt"
        git(self.checkout, "worktree", "add", "-q", str(worktree))
        code, lines, run_dir = self.main(scripted(), FakeSandbox([]), checkout=worktree)
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["head"], git(worktree, "rev-parse", "HEAD").strip())
        self.assertEqual(numbers["checkout"], str(worktree.resolve()))

    def test_git_that_cannot_run_before_the_run_is_a_usage_error(self):
        """seed: terms-checkout-and-tools. No git on PATH is a usage error naming git, exit 2, no
        traceback and no run directory."""
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": str(Path(self.tmp.name) / "nobin")}), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("usage", err.getvalue())
        self.assertIn("git", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_the_patch_is_gits_own_whatever_the_environment_or_the_attributes_say(self):
        """seed: terms-checkout-and-tools. GIT_EXTERNAL_DIFF, a diff.external in the configuration
        and a textconv driver named by a .gitattributes the model could write cannot replace
        diff.patch with a program's output."""
        spy = Path(self.tmp.name) / "spy.sh"
        spy.write_text("#!/bin/sh\necho not a patch\n")
        spy.chmod(0o755)
        config = Path(self.tmp.name) / "gitconfig"
        config.write_text(f'[diff "spy"]\n\ttextconv = {spy}\n[diff]\n\texternal = {spy}\n')
        (self.checkout / ".gitattributes").write_text("f.py diff=spy\n")
        git(self.checkout, "add", ".gitattributes")
        git(self.checkout, "commit", "-q", "-m", "attributes")
        model = scripted([call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")], [call("final_result", REPORT, "c2")])
        with mock.patch.dict(os.environ, {"GIT_EXTERNAL_DIFF": str(spy), "GIT_CONFIG_GLOBAL": str(config)}):
            code, lines, run_dir = self.main(model, FakeSandbox([]))
        self.assertEqual(code, 0)
        patch = (run_dir / "diff.patch").read_text()
        self.assertIn("+x = 2", patch)
        self.assertNotIn("not a patch", patch)

    def test_git_that_fails_before_the_run_reports_its_own_words(self):
        """seed: terms-checkout-and-tools. A git that ran and failed before the run directory
        exists, whichever call it was, is a usage error carrying git's message, exit 2; a good
        checkout is not called "not a git checkout" for a failure of git's."""
        bad = Path(self.tmp.name) / "bad.gitconfig"
        bad.write_text("[core\nbroken\n")
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(bad)}), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("bad config", err.getvalue())
        self.assertNotIn("not a git checkout", err.getvalue())
        self.assertFalse(self.runs.exists())
        real = builder.git
        calls: list[str] = []

        def failing(checkout, *args, **kwargs):
            calls.append(args[0])
            if len(calls) == 2:
                raise subprocess.TimeoutExpired(["git", *args], 60)
            return real(checkout, *args, **kwargs)

        err = io.StringIO()
        with mock.patch.object(builder, "git", failing), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("timed out", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_a_run_may_leave_files_named_like_an_option_or_a_revision(self):
        """seed: terms-checkout-and-tools. A file the run names -x.txt or HEAD is a file to git's
        diff, not an option or a revision: the patch and the numbers still come."""
        model = scripted(
            [call("write", {"path": "-x.txt", "content": "dash\n"}, "c1")],
            [call("write", {"path": "HEAD", "content": "head\n"}, "c2")],
            [call("final_result", REPORT, "c3")],
        )
        code, lines, run_dir = self.main(model, FakeSandbox([]))
        self.assertEqual(code, 0)
        patch = (run_dir / "diff.patch").read_text()
        self.assertIn("+dash", patch)
        self.assertIn("+head", patch)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual((numbers["files_changed"], numbers["insertions"]), (2, 2))
        self.assertNotIn("diff", numbers)
        self.assertEqual(len(lines), 2)

    def test_gits_refusal_of_a_real_checkout_carries_gits_words(self):
        """seed: terms-checkout-and-tools. "not a git checkout" is said only when git itself says
        the directory is no repository; a checkout whose own .git/config is broken is refused
        with git's words about it, exit 2, the same way at whichever call it fails."""
        (self.checkout / ".git" / "config").write_text("[core\nbroken\n")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("bad config", err.getvalue())
        self.assertNotIn("not a git checkout", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_the_record_names_every_path_the_run_touched_whatever_git_lists(self):
        """seed: record-hardening. A committed .gitattributes with `* -diff` cannot turn the patch
        into a binary notice, and the numbers carry the written and edited paths in order."""
        (self.checkout / ".gitattributes").write_text("* -diff\n")
        git(self.checkout, "add", ".gitattributes")
        git(self.checkout, "commit", "-q", "-m", "attributes")
        model = scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("write", {"path": "new.txt", "content": "hello\n"}, "c2")],
            [call("write", {"path": "sub/deep.txt", "content": "deep\n"}, "c3")],
            [call("final_result", REPORT, "c4")],
        )
        code, lines, run_dir = self.main(model, FakeSandbox([]))
        self.assertEqual(code, 0)
        patch = (run_dir / "diff.patch").read_text()
        for text in ("+x = 2", "+hello", "+deep"):
            self.assertIn(text, patch)
        self.assertNotIn("Binary files", patch)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual((numbers["written"], numbers["edited"]), (["new.txt", "sub/deep.txt"], ["f.py"]))
        self.assertIn("written=", lines[1])
        self.assertIn("edited=", lines[1])
        self.assertEqual(len(lines), 2)

    def test_gits_first_line_alone_decides_not_a_checkout(self):
        """seed: record-hardening. A path that contains git's phrase does not make a good checkout
        no checkout, and git answers in English whatever the host's locale says."""
        self.assertEqual(builder.git_env().get("LC_ALL"), "C")
        phrase = Path(self.tmp.name) / "not a git repository"
        phrase.mkdir()
        (phrase / "bad.gitconfig").write_text("[core\nbroken\n")
        err = io.StringIO()
        env = {"GIT_CONFIG_GLOBAL": str(phrase / "bad.gitconfig"), "LC_ALL": "es_ES.UTF-8", "LANGUAGE": "es", "LANG": "es_ES.UTF-8"}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("bad config", err.getvalue())
        self.assertNotIn("not a git checkout", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_a_seed_path_is_a_goal(self):
        """seed: formal-input-output. A path ending in .md that names a note of the checkout with a
        ## Goal is read from the checkout: the model's goal is `seed: <name>` then the section's
        text, goal.txt says exactly that, and the numbers carry the seed's name."""
        note = "---\ntype: seed\n---\n\n## Evidence\n\nSome.\n\n## Goal\n\nMake x equal 2 in f.py.\nAnd nothing else.\n"
        (self.checkout / "docs" / "seeds").mkdir(parents=True)
        (self.checkout / "docs" / "seeds" / "make-x-two.md").write_text(note)
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "seed")
        model = scripted([call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")], [call("final_result", REPORT, "c2")])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(self.checkout), "docs/seeds/make-x-two.md"], model=model, sandbox=FakeSandbox([]))
        self.assertEqual(code, 0)
        run_dir = self.records()[0]
        goal = "seed: make-x-two\nMake x equal 2 in f.py.\nAnd nothing else."
        self.assertEqual((run_dir / "goal.txt").read_text(), goal + "\n")
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["seed"], "make-x-two")
        self.assertIn("seed=make-x-two", out.getvalue().splitlines()[1])
        messages = json.loads((run_dir / "messages.json").read_text())
        prompts = [p["content"] for m in messages for p in m["parts"] if p.get("part_kind") == "user-prompt"]
        self.assertEqual(prompts[0], goal)

    def test_a_seed_path_without_a_note_or_a_goal_is_a_usage_error_and_text_stays_text(self):
        """seed: formal-input-output. A .md path naming no file of the checkout, or a note without a
        ## Goal with text, is a usage error before any run directory; a goal that is text is text
        and the seed is null."""
        (self.checkout / "docs").mkdir()
        (self.checkout / "docs" / "nogoal.md").write_text("---\ntype: seed\n---\n\n## Idea\n\nMaybe.\n")
        (self.checkout / "docs" / "empty.md").write_text("---\ntype: seed\n---\n\n## Goal\n\n## Evidence\n\nNone.\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "notes")
        for goal in ("docs/missing.md", "docs/nogoal.md", "docs/empty.md"):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(self.checkout), goal], model=scripted(), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, goal)
            self.assertIn("usage", err.getvalue(), goal)
        self.assertFalse(self.runs.exists())
        code, lines, run_dir = self.main(scripted(), FakeSandbox([]))
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads((run_dir / "numbers.json").read_text())["seed"])
        self.assertEqual((run_dir / "goal.txt").read_text(), "make x bigger\n")

    def test_a_goal_is_a_seed_path_only_when_it_is_one_word_ending_in_md(self):
        """seed: formal-input-output. A sentence that ends in a file's name, or a goal of several
        lines, is text whatever it ends with; only one word ending in .md, no whitespace in it, is
        the path of a seed, and one that names no note of the commit is refused."""
        for text in ("add the run's files to README.md", "case: two_files\nsay how they run, as in README.md", "docs/seeds/one two.md"):
            self.assertEqual(builder.read_seed(self.checkout, text), (text, None), text)
        goal = "case: two_files\nsay how builder.py runs, as in README.md"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(self.checkout), goal], model=scripted([call("final_result", REPORT, "c1")]), sandbox=FakeSandbox([]))
        self.assertEqual(code, 0)
        run_dir = self.records()[0]
        self.assertEqual((run_dir / "goal.txt").read_text(), goal + "\n")
        self.assertIsNone(json.loads((run_dir / "numbers.json").read_text())["seed"])
        with self.assertRaises(ValueError):
            builder.read_seed(self.checkout, "docs/seeds/missing.md")

    def test_the_seed_is_read_from_the_checkouts_commit(self):
        """seed: formal-input-output. The note's text is the commit's, git show HEAD:<path>, so the
        record's head names exactly the goal the model was given: a working copy that differs does
        not count, and a note git ignores, which no commit holds, is no seed."""
        (self.checkout / "docs" / "seeds").mkdir(parents=True)
        note = self.checkout / "docs" / "seeds" / "pinned.md"
        note.write_text("---\ntype: seed\n---\n\n## Goal\n\nThe committed goal.\n")
        (self.checkout / ".gitignore").write_text("ghost/\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "seed")
        note.write_text("---\ntype: seed\n---\n\n## Goal\n\nThe edited goal.\n")
        self.assertEqual(builder.read_seed(self.checkout, "docs/seeds/pinned.md"), ("seed: pinned\nThe committed goal.", "pinned"))
        git(self.checkout, "checkout", "--", "docs/seeds/pinned.md")
        (self.checkout / "ghost").mkdir()
        (self.checkout / "ghost" / "haunt.md").write_text("## Goal\n\nBoo.\n")
        self.assertEqual(builder.dirty_paths(self.checkout), [])  # ignored, so the clean check does not see it
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "ghost/haunt.md"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("usage", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_seed_paths_outside_the_checkout_are_refused(self):
        """seed: formal-input-output. `..`, an absolute path outside the checkout and a link that
        points out of it name no seed: a usage error before any run directory."""
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("## Goal\n\nNot yours.\n")
        (self.checkout / "docs").mkdir()
        (self.checkout / "docs" / "link.md").symlink_to(outside)
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "link")
        for goal in ("../outside.md", str(outside), "docs/link.md"):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(self.checkout), goal], model=scripted(), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, goal)
            self.assertIn("usage", err.getvalue(), goal)
        self.assertFalse(self.runs.exists())

    def test_the_goal_section_is_read_as_markdown(self):
        """seed: formal-input-output. The section runs from its heading to the next heading of
        level one or two; a fenced code block inside it belongs to it whole, whatever its lines
        start with; %% comments are not the note's text, so a ## Goal inside one is not the
        heading and a comment inside the section is not the goal."""
        (self.checkout / "docs").mkdir()
        fenced = (
            "---\ntype: seed\n---\n\n## Evidence\n\nA note may show a heading:\n\n```\n## Goal\n\nnot the goal\n```\n\n"
            "## Goal\n\nWrite the note as:\n\n```md\n# Title\n\n## Changelog\n```\n\nThen stop.\n\n# Appendix\n\nNot the goal either.\n"
        )
        (self.checkout / "docs" / "fenced.md").write_text(fenced)
        commented = (
            "---\ntype: seed\n---\n%%\nthe template's rubric\n## Goal\n\nthe drafted goal, commented out\n%%\n\n"
            "## Goal\n\n%%not this%%\nThe real goal.\nIn two lines.\n\n### Details\n\nStill the goal.\n%%\nnor this\n%%\n\n## Idea\n\nNo.\n"
        )
        (self.checkout / "docs" / "commented.md").write_text(commented)
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "notes")
        self.assertEqual(
            builder.read_seed(self.checkout, "docs/fenced.md"),
            ("seed: fenced\nWrite the note as:\n\n```md\n# Title\n\n## Changelog\n```\n\nThen stop.", "fenced"),
        )
        self.assertEqual(
            builder.read_seed(self.checkout, "docs/commented.md"),
            ("seed: commented\nThe real goal.\nIn two lines.\n\n### Details\n\nStill the goal.", "commented"),
        )

    def test_code_keeps_its_comment_marks_and_an_open_comment_is_refused(self):
        """seed: formal-input-output. %% inside a code span or a fenced block is the note's text,
        not a comment mark, so a Goal that mentions `%%` in code keeps it whole; a %% comment left
        open to the end of the note is a usage error, not a comment."""
        (self.checkout / "docs").mkdir()
        body = "The `%%` marks are comments; write `%%` in code.\nSecond line.\n\n```\n%%\nnot a comment\n%%\n```\n\nLast line."
        (self.checkout / "docs" / "spans.md").write_text(f"---\ntype: seed\n---\n\n## Goal\n\n{body}\n\n## Idea\n\nNo.\n")
        (self.checkout / "docs" / "open.md").write_text("---\ntype: seed\n---\n\n## Goal\n\nThe goal %% and a comment never closed.\n\n## Idea\n\nNo.\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "notes")
        self.assertEqual(builder.read_seed(self.checkout, "docs/spans.md"), (f"seed: spans\n{body}", "spans"))
        with self.assertRaises(ValueError):
            builder.read_seed(self.checkout, "docs/open.md")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "docs/open.md"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("usage", err.getvalue())
        self.assertFalse(self.runs.exists())

    def test_fences_close_like_markdown_and_indented_lines_are_not_headings(self):
        """seed: formal-input-output. A fence closes only with the same character and at least as
        many marks as opened it, so a block of four backticks holds a block of three whole and a
        backtick block holds tildes; a line indented four spaces is no heading, whatever it starts
        with, so it stays in the section."""
        (self.checkout / "docs").mkdir()
        body = (
            "Show both:\n\n````md\n```\n## Changelog\n```\n````\n\n```\n~~~\n## Not a heading\n~~~\n```\n\n"
            "    ## Changelog\n    indented code\n\nEnd."
        )
        (self.checkout / "docs" / "fences.md").write_text(f"---\ntype: seed\n---\n\n## Goal\n\n{body}\n\n## Idea\n\nNo.\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "note")
        self.assertEqual(builder.read_seed(self.checkout, "docs/fences.md"), (f"seed: fences\n{body}", "fences"))

    def test_a_commit_entry_that_is_not_a_file_is_no_seed(self):
        """seed: formal-input-output. A symbolic link is refused whatever its target's name says,
        since git show gives a link's target as its bytes; so is a directory."""
        (self.checkout / "docs").mkdir()
        (self.checkout / "docs" / "link.md").symlink_to("x\n## Goal\n\nowned\n")
        (self.checkout / "docs" / "dir.md").mkdir()
        (self.checkout / "docs" / "dir.md" / "inner.md").write_text("## Goal\n\nowned\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "entries")
        for arg in ("docs/link.md", "docs/dir.md"):
            with self.assertRaises(ValueError, msg=arg):
                builder.read_seed(self.checkout, arg)

    def test_a_note_with_crlf_lines_reads_as_one_with_lf(self):
        """seed: formal-input-output. A note whose lines end in CRLF is the same note: its fences
        close, its headings end the section, and the goal's lines end in LF."""
        (self.checkout / "docs").mkdir()
        body = "Show:\n\n```\n# inside\n```\n\nEnd."
        lf = f"---\ntype: seed\n---\n\n## Goal\n\n{body}\n\n## Idea\n\nNo.\n"
        (self.checkout / "docs" / "crlf.md").write_bytes(lf.replace("\n", "\r\n").encode())
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "note")
        self.assertEqual(builder.read_seed(self.checkout, "docs/crlf.md"), (f"seed: crlf\n{body}", "crlf"))

    def test_a_git_failure_reading_the_seed_is_a_usage_error(self):
        """seed: formal-input-output. A checkout without a commit, or an argument git reads as
        pathspec magic, is a usage error like any other refusal, exit 2 and no run directory, not
        a traceback."""
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        git(empty, "init", "-q")
        for checkout, goal in ((empty, "docs/x.md"), (self.checkout, ":!f.md"), (self.checkout, ":(icase)f.md")):
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(checkout), goal], model=scripted(), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, goal)
            self.assertIn("usage", err.getvalue(), goal)
        self.assertFalse(self.runs.exists())

    def test_the_section_keeps_its_first_lines_indentation_and_marks_in_indented_code(self):
        """seed: formal-input-output. Only blank lines are trimmed from the section's ends, so a
        first line indented four spaces keeps them and is no heading; %% on a line indented four
        spaces or more, an indented code block, is text like in a fence; the docstring of
        read_seed names the refusals."""
        (self.checkout / "docs").mkdir()
        body = "    ## Changelog\n    a = '%%'\n    b = '%%'\n\nThen stop."
        (self.checkout / "docs" / "indented.md").write_text(f"---\ntype: seed\n---\n\n## Goal\n\n{body}\n\n## Idea\n\nNo.\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "note")
        self.assertEqual(builder.read_seed(self.checkout, "docs/indented.md"), (f"seed: indented\n{body}", "indented"))
        for word in ("link", "%%", "commit"):
            self.assertIn(word, builder.read_seed.__doc__)

    def test_searches_are_counted(self):
        """seed: codebase-context. The numbers count the searches, in the line too."""
        model = scripted([call("search", {"pattern": "x = 1"}, "c1")], [call("final_result", REPORT, "c2")])
        code, lines, run_dir = self.main(model, FakeSandbox([]))
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["searches"], 1)
        self.assertIn("searches=1", lines[1])
        returns = [p["content"] for m in json.loads((run_dir / "messages.json").read_text()) for p in m["parts"] if p.get("part_kind") == "tool-return"]
        self.assertEqual(returns[0], "f.py:1:x = 1")

    def test_the_record_leaves_no_patch_when_the_run_left_nothing_and_the_text_says_so(self):
        """seed: terms-checkout-and-tools. record_diff writes diff.patch only when the run changed
        something, and the code's own text says so."""
        run_dir = Path(self.tmp.name) / "r"
        run_dir.mkdir()
        self.assertEqual(builder.record_diff(self.checkout, run_dir), {"files_changed": 0, "insertions": 0, "deletions": 0})
        self.assertFalse((run_dir / "diff.patch").exists())
        self.assertIn("diff.patch (what the run left in the checkout; absent when it left nothing)", builder.__doc__)
        self.assertIn("absent when the run left nothing", builder.record_diff.__doc__)
        self.assertIn("the six tools", builder.build_agent.__doc__)  # seed: codebase-context
        self.assertIn("not one of the tools", builder.git.__doc__)
        self.assertIn("reachable only through six tools", builder.__doc__)
        self.assertIn("wire.jsonl.gz", builder.__doc__)  # seed: records-outside-the-project
        self.assertNotIn("wire.jsonl (", builder.__doc__)  # the plain wire is no file of a record
        self.assertNotIn("runs/<utc-stamp>", builder.__doc__)
        self.assertIn("list, read, search, write, edit and check", builder.__doc__)
        self.assertNotIn("five", builder.__doc__)
        self.assertNotIn("Factory v0.3", builder.__doc__)

    def test_a_provider_error_is_recorded_and_returns_one(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        code, lines, run_dir = self.main(FunctionModel(model), FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()), ["goal.txt", "messages.json", "numbers.json", "wire.jsonl.gz"])
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "error")
        self.assertIn("boom", numbers["detail"])
        self.assertNotIn("detail=", lines[1])

    def test_the_head_is_recorded_for_a_git_checkout(self):
        """seed: world-pinned-to-commit; seed: terms-checkout-and-tools. A run is comparable only
        if the checkout it ran on is a known commit: numbers.json carries the checkout's HEAD as
        head, and the numbers line says checkout= and head=."""
        code, lines, run_dir = self.main(scripted(), FakeSandbox([]))
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["head"], git(self.checkout, "rev-parse", "HEAD").strip())
        self.assertRegex(numbers["head"], r"^[0-9a-f]{40}$")
        self.assertIn(f" head={numbers['head']}", lines[1])
        self.assertIn(f"checkout={self.checkout.resolve()}", lines[1])
        self.assertNotIn("world", lines[1])
        self.assertNotIn("world", numbers)
        self.assertNotIn("world_head", numbers)

    def test_a_dirty_checkout_is_refused_before_any_record_exists(self):
        """seed: world-pinned-to-commit. Uncommitted or untracked changes in a git checkout are a
        usage error naming the dirty paths, exit 2, no run directory and no model call: the
        tests must be committed before a build."""
        (self.checkout / "f.py").write_text("x = 2\n")  # modified, tracked
        (self.checkout / "stray.txt").write_text("stray\n")  # untracked
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "goal"], model=scripted(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 2)
        self.assertIn("usage", err.getvalue())
        self.assertIn("f.py", err.getvalue())
        self.assertIn("stray.txt", err.getvalue())
        self.assertFalse(self.runs.exists())

    def store(self, *args: str) -> str:
        return git(self.runs, *args)

    def test_a_record_is_committed_to_the_instance_s_store_with_its_wire_compressed(self):
        """seed: records-outside-the-project. seed: compress-the-wire. The store is the directory the
        instance's configuration names, a git repository of its own made on the first record; when
        a run ends its record is committed there, the one record and nothing else, the message the
        stamp, by the factory's own identity whatever the host has; the wire is compressed before
        the commit; and the first line printed is still the record's path."""
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        self.enterContext(mock.patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg")}))
        model = scripted([call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
                         [call("check", {}, "c2")], [call("final_result", REPORT, "c3")])  # fmt: skip
        self.assertFalse(self.runs.exists())
        code, lines, run_dir = self.main(model, FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0)
        self.assertEqual(Path(lines[0]), run_dir)
        self.assertEqual(run_dir.parent, self.runs)
        self.assertEqual(Path(self.store("rev-parse", "--show-toplevel").strip()), self.runs.resolve())
        names = sorted(p.name for p in run_dir.iterdir())
        self.assertIn("wire.jsonl.gz", names)
        self.assertNotIn("wire.jsonl", names)
        gzip.open(run_dir / "wire.jsonl.gz").read()  # a gzip file, whatever it holds
        self.assertEqual(self.store("log", "--format=%s|%an <%ae>").splitlines(), [f"{run_dir.name}|factory <factory@localhost>"])
        tracked = self.store("ls-tree", "-r", "--name-only", "HEAD").splitlines()
        self.assertEqual(sorted(tracked), [f"{run_dir.name}/{name}" for name in names])
        self.assertEqual(self.store("status", "--porcelain"), "")
        self.assertEqual(git(self.checkout, "status", "--porcelain").strip(), "M f.py")  # the project holds no record

        git(self.checkout, "checkout", "-q", "--", "f.py")
        (self.runs / "stray.txt").write_text("not a record\n")
        time.sleep(1.1)  # a stamp of its own
        code, _, _ = self.main(scripted([call("final_result", REPORT, "c1")]), FakeSandbox([]))
        self.assertEqual(code, 0)
        second = self.records()[-1]
        self.assertNotEqual(second, run_dir)
        self.assertEqual(self.store("log", "--format=%s").splitlines(), [second.name, run_dir.name])
        changed = self.store("show", "--format=", "--name-only", "HEAD").splitlines()
        self.assertTrue(changed and all(name.startswith(f"{second.name}/") for name in changed), changed)
        self.assertEqual(self.store("status", "--porcelain").strip(), "?? stray.txt")  # nothing else is committed

    def test_a_run_that_ends_in_an_error_is_committed_too(self):
        """seed: records-outside-the-project. Whatever ended the run, its record is the factory's log."""
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        code, _, run_dir = self.main(FunctionModel(model), FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertEqual(self.store("log", "--format=%s").splitlines(), [run_dir.name])
        self.assertEqual(self.store("status", "--porcelain"), "")

    def test_a_record_that_holds_the_key_s_value_is_not_committed(self):
        """seed: records-outside-the-project. Every file of the record is searched for the key's value
        before the commit: found, nothing of the record is committed, the run exits 1, stderr names
        the file and never the value, and the record stays on disk."""
        leak = dict(REPORT, did=["f.py: changed, and the key is not-a-key"])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "make x bigger"],
                                model=scripted([call("final_result", leak, "c1")]), sandbox=FakeSandbox([]))  # fmt: skip
        self.assertEqual(code, 1)
        (run_dir,) = self.records()
        self.assertIn("not-a-key", (run_dir / "report.json").read_text())
        self.assertNotIn("not-a-key", err.getvalue())
        self.assertNotIn("not-a-key", out.getvalue().splitlines()[0])
        self.assertTrue(any(name in err.getvalue() for name in ("report.json", "messages.json", "response.md")), err.getvalue())
        if (self.runs / ".git").exists():
            self.assertEqual(self.store("ls-files").strip(), "")

    def test_the_check_of_a_record_is_the_tree_the_model_leaves(self):
        """seed: the-check-on-the-final-tree. A record's check was the model's own last call, so a
        write after it was recorded green on a tree nobody tested. When the model returns, whatever
        ended the run, the builder runs the check once more on the tree as it is, unless nothing was
        written or edited since the last check: the check is numbered after the model's own and
        leaves its log beside them, `checks` counts it, `check` in the numbers is the last one run,
        and the seconds of every check are summed as before."""
        model = scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("check", {}, "c2")],
            [call("write", {"path": "after.txt", "content": "written after the check\n"}, "c3")],
            [call("final_result", REPORT, "c4")],
        )
        sandbox = FakeSandbox([(0, "OK\n"), (1, "FAILED on the tree left\n")])
        code, lines, run_dir = self.main(model, sandbox)
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual((numbers["checks"], numbers["check"]), (2, "red"))
        self.assertEqual([n for _, _, n in sandbox.calls], [1, 2])  # numbered after the model's own
        self.assertIn("FAILED on the tree left", (run_dir / "check-2.log").read_text())
        self.assertEqual(sandbox.results, [])
        self.assertGreaterEqual(numbers["check_seconds"], 0)

    def test_nothing_written_since_the_last_check_is_checked_no_further(self):
        """seed: the-check-on-the-final-tree. The check the model ran is the tree it left when nothing
        was written or edited after it, a write a wall refused among them, so the builder adds no
        check of its own and the record is as it was."""
        model = scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("check", {}, "c2")],
            [call("write", {"path": "runs/sneak.txt", "content": "refused by a wall\n"}, "c3")],
            [call("final_result", REPORT, "c4")],
        )
        sandbox = FakeSandbox([(0, "OK\n")])
        code, lines, run_dir = self.main(model, sandbox)
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual((numbers["checks"], numbers["check"], numbers["writes"]), (1, "green", 0))
        self.assertEqual([n for _, _, n in sandbox.calls], [1])
        self.assertFalse((run_dir / "check-2.log").exists())

    def test_a_run_that_never_checked_is_checked_once_when_it_changed_the_checkout(self):
        """seed: the-check-on-the-final-tree. A run that changed the checkout and never checked it is
        recorded on the tree it left, one check of the builder's."""
        model = scripted([call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
                         [call("final_result", REPORT, "c2")])  # fmt: skip
        sandbox = FakeSandbox([(1, "FAILED\n")])
        code, lines, run_dir = self.main(model, sandbox)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual((numbers["checks"], numbers["check"]), (1, "red"))
        self.assertEqual([n for _, _, n in sandbox.calls], [1])
        self.assertTrue((run_dir / "check-1.log").is_file())

    def test_a_run_that_changed_nothing_is_not_checked_at_all(self):
        """seed: the-check-on-the-final-tree. A run that wrote and edited nothing leaves the tree its
        checkout came with, so no check is run for it and its `check` is `none` as before."""
        nothing = FakeSandbox([])
        code, lines, run_dir = self.main(scripted([call("final_result", REPORT, "c1")]), nothing)
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual((numbers["checks"], numbers["check"], numbers["files_changed"]), (0, "none", 0))
        self.assertEqual(nothing.calls, [])
        self.assertFalse((run_dir / "check-1.log").exists())

    def test_a_capped_run_is_checked_on_the_tree_it_left(self):
        """seed: the-check-on-the-final-tree. Whatever ended the run: a run capped after writing is
        recorded on the tree it left, so the set reads a cap by the tree and not by the model's
        last word."""
        def checks_then_writes_forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            done = sum(1 for m in messages if isinstance(m, ModelResponse))
            if done == 0:
                return ModelResponse(parts=[call("check", {}, "c0")])
            return ModelResponse(parts=[call("write", {"path": f"after{done}.txt",
                                                       "content": "written after the check\n"}, f"c{done}")])

        with mock.patch.object(builder, "CALLS_CEILING", 2):
            sandbox = FakeSandbox([(0, "OK\n"), (1, "FAILED on the tree left\n")])
            code, lines, run_dir = self.main(FunctionModel(checks_then_writes_forever), sandbox)
        self.assertEqual(code, 1)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "cap")
        self.assertEqual((numbers["checks"], numbers["check"]), (2, "red"))
        self.assertIn("FAILED on the tree left", (run_dir / "check-2.log").read_text())

    def test_the_host_s_git_configuration_changes_no_record(self):
        """seed: records-outside-the-project. From the review: the store's git read no configuration of
        the host's while the builder's own git read all of it, so a global ignore rule kept a file
        the model wrote out of the record's diff and out of `files_changed` while the commit a
        build pushes held it. Every git the factory runs reads neither the system's configuration
        nor the global one, so what a record says of a run is the same whatever the host ignores."""
        home = Path(self.tmp.name) / "home"
        home.mkdir(exist_ok=True)
        (home / "ignore").write_text("*.log\n")
        (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {home / 'ignore'}\n")
        self.enterContext(mock.patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg")}))
        model = scripted(
            [call("write", {"path": "notes.log", "content": "the model's own note\n"}, "c1")],
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c2")],
            [call("check", {}, "c3")],
            [call("final_result", REPORT, "c4")],
        )
        code, lines, run_dir = self.main(model, FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0)
        patch = (run_dir / "diff.patch").read_text()
        self.assertIn("notes.log", patch)
        self.assertIn("f.py", patch)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["files_changed"], 2)
        self.assertEqual(numbers["written"], ["notes.log"])

    def test_the_final_check_is_not_bound_by_the_model_s_cap(self):
        """seed: the-check-on-the-final-tree. The cap of eight checks binds the model's own: a run that
        spent them all and then wrote is still recorded on the tree it left, a ninth check of the
        builder's numbered after the model's and logged beside them."""
        tools = Tools(self.checkout, self.runs / "record", sandbox=FakeSandbox([(0, "OK\n")] * 9))
        (self.runs / "record").mkdir(parents=True)
        for n in range(builder.CHECK_CAP):
            self.assertTrue(tools.check().startswith("exit 0"), n)
        self.assertIn("cap reached", tools.check())
        self.assertEqual(len(tools.checks), builder.CHECK_CAP)
        tools.write("after.txt", "written after the model's last check\n")
        tools.check_final()
        self.assertEqual(len(tools.checks), builder.CHECK_CAP + 1)
        self.assertTrue((self.runs / "record" / f"check-{builder.CHECK_CAP + 1}.log").is_file())

    def test_the_store_s_git_is_the_factory_s_alone(self):
        """seed: records-outside-the-project. From the review: the host's git configuration does not
        reach the store and the store's own hooks do not run, and a record's files are added
        whatever an ignore file says, so the commit holds every file of the record: a global
        `core.excludesFile` naming the log and the wire, `commit.gpgsign`, a `pre-commit` that
        refuses and an ignore file of the store's own leave the commit as it is without them."""
        self.runs.mkdir()
        git(self.runs, "init", "-q")
        (self.runs / ".gitignore").write_text("*.log\n")
        git(self.runs, "add", "-A")
        git(self.runs, "commit", "-q", "-m", "the store's own ignore file")
        hooks = self.runs / ".git" / "hooks"  # after the store's own commit, which the hook would refuse
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-commit").write_text("#!/bin/sh\necho 'the hook says no' >&2\nexit 1\n")
        (hooks / "pre-commit").chmod(0o755)
        home = Path(self.tmp.name) / "home"
        home.mkdir(exist_ok=True)
        (home / "ignore").write_text("*.log\n*.gz\n")
        (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {home / 'ignore'}\n[commit]\n\tgpgsign = true\n")
        self.enterContext(mock.patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg")}))
        model = scripted([call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
                         [call("check", {}, "c2")], [call("final_result", REPORT, "c3")])  # fmt: skip
        code, lines, run_dir = self.main(model, FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0)
        tree = self.store("ls-tree", "-r", "--name-only", "HEAD").split()
        committed = sorted(name.split("/", 1)[1] for name in tree if name.startswith(f"{run_dir.name}/"))
        self.assertEqual(committed, sorted(p.name for p in run_dir.iterdir()))  # every file of the record
        self.assertIn(".gitignore", tree)  # and the store's own state as it was
        self.assertIn("check-1.log", committed)
        self.assertIn("wire.jsonl.gz", committed)
        self.assertEqual(self.store("diff", "--cached", "--name-only"), "")

    def test_a_commit_the_store_refuses_is_reported_and_the_record_stays(self):
        """seed: records-outside-the-project. From the review: a store that cannot take the record, a
        lock left behind or a ref git cannot write, is a run reported and not a traceback: the
        record's path is the first line printed and the numbers line follows, one line on stderr
        names the record and git's own words, the run exits 1, the record stays on disk with its
        wire compressed, and the store is left as the run found it, nothing of the record staged."""
        self.runs.mkdir()
        git(self.runs, "init", "-q")
        (self.runs / ".git" / "index.lock").write_text("")
        model = scripted([call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
                         [call("check", {}, "c2")], [call("final_result", REPORT, "c3")])  # fmt: skip
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "make x bigger"], model=model,
                                sandbox=FakeSandbox([(0, "OK\n")]))  # fmt: skip
        self.assertEqual(code, 1)
        lines = out.getvalue().splitlines()
        locked = self.records()[-1]
        self.assertEqual(Path(lines[0]), locked)
        self.assertIn("cost_usd=", lines[1])
        self.assertEqual(len(err.getvalue().splitlines()), 1, err.getvalue())
        self.assertIn(locked.name, err.getvalue())
        self.assertIn("index.lock", err.getvalue())  # git's own words
        self.assertTrue((locked / "wire.jsonl.gz").is_file())
        self.assertEqual(self.store("diff", "--cached", "--name-only"), "")

        (self.runs / ".git" / "index.lock").unlink()
        (self.runs / ".git" / "refs" / "heads").chmod(0o500)
        self.addCleanup((self.runs / ".git" / "refs" / "heads").chmod, 0o700)
        git(self.checkout, "checkout", "-q", "--", "f.py")
        time.sleep(1.1)  # a stamp of its own
        code, lines, unwritable = self.main(model_again := scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("check", {}, "c2")], [call("final_result", REPORT, "c3")]), FakeSandbox([(0, "OK\n")]))  # fmt: skip
        self.assertEqual(code, 1)
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.store("diff", "--cached", "--name-only"), "")  # the record is not left staged
        self.assertEqual(self.store("for-each-ref", "--format=%(refname)").strip(), "")  # nothing committed

    def test_a_run_without_a_store_is_a_usage_error(self):
        """seed: records-outside-the-project. The store is the instance's and no constant of the
        program: a configuration that is missing, is not TOML, has no `records`, names a path that
        is not absolute, or names a store inside the checkout or holding it, is a usage error that
        names the configuration's file, exit 2, before the key is read, a model called or anything
        made; with no `FACTORY_INSTANCE` the file is `.config/factory/instance.toml` under the home
        of whoever runs it, read when the run starts."""
        self.assertFalse(hasattr(builder, "RUNS"))
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[call("final_result", REPORT, "c1")])

        def refused(text: str | None) -> str:
            if text is None:
                self.instance.unlink(missing_ok=True)
            else:
                self.instance.write_text(text)
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(self.checkout), "make x bigger"], model=FunctionModel(model), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, (text, err.getvalue()))
            self.assertIn(str(self.instance), err.getvalue(), text)
            self.assertEqual(called, [], text)
            self.assertFalse(self.runs.exists(), text)
            return err.getvalue()

        refused(None)
        refused("records = \n")
        self.assertIn("records", refused('other = "x"\n'))
        self.assertIn("records", refused('records = "runs"\n'))
        self.assertIn("records", refused("records = 7\n"))
        inside = self.checkout / "records"
        self.assertIn("checkout", refused(f'records = "{inside}"\n'))
        self.assertFalse(inside.exists())
        self.assertIn("checkout", refused(f'records = "{self.checkout.parent}"\n'))
        self.assertFalse((self.checkout.parent / ".git").exists())

        home = Path(self.tmp.name) / "home"
        (home / ".config" / "factory").mkdir(parents=True)
        (home / ".config" / "factory" / "instance.toml").write_text(f'records = "{self.runs}"\n')
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            del os.environ["FACTORY_INSTANCE"]
            code, lines, run_dir = self.main(scripted([call("final_result", REPORT, "c1")]), FakeSandbox([]))
        self.assertEqual(code, 0)
        self.assertEqual(run_dir.parent, self.runs)

    def test_the_search_for_the_key_does_not_fail_open(self):
        """seed: records-outside-the-project. From the review: the search skips what it cannot read and
        commits the record anyway, so a file it cannot open, a `.gz` that ends before its stream
        does, and a directory it will not walk into, a link, all pass the wall. Nothing the search
        cannot read through is committed: the record is refused as one holding the key is, its path
        and the reason on stderr and never the value, exit 1. A `.gz` that is not gzip at all is
        searched as the bytes it is, whatever the case of its name."""
        record = self.runs / "20260918T000000Z"
        record.mkdir(parents=True)
        (record / "numbers.json").write_text("{}\n")
        unreadable = record / "unreadable.log"
        unreadable.write_text("nothing of the key here\n")
        unreadable.chmod(0o000)
        self.addCleanup(unreadable.chmod, 0o644)
        with self.assertRaises(builder.LeakedKey) as refused:
            builder.commit_record(self.runs, record, key="not-a-key")
        self.assertIn("unreadable.log", str(refused.exception))
        self.assertNotIn("not-a-key", str(refused.exception))
        unreadable.chmod(0o644)

        whole = gzip.compress(b'{"body": "and the key is not-a-key"}\n')
        (record / "wire.jsonl.gz").write_bytes(whole[: len(whole) - 4])
        with self.assertRaises(builder.LeakedKey) as truncated:
            builder.commit_record(self.runs, record, key="not-a-key")
        self.assertIn("wire.jsonl.gz", str(truncated.exception))
        (record / "wire.jsonl.gz").write_bytes(whole)
        with self.assertRaises(builder.LeakedKey) as read_through:
            builder.commit_record(self.runs, record, key="not-a-key")
        self.assertIn("wire.jsonl.gz", str(read_through.exception))  # the compressed wire read through
        (record / "wire.jsonl.gz").write_bytes(gzip.compress(b"nothing of it here\n"))

        away = Path(self.tmp.name) / "away"
        away.mkdir()
        (away / "secret.txt").write_text("the key is not-a-key\n")
        os.symlink(away, record / "linked")
        with self.assertRaises(builder.LeakedKey) as linked:
            builder.commit_record(self.runs, record, key="not-a-key")
        self.assertIn("linked", str(linked.exception))
        (record / "linked").unlink()

        (record / "notes.GZ").write_bytes(b"not gzip at all, and the key is not-a-key\n")
        with self.assertRaises(builder.LeakedKey) as capital:
            builder.commit_record(self.runs, record, key="not-a-key")
        self.assertIn("notes.GZ", str(capital.exception))  # searched as the bytes it is
        (record / "notes.GZ").unlink()

        builder.commit_record(self.runs, record, key="not-a-key")  # nothing left it cannot read
        self.assertEqual(self.store("log", "--format=%s").splitlines(), ["20260918T000000Z"])

    def test_a_record_the_search_cannot_read_through_is_a_reported_run(self):
        """seed: records-outside-the-project. The same wall in a run: the record's path is the first
        line, the numbers line follows, one line on stderr names the file and never the key, the
        run exits 1 and nothing is committed."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = builder.main(["builder.py", str(self.checkout), "make x bigger"],
                                model=scripted([call("final_result", REPORT, "c1")]), sandbox=FakeSandbox([]))  # fmt: skip
        self.assertEqual(code, 0)
        (record,) = self.records()
        unreadable = record / "check-none.log"
        unreadable.write_text("the check that never ran\n")
        unreadable.chmod(0o000)
        self.addCleanup(unreadable.chmod, 0o644)
        with self.assertRaises(builder.LeakedKey):
            builder.commit_record(self.runs, record, key="not-a-key")

    def test_a_configuration_a_run_cannot_use_is_a_usage_error_before_anything(self):
        """seed: records-outside-the-project. From the review: three configurations the run reads as
        usable and then falls over on, each now refused in its own words, exit 2, with no model
        called and nothing made. `FACTORY_INSTANCE` set and empty names no file, and the home's
        configuration is not read in its place, so only an unset variable falls back; a
        configuration whose bytes are not UTF-8 is not TOML and its refusal names the file: both
        are read before the key, so both are refused with no key file at all. A `records` that
        cannot hold a record, a plain file or a path the run cannot make, is refused once the key
        is a key, naming the configuration's file and the store's path."""
        home = Path(self.tmp.name) / "home"
        (home / ".config" / "factory").mkdir(parents=True, exist_ok=True)
        elsewhere = Path(self.tmp.name) / "elsewhere"
        (home / ".config" / "factory" / "instance.toml").write_text(f'records = "{elsewhere}"\n')
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[call("final_result", REPORT, "c1")])

        def refused(**environ) -> str:
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err), \
                    mock.patch.dict(os.environ, {"HOME": str(home), **environ}):  # fmt: skip
                code = builder.main(["builder.py", str(self.checkout), "make x bigger"],
                                    model=FunctionModel(model), sandbox=FakeSandbox([]))  # fmt: skip
            self.assertEqual(code, 2, err.getvalue())
            self.assertEqual(called, [])
            self.assertFalse(self.runs.exists())
            self.assertFalse(elsewhere.exists())  # never the home's store
            return err.getvalue()

        empty = refused(FACTORY_INSTANCE="")
        self.assertIn("FACTORY_INSTANCE", empty)

        self.instance.write_bytes(b'records = "/tmp/\xff\xfe"\n')  # not TOML: refused before any key
        not_utf8 = refused()
        self.assertIn(str(self.instance), not_utf8)

        plain = Path(self.tmp.name) / "a-file"
        plain.write_text("not a store\n")
        self.instance.write_text(f'records = "{plain}"\n' + self.builder_role())
        file_store = refused()
        self.assertIn(str(self.instance), file_store)
        self.assertIn(str(plain), file_store)

        locked = Path(self.tmp.name) / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        self.addCleanup(locked.chmod, 0o700)
        self.instance.write_text(f'records = "{locked / "store"}"\n' + self.builder_role())
        cannot_make = refused()
        self.assertIn(str(self.instance), cannot_make)
        self.assertIn(str(locked / "store"), cannot_make)
        self.assertFalse((locked / "store").exists())
        self.assertEqual(len({empty, not_utf8, file_store, cannot_make}), 4)  # its own words for each fault

    def test_a_key_file_with_no_value_is_a_usage_error(self):
        """seed: records-outside-the-project. From the review: an empty key is a key no record can be
        searched for, and that search is the wall that keeps the key out of the store, so a key
        file that is empty or holds a name with nothing after it is a usage error naming the key's
        file, exit 2, with no model called and the store not made, and the search has no case for
        an empty key. A key of one character is a key: it appears in the record, and refusing to
        commit the record is the search working."""
        called = []

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            called.append(1)
            return ModelResponse(parts=[call("final_result", REPORT, "c1")])

        key = Path(self.tmp.name) / "key"
        for text in ("", "\n", "   \n", "DEEPSEEK_API_KEY=\n", "DEEPSEEK_API_KEY=''\n"):
            key.write_text(text)
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(self.checkout), "make x bigger"],
                                    model=FunctionModel(model), sandbox=FakeSandbox([]))  # fmt: skip
            self.assertEqual(code, 2, repr(text))
            self.assertIn(str(key), err.getvalue(), repr(text))
            self.assertEqual(called, [], repr(text))
            self.assertFalse(self.runs.exists(), repr(text))

        key.write_text("a\n")  # a key of one character is a key
        code, lines, run_dir = self.main(scripted([call("final_result", REPORT, "c1")]), FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertTrue(run_dir.is_dir())
        self.assertEqual(self.store("for-each-ref", "--format=%(refname)").strip(), "")

    def test_usage_errors_exit_two(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(builder.main(["builder.py"]), 2)
            self.assertEqual(builder.main(["builder.py", str(self.checkout)]), 2)
            self.assertEqual(builder.main(["builder.py", str(self.checkout / "nope"), "goal"]), 2)
            self.assertEqual(builder.main(["builder.py", str(self.checkout / "f.py"), "goal"]), 2)
        self.assertIn("usage", err.getvalue())
        self.assertFalse(self.runs.exists())


class WireTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "wire.jsonl"

    def test_the_wire_records_both_lines_with_the_key_redacted_and_json_bodies_as_json(self):
        def handler(request):
            if request.url.path == "/plain":
                return httpx2.Response(200, text="plain answer", headers={"set-cookie": "s=1"})
            return httpx2.Response(200, json={"ok": 1}, headers={"set-cookie": "s=1"})

        wire = builder.Wire(self.path, transport=httpx2.MockTransport(handler))

        async def go():
            await wire.client.post(
                "https://api.example/chat",
                json={"model": "deepseek-flash"},
                headers={"Authorization": "Bearer not-a-key"},
            )
            await wire.client.post("https://api.example/plain", content=b"not json")

        asyncio.run(go())
        lines = [json.loads(l) for l in self.path.read_text().splitlines()]
        self.assertEqual([m["dir"] for m in lines], ["request", "response", "request", "response"])
        # a body that is JSON is recorded as the parsed value, so the record reads without a
        # second json.loads; a body that is not JSON is recorded as the text it was
        self.assertEqual(lines[0]["body"], {"model": "deepseek-flash"})
        self.assertEqual(lines[1]["status"], 200)
        self.assertEqual(lines[1]["body"], {"ok": 1})
        self.assertEqual(lines[2]["body"], "not json")
        self.assertEqual(lines[3]["body"], "plain answer")
        self.assertEqual(wire.attempts, 2)
        self.assertNotIn("not-a-key", self.path.read_text())
        self.assertEqual(lines[0]["headers"]["authorization"], "<redacted>")
        self.assertEqual(lines[1]["headers"]["set-cookie"], "<redacted>")

    def test_the_request_the_library_sends_has_the_plan_shape(self):
        """Through the real model class and a mock transport: no temperature, tool_choice auto,
        the five functions plus final_result, the role as the system message."""
        def handler(request):
            completion = {
                "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "c1", "type": "function", "function": {
                        "name": "final_result", "arguments": json.dumps(REPORT)}}]}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            return httpx2.Response(200, json=completion)

        checkout = Path(self.tmp.name) / "checkout"
        checkout.mkdir()
        wire = builder.Wire(self.path, transport=httpx2.MockTransport(handler))
        tools = Tools(checkout, Path(self.tmp.name), sandbox=FakeSandbox([]))
        agent = build_agent(tools, key="not-a-key", http_client=wire.client)
        with mock.patch.object(models, "ALLOW_MODEL_REQUESTS", True):
            report, messages, usage, stopped, detail = run(agent, "goal")
        self.assertEqual(stopped, "answer")
        self.assertEqual(report.check, "green")
        request = next(json.loads(l) for l in self.path.read_text().splitlines())["body"]
        self.assertIsInstance(request, dict)  # the wire records a JSON body as JSON
        self.assertEqual(sorted(request), ["messages", "model", "stream", "tool_choice", "tools"])
        self.assertEqual(request["tool_choice"], "auto")
        self.assertNotIn("temperature", request)
        self.assertEqual([t["function"]["name"] for t in request["tools"]], ["list", "read", "search", "write", "edit", "check", "final_result"])  # seed: codebase-context
        self.assertEqual(request["messages"][0], {"role": "system", "content": builder.ROLE.rstrip("\n")})
        self.assertEqual(request["messages"][1], {"role": "user", "content": "goal"})
        self.assertNotIn("not-a-key", self.path.read_text())


class RepositoryTest(unittest.TestCase):
    """The repository the factory lives in, as its own suite sees it."""

    def test_the_run_records_are_tracked(self):
        """seed: commit-the-runs. The records are the baseline of every eval, so the ignore file
        no longer hides them from git; the builder's checkout hides them regardless (ToolsTest)."""
        ignored = (Path(builder.__file__).parent / ".gitignore").read_text().splitlines()
        self.assertNotIn("runs/", ignored)
        self.assertNotIn("runs", ignored)

if __name__ == "__main__":
    unittest.main()
