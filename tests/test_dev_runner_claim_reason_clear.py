"""Acceptance tests for issue #241 — dev-runner: claim clears a stale Blocked/Needs-info Reason.

Derived from the issue's acceptance criteria (the spec), NOT the implementation internals:

* WHEN a build claims a task whose Reason is `Blocked` or `Needs-info` AT CLAIM TIME, THE SYSTEM SHALL
  clear that Reason as part of the claim (issue #241, tools/dev-runner.sh:591's `set_status "In
  Progress"`).
* A Reason value outside that set (including no Reason at all) SHALL NOT be touched by the claim.
* The clear is by VALUE at claim time, not by writer — a Projects field carries no author, so a stale
  Blocked/Needs-info left over from ANY prior writer (needs-info bounce, blocked-at-end, env-hold,
  armed-block, or the epic-gate's stranded-claim raise) must not survive a fresh claim and ride the task
  all the way to Done still wearing it.
* Every promotion gate and record grammar stays unchanged: a claim that starts Blocked/Needs-info still
  runs the full IMPL -> TEST -> CHECK -> REVIEW -> In Review pipeline exactly as an unblemished claim
  would, and a build that legitimately fails AFTER such a claim still ends up Blocked via the normal
  failure-path `set_reason`, undisturbed by the claim-time clear that preceded it.

Reuses the stubbed-runner fixtures from test_dev_runner.py (git repo, issue JSON, gh/claude/check stubs,
timeline helpers) — the shared `gh` stub already records every `project item-edit` call verbatim
(including a bare `--clear` flag), so no stub changes are needed; only the canned board item needs a
`reason` string alongside the `status` string that `_item` already sets, mirroring exactly the flat
key shape `tools/dev-runner.sh` reads via `it.get("reason","")` from `gh project item-list --format json`.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td  # reuse the stubbed-runner fixtures (git repo, issue JSON, timeline)

ROOT = td.ROOT
RUNNER = td.RUNNER


# ---- a board item carrying a `reason` string, exactly like `_item` but with the extra field the
# shared helper doesn't set (test_dev_runner.py's own fixtures never need a starting Reason) ----

def _item_with_reason(tmp, *, number=5, status="Ready", reason="", item_id="ITEM1", repo="test/repo"):
    p = tmp / "item.json"
    items = [{"id": item_id, "status": status, "reason": reason,
              "content": {"number": number, "repository": repo}}]
    p.write_text(json.dumps({"items": items}))
    return p


def _env_with_reason(tmp, binp, *, number=5, title="Do a thing", reason="", status="Ready",
                      item_id="ITEM1", repo="test/repo"):
    ij = td._issue(tmp, number=number, title=title)
    it = _item_with_reason(tmp, number=number, status=status, reason=reason, item_id=item_id, repo=repo)
    return td._base_env(tmp, ij, it, binp)


def _reason_edits(tl):
    """Every EDIT line that touches the Reason field (by the readable REASONFIELD id override)."""
    return [l for l in td._edits(tl) if "REASONFIELD" in l]


def _claim_status_index(tl):
    return next(i for i, l in enumerate(tl)
                if l.startswith("EDIT") and "STATUSFIELD" in l and "InProgress" in l)


# ============ the stale Blocked/Needs-info Reason is cleared as part of the claim ============

def test_claim_clears_stale_blocked_reason(tmp_path):
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, _env_with_reason(tmp_path, binp, reason="Blocked"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    tl = td._timeline(tmp_path)
    reason_edits = _reason_edits(tl)
    assert reason_edits, "expected a Reason-field edit clearing the stale Blocked value"
    assert all("--clear" in l for l in reason_edits)
    assert all("ITEM1" in l for l in reason_edits)   # the target item, not some other id
    # the clear rides along with the claim itself: before any stage ran, at/after the claim's own
    # Status->In Progress edit lands.
    claim_i = _claim_status_index(tl)
    clear_i = next(i for i, l in enumerate(tl) if l in reason_edits)
    assert claim_i <= clear_i < tl.index("IMPL")


def test_claim_clears_stale_needs_info_reason(tmp_path):
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, _env_with_reason(tmp_path, binp, reason="Needs-info"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    tl = td._timeline(tmp_path)
    reason_edits = _reason_edits(tl)
    assert reason_edits, "expected a Reason-field edit clearing the stale Needs-info value"
    assert all("--clear" in l for l in reason_edits)
    claim_i = _claim_status_index(tl)
    clear_i = next(i for i, l in enumerate(tl) if l in reason_edits)
    assert claim_i <= clear_i < tl.index("IMPL")


# ============ any other Reason value is left completely untouched ============

def test_claim_leaves_unrelated_reason_value_untouched(tmp_path):
    """A Reason value outside {Blocked, Needs-info} — e.g. some other option the live field carries —
    must not be cleared, or otherwise written, by the claim."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, _env_with_reason(tmp_path, binp, reason="Some-other-reason"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    tl = td._timeline(tmp_path)
    assert not _reason_edits(tl), "a Reason value outside {Blocked, Needs-info} must not be written at all"


