"""The table's acceptance tests, written from docs/seeds/record-as-table.md before the code.

    uv run python -m unittest test_runs -v

Every test builds a small runs/ directory in a temporary folder with records of the three shapes
the factory has written: the observer's (v0.1, v0.2), the builder's before head (v0.3, v0.4, with
world and world_head) and the builder's since (checkout and head), plus a record without numbers.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import runs

COLUMNS = [
    "stamp", "head", "stopped", "check", "requests", "tool_calls", "lists", "reads", "writes", "edits",
    "checks", "tool_errors", "input_tokens", "input_per_request", "cache_read_tokens", "output_tokens", "reasoning_tokens", "cost_usd",
    "seconds", "files_changed", "insertions", "deletions", "goal",
]
OBSERVER = {
    "model": "deepseek-flash", "role": "a", "wrapper": "b", "library": "pydantic-ai-slim 2.43.0",
    "stopped": "answer", "requests": 4, "wire_attempts": 4, "tool_calls": 6, "input_tokens": 30000,
    "output_tokens": 900, "cache_read_tokens": 20000, "cost_usd": 0.007, "cost_source": "table",
    "lists": 2, "reads": 4, "files_read": 4, "lines_read": 701, "seconds": 18.5,
}
BUILDER_V04 = {
    "model": "deepseek-flash", "role": "a", "wrapper": "c", "library": "pydantic-ai-slim 2.43.0",
    "world": "/w", "world_head": "5fc43b79313570e639dfd4ba0640bc084fef84c6", "stopped": "answer",
    "requests": 23, "wire_attempts": 23, "tool_calls": 34, "input_tokens": 821201, "output_tokens": 40821,
    "cache_read_tokens": 790784, "reasoning_tokens": 34176, "cost_usd": 0.06286, "cost_source": "table",
    "lists": 6, "reads": 16, "files_read": 10, "lines_read": 2061, "writes": 1, "edits": 8, "checks": 3,
    "check": "green", "check_seconds": 24.2, "files_changed": 1, "insertions": 437, "deletions": 0,
    "seconds": 211.5,
}
BUILDER_V05 = dict(BUILDER_V04, checkout="/c", head="e414436e414436e414436e414436e414436e4144", stopped="cap",
                   check="red", requests=60, cost_usd=0.11462)
del BUILDER_V05["world"], BUILDER_V05["world_head"]


def record(base: Path, stamp: str, numbers: dict | None, goal: str) -> Path:
    d = base / stamp
    d.mkdir()
    (d / "goal.txt").write_text(goal)
    if numbers is not None:
        (d / "numbers.json").write_text(json.dumps(numbers, indent=1) + "\n")
    return d


def messages(record: Path, *contents: str) -> None:
    """A `messages.json` whose tool returns are `contents`, in the library's serialised shape."""
    (record / "messages.json").write_text(json.dumps([{"parts": [{"part_kind": "tool-return", "content": c}]} for c in contents]))


