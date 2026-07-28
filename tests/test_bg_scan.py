"""Unit tests for tools/bg_scan.py (issue #306) — the transcript scan for an unresolved CLI-managed
background-task conversion, derived directly from the acceptance criteria and Context's structural
grammar, never from the module's own internals. Hand-authored fixture transcripts only (minimal JSONL,
no live CLI, no dev-runner.sh subprocess).

Covered:
  * an unresolved conversion (no later reference to the task id at all) is reported unresolved;
  * resolution counts only positive terminal evidence: a kill/stop tool_use naming the id, a
    background-status tool_result reporting a terminal state, or any other completion notification
    naming the id;
  * resolution does NOT count: a status read that still reports "running", an assistant's own prose
    mention of the id, or a plain (non-kill/stop) tool_use that merely names the id;
  * the self-match defense: the marker text embedded inside a line-numbered (Read-style) or
    JSON-quoted (cat-style) tool_result must never match — the whole reason the grammar is
    start-anchored and block-scoped instead of a raw substring search;
  * a missing, empty, or unparseable transcript degrades to parsed=False (log-and-continue, never a
    gate) — positive, session-attributed evidence only;
  * the CLI surface (`bg_scan.py scan --transcript ...`) dev-runner.sh actually shells out to.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bg_scan  # noqa: E402

MARKER = "Command running in background with ID: {tid}. Output is being written to: /tmp/out-{tid}.log"


def _event(role, content):
    return json.dumps({"type": role, "message": {"content": content}})


def _tool_result(text, tool_use_id="toolu_1"):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}


def _text(text):
    return {"type": "text", "text": text}


def _tool_use(name, input_obj, tool_id="toolu_x"):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": input_obj}


def _conversion_line(tid):
    return _event("user", [_tool_result(MARKER.format(tid=tid))])


def _write(tmp_path, name, lines):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n")
    return p


# ============ the core grammar: unresolved vs resolved ============

def test_unresolved_conversion_with_no_later_reference_is_reported(tmp_path):
    p = _write(tmp_path, "t.jsonl", [
        _event("assistant", [_text("Running the suite now.")]),
        _conversion_line("bgtask1"),
    ])
    result = bg_scan.scan(str(p))
    assert result["parsed"] is True
    assert result["unresolved"] == ["bgtask1"]


def test_resolved_via_kill_stop_tool_use_naming_the_id(tmp_path):
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _event("assistant", [_tool_use("KillShell", {"shell_id": "bgtask1"})]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == []


def test_resolved_via_terminal_status_tool_result(tmp_path):
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _event("user", [_tool_result("Task bgtask1 is no longer running (exit 0).")]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == []


def test_resolved_via_completion_notification_naming_the_id(tmp_path):
    """A completion notification — a later event naming the id that is not a still-running status
    read — counts as resolution even without the words "no longer running"."""
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _event("user", [_tool_result("Background task bgtask1 finished with exit code 0.")]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == []


def test_still_running_status_read_does_not_resolve(tmp_path):
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _event("user", [_tool_result("Task bgtask1 is still running.")]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == ["bgtask1"]


def test_assistant_prose_mention_does_not_resolve(tmp_path):
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _event("assistant", [_text("I'll check on bgtask1 again before ending my turn.")]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == ["bgtask1"]


def test_non_kill_tool_use_naming_the_id_does_not_resolve(tmp_path):
    """A plain status-check tool_use (not named kill/stop) that happens to name the id is not itself
    resolution — only a following status read (or its absence) decides that."""
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _event("assistant", [_tool_use("BashOutput", {"bash_id": "bgtask1"})]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == ["bgtask1"]


def test_multiple_conversions_tracked_independently(tmp_path):
    p = _write(tmp_path, "t.jsonl", [
        _conversion_line("bgtask1"),
        _conversion_line("bgtask2"),
        _event("assistant", [_tool_use("KillShell", {"shell_id": "bgtask1"})]),
    ])
    result = bg_scan.scan(str(p))
    assert result["unresolved"] == ["bgtask2"]


# ============ the self-match defense ============
# A stage `Read`ing or `cat`ing a fixture transcript that itself contains this marker must never trip
# its own scan — the marker text is never at position 0 of the tool_result it appears inside.

def test_line_numbered_read_style_dump_does_not_self_match(tmp_path):
    """`Read`'s `cat -n`-style line-number prefix pushes the marker text off position 0."""
    dumped = "    42\t" + MARKER.format(tid="bgtask1")
    p = _write(tmp_path, "t.jsonl", [
        _event("user", [_tool_result(dumped)]),
    ])
    result = bg_scan.scan(str(p))
    assert result["parsed"] is True
    assert result["unresolved"] == []


def test_json_quoted_cat_style_dump_does_not_self_match(tmp_path):
    """`cat` shows the marker buried inside a JSON-encoded transcript line — the outer tool_result's
    own text starts with `{`, never the marker itself."""
    inner_line = _conversion_line("bgtask1")   # itself a JSON string (json.dumps'd transcript event)
    p = _write(tmp_path, "t.jsonl", [
        _event("user", [_tool_result(inner_line)]),
    ])
    result = bg_scan.scan(str(p))
    assert result["parsed"] is True
    assert result["unresolved"] == []


# ============ missing / unparseable transcripts: log and continue, never gate on their own absence ====

def test_missing_file_is_not_gating(tmp_path):
    result = bg_scan.scan(str(tmp_path / "does-not-exist.jsonl"))
    assert result == {"parsed": False, "unresolved": []}


def test_unparseable_file_is_not_gating(tmp_path):
    p = tmp_path / "garbage.jsonl"
    p.write_text("not json at all\n{{{broken\n")
    result = bg_scan.scan(str(p))
    assert result == {"parsed": False, "unresolved": []}


def test_empty_file_is_not_gating(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    result = bg_scan.scan(str(p))
    assert result == {"parsed": False, "unresolved": []}


def test_partially_unparseable_file_still_scans_the_good_lines(tmp_path):
    """A truncated tail line (a hard-killed session) is skipped on its own, not fatal to the whole
    file — the rest of the transcript is still scanned normally."""
    p = tmp_path / "half.jsonl"
    p.write_text(_conversion_line("bgtask1") + "\n{not valid json\n")
    result = bg_scan.scan(str(p))
    assert result["parsed"] is True
    assert result["unresolved"] == ["bgtask1"]


# ============ the CLI surface dev-runner.sh actually shells out to ============

def test_cli_scan_prints_json_result(tmp_path):
    p = _write(tmp_path, "t.jsonl", [_conversion_line("bgtask1")])
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "bg_scan.py"), "scan", "--transcript", str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"parsed": True, "unresolved": ["bgtask1"]}


def test_cli_scan_missing_transcript_reports_unparsed(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "bg_scan.py"), "scan",
         "--transcript", str(tmp_path / "nope.jsonl")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"parsed": False, "unresolved": []}
