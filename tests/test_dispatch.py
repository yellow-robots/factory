"""Unit tests for tools/dispatch.py — the spawn is stubbed, so no real build is ever launched."""
import contextlib, fcntl, importlib, json, os, pathlib, re, signal, subprocess, sys, threading, time
import urllib.error, urllib.request
from http.server import HTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dispatch  # noqa: E402


def _capture_cmd(**kwargs):
    """Call `build_task`, capturing the composed argv it would have spawned (never actually run). The
    lock home is created up front — the real `_spawn_detached` seam does this itself; bypassing it here
    (to run the composed argv synchronously) means the test must do that part manually."""
    lock_home = kwargs.get("lock_home")
    if lock_home:
        pathlib.Path(lock_home).mkdir(parents=True, exist_ok=True)
    calls = []
    dispatch.build_task(spawn=lambda *a: calls.append(a[0]), **kwargs)
    return calls[0]


def _hold_lock(path):
    """Open+flock `path` exclusively from THIS process — a canned 'busy' lock state a subprocess's own
    `flock -n` correctly contends against. Keep the returned handle referenced; closing it releases the
    lock."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w")
    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return f


# ---- build_task core ----

def test_build_task_spawns_flocked_runner():
    # spawn is now always called with (cmd, log_path) — record just cmd, same as before #85. The lock is
    # now composed: the repo lock acquired OUTERMOST (reserved busy code -E 200), then one capacity slot
    # per DISPATCH_MAX_BUILDS (epic #126 — per-repo locks + a global cap, superseding single-flight).
    calls = []
    r = dispatch.build_task("7", "o/r", runner="/x/run.sh", lock="/tmp/repo.lock", lock_home="/tmp",
                             max_builds=2, spawn=lambda *a: calls.append(a[0]))
    assert r["ok"] and r["dispatched"] and r["issue"] == 7 and r["repo"] == "o/r"
    cmd = calls[0]
    assert cmd[:5] == ["flock", "-n", "-E", "200", "/tmp/repo.lock"]   # repo lock OUTERMOST, reserved code
    assert cmd[5:7] == ["bash", "-c"]
    script = cmd[-1]
    assert "/x/run.sh 7 --repo o/r" in script                   # the runner invocation, embedded verbatim
    assert script.count("flock -n -E 200") == 2                 # one flock per capacity slot (max_builds=2)
    assert "capslot-0.lock" in script and "capslot-1.lock" in script
    assert "exit 201" in script                                 # a runner's own 200 is reserved/remapped
    assert script.rstrip().endswith("exit 0")                   # all slots busy -> a polite no-op


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


# ---- per-repo locks + the global capacity cap (epic #126) ----
# Single-flight is retired: concurrency is now bounded by two composed NON-BLOCKING flocks — the target
# repo's OWN lock (outermost, so a repo already building never starts a second build for itself and never
# consumes a capacity slot) and, inside that, the first free slot out of DISPATCH_MAX_BUILDS. `-E 200`
# distinguishes lock-busy from a real runner failure; the slot wrapper remaps a runner's own exit of
# exactly 200 to 201 so that reservation can never be misread as lock-busy. All slots busy -> a polite
# exit 0 (the task simply waits for the next dispatch tick — never dropped, never retried elsewhere).

def test_repo_lock_path_slug_pin():
    assert dispatch.repo_lock_path("owner/name", lock_home="/x") == "/x/dispatch-owner--name.lock"


def test_repo_lock_path_maps_case_dots_and_underscores_to_dashes():
    # any character outside [a-z0-9-] maps to '-' (collisions merely over-serialize onto the same lock —
    # fail-safe, never fail-open) and the slash between owner/name becomes '--'.
    assert dispatch.repo_lock_path("Owner.Two/Name_Three", lock_home="/x") == \
        "/x/dispatch-owner-two--name-three.lock"


def test_repo_lock_path_default_lock_home_is_the_dispatch_lock_directory():
    expected_home = pathlib.Path(dispatch.LOCK).parent
    assert dispatch.repo_lock_path("o/r") == str(expected_home / "dispatch-o--r.lock")


def test_slot_lock_path_pin():
    assert dispatch.slot_lock_path(0, lock_home="/x") == "/x/capslot-0.lock"
    assert dispatch.slot_lock_path(3, lock_home="/x") == "/x/capslot-3.lock"


def test_dispatch_max_builds_default_is_2_when_env_unset(monkeypatch):
    monkeypatch.delenv("DISPATCH_MAX_BUILDS", raising=False)
    try:
        importlib.reload(dispatch)
        assert dispatch.DISPATCH_MAX_BUILDS == 2
    finally:
        monkeypatch.undo()
        importlib.reload(dispatch)


def test_dispatch_max_builds_invalid_values_fall_back_to_the_default(monkeypatch):
    for raw in ("0", "-1", "abc", "", "1.5", "   "):
        monkeypatch.setenv("DISPATCH_MAX_BUILDS", raw)
        try:
            importlib.reload(dispatch)
            assert dispatch.DISPATCH_MAX_BUILDS == 2, raw
        finally:
            monkeypatch.undo()
            importlib.reload(dispatch)


def test_dispatch_max_builds_valid_override_is_honored(monkeypatch):
    monkeypatch.setenv("DISPATCH_MAX_BUILDS", "5")
    try:
        importlib.reload(dispatch)
        assert dispatch.DISPATCH_MAX_BUILDS == 5
    finally:
        monkeypatch.undo()
        importlib.reload(dispatch)


def test_build_task_defaults_to_the_module_level_max_builds_when_not_overridden():
    calls = []
    dispatch.build_task("1", "o/r", runner="/x/run.sh", lock_home="/tmp",
                         spawn=lambda *a: calls.append(a[0]))
    script = calls[0][-1]
    n = dispatch.DISPATCH_MAX_BUILDS
    assert f"capslot-{n - 1}.lock" in script
    assert f"capslot-{n}.lock" not in script


def test_busy_repo_lock_exits_with_the_reserved_code_and_never_touches_capacity_slots(tmp_path):
    lock_home = tmp_path / "locks"
    repo_lock = dispatch.repo_lock_path("o/r", lock_home=str(lock_home))
    held = _hold_lock(repo_lock)
    try:
        cmd = _capture_cmd(issue="9", repo="o/r", runner="/bin/true", lock_home=str(lock_home),
                            max_builds=2, runs_dir=str(tmp_path / "runs"))
        result = subprocess.run(cmd, timeout=5)
        assert result.returncode == 200                       # lock-busy, distinct from a runner failure
        assert not (lock_home / "capslot-0.lock").exists()     # a busy repo consumes no slot
        assert not (lock_home / "capslot-1.lock").exists()
    finally:
        held.close()


def test_runner_failure_propagates_and_is_not_retried_on_another_slot(tmp_path):
    lock_home = tmp_path / "locks"
    counter = tmp_path / "count"
    runner = _script(tmp_path / "runner.sh", f'echo x >> {counter}\nexit 7\n')
    cmd = _capture_cmd(issue="9", repo="o/r", runner=str(runner), lock_home=str(lock_home),
                        max_builds=2, runs_dir=str(tmp_path / "runs"))
    result = subprocess.run(cmd, timeout=5)
    assert result.returncode == 7                              # the real runner failure propagates unchanged
    assert counter.read_text().count("x") == 1                 # never retried on the second slot


def test_runner_exit_200_is_remapped_to_201_reserving_the_busy_code(tmp_path):
    lock_home = tmp_path / "locks"
    counter = tmp_path / "count"
    runner = _script(tmp_path / "runner.sh", f'echo x >> {counter}\nexit 200\n')
    cmd = _capture_cmd(issue="9", repo="o/r", runner=str(runner), lock_home=str(lock_home),
                        max_builds=2, runs_dir=str(tmp_path / "runs"))
    result = subprocess.run(cmd, timeout=5)
    assert result.returncode == 201                            # never misread as lock-busy at any layer above
    assert counter.read_text().count("x") == 1                 # remapped rc (201) != 200 -> no retry onto slot 1


def test_all_capacity_slots_busy_exits_politely_without_spawning_the_runner(tmp_path):
    lock_home = tmp_path / "locks"
    held0 = _hold_lock(dispatch.slot_lock_path(0, lock_home=str(lock_home)))
    held1 = _hold_lock(dispatch.slot_lock_path(1, lock_home=str(lock_home)))
    try:
        marker = tmp_path / "ran"
        runner = _script(tmp_path / "runner.sh", f'touch {marker}\n')
        cmd = _capture_cmd(issue="9", repo="o/r", runner=str(runner), lock_home=str(lock_home),
                            max_builds=2, runs_dir=str(tmp_path / "runs"))
        result = subprocess.run(cmd, timeout=5)
        assert result.returncode == 0                          # a polite no-op, not an error
        assert not marker.exists()                              # the runner was never invoked
    finally:
        held0.close(); held1.close()


def test_lock_home_mkdir_survives_the_composed_argv(tmp_path):
    # the composed argv no longer carries the lock path at cmd[2] (the old positional assumption) — the
    # lock home must still get created so flock can open a lock file there, or the failure would be a
    # silent "cannot open" rather than a legible busy/free result.
    lock_home = tmp_path / "nested" / "does" / "not" / "exist"
    marker = tmp_path / "ran"
    runner = _script(tmp_path / "runner.sh", f'touch {marker}\n')
    dispatch.build_task("4", "o/r", runner=str(runner), lock_home=str(lock_home), runs_dir=str(tmp_path / "runs"))
    assert _wait_for(marker.exists), "lock-home directory was never created, so flock couldn't open the lock path"
    assert lock_home.is_dir()


def test_same_repo_second_build_is_skipped_while_the_first_is_in_flight(tmp_path):
    lock_home = tmp_path / "locks"
    runs_dir = tmp_path / "runs"
    marker, counter = tmp_path / "marker", tmp_path / "count"
    slow_runner = _script(tmp_path / "slow.sh", f'echo x >> {counter}\ntouch {marker}\nsleep 2\n')
    dispatch.build_task("1", "o/r", runner=str(slow_runner), lock_home=str(lock_home), runs_dir=str(runs_dir))
    assert _wait_for(marker.exists), "the first build never started"

    second_marker = tmp_path / "second-ran"
    quick_runner = _script(tmp_path / "quick.sh", f'touch {second_marker}\n')
    dispatch.build_task("2", "o/r", runner=str(quick_runner), lock_home=str(lock_home), runs_dir=str(runs_dir))
    time.sleep(0.5)                                             # the busy-repo skip is a fast, synchronous exit
    assert counter.read_text().count("x") == 1                  # the runner never started a second time
    assert not second_marker.exists()


def test_two_different_repos_build_concurrently_under_their_own_locks_and_distinct_slots(tmp_path):
    lock_home = tmp_path / "locks"
    runs_dir = tmp_path / "runs"
    marker_a, marker_b = tmp_path / "a.marker", tmp_path / "b.marker"
    runner_a = _script(tmp_path / "runner_a.sh", f'touch {marker_a}\nsleep 2\n')
    runner_b = _script(tmp_path / "runner_b.sh", f'touch {marker_b}\nexit 0\n')
    dispatch.build_task("1", "o/repoA", runner=str(runner_a), lock_home=str(lock_home), runs_dir=str(runs_dir))
    assert _wait_for(marker_a.exists), "repo A's build never started"
    # repo B's build must not be blocked by repo A's own (still in-flight) repo lock, nor by repo A's
    # capacity slot — it gets the other free slot and runs to completion.
    dispatch.build_task("2", "o/repoB", runner=str(runner_b), lock_home=str(lock_home), runs_dir=str(runs_dir))
    assert _wait_for(marker_b.exists), "repo B's build was blocked by repo A's in-flight build"


def test_dispatch_makes_no_github_api_calls_of_its_own():
    # the stated seam (tools/dispatch.py:12): dispatch only flocks + spawns the runner/sweeper, which do
    # their own GitHub I/O — dispatch itself never calls `gh` or a GitHub API directly.
    src = pathlib.Path(dispatch.__file__).read_text()
    assert "github.com" not in src
    assert re.search(r'"gh"|\'gh\'', src) is None


# ---- ops-doc pins: the retired single-flight statements now describe locks, the cap, and slot files ----

def test_rfc_0004_header_carries_the_per_repo_amendment_pointer():
    rfc = (ROOT / "docs" / "rfcs" / "0004-dispatch.md").read_text()
    header = "\n".join(rfc.splitlines()[:5])
    assert re.search(r"amended", header, re.I)
    assert "#126" in header
    assert re.search(r"per-repo", header, re.I)
    assert re.search(r"single.flight", header, re.I)   # names what it supersedes


def test_dispatch_md_diagram_no_longer_claims_single_flight():
    doc = (ROOT / "deploy" / "DISPATCH.md").read_text()
    diagram_line = next(l for l in doc.splitlines() if "dispatch.service" in l)
    assert "single-flight" not in diagram_line.lower()
    assert re.search(r"repo.lock", diagram_line, re.I)


def test_dispatch_md_ops_paragraph_describes_locks_cap_and_slot_files():
    doc = (ROOT / "deploy" / "DISPATCH.md").read_text()
    assert "DISPATCH_MAX_BUILDS" in doc
    assert re.search(r"capslot", doc, re.I)
    assert re.search(r"per-repo", doc, re.I)
    assert "200" in doc                                  # the reserved lock-busy exit code is documented
    assert "single-flight" not in doc.lower()


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
    build_lock_path = build_calls[0][4]       # composed argv: [flock, -n, -E, 200, <repo-lock>, bash, -c, ...]
    sweep_lock_path = sweep_calls[0][2]       # sweep argv is unchanged: [flock, -n, <lock>, <sweeper>]
    assert build_lock_path != sweep_lock_path
    assert build_lock_path == dispatch.repo_lock_path("o/r")
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
        assert len(calls) == 1 and calls[0][:2] == ["flock", "-n"]
        assert "5" in calls[0][-1]   # the issue number reaches the runner invocation embedded in the composed script


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
