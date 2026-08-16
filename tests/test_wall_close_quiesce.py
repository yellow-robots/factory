"""it-31 slice 1 (#433): the close loop quiesces, and walls judge what an act can do.

The oscillation class (session 4c02860c, 2026-08-15): the wall's own close bookkeeping re-armed
the block forever. These tests pin the quiesce cycle (block once, loud once, then silence), the
terminal disposition for refusals that resolve no transition, the act-evidence exemptions
(same-value stamp; an append that cannot touch frontmatter), and the close path's dry-run
isolation. Fixtures only — sources stubbed at the `tools/sources.py` seam, like test_wall.py.
"""

import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import process  # noqa: E402
import sources  # noqa: E402
import wall  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}


@pytest.fixture(scope="module")
def model():
    return process.load()


def _stub_trail(monkeypatch, texts, ts="2026-08-08T01:00:00Z"):
    monkeypatch.setattr(sources, "issue_trail", lambda repo, issue: (True, list(texts)))
    monkeypatch.setattr(sources, "issue_trail_timed",
                        lambda repo, issue: (True, [(ts, t) for t in texts]))


def _vault_doc(tmp_path, monkeypatch, text):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")
    return doc


def test_close_terminal_refusal_exits_the_cycle_immediately(model, tmp_path, monkeypatch):
    """The production shape (session 4c02860c): a refusal that resolves NO transition
    (`store:*` id) has no lawful later pass by construction — the refusal was the correct final
    outcome. The close records `refusal-terminal` and stays SILENT: no block, ever."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [
        {"ts": 1786825869, "transition_id": "store:doc.frontmatter.status",
         "binding_id": "design.stamp.app-write", "scope": {}, "stance": "advise",
         "caller": "attended-agent"},
        {"ts": 1786826042, "transition_id": "store:doc.frontmatter.status",
         "binding_id": "design.stamp.obsidian-mcp", "scope": {"path": "/v/x.md"},
         "stance": "refuse", "caller": "attended-agent"}], "sT")
    assert wall.close({"session_id": "sT"}) is None
    assert wall.close({"session_id": "sT"}) is None
    kinds = [r["stance"] for r in process.journal_rows(model, "sT")]
    assert "refusal-terminal" in kinds and "close-block" not in kinds
    assert kinds.count("refusal-terminal") == 1     # recorded once, not per close


def test_close_override_is_terminal_for_unresolved_refusals(model, tmp_path, monkeypatch):
    """The oscillation regression: a REAL-transition refusal blocks once, overrides loud once,
    and a further close with traces unchanged ends SILENT — never a block/override alternation
    (the deployed 1.0.1 walls alternated forever; 9+9 rows observed before diagnosis)."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [{"ts": 100, "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sO")
    hook = {"session_id": "sO"}
    first = wall.close(hook)
    assert first is not None and first.get("decision") == "block"
    second = wall.close(hook)
    assert second is not None and "decision" not in second
    assert "OVERRIDE" in second["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None
    assert wall.close(hook) is None
    kinds = [r["stance"] for r in process.journal_rows(model, "sO")]
    assert kinds.count("close-block") == 1 and kinds.count("close-override") == 1


def test_close_new_refusal_after_override_rearms_the_cycle_once(model, tmp_path, monkeypatch):
    """Traces CHANGED after the override — a genuinely new refusal — re-arm exactly one more
    block/override pair; silence returns after. A controlled clock orders every journal row the
    way production does (a refusal always precedes the closes that judge it): `wall` and
    `process` share the `time` module singleton, so one patch covers both journal clocks."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    tick = {"t": 1000}

    def fake_time():
        tick["t"] += 1
        return tick["t"]

    monkeypatch.setattr(time, "time", fake_time)
    process.journal_append(model, [{"ts": 100, "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sN")
    hook = {"session_id": "sN"}
    assert wall.close(hook).get("decision") == "block"
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None
    process.journal_append(model, [{"ts": int(fake_time()),
                                    "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sN")
    assert wall.close(hook).get("decision") == "block"
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None


def test_close_override_terminal_covers_missing_posts(model, tmp_path, monkeypatch):
    """A permitted transition whose mandated record is STILL missing follows the same cycle:
    block once, override once, silent while the trace is unchanged."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    _stub_trail(monkeypatch, ["no promote record here"])
    process.journal_append(model, [{"ts": 100, "transition_id": "task.backlog->ready.standalone",
                                    "binding_id": "board.write.gh-cli",
                                    "scope": {"repo": "r/r", "issue": "1"},
                                    "stance": "observe", "caller": "human"}], "sM")
    hook = {"session_id": "sM"}
    assert wall.close(hook).get("decision") == "block"
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None


def test_same_value_stamp_is_not_a_transition(model, tmp_path, monkeypatch):
    """An act that provably cannot change a guarded store's value is not judged as that store's
    transition: the same-value mcp stamp observes silently — the production refusal class."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\nbody\n")
    hook = {"tool_name": "mcp__obsidian__vault_patch", "session_id": "sV",
            "tool_input": {"path": str(doc), "targetType": "frontmatter", "target": "status",
                           "operation": "replace", "content": "draft"}}
    out, rows = process.decide(model, hook, env=ATTENDED)
    assert out is None
    assert rows and rows[0]["stance"] == "observe"


def test_append_that_cannot_touch_frontmatter_is_silent(model, tmp_path, monkeypatch):
    """The vault NOTE cried wolf on 100% of writes: an append whose visible text can neither open
    a frontmatter fence nor carry the status key draws NO advisory; one that could still does."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\nbody\n")
    prose = {"tool_name": "mcp__obsidian__vault_append", "session_id": "sA",
             "tool_input": {"path": str(doc), "content": "a plain prose line, no fences"}}
    out, rows = process.decide(model, prose, env=ATTENDED)
    assert out is None
    assert rows and rows[0]["stance"] == "observe"
    risky = {"tool_name": "mcp__obsidian__vault_append", "session_id": "sA",
             "tool_input": {"path": str(doc), "content": "status: active"}}
    out2, _ = process.decide(model, risky, env=ATTENDED)
    assert out2 is not None and "additionalContext" in out2["hookSpecificOutput"]


def test_close_dry_run_decides_without_journaling(model, tmp_path, monkeypatch):
    """Test mode writes no live rows: the close path in dry-run computes the same decision but
    appends nothing — no block row, no terminal row (the admitted test-mode proposal)."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [
        {"ts": 100, "transition_id": "store:doc.frontmatter.status", "binding_id": None,
         "scope": {}, "stance": "refuse", "caller": "attended-agent"},
        {"ts": 110, "transition_id": "pr.approved->merged.evaluator", "binding_id": "merge.gh-cli",
         "scope": {}, "stance": "refuse", "caller": "attended-agent"}], "sY")
    out = wall.close({"session_id": "sY"}, no_journal=True)
    assert out is not None and out.get("decision") == "block"
    kinds = [r["stance"] for r in process.journal_rows(model, "sY")]
    assert "refusal-terminal" not in kinds and "close-block" not in kinds
