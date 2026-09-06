#!/usr/bin/env python3
"""strategy.py — reads a strategy note's fenced ```yr-strategy TOML block.

A strategy note lives under `<component>/strategy/`; its body carries exactly one fenced
```yr-strategy TOML block, using the same fence-word grammar `tools/merge_shadow.py` uses for its
own record blocks: find the marker, find the next closing fence, parse what's between — never a
second parser. The block is parsed with `tomllib` (never hand-written YAML) into themes (`id`,
`goal`, `target`, `repos`, `budget_usd`, `stop_when`), `constraints`, `kpi_targets`,
`loop_budget_usd_per_week` and `factory_cap`. A missing or malformed block is a loud finding, never
a silent empty result. The note's frontmatter, if any, is read through
`tools.textutil.split_frontmatter` — the one parser; an out-of-subset shape there is reported
alongside the parsed block, never silently dropped.

Usage: strategy.py <note.md>
Exit 0 printing the parsed strategy as JSON; 1 with a `<file>: <message>` line when the block is
missing or malformed.
"""
import argparse
import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.textutil import split_frontmatter

FENCE = "```yr-strategy"
REQUIRED_THEME_KEYS = ("id", "goal", "target", "repos", "budget_usd", "stop_when")
REQUIRED_KEYS = ("themes", "constraints", "kpi_targets", "loop_budget_usd_per_week", "factory_cap")


class StrategyError(Exception):
    """A missing or malformed ```yr-strategy block — always reported, never guessed past."""


def extract_block(body):
    """The raw TOML text between the ```yr-strategy fence and its closing ``` fence."""
    i = body.find(FENCE)
    if i < 0:
        raise StrategyError("no fenced ```yr-strategy block found")
    rest = body[i + len(FENCE):]
    j = rest.find("```")
    if j < 0:
        raise StrategyError("```yr-strategy block never closes")
    return rest[:j]


def parse_strategy(text):
    """Full note text -> the strategy dict (themes/constraints/kpi_targets/loop_budget_usd_per_week/
    factory_cap), or raises StrategyError loudly on a missing or malformed block."""
    _, body = split_frontmatter(text)
    block = extract_block(body)
    try:
        data = tomllib.loads(block)
    except tomllib.TOMLDecodeError as e:
        raise StrategyError(f"yr-strategy block is malformed TOML: {e}") from e
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise StrategyError(f"yr-strategy block missing required key(s): {', '.join(missing)}")
    themes = data["themes"]
    if not isinstance(themes, list) or not themes:
        raise StrategyError("yr-strategy `themes` must be a non-empty array of tables")
    for i, theme in enumerate(themes):
        if not isinstance(theme, dict):
            raise StrategyError(f"yr-strategy themes[{i}] must be a table")
        missing_theme = [k for k in REQUIRED_THEME_KEYS if k not in theme]
        if missing_theme:
            raise StrategyError(
                f"yr-strategy themes[{i}] missing required key(s): {', '.join(missing_theme)}")
    return {k: data[k] for k in REQUIRED_KEYS}


def frontmatter_findings(text):
    """The note's frontmatter out-of-subset findings, if any — surfaced, never silently dropped."""
    meta, _ = split_frontmatter(text)
    return list(meta.out_of_subset)


def matching_theme(parsed_strategy, repo):
    """The first theme (declared order) whose `repos` names `repo`, or `None` — "in-direction" is
    exactly "some theme targets this repo at all". The ONE theme-matching rule over a parsed
    strategy dict (NN2, #473 fold review round 2): moved here from `tools/design_gate.py`'s own
    private `_matching_theme` so every reader (the design sweep, `tools/round_record.py`'s own
    crossover) shares a public seam next to the schema it reads, rather than reaching into another
    module's underscore-prefixed name."""
    for theme in parsed_strategy.get("themes") or []:
        if repo in (theme.get("repos") or []):
            return theme
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read a strategy note's fenced yr-strategy TOML block.")
    ap.add_argument("note", help="path to the strategy note (markdown)")
    args = ap.parse_args(argv)
    path = Path(args.note)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"{args.note}: unreadable: {e}")
        return 1
    for finding in frontmatter_findings(text):
        print(f"{args.note}: frontmatter finding: {finding}")
    try:
        data = parse_strategy(text)
    except StrategyError as e:
        print(f"{args.note}: {e}")
        return 1
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
