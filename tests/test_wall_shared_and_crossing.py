"""it-31 slice 5 (#437): walls amendments — shared branches and the crossing condition.

The shared-branch push (neither main/master nor a task branch) becomes a guarded store write
whose one transition demands the human-instruction record on the branch's open PR trail — the
routable surface the record row already declares; no PR means the guard cannot be read and the
wall refuses fail-closed, teaching the route. The crossing condition returns as an invariant on
issue-creation acts carrying a Source line (cited from the registry by NAME — the model spells no
grammar), guarded through the governing-design resolver evaluated over the act's own body.
Fixtures only — sources stubbed at the seam.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import process  # noqa: E402
import records  # noqa: E402
import sources  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}
MACHINERY = {"YR_CALLER": "machinery"}


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture()
def reg(model):
    return model["_registry"]


def _bash(cmd, session="sS"):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": session}


def _instruction_text(reg):
    row = records.get(reg, "YR-HUMAN-INSTRUCTION")
    return row["marker"] + " push integration branch\n" + \
        "\n".join(f"{f}: x" for f in row["fields"]) + "\n"


def _stub_branch_route(monkeypatch, *, repo="yellow-robots/factory", pr="77", texts=None):
    monkeypatch.setattr(sources, "origin_repo", lambda cwd: (True, repo))
    if pr is None:
        monkeypatch.setattr(sources, "pr_for_branch",
                            lambda r, branch: (False, "no open PR fronts this branch"))
    else:
        monkeypatch.setattr(sources, "pr_for_branch", lambda r, branch: (True, pr))
    monkeypatch.setattr(sources, "pr_trail", lambda r, p: (True, list(texts or [])))


def test_shared_branch_push_without_record_refused(model, reg, monkeypatch):
    _stub_branch_route(monkeypatch, texts=["just chatter"])
    out, rows = process.decide(model, _bash("git push origin integration"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-HUMAN-INSTRUCTION" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_shared_branch_push_with_record_on_pr_trail_flows(model, reg, monkeypatch):
    _stub_branch_route(monkeypatch, texts=[_instruction_text(reg)])
    out, rows = process.decide(model, _bash("git push origin integration"), env=ATTENDED)
    assert out is None
    assert rows and rows[0]["stance"] == "observe"


def test_shared_branch_push_with_no_open_pr_refuses_naming_the_route(model, monkeypatch):
    _stub_branch_route(monkeypatch, pr=None)
    out, _ = process.decide(model, _bash("git push origin integration"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "could not be read" in reason or "no open PR" in reason


def test_force_spelling_hits_the_same_wall(model, monkeypatch):
    _stub_branch_route(monkeypatch, texts=["chatter"])
    out, _ = process.decide(model, _bash("git push origin +integration"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_and_task_branch_behavior_unchanged(model, monkeypatch):
    out, _ = process.decide(model, _bash("git push origin HEAD:main"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git.ref.main" in out["hookSpecificOutput"]["permissionDecisionReason"]
    ok, rows = process.decide(model, _bash("git push -u origin task/437-walls-amendments"),
                              env=ATTENDED)
    assert ok is None and rows == []


def test_machinery_shared_push_refused_fail_closed(model, monkeypatch):
    """The runner never pushes a non-task branch; a machinery act resolving this transition is
    refused (the sanctioned classes are human and attended-agent)."""
    _stub_branch_route(monkeypatch, texts=["chatter"])
    out, _ = process.decide(model, _bash("git push origin integration"), env=MACHINERY)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_crossing_with_inactive_design_refused(model, tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: draft\n---\n", encoding="utf-8")
    cmd = ('gh issue create --title "epic" '
           '--body "**Source:** product-spec [[04 projects/x/01-x]] (brain)"')
    out, _ = process.decide(model, _bash(cmd), env=ATTENDED)
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "design_not_active" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_crossing_with_active_design_flows(model, tmp_path, monkeypatch):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: active\n---\n", encoding="utf-8")
    cmd = ('gh issue create --title "epic" '
           '--body "**Source:** product-spec [[04 projects/x/01-x]] (brain)"')
    out, rows = process.decide(model, _bash(cmd), env=ATTENDED)
    assert out is None


def test_issue_create_without_source_line_flows(model, monkeypatch):
    out, rows = process.decide(model, _bash('gh issue create --title "plain task" --body "no crossing here"'),
                               env=ATTENDED)
    assert out is None


def test_crossing_body_file_is_read(model, tmp_path, monkeypatch):
    """A --body-file crossing is judged too — the enrichment reads the file, mirroring the
    trailer invariant's -F handling."""
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: draft\n---\n", encoding="utf-8")
    bf = tmp_path / "body.md"
    bf.write_text("**Source:** product-spec [[04 projects/x/01-x]] (brain)\n", encoding="utf-8")
    out, _ = process.decide(model, _bash(f'gh issue create --title "epic" --body-file {bf}'),
                            env=ATTENDED)
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_delete_spellings_are_walled(model, reg, monkeypatch):
    """Review finding 3: a shared-branch DELETION is a write to the guarded store — both the
    flag spelling and the empty-src refspec demand the record; neither falls through to the
    current-branch fallback."""
    _stub_branch_route(monkeypatch, texts=["chatter"])
    for cmd in ("git push origin --delete integration",
                "git push origin -d integration",
                "git push origin :integration"):
        out, _ = process.decide(model, _bash(cmd), env=ATTENDED)
        assert out is not None and out["hookSpecificOutput"]["permissionDecision"] == "deny", cmd


