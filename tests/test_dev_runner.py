"""Unit tests for tools/dev-runner.sh — stubbed, no live LLM and no network.

Lifecycle state lives on the native Projects Status/Reason fields. The `gh` stub serves `issue view`
and `project item-list` from canned JSON and records `project item-edit`/`issue comment` to a shared
timeline. The `claude` stub is STAGE-AWARE (implement / test / repair, detected from its argv) and the
CHECK_CMD is a stub script — both append to the timeline, so tests can prove the order
claim → IMPL → TEST → CHECK → (REPAIR → CHECK) → In Review, and that the check gate is deterministic.
Field/option ids are overridden to readable strings (STATUSFIELD, InProgress, …) for legible assertions.
"""
import json, os, stat, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "dev-runner.sh"

GH_STUB = '''#!/usr/bin/env bash
case "$1" in
  repo) echo "test/repo" ;;
  issue)
    case "$2" in
      view)    cat "$STUB_ISSUE_JSON" ;;
      comment) printf 'COMMENT %s\\n' "$*" >> "$STUB_TIMELINE" ;;
      *)       echo "unhandled issue $2" >&2; exit 9 ;;
    esac ;;
  project)
    case "$2" in
      item-list) [ -n "${STUB_ITEMLIST_FAIL:-}" ] && exit 4 || cat "$STUB_ITEM_JSON" ;;
      item-edit) printf 'EDIT %s\\n' "$*" >> "$STUB_TIMELINE" ;;
      *)         echo "unhandled project $2" >&2; exit 9 ;;
    esac ;;
  pr) case "$2" in
        comment) echo PRCOMMENT >> "$STUB_TIMELINE" ;;
        *)       printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1" ;;
      esac ;;
  *)  echo "unhandled gh $*" >&2; exit 9 ;;
esac
'''
# stage-aware: REVIEWER role -> reviewer (emits VERDICT); "REQUESTED CHANGES" -> review-repair;
# TESTER role -> tester; "tests FAIL" -> check-repair; otherwise implementer.
# Tester file-writing is controlled by separate env vars (STUB_TESTER_PROD_CHANGE /
# STUB_TESTER_TEST_CHANGE) so the boundary guard can be exercised independently of the
# implementer's STUB_CLAUDE_CHANGE, and the happy-path tests don't inadvertently violate
# the boundary by writing a prod file from the tester stage.
CLAUDE_STUB = '''#!/usr/bin/env bash
args="$*"
[ -n "${STUB_CLAUDE_ARGV:-}" ] && printf '%s\\n' "$@" > "$STUB_CLAUDE_ARGV"
case "$args" in
  *REVIEWER*)            echo REVIEW >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REVIEW_VERDICT:-}" ]; then printf '%s\\n' "$STUB_REVIEW_VERDICT"
                        elif [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then echo "VERDICT: REQUEST_CHANGES"
                        else echo "VERDICT: APPROVE"; fi ;;
  *"REQUESTED CHANGES"*) echo REVIEWFIX >> "$STUB_TIMELINE"; [ -n "${STUB_REVIEWFIX_CRASH:-}" ] && exit 7; [ -z "${STUB_REVIEW_NOFIX:-}" ] && : > review_repaired ;;
  *TESTER*)             echo TEST   >> "$STUB_TIMELINE"
                        [ -n "${STUB_TESTER_PROD_CHANGE:-}" ] && printf 'by tester\\n' > tester_prod.txt
                        [ -n "${STUB_TESTER_TEST_CHANGE:-}" ] && { mkdir -p tests && printf 'pass\\n' > tests/test_stub_output.py; } ;;
  *"tests FAIL"*)       echo REPAIR >> "$STUB_TIMELINE"; [ -z "${STUB_REPAIR_NOFIX:-}" ] && : > repaired ;;
  *)                    echo IMPL   >> "$STUB_TIMELINE"; [ -n "${STUB_CLAUDE_CHANGE:-}" ] && printf 'hello\\n' > feature.txt ;;
esac
exit 0
'''
# check gate stub (runs with cwd = worktree): pass, unless STUB_CHECK_FAIL and no 'repaired' marker yet.
CHECK_STUB = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -n "${STUB_CHECK_FAIL:-}" ] && [ ! -f repaired ]; then exit 1; fi
exit 0
'''

READABLE_IDS = {
    "PROJECT_ID": "PROJ", "STATUS_FIELD_ID": "STATUSFIELD", "REASON_FIELD_ID": "REASONFIELD",
    "OPT_BACKLOG": "Backlog", "OPT_READY": "Ready", "OPT_INPROGRESS": "InProgress",
    "OPT_INREVIEW": "InReview", "OPT_DONE": "Done", "OPT_NEEDSINFO": "NeedsInfo", "OPT_BLOCKED": "Blocked",
}


def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _stubs(binp):
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "gh", GH_STUB)
    _exec(binp / "claude", CLAUDE_STUB)
    _exec(binp / "check.sh", CHECK_STUB)


def _issue(tmp, *, number=7, title="Do a thing", body="### Acceptance criteria\n- [ ] it works\n", state="OPEN"):
    p = tmp / "issue.json"
    p.write_text(json.dumps({"number": number, "title": title, "state": state, "body": body}))
    return p


def _item(tmp, *, number=7, status="Ready", item_id="ITEM1", in_project=True):
    p = tmp / "item.json"
    items = [{"id": item_id, "status": status, "content": {"number": number}}] if in_project else []
    p.write_text(json.dumps({"items": items}))
    return p


def _run(args, env_extra, cwd=None):
    env = {**os.environ, **READABLE_IDS, **env_extra}
    return subprocess.run(["bash", str(RUNNER), *args],
                          capture_output=True, text=True, env=env, cwd=str(cwd or ROOT))


def _base_env(tmp, issue_json, item_json, binp):
    return {
        "GH_BIN": str(binp / "gh"), "CLAUDE_BIN": str(binp / "claude"),
        "CHECK_CMD": f"bash {binp / 'check.sh'}",
        "STUB_ISSUE_JSON": str(issue_json), "STUB_ITEM_JSON": str(item_json),
        "STUB_TIMELINE": str(tmp / "timeline"), "STUB_GH_CALLS": str(tmp / "gh_calls"),
        "STUB_CLAUDE_ARGV": str(tmp / "claude_argv"),
    }


def _env(tmp, binp, **kw):
    num = kw.pop("number", 7); status = kw.pop("status", "Ready"); in_project = kw.pop("in_project", True)
    ij = _issue(tmp, number=num, **kw)
    it = _item(tmp, number=num, status=status, in_project=in_project)
    return _base_env(tmp, ij, it, binp)


def _timeline(tmp):
    p = tmp / "timeline"
    return p.read_text().splitlines() if p.exists() else []


def _edits(tl):    return [l for l in tl if l.startswith("EDIT")]
def _comments(tl): return [l for l in tl if l.startswith("COMMENT")]
def _ran(tl):      return any(m in tl for m in ("IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX"))


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _make_repo(tmp):
    origin = tmp / "origin.git"; origin.mkdir()
    _git(["init", "--bare", "-b", "main", "."], origin)
    work = tmp / "work"; work.mkdir()
    _git(["init", "-b", "main", "."], work)
    _git(["config", "user.email", "t@t"], work); _git(["config", "user.name", "tester"], work)
    (work / "README.md").write_text("seed\n")
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "seed"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "origin", "main"], work)
    return work, origin


def _real(tmp, env, work):
    env.update({"GIT_BIN": "git", "BASE_REF": "origin/main",
                "BASE_REPO": str(work), "DEV_RUNNER_HOME": str(tmp / "drhome")})
    return env


# ============ DoR gate: refuse before any work, no stages, no writes ============

def test_gate_rejects_closed(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, state="CLOSED"))
    assert r.returncode == 3 and "not open" in r.stderr.lower()
    tl = _timeline(tmp_path); assert not _ran(tl) and not _edits(tl)


def test_gate_rejects_not_in_project(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, in_project=False))
    assert r.returncode == 3 and "not in project" in r.stderr.lower()
    assert not _ran(_timeline(tmp_path))


def test_gate_rejects_not_ready(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, status="Backlog"))
    assert r.returncode == 3 and "not ready" in r.stderr.lower()
    assert not _ran(_timeline(tmp_path))


def test_project_query_failure_is_clear(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["STUB_ITEMLIST_FAIL"] = "1"
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 1 and "project" in r.stderr.lower()
    assert not _ran(_timeline(tmp_path))


# ============ needs-info / dry-run ============

def test_needs_info_on_empty_criteria(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, body="### Goal\njust do it\n"))
    assert r.returncode == 3
    tl = _timeline(tmp_path); assert not _ran(tl)
    edit = " ".join(_edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit and _comments(tl)


def test_dryrun_runs_no_stages_and_writes_nothing(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], _env(tmp_path, binp))
    assert r.returncode == 0
    tl = _timeline(tmp_path)
    assert not _ran(tl) and "CHECK" not in tl and not _edits(tl) and not _comments(tl)


def test_dryrun_model_override_opus(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo", "--dry-run"],
             _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\n"))
    assert json.loads(r.stdout)["model"] == "claude-opus-4-8"


def test_unknown_model_override_real_bounces_needs_info(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"],
             _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: gpt-4\n"))
    assert r.returncode == 3
    tl = _timeline(tmp_path); assert not _ran(tl)
    assert "NeedsInfo" in " ".join(_edits(tl)) and _comments(tl)


# ============ full pass: claim -> implement -> tester -> check -> In Review ============

def test_happy_path_implement_then_test_then_check(tmp_path):
    work, origin = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Add greeting helper"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert "Closes #5" in (tmp_path / "gh_calls").read_text()
    tl = _timeline(tmp_path)
    # order: claim -> implement -> tester -> check -> review -> In Review
    claim_i = next(i for i, l in enumerate(tl) if l.startswith("EDIT") and "STATUSFIELD" in l and "InProgress" in l)
    inrev_i = next(i for i, l in enumerate(tl) if l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l)
    assert claim_i < tl.index("IMPL") < tl.index("TEST") < tl.index("CHECK") < tl.index("REVIEW") < inrev_i
    assert "PRCOMMENT" in tl                      # reviewer verdict attached to the PR
    # the implement-stage safety contract still reaches the real claude invocation
    argv = (tmp_path / "claude_argv").read_text().splitlines()
    assert "--permission-mode" in argv and "bypassPermissions" in argv and "--model" in argv


def test_check_fail_then_repair_passes(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Needs a repair"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1"})  # check fails until repair writes 'repaired'
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = _timeline(tmp_path)
    assert "REPAIR" in tl                       # one repair attempt fired
    assert tl.count("CHECK") == 2               # failed once, passed after repair


def test_check_fail_unrepaired_blocks(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Cannot fix"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REPAIR_NOFIX": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "checks still failing" in r.stderr.lower()
    tl = _timeline(tmp_path)
    assert "REPAIR" in tl                        # it tried once
    assert "REASONFIELD" in " ".join(_edits(tl)) and "Blocked" in " ".join(_edits(tl))
    assert "https://stub/pr/1" not in r.stdout   # no PR


def test_no_change_blocks(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Produces nothing"), work)  # no STUB_CLAUDE_CHANGE
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "no changes" in r.stderr.lower()
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))


def test_runner_prompts_contain_stub_markers():
    """Guard: the stage-aware claude stub classifies by the literals 'TESTER' and 'tests FAIL'.
    If the runner's prompts drop them the stub would silently misclassify, so fail loudly here."""
    src = RUNNER.read_text()
    assert "TESTER" in src and "REVIEWER" in src             # tester / reviewer role markers
    assert "tests FAIL" in src and "REQUESTED CHANGES" in src  # check-repair / review-repair markers


def test_review_block_then_approve(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Needs review fix"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1"})  # reviewer blocks until a repair
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = _timeline(tmp_path)
    assert "REVIEWFIX" in tl                       # one review-repair fired
    assert tl.count("REVIEW") == 2                 # blocked once, approved after repair


def test_review_still_blocks_after_repair(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Unfixable review"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEW_NOFIX": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "still requests changes" in r.stderr.lower()
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))
    assert "https://stub/pr/1" not in r.stdout     # no PR


def test_hedged_verdict_blocks(tmp_path):
    """A verdict whose LAST line is REQUEST_CHANGES (approve then changes) must NOT ship."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Hedged"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_VERDICT": "VERDICT: APPROVE\nVERDICT: REQUEST_CHANGES"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "https://stub/pr/1" not in r.stdout
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))


def test_trailing_junk_verdict_blocks(tmp_path):
    """'VERDICT: APPROVE' followed by trailing junk is not an exact approve → must NOT ship."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Junk verdict"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_VERDICT": "VERDICT: APPROVE -- jk it has blockers"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "https://stub/pr/1" not in r.stdout


def test_mangled_verdict_token_blocks(tmp_path):
    """A space-fractured token ('VERDICT: APP ROVE') is not an exact approve → must NOT ship."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Mangled token"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_VERDICT": "VERDICT: APP ROVE"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "https://stub/pr/1" not in r.stdout


def test_review_repair_crash_still_blocks(tmp_path):
    """A crash in the review-repair stage must end in Blocked (fail_blocked), not a raw exit/strand."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Repair crashes"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEWFIX_CRASH": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))   # fail_blocked ran, not a raw crash
    assert "https://stub/pr/1" not in r.stdout


def test_rerun_after_failure_not_wedged(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=9, title="Retry me"), work)
    r1 = _run(["9", "--repo", "test/repo"], env)
    assert r1.returncode != 0
    r2 = _run(["9", "--repo", "test/repo"], {**env, "STUB_CLAUDE_CHANGE": "1"})
    assert r2.returncode == 0, r2.stderr
    assert "https://stub/pr/1" in r2.stdout


# ============ tester boundary guard (builder != verifier, confinement principle) ============

def test_tester_boundary_guard_blocks_prod_file(tmp_path):
    """Tester writing any file outside tests/** must set Reason=Blocked, comment the filename, open no PR."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Boundary guard prod"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_PROD_CHANGE": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "TEST" in tl                                              # tester stage ran
    edits = " ".join(_edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits             # Reason=Blocked set
    comments = " ".join(_comments(tl))
    assert "tester_prod.txt" in comments                             # offending file named in comment
    assert "https://stub/pr/1" not in r.stdout                       # no PR opened
    diffs = list((tmp_path / "drhome" / "runs").glob("5-*/boundary-violation.diff"))
    assert diffs and "tester_prod.txt" in diffs[0].read_text()       # offending change preserved for diagnosis


def test_tester_boundary_guard_allows_test_files(tmp_path):
    """Tester writing only files under tests/** must proceed normally through check/review to a PR."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Boundary guard tests dir"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "TEST" in tl and "CHECK" in tl and "REVIEW" in tl        # all stages proceeded
    assert "https://stub/pr/1" in r.stdout                          # PR opened


def test_tester_boundary_guard_checkpoint_is_after_implementer(tmp_path):
    """Checkpoint is taken after the implementer: files the implementer wrote must not be flagged,
    only files the tester added after the checkpoint are offenders."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Checkpoint timing"), work)
    # implementer writes feature.txt (captured in IMPL_TREE); tester then adds tester_prod.txt.
    # The guard's diff (IMPL_TREE -> TESTER_TREE) must flag tester_prod.txt but NOT feature.txt.
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_PROD_CHANGE": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    comments = " ".join(_comments(_timeline(tmp_path)))
    assert "tester_prod.txt" in comments     # tester's new file IS flagged
    assert "feature.txt" not in comments     # implementer's file is NOT flagged (already in checkpoint)


# ============ Step B: repo-agnostic routing (workspace anchor + per-repo manifest) ============
# These exercise resolution/precedence via --dry-run, which reports the resolved config and exits
# before any git op — so no real repo is ever touched.

def _manifest_repo(tmp, *, check_cmd=None, model=None, base_ref=None, name="repo"):
    """A minimal repo dir carrying a .yr/factory.toml (no git needed — dry-run never touches git)."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    lines = []
    if check_cmd is not None: lines.append(f'check_cmd = "{check_cmd}"')
    if model is not None:     lines.append(f'model = "{model}"')
    if base_ref is not None:  lines.append(f'base_ref = "{base_ref}"')
    (repo / ".yr" / "factory.toml").write_text("\n".join(lines) + "\n")
    return repo


def test_dryrun_reports_workspace_default(tmp_path):
    """With no YR_WORKSPACE, the workspace is discovered relative to the script (factory/../..)."""
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], _env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["workspace"] == str(ROOT.parent)


def test_dryrun_resolves_base_repo_from_workspace(tmp_path):
    """The target repo's checkout is resolved as $YR_WORKSPACE/<name> when BASE_REPO is unset."""
    ws = tmp_path / "ws"; ws.mkdir()
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["YR_WORKSPACE"] = str(ws)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["base_repo"] == str(ws / "repo")


def test_dryrun_check_cmd_from_manifest(tmp_path):
    """A repo's .yr/factory.toml check_cmd is used when CHECK_CMD is not set in the env."""
    repo = _manifest_repo(tmp_path, check_cmd="make test")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo); del env["CHECK_CMD"]
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["check_cmd"] == "make test"


def test_dryrun_env_check_cmd_overrides_manifest(tmp_path):
    """Explicit CHECK_CMD in the env wins over the manifest (env > manifest > default)."""
    repo = _manifest_repo(tmp_path, check_cmd="make test")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_CMD"] = "pytest -q"
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["check_cmd"] == "pytest -q"


def test_dryrun_model_from_manifest(tmp_path):
    """A repo's manifest model sets the default tier (opus -> claude-opus-4-8)."""
    repo = _manifest_repo(tmp_path, model="opus")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["model"] == "claude-opus-4-8"


def test_dryrun_body_model_overrides_manifest(tmp_path):
    """The issue body `model:` override still wins over the manifest default."""
    repo = _manifest_repo(tmp_path, model="opus")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: sonnet\n")
    env["BASE_REPO"] = str(repo)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["model"] == "claude-sonnet-4-6"


def test_dryrun_base_ref_from_manifest(tmp_path):
    """A repo's manifest base_ref is used when BASE_REF is not set in the env."""
    repo = _manifest_repo(tmp_path, base_ref="origin/develop")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["base_ref"] == "origin/develop"


def test_check_runs_with_base_repo_venv_on_path(tmp_path):
    """The check runs with the base repo's .venv/bin on PATH, so a manifest can name bare tools
    (`pytest`) instead of a relative .venv path the ephemeral worktree doesn't contain."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    # a fake `pytest` that lives ONLY in the base repo's venv; it records that it ran, then passes.
    venvbin = work / ".venv" / "bin"; venvbin.mkdir(parents=True)
    marker = tmp_path / "base_pytest_ran"
    _exec(venvbin / "pytest", f'#!/usr/bin/env bash\n: > "{marker}"\nexit 0\n')
    (work / ".yr").mkdir(); (work / ".yr" / "factory.toml").write_text('check_cmd = "pytest tests/ -q"\n')
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Base venv on PATH"), work)
    del env["CHECK_CMD"]                 # fall back to the manifest's bare `pytest`
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert marker.exists()              # the base repo's venv pytest was found on PATH and ran
