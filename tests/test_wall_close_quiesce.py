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
                           "operation": "replace", "value": "draft"}}
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


def test_whole_file_writes_keep_the_advisory(model, tmp_path, monkeypatch):
    """Review finding 1 + re-review finding 1: only an APPEND is removal-safe. Write /
    vault_write replace the file (content omitting the key deletes it by truncation), and an
    Edit's match site is unknowable from the act alone (a bare VALUE substring lands inside the
    key's line) — all three keep the advisory."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\nbody\n")
    fs = {"tool_name": "Write", "session_id": "sW",
          "tool_input": {"file_path": str(doc), "content": "plain prose, no fences at all"}}
    out, _ = process.decide(model, fs, env=ATTENDED)
    assert out is not None and "additionalContext" in out["hookSpecificOutput"]
    app = {"tool_name": "mcp__obsidian__vault_write", "session_id": "sW",
           "tool_input": {"path": str(doc), "content": "plain prose, no fences at all"}}
    out2, _ = process.decide(model, app, env=ATTENDED)
    assert out2 is not None and "additionalContext" in out2["hookSpecificOutput"]
    edit = {"tool_name": "Edit", "session_id": "sW",
            "tool_input": {"file_path": str(doc), "old_string": "body",
                           "new_string": "body, amended"}}
    out3, _ = process.decide(model, edit, env=ATTENDED)
    assert out3 is not None and "additionalContext" in out3["hookSpecificOutput"]


def test_edit_value_substring_cannot_slip_the_wall(model, tmp_path, monkeypatch):
    """Re-review finding 1, the exact attack: Edit old_string="draft" matches INSIDE
    `status: draft` and produces `status: active` — the input-gate transition — so an Edit is
    never exempt: token absence proves the text isn't the key's line, not where the match lands."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\nbody\n")
    edit = {"tool_name": "Edit", "session_id": "sE2",
            "tool_input": {"file_path": str(doc), "old_string": "draft",
                           "new_string": "active"}}
    out, _ = process.decide(model, edit, env=ATTENDED)
    assert out is not None and "additionalContext" in out["hookSpecificOutput"]


def test_missing_post_in_a_second_scope_rearms(model, tmp_path, monkeypatch):
    """Re-review finding 2: the missing-advised anchor is scope-aware — issue 2's missing record
    is a NEW trace even after issue 1's identical (transition, record) pair was overridden."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    _stub_trail(monkeypatch, ["no promote record here"])
    process.journal_append(model, [{"ts": 100, "transition_id": "task.backlog->ready.standalone",
                                    "binding_id": "board.write.gh-cli",
                                    "scope": {"repo": "r/r", "issue": "1"},
                                    "stance": "observe", "caller": "human"}], "sSc")
    hook = {"session_id": "sSc"}
    assert wall.close(hook).get("decision") == "block"
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None
    process.journal_append(model, [{"ts": int(time.time()),
                                    "transition_id": "task.backlog->ready.standalone",
                                    "binding_id": "board.write.gh-cli",
                                    "scope": {"repo": "r/r", "issue": "2"},
                                    "stance": "observe", "caller": "human"}], "sSc")
    fourth = wall.close(hook)
    assert fourth is not None and fourth.get("decision") == "block"
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None


def test_spaced_colon_edit_keeps_the_advisory(model, tmp_path, monkeypatch):
    """Review finding 8: YAML accepts `status : draft`; the token evidence must too."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus : draft\n---\nbody\n")
    edit = {"tool_name": "Edit", "session_id": "sS",
            "tool_input": {"file_path": str(doc), "old_string": "status : draft",
                           "new_string": "status : active"}}
    out, _ = process.decide(model, edit, env=ATTENDED)
    assert out is not None and "additionalContext" in out["hookSpecificOutput"]


def test_invariant_refusal_stays_in_the_cycle(model, tmp_path, monkeypatch):
    """Review finding 2: an `invariant:*` refusal (the trailer-less commit) HAS a lawful
    agent-side resolution — retry with the trailer — and its retries are trackable by tid. It
    must block/override like any resolvable refusal, never be dispositioned terminal."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [{"ts": 100, "transition_id": "invariant:git.commit.trailer",
                                    "binding_id": None, "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sI")
    hook = {"session_id": "sI"}
    assert wall.close(hook).get("decision") == "block"
    kinds = [r["stance"] for r in process.journal_rows(model, "sI")]
    assert "refusal-terminal" not in kinds
    process.journal_append(model, [{"ts": 200, "transition_id": "invariant:git.commit.trailer",
                                    "binding_id": None, "scope": {}, "stance": "observe",
                                    "caller": "attended-agent"}], "sI")
    assert wall.close({"session_id": "sI"}) is None


def test_resolved_store_refusal_gets_no_terminal_row(model, tmp_path, monkeypatch):
    """Review finding 6: a `store:*` refusal RESOLVED by a later same-tid observe is not
    terminal — the journal must not carry a disposition the rows above it contradict."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [
        {"ts": 100, "transition_id": "store:manifest.auto_merge", "binding_id": "fs.write",
         "scope": {}, "stance": "refuse", "caller": "attended-agent"},
        {"ts": 200, "transition_id": "store:manifest.auto_merge", "binding_id": "fs.write",
         "scope": {}, "stance": "observe", "caller": "human"}], "sZ")
    assert wall.close({"session_id": "sZ"}) is None
    kinds = [r["stance"] for r in process.journal_rows(model, "sZ")]
    assert "refusal-terminal" not in kinds


