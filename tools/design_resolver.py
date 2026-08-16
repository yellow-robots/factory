#!/usr/bin/env python3
"""design_resolver.py — the governing-design resolver (it-31 slice 4, crossing disposition 4).

The one seam that answers "does this epic's governing design resolve, and is it active?": parse
the epic body's Source line (registry row SOURCE-LINE — the airlock's one crossing-link), take its
first [[wikilink]] as a vault path, read the doc's frontmatter status. Evaluator contract (the
merge evaluator's, inherited): exit 0 pass; exit 1 with the failed-condition token as stdout's
first line; anything else is UNKNOWN to the caller. Consumers: the epic-flip transition's
`governing-design` evaluator row, and slice 5's crossing invariant — one implementation, cited,
never copied.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records  # noqa: E402
import sources  # noqa: E402

_WIKILINK = re.compile(r"\[\[([^\]|#]+)")


def _source_marker() -> str:
    reg = records.load()
    return records.get(reg, "SOURCE-LINE")["marker"]


def check_body(body: str) -> tuple[int, str]:
    """The pure half: epic body text -> (exit_code, failed-condition token)."""
    marker = _source_marker()
    line = next((ln for ln in (body or "").splitlines() if ln.startswith(marker)), None)
    if line is None:
        return 1, "source_line_missing"
    m = _WIKILINK.search(line)
    if not m:
        return 1, "source_link_missing"
    rel = m.group(1).strip()
    vault = os.environ.get("YR_VAULT_ROOT", "/srv/obsidian/vaults/obsidian")
    path = Path(vault) / (rel if rel.endswith(".md") else rel + ".md")
    ok, text = sources.vault_doc(path)
    if not ok:
        return 1, "design_unresolvable"
    sm = re.search(r"^status:\s*(\S+)", text, flags=re.M)
    if not sm:
        return 1, "design_status_unreadable"
    return (0, "") if sm.group(1) == "active" else (1, "design_not_active")


def name_of(repo: str, issue: str) -> str:
    """The governing design's wikilink target from the epic body's Source line — the epic-flip
    record's `design` field. Empty when unresolvable (the caller falls back loudly)."""
    ok, texts = sources.issue_trail(repo, issue)
    if not ok or not texts:
        return ""
    marker = _source_marker()
    line = next((ln for ln in texts[0].splitlines() if ln.startswith(marker)), "")
    m = _WIKILINK.search(line)
    return m.group(1).strip() if m else ""


def check(repo: str, issue: str) -> int:
    ok, texts = sources.issue_trail(repo, issue)
    if not ok:
        print("epic_body_unreadable")
        return 1
    rc, token = check_body(texts[0] if texts else "")
    if rc != 0:
        print(token)
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the governing-design resolver (evaluator contract)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="exit 0 = the governing design resolves and is active")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True)
    p_n = sub.add_parser("name", help="print the governing design's wikilink target (or nothing)")
    p_n.add_argument("--repo", required=True)
    p_n.add_argument("--issue", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "name":
        n = name_of(args.repo, args.issue)
        if n:
            print(n)
        return 0 if n else 1
    return check(args.repo, args.issue)


if __name__ == "__main__":
    raise SystemExit(main())
