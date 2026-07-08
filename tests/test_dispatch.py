"""Unit tests for tools/dispatch.py — the spawn is stubbed, so no real build is ever launched."""
import contextlib, json, os, pathlib, signal, sys, threading, time, urllib.error, urllib.request
from http.server import HTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dispatch  # noqa: E402


# ---- build_task core ----

def test_build_task_spawns_flocked_runner():
    # spawn is now always called with (cmd, log_path) — record just cmd, same as before #85.
    calls = []
    r = dispatch.build_task("7", "o/r", runner="/x/run.sh", lock="/tmp/l",
                             spawn=lambda *a: calls.append(a[0]))
    assert r["ok"] and r["dispatched"] and r["issue"] == 7 and r["repo"] == "o/r"
    assert calls == [["flock", "-n", "/tmp/l", "/x/run.sh", "7", "--repo", "o/r"]]


def test_build_task_rejects_non_numeric():
    calls = []
    r = dispatch.build_task("7; rm -rf /", spawn=calls.append)
    assert not r["ok"] and calls == []          # rejected up front, nothing spawned


def test_build_task_rejects_missing_repo():
    calls = []
    r = dispatch.build_task("3", spawn=calls.append, runner="/r", lock="/l")   # no repo
    assert not r["ok"] and calls == []                  # fail-closed: no default, nothing spawned
    r2 = dispatch.build_task("3", "   ", spawn=calls.append)                    # whitespace-only repo
    assert not r2["ok"] and calls == []


def test_build_task_rejects_unicode_digit():
    calls = []
    r = dispatch.build_task("²", spawn=calls.append)   # superscript 2: isdigit() True but not decimal
    assert not r["ok"] and calls == []                       # rejected before spawn, no int() crash


def test_build_task_rejects_bad_repo():
    calls = []
    r = dispatch.build_task("5", "evil repo; rm -rf", spawn=calls.append)
    assert not r["ok"] and calls == []


# ---- run_sweep core ----

def test_run_sweep_spawns_flocked_sweeper():
    calls = []
    r = dispatch.run_sweep(sweeper="/x/epic_gate.py", lock="/tmp/sweep.lock", spawn=calls.append)
    assert r["ok"] and r["dispatched"]
    assert calls == [["flock", "-n", "/tmp/sweep.lock", "/x/epic_gate.py"]]


def test_run_sweep_takes_no_issue_or_repo_args():
    calls = []
    r = dispatch.run_sweep(spawn=calls.append)   # no issue/repo — org-wide, board is the input
    assert r["ok"] and r["dispatched"]
    assert len(calls) == 1 and len(calls[0]) == 4   # flock, -n, <lock>, <sweeper> — nothing else appended


def test_sweep_lock_distinct_from_build_lock():
    # default locks (no override) must differ so a build never blocks/blocks-on a sweep
    assert dispatch.SWEEP_LOCK != dispatch.LOCK

    build_calls, sweep_calls = [], []
    dispatch.build_task("7", "o/r", runner="/x/run.sh", spawn=lambda *a: build_calls.append(a[0]))
    dispatch.run_sweep(sweeper="/x/epic_gate.py", spawn=sweep_calls.append)
    build_lock_path = build_calls[0][2]
    sweep_lock_path = sweep_calls[0][2]
    assert build_lock_path != sweep_lock_path
    assert build_lock_path == dispatch.LOCK
    assert sweep_lock_path == dispatch.SWEEP_LOCK


def test_epic_sweeper_default_is_executable():
    # flock execs the sweeper directly (run_sweep's argv), detached with stderr to DEVNULL — a missing
    # exec bit means every /sweep 202s then dies silently (exit 126). Git checkouts preserve mode bits,
    # so pin the bit here.
    assert os.access(dispatch.EPIC_SWEEPER, os.X_OK)


# ---- HTTP adapter ----

