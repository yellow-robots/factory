"""Characterization pins for issue #387 — the board read/write contract every one of the current
board-plumbing sites implements today (which project item is selected, what a field write looks like,
record-before-flip order, environment overridability, the spawn-env allowlist, and the two genuinely
distinct board reads) — pinned so the next slice (collapsing the identifiers and the two hand-rolled
operations to one home) is provably behavior-identical.

Derived from the issue's acceptance criteria (the spec), not from the implementations' internals — though
the exact fixtures below necessarily mirror each script's real GraphQL/CLI shapes, since a characterization
pin only has teeth if it feeds the real shape the real code branches on.

This file is PURELY ACCRETIVE — it adds pins only, never modifies or duplicates one. Existing coverage,
read first per the issue's instruction:
  - test_epic_gate.py already pins epic_gate.py's write-call shape (`test_writes_use_runner_gh_mechanisms`)
    and its defaults + a PARTIAL (2 of 11) env-override set (`test_defaults_reuse_runner_ids`,
    `test_field_ids_env_overridable`) — this file completes the override side to all 11 identifiers and
    adds the one default this suite doesn't check (`PROJECT_NUMBER`).
  - test_promote.py already pins record-before-flip order and every refusal-writes-nothing path — not
    duplicated here.
  - test_promote.py / test_watch_build.py / test_board.py never build a MULTI-project-item response, so
    none of them pins the selection rule ("the node whose project number matches") against more than one
    candidate, nor an item present-but-none-matching case — this file adds both, per reader.
  - No existing suite exercises `tools/dev-runner.sh`'s field-write failure path (item-edit itself
    failing) or its `clear_reason` (`--clear`) write at all — both are new pins here.
  - No existing suite proves `tools/dev-runner.sh`'s per-issue-identifier defaults with every env override
    absent (every existing dev-runner suite always overrides them for legible assertions) — new here.
  - No existing suite proves the runner's board-wide `gh project item-list` read is mechanically distinct
    from the per-issue `gh api graphql` read the operator scripts and the sweep use — new here.
  - test_dispatch.py's spawn-allowlist coverage only probes `BUILD_MODEL`; this file extends the same
    real-spawn-and-dump technique to every board identifier name.

Deliberately NOT pinned: no assertion here checks that any identifier literal appears in a particular
file's own source text — where each identifier lives is exactly what the next slice moves.

Runs under `.venv/bin/python -m pytest tests/ -q` (attended); `pytest tests/ -q` in a cut build worktree.
"""
import json
import importlib
import os
import pathlib
import shlex
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_dev_runner as td      # shared runner harness (gh/claude/check stubs + fixtures)
import test_epic_gate as teg      # epic_gate module + its FakeGh/_sweep harness
import test_promote as tp         # promote.sh harness (GH_STUB_TOOLS)
import test_watch_build as twb    # watch_build.sh harness (GH_STUB_TOOLS)
import test_board as tb           # board.sh harness (GH_STUB_TOOLS)
import test_dispatch as disp      # dispatch module + its real-spawn env-dump harness

sys.path.insert(0, str(ROOT / "tests" / "harness"))
import gh_fake  # noqa: E402


# ============================================================================
# shared helpers
# ============================================================================

