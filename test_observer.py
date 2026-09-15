"""The plane, the report and the loop, checked without a provider.  uv run python -m unittest -v"""

import asyncio
import contextlib
import io
import json
import os
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

import observer
from observer import Plane, Report, build_agent, render, run

models.ALLOW_MODEL_REQUESTS = False

REPORT_ARGS = {
    "looked_at": ["."],
    "found": ["f.txt holds one line"],
    "missing": [],
    "unsure": ["whether it matters"],
}


def parts_of(messages: list[ModelMessage]) -> list[str]:
    return [type(p).__name__ for m in messages for p in m.parts]


class PlaneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "a.txt").write_text("one\ntwo\nthree\n")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("".join(f"line {i}\n" for i in range(1, 1001)))
        for hidden in observer.HIDDEN:
            (self.root / hidden).mkdir()
            (self.root / hidden / "secret").write_text("the record\n")
        os.symlink("/etc/hostname", self.root / "escape")
        self.plane = Plane(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_root_hides_the_record_and_shows_kinds(self):
        out = self.plane.list(".")
        self.assertIn("file\t14\ta.txt", out)
        self.assertIn("dir\t0\tsub", out)
        self.assertIn("link\t0\tescape", out)
        for hidden in observer.HIDDEN:
            self.assertNotIn(hidden, out)

    def test_paths_cannot_leave_the_world(self):
        for bad in ("..", "../..", "/etc", "escape", "runs/secret", ".claude/secret", "__pycache__/secret"):
            self.assertTrue(self.plane.read(bad).startswith("error:"), bad)
        self.assertTrue(self.plane.list("..").startswith("error: outside the world"))
        self.assertTrue(self.plane.list(".claude").startswith("error: not part of the world"))
        self.assertEqual(self.plane.read_paths, [])
        self.assertEqual(self.plane.listed, [])

    def test_read_numbers_lines_and_truncates_with_a_continuation(self):
        out = self.plane.read("a.txt")
        self.assertEqual(out, "1\tone\n2\ttwo\n3\tthree")
        out = self.plane.read("sub/b.txt")
        self.assertTrue(out.startswith("1\tline 1\n"))
        self.assertIn(f"...\ttruncated; continue with start={observer.READ_LINES_CAP + 1}", out)
        out = self.plane.read("sub/b.txt", start=990)
        self.assertTrue(out.startswith("990\tline 990\n"))
        self.assertTrue(out.endswith("1000\tline 1000"))
        self.assertEqual(self.plane.lines_read, 3 + observer.READ_LINES_CAP + 11)

    def test_a_wrong_kind_or_a_missing_path_is_an_error_not_a_crash(self):
        self.assertTrue(self.plane.list("a.txt").startswith("error: not a directory"))
        self.assertTrue(self.plane.read("sub").startswith("error: not a file"))
        self.assertTrue(self.plane.read("nope.txt").startswith("error: not a file"))

    def test_a_symlink_loop_is_an_error_not_a_crash(self):
        os.symlink("loop", self.root / "loop")  # resolve() raises RuntimeError on this one
        self.assertTrue(self.plane.read("loop").startswith("error:"))
        self.assertTrue(self.plane.list("loop").startswith("error:"))

    def test_a_line_longer_than_the_byte_cap_is_cut_not_a_dead_end(self):
        (self.root / "wide.txt").write_text("x" * 40_000 + "\n")
        out = self.plane.read("wide.txt")
        self.assertTrue(out.startswith("1\t" + "x" * 100))
        self.assertIn(f"…(line cut at {observer.READ_BYTES_CAP} bytes)", out)
        self.assertNotIn("truncated", out)  # the old dead-end: start=1 for ever, nothing read
        self.assertEqual(self.plane.lines_read, 1)

    def test_a_cut_line_still_continues_at_the_next_line(self):
        (self.root / "wide.txt").write_text("x" * 40_000 + "\nshort\n")
        out = self.plane.read("wide.txt")
        self.assertIn("…(line cut at", out)
        self.assertTrue(out.endswith("...\ttruncated; continue with start=2"))
        self.assertEqual(self.plane.read("wide.txt", start=2), "2\tshort")

    def test_the_read_docstring_states_the_caps(self):
        self.assertIn(str(observer.READ_LINES_CAP), Plane.read.__doc__)
        self.assertIn(str(observer.READ_BYTES_CAP), Plane.read.__doc__)


class RenderTest(unittest.TestCase):
    def test_four_headings_in_order_with_bullets(self):
        out = render(Report(**REPORT_ARGS))
        self.assertEqual(
            [line for line in out.splitlines() if line.startswith("## ")],
            ["## Looked at", "## Found", "## Missing", "## Unsure"],
        )
        self.assertIn("- f.txt holds one line", out)
        self.assertIn("- whether it matters", out)

    def test_an_empty_section_says_none(self):
        out = render(Report(looked_at=[], found=[], missing=[], unsure=[]))
        self.assertEqual(out, "## Looked at\n- (none)\n\n## Found\n- (none)\n\n"
                              "## Missing\n- (none)\n\n## Unsure\n- (none)\n")


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "f.txt").write_text("hello\n")
        self.plane = Plane(self.root)

    def test_calls_are_executed_and_the_final_result_ends_the_run(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart("list", {"path": "."}, tool_call_id="c1"),
                        ToolCallPart("read", {"path": "f.txt"}, tool_call_id="c2"),
                    ]
                )
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT_ARGS, tool_call_id="c3")])

        agent = build_agent(self.plane, model=FunctionModel(model))
        report, messages, usage, stopped, detail = run(agent, "goal")
        self.assertEqual(stopped, "answer")
        self.assertEqual(detail, "")
        self.assertIsInstance(report, Report)
        self.assertEqual(report.found, REPORT_ARGS["found"])
        self.assertEqual(self.plane.listed, ["."])
        self.assertEqual(self.plane.read_paths, ["f.txt"])
        self.assertEqual(self.plane.lines_read, 1)
        self.assertEqual(usage.tool_calls, 2)  # the output tool is not one of ours
        self.assertEqual(usage.requests, 2)
        self.assertEqual(
            parts_of(messages)[:6],
            ["UserPromptPart", "ToolCallPart", "ToolCallPart", "ToolReturnPart", "ToolReturnPart", "ToolCallPart"],
        )
        returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        self.assertEqual([p.tool_name for p in returns][:2], ["list", "read"])
        self.assertEqual(returns[1].content, "1\thello")

    def test_a_model_that_never_stops_hits_the_tool_call_cap(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart("list", {"path": "."})])

        agent = build_agent(self.plane, model=FunctionModel(model))
        report, messages, usage, stopped, detail = run(agent, "goal")
        self.assertEqual(stopped, "cap")
        self.assertIsNone(report)
        self.assertEqual(len(self.plane.listed), observer.TOOL_CALLS_CAP)
        self.assertEqual(usage.tool_calls, observer.TOOL_CALLS_CAP)
        self.assertIn("tool_calls_limit", detail)
        self.assertEqual(parts_of(messages).count("ToolCallPart"), observer.TOOL_CALLS_CAP + 1)

    def test_a_plain_text_answer_is_retried_by_the_library(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(parts=[TextPart("## Looked at\n.")])
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT_ARGS)])

        agent = build_agent(self.plane, model=FunctionModel(model))
        report, messages, usage, stopped, detail = run(agent, "goal")
        self.assertEqual(stopped, "answer")
        self.assertIsInstance(report, Report)
        # 2.43.0 has no "plain text is not permitted" message: the text is tried as the report's
        # JSON and the failure comes back as the library's validation retry prompt.
        retries = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
        self.assertEqual(len(retries), 1)
        self.assertIn("Invalid JSON", retries[0].model_response())
        self.assertIn("Fix the errors and try again", retries[0].model_response())

    def test_a_provider_error_stops_the_run_without_a_report(self):
        # A connection or timeout failure arrives as a plain ModelAPIError, not a ModelHTTPError.
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        agent = build_agent(self.plane, model=FunctionModel(model))
        report, messages, usage, stopped, detail = run(agent, "goal")
        self.assertEqual(stopped, "error")
        self.assertIsNone(report)
        self.assertIn("boom", detail)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "f.txt").write_text("hello\n")
        (self.root / "key").write_text("DEEPSEEK_API_KEY=not-a-key\n")
        for name, value in (("WORLD", self.root), ("RUNS", self.root / "runs"), ("KEY_FILE", self.root / "key")):
            self.enterContext(mock.patch.object(observer, name, value))

    def drive(self, model) -> tuple[int, list[str], Path]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = observer.main(["observer.py", "what is here"], model=FunctionModel(model))
        return code, out.getvalue().splitlines(), next((self.root / "runs").iterdir())

    def test_main_writes_the_record_and_one_numbers_line(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart("final_result", REPORT_ARGS)])

        code, lines, run_dir = self.drive(model)
        self.assertEqual(code, 0)
        names = sorted(p.name for p in run_dir.iterdir())
        self.assertEqual(
            names,
            ["goal.txt", "messages.json", "numbers.json", "report.json", "response.md", "wire.jsonl"],
        )
        self.assertEqual((run_dir / "goal.txt").read_text(), "what is here\n")
        self.assertEqual(Report(**json.loads((run_dir / "report.json").read_text())).found, REPORT_ARGS["found"])
        self.assertTrue((run_dir / "response.md").read_text().startswith("## Looked at\n"))
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "answer")
        self.assertEqual(numbers["library"], observer.LIBRARY)
        self.assertEqual(numbers["cost_source"], "table")
        self.assertEqual(numbers["wire_attempts"], 0)
        self.assertNotIn("detail", numbers)
        self.assertEqual(lines[0], str(run_dir))
        self.assertIn("stopped=answer", lines[1])
        self.assertEqual(len(lines), 2)

    def test_main_records_a_provider_error_and_returns_one(self):
        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise ModelAPIError("deepseek-flash", "boom")

        code, lines, run_dir = self.drive(model)
        self.assertEqual(code, 1)
        self.assertEqual(
            sorted(p.name for p in run_dir.iterdir()),
            ["goal.txt", "messages.json", "numbers.json", "wire.jsonl"],
        )
        numbers = json.loads((run_dir / "numbers.json").read_text())
        self.assertEqual(numbers["stopped"], "error")
        self.assertIn("boom", numbers["detail"])
        self.assertEqual(len(lines), 2)  # the numbers line stays one line of k=v
        self.assertNotIn("detail=", lines[1])


class WireTest(unittest.TestCase):
    def test_the_wire_records_both_lines_with_the_key_redacted(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "wire.jsonl"
        wire = observer.Wire(path, transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"ok": 1})))

        async def post():
            return await wire.client.post(
                "https://api.deepseek.com/chat/completions",
                json={"model": "deepseek-flash"},
                headers={"Authorization": "Bearer not-a-key"},
            )

        self.assertEqual(asyncio.run(post()).status_code, 200)
        self.assertEqual(wire.attempts, 1)
        text = path.read_text()
        request, response = [json.loads(line) for line in text.splitlines()]
        self.assertEqual([request["dir"], response["dir"]], ["request", "response"])
        self.assertEqual(json.loads(request["body"]), {"model": "deepseek-flash"})
        self.assertIsNone(request["status"])
        self.assertEqual(response["status"], 200)
        self.assertEqual(json.loads(response["body"]), {"ok": 1})
        self.assertEqual(request["headers"]["authorization"], "<redacted>")
        self.assertIn("content-type", response["headers"])
        self.assertNotIn("not-a-key", text)
        self.assertIn("authorization", text)


if __name__ == "__main__":
    unittest.main()
