"""Unit tests for tools/dev-runner.sh — stubbed, no live LLM and no network.

Lifecycle state lives on the native Projects Status/Reason fields. The `gh` stub serves `issue view`
and `project item-list` from canned JSON and records `project item-edit`/`issue comment` to a shared
timeline. The `claude` stub is STAGE-AWARE (implement / test / repair, detected from its argv) and the
CHECK_CMD is a stub script — both append to the timeline, so tests can prove the order
claim → IMPL → TEST → CHECK → (REPAIR → CHECK) → In Review, and that the check gate is deterministic.
Field/option ids are overridden to readable strings (STATUSFIELD, InProgress, …) for legible assertions.
"""
import json, os, re, stat, subprocess, pathlib

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
        view)    if [ -n "${STUB_PRVIEW_FAIL:-}" ]; then echo "pr view failed (stub env failure)" >&2; exit 5; fi
                 if [ -n "${STUB_ROLLUP_JSON:-}" ]; then cat "$STUB_ROLLUP_JSON"
                 else printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1"; fi ;;
        comment) echo PRCOMMENT >> "$STUB_TIMELINE"
                 if [ -n "${STUB_PRCOMMENTS:-}" ]; then
                   __p=""; __bf=""
                   for __a in "$@"; do [ "$__p" = "--body-file" ] && __bf="$__a"; __p="$__a"; done
                   [ -n "$__bf" ] && { echo "=== PRCOMMENT ==="; cat "$__bf"; } >> "$STUB_PRCOMMENTS"
                 fi ;;
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
[ -n "${STUB_CLAUDE_ENV_FILE:-}" ] && printf 'CLAUDE_CONFIG_DIR=%s\\n' "${CLAUDE_CONFIG_DIR:-}" >> "$STUB_CLAUDE_ENV_FILE"
case "$args" in
  *REVIEWER*)            echo REVIEW >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REVIEW_QUOTA:-}" ]; then echo "${STUB_REVIEW_QUOTA}" >&2; exit 1; fi
                        if [ -n "${STUB_REVIEW_VERDICT:-}" ]; then printf '%s\\n' "$STUB_REVIEW_VERDICT"
                        elif [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then echo "VERDICT: REQUEST_CHANGES"
                        else echo "VERDICT: APPROVE"; fi ;;
  *"REQUESTED CHANGES"*) echo REVIEWFIX >> "$STUB_TIMELINE"; [ -n "${STUB_REVIEWFIX_CRASH:-}" ] && exit 7; [ -z "${STUB_REVIEW_NOFIX:-}" ] && : > review_repaired ;;
  *TESTER*)             echo TEST   >> "$STUB_TIMELINE"
                        if [ -n "${STUB_TESTER_QUOTA:-}" ]; then echo "${STUB_TESTER_QUOTA}" >&2; exit 1; fi
                        [ -n "${STUB_TESTER_PROD_CHANGE:-}" ] && printf 'by tester\\n' > tester_prod.txt
                        [ -n "${STUB_TESTER_TEST_CHANGE:-}" ] && { mkdir -p tests && printf 'pass\\n' > tests/test_stub_output.py; }
                        [ -n "${STUB_TESTER_ARTIFACT_CHANGE:-}" ] && { mkdir -p tools/__pycache__ && printf 'bytecode\\n' > tools/__pycache__/check.cpython-314.pyc; } ;;
  *"tests FAIL"*)       echo REPAIR >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REPAIR_QUOTA:-}" ]; then echo "${STUB_REPAIR_QUOTA}" >&2; exit 1; fi
                        [ -z "${STUB_REPAIR_NOFIX:-}" ] && : > repaired ;;
  *)                    echo IMPL   >> "$STUB_TIMELINE"
                        if [ -n "${STUB_IMPL_QUOTA:-}" ]; then echo "${STUB_IMPL_QUOTA}" >&2; exit 1; fi
                        if [ -n "${STUB_IMPL_FAIL:-}" ]; then echo "${STUB_IMPL_FAIL}" >&2; exit 1; fi
                        [ -n "${STUB_CLAUDE_CHANGE:-}" ] && printf 'hello\\n' > feature.txt ;;
