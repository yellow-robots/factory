#!/usr/bin/env python3
"""rank.py — the Ideas Backlog Base's own rank, read by machinery instead of Obsidian.

Reproduces the Base's `formulas.rank` expression verbatim in meaning, over every `status == "open"`
seed found under a component root's `ideas/` folder(s):

    if(value && effort, (value - if(effort=="S",0,if(effort=="M",0.5,1))).round(1), "")

A seed missing `value` or `effort` carries no rank (printed as an empty column/`null`) but is still
listed — dropping it would silently hide backlog nobody asked to hide. An unrecognized `effort`
(anything other than "S"/"M") falls through to the "L" discount, exactly as the nested `if` does.
Frontmatter is read through `tools.textutil.split_frontmatter`, the one parser every crossing-link /
task / supersession guard already shares — never a second parser. A seed whose frontmatter reports a
shape outside that parser's declared subset is listed too, carrying the finding, rather than
disappearing because a field failed to parse.

Usage:
    rank.py list <root> [--json]
    rank.py top --n N <root> [--json]

`root` scopes the scan to one component (or any directory) — a seed outside it is never in view.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.textutil import split_frontmatter

STATUS_OPEN = "open"


def _is_ideas_note(rel_parts):
    """True when an `ideas` directory sits anywhere above the file itself in `rel_parts`."""
    return "ideas" in rel_parts[:-1]


def find_seeds(root):
    """Every ideas-folder note (*.md) at or below `root`, sorted for a stable scan order."""
    root = Path(root)
    return sorted(p for p in root.rglob("*.md") if _is_ideas_note(p.relative_to(root).parts))


def compute_rank(value, effort):
    """The Base's `formulas.rank` expression, verbatim in meaning. `None` (the formula's `""`) when
    `value` or `effort` is missing/empty, or `value` doesn't parse as a number."""
    if not value or not effort:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if effort == "S":
        discount = 0
    elif effort == "M":
        discount = 0.5
    else:
        discount = 1
    return round(numeric_value - discount, 1)


def load_seed(path, root):
    """One seed's report: its fields, computed rank, and any out-of-subset frontmatter findings."""
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, _ = split_frontmatter(text)
    return {
        "path": str(path.relative_to(root)),
        "status": meta.get("status", ""),
        "summary": meta.get("summary", ""),
        "value": meta.get("value", ""),
        "effort": meta.get("effort", ""),
        "rank": compute_rank(meta.get("value"), meta.get("effort")),
        "findings": list(meta.out_of_subset),
    }


def ranked_seeds(root):
    """Every open seed under `root`, plus any seed whose frontmatter reported an out-of-subset
    finding regardless of its readable status (a finding is never silently dropped), sorted
    descending by rank — unranked seeds last, ties broken by path for a stable order."""
    seeds = [load_seed(p, root) for p in find_seeds(root)]
    seeds = [s for s in seeds if s["status"] == STATUS_OPEN or s["findings"]]
    seeds.sort(key=lambda s: (s["rank"] is None, -(s["rank"] or 0), s["path"]))
    return seeds


def _print_tsv(seeds):
    print("\t".join(["path", "value", "effort", "rank", "summary", "findings"]))
    for s in seeds:
        rank = "" if s["rank"] is None else str(s["rank"])
        print("\t".join([s["path"], str(s["value"]), str(s["effort"]), rank,
                          s["summary"], "; ".join(s["findings"])]))


def _print_json(seeds):
    print(json.dumps(seeds, indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read the ideas-backlog rank without opening Obsidian.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="every open seed under root, ranked descending")
    p_list.add_argument("root", help="component root (or any directory) to scan for ideas/ folders")
    p_list.add_argument("--json", action="store_true", help="print JSON instead of TSV")
    p_top = sub.add_parser("top", help="the top N ranked seeds under root")
    p_top.add_argument("root", help="component root (or any directory) to scan for ideas/ folders")
    p_top.add_argument("--n", type=int, required=True, help="how many seeds to print")
    p_top.add_argument("--json", action="store_true", help="print JSON instead of TSV")
    args = ap.parse_args(argv)

    seeds = ranked_seeds(args.root)
    if args.cmd == "top":
        seeds = seeds[:args.n]
    (_print_json if args.json else _print_tsv)(seeds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
