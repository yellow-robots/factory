"""What bounds a run, and the room it has to land: the-walk-that-bounds-nothing.

    uv run python -m unittest -v

No provider, no network, no docker: the model is scripted with FunctionModel and the sandbox is a
fake. The fixtures of the builder's own suite are reused rather than copied.

What this file held until v0.18 was the walk: `call_budget` summed the reads every file the tools
can reach would cost and took a share of that pass as a run's budget of tool calls. Decomposed, it
counted files rather than lines, and more than half of what it counted was the vault and the
evaluation set the builder never opens. v0.17 made what a run has spent the thing that bounds it,
and this version removes what that replaced. The spend landing itself is tested in `test_builder`,
beside the tools it belongs to; what is here is the room a landed run has to report in, and what
the record says about the caps it was given.
"""

import contextlib
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


class FixedLimitsTest(unittest.TestCase):
    """seed: the-walk-that-bounds-nothing. The library's limits are constants and a backstop, not a
    budget and not the checkout's."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def checkout(self, name: str, files: int, lines: int) -> Path:
        """A checkout of that many files of that many lines, and nothing else."""
        root = self.base / name
        root.mkdir()
        for i in range(files):
            (root / f"f{i}.py").write_text("".join(f"line {n}\n" for n in range(lines)))
        return root

    def test_the_walk_over_the_checkout_is_gone_and_so_is_what_only_it_used(self):
        """The formula claimed to follow the reading a checkout costs and counted files: of its 182
        one-pass reads here, 156 were the one-per-file floor, and `docs/seeds` and `cases` were 53.9%
        of the basis against the root's 27.5%, so every seed promoted bought half a tool call for a
        file the builder has no reason to open. Nothing reads the number it produced now that the
        spend bounds a run, and a bound that decides nothing is a bound that misleads a reader."""
        for gone in ("call_budget", "CALLS_FLOOR", "CALLS_CEILING", "SHARE", "RESERVE", "REPORT_REQUESTS"):
            self.assertFalse(hasattr(builder, gone), gone)

    def test_the_limits_are_the_same_whatever_the_checkout_holds(self):
        """The old number moved with the tree and with the backlog. Two checkouts that differ by a
        hundred files and nine hundred lines apiece get the same limits, because the limits are no
        longer anything's share of anything."""
        small, large = self.checkout("small", 1, 3), self.checkout("large", 100, 900)
        self.assertEqual(builder.limits().tool_calls_limit, builder.CALLS_LIMIT)
        self.assertEqual(builder.limits().request_limit, builder.REQUEST_LIMIT)
        for root in (small, large):
            tools = Tools(root, self.base, sandbox=FakeSandbox([]))
            self.assertFalse(hasattr(tools, "budget"), "the tools carry no budget of their own")

    def test_neither_limit_binds_before_the_spend_does(self):
        """The limits are a cheap counter that catches a runaway, and the spend is the bound that
        means something, so the spend must reach its ceiling first on any run that is spending. At
        the expensive end of the store a run costs between $0.0021 and $0.0040 a request, so
        `HARD_SPEND` is reached between 60 and 120 requests; both limits sit above that. No record
        of the 190 has ever passed 80 tool calls or 60 requests, and both of those were the old caps
        doing the censoring rather than the runs stopping there."""
        dearest, cheapest = 0.0040, 0.0021
        self.assertGreater(builder.REQUEST_LIMIT, builder.HARD_SPEND / cheapest)
        self.assertGreater(builder.CALLS_LIMIT, builder.HARD_SPEND / dearest)
        self.assertGreater(builder.REQUEST_LIMIT, builder.CALLS_LIMIT)