def test_same_value_patch_with_mutating_operation_still_refused(model, tmp_path, monkeypatch):
    """Review finding 3: `operation: append` on a frontmatter key MUTATES the value even when
    the content equals the current value — "provably cannot change the store" holds for
    `replace` alone."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\nbody\n")
    hook = {"tool_name": "mcp__obsidian__vault_patch", "session_id": "sP2",
            "tool_input": {"path": str(doc), "targetType": "frontmatter", "target": "status",
                           "operation": "append", "value": "draft"}}
    out, _ = process.decide(model, hook, env=ATTENDED)
    assert out is not None
    assert out["hookSpecificOutput"].get("permissionDecision") == "deny"


def test_same_second_new_refusal_still_rearms(model, tmp_path, monkeypatch):
    """Review finding 4: at 1-second journal granularity, a refusal landing in the SAME second
    as the override — but after it in the journal sequence — is a new trace and re-arms; row
    order within the journal is the tiebreaker."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [{"ts": 100, "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sTie")
    hook = {"session_id": "sTie"}
    assert wall.close(hook).get("decision") == "block"
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    override_ts = max(r.get("ts", 0) for r in process.journal_rows(model, "sTie")
                      if r["stance"] == "close-override")
    process.journal_append(model, [{"ts": override_ts,
                                    "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sTie")
    assert wall.close(hook).get("decision") == "block"


def test_missing_post_detected_after_override_is_still_announced(model, tmp_path, monkeypatch):
    """Review finding 5: a mandated record whose absence is first DETECTED after the override
    (the trail was unreadable before) was never announced — the override cannot be terminal for
    a trace it never covered. Announcement, not the permitted row, anchors the trace."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    monkeypatch.setattr(sources, "issue_trail", lambda repo, issue: (False, "trail fetch flake"))
    monkeypatch.setattr(sources, "issue_trail_timed",
                        lambda repo, issue: (False, "trail fetch flake"))
    process.journal_append(model, [
        {"ts": 100, "transition_id": "task.backlog->ready.standalone",
         "binding_id": "board.write.gh-cli", "scope": {"repo": "r/r", "issue": "1"},
         "stance": "observe", "caller": "human"},
        {"ts": 110, "transition_id": "pr.approved->merged.evaluator",
         "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
         "caller": "attended-agent"}], "sL")
    hook = {"session_id": "sL"}
    assert wall.close(hook).get("decision") == "block"          # the refusal blocks; post UNKNOWN
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    _stub_trail(monkeypatch, ["no promote record here"])        # trail readable now: truly missing
    third = wall.close(hook)
    assert third is not None and third.get("decision") == "block"
    assert "MISSING" in third["reason"]
    assert "OVERRIDE" in wall.close(hook)["hookSpecificOutput"]["additionalContext"]
    assert wall.close(hook) is None


def test_upgrade_recovery_from_the_polluted_production_journal(model, tmp_path, monkeypatch):
    """Review finding 7 — the verbatim acceptance: a journal already carrying the production
    9+9 close-block/close-override alternation (session 4c02860c's shape, real timestamps)
    quiesces on the first post-upgrade close — silent, one terminal row, no new bookkeeping."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    rows = [
        {"ts": 1786825869, "transition_id": "store:doc.frontmatter.status",
         "binding_id": "design.stamp.app-write", "scope": {}, "stance": "advise",
         "caller": "attended-agent"},
        {"ts": 1786825996, "transition_id": "store:doc.frontmatter.status",
         "binding_id": "design.stamp.app-write", "scope": {}, "stance": "advise",
         "caller": "attended-agent"},
        {"ts": 1786826042, "transition_id": "store:doc.frontmatter.status",
         "binding_id": "design.stamp.obsidian-mcp", "scope": {"path": "/v/x.md"},
         "stance": "refuse", "caller": "attended-agent"}]
    alternation = [1786826197, 1786826235, 1786826245, 1786826263, 1786826271, 1786826291,
                   1786826296, 1786826311, 1786826317, 1786827812, 1786827822, 1786827828,
                   1786827835, 1786827841, 1786827849, 1786827855, 1786827862, 1786827868]
    for i, ts in enumerate(alternation):
        rows.append({"ts": ts, "transition_id": "close", "binding_id": None, "scope": {},
                     "stance": "close-block" if i % 2 == 0 else "close-override",
                     "caller": "attended-agent"})
    process.journal_append(model, rows, "sU")
    assert wall.close({"session_id": "sU"}) is None
    after = process.journal_rows(model, "sU")
    kinds = [r["stance"] for r in after]
    assert kinds.count("refusal-terminal") == 1
    assert kinds.count("close-block") == 9 and kinds.count("close-override") == 9


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
