"""Acceptance tests for issue #38 — Autonomous merge: arming, shadow completion, sentinel, squash.

Derived from the issue's acceptance criteria (the spec), NOT the implementation internals. Two layers:

* End-to-end on the stubbed runner (`tools/dev-runner.sh`). The base `gh`/`claude`/check stubs live in
  `test_dev_runner.py`; this module reuses the low-level fixtures (git repo, issue/item JSON, timeline
  parsing) and swaps in an EXTENDED `gh` stub that additionally serves `pr merge` (recording `--squash`),
  `pr list` (canned prior-PR merge records for shadow completion), and `pr view --json mergeCommit`.
  `main` history is real git in the throwaway repo, so revert detection and freshness are exercised for
  real. These prove the *behaviours*: an armed all-pass PR is squash-merged with a durable `YR-MERGE:
  MERGED` record and no `In Review`; `auto_merge` read from the base ref tip; shadow-incomplete refuses to
  honour arming; the sentinel refuses globally; an armed failed condition Blocks; a moved `main` rebases +
  re-greens (or Blocks on conflict); a merge-API error is environmental; an unranked env override never
  merges; and promotion-to-Ready never happens.
* Unit tests on `tools/merge_shadow.py shadow-complete` over canned records — the mechanical N=5/K=3
  unified-window algorithm: successes arm, an overridden WOULD-BLOCK / a reverted MERGED / a malformed or
  machinery-error record resets, and clean armed MERGED records keep the window complete.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json, os, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # reuse the stubbed-runner fixtures (git repo, issue JSON, timeline)

ROOT = td.ROOT
RUNNER = td.RUNNER
READABLE_IDS = td.READABLE_IDS
MERGE_SHADOW = ROOT / "tools" / "merge_shadow.py"
CR_OK, CR_FAIL, CR_INFLIGHT = td.CR_OK, td.CR_FAIL, td.CR_INFLIGHT
EMDASH = "—"

def _stubs(binp):
    binp.mkdir(parents=True, exist_ok=True)
    td._exec(binp / "gh", td.GH_STUB)
    td._exec(binp / "claude", td.CLAUDE_STUB)
    td._exec(binp / "check.sh", td.CHECK_STUB)


def _run(args, env, cwd=None):
    full = {**os.environ, **READABLE_IDS, **env}
    return subprocess.run(["bash", str(RUNNER), *args], capture_output=True, text=True,
                          env=full, cwd=str(cwd or ROOT), timeout=120)


# ---- canned prior-PR merge records (for shadow completion) ----------------------------------------
# A PR's merge record is the fenced ```yr-merge-record JSON in its last YR-MERGE(-SHADOW) comment. These
# are hand-built to the versioned schema so the tester stays independent of how the runner renders them.

def _rec_comment(decision, *, machinery_ok=True, merge_commit=None, malformed=False):
    if malformed:
        block = "{ this is not valid json"
    else:
        d = {"schema": "yr-merge-record/1", "decision": decision, "machinery_ok": machinery_ok}
        if merge_commit is not None:
            d["merge_commit"] = merge_commit
        block = json.dumps(d)
    prefix = "YR-MERGE" if decision in ("MERGED", "BLOCKED") else "YR-MERGE-SHADOW"
    return {"body": f"{prefix}: {decision}\n\n```yr-merge-record\n{block}\n```\n"}


def _pr(number, decision, *, state="MERGED", oid=None, merge_commit=None,
        machinery_ok=True, malformed=False):
    return {"number": number, "state": state,
            "mergeCommit": ({"oid": oid} if oid else None),
            "comments": [_rec_comment(decision, machinery_ok=machinery_ok,
                                      merge_commit=merge_commit, malformed=malformed)]}


def _complete_prs():
    """Three clean landed successes (a mix of human-merged WOULD-MERGE and factory MERGED) — a window
    that satisfies K=3, none reverted. Numbered above the current PR (#1 from the stub URL)."""
    return [
        _pr(20, "WOULD-MERGE", oid="a" * 40),
        _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
        _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40),
    ]


