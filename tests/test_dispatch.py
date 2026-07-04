"""Unit tests for tools/dispatch.py — the spawn is stubbed, so no real build is ever launched."""
import contextlib, json, os, pathlib, sys, threading, urllib.error, urllib.request
from http.server import HTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dispatch  # noqa: E402


# ---- build_task core ----

def test_build_task_spawns_flocked_runner():
    calls = []
    r = dispatch.build_task("7", "o/r", runner="/x/run.sh", lock="/tmp/l", spawn=calls.append)
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
    dispatch.build_task("7", "o/r", runner="/x/run.sh", spawn=build_calls.append)
    dispatch.run_sweep(sweeper="/x/epic_gate.py", spawn=sweep_calls.append)
    build_lock_path = build_calls[0][2]
    sweep_lock_path = sweep_calls[0][2]
    assert build_lock_path != sweep_lock_path
    assert build_lock_path == dispatch.LOCK
    assert sweep_lock_path == dispatch.SWEEP_LOCK


# ---- HTTP adapter ----

@contextlib.contextmanager
def _server(token="secret"):
    os.environ["DISPATCH_TOKEN"] = token
    calls = []
    orig = dispatch._SPAWN
    dispatch._SPAWN = calls.append                # no real spawn during HTTP tests
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
