#!/usr/bin/env python3
"""compile_slice.py — the delivered slice's position half + the delivery boundary gate
(it-31 slice 8, epic #432; supersedes the it-30 slice-4 canon splicer).

The STATIC half is generated from the process model (`process.py compile slice` ->
`build/slice-static.md`, committed with the model): `hooks/deliver.sh` serves that artifact
verbatim and appends the position element this module composes at delivery time. The old
canon-table splice is retired — a hand map beside a generated one is a drift twin, and the model
rules on any disagreement.

Two entry points, both for the delivery hook:
  --in-scope DIR   the boundary gate: exit 0 inside the factory's declared world, exit 3 outside
                   (a clean verdict — delivery stays silent), anything else is a FAILURE the hook
                   banners loudly (a crash is never silence: it must not lock the human out, and
                   it must not quietly kill delivery in a factory session either).
  --position DIR   the runtime position element, composed at delivery and never cached: the workspace
                   checkout's own commit (DIR — the session's `$CWD`, never `__file__`-relative) and
                   the plugin cache's commit (cross-checked against the installer's record), the
                   stored probe-drift note, the repo, its open PRs, and this repo's board rows —
                   every read bounded, every failure a loud line, exit always 0.
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402 — sibling import, tools/ is on sys.path (line above)


def _run(argv: list[str], timeout: int) -> tuple[int, str]:
    """The ONLY subprocess seam — stubbed whole in tests; a timeout or missing binary is rc 1."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return out.returncode, out.stdout or ""


def position(root: Path) -> str:
    """The runtime position — repo-aware, never hardcoded (B5: a factory-hardcoded read told a
    website session the factory's PRs were its position). Loud, non-blocking throughout.

    `root` is the session's own working directory (the caller's `$CWD`), never `__file__`-relative —
    this runs from `hooks/deliver.sh`, which executes from the plugin CACHE, not the workspace
    checkout it must state. States BOTH declared halves (it-33 slice 2): the workspace checkout at
    `root`, and the plugin cache's own HEAD, cross-checked against the installer's recorded commit."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    lines = [f"\n## Position (composed at delivery — {ts})\n"]
    lines.append(f"Checkout {provenance.statement(root)}")
    lines.append(f"Plugin {provenance.plugin_cache_statement()}")
    rc, deg = _run(["python3", str(root / "tools" / "process.py"), "decay", "--stored-note"], 10)
    if rc == 0 and deg.strip():
        lines.append(deg.strip())
    rc, repo = _run(["gh", "repo", "view", "--json", "nameWithOwner",
                     "--jq", ".nameWithOwner"], 10)
    repo = (repo or "").strip()
    if rc != 0 or not repo:
        lines.append("Position unavailable: this directory resolves to no GitHub repo "
                     "(loud, non-blocking) — read the board by hand.")
        return "\n".join(lines) + "\n"
    lines.append(f"Repo: {repo}")
    rc, prs = _run(["gh", "pr", "list", "--repo", repo, "--state", "open",
                    "--json", "number,title,mergeStateStatus",
                    "--jq", 'map("PR#\\(.number) \\(.mergeStateStatus): \\(.title)") | join("\\n")'],
                   15)
    if rc == 0:
        lines.append(f"Open PRs:\n{prs.strip()}" if prs.strip() else "No open PRs.")
    else:
        lines.append("PR read unavailable (gh failed or timed out) — loud, non-blocking.")
    rc, board = _run(["bash", str(root / "tools" / "board.sh")], 20)
    if rc == 0 and board.strip():
        # board.sh's TSV: number, nameWithOwner, itype, status, reason, title — the filter matches
        # the FULL owner/name (the slice-8 review: a short-name compare matched nothing, ever)
        rows = []
        for line in board.splitlines():
            f = line.split("\t")
            if len(f) >= 6 and f[1] == repo:
                mark = f[3] + (f" · {f[4]}" if f[4].strip() else "")
                rows.append(f"  #{f[0]} [{mark}] {f[5]}")
        if rows:
            lines.append("Board (this repo, open items):\n" + "\n".join(rows[:12]))
    return "\n".join(lines) + "\n"


def in_scope_gate(target: str) -> int:
    """Delegates to the engine's own boundary (`process.in_scope`) — one rule, one home. Exit 0
    inside; 3 outside (clean silence); a load/evaluation failure propagates as an exception the
    CLI turns into exit 2 with the reason on stderr (the hook banners it)."""
    import process
    model = process.load()
    return 0 if process.in_scope(model, Path(target)) else 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the delivered slice's position half + boundary gate")
    ap.add_argument("--position", metavar="DIR", default=None,
                    help="print the runtime position element for the session's workspace root DIR "
                         "(never __file__-relative — this module may itself be running from the "
                         "plugin cache, not the checkout it must state)")
    ap.add_argument("--in-scope", metavar="DIR", default=None,
                    help="boundary gate: exit 0 inside, 3 outside, else failure")
    args = ap.parse_args(argv)
    if args.in_scope is not None:
        try:
            return in_scope_gate(args.in_scope)
        except Exception as e:  # noqa: BLE001 — a crash must reach the hook AS a failure, loudly
            print(f"compile_slice: boundary check failed: {e}", file=sys.stderr)
            return 2
    if args.position is not None:
        sys.stdout.write(position(Path(args.position)))
        return 0
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