def test_tag_pushes_by_full_ref_flow_and_bare_names_stay_walled(model, monkeypatch):
    """Review finding 4: a tag pushed by its full ref is skipped (slice 7's release path pushes
    refs/tags/...); a bare name is ref-ambiguous and stays walled fail-closed — the documented
    direction, loud, with the full-ref spelling as the derivable route."""
    _stub_branch_route(monkeypatch, texts=["chatter"])
    ok, rows = process.decide(model, _bash("git push origin refs/tags/skill/v1.4.0"), env=ATTENDED)
    assert ok is None
    tags_only, _ = process.decide(model, _bash("git push origin --tags"), env=ATTENDED)
    assert tags_only is None
    bare, _ = process.decide(model, _bash("git push origin v1.0.0"), env=ATTENDED)
    assert bare is not None and bare["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_push_head_resolves_to_the_current_branch(model, monkeypatch):
    """Review finding 5: `git push origin HEAD` resolves through the repository — on a task
    branch it flows exactly like naming the branch."""
    out, rows = process.decide(model, _bash("git push origin HEAD"), env=ATTENDED)
    assert out is None and rows == []


def test_ref_containing_at_still_walled(model, monkeypatch):
    """Review finding 6: the remote-skip heuristic skips remote-shaped operands only — a ref
    spelled with @ still reaches the wall."""
    _stub_branch_route(monkeypatch, texts=["chatter"])
    out, _ = process.decide(model, _bash("git push origin HEAD@{1}:integration"), env=ATTENDED)
    assert out is not None and out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_unreadable_body_file_refuses_fail_closed(model, monkeypatch):
    """Review finding 2: a DECLARED body file that cannot be read is UNKNOWN, never a silent
    pass — the parallel of the trailer invariant's own fail-closed shape."""
    out, _ = process.decide(model, _bash("gh issue create --title t -F /nonexistent/body.md"),
                            env=ATTENDED)
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "could not be read" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_two_open_prs_front_the_branch_refuses_ambiguity(model, reg, monkeypatch):
    """Review finding 7's sharp edge: two PRs fronting the branch is an ambiguous route — the
    wall refuses naming it rather than silently reading one of the two."""
    monkeypatch.setattr(sources, "origin_repo", lambda cwd: (True, "yellow-robots/factory"))
    monkeypatch.setattr(sources, "pr_for_branch",
                        lambda r, b: (False, "two open PRs front this branch — ambiguous route"))
    out, _ = process.decide(model, _bash("git push origin integration"), env=ATTENDED)
    assert out is not None and out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_registry_readers_note_names_the_wall(reg):
    row = records.get(reg, "YR-HUMAN-INSTRUCTION")
    joined = " ".join(row["readers"])
    assert "no wall reads it yet" not in joined
