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
                   __p=""; __bf=""; __body=""
                   for __a in "$@"; do
                     [ "$__p" = "--body-file" ] && __bf="$__a"
                     [ "$__p" = "--body" ] && __body="$__a"
                     __p="$__a"
                   done
                   [ -n "$__bf" ] && { echo "=== PRCOMMENT ==="; cat "$__bf"; } >> "$STUB_PRCOMMENTS"
                   [ -n "$__body" ] && { echo "=== PRCOMMENT ==="; printf '%s\\n' "$__body"; } >> "$STUB_PRCOMMENTS"
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
# Capture stdin byte-exactly: `$(cat)` strips ALL trailing newlines, so append a sentinel before the
# command substitution and strip it after — the byte-exact stdin pin (issue #121) must be able to see a
# stray trailing newline the transport might add, which a naive `$(cat)` would silently swallow.
stdin_content="$(cat; printf x)"; stdin_content="${stdin_content%x}"
[ -n "${STUB_CLAUDE_ARGV:-}" ] && printf '%s\\n' "$@" > "$STUB_CLAUDE_ARGV"
[ -n "${STUB_CLAUDE_ARGV_LOG:-}" ] && { printf '===STUB-CALL===\\n'; printf '%s\\n' "$@"; } >> "$STUB_CLAUDE_ARGV_LOG"
[ -n "${STUB_CLAUDE_STDIN:-}" ] && printf '%s' "$stdin_content" > "$STUB_CLAUDE_STDIN"
[ -n "${STUB_CLAUDE_STDIN_LOG:-}" ] && { printf '===STUB-STDIN-BEGIN===\\n'; printf '%s' "$stdin_content"; printf '\\n===STUB-STDIN-END===\\n'; } >> "$STUB_CLAUDE_STDIN_LOG"
# issue #121: the task prompt travels on stdin now, never argv — so stage classification (below) must
# match against the combined argv+stdin text, not argv alone, or every stage whose routing literal lived
# in its task prompt (check-repair's "tests FAIL", review-repair's "REQUESTED CHANGES") misclassifies.
args="$*"$'\\n'"$stdin_content"
[ -n "${STUB_CLAUDE_ENV_FILE:-}" ] && printf 'CLAUDE_CONFIG_DIR=%s\\n' "${CLAUDE_CONFIG_DIR:-}" >> "$STUB_CLAUDE_ENV_FILE"
[ -n "${STUB_CLAUDE_GITENV_FILE:-}" ] && printf 'GIT_CONFIG_GLOBAL=%s GIT_CONFIG_SYSTEM=%s\\n' "${GIT_CONFIG_GLOBAL:-unset}" "${GIT_CONFIG_SYSTEM:-unset}" >> "$STUB_CLAUDE_GITENV_FILE"
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
[ -n "${STUB_CHECK_GITENV_FILE:-}" ] && printf 'GIT_CONFIG_GLOBAL=%s GIT_CONFIG_SYSTEM=%s\\n' "${GIT_CONFIG_GLOBAL:-unset}" "${GIT_CONFIG_SYSTEM:-unset}" >> "$STUB_CHECK_GITENV_FILE"
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


def _item(tmp, *, number=7, status="Ready", item_id="ITEM1", in_project=True, repo="test/repo", foreign=None):
    """`content.repository` (nameWithOwner) must be carried alongside `content.number`, since the
    matcher (#57) requires both to agree — a bare number is not enough on a board shared across repos.
    `foreign`, when given, is a same-numbered item from another repo placed AHEAD of the target in list
    order (as in the live incident: board position decided the winner before the matcher was repo-scoped)."""
    p = tmp / "item.json"
    items = []
    if foreign is not None:
        items.append({"id": foreign.get("item_id", "ITEMFOREIGN"), "status": foreign.get("status", "Done"),
                       "content": {"number": foreign.get("number", number),
                                   "repository": foreign.get("repo", "other/repo")}})
    if in_project:
        items.append({"id": item_id, "status": status, "content": {"number": number, "repository": repo}})
    p.write_text(json.dumps({"items": items}))
    return p


def _run(args, env_extra, cwd=None):
    # Scrub the check gate's own GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM neutralization (#67/#69,
    # tools/dev-runner.sh:737) from the ambient os.environ BEFORE merging env_extra, so a factory
    # self-build (whose check_cmd process tree carries these as /dev/null) doesn't leak that
    # neutralization into the inner runner spawned here — while a test that sets either key via
    # env_extra still wins (#77).
    base_env = {k: v for k, v in os.environ.items() if k not in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")}
    env = {**base_env, **READABLE_IDS, **env_extra}
    return subprocess.run(["bash", str(RUNNER), *args],
                          capture_output=True, text=True, env=env, cwd=str(cwd or ROOT))


def _base_env(tmp, issue_json, item_json, binp):
    return {
        "GH_BIN": str(binp / "gh"), "CLAUDE_BIN": str(binp / "claude"),
        "CHECK_CMD": f"bash {binp / 'check.sh'}",
        "STUB_ISSUE_JSON": str(issue_json), "STUB_ITEM_JSON": str(item_json),
        "STUB_TIMELINE": str(tmp / "timeline"), "STUB_GH_CALLS": str(tmp / "gh_calls"),
        "STUB_CLAUDE_ARGV": str(tmp / "claude_argv"),
        "STUB_CLAUDE_ARGV_LOG": str(tmp / "claude_argv_log"),
        "STUB_CLAUDE_STDIN": str(tmp / "claude_stdin"),
        "STUB_CLAUDE_STDIN_LOG": str(tmp / "claude_stdin_log"),
        "STUB_PRCOMMENTS": str(tmp / "prcomments"),
    }


def _env(tmp, binp, **kw):
    num = kw.pop("number", 7); status = kw.pop("status", "Ready"); in_project = kw.pop("in_project", True)
    item_id = kw.pop("item_id", "ITEM1"); repo = kw.pop("repo", "test/repo"); foreign = kw.pop("foreign", None)
    ij = _issue(tmp, number=num, **kw)
    it = _item(tmp, number=num, status=status, in_project=in_project, item_id=item_id, repo=repo, foreign=foreign)
    return _base_env(tmp, ij, it, binp)


def _timeline(tmp):
    p = tmp / "timeline"
    return p.read_text().splitlines() if p.exists() else []


def _edits(tl):    return [l for l in tl if l.startswith("EDIT")]
def _comments(tl): return [l for l in tl if l.startswith("COMMENT")]
def _ran(tl):      return any(m in tl for m in ("IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX"))


def _argv_calls(tmp):
    """Every `claude` invocation's argv, in call order, as a list of arg lists (STUB_CLAUDE_ARGV_LOG:
    one call per '===STUB-CALL===' boundary, flattened one-arg-per-line same as STUB_CLAUDE_ARGV)."""
    p = tmp / "claude_argv_log"
    if not p.exists():
        return []
    chunks = p.read_text().split("===STUB-CALL===\n")
    return [c.splitlines() for c in chunks if c]


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _seed_manifest(work):
    """Every repo this harness builds is onboarded by default (issue #125's admission wall bounces any
    repo with NO `.yr/factory.toml` at the base ref before claim) — a bare, key-less manifest so its mere
    PRESENCE satisfies the wall while every per-key default this suite already exercises stays untouched."""
    (work / ".yr").mkdir(parents=True, exist_ok=True)
    (work / ".yr" / "factory.toml").write_text("# seeded by the test harness — no keys, per-key defaults apply\n")


def _make_repo(tmp):
    origin = tmp / "origin.git"; origin.mkdir()
    _git(["init", "--bare", "-b", "main", "."], origin)
    work = tmp / "work"; work.mkdir()
    _git(["init", "-b", "main", "."], work)
    _git(["config", "user.email", "t@t"], work); _git(["config", "user.name", "tester"], work)
    (work / "README.md").write_text("seed\n")
    _seed_manifest(work)
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "seed"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "origin", "main"], work)
    return work, origin


def _make_repo_no_local_identity(tmp):
    """Like `_make_repo`, but the repo's own (persistent) git config never gets a `user.email`/`user.name`
    — the seed commit is made with one-shot `-c` flags that don't persist. Any later commit inside this
    repo (or a worktree of it) that succeeds must be getting its identity from elsewhere (global config),
    which is exactly what #67 must NOT let a neutralized `check_cmd` fall back to, while the runner's own
    git operations must still be free to."""
    origin = tmp / "origin.git"; origin.mkdir()
    _git(["init", "--bare", "-b", "main", "."], origin)
    work = tmp / "work"; work.mkdir()
    _git(["init", "-b", "main", "."], work)
    (work / "README.md").write_text("seed\n")
    _seed_manifest(work)
    _git(["add", "-A"], work)
    subprocess.run(["git", "-c", "user.email=seed@seed", "-c", "user.name=seed", "commit", "-q", "-m", "seed"],
                   cwd=str(work), check=True, capture_output=True, text=True)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "origin", "main"], work)
    return work


def _fake_global_gitconfig(tmp, name="fakehome"):
    """A fixture HOME whose `.gitconfig` supplies a git identity — standing in for the operator's
    host-global git config in PR #65 (an ambient identity that must never leak into a neutralized
    `check_cmd`, but must remain visible to every other process the runner spawns)."""
    home = tmp / name; home.mkdir()
    (home / ".gitconfig").write_text("[user]\n\tname = Host Operator\n\temail = host-operator@example.com\n")
    return home


def _real(tmp, env, work):
    env.update({"GIT_BIN": "git", "BASE_REF": "origin/main",
                "BASE_REPO": str(work), "DEV_RUNNER_HOME": str(tmp / "drhome")})
    return env


def _make_factory_repo(tmp, behind=0, name="factory"):
    """A local git repo (bare origin + checkout), independent of the target BASE_REPO, standing in for
    the factory's OWN deployment — so FACTORY_DIR can be driven to a controlled behind-count without
    touching the real factory checkout these tests run from. `behind` commits are pushed to origin from
    a separate clone, so `work`'s HEAD never sees them until it fetches."""
    origin = tmp / f"{name}_origin.git"; origin.mkdir()
    _git(["init", "--bare", "-b", "main", "."], origin)
    work = tmp / f"{name}_work"; work.mkdir()
    _git(["init", "-b", "main", "."], work)
    _git(["config", "user.email", "t@t"], work); _git(["config", "user.name", "tester"], work)
    (work / "README.md").write_text("seed\n")
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "seed"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-q", "origin", "main"], work)
    if behind:
        other = tmp / f"{name}_other"
        _git(["clone", "-q", str(origin), str(other)], tmp)
        _git(["config", "user.email", "t@t"], other); _git(["config", "user.name", "tester"], other)
        for i in range(behind):
            (other / f"extra{i}.txt").write_text("x\n")
            _git(["add", "-A"], other); _git(["commit", "-q", "-m", f"extra {i}"], other)
        _git(["push", "-q", "origin", "main"], other)
    return work


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