def _argv_flags(argv):
    """--flag/value pairs from an already-tokenized argv list (promote.sh / watch_build.sh / board.sh
    calls, which GH_STUB_TOOLS logs as JSON arrays — no shell re-parsing needed)."""
    d, i = {}, 0
    while i < len(argv):
        if argv[i].startswith("--"):
            d[argv[i]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            i += 1
    return d


def _edit_line_flags(edit_line):
    """--flag/value pairs from one of dev-runner.sh's raw `EDIT ...` timeline lines (a single shell-quoted
    string logged by the bash gh fake — tokenize with shlex before extracting flags)."""
    tokens = shlex.split(edit_line[len("EDIT "):])
    return _argv_flags(tokens)


def _run_no_id_override(args, env_extra, cwd=None):
    """Runs tools/dev-runner.sh WITHOUT the READABLE_IDS overlay td._run() always applies — the only way
    to observe the script's real shipped identifier defaults/behavior rather than the harness's
    legibility substitutes."""
    base_env = {k: v for k, v in os.environ.items() if k not in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")}
    env = {**base_env, **env_extra}
    return subprocess.run(["bash", str(td.RUNNER), *args],
                          capture_output=True, text=True, env=env, cwd=str(cwd or td.ROOT))


def _bin_with_gh_call_log(tmp, *, itemedit_fails=False):
    """A `gh` shim wrapping the shared bash GH_STUB: every call's argv is appended (space-joined) to
    $GH_CALL_LOG before delegating to the real stub — GH_STUB itself only ever logs `issue comment` /
    `project item-edit` to STUB_TIMELINE, never `project item-list`, so this is the only way to observe
    the runner's board-wide read's own argv shape. `itemedit_fails=True` additionally makes every
    `project item-edit` call fail (after still delegating, so STUB_TIMELINE bookkeeping is untouched) when
    $STUB_ITEMEDIT_FAIL is set — the only lever available to prove the runner's writes are best-effort,
    since the shared fake never fails an edit on its own."""
    b = tmp / "bin"
    b.mkdir(parents=True, exist_ok=True)
    real = b / "gh_real"
    td._exec(real, td.GH_STUB)
    fail_arm = (
        'if [ "$1" = "project" ] && [ "$2" = "item-edit" ] && [ -n "${STUB_ITEMEDIT_FAIL:-}" ]; then\n'
        f'  "{real}" "$@" >/dev/null 2>&1\n'
        '  exit 7\n'
        'fi\n'
    ) if itemedit_fails else ""
    wrapper = (
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$*" >> "$GH_CALL_LOG"\n'
        f"{fail_arm}"
        f'exec "{real}" "$@"\n'
    )
    td._exec(b / "gh", wrapper)
    td._exec(b / "claude", td.CLAUDE_STUB)
    td._exec(b / "check.sh", td.CHECK_STUB)
    return b


def _promote_multi_response(*, state="OPEN", itype="Task", nodes):
    """The promote.sh issue-side GraphQL shape (same as test_promote.py's `_response`), but taking a
    caller-built `nodes` list directly so more than one projectItems node (at different project numbers)
    can be modeled — `_response` only ever builds zero or one."""
    return json.dumps({"data": {"repository": {"issue": {
        "state": state,
        "issueType": ({"name": itype} if itype else None),
        "projectItems": {"nodes": nodes},
    }}}})


def _promote_env(tmp, binp, resp, issue="7"):
    return {**os.environ, "GH_BIN": str(binp / "gh"), "STUB_ISSUE_RESPONSE": resp,
            "STUB_CALLS_LOG": str(tmp / "calls.log"), "STUB_REPO": "test/repo"}


def _watch_multi_response(*, state="OPEN", nodes):
    """The watch_build.sh issue-side GraphQL shape, taking a caller-built `nodes` list directly (same
    reasoning as `_promote_multi_response` — twb's own STUB_STATES path only ever builds one node)."""
    return json.dumps({"data": {"repository": {"issue": {"state": state, "projectItems": {"nodes": nodes}}}}})


def _watch_env(tmp, binp, resp):
    (tmp / "counter").write_text("0")
    return {**os.environ, "GH_BIN": str(binp / "gh"), "STUB_ISSUE_RESPONSE": resp,
            "STUB_STATES": json.dumps([{"pr_open": False}]),   # fetch_pr still reads STUB_STATES every tick
            "STUB_COUNTER": str(tmp / "counter"), "STUB_CALLS_LOG": str(tmp / "calls.log"),
            "STUB_ISSUE": "7", "STUB_REPO": "test/repo", "STUB_COMMENTS": "[]"}


def _child_multi_pi(number, *, pis, itype="Task", state="OPEN", repo=None, body=""):
    """A sub-issue node, as epic_gate.py's EPIC_QUERY returns it, but taking a caller-built `pis` list of
    projectItems nodes directly — teg._child only ever builds zero or one."""
    return {
        "number": number, "state": state, "issueType": teg._select(itype),
        "repository": {"nameWithOwner": repo or teg.REPO}, "body": body,
        "projectItems": {"nodes": pis},
    }


# ============================================================================
# AC — the selection rule: pinned at each of the three per-issue reads. Each pair proves the SAME rule
# ("the node whose project number equals the configured project number") against a case with more than
# one candidate (the wrong one listed first, to rule out "just takes nodes[0]") and a case with none.
# ============================================================================

# ---- epic_gate.py (the sweep's per-child read) ----

def test_epic_gate_selection_picks_the_node_whose_project_number_matches():
    board = [teg._item(100, item_id="EI-100", itype="Feature", status="Ready")]
    child = _child_multi_pi(101, pis=[
        {"id": "PI-WRONG", "project": {"number": 99}, "status": teg._select("Backlog"), "reason": None},
        {"id": "PI-RIGHT", "project": {"number": 1}, "status": teg._select("Backlog"), "reason": None},
    ])
    epics = {100: teg._epic_detail(comments=[teg.VALID_RECORD], children=[child])}
    fake = teg.FakeGh(board, epics)
    teg._sweep(fake)
    assert fake.edits == [("PI-RIGHT", teg.STATUS_FIELD, "Ready")]


def test_epic_gate_selection_picks_nothing_when_no_project_item_matches():
    board = [teg._item(100, item_id="EI-100", itype="Feature", status="Ready")]
    child = _child_multi_pi(101, pis=[
        {"id": "PI-WRONG", "project": {"number": 99}, "status": teg._select("Backlog"), "reason": None},
    ])
    epics = {100: teg._epic_detail(comments=[teg.VALID_RECORD], children=[child])}
    fake = teg.FakeGh(board, epics)
    teg._sweep(fake)
    assert fake.edits == [] and fake.comments == []   # not on the board yet -> nothing to promote


# ---- promote.sh (the operator promotion's per-issue read) ----

def test_promote_selection_picks_the_node_whose_project_number_matches(tmp_path):
    binp = tp._bin(tmp_path)
    resp = _promote_multi_response(nodes=[
        {"id": "ITEM-WRONG", "project": {"number": 99}},
        {"id": "ITEM-RIGHT", "project": {"number": 1}},
    ])
    r = tp._run(["7", "--repo", "test/repo"], _promote_env(tmp_path, binp, resp))
    assert r.returncode == 0, r.stderr
    edit_call = next(c for c in tp._calls(tmp_path) if c[:2] == ["project", "item-edit"])
    assert "ITEM-RIGHT" in edit_call and "ITEM-WRONG" not in edit_call


def test_promote_selection_refuses_when_no_project_item_matches(tmp_path):
    binp = tp._bin(tmp_path)
    resp = _promote_multi_response(nodes=[{"id": "ITEM-WRONG", "project": {"number": 99}}])
    r = tp._run(["7", "--repo", "test/repo"], _promote_env(tmp_path, binp, resp))
    assert r.returncode != 0
    assert not tp._writes(tp._calls(tmp_path))   # present-but-wrong-project reads the same as absent


# ---- watch_build.sh (the operator watch's per-issue read) ----

def test_watch_build_selection_picks_the_node_whose_project_number_matches(tmp_path):
    binp = twb._bin(tmp_path)
    resp = _watch_multi_response(nodes=[
        {"project": {"number": 99}, "status": {"name": "In Progress"}, "reason": None},
        {"project": {"number": 1}, "status": {"name": "Done"}, "reason": None},
    ])
    r = twb._run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"],
                 _watch_env(tmp_path, binp, resp))
    assert r.returncode == 2   # Done, from the MATCHING node — never the wrong node's non-terminal state


def test_watch_build_selection_picks_nothing_when_no_project_item_matches(tmp_path):
    binp = twb._bin(tmp_path)
    resp = _watch_multi_response(nodes=[{"project": {"number": 99}, "status": {"name": "Done"}, "reason": None}])
    r = twb._run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "0"],
                 _watch_env(tmp_path, binp, resp))
    assert r.returncode == 4                 # not-on-board reads as status="" -> never Done -> times out


