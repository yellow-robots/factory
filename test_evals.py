"""The evaluation harness's acceptance tests, written from docs/seeds/failure-mode-set.md and
docs/seeds/variance-runs.md before the code.

    uv run python -m unittest test_evals -v

Each test builds a temporary repository with one or two cases, points the builder's record
directory and key file into the temporary folder, and runs evals.main with a model that plays its
part from the message history alone, so every run of a case is the same play, and a fake sandbox
that answers the checks in order.
"""

import contextlib
import io
import itertools
import json
import shutil
import statistics
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import builder
import evals
import runs

models.ALLOW_MODEL_REQUESTS = False

GREEN = {"changed": ["f.py"], "did": ["f.py: x is 2"], "check": "green", "failing": [], "unsure": []}
COLUMNS = [
    "case", "runs", "green", "honest", "refused", "passed", "requests", "requests_spread", "tool_calls", "edits",
    "checks", "tool_errors", "input_per_request", "cost_usd", "cost_usd_spread", "seconds", "seconds_spread",
    "cost_total", "diff_lines", "files_changed", "deletions", "stray_files",
]
EDIT = ("edit", {"path": "f.py", "old": "x = 1", "new": "x = 2"})
CHECK = ("check", {})
BAD_LIST = ("list", {"path": "f.py"})  # a path of the wrong kind: the model's error, not a wall's
BAD_EDIT = ("edit", {"path": "f.py", "old": "nope", "new": "x = 2"})  # an anchor that misses
REFUSE = ("read", {"path": "runs/x"})  # a wall's refusal
PEEK = ("read", {"path": "cases/alpha/pass.txt"})  # the word that says what a pass is


class FakeSandbox:
    """Scripted check results, consumed in order across every run of a test."""

    def __init__(self, results):
        self.results = list(results)

    def run(self, checkout, run_dir, n):
        return self.results.pop(0)


def returns(messages: list[ModelMessage]) -> list[str]:
    return [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart) and isinstance(p.content, str)]


def player(*plays, report=GREEN, stop_on_green=True):
    """A model acting from the history alone: it plays `plays` in turn, and after a check that
    answered exit 0 it reports; with the plays exhausted it plays edit and check until a green
    check. A run's history starts empty, so every run of a case is the same play."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        done = returns(messages)
        if stop_on_green and done and done[-1].startswith("exit 0"):
            return ModelResponse(parts=[ToolCallPart("final_result", report, tool_call_id="end")])
        turn = len(done)
        name, args = plays[turn] if turn < len(plays) else (EDIT if (turn - len(plays)) % 2 == 0 else CHECK)
        return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"c{turn}")])

    return FunctionModel(model)


def liar():
    """Checks once and reports green whatever the check said."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if returns(messages):
            return ModelResponse(parts=[ToolCallPart("final_result", GREEN, tool_call_id="end")])
        return ModelResponse(parts=[ToolCallPart("check", {}, tool_call_id="c0")])

    return FunctionModel(model)


def endless():
    """Lists forever: the cap ends the run with no report."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("list", {"path": "."}, tool_call_id=f"c{len(returns(messages))}")])

    return FunctionModel(model)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


TEST_ALPHA = "import unittest\n\nimport f\n\n\nclass Alpha(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(f.x, 2)\n"


def make_repo(base: Path, cases=("alpha",)) -> Path:
    root = base / "repo"
    write(root, "f.py", "x = 1\n")
    write(root, "README.md", "the repository under evaluation\n")
    for name in cases:
        write(root, f"cases/{name}/goal.md", f"Make x equal 2 in f.py ({name}).\n")
        write(root, f"cases/{name}/test_{name}.py", TEST_ALPHA.replace("Alpha", name.title()))
        write(root, f"cases/{name}/pass.txt", "green\n")
    write(root, "cases/alpha/files/extra.txt", "extra\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "one")
    return root


def run(root: Path, *args: str, model=None, sandbox=None) -> tuple[int, list[list[str]], str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = evals.main(["evals.py", *args], root=root, model=model, sandbox=sandbox)
    rows = [line.split("\t") for line in out.getvalue().splitlines()]
    return code, rows, err.getvalue()


def tool_returns(record: Path) -> list[str]:
    """The tool returns of a record's messages, in order."""
    messages = json.loads((record / "messages.json").read_text())
    return [p["content"] for m in messages for p in m.get("parts", []) if p.get("part_kind") == "tool-return" and isinstance(p.get("content"), str)]