# ============ #57: cross-repo issue-number collision on the shared board ============
# The "Yellow Robots — Dev" board spans every product repo, so two repos can carry a same-numbered
# item. The matcher must key on (number, repository) together, never number alone — a foreign repo's
# item, however it sorts on the board, must never be read, gated on, claimed, or written in place of
# the dispatched repo's own item. `epic_gate.py` is not exercised here: it resolves per-issue Status
# via that issue's own `projectItems` (GraphQL) plus native `subIssues` order, not a board-wide
# number scan, so it is a different code path and not subject to this collision by construction.

def test_foreign_done_same_number_does_not_gate_a_ready_target(tmp_path):
    """A same-numbered Done item from another repo — listed ahead of the target, as board position
    decided the (buggy) winner in the live incident — must never shadow the target's own Ready status.
    The build must proceed to completion, never refusing with the foreign item's Done status."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, number=5, item_id="ITEM1", title="Real work",
               foreign={"number": 5, "status": "Done", "item_id": "ITEMFOREIGN", "repo": "yellow-robots/other"})
    env = _real(tmp_path, env, work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr        # must NOT gate as "not Ready (Status: Done)"
    assert "not ready" not in r.stderr.lower()
    edits = _edits(_timeline(tmp_path))
    assert edits and all("ITEMFOREIGN" not in e for e in edits) and all("ITEM1" in e for e in edits)


def test_foreign_ready_same_number_is_never_claimed_only_target_item_is_written(tmp_path):
    """A same-numbered Ready item from a foreign repo must not be claimed in place of the dispatched
    repo's own Ready item — every field write must carry the target's item id, never the foreign one."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, number=5, item_id="ITEMTARGET", title="Real work",
               foreign={"number": 5, "status": "Ready", "item_id": "ITEMFOREIGN", "repo": "yellow-robots/other"})
    env = _real(tmp_path, env, work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    edits = _edits(_timeline(tmp_path))
    assert edits                                          # claim + In Review writes happened
    assert all("ITEMFOREIGN" not in e for e in edits)
    assert all("ITEMTARGET" in e for e in edits)


def test_foreign_item_present_but_target_absent_still_gates_not_in_project(tmp_path):
    """A same-numbered foreign-repo item existing on the board must not satisfy the DoR gate for the
    dispatched repo's issue — with no item of its own, the "not in project" refusal fires exactly as
    it would with an empty board (no false-positive match off the foreign repo's item)."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, in_project=False, foreign={"status": "Ready", "repo": "yellow-robots/other"})
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3 and "not in project" in r.stderr.lower()
    assert not _ran(_timeline(tmp_path)) and not _edits(_timeline(tmp_path))


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
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True


# ============ opening self-identification line (issue #85) ============
# A dispatched run's combined output is captured to a file the runner can't name in advance (it doesn't
# know its own run dir until it computes RUN_DIR from $$); the runner instead self-identifies as its very
# first line, so a captured log — or an attended terminal — always says which issue/repo/run dir it is.

def test_opening_line_names_issue_repo_and_run_dir(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp)
    env["DEV_RUNNER_HOME"] = str(tmp_path / "drhome")
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "7" in r.stderr and "test/repo" in r.stderr
    assert str(tmp_path / "drhome" / "runs" / "7-") in r.stderr


def test_opening_line_prints_before_any_dor_refusal(tmp_path):
    # the self-id line must survive even when the run is refused outright (closed issue) — an operator
    # (or a captured log) needs to know WHICH run this was even when it never gets past the gate.
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, state="CLOSED")
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    assert "7" in r.stderr and "test/repo" in r.stderr and "run dir" in r.stderr.lower()


def test_opening_line_goes_to_stderr_not_stdout(tmp_path):
    # unchanged convention (log() writes to fd 2): dry-run's machine-readable plan is the only thing on
    # stdout, so a script parsing stdout as JSON is never polluted by the new line.
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "starting" not in r.stdout
    json.loads(r.stdout)   # stdout stays pure JSON — attended callers parsing it are unaffected


def test_attended_invocation_still_emits_to_the_terminal(tmp_path):
    # no dispatch in the picture here (no log-file redirection at all) — a plain, attended invocation
    # (an operator's terminal) must still see every "dev-runner: ..." line, including the new one.
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stderr.splitlines() if l.startswith("dev-runner:")]
    assert any("starting" in l and "run dir" in l for l in lines)


# ============ needs-info / dry-run ============

def test_needs_info_on_empty_criteria(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Goal\njust do it\n")
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded: isolates the empty-AC bounce specifically
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = _timeline(tmp_path); assert not _ran(tl)
    edit = " ".join(_edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit and _comments(tl)
    assert "acceptance-criteria section is empty" in r.stderr


def test_dryrun_runs_no_stages_and_writes_nothing(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0
    tl = _timeline(tmp_path)
    assert not _ran(tl) and "CHECK" not in tl and not _edits(tl) and not _comments(tl)


def test_dryrun_model_override_opus(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\n")
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert json.loads(r.stdout)["model"] == "claude-opus-4-8"


def test_unknown_model_override_real_bounces_needs_info(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: gpt-4\n")
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded: isolates the unknown-model bounce
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = _timeline(tmp_path); assert not _ran(tl)
    assert "NeedsInfo" in " ".join(_edits(tl)) and _comments(tl)
    assert "unknown build model" in r.stderr


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


# ============ #67: neutralize host git config for the check gate ============
# Host-ambient git config (an operator's global user.email/user.name, or a system-level config) must
# never make the check gate greener than CI. The runner sets GIT_CONFIG_GLOBAL=/dev/null and
# GIT_CONFIG_SYSTEM=/dev/null in the check_cmd child ONLY — every other spawned process (the LLM stages,
# and the runner's own git worktree/commit/push) keeps the full host environment.

def test_check_gate_git_config_neutralized_initial_and_recheck(tmp_path):
    """GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM must read /dev/null inside the check_cmd child, in BOTH
    the initial check and the post-repair re-check (the two call sites named in the acceptance criteria)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Git config neutralized"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1",
                "STUB_CHECK_GITENV_FILE": str(tmp_path / "check_gitenv")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                # code failure earns a repair, then passes
    tl = _timeline(tmp_path)
    assert tl.count("CHECK") == 2                      # initial check + post-repair re-check
    lines = (tmp_path / "check_gitenv").read_text().splitlines()
    assert lines == ["GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null"] * 2


def test_check_gate_git_config_neutralized_on_review_repair_recheck_too(tmp_path):
    """The check re-run after a review-repair (a third call site sharing the same `run_checks`) is
    neutralized the same way as the initial/code-repair checks."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Review repair recheck"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1",
                "STUB_CHECK_GITENV_FILE": str(tmp_path / "check_gitenv")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "REVIEWFIX" in tl                           # a review-repair round fired
    lines = (tmp_path / "check_gitenv").read_text().splitlines()
    assert len(lines) == 2                             # initial check + the review-repair re-check
    assert all(l == "GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null" for l in lines)


def test_llm_stages_are_not_git_config_neutralized(tmp_path):
    """The scrub is scoped to the check_cmd child only: an LLM stage (implement/test/repair/review) must
    see the ambient GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM untouched, never /dev/null."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="LLM stage git env"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CLAUDE_GITENV_FILE": str(tmp_path / "claude_gitenv")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "claude_gitenv").read_text().splitlines()
    assert lines                                       # at least one LLM stage ran and recorded its env
    assert all("/dev/null" not in l for l in lines)     # never neutralized for an LLM stage


def test_runner_own_git_commit_is_not_neutralized(tmp_path):
    """The runner's own git operations (worktree add, the PR commit, push) must keep the full host git
    config. Using a repo with NO local git identity plus a fixture HOME whose global .gitconfig supplies
    one, the runner's own commit (which stamps the PR) must still succeed by falling back to that host-
    global identity — proving the neutralization does not leak past the check_cmd child."""
    work = _make_repo_no_local_identity(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    fake_home = _fake_global_gitconfig(tmp_path)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Runner commit falls back to host identity"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["HOME"] = str(fake_home)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout             # the runner's own commit succeeded and reached a PR


def test_run_helper_scrubs_ambient_git_config_neutralization(monkeypatch, tmp_path):
    """#77: `_run` must not let the check gate's own GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM neutralization
    (the factory's own check-gate ambient, tools/dev-runner.sh:737) ride into the inner runner it spawns —
    reproducing the self-build recursion where these tests run themselves under `run_checks`. With both
    keys set to /dev/null in the ambient os.environ, an LLM stage of the _run-spawned runner must observe
    them as unset, while an explicit env_extra value for either key still wins."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Ambient scrub"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CLAUDE_GITENV_FILE": str(tmp_path / "claude_gitenv")})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "claude_gitenv").read_text().splitlines()
    assert lines
    assert all("GIT_CONFIG_GLOBAL=unset GIT_CONFIG_SYSTEM=unset" == l for l in lines)


def test_run_helper_lets_explicit_env_extra_win_over_the_scrub(monkeypatch, tmp_path):
    """The scrub in `_run` only drops the ambient os.environ copy of the two keys before merging
    env_extra — a test that sets either key explicitly via env_extra (as the #67 check-gate-neutralized
    tests do with the real runner) must still see that value, not `unset`."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Explicit env_extra wins"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CLAUDE_GITENV_FILE": str(tmp_path / "claude_gitenv"),
                "GIT_CONFIG_GLOBAL": "/explicit/global", "GIT_CONFIG_SYSTEM": "/explicit/system"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    lines = (tmp_path / "claude_gitenv").read_text().splitlines()
    assert lines
    assert all("GIT_CONFIG_GLOBAL=/explicit/global GIT_CONFIG_SYSTEM=/explicit/system" == l for l in lines)


def test_check_gate_fails_the_pr65_scenario_instead_of_masking_it(tmp_path):
    """The PR #65 failure mode, reproduced directly: a check_cmd that does `git commit` in a *worktree
    that has no local git identity*, relying on a fallback to host-global config to supply one (a fixture
    HOME's .gitconfig stands in for the operator's ambient config). Before #67 this would pass on the
    host (global config supplies an identity) while CI — with no such ambient config — fails with exit
    128. With the neutralization in place, the check gate must fail here too: host-green can no longer
    mask CI-red."""
    work, _ = _make_repo(tmp_path)   # the target repo (has local identity) — irrelevant to the check_cmd below
    binp = tmp_path / "bin"; _stubs(binp)
    fake_home = _fake_global_gitconfig(tmp_path)
    commit_check = tmp_path / "commit_check.sh"
    _exec(commit_check, '''#!/usr/bin/env bash
set -e
repo="$(mktemp -d)"
git init -q "$repo"
cd "$repo"
echo x > f.txt
git add f.txt
git commit -q -m "no local identity, relies on global config"
''')
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="PR 65 repro"), work)
    env["CHECK_CMD"] = f"bash {commit_check}"
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["HOME"] = str(fake_home)   # would supply an identity if the check_cmd child weren't neutralized
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0                           # gate fails, not silently green
    assert "https://stub/pr/1" not in r.stdout          # caught before a PR ever exists
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))


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
    """A minimal repo dir carrying a .yr/factory.toml (no git needed — dry-run never touches git). A
    leading comment line is always present — with no keys at all, `"\\n".join([]) + "\\n"` is just a
    newline, and `$(cat ...)` strips an all-whitespace read down to an EMPTY string, which the admission
    wall (issue #125) can't tell apart from no manifest at all."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    lines = ["# seeded by the test harness"]
    if check_cmd is not None: lines.append(f'check_cmd = "{check_cmd}"')
    if model is not None:     lines.append(f'model = "{model}"')
    if base_ref is not None:  lines.append(f'base_ref = "{base_ref}"')
    (repo / ".yr" / "factory.toml").write_text("\n".join(lines) + "\n")
    return repo


def test_dryrun_reports_workspace_default(tmp_path):
    """With no YR_WORKSPACE, the workspace is discovered relative to the script (factory/../..). BASE_REPO
    is pinned to a manifest-bearing dir (independent of the workspace default under test) purely so the
    admission wall doesn't bounce the run before it reaches the JSON report."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["workspace"] == str(ROOT.parent)