esac
exit 0
'''
# check gate stub (runs with cwd = worktree): pass, unless STUB_CHECK_FAIL and no 'repaired' marker yet.
# STUB_CHECK_ENVFAIL=<code> makes it exit with that code (use 126/127) to simulate a harness that cannot
# EXECUTE — an environment failure, not a test failure — which no 'repaired' marker can clear.
CHECK_STUB = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
[ -n "${STUB_CHECK_ENVFAIL:-}" ] && exit "${STUB_CHECK_ENVFAIL}"
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


def _issue(tmp, *, number=7, title="Do a thing", body="### Acceptance criteria\n- [ ] it works\n",
           state="OPEN", issue_type="Task"):
    p = tmp / "issue.json"
    # issueType mirrors `gh issue view --json issueType`: an object with a .name, or null when untyped.
    d = {"number": number, "title": title, "state": state, "body": body,
         "issueType": ({"name": issue_type} if issue_type else None)}
    p.write_text(json.dumps(d))
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
        "STUB_PRCOMMENTS": str(tmp / "prcomments"),
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


def test_gate_rejects_non_task_type(tmp_path):
    """A non-Task issue (e.g. a Feature/epic accidentally set Ready) is refused at the gate — the
    runner builds Tasks only; epics are tracked as native sub-issue parents, never built (footgun F3)."""
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, issue_type="Feature"))
    assert r.returncode == 3 and "task" in r.stderr.lower()
    tl = _timeline(tmp_path); assert not _ran(tl) and not _edits(tl)   # no stages, no state writes


def test_gate_rejects_untyped_issue(tmp_path):
    """An issue with no Issue Type at all is also refused (fail closed: build only explicit Tasks)."""
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, issue_type=None))
    assert r.returncode == 3 and "task" in r.stderr.lower()
    assert not _ran(_timeline(tmp_path)) and not _edits(_timeline(tmp_path))


def test_gate_type_check_can_be_disabled(tmp_path):
    """REQUIRE_ISSUE_TYPE='' disables the Type gate for repos that don't use Issue Types (repo-agnostic
    escape hatch). A Feature then clears the gate — shown read-only via --dry-run."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, issue_type="Feature"); env["REQUIRE_ISSUE_TYPE"] = ""
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True


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


def test_check_env_failure_blocks_without_repair(tmp_path):
    """A check that cannot EXECUTE (exit 126 — e.g. a venv console-script whose shebang points at a
    moved/rebuilt interpreter) is an ENVIRONMENT failure, not a code failure. It must fail closed
    immediately — NO LLM repair attempt (which could paper it over, e.g. pip --break-system-packages)
    — and be reported as an environment/toolchain problem (footgun F5)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "REPAIR" not in tl                          # the LLM repair stage must NOT be invoked
    assert tl.count("CHECK") == 1                      # checked once, failed closed (no second check)
    edits = " ".join(_edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits                  # Reason=Blocked set
    assert "environment" in r.stderr.lower() or "toolchain" in r.stderr.lower()
    assert _comments(tl)                               # the env failure is reported on the issue
    assert "https://stub/pr/1" not in r.stdout         # no PR


def test_check_env_failure_127_also_blocks_without_repair(tmp_path):
    """The other 'cannot execute' code, 127 (command not found), is treated the same way."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Missing tool"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "127"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "REPAIR" not in tl and tl.count("CHECK") == 1
    assert "Blocked" in " ".join(_edits(tl)) and "https://stub/pr/1" not in r.stdout


def test_check_env_failure_after_repair_blocks_as_env(tmp_path):
    """A CODE failure (exit 1) earns the one repair attempt, but if the toolchain then breaks (exit 126
    on the re-check) it is reported as an ENVIRONMENT failure — not the generic 'checks still failing'."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Repairs into a broken env"), work)
    # check.sh: first call exits 1 (code failure) so a repair fires; the repair exports a marker the
    # stub reads to switch to exit 126 on the re-check (toolchain now 'broken').
    envfail_after = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -f repaired ]; then exit 126; fi
exit 1
'''
    _exec(binp / "check.sh", envfail_after)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "REPAIR" in tl and tl.count("CHECK") == 2   # code failure earned one repair, then re-checked
    assert "environment" in r.stderr.lower() or "toolchain" in r.stderr.lower()
    assert "still failing" not in r.stderr.lower()     # reported as env, not the generic code-failure message
    assert "https://stub/pr/1" not in r.stdout


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


def test_tester_boundary_guard_ignores_build_artifacts(tmp_path):
    """A build artifact the tester incidentally produces (e.g. __pycache__/*.pyc from running the
    gate) is not an implementation change and must not trip the guard: the run proceeds to a PR."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Boundary guard artifact"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1", "STUB_TESTER_ARTIFACT_CHANGE": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "TEST" in tl and "CHECK" in tl and "REVIEW" in tl        # all stages proceeded past the guard
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
    assert json.loads(r.stdout)["model"] == "claude-sonnet-5"


def test_dryrun_default_model_no_overrides(tmp_path):
    """With no MODEL env, no manifest model, and no body model: line, the resolved model is claude-sonnet-5."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp)
    env["MODEL"] = ""  # empty string triggers :- in the runner, so the built-in default is used
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["model"] == "claude-sonnet-5"


