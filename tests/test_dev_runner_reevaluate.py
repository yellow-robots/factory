"""Acceptance tests for issue #70 and issue #239 — dev-runner: --re-evaluate, re-run the terminal merge
decision for an existing PR, INCLUDING a PR that carries no prior merge-decision record at all.

Derived from the issues' acceptance criteria (the spec), NOT the implementation internals:

* `dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>` re-runs the terminal merge decision
  (the four deterministic conditions + the record post) against the PR's CURRENT head — no DoR gate, no
  claim, no worktree, no LLM stage. Two shapes, by whether a prior YR-MERGE(-SHADOW) record exists:
    - a prior record exists (issue #70, completed by issue #510): reuse ITS originating run's persisted
      inputs (review verdict, bundle hash, resolved roles/ranks); the posted record's note names the
      superseded decision/reason and the superseded record stays on the trail. Since #510 (the owner's
      ruling: a green recovery merges; the human's intervention is for a recovery that fails) this
      shape is judged under the SAME arming/sentinel/shadow-completion gates as the record-less shape
      and produces the SAME record class — an armed, shadow-complete, sentinel-clear, all-pass
      re-evaluation squash-merges and posts YR-MERGE: MERGED; a prior `unrecoverable` block is no
      exception (the live head is what is judged; the build itself is never resumed).
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
  repo's arming state already permits. The PR's base is its merge base with the base branch (#510), so
  a branch carrying more than one commit on a fresh tip is not misjudged as stale, and a head already
  contained in the base branch refuses as malformed_record.
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

def _rec_comment(decision, *, run_id, failed_condition=None, mode="shadow", malformed=False,
                  base_sha=None, head_sha=None):
    if malformed:
        block = "{ this is not valid json"
    else:
        d = {"schema": "yr-merge-record/1", "decision": decision, "run_id": run_id,
             "failed_condition": failed_condition, "mode": mode, "machinery_ok": True}
        if base_sha is not None:
            d["base_sha"] = base_sha
        if head_sha is not None:
            d["head_sha"] = head_sha
        block = json.dumps(d)
    prefix = "YR-MERGE" if mode == "armed" else "YR-MERGE-SHADOW"
    marker = f"{prefix}: {decision}" if failed_condition is None else f"{prefix}: {decision} — {failed_condition}"
    return {"body": f"{marker}\n\n```yr-merge-record\n{block}\n```\n"}


# ---- stage 2: the --re-evaluate invocation, with its own gh stub + isolated timeline/calls/comments ----

def _reeval_env(tmp_path, env1, *, pr_number, state="OPEN", head_ref, base_ref="main",
                head_oid, comments, checks=(td.CR_OK,), prs=None, merge_commit_oid=None, extra=None):
    binp2 = tmp_path / "bin2"; binp2.mkdir(parents=True, exist_ok=True)
    td._exec(binp2 / "gh", td.GH_STUB)
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


# ================= issue #319: the recovery lane judges LIVE state, not a stale API/record view =========
# Before judging anything, a freshly fetched task-branch tip must agree with the PR's live head already
# read from the API — a disagreement (the API's headRefOid stale relative to a fresh fetch, e.g. a
# force-push/rebase landing between the two reads) is refused loudly, naming BOTH shas, before any record
# is posted (the seed's website#86/PR#93 exercise judged the pre-rebase head this way). Separately, a
# prior record that PARSED cleanly can still carry the observed incident shape — its own recorded
# base_sha equal to its own recorded head_sha, or a recorded base_sha that is not an ancestor of the PR's
# live head — and must refuse as `malformed_record`, never be silently re-derived as a plausible
# `freshness` (or any other) condition.

def test_reevaluate_refuses_when_fetched_tip_disagrees_with_api_live_head_naming_both_shas(tmp_path):
    """BEFORE judging, the just-fetched branch tip must agree with the PR's live head already read from
    the API. A disagreement refuses loudly, naming BOTH shas, and posts no record at all."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=33, title="Live head disagreement")
    stale_api_head = "e" * 40                       # disagrees with the actually-pushed branch tip
    env2 = _reeval_env(tmp_path, env1, pr_number=320, head_ref=branch, head_oid=stale_api_head, comments=[])
    r = _run_reeval(33, 320, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert head_oid in r.stderr                     # the fetched (real, current) tip
    assert stale_api_head in r.stderr                # the API's reported (stale) live head
    _no_writes(tmp_path, run_dir)


def test_reevaluate_matching_head_does_not_trip_the_disagreement_refusal(tmp_path):
    """Clean-path pin: when the fetched tip and the API's live head agree (the ordinary case, exactly
    what every other test in this module already exercises), the new disagreement check never fires and
    re-evaluation proceeds exactly as before issue #319."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=34, title="Live head agrees")
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name)]
    env2 = _reeval_env(tmp_path, env1, pr_number=321, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(34, 321, env2)
    assert r.returncode == 0, r.stderr
    assert "disagrees" not in r.stderr
    body = _reeval_body(run_dir)
    assert body is not None and body.splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-MERGE")


def test_reevaluate_refuses_malformed_record_when_recorded_base_equals_head_sha(tmp_path):
    """Issue #319, the PR#93 shape: a prior record whose OWN recorded base_sha equals its own recorded
    head_sha is refused as malformed_record, naming the malformation — never re-derived as a plausible
    `freshness` (or any other) condition, and no record is posted."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=35, title="Malformed record base==head")
    same_sha = "a" * 40
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name, base_sha=same_sha, head_sha=same_sha)]
    env2 = _reeval_env(tmp_path, env1, pr_number=322, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(35, 322, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "malformed_record" in r.stderr
    assert same_sha in r.stderr
    _no_writes(tmp_path, run_dir)   # never posted as a freshness (or any) record — a bare refusal only


def test_reevaluate_refuses_malformed_record_when_recorded_base_is_not_an_ancestor_of_live_head(tmp_path):
    """Issue #319: a prior record's recorded base_sha that is NOT an ancestor of the PR's live head is
    refused as malformed_record, naming the malformation — never re-derived as a plausible `freshness`
    condition. The base_sha here is a real, resolvable commit (main advanced AFTER the branch was cut),
    not merely an unresolvable string — the genuinely-diverged shape, not just a typo'd sha."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=36, title="Malformed record non-ancestor base")
    td._git(["checkout", "main"], work)
    (work / "later_main.txt").write_text("later\n")
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "a later main commit, landed after the branch was cut"], work)
    td._git(["push", "-q", "origin", "main"], work)
    later_main_sha = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True).stdout.strip()
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name, base_sha=later_main_sha, head_sha="b" * 40)]
    env2 = _reeval_env(tmp_path, env1, pr_number=323, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(36, 323, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "malformed_record" in r.stderr
    assert later_main_sha in r.stderr
    _no_writes(tmp_path, run_dir)   # never posted as a freshness (or any) record — a bare refusal only


def test_reevaluate_well_formed_base_and_head_sha_in_prior_record_does_not_refuse(tmp_path):
    """Clean-path pin: a prior record whose base_sha genuinely IS an ancestor of the live head, and
    differs from its head_sha (the ordinary, well-formed shape) must not trip either new malformed_record
    check — re-evaluation proceeds to its normal shadow supersession exactly as before issue #319."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=37, title="Well-formed base/head sha")
    real_base_sha = subprocess.run(["git", "-C", str(work), "rev-parse", f"{head_oid}^"],
                                   capture_output=True, text=True, check=True).stdout.strip()
    comments = [_rec_comment("WOULD-MERGE", run_id=run_dir.name, base_sha=real_base_sha, head_sha=head_oid)]
    env2 = _reeval_env(tmp_path, env1, pr_number=324, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(37, 324, env2)
    assert r.returncode == 0, r.stderr
    assert "malformed_record" not in r.stderr
    body = _reeval_body(run_dir)
    assert body is not None and body.splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-MERGE")


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


# ================= issue #240 as ruled by issue #510: a prior unrecoverable block is judged on its live head ==

def test_reevaluate_prior_unrecoverable_block_armed_all_pass_completes_the_merge(tmp_path):
    """Issue #510 (the owner's ruling: "complete it too"): a PR carrying a prior `YR-MERGE: BLOCKED —
    unrecoverable` record (the fact-stating record the terminal step posts once freshness remediation
    has already force-pushed the branch before a later step failed environmentally) is judged like any
    other prior record — the runner's own rebase was content-identical, so the live head is the reviewed
    content. Armed, shadow-complete, sentinel-clear, every condition passing: the lane squash-merges and
    posts YR-MERGE: MERGED whose note names the unrecoverable record; the build itself is never resumed
    (only the terminal decision re-runs), and the superseded record stays on the trail."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=29, title="Re-evaluate a prior unrecoverable block")
    run_id = run_dir.name
    comments = [_rec_comment("BLOCKED", run_id=run_id, failed_condition="unrecoverable", mode="armed")]
    env2 = _reeval_env(tmp_path, env1, pr_number=209, head_ref=branch, head_oid=head_oid, comments=comments,
                       prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(29, 209, env2)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path), "an armed, shadow-complete, all-pass re-evaluation completes the merge"
    body = _reeval_record_body(run_dir)
    assert body is not None, "the durable armed record must be written"
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE: MERGED")
    assert f"supersedes BLOCKED {EMDASH} unrecoverable" in first   # names the superseded unrecoverable block
    rec = td._shadow_block(body)
    assert rec["mode"] == "armed" and rec["decision"] == "MERGED" and rec["run_id"] == run_id
    assert rec["merge_commit"] == "f" * 40
    assert _reeval_body(run_dir) is None                 # never the shadow-path file on this path


def test_reevaluate_prior_unrecoverable_block_armed_red_condition_blocks_no_merge(tmp_path):
    """The same shape with CI red: the lane blocks on the live condition (an armed BLOCKED — ci_green
    record naming the superseded unrecoverable block), never a merge — the ruling completes a GREEN
    recovery, and a failing one is where the human's intervention belongs."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=30, title="Re-evaluate a prior unrecoverable block, CI red")
    run_id = run_dir.name
    comments = [_rec_comment("BLOCKED", run_id=run_id, failed_condition="unrecoverable", mode="armed")]
    env2 = _reeval_env(tmp_path, env1, pr_number=210, head_ref=branch, head_oid=head_oid, comments=comments,
                       checks=(td.CR_OK, td.CR_FAIL), prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(30, 210, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_record_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith(f"YR-MERGE: BLOCKED {EMDASH} ci_green")
    assert f"supersedes BLOCKED {EMDASH} unrecoverable" in first
    rec = td._shadow_block(body)
    assert rec["mode"] == "armed" and rec["decision"] == "BLOCKED" and rec["failed_condition"] == "ci_green"


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
    had for the prior-record shape. Since #510 the base is the merge base with main, so the unlocatable
    shape is a branch cut from a main commit no run was built from: main moves, the branch is re-cut from
    the new tip with one unbuilt commit, and its merge base (the new tip) is no run's recorded base."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=28, title="Record-less unlocatable reeval")
    td._git(["checkout", "-q", "main"], work)
    (work / "moved.txt").write_text("main moved\n")
    td._git(["add", "-A"], work); td._git(["commit", "-q", "-m", "main moves past the seed"], work)
    td._git(["push", "-q", "origin", "main"], work)
    td._git(["checkout", "-q", "-b", "recut"], work)
    (work / "extra_file.txt").write_text("extra\n")
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "an unbuilt commit on a re-cut branch"], work)
    td._git(["push", "-q", "-f", "origin", f"HEAD:{branch}"], work)
    new_head = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    td._git(["checkout", "-q", "main"], work)
    env2 = _reeval_env(tmp_path, env1, pr_number=208, head_ref=branch, head_oid=new_head, comments=[])
    r = _run_reeval(28, 208, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr
    assert "could not locate a build" in r.stderr.lower()
    _no_writes(tmp_path, run_dir)


def test_reevaluate_record_less_two_commit_branch_is_located_by_its_merge_base(tmp_path):
    """#510: the pre-#510 unlocatable shape — an extra commit ON TOP of the real build commit — is now
    located: the merge base with main is the seed the run's bundle recorded, so the record-less PR is
    evaluated live instead of refused (the it-33 PR #489 repair shape, record-less variant)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=48, title="Record-less two-commit branch, located")
    main_tip = _origin_main(work)
    new_head = _push_second_commit(work, branch, "repair\n")
    env2 = _reeval_env(tmp_path, env1, pr_number=417, head_ref=branch, head_oid=new_head, comments=[])
    r = _run_reeval(48, 417, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE"), first
    assert "no prior merge decision record" in first
    rec = td._shadow_block(body)
    assert rec["base_sha"] == main_tip and rec["head_sha"] == new_head


# ================= never merges / rebases / claims / writes board state, even armed + would-be-complete =

def test_reevaluate_prior_record_armed_shadow_incomplete_stays_shadow_no_merge(tmp_path):
    """auto_merge=true with a prior record but the shadow phase incomplete (no prior PRs at all here):
    arming is not honoured — the lane posts the shadow supersession with the 'armed, shadow-incomplete
    k/N' note and never calls the merge API, rebases, or touches board state (#510 keeps the
    record-less shape's stop; shadow incompleteness is never a BLOCKED reason)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(tmp_path, number=16, title="Armed reeval")
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_dir.name, failed_condition="freshness")]
    prs = [tam._pr(20, "WOULD-MERGE", oid="a" * 40), tam._pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40)]
    env2 = _reeval_env(tmp_path, env1, pr_number=101, head_ref=branch, head_oid=head_oid, comments=comments,
                       prs=prs, extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(16, 101, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE")     # shadow-incomplete: never the armed marker
    assert "armed, shadow-incomplete 2/5" in first
    rec = td._shadow_block(body)
    assert rec["mode"] == "shadow" and rec["shadow_complete"] is False and rec["shadow_progress"] == "2/5"
    assert _reeval_record_body(run_dir) is None
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
    # issue #510: the choreography states the ruling and no longer claims the with-record stop-short
    assert "a green recovery merges" in low, "pipeline.md missing #510's rule"
    assert "never merges, rebases, claims, or writes board state" not in low, \
        "pipeline.md still claims the with-record re-evaluation never merges (pre-#510)"


# ================= issue #510: the recovery lane completes an armed merge when green ====================
# The owner's ruling (2026-09-06): "The recovery lane should provide a way to merge if the checks are
# green... The actual value of forcing human intervention is when the recovery lane fails to recover."
# A prior-record re-evaluation is judged under the SAME arming/sentinel/shadow-completion gates as the
# record-less shape and produces the SAME record class; the superseded record stays on the trail. The
# PR's base is its merge base with the base branch, never the head's parent.

def _push_second_commit(work, branch, text):
    """An attended repair pushed as a SECOND commit on the runner's branch (it-33's PR #489 shape):
    returns the new branch tip. `work` is left back on main."""
    td._git(["fetch", "-q", "origin", branch], work)
    td._git(["checkout", "-q", "--detach", f"origin/{branch}"], work)
    (work / "REPAIR.md").write_text(text)
    td._git(["add", "-A"], work); td._git(["commit", "-q", "-m", "attended repair, second commit"], work)
    td._git(["push", "-q", "origin", f"HEAD:refs/heads/{branch}"], work)
    tip = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    td._git(["checkout", "-q", "main"], work)
    return tip


def _move_main(work, text):
    """Main moves (an unrelated merge landed): returns the new main tip."""
    td._git(["checkout", "-q", "main"], work)
    (work / "OTHER.md").write_text(text)
    td._git(["add", "-A"], work); td._git(["commit", "-q", "-m", "an unrelated merge on main"], work)
    td._git(["push", "-q", "origin", "main"], work)
    return subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _origin_main(work):
    td._git(["fetch", "-q", "origin", "main"], work)
    return subprocess.run(["git", "-C", str(work), "rev-parse", "origin/main"],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_reevaluate_prior_record_armed_shadow_complete_all_pass_completes_the_merge(tmp_path):
    """#510 criterion 1: a prior BLOCKED — ci_green record (a suite race on an unchanged head, the it-32
    slice 3 shape), now green: armed, shadow-complete, sentinel clear, every condition passing — the lane
    squash-merges and posts YR-MERGE: MERGED whose note names the superseded record, reusing the
    originating run's verdict and ranks. The prior record is never edited: the trail keeps both."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=41, title="Prior block, green recovery, armed")
    run_id = run_dir.name
    comments = [_rec_comment("BLOCKED", run_id=run_id, failed_condition="ci_green", mode="armed")]
    env2 = _reeval_env(tmp_path, env1, pr_number=410, head_ref=branch, head_oid=head_oid, comments=comments,
                       prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(41, 410, env2)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path), "a green recovery on an armed, shadow-complete repo completes the merge"
    body = _reeval_record_body(run_dir)
    assert body is not None, "no durable armed re-evaluation record was written"
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE: MERGED")
    assert f"re-evaluation of run {run_id} {EMDASH} supersedes BLOCKED {EMDASH} ci_green" in first
    rec = td._shadow_block(body)
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["decision"] == "MERGED" and rec["mode"] == "armed" and rec["machinery_ok"] is True
    assert rec["run_id"] == run_id                                   # the ORIGINATING run's id, reused verbatim
    assert rec["review_verdict"] == "VERDICT: APPROVE"               # reused from the original review.md
    assert rec["build"]["rank"] == 30 and rec["review"]["rank"] == 40
    assert rec["merge_commit"] == "f" * 40
    assert rec["shadow_complete"] is True and rec["sentinel"] == "ok" and rec["auto_merge"] is True
    assert _reeval_body(run_dir) is None                             # never the shadow-path file on this path
    assert _reeval_prcomments(tmp_path).count("YR-MERGE: MERGED") == 1   # posted exactly once
    assert all(not l.startswith("EDIT") for l in _reeval_timeline(tmp_path))   # no board write by the lane


def test_reevaluate_prior_record_armed_failed_condition_blocks_no_merge(tmp_path):
    """#510 criterion 2: armed, shadow-complete, sentinel clear, but CI is still red — an armed
    YR-MERGE: BLOCKED — ci_green record naming the superseded record, and NO merge: a failing recovery
    is exactly where the human's intervention belongs."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=42, title="Prior block, recovery still red, armed")
    run_id = run_dir.name
    comments = [_rec_comment("BLOCKED", run_id=run_id, failed_condition="ci_green", mode="armed")]
    env2 = _reeval_env(tmp_path, env1, pr_number=411, head_ref=branch, head_oid=head_oid, comments=comments,
                       checks=(td.CR_OK, td.CR_FAIL), prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(42, 411, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_record_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith(f"YR-MERGE: BLOCKED {EMDASH} ci_green")
    assert f"supersedes BLOCKED {EMDASH} ci_green" in first
    rec = td._shadow_block(body)
    assert rec["mode"] == "armed" and rec["decision"] == "BLOCKED" and rec["failed_condition"] == "ci_green"
    assert rec["sentinel"] == "ok" and rec["shadow_complete"] is True
    assert _reeval_body(run_dir) is None


def test_reevaluate_prior_record_armed_sentinel_thrown_blocks_no_merge(tmp_path):
    """#510 criterion 2: the host sentinel is thrown — the merge is refused globally, an armed
    YR-MERGE: BLOCKED — sentinel record is posted, no merge; the prior-record shape gets no exemption."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=43, title="Prior block, sentinel thrown, armed")
    run_id = run_dir.name
    drhome = tmp_path / "drhome"; drhome.mkdir(parents=True, exist_ok=True)
    (drhome / "merge-killswitch").write_text("stop\n")
    comments = [_rec_comment("BLOCKED", run_id=run_id, failed_condition="ci_green", mode="armed")]
    env2 = _reeval_env(tmp_path, env1, pr_number=412, head_ref=branch, head_oid=head_oid, comments=comments,
                       prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(43, 412, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_record_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith(f"YR-MERGE: BLOCKED {EMDASH} sentinel")
    rec = td._shadow_block(body)
    assert rec["mode"] == "armed" and rec["failed_condition"] == "sentinel" and rec["sentinel"] == "thrown"


def test_reevaluate_prior_record_non_armed_shadow_complete_stays_shadow_no_merge(tmp_path):
    """#510 criterion 3: a non-armed repo is unchanged — even shadow-complete and all-pass, a prior-record
    re-evaluation posts the shadow supersession and never merges (arming, not shadow completion, gates
    the mode)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=44, title="Prior block, non-armed, shadow complete")
    run_id = run_dir.name
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_id, failed_condition="ci_green")]
    env2 = _reeval_env(tmp_path, env1, pr_number=413, head_ref=branch, head_oid=head_oid, comments=comments,
                       prs=tam._complete_prs(), merge_commit_oid="f" * 40)
    r = _run_reeval(44, 413, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    assert f"supersedes WOULD-BLOCK {EMDASH} ci_green" in first
    rec = td._shadow_block(body)
    assert rec["mode"] == "shadow" and rec["auto_merge"] is False
    assert _reeval_record_body(run_dir) is None


def test_reevaluate_two_commit_branch_on_current_tip_is_fresh(tmp_path):
    """#510 criterion 4: an attended repair pushed as a SECOND commit on the runner's branch, main
    unmoved — the base is the merge base (main's tip), so freshness passes and the record's base_sha is
    the tip, not the runner's slice commit; the prior record's recorded base stays an ancestor."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=45, title="Two-commit branch, fresh")
    run_id = run_dir.name
    main_tip = _origin_main(work)
    new_tip = _push_second_commit(work, branch, "repair\n")
    assert new_tip != head_oid
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_id, failed_condition="ci_green",
                             base_sha=main_tip, head_sha=head_oid)]
    env2 = _reeval_env(tmp_path, env1, pr_number=414, head_ref=branch, head_oid=new_tip, comments=comments)
    r = _run_reeval(45, 414, env2)
    assert r.returncode == 0, r.stderr
    body = _reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE"), first    # fresh — never a false freshness block
    rec = td._shadow_block(body)
    assert rec["base_sha"] == main_tip and rec["main_tip_sha"] == main_tip and rec["head_sha"] == new_tip


def test_reevaluate_stale_base_is_merge_base_not_tip(tmp_path):
    """#510 criterion 4, the genuinely stale case with the REAL origin tip moved (not a canned sha): main
    gained an unrelated commit after the branch was cut — the merge base is the old cut point, main's tip
    is newer, so freshness fails; a stale green never merges."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=46, title="Stale base via a moved main")
    run_id = run_dir.name
    old_tip = _origin_main(work)
    new_main = _move_main(work, "other\n")
    assert new_main != old_tip
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_id, failed_condition="ci_green")]
    env2 = _reeval_env(tmp_path, env1, pr_number=415, head_ref=branch, head_oid=head_oid, comments=comments,
                       prs=tam._complete_prs(), merge_commit_oid="f" * 40,
                       extra={"MERGE_AUTO_MERGE": "true"})
    r = _run_reeval(46, 415, env2)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _reeval_record_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith(f"YR-MERGE: BLOCKED {EMDASH} freshness")
    rec = td._shadow_block(body)
    assert rec["base_sha"] == old_tip and rec["main_tip_sha"] == new_main


def test_reevaluate_refuses_when_head_is_already_contained_in_base(tmp_path):
    """#510 criterion 4: a head already contained in the base branch (main fast-forwarded onto it) has a
    merge base equal to the head — the malformed shape — and refuses by name, with no writes."""
    work, origin, env1, run_dir, branch, head_oid = _first_build(
        tmp_path, number=47, title="Head contained in base")
    td._git(["fetch", "-q", "origin", branch], work)
    td._git(["checkout", "-q", "main"], work)
    td._git(["merge", "-q", "--ff-only", f"origin/{branch}"], work)
    td._git(["push", "-q", "origin", "main"], work)
    comments = [_rec_comment("WOULD-BLOCK", run_id=run_dir.name, failed_condition="ci_green")]
    env2 = _reeval_env(tmp_path, env1, pr_number=416, head_ref=branch, head_oid=head_oid, comments=comments)
    r = _run_reeval(47, 416, env2)
    assert r.returncode == 3
    assert "RE-EVALUATE REFUSED" in r.stderr and "malformed_record" in r.stderr and head_oid in r.stderr
    _no_writes(tmp_path, run_dir)