# ---- env builders / accessors ---------------------------------------------------------------------

def _armed_env(tmp, binp, work, origin, *, number=5, title="Armed merge", body=None,
               checks=(CR_OK,), prs=None, auto_merge="true", extra=None):
    kw = {"number": number, "title": title}
    if body is not None:
        kw["body"] = body
    env = td._real(tmp, td._env(tmp, binp, **kw), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp, list(checks))
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    env["MERGE_CI_TIMEOUT"] = "0"
    env["STUB_ORIGIN"] = str(origin)
    env["STUB_MERGECOMMIT_OID"] = "f" * 40
    if auto_merge is not None:
        env["MERGE_AUTO_MERGE"] = auto_merge
    if prs is not None:
        pf = tmp / "prs.json"
        pf.write_text(json.dumps(prs))
        env["STUB_PRS_JSON"] = str(pf)
    if extra:
        env.update(extra)
    return env


def _gh_calls(tmp):
    p = tmp / "gh_calls"
    return p.read_text() if p.exists() else ""


def _merge_record(tmp, number=5):
    files = list((tmp / "drhome" / "runs").glob(f"{number}-*/merge-record.md"))
    return files[0].read_text() if files else None


def _shadow_body(tmp, number=5):
    files = list((tmp / "drhome" / "runs").glob(f"{number}-*/merge-shadow.md"))
    return files[0].read_text() if files else None


def _block(body):
    return td._shadow_block(body)


def _merged_stub(tmp):
    """Was `gh pr merge ... --squash` invoked (i.e. did the factory actually merge)?"""
    calls = _gh_calls(tmp)
    return "MERGE " in calls and "--squash" in calls


def _blocked(tl):
    return any("REASONFIELD" in l and "Blocked" in l for l in td._edits(tl))


def _in_review(tl):
    return any(l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l for l in tl)


def _promoted_ready(tl):
    """The runner must NEVER set Status=Ready (the input gate is untouched, criterion 10)."""
    return any(l.startswith("EDIT") and "STATUSFIELD" in l and "Ready" in l for l in tl)


# ================= criterion 1 & 7: armed + all conditions pass -> factory squash-merge =============

def test_armed_all_conditions_squash_merges_with_durable_record(tmp_path):
    """Green+fresh CI, clean terminal approval, rank gate holds, auto_merge true, sentinel not thrown,
    shadow complete -> the factory squash-merges the PR itself: a durable YR-MERGE: MERGED record, the
    merge call carries --squash, and the branch is NOT parked at In Review (native close->Done finishes)."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout                        # a PR was opened
    assert _merged_stub(tmp_path)                                 # squash-merged BY THE FACTORY (--squash)
    body = _merge_record(tmp_path)
    assert body is not None, "no durable YR-MERGE record was written"
    assert body.splitlines()[0] == "YR-MERGE: MERGED"            # loud durable marker, exact
    rec = _block(body)
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["decision"] == "MERGED" and rec["mode"] == "armed" and rec["machinery_ok"] is True
    # criterion 7: the record NAMES verdict, build/review models+ranks, checks with SHAs, bundle, commit.
    assert rec["review_verdict"] == "VERDICT: APPROVE"
    assert rec["build"]["rank"] == 30 and rec["review"]["rank"] == 40      # sonnet(30) < opus(40)
    assert rec["bundle_sha256"] and len(rec["base_sha"]) == 40 and len(rec["head_sha"]) == 40
    assert rec["merge_commit"] == "f" * 40                        # the squash merge commit
    tl = td._timeline(tmp_path)
    assert not _in_review(tl)                                     # merge supersedes In Review
    assert not _blocked(tl)                                       # a clean merge is not Blocked
    assert not _promoted_ready(tl)                                # criterion 10: no promotion to Ready


def test_armed_merges_into_main_only(tmp_path):
    """The squash-merge targets `main` (the PR base), never a deploy/release branch (criterion 7)."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path)
    assert "--base main" in _gh_calls(tmp_path)                   # PR opened against main; merge lands there


