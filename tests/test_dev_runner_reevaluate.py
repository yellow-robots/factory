"""Acceptance tests for issue #70 and issue #239 — dev-runner: --re-evaluate, re-run the terminal merge
decision for an existing PR, INCLUDING a PR that carries no prior merge-decision record at all.

Derived from the issues' acceptance criteria (the spec), NOT the implementation internals:

* `dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>` re-runs the terminal merge decision
  (the four deterministic conditions + the record post) against the PR's CURRENT head — no DoR gate, no
  claim, no worktree, no LLM stage. Two shapes, by whether a prior YR-MERGE(-SHADOW) record exists:
    - a prior record exists (issue #70): reuse ITS originating run's persisted inputs (review verdict,
      bundle hash, resolved roles/ranks); the posted record is ALWAYS a shadow supersession — never a
      merge/rebase/board write, an armed repo included. Its note names the superseded decision/reason.
    - NO prior record (issue #239): the absence of a record is no longer a refusal — it is processed to
      a durable decision record under the standard conditions (green, fresh, approved, rank, shadow
      phase, sentinel, arming), the SAME way the end-of-build terminal step would: an armed, shadow-
      complete, sentinel-clear repo with all conditions passing gets a real squash-merge + a durable
      YR-MERGE: MERGED/BLOCKED record; a non-armed repo (or one still shadow-incomplete) gets a
      YR-MERGE-SHADOW WOULD-MERGE/WOULD-BLOCK record and is NEVER merged. The note records the absence
      of a prior record as a fact, not a refusal reason.
* It refuses (stderr reason, no writes) when the PR is closed/merged, doesn't match the named issue, the
  PR itself can't be fetched, or (record-less) no local build matches the PR's base commit at all — the
  genuinely unprocessable states stay refused.
* It never merges/rebases/claims/writes board state on a non-armed repo, and never weakens the sentinel,
  shadow-completion, or any of the four base conditions — the produced record class is exactly what the
  repo's arming state already permits.
* Pipeline reference documents the shadow merge choreography.

Reuses the stubbed-runner fixtures from test_dev_runner.py (git repo, issue/item JSON) — a REAL first
build (stubbed LLM/gh) produces an actual pushed single-commit branch + a real run dir (review.md,
review-bundle.json), which is exactly the artifact set `--re-evaluate` must locate and reuse. A second,
`--re-evaluate`-specific `gh` stub then serves the PR-state query (`--json
number,state,url,headRefName,baseRefName,headRefOid,comments`) that this mode issues, with a hand-built
prior merge-record comment standing in for the stale record being superseded (or an empty comment list
for the record-less #239 shape). The stub additionally serves `pr list` (canned prior-PR records, for
shadow completion) and `pr merge`/`pr view --json mergeCommit` (the armed squash-merge path), reusing the
canned-record helpers from test_autonomous_merge.py so the tester stays independent of how the runner
renders its own records.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json, os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # reuse the stubbed-runner fixtures (git repo, issue JSON, timeline)
import test_autonomous_merge as tam   # reuse canned prior-PR shadow-completion records

ROOT = td.ROOT
RUNNER = td.RUNNER
EMDASH = "—"

GH_STUB_REEVAL = r'''#!/usr/bin/env bash
case "$1" in
  pr)
    case "$2" in
      view)
        if printf '%s\n' "$@" | grep -q statusCheckRollup; then
          [ -n "${STUB_PRVIEW_FAIL:-}" ] && { echo "pr view failed (stub)" >&2; exit 5; }
          cat "$STUB_ROLLUP_JSON"
        elif printf '%s\n' "$@" | grep -q mergeCommit; then
          printf '{"mergeCommit":{"oid":"%s"}}\n' "${STUB_MERGECOMMIT_OID:-}"
        else
          [ -n "${STUB_PRFETCH_FAIL:-}" ] && { echo "pr view failed (stub)" >&2; exit 5; }
          cat "$STUB_REEVAL_PRJSON"
        fi ;;
      list)
        [ -n "${STUB_PRLIST_FAIL:-}" ] && { echo "pr list failed (stub)" >&2; exit 5; }
        cat "${STUB_PRS_JSON:-/dev/null}" ;;
      comment)
        printf 'PRCOMMENT %s\n' "$*" >> "$STUB_TIMELINE"
        __p=""; __bf=""
        for __a in "$@"; do [ "$__p" = "--body-file" ] && __bf="$__a"; __p="$__a"; done
        [ -n "$__bf" ] && { echo "=== PRCOMMENT ==="; cat "$__bf"; } >> "$STUB_PRCOMMENTS"
        ;;
      merge)
        printf 'MERGE %s\n' "$*" >> "$STUB_GH_CALLS"
        [ -n "${STUB_MERGE_FAIL:-}" ] && { echo "merge API failed (stub)" >&2; exit 6; }
        echo "merged" ;;
      *)       printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS" ;;
    esac ;;
  issue)
    case "$2" in
      comment) printf 'COMMENT %s\n' "$*" >> "$STUB_TIMELINE" ;;
      *)       echo "unhandled issue $2" >&2; exit 9 ;;
    esac ;;
  project)
    case "$2" in
      item-edit) printf 'EDIT %s\n' "$*" >> "$STUB_TIMELINE" ;;
      *)         echo "unhandled project $2" >&2; exit 9 ;;
    esac ;;
  *)  echo "unhandled gh $*" >&2; exit 9 ;;
esac
'''


# ---- stage 1: a REAL first build, stubbed LLM/gh/check, producing a real pushed branch + run dir ----

def _branch_name(work, number):
    """The pushed branch name for issue `number`. The runner deletes its OWN local branch in
    `cleanup_wt` once the build finishes (success or otherwise), but the push already landed it on
    `origin` — and since the runner's worktree shares one object store + refs with `work` (`git
    worktree add`), the remote-tracking ref `refs/remotes/origin/task/<n>-*` survives right there,
    without needing a fetch."""
    r = subprocess.run(["git", "-C", str(work), "for-each-ref", "--format=%(refname:short)",
                        f"refs/remotes/origin/task/{number}-*"], capture_output=True, text=True, check=True)
    lines = r.stdout.strip().splitlines()
    assert lines, f"no origin/task/{number}-* ref found in {work}"
    return lines[0].removeprefix("origin/")


def _first_build(tmp_path, *, number, title, checks=(td.CR_OK,), extra=None):
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=number, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, list(checks))
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    if extra:
        env.update(extra)
    r = td._run([str(number), "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    run_dirs = list((tmp_path / "drhome" / "runs").glob(f"{number}-*"))
    assert run_dirs, "the first build created no run dir"
    run_dir = run_dirs[0]
    branch = _branch_name(work, number)
    head_oid = subprocess.run(["git", "-C", str(work), "rev-parse", f"origin/{branch}"],
                              capture_output=True, text=True, check=True).stdout.strip()
    return work, origin, env, run_dir, branch, head_oid


# ---- a hand-built prior merge-record PR comment (what --re-evaluate must supersede) ----

def _rec_comment(decision, *, run_id, failed_condition=None, mode="shadow", malformed=False):
    if malformed:
        block = "{ this is not valid json"
    else:
        d = {"schema": "yr-merge-record/1", "decision": decision, "run_id": run_id,
             "failed_condition": failed_condition, "mode": mode, "machinery_ok": True}
        block = json.dumps(d)
    prefix = "YR-MERGE" if mode == "armed" else "YR-MERGE-SHADOW"
    marker = f"{prefix}: {decision}" if failed_condition is None else f"{prefix}: {decision} — {failed_condition}"
    return {"body": f"{marker}\n\n```yr-merge-record\n{block}\n```\n"}


# ---- stage 2: the --re-evaluate invocation, with its own gh stub + isolated timeline/calls/comments ----

def _reeval_env(tmp_path, env1, *, pr_number, state="OPEN", head_ref, base_ref="main",
                head_oid, comments, checks=(td.CR_OK,), prs=None, merge_commit_oid=None, extra=None):
    binp2 = tmp_path / "bin2"; binp2.mkdir(parents=True, exist_ok=True)
    td._exec(binp2 / "gh", GH_STUB_REEVAL)
    env = dict(env1)
    env["GH_BIN"] = str(binp2 / "gh")
    prjson = tmp_path / "reeval_pr.json"
    prjson.write_text(json.dumps({
        "number": pr_number, "state": state, "url": f"https://stub/pr/{pr_number}",
        "headRefName": head_ref, "baseRefName": base_ref, "headRefOid": head_oid, "comments": comments,
    }))
    env["STUB_REEVAL_PRJSON"] = str(prjson)
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, list(checks))
    env["STUB_TIMELINE"] = str(tmp_path / "reeval_timeline")
    env["STUB_GH_CALLS"] = str(tmp_path / "reeval_gh_calls")
    env["STUB_PRCOMMENTS"] = str(tmp_path / "reeval_prcomments")
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    env["MERGE_CI_REG_GRACE"] = "0"; env["MERGE_CI_REG_POLL_INTERVAL"] = "0"
    if prs is not None:
        pf = tmp_path / "reeval_prs.json"; pf.write_text(json.dumps(prs))
        env["STUB_PRS_JSON"] = str(pf)
    if merge_commit_oid is not None:
        env["STUB_MERGECOMMIT_OID"] = merge_commit_oid
    if extra:
        env.update(extra)
    return env


def _run_reeval(issue, pr_number, env):
    full = {**os.environ, **td.READABLE_IDS, **env}
    return subprocess.run(["bash", str(RUNNER), str(issue), "--repo", "test/repo",
                          "--re-evaluate", str(pr_number)],
                         capture_output=True, text=True, env=full, cwd=str(ROOT), timeout=60)


def _reeval_body(run_dir):
    p = run_dir / "merge-shadow-reeval.md"
    return p.read_text() if p.exists() else None


def _reeval_record_body(run_dir):
    """The ARMED-path re-evaluation record (MERGED/BLOCKED) — a different file than the shadow one, so a
    test can assert exactly one of the two ever gets written."""
    p = run_dir / "merge-record-reeval.md"
    return p.read_text() if p.exists() else None


def _merged_stub(tmp_path):
    calls = _reeval_gh_calls(tmp_path)
    return "MERGE " in calls and "--squash" in calls


def _reeval_timeline(tmp_path):
    p = tmp_path / "reeval_timeline"
    return p.read_text().splitlines() if p.exists() else []


def _reeval_gh_calls(tmp_path):
    p = tmp_path / "reeval_gh_calls"
    return p.read_text() if p.exists() else ""


def _reeval_prcomments(tmp_path):
    p = tmp_path / "reeval_prcomments"
    return p.read_text() if p.exists() else ""


def _no_writes(tmp_path, run_dir):
    """No record was written to the run dir, no comment was posted, no board/merge/rebase call fired."""
    assert _reeval_body(run_dir) is None
    assert _reeval_record_body(run_dir) is None
    assert _reeval_prcomments(tmp_path) == ""
    assert "MERGE " not in _reeval_gh_calls(tmp_path)
    assert all(not l.startswith("EDIT") for l in _reeval_timeline(tmp_path))


# ================= fresh green head -> WOULD-MERGE, re-evaluation note names the superseded record =====

def test_reevaluate_fresh_green_head_posts_would_merge_with_reeval_note(tmp_path):
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=5, title="Shadow reeval fresh green")
    run_id = run_dir.name
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_id, failed_condition="freshness")]
    env2 = _reeval_env(tmp_path, env1, pr_number=90, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(5, 90, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None, "no re-evaluation record was written"
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    assert f"supersedes WOULD-BLOCK {EMDASH} freshness" in first     # names the superseded decision + reason
    rec = td._shadow_block(body)
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["decision"] == "WOULD-MERGE" and rec["mode"] == "shadow" and rec["machinery_ok"] is True
    assert rec["run_id"] == run_id                                   # the ORIGINATING run's id, reused verbatim
    assert rec["review_verdict"] == "VERDICT: APPROVE"               # reused from the original review.md
    assert rec["build"]["rank"] == 30 and rec["review"]["rank"] == 40  # reused resolved roles/ranks
    assert rec["head_sha"] == head_oid
    assert _reeval_prcomments(tmp_path).count("YR-MERGE-SHADOW") == 1   # posted exactly once
    # branch untouched: no rebase happened (checked on the bare origin, the durable copy of the branch)
    tip = subprocess.run(["git", "-C", str(origin), "rev-parse", f"refs/heads/{branch}"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert tip == head_oid


# ================= stale base (main moved) -> WOULD-BLOCK — freshness =====

def test_reevaluate_stale_base_posts_would_block_freshness(tmp_path):
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=6, title="Shadow reeval stale base")
    run_id = run_dir.name
    comments = [_rec_comment("WOULD-MERGE", run_id=run_id)]
    env2 = _reeval_env(tmp_path, env1, pr_number=91, head_ref=branch, head_oid=head_oid, comments=comments,
                       extra={"MERGE_MAIN_TIP": "0" * 40})           # forces a stale-base decision
    r = _run_reeval(6, 91, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith(f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} freshness")
    assert "supersedes WOULD-MERGE" in first
    rec = td._shadow_block(body)
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "freshness"
    assert rec["main_tip_sha"] == "0" * 40


# ================= issue #239: a record-less, CI-green, review-approved PR is PROCESSED, not refused ===
# The absence of a prior YR-MERGE(-SHADOW) record is no longer a refusal condition — it is evaluated live
# under the standard conditions and produces exactly the record class the repo's arming state permits.

def test_reevaluate_processes_record_less_pr_on_non_armed_repo_to_shadow_would_merge(tmp_path):
    """No prior record, non-armed repo: the PR is processed (not refused) to a shadow WOULD-MERGE record;
    the note carries the record's absence as a fact, and the repo is never merged into (criterion 2)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=20, title="Record-less non-armed")
    env2 = _reeval_env(tmp_path, env1, pr_number=200, head_ref=branch, head_oid=head_oid, comments=[])
    r = _run_reeval(20, 200, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None, "a record-less green/approved PR must be processed, not refused"
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    assert "no prior merge decision record" in first
    rec = td._shadow_block(body)
    assert rec["schema"] == "yr-merge-record/1" and rec["mode"] == "shadow"
    assert rec["run_id"] == run_dir.name                          # located by matching the PR's base commit
    assert rec["review_verdict"] == "VERDICT: APPROVE"
    assert rec["head_sha"] == head_oid
    assert not _merged_stub(tmp_path)                              # never merges on a non-armed repo
    assert _reeval_record_body(run_dir) is None                    # the armed-path record file was never written


def test_reevaluate_never_merges_record_less_pr_on_non_armed_repo_even_shadow_complete(tmp_path):
    """Criterion 2, explicit: even with a fully complete shadow window, a non-armed repo is NEVER merged
    into — the produced record stays shadow, because arming (not shadow completion) gates the mode."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=21, title="Record-less non-armed, shadow complete")
    env2 = _reeval_env(tmp_path, env1, pr_number=201, head_ref=branch, head_oid=head_oid, comments=[],
                       prs=tam._complete_prs())
    r = _run_reeval(21, 201, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None
    rec = td._shadow_block(body)
    assert rec["mode"] == "shadow"
    assert not _merged_stub(tmp_path)
    assert "MERGE " not in _reeval_gh_calls(tmp_path)
    assert all(not l.startswith("EDIT") for l in _reeval_timeline(tmp_path))   # no board writes either


def test_reevaluate_record_less_pr_armed_shadow_complete_all_pass_squash_merges(tmp_path):
    """Armed, shadow-complete, sentinel clear, every condition passing: the record-less PR is driven all
    the way to a real squash-merge and a durable YR-MERGE: MERGED record — the armed evaluator's own
    terminal record, exactly what an armed repo already permits."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=22, title="Record-less armed all-pass")
    env2 = _reeval_env(tmp_path, env1, pr_number=202, head_ref=branch, head_oid=head_oid, comments=[],
                       prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(22, 202, env2)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path), "an armed, shadow-complete, all-pass record-less PR must be squash-merged"
    body = _reeval_record_body(run_dir)
    assert body is not None, "no durable armed re-evaluation record was written"
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE: MERGED")                   # loud durable marker — armed, not shadow
    assert "no prior merge decision record" in first
    rec = td._shadow_block(body)
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["decision"] == "MERGED" and rec["mode"] == "armed" and rec["machinery_ok"] is True
    assert rec["merge_commit"] == "f" * 40
    assert rec["shadow_complete"] is True and rec["sentinel"] == "ok"
    assert rec["build"]["rank"] == 30 and rec["review"]["rank"] == 40
    assert _reeval_body(run_dir) is None                           # never the shadow-path file on this path


def test_reevaluate_record_less_pr_armed_shadow_incomplete_stays_shadow_no_merge(tmp_path):
    """Armed + auto_merge=true but the repo has not completed shadow (only 2 of the needed 3 landed
    successes): arming is refused to be honoured — a shadow WOULD-MERGE with the 'armed, shadow-incomplete
    n/N' note is posted, and NOT a merge (mirrors the live pipeline's own shadow-incomplete stop)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=23, title="Record-less armed shadow-incomplete")
    prs = [tam._pr(20, "WOULD-MERGE", oid="a" * 40), tam._pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40)]
    env2 = _reeval_env(tmp_path, env1, pr_number=203, head_ref=branch, head_oid=head_oid, comments=[],
                       prs=prs, extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(23, 203, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    assert "armed, shadow-incomplete 2/5" in first
    rec = td._shadow_block(body)
    assert rec["mode"] == "shadow" and rec["shadow_complete"] is False and rec["shadow_progress"] == "2/5"
    assert _reeval_record_body(run_dir) is None


def test_reevaluate_record_less_pr_armed_sentinel_thrown_blocks_no_merge(tmp_path):
    """Armed, shadow-complete, every condition passing, but the host sentinel is thrown: the merge is
    refused globally, an armed YR-MERGE: BLOCKED — sentinel record is posted, and no merge happens."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=24, title="Record-less armed sentinel")
    drhome = tmp_path / "drhome"; drhome.mkdir(parents=True, exist_ok=True)
    (drhome / "merge-killswitch").write_text("stop\n")
    env2 = _reeval_env(tmp_path, env1, pr_number=204, head_ref=branch, head_oid=head_oid, comments=[],
                       prs=tam._complete_prs(), extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(24, 204, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_record_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith(f"YR-MERGE: BLOCKED {EMDASH} sentinel")
    rec = td._shadow_block(body)
    assert rec["mode"] == "armed" and rec["decision"] == "BLOCKED" and rec["failed_condition"] == "sentinel"
    assert rec["sentinel"] == "thrown" and rec["shadow_complete"] is True


def test_reevaluate_record_less_pr_armed_failed_condition_blocks_no_merge(tmp_path):
    """Armed, shadow-complete, sentinel clear, but CI is red: an armed YR-MERGE: BLOCKED — ci_green record
    is posted and NO merge happens — a failed condition is never weakened by arming."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=25, title="Record-less armed condition fails")
    env2 = _reeval_env(tmp_path, env1, pr_number=205, head_ref=branch, head_oid=head_oid, comments=[],
                       checks=(td.CR_OK, td.CR_FAIL), prs=tam._complete_prs(),
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(25, 205, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_record_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith(f"YR-MERGE: BLOCKED {EMDASH} ci_green")
    rec = td._shadow_block(body)
    assert rec["mode"] == "armed" and rec["decision"] == "BLOCKED" and rec["failed_condition"] == "ci_green"
    assert rec["sentinel"] == "ok" and rec["shadow_complete"] is True


# ================= refusals: closed / merged / mismatched issue / no or bad prior record / missing =====
# artifacts -- all fail-closed with a stderr reason and NO writes (no record, no comment, no board edit,
# no merge call).

def test_reevaluate_refuses_closed_pr(tmp_path):
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=7, title="Closed PR reeval")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=92, state="CLOSED", head_ref=branch, head_oid=head_oid,
                       comments=comments)
    r = _run_reeval(7, 92, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_merged_pr(tmp_path):
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=8, title="Merged PR reeval")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=93, state="MERGED", head_ref=branch, head_oid=head_oid,
                       comments=comments)
    r = _run_reeval(8, 93, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_pr_not_matching_named_issue(tmp_path):
    """The PR's branch must name THIS issue (task/<issue>-*) — a same-numbered PR belonging to another
    issue's branch is refused, never guessed at."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=9, title="Mismatch reeval")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=94, head_ref="task/999-someone-elses-issue",
                       head_oid=head_oid, comments=comments)
    r = _run_reeval(9, 94, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "issue #9" in r.stderr or "does not belong" in r.stderr.lower()
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_malformed_prior_record(tmp_path):
    """A last merge-record comment that can't be parsed must not be guessed at — refuse."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=11, title="Malformed reeval")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name, malformed=True)]
    env2 = _reeval_env(tmp_path, env1, pr_number=96, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(11, 96, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "malformed" in r.stderr.lower()
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_when_originating_run_dir_is_missing(tmp_path):
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=12, title="Missing run dir")
    comments = [_rec_comment("WOULD-MERGE", run_id="12-doesnotexist")]
    env2 = _reeval_env(tmp_path, env1, pr_number=97, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(12, 97, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_when_review_transcript_is_missing(tmp_path):
    """The originating run's review.md (the terminal-approval input) must exist, or refuse."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=13, title="Missing review.md")
    (run_dir / "review.md").unlink()
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=98, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(13, 98, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_when_review_bundle_is_missing(tmp_path):
    """The originating run's review-bundle.json (rank/provider inputs) must exist, or refuse."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=14, title="Missing bundle")
    (run_dir / "review-bundle.json").unlink()
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=99, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(14, 99, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    _no_writes(tmp_path, run_dir)


def test_reevaluate_environmental_ci_read_failure_refuses_with_no_writes(tmp_path):
    """An environmental gh failure while reading CI status refuses (fail-closed) rather than guessing —
    still no partial/garbage record is ever posted."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=15, title="Env CI failure")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=100, head_ref=branch, head_oid=head_oid, comments=comments,
                       extra={"STUB_PRVIEW_FAIL": "1"})
    r = _run_reeval(15, 100, env2)
    assert r.returncode == 3
    _no_writes(tmp_path, run_dir)


# ================= issue #239: genuinely unprocessable states stay refused, record-less included =======

def test_reevaluate_refuses_closed_pr_with_no_prior_record(tmp_path):
    """A closed PR is unprocessable regardless of whether it ever carried a merge record — the closed
    check still fires first and refuses, even with an empty comment list (no prior record)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=26, title="Closed, record-less reeval")
    env2 = _reeval_env(tmp_path, env1, pr_number=206, state="CLOSED", head_ref=branch, head_oid=head_oid,
                       comments=[])
    r = _run_reeval(26, 206, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_when_pr_cannot_be_fetched_at_all(tmp_path):
    """No PR: the PR fetch itself fails (deleted/never existed/wrong repo) — refused before any record
    lookup is even attempted, exactly as today."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=27, title="Unfetchable PR reeval")
    env2 = _reeval_env(tmp_path, env1, pr_number=207, head_ref=branch, head_oid=head_oid, comments=[],
                       extra={"STUB_PRFETCH_FAIL": "1"})
    r = _run_reeval(27, 207, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "could not fetch" in r.stderr.lower()
    _no_writes(tmp_path, run_dir)


def test_reevaluate_refuses_record_less_pr_with_no_matching_local_build(tmp_path):
    """A record-less PR whose base commit matches NO local run bundle at all (a genuinely
    unbuilt/unlocatable PR) stays a refusal — the fail-closed spirit the missing-run_id refusal already
    had for the prior-record shape."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=28, title="Record-less unlocatable reeval")
    # advance the branch with an extra commit ON TOP of the real build commit: the PR's head^ then
    # resolves to the build's OWN head sha, which is not any run's recorded base_sha (that's the seed).
    td._git(["checkout", "-b", "extra", f"origin/{branch}"], work)
    (work / "extra_file.txt").write_text("extra\n")
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "an extra unbuilt commit"], work)
    td._git(["push", "-q", "origin", f"HEAD:{branch}"], work)
    new_head = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    td._git(["checkout", "main"], work)
    env2 = _reeval_env(tmp_path, env1, pr_number=208, head_ref=branch, head_oid=new_head, comments=[])
    r = _run_reeval(28, 208, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "could not locate a build" in r.stderr.lower()
    _no_writes(tmp_path, run_dir)


# ================= never merges / rebases / claims / writes board state, even armed + would-be-complete =

def test_reevaluate_never_arms_or_merges_even_with_auto_merge_true(tmp_path):
    """auto_merge=true must not flip the posted record to armed/MERGED — re-evaluation always posts a
    shadow record and never calls the merge API, rebases, or touches board state."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=16, title="Armed reeval")
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_dir.name, failed_condition="freshness")]
    env2 = _reeval_env(tmp_path, env1, pr_number=101, head_ref=branch, head_oid=head_oid, comments=comments,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(16, 101, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith("YR-MERGE-SHADOW")   # never the armed YR-MERGE marker
    rec = td._shadow_block(body)
    assert rec["mode"] == "shadow"
    assert "MERGE " not in _reeval_gh_calls(tmp_path)            # the merge API was never called
    assert all(not l.startswith("EDIT") for l in _reeval_timeline(tmp_path))  # no board writes
    tip = subprocess.run(["git", "-C", str(origin), "rev-parse", f"refs/heads/{branch}"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert tip == head_oid                                       # no rebase: the branch tip is unmoved


def test_reevaluate_makes_no_issue_comments_only_the_pr_record(tmp_path):
    """Re-evaluation is silent on the issue itself — its only write is the one PR comment."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=17, title="Silent on issue")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=102, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(17, 102, env2)
    assert r.returncode == 0, r.stderr
    tl = _reeval_timeline(tmp_path)
    assert not any(l.startswith("COMMENT") for l in tl)          # no issue comment
    assert not any(l.startswith("EDIT") for l in tl)              # no board field write
    assert any(l.startswith("PRCOMMENT") for l in tl)             # the record IS posted on the PR


# ================= arg parsing =====

def test_reevaluate_and_dry_run_are_mutually_exclusive(tmp_path):
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp)
    r = td._run(["5", "--repo", "test/repo", "--dry-run", "--re-evaluate", "1"], env)
    assert r.returncode != 0
    assert "mutually exclusive" in r.stderr.lower()


def test_reevaluate_requires_a_numeric_pr_number(tmp_path):
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp)
    r = td._run(["5", "--repo", "test/repo", "--re-evaluate", "abc"], env)
    assert r.returncode != 0
    assert "numeric" in r.stderr.lower()


# ================= documentation: the shadow merge choreography is written down =====

PIPELINE_MD = ROOT / "skills" / "factory" / "references" / "pipeline.md"


def test_pipeline_md_documents_shadow_merge_choreography():
    text = PIPELINE_MD.read_text(encoding="utf-8")
    assert "--re-evaluate" in text, "pipeline.md does not mention --re-evaluate"
    low = text.lower()
    assert "merge only while no build is in flight" in low or "no build is in flight" in low, \
        "pipeline.md missing the serial-merge choreography rule"
    assert "reset" in low, "pipeline.md missing the merged-over WOULD-BLOCK = rolling-window reset rule"
    assert "rebase" in low, "pipeline.md missing the content-identical-rebase recovery step"