class LandingTest(unittest.TestCase):
    """A run told to report has the room to do it. The landing is the spend's; this is the room."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.root.mkdir()
        (self.root / "a.py").write_text("x = 1\n")
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()

    def tools(self, spent) -> Tools:
        """The tools over that checkout, asking `spent` for what the run has cost, and a sandbox
        that would raise if a check ever reached it."""
        return Tools(self.root, self.run_dir, spent=spent, sandbox=FakeSandbox([]))

    def test_a_run_told_to_report_has_the_requests_to_do_it(self):
        """seed: the-walk-that-bounds-nothing, seed: caps-for-the-checkout-as-it-is. Four runs of
        v0.15 reached a green check with the
        whole change made and were cut off before they could report, because the request cap sat
        below the tool-call cap and the provider budget ran out before the tools could say stop.
        That is what the landing exists to prevent and it must survive the budget it was built on:
        a model told to report now has the requests to do it, and the run ends with an answer and
        no cap at all."""
        spend = [0.0]
        tools = self.tools(lambda: spend[0])

        def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            answered = [str(p.content) for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
            if answered and "report now" in answered[-1]:
                return ModelResponse(parts=[call("final_result", REPORT, "end")])
            if len(answered) >= 3:
                spend[0] = builder.SOFT_SPEND  # the run crosses the line mid-way, as a run does
            return ModelResponse(parts=[call("list", {"path": "."}, f"c{len(answered)}")])

        report, messages, usage, stopped, detail = run(build_agent(tools, model=FunctionModel(model)), "goal")
        self.assertEqual((stopped, detail), ("answer", ""))
        self.assertIsNotNone(report)
        self.assertEqual(len(tools.listed), 3, "three calls of looking before it crossed")
        self.assertEqual(tools.calls, 4, "and the fourth was the refusal that ended the looking")

    def test_the_requests_a_run_is_given_always_outlast_its_calls(self):
        """seed: the-walk-that-bounds-nothing, seed: caps-for-the-checkout-as-it-is.
        `REQUEST_CAP = 60` sat below `TOOL_CALLS_CAP = 80`
        from v0.3 to v0.15, so the requests ran out twenty calls before the tools could refuse and
        the landing could never fire. The two are constants now rather than derived, which is one
        fewer way for them to drift apart and no reason at all for the order between them to change:
        a run that has spent its calls still has requests left to say what it did."""
        limits = builder.limits()
        self.assertGreater(limits.request_limit, limits.tool_calls_limit)

    def test_a_response_of_any_size_still_lands(self):
        """seed: the-walk-that-bounds-nothing, seed: caps-for-the-checkout-as-it-is. The library
        admits or refuses a whole response's tool
        calls together, which under the old budget meant a response wider than the reserve was
        refused entire and the model was never told to report -- the failure the landing exists to
        remove, moved from the requests to the calls. The reserve is gone with the budget, and the
        reason it is not missed is that the tools answer each call of a response on its own: an
        obedient model lands whatever size its last response was."""
        for size in (1, 5, 16):
            spend = [0.0]
            tools = self.tools(lambda: spend[0])

            def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
                answered = [str(p.content) for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
                if any("report now" in a for a in answered):
                    return ModelResponse(parts=[call("final_result", REPORT, "end")])
                if len(answered) >= 3:
                    spend[0] = builder.SOFT_SPEND
                return ModelResponse(parts=[call("list", {"path": "."}, f"c{len(answered)}-{i}")
                                            for i in range(size)])  # fmt: skip

            report, messages, usage, stopped, detail = run(build_agent(tools, model=FunctionModel(model)), "goal")
            self.assertEqual((stopped, detail), ("answer", ""), f"a response of {size} calls")
            self.assertIsNotNone(report, f"a response of {size} calls")


class RecordTest(KeysBase):
    """What a run's numbers say about the caps it was given, and which one ended it."""

    def numbers(self, record: Path) -> dict:
        return json.loads((record / "numbers.json").read_text())

    def test_the_record_carries_the_caps_beside_the_counts_they_bound(self):
        """seed: the-walk-that-bounds-nothing. A count without the cap it was bounded by cannot be
        read: 24 requests of 60 and 24 of 250 are different runs. The record carries both caps
        beside both counts and says nothing about a cap when none ended the run. What changed is
        that the caps are the same for every run now, so what they are for is telling a later reader
        what a count meant rather than what this checkout was worth."""
        code, err = self.build()
        self.assertEqual(code, 0, err)
        (record,) = self.records()
        n = self.numbers(record)
        self.assertEqual(n["calls_cap"], builder.CALLS_LIMIT)
        self.assertEqual(n["requests_cap"], builder.REQUEST_LIMIT)
        self.assertEqual(n["cap"], "")
        self.assertLessEqual(n["tool_calls"], n["calls_cap"])
        self.assertLessEqual(n["requests"], n["requests_cap"])
        self.assertEqual(n["spend_cap"], builder.SOFT_SPEND)
        self.assertEqual(n["hard_spend_cap"], builder.HARD_SPEND)

    def test_the_record_says_which_cap_ended_the_run(self):
        """seed: the-walk-that-bounds-nothing. A run cut off by the calls and one cut off by the
        requests were both `stopped: cap` with only `detail` telling them apart, so the table could
        not say which bound a run. The numbers say which, and nothing when none did. There are three
        now: the two the library enforces, and the hard spend ceiling the tools raise."""
        self.assertEqual(builder.which_cap("answer", ""), "")
        self.assertEqual(builder.which_cap("error", "the provider fell over"), "")
        self.assertEqual(builder.which_cap("cap", "exceed the tool_calls_limit of 200"), "calls")
        self.assertEqual(builder.which_cap("cap", "exceed the request_limit of 250"), "requests")
        self.assertEqual(builder.which_cap("cap", "exceed the hard spend ceiling of 0.25 USD"), "spend")

        def endless(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[call("list", {"path": "."}, "c")])

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(builder, "CALLS_LIMIT", 2):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = builder.main(["builder.py", str(self.checkout), "goal"],
                                    model=FunctionModel(endless), sandbox=FakeSandbox([]))  # fmt: skip
        self.assertEqual(code, 1, err.getvalue())
        (record,) = self.records()
        n = self.numbers(record)
        self.assertEqual((n["stopped"], n["cap"], n["calls_cap"]), ("cap", "calls", 2))

    def test_the_table_shows_the_caps_beside_the_counts_they_bound(self):
        """seed: the-walk-that-bounds-nothing. A version reads its own runs off the table, so the
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
        self.assertEqual(recent["calls_cap"], str(builder.CALLS_LIMIT))
        self.assertEqual(recent["cap"], "")


if __name__ == "__main__":
    unittest.main()