def test_dryrun_resolves_base_repo_from_workspace(tmp_path):
    """The target repo's checkout is resolved as $YR_WORKSPACE/<name> when BASE_REPO is unset. A manifest
    is seeded at that exact resolved path (not via a BASE_REPO override, which would defeat the point)
    purely so the admission wall doesn't bounce the run before it reaches the JSON report."""
    ws = tmp_path / "ws"; ws.mkdir()
    binp = tmp_path / "bin"; _stubs(binp)
    (ws / "repo" / ".yr").mkdir(parents=True)
    (ws / "repo" / ".yr" / "factory.toml").write_text("# seeded by the test harness\n")
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
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded but key-less: a sparse-manifest default
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["model"] == "claude-sonnet-5"


def test_dryrun_body_model_sonnet_resolves_to_sonnet_5(tmp_path):
    """A bare `model: sonnet` body override (with no manifest model) resolves to claude-sonnet-5."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: sonnet\n")
    env["MODEL"] = ""  # isolate from any ambient MODEL env var so only the body override and built-in default apply
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded but key-less: a sparse-manifest default
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


# ============ the admission wall's runner-side backstop (issue #125) ============
# The epic-gate's sweep is the earliest machine moment un-onboarded work is refused, but the runner's OWN
# config read is the backstop: raw manifest text empty after BOTH the base-ref read and the working-tree
# fallback means the repo carries no `.yr/factory.toml` anywhere -- never onboarded. That bounces exactly
# like the DoR content gate (Status=Backlog + Reason=Needs-info, a comment, exit before claim/worktree),
# distinct from a manifest that EXISTS but is merely sparse (individual keys absent keep their documented
# per-key defaults, already pinned throughout this file's other manifest tests).

def _make_repo_no_manifest(tmp):
    """A real git repo carrying NO `.yr/factory.toml` anywhere — at the base ref or in the working tree —
    the un-onboarded case (issue #125). `_make_repo` itself always seeds one (every other test in this
    suite is an onboarded repo by default), so this is the one fixture that deliberately withholds it."""
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


def test_missing_manifest_anywhere_bounces_before_claim_and_worktree(tmp_path):
    work, _ = _make_repo_no_manifest(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Un-onboarded repo"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3

    tl = _timeline(tmp_path)
    assert not _ran(tl)                                        # no stage ever launched — refused pre-claim
    edit = " ".join(_edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit            # the runner's existing bounce shape
    comments = " ".join(_comments(tl)).lower()
    assert "not onboarded" in comments and "factory.toml" in comments
    assert "auth" in comments and "arming" in comments          # names the non-delegable acts

    assert _wt_dir(tmp_path) is None                            # never got as far as a worktree


def test_missing_manifest_bounce_names_the_repo_not_the_criteria(tmp_path):
    """A GOOD acceptance-criteria body still bounces on an un-onboarded repo — the reason named is
    onboarding, not empty criteria (the two bounces are independent, folded into the same NEEDS_INFO)."""
    work, _ = _make_repo_no_manifest(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Un-onboarded, good criteria"), work)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    assert "not onboarded" in r.stderr.lower()
    assert "acceptance-criteria section is empty" not in r.stderr


def test_missing_manifest_bounce_is_not_rescued_by_an_env_override(tmp_path):
    """An explicit CHECK_CMD env override doesn't rescue an un-onboarded repo from the bounce — onboarding
    is a repo-level gate, independent of any single config key's precedence."""
    work, _ = _make_repo_no_manifest(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Un-onboarded, env override"), work)
    env["CHECK_CMD"] = "pytest -q"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    assert "not onboarded" in r.stderr.lower()


def test_sparse_manifest_present_but_key_less_proceeds_on_defaults(tmp_path):
    """The OTHER branch of the same fork: a manifest that EXISTS (even with no keys at all) is NOT the
    un-onboarded case — the run proceeds exactly as today, on the documented built-in defaults."""
    work, _ = _make_repo(tmp_path)                             # _make_repo's own seeded manifest: key-less
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Sparse manifest"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "CHECK" in tl and _ran(tl)                           # the run proceeded through every stage
    assert not any("not onboarded" in c.lower() for c in _comments(tl))


def test_check_runs_with_base_repo_venv_on_path(tmp_path):
    """The check runs with the base repo's .venv/bin on PATH, so a manifest can name bare tools
    (`pytest`) instead of a relative .venv path the ephemeral worktree doesn't contain."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    # a fake `pytest` that lives ONLY in the base repo's venv; it records that it ran, then passes.
    venvbin = work / ".venv" / "bin"; venvbin.mkdir(parents=True)
    marker = tmp_path / "base_pytest_ran"
    _exec(venvbin / "pytest", f'#!/usr/bin/env bash\n: > "{marker}"\nexit 0\n')
    (work / ".yr" / "factory.toml").write_text('check_cmd = "pytest tests/ -q"\n')
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "manifest"], work)
    _git(["push", "-q", "origin", "main"], work)
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
    (work / ".yr" / "factory.toml").write_text('check_cmd = "echo MANIFEST_FROM_REF"\n')
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "add manifest"], work)
    _git(["push", "-q", "origin", "main"], work)
    _git(["reset", "--hard", "HEAD~1"], work)            # working tree drifts behind origin/main
    # the seed's bare (key-less) manifest is what's left locally — present (the wall stays satisfied
    # either way), but it is NOT the ref's check_cmd: proves the ref, not the stale working tree, wins.
    assert "MANIFEST_FROM_REF" not in (work / ".yr" / "factory.toml").read_text()
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
    """Zero configured checks, still zero after the registration grace elapses, is a failure evaluated
    WITHOUT the (much longer) in-flight CI wait (issue #61, criterion 2). Proven by a huge poll interval/
    timeout for that in-flight wait with a hard subprocess timeout: if it ever entered that wait it would
    hang. The grace itself is collapsed to zero so the test stays fast and deterministic — its own
    tunability is covered by tests/test_ci_registration_grace.py."""
    env = _shadow_env(tmp_path, title="Shadow zero checks", checks=[])
    env["MERGE_CI_POLL_INTERVAL"] = "600"; env["MERGE_CI_TIMEOUT"] = "600"
    env["MERGE_CI_REG_GRACE"] = "0"; env["MERGE_CI_REG_POLL_INTERVAL"] = "0"
    full = {**os.environ, **READABLE_IDS, **env}
    r = subprocess.run(["bash", str(RUNNER), "5", "--repo", "test/repo"],
                       capture_output=True, text=True, env=full, cwd=str(ROOT), timeout=60)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("ci_green")
    rec = _shadow_block(body)
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "ci_green"
    # issue #61: the registration grace still yielded nothing, so the state is the NEW, distinguishing
    # 'empty_after_grace' — never confused with a rollup that registered and then failed/timed out.
    assert rec["check_rollup"] == "empty_after_grace"
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


# ============ Issue #48: stage usage capture — every build records what it cost ============
# `run_stage` now runs every claude -p stage with `--output-format json` by default, extracts the
# CLI's single JSON result envelope on a clean exit, rewrites the stage log to the plain reply text,
# and files the usage (fresh input/output/cache-write/cache-read + model + duration) as
# usage-<stage>.json in the run dir. A log that never held an envelope (plain text — the rest of this
# stub suite) or a failed stage is left completely untouched and yields no artifact. After PR create,
# the per-stage artifacts are aggregated into usage-summary.json + one PR comment. An explicit
# CLAUDE_OUTPUT_FORMAT still wins (old stream-json+--verbose pairing, no capture attempted).
#
# CLAUDE_STUB_JSON is a second claude stub, stage-aware like CLAUDE_STUB, but each branch emits a
# single-line `--output-format json` result envelope (fixed, distinguishable token counts per stage)
# instead of plain text — proving extraction, the rewrite, and the summary end-to-end.

CLAUDE_STUB_JSON = '''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\\n'"$stdin_content"   # issue #121: classification must see stdin too (the task prompt lives there)
[ -n "${STUB_CLAUDE_ARGV:-}" ] && printf '%s\\n' "$@" > "$STUB_CLAUDE_ARGV"
emit_json() {  # $1=result-text $2=input $3=output $4=cache_write $5=cache_read $6=duration_ms
  printf '{"type":"result","subtype":"success","is_error":false,"duration_ms":%s,"result":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":%s}}\\n' "$6" "$1" "$2" "$3" "$4" "$5"
}
case "$args" in
  *REVIEWER*)
    echo REVIEW >> "$STUB_TIMELINE"
    if [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then
      emit_json "VERDICT: REQUEST_CHANGES" 11 12 13 14 100
    else
      emit_json "VERDICT: APPROVE" 21 22 23 24 200
    fi ;;
  *"REQUESTED CHANGES"*)
    echo REVIEWFIX >> "$STUB_TIMELINE"
    : > review_repaired
    emit_json "fixed the blockers" 31 32 33 34 300 ;;
  *TESTER*)
    echo TEST >> "$STUB_TIMELINE"
    mkdir -p tests && printf 'pass\\n' > tests/test_stub_output.py
    emit_json "wrote tests" 41 42 43 44 400 ;;
  *"tests FAIL"*)
    echo REPAIR >> "$STUB_TIMELINE"
    : > repaired
    emit_json "repaired the code" 51 52 53 54 500 ;;
  *)
    echo IMPL >> "$STUB_TIMELINE"
    printf 'hello\\n' > feature.txt
    emit_json "implemented the feature" 61 62 63 64 600
    if [ -n "${STUB_IMPL_JSON_THEN_FAIL:-}" ]; then exit 1; fi ;;
esac
exit 0
'''


def _stubs_json(binp):
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "gh", GH_STUB)
    _exec(binp / "claude", CLAUDE_STUB_JSON)
    _exec(binp / "check.sh", CHECK_STUB)


def _run_dir(tmp, number=5):
    dirs = list((tmp / "drhome" / "runs").glob(f"{number}-*"))
    assert len(dirs) == 1, f"expected exactly one run dir, found {dirs}"
    return dirs[0]


def _usage_files(rundir):
    """Per-stage usage artifacts only — excludes the aggregate usage-summary.json, which is always
    produced (even with zero per-stage artifacts) and is not itself a per-stage artifact."""
    return sorted(p.name for p in rundir.glob("usage-*.json") if p.name != "usage-summary.json")


def test_json_envelope_writes_per_stage_usage_and_rewrites_logs(tmp_path):
    """The JSON-envelope stub case: per-stage usage artifacts are written (fresh input/output/cache
    write/cache read + model + duration), each stage log is rewritten to the plain result text, the
    fail-closed verdict gate still passes on that extracted text, and a usage-summary comment lands
    on the PR after PR create."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Usage capture happy path"), work)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    rd = _run_dir(tmp_path)

    # per-stage artifacts, named for the stage, with exactly the fields the envelope carried
    assert json.loads((rd / "usage-implement.json").read_text()) == {
        "stage": "implement", "model": "claude-sonnet-5", "duration_ms": 600,
        "input_tokens": 61, "output_tokens": 62, "cache_write_tokens": 63, "cache_read_tokens": 64,
    }
    assert json.loads((rd / "usage-test.json").read_text()) == {
        "stage": "test", "model": "claude-sonnet-5", "duration_ms": 400,
        "input_tokens": 41, "output_tokens": 42, "cache_write_tokens": 43, "cache_read_tokens": 44,
    }
    assert json.loads((rd / "usage-review.json").read_text()) == {
        "stage": "review", "model": "claude-opus-4-8", "duration_ms": 200,
        "input_tokens": 21, "output_tokens": 22, "cache_write_tokens": 23, "cache_read_tokens": 24,
    }

    # every existing consumer of the stage log must keep seeing plain, byte-identical-in-shape text:
    # the log is rewritten to EXACTLY the envelope's `result` text (verdict gate still parses it).
    assert (rd / "implement.log").read_text() == "implemented the feature"
    assert (rd / "test.log").read_text() == "wrote tests"
    assert (rd / "review.md").read_text() == "VERDICT: APPROVE"

    # the aggregate rolls up all three stages
    summary = json.loads((rd / "usage-summary.json").read_text())
    assert len(summary["stages"]) == 3
    assert summary["totals"] == {"input_tokens": 61 + 41 + 21, "output_tokens": 62 + 42 + 22,
                                  "cache_write_tokens": 63 + 43 + 23, "cache_read_tokens": 64 + 44 + 24}

    # one usage-summary comment posted on the PR after PR create
    tl = _timeline(tmp_path)
    assert "PRCOMMENT" in tl
    comments = _prcomments(tmp_path)
    assert "### dev-runner usage" in comments
    assert "YR-MERGE" not in comments.split("### dev-runner usage", 1)[1].split("=== PRCOMMENT ===")[0]


