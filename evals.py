#!/usr/bin/env python3
"""The evaluation harness: run the builder over a set of cases and tabulate the runs.

    uv run evals.py [--runs N] [case ...]

A case is a directory `cases/<name>/` under the repository holding `goal.md`, exactly one
`test_<name>.py`, and optionally `files/`. Each case runs N times (three unless `--runs N`), each
run in a throwaway git worktree of the repository at HEAD: the case's `files/` and test are
committed there as `case: <name>` by `factory <factory@localhost>`, the builder runs on that
worktree, and the worktree is removed and pruned whether the run succeeded or not. The records
land in the repository's `runs/`, where the builder leaves them, so every run is one more record
and the goal's first line names the case. Nothing here changes the repository the worktrees are
cut from.

When every run is done one tab-separated table is printed: a header, then one row per case in the
order given, with the counts of green, honest and refused runs and the medians of the builder's
numbers: `tool_errors`, right after `checks`, is the median over the case's runs of the tool
returns that start `error:` and are not a wall's refusal, read from each record's `messages.json`
as `refused` is and left out of the median when a run has none to read; beside the median of
`requests`, `cost_usd` and `seconds` the spread over the case's runs
is printed as `min-max`, the lowest and the highest value, each written as the median is. Each case
declares in `cases/<name>/pass.txt` the word that says what a pass is, `green`, `red` or `refused`,
and the table counts the runs that reached it in the `passed` column; after the table and one empty
line one line gives the set's pass rate and its standard error, the standard error left off when
there is one run per case and the line absent when there is no case. Exit 0
when every run ended with the `answer` answer, 1 when any run was capped or
errored, 2 on stderr for a usage error (a case that does not exist or is not whole, or a run
count that is not a positive integer).
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

import builder
import runs

DEFAULT_RUNS = 3
# The words a case's `pass.txt` may hold, each saying what a run of the case must be to pass it.
PASS_WORDS = ("green", "red", "refused")
COLUMNS = (
    "case", "runs", "green", "honest", "refused", "passed", "requests", "requests_spread", "tool_calls",
    "edits", "checks", "tool_errors", "input_per_request", "cost_usd", "cost_usd_spread", "seconds",
    "seconds_spread", "cost_total", "diff_lines", "files_changed", "deletions", "stray_files",
)  # fmt: skip
# A run's medians are taken over its own numbers: every column a record may lack, the derived
# input-per-request and diff-lines, computed here the way runs.py computes them, and tool-errors,
# read from runs.py, where the one count is computed for both tables, not computed here.
MEDIAN_COLUMNS = (
    "requests", "tool_calls", "edits", "checks", "tool_errors", "input_per_request", "cost_usd",
    "seconds",
)  # fmt: skip
# The medians that decide a comparison between two runs of the set carry their spread beside them.
SPREAD_COLUMNS = ("requests", "cost_usd", "seconds")


def usage_error(reason: str = "") -> int:
    print("usage: evals.py [--runs N] [case ...]", file=sys.stderr)
    if reason:
        print(reason, file=sys.stderr)
    return 2


def _number(value: Any) -> float | None:
    """`value` as a number, or None when it is absent or not one; a bool is not a number, and a
    non-finite float -- JSON's `NaN` or an infinity -- is not one either."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _numbers(record: Path | None) -> dict[str, Any]:
    """The record's `numbers.json` as a mapping; empty when it is absent or unreadable."""
    if record is None:
        return {}
    try:
        data = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _metric(record: Path | None, column: str) -> float | None:
    """One run's value for a numeric column, derived ones included; None when it lacks it."""
    if column == "tool_errors":  # the same count the runs table prints, so they never disagree
        return runs.tool_errors(record)
    numbers = _numbers(record)
    if column == "input_per_request":
        tokens, requests = _number(numbers.get("input_tokens")), _number(numbers.get("requests"))
        if tokens is None or requests is None or requests == 0:
            return None
        return round(tokens / requests)
    if column == "diff_lines":
        added, removed = _number(numbers.get("insertions")), _number(numbers.get("deletions"))
        if added is None or removed is None:
            return None
        return added + removed
    return _number(numbers.get(column))


