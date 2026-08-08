"""The wall engine (tools/wall.py) + the two in-funnel walls (it-30 slice 5, epic #415).

Offline throughout: gh is stubbed on PATH, the vault is a tmp fixture, counts go to a tmp state dir.
Every refusal must NAME THE RULE — the talking wall is the teaching mechanism, and the tests pin it.
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


@pytest.fixture()
def wall(tmp_path, monkeypatch):
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path / "vault"))
    import wall as w
    importlib.reload(w)
    return w


def _hook(tool, tool_input, session="s1"):
    return {"session_id": session, "tool_name": tool, "tool_input": tool_input}


# ── classification + decisions ───────────────────────────────────────────────────────────────────

def test_hand_merge_categorically_refused(wall):
    out = wall.decide(_hook("Bash", {"command": "gh pr merge 422 --repo yellow-robots/factory --squash"}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "evaluator" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_push_main_refused_own_task_branch_lawful(wall):
    deny = wall.decide(_hook("Bash", {"command": "git push origin main"}))
    assert deny and "branch protection" in deny["hookSpecificOutput"]["permissionDecisionReason"]
    assert wall.decide(_hook("Bash", {"command": "git push -u origin task/416-record-registry"})) is None
    other = wall.decide(_hook("Bash", {"command": "git push origin somebody-elses-branch"}))
    assert other and "explicit instruction" in other["hookSpecificOutput"]["permissionDecisionReason"]


def test_board_write_and_lifecycle_and_arming_and_release_and_vault_fs(wall, tmp_path):
    for tool, ti, key in (
        ("Bash", {"command": "python3 tools/board_plumbing.py set-field --id X --status Ready"}, "YR-BOARD-FLIP"),
        ("mcp__obsidian__vault_patch",
         {"targetType": "frontmatter", "target": "status", "content": '"active"', "path": "x.md"}, "accept act"),
        ("Edit", {"file_path": "/repo/.yr/factory.toml"}, "exclusively by the human"),
        ("Edit", {"file_path": "/repo/.claude-plugin/plugin.json"}, "freeze checks"),
        ("Write", {"file_path": str(tmp_path / "vault" / "04 projects" / "x.md")}, "off-table"),
    ):
        out = wall.decide(_hook(tool, ti))
        assert out, (tool, ti)
        assert key in out["hookSpecificOutput"]["permissionDecisionReason"], key


def test_unwalled_calls_stay_silent(wall):
    assert wall.decide(_hook("Bash", {"command": "ls -la"})) is None
    assert wall.decide(_hook("Bash", {"command": "gh pr view 422 --json body"})) is None
    assert wall.decide(_hook("Write", {"file_path": "/tmp/scratch.md"})) is None
    assert wall.decide(_hook("Read", {"file_path": "/anything"})) is None


def test_crossing_active_design_passes_inactive_refuses_unreadable_refuses(wall, tmp_path):
    vault = tmp_path / "vault" / "04 projects" / "factory" / "iterations" / "30-x"
    vault.mkdir(parents=True)
    (vault / "01-x.md").write_text("---\nstatus: active\n---\n", encoding="utf-8")
    body_ok = tmp_path / "ok.md"
    body_ok.write_text("**Source:** product-spec [[04 projects/factory/iterations/30-x/01-x]] …", encoding="utf-8")
    assert wall.decide(_hook("Bash", {"command": f"gh issue create --repo r --body-file {body_ok}"})) is None
    (vault / "01-x.md").write_text("---\nstatus: draft\n---\n", encoding="utf-8")
    deny = wall.decide(_hook("Bash", {"command": f"gh issue create --repo r --body-file {body_ok}"}))
    assert deny and "active" in deny["hookSpecificOutput"]["permissionDecisionReason"]
    deny2 = wall.decide(_hook("Bash", {"command": "gh issue create --repo r --body-file /nope.md"}))
    assert deny2 and "could not be read" in deny2["hookSpecificOutput"]["permissionDecisionReason"]


def test_commit_trailer_discipline(wall, tmp_path):
    ok = 'git commit -m "msg\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>"'
    assert wall.decide(_hook("Bash", {"command": ok})) is None
    deny = wall.decide(_hook("Bash", {"command": 'git commit -m "no trailer"'}))
    assert deny and "Co-Authored-By" in deny["hookSpecificOutput"]["permissionDecisionReason"]
    f = tmp_path / "msg.txt"
    f.write_text("body\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n", encoding="utf-8")
    assert wall.decide(_hook("Bash", {"command": f"git commit -F {f}"})) is None


# ── counts + close ───────────────────────────────────────────────────────────────────────────────

def test_refusals_land_in_counts(wall):
    wall.decide(_hook("Bash", {"command": "git push origin main"}, session="sX"))
    rows = wall.read_counts("sX")
    assert rows and rows[-1]["kind"] == "refusal" and rows[-1]["act"] == "push-main"


def test_close_silent_with_no_activity(wall):
    assert wall.close_check({"session_id": "quiet"}) is None


def test_close_blocks_once_then_overrides_loud(wall):
    wall.decide(_hook("Bash", {"command": "git push origin main"}, session="sC"))
    first = wall.close_check({"session_id": "sC"})
    assert first and first["decision"] == "block" and "push-main" in first["reason"]
    second = wall.close_check({"session_id": "sC"})
    assert second is None
    kinds = [r["kind"] for r in wall.read_counts("sC")]
    assert "close-block" in kinds and "close-override" in kinds


# ── the promote wall (stubbed gh) ────────────────────────────────────────────────────────────────

def _stub_gh(tmp_path, comment_bodies, rc=0):
    """A gh whose `issue view --json comments` returns the given bodies — the shape both the real gh
    and the harness fake produce, and the shape the wall parses."""
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir(exist_ok=True)
    payload = tmp_path / "bin" / "payload.json"
    payload.write_text(json.dumps({"comments": [{"body": b} for b in comment_bodies]}), encoding="utf-8")
    gh.write_text(f"#!/bin/sh\ncat > /dev/null\ncat {payload}\nexit {rc}\n")
    gh.chmod(0o755)
    return str(gh.parent)


def test_promote_check_passes_with_record(wall, tmp_path, monkeypatch):
    trail = "YR-TASK-GATES\nreview: passed cold\nfit: FIT\nwho: operator\n"
    monkeypatch.setenv("PATH", _stub_gh(tmp_path, [trail]) + os.pathsep + os.environ["PATH"])
    assert wall.promote_check("o/r", "7") == 0


def test_promote_check_refuses_without_record_and_promoted_never_satisfies(wall, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", _stub_gh(tmp_path, ["YR-PROMOTED\nwho: @x\nwhy: y\ndate: z"]) + os.pathsep + os.environ["PATH"])
    assert wall.promote_check("o/r", "7") == 1
    assert "YR-TASK-GATES" in capsys.readouterr().err


def test_promote_check_refuses_when_trail_unreadable(wall, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", _stub_gh(tmp_path, [], rc=1) + os.pathsep + os.environ["PATH"])
    assert wall.promote_check("o/r", "7") == 1
    assert "cannot evaluate" in capsys.readouterr().err


# ── the board funnel wall ────────────────────────────────────────────────────────────────────────

def test_board_funnel_untouched_for_non_attended_callers(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("YR_MACHINERY", raising=False)
    import board_plumbing
    calls = []
    board_plumbing.set_field(lambda argv: calls.append(argv), "ITEM", "FIELD", "OPT")
    assert calls and "--single-select-option-id" in calls[0]


def test_board_funnel_passes_declared_machinery_even_under_an_attended_session(monkeypatch):
    """The declaration is load-bearing: the runner's own integration tests run INSIDE an attended
    session and inherit CLAUDECODE — sniffing alone refused the machinery's own writes."""
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("YR_MACHINERY", "1")
    import board_plumbing
    calls = []
    board_plumbing.set_field(lambda argv: calls.append(argv), "ITEM", "FIELD", "OPT")
    assert calls


