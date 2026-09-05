#!/usr/bin/env python3
"""drift.py — the one drift alarm: two moments, per-host population (it-33 slice 4, epic #455;
issue #458). Depends on slice 2 (`provenance.py`, issue #457).

Two callers, two moments, ONE alarm: `tools/compile_slice.py:position()` at attended session start,
and `tools/epic_gate.py:main()` at each sweep — both call this module's functions directly, never a
subprocess, so the check runs on a path that needs no runner build. The runner's own pre-existing
staleness warning (issue #58, `tools/dev-runner.sh`) is this alarm's RUNNER-SIDE instance under the
same population rule — left in place, its comment reworded to say so; there is one alarm, not two.

Population = `provenance.SURFACES`, split by what each host can actually read — no cross-host read
(spec callout (k)):
  * workspace host (the attended session) reads `attended-session` two ways — the session's own
    checkout AND the plugin cache, each independently — and cannot read `dispatch`, `dev-runner`,
    or `epic-gate` (those run on the build host).
  * build host (the sweep) reads `epic-gate` and `dev-runner` from its own checkout (the one tree
    both run from) and `dispatch` from its captured statement file, and cannot read
    `attended-session` (that runs on a workspace host).

Each readable surface is compared against ITS OWN checkout's `origin/main` tip — a bounded
`git ls-remote origin main` (the `tools/sources.py` discipline: a timeout is a finding, never a
crash), fetched ONCE per report and reused for every surface it prices — one report is one
decision, so a plain local variable is the per-decision cache. Silent when a surface is clean; a
finding names either the lag or why the surface could not be read.

Tier contract (mirrors `process.py`'s check_drift, header lines 10-13): ADVISORY, loud, never
`check_cmd`, CI, or a merge condition.

Slice 6 (issue #462, epic #455) adds the deploy-record comparison, `deploy_record_findings`: the
latest `YR-DEPLOY` record on the deploy trail issue (read through `tools/sources.py issue_trail` —
the ONLY trail read in this module) against each build-host surface it names, on THIS host's own
live version statement. Readable only at the sweep (`epic_gate.py:main()`) — a deploy record only
ever describes a build-host surface (`dispatch`/`dev-runner`/`epic-gate`), which the workspace-host
moment cannot read anyway (see `workspace_findings`'s own per-host population rule above).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402 — sibling import, tools/ is on sys.path (line above)
import records     # noqa: E402
import sources     # noqa: E402
import textutil    # noqa: E402

LS_REMOTE_TIMEOUT = 10

_UNREADABLE_ELSEWHERE = "not readable from this host — no cross-host read"


def _run(argv: list[str], timeout: int) -> tuple[int, str]:
    """The one subprocess seam here — bounded, never raises (a timeout or missing binary is rc 1)."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return out.returncode, out.stdout or ""


def _origin_main_sha(repo_dir: Path | str) -> tuple[bool, str]:
    """Bounded `git -C repo_dir ls-remote origin main`. Never raises: `(False, reason)` on any
    failure — offline, no origin, a timeout — so a report always finishes."""
    rc, out = _run(["git", "-C", str(repo_dir), "ls-remote", "origin", "main"], LS_REMOTE_TIMEOUT)
    if rc != 0:
        return False, "git ls-remote origin main failed"
    sha = out.split()[0] if out.strip() else ""
    return (True, sha) if sha else (False, "empty ls-remote")


def _finding(name: str, commit: str, origin_ok: bool, origin: str) -> str | None:
    """None when `name` is clean; a line naming either an unreadable local commit or a lag against
    origin/main. Silent when `origin` itself could not be read — that failure is reported once by
    the caller, never repeated per surface."""
    if commit.startswith("unreadable"):
        return f"{name}: UNREADABLE — {commit.removeprefix('unreadable: ')}"
    if not origin_ok:
        return None
    if commit != origin:
        return f"{name}: TRAILS origin/main (at {commit[:12]}, origin/main at {origin[:12]})"
    return None