# ================= criterion 2: auto_merge read from the base ref current tip, not start-of-run =====

def test_armed_reads_auto_merge_from_base_ref_tip_not_working_tree(tmp_path):
    """auto_merge is honoured from origin/main's CURRENT tip at decision time: the manifest lives ONLY on
    the ref (the base checkout's working tree has drifted behind and no longer has it), and the factory
    still arms and merges. Proves the decision reads the ref, never a mutable/stale working-tree copy."""
    work, origin = td._make_repo(tmp_path)
    (work / ".yr" / "factory.toml").write_text("auto_merge = true\n")
    td._git(["add", "-A"], work); td._git(["commit", "-q", "-m", "arm the repo"], work)
    td._git(["push", "-q", "origin", "main"], work)
    td._git(["reset", "--hard", "HEAD~1"], work)                  # working tree drifts: manifest gone locally
    # the seed's bare (key-less) manifest is what's left locally — present (never un-onboarded), but it
    # does NOT carry auto_merge: proves the ref tip, not the stale working tree, is what arms the merge.
    assert "auto_merge" not in (work / ".yr" / "factory.toml").read_text()
    binp = tmp_path / "bin"; _stubs(binp)
    # auto_merge=None => do NOT set MERGE_AUTO_MERGE, so arming can only come from the ref manifest.
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(), auto_merge=None)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path)                                 # armed & merged purely off the ref tip
    assert _merge_record(tmp_path).splitlines()[0] == "YR-MERGE: MERGED"


# ================= criterion 3 & 4: shadow-incomplete refuses to honor auto_merge ===================

def test_armed_but_shadow_incomplete_refuses_to_honor(tmp_path):
    """auto_merge is true and every merge condition passes, but the repo has not completed shadow (only 2
    landed successes) -> the factory REFUSES to honor auto_merge: it posts a loud
    'YR-MERGE-SHADOW: WOULD-MERGE — armed, shadow-incomplete n/5' record, does NOT merge, and stops for
    the human at In Review — not a Blocked outcome."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    prs = [_pr(20, "WOULD-MERGE", oid="a" * 40), _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40)]
    env = _armed_env(tmp_path, binp, work, origin, prs=prs)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                            # arming refused: no factory merge
    body = _shadow_body(tmp_path)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith("YR-MERGE-SHADOW: WOULD-MERGE")      # shadow marker, not YR-MERGE (armed)
    assert "armed, shadow-incomplete 2/5" in first              # exact grammar incl the n/5 progress
    rec = _block(body)
    assert rec["decision"] == "WOULD-MERGE" and rec["mode"] == "shadow"
    assert rec["shadow_complete"] is False
    tl = td._timeline(tmp_path)
    assert _in_review(tl) and not _blocked(tl)                  # normal shadow stop, not Blocked


def test_armed_reverted_factory_merge_returns_repo_to_shadow(tmp_path):
    """A human revert of a prior factory MERGED breaks the window (revert detected in `main` history):
    the armed repo automatically returns to shadow and refuses to honor auto_merge, even though the
    current PR's own conditions all pass. Proves completion is recomputed from records + main history."""
    work, origin = td._make_repo(tmp_path)
    reverted_oid = "d" * 40
    # A revert of PR #20's merge commit lands on main BEFORE this run (so main's tip is stable => fresh).
    td._git(["commit", "--allow-empty", "-q", "-m",
             f"Revert the thing\n\nThis reverts commit {reverted_oid}."], work)
    td._git(["push", "-q", "origin", "main"], work)
    binp = tmp_path / "bin"; _stubs(binp)
    prs = [
        _pr(20, "MERGED", oid=reverted_oid, merge_commit=reverted_oid),   # reverted -> reset
        _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
        _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40),
    ]
    env = _armed_env(tmp_path, binp, work, origin, prs=prs)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                           # returned to shadow: no factory merge
    body = _shadow_body(tmp_path)
    assert body is not None and "armed, shadow-incomplete" in body.splitlines()[0]
    assert _block(body)["shadow_complete"] is False
    assert not _blocked(td._timeline(tmp_path))                 # shadow, not Blocked


