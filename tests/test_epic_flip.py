"""it-31 slice 4 (#436): the epic Ready flip gets its tool, facet, and records (ruling 5).

The model gains the issue-type facet (store `issue.type`, read through the board source) and the
epic-flip transition — discriminated from the standalone promote by `facet_is` guards on the type
facet, provably disjoint at load time and narrowed at runtime. The governing-design resolver is
one seam (`tools/design_resolver.py`, the delegation pattern: an evaluator, cited never copied),
parsing the epic body's Source line — a grammar that earns its registry row. The v1 mis-teaching
(an attended Feature flip refused with the standalone row's lesson) retires. The Ready+Blocked
unraise row closes the #432 gap: clearing a hold's Reason is a lawful attended act with the fresh
flip record. Fixtures only — sources stubbed at the seam.
"""

import subprocess as real_subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import board_plumbing  # noqa: E402
import process  # noqa: E402
import records  # noqa: E402
import sources  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture()
def reg(model):
    return model["_registry"]


def _bash(cmd, session="sF"):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": session}


def _stub_board(monkeypatch, status, reason="", itype="Task"):
    monkeypatch.setattr(sources, "board_item", lambda item_id: (True, {
        "status": status, "reason": reason, "itype": itype,
        "updatedAt": "2026-08-08T00:00:00Z",
        "repo": "yellow-robots/factory", "issue": "420"}))


def _stub_trail(monkeypatch, texts, ts="2026-08-08T01:00:00Z"):
    monkeypatch.setattr(sources, "issue_trail", lambda repo, issue: (True, list(texts)))
    monkeypatch.setattr(sources, "issue_trail_timed",
                        lambda repo, issue: (True, [(ts, t) for t in texts]))


def _stub_evaluator(monkeypatch, returncode=0, first_line=""):
    class _Out:
        def __init__(self):
            self.returncode = returncode
            self.stdout = first_line
            self.stderr = ""

    monkeypatch.setattr(process.subprocess, "run", lambda *a, **k: _Out())


def _approval_text(reg):
    row = records.get(reg, "YR-EPIC-APPROVAL")
    return row["marker"] + "\n" + "\n".join(f"{f}: x" for f in row["fields"]) + "\n"


def _gates_text(reg):
    row = records.get(reg, "YR-TASK-GATES")
    return row["marker"] + "\n" + "\n".join(f"{f}: x" for f in row["fields"]) + "\n"


def _flip_text(reg):
    row = records.get(reg, "YR-BOARD-FLIP")
    return row["marker"] + " unblock\n" + "\n".join(f"{f}: x" for f in row["fields"]) + "\n"


def _ready_cmd():
    return (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
            f"--field-id {board_plumbing.status_field_id()} "
            f"--single-select-option-id {board_plumbing.status_opt()['Ready']}")


def _clear_reason_cmd():
    return (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
            f"--field-id {board_plumbing.reason_field_id()} --clear")