def table(base: Path, *args: str) -> tuple[int, list[list[str]], str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = runs.main(["runs.py", *args], runs=base)
    rows = [line.split("\t") for line in out.getvalue().splitlines()]
    return code, rows, err.getvalue()


class RunsTest(unittest.TestCase):
    """seed: record-as-table. One tab-separated row per record, fixed columns, nothing written."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "runs"
        self.base.mkdir()
        record(self.base, "20260917T000000Z", BUILDER_V05, "rename\teverything\nsecond line\n")
        record(self.base, "20260915T085903Z", OBSERVER, "describe what this program does\n")
        record(self.base, "20260916T121241Z", BUILDER_V04, "Add `gate.py`, run as `uv run gate.py <command>`\n")
        record(self.base, "20260918T000000Z", None, "a build that died before its numbers\n")
        (self.base / "notes.txt").write_text("not a record\n")

    def test_the_header_names_the_columns_in_order(self):
        code, rows, err = table(self.base)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual(len(rows), 5)  # the header and four records; notes.txt is not one

    def test_one_row_per_record_in_stamp_order_with_the_three_shapes(self):
        code, rows, _ = table(self.base)
        by_stamp = {row[0]: dict(zip(COLUMNS, row)) for row in rows[1:]}
        self.assertEqual([row[0] for row in rows[1:]], ["20260915T085903Z", "20260916T121241Z", "20260917T000000Z", "20260918T000000Z"])
        observer = by_stamp["20260915T085903Z"]
        self.assertEqual((observer["stopped"], observer["requests"], observer["reads"], observer["cost_usd"], observer["seconds"]), ("answer", "4", "4", "0.007", "18.5"))
        self.assertEqual((observer["head"], observer["check"], observer["writes"], observer["edits"], observer["checks"], observer["reasoning_tokens"], observer["files_changed"]), ("", "", "", "", "", "", ""))
        self.assertEqual(observer["input_per_request"], "7500")  # seed: cost-of-context; 30000 / 4
        self.assertEqual(observer["goal"], "describe what this program does")
        old = by_stamp["20260916T121241Z"]
        self.assertEqual(old["head"], "5fc43b79313570e639dfd4ba0640bc084fef84c6")  # world_head, before v0.5
        self.assertEqual((old["check"], old["writes"], old["edits"], old["checks"], old["insertions"], old["deletions"]), ("green", "1", "8", "3", "437", "0"))
        self.assertEqual(old["goal"], "Add `gate.py`, run as `uv run gate.py <command>`")
        new = by_stamp["20260917T000000Z"]
        self.assertEqual((new["head"], new["stopped"], new["check"], new["requests"]), ("e414436e414436e414436e414436e414436e4144", "cap", "red", "60"))
        self.assertEqual(new["goal"], "rename everything")  # first line only, tabs as spaces
        empty = by_stamp["20260918T000000Z"]
        self.assertEqual(empty["goal"], "a build that died before its numbers")
        self.assertEqual([empty[c] for c in COLUMNS[1:-1]], [""] * (len(COLUMNS) - 2))
        for row in rows:
            self.assertEqual(len(row), len(COLUMNS))

    def test_nothing_is_written_and_an_empty_directory_is_a_header_alone(self):
        before = sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob("*"))
        table(self.base)
        self.assertEqual(before, sorted(p.relative_to(self.base).as_posix() for p in self.base.rglob("*")))
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        code, rows, _ = table(empty)
        self.assertEqual((code, rows), (0, [COLUMNS]))

    def test_any_argument_is_a_usage_error(self):
        code, rows, err = table(self.base, "20260917T000000Z")
        self.assertEqual((code, rows), (2, []))
        self.assertIn("usage", err)

    def test_every_cell_is_one_field_in_json_dialect(self):
        """seed: record-as-table. From the review: a tab or newline in any value or in a record's
        name becomes a space, a JSON null is an empty cell and head falls back past it, a value
        that is not a string prints as JSON prints it, and a byte order mark does not hide the
        numbers."""
        odd = dict(BUILDER_V05, head=None, world_head="abc123", stopped="a\tb\nc", check=True, lists=[1, 2], reads={"x": 1})
        record(self.base, "20260919T000000Z", odd, "odd\n")
        d = self.base / "20260919T000000Z"
        (d / "numbers.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(odd).encode())
        tabbed = self.base / "20260920T000000Z\tx"
        tabbed.mkdir()
        (tabbed / "goal.txt").write_text("tabbed name\n")
        code, rows, _ = table(self.base)
        self.assertEqual(code, 0)
        for row in rows:
            self.assertEqual(len(row), len(COLUMNS), row)
        by_stamp = {row[0]: dict(zip(COLUMNS, row)) for row in rows[1:]}
        cells = by_stamp["20260919T000000Z"]
        self.assertEqual((cells["head"], cells["stopped"], cells["check"], cells["lists"], cells["reads"]), ("abc123", "a b c", "true", "[1, 2]", '{"x": 1}'))
        self.assertEqual(cells["requests"], "60")
        self.assertIn("20260920T000000Z x", by_stamp)
        self.assertEqual(by_stamp["20260920T000000Z x"]["goal"], "tabbed name")
        nulls = dict(BUILDER_V05, head=None)
        del nulls["stopped"]
        record(self.base, "20260921T000000Z", nulls, "null head\n")
        code, rows, _ = table(self.base)
        cells = {row[0]: dict(zip(COLUMNS, row)) for row in rows[1:]}["20260921T000000Z"]
        self.assertEqual((cells["head"], cells["stopped"]), ("", ""))

    def test_input_per_request_is_the_cost_of_context(self):
        """seed: cost-of-context. input_tokens over requests, rounded to the nearest integer, after
        input_tokens; empty when either is missing or not a number or requests is zero."""
        code, rows, _ = table(self.base)
        self.assertEqual(rows[0][rows[0].index("input_tokens") + 1], "input_per_request")
        by_stamp = {row[0]: dict(zip(COLUMNS, row)) for row in rows[1:]}
        self.assertEqual(by_stamp["20260916T121241Z"]["input_per_request"], "35704")  # 821201 / 23
        self.assertEqual(by_stamp["20260917T000000Z"]["input_per_request"], "13687")  # 821201 / 60
        self.assertEqual(by_stamp["20260918T000000Z"]["input_per_request"], "")
        for stamp, numbers in (
            ("20260922T000000Z", dict(OBSERVER, requests=0)),
            ("20260923T000000Z", dict(OBSERVER, requests="four")),
            ("20260924T000000Z", {k: v for k, v in OBSERVER.items() if k != "input_tokens"}),
        ):
            record(self.base, stamp, numbers, "odd\n")
        code, rows, _ = table(self.base)
        by_stamp = {row[0]: dict(zip(COLUMNS, row)) for row in rows[1:]}
        for stamp in ("20260922T000000Z", "20260923T000000Z", "20260924T000000Z"):
            self.assertEqual(by_stamp[stamp]["input_per_request"], "", stamp)
        for row in rows:
            self.assertEqual(len(row), len(COLUMNS), row)


if __name__ == "__main__":
    unittest.main()


class ToolErrorsTest(unittest.TestCase):
    """seed: tool-errors-column. `tool_errors`, right after `checks`: the record's tool returns
    that start `error:` and are not a wall's refusal, read from `messages.json` when the table is
    printed and stored nowhere; empty for a record without messages to read."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "runs"
        self.base.mkdir()
        lapses = record(self.base, "20260917T000001Z", BUILDER_V05, "two of the model's\n")
        messages(lapses, "dir\t0\tsub", "error: not a directory: builder.py", "error: protected: test_x.py", "exit 1\nFAIL",
                 "error: old text not found in f.py", "error: not part of the checkout: runs", "error: outside the checkout: ..")
        clean = record(self.base, "20260917T000002Z", BUILDER_V05, "none\n")
        messages(clean, "1\tx = 1", "exit 0\nOK")
        record(self.base, "20260917T000003Z", BUILDER_V05, "no messages\n")
        broken = record(self.base, "20260917T000004Z", BUILDER_V05, "messages unreadable\n")
        (broken / "messages.json").write_text("{not json")

    def test_the_count_per_record_refusals_apart_and_empty_without_messages(self):
        code, rows, err = table(self.base)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual(rows[0][rows[0].index("checks") + 1], "tool_errors")
        by_stamp = {row[0]: dict(zip(COLUMNS, row))["tool_errors"] for row in rows[1:]}
        self.assertEqual(by_stamp, {"20260917T000001Z": "2", "20260917T000002Z": "0", "20260917T000003Z": "", "20260917T000004Z": ""})
        self.assertFalse((self.base / "20260917T000003Z" / "messages.json").exists())  # nothing written

    def test_the_module_docstring_names_the_column(self):
        self.assertIn("tool_errors", runs.__doc__)
