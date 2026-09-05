#!/usr/bin/env python3
"""provenance.py — the one self-locate helper (it-33 slice 2, epic #455, runtime provenance).

Every declared runtime surface states the commit of the whole tree it is executing from, never a
version string alone — the `YR-RELEASE` field grammar's `commit: <sha>` line (records.toml:466-474).
This module is the SINGLE home of the git self-locate read (`factory_commit`) and of the declared
population of surfaces (`SURFACES`); no emission site shells out to `git` on its own.

Four declared surfaces, one per runtime shape:
  * dispatch          — the resident HTTP server (tools/dispatch.py): the statement is captured at
                        import (serve_forever() holds that import closure for the process's whole
                        life), printed on its startup line, and written to `dispatch_statement_path()`
                        so a pull under a running process never changes what it reports.
  * dev-runner        — the per-build runner (tools/dev-runner.sh): shells out to this module's CLI,
                        best-effort, for its run-opening banner.
  * epic-gate         — the org-wide sweep (tools/epic_gate.py): one statement line before acting.
  * attended-session  — the delivered position (tools/compile_slice.py): states BOTH the workspace
                        checkout (root taken from the session's cwd, never `__file__`-relative — a
                        delivery hook runs from the plugin CACHE, not the checkout) and the plugin
                        cache's own HEAD, cross-checked against the installer's recorded commit.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SURFACES = ("dispatch", "dev-runner", "epic-gate", "attended-session")

PLUGIN_ID = "factory@yellow-robots"


def factory_commit(root: Path | str) -> str:
    """`git rev-parse HEAD` under `root` — the whole delivered tree's commit. Never raises: a
    non-git root, a missing `git`, or a timeout all report as `unreadable: <reason>`, because every
    declared surface must still emit ITS statement line even when the read fails."""
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unreadable: {exc}"
    if out.returncode != 0:
        return f"unreadable: {(out.stderr or '').strip() or 'git rev-parse failed'}"
    sha = out.stdout.strip()
    return sha if sha else "unreadable: empty HEAD"


def statement(root: Path | str) -> str:
    """The `commit: <sha>` line every emission site prints verbatim."""
    return f"commit: {factory_commit(root)}"


def dispatch_statement_path(home: Path | str) -> Path:
    """The statement file dispatch writes at startup: `dispatch.statement` in the runner home
    (`home` — the caller passes its own DEV_RUNNER_HOME so the two never drift)."""
    return Path(home) / "dispatch.statement"


def _installed_plugins_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def plugin_cache_root(plugins_path: Path | str | None = None) -> tuple[Path | None, str | None]:
    """Reads `installed_plugins.json` for `factory@yellow-robots`, returning
    `(install_path, recorded_commit)`. Either is None when the file, the entry, or the field is
    missing or unreadable — never raises."""
    path = Path(plugins_path) if plugins_path is not None else _installed_plugins_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    entry = data.get(PLUGIN_ID)
    if not isinstance(entry, dict):
        return None, None
    install_path = entry.get("installPath")
    recorded = entry.get("gitCommitSha")
    return (Path(install_path) if install_path else None,
            recorded if isinstance(recorded, str) and recorded else None)


def plugin_cache_statement(plugins_path: Path | str | None = None) -> str:
    """The cache half of the attended position: the cache's own HEAD, cross-checked both ways
    against the installer's recorded commit — a mismatch is named, never silent."""
    root, recorded = plugin_cache_root(plugins_path)
    if root is None:
        return ("cache commit: unreadable: no factory@yellow-robots entry in "
                "installed_plugins.json")
    actual = factory_commit(root)
    if recorded and not actual.startswith("unreadable") and actual != recorded:
        return f"cache commit: {actual} (installer recorded {recorded} — MISMATCH)"
    return f"cache commit: {actual}"


def main(argv: list[str] | None = None) -> int:
    """CLI: print the checkout statement for ROOT (default `.`) — the best-effort seam
    `tools/dev-runner.sh` shells out to for its run-opening banner."""
    import argparse
    ap = argparse.ArgumentParser(description="print the commit statement for a tree root")
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args(argv)
    print(statement(args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
