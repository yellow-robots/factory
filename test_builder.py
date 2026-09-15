"""The builder's acceptance tests, written from plans/v0.3.md before the code.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel or answered by a
mock transport, the sandbox is a fake that returns scripted check results, and docker is a
patched subprocess. The interface under test is the one the plan names.
"""

import asyncio
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
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
from builder import BuildReport, Plane, Sandbox, build_agent, render, run

models.ALLOW_MODEL_REQUESTS = False

REPORT = {
    "changed": ["f.py"],
    "did": ["f.py: changed x so the test passes"],
    "check": "green",
    "failing": [],
    "unsure": [],
}
ROLE_SHA256 = "3d4040934b16a225"  # plans/v0.3.md decision 10; changing the prompt is a version


class FakeSandbox:
    """Scripted check results, consumed in order; records every call."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def run(self, world, run_dir, n):
        self.calls.append((Path(world), Path(run_dir), n))
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


def git(world: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=world, capture_output=True, text=True, check=True,
    )
    return out.stdout


def names_in(listing: str) -> list[str]:
    return [line.split("\t")[2] for line in listing.splitlines() if "\t" in line]


class PlaneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "world"
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
        self.plane = Plane(self.root, self.run_dir, sandbox=self.sandbox)

    # carried over from v0.2

    def test_list_root_hides_the_record_and_shows_kinds(self):
        out = self.plane.list(".")
        self.assertIn("file\t14\ta.txt", out)
        self.assertIn("dir\t0\tsub", out)
        self.assertIn("link\t0\tescape", out)
        names = names_in(out)
        self.assertIn(".gitignore", names)
        for hidden in builder.HIDDEN:
            self.assertNotIn(hidden, names)

    def test_paths_cannot_leave_the_world(self):
        for bad in ("..", "../..", "/etc", "escape", "outside_dir/hostname", *(f"{h}/secret" for h in builder.HIDDEN)):
            self.assertTrue(self.plane.read(bad).startswith("error:"), bad)
        self.assertTrue(self.plane.list("..").startswith("error: outside the world"))
        self.assertTrue(self.plane.list(".claude").startswith("error: not part of the world"))
        self.assertTrue(self.plane.list(".git").startswith("error: not part of the world"))
        self.assertEqual(self.plane.read_paths, [])
        self.assertEqual(self.plane.listed, [])

    def test_read_numbers_lines_and_truncates_with_a_continuation(self):
        self.assertEqual(self.plane.read("a.txt"), "1\tone\n2\ttwo\n3\tthree")
        out = self.plane.read("sub/b.txt")
        self.assertTrue(out.startswith("1\tline 1\n"))
        self.assertIn(f"...\ttruncated; continue with start={builder.READ_LINES_CAP + 1}", out)
        out = self.plane.read("sub/b.txt", start=990)
        self.assertTrue(out.startswith("990\tline 990\n"))
        self.assertTrue(out.endswith("1000\tline 1000"))
        self.assertEqual(self.plane.lines_read, 3 + builder.READ_LINES_CAP + 11)

    def test_a_line_longer_than_the_byte_cap_is_cut_and_the_next_line_continues(self):
        (self.root / "wide.txt").write_text("x" * 40_000 + "\nshort\n")
        out = self.plane.read("wide.txt")
        self.assertTrue(out.startswith("1\t" + "x" * 100))
        self.assertIn(f"(line cut at {builder.READ_BYTES_CAP} bytes)", out)
        self.assertTrue(out.endswith("...\ttruncated; continue with start=2"))
        self.assertEqual(self.plane.read("wide.txt", start=2), "2\tshort")

    def test_wrong_kinds_missing_paths_and_symlink_loops_are_errors_not_crashes(self):
        os.symlink("loop", self.root / "loop")
        self.assertTrue(self.plane.list("a.txt").startswith("error: not a directory"))
        self.assertTrue(self.plane.read("sub").startswith("error: not a file"))
        self.assertTrue(self.plane.read("nope.txt").startswith("error: not a file"))
        self.assertTrue(self.plane.read("loop").startswith("error:"))
        self.assertTrue(self.plane.list("loop").startswith("error:"))

    def test_the_docstrings_state_the_caps(self):
        self.assertIn(str(builder.READ_LINES_CAP), Plane.read.__doc__)
        self.assertIn(str(builder.READ_BYTES_CAP), Plane.read.__doc__)
        self.assertIn(str(builder.CHECK_CAP), Plane.check.__doc__)

    # v0.3: write

    def test_write_creates_with_parents_and_overwrites(self):
        self.assertEqual(self.plane.write("new/dir/f.txt", "a\nb\n"), "wrote new/dir/f.txt (2 lines)")
        self.assertEqual((self.root / "new" / "dir" / "f.txt").read_text(), "a\nb\n")
        self.assertEqual(self.plane.write("new/dir/f.txt", "c\n"), "wrote new/dir/f.txt (1 lines)")
        self.assertEqual((self.root / "new" / "dir" / "f.txt").read_text(), "c\n")
        self.assertEqual(self.plane.written, ["new/dir/f.txt", "new/dir/f.txt"])

    def test_write_and_edit_refuse_outside_hidden_and_protected_paths(self):
        outside = ("../x.txt", "/etc/x", "escape", "outside_dir/x")
        hidden = tuple(f"{h}/x" for h in builder.HIDDEN) + (".git/hooks/pre-commit",)
        protected = ("test_x.py", "testfoo.py", "tests_x.py", "sub/test_y.py", "tests/a/b.py", "pyproject.toml", "uv.lock", "check.Dockerfile", "alias.py")
        for bad in outside + hidden + protected:
            self.assertTrue(self.plane.write(bad, "x\n").startswith("error:"), bad)
            self.assertTrue(self.plane.edit(bad, "keep", "x").startswith("error:"), bad)
        for p in protected:
            self.assertIn("protected", self.plane.write(p, "x\n"), p)
            self.assertEqual((self.root / p).read_text(), "keep\n", p)
        self.assertFalse((self.root / "runs" / "x").exists())
        self.assertFalse((self.root / ".git" / "hooks").exists())
        self.assertFalse(Path("/etc/x").exists())
        self.assertEqual(self.plane.written, [])
        self.assertEqual(self.plane.edited, [])

    def test_names_that_only_resemble_protected_ones_are_free(self):
        self.assertTrue(self.plane.write("contest.py", "x\n").startswith("wrote contest.py"))
        self.assertTrue(self.plane.write("attest.py", "x\n").startswith("wrote attest.py"))
        self.assertTrue(self.plane.write("sub/pyproject.toml", "x\n").startswith("wrote sub/pyproject.toml"))
        self.assertTrue(self.plane.edit("contest.py", "x", "y").startswith("edited contest.py"))

    # v0.3: edit

    def test_edit_replaces_exactly_one_occurrence(self):
        self.assertEqual(self.plane.edit("a.txt", "two", "2"), "edited a.txt (3 -> 3 lines)")
        self.assertEqual((self.root / "a.txt").read_text(), "one\n2\nthree\n")
        self.assertEqual(self.plane.edit("a.txt", "2\n", "2\n2b\n"), "edited a.txt (3 -> 4 lines)")
        self.assertEqual(self.plane.edited, ["a.txt", "a.txt"])

    def test_edit_errors_on_zero_empty_and_many_occurrences_without_touching_the_file(self):
        (self.root / "dup.txt").write_text("x\nx\n")
        self.assertEqual(self.plane.edit("a.txt", "nope", "x"), "error: old text not found in a.txt")
        self.assertEqual(self.plane.edit("a.txt", "", "x"), "error: old text is empty")
        self.assertEqual(
            self.plane.edit("dup.txt", "x", "y"),
            "error: old text found 2 times in dup.txt; include more context",
        )
        self.assertEqual((self.root / "a.txt").read_text(), "one\ntwo\nthree\n")
        self.assertEqual((self.root / "dup.txt").read_text(), "x\nx\n")
        self.assertTrue(self.plane.edit("nope.txt", "a", "b").startswith("error: not a file"))
        self.assertTrue(self.plane.edit("sub", "a", "b").startswith("error: not a file"))
        self.assertEqual(self.plane.edited, [])

    def test_writes_and_edits_share_one_cap(self):
        for i in range(builder.WRITE_CAP - 1):
            self.assertTrue(self.plane.write(f"w{i}.txt", "x\n").startswith("wrote"))
        self.assertTrue(self.plane.edit("a.txt", "one", "1").startswith("edited"))
        cap = f"error: cap reached ({builder.WRITE_CAP} writes and edits); report now"
        self.assertEqual(self.plane.write("late.txt", "x\n"), cap)
        self.assertEqual(self.plane.edit("a.txt", "1", "one"), cap)
        self.assertFalse((self.root / "late.txt").exists())
        self.assertEqual(len(self.plane.written) + len(self.plane.edited), builder.WRITE_CAP)

    # v0.3: check

    def test_check_records_each_run_and_returns_the_exit_and_the_tail(self):
        first = "F\n" + "=" * 10 + "\nFAIL: test_a\nFAILED (failures=1)\n"
        self.sandbox.results = [(1, first), (0, "..\nOK\n")]
        out = self.plane.check()
        self.assertTrue(out.startswith("exit 1\n"), out)
        self.assertIn("FAILED (failures=1)", out)
        self.assertEqual((self.run_dir / "check-1.log").read_text(), first)
        self.assertTrue(self.plane.check().startswith("exit 0\n"))
        self.assertEqual((self.run_dir / "check-2.log").read_text(), "..\nOK\n")
        self.assertEqual([c["exit"] for c in self.plane.checks], [1, 0])
        self.assertTrue(all(isinstance(c["seconds"], (int, float)) for c in self.plane.checks))
        self.assertEqual([c[2] for c in self.sandbox.calls], [1, 2])
        self.assertEqual(self.sandbox.calls[0][0], self.root)
        self.assertEqual(self.sandbox.calls[0][1], self.run_dir)

    def test_check_tail_is_capped_by_lines_and_bytes_but_the_log_is_whole(self):
        long = "".join(f"l{i}\n" for i in range(200))
        self.sandbox.results = [(0, long), (0, "y" * 20_000 + "\nOK\n")]
        out = self.plane.check()
        body = out.split("\n", 1)[1]
        self.assertEqual(body.count("\n") + (0 if body.endswith("\n") else 1), 60)
        self.assertTrue(body.startswith("l140\n"))
        self.assertEqual((self.run_dir / "check-1.log").read_text(), long)
        out = self.plane.check()
        self.assertLessEqual(len(out.encode()) - len("exit 0\n"), 8000)
        self.assertTrue(out.rstrip().endswith("OK"))

    def test_check_without_a_sandbox_or_with_a_broken_one_is_an_error_not_a_crash(self):
        self.assertTrue(Plane(self.root, self.run_dir).check().startswith("error: no sandbox"))

        class Broken:
            def run(self, world, run_dir, n):
                raise RuntimeError("docker build failed (exit 1); see image-build.log")

        out = Plane(self.root, self.run_dir, sandbox=Broken()).check()
        self.assertEqual(out, "error: docker build failed (exit 1); see image-build.log")
        self.assertFalse((self.run_dir / "check-1.log").exists())

    def test_check_cap_stops_calling_the_sandbox(self):
        self.sandbox.results = [(0, "OK\n")] * builder.CHECK_CAP
        for _ in range(builder.CHECK_CAP):
            self.assertTrue(self.plane.check().startswith("exit 0"))
        self.assertEqual(self.plane.check(), f"error: cap reached ({builder.CHECK_CAP} checks); report now")
        self.assertEqual(len(self.sandbox.calls), builder.CHECK_CAP)
        self.assertEqual(len(self.plane.checks), builder.CHECK_CAP)


class SandboxTest(unittest.TestCase):
    """Docker is a patched subprocess: the argv is the security boundary and is fixed by the plan."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = Path(self.tmp.name) / "world"
        self.world.mkdir()
        (self.world / "uv.lock").write_text("lock\n")
        (self.world / "check.Dockerfile").write_text("FROM x\n")
        self.run_dir = Path(self.tmp.name) / "20260915T170000Z-2"
        self.run_dir.mkdir()
        self.image = "factory-check:" + hashlib.sha256(b"lock\n" + b"FROM x\n").hexdigest()[:12]

    def done(self, code=0, out=b"", err=b""):
        return subprocess.CompletedProcess([], code, out, err)

    def test_image_name_hashes_the_lock_and_the_dockerfile(self):
        self.assertEqual(Sandbox.image(self.world), self.image)
        (self.world / "uv.lock").write_text("other\n")
        self.assertNotEqual(Sandbox.image(self.world), self.image)

    def test_run_uses_the_existing_image_with_the_plan_argv(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw))
            if argv[:3] == ["docker", "image", "inspect"]:
                return self.done(0)
            return self.done(1, b"..F\n", b"FAILED (failures=1)\n")

        with mock.patch.object(builder.subprocess, "run", fake_run):
            code, output = Sandbox.run(self.world, self.run_dir, 1)
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
                "-v", f"{self.world}:/w:ro", "-w", "/w",
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
            code, output = Sandbox.run(self.world, self.run_dir, 1)
        self.assertEqual((code, output), (0, "OK\n"))
        build, kw = calls[1]
        self.assertEqual(build, ["docker", "build", "-f", str(self.world / "check.Dockerfile"), "-t", self.image, str(self.world)])
        self.assertEqual(kw.get("timeout"), builder.IMAGE_TIMEOUT)
        self.assertEqual((self.run_dir / "image-build.log").read_bytes(), b"built\n")

    def test_a_failed_build_is_a_runtime_error_naming_the_log(self):
        def fake_run(argv, **kw):
            if argv[:3] == ["docker", "image", "inspect"]:
                return self.done(1)
            return self.done(2, b"", b"boom\n")

        with mock.patch.object(builder.subprocess, "run", fake_run):
            with self.assertRaises(RuntimeError) as ctx:
                Sandbox.run(self.world, self.run_dir, 1)
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
            code, output = Sandbox.run(self.world, self.run_dir, 3)
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
        self.assertEqual(hashlib.sha256(builder.ROLE.encode()).hexdigest()[:16], ROLE_SHA256)
        self.assertTrue(builder.ROLE.startswith("You are the builder."))
        self.assertIn("Work in this order:", builder.ROLE)
        self.assertIn("Rules: change only what the goal needs;", builder.ROLE)


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "world"
        self.root.mkdir()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        (self.root / "f.py").write_text("x = 1\n")

    def plane(self, results):
        self.sandbox = FakeSandbox(results)
        return Plane(self.root, self.run_dir, sandbox=self.sandbox)

    def test_edit_check_edit_check_then_the_report_ends_the_run(self):
        plane = self.plane([(1, "FAIL: test_x\n"), (0, "OK\n")])
        model = scripted(
            [call("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"}, "c1")],
            [call("check", {}, "c2")],
            [call("edit", {"path": "f.py", "old": "x = 2", "new": "x = 3"}, "c3")],
            [call("check", {}, "c4")],
            [call("final_result", REPORT, "c5")],
        )
        report, messages, usage, stopped, detail = run(build_agent(plane, model=model), "goal")
        self.assertEqual((stopped, detail), ("answer", ""))
        self.assertIsInstance(report, BuildReport)
        self.assertEqual(report.check, "green")
        self.assertEqual((self.root / "f.py").read_text(), "x = 3\n")
        self.assertEqual(plane.edited, ["f.py", "f.py"])
        self.assertEqual([c["exit"] for c in plane.checks], [1, 0])
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
        plane = self.plane([])
        turns = [[call("write", {"path": f"w{i}.txt", "content": "x\n"}, f"w{i}")] for i in range(builder.WRITE_CAP + 1)]
        report, messages, usage, stopped, detail = run(build_agent(plane, model=scripted(*turns)), "goal")
        self.assertEqual(stopped, "answer")
        self.assertEqual(len(plane.written), builder.WRITE_CAP)
        # the last tool return is the library's own for final_result; the cap error precedes it
        self.assertEqual(returns_of(messages)[-2], f"error: cap reached ({builder.WRITE_CAP} writes and edits); report now")

    def test_a_model_that_never_stops_hits_the_tool_call_cap(self):
        plane = self.plane([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            # two calls per turn, so the tool-call cap binds before the request cap does
            return ModelResponse(parts=[call("list", {"path": "."}, "c1"), call("list", {"path": "."}, "c2")])

        report, messages, usage, stopped, detail = run(build_agent(plane, model=FunctionModel(model)), "goal")
        self.assertEqual(stopped, "cap")
        self.assertIsNone(report)
        self.assertEqual(len(plane.listed), builder.TOOL_CALLS_CAP)
        self.assertIn("tool_calls_limit", detail)

    def test_a_model_that_never_stops_one_call_at_a_time_hits_the_request_cap(self):
        plane = self.plane([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[call("list", {"path": "."}, "c")])

        report, messages, usage, stopped, detail = run(build_agent(plane, model=FunctionModel(model)), "goal")
        self.assertEqual(stopped, "cap")
        self.assertIsNone(report)
        self.assertEqual(len(plane.listed), builder.REQUEST_CAP)
        self.assertIn("request_limit", detail)

    def test_a_plain_text_answer_is_retried_by_the_library(self):
        plane = self.plane([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(parts=[TextPart("done")])
            return ModelResponse(parts=[call("final_result", REPORT, "c")])

        report, messages, usage, stopped, detail = run(build_agent(plane, model=FunctionModel(model)), "goal")
        self.assertEqual(stopped, "answer")
        self.assertIsInstance(report, BuildReport)
        retries = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
        self.assertEqual(len(retries), 1)
        self.assertIn("Fix the errors and try again", retries[0].model_response())

    def test_a_provider_error_stops_the_run_without_a_report(self):
        plane = self.plane([])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        report, messages, usage, stopped, detail = run(build_agent(plane, model=FunctionModel(model)), "goal")
        self.assertEqual(stopped, "error")
        self.assertIsNone(report)
        self.assertIn("boom", detail)


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.world = base / "world"
        self.world.mkdir()
        (self.world / "f.py").write_text("x = 1\n")
        (base / "key").write_text("DEEPSEEK_API_KEY=not-a-key\n")
        self.runs = base / "runs"
        self.enterContext(mock.patch.object(builder, "RUNS", self.runs))
        self.enterContext(mock.patch.object(builder, "KEY_FILE", base / "key"))

    def main(self, model, sandbox, world=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = builder.main(["builder.py", str(world or self.world), "make x bigger"], model=model, sandbox=sandbox)
        run_dirs = list(self.runs.iterdir()) if self.runs.exists() else []
        return code, out.getvalue().splitlines(), (run_dirs[0] if run_dirs else None)

    def test_a_green_build_in_a_git_world_leaves_the_full_record_and_the_diff(self):
        git(self.world, "init", "-q")
        git(self.world, "add", "f.py")
        git(self.world, "commit", "-q", "-m", "start")
        (self.world / "staged.txt").write_text("staged\n")
        git(self.world, "add", "staged.txt")
        os.symlink("nowhere", self.world / "dangling")
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
            ["check-1.log", "diff.patch", "goal.txt", "messages.json", "numbers.json", "report.json", "response.md", "wire.jsonl"],
        )
        patch = (run_dir / "diff.patch").read_text()
        self.assertIn("+x = 2", patch)
        self.assertIn("-x = 1", patch)
        self.assertIn("new.txt", patch)
        self.assertIn("+hello", patch)
        self.assertIn("+staged", patch)  # staged but uncommitted changes are part of what the run left
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "answer")
        self.assertEqual(numbers["check"], "green")
        self.assertEqual((numbers["checks"], numbers["writes"], numbers["edits"]), (1, 1, 1))
        self.assertEqual(numbers["files_changed"], 4)  # f.py, new.txt, staged.txt, dangling
        self.assertGreaterEqual(numbers["insertions"], 4)
        self.assertEqual(numbers["deletions"], 1)
        self.assertEqual(numbers["world"], str(self.world.resolve()))
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

    def test_a_world_without_git_records_that_and_no_patch(self):
        code, lines, run_dir = self.main(scripted(), FakeSandbox([]))
        self.assertEqual(code, 0)
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["diff"], "not a git checkout")
        self.assertEqual(numbers["check"], "none")
        self.assertFalse((run_dir / "diff.patch").exists())

    def test_a_provider_error_is_recorded_and_returns_one(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        code, lines, run_dir = self.main(FunctionModel(model), FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()), ["goal.txt", "messages.json", "numbers.json", "wire.jsonl"])
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "error")
        self.assertIn("boom", numbers["detail"])
        self.assertNotIn("detail=", lines[1])

    def test_usage_errors_exit_two(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(builder.main(["builder.py"]), 2)
            self.assertEqual(builder.main(["builder.py", str(self.world)]), 2)
            self.assertEqual(builder.main(["builder.py", str(self.world / "nope"), "goal"]), 2)
            self.assertEqual(builder.main(["builder.py", str(self.world / "f.py"), "goal"]), 2)
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

        world = Path(self.tmp.name) / "world"
        world.mkdir()
        wire = builder.Wire(self.path, transport=httpx2.MockTransport(handler))
        plane = Plane(world, Path(self.tmp.name), sandbox=FakeSandbox([]))
        agent = build_agent(plane, key="not-a-key", http_client=wire.client)
        with mock.patch.object(models, "ALLOW_MODEL_REQUESTS", True):
            report, messages, usage, stopped, detail = run(agent, "goal")
        self.assertEqual(stopped, "answer")
        self.assertEqual(report.check, "green")
        request = next(json.loads(l) for l in self.path.read_text().splitlines())["body"]
        self.assertIsInstance(request, dict)  # the wire records a JSON body as JSON
        self.assertEqual(sorted(request), ["messages", "model", "stream", "tool_choice", "tools"])
        self.assertEqual(request["tool_choice"], "auto")
        self.assertNotIn("temperature", request)
        self.assertEqual([t["function"]["name"] for t in request["tools"]], ["list", "read", "write", "edit", "check", "final_result"])
        self.assertEqual(request["messages"][0], {"role": "system", "content": builder.ROLE.rstrip("\n")})
        self.assertEqual(request["messages"][1], {"role": "user", "content": "goal"})
        self.assertNotIn("not-a-key", self.path.read_text())


if __name__ == "__main__":
    unittest.main()