def test_plain_text_stub_degrades_no_artifacts_logs_untouched_and_warns(tmp_path):
    """The plain-text stub case (this whole suite's default `claude`): no usage artifacts are written,
    every stage log is left byte-identical to the stub's plain output, the pipeline still goes green
    end to end, and the zero-artifact degrade is logged loudly (never silent)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Plain text degrade"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    rd = _run_dir(tmp_path)

    assert _usage_files(rd) == []                                   # no per-stage artifacts at all
    assert (rd / "review.md").read_text() == "VERDICT: APPROVE\n"   # untouched, byte-identical

    # the loud, visible degrade warning (never silent)
    assert "WARNING" in r.stderr
    assert "zero per-stage usage artifacts" in r.stderr.lower()

    # the aggregate + comment are still produced, just say so
    summary = json.loads((rd / "usage-summary.json").read_text())
    assert summary["stages"] == []
    comments = _prcomments(tmp_path)
    assert "no per-stage usage artifacts" in comments.lower()
    assert "YR-MERGE" not in comments


def test_failed_json_stage_writes_no_usage_and_leaves_log_untouched(tmp_path):
    """Criterion: a stage that FAILED must never get its output captured, even if that output happens
    to be a well-formed envelope — the failure must never be masked by a plausible-looking artifact."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Envelope then fail"), work)
    env["STUB_IMPL_JSON_THEN_FAIL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    rd = _run_dir(tmp_path)
    assert not (rd / "usage-implement.json").exists()
    assert (rd / "implement.log").read_text().strip().startswith('{"type":"result"')   # untouched raw envelope


def test_review_second_round_usage_is_suffixed_not_overwritten(tmp_path):
    """The reviewer can run twice into the same log (blocked, repaired, re-approved): the second
    round's artifact is suffixed rather than overwriting the first, so the summary counts both rounds."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Two review rounds"), work)
    env["STUB_REVIEW_BLOCK"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = _run_dir(tmp_path)
    round1 = json.loads((rd / "usage-review.json").read_text())
    round2 = json.loads((rd / "usage-review-2.json").read_text())
    assert round1["input_tokens"] == 11 and round2["input_tokens"] == 21   # distinct, both present
    summary = json.loads((rd / "usage-summary.json").read_text())
    stages = {r["stage"] for r in summary["stages"]}
    assert "review" in stages and "review-2" in stages
    assert summary["totals"]["input_tokens"] >= 11 + 21   # both rounds counted, not undercounted


def test_default_output_format_is_json_without_verbose(tmp_path):
    """The new default: every stage runs `--output-format json`, deliberately WITHOUT --verbose
    (pairing it with --verbose turns the envelope into a stream array instead of one object)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Default format flags"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    argv = (tmp_path / "claude_argv").read_text().splitlines()
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "--verbose" not in argv


def test_explicit_output_format_env_wins_over_default_and_keeps_old_pairing(tmp_path):
    """An explicitly set CLAUDE_OUTPUT_FORMAT must win over the new json default, verbatim (the old
    stream-json + --verbose pairing) — and no usage capture is attempted on that path at all."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Explicit format override"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CLAUDE_OUTPUT_FORMAT"] = "stream-json"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                     # old behavior: pipeline still goes green
    assert "https://stub/pr/1" in r.stdout
    argv = (tmp_path / "claude_argv").read_text().splitlines()
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    rd = _run_dir(tmp_path)
    assert _usage_files(rd) == []                          # no capture attempted under the override


def test_output_format_override_skips_capture_even_for_envelope_shaped_output(tmp_path):
    """Even when a stage's raw stdout happens to be a well-formed envelope, an explicit
    CLAUDE_OUTPUT_FORMAT override must skip extraction entirely (fmt_overridden) — proving the env
    value truly wins over the new default rather than merely being unexercised."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Override with json-shaped output"), work)
    env["CLAUDE_OUTPUT_FORMAT"] = "stream-json"
    _run(["5", "--repo", "test/repo"], env)   # the run may fail downstream; that's not what's under test
    rd = _run_dir(tmp_path)
    assert _usage_files(rd) == []
    assert (rd / "implement.log").read_text().strip().startswith('{"type":"result"')   # never rewritten


def test_dryrun_json_contract_unchanged_by_usage_capture(tmp_path):
    """Acceptance criterion: usage capture must not change the dry-run JSON contract. Pin the exact
    key set the dry-run has always emitted (tools/registry.py-resolved build/review roles, etc.) —
    no usage-related key must appear."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert set(d) == {"repo", "issue", "branch", "model", "workspace", "base_repo", "base_ref",
                       "check_cmd", "auto_merge", "build", "review", "ready"}


def test_usage_summary_never_collides_with_the_yr_merge_shadow_record(tmp_path):
    """A live test pinning the acceptance criterion exactly: across every PR-comment body posted for
    a run (reviewer verdict, usage summary, terminal merge-shadow record), the string YR-MERGE-SHADOW
    appears EXACTLY once (from the shadow record alone), and the usage comment neither contains
    YR-MERGE anywhere nor opens with any YR- marker line."""
    env = _shadow_env(tmp_path, title="Usage vs shadow marker", checks=[CR_OK])
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    all_comments = _prcomments(tmp_path)
    assert all_comments.count("YR-MERGE-SHADOW") == 1

    rd = _run_dir(tmp_path)
    usage_comment = (rd / "usage-summary.md").read_text()
    assert "YR-MERGE" not in usage_comment
    assert not usage_comment.splitlines()[0].startswith("YR-")
    assert usage_comment.splitlines()[0] == "### dev-runner usage"


# ============ Issue #49: stage context isolation — a stage loads only its job ============
# A cold stage must not inherit the operator's consumer-session surface (user/local-scope settings,
# MCP server configs). Every `run_stage` invocation carries `--setting-sources <sources>
# --strict-mcp-config`, sources defaulting to "project" and overridable via STAGE_SETTING_SOURCES —
# with every other argv element (model, effort, permission mode, allowed tools, system prompt, output
# format) left exactly as it was. STUB_CLAUDE_ARGV_LOG (see CLAUDE_STUB) records one argv per claude
# call, in call order, so every stage's own invocation can be checked — not just the last one.

def _all_stages_env(tmp, binp, title):
    """Drive a run through all five claude -p stage kinds: implement, tester, check-repair
    (STUB_CHECK_FAIL), review + review-repair (STUB_REVIEW_BLOCK)."""
    work, _ = _make_repo(tmp)
    env = _real(tmp, _env(tmp, binp, number=5, title=title), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REVIEW_BLOCK": "1"})
    return env


def test_isolation_flags_on_every_stage_call(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Isolation on every stage")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    # every claude -p stage kind fired: implement, tester, check-repair, review (x2: block, then approve
    # after repair), review-repair.
    for marker in ("IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX"):
        assert marker in tl, f"{marker} stage never ran — can't prove isolation flags on it"

    calls = _argv_calls(tmp_path)
    assert len(calls) >= 5, "expected at least 5 recorded claude invocations (one per stage kind)"
    for i, argv in enumerate(calls):
        assert "--setting-sources" in argv, f"call {i} missing --setting-sources: {argv}"
        assert argv[argv.index("--setting-sources") + 1] == "project", \
            f"call {i} default setting-sources should be 'project': {argv}"
        assert "--strict-mcp-config" in argv, f"call {i} missing --strict-mcp-config: {argv}"


def test_stage_setting_sources_env_overrides_default_on_every_call(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Isolation override on every stage")
    env["STAGE_SETTING_SOURCES"] = "user,project"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    calls = _argv_calls(tmp_path)
    assert len(calls) >= 5
    for i, argv in enumerate(calls):
        assert "--setting-sources" in argv
        assert argv[argv.index("--setting-sources") + 1] == "user,project", \
            f"call {i} did not pick up STAGE_SETTING_SOURCES: {argv}"
        assert "--strict-mcp-config" in argv


def test_isolation_flags_leave_every_other_stage_argument_unchanged(tmp_path):
    """The isolation flags are additive: model, effort, permission mode, allowed tools, and the
    output-format seam must be exactly what they were before, on every stage call."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Isolation preserves other args")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    calls = _argv_calls(tmp_path)
    assert len(calls) >= 5
    for i, argv in enumerate(calls):
        assert "--model" in argv
        assert "--effort" in argv
        assert argv[argv.index("--effort") + 1] == "high"
        assert "--permission-mode" in argv
        assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"
        assert "--append-system-prompt" in argv
        assert "--allowedTools" in argv
        assert "--output-format" in argv
        assert argv[argv.index("--output-format") + 1] == "json"
        assert "--verbose" not in argv


