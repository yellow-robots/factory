"""Acceptance tests for tools/board.sh — the one-shot board-scan operator command (#53).

Stubbed `gh` (no network, no `claude`): one `gh api graphql` call returns the org-wide
`organization.projectV2.items` shape; the script prints one TSV row per OPEN item
(issue · repo · type · status · reason · title), skipping closed items.
"""
import json, os, stat, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "board.sh"

GH_STUB = '''#!/usr/bin/env python3
import sys, os, json

argv = sys.argv[1:]
if argv[:2] == ["api", "graphql"]:
    nodes = json.loads(os.environ["STUB_NODES"])
    print(json.dumps({"data": {"organization": {"projectV2": {"items": {"nodes": nodes}}}}}))
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


def _node(number, *, repo="yr/repo", itype="Task", state="OPEN", status=None, reason=None, title="do a thing"):
    return {
        "content": {
            "number": number, "title": title, "state": state,
            "issueType": ({"name": itype} if itype else None),
            "repository": {"nameWithOwner": repo},
        },
        "status": ({"name": status} if status else None),
        "reason": ({"name": reason} if reason else None),
    }


def _run(tmp, nodes, extra_env=None):
    binp = _bin(tmp)
    env = {**os.environ, "GH_BIN": str(binp / "gh"), "STUB_NODES": json.dumps(nodes), **(extra_env or {})}
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)


def _rows(stdout):
    return [l.split("\t") for l in stdout.splitlines() if l]


# ============ one row per open item, correct column order ============

def test_one_row_per_open_item_with_correct_columns(tmp_path):
    nodes = [
        _node(7, repo="yr/alpha", itype="Task", status="In Progress", reason=None, title="Fix the thing"),
        _node(9, repo="yr/beta", itype="Feature", status="Ready", reason="Needs-info", title="Epic work"),
        _node(3, repo="yr/alpha", state="CLOSED", status="Done", title="Old done work"),
    ]
    r = _run(tmp_path, nodes)
    assert r.returncode == 0, r.stderr
    rows = _rows(r.stdout)
    assert len(rows) == 2   # the closed item is excluded
    by_num = {row[0]: row for row in rows}
    assert by_num["7"] == ["7", "yr/alpha", "Task", "In Progress", "", "Fix the thing"]
    assert by_num["9"] == ["9", "yr/beta", "Feature", "Ready", "Needs-info", "Epic work"]


def test_closed_items_are_excluded(tmp_path):
    nodes = [_node(1, state="CLOSED"), _node(2, state="CLOSED")]
    r = _run(tmp_path, nodes)
    assert r.returncode == 0, r.stderr
    assert _rows(r.stdout) == []


def test_missing_status_and_reason_render_as_empty_columns_not_null(tmp_path):
    nodes = [_node(5, status=None, reason=None)]
    r = _run(tmp_path, nodes)
    assert r.returncode == 0, r.stderr
    rows = _rows(r.stdout)
    assert len(rows) == 1
    assert rows[0][3] == "" and rows[0][4] == ""
    assert "null" not in r.stdout.lower() and "none" not in r.stdout.lower()


def test_each_row_has_six_tab_separated_fields(tmp_path):
    nodes = [_node(11, repo="yr/gamma", itype="Bug", status="Blocked", reason="Blocked", title="Broken thing")]
    r = _run(tmp_path, nodes)
    assert r.returncode == 0, r.stderr
    rows = _rows(r.stdout)
    assert len(rows) == 1 and len(rows[0]) == 6


def test_multiple_open_items_across_repos_all_present(tmp_path):
    nodes = [_node(1, repo="yr/a"), _node(2, repo="yr/b"), _node(3, repo="yr/c")]
    r = _run(tmp_path, nodes)
    assert r.returncode == 0, r.stderr
    numbers = {row[0] for row in _rows(r.stdout)}
    assert numbers == {"1", "2", "3"}


# ============ no LLM anywhere ============

def test_script_never_invokes_an_llm():
    text = SCRIPT.read_text().lower()
    assert "claude" not in text