# ================= criterion 6: the host sentinel refuses the merge globally ========================

def test_armed_sentinel_thrown_blocks_the_merge(tmp_path):
    """A sentinel FILE present in the dispatch home at decision time refuses the merge for the very next
    decision (no git round-trip): YR-MERGE: BLOCKED — sentinel, Reason=Blocked, and no merge — even
    though every other condition passes and shadow is complete."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    drhome = tmp_path / "drhome"; drhome.mkdir(parents=True, exist_ok=True)
    (drhome / "merge-killswitch").write_text("stop\n")           # the sentinel is thrown
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                           # the merge is refused globally
    body = _merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} sentinel"
    assert _block(body)["failed_condition"] == "sentinel"
    assert _blocked(td._timeline(tmp_path))                     # Reason=Blocked set


# ================= criterion 8 (block): any failed condition for an armed repo -> BLOCKED ============

def test_armed_failed_condition_blocks_and_sets_reason_blocked(tmp_path):
    """When a merge condition fails for an armed, shadow-complete repo (here CI is red), the factory
    posts 'YR-MERGE: BLOCKED — <condition>' and sets Reason=Blocked (distinct from the normal shadow
    stop). No merge happens."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, checks=(CR_OK, CR_FAIL), prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    body = _merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} ci_green"
    rec = _block(body)
    assert rec["decision"] == "BLOCKED" and rec["mode"] == "armed"
    assert rec["failed_condition"] == "ci_green"
    assert _blocked(td._timeline(tmp_path))                     # Reason=Blocked