def test_dryrun_body_model_sonnet_resolves_to_sonnet_5(tmp_path):
    """A bare `model: sonnet` body override (with no manifest model) resolves to claude-sonnet-5."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: sonnet\n")
    env["MODEL"] = ""  # isolate from any ambient MODEL env var so only the body override and built-in default apply
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["model"] == "claude-sonnet-5"


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


def test_manifest_read_from_base_ref_not_stale_working_tree(tmp_path):
    """The manifest comes from origin/main (the build's base ref), not the base checkout's working
    tree — so a checkout that has drifted behind origin (e.g. a shared/live dev workspace that never
    pulled the manifest merge) still builds with the right check_cmd, read from the ref."""
    work, _ = _make_repo(tmp_path)
    (work / ".yr").mkdir(); (work / ".yr" / "factory.toml").write_text('check_cmd = "echo MANIFEST_FROM_REF"\n')
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "add manifest"], work)
    _git(["push", "-q", "origin", "main"], work)
    _git(["reset", "--hard", "HEAD~1"], work)            # working tree drifts behind origin/main
    assert not (work / ".yr" / "factory.toml").exists()  # present only on the ref now
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Manifest from ref"), work)
    del env["CHECK_CMD"]                                  # fall back to the manifest's check_cmd
    env.update({"STUB_CLAUDE_CHANGE": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    checks_log = list((tmp_path / "drhome" / "runs").glob("5-*/checks.log"))[0].read_text()
    assert "MANIFEST_FROM_REF" in checks_log             # ran the ref's check_cmd, not the .venv default
    assert "https://stub/pr/1" in r.stdout               # proceeded to a PR


# ============ Issue #37: terminal (shadow) merge-condition evaluator + loud record ============
# After the PR opens, the runner runs a DETERMINISTIC terminal step (no new LLM stage) that evaluates
# the fail-closed merge conditions IN ORDER, IN CODE (indeterminate = failed), and — treating every
# repo as shadow — posts one loud, machine-readable YR-MERGE-SHADOW record on the PR, then stops for
# the human exactly as today (still reaches In Review). The gh stub now serves a check rollup
# (`gh pr view --json statusCheckRollup`) and captures PR comment bodies (STUB_PRCOMMENTS).

EMDASH = "—"   # the marker separator: 'WOULD-BLOCK — <condition>'
WOULD_MERGE = "YR-MERGE-SHADOW: WOULD-MERGE"

# rollup entry shapes, as `gh pr view --json statusCheckRollup` returns them.
CR_OK = {"__typename": "CheckRun", "name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}
CR_FAIL = {"__typename": "CheckRun", "name": "ci", "status": "COMPLETED", "conclusion": "FAILURE"}
CR_INFLIGHT = {"__typename": "CheckRun", "name": "ci", "status": "IN_PROGRESS", "conclusion": None}

# fields the epic fixes on the record — the versioned yr-merge-record/1 contract.
SHADOW_FIELDS = {
    "schema", "decision", "mode", "machinery_ok", "failed_condition", "bundle_sha256",
    "base_sha", "head_sha", "main_tip_sha", "check_rollup", "checks", "review_verdict",
    "rounds", "build", "review", "run_id", "timestamp",
}


def _would_block(cond):
    return f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} {cond}"


def _rollup(tmp, checks):
    p = tmp / "rollup.json"
    p.write_text(json.dumps({"statusCheckRollup": checks}))
    return str(p)


def _shadow_body(tmp, number=5):
    """The shadow record body the runner wrote+posted (merge-shadow.md in the run dir), or None."""
    files = list((tmp / "drhome" / "runs").glob(f"{number}-*/merge-shadow.md"))
    return files[0].read_text() if files else None


def _prcomments(tmp):
    p = tmp / "prcomments"
    return p.read_text() if p.exists() else ""


def _shadow_block(body):
    """Parse the fenced `yr-merge-record` JSON block out of a posted shadow comment."""
    start = body.index("```yr-merge-record") + len("```yr-merge-record")
    rest = body[start:]
    return json.loads(rest[: rest.index("```")])


def _shadow_env(tmp_path, *, title, checks, body=None, extra=None):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    kw = {"number": 5, "title": title}
    if body is not None:
        kw["body"] = body
    env = _real(tmp_path, _env(tmp_path, binp, **kw), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = _rollup(tmp_path, checks)
    # keep the CI wait cheap/deterministic in tests (no real sleeps for the all-complete rollups).
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    if extra:
        env.update(extra)
    return env


def _assert_not_blocked_and_in_review(tl, r):
    assert "https://stub/pr/1" in r.stdout                                   # the PR was opened
    assert any(l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l for l in tl)
    # criterion 7: a shadow WOULD-BLOCK is a NORMAL outcome, never Reason=Blocked.
    assert not any("REASONFIELD" in l and "Blocked" in l for l in tl)


def test_shadow_would_merge_and_reaches_in_review(tmp_path):
    """Green CI + fresh base + clean approval + rank-holding pair -> WOULD-MERGE, posted on the PR,
    and the run still stops for the human at In Review (criteria 1-7)."""
    env = _shadow_env(tmp_path, title="Shadow would-merge", checks=[CR_OK])
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body is not None, "the terminal step wrote no shadow record"
    assert body.splitlines()[0] == WOULD_MERGE                               # first line is EXACTLY the marker
    # exactly one shadow comment was posted on the PR.
    assert _prcomments(tmp_path).count("YR-MERGE-SHADOW") == 1
    rec = _shadow_block(body)
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["decision"] == "WOULD-MERGE" and rec["failed_condition"] is None
    assert rec["mode"] == "shadow" and rec["machinery_ok"] is True
    assert SHADOW_FIELDS <= set(rec), f"missing: {SHADOW_FIELDS - set(rec)}"
    assert rec["review_verdict"] == "VERDICT: APPROVE"
    assert rec["check_rollup"] == "success"
    assert len(rec["head_sha"]) == 40                                        # the pushed PR head commit
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_would_block_zero_checks_fails_fast(tmp_path):
    """Zero configured checks is a failure evaluated WITHOUT the bounded wait (criterion 2). Proven by
    a huge poll interval/timeout with a hard subprocess timeout: if it entered the wait it would hang."""
    env = _shadow_env(tmp_path, title="Shadow zero checks", checks=[])
    env["MERGE_CI_POLL_INTERVAL"] = "600"; env["MERGE_CI_TIMEOUT"] = "600"
    full = {**os.environ, **READABLE_IDS, **env}
    r = subprocess.run(["bash", str(RUNNER), "5", "--repo", "test/repo"],
                       capture_output=True, text=True, env=full, cwd=str(ROOT), timeout=60)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("ci_green")
    rec = _shadow_block(body)
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "ci_green"
    assert rec["check_rollup"] == "empty"                                    # zero checks -> empty, not a wait/timeout
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_would_block_ci_failure(tmp_path):
    """A failing configured check means CI is not green -> WOULD-BLOCK ci_green (criterion 2)."""
    env = _shadow_env(tmp_path, title="Shadow ci failure", checks=[CR_OK, CR_FAIL])
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("ci_green")
    assert _shadow_block(body)["check_rollup"] == "failure"
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_would_block_ci_timeout(tmp_path):
    """In-flight checks that never finish within the bounded wait time out -> failure (criterion 2)."""
    env = _shadow_env(tmp_path, title="Shadow ci timeout", checks=[CR_INFLIGHT])
    # MERGE_CI_TIMEOUT=0 (set by _shadow_env) makes the first poll with in-flight runs time out at once.
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("ci_green")
    assert _shadow_block(body)["check_rollup"] == "timed_out"
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_would_block_freshness(tmp_path):
    """The reviewed base SHA must equal main's tip at decision time; a moved main tip -> WOULD-BLOCK
    freshness (criterion 3). CI is green so freshness is the FIRST failing condition."""
    env = _shadow_env(tmp_path, title="Shadow stale base", checks=[CR_OK],
                      extra={"MERGE_MAIN_TIP": "0" * 40})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("freshness")
    rec = _shadow_block(body)
    assert rec["failed_condition"] == "freshness"
    assert rec["main_tip_sha"] == "0" * 40 and rec["base_sha"] != rec["main_tip_sha"]
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_would_block_rank_gate(tmp_path):
    """An equal-rank pair (build==review) clears intake but fails the STRICT review>build merge gate ->
    WOULD-BLOCK rank_gate (criterion 5). CI green + fresh, so rank_gate is the first failing condition."""
    body_md = "### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: opus\n"
    env = _shadow_env(tmp_path, title="Shadow equal rank", checks=[CR_OK], body=body_md)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                                       # intake did NOT bounce the equal pair
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("rank_gate")
    assert _shadow_block(body)["failed_condition"] == "rank_gate"
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_first_failed_condition_is_earliest_in_order(tmp_path):
    """Conditions are evaluated IN ORDER (criterion 1): with BOTH ci_green (zero checks) and rank_gate
    (equal pair) failing, the record names ci_green — the earliest — not rank_gate."""
    body_md = "### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: opus\n"
    env = _shadow_env(tmp_path, title="Shadow ordering", checks=[], body=body_md)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("ci_green")                  # earliest failing condition
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_reapproval_of_revised_diff_still_would_merge(tmp_path):
    """criterion 4: the final round need only be a clean APPROVE — re-approval of a revised diff (after
    a first-round REQUEST_CHANGES + repair) suffices, and yields WOULD-MERGE with rounds=2."""
    env = _shadow_env(tmp_path, title="Shadow re-approval", checks=[CR_OK],
                      extra={"STUB_REVIEW_BLOCK": "1"})   # block once, approve on re-review
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert tl.count("REVIEW") == 2 and "REVIEWFIX" in tl                     # blocked once, re-approved
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == WOULD_MERGE
    rec = _shadow_block(body)
    assert rec["decision"] == "WOULD-MERGE"
    assert rec["rounds"] == 2 and rec["review_verdict"] == "VERDICT: APPROVE"


def test_shadow_block_does_not_set_reason_blocked(tmp_path):
    """criterion 7 (explicit): a shadow WOULD-BLOCK must NOT flip Reason=Blocked — it is a normal
    negative outcome that stops for the human, distinct from the code/machinery Blocked path."""
    env = _shadow_env(tmp_path, title="Shadow block not blocked", checks=[CR_FAIL])
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "Blocked" not in " ".join(_edits(tl))            # no Reason=Blocked anywhere
    assert _shadow_body(tmp_path).splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-BLOCK")
    _assert_not_blocked_and_in_review(tl, r)


def test_shadow_environmental_failure_posts_no_record(tmp_path):
    """criterion 8: when the terminal step's OWN execution fails environmentally (a gh API blip while
    reading the rollup), it is classified environmental — NO machinery-error record is posted, the run
    is not Blocked, and it still stops for the human at In Review (resumable)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Shadow env failure"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_PRVIEW_FAIL": "1"})   # gh pr view errors while evaluating CI
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _shadow_body(tmp_path) is None                    # no record was built/written
    assert "YR-MERGE-SHADOW" not in _prcomments(tmp_path)    # and none was posted on the PR
    tl = _timeline(tmp_path)
    assert "Blocked" not in " ".join(_edits(tl))             # env failure of the terminal step never Blocks
    _assert_not_blocked_and_in_review(tl, r)
    # classified environmental / resumable in the log, not a machinery error.
    assert "environmental" in r.stderr.lower() or "resumable" in r.stderr.lower()