def messages_json(*contents: str) -> str:
    """A `messages.json` whose tool returns are `contents`, in the library's serialised shape."""
    return json.dumps([{"parts": [{"part_kind": "tool-return", "content": c}]} for c in contents])


def scripted(runs_dir: Path, script):
    """A stand-in for builder.main: `script(case, n)` gives the files of the case's n-th record,
    name to text, or None for a run that died before its record; the record is written under
    `runs_dir` and its path printed first, as the builder prints it."""
    counts: dict[str, int] = {}
    ordinal = itertools.count(1)

    def fake_build(argv, model=None, sandbox=None):
        case = argv[2].splitlines()[0].removeprefix("case: ")
        counts[case] = counts.get(case, 0) + 1
        files = script(case, counts[case])
        if files is None:
            return 1
        record = runs_dir / f"20260917T{next(ordinal):06d}Z"
        record.mkdir(parents=True)
        for name, text in files.items():
            (record / name).write_text(text)
        print(record)
        return 0

    return fake_build


def body(rows: list[list[str]]) -> list[list[str]]:
    """The table's rows after the header and before the empty line that ends it, since v0.11."""
    return rows[1:rows.index([""])] if [""] in rows else rows[1:]


def number_text(value: float) -> str:
    return str(int(value)) if value == int(value) else str(round(value, 6))


def median_text(values: list[float]) -> str:
    return number_text(statistics.median(values))


def spread_text(values: list[float]) -> str:
    return f"{number_text(min(values))}-{number_text(max(values))}"


class EvalsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = make_repo(base)
        self.runs = base / "runs"
        (base / "key").write_text("DEEPSEEK_API_KEY=not-a-key\n")
        self.enterContext(mock.patch.object(builder, "RUNS", self.runs))
        self.enterContext(mock.patch.object(builder, "KEY_FILE", base / "key"))
        self.status_before = git(self.root, "status", "--porcelain")
        self.head_before = git(self.root, "rev-parse", "HEAD").strip()

    def records(self) -> list[Path]:
        return sorted(self.runs.iterdir()) if self.runs.exists() else []

    def numbers(self, record: Path) -> dict:
        return json.loads((record / "numbers.json").read_text())

    def assert_root_untouched(self):
        self.assertEqual(git(self.root, "status", "--porcelain"), self.status_before)
        self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), self.head_before)
        self.assertEqual(git(self.root, "worktree", "list", "--porcelain").count("worktree "), 1)


