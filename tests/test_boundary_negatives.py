"""Per-surface boundary negatives (it-31 slice 8, #440): outside the factory's declared world,
every lane hook stays silent — walls and delivery alike.

Three surfaces, three negatives (the PreToolUse one restates tests/test_wall.py's shipped shape so
the trio lives together; delivery's subprocess-level negative is test_compile_slice.py's):
PreToolUse observes silence, Stop observes silence, delivery emits zero bytes.
"""

import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import process  # noqa: E402
import wall  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}


@pytest.fixture(scope="module")
def model():
    return process.load()


def test_pretooluse_outside_the_boundary_is_silent(model, outside_cwd):
    hook = {"tool_name": "Bash", "session_id": "sB",
            "tool_input": {"command": "gh pr merge 1 --repo o/r --squash"},
            "cwd": str(outside_cwd)}
    out, rows = process.decide(model, hook, env=ATTENDED)
    assert out is None and rows == []


def test_stop_outside_the_boundary_is_silent_for_an_actless_session(model, tmp_path, outside_cwd,
                                                                   monkeypatch):
    """The Stop negative (new surface): a session with NO journaled acts hears nothing when the
    close fires outside the factory's world — the foreign-repo noise case."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    process.journal_append(model, [{"ts": int(time.time()),
                                    "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sOTHER")
    outside = wall.close({"session_id": "sEMPTY", "cwd": str(outside_cwd)},
                         no_journal=True)
    assert outside is None


def test_stop_never_eats_a_session_with_journaled_acts(model, tmp_path, outside_cwd, monkeypatch):
    """decide()'s own lesson, applied to Stop (the slice-8 review's major 2): journal rows exist
    only because decide() judged the underlying acts in-scope — an out-of-scope cwd at close time
    must NOT silence the unresolved traces the quiesce discipline exists to surface."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    process.journal_append(model, [{"ts": int(time.time()),
                                    "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sBND")
    outside = wall.close({"session_id": "sBND", "cwd": str(outside_cwd)},
                         no_journal=True)
    assert outside is not None, "an out-of-scope cwd silenced a session with real traces"
    inside = wall.close({"session_id": "sBND", "cwd": str(REPO)}, no_journal=True)
    assert inside is not None, "the same journal inside the boundary still reports"


def test_stop_with_no_cwd_stays_inside_default(model, tmp_path, monkeypatch):
    """A Stop payload without cwd falls back to the process cwd (the suite runs inside the repo):
    absence of the field must not silence a factory session's close."""
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    process.journal_append(model, [{"ts": int(time.time()),
                                    "transition_id": "pr.approved->merged.evaluator",
                                    "binding_id": "merge.gh-cli", "scope": {}, "stance": "refuse",
                                    "caller": "attended-agent"}], "sBND2")
    assert wall.close({"session_id": "sBND2"}, no_journal=True) is not None
