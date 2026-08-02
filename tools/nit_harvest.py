#!/usr/bin/env python3
"""nit_harvest — the census's nit-harvest arm (technical-RFC slice P5 of epic #357).

Reads a repo's merged-PR comment trail and returns duplication / consolidation clusters ranked by
**recurrence across independent reviews** — a file named by findings in two or more *separate* PRs that
still resolves in the tree today. It feeds the census (`templates/debt-census.md` → *Duplication /
consolidation sets*); it NEVER files a finding as an issue, because `tools/epic_gate.py`'s intake sweep
(`_sweep_intake`, tools/epic_gate.py:661) adds every open issue in a registered repo to the shared board,
so a harvested-nit issue would flood the very state machine the census feeds.

Two finding sources, one label per row:

  source: record    — a line beginning ``YR-NIT:`` at column 0 in a comment. The record grammar,
                      defined here once and nowhere else:

                          YR-NIT: tag=<blocker|nit> path=<repo-relative path> [line=<n>] — <one sentence>

                      The anchor is ``line.startswith("YR-NIT:")`` on the RAW line — column 0, no
                      ``.strip()`` and no ``\\s*`` tolerance — the same discipline
                      ``tools/epic_gate.py:453``/``:463`` and ``tools/dev-runner.sh:262`` use for their
                      own markers. It matters because the shadow review seat's PR comment blockquotes its
                      transcript (``tools/dev-runner.sh:2235``), so a shadow nit arrives indented behind
                      ``> `` and never sits at column 0 — column-0 anchoring is exactly what keeps shadow
                      nits out of the harvest.

  source: heuristic — when a finding carries NO record, the prose parser recovers repo-relative paths
                      that resolve in the tree and marks the row heuristically sourced. This path
                      degrades PRECISION, never a run: an absent record never raises and never fails the
                      build.

A stored ``line=<n>`` is **provenance only** — carried on the row so a reader can find the original
comment, never used to locate anything: clustering and tree-resolution key on the path alone.

Read shape (no product knowledge, injectable for a network-free suite): the merged-PR comment trail is
``gh api repos/{owner}/{name}/issues/comments --paginate`` (following ``tools/bench_report.py:239``); the
suite injects the comment array as a file or a list (the ``--comments-file`` shape of
``tools/merge_shadow.py:36``), so no test touches the network or ``tests/harness/``.
"""
import argparse
import json
import pathlib
import re
import sys
import subprocess

# The one matcher constant for the record grammar (see the module docstring). Column-0, raw-line anchor:
# `raw_line.startswith(NIT_PREFIX)`, never a `.strip()`ed or `\s*`-tolerant match.
NIT_PREFIX = "YR-NIT:"

# Fields inside a YR-NIT payload. Parsed individually (not one rigid regex) so a well-formed record with
# an unexpected field order still reads; tag and path are the required pair.
_TAG_RE = re.compile(r"\btag=(blocker|nit)\b")
_PATH_RE = re.compile(r"\bpath=(\S+)")
_LINE_RE = re.compile(r"\bline=(\d+)\b")
_SENTENCE_RE = re.compile(r"—\s*(.*)$")

# A prose path token: either something containing a slash (`tools/nit_harvest.py`, `a/b/c`) or a bare
# filename with an extension (`README.md`). The tree-resolution filter (cluster()) discards any token
# that isn't a real file, so this stays deliberately permissive — it degrades precision, never a run.
_PROSE_PATH_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w-]+\.[A-Za-z][\w]*")

# The PR (or issue) number an `issues/comments` entry belongs to lives in its `issue_url` tail, matching
# tools/bench_report.py's own reader.
_ISSUE_URL_RE = re.compile(r"/issues/(\d+)")


def parse_nit(raw_line):
    """One record row ({tag, path, line, sentence, source='record'}) from a RAW comment line, or None
    when the line is not a column-0 ``YR-NIT:`` record. The stored ``line`` is provenance only — kept on
    the row, never used to locate anything. Indentation or a blockquote prefix means `startswith` is
    False, so an indented or `> `-quoted YR-NIT never matches (the shadow-transcript guard)."""
    if not raw_line.startswith(NIT_PREFIX):
        return None
    payload = raw_line[len(NIT_PREFIX):]
    tag = _TAG_RE.search(payload)
    path = _PATH_RE.search(payload)
    if not tag or not path:
        return None
    line = _LINE_RE.search(payload)
    sentence = _SENTENCE_RE.search(payload)
    return {
        "tag": tag.group(1),
        "path": path.group(1).rstrip("/"),
        "line": int(line.group(1)) if line else None,   # provenance only
        "sentence": sentence.group(1).strip() if sentence else "",
        "source": "record",
    }