def test_armed_unranked_env_override_never_auto_merges(tmp_path):
    """An operator env override that names a raw, unregistered build id runs UNRANKED — it clears intake
    but can never satisfy the rank gate (review-rank >= build-rank requires both entries ranked; issue
    #139's relaxation to >= only widens which RANKED pairs pass), so an armed repo with it never
    auto-merges (it BLOCKS on rank_gate instead of merging)."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(),
                     extra={"BUILD_MODEL": "some-unregistered-model-x"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                           # the core assertion: never auto-merges
    body = _merge_record(tmp_path)
    assert body is not None and body.splitlines()[0].startswith("YR-MERGE: BLOCKED")
    assert _block(body)["failed_condition"] == "rank_gate"


# ================= criterion 8 (environmental): a merge-API error is environmental, resumable ========

def test_armed_merge_api_error_is_environmental_no_reset_no_block(tmp_path):
    """When the merge API itself errors while merging, it is classified environmental: NO durable record
    is posted, the run is NOT hard-Blocked and the streak is not reset (resumable), and it falls back to
    stopping for the human at In Review."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(),
                     extra={"STUB_MERGE_FAIL": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _merge_record(tmp_path) is None                      # no MERGED/BLOCKED record was written
    tl = td._timeline(tmp_path)
    assert not _blocked(tl)                                     # environmental != Blocked
    assert _in_review(tl)                                       # resumable: stops for the human
    assert "environmental" in r.stderr.lower() or "resumable" in r.stderr.lower()


# ================= criterion 5: a moved main triggers rebase + re-green before merge =================

# A check-gate stub that ADVANCES origin/main exactly once (guarded by STUB_ADVANCE_MARKER) by cloning
# the origin, committing, and pushing — so the runner's decision-time freshness sees a moved main.
_ADVANCE_UNRELATED = r'''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -n "${STUB_ADVANCE_MARKER:-}" ] && [ ! -f "$STUB_ADVANCE_MARKER" ]; then
  : > "$STUB_ADVANCE_MARKER"
  wc="$(mktemp -d)"
  git clone -q "$STUB_ORIGIN" "$wc" >/dev/null 2>&1
  ( cd "$wc" && git config user.email t@t && git config user.name t \
    && printf 'unrelated\n' > OTHER.txt && git add -A \
    && git commit -q -m "advance main (no conflict)" && git push -q origin main ) >/dev/null 2>&1
fi
exit 0
'''

_ADVANCE_CONFLICT = r'''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -n "${STUB_ADVANCE_MARKER:-}" ] && [ ! -f "$STUB_ADVANCE_MARKER" ]; then
  : > "$STUB_ADVANCE_MARKER"
  wc="$(mktemp -d)"
  git clone -q "$STUB_ORIGIN" "$wc" >/dev/null 2>&1
  ( cd "$wc" && git config user.email t@t && git config user.name t \
    && printf 'main-side content\n' > feature.txt && git add -A \
    && git commit -q -m "advance main (touches feature.txt)" && git push -q origin main ) >/dev/null 2>&1
fi
exit 0
'''


def test_armed_moved_main_rebases_re_greens_then_merges(tmp_path):
    """main advances (non-conflicting) after the checks first passed. The factory rebases the branch onto
    the new tip, RE-RUNS the check gate (re-green) and re-waits CI, then squash-merges — a stale green is
    never merged straight through."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    adv = binp / "check_adv.sh"; td._exec(adv, _ADVANCE_UNRELATED)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(),
                     extra={"CHECK_CMD": f"bash {adv}", "STUB_ADVANCE_MARKER": str(tmp_path / "advanced")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path)                              # it merged, but only after remediation
    tl = td._timeline(tmp_path)
    assert tl.count("CHECK") >= 2                              # gate re-run on the rebased tree (re-green)
    assert _merge_record(tmp_path).splitlines()[0] == "YR-MERGE: MERGED"
    assert not _blocked(tl)


def test_armed_rebase_conflict_blocks_for_human(tmp_path):
    """When the rebase onto the moved tip CONFLICTS, the factory blocks for the human — Reason=Blocked,
    YR-MERGE: BLOCKED — freshness — and never merges a stale/unrebased PR."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    adv = binp / "check_adv.sh"; td._exec(adv, _ADVANCE_CONFLICT)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(),
                     extra={"CHECK_CMD": f"bash {adv}", "STUB_ADVANCE_MARKER": str(tmp_path / "advanced")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                          # a conflicting rebase never merges
    body = _merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} freshness"
    assert _blocked(td._timeline(tmp_path))


# ================= issue #240: an environmental failure AFTER freshness remediation has already =========
# force-pushed the branch can no longer be silently resumed the way every other terminal-step
# environmental failure is -- the PR's remote head no longer matches any local run's recorded base
# commit, so no named recovery lane (re-evaluation's base-commit match, the environmental-hold resume, a
# plain re-Ready re-dispatch) can locate or resume it. The runner must instead leave a fact-stating
# YR-MERGE: BLOCKED record that names the unrecoverable condition and routes to a rebuild -- never a
# silent no-record exit, and never a record that claims this state is resumable.

# A GIT_BIN wrapper that fails exactly once on the freshness-remediation's OWN force-with-lease push
# (simulating a network drop / lease race at that exact point) and passes every other git invocation
# straight through to the real binary -- so the remote is NEVER actually rewritten in this scenario.
_GIT_FAIL_FORCE_PUSH = r'''#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "--force-with-lease" ]; then
    if [ -n "${STUB_FAIL_FORCE_PUSH_MARKER:-}" ] && [ ! -f "${STUB_FAIL_FORCE_PUSH_MARKER}" ]; then
      : > "${STUB_FAIL_FORCE_PUSH_MARKER}"
      echo "simulated environmental failure on the freshness-remediation force-push" >&2
      exit 1
    fi
  fi
done
exec git "$@"
'''

# Like _ADVANCE_UNRELATED, but the check gate only advances main + passes on its FIRST call (the pre-PR
# check gate); every SUBSEQUENT call (the post-rebase re-check inside rebase_onto_tip) fails with an
# environment exit code (126) -- simulating an environmental failure that lands only after the freshness
# remediation has already rebased AND force-pushed the branch onto the new base.
_ADVANCE_THEN_ENV_FAIL = r'''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -n "${STUB_ADVANCE_MARKER:-}" ] && [ ! -f "${STUB_ADVANCE_MARKER}" ]; then
  : > "${STUB_ADVANCE_MARKER}"
  wc="$(mktemp -d)"
  git clone -q "$STUB_ORIGIN" "$wc" >/dev/null 2>&1
  ( cd "$wc" && git config user.email t@t && git config user.name t \
    && printf 'unrelated\n' > OTHER.txt && git add -A \
    && git commit -q -m "advance main (no conflict)" && git push -q origin main ) >/dev/null 2>&1
  exit 0
fi
exit 126
'''


def test_armed_env_failure_after_force_push_posts_fact_stating_unrecoverable_block(tmp_path):
    """Acceptance (issue #240): once freshness remediation has rebased AND FORCE-PUSHED the branch onto
    main's moved tip, a LATER environmental failure in that same remediation (here: the post-rebase
    re-check gate crashes with an environment exit code) can no longer be silently resumed. Instead of the
    usual silent no-record exit, the runner leaves a fact-stating YR-MERGE: BLOCKED — unrecoverable
    record, sets Reason=Blocked, and its comment names the rebuild routing (close the PR, delete the
    branch, set the issue back to Ready) -- never a claim of resumability."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    adv = binp / "check_adv_then_fail.sh"; td._exec(adv, _ADVANCE_THEN_ENV_FAIL)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(),
                     extra={"CHECK_CMD": f"bash {adv}", "STUB_ADVANCE_MARKER": str(tmp_path / "advanced")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                        # never merges past an unrecoverable state
    body = _merge_record(tmp_path)
    assert body is not None, "an env failure past the force-push must leave a fact-stating record, not silence"
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} unrecoverable"
    rec = _block(body)
    assert rec["decision"] == "BLOCKED" and rec["mode"] == "armed" and rec["machinery_ok"] is True
    assert rec["failed_condition"] == "unrecoverable"
    tl = td._timeline(tmp_path)
    assert _blocked(tl)                                      # Reason=Blocked -- never left silently resumable
    # bullet 2: no lane may be told this is resumable -- the comment must instead route to a rebuild.
    comments = " ".join(td._comments(tl)).lower()
    assert "rebuild" in comments
    assert "ready" in comments                               # names setting the issue back to Ready
    assert "delete" in comments and "branch" in comments      # names deleting the stale branch


def test_armed_env_failure_before_force_push_stays_silently_resumable(tmp_path):
    """Regression companion (criterion 3: the rest of the merge evaluator is unchanged). An environmental
    failure BEFORE the freshness-remediation force-push actually lands -- here, the force-with-lease push
    itself fails -- is still the ordinary silently-resumable environmental case: no durable record, not
    Blocked, falls back to a plain In Review stop, exactly like every other pre-existing environmental
    terminal-step failure. Proves the new unrecoverable branch engages ONLY once the remote head has
    actually been rewritten, never before."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    adv = binp / "check_adv.sh"; td._exec(adv, _ADVANCE_UNRELATED)
    gitwrap = binp / "git-fail-force-push.sh"; td._exec(gitwrap, _GIT_FAIL_FORCE_PUSH)
    marker = tmp_path / "force-push-failed-once"
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(),
                     extra={"CHECK_CMD": f"bash {adv}", "STUB_ADVANCE_MARKER": str(tmp_path / "advanced"),
                            "GIT_BIN": str(gitwrap), "STUB_FAIL_FORCE_PUSH_MARKER": str(marker)})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    assert _merge_record(tmp_path) is None                   # silent -- no durable record at all
    tl = td._timeline(tmp_path)
    assert not _blocked(tl)                                  # environmental != Blocked
    assert _in_review(tl)                                    # resumable: stops for the human, same as before


