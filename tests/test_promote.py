"""Acceptance tests for tools/promote.sh — the standalone-task promotion operator command (#53).

Stubbed `gh` (no network, no `claude`): a fake `gh` serves the canned issue-side GraphQL read and
RECORDS every call (in order) to a shared log file, so the promotion-record-before-status-flip claim
is a call-order assertion, not a convention taken on faith. Every refusal path (closed / off-board /
Type=Feature) is asserted to write NOTHING — no `issue comment`, no `project item-edit`.
"""
import json, os, stat, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "promote.sh"

GH_STUB = '''#!/usr/bin/env python3
import sys, os, json

argv = sys.argv[1:]
log = os.environ.get("STUB_CALLS_LOG")
if log:
    with open(log, "a") as f:
        print(json.dumps(argv), file=f)

if argv[:2] == ["repo", "view"]:
    print(os.environ.get("STUB_REPO", "test/repo"))
    sys.exit(0)

if argv[:2] == ["api", "graphql"]:
    print(os.environ["STUB_ISSUE_RESPONSE"])
    sys.exit(0)

if argv[:2] == ["api", "user"]:
    print(os.environ.get("STUB_WHO", "operator"))
    sys.exit(0)

if argv[:2] == ["issue", "comment"]:
    sys.exit(1 if os.environ.get("STUB_COMMENT_FAIL") else 0)

if argv[:2] == ["project", "item-edit"]:
    sys.exit(1 if os.environ.get("STUB_EDIT_FAIL") else 0)

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


def _response(*, state="OPEN", itype="Task", item_id="ITEM1", project_number=1, on_board=True):
    nodes = []
    if on_board:
        nodes.append({"id": item_id, "project": {"number": project_number}})
    return json.dumps({"data": {"repository": {"issue": {
        "state": state,
        "issueType": ({"name": itype} if itype else None),
        "projectItems": {"nodes": nodes},
    }}}})


def _env(tmp, binp, **kw):
    return {
        **os.environ,
        "GH_BIN": str(binp / "gh"),
        "STUB_ISSUE_RESPONSE": _response(**kw),
        "STUB_CALLS_LOG": str(tmp / "calls.log"),
        "STUB_REPO": "test/repo",
    }


def _run(args, env):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)


def _calls(tmp):
    p = tmp / "calls.log"
    return [json.loads(l) for l in p.read_text().splitlines() if l] if p.exists() else []


def _writes(calls):
    return [c for c in calls if c[:2] in (["issue", "comment"], ["project", "item-edit"])]


# ============ happy path: record before flip, by construction ============

def test_comment_posted_strictly_before_status_flip(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    calls = _calls(tmp_path)
    comment_idx = next(i for i, c in enumerate(calls) if c[:2] == ["issue", "comment"])
    edit_idx = next(i for i, c in enumerate(calls) if c[:2] == ["project", "item-edit"])
    assert comment_idx < edit_idx


def test_exactly_one_comment_and_one_status_edit(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    writes = _writes(_calls(tmp_path))
    comments = [c for c in writes if c[:2] == ["issue", "comment"]]
    edits = [c for c in writes if c[:2] == ["project", "item-edit"]]
    assert len(comments) == 1 and len(edits) == 1


def test_comment_body_carries_who_why_date_record(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo", "--reason", "DoR reviewed live"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    comment_call = next(c for c in _calls(tmp_path) if c[:2] == ["issue", "comment"])
    body = comment_call[comment_call.index("--body") + 1]
    assert "YR-PROMOTED" in body
    assert "who:" in body and "why: DoR reviewed live" in body and "date:" in body


def test_status_flip_targets_the_resolved_item_id(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, item_id="ITEM-XYZ"))
    assert r.returncode == 0, r.stderr
    edit_call = next(c for c in _calls(tmp_path) if c[:2] == ["project", "item-edit"])
    assert "ITEM-XYZ" in edit_call


# ============ refusals: write nothing ============

def test_refuses_closed_issue_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, state="CLOSED"))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refuses_issue_absent_from_board_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, on_board=False))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refuses_type_feature_epic_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, itype="Feature"))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refusal_exit_code_is_distinct_from_success(tmp_path):
    binp = _bin(tmp_path)
    ok = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp))
    refused = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, state="CLOSED"))
    assert ok.returncode == 0
    assert refused.returncode != 0 and refused.returncode != ok.returncode


# ============ no LLM anywhere ============

def test_script_never_invokes_an_llm():
    text = SCRIPT.read_text().lower()
    assert "claude" not in text
