#!/usr/bin/env python3
"""The records as one table: header then a row per run, tab-separated.

    uv run runs.py

`runs` is the records directory (by default `runs/` beside this file). Every subdirectory is one
record and becomes one row in stamp order; each value comes from the record's `numbers.json` as
it is there, `goal` is the first line of `goal.txt` with tabs as spaces, a key the record lacks is
an empty cell, and `head` reads `head` and, before v0.5, `world_head`. A record without
`numbers.json` is a row with its stamp and goal alone. Nothing is written. Any argument is a
usage error on stderr, exit 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

RUNS = Path(__file__).resolve().parent / "runs"  # the factory's record, beside this file

COLUMNS = (
    "stamp", "head", "stopped", "check", "requests", "tool_calls", "lists", "reads", "writes", "edits",
    "checks", "input_tokens", "cache_read_tokens", "output_tokens", "reasoning_tokens", "cost_usd",
    "seconds", "files_changed", "insertions", "deletions", "goal",
)  # fmt: skip


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


def _numbers(record: Path) -> dict[str, Any]:
    """The record's `numbers.json` as a mapping; empty when it is absent or unreadable."""
    try:
        data = json.loads((record / "numbers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cell(numbers: dict[str, Any], column: str) -> str:
    if column == "head":  # v0.5 renamed the field; older records carry the checkout as world_head
        for key in ("head", "world_head"):
            if key in numbers:
                return str(numbers[key])
        return ""
    return str(numbers[column]) if column in numbers else ""


def main(argv: list[str], runs: Any = None) -> int:
    if len(argv) != 1:
        return usage_error("no arguments")
    base = Path(runs) if runs is not None else RUNS
    records = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    lines = ["\t".join(COLUMNS)]
    for record in records:
        numbers = _numbers(record)
        lines.append(
            "\t".join(
                record.name if column == "stamp" else
                _first_line(record / "goal.txt") if column == "goal" else
                _cell(numbers, column)
                for column in COLUMNS
            )
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
