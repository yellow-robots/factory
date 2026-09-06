"""Acceptance tests for tools/promote.sh — the standalone-task promotion operator command (#53).

Stubbed `gh` (no network, no `claude`): a fake `gh` serves the canned issue-side GraphQL read and
RECORDS every call (in order) to a shared log file, so the promotion-record-before-status-flip claim
is a call-order assertion, not a convention taken on faith. Every refusal path (closed / off-board /
Type=Feature) is asserted to write NOTHING — no `issue comment`, no `project item-edit`.
"""
import json, os, stat, subprocess, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "promote.sh"

# the shared gh fake (python face, for non-runner operator tools) — lives in tests/harness/gh_fake.py;
# see tests/harness/contract.md for the harness contract this module documents.
sys.path.insert(0, str(ROOT / "tests" / "harness"))
import gh_fake  # noqa: E402
GH_STUB = gh_fake.GH_STUB_TOOLS


def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _bin(tmp):
    b = tmp / "bin"
    b.mkdir(exist_ok=True)
    _exec(b / "gh", GH_STUB)
    return b


def _response(*, state="OPEN", itype="Task", item_id="ITEM1", project_number=1, on_board=True,
              status="Backlog", reason=""):
    """The item now carries Status/Reason: since #436 the engine's transition-check judges the
    from-state too (a funnel must never rewind the machine), so the stub serves where it sits."""
    nodes = []
    if on_board:
        nodes.append({"id": item_id, "project": {"number": project_number},
                      "status": ({"name": status} if status else None),
                      "reason": ({"name": reason} if reason else None)})
    return json.dumps({"data": {"repository": {"issue": {
        "state": state,
        "issueType": ({"name": itype} if itype else None),
        "projectItems": {"nodes": nodes},
    }}}})


# The standalone gates record the promote-act wall demands (it-30, epic #415: the direct lane's fit
# check is enforced AT the promote act, not only downstream at claim). Every promote happy path now
# stubs it onto the trail; `_env(..., gates=False)` models its absence for the refusal test.
GATES_RECORD = "YR-TASK-GATES\nreview: cold pass, findings dispositioned\nfit: FIT\nwho: operator"


def _env(tmp, binp, *, gates=True, **kw):
    return {
        **os.environ,
        "GH_BIN": str(binp / "gh"),
        "STUB_ISSUE_RESPONSE": _response(**kw),
        "STUB_CALLS_LOG": str(tmp / "calls.log"),
        "STUB_REPO": "test/repo",
        "STUB_COMMENTS": json.dumps([GATES_RECORD] if gates else []),
    }


def _run(args, env):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)


def _calls(tmp):
    p = tmp / "calls.log"
    return [json.loads(l) for l in p.read_text().splitlines() if l] if p.exists() else []


def _writes(calls):
    return [c for c in calls if c[:2] in (["issue", "comment"], ["project", "item-edit"])]


# ============ happy path: record before flip, by construction ============

def test_the_promote_act_wall_refuses_without_the_gates_record_and_writes_nothing(tmp_path):
    """it-30 (epic #415): the standalone lane's fit check is enforced AT the promote act, not only
    downstream at claim time. Without the YR-TASK-GATES record on the trail, promote.sh refuses
    before any write — and the refusal names the rule, per the lane's talking-wall discipline."""
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, gates=False))
    assert r.returncode != 0
    assert "YR-TASK-GATES" in r.stderr
    writes = _writes(_calls(tmp_path))
    assert writes == [], f"the wall refused but something was written: {writes}"


def test_comment_posted_strictly_before_status_flip(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    calls = _calls(tmp_path)
    comment_idx = next(i for i, c in enumerate(calls) if c[:2] == ["issue", "comment"])
    edit_idx = next(i for i, c in enumerate(calls) if c[:2] == ["project", "item-edit"])
    assert comment_idx < edit_idx


def test_exactly_one_comment_and_one_status_edit(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    writes = _writes(_calls(tmp_path))
    comments = [c for c in writes if c[:2] == ["issue", "comment"]]
    edits = [c for c in writes if c[:2] == ["project", "item-edit"]]
    assert len(comments) == 1 and len(edits) == 1


def test_comment_body_carries_who_why_date_record(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo", "--reason", "DoR reviewed live"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    comment_call = next(c for c in _calls(tmp_path) if c[:2] == ["issue", "comment"])
    body = comment_call[comment_call.index("--body") + 1]
    assert "YR-PROMOTED" in body
    assert "who:" in body and "why: DoR reviewed live" in body and "date:" in body


def test_status_flip_targets_the_resolved_item_id(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, item_id="ITEM-XYZ"))
    assert r.returncode == 0, r.stderr
    edit_call = next(c for c in _calls(tmp_path) if c[:2] == ["project", "item-edit"])
    assert "ITEM-XYZ" in edit_call


# ============ refusals: write nothing ============

def test_refuses_closed_issue_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, state="CLOSED"))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refuses_issue_absent_from_board_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, on_board=False))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refuses_type_feature_epic_writes_nothing(tmp_path):
    """Since it-31 slice 4 the Feature arm is ruling 5's conditional funnel, not a categorical
    refusal: HERE the harness carries no approval and no resolvable design, so the epic-flip
    wall refuses fail-closed and writes nothing — the pin's teeth are unchanged."""
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, itype="Feature"))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