# ================= criterion (human-merged otherwise): a non-armed repo just shadows =================

def test_not_armed_repo_stays_shadow_never_merges(tmp_path):
    """A repo that does NOT set auto_merge is never touched by the factory merge: all conditions pass but
    it only posts a shadow record and stops for the human (human-merged otherwise)."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, auto_merge="false")   # not armed
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)                          # never merged by the factory
    body = _shadow_body(tmp_path)
    assert body is not None and body.splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    tl = td._timeline(tmp_path)
    assert _in_review(tl) and not _blocked(tl) and not _promoted_ready(tl)


# ================= criterion 10: promotion to Ready is never automated ==============================

def test_no_promotion_to_ready_on_any_merge_run(tmp_path):
    """Across a full autonomous-merge run, the runner never sets Status=Ready — the input gate is
    untouched (it only ever claims In Progress, then merges or stops)."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _promoted_ready(td._timeline(tmp_path))


# ================= issue #206: ledger row at the armed-merge terminal branches =======================
# tools/ledger.py's `append` derives the row's outcome from the SAME terminal decision this whole module
# exercises: a factory MERGED lands type=merged/decision=MERGED; an armed_block (any failed condition,
# the sentinel, an unranked override) is PINNED as type=in-review/decision=BLOCKED — never a plain
# "blocked" outcome type (that belongs to fail_blocked's own build-failure branch) — and armed_block
# itself never appends, so exactly ONE row lands, at the shared terminus; a merge-API environmental
# failure inside terminal_step falls through to a plain in-review with no decision at all.