def prose_findings(body):
    """Heuristic rows recovered from a comment `body` that carries no record — one per distinct
    repo-relative path token, tag defaulted to 'nit', no provenance line (a prose finding has none). Never
    raises: an unparseable body simply yields no rows, so the absent-record path never fails a build.

    Blockquoted lines (a `>` prefix) and off-column `YR-NIT:` marker lines are skipped: those are quoted
    transcript or teaching/example content, not the reviewer's own prose. This extends the column-0 shadow
    guard to the heuristic path — a shadow nit blockquoted behind `> ` must not leak back in as a
    heuristic row just because its `path=` token is still readable inside the quote."""
    rows = []
    seen = set()
    for line in (body or "").splitlines():
        lead = line.lstrip()
        if lead.startswith(">") or lead.startswith(NIT_PREFIX):
            continue
        for match in _PROSE_PATH_RE.finditer(line):
            path = match.group(0).rstrip("/").rstrip(".,;:)")
            if not path or path in seen:
                continue
            seen.add(path)
            rows.append({
                "tag": "nit",
                "path": path,
                "line": None,
                "sentence": line.strip(),
                "source": "heuristic",
            })
    return rows


def findings_from_comment(pr, body):
    """Every finding row a single comment yields, each stamped with its `pr`. A comment carrying at least
    one column-0 record is read as records (`source: record`); a comment with none degrades to the prose
    parser (`source: heuristic`) — the per-comment expression of "when a finding carries no record"."""
    records = []
    for line in (body or "").splitlines():
        row = parse_nit(line)
        if row is not None:
            records.append({**row, "pr": pr})
    if records:
        return records
    return [{**row, "pr": pr} for row in prose_findings(body)]


def _comment_pr(comment):
    """The PR/issue number a comment belongs to — an explicit `pr`/`number` field if the caller injected
    one, else parsed from the `issue_url` tail (the real `issues/comments` shape). None when neither
    resolves, so a shapeless comment is skipped rather than raising."""
    for key in ("pr", "number"):
        value = comment.get(key)
        if isinstance(value, int):
            return value
    match = _ISSUE_URL_RE.search(comment.get("issue_url") or "")
    return int(match.group(1)) if match else None


def cluster(findings, *, tree_root):
    """Rank findings into recurrence clusters. A cluster is a path named by findings from TWO OR MORE
    distinct PRs (recurrence across independent reviews) that still resolves under `tree_root`. Keyed on
    the path alone — a stored provenance line is never consulted to cluster or to resolve. A path named in
    a single PR is not a cluster; a path that no longer resolves in the tree is dropped. Sorted by
    recurrence (descending), then path, for a stable order."""
    root = pathlib.Path(tree_root)
    by_path = {}
    for finding in findings:
        by_path.setdefault(finding["path"], []).append(finding)
    clusters = []
    for path, rows in by_path.items():
        prs = sorted({row["pr"] for row in rows})
        if len(prs) < 2:
            continue
        if not (root / path).exists():   # path-only resolution; the provenance line is never used here
            continue
        clusters.append({
            "path": path,
            "recurrence": len(prs),
            "prs": prs,
            "findings": rows,
        })
    clusters.sort(key=lambda c: (-c["recurrence"], c["path"]))
    return clusters


def harvest(comments, *, tree_root):
    """The arm's whole pass: every finding across `comments` (a list of `issues/comments`-shaped dicts),
    clustered and ranked by recurrence. Never raises on a shapeless comment or an absent record."""
    findings = []
    for comment in comments:
        pr = _comment_pr(comment)
        if pr is None:
            continue
        findings.extend(findings_from_comment(pr, comment.get("body") or ""))
    return cluster(findings, tree_root=tree_root)


# --- the network read (injectable; the suite never reaches here) -----------------------------------
def _default_gh(argv):
    """Run `gh <argv...>`, returning stdout; raise on non-zero so a broken read is loud (mirrors
    tools/bench_report.py's own `_default_gh`)."""
    proc = subprocess.run(["gh", *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def read_comments(repo, gh=None):
    """Every issue/PR comment on `repo` (`owner/name`), paginated — following tools/bench_report.py:239.
    `gh api .../issues/comments` covers both issue and PR comments; a non-PR comment simply never yields a
    resolving cluster."""
    gh = gh or _default_gh
    owner, _, name = repo.partition("/")
    out = gh(["api", f"repos/{owner}/{name}/issues/comments", "--paginate"])
    return out if isinstance(out, (list, dict)) else json.loads(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Harvest recurrence-ranked nit clusters from a PR comment trail.")
    ap.add_argument("--repo", default="", help="owner/name — read the live comment trail via gh")
    ap.add_argument("--comments-file", default="",
                    help="JSON array of issue/PR comments (gh api repos/OWNER/NAME/issues/comments), for an offline run")
    ap.add_argument("--tree-root", default=".", help="the tree a clustered path must still resolve in (default: cwd)")
    args = ap.parse_args(argv)

    if args.comments_file:
        comments = json.loads(pathlib.Path(args.comments_file).read_text())
    elif args.repo:
        comments = read_comments(args.repo)
    else:
        ap.error("one of --repo or --comments-file is required")

    print(json.dumps(harvest(comments, tree_root=args.tree_root), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