class CaseTest(EvalsTest):
    """seed: failure-mode-set. A case runs in a throwaway worktree of the repository, its files and
    test committed there first, and leaves one record per run where the builder leaves them."""

    def test_a_case_runs_n_times_in_throwaway_worktrees_and_leaves_records(self):
        code, rows, err = run(self.root, "--runs", "2", "alpha", model=player(("read", {"path": "extra.txt"}), EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")] * 2))
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.records()), 2)
        for record in self.records():
            self.assertTrue((record / "goal.txt").read_text().startswith("case: alpha\nMake x equal 2 in f.py (alpha).\n"))
            numbers = self.numbers(record)
            self.assertEqual((numbers["stopped"], numbers["check"], numbers["edits"], numbers["checks"]), ("answer", "green", 1, 1))
            self.assertNotIn(str(self.root), numbers["checkout"])  # a worktree elsewhere, not the repository
            self.assertNotEqual(numbers["head"], self.head_before)  # the case's commit, on top of HEAD
            patch = (record / "diff.patch").read_text()
            self.assertIn("+x = 2", patch)
            self.assertNotIn("test_alpha.py", patch)  # committed before the run, not left by it
            self.assertNotIn("extra.txt", patch)
            self.assertFalse(Path(numbers["checkout"]).exists())  # the worktree is gone
            messages = json.loads((record / "messages.json").read_text())
            texts = [p["content"] for m in messages for p in m["parts"] if p.get("part_kind") == "tool-return"]
            self.assertTrue(any("extra" in t for t in texts), texts)  # files/ was copied in first
        self.assert_root_untouched()

    def test_the_case_commit_carries_an_identity_of_its_own(self):
        code, rows, err = run(self.root, "--runs", "1", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        record = self.records()[0]
        head = self.numbers(record)["head"]
        self.assertRegex(head, r"^[0-9a-f]{40}$")
        self.assertNotEqual(head, self.head_before)
        self.assert_root_untouched()


class TableTest(EvalsTest):
    """seed: failure-mode-set. One tab-separated table: counts of green, honest and refused runs,
    medians of the numbers, the cost summed."""

    def test_the_header_and_one_row_per_case_in_the_order_given(self):
        write(self.root, "cases/beta/goal.md", "Make x equal 2 in f.py (beta).\n")
        write(self.root, "cases/beta/test_beta.py", TEST_ALPHA.replace("Alpha", "Beta"))
        write(self.root, "cases/beta/pass.txt", "green\n")  # since v0.11 a case declares its pass
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "beta")
        self.status_before = git(self.root, "status", "--porcelain")
        self.head_before = git(self.root, "rev-parse", "HEAD").strip()
        code, rows, err = run(self.root, "--runs", "1", "beta", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")] * 2))
        self.assertEqual(code, 0, err)
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual([row[0] for row in body(rows)], ["beta", "alpha"])
        code, rows, err = run(self.root, "--runs", "1", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")] * 2))
        self.assertEqual(code, 0, err)
        self.assertEqual([row[0] for row in body(rows)], ["alpha", "beta"])  # every case, in directory order
        for row in [rows[0], *body(rows)]:
            self.assertEqual(len(row), len(COLUMNS), row)
        self.assert_root_untouched()

    def test_counts_and_medians_come_from_the_records(self):
        sandbox = FakeSandbox([(1, "FAIL\n"), (0, "OK\n"), (0, "OK\n"), (0, "OK\n")])  # run 1: two checks; runs 2 and 3: one
        code, rows, err = run(self.root, "--runs", "3", "alpha", model=player(("write", {"path": "test_zz.py", "content": "x\n"}), EDIT, CHECK), sandbox=sandbox)
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        numbers = [self.numbers(r) for r in self.records()]
        self.assertEqual(len(numbers), 3)
        self.assertEqual((cells["case"], cells["runs"], cells["green"], cells["honest"], cells["refused"]), ("alpha", "3", "3", "3", "3"))
        for column in ("requests", "tool_calls", "edits", "checks", "cost_usd", "seconds"):
            self.assertEqual(cells[column], median_text([n[column] for n in numbers]), column)
        self.assertEqual(cells["checks"], "1")  # 2, 1, 1
        self.assertEqual(cells["edits"], "1")
        self.assertEqual(cells["input_per_request"], median_text([round(n["input_tokens"] / n["requests"]) for n in numbers]))
        self.assertEqual(cells["cost_total"], str(round(sum(n["cost_usd"] for n in numbers), 6)))
        self.assertEqual(cells["diff_lines"], median_text([n["insertions"] + n["deletions"] for n in numbers]))
        self.assert_root_untouched()

    def test_the_diff_is_measured_against_the_goal(self):
        """seed: diff-as-measure. files_changed and deletions from the numbers; stray_files the
        distinct written or edited paths the goal's text names neither by path nor by basename;
        medians over the runs, after diff_lines."""
        plays = (EDIT, ("write", {"path": "notes/extra.md", "content": "x\n"}), ("write", {"path": "f.py", "content": "x = 2\n"}), CHECK)
        code, rows, err = run(self.root, "--runs", "2", "alpha", model=player(*plays), sandbox=FakeSandbox([(0, "OK\n")] * 2))
        self.assertEqual(code, 0, err)
        self.assertEqual(rows[0][rows[0].index("diff_lines") + 1:], ["files_changed", "deletions", "stray_files"])
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["files_changed"], cells["deletions"], cells["stray_files"], cells["diff_lines"]), ("2", "1", "1", "3"))
        for record in self.records():
            numbers = self.numbers(record)
            self.assertEqual((numbers["written"], numbers["edited"]), (["notes/extra.md", "f.py"], ["f.py"]))
        self.assert_root_untouched()

    def test_a_lying_report_is_not_honest_and_a_red_check_is_not_green(self):
        code, rows, err = run(self.root, "--runs", "2", "alpha", model=liar(), sandbox=FakeSandbox([(1, "FAIL\n")] * 2))
        self.assertEqual(code, 0, err)  # the runs ended with a report; red is an answer
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["green"], cells["honest"], cells["refused"], cells["edits"], cells["diff_lines"]), ("0", "0", "0", "0", "0"))

    def test_a_capped_run_counts_no_green_and_exits_one(self):
        code, rows, err = run(self.root, "--runs", "1", "alpha", model=endless(), sandbox=FakeSandbox([]))
        self.assertEqual(code, 1)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["green"], cells["honest"]), ("1", "0", "0"))
        self.assertEqual(self.numbers(self.records()[0])["stopped"], "cap")
        self.assertEqual(cells["checks"], "0")
        self.assert_root_untouched()


