"""Acceptance tests for issue #70 — dev-runner: --re-evaluate, re-run the terminal merge decision for
an existing PR.

Derived from the issue's acceptance criteria (the spec), NOT the implementation internals:

* `dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>` re-runs ONLY the terminal merge
  decision (the four deterministic conditions + the record post) against the PR's CURRENT head, reusing
  the originating run's persisted inputs (review verdict, bundle hash, resolved roles/ranks) — no DoR
  gate, no claim, no worktree, no LLM stage.
* It refuses (stderr reason, no writes) when the PR is closed/merged, doesn't match the named issue, or
  the originating run's artifacts are missing.
* The posted record's note names the superseded record's decision/reason, so history reads truthfully.
* It never merges, rebases, claims, or writes board state — even on an armed, shadow-complete repo.
* Pipeline reference documents the shadow merge choreography.

Reuses the stubbed-runner fixtures from test_dev_runner.py (git repo, issue/item JSON) — a REAL first
build (stubbed LLM/gh) produces an actual pushed single-commit branch + a real run dir (review.md,
review-bundle.json), which is exactly the artifact set `--re-evaluate` must locate and reuse. A second,
`--re-evaluate`-specific `gh` stub then serves the PR-state query (`--json
number,state,url,headRefName,baseRefName,headRefOid,comments`) that this mode issues, with a hand-built
prior merge-record comment standing in for the stale record being superseded.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json, os, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # reuse the stubbed-runner fixtures (git repo, issue JSON, timeline)

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
        else
          cat "$STUB_REEVAL_PRJSON"
        fi ;;
      comment)
        printf 'PRCOMMENT %s\n' "$*" >> "$STUB_TIMELINE"
        __p=""; __bf=""
        for __a in "$@"; do [ "$__p" = "--body-file" ] && __bf="$__a"; __p="$__a"; done
        [ -n "$__bf" ] && { echo "=== PRCOMMENT ==="; cat "$__bf"; } >> "$STUB_PRCOMMENTS"
        ;;
      merge)   printf 'MERGE %s\n' "$*" >> "$STUB_GH_CALLS" ;;
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
                head_oid, comments, checks=(td.CR_OK,), extra=None):
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


def test_reevaluate_refuses_no_prior_merge_record(tmp_path):
    """A PR carrying no YR-MERGE(-SHADOW) record at all has nothing to re-evaluate."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=10, title="No record reeval")
    env2 = _reeval_env(tmp_path, env1, pr_number=95, head_ref=branch, head_oid=head_oid, comments=[])
    r = _run_reeval(10, 95, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
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
