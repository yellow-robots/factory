"""The process model (process.toml + tools/process.py, it-30): the loader's rules, the derivations,
the compiled lanes, and the conformance vectors.

THE GATING TIER LIVES HERE (ruling 1, split tier): `test_the_shipped_model_loads` failing means the
walls are structurally off — and because this file runs inside `check_cmd` and CI, a diff that breaks
the model cannot merge. The drift check stays ADVISORY by the same ruling and is deliberately NOT
asserted here.
"""

import copy
import json
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import predicates  # noqa: E402
import process  # noqa: E402
import records  # noqa: E402
import sources  # noqa: E402

ATTENDED = {"YR_CALLER": "attended-agent"}


@pytest.fixture(scope="module")
def model():
    return process.load()


@pytest.fixture(scope="module")
def reg():
    return records.load()


def _raw():
    return tomllib.loads((REPO / "process.toml").read_text(encoding="utf-8"))


def _expect_error(mutated, reg, match):
    with pytest.raises(process.ModelError, match=match):
        process._validate(mutated, reg, "mutated")


# ── the gating tier: a model that does not load means the walls are OFF ──────────────────────────

def test_the_shipped_model_loads(model):
    assert model["model"]["contract"] == "yr-process/1"
    assert model.get("transition") and model.get("store") and model["port"]["binding"]


def test_compiled_lanes_reproduce_the_design_trace(model):
    mandate, forbid = process.lanes(model)
    assert mandate == {
        "standalone": ["YR-PROMOTED", "YR-TASK-GATES"],
        "epic": ["YR-AUTO-PROMOTED", "YR-EPIC-APPROVAL", "YR-EPIC-READY"],
        "design": ["YR-ACCEPT", "YR-DESIGN-FIT", "YR-DESIGN-REVIEW"],
        "close": ["YR-ROUND-RECORD", "YR-SHIP-WALK"],
        "merge": ["YR-MERGE"],
    }
    assert forbid == {"epic": ["YR-OPEN-QUESTION"], "design": ["YR-OPEN-QUESTION"]}


def test_records_lanes_delegates_to_the_model(reg):
    assert records.lanes(reg)["standalone"] == ["YR-PROMOTED", "YR-TASK-GATES"]
    assert records.lane_forbids(reg)["epic"] == ["YR-OPEN-QUESTION"]


# ── loader rules, each shown to bite on the real file ────────────────────────────────────────────

def test_rule_unknown_key_a_stance_field_is_unspellable(reg):
    m = _raw()
    m["transition"][0]["stance"] = "observe"       # the flagship kill: stance cannot be authored
    _expect_error(m, reg, "unknown key")


def test_rule_p_state_values_must_permute_store_values(reg):
    m = _raw()
    dead = [st for st in m["state"] if not (st["machine"] == "task" and st["id"] == "done")]
    m["state"] = dead
    _expect_error(m, reg, "rule P|permutation|has no states")