class MediansTest(EvalsTest):
    """seed: variance-runs. Three runs by default, and medians as the middle of three, the mean of
    two, or the one value of one."""

    def test_three_runs_by_default_and_the_median_is_the_middle(self):
        sandbox = FakeSandbox([(1, "FAIL\n"), (1, "FAIL\n"), (0, "OK\n"), (1, "FAIL\n"), (0, "OK\n"), (0, "OK\n")])  # 3, 2, 1 checks
        code, rows, err = run(self.root, "alpha", model=player(EDIT, CHECK), sandbox=sandbox)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.records()), 3)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["checks"], cells["edits"]), ("3", "2", "1"))  # the re-edits find no anchor and are not edits

    def test_two_runs_give_the_mean_of_the_middle_and_one_run_its_value(self):
        sandbox = FakeSandbox([(1, "FAIL\n"), (0, "OK\n"), (0, "OK\n")])  # 2 checks, then 1
        code, rows, err = run(self.root, "--runs", "2", "alpha", model=player(EDIT, CHECK), sandbox=sandbox)
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["checks"], cells["edits"]), ("2", "1.5", "1"))
        code, rows, err = run(self.root, "--runs", "1", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["checks"], cells["edits"]), ("1", "1", "1"))


class SpreadTest(EvalsTest):
    """seed: spread-column. Beside the median of requests, cost_usd and seconds, the lowest and the
    highest value over the runs as `min-max`, each written as the median is; a run that lacks the
    measure is left out, and the cell is empty when no run has it."""

    def test_the_spread_sits_beside_the_medians_of_requests_cost_and_seconds(self):
        sandbox = FakeSandbox([(1, "FAIL\n"), (1, "FAIL\n"), (0, "OK\n"), (1, "FAIL\n"), (0, "OK\n"), (0, "OK\n")])  # 3, 2, 1 checks
        code, rows, err = run(self.root, "alpha", model=player(EDIT, CHECK), sandbox=sandbox)
        self.assertEqual(code, 0, err)
        self.assertEqual(rows[0], COLUMNS)
        for column in ("requests", "cost_usd", "seconds"):
            self.assertEqual(rows[0][rows[0].index(column) + 1], f"{column}_spread")
        self.assertEqual(len(rows[1]), len(COLUMNS), rows[1])
        cells = dict(zip(COLUMNS, rows[1]))
        numbers = [self.numbers(r) for r in self.records()]
        self.assertEqual(len(numbers), 3)
        requests = [n["requests"] for n in numbers]
        self.assertLess(min(requests), max(requests))  # the runs did differ: 3, 2 and 1 checks
        self.assertEqual(cells["requests_spread"], f"{min(requests)}-{max(requests)}")
        for column in ("requests", "cost_usd", "seconds"):
            values = [n[column] for n in numbers]
            self.assertEqual(cells[column], median_text(values), column)
            self.assertEqual(cells[f"{column}_spread"], spread_text(values), column)
        self.assert_root_untouched()

    def test_one_run_has_the_same_value_at_both_ends_and_no_number_leaves_the_cell_empty(self):
        code, rows, err = run(self.root, "--runs", "1", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        n = self.numbers(self.records()[0])
        self.assertEqual(cells["requests_spread"], f"{n['requests']}-{n['requests']}")
        self.assertEqual(cells["cost_usd_spread"], spread_text([n["cost_usd"]]))
        self.assertEqual(cells["seconds_spread"], spread_text([n["seconds"]]))

        def exploding(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise RuntimeError("the model exploded")

        code, rows, err = run(self.root, "--runs", "2", "alpha", model=FunctionModel(exploding), sandbox=FakeSandbox([]))
        self.assertEqual(code, 1)
        cells = dict(zip(COLUMNS, rows[1]))
        for column in ("requests", "cost_usd", "seconds"):
            self.assertEqual((cells[column], cells[f"{column}_spread"]), ("", ""), column)

    def test_a_number_that_is_not_finite_is_a_measure_the_run_lacks(self):
        """From the review: JSON accepts NaN and Infinity, and a record holding one aborted the
        table after every run was paid for; it is a measure the run lacks, for the median, the
        spread and the summed cost alike."""
        requests, ordinal = iter(("NaN", "Infinity", "3")), itertools.count(1)

        def fake_build(argv, model=None, sandbox=None):
            record = self.runs / f"20260917T000000Z-{next(ordinal)}"
            record.mkdir(parents=True)
            (record / "numbers.json").write_text('{"requests": %s, "cost_usd": 0.5, "seconds": 2, "check": "green"}' % next(requests))
            print(record)
            return 0

        with mock.patch.object(builder, "main", fake_build):
            code, rows, err = run(self.root, "--runs", "3", "alpha")
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["green"]), ("3", "3"))
        self.assertEqual((cells["requests"], cells["requests_spread"]), ("3", "3-3"))
        self.assertEqual((cells["cost_usd"], cells["cost_usd_spread"], cells["cost_total"]), ("0.5", "0.5-0.5", "1.5"))
        self.assertEqual((cells["seconds"], cells["seconds_spread"]), ("2", "2-2"))
        self.assert_root_untouched()

    def test_the_module_docstring_names_the_spread(self):
        """From the review: the docstring said medians alone while README and AGENTS.md said the spread."""
        self.assertIn("`min-max`", evals.__doc__)
        self.assertIn("spread", evals.__doc__)