def test_feature_flip_with_approval_and_active_design_escalates(model, reg, monkeypatch):
    """The lawful epic flip: Feature-typed, approval on the trail, no open question, the
    governing design resolves active — propose at a one-way door asks the human."""
    _stub_board(monkeypatch, "Backlog", itype="Feature")
    _stub_trail(monkeypatch, [_approval_text(reg)])
    _stub_evaluator(monkeypatch, returncode=0)
    out, _ = process.decide(model, _bash(_ready_cmd()), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "task.backlog->ready.epic-flip" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_feature_flip_without_approval_refuses_naming_the_approval(model, reg, monkeypatch):
    """The mis-teaching retires: a Feature flip's refusal names the epic row's own rule —
    the approval record — never YR-TASK-GATES."""
    _stub_board(monkeypatch, "Backlog", itype="Feature")
    _stub_trail(monkeypatch, ["chatter only"])
    _stub_evaluator(monkeypatch, returncode=0)
    out, _ = process.decide(model, _bash(_ready_cmd()), env=ATTENDED)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-EPIC-APPROVAL" in reason and "YR-TASK-GATES" not in reason


def test_feature_flip_with_inactive_design_refuses_naming_the_evaluator(model, reg, monkeypatch):
    _stub_board(monkeypatch, "Backlog", itype="Feature")
    _stub_trail(monkeypatch, [_approval_text(reg)])
    _stub_evaluator(monkeypatch, returncode=1, first_line="design_not_active")
    out, _ = process.decide(model, _bash(_ready_cmd()), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "design_not_active" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_task_type_still_routes_to_the_standalone_row(model, reg, monkeypatch):
    _stub_board(monkeypatch, "Backlog", itype="Task")
    _stub_trail(monkeypatch, [_gates_text(reg)])
    out, _ = process.decide(model, _bash(_ready_cmd()), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "task.backlog->ready.standalone" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_untyped_issue_flip_refuses_fail_closed(model, reg, monkeypatch):
    """An untyped issue (the attended children's own shape) matches neither discriminator —
    the write refuses; promotion of untyped work is nobody's lawful act."""
    _stub_board(monkeypatch, "Backlog", itype="")
    _stub_trail(monkeypatch, [_gates_text(reg)])
    out, _ = process.decide(model, _bash(_ready_cmd()), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_unraise_clears_a_blocked_ready_epic_with_the_fresh_flip_record(model, reg, monkeypatch):
    """The #432 gap closes: Ready+Blocked has a lawful attended clear — the fresh YR-BOARD-FLIP
    record licenses it, and without the record the wall teaches exactly that."""
    _stub_board(monkeypatch, "Ready", reason="Blocked", itype="Feature")
    _stub_trail(monkeypatch, [_flip_text(reg)])
    out, rows = process.decide(model, _bash(_clear_reason_cmd()), env=ATTENDED)
    assert out is None
    assert rows and rows[0]["stance"] == "observe"
    _stub_trail(monkeypatch, ["no flip record"])
    out2, _ = process.decide(model, _bash(_clear_reason_cmd()), env=ATTENDED)
    assert out2["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-BOARD-FLIP" in out2["hookSpecificOutput"]["permissionDecisionReason"]


def test_machinery_claim_still_clears_reason_from_ready(model, monkeypatch):
    """The unraise row must not steal machinery's claim: the runner's In Progress write with its
    by-design reason clear flows exactly as before."""
    _stub_board(monkeypatch, "Ready", itype="Task")
    _stub_trail(monkeypatch, ["chatter"])
    cmd = (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
           f"--field-id {board_plumbing.status_field_id()} "
           f"--single-select-option-id {board_plumbing.status_opt()['In Progress']}")
    out, rows = process.decide(model, _bash(cmd), env={"YR_CALLER": "machinery"})
    assert out is None
    assert rows and rows[0]["stance"] == "observe"


def test_registry_rows_exist(reg):
    ready = records.get(reg, "YR-EPIC-READY")
    assert ready["fields"] == ["design", "who"]
    source = records.get(reg, "SOURCE-LINE")
    assert source["marker"].startswith("**Source:**") or source["marker"].startswith("Source:")


def test_design_resolver_source_line_to_verdict(tmp_path, monkeypatch):
    """The resolver: epic body Source line -> vault doc -> status; exit 0 active, 1 with a token
    otherwise — the evaluator contract."""
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "factory" / "iterations" / "9-x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: active\n---\nbody\n", encoding="utf-8")
    body = "**Source:** product-spec [[04 projects/factory/iterations/9-x/01-x]] (Obsidian design brain)"
    import design_resolver
    assert design_resolver.check_body(body) == (0, "")
    doc.write_text("---\nstatus: draft\n---\nbody\n", encoding="utf-8")
    rc, token = design_resolver.check_body(body)
    assert rc == 1 and token == "design_not_active"
    rc2, token2 = design_resolver.check_body("no source line here")
    assert rc2 == 1 and token2 == "source_line_missing"


def test_transition_check_covers_the_epic_flip_row(model, reg, monkeypatch):
    """The funnel's precondition seam (promote.sh delegates here): all guards through one judge."""
    monkeypatch.setattr(sources, "issue_board_position",
                        lambda r, i: (True, {"status": "Backlog", "reason": "", "itype": "Feature"}))
    _stub_trail(monkeypatch, [_approval_text(reg)])
    _stub_evaluator(monkeypatch, returncode=0)
    rc, failures = process.transition_check(model, "task.backlog->ready.epic-flip",
                                            {"repo": "r/r", "issue": "9"})
    assert rc == 0 and not failures
    _stub_evaluator(monkeypatch, returncode=1, first_line="design_not_active")
    rc2, failures2 = process.transition_check(model, "task.backlog->ready.epic-flip",
                                              {"repo": "r/r", "issue": "9"})
    assert rc2 == 1 and any("design_not_active" in f for f in failures2)


def test_transition_check_refuses_the_wrong_from_state(model, reg, monkeypatch):
    """The review's medium 1: the funnel's preconditions include WHERE THE MACHINE IS — a Feature
    sitting In Progress must never be rewound to Ready with a legitimizing record."""
    monkeypatch.setattr(sources, "issue_board_position",
                        lambda r, i: (True, {"status": "In Progress", "reason": "",
                                             "itype": "Feature"}))
    _stub_trail(monkeypatch, [_approval_text(reg)])
    _stub_evaluator(monkeypatch, returncode=0)
    rc, failures = process.transition_check(model, "task.backlog->ready.epic-flip",
                                            {"repo": "r/r", "issue": "9"})
    assert rc == 1
    assert any("backlog" in f and "in-progress" in f for f in failures)


def test_transition_check_unreadable_from_state_is_unknown_never_ok(model, reg, monkeypatch):
    monkeypatch.setattr(sources, "issue_board_position",
                        lambda r, i: (False, "board unreachable"))
    _stub_trail(monkeypatch, [_approval_text(reg)])
    _stub_evaluator(monkeypatch, returncode=0)
    rc, failures = process.transition_check(model, "task.backlog->ready.epic-flip",
                                            {"repo": "r/r", "issue": "9"})
    assert rc == 1
    assert any("UNKNOWN" in f for f in failures)


def test_resolver_refuses_targets_outside_the_vault(tmp_path, monkeypatch):
    """The review's medium 2: the guarded surface must not steer the guard — a traversal or
    absolute wikilink target refuses instead of reading outside YR_VAULT_ROOT."""
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    outside = tmp_path.parent / "outside.md"
    outside.write_text("---\nstatus: active\n---\n", encoding="utf-8")
    import design_resolver
    rc, token = design_resolver.check_body("**Source:** spec [[../outside]] (x)")
    assert rc == 1 and token == "design_outside_vault"
    rc2, token2 = design_resolver.check_body(f"**Source:** spec [[{outside}]] (x)")
    assert rc2 == 1 and token2 == "design_outside_vault"


def test_resolver_reads_status_from_frontmatter_only(tmp_path, monkeypatch):
    """A column-0 `status: active` in the BODY never satisfies the guard — the parse is bounded
    to the leading frontmatter block."""
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("no frontmatter here\nstatus: active\n", encoding="utf-8")
    import design_resolver
    rc, token = design_resolver.check_body("**Source:** spec [[04 projects/x]] (x)")
    assert rc == 1 and token == "design_status_unreadable"


def test_intra_row_contradictory_discriminators_refuse_at_load(model, reg):
    """The review's finding 4: a row carrying facet_is guards to two different states on ONE
    facet is runtime-unsatisfiable dead weight — the loader refuses it outright."""
    import copy
    import tomllib
    m = copy.deepcopy(tomllib.loads((REPO / "process.toml").read_text(encoding="utf-8")))
    t = next(t for t in m["transition"] if t["id"] == "task.backlog->ready.standalone")
    t["guard"].append({"predicate": "facet_is", "args": {"facet": "type", "state": "feature"},
                       "why": "contradiction"})
    import pytest as _pytest
    with _pytest.raises(process.ModelError, match="contradict"):
        process._validate(m, reg, "inline")


def test_model_loads_and_determinism_holds(model):
    """The two backlog->ready attended rows coexist because their type discriminators are
    provably disjoint — the loader accepts the pair and still rejects true overlaps."""
    tids = {t["id"] for t in model["transition"]}
    assert "task.backlog->ready.epic-flip" in tids and "task.backlog->ready.standalone" in tids