def test_ledger_row_on_armed_merged(tmp_path):
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _merged_stub(tmp_path)
    rows = td._ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "merged", "decision": "MERGED"}
    assert rows[0]["models"] == {"build": "claude-sonnet-5", "review": "claude-opus-4-8"}


def test_ledger_row_on_armed_blocked_pinned_as_in_review(tmp_path):
    """Acceptance: the armed-BLOCKED case is pinned as outcome.type in-review / outcome.decision
    BLOCKED, and armed_block itself appends nothing — this is the ONE row for the whole run."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, checks=(CR_OK, CR_FAIL), prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not _merged_stub(tmp_path)
    rows = td._ledger_rows(tmp_path)
    assert len(rows) == 1                       # armed_block itself never appends — only the terminus does
    assert rows[0]["outcome"] == {"type": "in-review", "decision": "BLOCKED"}


def test_ledger_row_on_sentinel_thrown_also_pinned_as_in_review_blocked(tmp_path):
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    drhome = tmp_path / "drhome"; drhome.mkdir(parents=True, exist_ok=True)
    (drhome / "merge-killswitch").write_text("stop\n")
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs())
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rows = td._ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "in-review", "decision": "BLOCKED"}


def test_ledger_row_on_armed_environmental_terminal_failure(tmp_path):
    """A merge-API error inside terminal_step is classified environmental (no durable record at all) —
    the ledger row still lands exactly once, at the shared terminus, as a plain in-review with no
    decision."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _armed_env(tmp_path, binp, work, origin, prs=_complete_prs(), extra={"STUB_MERGE_FAIL": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _merge_record(tmp_path) is None
    rows = td._ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "in-review", "decision": None}


# ================= criterion 4 (mechanics): shadow completion computed over canned records ==========
# Direct tests of `merge_shadow.py shadow-complete` — the unified N=5/K=3 window algorithm.

