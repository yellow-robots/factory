"""Acceptance tests for issue #172 — dev-runner: persist the post-repair diff so a blocked run's
salvage recovers the FINAL tree, not the pre-repair snapshot.

Derived from the issue's acceptance criteria (the spec), NOT the implementation internals:

* When the review-repair stage returns (any exit status), the runner stages the worktree and captures
  the staged diff into the run dir as `final.patch`, BEFORE the post-repair check re-run — so both
  blocked-after-repair paths (checks failing after repair; the second review round blocking) leave the
  artifact in place.
* A run that ends Blocked after a repair round ran still has `final.patch` in the run dir after
  worktree teardown.
* A run with no review-repair round writes no `final.patch`; `diff.patch` remains the only diff artifact.
* The pre-PR blocked path (`fail_blocked`) names `final.patch` in its posted record when it exists for
  that run, and omits any such pointer when it doesn't.

Reuses the stubbed-runner fixtures from test_dev_runner.py (git repo, issue/item JSON, gh/claude/check
stubs, timeline) — a REAL build (stubbed LLM/gh) produces a real run dir under a temp DEV_RUNNER_HOME,
which is exactly where the persisted artifacts under test live. The shared claude fake's own
STUB_REVIEWFIX_EDIT knob (tests/harness/claude_fake.py) makes the review-repair round append a
content-visible edit, independent of whether it also "fixes" the review (STUB_REVIEW_NOFIX).

Assertions are on artifact presence/absence and content shape only — never on log prose or exact
runner messages, per the issue's test expectations.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # reuse the stubbed-runner fixtures (git repo, issue JSON, timeline, stubs)

ROOT = td.ROOT
RUNNER = td.RUNNER

# Passes on the FIRST check (before the review round) but fails once the review-repair round has run —
# keyed on the same 'review_repaired' marker the repair stage drops — so the post-repair check re-run
# fails deterministically, exercising the "checks failing after review-repair" blocked path without ever
# reaching a second review round.
CHECK_STUB_FAIL_AFTER_REPAIR = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -f review_repaired ]; then exit 1; fi
exit 0
'''


def _stubs_repair(binp):
    binp.mkdir(parents=True, exist_ok=True)
    td._exec(binp / "gh", td.GH_STUB)
    td._exec(binp / "claude", td.CLAUDE_STUB)
    td._exec(binp / "check.sh", td.CHECK_STUB)   # default: always passes


def _setup(tmp_path, **kw):
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_repair(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, **kw), work)
    return env


# ============ AC: repair round persists a post-repair artifact distinct from the pre-repair diff ============

def test_repair_round_persists_post_repair_artifact_with_the_edit(tmp_path):
    """A run whose review-repair round edits a file persists final.patch containing that edit, and
    final.patch differs from diff.patch (the pre-repair snapshot captured before the review stage)."""
    env = _setup(tmp_path, title="Repair edits a file")
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEWFIX_EDIT": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = td._timeline(tmp_path)
    assert "REVIEWFIX" in tl and tl.count("REVIEW") == 2   # one repair round, re-approved

    rd = td._run_dir(tmp_path)
    diff_before = (rd / "diff.patch").read_text()
    assert "repaired-by-review" not in diff_before          # pre-repair snapshot: no repair content yet

    final = rd / "final.patch"
    assert final.exists()
    final_text = final.read_text()
    assert "repaired-by-review" in final_text                # the repair's edit IS captured
    assert final_text != diff_before                         # and the artifact differs from the pre-repair one


# ============ AC: no repair round -> unchanged behavior, no post-repair artifact ============

def test_no_repair_round_writes_no_post_repair_artifact(tmp_path):
    """A run whose reviewer approves on the first pass never runs review-repair: diff.patch remains the
    only and final diff artifact, and no final.patch is written."""
    env = _setup(tmp_path, title="Clean approve, no repair")
    env["STUB_CLAUDE_CHANGE"] = "1"   # no STUB_REVIEW_BLOCK: reviewer approves immediately
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    assert "REVIEWFIX" not in tl and tl.count("REVIEW") == 1

    rd = td._run_dir(tmp_path)
    assert (rd / "diff.patch").exists()
    assert "hello" in (rd / "diff.patch").read_text()
    assert not (rd / "final.patch").exists()


# ============ AC: blocked-after-repair paths leave the artifact readable after teardown ============

def test_checks_fail_after_repair_leaves_artifact_readable_with_no_second_review(tmp_path):
    """The checks-fail-after-repair path: the post-repair check re-run fails, so the run blocks WITHOUT
    a second review round ever firing — final.patch must already exist and be readable, containing the
    repair's edit, and the worktree must be torn down while the run dir survives."""
    env = _setup(tmp_path, title="Checks fail after repair")
    td._exec(tmp_path / "bin" / "check.sh", CHECK_STUB_FAIL_AFTER_REPAIR)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEWFIX_EDIT": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    tl = td._timeline(tmp_path)
    assert "REVIEWFIX" in tl
    assert tl.count("REVIEW") == 1                            # no second review round ran on this path
    assert "Blocked" in " ".join(td._edits(tl))

    assert td._wt_dir(tmp_path) is None                        # worktree torn down (fail_blocked -> cleanup_wt)
    rd = td._run_dir(tmp_path)                                 # run dir survives teardown
    final = rd / "final.patch"
    assert final.exists()
    assert "repaired-by-review" in final.read_text()