def workspace_findings(root: Path | str, plugins_path: Path | str | None = None) -> list[str]:
    """The workspace-host moment (`compile_slice.py:position()`, attended session start)."""
    origin_ok, origin = _origin_main_sha(root)
    findings: list[str] = []
    if not origin_ok:
        findings.append(f"origin/main: UNREADABLE — {origin}")
    f = _finding("attended-session (checkout)", provenance.factory_commit(root), origin_ok, origin)
    if f:
        findings.append(f)
    cache_root, _ = provenance.plugin_cache_root(plugins_path)
    if cache_root is None:
        findings.append("attended-session (plugin cache): UNREADABLE — no factory@yellow-robots "
                        "entry in installed_plugins.json")
    else:
        f = _finding("attended-session (plugin cache)", provenance.factory_commit(cache_root),
                     origin_ok, origin)
        if f:
            findings.append(f)
    for name in ("dispatch", "dev-runner", "epic-gate"):
        findings.append(f"{name}: {_UNREADABLE_ELSEWHERE}")
    return findings


def build_findings(repo_dir: Path | str, home: Path | str) -> list[str]:
    """The build-host moment (`epic_gate.py:main()`, each sweep)."""
    origin_ok, origin = _origin_main_sha(repo_dir)
    findings: list[str] = []
    if not origin_ok:
        findings.append(f"origin/main: UNREADABLE — {origin}")
    checkout_commit = provenance.factory_commit(repo_dir)
    for name in ("epic-gate", "dev-runner"):
        f = _finding(name, checkout_commit, origin_ok, origin)
        if f:
            findings.append(f)
    stmt_path = provenance.dispatch_statement_path(home)
    try:
        raw = stmt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        findings.append(f"dispatch: UNREADABLE — {exc}")
    else:
        commit = raw.removeprefix("commit: ")
        f = _finding("dispatch", commit, origin_ok, origin)
        if f:
            findings.append(f)
    findings.append(f"attended-session: {_UNREADABLE_ELSEWHERE}")
    return findings


# ── the deploy-record comparison (slice 6, issue #462): readable only at the sweep ─────────────────

DEPLOY_TRAIL_REPO = "yellow-robots/factory"
DEPLOY_TRAIL_ISSUE = "464"

# The build-host surfaces a `YR-DEPLOY` record's `surface` field may name — exactly the three
# build-host entries of `provenance.SURFACES` (never `attended-session`: that runs on a workspace
# host, which a deploy act never touches).
_DEPLOY_SURFACES = ("dispatch", "dev-runner", "epic-gate")


def _deploy_field(lines: list[str], field: str) -> str | None:
    """One field's value off a marker-carrying record's own lines — `<field>: <value>`, matching
    `check_trail.py`'s `_missing_fields` grammar (a line, lstripped, starting with `<field>:`)."""
    prefix = f"{field}:"
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None


def _parse_deploy_records(texts: list[str]) -> list[dict]:
    """Every well-formed `YR-DEPLOY` record among `texts`, IN TRAIL ORDER, as
    `{"surface", "commit", "restart"}` dicts. A record missing `surface` or `commit` is skipped,
    never mistaken for a complete one (mirrors the grammar `check_trail.py`'s `_missing_fields`
    enforces — a record must be complete within ONE text). `restart` is the lowercased, stripped
    field text, or `""` when the field is absent — never mistaken for a stated `"no"`. Reads
    `records.toml`'s own row for the marker, never a hardcoded string, so a canon-side marker
    change is never silently missed here."""
    reg = records.load()
    row = records.get(reg, "YR-DEPLOY")
    marker = row["marker"]
    out: list[dict] = []
    for text in texts:
        lines = text.splitlines()
        if not any(textutil.marker_line_matches(l, marker, mode=textutil.MARKER_PREFIX) for l in lines):
            continue
        surface = _deploy_field(lines, "surface")
        commit = _deploy_field(lines, "commit")
        restart = _deploy_field(lines, "restart")
        if surface and commit:
            out.append({"surface": surface, "commit": commit,
                       "restart": (restart or "").strip().lower()})
    return out