def _shadow_complete(tmp, prs, *, main_log="", repo="test/repo", window=5, need=3, exclude=""):
    pf = tmp / "prs.json"; pf.write_text(json.dumps(prs))
    mf = tmp / "main-log.txt"; mf.write_text(main_log)
    r = subprocess.run([sys.executable, str(MERGE_SHADOW), "shadow-complete",
                        "--prs-file", str(pf), "--main-log-file", str(mf), "--repo", repo,
                        "--exclude-pr", exclude, "--window", str(window), "--need", str(need)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    done, k, n = r.stdout.split()
    return done, int(k), int(n)


def _mainlog(*messages):
    return "".join(f"{'0' * 40}\x1e{m}\x00" for m in messages)


def test_shadow_complete_meets_nk_over_unified_window():
    """>=K=3 landed unreverted successes over the window (a mix of human-merged WOULD-MERGE and factory
    MERGED, unified in one window) with no reset -> complete."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(20, "WOULD-MERGE", oid="a" * 40),
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "WOULD-MERGE", oid="c" * 40)]
        done, k, n = _shadow_complete(tmp, prs)
        assert done == "true" and k == 3


def test_shadow_complete_below_k_is_incomplete():
    """Fewer than K successes -> incomplete, even with no reset."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(20, "WOULD-MERGE", oid="a" * 40), _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40)]
        done, k, n = _shadow_complete(tmp, prs)
        assert done == "false" and k == 2


def test_shadow_complete_overridden_would_block_resets():
    """A WOULD-BLOCK that a human merged anyway (an override) is a reset in the window -> incomplete,
    even though enough other successes exist."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(20, "WOULD-BLOCK", state="MERGED", oid="a" * 40),   # merged over a block => reset
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40),
               _pr(23, "MERGED", oid="e" * 40, merge_commit="e" * 40)]
        done, k, n = _shadow_complete(tmp, prs)
        assert done == "false"


def test_shadow_complete_reverted_factory_merge_resets():
    """A factory MERGED whose merge commit was reverted in `main` history is a reset -> incomplete."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        reverted = "a" * 40
        prs = [_pr(20, "MERGED", oid=reverted, merge_commit=reverted),
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40)]
        done, k, n = _shadow_complete(tmp, prs, main_log=_mainlog(f"This reverts commit {reverted}"))
        assert done == "false"


def test_shadow_complete_malformed_record_resets():
    """A malformed record block in the window is a reset -> incomplete."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(20, "MERGED", oid="a" * 40, merge_commit="a" * 40, malformed=True),
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40)]
        done, k, n = _shadow_complete(tmp, prs)
        assert done == "false"


def test_shadow_complete_machinery_error_resets():
    """A machinery-error record (machinery_ok=false) in the window is a reset -> incomplete."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(20, "MERGED", oid="a" * 40, merge_commit="a" * 40, machinery_ok=False),
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40)]
        done, k, n = _shadow_complete(tmp, prs)
        assert done == "false"


def test_shadow_complete_clean_armed_merges_keep_window_complete():
    """Clean factory MERGED records (unreverted) count as successes and keep the window complete — no
    flip-flop back to shadow after arming."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(20, "MERGED", oid="a" * 40, merge_commit="a" * 40),
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40)]
        # A revert of an UNRELATED commit must not touch these.
        done, k, n = _shadow_complete(tmp, prs, main_log=_mainlog("This reverts commit " + "9" * 40))
        assert done == "true" and k == 3


def test_shadow_complete_current_pr_excluded_from_window():
    """The current PR is excluded from its own completion window."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        prs = [_pr(1, "WOULD-MERGE", state="OPEN"),               # the current PR (open, no landing)
               _pr(20, "MERGED", oid="a" * 40, merge_commit="a" * 40),
               _pr(21, "MERGED", oid="b" * 40, merge_commit="b" * 40),
               _pr(22, "MERGED", oid="c" * 40, merge_commit="c" * 40)]
        done, k, n = _shadow_complete(tmp, prs, exclude="1")
        assert done == "true" and k == 3 and n == 3              # only the 3 prior records form the window


# ================= criterion 11: docs describe the factory-executed output gate + sentinel ===========

def test_agents_md_describes_factory_executed_output_gate():
    text = (ROOT / "AGENTS.md").read_text().lower()
    assert "factory-executed" in text                            # the output gate is factory-executed...
    assert "armed" in text and "auto_merge" in text
    assert "human-merged" in text                                # ...for armed repos, human-merged otherwise


def test_dispatch_md_documents_the_sentinel_kill_switch():
    text = (ROOT / "deploy" / "DISPATCH.md").read_text().lower()
    assert "sentinel" in text and "merge-killswitch" in text     # the sentinel file is documented
    assert "auto_merge" in text