def test_second_review_still_blocks_leaves_artifact_readable(tmp_path):
    """The second-review-blocks path: the repair does not clear the reviewer's block (STUB_REVIEW_NOFIX),
    checks pass on the re-run, but the second review round still requests changes -> Blocked. final.patch
    must already exist (captured before the check re-run) and contain the repair's edit, readable in the
    run dir after the worktree is torn down."""
    env = _setup(tmp_path, title="Second review still blocks")
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1",
                "STUB_REVIEWFIX_EDIT": "1", "STUB_REVIEW_NOFIX": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    tl = td._timeline(tmp_path)
    assert "REVIEWFIX" in tl
    assert tl.count("REVIEW") == 2                             # blocked, repaired, blocked again
    assert "Blocked" in " ".join(td._edits(tl))

    assert td._wt_dir(tmp_path) is None
    rd = td._run_dir(tmp_path)
    final = rd / "final.patch"
    assert final.exists()
    assert "repaired-by-review" in final.read_text()


# ============ AC: fail_blocked's posted record names the artifact iff it exists for the run ============

def test_blocked_record_names_the_post_repair_artifact_when_present(tmp_path):
    """When a repair round ran and final.patch exists, the fail_blocked record (posted issue comment)
    must name it, so recovery is derivable from the trail alone."""
    env = _setup(tmp_path, title="Blocked record names artifact")
    td._exec(tmp_path / "bin" / "check.sh", CHECK_STUB_FAIL_AFTER_REPAIR)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEWFIX_EDIT": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    comments = " ".join(td._comments(tl))
    rd = td._run_dir(tmp_path)
    assert str(rd / "final.patch") in comments


def test_blocked_record_omits_artifact_pointer_when_no_repair_ran(tmp_path):
    """A run blocked WITHOUT any review-repair round (no final.patch ever written) must not name it in
    the fail_blocked record — no dangling pointer to an artifact that doesn't exist."""
    env = _setup(tmp_path, title="Blocked without repair, no pointer")
    # no STUB_CLAUDE_CHANGE: the implementer produces no changes -> "no changes produced" blocks pre-PR,
    # with no review-repair round ever having run.
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    comments = " ".join(td._comments(tl))
    assert "Blocked" in " ".join(td._edits(tl))
    assert "final.patch" not in comments
    rd = td._run_dir(tmp_path)
    assert not (rd / "final.patch").exists()