def _surface_statement(name: str, checkout_root: Path | str, home: Path | str) -> str | None:
    """One build-host surface's own live version statement, mirroring `build_findings` above:
    `dispatch` reads its captured statement file (a resident process, statement fixed at import);
    `dev-runner`/`epic-gate` read the checkout's own HEAD (they recompute fresh on every
    invocation — no cache, so a successful `git pull` alone already carries them). `None` for a
    surface name outside `_DEPLOY_SURFACES` — nothing declared to compare against."""
    if name not in _DEPLOY_SURFACES:
        return None
    if name == "dispatch":
        stmt_path = provenance.dispatch_statement_path(home)
        try:
            raw = stmt_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            return f"unreadable: {exc}"
        return raw.removeprefix("commit: ")
    return provenance.factory_commit(checkout_root)


def deploy_record_findings(checkout_root: Path | str, home: Path | str, *,
                           repo: str = DEPLOY_TRAIL_REPO, issue: str = DEPLOY_TRAIL_ISSUE) -> list[str]:
    """The sweep-only moment: the deploy trail's `YR-DEPLOY` records (read LIVE through
    `tools/sources.py issue_trail` — the one trail read in this module), against each build-host
    surface the LATEST record names, on THIS host's own live statement. `dev-runner`/`epic-gate`
    recompute fresh on every invocation, so they are judged against the latest record's commit
    regardless of its `restart` value. `dispatch` is a resident process: a `restart: no` deploy
    LEGITIMATELY leaves it on its prior commit — that is never drift — so dispatch is judged
    against the latest record that actually claims `restart: yes` (silent when none exists yet,
    e.g. every deploy so far left the closure untouched); a genuinely stale record (someone hand-
    pulled and hand-restarted without ever posting one) still surfaces as a disagreement, because
    the live statement has moved past what that last `restart: yes` record claimed.

    Silent when everything agrees, when the trail cannot be read (a bounded, never-raising fetch —
    the caller still gets a named finding, not a crash), or when no `YR-DEPLOY` record exists yet.
    A finding per disagreeing or unreadable named surface; an unrecognized surface name is itself a
    finding (the record names something this alarm has no live statement for)."""
    ok, texts = sources.issue_trail(repo, str(issue))
    if not ok:
        return [f"deploy-record ({repo}#{issue}): UNREADABLE — {texts}"]
    parsed = _parse_deploy_records(texts)
    if not parsed:
        return []
    latest = parsed[-1]
    latest_restart_yes = next((r for r in reversed(parsed) if r["restart"] == "yes"), None)

    findings: list[str] = []
    for name in [s.strip() for s in latest["surface"].split(",") if s.strip()]:
        if name == "dispatch":
            if latest_restart_yes is None:
                continue   # never claimed a restart yet -- nothing to judge dispatch against
            commit = latest_restart_yes["commit"]
        elif name in _DEPLOY_SURFACES:
            commit = latest["commit"]
        else:
            findings.append(f"deploy-record: {name}: not a recognized build-host surface")
            continue
        # `name` is one of `_DEPLOY_SURFACES` on every path that reaches here (the unrecognized
        # case already `continue`d above), so `_surface_statement` never returns None below.
        live = _surface_statement(name, checkout_root, home)
        if live.startswith("unreadable"):
            findings.append(f"deploy-record: {name}: UNREADABLE — {live.removeprefix('unreadable: ')}")
        elif commit != live:
            findings.append(f"deploy-record: {name}: DISAGREES (record says {commit[:12]}, "
                            f"live states {live[:12]})")
    return findings


def main(argv: list[str] | None = None) -> int:
    """CLI: `drift.py workspace ROOT [--plugins PATH]` / `drift.py build ROOT --home HOME` — a
    standalone diagnostic path; the two callers import this module's functions directly (no
    subprocess, no runner build). Advisory: loud, exit 1 on any finding, never a gate."""
    ap = argparse.ArgumentParser(description="the one drift alarm — per-host population")
    sub = ap.add_subparsers(dest="mode", required=True)
    p_ws = sub.add_parser("workspace", help="the workspace-host moment (attended session start)")
    p_ws.add_argument("root")
    p_ws.add_argument("--plugins", default=None)
    p_bd = sub.add_parser("build", help="the build-host moment (each sweep)")
    p_bd.add_argument("root")
    p_bd.add_argument("--home", required=True)
    args = ap.parse_args(argv)
    if args.mode == "workspace":
        findings = workspace_findings(args.root, args.plugins)
    else:
        findings = build_findings(args.root, args.home)
    for f in findings:
        print(f"drift: {f}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
