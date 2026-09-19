"""The budget a run is given and the landing at the end of it: caps-for-the-checkout-as-it-is.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel and the sandbox is a
fake. The fixtures of the builder's own suite are reused rather than copied.
"""

import contextlib
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import builder
import runs
from builder import Tools, build_agent, run
from test_builder import REPORT, FakeSandbox, call
from test_keys import KeysBase

models.ALLOW_MODEL_REQUESTS = False

LINES = 900
FILES = 40  # 3 reads a file at 300 lines a read, so 120 reads for one pass over the checkout
BUDGET = 104  # 120 * 55 per cent = 66 reads of looking, + 30 writes + 8 checks


class BudgetTest(unittest.TestCase):
    """How many tool calls a run over a checkout is given, and what the count is taken over."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.run_dir = self.base / "run"
        self.run_dir.mkdir()

    def checkout(self, name: str, files: int, lines: int) -> Path:
        """A checkout of that many files of that many lines, and nothing else."""
        root = self.base / name
        root.mkdir()
        for i in range(files):
            (root / f"f{i}.py").write_text("".join(f"line {n}\n" for n in range(lines)))
        return root

    def test_the_budget_is_a_share_of_one_pass_over_the_checkout_and_the_work(self):
        """seed: caps-for-the-checkout-as-it-is. The caps were set at v0.3 for a program of three
        hundred lines and have not moved since, while the checkout the builder works on has grown
        to thirteen thousand. The budget is a share of what one pass over the checkout costs, plus
        the writes and the checks a run is already allowed."""
        root = self.checkout("one-pass", FILES, LINES)
        self.assertEqual(builder.call_budget(root), BUDGET)

    def test_one_pass_is_the_reads_the_tools_would_answer_with(self):
        """seed: caps-for-the-checkout-as-it-is. Found by the reviewer of the first three runs. A
        read answers about one file and never spans two, so what one pass costs is the reads each
        file costs, summed, and not the checkout's lines over the lines a read returns. A file the
        tools can reach costs at least one read however short it is, and the error is in the count
        of files rather than their size: two hundred files of one line are two hundred reads, and
        dividing the lines called them one."""
        many = self.checkout("many-small", 200, 1)
        self.assertEqual(builder.call_budget(many), 148)  # 200 * 55 per cent + 30 + 8

    def test_a_small_checkout_gets_the_floor_and_a_large_one_the_ceiling(self):
        """seed: caps-for-the-checkout-as-it-is. A checkout smaller than the one the caps were set
        for is given no fewer calls than they were, so nothing the factory already builds is made
        worse; and no checkout is given more than the ceiling, so the worst a run can cost is a
        number and not a function of whatever the factory is pointed at."""
        self.assertEqual(builder.call_budget(self.checkout("small", 1, 3)), builder.CALLS_FLOOR)
        big = self.checkout("big", FILES, LINES)
        with mock.patch.object(builder, "CALLS_CEILING", 90):
            self.assertEqual(builder.call_budget(big), 90)

    def test_only_what_the_tools_can_reach_is_counted(self):
        """seed: caps-for-the-checkout-as-it-is. The budget is for the reading, so what is counted
        is what the tools would answer with: a hidden name at the root, git's own files at any
        depth and a symlink are not the checkout's text, and a file that is not text or cannot be
        read counts nothing rather than stopping the count."""
        root = self.checkout("one-pass", FILES, LINES)
        self.assertEqual(builder.call_budget(root), BUDGET)
        plenty = "".join(f"line {n}\n" for n in range(3000))

        for name in builder.HIDDEN:  # hidden at the root, where the tools hide them
            (root / name).mkdir()
            (root / name / "big.py").write_text(plenty)
        (root / "sub" / ".git").mkdir(parents=True)  # git's own, at any depth
        (root / "sub" / ".git" / "big.py").write_text(plenty)
        outside = self.base / "outside.py"  # a link is never walked into
        outside.write_text(plenty)
        os.symlink(outside, root / "link.py")
        (root / "blob.bin").write_bytes(bytes(range(256)) * 4000)  # not text
        shut = root / "shut.py"  # text, but not this process's to read
        shut.write_text(plenty)
        shut.chmod(0o000)
        self.addCleanup(shut.chmod, 0o600)

        self.assertEqual(builder.call_budget(root), BUDGET)

    def test_the_tools_carry_the_budget_of_the_checkout_they_are_given(self):
        """seed: caps-for-the-checkout-as-it-is. The count is taken once, from the tree the run
        starts on, and the tools carry it; a caller that already knows the budget names it and the
        tree is not walked for it."""
        root = self.checkout("one-pass", FILES, LINES)
        self.assertEqual(Tools(root, self.run_dir, sandbox=FakeSandbox([])).budget, BUDGET)
        self.assertEqual(Tools(root, self.run_dir, budget=7, sandbox=FakeSandbox([])).budget, 7)
        hidden = Tools(root, self.run_dir, hidden=(*builder.HIDDEN, "f0.py"), sandbox=FakeSandbox([]))
        self.assertEqual(hidden.budget, builder.call_budget(root, (*builder.HIDDEN, "f0.py")))
        self.assertLess(hidden.budget, BUDGET, "what the tools hide is not what they must read")


class LandingTest(unittest.TestCase):
    """A run that spends its budget is told to report and has the requests left to do it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.root.mkdir()
        (self.root / "a.py").write_text("x = 1\n")
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()

    def tools(self, budget: int) -> Tools:
        """The tools over that checkout, given that many calls and a sandbox that would raise if a
        check ever reached it."""
        return Tools(self.root, self.run_dir, budget=budget, sandbox=FakeSandbox([]))

    def test_every_tool_refuses_once_the_budget_is_spent(self):
        """seed: caps-for-the-checkout-as-it-is. The tools count every call made through them and
        stop when the budget is gone, in the words the write cap and the check cap already use, so
        the run lands instead of being cut off. All six refuse, none of them does anything, and a
        refused call counts too: what the budget bounds is what the model asked for."""
        tools = self.tools(3)
        self.assertEqual(tools.budget, 3)
        for _ in range(3):
            tools.list(".")
        self.assertEqual((tools.calls, len(tools.listed)), (3, 3))

        refusal = "error: cap reached (3 tool calls); report now"
        self.assertEqual(tools.list("."), refusal)
        self.assertEqual(tools.read("a.py"), refusal)
        self.assertEqual(tools.search("x"), refusal)
        self.assertEqual(tools.write("new.py", "y = 2\n"), refusal)
        self.assertEqual(tools.edit("a.py", "x = 1", "x = 2"), refusal)
        self.assertEqual(tools.check(), refusal)

        self.assertEqual(len(tools.listed), 3, "the refused list is not a list")
        self.assertEqual((tools.read_paths, tools.searched, tools.written, tools.edited), ([], [], [], []))
        self.assertEqual(tools.checks, [], "the check never reached the sandbox")
        self.assertFalse((self.root / "new.py").exists(), "the refused write wrote nothing")
        self.assertEqual((self.root / "a.py").read_text(), "x = 1\n", "the refused edit changed nothing")
        self.assertEqual(tools.calls, 9, "a call the budget refused is still a call")

    def test_a_run_that_spends_its_budget_reports_instead_of_being_cut_off(self):
        """seed: caps-for-the-checkout-as-it-is. Four runs of v0.15 reached a green check with the
        whole change made and were cut off before they could report, because the request cap was
        below the tool-call cap and the provider budget ran out before the tools could say stop.
        A model that is told to report now has the requests to do it, and the run ends with an
        answer and no cap at all."""
        tools = self.tools(3)

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            answered = [str(p.content) for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
            if answered and "report now" in answered[-1]:
                return ModelResponse(parts=[call("final_result", REPORT, "end")])
            return ModelResponse(parts=[call("list", {"path": "."}, f"c{len(answered)}")])

        report, messages, usage, stopped, detail = run(
            build_agent(tools, model=FunctionModel(model)), "goal", 3
        )
        self.assertEqual((stopped, detail), ("answer", ""))
        self.assertIsNotNone(report)
        self.assertEqual(len(tools.listed), 3, "three calls of the three were work")
        self.assertEqual(tools.calls, 4, "and the fourth was the refusal that ended the looking")

    def test_the_requests_a_run_is_given_always_outlast_its_calls(self):
        """seed: caps-for-the-checkout-as-it-is. `REQUEST_CAP = 60` sat below `TOOL_CALLS_CAP = 80`
        from v0.3 to v0.15, so the requests ran out twenty calls before the tools could refuse and
        the landing could never fire. The two limits are derived from the budget and never set
        apart: above the budget there are calls left to answer a refusal with, and above those
        there are requests left to report with."""
        for budget in (1, 3, builder.CALLS_FLOOR, builder.CALLS_CEILING):
            limits = builder.limits(budget)
            self.assertGreater(limits.tool_calls_limit, budget, "a refusal can be answered")
            self.assertGreater(limits.request_limit, limits.tool_calls_limit, "and then reported")

    def test_a_response_larger_than_the_reserve_still_lands(self):
        """seed: caps-for-the-checkout-as-it-is. Found by the reviewer of the first three runs. The
        library admits or refuses a whole response's tool calls together, so a response that steps
        over the budget by more than the reserve is refused entire and the model is never told to
        report: the failure this seed exists to remove, moved from the requests to the calls. Of
        3,635 responses in the store 29 carried more than four calls and the largest carried 16, so
        the reserve is wide enough for any response the factory has made. An obedient model lands
        whatever size its last response was, and the requests are never what stopped it."""
        for size in (1, 5, 16):
            tools = self.tools(3)

            def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
                answered = [str(p.content) for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
                if any("report now" in a for a in answered):
                    return ModelResponse(parts=[call("final_result", REPORT, "end")])
                return ModelResponse(parts=[call("list", {"path": "."}, f"c{len(answered)}-{i}")
                                            for i in range(size)])  # fmt: skip

            report, messages, usage, stopped, detail = run(
                build_agent(tools, model=FunctionModel(model)), "goal", 3
            )
            self.assertEqual((stopped, detail), ("answer", ""), f"a response of {size} calls")
            self.assertIsNotNone(report, f"a response of {size} calls")
            self.assertEqual(len(tools.listed), 3, f"a response of {size} calls")

    def test_the_budget_a_run_is_given_is_the_budget_its_tools_carry(self):
        """seed: caps-for-the-checkout-as-it-is. Found by the reviewer of the first three runs, and
        the build that answered it met this test's letter rather than the Goal: it kept the default
        and hung the tools' number on the library's own agent to compare against, so a caller could
        still name the wrong one and the program carried a side-channel through a class it does not
        own. There is one number and one way to pass it. The budget has no default, so a run that is
        not given one is not a call, and nothing needs to be carried on the agent to notice."""
        tools = self.tools(3)
        agent = build_agent(tools, model=FunctionModel(lambda messages, info: ModelResponse(parts=[])))
        with self.assertRaises(TypeError):
            run(agent, "goal")
        self.assertIs(inspect.signature(run).parameters["budget"].default, inspect.Parameter.empty)


class RecordTest(KeysBase):
    """What a run's numbers say about the caps it was given, and which one ended it."""

    def numbers(self, record: Path) -> dict:
        return json.loads((record / "numbers.json").read_text())

    def test_the_record_carries_the_caps_beside_the_counts_they_bound(self):
        """seed: caps-for-the-checkout-as-it-is. A count without the cap it was bounded by cannot
        be read: 24 requests of 60 and 24 of 138 are different runs. The record carries both caps
        beside both counts, and says nothing about a cap when no cap ended the run."""
        code, err = self.build()
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        n = self.numbers(record)
        budget = builder.call_budget(self.checkout)
        self.assertEqual(n["calls_cap"], budget)
        self.assertEqual(n["requests_cap"], builder.limits(budget).request_limit)
        self.assertEqual(n["cap"], "")
        # The two caps are not the same kind of number, which the reviewer of the first three runs
        # found the test asserting away: a request can never pass its limit, and the calls pass the
        # budget by as much as the reserve, because the budget is what the tools refuse at and the
        # reserve is what the library allows above it so a refusal can be answered.
        self.assertLessEqual(n["tool_calls"], n["calls_cap"] + builder.RESERVE)
        self.assertLessEqual(n["requests"], n["requests_cap"])

    def test_the_record_says_which_cap_ended_the_run(self):
        """seed: caps-for-the-checkout-as-it-is. A run cut off by the calls and one cut off by the
        requests were both `stopped: cap` with only `detail` telling them apart, so the table
        could not say which budget bound a run. The numbers say which, and nothing when no cap
        did; a run the requests bound means the reserve was wrong, because the requests are meant
        to outlast the calls."""
        self.assertEqual(builder.which_cap("answer", ""), "")
        self.assertEqual(builder.which_cap("error", "the provider fell over"), "")
        self.assertEqual(builder.which_cap("cap", "exceed the tool_calls_limit of 84"), "calls")
        self.assertEqual(builder.which_cap("cap", "exceed the request_limit of 90"), "requests")

        def endless(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[call("list", {"path": "."}, "c")])

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(builder, "CALLS_CEILING", 2):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(self.checkout), "goal"],
                                    model=FunctionModel(endless), sandbox=FakeSandbox([]))  # fmt: skip
        self.assertEqual(code, 1, err.getvalue())
        (record,) = self.records()
        n = self.numbers(record)
        self.assertEqual((n["stopped"], n["cap"], n["calls_cap"]), ("cap", "calls", 2))

    def test_the_table_shows_the_caps_beside_the_counts_they_bound(self):
        """seed: caps-for-the-checkout-as-it-is. A version reads its own runs off the table, so the
        caps belong beside the counts they bound and the cap that bit beside how the run stopped.
        A record written before the caps were recorded has empty cells and is still a row."""
        self.assertEqual(runs.COLUMNS.index("cap"), runs.COLUMNS.index("stopped") + 1)
        self.assertEqual(runs.COLUMNS.index("requests_cap"), runs.COLUMNS.index("requests") + 1)
        self.assertEqual(runs.COLUMNS.index("calls_cap"), runs.COLUMNS.index("tool_calls") + 1)

        code, err = self.build()
        self.assertEqual(code, 0, err)
        older = self.runs / "20250101T000000Z"
        older.mkdir()
        (older / "goal.txt").write_text("a run from before the caps were recorded\n")
        (older / "numbers.json").write_text('{"stopped": "answer", "requests": 4}\n')

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(runs.main(["runs.py"], runs=self.runs), 0)
        rows = [line.split("\t") for line in out.getvalue().splitlines()]
        by_stamp = {row[0]: dict(zip(rows[0], row)) for row in rows[1:]}
        self.assertEqual(by_stamp[older.name]["calls_cap"], "")
        self.assertEqual(by_stamp[older.name]["cap"], "")
        recent = by_stamp[self.records()[-1].name]
        self.assertEqual(recent["calls_cap"], str(builder.call_budget(self.checkout)))
        self.assertEqual(recent["cap"], "")

if __name__ == "__main__":
    unittest.main()
