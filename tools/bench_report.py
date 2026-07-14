#!/usr/bin/env python3
"""bench_report — the bench evidence report + verdict-diff aggregate with merge-outcome backfill
(issue #167, slice F of epic yellow-robots/factory#161).

Two independent, attended host-tool writes — no runner coupling, no build-time write to the factory
checkout; committed through ordinary attended git, same discipline as tools/bench_corpus.py's own corpus
data:

  1. `report`: aggregates every `yr-bench-result/1` candidate row (tools/bench_replay.py's
     `run_candidate` driver) under bench/results/*.jsonl into bench/reports/<date>-report.md —
     per-configuration pass rate and weighted cost (raw outcome counts preserved alongside the rate,
     never collapsed away), N stated plainly, per-repo composition, the grading caveat (quoted verbatim
     from bench/corpus/README.md's own `## Grading caveat` section, never re-worded here), and this
     aggregation's own total weighted-token cost across every configuration. The weighted-cost
     arithmetic imports tools/stage_usage.py's WEIGHTED_TOTAL_WEIGHTS directly — never re-typed.

  2. `sweep-diffs`: sweeps every posted `YR-VERDICT-DIFF` PR-trail comment (tools/verdict_diff.py's
     `render_comment` shape — comments only ever land on a PR, via `gh pr comment`) across one repo into
     bench/diffs/<owner>--<name>.jsonl, backfilling each PR's merge outcome (`gh pr view --json
     state,mergedAt`) at aggregation time: `merged` / `closed` / `pending` (a still-open PR). Idempotent
     by construction — keyed on repo+PR+round, an existing record for the same key is updated in place
     rather than duplicated, so re-running the sweep over an unchanged comment trail is a byte-identical
     no-op.

Stdlib-only JSON-CLI, mirroring tools/bench_corpus.py's injectable `gh(argv)` seam and
tools/stage_usage.py's summarize shape.
"""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

# sibling-module import (never `tools.`-prefixed): run as a bare script, sys.path[0] is already
# `tools/` — the same discipline tools/bench_replay.py documents for `import registry` / `stage_usage`.
import stage_usage

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = ROOT / "bench" / "results"
DEFAULT_REPORTS_DIR = ROOT / "bench" / "reports"
DEFAULT_DIFFS_DIR = ROOT / "bench" / "diffs"
DEFAULT_CORPUS_README = ROOT / "bench" / "corpus" / "README.md"

RESULT_SCHEMA = "yr-bench-result/1"
DIFF_SCHEMA = "yr-verdict-diff/1"

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