def _median(values: list[float]) -> float | None:
    """The middle of an odd count, the mean of the two middles of an even one; None when empty."""
    return statistics.median(values) if values else None


def _number_text(value: float) -> str:
    """A number as text: whole prints without a decimal point, any other rounded to six decimals."""
    return str(int(value)) if value == int(value) else str(round(value, 6))


def _median_text(values: list[float]) -> str:
    """A median as text: whole prints without a decimal point, any other rounded to six decimals."""
    median = _median(values)
    return "" if median is None else _number_text(median)


def _spread_text(values: list[float]) -> str:
    """The spread as text, the lowest and the highest as `min-max`; empty when there are no values."""
    if not values:
        return ""
    return f"{_number_text(min(values))}-{_number_text(max(values))}"


def _cost_total(records: list[Path | None]) -> str:
    """The sum of the runs' `cost_usd`, rounded to six decimals; empty when no run has one."""
    costs = [v for v in (_number(_numbers(r).get("cost_usd")) for r in records) if v is not None]
    return "" if not costs else str(round(sum(costs), 6))


def _contents(record: Path | None) -> list[Any]:
    """The record's serialised messages, or an empty list when there are none to read."""
    if record is None:
        return []
    try:
        messages = json.loads((record / "messages.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    return messages if isinstance(messages, list) else []


def _refused(record: Path | None) -> int:
    """Tool returns in a run that refused the model a path, over all runs of the case."""
    total = 0
    for message in _contents(record):
        if not isinstance(message, dict):
            continue
        parts = message.get("parts")
        for part in parts if isinstance(parts, list) else []:
            if not isinstance(part, dict) or part.get("part_kind") != "tool-return":
                continue
            content = part.get("content")
            if isinstance(content, str) and content.startswith(runs.REFUSED):
                total += 1
    return total


def _green(record: Path | None) -> bool:
    return _numbers(record).get("check") == "green"


def _honest(record: Path | None) -> bool:
    """The report exists and its claimed check is the one the numbers recorded."""
    if record is None:
        return False
    try:
        report = json.loads((record / "report.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(report, dict) and report.get("check") == _numbers(record).get("check")


def _passed(record: Path | None, word: str) -> bool:
    """Whether a run is a pass by the case's word: `green` a green check, `red` an honest red, and
    `refused` an honest red that wrote and edited nothing; a run without a record passes nothing."""
    numbers = _numbers(record)
    if word == "green":
        return numbers.get("check") == "green"
    if word == "red":
        return numbers.get("check") == "red" and _honest(record)
    if word == "refused":
        return (numbers.get("check") == "red" and _honest(record)
                and numbers.get("written") == [] and numbers.get("edited") == [])  # fmt: skip
    return False


def _stray(record: Path | None, goal: str) -> int | None:
    """The distinct paths a run wrote or edited that `goal` names neither by path nor by basename;
    None when the run has no written and edited paths to measure."""
    numbers = _numbers(record)
    written, edited = numbers.get("written"), numbers.get("edited")
    if not isinstance(written, list) or not isinstance(edited, list):
        return None
    paths: list[str] = []
    for path in [*written, *edited]:
        if isinstance(path, str) and path not in paths:
            paths.append(path)
    return sum(1 for path in paths if path not in goal and path.rsplit("/", 1)[-1] not in goal)


def _row(name: str, records: list[Path | None], goal: str, word: str) -> list[str]:
    """One case's row: its counts, the runs that passed by its word, its medians and its summed cost."""
    cells = [
        name,
        str(len(records)),
        str(sum(1 for r in records if _green(r))),
        str(sum(1 for r in records if _honest(r))),
        str(sum(_refused(r) for r in records)),
        str(sum(1 for r in records if _passed(r, word))),
    ]
    for column in MEDIAN_COLUMNS:
        values = [v for v in (_metric(r, column) for r in records) if v is not None]
        cells.append(_median_text(values))
        if column in SPREAD_COLUMNS:
            cells.append(_spread_text(values))
    cells.append(_cost_total(records))
    for column in ("diff_lines", "files_changed", "deletions"):
        cells.append(_median_text([v for v in (_metric(r, column) for r in records) if v is not None]))
    cells.append(_median_text([v for v in (_stray(r, goal) for r in records) if v is not None]))
    return cells


def _parse(argv: list[str]) -> tuple[int, list[str], str]:
    """`--runs N` and the case names; the reason of a usage error instead, with runs and names."""
    runs, names, i = DEFAULT_RUNS, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--runs" or arg.startswith("--runs="):
            value = argv[i + 1] if arg == "--runs" and i + 1 < len(argv) else arg.partition("=")[2]
            if arg == "--runs" and i + 1 >= len(argv):
                return runs, names, "--runs needs a value"
            try:
                count = int(value)
            except ValueError:
                return runs, names, f"--runs is not a positive integer: {value}"
            if count < 1:
                return runs, names, f"--runs is not a positive integer: {value}"
            runs = count
            i += 2 if arg == "--runs" else 1
        elif arg.startswith("-") and arg != "-":
            return runs, names, f"unknown argument: {arg}"
        elif not _valid_name(arg):
            return runs, names, f"not a case name: {arg}"
        else:
            names.append(arg)
            i += 1
    return runs, names, ""


def _valid_name(name: str) -> bool:
    """A case name is one path segment: no separator, no `.` or `..`, and not empty."""
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


def _case(root: Path, name: str) -> tuple[Path, Path, str] | str:
    """The case's directory, its one red test and its pass word, or the reason it is not whole."""
    directory = root / "cases" / name
    if not directory.is_dir():
        return f"no such case: {name}"
    if not (directory / "goal.md").is_file():
        return f"case {name} has no goal.md"
    tests = sorted(directory.glob("test_*.py"))
    if len(tests) != 1:
        return f"case {name} needs exactly one test_*.py, found {len(tests)}"
    word_file = directory / "pass.txt"
    if not word_file.is_file():
        return f"case {name} has no pass.txt"
    word = word_file.read_text(encoding="utf-8-sig").strip()
    if word not in PASS_WORDS:
        return f"case {name} has an unknown pass.txt word: {word}"
    return directory, tests[0], word


def _goal(directory: Path, name: str) -> str:
    """The goal: `case: <name>` first, then the text of `goal.md`."""
    text = (directory / "goal.md").read_text(encoding="utf-8")
    return f"case: {name}\n{text.rstrip(chr(10))}"


def _run_case(root: Path, name: str, directory: Path, test: Path, worktree: Path,
              model: Any, sandbox: Any) -> tuple[int, Path | None]:  # fmt: skip
    """One run: a worktree, the case committed in it, the builder, and the worktree gone.

    The record is the directory the builder printed as its first line -- never read out of the
    runs directory, where a run that died before printing its own record would be guessed at.
    """
    builder.git(root, "worktree", "add", "--detach", str(worktree), "HEAD")
    try:
        files = directory / "files"
        if files.is_dir():
            shutil.copytree(files, worktree, dirs_exist_ok=True)
        shutil.copy2(test, worktree / test.name)
        builder.git(worktree, "add", "-A")
        builder.git(worktree, "-c", "user.name=factory", "-c", "user.email=factory@localhost",
                    "commit", "-q", "-m", f"case: {name}")  # fmt: skip  # a host identity is never needed
        out = io.StringIO()
        with contextlib.redirect_stdout(out):  # the table is the only stdout evals owns
            code = builder.main(["builder.py", str(worktree), _goal(directory, name)],
                                model=model, sandbox=sandbox)  # fmt: skip
        printed = out.getvalue().splitlines()
        return code, Path(printed[0]) if printed and printed[0].strip() else None
    finally:
        _remove_worktree(root, worktree)


def _remove_worktree(root: Path, worktree: Path) -> None:
    """Remove the worktree, whatever the run left in it; a removal that fails says so on stderr."""
    try:
        if worktree.exists():
            builder.git(root, "worktree", "remove", "--force", str(worktree))
    except Exception as e:  # a worktree git will not remove must not end the set
        print(f"could not remove the worktree {worktree}: {e}", file=sys.stderr)


def _prune(root: Path) -> None:
    """Prune the worktree metadata once the temporary directory that held them is gone."""
    try:
        builder.git(root, "worktree", "prune")
    except Exception as e:  # a prune git will not do must not end the set
        print(f"could not prune worktrees of {root}: {e}", file=sys.stderr)


def _whole(base: Path, names: list[str]) -> tuple[list[tuple[str, Path, Path, str]] | None, str]:
    """The cases to run: the named ones must be whole, an unnamed directory only may be skipped."""
    whole: list[tuple[str, Path, Path, str]] = []
    if names:
        for name in names:
            found = _case(base, name)
            if isinstance(found, str):
                return None, found
            whole.append((name, found[0], found[1], found[2]))
        return whole, ""
    cases = base / "cases"
    for directory in sorted(cases.iterdir()) if cases.is_dir() else []:
        if not directory.is_dir():
            continue
        found = _case(base, directory.name)
        if isinstance(found, str):  # not named: not a usage error, just not a case
            print(f"skipping {directory.name}: {found}", file=sys.stderr)
            continue
        whole.append((directory.name, found[0], found[1], found[2]))
    return whole, ""


def _pass_rate(whole: list[tuple[str, Path, Path, str]],
               results: list[list[Path | None]]) -> tuple[float, float]:
    """The set's pass rate and its standard error: the mean over the cases of each case's passed
    runs over its runs, and the root of the sum over the cases of n/(n-1) p(1-p) over the square
    of the case count, n the case's runs and p its passed runs over them."""
    rates: list[float] = []
    terms: list[float] = []
    for (_, _, _, word), records in zip(whole, results):
        n = len(records)
        p = sum(1 for record in records if _passed(record, word)) / n if n else 0.0
        rates.append(p)
        if n > 1:
            terms.append(n / (n - 1) * p * (1 - p))
    return sum(rates) / len(rates), math.sqrt(sum(terms) / len(whole) ** 2)


def main(argv: list[str], root: Any = None, model: Any = None, sandbox: Any = None) -> int:
    base = Path(root).resolve() if root is not None else Path(__file__).resolve().parent
    runs, names, reason = _parse(list(argv[1:]))
    if reason:
        return usage_error(reason)
    whole, reason = _whole(base, names)
    if whole is None:
        return usage_error(reason)
    results: list[list[Path | None]] = []
    answered = True
    base_tmp = Path(tempfile.mkdtemp(prefix="factory-evals-"))
    try:
        for name, directory, test, _word in whole:
            records: list[Path | None] = []
            for nth in range(runs):
                n = nth + 1
                try:  # one failed run, its error on stderr, and the set goes on
                    code, record = _run_case(base, name, directory, test, base_tmp / f"{name}-{n}",
                                             model, sandbox)  # fmt: skip
                except Exception as e:
                    code, record = 1, None
                    print(f"{name} {n}/{runs} error {e}", file=sys.stderr)
                else:
                    numbers = _numbers(record)
                    stamp = record.name if record is not None else "-"
                    print(f"{name} {n}/{runs} {numbers.get('stopped', '')} "
                          f"{numbers.get('check', '')} {stamp}", file=sys.stderr)
                records.append(record)
                answered = answered and code == 0
            results.append(records)
    finally:
        shutil.rmtree(base_tmp, ignore_errors=True)
        _prune(base)
    lines = ["\t".join(COLUMNS)]
    lines.extend("\t".join(_row(name, records, _goal(directory, name), word))
                 for (name, directory, _, word), records in zip(whole, results))  # fmt: skip
    if whole:
        rate, error = _pass_rate(whole, results)
        line = f"pass rate {rate:.3f}"
        if runs > 1:
            line += f" standard error {error:.3f}"
        lines.extend(["", line])
    print("\n".join(lines))
    return 0 if answered else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
