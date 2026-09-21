#!/usr/bin/env python3
"""The records as one table: header then a row per run, tab-separated.

    uv run runs.py

`runs` is the records directory: given one, the table reads it; given none, it reads the store the
instance's configuration names and, when there is none, is a usage error that names the
configuration's file, exit 2. Every subdirectory is one record, the store's own `.git` excepted,
and becomes one row in stamp order; each value comes from the record's `numbers.json` as it is
there, `goal` is the first line of `goal.txt` with tabs as spaces, a key the record lacks is an
empty cell, and `head` reads `head` and, before v0.5, `world_head`. Two cells are derived when
the table is printed and stored nowhere: `input_per_request`, `input_tokens` over `requests`, and
`tool_errors`, right after `checks`, a record's tool returns in `messages.json` that start `error:`
and are not a wall's refusal, empty for a record without messages to read. `capped`, read beside
`tool_errors`, says whether a run was stopped by a cap: its numbers' `stopped` is `cap`, or its
messages hold a return beginning `error: cap reached`. A record without
`numbers.json` is a row with its stamp and goal alone. Nothing is written. Any argument is a
usage error on stderr, exit 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import instance

COLUMNS = (
    "stamp", "head", "stopped", "cap", "check", "requests", "requests_cap", "tool_calls", "calls_cap",
    "lists", "reads", "writes", "edits",
    "checks", "tool_errors", "input_tokens", "input_per_request", "cache_read_tokens", "output_tokens",
    "reasoning_tokens", "cost_usd", "seconds", "files_changed", "insertions", "deletions", "goal",
)  # fmt: skip
# The refusals a wall gives, shared with the evaluation table so neither counts the other's returns.
REFUSED = ("error: protected", "error: not part of", "error: outside")
# The other returns a wall gives that are no refusal: a cap reached and a check without a sandbox.
WALLS = ("error: cap reached", "error: no sandbox")


def usage_error(reason: str = "") -> int:
    print("usage: runs.py", file=sys.stderr)
    if reason:
        print(reason, file=sys.stderr)
    return 2


def _first_line(path: Path) -> str:
    """The first line of `path`, tabs as spaces; empty when the file or its first line is absent."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return lines[0].replace("\t", " ") if lines else ""


def numbers(record: Path | None) -> dict[str, Any] | None:
    """The record's `numbers.json` as a mapping, or None when the record, the file or its JSON is
    absent or is not a mapping. The one reading of a record's numbers, shared by the table and the
    tally so the two never disagree on a record."""
    if record is None:
        return None
    try:
        data = json.loads((record / "numbers.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _numbers(record: Path) -> dict[str, Any]:
    """The record's `numbers.json` as a mapping; empty when it is absent or unreadable."""
    data = numbers(record)
    return data if data is not None else {}


def _field(value: Any) -> str:
    """One cell: a string as it is, anything else as JSON prints it; a tab or newline becomes a space."""
    text = value if isinstance(value, str) else json.dumps(value)
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _number(value: Any) -> float | None:
    """`value` as a number, or None when it is absent or not one; a bool is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _per_request(numbers: dict[str, Any]) -> str:
    """`input_tokens` over `requests`, to the nearest integer; empty when either is unusable or requests is zero."""
    tokens, requests = _number(numbers.get("input_tokens")), _number(numbers.get("requests"))
    if tokens is None or requests is None or requests == 0:
        return ""
    return _field(round(tokens / requests))


def tool_errors(record: Path | None) -> int | None:
    """The record's tool returns that start `error:` and are not a wall's refusal, in its
    `messages.json`; None when there are no messages to read. One function's count, and the
    evaluation table reads it through here so the two never disagree on a record."""
    if record is None:
        return None
    try:
        messages = json.loads((record / "messages.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(messages, list):
        return None
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        parts = message.get("parts")
        for part in parts if isinstance(parts, list) else []:
            if not isinstance(part, dict) or part.get("part_kind") != "tool-return":
                continue
            content = part.get("content")
            if (isinstance(content, str) and content.startswith("error:")
                    and not content.startswith(REFUSED) and not content.startswith(WALLS)):  # fmt: skip
                total += 1
    return total


def _cap_returns(record: Path) -> bool:
    """Whether the record's `messages.json` holds a tool return that begins `error: cap reached`;
    False when there are no messages to read. The wall return that says a run was landed."""
    try:
        messages = json.loads((record / "messages.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, dict):
            continue
        parts = message.get("parts")
        for part in parts if isinstance(parts, list) else []:
            if not isinstance(part, dict) or part.get("part_kind") != "tool-return":
                continue
            content = part.get("content")
            if isinstance(content, str) and content.startswith("error: cap reached"):
                return True
    return False


def capped(record: Path | None) -> bool | None:
    """Whether the run a record holds was stopped by a cap: its numbers' `stopped` is `cap`, or
    its `messages.json` holds a tool return beginning `error: cap reached`. None when no record is
    named; the one reading the tally uses beside `tool_errors`."""
    if record is None:
        return None
    data = numbers(record)
    if data is not None and data.get("stopped") == "cap":
        return True
    return _cap_returns(record)


def _cell(record: Path, numbers: dict[str, Any], column: str) -> str:
    if column == "tool_errors":  # the model's lapses are derived, not stored
        count = tool_errors(record)
        return "" if count is None else _field(count)
    if column == "input_per_request":  # the cost-of-context column is derived, not stored
        return _per_request(numbers)
    keys = ("head", "world_head") if column == "head" else (column,)
    for key in keys:  # v0.5 renamed the field; older records carry the checkout as world_head
        if key in numbers and numbers[key] is not None:
            return _field(numbers[key])
    return ""


def main(argv: list[str], runs: Any = None) -> int:
    if len(argv) != 1:
        return usage_error("no arguments")
    if runs is not None:
        base = Path(runs)
    else:
        try:  # no directory given: the store the instance's configuration names
            base = instance.record_store()
        except (ValueError, OSError) as e:
            return usage_error(str(e))
    # A record is a directory at the store's root; the store's own .git is not one.
    records = sorted(p for p in base.iterdir() if p.is_dir() and p.name != ".git") if base.is_dir() else []
    lines = ["\t".join(COLUMNS)]
    for record in records:
        numbers = _numbers(record)
        lines.append(
            "\t".join(
                _field(record.name) if column == "stamp" else
                _field(_first_line(record / "goal.txt")) if column == "goal" else
                _cell(record, numbers, column)
                for column in COLUMNS
            )
        )
    print("\n".join(lines))
    return 0


def cli() -> None:
    """The console script's entry: no argument, `main` called with `sys.argv` whole and the process
    exited with what `main` returned, as the guard does when the file is run."""
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    cli()
