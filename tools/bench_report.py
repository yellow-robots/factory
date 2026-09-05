#!/usr/bin/env python3
"""bench_report — the bench evidence report (issue #167, slice F of epic yellow-robots/factory#161).

An independent, attended host-tool write — no runner coupling, no build-time write to the factory
checkout; committed through ordinary attended git, same discipline as tools/bench_corpus.py's own corpus
data.

`report`: aggregates every `yr-bench-result/1` candidate row (tools/bench_replay.py's `run_candidate`
driver) under bench/results/*.jsonl into bench/reports/<date>-report.md — per-configuration pass rate
and weighted cost (raw outcome counts preserved alongside the rate, never collapsed away), N stated
plainly, per-repo composition, the grading caveat (quoted verbatim from bench/corpus/README.md's own
`## Grading caveat` section, never re-worded here), and this aggregation's own total weighted-token cost
across every configuration. The weighted-cost arithmetic imports tools/stage_usage.py's
WEIGHTED_TOTAL_WEIGHTS directly — never re-typed.

Stdlib-only JSON-CLI, mirroring tools/bench_corpus.py's injectable `gh(argv)` seam and
tools/stage_usage.py's summarize shape.
"""
import argparse
import datetime
import json
import pathlib
import sys

# sibling-module import (never `tools.`-prefixed): run as a bare script, sys.path[0] is already
# `tools/` — the same discipline tools/bench_replay.py documents for `import registry` / `stage_usage`.
import stage_usage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = ROOT / "bench" / "results"
DEFAULT_REPORTS_DIR = ROOT / "bench" / "reports"
DEFAULT_CORPUS_README = ROOT / "bench" / "corpus" / "README.md"

RESULT_SCHEMA = "yr-bench-result/1"

CAVEAT_HEADING = "## Grading caveat"


def _utcnow_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# --- report: bench/results/*.jsonl -> bench/reports/<date>-report.md ------------------------------------
def load_result_rows(results_dir=None):
    """Every yr-bench-result/1 row carrying a `config` (a candidate-replay row from
    tools/bench_replay.py's `run_candidate` — never a bare `grade()` row, which carries no `config`)
    across every bench/results/*.jsonl file, in file-then-line order. A line that fails to parse, or
    parses but isn't schema-matched/config-bearing, is skipped — degrade, never crash the report over
    one bad line."""
    results_dir = pathlib.Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR
    rows = []
    for path in sorted(results_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("schema") == RESULT_SCHEMA and row.get("config"):
                rows.append(row)
    return rows


def load_grading_caveat(readme_path=None):
    """The `## Grading caveat` section of bench/corpus/README.md, verbatim, stripped of surrounding
    blank lines — the report only ever quotes this, never re-words it. Raises if the file or the section
    is missing: a report silently missing its own grading caveat would misrepresent what a pass proves."""
    path = pathlib.Path(readme_path) if readme_path else DEFAULT_CORPUS_README
    lines = path.read_text().splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == CAVEAT_HEADING)
    except StopIteration:
        raise ValueError(f"{path} carries no {CAVEAT_HEADING!r} section")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = "\n".join(lines[start + 1:end]).strip()
    if not section:
        raise ValueError(f"{path}'s {CAVEAT_HEADING!r} section is empty")
    return section


def aggregate_by_config(rows):
    """Per-configuration raw outcome counts (preserved, never collapsed) + pass rate (pass / (pass +
    fail); an ungraded-environmental or invalid-seal row is excluded from that denominator — it is
    evidence of nothing about the candidate) + the summed weighted-token cost
    (tools/stage_usage.py's own WEIGHTED_TOTAL_WEIGHTS). Returns a dict keyed by config name,
    insertion-ordered by first appearance."""
    by_config = {}
    for row in rows:
        agg = by_config.setdefault(row["config"], {"n": 0, "outcomes": {}, "weighted_total": 0})
        agg["n"] += 1
        outcome = row.get("outcome") or "unknown"
        agg["outcomes"][outcome] = agg["outcomes"].get(outcome, 0) + 1
        agg["weighted_total"] += int(row.get("weighted_total") or 0)
    for agg in by_config.values():
        graded = agg["outcomes"].get("pass", 0) + agg["outcomes"].get("fail", 0)
        agg["pass_rate"] = (agg["outcomes"].get("pass", 0) / graded) if graded else None
    return by_config