# ============ Issue #39: stage-completion checkpoints + resume on environmental failure ============
# On an ENVIRONMENTAL check failure (the existing 126/127 path) the runner PRESERVES the branch-keyed
# worktree + run dir + per-branch stage-completion markers (env_hold) instead of tearing them down, and a
# relaunch REUSES them, re-entering at the first stage without a `.done` marker. On success or a
# code/machinery failure the state is cleared and the worktree torn down exactly as today. The env failure
# is driven deterministically via STUB_CHECK_ENVFAIL (as the test_check_env_failure_* fixtures do), so no
# real toolchain break is needed. State lives under $DEV_RUNNER_HOME (= tmp/drhome via _real).

def _state_dir(tmp):
    """The single per-branch stage-completion state dir under the dispatch home, or None."""
    dirs = [d for d in (tmp / "drhome" / "state").glob("*") if d.is_dir()]
    return dirs[0] if dirs else None


def _wt_dir(tmp):
    """The single preserved branch-keyed worktree dir, or None once torn down."""
    dirs = [d for d in (tmp / "drhome" / "wt").glob("*") if d.is_dir()]
    return dirs[0] if dirs else None


def _run_dirs(tmp, number=5):
    return list((tmp / "drhome" / "runs").glob(f"{number}-*"))


def test_env_failure_preserves_worktree_markers_and_run_dir(tmp_path):
    """Criteria 1 & 2: each completed stage drops a durable per-branch `.done` marker, and an
    environmental check failure PRESERVES the worktree, the run dir, and those markers (env_hold does NOT
    tear down) — plus an env-hold marker and a self-describing run.json so the state is resumable."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    # the branch-keyed worktree is preserved (not torn down by the env-failure path)
    wt = _wt_dir(tmp_path)
    assert wt is not None and wt.exists()
    # the run dir (with its check output) is preserved
    rundirs = _run_dirs(tmp_path)
    assert rundirs and (rundirs[0] / "checks.log").exists()
    # per-branch stage markers: implement + test completed before the check failed -> present;
    # the check never completed -> no marker (criterion 1: a marker is written as each stage completes).
    sd = _state_dir(tmp_path)
    assert sd is not None
    assert (sd / "01-implement.done").exists()
    assert (sd / "02-test.done").exists()
    assert not (sd / "03-check.done").exists()
    # the env-hold marker + the self-describing resume manifest
    assert (sd / "env-hold").exists()
    rj = json.loads((sd / "run.json").read_text())
    assert rj["branch"] == "task/5-broken-toolchain"        # per-branch, stable across runs
    assert rj["worktree"] == str(wt)


def test_relaunch_resumes_at_first_incomplete_stage(tmp_path):
    """Criterion 3: relaunching an issue with preserved env-hold state REUSES the worktree + branch and
    resumes at the first stage without a `.done` marker — the earlier green stages are NOT re-run."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r1 = _run(["5", "--repo", "test/repo"], env)
    assert r1.returncode != 0
    wt1 = _wt_dir(tmp_path)
    assert wt1 is not None
    # relaunch: same preserved state, but the toolchain is healthy now (no ENVFAIL). Isolate the timeline
    # so we assert only what the SECOND run does.
    env2 = {**env, "STUB_TIMELINE": str(tmp_path / "timeline2")}
    del env2["STUB_CHECK_ENVFAIL"]
    r2 = _run(["5", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr
    assert "https://stub/pr/1" in r2.stdout                          # resumed all the way to a PR
    tl2 = (tmp_path / "timeline2").read_text().splitlines()
    # implement + test carried `.done` markers -> skipped on the relaunch timeline (not re-run)
    assert "IMPL" not in tl2 and "TEST" not in tl2
    # resumed at the first incomplete stage (check) and continued (review)
    assert "CHECK" in tl2 and "REVIEW" in tl2
    # the SAME preserved worktree/branch was reused, not a fresh one (the resume log names its path)
    assert "reusing preserved env-hold worktree" in r2.stderr
    assert str(wt1) in r2.stderr
    assert "resume: skipping implement" in r2.stderr and "resume: skipping test" in r2.stderr
    # after the successful resume, cleanup_wt cleared the state and tore the worktree down (criterion 5)
    assert _state_dir(tmp_path) is None
    assert list((tmp_path / "drhome" / "wt").glob("*")) == []


def test_relaunch_without_preserved_state_runs_fresh(tmp_path):
    """Criterion 4: with no preserved env-hold state, a run creates a FRESH worktree and runs every stage
    exactly as today — nothing is skipped and no resume path is taken."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Fresh run"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "IMPL" in tl and "TEST" in tl and "CHECK" in tl and "REVIEW" in tl   # every stage ran fresh
    assert "reusing preserved env-hold" not in r.stderr                         # no resume path taken
    assert "resume: skipping" not in r.stderr


def test_success_clears_state_and_tears_down(tmp_path):
    """Criterion 5 (success branch): a successful build clears the stage-completion state and tears the
    worktree down exactly as today — no markers or worktree leak into the next run."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Clean success"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert _wt_dir(tmp_path) is None        # worktree torn down
    assert _state_dir(tmp_path) is None     # stage-completion state cleared


def test_code_failure_clears_state_and_tears_down_no_resume(tmp_path):
    """Criterion 5 + the constraint 'resume must never reuse state across a code failure': a CODE failure
    (check fails, the one repair can't fix) clears the stage state and tears the worktree down as today,
    and a later relaunch runs FRESH — resume is for environmental failures only."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Cannot fix"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REPAIR_NOFIX": "1"})
    r1 = _run(["5", "--repo", "test/repo"], env)
    assert r1.returncode != 0 and "Blocked" in " ".join(_edits(_timeline(tmp_path)))
    # torn down: no worktree, no state dir, no lingering env-hold survive a code failure
    assert _wt_dir(tmp_path) is None
    assert _state_dir(tmp_path) is None
    # relaunch with a healthy build must run FRESH (state was cleared, not preserved -> no resume)
    env2 = {**env, "STUB_TIMELINE": str(tmp_path / "timeline2")}
    env2.pop("STUB_CHECK_FAIL"); env2.pop("STUB_REPAIR_NOFIX")
    r2 = _run(["5", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr
    tl2 = (tmp_path / "timeline2").read_text().splitlines()
    assert "IMPL" in tl2 and "TEST" in tl2          # everything re-run from scratch, nothing skipped
    assert "reusing preserved env-hold" not in r2.stderr


def test_env_hold_is_visible_on_the_issue(tmp_path):
    """Criterion 6: an environmental hold is recorded VISIBLY on the issue (a comment naming the hold and
    the preserved-state resume + Reason=Blocked on the board) — never a silently stranded claim."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    comments = " ".join(_comments(tl))
    assert comments                                                 # a comment WAS posted (not silent)
    assert "hold" in comments.lower()                              # it is named an (environmental) hold
    assert "resume" in comments.lower() or "preserved" in comments.lower()  # the preserved-state resume
    assert "Blocked" in " ".join(_edits(tl))                       # and visible on the board too


# ============ Issue #40: claude -p stage quota/limit kill classified environmental ============
# A `claude -p` stage (implement/test/check-repair/review) that exits non-zero AND whose log matches a
# quota/rate-limit signature is an ENVIRONMENTAL ceiling, never a code failure: no LLM repair, the same
# preserve+resume path as the check gate's env_hold (issue #39), and a Blocked comment naming it
# environmental (quota) rather than a generic code failure. QUOTA_SIGNATURES is overridable data, and a
# non-zero stage whose log has no signature match stays a plain code failure exactly as before.

def test_implement_quota_kill_is_environmental_hold(tmp_path):
    """A build-stage (implement) death with a quota signature in its log is classified environmental:
    Blocked (visible on the board), but named a quota/environmental hold rather than a code failure —
    and preserved/resumable (no cleanup_wt), matching the check gate's env_hold discipline (issue #39).
    No later stage (test/check) ever ran."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Quota kill on implement"), work)
    env["STUB_IMPL_QUOTA"] = "Error: usage limit reached for this account, try again later"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "IMPL" in tl and "TEST" not in tl and "CHECK" not in tl        # died at implement; nothing after
    edits = " ".join(_edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits                 # still visible as Blocked
    comments = " ".join(_comments(tl))
    assert comments and "environmental" in comments.lower() and "quota" in comments.lower()
    assert "environmental" in r.stderr.lower() and "quota" in r.stderr.lower()
    assert "https://stub/pr/1" not in r.stdout
    # preserved for resume — NOT torn down the way a plain code failure would be
    wt = _wt_dir(tmp_path); assert wt is not None and wt.exists()
    sd = _state_dir(tmp_path); assert sd is not None
    assert (sd / "env-hold").exists()
    assert not (sd / "01-implement.done").exists()   # died before the implement checkpoint was recorded


def test_implement_generic_failure_without_quota_signature_stays_code_blocked(tmp_path):
    """Control case: a non-zero implement exit with NO quota/limit signature in its log is a plain code
    failure exactly as today — Blocked, torn down (no preserved resume state), no 'environmental' or
    'quota' wording anywhere."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Generic implement crash"), work)
    env["STUB_IMPL_FAIL"] = "TypeError: unexpected keyword argument 'foo'"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "IMPL" in tl and "TEST" not in tl
    assert "Blocked" in " ".join(_edits(tl))
    assert "environmental" not in r.stderr.lower() and "quota" not in r.stderr.lower()
    assert "https://stub/pr/1" not in r.stdout
    # torn down like any other code/machinery failure — no resumable state left behind
    assert _wt_dir(tmp_path) is None
    assert _state_dir(tmp_path) is None