# --- sweep-diffs: YR-VERDICT-DIFF PR comments -> bench/diffs/<owner>--<name>.jsonl, merge backfilled ----
def _default_gh(argv):
    """Run `gh <argv...>`; return stdout text. Raises on a non-zero exit so a broken read is loud —
    mirrors tools/bench_corpus.py's own `_gh`."""
    proc = subprocess.run(["gh", *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _gh_json(gh, argv):
    out = gh(argv)
    return out if isinstance(out, (dict, list)) else json.loads(out)


_ISSUE_URL_RE = re.compile(r"/issues/(\d+)$")

_COMMENT_FIELD_RES = {
    "round": re.compile(r"^round:\s*(\d+)\s*$", re.MULTILINE),
    "gating": re.compile(r"^gating:\s*(.+?)\s*$", re.MULTILINE),
    "shadow": re.compile(r"^shadow:\s*(.+?)\s*$", re.MULTILINE),
    "agree": re.compile(r"^agree:\s*(true|false)\s*$", re.MULTILINE),
}


def parse_verdict_diff_comment(pr_number, body):
    """One yr-verdict-diff/1-shaped record ({schema, pr, round, gating, shadow, agree}) from a posted
    YR-VERDICT-DIFF comment body (tools/verdict_diff.py's `render_comment` shape), or None if `body`
    isn't such a comment or is missing a field — never a partial/guessed record."""
    if not body.startswith("YR-VERDICT-DIFF:"):
        return None
    matches = {key: rx.search(body) for key, rx in _COMMENT_FIELD_RES.items()}
    if not all(matches.values()):
        return None
    return {
        "schema": DIFF_SCHEMA,
        "pr": pr_number,
        "round": int(matches["round"].group(1)),
        "gating": matches["gating"].group(1),
        "shadow": matches["shadow"].group(1),
        "agree": matches["agree"].group(1) == "true",
    }


def _list_comments(gh, owner, name):
    """Every issue/PR comment on `owner/name`, paginated — `gh api .../issues/comments` covers both
    issue and PR comments; a YR-VERDICT-DIFF comment only ever lands on a PR (tools/dev-runner.sh's `gh
    pr comment`), so a comment on a plain issue simply never matches parse_verdict_diff_comment's
    grammar."""
    return _gh_json(gh, ["api", f"repos/{owner}/{name}/issues/comments", "--paginate"])


def backfill_merge_outcome(gh, owner, name, pr_number):
    """`merged` / `closed` / `pending` (a still-open PR), read fresh from `gh pr view --json
    state,mergedAt` at aggregation time — never cached from a prior sweep."""
    out = _gh_json(gh, ["pr", "view", str(pr_number), "--repo", f"{owner}/{name}",
                         "--json", "state,mergedAt"])
    if out.get("mergedAt") or (out.get("state") or "").upper() == "MERGED":
        return "merged"
    if (out.get("state") or "").upper() == "CLOSED":
        return "closed"
    return "pending"


def _load_existing_diffs(out_path):
    existing = {}
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            existing[(row["pr"], row["round"])] = row
    return existing


def sweep_diffs(repo, *, gh=None, out_dir=None):
    """Sweep every posted YR-VERDICT-DIFF PR comment on `repo` (`owner/name`) into
    bench/diffs/<owner>--<name>.jsonl, backfilling each PR's merge outcome. Idempotent: keyed on
    repo+PR+round, an existing record for the same key is updated in place rather than duplicated, so
    re-running the sweep over an unchanged comment trail produces a byte-identical file. Returns the
    written path."""
    gh = gh or _default_gh
    owner, _, name = repo.partition("/")
    out_dir = pathlib.Path(out_dir) if out_dir else DEFAULT_DIFFS_DIR
    out_path = out_dir / f"{owner}--{name}.jsonl"

    existing = _load_existing_diffs(out_path)

    records = []
    for comment in _list_comments(gh, owner, name):
        match = _ISSUE_URL_RE.search(comment.get("issue_url") or "")
        if not match:
            continue
        record = parse_verdict_diff_comment(int(match.group(1)), comment.get("body") or "")
        if record:
            records.append(record)

    outcome_by_pr = {pr: backfill_merge_outcome(gh, owner, name, pr)
                      for pr in sorted({r["pr"] for r in records})}

    for record in records:
        record["repo"] = repo
        record["outcome"] = outcome_by_pr[record["pr"]]
        existing[(record["pr"], record["round"])] = record

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for key in sorted(existing):
            f.write(json.dumps(existing[key], sort_keys=True) + "\n")
    return out_path


# --- CLI ------------------------------------------------------------------------------------------------
def _cli_report(args):
    path = aggregate_report(results_dir=args.results_dir, out_dir=args.out_dir, readme_path=args.readme)
    print(path)
    return 0


def _cli_sweep_diffs(args):
    path = sweep_diffs(args.repo, out_dir=args.out_dir)
    print(path)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Bench report generator + verdict-diff aggregation with merge-outcome backfill (issue #167).")
    sub = ap.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="aggregate bench/results/*.jsonl into bench/reports/<date>-report.md")
    p_report.add_argument("--results-dir", default=None, help="bench/results dir (default: bench/results)")
    p_report.add_argument("--out-dir", default=None, help="bench/reports dir (default: bench/reports)")
    p_report.add_argument("--readme", default=None,
                           help="corpus README carrying the grading caveat (default: bench/corpus/README.md)")
    p_report.set_defaults(func=_cli_report)

    p_sweep = sub.add_parser("sweep-diffs",
                              help="sweep YR-VERDICT-DIFF PR comments into bench/diffs/<owner>--<name>.jsonl, backfilling merge outcome")
    p_sweep.add_argument("--repo", required=True, help="owner/name")
    p_sweep.add_argument("--out-dir", default=None, help="bench/diffs dir (default: bench/diffs)")
    p_sweep.set_defaults(func=_cli_sweep_diffs)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