def test_isolation_flags_present_on_plain_happy_path_single_stage_chain(tmp_path):
    """No repairs needed: implement -> tester -> check -> review, still carries the isolation flags
    on each of those three claude calls (implement, tester, review)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Isolation happy path"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert tl.index("IMPL") < tl.index("TEST") < tl.index("REVIEW")

    calls = _argv_calls(tmp_path)
    assert len(calls) == 3   # implement, tester, review — no repairs fired
    for argv in calls:
        assert "--setting-sources" in argv and argv[argv.index("--setting-sources") + 1] == "project"
        assert "--strict-mcp-config" in argv


# ============ Issue #58: loud staleness warning when the deployed factory is behind its origin/main ==
# The FACTORY's own checkout (FACTORY_DIR, default SELF_DIR/..) can drift behind ITS origin/main
# independently of the target repo being built — a stale deployment silently building current code.
# Visibility only: one loud `log` line in the run log, and one additive PR comment naming the commit
# count, when behind; total silence when current; a silent skip when the freshness check itself can't
# run (offline/no origin) — never a gate, never a Blocked/failure outcome.

def test_staleness_warning_names_commits_behind_in_log_and_pr_comment(tmp_path):
    """Acceptance: a factory behind its own origin/main by N commits gets one loud warning in the run
    log AND on the PR, naming N — without blocking or otherwise altering the build."""
    work, _ = _make_repo(tmp_path)
    factory = _make_factory_repo(tmp_path, behind=3)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Stale factory deployment"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["FACTORY_DIR"] = str(factory)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout                     # the build was never blocked/delayed
    assert "WARNING" in r.stderr
    assert "3 commit" in r.stderr and "behind" in r.stderr.lower()
    comments = _prcomments(tmp_path)
    assert "staleness" in comments.lower()
    assert "3 commit" in comments


def test_no_staleness_output_when_factory_checkout_is_current(tmp_path):
    """Acceptance: while the deployed factory checkout is current, no staleness output appears anywhere
    (run log or PR)."""
    work, _ = _make_repo(tmp_path)
    factory = _make_factory_repo(tmp_path, behind=0)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Current factory deployment"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["FACTORY_DIR"] = str(factory)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "commit(s) behind" not in r.stderr
    assert "staleness warning" not in _prcomments(tmp_path).lower()
    assert "commit(s) behind" not in _prcomments(tmp_path)


def test_freshness_check_fetch_failure_skips_silently_build_unaffected(tmp_path):
    """Acceptance: if the freshness check itself cannot run (here: FACTORY_DIR has no `origin` to fetch
    from), it is skipped silently — no warning anywhere — and the build proceeds and completes exactly
    as if the check had never run."""
    work, _ = _make_repo(tmp_path)
    unreachable = tmp_path / "not_a_git_repo"; unreachable.mkdir()  # fetch fails immediately, no network
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Offline freshness check"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["FACTORY_DIR"] = str(unreachable)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                          # the build is unaffected
    assert "https://stub/pr/1" in r.stdout
    assert "commit(s) behind" not in r.stderr
    assert "staleness warning" not in _prcomments(tmp_path).lower()


def test_staleness_comment_clear_of_merge_grammar_alongside_a_shadow_record(tmp_path):
    """Acceptance: the staleness comment stays clear of every parsed comment grammar — no `YR-` marker
    line, no `YR-MERGE` string anywhere — proven live alongside a shadow terminal-merge run so the
    YR-MERGE-SHADOW marker still appears EXACTLY once (the staleness comment must not add a second, and
    must not itself open with a `YR-` marker)."""
    factory = _make_factory_repo(tmp_path, behind=2)
    env = _shadow_env(tmp_path, title="Staleness vs shadow grammar", checks=[CR_OK])
    env["FACTORY_DIR"] = str(factory)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    all_comments = _prcomments(tmp_path)
    assert all_comments.count("YR-MERGE-SHADOW") == 1
    blocks = all_comments.split("=== PRCOMMENT ===")
    stale_blocks = [b for b in blocks if "staleness" in b.lower()]
    assert len(stale_blocks) == 1, "expected exactly one staleness comment on the PR"
    stale_comment = stale_blocks[0].strip()
    assert "YR-MERGE" not in stale_comment
    assert not stale_comment.splitlines()[0].startswith("YR-")


def test_self_build_reads_behind_count_without_double_fetch_or_error(tmp_path):
    """When BASE_REPO IS the factory's own checkout (the factory building itself), the freshness check
    must not fetch a second time or error — the target-repo fetch already refreshed origin/main there,
    and reading the count directly must not disturb the (silent, current) happy path."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Factory builds itself"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["FACTORY_DIR"] = str(work)          # same repo as BASE_REPO
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert "commit(s) behind" not in r.stderr   # BASE_REPO/FACTORY_DIR are the same, already-fetched repo


# ============ Issue #50: stage charter — every stage knows its walls, in every repo ============
# Every stage the runner spawns (in every target repo, not just the factory's own) must get one shared
# confinement contract appended to its system prompt, so a stage building a foreign repo — which carries
# none of this knowledge itself — still knows the walls it runs inside. The three role prompts
# (IMPL_SYS/TEST_SYS/REVIEW_SYS) are expected to shed the clauses the charter now states once, globally.
#
# Hard constraint: the stage-aware stub above routes on four CASE-SENSITIVE literals — TESTER, REVIEWER,
# "tests FAIL", "REQUESTED CHANGES". A literal leaked into the wrong stage's argv (e.g. via a careless
# shared charter) misroutes the stub and silently corrupts every stage-order assertion in this whole
# suite — so exclusivity is checked explicitly here, live, not just inferred from the rest passing.

ROUTED_LITERALS = ["TESTER", "REVIEWER", "tests FAIL", "REQUESTED CHANGES"]


def _shell_var(name):
    """The literal value assigned to a single-line shell string variable in the runner source (e.g.
    `STAGE_CHARTER="..."`). Used, per the task's own rebuild note, to reconstruct the expected appended
    system prompt (`role + "\\n\\n" + charter`) straight from the shell variables and compare it
    byte-for-byte against what each stage actually sent to `claude` — not a paraphrase of it."""
    src = RUNNER.read_text()
    m = re.search(rf'(?m)^{name}="(.*)"$', src)
    assert m, f"could not find a single-line shell assignment for {name} in {RUNNER}"
    return m.group(1)


def _argv_raw_calls(tmp):
    """Every `claude` invocation's raw argv text, embedded newlines preserved (unlike _argv_calls',
    which flattens on every newline) — needed because the appended system prompt itself spans multiple
    lines (role prompt, blank line, charter)."""
    p = tmp / "claude_argv_log"
    if not p.exists():
        return []
    chunks = p.read_text().split("===STUB-CALL===\n")
    return [c for c in chunks if c]


def _extract_append_system_prompt(raw_call):
    """Pull the exact `--append-system-prompt` value out of one raw call's text. `--allowedTools`
    always immediately follows it in run_stage's args array, and that literal never appears inside any
    role prompt or the charter, so the span between the two is the exact value passed to `claude`."""
    m = re.search(r'--append-system-prompt\n(.*?)\n--allowedTools\n', raw_call, re.S)
    assert m, f"could not find --append-system-prompt in call:\n{raw_call}"
    return m.group(1)


def _stdin_raw_calls(tmp):
    """Every `claude` invocation's raw STDIN content, in call order — issue #121's task-prompt channel
    (role instruction + SPEC), byte-exact. Parsed off explicit BEGIN/END markers (rather than the
    ===STUB-CALL=== boundary the argv log uses) since the content itself is free-form and may contain
    embedded blank lines right up against a call boundary."""
    p = tmp / "claude_stdin_log"
    if not p.exists():
        return []
    return re.findall(r'===STUB-STDIN-BEGIN===\n(.*?)\n===STUB-STDIN-END===\n', p.read_text(), re.S)


def _stage_calls(tmp):
    """Every recorded `claude` call, grouped by which stage fired it — paired positionally with the
    timeline's stage markers (IMPL/TEST/REPAIR/REVIEW/REVIEWFIX), which fire in the same order as the
    claude invocations they came from (one timeline entry per claude call, every stub branch here).
    Each call's text is argv + stdin combined (issue #121 moved the task prompt off argv onto stdin, so
    a literal that only ever lived in the task prompt — e.g. check-repair's "tests FAIL" — is only found
    by searching both channels together)."""
    tl = [l for l in _timeline(tmp) if l in ("IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX")]
    argv_calls = _argv_raw_calls(tmp)
    assert len(tl) == len(argv_calls), (tl, len(argv_calls))
    stdin_calls = _stdin_raw_calls(tmp)
    if stdin_calls:
        assert len(stdin_calls) == len(argv_calls), (len(stdin_calls), len(argv_calls))
        calls = [f"{a}\n{s}" for a, s in zip(argv_calls, stdin_calls)]
    else:
        calls = argv_calls
    out = {}
    for stage, call in zip(tl, calls):
        out.setdefault(stage, []).append(call)
    return out


def _stdin_stage_calls(tmp):
    """Like `_stage_calls`, but each call is its raw STDIN content ALONE (no argv folded in) — for
    assertions that care specifically about what did/didn't travel on which channel."""
    tl = [l for l in _timeline(tmp) if l in ("IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX")]
    calls = _stdin_raw_calls(tmp)
    assert len(tl) == len(calls), (tl, len(calls))
    out = {}
    for stage, call in zip(tl, calls):
        out.setdefault(stage, []).append(call)
    return out