def test_board_funnel_marker_literal_agrees_with_its_registry_row():
    """board_plumbing spells the prefix check inline (stdlib-only home). The literal and the mode
    must match the registry row, or the funnel and the registry drift apart silently."""
    import records
    row = records.get(records.load(), "YR-BOARD-FLIP")
    src = (REPO / "tools" / "board_plumbing.py").read_text(encoding="utf-8")
    assert f'l.startswith("{row["marker"]}")' in src, "the funnel's inline marker left its row"
    assert row["mode"] == "prefix", "the row's mode is no longer the one the inline check implements"


def test_runner_and_epic_gate_declare_themselves():
    runner = (REPO / "tools" / "dev-runner.sh").read_text(encoding="utf-8")
    assert "export YR_MACHINERY=1" in runner, "the runner no longer declares itself to the board wall"
    gate = (REPO / "tools" / "epic_gate.py").read_text(encoding="utf-8")
    assert 'setdefault("YR_MACHINERY"' in gate, "the epic gate no longer declares itself"


def test_board_funnel_refuses_attended_without_record(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv("YR_MACHINERY", raising=False)   # opt in to the ATTENDED path (conftest declares machinery)
    monkeypatch.delenv("YR_BOARD_WALL_OFF", raising=False)
    monkeypatch.setenv("PATH", _stub_gh_raw(tmp_path, "just prose, no record\n") + os.pathsep + os.environ["PATH"])
    import board_plumbing
    with pytest.raises(RuntimeError, match="YR-BOARD-FLIP"):
        board_plumbing.set_field(lambda argv: None, "ITEM", "FIELD", "OPT")


def _stub_gh_raw(tmp_path, text):
    """A gh whose stdout is raw text — the shape `gh api graphql --jq` produces for the board
    funnel's trail read (the funnel matches column-0 lines, not JSON)."""
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir(exist_ok=True)
    payload = tmp_path / "bin" / "raw.txt"
    payload.write_text(text, encoding="utf-8")
    gh.write_text(f"#!/bin/sh\ncat > /dev/null\ncat {payload}\nexit 0\n")
    gh.chmod(0o755)
    return str(gh.parent)


def test_board_funnel_passes_attended_with_record(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv("YR_MACHINERY", raising=False)
    monkeypatch.setenv("PATH", _stub_gh_raw(tmp_path, "YR-BOARD-FLIP: who=op to=Ready\n") + os.pathsep + os.environ["PATH"])
    import board_plumbing
    calls = []
    board_plumbing.set_field(lambda argv: calls.append(argv), "ITEM", "FIELD", "OPT")
    assert calls


def test_board_funnel_escape_is_explicit(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv("YR_MACHINERY", raising=False)
    monkeypatch.setenv("YR_BOARD_WALL_OFF", "1")
    import board_plumbing
    calls = []
    board_plumbing.set_field(lambda argv: calls.append(argv), "ITEM", "FIELD", "OPT")
    assert calls


# ── the CLI stays silent on unreadable hook input ────────────────────────────────────────────────

def test_cli_never_bricks_on_garbage_stdin(wall):
    out = subprocess.run([sys.executable, str(REPO / "tools" / "wall.py"), "pre-tool"],
                         input="not json", capture_output=True, text=True,
                         env=dict(os.environ, YR_WALL_STATE="/tmp/yr-wall-test-garbage"))
    assert out.returncode == 0 and out.stdout.strip() == ""