# ============================================================================
# AC — the field-write shape: item id, project id, field id, and option id (or --clear instead of an
# option id), pinned at the write sites not already covered by test_epic_gate.py's own
# `test_writes_use_runner_gh_mechanisms`.
# ============================================================================

def test_dev_runner_setter_write_shape_carries_item_project_field_and_option_ids(tmp_path):
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, item_id="ITEM-XYZ",
                                     title="Setter write shape"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    claim_edit = next(e for e in td._edits(td._timeline(tmp_path)) if "InProgress" in e)
    f = _edit_line_flags(claim_edit)
    assert f["--id"] == "ITEM-XYZ"
    assert f["--project-id"] == td.READABLE_IDS["PROJECT_ID"]
    assert f["--field-id"] == td.READABLE_IDS["STATUS_FIELD_ID"]
    assert f["--single-select-option-id"] == "InProgress"
    assert "--clear" not in claim_edit


def test_dev_runner_clear_reason_write_shape_carries_the_clear_flag_not_an_option_id(tmp_path):
    """A stale Blocked/Needs-info Reason at claim time is cleared via `clear_reason` — the ONLY `--clear`
    call site in the codebase, and, per every existing test_dev_runner.py fixture never setting a `reason`
    on the canned item JSON, one no existing suite reaches at all."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    issue_json = td._issue(tmp_path, number=5, title="Clear-reason write shape")
    item_json = tmp_path / "item.json"
    item_json.write_text(json.dumps({"items": [
        {"id": "ITEM-STALE", "status": "Ready", "reason": "Blocked",
         "content": {"number": 5, "repository": "test/repo"}},
    ]}))
    env = td._real(tmp_path, td._base_env(tmp_path, issue_json, item_json, binp), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    clear_edit = next(e for e in td._edits(tl) if "--clear" in e)
    f = _edit_line_flags(clear_edit)
    assert f["--id"] == "ITEM-STALE"
    assert f["--project-id"] == td.READABLE_IDS["PROJECT_ID"]
    assert f["--field-id"] == td.READABLE_IDS["REASON_FIELD_ID"]
    assert "--single-select-option-id" not in f


def test_promote_write_shape_carries_item_project_field_and_option_ids(tmp_path):
    """Doubles as a shipped-defaults pin: unlike test_dev_runner.py's harness, test_promote.py's own
    `_env` never overrides PROJECT_ID/STATUS_FIELD_ID/OPT_READY, so this run resolves promote.sh's real
    production defaults."""
    binp = tp._bin(tmp_path)
    r = tp._run(["7", "--repo", "test/repo"], tp._env(tmp_path, binp, item_id="ITEM-XYZ"))
    assert r.returncode == 0, r.stderr
    edit_call = next(c for c in tp._calls(tmp_path) if c[:2] == ["project", "item-edit"])
    f = _argv_flags(edit_call)
    assert f["--id"] == "ITEM-XYZ"
    assert f["--project-id"] == "PVT_kwDOEEAo0M4Ba6Ls"
    assert f["--field-id"] == "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw"
    assert f["--single-select-option-id"] == "c85eb5c1"


# ============================================================================
# AC — failure semantics, deliberately different between callers, both directions.
# ============================================================================

def test_dev_runner_field_write_failure_is_best_effort_warns_and_does_not_abort(tmp_path):
    work, origin = td._make_repo(tmp_path)
    binp = _bin_with_gh_call_log(tmp_path, itemedit_fails=True)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Field write failure is best-effort"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ITEMEDIT_FAIL"] = "1"
    env["GH_CALL_LOG"] = str(tmp_path / "gh_call_log")
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                       # every item-edit failed; the run still succeeded
    assert "https://stub/pr/1" in r.stdout                   # ...and reached PR-open, not aborted mid-way
    assert "warn: could not set" in r.stderr
    edit_attempts = [l for l in (tmp_path / "gh_call_log").read_text().splitlines()
                     if l.startswith("project item-edit")]
    assert len(edit_attempts) >= 2                            # claim (In Progress) AND terminal (In Review)


def test_promote_refuses_hard_when_the_status_flip_fails_after_the_record_has_landed(tmp_path):
    binp = tp._bin(tmp_path)
    env = tp._env(tmp_path, binp)
    env["STUB_EDIT_FAIL"] = "1"
    r = tp._run(["7", "--repo", "test/repo"], env)
    assert r.returncode != 0
    calls = tp._calls(tmp_path)
    assert len([c for c in calls if c[:2] == ["issue", "comment"]]) == 1     # the record WAS posted
    assert len([c for c in calls if c[:2] == ["project", "item-edit"]]) == 1  # the flip WAS attempted, and failed
    assert "promotion record posted, but the Status=Ready write failed" in r.stderr


# ============================================================================
# AC — environment overridability, for every identifier, together with the shipped defaults.
# ============================================================================

def test_epic_gate_every_board_identifier_is_environment_overridable(monkeypatch):
    """Extends test_epic_gate.py's existing 2-of-11 override coverage (PROJECT_ID, STATUS_FIELD_ID) to
    all 11 — REASON_FIELD_ID, PROJECT_NUMBER, and all seven status/reason option ids were untested."""
    overrides = {
        "PROJECT_NUMBER": "77", "PROJECT_ID": "OVR_PROJECT", "STATUS_FIELD_ID": "OVR_STATUS",
        "REASON_FIELD_ID": "OVR_REASON", "OPT_BACKLOG": "OVR_BACKLOG", "OPT_READY": "OVR_READY",
        "OPT_INPROGRESS": "OVR_INPROGRESS", "OPT_INREVIEW": "OVR_INREVIEW", "OPT_DONE": "OVR_DONE",
        "OPT_NEEDSINFO": "OVR_NEEDSINFO", "OPT_BLOCKED": "OVR_BLOCKED",
    }
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)
    try:
        importlib.reload(teg.epic_gate)
        eg = teg.epic_gate
        assert eg.PROJECT_NUMBER == 77
        assert eg.PROJECT_ID == "OVR_PROJECT"
        assert eg.STATUS_FIELD_ID == "OVR_STATUS"
        assert eg.REASON_FIELD_ID == "OVR_REASON"
        assert eg.STATUS_OPT == {"Backlog": "OVR_BACKLOG", "Ready": "OVR_READY",
                                  "In Progress": "OVR_INPROGRESS", "In Review": "OVR_INREVIEW",
                                  "Done": "OVR_DONE"}
        assert eg.REASON_OPT == {"Needs-info": "OVR_NEEDSINFO", "Blocked": "OVR_BLOCKED"}
    finally:
        monkeypatch.undo()
        importlib.reload(teg.epic_gate)   # restore pristine module for the rest of the suite


def test_epic_gate_project_number_shipped_default_is_one(monkeypatch):
    """The one identifier test_epic_gate.py's own `test_defaults_reuse_runner_ids` doesn't check."""
    monkeypatch.delenv("PROJECT_NUMBER", raising=False)
    try:
        importlib.reload(teg.epic_gate)
        assert teg.epic_gate.PROJECT_NUMBER == 1
    finally:
        importlib.reload(teg.epic_gate)


def test_dev_runner_shipped_defaults_used_when_no_identifier_env_override_is_set(tmp_path):
    """Every existing test_dev_runner.py fixture overrides every identifier via READABLE_IDS for legible
    assertions — none proves the script's real shipped defaults resolve at all. This one bypasses that
    overlay entirely (see `_run_no_id_override`)."""
    work, origin = td._make_repo(tmp_path)
    binp = _bin_with_gh_call_log(tmp_path)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Shipped defaults, no id override"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["GH_CALL_LOG"] = str(tmp_path / "gh_call_log")
    r = _run_no_id_override(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    calls = (tmp_path / "gh_call_log").read_text().splitlines()
    assert any(c.startswith("project item-list 1 ") for c in calls)   # PROJECT_NUMBER default = 1

    claim_edit = next(e for e in td._edits(td._timeline(tmp_path))
                      if "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw" in e and "14e415a3" in e)
    f = _edit_line_flags(claim_edit)
    assert f["--id"] == "ITEM1"                              # td._item()'s own default item id
    assert f["--project-id"] == "PVT_kwDOEEAo0M4Ba6Ls"
    assert f["--field-id"] == "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw"
    assert f["--single-select-option-id"] == "14e415a3"


def test_promote_identifiers_are_environment_overridable(tmp_path):
    binp = tp._bin(tmp_path)
    env = tp._env(tmp_path, binp, item_id="ITEM-OVR")
    env.update({"PROJECT_ID": "OVR_PROJECT", "STATUS_FIELD_ID": "OVR_STATUS", "OPT_READY": "OVR_READY"})
    r = tp._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    f = _argv_flags(next(c for c in tp._calls(tmp_path) if c[:2] == ["project", "item-edit"]))
    assert f["--project-id"] == "OVR_PROJECT"
    assert f["--field-id"] == "OVR_STATUS"
    assert f["--single-select-option-id"] == "OVR_READY"


def test_promote_project_number_is_environment_overridable(tmp_path):
    binp = tp._bin(tmp_path)
    resp = _promote_multi_response(nodes=[{"id": "ITEM-42", "project": {"number": 42}}])
    env = _promote_env(tmp_path, binp, resp)
    env["PROJECT_NUMBER"] = "42"
    r = tp._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    edit_call = next(c for c in tp._calls(tmp_path) if c[:2] == ["project", "item-edit"])
    assert "ITEM-42" in edit_call


def test_watch_build_project_number_shipped_default_and_env_override(tmp_path):
    binp = twb._bin(tmp_path)
    resp = _watch_multi_response(nodes=[{"project": {"number": 42}, "status": {"name": "Done"}, "reason": None}])

    default_env = _watch_env(tmp_path, binp, resp)   # PROJECT_NUMBER unset -> shipped default of 1
    r_default = twb._run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "0"], default_env)
    assert r_default.returncode == 4                 # node is at #42; default #1 never matches -> times out

    override_env = _watch_env(tmp_path, binp, resp)
    override_env["PROJECT_NUMBER"] = "42"
    r_override = twb._run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"], override_env)
    assert r_override.returncode == 2                # now matches -> Done


def test_board_project_number_shipped_default_and_env_override(tmp_path):
    binp = tb._bin(tmp_path)
    nodes = [tb._node(1)]

    calls_log = tmp_path / "calls_default.log"
    default_env = {**os.environ, "GH_BIN": str(binp / "gh"), "STUB_NODES": json.dumps(nodes),
                   "STUB_CALLS_LOG": str(calls_log)}
    r_default = subprocess.run(["bash", str(tb.SCRIPT)], capture_output=True, text=True, env=default_env)
    assert r_default.returncode == 0, r_default.stderr
    default_call = next(json.loads(l) for l in calls_log.read_text().splitlines()
                        if json.loads(l)[:2] == ["api", "graphql"])
    assert "project=1" in default_call

    calls_log2 = tmp_path / "calls_override.log"
    override_env = {**default_env, "PROJECT_NUMBER": "42", "STUB_CALLS_LOG": str(calls_log2)}
    r_override = subprocess.run(["bash", str(tb.SCRIPT)], capture_output=True, text=True, env=override_env)
    assert r_override.returncode == 0, r_override.stderr
    override_call = next(json.loads(l) for l in calls_log2.read_text().splitlines()
                         if json.loads(l)[:2] == ["api", "graphql"])
    assert "project=42" in override_call


# ============================================================================
# AC — the spawn-environment allowlist: every board identifier name passes through to a spawned runner.
# ============================================================================

BOARD_IDENTIFIER_ENV_NAMES = [
    "PROJECT_NUMBER", "PROJECT_ID", "STATUS_FIELD_ID", "REASON_FIELD_ID",
    "OPT_BACKLOG", "OPT_READY", "OPT_INPROGRESS", "OPT_INREVIEW", "OPT_DONE",
    "OPT_NEEDSINFO", "OPT_BLOCKED",
]


def test_dispatch_spawn_allowlist_passes_through_every_board_identifier_env_name(tmp_path, monkeypatch):
    """test_dispatch.py's own allowlist coverage only probes BUILD_MODEL; same real-spawn-and-dump
    technique (`disp._dump_env_script` / `disp._read_env_dump`), extended to all 11 board identifiers."""
    for name in BOARD_IDENTIFIER_ENV_NAMES:
        monkeypatch.setenv(name, f"probe-{name}")
    monkeypatch.setenv("DEV_RUNNER_HOME", str(tmp_path / "drhome"))
    env_file = tmp_path / "env.txt"
    runner = disp._dump_env_script(tmp_path / "runner.sh", env_file)
    r = disp.dispatch.build_task("78", "o/r2", runner=str(runner), lock=str(tmp_path / "lock"),
                                  runs_dir=str(tmp_path / "runs"))
    assert r["ok"]
    assert disp._wait_for(env_file.exists)
    time.sleep(0.2)
    got = disp._read_env_dump(env_file)
    for name in BOARD_IDENTIFIER_ENV_NAMES:
        assert got.get(name) == f"probe-{name}"


# ============================================================================
# AC — the two reads are distinct and both stay: the runner's board-wide `gh project item-list` read
# (lagging) is a mechanically different gh subcommand family from the per-issue `gh api graphql` read the
# operator scripts (and the sweep) use — never the same call shape.
# ============================================================================

def test_runner_board_wide_read_and_operator_per_issue_read_use_different_gh_subcommand_families(tmp_path):
    work, origin = td._make_repo(tmp_path)
    binp = _bin_with_gh_call_log(tmp_path)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Two reads are distinct"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["GH_CALL_LOG"] = str(tmp_path / "gh_call_log")
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    runner_calls = (tmp_path / "gh_call_log").read_text().splitlines()
    assert any(c.startswith("project item-list ") for c in runner_calls)
    assert not any(c.startswith("api graphql") for c in runner_calls)

    binp2 = tp._bin(tmp_path)
    r2 = tp._run(["7", "--repo", "test/repo"], tp._env(tmp_path, binp2))
    assert r2.returncode == 0, r2.stderr
    promote_calls = tp._calls(tmp_path)
    assert any(c[:2] == ["api", "graphql"] for c in promote_calls)
    assert not any(c[:2] == ["project", "item-list"] for c in promote_calls)