APPROVAL_RECORD = "YR-EPIC-APPROVAL\ndesign: 01-x\nreview: approved after the cold pass\nwho: operator"


def test_epic_flip_happy_path_record_before_flip_and_verified(tmp_path):
    """Ruling 5's SHALLs end to end in bash (it-31 slice 4): preconditions pass through the
    engine, the YR-EPIC-READY comment lands strictly BEFORE the item-edit, exactly one of each
    write, and the postcondition re-read verifies Ready (the after-edit stub shape)."""
    binp = _bin(tmp_path)
    vault = tmp_path / "vault"
    doc = vault / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: active\n---\nbody\n", encoding="utf-8")
    env = _env(tmp_path, binp, itype="Feature")
    env["STUB_BODY"] = "**Source:** product-spec [[04 projects/x/01-x]] (Obsidian design brain)"
    env["STUB_COMMENTS"] = json.dumps([APPROVAL_RECORD])
    env["STUB_ISSUE_RESPONSE_AFTER_EDIT"] = _response(itype="Feature", status="Ready")
    env["YR_VAULT_ROOT"] = str(vault)
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    calls = _calls(tmp_path)
    comment_idx = [i for i, c in enumerate(calls) if c[:2] == ["issue", "comment"]]
    edit_idx = [i for i, c in enumerate(calls) if c[:2] == ["project", "item-edit"]]
    assert len(comment_idx) == 1 and len(edit_idx) == 1
    assert comment_idx[0] < edit_idx[0]                     # record BEFORE flip, by construction
    body_call = calls[comment_idx[0]]
    assert any("YR-EPIC-READY" in a for a in body_call)
    assert any("04 projects/x/01-x" in a for a in body_call)


def test_epic_flip_refuses_when_design_is_not_active_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    vault = tmp_path / "vault"
    doc = vault / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: draft\n---\nbody\n", encoding="utf-8")
    env = _env(tmp_path, binp, itype="Feature")
    env["STUB_BODY"] = "**Source:** product-spec [[04 projects/x/01-x]] (Obsidian design brain)"
    env["STUB_COMMENTS"] = json.dumps([APPROVAL_RECORD])
    env["YR_VAULT_ROOT"] = str(vault)
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refuses_type_epic_epic_writes_nothing(tmp_path):
    """issue #407: the refuse gate matches both arms of the vocabulary — an Epic-typed epic is refused
    exactly like a Feature-typed one, never promoted as if standalone."""
    binp = _bin(tmp_path)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, itype="Epic"))
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_refuses_type_epic_case_insensitively(tmp_path):
    binp = _bin(tmp_path)
    for itype in ("EPIC", "epic", "EpIc", "FEATURE", "feature"):
        r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, itype=itype))
        assert r.returncode != 0, f"itype={itype!r} should refuse"
    assert not _writes(_calls(tmp_path))


def test_refusal_exit_code_matches_between_feature_and_epic_arms(tmp_path):
    """Both arms of the vocabulary refuse via the identical code path — same exit code, not two
    different refusal shapes for the two spellings of 'epic'."""
    binp = _bin(tmp_path)
    feature_refused = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, itype="Feature"))
    epic_refused = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, itype="Epic"))
    assert feature_refused.returncode == epic_refused.returncode != 0


def test_refusal_exit_code_is_distinct_from_success(tmp_path):
    binp = _bin(tmp_path)
    ok = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp))
    refused = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, state="CLOSED"))
    assert ok.returncode == 0
    assert refused.returncode != 0 and refused.returncode != ok.returncode


# ============ the machinery arm (it-36 slice G, #472) ============
#
# Under YR_MACHINERY, the App identity flips the epic through the SAME funnel shape, but through
# the machinery-only transition row (`task.backlog->ready.epic-flip.machinery`) — its own extra
# `epic-triage-license` evaluator guard (`tools/design_gate.py evaluate --issue`), real end to end
# here (not stubbed out): the epic's own trail carries both the YR-EPIC-APPROVAL record and, in the
# SAME canned comments (the generic `issue view` stub answers any issue number identically — the
# triage evaluator's own `gh issue view <triage_issue>` read lands on the very same fixture), the
# owner's `YR-TRIAGE: seed=<issue#> disposition=go` record — `epic-triage-license`'s own scope-by-
# issue addressing (`design_gate.triage_license`) treats the epic issue NUMBER itself as the seed.
# WHO comes from YR_GH_APP_SLUG; `gh api user` is never called (it answers 403 under an installation
# token) — asserted directly against the call log.

