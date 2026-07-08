#!/usr/bin/env python3
"""Dispatch endpoint for the dev factory (RFC 0004).

`build_task(issue, repo)` is the reusable core: it fires the dev-runner for one Ready issue under a
NON-BLOCKING flock (single-flight), DETACHED, and returns immediately — the build runs async and the
runner does its own GitHub I/O. An HTTP adapter (POST /build) lets n8n trigger it; the same core wraps
as a YR MCP tool later (one core, two faces).

`run_sweep()` is the same shape for the org-wide epic-gate sweep (RFC — epic-gate sweep): it fires
`epic_gate.py` under its own NON-BLOCKING flock on a SEPARATE lock, DETACHED, and returns immediately.
POST /sweep wraps it. The sweep takes no issue/repo — the board is org-wide and the tool does its own
GitHub I/O — so dispatch here only flocks + spawns, same seam as build_task.

Config (env): DISPATCH_TOKEN (bearer, required to start the HTTP server), DISPATCH_BIND (default
127.0.0.1), DISPATCH_PORT (default 8770), DEV_RUNNER (default dev-runner.sh next to this file),
DISPATCH_LOCK (default ~/.cache/dev-runner/dispatch.lock), EPIC_SWEEPER (default epic_gate.py next to
this file), SWEEP_LOCK (default ~/.cache/dev-runner/epic-sweep.lock — distinct from DISPATCH_LOCK, so a
sweep never blocks or is blocked by a build), DEV_RUNNER_HOME (default ~/.cache/dev-runner — same home the
runner itself uses for its `runs/` dir). Dispatch is fail-closed: every /build request must carry an
explicit repo (owner/name) — there is no default repo, so a missing/unroutable repo never builds.

The runner is spawned detached (start_new_session, no parent to inherit a terminal from), so its
stdout+stderr are captured into a per-run log file under DEV_RUNNER_HOME/runs/ (`dispatch-<issue>-<epoch
ms>.log`) rather than a terminal — otherwise a failure outside a per-stage log file (e.g. the runner dying
before it can write anything of its own) is untraceable. The file is opened by dispatch itself, before the
spawn, so a hard-killed runner still leaves whatever it managed to write; the actual runs/ directory is
never cleaned up by the runner's own teardown (tools/dev-runner.sh's cleanup_wt), so the log outlives any
run-failure disposal. This capture is orthogonal to the runner's own stdio: an attended `dev-runner.sh`
invocation (an operator's terminal, not dispatch) is never routed through this file and keeps printing to
the terminal exactly as before.
"""
import hmac
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SELF = pathlib.Path(__file__).resolve()
DEV_RUNNER = os.environ.get("DEV_RUNNER", str(SELF.parent / "dev-runner.sh"))
DEV_RUNNER_HOME = os.environ.get("DEV_RUNNER_HOME", str(pathlib.Path.home() / ".cache" / "dev-runner"))
LOCK = os.environ.get("DISPATCH_LOCK", str(pathlib.Path.home() / ".cache" / "dev-runner" / "dispatch.lock"))
EPIC_SWEEPER = os.environ.get("EPIC_SWEEPER", str(SELF.parent / "epic_gate.py"))
SWEEP_LOCK = os.environ.get("SWEEP_LOCK", str(pathlib.Path.home() / ".cache" / "dev-runner" / "epic-sweep.lock"))
RUNS_DIR = os.environ.get("RUNS_DIR", str(pathlib.Path(DEV_RUNNER_HOME) / "runs"))
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _spawn_detached(cmd, log_path=None):
    pathlib.Path(cmd[2]).parent.mkdir(parents=True, exist_ok=True)   # cmd = [flock, -n, <lock>, ...]
    if log_path is None:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return
    # opened by dispatch, handed to the child as its stdout/stderr fd: writes land on disk as the child
    # makes them, so a SIGKILL (or any hard teardown) still leaves the log's prefix intact. Closing our
    # end right after Popen is safe — the child holds its own dup of the fd.
    log_path = pathlib.Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log_f:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log_f,
                         stderr=subprocess.STDOUT, start_new_session=True)


_SPAWN = _spawn_detached   # tests override this


def build_task(issue, repo=None, *, runner=None, lock=None, spawn=None, runs_dir=None):
    """Reusable core: fire the dev-runner for one issue under a non-blocking flock, detached.
    Returns immediately (the build runs async). All externals injectable for tests; never waits."""
    issue = str(issue).strip()
    if not (issue.isascii() and issue.isdigit()):          # ASCII decimal only — no unicode digits
        return {"ok": False, "error": f"issue must be a decimal number, got {issue!r}"}
    repo = (repo or "").strip()
    if not repo:                                            # fail-closed: no default — every dispatch must route explicitly
        return {"ok": False, "error": "repo is required (no default); dispatch is fail-closed"}
    if not _REPO_RE.match(repo):                            # owner/name only — no flags/whitespace/metachars
        return {"ok": False, "error": f"invalid repo {repo!r}"}
    # all validation precedes the spawn — a bad input never launches a build.
    # flock -n: if a build already holds the lock, this invocation exits immediately (single-flight).
    cmd = ["flock", "-n", lock or LOCK, runner or DEV_RUNNER, issue, "--repo", repo]
    log_path = pathlib.Path(runs_dir or RUNS_DIR) / f"dispatch-{issue}-{int(time.time() * 1000)}.log"
    (spawn or _SPAWN)(cmd, log_path)
    return {"ok": True, "issue": int(issue), "repo": repo, "dispatched": True, "log": str(log_path)}


def run_sweep(*, sweeper=None, lock=None, spawn=None):
    """Reusable core: fire the org-wide epic-gate sweep under its own non-blocking flock, detached.
    Returns immediately. Takes no issue/repo — the sweep tool reads/writes the board itself; dispatch
    only flocks + spawns, on a lock separate from the build lock so neither blocks the other."""
    cmd = ["flock", "-n", lock or SWEEP_LOCK, sweeper or EPIC_SWEEPER]
    (spawn or _SPAWN)(cmd)
    return {"ok": True, "dispatched": True}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        token = os.environ.get("DISPATCH_TOKEN", "")
        auth = self.headers.get("Authorization", "")
        if not token or not hmac.compare_digest(auth, f"Bearer {token}"):   # constant-time
            return self._send(401, {"ok": False, "error": "unauthorized"})
        path = self.path.rstrip("/")
        if path not in ("/build", "/sweep"):
            return self._send(404, {"ok": False, "error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"ok": False, "error": "bad json"})
        if path == "/sweep":
            res = run_sweep()
        else:
            res = build_task(data.get("issue"), data.get("repo"))
        self._send(202 if res["ok"] else 400, res)

    def log_message(self, *args):   # keep the server quiet
        pass


def main():
    if not os.environ.get("DISPATCH_TOKEN"):
        print("dispatch: refusing to start without DISPATCH_TOKEN", file=sys.stderr)
        return 2
    bind = os.environ.get("DISPATCH_BIND", "127.0.0.1")
    port = int(os.environ.get("DISPATCH_PORT", "8770"))
    print(f"dispatch: listening on {bind}:{port}", file=sys.stderr)
    HTTPServer((bind, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
