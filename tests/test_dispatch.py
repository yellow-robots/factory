"""Unit tests for tools/dispatch.py — the spawn is stubbed, so no real build is ever launched."""
import contextlib, errno, fcntl, importlib, json, os, pathlib, re, shlex, signal, subprocess, sys, threading, time
import urllib.error, urllib.request
from http.server import HTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dispatch  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_dispatch_instance(monkeypatch):
    """Order-independence pin (it-36 slice D, #469, review round 3): `dispatch.main()` assigns
    module-level `dispatch._INSTANCE` directly (never through monkeypatch), so a test that calls
    `main(["--instance", "pm"])` leaks that value into whichever test runs next — reproduced by
    the reviewer running `test_main_accepts_each_valid_instance_value` immediately before
    `test_spawn_env_excludes_vault_api_key_on_the_build_instance` (an order xdist/random-order CI
    can produce, collection order alone does not). Recording the value here and letting
    `monkeypatch` restore it after EVERY test in this file — regardless of whether that test used
    monkeypatch itself to change it — closes this structurally rather than per-test."""
    monkeypatch.setattr(dispatch, "_INSTANCE", dispatch._INSTANCE)


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
    r = dispatch.run_sweep(sweeper="/x/epic_gate.py", lock="/tmp/sweep.lock",
                            spawn=lambda *a: calls.append(a[0]))
    assert r["ok"] and r["dispatched"]
    assert calls == [["flock", "-n", "/tmp/sweep.lock", "/x/epic_gate.py"]]


def test_run_sweep_takes_no_issue_or_repo_args():
    calls = []
    r = dispatch.run_sweep(spawn=lambda *a: calls.append(a[0]))   # no issue/repo — org-wide, board is the input
    assert r["ok"] and r["dispatched"]
    assert len(calls) == 1 and len(calls[0]) == 4   # flock, -n, <lock>, <sweeper> — nothing else appended


def test_run_sweep_spawn_receives_a_log_path_under_runs_dir(tmp_path):
    # unlike build_task (unstubbed spawn is invoked with cmd, log_path, lock_home), run_sweep's spawn
    # shape is (cmd, log_path) — the sweeper never needed a lock_home override.
    calls = []
    runs_dir = tmp_path / "runs"
    r = dispatch.run_sweep(sweeper="/x/epic_gate.py", lock="/tmp/sweep.lock",
                            spawn=lambda cmd, log_path: calls.append((cmd, log_path)),
                            runs_dir=str(runs_dir))
    assert r["ok"] and r["dispatched"]
    assert len(calls) == 1
    cmd, log_path = calls[0]
    assert cmd == ["flock", "-n", "/tmp/sweep.lock", "/x/epic_gate.py"]
    assert pathlib.Path(log_path).parent == runs_dir


def test_run_sweep_log_path_is_the_same_single_file_across_invocations(tmp_path):
    """AC: a single append-mode sweep log, not one file per poll tick — the log path handed to spawn
    must be IDENTICAL across repeated sweeps against the same runs_dir."""
    calls = []
    runs_dir = tmp_path / "runs"
    for _ in range(4):
        r = dispatch.run_sweep(sweeper="/x/epic_gate.py", lock="/tmp/sweep.lock",
                                spawn=lambda cmd, log_path: calls.append(log_path),
                                runs_dir=str(runs_dir))
        assert r["ok"]
    assert len(calls) == 4
    assert len({str(p) for p in calls}) == 1, f"expected one stable log path, got {sorted(set(map(str, calls)))}"


def test_sweep_lock_distinct_from_build_lock():
    # default locks (no override) must differ so a build never blocks/blocks-on a sweep
    assert dispatch.SWEEP_LOCK != dispatch.LOCK

    build_calls, sweep_calls = [], []
    dispatch.build_task("7", "o/r", runner="/x/run.sh", spawn=lambda *a: build_calls.append(a[0]))
    dispatch.run_sweep(sweeper="/x/epic_gate.py", spawn=lambda *a: sweep_calls.append(a[0]))
    build_lock_path = build_calls[0][4]       # composed argv: [flock, -n, -E, 200, <repo-lock>, bash, -c, ...]
    sweep_lock_path = sweep_calls[0][2]       # sweep argv is unchanged: [flock, -n, <lock>, <sweeper>]
    assert build_lock_path != sweep_lock_path
    assert build_lock_path == dispatch.repo_lock_path("o/r")
    assert sweep_lock_path == dispatch.SWEEP_LOCK


