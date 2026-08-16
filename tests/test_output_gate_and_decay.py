"""it-31 slice 6 (#438): the output gate's switches leave a trail, and drift degrades coverage.

Un-arming and the sentinel's throw/clear become modeled transitions whose record —
YR-OUTPUT-SWITCH, minted here — is the trail both directions of the master switches now owe:
detection where prevention cannot reach (a human's ssh act on the host is flagged by its missing
record, never prevented; an agent's edit stays categorically refused at the permission tier).
Probe drift persists as a stored downgrade consumed by the liveness derivation, and the delivered
slice names the degradation at delivery time; the compiled surfaces stay deterministic (compile
consumes no session state). Fixtures only.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import process  # noqa: E402
import records  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}
MACHINERY = {"YR_CALLER": "machinery"}


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture()
def reg(model):
    return model["_registry"]


def test_switch_transitions_exist_with_the_record_post(model):
    tids = {t["id"]: t for t in model["transition"]}
    for tid in ("arming.armed->disarmed.unarm", "arming.disarmed->armed.arm",
                "sentinel.clear->thrown.throw", "sentinel.thrown->clear.clear"):
        assert tid in tids, tid
        t = tids[tid]
        assert t["actor"] == ["human"], tid
        assert any(po["predicate"] == "record_present"
                   and po["args"]["record"] == "YR-OUTPUT-SWITCH"
                   for po in t.get("post") or []), tid


def test_sentinel_store_is_guarded_detection_tier(model):
    store = model["_stores"]["host.merge_sentinel"]
    assert store["guarded"] is True
    paths = store.get("write_path") or []
    assert paths and all(not wp.get("observable") for wp in paths)
    assert all(wp.get("detected_by") == "YR-OUTPUT-SWITCH" for wp in paths)


def test_registry_row_exists(reg):
    row = records.get(reg, "YR-OUTPUT-SWITCH")
    assert row["fields"] == ["switch", "to", "who"]
    assert "issue-trail" in row["surfaces"] or "pr-trail" in row["surfaces"]


def test_agent_unarm_edit_still_refused_both_directions(model, tmp_path):
    """The categorical wall is untouched: no record licenses an agent's arming OR un-arming
    edit — the transitions document the human's own acts, they never open an agent path."""
    for old, new in (("auto_merge = false", "auto_merge = true"),
                     ("auto_merge = true", "auto_merge = false")):
        hook = {"tool_name": "Edit", "session_id": "s6",
                "tool_input": {"file_path": str(tmp_path / "r" / ".yr" / "factory.toml"),
                               "old_string": old, "new_string": new}}
        for env in (ATTENDED, MACHINERY):
            out, _ = process.decide(model, hook, env=env)
            assert out["hookSpecificOutput"]["permissionDecision"] == "deny", (old, env)


def test_decay_writes_and_heals_the_downgrade_store(model, tmp_path, monkeypatch):
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))

    class _Out:
        def __init__(self, stdout=b"drifted-surface"):
            self.stdout = stdout

    monkeypatch.setattr(process.subprocess, "run", lambda *a, **k: _Out())
    notes = process.run_decay(model)
    assert any("DRIFTED" in n for n in notes)
    store = process.stored_downgrades(model)
    assert store, "drifted probes must persist"
    # self-heal: fingerprints matching again clears the entries
    import hashlib
    real = {pr["id"]: pr["fingerprint"] for pr in model["port"]["probe"]}
    try:
        for pr in model["port"]["probe"]:
            pr["fingerprint"] = "sha256:" + hashlib.sha256(b"drifted-surface").hexdigest()
        notes2 = process.run_decay(model)
        assert not any("DRIFTED" in n for n in notes2)
        assert not process.stored_downgrades(model), "healed probes must clear"
    finally:
        for pr in model["port"]["probe"]:
            pr["fingerprint"] = real[pr["id"]]


def test_enforcement_consumes_stored_downgrades(model):
    """A drifted probe degrades every binding standing on it: the merge transition's enforcement
    weakens when gh.pr.surface is downgraded — and compile-time output (empty downgrades) is
    unchanged, so committed surfaces stay deterministic."""
    t = next(t for t in model["transition"] if t["id"] == "pr.approved->merged.evaluator")
    base_val, _ = process.enforcement(t, model)
    down_val, open_paths = process.enforcement(
        t, model, downgrades={"gh.pr.surface": {"drifted_on": "2026-08-16"}})
    assert base_val != down_val or open_paths, \
        "a downgraded probe must weaken enforcement or open paths"


def test_stored_note_prints_only_when_degraded(model, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    rc = process.main(["decay", "--stored-note"])
    out = capsys.readouterr().out
    assert rc == 0 and out.strip() == ""
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "downgrades.json").write_text(
        json.dumps({"gh.pr.surface": {"drifted_on": "2026-08-16"}}), encoding="utf-8")
    rc2 = process.main(["decay", "--stored-note"])
    out2 = capsys.readouterr().out
    assert rc2 == 0 and "COVERAGE DEGRADED" in out2 and "gh.pr.surface" in out2


def test_compiled_acts_ignore_session_state(model, tmp_path, monkeypatch):
    baseline = process.compile_acts(model)
    monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "state"))
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "downgrades.json").write_text(
        json.dumps({"gh.pr.surface": {"drifted_on": "2026-08-16"}}), encoding="utf-8")
    assert process.compile_acts(model) == baseline