def test_quota_signatures_overridable_via_env(tmp_path):
    """QUOTA_SIGNATURES is overridable data: a phrase absent from the DEFAULT list is not classified
    environmental (plain code failure, torn down), but IS once QUOTA_SIGNATURES is overridden to
    include it (environmental hold, preserved)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    phrase = "acme-provider-daily-cap-hit"

    env1 = _real(tmp_path, _env(tmp_path, binp, number=5, title="Custom signature"), work)
    env1["STUB_IMPL_QUOTA"] = phrase
    r1 = _run(["5", "--repo", "test/repo"], env1)
    assert r1.returncode != 0
    assert "environmental" not in r1.stderr.lower()
    assert _wt_dir(tmp_path) is None and _state_dir(tmp_path) is None   # torn down, not preserved

    env2 = _real(tmp_path, _env(tmp_path, binp, number=5, title="Custom signature"), work)
    env2["STUB_IMPL_QUOTA"] = phrase
    env2["QUOTA_SIGNATURES"] = phrase
    r2 = _run(["5", "--repo", "test/repo"], env2)
    assert r2.returncode != 0
    assert "environmental" in r2.stderr.lower()
    assert _wt_dir(tmp_path) is not None and _state_dir(tmp_path) is not None   # preserved this time


def test_default_quota_signatures_cover_the_epic_proposed_list():
    """Guard: the shipped default QUOTA_SIGNATURES covers the epic-proposed signatures (usage limit,
    rate limit, quota, overloaded, 429) — the live-CLI verification (manual, noted in the PR) pins
    against exactly this list, so a default drifting away from it would silently narrow coverage."""
    src = RUNNER.read_text()
    m = re.search(r'QUOTA_SIGNATURES="\$\{QUOTA_SIGNATURES:-([^}]*)\}"', src)
    assert m, "QUOTA_SIGNATURES default assignment not found in dev-runner.sh"
    default = m.group(1)
    for sig in ("usage limit", "rate limit", "quota", "overloaded", "429"):
        assert sig in default, f"default QUOTA_SIGNATURES missing '{sig}': {default!r}"


def test_check_repair_quota_kill_is_environmental(tmp_path):
    """A quota kill in the CHECK-REPAIR claude stage (fired after a failing check) is classified
    environmental — not the generic 'checks still failing' code Blocked — and no second check ever runs."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Quota kill on check repair"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1",
                "STUB_REPAIR_QUOTA": "429 Too Many Requests"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert tl.count("CHECK") == 1 and "REPAIR" in tl        # one failing check, one (quota-killed) repair
    assert "still failing" not in r.stderr.lower()
    assert "environmental" in r.stderr.lower() and "quota" in r.stderr.lower()
    comments = " ".join(_comments(tl))
    assert "environmental" in comments.lower() and "quota" in comments.lower()
    assert _wt_dir(tmp_path) is not None and _state_dir(tmp_path) is not None
    assert "https://stub/pr/1" not in r.stdout