def test_rule_f1_guarding_reason_requires_disposing_it(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.blocked->ready.unblock")
    t["post"] = [p for p in t["post"] if p["args"].get("facet") != "reason"]
    _expect_error(m, reg, "rule F1")


def test_rule_f2_undeclared_reason_write_is_refused(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.backlog->ready.standalone")
    t["post"].append({"predicate": "facet_is", "args": {"facet": "reason", "state": "none"}})
    _expect_error(m, reg, "rule F2")


def test_rule_d_one_way_door_forbids_execute(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.backlog->ready.standalone")
    t["agent_may"] = "execute"
    _expect_error(m, reg, "rule D")


def test_rule_a_agent_may_needs_the_attended_class(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.ready->in-progress.claim")
    t["agent_may"] = "propose"
    _expect_error(m, reg, "rule A")


def test_rule_c_uncovered_observable_path_fails_the_load(reg):
    m = _raw()
    store = next(s for s in m["store"] if s["id"] == "board.status")
    store["write_path"].append({"id": "rest", "how": "the REST field-update endpoint",
                                "observable": True})
    _expect_error(m, reg, "rule C")


def test_rule_c2_unobservable_path_needs_detected_by(reg):
    m = _raw()
    store = next(s for s in m["store"] if s["id"] == "board.status")
    wp = next(w for w in store["write_path"] if w["id"] == "web-ui")
    del wp["detected_by"]
    _expect_error(m, reg, "detected_by|undetectable")


def test_rule_r_an_unregistered_record_is_a_load_error(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.backlog->ready.standalone")
    g = next(g for g in t["guard"] if g["predicate"] == "record_present")
    g["args"]["record"] = "YR-NEVER-MINTED"
    _expect_error(m, reg, "unregistered record")


def test_rule_s_a_self_licensing_guard_is_dead_at_load(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.backlog->ready.standalone")
    t["guard"].append({"predicate": "record_present", "args": {"record": "YR-PROMOTED"},
                       "why": "the half-write shape"})
    _expect_error(m, reg, "rule S|self-licensing")


def test_rule_v_prose_conditions_are_unwritable(reg):
    m = _raw()
    t = next(t for t in m["transition"] if t["id"] == "task.backlog->ready.standalone")
    t["guard"][0]["predicate"] = "looks_reasonable"
    _expect_error(m, reg, "rule V|not in")


def test_rule_determinism_two_rules_for_one_cell_refuse_to_load(reg):
    m = _raw()
    t = copy.deepcopy(next(t for t in m["transition"]
                           if t["id"] == "task.backlog->ready.standalone"))
    t["id"] = "task.backlog->ready.twin"
    m["transition"].append(t)
    _expect_error(m, reg, "determinism")


def test_rule_seam_a_neutral_row_may_not_cite_port(reg):
    m = _raw()
    m["transition"][0]["because"] = "port.transport.anthropic-claude-code carries this"
    _expect_error(m, reg, "seam|port")


def test_observability_constants_cannot_flip(reg):
    m = _raw()
    m["observability"]["may_influence_decisions"] = True
    _expect_error(m, reg, "constant")


def test_invariant_with_state_predicate_is_refused(reg):
    m = _raw()
    m["invariant"][0]["guard"].append({"predicate": "facet_is",
                                       "args": {"facet": "status", "state": "ready"},
                                       "why": "state smuggled into the conduct tier"})
    _expect_error(m, reg, "state predicate|transition guard")


def test_binding_does_not_cover_is_required_nonempty(reg):
    m = _raw()
    m["port"]["binding"][0]["does_not_cover"] = []
    _expect_error(m, reg, "does_not_cover")


# ── derivations: code, never authored ────────────────────────────────────────────────────────────

def test_stance_derivation_table(model):
    t = next(t for t in model["transition"] if t["id"] == "task.backlog->ready.standalone")
    assert process.stance("machinery", t, True, None) == "refuse"       # not in actor: categorical
    assert process.stance("attended-agent", t, False, None) == "refuse"  # guards FALSE
    assert process.stance("attended-agent", t, True, None) == "escalate"  # propose at the gate
    assert process.stance("human", t, True, None) == "observe"
    over = {"precision": "over-matching"}
    assert process.stance("attended-agent", t, False, over) == "advise"  # may never refuse


def test_enforcement_is_partial_wherever_an_unobservable_door_exists(model):
    t = next(t for t in model["transition"] if t["id"] == "pr.approved->merged.evaluator")
    enf, open_paths = process.enforcement(t, model)
    assert enf == "partial"
    assert any("web-ui" in p for p in open_paths)     # the open door is printed, never elided


def test_predicate_results_have_no_truthiness():
    with pytest.raises(TypeError):
        bool(predicates.TRUE)


def test_record_absent_unknown_stays_unknown(reg):
    res = predicates.record_absent("YR-OPEN-QUESTION", registry=reg, texts=None)
    assert res.state == "UNKNOWN"                      # `not UNKNOWN` is the fail-open trapdoor


# ── the compiled surfaces ────────────────────────────────────────────────────────────────────────

def test_compiled_surfaces_carry_the_generated_header(model):
    for rel in ("build/lanes.toml", "build/walled-acts.md", "build/slice-static.md"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "GENERATED from process.toml" in text.splitlines()[0]


def test_slice_respects_its_byte_bound_and_fails_loud_past_it(model):
    out = process.compile_slice(model)
    assert len(out.encode()) <= model["model"]["slice_max_bytes"]
    assert "caller_trust = `declared`" in out
    shrunk = dict(model)
    shrunk["model"] = dict(model["model"], slice_max_bytes=100)
    with pytest.raises(process.ModelError, match="fail loud"):
        process.compile_slice(shrunk)


def test_lanes_toml_carries_the_version_table_row(model):
    lanes = tomllib.loads((REPO / "build" / "lanes.toml").read_text(encoding="utf-8"))
    assert lanes["meta"]["model_version"] == model["model"]["version"]
    assert lanes["meta"]["effective"]                  # ruling 3: judged by schema version


# ── conformance: the schema's promises reach the code ────────────────────────────────────────────

@pytest.fixture(scope="module")
def vectors():
    return json.loads((REPO / "build" / "conformance.json").read_text(encoding="utf-8"))["vectors"]


def _fail_all_sources(monkeypatch):
    for name in ("issue_trail", "pr_trail", "board_item", "issue_board_position", "pr_state"):
        monkeypatch.setattr(sources, name, lambda *a, **k: (False, "stubbed down"))
    monkeypatch.setattr(sources, "vault_doc", lambda p: (False, "stubbed down"))


def _fail_more_sources(monkeypatch):
    _fail_all_sources(monkeypatch)
    monkeypatch.setattr(sources, "issue_trail_timed", lambda *a, **k: (False, "stubbed down"))
    monkeypatch.setattr(sources, "manifest_at_base_tip", lambda *a, **k: (False, "stubbed down"))
    monkeypatch.setattr(sources, "host_file", lambda *a, **k: (False, "stubbed down"))


def test_journal_independence_decisions_identical_with_journal_unwritable(model, vectors,
                                                                          monkeypatch, tmp_path):
    _fail_more_sources(monkeypatch)
    outputs = []
    for v in [v for v in vectors if v["kind"] == "journal-independence"]:
        hook = {**v["act"], "session_id": "conf"}
        monkeypatch.setenv("YR_WALL_STATE", str(tmp_path / "writable"))
        a, rows_a = process.decide(model, hook, env=ATTENDED)
        monkeypatch.setenv("YR_WALL_STATE", "/proc/definitely-unwritable/x")
        b, rows_b = process.decide(model, hook, env=ATTENDED)
        process.journal_append(model, rows_b, "conf")   # must swallow the unwritable path silently
        assert a == b, f"decision differed under an unwritable journal: {v['binding']}"
        outputs.append(a)
    # non-vacuity: an all-None regression (walls silently off) must fail this test
    assert any(o is not None for o in outputs), "every vector decided silence — the walls are off"


# exact bindings on guarded stores: with every source down, the attended class must be DENIED —
# UNKNOWN is never a pass (the disposition table's left column, consumed per generated vector)
_EXACT_DENY = {"board.write.gh-cli", "board.write.funnel", "board.write.graphql",
               "merge.gh-cli", "merge.graphql", "arming.fs", "push.main", "push.shared",
               "design.stamp.obsidian-mcp"}


def test_unknown_always_disposes_closed_never_open(model, vectors, monkeypatch):
    """Every source down: each exact-binding vector DENIES for the attended class; each
    over-matching vector advises without ever denying. A fail-open regression flips these."""
    _fail_more_sources(monkeypatch)
    for v in [v for v in vectors if v["kind"] == "journal-independence"]:
        out, _ = process.decide(model, {**v["act"], "session_id": "conf"}, env=ATTENDED)
        if v["binding"] in _EXACT_DENY:
            assert out is not None, f"{v['binding']}: silence under UNKNOWN is fail-open"
            assert out["hookSpecificOutput"].get("permissionDecision") == "deny", v["binding"]
        elif out is not None:
            hso = out["hookSpecificOutput"]
            assert hso.get("permissionDecision") in (None, "ask"), (
                f"{v['binding']}: an over-matching binding may never refuse")


def test_every_unknown_refuses_vector_evaluates_non_true_under_failed_sources(model, vectors,
                                                                              monkeypatch):
    """The per-guard conformance vectors, actually consumed: with every source down, no guard in
    the model can evaluate TRUE — an unreadable world licenses nothing."""
    _fail_more_sources(monkeypatch)
    tids = {t["id"]: t for t in model["transition"]}
    checked = 0
    for v in [v for v in vectors if v["kind"] == "unknown-refuses"]:
        t = tids[v["transition"]]
        g = (t.get("guard") or [])[v["guard"]]
        ctx = process._Ctx(model)
        res = process._eval_guard(ctx, t, g, act={"fields": {}})
        assert res.state != "TRUE", f"{v['transition']} guard {v['guard']} passed with no source"
        checked += 1
    assert checked >= 10, "the unknown-refuses vector set shrank unexpectedly"


def test_predicates_module_is_pure_no_io_imports():
    """The design's import-level purity guard, real: the predicate module may not fetch."""
    src = (REPO / "tools" / "predicates.py").read_text(encoding="utf-8")
    for forbidden in ("import subprocess", "import socket", "import urllib", "import requests",
                      "read_text(", "urlopen", "Popen"):
        assert forbidden not in src, f"predicates.py grew I/O: {forbidden}"


def test_funnel_and_raw_spellings_reach_the_same_transition(model, vectors, monkeypatch):
    _fail_all_sources(monkeypatch)
    monkeypatch.setattr(sources, "board_item", lambda item_id: (True, {
        "status": "Backlog", "reason": "", "itype": "Task", "updatedAt": "",
        "repo": "r/r", "issue": "1"}))
    monkeypatch.setattr(sources, "issue_trail", lambda repo, issue: (True, ["chatter"]))
    v = next(v for v in vectors if v["kind"] == "same-transition")
    reasons = []
    for act in v["acts"]:
        out, _ = process.decide(model, {**act, "session_id": "conf"}, env=ATTENDED)
        reasons.append(out["hookSpecificOutput"]["permissionDecisionReason"])
    assert all("task.backlog->ready.standalone" in r for r in reasons)


# ── transition-check: the sharper unit ───────────────────────────────────────────────────────────

def test_transition_check_unknown_transition_is_rc2(model):
    rc, msgs = process.transition_check(model, "task.nonesuch", {})
    assert rc == 2 and "unknown transition" in msgs[0]
