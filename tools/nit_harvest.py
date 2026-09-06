#!/usr/bin/env python3
"""nit_harvest — the census's nit-harvest arm (technical-RFC slice P5 of epic #357).

Reads a repo's merged-PR comment trail and returns duplication / consolidation clusters ranked by
**recurrence across independent reviews** — a file named by findings in two or more *separate* PRs that
still resolves in the tree today. It feeds the census (`skills/factory/templates/debt-census.md` →
*Duplication / consolidation sets*); it NEVER files a finding as an issue, because `tools/epic_gate.py`'s
intake sweep (`_sweep_intake`, tools/epic_gate.py:661) adds every open issue in a registered repo to the
shared board, so a harvested-nit issue would flood the very state machine the census feeds.

Two finding sources, one label per row:

  source: record    — a line beginning ``YR-NIT:`` at column 0 in a comment. The record grammar,
                      defined here once and nowhere else:

                          YR-NIT: tag=<blocker|nit> path=<repo-relative path> [line=<n>] — <one sentence>

                      The anchor is ``textutil.marker_line_matches(..., mode="prefix")`` on the RAW line
                      — column 0, no ``.strip()`` and no ``\\s*`` tolerance — the same discipline
                      ``tools/epic_gate.py:453``/``:463`` and ``tools/dev-runner.sh:262`` use for their
                      own markers. It matters because a quoted review transcript (e.g. a bench replay's
                      candidate transcript, reproduced verbatim wherever it is read back) can carry an
                      embedded ``YR-NIT:`` line, and quoting always indents it behind ``> `` so it never
                      sits at column 0 — column-0 anchoring is exactly what keeps a quoted transcript's
                      nits out of the harvest.

  source: heuristic — when a finding carries NO record, the prose parser recovers repo-relative paths
                      that resolve in the tree and marks the row heuristically sourced. This path
                      degrades PRECISION, never a run: an absent record never raises and never fails the
                      build.

A stored ``line=<n>`` is **provenance only** — carried on the row so a reader can find the original
comment, never used to locate anything; no clustering or resolution step ever consults it.

TWO ARMS, and ``harvest()`` returns both. ``by_symbol`` clusters on a backticked identifier that
resolves in the tree — a contract's consumers share a NAME, not a file, so this is the arm that
answers "has this contract acquired consumers?". ``by_path`` clusters on the file. Path
clustering alone ranks the most-edited files to the top by construction, which inverts the
ordering the census actually wants (issue #376).

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

import textutil

# The one matcher constant for the record grammar (see the module docstring). Column-0, raw-line anchor
# via textutil's shared prefix mode, never a `.strip()`ed or `\s*`-tolerant match.
NIT_PREFIX = "YR-NIT:"

# Fields inside a YR-NIT payload. Parsed individually (not one rigid regex) so a well-formed record with
# an unexpected field order still reads; tag and path are the required pair.
_TAG_RE = re.compile(r"\btag=(blocker|nit)\b")
_PATH_RE = re.compile(r"\bpath=(\S+)")
_LINE_RE = re.compile(r"\bline=(\d+)\b")
_SENTENCE_RE = re.compile(r"—\s*(.*)$")

# A `path=` value as a human actually types it: backticked, quoted, and/or carrying a `:NN` suffix
# copied straight off a grep hit. All three parse fine and then fail tree-resolution, so the record is
# silently dropped — the reviewer emitted a conforming-looking record and the harvest lost it. Normalize
# once, at parse time, and recover the suffix as provenance when no explicit `line=` was given.
_PATH_DECORATION = "`'\"()[],;"
_PATH_LINE_SUFFIX_RE = re.compile(r":(\d+)$")

# A symbol token in review prose: a backticked identifier that is not a path. Symbol clustering is the
# half the arm was justified by — a contract's consumers share a NAME, not a file, and `read_ci_timeout`
# recurring across two PRs is the signal, while `tools/dev-runner.sh` recurring across sixty is churn.
_SYMBOL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{2,63})`")

# Identifiers present in the tree, for the symbol arm's resolution filter (the analogue of a path's
# `.exists()`). Same closed exclusion set the rest of the factory's tree walks use.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,63}")
_TREE_SKIP = {".git", ".venv", "node_modules", ".claude", "__pycache__", "bench"}
_TREE_TEXT_SUFFIXES = {".py", ".sh", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".cfg", ".ini"}

# A prose path token: either something containing a slash (`tools/nit_harvest.py`, `a/b/c`) or a bare
# filename with an extension (`README.md`). The tree-resolution filter (cluster()) discards any token
# that isn't a real file, so this stays deliberately permissive — it degrades precision, never a run.
_PROSE_PATH_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w-]+\.[A-Za-z][\w]*")

# The PR (or issue) number an `issues/comments` entry belongs to lives in its `issue_url` tail.
_ISSUE_URL_RE = re.compile(r"/issues/(\d+)")


def parse_nit(raw_line):
    """One record row ({tag, path, line, sentence, source='record'}) from a RAW comment line, or None
    when the line is not a column-0 ``YR-NIT:`` record. The stored ``line`` is provenance only — kept on
    the row, never used to locate anything. Indentation or a blockquote prefix means `startswith` is
    False, so an indented or `> `-quoted YR-NIT never matches (the bench-transcript guard)."""
    if not textutil.marker_line_matches(raw_line, NIT_PREFIX, mode="prefix"):
        return None
    payload = raw_line[len(NIT_PREFIX):]
    tag = _TAG_RE.search(payload)
    path = _PATH_RE.search(payload)
    if not tag or not path:
        return None
    line = _LINE_RE.search(payload)
    sentence = _SENTENCE_RE.search(payload)
    raw_path, suffix_line = _normalize_path(path.group(1))
    return {
        "tag": tag.group(1),
        "path": raw_path,
        # provenance only. An explicit `line=` wins; otherwise a `:NN` suffix on the path is where the
        # reviewer put it, and discarding it would throw away provenance the record did carry.
        "line": int(line.group(1)) if line else suffix_line,
        "sentence": sentence.group(1).strip() if sentence else "",
        "source": "record",
    }


def _normalize_path(value):
    """(path, line_or_None) from a raw `path=` value as a human actually types it.

    Strips backticks, quotes and trailing punctuation, and lifts a `:NN` suffix into provenance. Without
    this a record reading ``path=`tools/x.py`:42`` parses cleanly, fails `.exists()` in cluster(), and
    vanishes — the reviewer did everything right and the finding was lost silently, which is worse than
    a rejected record because nothing anywhere reports it.
    """
    path = (value or "").strip().strip(_PATH_DECORATION)
    suffix = _PATH_LINE_SUFFIX_RE.search(path)
    line = None
    if suffix:
        path = path[: suffix.start()]
        line = int(suffix.group(1))
    return path.rstrip("/").strip(_PATH_DECORATION), line


# A review report's own scaffolding — headings, scope declarations, verification ticks. These name a
# file WITHOUT reporting a defect in it, and the first live run (2026-08-03) showed they dominate the
# heuristic yield: sampled "findings" were `**AC3 — scope.** Outside tests/, the only file touched is…`
# and `- No changes to docs/rfcs/. ✅`. Harvesting them inverts the ranking, because the files a report
# declares scope over are exactly the files every report mentions.
#
# The vocabulary is CLOSED and lives here, deliberately: precision is what the heuristic path trades
# away, and widening this set silently is how a filter starts eating real findings. Anything not matched
# here is treated as prose, so the failure direction stays "too many rows", never "a lost finding".
# A line naming itself a finding is never scaffolding, whatever shape it wears. Checked FIRST in
# is_report_scaffolding() — see that docstring for the 16 real findings its absence ate.
_FINDING_SIGNAL_RE = re.compile(r"\b(nits?|blockers?|defects?|bugs?)\b", re.IGNORECASE)

_VERIFICATION_GLYPHS = ("✓", "✔", "✅", "❌", "✗", "🟢", "🔴")
_REPORT_LABELS = (
    "scope", "constraints", "acceptance", "acceptance criteria", "verification", "verified",
    "summary", "verdict", "steelman", "findings", "blockers", "nits", "coverage", "evidence",
    "provenance", "grounding", "notes", "out of scope", "test expectations", "goal",
)
_BOLD_ONLY_RE = re.compile(r"^\*\*[^*]+\*\*[.:\s]*$")
_BOLD_LABEL_RE = re.compile(r"^\*\*([^*]+?)\*\*")
_AC_LABEL_RE = re.compile(r"^\*\*AC\s*\d+\b", re.IGNORECASE)


def is_report_scaffolding(line):
    """True when `line` is a review report's own structure rather than a finding about a file.

    A FINDING SIGNAL OVERRIDES EVERY RULE BELOW, and that override is the filter's correctness. The
    first version had none, and it inverted the very property it was built to have: measured against
    the live 822-comment corpus it ate **16 explicitly self-labelled findings, three of them tagged
    blocker**, because reviewers in this repo routinely write a nit AS a markdown heading —
    `### nit — <file:line> — <finding>` is the canonical shape in PRs #372/#373 — and a heading was
    unconditionally scaffolding. It also ate `**Defects in already-merged slice P5 …**`, which is
    why `tools/nit_harvest.py` itself dropped out of the path clusters.

    So a line naming itself a nit, blocker, defect or bug is never scaffolding, whatever shape it
    wears. The other rules fire only on lines carrying no such signal, which restores the stated
    failure direction: surplus rows, never a lost finding.
    """
    # Strip a LIST BULLET only — `- `, `+ `, or a single `* ` — never a bare run of `*`. A naive
    # `.lstrip("-*+ ")` eats the `**` of a bold heading, so every `**heading**` then failed the
    # bold-only test below and was harvested as a finding. That was the first version of this filter
    # and the live corpus caught it.
    stripped = re.sub(r"^(?:[-+]|\*(?!\*))\s+", "", line.strip())
    if not stripped:
        return False
    if _FINDING_SIGNAL_RE.search(stripped):
        return False                                 # names itself a finding — never scaffolding
    if stripped.startswith("#"):
        return True                                  # a markdown heading
    if _BOLD_ONLY_RE.match(stripped):
        return True                                  # a bold heading and nothing else
    if any(glyph in stripped for glyph in _VERIFICATION_GLYPHS):
        return True                                  # a confirmation, not a defect
    if _AC_LABEL_RE.match(stripped):
        return True                                  # `**AC3 — scope.** …`
    label = _BOLD_LABEL_RE.match(stripped)
    if label:
        head = label.group(1).strip().rstrip(":.").strip().lower()
        head = head.split("—")[0].split("--")[0].strip()
        if head in _REPORT_LABELS:
            return True
    return False


def prose_findings(body):
    """Heuristic rows recovered from a comment `body` that carries no record — one per distinct
    repo-relative path token, tag defaulted to 'nit', no provenance line (a prose finding has none). Never
    raises: an unparseable body simply yields no rows, so the absent-record path never fails a build.

    Blockquoted lines (a `>` prefix) and off-column `YR-NIT:` marker lines are skipped: those are quoted
    transcript or teaching/example content, not the reviewer's own prose. This extends the column-0
    quoted-transcript guard to the heuristic path — a quoted nit blockquoted behind `> ` must not leak
    back in as a heuristic row just because its `path=` token is still readable inside the quote."""
    rows = []
    seen = set()
    for line in (body or "").splitlines():
        lead = line.lstrip()
        # Skip blockquoted lines and any off-column YR-NIT: marker echo: matching the shared prefix mode
        # against the left-stripped text deliberately tolerates indentation here (unlike parse_nit's RAW
        # column-0 record anchor), so an indented teaching/example marker is dropped, not mined for paths.
        if lead.startswith(">") or textutil.marker_line_matches(lead, NIT_PREFIX, mode="prefix"):
            continue
        if is_report_scaffolding(line):
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

# NOT FIXED HERE, deliberately — an off-column `YR-NIT:` (indented, or bulleted out of habit) is
# matched by nothing: not a record, and prose_findings() skips marker lines too, so it is dropped with
# no heuristic fallback and no report anywhere. An it-27 review called that a defect. But
# test_indented_and_blockquoted_yr_nit_are_not_matched_as_records pins the current behaviour
# deliberately and states its reason, and it passed independent review — so this is a live
# disagreement between two reviews about what the grammar should tolerate, not a bug to quietly
# resolve by editing the test that encodes the decision. It goes to the human.
#
# The two positions, both defensible: strictness says a near-miss must fail visibly or reviewers
# learn sloppy emission still works; the absent-record contract says a finding with no valid record
# should degrade to `source: heuristic`, never vanish. Note the blockquote half is NOT in dispute —
# `> `-prefixed markers must stay excluded either way, because a quoted review transcript (e.g. a
# bench replay's own candidate transcript) blockquotes its whole body and recovering those would
# double-count the corpus.


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


def tree_identifiers(tree_root):
    """Every identifier-shaped token in the tree's text files — the symbol arm's resolution filter.

    The analogue of a path's `.exists()`: a symbol named by two reviews but no longer present in the
    tree is a finding about code that is already gone. Read once into a set rather than grepped per
    candidate, so the arm costs one tree pass regardless of how many symbols it is testing.
    """
    idents = set()
    root = pathlib.Path(tree_root)
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _TREE_TEXT_SUFFIXES:
            continue
        if any(part in _TREE_SKIP for part in path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        idents.update(_IDENT_RE.findall(text))
    return idents


def is_compound_identifier(symbol):
    """True for `read_ci_timeout`, `MERGE_CI_TIMEOUT`, `runLint` — false for `active`, `main`, `None`.

    Backticks in review prose wrap two different things: code symbols, and ordinary English words a
    reviewer is quoting (`active`, `superseded`, `main`, `log`). Both resolve as identifiers somewhere
    in a tree this size, so tree-resolution alone cannot separate them, and the first run of the symbol
    arm surfaced six English words inside its top fourteen.

    A compound identifier — one carrying an underscore, or a capital anywhere but the first character
    — is the shape a code symbol takes, and the shape a CLONED CONTRACT takes in particular: contracts
    get named things like `read_server_ci`, never `active`.

    The capital must be INTERNAL, which is the whole discriminator: `runLint` and `EpicGate` are
    symbols, `None` and `Draft` are capitalised English. Counting capitals instead would reject
    `runLint` — and this rule has to survive a repo that names things in camelCase, since the tier
    assumes no language.

    It drops a genuinely single-word symbol (`harvest`, `cluster`), which is the honest cost: the arm
    exists to find duplicated contracts, and a bare verb is not evidence of one.
    """
    return "_" in symbol or any(c.isupper() for c in symbol[1:])


def cluster_symbols(findings, *, tree_root, known=None):
    """Recurrence clusters keyed on a SYMBOL rather than a path.

    This is the half the arm was justified by and the half that shipped missing. A contract's consumers
    share a NAME, not a file: `read_ci_timeout` named by findings in two separate PRs is the signal that
    a reader has been cloned, while `tools/dev-runner.sh` named in sixty is only churn. Path clustering
    ranks the most-edited files to the top by construction, which inverts the very ordering the arm
    exists to produce.

    Same rule as `cluster()` in every other respect — two or more distinct PRs, must still resolve in
    the tree — so the two arms are comparable and neither invents its own threshold.
    """
    idents = tree_identifiers(tree_root) if known is None else known
    by_symbol = {}
    for finding in findings:
        for symbol in _SYMBOL_RE.findall(finding.get("sentence") or ""):
            if symbol in idents and is_compound_identifier(symbol):
                by_symbol.setdefault(symbol, []).append(finding)
    clusters = []
    for symbol, rows in by_symbol.items():
        prs = sorted({row["pr"] for row in rows})
        if len(prs) < 2:
            continue
        clusters.append({
            "symbol": symbol,
            "recurrence": len(prs),
            "prs": prs,
            "findings": rows,
        })
    clusters.sort(key=lambda c: (-c["recurrence"], c["symbol"]))
    return clusters


def harvest(comments, *, tree_root):
    """The arm's whole pass: every finding across `comments`, clustered and ranked by recurrence.

    Returns BOTH arms — `{"by_symbol": [...], "by_path": [...], "counts": {...}}` — because they answer
    different questions and collapsing them loses the useful one. A symbol cluster says a contract has
    acquired consumers; a path cluster says a file draws attention. Symbol first, because that is the
    ordering the census actually reads.

    Never raises on a shapeless comment or an absent record.
    """
    findings = []
    for comment in comments:
        pr = _comment_pr(comment)
        if pr is None:
            continue
        findings.extend(findings_from_comment(pr, comment.get("body") or ""))
    by_path = cluster(findings, tree_root=tree_root)
    by_symbol = cluster_symbols(findings, tree_root=tree_root)
    return {
        "by_symbol": by_symbol,
        "by_path": by_path,
        "counts": {
            "findings": len(findings),
            "records": sum(1 for f in findings if f["source"] == "record"),
            "heuristic": sum(1 for f in findings if f["source"] == "heuristic"),
            "symbol_clusters": len(by_symbol),
            "path_clusters": len(by_path),
        },
    }


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