def test_review_quota_kill_is_environmental(tmp_path):
    """A quota kill in the REVIEWER claude stage is classified environmental, not the generic
    'reviewer still requests changes' code Blocked."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Quota kill on review"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_QUOTA": "the account is rate limited"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "CHECK" in tl and "REVIEW" in tl
    assert "environmental" in r.stderr.lower() and "quota" in r.stderr.lower()
    comments = " ".join(_comments(tl))
    assert "environmental" in comments.lower() and "quota" in comments.lower()
    assert "https://stub/pr/1" not in r.stdout
    assert _wt_dir(tmp_path) is not None and _state_dir(tmp_path) is not None


# ============ Issue #40: pool -> credential seam (YR_POOL_<POOL>) ============
# Every registry entry names a quota_pool; a stage whose resolved model belongs to pool "<pool>" looks up
# YR_POOL_<POOL_UPPER_SNAKE> in the dispatch environment to select its claude credential (CLAUDE_CONFIG_DIR),
# falling back to the ambient default (today's single-account behavior) when unset. STUB_CLAUDE_ENV_FILE
# has the claude stub record the CLAUDE_CONFIG_DIR it saw on each invocation, in call order.

def test_pool_credential_falls_back_to_ambient_default_when_unset(tmp_path):
    """With no YR_POOL_* set, every claude invocation runs with no CLAUDE_CONFIG_DIR override — today's
    single-account behavior is unchanged (the seam is named but not exercised)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="No pool override"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CLAUDE_ENV_FILE"] = str(tmp_path / "claude_env")
    env["CLAUDE_CONFIG_DIR"] = ""   # isolate from any ambient value on the host running the test
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "claude_env").read_text().splitlines()
    assert lines and all(l == "CLAUDE_CONFIG_DIR=" for l in lines)


