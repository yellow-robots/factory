"""it-31 slice 2 (#434): propose has no one to propose to — the headless stance.

The verified harness contract (§3b, probed): `permissionDecision: ask` fails OPEN under
`bypassPermissions` with no human present — the tool runs silently. So on the two propose-gated
one-way doors (standalone promote, design-active) the escalation can never be the last wall: where
the transport's declared headless signal is present, the derived stance is a plain deny — the
session continues, nothing hangs. Field absent = interactive, preserving today's behavior (the
contract leaves non-bypass headless unclaimed, and the surfaces print that residual).
Fixtures only — sources stubbed at the `tools/sources.py` seam, like test_wall.py.
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

ATTENDED = {"YR_CALLER": "attended-agent"}


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture()
def reg(model):
    return model["_registry"]


def _bash(cmd, session="sH", permission_mode=None):
    hook = {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": session}
    if permission_mode is not None:
        hook["permission_mode"] = permission_mode
    return hook


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


def _board_cmd(opt_name="Ready"):
    fid = board_plumbing.status_field_id()
    opt = board_plumbing.status_opt()[opt_name]
    return (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
            f"--field-id {fid} --single-select-option-id {opt}")


def _vault_doc(tmp_path, monkeypatch, text):
    monkeypatch.setenv("YR_VAULT_ROOT", str(tmp_path))
    doc = tmp_path / "04 projects" / "x.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")
    return doc


def test_headless_promote_refuses_instead_of_asking(model, reg, monkeypatch):
    """Guards HOLD, caller lawful, agent_may=propose, headless signal present: the derived stance
    is a plain deny — never an ask that would fall through with nobody watching."""
    _stub_board(monkeypatch, "Backlog")
    _stub_trail(monkeypatch, [_gates_text(reg)])
    out, rows = process.decide(model, _bash(_board_cmd("Ready"),
                                            permission_mode="bypassPermissions"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "cannot reach a human" in reason
    assert rows and rows[0]["stance"] == "refuse"


def test_interactive_promote_still_asks(model, reg, monkeypatch):
    """Field absent = interactive: the ask flow is byte-identical to today."""
    _stub_board(monkeypatch, "Backlog")
    _stub_trail(monkeypatch, [_gates_text(reg)])
    out, _ = process.decide(model, _bash(_board_cmd("Ready")), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
    interactive, _ = process.decide(model, _bash(_board_cmd("Ready"), permission_mode="default"),
                                    env=ATTENDED)
    assert interactive["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_headless_design_activation_refuses(model, reg, tmp_path, monkeypatch):
    """The input gate itself: guards hold (review + fit records in the doc) and the headless
    signal is present — deny, never a fall-through activation."""
    rows_txt = "".join(records.get(reg, n)["marker"] + " done\nwho: r\nverdict: pass\n"
                       for n in ("YR-DESIGN-REVIEW", "YR-DESIGN-FIT"))
    doc = _vault_doc(tmp_path, monkeypatch, f"---\nstatus: draft\n---\n{rows_txt}")
    hook = {"tool_name": "mcp__obsidian__vault_patch", "session_id": "sH",
            "permission_mode": "bypassPermissions",
            "tool_input": {"path": str(doc), "targetType": "frontmatter", "target": "status",
                           "operation": "replace", "content": "active"}}
    out, _ = process.decide(model, hook, env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    interactive = dict(hook)
    del interactive["permission_mode"]
    out2, _ = process.decide(model, interactive, env=ATTENDED)
    assert out2["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_headless_execute_transitions_unchanged(model, reg, monkeypatch):
    """The narrowing is propose-only: an agent_may=execute transition (the unblock) flows
    headless exactly as interactive — the human's standing rule already licenses it."""
    _stub_board(monkeypatch, "In Progress", reason="Blocked")
    _stub_trail(monkeypatch, [_flip_text(reg)])
    cmd = (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
           f"--field-id {board_plumbing.status_field_id()} "
           f"--single-select-option-id {board_plumbing.status_opt()['Ready']}")
    out, rows = process.decide(model, _bash(cmd, permission_mode="bypassPermissions"),
                               env=ATTENDED)
    assert out is None
    assert rows and rows[0]["stance"] == "observe"


def test_headless_guard_failure_still_teaches_the_guard(model, reg, monkeypatch):
    """A failed guard refuses with ITS OWN teaching, headless or not — the headless refuse only
    replaces the ask that would have followed a HOLD."""
    _stub_board(monkeypatch, "Backlog")
    _stub_trail(monkeypatch, ["no gates record"])
    out, _ = process.decide(model, _bash(_board_cmd("Ready"),
                                         permission_mode="bypassPermissions"), env=ATTENDED)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "YR-TASK-GATES" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_compiled_surfaces_print_the_headless_rule(model):
    """The map never overclaims: the compiled act map and the delivered slice state the headless
    behavior and the blind-write residual (over-matching advises, detection-tier)."""
    acts_out = process.compile_acts(model)
    slice_out = process.compile_slice(model)
    for text in (acts_out, slice_out):
        assert "headless" in text.lower()
        assert "over-matching" in text.lower() or "blind-write" in text.lower()


def test_overmatching_binding_still_advises_headless(model, tmp_path, monkeypatch):
    """The blind-write residual at the derivation level (the review's pin): headless never
    promotes an over-matching binding to a denier — the clamp runs after the narrowing."""
    doc = _vault_doc(tmp_path, monkeypatch, "---\nstatus: draft\n---\n")
    hook = {"tool_name": "Write", "session_id": "sHB", "permission_mode": "bypassPermissions",
            "tool_input": {"file_path": str(doc), "content": "---\nstatus: active\n---\n"}}
    out, _ = process.decide(model, hook, env=ATTENDED)
    assert "additionalContext" in out["hookSpecificOutput"]
    assert "permissionDecision" not in out["hookSpecificOutput"]


def test_machinery_caller_headless_unchanged(model, monkeypatch):
    """The pipeline is unaffected: machinery's lawful claim flows identically under the headless
    signal — the narrowing lives in the propose branch machinery never enters."""
    _stub_board(monkeypatch, "Ready")
    _stub_trail(monkeypatch, ["chatter"])
    cmd = (f"gh project item-edit --id ITEM --project-id {board_plumbing.project_id()} "
           f"--field-id {board_plumbing.status_field_id()} "
           f"--single-select-option-id {board_plumbing.status_opt()['In Progress']}")
    out, rows = process.decide(model, _bash(cmd, permission_mode="bypassPermissions"),
                               env={"YR_CALLER": "machinery"})
    assert out is None
    assert rows and rows[0]["stance"] == "observe"


def test_malformed_headless_declaration_refuses_to_load(tmp_path):
    """Rule H (the review's fold): a malformed declaration must fail the load, never degrade
    silently to interactive — that direction re-opens the fail-open ask."""
    text = (REPO / "process.toml").read_text(encoding="utf-8")
    good = 'headless = { field = "permission_mode", values = ["bypassPermissions"] }'
    assert good in text, "fixture anchor drifted — realign with process.toml"
    bad = tmp_path / "process.toml"
    bad.write_text(text.replace(good, 'headless = { field = "", values = [] }', 1),
                   encoding="utf-8")
    with pytest.raises(process.ModelError):
        process.load(bad)


def test_transport_declares_the_headless_signal(model):
    """The signal lives in the vendor-coupled port block, never inferred inside the engine."""
    tr = model["port"]["transport"]["anthropic-claude-code"]
    h = tr.get("headless")
    assert h and h.get("field") == "permission_mode"
    assert "bypassPermissions" in (h.get("values") or [])