def test_stage_charter_itself_is_free_of_stub_routing_literals():
    """Acceptance: the charter is kept free of the four stub routing literals (their uppercase routed
    forms — the stub's matching is case-sensitive) — checked directly against the charter text alone,
    independent of any particular run."""
    charter = _shell_var("STAGE_CHARTER")
    for literal in ROUTED_LITERALS:
        assert literal not in charter, f"stage charter must not contain the routed literal {literal!r}"


def test_existing_stub_marker_pin_still_passes():
    """The existing presence pin (test_runner_prompts_contain_stub_markers) must stay green, unedited,
    alongside the new charter work — re-run its exact assertions here as a belt-and-braces check that
    this test module didn't have to touch it to make the suite pass."""
    src = RUNNER.read_text()
    assert "TESTER" in src and "REVIEWER" in src
    assert "tests FAIL" in src and "REQUESTED CHANGES" in src


def test_routing_literals_appear_only_in_their_own_stage_argv(tmp_path):
    """Acceptance: each of the four routed literals appears in exactly its own stage's argv and no
    other stage's — proven live across a run that fires all five stage kinds (implement, tester,
    check-repair, review x2, review-repair)."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Routing literal exclusivity")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    by_stage = _stage_calls(tmp_path)
    assert set(by_stage) >= {"IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX"}

    owner = {"TESTER": "TEST", "REVIEWER": "REVIEW", "tests FAIL": "REPAIR", "REQUESTED CHANGES": "REVIEWFIX"}
    for literal, own_stage in owner.items():
        for stage, calls in by_stage.items():
            for call in calls:
                if stage == own_stage:
                    assert literal in call, f"{literal!r} missing from its own stage {stage}'s argv"
                else:
                    assert literal not in call, \
                        f"{literal!r} (owned by {own_stage}) leaked into stage {stage}'s argv"


def test_charter_appended_to_every_stage_and_states_required_clauses(tmp_path):
    """Acceptance: every stage the runner spawns gets one stage charter appended to its system prompt,
    stating: one stage of an automated pipeline in one fresh worktree; builder != verifier with the
    three roles' separation; worktree-only writes; no git or board writes (the reviewer's read-only git
    excepted); tests derived from the acceptance criteria; gates never weakened; Blocked as a correct
    outcome; PRs only, never deploy or host work."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Charter on every stage")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    by_stage = _stage_calls(tmp_path)
    assert set(by_stage) >= {"IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX"}

    required_clauses = [
        "one stage",                              # one stage of an automated pipeline
        "automated pipeline",
        "fresh worktree",                          # in one fresh worktree
        "implementer", "tester", "reviewer",       # the three roles' separation
        "write only inside this worktree",          # worktree-only writes
        "no git or board writes",                   # no git or board writes
        "read-only git",                             # the reviewer's read-only git carve-out
        "derived from the acceptance criteria",     # tests derived from the acceptance criteria
        "never weaken a gate",                       # gates never weakened
        "blocked run is a correct outcome",          # Blocked as a correct outcome
        "pull request only",                          # PRs only
        "deploy",                                     # never deploy or host work
        "targeted tests",                             # in-stage verification is scoped, targeted
        "full check suite",                            # the full suite belongs to the check gate/CI
        "foreground",                                  # a stage works in the foreground only
        "never poll",                                  # never polls/watches/sleeps on external state
        "self-contained",                              # the task slice is self-contained by design
        "standing documents",                          # standing documents are not context
    ]
    for stage, calls in by_stage.items():
        for call in calls:
            prompt = _extract_append_system_prompt(call).lower()
            for clause in required_clauses:
                assert clause in prompt, f"stage {stage} missing charter clause {clause!r}"


def test_stage_charter_append_is_byte_exact_role_then_blank_line_then_charter(tmp_path):
    """Acceptance (rebuild note): the append is byte-exact — role prompt, then exactly one blank line,
    then the charter, with no stray trailing whitespace/newline after the role prompt and none leading
    the charter. Reconstruct `role + "\\n\\n" + charter` from the shell variables themselves and compare
    it byte-for-byte against what each stage actually sent to `claude` (the prior build's regression:
    a stray trailing newline/whitespace on the role prompt broke exactly this comparison)."""
    charter = _shell_var("STAGE_CHARTER")
    impl_sys = _shell_var("IMPL_SYS")
    test_sys = _shell_var("TEST_SYS")
    review_sys = _shell_var("REVIEW_SYS")

    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Byte-exact charter append")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    by_stage = _stage_calls(tmp_path)

    # repair stages (check-repair, review-repair) run at the IMPL_SYS role, same as the implementer.
    expected_role = {
        "IMPL": impl_sys, "REPAIR": impl_sys, "REVIEWFIX": impl_sys,
        "TEST": test_sys, "REVIEW": review_sys,
    }
    for stage, role_text in expected_role.items():
        for call in by_stage[stage]:
            actual = _extract_append_system_prompt(call)
            assert actual == f"{role_text}\n\n{charter}", \
                f"stage {stage}: appended system prompt is not exactly role + blank line + charter"


def test_tester_production_code_ban_and_reviewer_verdict_protocol_pinned(tmp_path):
    """Acceptance: the tester's operative production-code ban stays inside the tester prompt, and the
    reviewer's verdict protocol stays byte-exact (unrelated to the git-ban clause the charter absorbed)."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Ban and verdict protocol pinned")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    by_stage = _stage_calls(tmp_path)

    for call in by_stage["TEST"]:
        prompt = _extract_append_system_prompt(call)
        assert "Do NOT modify production code — only add or extend tests." in prompt

    verdict_protocol = (
        "Tag each finding 'blocker' or 'nit'. Do NOT modify any files. "
        "End your reply with a final line that is exactly 'VERDICT: APPROVE' "
        "if there are zero blockers, or 'VERDICT: REQUEST_CHANGES' otherwise."
    )
    for call in by_stage["REVIEW"]:
        prompt = _extract_append_system_prompt(call)
        assert verdict_protocol in prompt, "reviewer verdict protocol is not byte-exact"


def test_repair_prompt_templates_unchanged(tmp_path):
    """Acceptance: the repair prompt templates (check-repair, review-repair) are left untouched — their
    literals are load-bearing stub routing, unrelated to the charter dedupe (they're task prompts, not
    the shared role/charter system prompt). The check-repair prompt gained one appended sentence scoping
    the repair to the failing tests and noting the runner re-runs the full check suite afterward; that
    sentence must survive intact and the pinned routing fragment must stay contiguous around it."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Repair templates unchanged")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    by_stage = _stage_calls(tmp_path)

    check_repair_fragment = "The project tests FAIL. Fix the PRODUCTION CODE so they pass — do NOT modify the tests."
    check_repair_scoping = "Reproduce with the failing tests only; the runner re-runs the full check suite after this stage."
    for call in by_stage["REPAIR"]:
        assert check_repair_fragment in call
        assert check_repair_scoping in call

    review_repair_fragment = ("A reviewer REQUESTED CHANGES. Fix the blocking findings "
                               "(production code; only touch a test if the test itself is wrong).")
    for call in by_stage["REVIEWFIX"]:
        assert review_repair_fragment in call


# ============ Issue #121: SPEC via stdin, per-stage process-group reap, signal-terminated legibility ==
# `run_stage` used to pass the whole task prompt as a `claude -p "$SPEC"` argv value — a task whose body
# quotes a runnable string could pattern-match the stage's own command line (gilda#9 run 9-4131516: a
# `pkill -f "bash qa/qa-gate.sh"` self-hit its own argv, signal-terminating the harness with a zero-byte
# implement.log). Three independent repairs: (1) the task prompt now travels on stdin, never argv; (2)
# each stage runs as the leader of its own process group and that group is reaped before the next stage
# starts, so a stray child never survives into the next attempt; (3) a signal-terminated stage (empty
# log) gets a Blocked record naming the exit code and pointing at the preserved session transcript,
# rather than only the empty log file.

def test_task_prompt_delivered_via_stdin_byte_exact(tmp_path):
    """Acceptance: the task prompt (role instruction + full issue SPEC) is delivered to the stage CLI
    over stdin, byte-for-byte — the same text that used to travel as the `-p` positional argv value, with
    no added/stripped whitespace (a stray trailing newline from the delivery mechanism would break this
    exact comparison, same rebuild-note class as the charter's byte-exact append)."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Byte exact stdin delivery")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    # The delivered SPEC carries no trailing newline: `run_stage`'s SPEC is built with a command
    # substitution (`SPEC="$(printf ... "$BODY")"`), which strips trailing newlines — so the byte-exact
    # task prompt ends at the last acceptance-criterion character, exactly as the argv `-p` value did.
    spec = "GitHub issue #5: Byte exact stdin delivery\n\n### Acceptance criteria\n- [ ] it works"
    expected = {
        "IMPL": f"Implement the task below against its acceptance criteria. Make the minimal, clean change.\n\n{spec}",
        "TEST": f"Write tests that verify the acceptance criteria below.\n\n{spec}",
    }
    stdin_calls = _stdin_stage_calls(tmp_path)
    for stage, text in expected.items():
        assert stdin_calls[stage][0] == text, f"stage {stage}: stdin task prompt is not byte-exact"


def test_task_prompt_absent_from_own_command_line(tmp_path):
    """Acceptance: a task whose body quotes a runnable string — here the exact
    `pkill -f "bash qa/qa-gate.sh"` string that self-matched the harness's own argv in gilda#9 run
    9-4131516 — must never appear on any stage's own command line (argv); it must still reach the stage,
    but only over stdin."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    body = ('### Acceptance criteria\n'
            '- [ ] kill any stray process with `pkill -f "bash qa/qa-gate.sh"`\n')
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Argv self-match trap", body=body), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    argv_calls = _argv_raw_calls(tmp_path)
    assert argv_calls, "expected at least one recorded claude call"
    for call in argv_calls:
        assert "pkill -f" not in call, "the task text leaked onto a stage's own command line (argv)"

    stdin_calls = _stdin_raw_calls(tmp_path)
    assert any("pkill -f" in call for call in stdin_calls), \
        "the task text must still reach the stage — on stdin, never on argv"


REAP_CLAUDE_STUB = r'''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\n'"$stdin_content"
case "$args" in
  *TESTER*)
    echo TEST >> "$STUB_TIMELINE"
    child_pid="$(cat "$STUB_LINGER_PIDFILE" 2>/dev/null)"
    if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
      echo LINGERING >> "$STUB_TIMELINE"
    fi ;;
  *REVIEWER*)
    # The reviewer must approve so the run reaches rc=0 and the reap assertion (no LINGERING) can gate;
    # without this branch a REVIEWER call falls to the IMPL default, never emits a verdict, and the run
    # blocks independent of the reap fix under test.
    echo REVIEW >> "$STUB_TIMELINE"
    echo "VERDICT: APPROVE" ;;
  *)
    echo IMPL >> "$STUB_TIMELINE"
    [ -n "${STUB_CLAUDE_CHANGE:-}" ] && printf 'hello\n' > feature.txt
    ( exec sleep 5 ) &
    echo $! > "$STUB_LINGER_PIDFILE" ;;
esac
exit 0
'''