def test_pool_credential_selects_env_var_when_set(tmp_path):
    """Both shipping registry entries (sonnet, opus) share quota_pool='anthropic-main'. Setting
    YR_POOL_ANTHROPIC_MAIN selects that credential for every claude invocation (build and review)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Pool override set"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CLAUDE_ENV_FILE"] = str(tmp_path / "claude_env")
    env["YR_POOL_ANTHROPIC_MAIN"] = "/creds/anthropic-main"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "claude_env").read_text().splitlines()
    assert lines and all(l == "CLAUDE_CONFIG_DIR=/creds/anthropic-main" for l in lines)


def test_pool_credential_differs_by_role_pool(tmp_path):
    """A registry where build and review draw from DIFFERENT pools: only the pool with a YR_POOL_*
    value set gets a credential override; the other role falls back to the ambient default."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    registry = tmp_path / "custom-models.toml"
    registry.write_text('''
[models.sonnet]
id = "claude-sonnet-5"
provider = "anthropic"
rank = 30
quota_pool = "pool-a"

[models.opus]
id = "claude-opus-4-8"
provider = "anthropic"
rank = 40
quota_pool = "pool-b"

[roles]
build = "sonnet"
review = "opus"
''')
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Differential pool"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CLAUDE_ENV_FILE"] = str(tmp_path / "claude_env")
    env["MODELS_REGISTRY"] = str(registry)
    env["CLAUDE_CONFIG_DIR"] = ""    # isolate from any ambient value on the host running the test
    env["YR_POOL_POOL_A"] = "/creds/pool-a"   # only pool-a (build) has a credential set; pool-b does not
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "claude_env").read_text().splitlines()
    assert len(lines) == 3                                       # implement, test (both build/pool-a), review
    assert lines[0] == "CLAUDE_CONFIG_DIR=/creds/pool-a"          # implement
    assert lines[1] == "CLAUDE_CONFIG_DIR=/creds/pool-a"          # test
    assert lines[2] == "CLAUDE_CONFIG_DIR="                       # review (pool-b, no override -> ambient)


def test_pool_seam_documented_in_dispatch_md_and_env_example():
    """Acceptance criterion: the pool->credential seam is documented in deploy/DISPATCH.md and
    deploy/dispatch.env.example (not just implemented)."""
    dispatch_md = (ROOT / "deploy" / "DISPATCH.md").read_text()
    env_example = (ROOT / "deploy" / "dispatch.env.example").read_text()
    assert "YR_POOL_" in dispatch_md and "quota_pool" in dispatch_md.lower()
    assert "YR_POOL_" in env_example