def test_claim_with_no_reason_writes_nothing_to_the_reason_field(tmp_path):
    """The ordinary case — no Reason set at all — must not spuriously invoke a clear."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, _env_with_reason(tmp_path, binp, reason=""), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    tl = td._timeline(tmp_path)
    assert not _reason_edits(tl)


# ============ the rest of the promotion machinery / record grammar is unchanged ============

def test_stale_blocked_claim_still_runs_the_full_pipeline_in_order(tmp_path):
    """A claim that clears a stale Blocked Reason still proceeds through the same
    claim -> implement -> tester -> check -> review -> In Review order as any other claim — the fix
    touches only the Reason field, never the Status pipeline or its ordering."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, _env_with_reason(tmp_path, binp, reason="Blocked"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout

    tl = td._timeline(tmp_path)
    claim_i = _claim_status_index(tl)
    inrev_i = next(i for i, l in enumerate(tl)
                   if l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l)
    assert claim_i < tl.index("IMPL") < tl.index("TEST") < tl.index("CHECK") < tl.index("REVIEW") < inrev_i


def test_claim_time_clear_does_not_suppress_a_later_legitimate_blocked(tmp_path):
    """A task that starts Blocked (stale), gets cleared at claim, and then legitimately fails its checks
    must still end up Blocked via the normal failure-path `set_reason` — the claim-time clear is a
    one-shot value check at claim, not a standing suppression of the Reason field for the rest of the
    run."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, _env_with_reason(tmp_path, binp, reason="Blocked"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REPAIR_NOFIX": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "checks still failing" in r.stderr.lower()

    tl = td._timeline(tmp_path)
    reason_edits = _reason_edits(tl)
    # the stale-clear at claim (a --clear) is followed, after the unrepairable failure, by a fresh
    # Reason=Blocked write (a --single-select-option-id, not a --clear) — both against the real item.
    assert any("--clear" in l for l in reason_edits)
    assert any("Blocked" in l and "--clear" not in l for l in reason_edits)
    assert "https://stub/pr/1" not in r.stdout


def test_claim_time_clear_does_not_suppress_a_later_legitimate_needs_info(tmp_path):
    """Same as above for the Needs-info bounce path: an unknown build-model override still bounces the
    task to Backlog/Needs-info with its own fresh comment, even though this claim's own stale Reason
    (had it reached the claim) would have been cleared — here the bounce fires from the DoR gate,
    strictly before the claim step, so the pre-existing Reason is untouched by the clear at all and the
    bounce's own fresh Needs-info write is the only Reason edit."""
    binp = tmp_path / "bin"; td._stubs(binp)
    env = _env_with_reason(tmp_path, binp,
                            reason="Needs-info")
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    ij = td._issue(tmp_path, number=5, body="### Acceptance criteria\n- [ ] x\n\nmodel: gpt-4\n")
    env["STUB_ISSUE_JSON"] = str(ij)
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                              # bounced before claim: no stages ever ran
    reason_edits = _reason_edits(tl)
    assert reason_edits and all("--clear" not in l for l in reason_edits)
    assert any("NeedsInfo" in l for l in reason_edits)