def test_epic_sweeper_default_is_executable():
    # flock execs the sweeper directly (run_sweep's argv), detached with stdout+stderr into sweep.log —
    # a missing exec bit means every /sweep 202s then dies with exit 126, traceable in that log rather
    # than silently. Git checkouts preserve mode bits,
    # so pin the bit here.
    assert os.access(dispatch.EPIC_SWEEPER, os.X_OK)


# ---- run_design_sweep core (it-36 slice E, #470): `run_sweep`'s exact shape, its own separate lock ----

def test_run_design_sweep_spawns_flocked_sweeper():
    calls = []
    r = dispatch.run_design_sweep(sweeper="/x/design_gate.py", lock="/tmp/design-sweep.lock",
                                   spawn=lambda *a: calls.append(a[0]))
    assert r["ok"] and r["dispatched"]
    assert calls == [["flock", "-n", "/tmp/design-sweep.lock", "/x/design_gate.py"]]


def test_run_design_sweep_takes_no_issue_or_repo_args():
    calls = []
    r = dispatch.run_design_sweep(spawn=lambda *a: calls.append(a[0]))
    assert r["ok"] and r["dispatched"]
    assert len(calls) == 1 and len(calls[0]) == 4   # flock, -n, <lock>, <sweeper> — nothing else appended


def test_run_design_sweep_spawn_receives_a_log_path_under_runs_dir(tmp_path):
    calls = []
    runs_dir = tmp_path / "runs"
    r = dispatch.run_design_sweep(sweeper="/x/design_gate.py", lock="/tmp/design-sweep.lock",
                                   spawn=lambda cmd, log_path: calls.append((cmd, log_path)),
                                   runs_dir=str(runs_dir))
    assert r["ok"] and r["dispatched"]
    assert len(calls) == 1
    cmd, log_path = calls[0]
    assert cmd == ["flock", "-n", "/tmp/design-sweep.lock", "/x/design_gate.py"]
    assert pathlib.Path(log_path).name == "design-sweep.log"
    assert pathlib.Path(log_path).parent == runs_dir


def test_run_design_sweep_log_path_is_the_same_single_file_across_invocations(tmp_path):
    calls = []
    runs_dir = tmp_path / "runs"
    for _ in range(4):
        r = dispatch.run_design_sweep(sweeper="/x/design_gate.py", lock="/tmp/design-sweep.lock",
                                       spawn=lambda cmd, log_path: calls.append(log_path),
                                       runs_dir=str(runs_dir))
        assert r["ok"]
    assert len(calls) == 4
    assert len({str(p) for p in calls}) == 1, f"expected one stable log path, got {sorted(set(map(str, calls)))}"


def test_design_sweep_lock_distinct_from_both_build_and_epic_sweep_locks():
    # its own lock — separate from BOTH the build locks and the epic-sweep lock — so a design sweep
    # never blocks or is blocked by either.
    assert dispatch.DESIGN_SWEEP_LOCK != dispatch.LOCK
    assert dispatch.DESIGN_SWEEP_LOCK != dispatch.SWEEP_LOCK

    build_calls, epic_calls, design_calls = [], [], []
    dispatch.build_task("7", "o/r", runner="/x/run.sh", spawn=lambda *a: build_calls.append(a[0]))
    dispatch.run_sweep(sweeper="/x/epic_gate.py", spawn=lambda *a: epic_calls.append(a[0]))
    dispatch.run_design_sweep(sweeper="/x/design_gate.py", spawn=lambda *a: design_calls.append(a[0]))
    build_lock_path = build_calls[0][4]
    epic_lock_path = epic_calls[0][2]
    design_lock_path = design_calls[0][2]
    assert len({build_lock_path, epic_lock_path, design_lock_path}) == 3
    assert design_lock_path == dispatch.DESIGN_SWEEP_LOCK


