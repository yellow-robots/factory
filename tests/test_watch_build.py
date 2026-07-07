"""Acceptance tests for tools/watch_build.sh — the build-watch operator command (#53).

Stubbed `gh` (no network, no `claude`): each poll tick calls `gh api graphql` for the issue-side
Status/Reason, then `gh pr list` for PR presence. The fake `gh` serves a canned sequence of states —
one per tick — advancing its shared counter on the `pr list` call, since that call happens exactly once
per tick regardless of which terminal branch fires. `--interval 0` keeps polling loops instant in tests.
"""
import json, os, stat, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "watch_build.sh"

GH_STUB = '''#!/usr/bin/env python3
import sys, os, json

argv = sys.argv[1:]
log = os.environ.get("STUB_CALLS_LOG")
if log:
    with open(log, "a") as f:
        print(json.dumps(argv), file=f)

states = json.loads(os.environ["STUB_STATES"])
counter_file = os.environ["STUB_COUNTER"]

def idx():
    try:
        return int(open(counter_file).read().strip())
    except Exception:
        return 0

def bump():
    i = idx()
    if i < len(states) - 1:
        open(counter_file, "w").write(str(i + 1))

if argv[:2] == ["repo", "view"]:
    print(os.environ.get("STUB_REPO", "test/repo"))
    sys.exit(0)

if argv[:2] == ["api", "graphql"]:
    st = states[idx()]
    print(json.dumps({"data": {"repository": {"issue": {
        "state": st.get("issue_state", "OPEN"),
        "projectItems": {"nodes": [{
            "project": {"number": int(os.environ.get("PROJECT_NUMBER", "1"))},
            "status": ({"name": st["status"]} if st.get("status") else None),
            "reason": ({"name": st["reason"]} if st.get("reason") else None),
        }]},
    }}}}))
    sys.exit(0)

if argv[:2] == ["pr", "list"]:
    st = states[idx()]
    prs = []
    if st.get("pr_open"):
        prs = [{"number": 1, "headRefName": "task/%s-x" % os.environ["STUB_ISSUE"], "url": "https://example/pr/1"}]
    print(json.dumps(prs))
    bump()
    sys.exit(0)

if argv[:2] == ["issue", "view"]:
    comments = json.loads(os.environ.get("STUB_COMMENTS", "[]"))
    print(json.dumps({"comments": comments}))
    sys.exit(0)

sys.exit(9)
'''


def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _bin(tmp):
    b = tmp / "bin"
    b.mkdir(exist_ok=True)
    _exec(b / "gh", GH_STUB)
    return b


def _base_env(tmp, binp, states, issue="7", repo="test/repo", comments=None):
    (tmp / "counter").write_text("0")
    return {
        **os.environ,
        "GH_BIN": str(binp / "gh"),
        "STUB_STATES": json.dumps(states),
        "STUB_COUNTER": str(tmp / "counter"),
        "STUB_CALLS_LOG": str(tmp / "calls.log"),
        "STUB_ISSUE": issue,
        "STUB_REPO": repo,
        "STUB_COMMENTS": json.dumps(comments or []),
        "PROJECT_NUMBER": "1",
    }


def _run(args, env, timeout=10):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=timeout)


def _calls(tmp):
    p = tmp / "calls.log"
    return [json.loads(l) for l in p.read_text().splitlines() if l] if p.exists() else []


# ============ four terminal exit codes ============

def test_exit0_on_open_pr_and_in_review_prints_pr_url(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "In Review", "pr_open": True}]
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"],
             _base_env(tmp_path, binp, states))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "https://example/pr/1"


def test_exit2_on_done(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "Done"}]
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"],
             _base_env(tmp_path, binp, states))
    assert r.returncode == 2


def test_exit3_on_blocked_prints_latest_runner_comment(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "In Progress", "reason": "Blocked"}]
    comments = [{"body": "just chatting"}, {"body": "dev-runner: build failed at check gate"}]
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"],
             _base_env(tmp_path, binp, states, comments=comments))
    assert r.returncode == 3
    assert "dev-runner: build failed at check gate" in r.stdout
    assert "just chatting" not in r.stdout   # the LATEST runner comment only, not every comment


def test_exit3_on_needs_info(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "Backlog", "reason": "Needs-info"}]
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"],
             _base_env(tmp_path, binp, states))
    assert r.returncode == 3


def test_exit4_on_timeout(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "In Progress"}]   # never reaches a terminal state
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "0"],
             _base_env(tmp_path, binp, states))
    assert r.returncode == 4


# ============ transitions printed as they happen ============

def test_transitions_are_printed_across_polls(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "In Progress"}, {"status": "In Review", "pr_open": True}]
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "30"],
             _base_env(tmp_path, binp, states))
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stderr.splitlines() if l.startswith("watch-build:")]
    assert len(lines) >= 2
    assert "status=In Progress" in lines[0]
    assert "status=In Review" in lines[-1] and "pr=https://example/pr/1" in lines[-1]


def test_no_transition_line_repeated_when_state_is_unchanged(tmp_path):
    """Polling the same unchanged state twice before timing out prints only ONE transition line —
    the watcher reports transitions, not every poll tick."""
    binp = _bin(tmp_path)
    states = [{"status": "In Progress"}]
    r = _run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "0"],
             _base_env(tmp_path, binp, states))
    assert r.returncode == 4
    lines = [l for l in r.stderr.splitlines() if l.startswith("watch-build:")]
    assert len(lines) == 1


# ============ repo auto-detection ============

def test_repo_is_auto_detected_when_not_given(tmp_path):
    binp = _bin(tmp_path)
    states = [{"status": "Done"}]
    r = _run(["7", "--interval", "0", "--timeout", "10"], _base_env(tmp_path, binp, states))
    assert r.returncode == 2   # only reachable if `gh repo view` resolution succeeded


# ============ no LLM anywhere ============

def test_script_never_invokes_an_llm():
    text = SCRIPT.read_text().lower()
    assert "claude" not in text