def repo_composition(rows):
    """Row count per repo, insertion-ordered by first appearance."""
    counts = {}
    for row in rows:
        repo = row.get("repo") or "unknown"
        counts[repo] = counts.get(repo, 0) + 1
    return counts


def render_report(rows, *, date, caveat):
    """The full bench/reports/<date>-report.md body: N stated plainly, per-repo composition,
    per-configuration pass rate + raw outcome counts + weighted cost, the grading caveat quoted
    verbatim, and this aggregation's own total weighted-token cost across every configuration."""
    by_config = aggregate_by_config(rows)
    by_repo = repo_composition(rows)
    total_weighted = sum(agg["weighted_total"] for agg in by_config.values())

    lines = [f"# Bench report — {date}", ""]
    lines.append(f"N = {len(rows)} graded row(s) across {len(by_config)} configuration(s) "
                 f"and {len(by_repo)} repo(s).")
    lines.append("")

    lines.append("## Per-repo composition")
    lines.append("")
    if by_repo:
        for repo in sorted(by_repo):
            lines.append(f"- {repo}: {by_repo[repo]}")
    else:
        lines.append("_no rows._")
    lines.append("")

    lines.append("## Per-configuration results")
    lines.append("")
    if by_config:
        lines.append("| config | N | pass rate | outcome counts (raw) | weighted cost |")
        lines.append("|---|---|---|---|---|")
        for config in sorted(by_config):
            agg = by_config[config]
            rate = f"{agg['pass_rate']:.1%}" if agg["pass_rate"] is not None else "n/a"
            outcomes = ", ".join(f"{k}={v}" for k, v in sorted(agg["outcomes"].items()))
            lines.append(f"| {config} | {agg['n']} | {rate} | {outcomes} | {agg['weighted_total']} |")
    else:
        lines.append("_no rows._")
    lines.append("")

    lines.append(CAVEAT_HEADING)
    lines.append("")
    lines.append(caveat)
    lines.append("")

    lines.append("## Total weighted-token cost")
    lines.append("")
    lines.append(f"This aggregation's total weighted-token cost across every configuration: "
                 f"**{total_weighted}** (fresh input ×1 · output ×5 · cache-write ×1.25 · cache-read "
                 f"×0.1 — tools/stage_usage.py's WEIGHTED_TOTAL_WEIGHTS).")
    lines.append("")
    return "\n".join(lines)


def aggregate_report(*, results_dir=None, out_dir=None, readme_path=None, now=None):
    """Load every candidate result row, quote the grading caveat, render the report, and write it to
    bench/reports/<date>-report.md (`date` is this aggregation's own run date). Returns the written
    path."""
    now = now or _utcnow_iso
    date = now().split("T", 1)[0]
    rows = load_result_rows(results_dir)
    caveat = load_grading_caveat(readme_path)
    report = render_report(rows, date=date, caveat=caveat)
    out_dir = pathlib.Path(out_dir) if out_dir else DEFAULT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{date}-report.md"
    path.write_text(report)
    return path


# --- CLI ------------------------------------------------------------------------------------------------
def _cli_report(args):
    path = aggregate_report(results_dir=args.results_dir, out_dir=args.out_dir, readme_path=args.readme)
    print(path)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bench report generator (issue #167).")
    sub = ap.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="aggregate bench/results/*.jsonl into bench/reports/<date>-report.md")
    p_report.add_argument("--results-dir", default=None, help="bench/results dir (default: bench/results)")
    p_report.add_argument("--out-dir", default=None, help="bench/reports dir (default: bench/reports)")
    p_report.add_argument("--readme", default=None,
                           help="corpus README carrying the grading caveat (default: bench/corpus/README.md)")
    p_report.set_defaults(func=_cli_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