MACHINERY_TRIAGE_GO = {"body": "YR-TRIAGE: seed=7 disposition=go who=@the-owner",
                       "author": {"login": "the-owner"}}


def _pm_config(tmp, *, repo="test/repo", triage_issue=55, epic_issue=7):
    path = tmp / "pm-repos.json"
    path.write_text(json.dumps({"repos": [
        {"repo": repo, "triage_issue": triage_issue, "epic_issue": epic_issue}]}))
    return path


def _machinery_env(tmp_path, binp, *, slug="yr-pm[bot]", triage_go=True, **kw):
    env = _env(tmp_path, binp, itype="Feature", **kw)
    env["YR_MACHINERY"] = "1"
    if slug is not None:
        env["YR_GH_APP_SLUG"] = slug
    env["YR_OWNER_LOGIN"] = "the-owner"
    env["YR_PM_CONFIG"] = str(_pm_config(tmp_path))
    comments = [APPROVAL_RECORD] + ([MACHINERY_TRIAGE_GO] if triage_go else [])
    env["STUB_COMMENTS"] = json.dumps(comments)
    env["STUB_BODY"] = "**Source:** product-spec [[04 projects/x/01-x]] (Obsidian design brain)"
    return env


def test_machinery_arm_happy_path_record_before_flip_who_from_slug(tmp_path):
    binp = _bin(tmp_path)
    vault = tmp_path / "vault"
    doc = vault / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: active\n---\nbody\n", encoding="utf-8")
    env = _machinery_env(tmp_path, binp)
    env["YR_VAULT_ROOT"] = str(vault)
    env["STUB_ISSUE_RESPONSE_AFTER_EDIT"] = _response(itype="Feature", status="Ready")
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    calls = _calls(tmp_path)
    comment_idx = [i for i, c in enumerate(calls) if c[:2] == ["issue", "comment"]]
    edit_idx = [i for i, c in enumerate(calls) if c[:2] == ["project", "item-edit"]]
    assert len(comment_idx) == 1 and len(edit_idx) == 1
    assert comment_idx[0] < edit_idx[0]                     # record BEFORE flip, by construction
    body_call = calls[comment_idx[0]]
    assert any("YR-EPIC-READY" in a for a in body_call)
    body = body_call[body_call.index("--body") + 1]
    assert "who: @yr-pm[bot]" in body
    assert not any(c[:2] == ["api", "user"] for c in calls), \
        "the machinery arm must never call `gh api user` (403 under an installation token)"
    assert "yr-pm[bot]" in r.stdout


def test_yr_machinery_alone_without_the_app_slug_still_takes_the_attended_arm(tmp_path):
    """The discriminator is BOTH YR_MACHINERY and the App identity, never YR_MACHINERY alone — this
    suite's own autouse fixture sets YR_MACHINERY=1 for every test (`tests/conftest.py`), so absent
    YR_GH_APP_SLUG the existing attended arm must still run unmodified (`gh api user` included),
    never a refusal."""
    binp = _bin(tmp_path)
    vault = tmp_path / "vault"
    doc = vault / "04 projects" / "x" / "01-x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nstatus: active\n---\nbody\n", encoding="utf-8")
    env = _machinery_env(tmp_path, binp, slug=None, triage_go=False)
    env["YR_VAULT_ROOT"] = str(vault)
    env["STUB_ISSUE_RESPONSE_AFTER_EDIT"] = _response(itype="Feature", status="Ready")
    env["STUB_WHO"] = "a-human-operator"
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert any(c[:2] == ["api", "user"] for c in _calls(tmp_path))
    assert "a-human-operator" in r.stdout


def test_machinery_arm_refuses_without_a_triage_go_record_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    env = _machinery_env(tmp_path, binp, triage_go=False)
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


def test_machinery_arm_refuses_without_the_epic_approval_record_writes_nothing(tmp_path):
    binp = _bin(tmp_path)
    env = _machinery_env(tmp_path, binp)
    env["STUB_COMMENTS"] = json.dumps([MACHINERY_TRIAGE_GO])   # no YR-EPIC-APPROVAL at all
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert not _writes(_calls(tmp_path))


# ============ no LLM anywhere ============

def test_script_never_invokes_an_llm():
    text = SCRIPT.read_text().lower()
    assert "claude" not in text