def test_process_group_reap_kills_lingering_child_before_next_stage(tmp_path):
    """Acceptance: a stage's stray background child (the class that motivated the fatal `pkill` cleanup
    in gilda#9 run 9-4131516 — a leftover Playwright run from an EARLIER attempt) must be dead before the
    NEXT stage starts. The implement stub backgrounds a `sleep`, exits immediately without waiting on it,
    and records its pid; the tester stub — the very next stage to run — checks that pid the moment IT
    starts and would mark the timeline LINGERING if it were still alive."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "gh", GH_STUB)
    _exec(binp / "claude", REAP_CLAUDE_STUB)
    _exec(binp / "check.sh", CHECK_STUB)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Reap lingering child"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_LINGER_PIDFILE"] = str(tmp_path / "linger.pid")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert tl.index("IMPL") < tl.index("TEST")
    assert "LINGERING" not in tl, "the implementer's stray child was still alive when the tester stage started"


SIGNAL_CLAUDE_STUB = '''#!/usr/bin/env bash
cat >/dev/null
kill -KILL $$
'''


def test_signal_terminated_stage_blocked_record_names_exit_code_and_transcript(tmp_path):
    """Acceptance: a stage terminated by a signal before it writes anything (an empty log — the exact
    shape of gilda#9 run 9-4131516's zero-byte implement.log) must produce a Blocked record that states
    the numeric exit code, names signal termination as the likely class, and points at the preserved
    session transcript — never a record naming only the empty log file."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "gh", GH_STUB)
    _exec(binp / "claude", SIGNAL_CLAUDE_STUB)
    _exec(binp / "check.sh", CHECK_STUB)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Signal terminated implementer"), work)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0

    rundirs = list((tmp_path / "drhome" / "runs").glob("5-*"))
    assert len(rundirs) == 1
    log = rundirs[0] / "implement.log"
    assert log.exists() and log.stat().st_size == 0            # the zero-byte mystery this record closes

    assert "137" in r.stderr                                    # 128+9 (SIGKILL): the exit code, stated
    assert "signal-terminated" in r.stderr.lower()
    assert "transcript" in r.stderr.lower()

    tl = _timeline(tmp_path)
    edits = " ".join(_edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits
    comments = " ".join(_comments(tl))
    assert "137" in comments and "signal-terminated" in comments.lower()


# ============ Issue #116: build-pipeline (implement -> review) gate-pass-count pins ============
# The check command (CHECK_STUB, timestamped "CHECK" on the shared timeline) is the repo's full check
# suite — the same one the deterministic check gate and server CI run. Repair choreography must not
# silently multiply how often it fires: a clean build runs it once; a check-repair round adds exactly
# one re-run; a review-repair round (tools/dev-runner.sh:837) adds exactly one re-run of its own; both
# rounds together add both. These are the build pipeline's own gate passes — the armed merge path's
# freshness re-green (rebase, then one more gate pass, tools/dev-runner.sh:1012-1029) is a separate,
# out-of-scope concern and is not exercised or asserted against here.

def test_gate_pass_count_clean_build_invokes_check_once(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Clean build gate pass count"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _timeline(tmp_path).count("CHECK") == 1


def test_gate_pass_count_check_repair_round_invokes_check_twice(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Check repair round gate pass count"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _timeline(tmp_path).count("CHECK") == 2


def test_gate_pass_count_review_repair_round_invokes_check_twice(tmp_path):
    """A review-repair round adds its own re-check (tools/dev-runner.sh:837) even though the check gate
    itself passed clean the first time — so this scenario's count is 2, not 1."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Review repair round gate pass count"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _timeline(tmp_path).count("CHECK") == 2


def test_gate_pass_count_both_repair_rounds_invokes_check_three_times(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Both repair rounds gate pass count")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _timeline(tmp_path).count("CHECK") == 3


# ============ Issue #84: PR-stage remote writes (push / pr create) survive transients ============
# `git push` and `gh pr create` each get PR_STAGE_ATTEMPTS (= PR_STAGE_RETRIES + 1) attempts with
# exponential backoff before falling back to the SAME preserve+resume environmental hold as the check
# gate / quota holds (env_hold_record) — never cleanup_wt. A custom GIT_BIN wrapper intercepts only the
# `push` subcommand (forwarding everything else through to the real `git`), driven by STUB_PUSH_* env
# vars so a transient vs. persistent failure is deterministic and needs no real network. A custom GH_BIN
# stub adds controllable `pr list`/`pr create` behavior (STUB_PRCREATE_*) on top of the existing GH_STUB
# shape, so the branch's existing-open-PR reuse path (find_open_pr) is exercised the same way. Backoff
# delays are zeroed in most tests (a real `sleep 0` is instant) except the dedicated knob test, which
# intercepts `sleep` itself via a PATH stub to assert the requested delays without ever really waiting.
# `_state_dir`/`_wt_dir`/`_run_dirs` are the issue #39 section's helpers above, reused as-is.

GIT_PUSH_WRAPPER = '''#!/usr/bin/env bash
is_push=0
for a in "$@"; do [ "$a" = "push" ] && is_push=1; done
if [ "$is_push" = "1" ]; then
  [ -n "${STUB_PUSH_ARGV_LOG:-}" ] && printf '%s\\n' "$*" >> "$STUB_PUSH_ARGV_LOG"
  n=0
  if [ -n "${STUB_PUSH_COUNTER:-}" ] && [ -f "$STUB_PUSH_COUNTER" ]; then n=$(cat "$STUB_PUSH_COUNTER"); fi
  n=$((n + 1))
  [ -n "${STUB_PUSH_COUNTER:-}" ] && printf '%s' "$n" > "$STUB_PUSH_COUNTER"
  fail_count="${STUB_PUSH_FAIL_COUNT:-0}"
  if [ "$fail_count" = "always" ] || [ "$n" -le "$fail_count" ]; then
    echo "${STUB_PUSH_ERR:-stub push error: connection reset by peer}" >&2
    exit 1
  fi
fi
exec git "$@"
'''

# Extends the base GH_STUB with controllable `pr list` (find_open_pr) / `pr create` behavior. Everything
# else (issue view/comment, project item-list/item-edit, pr comment/view) is identical to GH_STUB.
GH_STUB_PR = '''#!/usr/bin/env bash
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
  pr)
    case "$2" in
      list)
        if [ -n "${STUB_PR_EXISTS_FILE:-}" ] && [ -f "$STUB_PR_EXISTS_FILE" ]; then
          printf '[{"url": "%s"}]' "$(cat "$STUB_PR_EXISTS_FILE")"
        else
          printf '[]'
        fi ;;
      create)
        printf 'CALL\\n' >> "${STUB_PRCREATE_CALLS:-/dev/null}"
        n=0
        if [ -n "${STUB_PRCREATE_COUNTER:-}" ] && [ -f "$STUB_PRCREATE_COUNTER" ]; then n=$(cat "$STUB_PRCREATE_COUNTER"); fi
        n=$((n + 1))
        [ -n "${STUB_PRCREATE_COUNTER:-}" ] && printf '%s' "$n" > "$STUB_PRCREATE_COUNTER"
        fail_count="${STUB_PRCREATE_FAIL_COUNT:-0}"
        if [ "$fail_count" = "always" ] || [ "$n" -le "$fail_count" ]; then
          if [ -n "${STUB_PRCREATE_MARKS_EXISTING:-}" ] && [ -n "${STUB_PR_EXISTS_FILE:-}" ]; then
            echo "https://stub/pr/1" > "$STUB_PR_EXISTS_FILE"
          fi
          echo "${STUB_PRCREATE_ERR:-stub pr create error: timeout}" >&2
          exit 1
        fi
        echo "https://stub/pr/1" ;;
      comment) echo PRCOMMENT >> "$STUB_TIMELINE"
               if [ -n "${STUB_PRCOMMENTS:-}" ]; then
                 __p=""; __bf=""; __body=""
                 for __a in "$@"; do
                   [ "$__p" = "--body-file" ] && __bf="$__a"
                   [ "$__p" = "--body" ] && __body="$__a"
                   __p="$__a"
                 done
                 [ -n "$__bf" ] && { echo "=== PRCOMMENT ==="; cat "$__bf"; } >> "$STUB_PRCOMMENTS"
                 [ -n "$__body" ] && { echo "=== PRCOMMENT ==="; printf '%s\\n' "$__body"; } >> "$STUB_PRCOMMENTS"
               fi ;;
      view)    if [ -n "${STUB_ROLLUP_JSON:-}" ]; then cat "$STUB_ROLLUP_JSON"
               else printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1"; fi ;;
      *)       printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1" ;;
    esac ;;
  *)  echo "unhandled gh $*" >&2; exit 9 ;;
esac
'''

SLEEP_STUB = '''#!/usr/bin/env bash
[ -n "${STUB_SLEEP_LOG:-}" ] && printf '%s\\n' "$1" >> "$STUB_SLEEP_LOG"
exit 0
'''


def _raw_timeline(tmp):
    """The full timeline file, unsplit — the PR-stage hold's issue comment (unlike every earlier hold's)
    embeds real newlines/backticks (the stderr tail), so a substring like the stderr text or the
    ENVIRONMENTAL marker can land on a continuation line that `_comments()`'s line-prefix filter would
    miss; a raw substring search over the whole file finds it regardless of which physical line it's on."""
    p = tmp / "timeline"
    return p.read_text() if p.exists() else ""


def _pr_stage_env(tmp_path, binp, work, *, number=5, title="PR stage transient", fast=True):
    """`_real`'s base env, plus the retrying-git wrapper as GIT_BIN and (if `fast`) zeroed backoff knobs
    so these tests never wait for real — a bare `sleep 0` returns immediately."""
    env = _real(tmp_path, _env(tmp_path, binp, number=number, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    git_wrapper = _exec(binp / "git-push-wrapper.sh", GIT_PUSH_WRAPPER)
    env["GIT_BIN"] = str(git_wrapper)
    if fast:
        env["PR_STAGE_BACKOFF_BASE"] = "0"
        env["PR_STAGE_BACKOFF_FACTOR"] = "1"
        env["PR_STAGE_BACKOFF_MAX"] = "0"
    return env


def _fail_all_commits(work):
    """Install a pre-commit hook that always refuses — standing in for a failure IN the commit step
    itself (distinct from the empty-diff 'no changes produced' guard ahead of it), which the PR stage
    leaves uncaught exactly as before issue #84: no `|| fail_blocked` wraps the commit call, only the
    remote writes below it gained the retry/hold machinery."""
    hook = work / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/usr/bin/env bash\necho 'stub: pre-commit hook refuses' >&2\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_pr_stage_push_retries_then_succeeds_no_hold(tmp_path):
    """Criterion 1: a push that fails twice then succeeds completes the PR stage normally — one PR opened,
    the retry count visible in the run's log, never a force-push on any attempt — and records no
    environmental hold (state cleared, worktree torn down, stage order and Reason unaffected)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Push retries then succeeds")
    env.update({
        "STUB_PUSH_FAIL_COUNT": "2",
        "STUB_PUSH_COUNTER": str(tmp_path / "push_counter"),
        "STUB_PUSH_ARGV_LOG": str(tmp_path / "push_argv"),
        "STUB_PUSH_ERR": "stub: connection reset by peer",
    })
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert (tmp_path / "push_counter").read_text() == "3"            # 2 failures + 1 success
    assert "attempt 1/4 failed" in r.stderr and "attempt 2/4 failed" in r.stderr
    assert "succeeded on attempt 3/4 (2 retries)" in r.stderr         # retry count visible in the log
    argv_lines = (tmp_path / "push_argv").read_text().splitlines()
    assert len(argv_lines) == 3
    assert all("force" not in l for l in argv_lines)                 # never a force-push, on any attempt
    assert _state_dir(tmp_path) is None                               # no hold recorded
    assert _wt_dir(tmp_path) is None                                  # torn down normally
    tl = _timeline(tmp_path)
    assert "Blocked" not in " ".join(_edits(tl))
    assert tl.index("IMPL") < tl.index("TEST") < tl.index("CHECK") < tl.index("REVIEW")   # stage order intact
    assert "Environmental hold" not in r.stderr                          # no PR-stage hold fired


def test_pr_stage_default_retries_at_least_three_beyond_first_attempt(tmp_path):
    """Criterion 2 (default floor): with PR_STAGE_RETRIES left at its default (unset), 3 straight failures
    still leave one more attempt to succeed on — the default is at least 3 retries beyond the first."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Default retry floor")
    env.update({"STUB_PUSH_FAIL_COUNT": "3", "STUB_PUSH_COUNTER": str(tmp_path / "push_counter")})
    assert "PR_STAGE_RETRIES" not in env
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert (tmp_path / "push_counter").read_text() == "4"            # 3 failures + 1 success, within the default


def test_pr_stage_push_exhausts_retries_records_environmental_hold(tmp_path):
    """Criterion 3: a persistently-failing push exhausts retries and falls back to the SAME preserve+
    resume core as the check gate's env_hold — hold marker + resume manifest written, Reason=Blocked, a
    comment carrying an ENVIRONMENTAL marker and the final attempt's captured stderr, worktree/branch/
    state preserved (no teardown), non-zero exit."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Push exhausts retries")
    env.update({"STUB_PUSH_FAIL_COUNT": "always", "STUB_PUSH_ERR": "stub: DNS resolution failed for github.com"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout                       # no PR ever opened
    wt = _wt_dir(tmp_path); assert wt is not None and wt.exists()     # preserved, not torn down
    sd = _state_dir(tmp_path); assert sd is not None
    assert (sd / "env-hold").exists()
    rj = json.loads((sd / "run.json").read_text())
    assert rj["branch"] == "task/5-push-exhausts-retries"
    assert (sd / "05-commit.done").exists()                          # commit stage completed before push failed
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))
    raw = _raw_timeline(tmp_path)
    assert "ENVIRONMENTAL" in raw
    assert "stub: DNS resolution failed for github.com" in raw       # final attempt's stderr tail
    assert "push" in raw.lower()


def test_pr_stage_relaunch_after_push_hold_resumes_at_pr_stage(tmp_path):
    """Criterion 4: a relaunch after a push-exhaustion hold reuses the preserved worktree/branch and
    re-enters directly at the PR stage — implement/test/check/review are NOT re-run."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Push hold then resume")
    env["STUB_PUSH_FAIL_COUNT"] = "always"
    r1 = _run(["5", "--repo", "test/repo"], env)
    assert r1.returncode != 0
    wt1 = _wt_dir(tmp_path); assert wt1 is not None

    env2 = {**env, "STUB_TIMELINE": str(tmp_path / "timeline2")}
    env2.pop("STUB_PUSH_FAIL_COUNT")                                  # the transient clears; push now succeeds
    r2 = _run(["5", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr
    assert "https://stub/pr/1" in r2.stdout
    tl2 = (tmp_path / "timeline2").read_text().splitlines() if (tmp_path / "timeline2").exists() else []
    assert "IMPL" not in tl2 and "TEST" not in tl2 and "CHECK" not in tl2 and "REVIEW" not in tl2
    assert "reusing preserved env-hold worktree" in r2.stderr
    assert str(wt1) in r2.stderr
    assert "resume: skipping commit (05-commit.done present)" in r2.stderr
    assert _state_dir(tmp_path) is None                               # successful resume clears state...
    assert _wt_dir(tmp_path) is None                                  # ...and tears the worktree down again


def test_pr_stage_pr_create_reuses_existing_pr_on_retry_no_duplicate(tmp_path):
    """Criterion 5 (idempotent create): a `pr create` that fails to report back (as if the branch's PR
    was created server-side but the acknowledgment was lost) is not retried into a duplicate — the next
    attempt's existence check (`pr list --head`) finds it and reuses it instead of creating again."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="PR create reuse on retry")
    _exec(binp / "gh", GH_STUB_PR)
    env.update({
        "STUB_PRCREATE_FAIL_COUNT": "1",
        "STUB_PRCREATE_MARKS_EXISTING": "1",
        "STUB_PR_EXISTS_FILE": str(tmp_path / "pr_exists"),
        "STUB_PRCREATE_CALLS": str(tmp_path / "prcreate_calls"),
        "STUB_PRCREATE_ERR": "stub: timeout waiting for GitHub API",
    })
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    calls = (tmp_path / "prcreate_calls").read_text().splitlines()
    assert len(calls) == 1                                           # `gh pr create` invoked exactly once
    assert "pr create succeeded on attempt 2/4 (1 retry)" in r.stderr
    assert _state_dir(tmp_path) is None                               # success, no hold


def test_pr_stage_pr_create_exhausts_retries_records_environmental_hold(tmp_path):
    """The pr-create branch of the same fallback: retries exhausted on `gh pr create` (push itself
    succeeded first try, isolating this path) records the same environmental hold as the push branch —
    preserved worktree/state, Reason=Blocked, an ENVIRONMENTAL comment naming the failed step and
    carrying the captured stderr."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="PR create exhausts retries")
    _exec(binp / "gh", GH_STUB_PR)
    env.update({
        "STUB_PRCREATE_FAIL_COUNT": "always",
        "STUB_PRCREATE_ERR": "stub: 502 Bad Gateway",
        "STUB_PRCREATE_CALLS": str(tmp_path / "prcreate_calls"),
    })
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    wt = _wt_dir(tmp_path); assert wt is not None and wt.exists()
    sd = _state_dir(tmp_path); assert sd is not None
    assert (sd / "env-hold").exists()
    assert (sd / "05-commit.done").exists()
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))
    raw = _raw_timeline(tmp_path)
    assert "ENVIRONMENTAL" in raw and "pr create" in raw.lower()
    assert "stub: 502 Bad Gateway" in raw
    calls = (tmp_path / "prcreate_calls").read_text().splitlines()
    assert len(calls) == 4                                           # every attempt actually called create


def test_pr_stage_no_changes_still_hard_blocks_with_teardown(tmp_path):
    """Criterion 6 (non-remote failures unaffected): 'no changes produced' is still a hard Block through
    fail_blocked — Reason=Blocked, teardown, no PR — even with the new stage-marker gate wrapping the
    commit step, and never touches the retry/hold machinery (push is never even attempted)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Produces nothing")
    env.pop("STUB_CLAUDE_CHANGE")                                     # implementer writes nothing
    env["STUB_PUSH_ARGV_LOG"] = str(tmp_path / "push_argv")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "no changes" in r.stderr.lower()
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))
    assert "https://stub/pr/1" not in r.stdout
    assert _wt_dir(tmp_path) is None and _state_dir(tmp_path) is None  # torn down, not preserved
    assert not (tmp_path / "push_argv").exists()                      # push never attempted
    assert "environmental" not in r.stderr.lower()


def test_pr_stage_commit_failure_is_unchanged_not_retried_or_held(tmp_path):
    """Criterion 6 (non-remote failures unaffected): a failure IN the commit step itself (not the
    empty-diff guard, and not a remote write) stays exactly as before issue #84 — it never reaches the
    push/pr-create retry loop or the environmental-hold fallback, and never opens a PR."""
    work, _ = _make_repo(tmp_path)
    _fail_all_commits(work)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Commit itself fails")
    env["STUB_PUSH_ARGV_LOG"] = str(tmp_path / "push_argv")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    assert not (tmp_path / "push_argv").exists()                      # never reached the push retry loop
    assert "environmental" not in r.stderr.lower() and "ENVIRONMENTAL" not in r.stderr
    tl = _timeline(tmp_path)
    assert "IMPL" in tl and "TEST" in tl and "CHECK" in tl and "REVIEW" in tl   # every LLM stage still ran
    assert tl.index("IMPL") < tl.index("TEST") < tl.index("CHECK") < tl.index("REVIEW")   # in order


def test_pr_stage_backoff_honors_env_knobs_and_caps_at_max(tmp_path):
    """Criterion 2 (operator-tunable, bounded): PR_STAGE_RETRIES/BACKOFF_BASE/BACKOFF_FACTOR/BACKOFF_MAX
    drive the retry loop's actual requested delays, capped at BACKOFF_MAX rather than growing unbounded —
    verified via a `sleep` stub placed on PATH that records the requested delay and returns immediately
    (no real waiting anywhere in this suite)."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _pr_stage_env(tmp_path, binp, work, title="Backoff knobs", fast=False)
    env["STUB_PUSH_FAIL_COUNT"] = "always"
    sleep_log = tmp_path / "sleep_log"
    _exec(binp / "sleep", SLEEP_STUB)
    env["STUB_SLEEP_LOG"] = str(sleep_log)
    env["PATH"] = f"{binp}{os.pathsep}{os.environ.get('PATH', '')}"
    env.update({
        "PR_STAGE_RETRIES": "4", "PR_STAGE_BACKOFF_BASE": "3",
        "PR_STAGE_BACKOFF_FACTOR": "2", "PR_STAGE_BACKOFF_MAX": "5",
    })
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0                                          # retries exhausted -> hold
    delays = [int(l) for l in sleep_log.read_text().splitlines()] if sleep_log.exists() else []
    # 5 attempts (retries=4) -> 4 inter-attempt delays: base, then doubling, capped at BACKOFF_MAX
    assert delays == [3, 5, 5, 5]
    assert sum(delays) < 60                                           # cumulative delay stays bounded (minutes-scale)
    sd = _state_dir(tmp_path); assert sd is not None and (sd / "env-hold").exists()
