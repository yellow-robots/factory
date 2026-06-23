#!/usr/bin/env python3
"""Dispatch endpoint for the dev factory (RFC 0004).

`build_task(issue, repo)` is the reusable core: it fires the dev-runner for one Ready issue under a
NON-BLOCKING flock (single-flight), DETACHED, and returns immediately — the build runs async and the
runner does its own GitHub I/O. An HTTP adapter (POST /build) lets n8n trigger it; the same core wraps
as a YR MCP tool later (one core, two faces).

Config (env): DISPATCH_TOKEN (bearer, required to start the HTTP server), DISPATCH_BIND (default
127.0.0.1), DISPATCH_PORT (default 8770), DEV_RUNNER (default dev-runner.sh next to this file),
DISPATCH_LOCK (default ~/.cache/dev-runner/dispatch.lock), DEFAULT_REPO (default yellow-robots/yellow-robots).
"""
import hmac
import json
import os
import pathlib
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SELF = pathlib.Path(__file__).resolve()
DEV_RUNNER = os.environ.get("DEV_RUNNER", str(SELF.parent / "dev-runner.sh"))
LOCK = os.environ.get("DISPATCH_LOCK", str(pathlib.Path.home() / ".cache" / "dev-runner" / "dispatch.lock"))
DEFAULT_REPO = os.environ.get("DEFAULT_REPO", "yellow-robots/yellow-robots")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _spawn_detached(cmd):
    pathlib.Path(cmd[2]).parent.mkdir(parents=True, exist_ok=True)   # cmd = [flock, -n, <lock>, ...]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


_SPAWN = _spawn_detached   # tests override this


def build_task(issue, repo=None, *, runner=None, lock=None, spawn=None):
    """Reusable core: fire the dev-runner for one issue under a non-blocking flock, detached.
    Returns immediately (the build runs async). All externals injectable for tests; never waits."""
    issue = str(issue).strip()
    if not (issue.isascii() and issue.isdigit()):          # ASCII decimal only — no unicode digits
        return {"ok": False, "error": f"issue must be a decimal number, got {issue!r}"}
    repo = repo or DEFAULT_REPO
    if not _REPO_RE.match(repo):                            # owner/name only — no flags/whitespace/metachars
        return {"ok": False, "error": f"invalid repo {repo!r}"}
    # all validation precedes the spawn — a bad input never launches a build.
    # flock -n: if a build already holds the lock, this invocation exits immediately (single-flight).
    cmd = ["flock", "-n", lock or LOCK, runner or DEV_RUNNER, issue, "--repo", repo]
    (spawn or _SPAWN)(cmd)
    return {"ok": True, "issue": int(issue), "repo": repo, "dispatched": True}


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
        if self.path.rstrip("/") != "/build":
            return self._send(404, {"ok": False, "error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"ok": False, "error": "bad json"})
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