def test_design_sweeper_default_is_executable():
    # the same `flock` + direct-exec shape as the epic sweeper (test_epic_sweeper_default_is_executable
    # above): a missing exec bit means every /design-sweep 202s then dies with exit 126.
    assert os.access(dispatch.DESIGN_SWEEPER, os.X_OK)


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


# ---- /design-sweep HTTP adapter (it-36 slice E, #470) ----
# `/design-sweep` is answered regardless of `--instance` (exactly like /build and /sweep) — only the
# systemd unit's own schedule decides which instance actually POSTs here in production.

def test_http_design_sweep_requires_token():
    with _server() as (url, calls):
        assert _post(url + "/design-sweep", {})[0] == 401
        assert _post(url + "/design-sweep", {}, token="wrong")[0] == 401
        assert calls == []                                          # never reached run_design_sweep


def test_http_design_sweep_happy_202_spawns_once():
    with _server() as (url, calls):
        code, body = _post(url + "/design-sweep", {}, token="secret")
        assert code == 202 and body["ok"] and body["dispatched"]
        assert len(calls) == 1 and calls[0][:2] == ["flock", "-n"]


def test_http_design_sweep_no_body_required():
    with _server() as (url, calls):
        req = urllib.request.Request(url + "/design-sweep", data=b"", method="POST")
        req.add_header("Authorization", "Bearer secret")
        with urllib.request.urlopen(req) as resp:
            code = resp.status
        assert code == 202 and len(calls) == 1


def test_http_design_sweep_uses_a_lock_distinct_from_build_and_epic_sweep_locks():
    with _server() as (url, calls):
        _post(url + "/build", {"issue": 5, "repo": "o/r"}, token="secret")
        _post(url + "/sweep", {}, token="secret")
        _post(url + "/design-sweep", {}, token="secret")
        assert len(calls) == 3
        build_lock, sweep_lock, design_lock = calls[0][2], calls[1][2], calls[2][2]
        assert len({build_lock, sweep_lock, design_lock}) == 3


def test_http_unknown_path_404_still_enforced_with_design_sweep_route_present():
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