class UsageTest(EvalsTest):
    """seed: failure-mode-set. A case that does not exist or is not whole, or a run count that is
    not a positive integer, is a usage error on stderr, exit 2, and nothing runs."""

    def test_usage_errors_exit_two_and_run_nothing(self):
        write(self.root, "cases/gamma/goal.md", "no test here\n")
        write(self.root, "cases/delta/test_delta.py", "no goal here\n")
        write(self.root, "cases/epsilon/goal.md", "two tests\n")
        write(self.root, "cases/epsilon/test_one.py", "")
        write(self.root, "cases/epsilon/test_two.py", "")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "broken cases")
        self.status_before = git(self.root, "status", "--porcelain")
        self.head_before = git(self.root, "rev-parse", "HEAD").strip()
        for args in (("nope",), ("--runs", "0", "alpha"), ("--runs", "x", "alpha"), ("gamma",), ("delta",), ("epsilon",)):
            code, rows, err = run(self.root, *args, model=player(EDIT, CHECK), sandbox=FakeSandbox([]))
            self.assertEqual(code, 2, args)
            self.assertIn("usage", err, args)
            self.assertEqual(rows, [], args)
        self.assertEqual(self.records(), [])
        self.assert_root_untouched()


class RobustnessTest(EvalsTest):
    """seed: failure-mode-set. From the review: a run that raises is one failed run and not the end
    of the set; a line per finished run goes to stderr; a case name is one path segment; stale
    worktrees are pruned once the temporary directory is gone."""

    def test_a_run_that_raises_is_one_failed_run_and_the_set_goes_on(self):
        def exploding(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise RuntimeError("the model exploded")

        code, rows, err = run(self.root, "--runs", "2", "alpha", model=FunctionModel(exploding), sandbox=FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertEqual(rows[0], COLUMNS)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["case"], cells["runs"], cells["green"], cells["honest"]), ("alpha", "2", "0", "0"))
        self.assertIn("the model exploded", err)
        self.assert_root_untouched()

    def test_a_line_per_finished_run_on_stderr(self):
        code, rows, err = run(self.root, "--runs", "2", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")] * 2))
        self.assertEqual(code, 0)
        progress = [line for line in err.splitlines() if line.startswith("alpha ")]
        self.assertEqual(len(progress), 2, err)
        stamps = sorted(r.name for r in self.records())
        self.assertTrue(progress[0].startswith("alpha 1/2 answer green "), progress[0])
        self.assertTrue(progress[1].startswith("alpha 2/2 answer green "), progress[1])
        self.assertEqual([line.split()[-1] for line in progress], stamps)

    def test_a_case_name_is_one_path_segment_and_a_stray_directory_is_skipped(self):
        for bad in ("../outside", "alpha/../alpha", "group/sub", ".", ".."):
            code, rows, err = run(self.root, "--runs", "1", bad, model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")] * 3))
            self.assertEqual(code, 2, bad)
            self.assertIn("usage", err, bad)
            self.assertEqual(rows, [], bad)
        write(self.root, "cases/notes/README.md", "not a case\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "notes")
        self.status_before = git(self.root, "status", "--porcelain")
        self.head_before = git(self.root, "rev-parse", "HEAD").strip()
        code, rows, err = run(self.root, "--runs", "1", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        self.assertEqual([row[0] for row in body(rows)], ["alpha"])
        self.assertIn("notes", err)
        self.assert_root_untouched()

    def test_stale_worktrees_are_pruned_once_the_temporary_directory_is_gone(self):
        stale = Path(self.tmp.name) / "stale"
        git(self.root, "worktree", "add", "--detach", "-q", str(stale), "HEAD")
        shutil.rmtree(stale)
        self.assertEqual(git(self.root, "worktree", "list", "--porcelain").count("worktree "), 2)
        code, rows, err = run(self.root, "--runs", "1", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        self.assert_root_untouched()


if __name__ == "__main__":
    unittest.main()


class ToolErrorsTest(EvalsTest):
    """seed: tool-errors-column. A run's tool returns that start `error:` and are not a wall's
    refusal, counted from the record's messages: the median over the runs in the evaluation table,
    right after checks, and the count per record in the runs table, the same count in both."""

    def test_the_errors_that_are_the_models_are_counted_apart_from_refusals_in_both_tables(self):
        sandbox = FakeSandbox([(0, "OK\n")] * 3)
        code, rows, err = run(self.root, "alpha", model=player(BAD_LIST, BAD_EDIT, REFUSE, EDIT, CHECK), sandbox=sandbox)
        self.assertEqual(code, 0, err)
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual(rows[0][rows[0].index("checks") + 1], "tool_errors")
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["tool_errors"], cells["refused"]), ("3", "2", "3"))
        for record in self.records():
            returns = tool_returns(record)
            self.assertTrue(returns[0].startswith("error: not a directory"), returns[0])
            self.assertTrue(returns[1].startswith("error: old text not found"), returns[1])
            self.assertTrue(returns[2].startswith("error: not part of"), returns[2])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(runs.main(["runs.py"], runs=self.runs), 0)
        table = [line.split("\t") for line in out.getvalue().splitlines()]
        self.assertEqual(table[0][table[0].index("checks") + 1], "tool_errors")
        self.assertEqual([dict(zip(table[0], row))["tool_errors"] for row in table[1:]], ["2", "2", "2"])
        self.assert_root_untouched()

    def test_the_median_over_the_runs_and_a_run_without_messages_is_left_out(self):
        numbers = '{"check": "green", "requests": 1}'
        second = ("error: not a directory: f.py", "exit 1\nFAIL", "error: protected: test_x.py", "error: not a file: cases",
                  "error: old text found 2 times in f.py; include more context", "error: outside the checkout: ../x",
                  "error: the pattern is empty", "1\tx = 1")  # four of the model's, two refusals, a check and a read

        def script(case, n):
            files = {"numbers.json": numbers}
            if n == 1:
                files["messages.json"] = messages_json("error: old text not found in f.py")
            if n == 2:
                files["messages.json"] = messages_json(*second)
            return files  # the third run has no messages.json

        with mock.patch.object(builder, "main", scripted(self.runs, script)):
            code, rows, err = run(self.root, "alpha")
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["runs"], cells["tool_errors"], cells["refused"]), ("3", "2.5", "2"))
        shutil.rmtree(self.runs)
        with mock.patch.object(builder, "main", scripted(self.runs, lambda case, n: {"numbers.json": numbers})):
            code, rows, err = run(self.root, "alpha")
        self.assertEqual(code, 0, err)
        self.assertEqual(dict(zip(COLUMNS, rows[1]))["tool_errors"], "")
        self.assert_root_untouched()

    def test_the_module_docstring_names_the_column(self):
        self.assertIn("tool_errors", evals.__doc__)


class PassRateTest(EvalsTest):
    """seed: pass-rate-error. Each case declares in `pass.txt` the outcome that is a pass, green,
    red or refused; the table counts the runs that reached it in `passed`, and after the table one
    line gives the set's pass rate and its standard error. The word is hidden from the builder with
    the rest of `cases/`."""

    def test_each_case_declares_its_pass_and_the_line_after_the_table_gives_the_rate_and_its_error(self):
        root = make_repo(Path(self.tmp.name) / "three", ("alpha", "beta", "gamma"))
        write(root, "cases/beta/pass.txt", "red\n")
        write(root, "cases/gamma/pass.txt", "refused\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "the words")
        plays = {  # the check the numbers recorded, the check the report claims, what was edited
            "alpha": [("green", "green", []), ("green", "green", ["f.py"]), ("red", "red", [])],
            "beta": [("red", "red", []), ("red", "red", ["f.py"]), ("green", "green", [])],
            "gamma": [("red", "red", []), ("red", "red", ["f.py"]), ("red", "green", [])],
        }

        def script(case, n):
            check, claimed, edited = plays[case][n - 1]
            return {"numbers.json": json.dumps({"check": check, "written": [], "edited": edited, "requests": 1}),
                    "report.json": json.dumps({"check": claimed})}

        with mock.patch.object(builder, "main", scripted(self.runs, script)):
            code, rows, err = run(root, "alpha", "beta", "gamma")
        self.assertEqual(code, 0, err)
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual(rows[0][rows[0].index("refused") + 1], "passed")
        self.assertEqual([dict(zip(COLUMNS, row))["passed"] for row in rows[1:4]], ["2", "2", "1"])
        self.assertEqual(rows[4:], [[""], ["pass rate 0.556 standard error 0.333"]])

    def test_a_case_without_the_file_or_with_another_word_is_not_whole(self):
        word = self.root / "cases" / "alpha" / "pass.txt"
        word.unlink()
        code, rows, err = run(self.root, "alpha", model=endless(), sandbox=FakeSandbox([]))
        self.assertEqual((code, rows, self.records()), (2, [], []))
        self.assertIn("pass.txt", err)
        code, rows, err = run(self.root, model=endless(), sandbox=FakeSandbox([]))
        self.assertEqual((code, rows, self.records()), (0, [COLUMNS], []))  # skipped; no case, no line
        self.assertIn("skipping alpha", err)
        self.assertIn("pass.txt", err)
        word.write_text("maybe\n")
        code, rows, err = run(self.root, "alpha", model=endless(), sandbox=FakeSandbox([]))
        self.assertEqual((code, rows, self.records()), (2, [], []))
        self.assertIn("maybe", err)

    def test_one_run_per_case_gives_the_rate_alone_and_a_run_without_a_record_passes_nothing(self):
        code, rows, err = run(self.root, "--runs", "1", "alpha", model=player(EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")]))
        self.assertEqual(code, 0, err)
        self.assertEqual(dict(zip(COLUMNS, rows[1]))["passed"], "1")
        self.assertEqual(rows[2:], [[""], ["pass rate 1.000"]])

        def exploding(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise RuntimeError("the model exploded")

        code, rows, err = run(self.root, "--runs", "2", "alpha", model=FunctionModel(exploding), sandbox=FakeSandbox([]))
        self.assertEqual(code, 1)
        self.assertEqual(dict(zip(COLUMNS, rows[1]))["passed"], "0")
        self.assertEqual(rows[2:], [[""], ["pass rate 0.000 standard error 0.000"]])

    def test_the_word_is_the_harness_s_and_the_builder_s_look_at_it_is_a_refusal(self):
        code, rows, err = run(self.root, "alpha", model=player(PEEK, EDIT, CHECK), sandbox=FakeSandbox([(0, "OK\n")] * 3))
        self.assertEqual(code, 0, err)
        cells = dict(zip(COLUMNS, rows[1]))
        self.assertEqual((cells["passed"], cells["refused"]), ("3", "3"))
        for record in self.records():
            first = tool_returns(record)[0]
            self.assertTrue(first.startswith("error: not part of the checkout"), first)
            self.assertNotIn("green", first)
        self.assert_root_untouched()

    def test_the_module_docstring_names_the_file_the_column_and_the_line(self):
        for term in ("pass.txt", "passed", "pass rate", "standard error"):
            self.assertIn(term, evals.__doc__, term)
