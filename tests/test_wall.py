"""The rebuilt walls (it-30 slice 5): a loop over process.toml's compiled rows, never per-act regexes.

Fixtures only — every source fetch is stubbed at the `tools/sources.py` seam. The suite declares
itself machinery (conftest); a test exercising the ATTENDED path sets `YR_CALLER=attended-agent`,
which wins over the bridge by construction (`resolve_caller` reads the declared class first).
Every refusal must NAME THE RULE — the talking wall is the teaching mechanism, and the tests pin it.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import board_plumbing  # noqa: E402
import process  # noqa: E402
import records  # noqa: E402
import sources  # noqa: E402
import wall  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}
MACHINERY = {"YR_CALLER": "machinery"}


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture()
def reg(model):
    return model["_registry"]


def _bash(cmd, session="s1"):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": session}


def _gates_text(reg):
    row = records.get(reg, "YR-TASK-GATES")
    return row["marker"] + "\n" + "\n".join(f"{f}: x" for f in row["fields"]) + "\n"


def _flip_text(reg):
    row = records.get(reg, "YR-BOARD-FLIP")
    return row["marker"] + " unblock\n" + "\n".join(f"{f}: x" for f in row["fields"]) + "\n"


def _stub_board(monkeypatch, status, reason=""):
    monkeypatch.setattr(sources, "board_item", lambda item_id: (True, {
        "status": status, "reason": reason, "updatedAt": "2026-08-08T00:00:00Z",
        "repo": "yellow-robots/factory", "issue": "420"}))


def _stub_trail(monkeypatch, texts, ts="2026-08-08T01:00:00Z"):
    monkeypatch.setattr(sources, "issue_trail", lambda repo, issue: (True, list(texts)))
    monkeypatch.setattr(sources, "issue_trail_timed",
                        lambda repo, issue: (True, [(ts, t) for t in texts]))


def _board_cmd(opt_name="Ready", field="status"):
    fid = board_plumbing.status_field_id() if field == "status" else board_plumbing.reason_field_id()
    opt = (board_plumbing.status_opt() if field == "status" else board_plumbing.reason_opt())[opt_name]
    return (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
            f"--field-id {fid} --single-select-option-id {opt}")


# ── the categorical rows: one word does the refusing ─────────────────────────────────────────────

def test_hand_merge_refused_naming_the_sanctioned_actor(model, monkeypatch):
    monkeypatch.setattr(sources, "pr_state", lambda repo, pr: (True, {
        "state": "OPEN", "reviewDecision": "APPROVED", "mergedAt": None}))
    out, rows = process.decide(model, _bash("gh pr merge 123 --repo yellow-robots/factory --squash"),
                               env=ATTENDED)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    # the store-permission tier fires first (the design's step 4): pr.merged is not writable by the
    # attended class at all, and the refusal names the store, the permitted classes, and the trust
    assert "pr.merged" in hso["permissionDecisionReason"]
    assert "machinery" in hso["permissionDecisionReason"]
    assert "caller_trust = declared" in hso["permissionDecisionReason"]
    assert any(r["stance"] == "refuse" for r in rows)


def test_hand_merge_graphql_spelling_hits_the_same_wall(model, monkeypatch):
    monkeypatch.setattr(sources, "pr_state", lambda repo, pr: (True, {
        "state": "OPEN", "reviewDecision": "APPROVED", "mergedAt": None}))
    cmd = 'gh api graphql -f query="mutation { mergePullRequest(input: {pullRequestId: \\"X\\"}) }"'
    out, _ = process.decide(model, _bash(cmd), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "machinery" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_push_main_refused_by_store_permission(model):
    out, _ = process.decide(model, _bash("git push origin HEAD:main"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git.ref.main" in out["hookSpecificOutput"]["permissionDecisionReason"]
    # machinery is walled off main just the same — only GitHub's merge advances it
    out2, _ = process.decide(model, _bash("git push origin main"), env=MACHINERY)
    assert out2["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_own_task_branch_push_flows(model):
    out, rows = process.decide(model, _bash("git push -u origin task/420-walls"), env=ATTENDED)
    assert out is None and rows == []


def test_arming_edit_refused_for_agent_and_machinery_alike(model, tmp_path):
    hook = {"tool_name": "Edit", "session_id": "s1",
            "tool_input": {"file_path": str(tmp_path / "r" / ".yr" / "factory.toml"),
                           "old_string": "auto_merge = false", "new_string": "auto_merge = true"}}
    for env in (ATTENDED, MACHINERY):
        out, _ = process.decide(model, hook, env=env)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "manifest.auto_merge" in out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "caller_trust = declared" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_manifest_edit_not_touching_arming_flows(model, tmp_path):
    hook = {"tool_name": "Edit", "session_id": "s1",
            "tool_input": {"file_path": str(tmp_path / "r" / ".yr" / "factory.toml"),
                           "old_string": 'check_cmd = "pytest"', "new_string": 'check_cmd = "pytest -q"'}}
    out, _ = process.decide(model, hook, env=ATTENDED)
    assert out is None


# ── the board writes: one mechanism, many transitions, resolved by where the machine is ──────────

def test_promote_without_gates_record_refused(model, reg, monkeypatch):
    _stub_board(monkeypatch, "Backlog")
    _stub_trail(monkeypatch, ["just chatter"])
    out, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-TASK-GATES" in reason and "task.backlog->ready.standalone" in reason


def test_promote_with_gates_record_escalates_to_the_human(model, reg, monkeypatch):
    _stub_board(monkeypatch, "Backlog")
    _stub_trail(monkeypatch, [_gates_text(reg)])
    out, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "task.backlog->ready.standalone" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_funnel_and_raw_spelling_resolve_the_same_transition(model, reg, monkeypatch):
    _stub_board(monkeypatch, "Backlog")
    _stub_trail(monkeypatch, ["chatter"])
    raw, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    funnel, _ = process.decide(
        model, _bash("python3 tools/board_plumbing.py set-field --id ITEM --status Ready"),
        env=ATTENDED)
    for out in (raw, funnel):
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "task.backlog->ready.standalone" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_unblock_needs_flip_record_and_passes_with_it(model, reg, monkeypatch):
    _stub_board(monkeypatch, "In Progress", "Blocked")
    _stub_trail(monkeypatch, ["chatter"])
    out, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-BOARD-FLIP" in reason and "task.blocked->ready.unblock" in reason
    _stub_trail(monkeypatch, [_flip_text(reg)])
    out2, rows = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    assert out2 is None                       # agent_may = execute, guards TRUE -> observe
    assert any(r["stance"] == "observe" for r in rows)


def test_unblock_window_a_stale_flip_record_licenses_nothing(model, reg, monkeypatch):
    """The `since-store-change` window at decision time: a flip record OLDER than the board item's
    last change never satisfies the unblock — one old record cannot license every future flip."""
    _stub_board(monkeypatch, "In Progress", "Blocked")          # updatedAt = 2026-08-08T00:00:00Z
    _stub_trail(monkeypatch, [_flip_text(reg)], ts="2026-01-01T00:00:00Z")
    out, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-BOARD-FLIP" in out["hookSpecificOutput"]["permissionDecisionReason"]
    # timestamps unreadable -> UNKNOWN -> refuse, never a silent pass
    monkeypatch.setattr(sources, "issue_trail_timed", lambda repo, issue: (False, "gh: down"))
    out2, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    assert out2["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_unreadable_board_state_refuses_naming_what_it_could_not_read(model, monkeypatch):
    monkeypatch.setattr(sources, "board_item", lambda item_id: (False, "gh: boom"))
    out, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "could not be read" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_machinery_claim_is_lawful_and_unmodeled_bounce_observes(model, monkeypatch):
    _stub_board(monkeypatch, "Ready")
    out, rows = process.decide(model, _bash(_board_cmd("In Progress")), env=MACHINERY)
    assert out is None                        # the claim is machinery's own transition
    _stub_board(monkeypatch, "In Progress")
    out2, rows2 = process.decide(model, _bash(_board_cmd("Needs-info", field="reason")),
                                 env=MACHINERY)
    assert out2 is None                       # v1: an unmodeled machinery act observes, journaled
    assert rows2 and all(r["stance"] == "observe" for r in rows2)


def test_attended_unmodeled_board_value_refuses(model, monkeypatch):
    _stub_board(monkeypatch, "In Progress")
    _stub_trail(monkeypatch, ["chatter"])
    out, _ = process.decide(model, _bash(_board_cmd("Needs-info", field="reason")), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "no lawful transition" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_evasion_spellings_still_hit_the_wall(model, monkeypatch):
    """The review's confirmed evasions, each now a segment the matcher sees: glued operators,
    an env-assignment prefix, a force-push refspec, and a duplicated innocent query flag."""
    monkeypatch.setattr(sources, "pr_state", lambda repo, pr: (True, {
        "state": "OPEN", "reviewDecision": "APPROVED", "mergedAt": None}))
    for cmd in (
        "echo x;gh pr merge 1 --repo yellow-robots/factory",          # glued `;`
        "true&&gh pr merge 1 --repo yellow-robots/factory",           # glued `&&`
        "FOO=1 gh pr merge 1 --repo yellow-robots/factory",           # env prefix hides the program
        'gh api graphql -f query="mutation { mergePullRequest(input: {}) }" -f query="query { viewer }"',
    ):
        out, _ = process.decide(model, _bash(cmd), env=ATTENDED)
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny", cmd
    out, _ = process.decide(model, _bash("git push origin +main"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"   # +main is a FORCE push


def test_machinery_merge_evaluates_the_guards_never_skips_them(model, monkeypatch):
    """The review's guard-skip: a machinery `gh pr merge` must run the merge guards, not observe
    through them — an unarmed repo refuses machinery too, naming the manifest."""
    monkeypatch.setattr(sources, "pr_state", lambda repo, pr: (True, {
        "state": "OPEN", "reviewDecision": "APPROVED", "mergedAt": None}))
    monkeypatch.setattr(sources, "manifest_at_base_tip",
                        lambda repo_dir, base_ref="origin/main": (True, "auto_merge = false\n"))
    out, _ = process.decide(model, _bash("gh pr merge 7 --repo yellow-robots/factory"),
                            env=MACHINERY)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "manifest.auto_merge" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_boundary_judges_the_target_not_only_the_cwd(model, tmp_path):
    """A session sitting in /tmp writing INTO a factory-governed tree is factory work: the arming
    edit refuses even though the cwd is out of scope."""
    hook = {"tool_name": "Edit", "session_id": "s1",
            "tool_input": {"file_path": str(REPO / ".yr" / "factory.toml"),
                           "old_string": "auto_merge = false", "new_string": "auto_merge = true"}}
    out, _ = process.decide(model, hook, env=ATTENDED, cwd=tmp_path)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "manifest.auto_merge" in out["hookSpecificOutput"]["permissionDecisionReason"]


# ── the vault: exact stamp binding asks; blind writes advise, never deny ─────────────────────────

def _vault_doc(tmp_path, monkeypatch, text):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")
    return doc


def test_lifecycle_stamp_with_records_asks_without_refuses(model, reg, tmp_path, monkeypatch):
    rows_txt = "".join(records.get(reg, n)["marker"] + " done\nwho: r\nverdict: pass\n"
                       for n in ("YR-DESIGN-REVIEW", "YR-DESIGN-FIT"))
    doc = _vault_doc(tmp_path, monkeypatch, f"---\nstatus: draft\n---\n{rows_txt}")
    hook = {"tool_name": "mcp__obsidian__vault_patch", "session_id": "s1",
            "tool_input": {"path": str(doc), "targetType": "frontmatter", "target": "status",
                           "operation": "replace", "content": "active"}}
    out, _ = process.decide(model, hook, env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"      # propose at a one-way door
    bare = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\nno records here\n")
    hook["tool_input"]["path"] = str(bare)
    out2, _ = process.decide(model, hook, env=ATTENDED)
    assert out2["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-DESIGN-REVIEW" in out2["hookSpecificOutput"]["permissionDecisionReason"]


def test_vault_fs_write_advises_never_denies(model, tmp_path, monkeypatch):
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\n")
    hook = {"tool_name": "Write", "session_id": "s1",
            "tool_input": {"file_path": str(doc), "content": "---\nstatus: active\n---\n"}}
    out, _ = process.decide(model, hook, env=ATTENDED)
    assert "additionalContext" in out["hookSpecificOutput"]
    assert "permissionDecision" not in out["hookSpecificOutput"]


# ── conduct tier ─────────────────────────────────────────────────────────────────────────────────

def test_untrailed_commit_refused_trailed_passes_editor_invisible(model):
    out, _ = process.decide(model, _bash('git commit -m "no trailer here"'), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Co-Authored-By" in out["hookSpecificOutput"]["permissionDecisionReason"]
    ok, _ = process.decide(
        model, _bash('git commit -m "fix\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>"'),
        env=ATTENDED)
    assert ok is None
    editor, _ = process.decide(model, _bash("git commit"), env=ATTENDED)
    assert editor is None                     # the body is not visible pre-execution: not matched
    machinery, _ = process.decide(model, _bash('git commit -m "runner commit"'), env=MACHINERY)
    assert machinery is None                  # the invariant walls the attended class only


# ── boundary, journal, close ─────────────────────────────────────────────────────────────────────

def test_out_of_scope_is_silence_with_no_journal(model, tmp_path):
    out, rows = process.decide(model, _bash("gh pr merge 1"), env=ATTENDED, cwd=tmp_path)
    assert out is None and rows == []


def test_journal_rides_the_wall_and_dry_run_skips_it(model, tmp_path, monkeypatch):
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("YR_CALLER", "attended-agent")
    monkeypatch.setattr(sources, "pr_state", lambda repo, pr: (True, {
        "state": "OPEN", "reviewDecision": "APPROVED", "mergedAt": None}))
    hook = _bash("gh pr merge 9 --repo yellow-robots/factory", session="sJ")
    wall.pre_tool(hook, no_journal=True)
    assert not (tmp_path / "state" / "journal.jsonl").exists()
    wall.pre_tool(hook)
    rows = process.journal_rows(model, "sJ")
    assert rows and rows[-1]["stance"] == "refuse"


def test_close_reports_missing_postconditions_and_blocks_once(model, tmp_path, monkeypatch):
    """Surface 4 tracks MANDATED TRACES: a transition this session was PERMITTED to perform whose
    record post never landed is surfaced (and counted as a detector finding) — never silent."""
    import json as _json
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    _stub_trail(monkeypatch, ["no promote record here"])
    process.journal_append(model, [{"ts": 100, "transition_id": "task.backlog->ready.standalone",
                                    "binding_id": "board.write.gh-cli",
                                    "scope": {"repo": "r/r", "issue": "1"},
                                    "stance": "observe", "caller": "human"}], "sP")
    text, block = process.close_report(model, "sP")
    assert "MISSING" in text and "YR-PROMOTED" in text and block
    counts = _json.loads(text.split("close report — ", 1)[1].splitlines()[0])
    assert counts["detector-findings"] == 1


def test_close_blocks_once_then_overrides_loud(model, tmp_path, monkeypatch):
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [{"ts": 100, "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sC")
    hook = {"session_id": "sC"}
    first = wall.close(hook)
    assert first["decision"] == "block" and "UNRESOLVED" in first["reason"]
    second = wall.close(hook)
    assert "decision" not in (second or {})
    assert "OVERRIDE" in second["hookSpecificOutput"]["additionalContext"]
    kinds = [r["stance"] for r in process.journal_rows(model, "sC")]
    assert "close-block" in kinds and "close-override" in kinds


def test_close_clean_session_is_silent(model, tmp_path, monkeypatch):
    """#428: a session with journal rows but NO actionable trace ends silent — and the same
    fixture emits once a trace IS actionable, so the silence is the decision, not a dead path."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [{"ts": 100, "transition_id": "store:doc.frontmatter.status",
                                    "binding_id": "design.stamp.app-write", "scope": {},
                                    "stance": "advise", "caller": "attended-agent"}], "sQ")
    assert wall.close({"session_id": "sQ"}) is None
    process.journal_append(model, [{"ts": 200, "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sQ")
    out = wall.close({"session_id": "sQ"})
    assert out is not None and out.get("decision") == "block"
    assert "close report — " in out["reason"]


def test_close_recovered_refusal_is_clean_silence(model, tmp_path, monkeypatch):
    """#428: counts never decide — a refusal later resolved by a lawful pass leaves refusals >= 1
    in the journal and a SILENT close (clean = no actionable trace, never counts-zero)."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [
        {"ts": 100, "transition_id": "store:manifest.auto_merge", "binding_id": "fs.write",
         "scope": {}, "stance": "refuse", "caller": "attended-agent"},
        {"ts": 200, "transition_id": "store:manifest.auto_merge", "binding_id": "fs.write",
         "scope": {}, "stance": "observe", "caller": "human"}], "sR")
    assert wall.close({"session_id": "sR"}) is None


def test_close_error_row_emits_never_silent(model, tmp_path, monkeypatch):
    """#428: a wall crash (stance `error`) appears in no count, but a session whose walls crashed
    is never clean — the close emits, non-blocking, naming the crash."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: [])
    process.journal_append(model, [
        {"ts": 100, "transition_id": "store:doc.frontmatter.status", "binding_id": None,
         "scope": {}, "stance": "advise", "caller": "attended-agent"},
        {"ts": 110, "transition_id": None, "binding_id": None, "scope": {}, "stance": "error",
         "caller": "?", "detail": "synthetic crash"}], "sE")
    out = wall.close({"session_id": "sE"})
    assert out is not None and "decision" not in out
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "ERROR" in ctx and "synthetic crash" in ctx and "never clean" in ctx


def test_close_drift_announces_once_per_session(model, tmp_path, monkeypatch):
    """#428 lands ruling 1B's close-report drift surface BOUNDED: an outstanding finding is
    announced at most once per session (drift is durable repo state — unbounded announcement is
    the wake/stop loop again). check_drift is stubbed: the drift tier stays advisory and the
    gating suite never asserts real build/ freshness."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift",
                        lambda m: ["build/lanes.toml: STALE against process.toml v1.0.0"])
    process.journal_append(model, [{"ts": 100, "transition_id": "store:doc.frontmatter.status",
                                    "binding_id": "design.stamp.app-write", "scope": {},
                                    "stance": "advise", "caller": "attended-agent"}], "sD")
    first = wall.close({"session_id": "sD"})
    assert first is not None and "decision" not in first
    assert "DRIFT (advisory)" in first["hookSpecificOutput"]["additionalContext"]
    assert wall.close({"session_id": "sD"}) is None
    kinds = [r["stance"] for r in process.journal_rows(model, "sD")]
    assert "drift-advised" in kinds


def test_close_rows_empty_stays_silent_even_when_drifted(model, tmp_path, monkeypatch):
    """#428: a rows-empty session never announces drift — the SessionStart banner is the
    every-session drift surface; the close speaks only to sessions with in-scope activity."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(process, "check_drift", lambda m: ["build/lanes.toml: STALE"])
    assert wall.close({"session_id": "sNothing"}) is None


def test_model_not_loading_is_loud_but_never_blocks(monkeypatch):
    def broken():
        raise process.ModelError("synthetic breakage")
    monkeypatch.setattr(process, "load", broken)
    out = wall.pre_tool(_bash("gh pr merge 1"))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "MODEL DOES NOT LOAD" in ctx and "walls are OFF" in ctx
    assert "permissionDecision" not in out["hookSpecificOutput"]


# ── the promote wall: promote.sh's seam, now the engine's transition-check ───────────────────────

def test_promote_check_passes_with_gates_record(model, reg, monkeypatch):
    monkeypatch.setattr(sources, "issue_board_position",
                        lambda repo, issue: (True, {"status": "Backlog", "reason": ""}))
    _stub_trail(monkeypatch, [_gates_text(reg)])
    assert wall.promote_check("yellow-robots/factory", "1") == 0


def test_promote_check_refuses_without_record_and_on_unreadable_trail(model, reg, monkeypatch, capsys):
    monkeypatch.setattr(sources, "issue_board_position",
                        lambda repo, issue: (True, {"status": "Backlog", "reason": ""}))
    _stub_trail(monkeypatch, ["YR-PROMOTED\n"])   # the funnel's own record never satisfies the gate
    assert wall.promote_check("yellow-robots/factory", "1") == 1
    assert "YR-TASK-GATES" in capsys.readouterr().err
    monkeypatch.setattr(sources, "issue_trail", lambda repo, issue: (False, "gh: down"))
    assert wall.promote_check("yellow-robots/factory", "1") == 1
    assert "UNKNOWN" in capsys.readouterr().err


# ── machinery declaration compatibility (the runner's standing export) ───────────────────────────

def test_yr_machinery_bridge_still_declares_machinery(model):
    assert process.resolve_caller(model, {"YR_MACHINERY": "1"}) == "machinery"
    assert process.resolve_caller(model, {}) == "attended-agent"          # fail-closed default
    assert process.resolve_caller(model, {"YR_CALLER": "human"}) == "human"
    assert process.resolve_caller(model, {"YR_CALLER": "nonsense"}) == "attended-agent"