def _lock_released(path):
    """True once no process holds the flock on `path` — probed the way the next `flock -n` spawn
    will: a chained `flock -n` spawn on one lock must wait for the RELEASE, never for a side effect
    of the holder (the sweeper's flock parent releases only at exit, after its last tick; under
    xdist load the gap between the two is ordinary and the next spawn silently skips)."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    finally:
        os.close(fd)


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


# ---- sweep output lands in a single append-mode log file, not a discarded stdout (issue #407) ----
# These exercise the REAL spawn path (dispatch's own _spawn_detached, not the injectable stub) — the same
# rationale as the build_task real-spawn section above: the behavior lives in that seam.

def test_run_sweep_persists_combined_stdout_stderr_to_a_discoverable_log(tmp_path):
    sweeper = _script(tmp_path / "sweeper.sh", 'echo "sweep-out-marker"\necho "sweep-err-marker" >&2\n')
    runs_dir = tmp_path / "runs"
    r = dispatch.run_sweep(sweeper=str(sweeper), lock=str(tmp_path / "sweep.lock"), runs_dir=str(runs_dir))
    assert r["ok"] and r["dispatched"]
    assert _wait_for(lambda: runs_dir.exists() and any(runs_dir.iterdir()))
    files = list(runs_dir.iterdir())
    assert len(files) == 1, f"expected exactly one sweep log file, found {files}"
    log_path = files[0]
    assert _wait_for(lambda: log_path.exists() and "sweep-err-marker" in log_path.read_text())
    content = log_path.read_text()
    assert "sweep-out-marker" in content and "sweep-err-marker" in content   # both streams, combined


def test_run_sweep_appends_across_invocations_file_count_stays_at_one(tmp_path):
    """AC: 'the file count stays bounded on the poll cadence' — repeated sweep spawns append to the SAME
    file rather than accreting one file per invocation."""
    counter = tmp_path / "counter"
    sweeper = _script(tmp_path / "sweeper.sh",
                       f'echo "tick" >> {shlex.quote(str(counter))}\necho "tick-marker"\n')
    runs_dir = tmp_path / "runs"
    lock = tmp_path / "sweep.lock"
    for i in range(3):
        r = dispatch.run_sweep(sweeper=str(sweeper), lock=str(lock), runs_dir=str(runs_dir))
        assert r["ok"]
        assert _wait_for(lambda i=i: counter.exists() and counter.read_text().count("tick") == i + 1), \
            f"invocation {i} never completed"
        # the next `flock -n` depends on the lock's RELEASE (the holder's exit), not on its tick —
        # waiting on the tick alone raced the release under xdist load (PR #480, PR #502)
        assert _wait_for(lambda: _lock_released(str(lock))), \
            f"invocation {i} never released the sweep lock"
    files = list(runs_dir.iterdir())
    assert len(files) == 1, f"sweep log file count must stay bounded on the poll cadence, found {files}"
    assert files[0].read_text().count("tick-marker") == 3   # each invocation's output landed, none overwritten


# ---- spawn env allowlist (issue #237) ----
# The runner (and everything it spawns) must receive an ALLOWLISTED environment, not dispatch's own
# os.environ wholesale: dispatch's bearer secret (DISPATCH_TOKEN) must never reach the runner or any
# stage, while the runner's declared seam (process basics, the homes it reads, its named credential/
# config seams) and the test harness's own STUB_* injection flags still flow through. These exercise the
# REAL spawn path (unstubbed _spawn_detached), since the behavior lives in that seam, not in build_task's
# argv construction.

def _dump_env_script(path, out_file):
    return _script(path, f'env > {shlex.quote(str(out_file))}\n')


def _read_env_dump(path):
    """Parse a KEY=VALUE-per-line `env` dump into a dict (values may contain '=' themselves)."""
    lines = path.read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def test_build_task_spawn_env_excludes_dispatch_token_and_includes_allowlisted_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPATCH_TOKEN", "top-secret-bearer-value")
    monkeypatch.setenv("BUILD_MODEL", "sonnet")
    monkeypatch.setenv("DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setenv("YR_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("STUB_HARNESS_FLAG", "harness-value")
    monkeypatch.setenv("SOME_UNRELATED_SECRET", "must-not-leak")
    env_file = tmp_path / "env.txt"
    runner = _dump_env_script(tmp_path / "runner.sh", env_file)
    runs_dir = tmp_path / "runs"
    r = dispatch.build_task("55", "o/r", runner=str(runner), lock=str(tmp_path / "lock"),
                             runs_dir=str(runs_dir))
    assert r["ok"]
    assert _wait_for(env_file.exists)
    time.sleep(0.2)   # let the (already-exited) writer's buffered output settle onto disk
    got = _read_env_dump(env_file)

    # the dispatch service's own secret never reaches the runner, under any name or value
    assert "DISPATCH_TOKEN" not in got
    assert "top-secret-bearer-value" not in env_file.read_text()

    # an arbitrary var dispatch happened to have is NOT let through (allowlist, not a scrub-list of one)
    assert "SOME_UNRELATED_SECRET" not in got

    # process basics + the homes the runner reads + a named seam all flow through
    assert "PATH" in got and got["PATH"]
    assert got.get("DEV_RUNNER_HOME") == str(tmp_path / "drhome")
    assert got.get("YR_WORKSPACE") == str(tmp_path / "ws")
    assert got.get("BUILD_MODEL") == "sonnet"

    # the test harness's own STUB_* injection flags still flow (additive allowlist, per the spec's ruling)
    assert got.get("STUB_HARNESS_FLAG") == "harness-value"


def test_build_task_spawn_env_is_not_empty_and_not_the_full_parent_environ(tmp_path, monkeypatch):
    # guards against a no-op "allowlist" that's actually empty (breaks every runner) or actually everything
    # (doesn't fix the leak) — the spawned env must be a proper, non-trivial subset.
    monkeypatch.setenv("DISPATCH_TOKEN", "should-not-appear")
    monkeypatch.setenv("SOME_OTHER_RANDOM_VAR_237", "also-should-not-appear")
    env_file = tmp_path / "env.txt"
    runner = _dump_env_script(tmp_path / "runner.sh", env_file)
    r = dispatch.build_task("56", "o/r", runner=str(runner), lock=str(tmp_path / "lock"),
                             runs_dir=str(tmp_path / "runs"))
    assert r["ok"]
    assert _wait_for(env_file.exists)
    time.sleep(0.2)
    got = _read_env_dump(env_file)
    assert len(got) > 0                                      # not an empty environment
    assert "PATH" in got                                     # a bare minimum a subprocess needs
    assert "SOME_OTHER_RANDOM_VAR_237" not in got             # not a wholesale copy of the parent either


def test_spawn_env_excludes_vault_api_key_on_the_build_instance(monkeypatch):
    # issue #393, restored to a structural default-deny (it-36 slice D, #469, review round 2 —
    # the env-based discriminator was inert per systemd.exec(5): an EnvironmentFile= always
    # overrides that SAME unit's own Environment=, so no unit-file pin could ever be trusted).
    # YR_VAULT_API_KEY is NOT a member of _ENV_ALLOW_KEYS at all: the build instance's spawn
    # never lists the key, let alone its value. _INSTANCE (an argv flag, set once in main() from
    # --instance, never read from the environment) defaults to "build".
    assert dispatch._INSTANCE == "build"
    monkeypatch.setenv("YR_VAULT_API_KEY", "top-secret-vault-key-should-never-reach-a-stage")
    env = dispatch._spawn_env()
    assert "YR_VAULT_API_KEY" not in env
    monkeypatch.setattr(dispatch, "_INSTANCE", "build")   # explicit, not just the module default
    env = dispatch._spawn_env()
    assert "YR_VAULT_API_KEY" not in env


def test_spawn_env_includes_vault_api_key_on_the_pm_instance(monkeypatch):
    # the PM instance (deploy/pm-dispatch.service, `--instance pm`) is the one dispatch process
    # that DOES hand the vault key to its spawned design-sweep child — the flip side of the build
    # instance's exclusion above, both pinned so a future edit can't silently collapse either way.
    monkeypatch.setattr(dispatch, "_INSTANCE", "pm")
    monkeypatch.setenv("YR_VAULT_API_KEY", "top-secret-vault-key-reaches-the-pm-child")
    env = dispatch._spawn_env()
    assert env.get("YR_VAULT_API_KEY") == "top-secret-vault-key-reaches-the-pm-child"


def test_spawn_env_excludes_notify_secret_on_the_build_instance(monkeypatch):
    # YR_NOTIFY_SECRET (it-36 slice I, #474 — tools/notify.py's HMAC signing key) is PM-only, same
    # reasoning and same structural default-deny as YR_VAULT_API_KEY above: a task-typed build the
    # build instance spawns never notifies a stakeholder, so its child never lists the key.
    assert dispatch._INSTANCE == "build"
    monkeypatch.setenv("YR_NOTIFY_SECRET", "top-secret-notify-key-should-never-reach-a-stage")
    env = dispatch._spawn_env()
    assert "YR_NOTIFY_SECRET" not in env


def test_spawn_env_includes_notify_secret_on_the_pm_instance(monkeypatch):
    monkeypatch.setattr(dispatch, "_INSTANCE", "pm")
    monkeypatch.setenv("YR_NOTIFY_SECRET", "top-secret-notify-key-reaches-the-pm-child")
    env = dispatch._spawn_env()
    assert env.get("YR_NOTIFY_SECRET") == "top-secret-notify-key-reaches-the-pm-child"


def test_spawn_env_app_keys_flow_on_either_instance(monkeypatch):
    # the GitHub App identity is NOT vault-gated: both instances may need to authenticate as the
    # App (the build instance for its own PR/issue writes, the PM instance for design-sweep issue
    # creation), so these five ride the general allowlist unconditionally, on the module default.
    app_keys = {
        "YR_GH_APP_ID": "12345", "YR_GH_APP_KEY_PATH": "/etc/yr/app.pem",
        "YR_GH_APP_INSTALLATION": "67890", "YR_GH_APP_SLUG": "yr-bot",
        "YR_OWNER_LOGIN": "yellow-robots",
    }
    for k, v in app_keys.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(dispatch, "_INSTANCE", "build")
    env = dispatch._spawn_env()
    for k, v in app_keys.items():
        assert env.get(k) == v


# ---- I1, corrected off the env channel (it-36 slice D, #469, review round 2): each unit's ----
# ---- ExecStart carries its own --instance flag; neither unit sets DISPATCH_INSTANCE at all. ----

def _unit_lines(name):
    return (ROOT / "deploy" / name).read_text(encoding="utf-8").splitlines()


def test_build_unit_execstart_carries_its_instance_flag():
    lines = _unit_lines("dispatch.service")
    execstart = next(l for l in lines if l.startswith("ExecStart="))
    assert execstart.rstrip().endswith("--instance build")
    assert not any(l.startswith("Environment=DISPATCH_INSTANCE") for l in lines)


def test_pm_unit_execstart_carries_its_instance_flag():
    lines = _unit_lines("pm-dispatch.service")
    execstart = next(l for l in lines if l.startswith("ExecStart="))
    assert execstart.rstrip().endswith("--instance pm")
    assert not any(l.startswith("Environment=DISPATCH_INSTANCE") for l in lines)


def test_run_sweep_spawn_env_excludes_dispatch_token(tmp_path, monkeypatch):
    # the sweep spawn is the same seam as the build spawn (both go through _spawn_detached) — the
    # acceptance criteria call out "the runner or any stage", which includes the sweeper.
    monkeypatch.setenv("DISPATCH_TOKEN", "sweep-secret-value")
    monkeypatch.setenv("STUB_SWEEP_FLAG", "1")
    env_file = tmp_path / "env.txt"
    sweeper = _dump_env_script(tmp_path / "sweeper.sh", env_file)
    r = dispatch.run_sweep(sweeper=str(sweeper), lock=str(tmp_path / "sweep.lock"),
                            runs_dir=str(tmp_path / "runs"))
    assert r["ok"]
    assert _wait_for(env_file.exists)
    time.sleep(0.2)
    got = _read_env_dump(env_file)
    assert "DISPATCH_TOKEN" not in got
    assert "sweep-secret-value" not in env_file.read_text()
    assert "PATH" in got
    assert got.get("STUB_SWEEP_FLAG") == "1"


def test_http_build_spawn_env_excludes_the_live_dispatch_token(tmp_path):
    # end-to-end over the real HTTP adapter (the actual deployed path): the service's own bearer secret,
    # read fresh by do_POST from os.environ["DISPATCH_TOKEN"], must not ride into the spawned runner even
    # though the request that triggered the spawn was itself authenticated with that exact token.
    token = "live-dispatch-bearer-token"
    os.environ["DISPATCH_TOKEN"] = token
    env_file = tmp_path / "env.txt"
    runner = _dump_env_script(tmp_path / "runner.sh", env_file)
    runs_dir = tmp_path / "runs"
    orig_runner, orig_runs, orig_lock = dispatch.DEV_RUNNER, dispatch.RUNS_DIR, dispatch.LOCK
    dispatch.DEV_RUNNER, dispatch.RUNS_DIR, dispatch.LOCK = str(runner), str(runs_dir), str(tmp_path / "lock")
    srv = HTTPServer(("127.0.0.1", 0), dispatch.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        code, body = _post(url + "/build", {"issue": 77, "repo": "o/r"}, token=token)
        assert code == 202 and body["dispatched"]
        assert _wait_for(env_file.exists)
        time.sleep(0.2)
        content = env_file.read_text()
        assert "DISPATCH_TOKEN" not in _read_env_dump(env_file)
        assert token not in content
    finally:
        srv.shutdown()
        dispatch.DEV_RUNNER, dispatch.RUNS_DIR, dispatch.LOCK = orig_runner, orig_runs, orig_lock


# ---- SIGCHLD reap of detached children (issue #138) ----
# dispatch keeps no Popen and has no in-process waiter anywhere, so main() installs
# signal.signal(SIGCHLD, SIG_IGN) before serve_forever() and lets the kernel auto-reap every detached
# flock child instead of leaving it <defunct> until the next Popen call happens to reap it lazily.

def test_main_installs_sigchld_ignore_before_serve_forever(monkeypatch):
    order = []

    def fake_signal(sig, handler):
        order.append(("signal", sig, handler))

    class FakeServer:
        def __init__(self, *a, **kw):
            pass

        def serve_forever(self):
            order.append(("serve_forever",))

    monkeypatch.setenv("DISPATCH_TOKEN", "secret")
    monkeypatch.setattr(dispatch.signal, "signal", fake_signal)
    monkeypatch.setattr(dispatch, "HTTPServer", FakeServer)

    rc = dispatch.main([])

    assert rc == 0
    assert ("signal", signal.SIGCHLD, signal.SIG_IGN) in order   # the exact disposition required
    sigchld_calls = [c for c in order if c[0] == "signal" and c[1] == signal.SIGCHLD]
    assert len(sigchld_calls) == 1                                # installed exactly once, not re-armed per request
    assert order.index(("signal", signal.SIGCHLD, signal.SIG_IGN)) < order.index(("serve_forever",))


def test_main_without_token_never_touches_sigchld_or_serves(monkeypatch):
    # the early refusal (no DISPATCH_TOKEN) must not install the disposition or start serving
    order = []
    monkeypatch.delenv("DISPATCH_TOKEN", raising=False)
    monkeypatch.setattr(dispatch.signal, "signal", lambda *a: order.append(("signal", *a)))
    monkeypatch.setattr(dispatch, "HTTPServer", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("HTTPServer must not be constructed without a token")))

    rc = dispatch.main([])

    assert rc == 2
    assert order == []


def test_sigchld_ignore_reaps_detached_flock_children_without_defunct(tmp_path):
    # end-to-end: the actual behavior the acceptance criteria require — a detached child (the composed
    # `flock ... bash -c ...` build_task spawns for real, via the unstubbed _spawn_detached seam) leaves
    # no <defunct> entry parented to this process once it exits, under the disposition main() installs.
    old_handler = signal.getsignal(signal.SIGCHLD)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    real_popen = dispatch.subprocess.Popen
    captured = []

    def spy_popen(*a, **kw):
        p = real_popen(*a, **kw)
        captured.append(p.pid)
        return p

    dispatch.subprocess.Popen = spy_popen
    try:
        runner = _script(tmp_path / "runner.sh", "exit 0\n")
        dispatch.build_task("1", "o/r", runner=str(runner), lock=str(tmp_path / "lock"),
                             runs_dir=str(tmp_path / "runs"))
        assert _wait_for(lambda: len(captured) == 1), "the detached flock child was never spawned"
        pid = captured[0]

        def not_a_zombie():
            try:
                stat = pathlib.Path(f"/proc/{pid}/stat").read_text()
            except FileNotFoundError:
                return True                                        # gone entirely — reaped, no zombie left
            state = stat.rsplit(")", 1)[1].split()[0]
            return state != "Z"

        assert _wait_for(not_a_zombie, timeout=5), \
            "the detached child stayed <defunct> — SIGCHLD=SIG_IGN did not reap it"

        # a lingering zombie would still be reapable by an explicit waitpid; the kernel having already
        # auto-reaped it under SIG_IGN means there is nothing left to wait on: ECHILD, not a status.
        try:
            os.waitpid(pid, 0)
        except OSError as exc:
            assert exc.errno == errno.ECHILD
        else:
            raise AssertionError("waitpid succeeded — the child was still there to be reaped, i.e. it was <defunct>")
    finally:
        dispatch.subprocess.Popen = real_popen
        signal.signal(signal.SIGCHLD, old_handler)


# ---- it-33 slice 2 (issue #457) — dispatch states the commit it runs from ----
# The resident process names the commit of the whole tree it is executing from: on its startup line,
# and in a statement file a pull under a running process cannot change (captured once, at import).

def test_statement_names_the_real_commit_of_the_whole_tree_dispatch_runs_from():
    real = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert dispatch.STATEMENT == f"commit: {real}"


def test_statement_is_never_a_bare_version_string():
    assert dispatch.STATEMENT.startswith("commit: ")


def test_statement_was_captured_once_at_import_a_later_git_read_cannot_change_it(monkeypatch):
    # A `git pull` under a running dispatch must not change what it reports: prove the value isn't
    # recomputed by making a fresh call to the underlying read return something else, and showing
    # the already-bound STATEMENT is untouched.
    monkeypatch.setattr(dispatch.provenance, "factory_commit", lambda root: "deadbeef" * 5)
    assert dispatch.STATEMENT != "commit: " + "deadbeef" * 5
    assert dispatch.STATEMENT.startswith("commit: ")


def test_main_prints_the_statement_on_its_startup_line(monkeypatch, capsys):
    monkeypatch.setenv("DISPATCH_TOKEN", "secret")
    monkeypatch.setattr(dispatch.signal, "signal", lambda *a, **kw: None)

    class FakeServer:
        def __init__(self, *a, **kw):
            pass

        def serve_forever(self):
            pass

    monkeypatch.setattr(dispatch, "HTTPServer", FakeServer)

    rc = dispatch.main([])

    assert rc == 0
    err = capsys.readouterr().err
    assert dispatch.STATEMENT in err
    assert "listening on" in err


def test_main_writes_the_statement_file_at_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPATCH_TOKEN", "secret")
    monkeypatch.setattr(dispatch, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    monkeypatch.setattr(dispatch.signal, "signal", lambda *a, **kw: None)

    class FakeServer:
        def __init__(self, *a, **kw):
            pass

        def serve_forever(self):
            pass

    monkeypatch.setattr(dispatch, "HTTPServer", FakeServer)

    rc = dispatch.main([])

    assert rc == 0
    stmt_path = tmp_path / "drhome" / "dispatch.statement"
    assert stmt_path.read_text(encoding="utf-8") == dispatch.STATEMENT + "\n"


def test_main_without_token_never_writes_the_statement_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DISPATCH_TOKEN", raising=False)
    monkeypatch.setattr(dispatch, "DEV_RUNNER_HOME", str(tmp_path / "drhome"))

    rc = dispatch.main([])

    assert rc == 2
    assert not (tmp_path / "drhome" / "dispatch.statement").exists()


# ---- N2, corrected off the env channel (it-36 slice D, #469, review round 2): the discriminator
# ---- is now an argv flag with a closed `choices` set — argparse refuses a typo loudly by
# ---- construction, so the custom warning this section used to pin is moot; what's left to pin
# ---- is that argparse's own refusal names the value, exits non-zero, and never a secret. ----

def _main_with_fake_server(monkeypatch):
    monkeypatch.setenv("DISPATCH_TOKEN", "secret")
    monkeypatch.setattr(dispatch.signal, "signal", lambda *a, **kw: None)

    class FakeServer:
        def __init__(self, *a, **kw):
            pass

        def serve_forever(self):
            pass

    monkeypatch.setattr(dispatch, "HTTPServer", FakeServer)


def test_main_rejects_an_invalid_instance_value(monkeypatch, capsys):
    _main_with_fake_server(monkeypatch)

    with pytest.raises(SystemExit) as exc:
        dispatch.main(["--instance", "PM"])   # a plausible typo — wrong case

    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "PM" in err
    assert "secret" not in err   # the token never rides the diagnostic


def test_main_accepts_each_valid_instance_value(monkeypatch):
    for value in ("build", "pm"):
        _main_with_fake_server(monkeypatch)

        rc = dispatch.main(["--instance", value])

        assert rc == 0
        assert dispatch._INSTANCE == value


def test_main_defaults_to_build_with_no_instance_flag(monkeypatch):
    _main_with_fake_server(monkeypatch)

    rc = dispatch.main([])

    assert rc == 0
    assert dispatch._INSTANCE == "build"