@contextlib.contextmanager
def _server(token="secret"):
    os.environ["DISPATCH_TOKEN"] = token
    calls = []
    orig = dispatch._SPAWN
    dispatch._SPAWN = lambda *a: calls.append(a[0])   # no real spawn; record just cmd (2nd arg = log_path)
    srv = HTTPServer(("127.0.0.1", 0), dispatch.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", calls
    finally:
        srv.shutdown()
        dispatch._SPAWN = orig


def _post(url, body, token=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_requires_token():
    with _server() as (url, calls):
        assert _post(url + "/build", {"issue": 5})[0] == 401              # missing token
        assert _post(url + "/build", {"issue": 5}, token="wrong")[0] == 401
        assert calls == []                                                # never reached build_task


def test_http_bad_issue_400():
    with _server() as (url, calls):
        code, _ = _post(url + "/build", {"issue": "nope"}, token="secret")
        assert code == 400 and calls == []


def test_http_wrong_path_404():
    with _server() as (url, _calls):
        assert _post(url + "/nope", {"issue": 5}, token="secret")[0] == 404


def test_http_happy_202_spawns_once():
    with _server() as (url, calls):
        code, body = _post(url + "/build", {"issue": 5, "repo": "o/r"}, token="secret")
        assert code == 202 and body["dispatched"] and body["issue"] == 5
        assert len(calls) == 1 and calls[0][:2] == ["flock", "-n"] and "5" in calls[0]


def test_http_missing_repo_400_no_spawn():
    with _server() as (url, calls):
        code, _ = _post(url + "/build", {"issue": 5}, token="secret")   # no repo → fail-closed
        assert code == 400 and calls == []                              # endpoint refuses a repo-less dispatch


def test_http_unicode_digit_400_no_spawn():
    with _server() as (url, calls):
        code, _ = _post(url + "/build", {"issue": "²"}, token="secret")
        assert code == 400 and calls == []                  # bad input never spawns a build


def test_http_malformed_json_400():
    with _server() as (url, calls):
        req = urllib.request.Request(url + "/build", data=b"not json", method="POST")
        req.add_header("Authorization", "Bearer secret")
        try:
            with urllib.request.urlopen(req) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 400 and calls == []


# ---- /sweep HTTP adapter ----

def test_http_sweep_requires_token():
    with _server() as (url, calls):
        assert _post(url + "/sweep", {})[0] == 401                       # missing token
        assert _post(url + "/sweep", {}, token="wrong")[0] == 401        # wrong token
        assert calls == []                                               # never reached run_sweep


def test_http_sweep_happy_202_spawns_once():
    with _server() as (url, calls):
        code, body = _post(url + "/sweep", {}, token="secret")
        assert code == 202 and body["ok"] and body["dispatched"]
        assert len(calls) == 1 and calls[0][:2] == ["flock", "-n"]


def test_http_sweep_no_body_required():
    with _server() as (url, calls):
        req = urllib.request.Request(url + "/sweep", data=b"", method="POST")
        req.add_header("Authorization", "Bearer secret")
        with urllib.request.urlopen(req) as resp:
            code = resp.status
        assert code == 202 and len(calls) == 1


def test_http_sweep_uses_lock_distinct_from_build_lock():
    with _server() as (url, calls):
        _post(url + "/build", {"issue": 5, "repo": "o/r"}, token="secret")
        _post(url + "/sweep", {}, token="secret")
        assert len(calls) == 2
        build_lock = calls[0][2]
        sweep_lock = calls[1][2]
        assert build_lock != sweep_lock


def test_http_unknown_path_404_still_enforced_with_sweep_route_present():
    with _server() as (url, calls):
        assert _post(url + "/nope", {}, token="secret")[0] == 404
        assert calls == []


# ---- persisted per-run output (issue #85) ----
# These exercise the REAL spawn path (dispatch's own _spawn_detached, not the injectable stub), since the
# behavior under test — a runner's stdout+stderr landing on disk under a discoverable name, surviving a
# hard kill — lives in that seam, not in build_task's argv construction (already covered above).

def _wait_for(predicate, timeout=5, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _script(path, body):
    path.write_text(f"#!/bin/bash\n{body}\n")
    path.chmod(0o755)
    return path


def test_build_task_persists_combined_stdout_stderr_to_a_discoverable_log(tmp_path):
    runner = _script(tmp_path / "runner.sh", 'echo "out-marker $1"\necho "err-marker" >&2\n')
    runs_dir = tmp_path / "runs"
    r = dispatch.build_task("42", "o/r", runner=str(runner), lock=str(tmp_path / "lock"),
                             runs_dir=str(runs_dir))
    assert r["ok"] and r["dispatched"]
    log_path = pathlib.Path(r["log"])
    assert log_path.parent == runs_dir                      # discoverable under the runs home
    assert "42" in log_path.name                             # discoverable from the issue number
    assert _wait_for(lambda: log_path.exists() and "err-marker" in log_path.read_text())
    content = log_path.read_text()
    assert "out-marker 42" in content and "err-marker" in content   # both streams, combined


def test_build_task_log_lives_under_runs_dir_default(tmp_path):
    # no runs_dir override: falls back to dispatch.RUNS_DIR (DEV_RUNNER_HOME/runs) — same home the
    # runner itself uses for its own RUN_DIR, so the two are siblings under one discoverable root.
    calls = []
    r = dispatch.build_task("9", "o/r", runner="/x/run.sh", lock="/tmp/l",
                             spawn=lambda *a: calls.append(a[0]))
    log_path = pathlib.Path(r["log"])
    assert log_path.parent == pathlib.Path(dispatch.RUNS_DIR)
    assert log_path.name.startswith("dispatch-9-") and log_path.name.endswith(".log")


def test_rejected_build_never_creates_a_log_file(tmp_path):
    # fail-closed: validation runs before the log file (and the spawn) — a refused dispatch leaves no
    # trace a runner ever started, matching "a refused ... runner stays invisible to n8n".
    runs_dir = tmp_path / "runs"
    r = dispatch.build_task("not-a-number", "o/r", runs_dir=str(runs_dir))
    assert not r["ok"]
    assert not runs_dir.exists() or not list(runs_dir.glob("*.log"))


def test_build_task_survives_a_hard_kill_of_the_runner(tmp_path):
    pidfile = tmp_path / "pid"
    runner = _script(tmp_path / "runner.sh", f'''echo "before-kill"
echo $$ > {pidfile}
sleep 30
echo "after-kill"
''')
    runs_dir = tmp_path / "runs"
    r = dispatch.build_task("13", "o/r", runner=str(runner), lock=str(tmp_path / "lock"),
                             runs_dir=str(runs_dir))
    log_path = pathlib.Path(r["log"])
    assert _wait_for(pidfile.exists), "runner never started"
    pid = int(pidfile.read_text().strip())
    os.kill(pid, signal.SIGKILL)
    assert _wait_for(lambda: log_path.exists() and "before-kill" in log_path.read_text())
    time.sleep(0.3)   # give the killed process's exit a moment to settle before the final read
    content = log_path.read_text()
    assert "before-kill" in content
    assert "after-kill" not in content   # died before it could get there — the partial log survives


def test_http_build_answers_before_the_runner_finishes_and_still_persists_its_output(tmp_path):
    # fire-and-forget contract: n8n's response must not wait on the runner. A short sleep before the
    # marker makes "answered first" observable without a flaky race.
    runner = _script(tmp_path / "runner.sh", 'sleep 1\necho "fire-and-forget-marker"\n')
    runs_dir = tmp_path / "runs"
    os.environ["DISPATCH_TOKEN"] = "secret"
    orig_runner, orig_runs, orig_lock = dispatch.DEV_RUNNER, dispatch.RUNS_DIR, dispatch.LOCK
    dispatch.DEV_RUNNER, dispatch.RUNS_DIR, dispatch.LOCK = str(runner), str(runs_dir), str(tmp_path / "lock")
    srv = HTTPServer(("127.0.0.1", 0), dispatch.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        t0 = time.monotonic()
        code, body = _post(url + "/build", {"issue": 21, "repo": "o/r"}, token="secret")
        elapsed = time.monotonic() - t0
        assert code == 202 and body["dispatched"]
        assert elapsed < 0.8, "the HTTP response waited on the (1s-sleeping) runner"
        log_path = pathlib.Path(body["log"])
        assert _wait_for(lambda: log_path.exists() and "fire-and-forget-marker" in log_path.read_text())
    finally:
        srv.shutdown()
        dispatch.DEV_RUNNER, dispatch.RUNS_DIR, dispatch.LOCK = orig_runner, orig_runs, orig_lock
