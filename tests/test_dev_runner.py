"""Unit tests for tools/dev-runner.sh — stubbed, no live LLM and no network.

Lifecycle state lives on the native Projects Status/Reason fields. The `gh` stub serves `issue view`
and `project item-list` from canned JSON and records `project item-edit`/`issue comment` to a shared
timeline. The `claude` stub is STAGE-AWARE (implement / test / repair, detected from its argv) and the
CHECK_CMD is a stub script — both append to the timeline, so tests can prove the order
claim → IMPL → TEST → CHECK → (REPAIR → CHECK) → In Review, and that the check gate is deterministic.
Field/option ids are overridden to readable strings (STATUSFIELD, InProgress, …) for legible assertions.
"""
import json, os, re, signal, stat, subprocess, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "dev-runner.sh"

# the shared stage-aware claude fake (classifier included) — the single legal stage-recognition
# path; see tests/harness/contract.md for the harness contract this module documents.
sys.path.insert(0, str(ROOT / "tests" / "harness"))
import claude_fake  # noqa: E402
CLAUDE_STUB = claude_fake.CLAUDE_STUB

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
                 fi
                 true ;;   # a real `gh pr comment` exits 0 on success regardless of which of
                           # --body-file/--body was used — the two recording checks above are each
                           # conditional (false whenever their own flag wasn't the one passed), so
                           # without this the LAST one's false test would leak out as the stub's own
                           # exit code and falsely fail every --body-file-only caller (e.g. emit_and_post).
        *)       printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1" ;;
      esac ;;
  *)  echo "unhandled gh $*" >&2; exit 9 ;;
esac
'''
# CLAUDE_STUB — the stage-aware claude fake — lives in tests/harness/claude_fake.py (imported
# above); this is the ONLY legal stage-recognition path other suites may consume or derive from.
# check gate stub (runs with cwd = worktree): pass, unless STUB_CHECK_FAIL and no 'repaired' marker yet.
# STUB_CHECK_ENVFAIL=<code> makes it exit with that code (use 126/127) to simulate a harness that cannot
# EXECUTE — an environment failure, not a test failure — which no 'repaired' marker can clear.
CHECK_STUB = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
[ -n "${STUB_CHECK_GITENV_FILE:-}" ] && printf 'GIT_CONFIG_GLOBAL=%s GIT_CONFIG_SYSTEM=%s\\n' "${GIT_CONFIG_GLOBAL:-unset}" "${GIT_CONFIG_SYSTEM:-unset}" >> "$STUB_CHECK_GITENV_FILE"
# issue #142: same observation hook as the claude stub, for the check-gate subprocess itself — plus the
# argument count the runner invoked it with, proving no flags (pytest-specific or otherwise) got injected
# into check_cmd's own invocation on the way to routing its temp residue.
[ -n "${STUB_CHECK_TMPDIR_FILE:-}" ] && { printf 'TMPDIR=%s\\n' "${TMPDIR:-unset}"; { [ -n "${TMPDIR:-}" ] && [ -d "$TMPDIR" ]; } && echo DIR_EXISTS=1 || echo DIR_EXISTS=0; printf 'ARGC=%s\\n' "$#"; } >> "$STUB_CHECK_TMPDIR_FILE"
[ -n "${STUB_CHECK_ENVFAIL:-}" ] && exit "${STUB_CHECK_ENVFAIL}"
if [ -n "${STUB_CHECK_FAIL:-}" ] && [ ! -f repaired ]; then exit 1; fi
exit 0
'''
# a hanging variant of CHECK_STUB, for the hard-kill test: signals it was reached, records TMPDIR, then
# sleeps well past the test's own kill — the test SIGKILLs the whole process group once it sees the
# reached-marker, so no teardown path in the runner ever executes for that run.
CHECK_STUB_HANG = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
printf 'TMPDIR=%s\\n' "${TMPDIR:-unset}" > "$STUB_CHECK_TMPDIR_FILE"
: > "$STUB_CHECK_REACHED"
sleep 300
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
    runner builds Tasks only; epics are tracked as native sub-issue parents, never built (footgun F3).
    This stays the polite no-write refusal (issue #132): a typed epic must stay Ready for the
    epic-gate sweeper, so the gate makes zero board writes and posts no comment."""
    binp = tmp_path / "bin"; _stubs(binp)
    r = _run(["7", "--repo", "test/repo"], _env(tmp_path, binp, issue_type="Feature"))
    assert r.returncode == 3 and "task" in r.stderr.lower()
    tl = _timeline(tmp_path)
    assert not _ran(tl) and not _edits(tl) and not _comments(tl)   # no stages, no state writes, no comment


def test_untyped_ready_issue_bounces_to_needs_info(tmp_path):
    """An issue with NO Issue Type at all is not an epic (issue #132) — left as a bare no-write gate it
    would win the dispatch flock every tick with no state change, permanently starving the rest of the
    board (the live incident this task fixes). So it leaves Ready through the existing Needs-info bounce
    instead: Status=Backlog + Reason=Needs-info + a comment naming the Type requirement and the recovery
    act, same shape as the admission wall and the empty-criteria bounce."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, issue_type=None)
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded: isolates the Type bounce specifically
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3   # stays in the gate family, but now via the bounce, not a bare refusal
    tl = _timeline(tmp_path)
    assert not _ran(tl)   # still no LLM stages on a DoR refusal
    edit = " ".join(_edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit
    comments = _comments(tl)
    assert comments
    comment_text = " ".join(comments)
    # names the Type requirement and the recovery act (set Issue Type, then Status back to Ready) —
    # assert by substring on the rule, not exact bytes, since wording is the implementer's to phrase.
    assert "Type" in comment_text
    assert "Ready" in comment_text


def test_untyped_ready_issue_dry_run_is_read_only(tmp_path):
    """--dry-run over an untyped Ready issue stays read-only, exactly like every other NEEDS_INFO
    condition — the bounce is reported (still exit 3), never written to the board."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, issue_type=None)
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    tl = _timeline(tmp_path)
    assert not _ran(tl) and not _edits(tl) and not _comments(tl)


def test_untyped_issue_require_issue_type_optout_unaffected(tmp_path):
    """REQUIRE_ISSUE_TYPE='' (the opt-out for repos without Issue Types) behaves exactly as today for an
    untyped issue too — no Type check at all, so it clears the gate rather than bouncing."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, issue_type=None); env["REQUIRE_ISSUE_TYPE"] = ""
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True
    tl = _timeline(tmp_path)
    assert not _edits(tl) and not _comments(tl)   # dry-run: read-only regardless


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

def _manifest_repo(tmp, *, check_cmd=None, model=None, base_ref=None, lint_cmd=None,
                   lint_fix_cmd=None, lens_cmd=None, name="repo"):
    """A minimal repo dir carrying a .yr/factory.toml (no git needed — dry-run never touches git). A
    leading comment line is always present — with no keys at all, `"\\n".join([]) + "\\n"` is just a
    newline, and `$(cat ...)` strips an all-whitespace read down to an EMPTY string, which the admission
    wall (issue #125) can't tell apart from no manifest at all."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    lines = ["# seeded by the test harness"]
    if check_cmd is not None:    lines.append(f'check_cmd = "{check_cmd}"')
    if model is not None:        lines.append(f'model = "{model}"')
    if base_ref is not None:     lines.append(f'base_ref = "{base_ref}"')
    if lint_cmd is not None:     lines.append(f'lint_cmd = "{lint_cmd}"')
    if lint_fix_cmd is not None: lines.append(f'lint_fix_cmd = "{lint_fix_cmd}"')
    if lens_cmd is not None:     lines.append(f'lens_cmd = "{lens_cmd}"')
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
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded but key-less: a sparse-manifest default
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["model"] == "claude-sonnet-5"


def test_dryrun_body_model_sonnet_resolves_to_sonnet_5(tmp_path):
    """A bare `model: sonnet` body override (with no manifest model) resolves to claude-sonnet-5."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Acceptance criteria\n- [ ] x\n\nmodel: sonnet\n")
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))  # onboarded but key-less: a sparse-manifest default
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["model"] == "claude-sonnet-5"


def test_no_op_model_env_isolation_scaffolding_is_gone():
    """issue #148: the two no-op retired-env-var isolation lines (and their comments) that used to sit
    in test_dryrun_default_model_no_overrides / test_dryrun_body_model_sonnet_resolves_to_sonnet_5 are
    deleted — the runner reads BUILD_MODEL/REVIEW_MODEL only, so setting that retired var never isolated
    anything. The needle is assembled by concatenation (and never written out literally, including here
    in the docstring) so this guard can't match its own source and become tautological."""
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    needle = "".join(['env[', '"', 'MOD', 'EL', '"', ']', ' = ', '""'])
    assert needle not in text


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


def test_shadow_would_merge_equal_rank_pair(tmp_path):
    """issue #139: an equal-rank pair (build==review, same provider, both ranked) clears intake AND now
    clears the merge gate too (review-rank >= build-rank — the reviewer is never weaker) -> WOULD-MERGE,
    not WOULD-BLOCK rank_gate. This used to be the strict-> failure case; the relaxation to >= means the
    top-ranked model (nothing outranks it) can now be commissioned as a builder."""
    body_md = "### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: opus\n"
    env = _shadow_env(tmp_path, title="Shadow equal rank", checks=[CR_OK], body=body_md)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                                       # intake did NOT bounce the equal pair
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == WOULD_MERGE
    rec = _shadow_block(body)
    assert rec["decision"] == "WOULD-MERGE" and rec["failed_condition"] is None
    assert rec["build"]["rank"] == rec["review"]["rank"] == 40
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_would_block_rank_gate_unranked_override(tmp_path):
    """A raw, unregistered build id via the operator env override clears intake (the only non-registry
    escape) but runs UNRANKED — it can never satisfy the rank gate (review-rank >= build-rank requires
    both entries ranked), so it still WOULD-BLOCK rank_gate (criterion 5) exactly as before issue #139:
    the relaxation widened WHICH ranked pairs pass, not whether an unranked pair can."""
    env = _shadow_env(tmp_path, title="Shadow unranked override", checks=[CR_OK],
                      extra={"BUILD_MODEL": "some-unregistered-model-x"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    body = _shadow_body(tmp_path)
    assert body.splitlines()[0] == _would_block("rank_gate")
    assert _shadow_block(body)["failed_condition"] == "rank_gate"
    _assert_not_blocked_and_in_review(_timeline(tmp_path), r)


def test_shadow_first_failed_condition_is_earliest_in_order(tmp_path):
    """Conditions are evaluated IN ORDER (criterion 1): with BOTH ci_green (zero checks) and rank_gate
    (unranked build override) failing, the record names ci_green — the earliest — not rank_gate."""
    env = _shadow_env(tmp_path, title="Shadow ordering", checks=[],
                      extra={"BUILD_MODEL": "some-unregistered-model-x"})
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


def _state_dir_names(tmp):
    return sorted(d.name for d in (tmp / "drhome" / "state").glob("*") if d.is_dir())


def _wt_dir_names(tmp):
    return sorted(d.name for d in (tmp / "drhome" / "wt").glob("*") if d.is_dir())


# ---- epic #126: the worktree + state dirs are repo-keyed, not branch-keyed alone ----
# Two DIFFERENT repos' same-numbered tasks embed the identical branch (task/<issue>-<slug>) — now that
# builds run concurrently across repos, that would collide on one worktree and on each other's resume
# markers unless both paths also carry the target repo's own slug.

def test_worktree_and_state_dirs_are_repo_keyed_for_same_numbered_tasks_across_repos(tmp_path):
    # two DIFFERENT repos' own checkouts (a shared BASE_REPO would collide on the branch name itself,
    # independent of worktree/state keying — the collision under test lives one layer up, in dev-runner's
    # own worktree/state paths, not in git's "branch already checked out" refusal).
    (tmp_path / "repo-a").mkdir(); (tmp_path / "repo-b").mkdir()
    work_a, _ = _make_repo(tmp_path / "repo-a")
    work_b, _ = _make_repo(tmp_path / "repo-b")
    binp = tmp_path / "bin"; _stubs(binp)

    env_a = _real(tmp_path, _env(tmp_path, binp, number=5, title="Same task", repo="owner-a/repo"), work_a)
    env_a.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})   # preserve state for inspection
    r_a = _run(["5", "--repo", "owner-a/repo"], env_a)
    assert r_a.returncode != 0

    env_b = _real(tmp_path, _env(tmp_path, binp, number=5, title="Same task", repo="owner-b/repo"), work_b)
    env_b.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126",
                  "STUB_TIMELINE": str(tmp_path / "timeline-b")})
    r_b = _run(["5", "--repo", "owner-b/repo"], env_b)
    assert r_b.returncode != 0

    wts, states = _wt_dir_names(tmp_path), _state_dir_names(tmp_path)
    assert len(wts) == 2, f"expected two distinct worktree dirs (one per repo), got {wts}"
    assert len(states) == 2, f"expected two distinct state dirs (one per repo), got {states}"
    # same branch slug (identical issue# + title -> identical BRANCH) in both, distinguished only by the
    # repo prefix — proving the repo slug, not the branch, is what keeps them apart.
    assert all(name.endswith("--task-5-same-task") for name in wts)
    assert all(name.endswith("--task-5-same-task") for name in states)
    assert any(name.startswith("owner-a--repo--") for name in wts)
    assert any(name.startswith("owner-b--repo--") for name in wts)
    assert any(name.startswith("owner-a--repo--") for name in states)
    assert any(name.startswith("owner-b--repo--") for name in states)


def test_fresh_run_completes_under_the_repo_keyed_paths(tmp_path):
    """Criterion: resume paths keep working across the keying change for fresh runs — an ordinary
    successful build (no resume involved) still runs every stage and reaches a PR under the new,
    repo-prefixed worktree/state naming."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=9, title="Fresh under new keying", repo="acme/widgets"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["9", "--repo", "acme/widgets"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = _timeline(tmp_path)
    assert "IMPL" in tl and "TEST" in tl and "CHECK" in tl and "REVIEW" in tl   # every stage ran
    # torn down on success exactly as today (repo-keying doesn't change the success teardown contract)
    assert _wt_dir(tmp_path) is None and _state_dir(tmp_path) is None


def test_relaunch_resumes_under_the_repo_keyed_worktree_and_state_paths(tmp_path):
    """Criterion: resume paths keep working across the keying change — a relaunch of a preserved
    env-hold still finds and reuses the SAME repo-keyed worktree/state dir it left behind, resuming at
    the first incomplete stage exactly as the pre-existing (branch-only-keyed) resume behavior did."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain", repo="acme/widgets"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r1 = _run(["5", "--repo", "acme/widgets"], env)
    assert r1.returncode != 0
    wt1 = _wt_dir(tmp_path)
    assert wt1 is not None and wt1.name.startswith("acme--widgets--")

    env2 = {**env, "STUB_TIMELINE": str(tmp_path / "timeline2")}
    del env2["STUB_CHECK_ENVFAIL"]
    r2 = _run(["5", "--repo", "acme/widgets"], env2)
    assert r2.returncode == 0, r2.stderr
    assert "reusing preserved env-hold worktree" in r2.stderr
    assert str(wt1) in r2.stderr                                     # the SAME repo-keyed worktree reused
    tl2 = (tmp_path / "timeline2").read_text().splitlines()
    assert "IMPL" not in tl2 and "TEST" not in tl2                    # already-.done stages skipped
    assert "CHECK" in tl2 and "REVIEW" in tl2


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
# issue #205: emit_json optionally adds a "session_id" key when STUB_SESSION_ID is set — no pre-existing
# exact-dict-equality assertion in this suite ever sets that var, so this stays byte-for-byte
# backward-compatible there; new tests opt in to exercise session_id-based transcript resolution.
emit_json() {  # $1=result-text $2=input $3=output $4=cache_write $5=cache_read $6=duration_ms
  if [ -n "${STUB_SESSION_ID:-}" ]; then
    printf '{"type":"result","subtype":"success","is_error":false,"duration_ms":%s,"result":"%s","session_id":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":%s}}\\n' "$6" "$1" "$STUB_SESSION_ID" "$2" "$3" "$4" "$5"
  else
    printf '{"type":"result","subtype":"success","is_error":false,"duration_ms":%s,"result":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":%s}}\\n' "$6" "$1" "$2" "$3" "$4" "$5"
  fi
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
    # issue #213 expands this contract by lint_cmd/lint_fix_cmd; issue #214 adds lens_cmd — each tier's
    # acceptance criterion requires the dry-run to report its own key(s). No USAGE-related key may appear.
    assert set(d) == {"repo", "issue", "branch", "model", "workspace", "base_repo", "base_ref",
                       "check_cmd", "auto_merge", "lint_cmd", "lint_fix_cmd", "lens_cmd",
                       "build", "review", "ready"}


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
        "by pid only",                                 # process management is by PID only (issue #122)
        "pkill -f",                                    # pattern-kills named and forbidden
        "pgrep -f",                                    # pattern-kills named and forbidden
        "own command environment can contain the task text",  # why: argv/env can echo the task text
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
        # issue #122: the tester's only legal write surface is named as repo-root tests/ — and the
        # prompt calls out that a same-named directory nested inside a deliverable (e.g. qa/tests/) is
        # NOT that surface, since the boundary guard (not this prompt) is what actually disposes.
        assert "repo-root tests/" in prompt, "tester prompt must name repo-root tests/ as its write surface"
        assert "qa/tests/" in prompt, "tester prompt must call out a nested same-named dir as out of bounds"

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


# ============ Issue #142: run-scoped TMPDIR for stage and gate residue ============
# The runner owns its check-gate residue: every stage/gate subprocess (implement/test/check/review, and
# the check re-runs) must see a TMPDIR the runner created under its OWN run dir, so any tool that honors
# TMPDIR (pytest's /tmp/pytest-of-* among them) routes its temp files there instead of onto the shared
# /tmp. That per-run tmp dir is removed on every one of today's teardown paths (success, the one-repair
# code failure, review-repair) — but NOT on the env-hold path, which deliberately preserves everything for
# a resumable relaunch — and a hard-killed run (no teardown at all) must still have bounded its own
# residue to its own tmp dir, never touching a later run's.

def _tmpdir_captures(path):
    """Parse a STUB_*_TMPDIR_FILE into a list of (tmpdir, dir_existed) pairs, one per subprocess call."""
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    out = []
    i = 0
    while i < len(lines):
        assert lines[i].startswith("TMPDIR=")
        tmpdir = lines[i][len("TMPDIR="):]
        assert lines[i + 1] in ("DIR_EXISTS=1", "DIR_EXISTS=0")
        out.append((tmpdir, lines[i + 1] == "DIR_EXISTS=1"))
        i += 2
        if i < len(lines) and lines[i].startswith("ARGC="):
            i += 1
    return out


def test_tmpdir_exported_under_run_dir_for_every_stage_and_gate_subprocess(tmp_path):
    """Criterion 1: implement/test/check/review (and the repair stages, since STUB_CHECK_FAIL forces one
    check re-run) all see the SAME TMPDIR, it lives under this run's own run dir (not /tmp, not the
    worktree), the directory already exists at the moment each subprocess runs, and the check gate itself
    receives no extra arguments — the seam is TMPDIR alone, no injected flags."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="TMPDIR export"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CHECK_FAIL"] = "1"           # forces one check-repair round -> an extra check + claude call
    env["STUB_CLAUDE_TMPDIR_FILE"] = str(tmp_path / "claude_tmpdir")
    env["STUB_CHECK_TMPDIR_FILE"] = str(tmp_path / "check_tmpdir")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    rd = _run_dir(tmp_path, 5)
    expected = str(rd / "tmp")

    claude_calls = _tmpdir_captures(tmp_path / "claude_tmpdir")
    check_calls = _tmpdir_captures(tmp_path / "check_tmpdir")
    assert len(claude_calls) >= 3   # implement, test, review at minimum (repair adds a 4th)
    assert len(check_calls) >= 2    # the initial check + the post-repair re-run

    for tmpdir, existed in claude_calls + check_calls:
        assert tmpdir == expected, f"expected every subprocess TMPDIR == {expected}, got {tmpdir}"
        assert existed, f"TMPDIR {tmpdir} did not exist when the subprocess ran"

    # no pytest-specific (or any other) flags injected into the check_cmd invocation itself
    argc_lines = [l for l in (tmp_path / "check_tmpdir").read_text().splitlines() if l.startswith("ARGC=")]
    assert argc_lines and all(l == "ARGC=0" for l in argc_lines)


def test_tmpdir_removed_on_success_teardown_logs_and_usage_survive(tmp_path):
    """Criterion 2 (success branch): once a build reaches cleanup_wt, its per-run tmp dir is gone, but
    the run dir itself, its stage logs, and its usage artifacts (RUN_DIR is never touched by cleanup_wt,
    only STATE_DIR/WT/its own tmp subdir are) are all still there."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Success teardown"), work)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout

    rd = _run_dir(tmp_path, 5)
    assert rd.exists()                                    # the run dir itself is never torn down
    assert not (rd / "tmp").exists()                       # its tmp subdir IS torn down
    assert (rd / "checks.log").exists()
    assert (rd / "implement.log").exists()
    assert (rd / "test.log").exists()
    assert (rd / "review.md").exists()
    assert (rd / "usage-implement.json").exists()          # usage artifacts untouched
    assert (rd / "usage-summary.json").exists()


def test_tmpdir_removed_on_blocked_code_failure_teardown(tmp_path):
    """Criterion 2 (the other cleanup_wt-calling branch): an unrepairable code failure still tears down
    the per-run tmp dir even though the build itself never reaches success, while the run dir's own logs
    (which named the failure) stay in place."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Cannot fix"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REPAIR_NOFIX": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "Blocked" in " ".join(_edits(_timeline(tmp_path)))

    rd = _run_dir(tmp_path, 5)
    assert rd.exists()
    assert not (rd / "tmp").exists()
    assert (rd / "checks.log").exists()


def test_tmpdir_preserved_on_env_hold_and_a_relaunch_gets_its_own_fresh_one(tmp_path):
    """Criterion 3, exercised via the one teardown-skipping path the runner already has (env_hold —
    tools/dev-runner.sh's own comment says cleanup_wt is deliberately not called there): the held run's
    tmp dir is NOT removed (no teardown ran for it), and a later relaunch of the SAME issue gets a
    different, fresh run dir/tmp dir of its own — the first run's leftover never leaks into or blocks the
    second run, which still tears its own tmp dir down normally on its own success."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r1 = _run(["5", "--repo", "test/repo"], env)
    assert r1.returncode != 0

    rd1 = _run_dir(tmp_path, 5)
    assert (rd1 / "tmp").exists()          # no teardown ran for the held run -> its tmp dir survives

    env2 = {**env, "STUB_TIMELINE": str(tmp_path / "timeline2")}
    del env2["STUB_CHECK_ENVFAIL"]
    r2 = _run(["5", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr
    assert "reusing preserved env-hold worktree" in r2.stderr

    rundirs = _run_dirs(tmp_path, 5)
    assert len(rundirs) == 2                                     # the resume got a FRESH run dir
    rd2 = next(d for d in rundirs if d != rd1)
    assert not (rd2 / "tmp").exists()       # the successful resume tore its OWN tmp dir down normally
    assert (rd1 / "tmp").exists()           # the first run's leftover is untouched by the second run


def _run_bg(args, env_extra, cwd=None):
    base_env = {k: v for k, v in os.environ.items() if k not in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")}
    env = {**base_env, **READABLE_IDS, **env_extra}
    return subprocess.Popen(["bash", str(RUNNER), *args], env=env, cwd=str(cwd or ROOT),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)


def test_hard_kill_bounds_residue_to_its_own_run_dir_and_a_later_run_is_unaffected(tmp_path):
    """Criterion 3 (the hard-kill case itself): a run SIGKILLed mid check-gate — the whole process group,
    so nothing gets a chance to run any teardown path — never wrote its check subprocess's TMPDIR outside
    that run's own tmp dir in the first place (the export happens before the subprocess is ever spawned),
    so whatever residue it left is bounded there. A later, independent run is completely unaffected: it
    gets its own fresh run dir/tmp dir and completes/tears down normally regardless of the killed run's
    leftovers."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "gh", GH_STUB)
    _exec(binp / "claude", CLAUDE_STUB)
    _exec(binp / "check.sh", CHECK_STUB_HANG)

    reached = tmp_path / "check_reached"
    check_tmpdir_file = tmp_path / "check_tmpdir_hang"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Hard killed run"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CHECK_REACHED"] = str(reached)
    env["STUB_CHECK_TMPDIR_FILE"] = str(check_tmpdir_file)

    proc = _run_bg(["5", "--repo", "test/repo"], env)
    try:
        deadline = time.monotonic() + 20
        while not reached.exists():
            assert proc.poll() is None, f"runner exited early (rc={proc.poll()}) before reaching the check gate"
            assert time.monotonic() < deadline, "check gate was never reached within the timeout"
            time.sleep(0.05)

        rundirs = _run_dirs(tmp_path, 5)
        assert len(rundirs) == 1
        rd = rundirs[0]

        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=10)

    captured = check_tmpdir_file.read_text().strip()
    assert captured == f"TMPDIR={rd / 'tmp'}"           # the killed subprocess's own TMPDIR, bounded here
    assert (rd / "tmp").exists()                        # nothing tore it down (no teardown path ran)

    # a later, independent run is unaffected: fresh run dir, own tmp dir, normal success + teardown
    binp2 = tmp_path / "bin2"; _stubs(binp2)
    env2 = _real(tmp_path, _env(tmp_path, binp2, number=6, title="Unaffected later run"), work)
    env2["STUB_CLAUDE_CHANGE"] = "1"
    env2["STUB_TIMELINE"] = str(tmp_path / "timeline6")
    r2 = _run(["6", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr

    rd2 = _run_dir(tmp_path, 6)
    assert rd2 != rd
    assert not (rd2 / "tmp").exists()                   # its own tmp dir was torn down normally
    assert (rd / "tmp").exists()                         # the killed run's leftover is still just sitting there, untouched


# ============ Issue #205: the stage transcript becomes a run artifact, capped ============
# Every completed LLM stage's full CLI session transcript is copied into the run dir as
# transcript-<stage>.jsonl (dedup suffix -2/-3 on repair re-runs, matching usage-<stage>.json), resolved
# from the stage log's result envelope session_id when it names a real file under the CLI project slug
# dir ($HOME/.claude/projects/<slugified $WT>/<session_id>.jsonl) — else the newest .jsonl there
# (heuristic, always so logged) — skipping loud only when that dir is absent or empty. tools/ledger.py
# also provides a runner-owned prune (age, then size, oldest-first) wired fail-soft into the success
# terminus. CLAUDE_STUB_JSON's emit_json (above) is extended, not cloned, with an optional
# STUB_SESSION_ID-driven "session_id" envelope key for these tests to opt into.

def _resolve_wt_slug(env, repo, number):
    """The exact CLI project-slug dir tools/dev-runner.sh's own wt_slug() produces for this run — read
    from --dry-run's real 'branch' field (never re-deriving the title-slugify pipeline by hand) combined
    with the trivial owner--name REPO_SLUG this whole suite's repo="test/repo" reduces to unambiguously
    (no upper-case/special chars to fold). --dry-run is read-only (proven elsewhere in this file), so
    calling it ahead of the real run never disturbs any state the real run depends on."""
    r = _run([str(number), "--repo", repo, "--dry-run"], dict(env))
    assert r.returncode == 0, r.stderr
    branch = json.loads(r.stdout)["branch"]
    owner, name = repo.split("/", 1)
    repo_slug = f"{owner}--{name}".lower()
    wt = f"{env['DEV_RUNNER_HOME']}/wt/{repo_slug}--{branch.replace('/', '-')}"
    return wt.replace("/", "-").replace(".", "-")


def _seed_slug_dir(home, slug):
    d = pathlib.Path(home) / ".claude" / "projects" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _transcript_files(rundir):
    return sorted(p.name for p in rundir.glob("transcript-*.jsonl"))


def test_transcript_archived_via_heuristic_fallback_for_every_llm_stage(tmp_path):
    """The plain-text stub (this suite's default `claude`, no JSON envelope anywhere) still gets its
    per-stage transcript archived, via the documented fallback: the newest .jsonl under the CLI project
    slug dir — since the stub never rotates it, every stage-named transcript resolves to the one seeded
    fixture file, byte-faithfully."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    home = tmp_path / "home"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Transcript heuristic fallback"), work)
    env["HOME"] = str(home)
    env["STUB_CLAUDE_CHANGE"] = "1"
    slug = _resolve_wt_slug(env, "test/repo", 5)
    slug_dir = _seed_slug_dir(home, slug)
    fixture = slug_dir / "session-abc123.jsonl"
    fixture.write_text('{"fixture": "transcript content"}\n')

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = _run_dir(tmp_path, 5)
    assert _transcript_files(rd) == ["transcript-implement.jsonl", "transcript-review.jsonl", "transcript-test.jsonl"]
    for name in _transcript_files(rd):
        assert (rd / name).read_text() == fixture.read_text()   # byte-faithful copy, no redaction


def test_transcript_archive_skipped_loudly_when_slug_dir_absent(tmp_path):
    """No envelope AND no CLI project slug dir at all (never created) — archiving is skipped, logged
    loudly (never silently), and the run's own outcome is completely unaffected."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    home = tmp_path / "home-empty"; home.mkdir()
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Transcript slug dir absent"), work)
    env["HOME"] = str(home)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = _run_dir(tmp_path, 5)
    assert _transcript_files(rd) == []
    assert "transcript archive" in r.stderr.lower()
    assert "skipped" in r.stderr.lower() and "absent" in r.stderr.lower()


def test_transcript_archive_skipped_loudly_when_slug_dir_empty(tmp_path):
    """The slug dir exists but holds no .jsonl at all — same loud skip, distinguished reason."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    home = tmp_path / "home-empty-dir"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Transcript slug dir empty"), work)
    env["HOME"] = str(home)
    env["STUB_CLAUDE_CHANGE"] = "1"
    slug = _resolve_wt_slug(env, "test/repo", 5)
    _seed_slug_dir(home, slug)   # created, but left empty
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = _run_dir(tmp_path, 5)
    assert _transcript_files(rd) == []
    assert "skipped" in r.stderr.lower() and "empty" in r.stderr.lower()


def test_transcript_archive_never_blocks_or_fails_the_run(tmp_path):
    """Fail-soft, restated as a direct assertion: even with no slug dir at all, the pipeline still reaches
    a PR — archiving failures/skips are advisory only, never a gate."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Transcript never gates"), work)
    env["HOME"] = str(tmp_path / "home-never-created")
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout


def test_transcript_dedup_suffix_on_review_repair_recheck_matches_usage_convention(tmp_path):
    """review.md is the one log file run_stage writes into TWICE in a single run (initial review, then
    the post-repair re-review) — archiving must suffix the second round's transcript exactly like
    usage-review-2.json does, never overwriting the first round's copy."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    home = tmp_path / "home"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Transcript dedup on review repair"), work)
    env["HOME"] = str(home)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1"})
    slug = _resolve_wt_slug(env, "test/repo", 5)
    slug_dir = _seed_slug_dir(home, slug)
    (slug_dir / "session-x.jsonl").write_text("dedup fixture\n")

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert tl.count("REVIEW") == 2   # blocked once, approved after repair — review.md written to twice

    rd = _run_dir(tmp_path, 5)
    files = _transcript_files(rd)
    assert "transcript-review.jsonl" in files
    assert "transcript-review-2.jsonl" in files


def test_session_id_resolution_wins_over_the_newest_file_heuristic(tmp_path):
    """Acceptance: envelope parsing must read the stage log's intact result envelope BEFORE
    capture_stage_usage rewrites it — proven here by placing a session_id-NAMED transcript with an OLDER
    mtime alongside a plain DECOY file with a NEWER mtime in the slug dir. If archiving ran after the
    rewrite (or ignored session_id), the heuristic-newest fallback would pick the decoy instead."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    home = tmp_path / "home"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Session id wins over heuristic"), work)
    env["HOME"] = str(home)
    env["STUB_SESSION_ID"] = "sess-1"
    slug = _resolve_wt_slug(env, "test/repo", 5)
    slug_dir = _seed_slug_dir(home, slug)

    named = slug_dir / "sess-1.jsonl"
    named.write_text("the correct session transcript\n")
    os.utime(named, (time.time() - 3600, time.time() - 3600))   # older

    decoy = slug_dir / "decoy-newer.jsonl"
    decoy.write_text("must NOT be picked\n")
    # decoy keeps its just-created (newer) mtime

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = _run_dir(tmp_path, 5)
    assert (rd / "transcript-implement.jsonl").read_text() == "the correct session transcript\n"


def test_failed_stage_archives_from_intact_envelope_without_rewrite(tmp_path):
    """rc != 0: capture_stage_usage never runs (guarded on rc -eq 0), so the envelope sits intact in the
    log either way — archiving must still resolve session_id from it and copy the named transcript."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    home = tmp_path / "home"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Failed stage still archives"), work)
    env["HOME"] = str(home)
    env["STUB_SESSION_ID"] = "sess-fail-1"
    env["STUB_IMPL_JSON_THEN_FAIL"] = "1"
    slug = _resolve_wt_slug(env, "test/repo", 5)
    slug_dir = _seed_slug_dir(home, slug)
    (slug_dir / "sess-fail-1.jsonl").write_text("the failed stage's own transcript\n")

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    rd = _run_dir(tmp_path, 5)
    assert (rd / "implement.log").read_text().strip().startswith('{"type":"result"')   # untouched, per #48
    assert (rd / "transcript-implement.jsonl").read_text() == "the failed stage's own transcript\n"


def test_session_id_additive_field_in_usage_record_when_envelope_carries_one(tmp_path):
    """Acceptance: adding session_id to the usage record is the one permitted additive change — present
    when the envelope carries one, alongside every field the pre-existing #48 suite already pins."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Session id in usage record"), work)
    env["HOME"] = str(tmp_path / "home")
    env["STUB_SESSION_ID"] = "sess-usage-1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = _run_dir(tmp_path, 5)
    record = json.loads((rd / "usage-implement.json").read_text())
    assert record["session_id"] == "sess-usage-1"
    assert record["input_tokens"] == 61   # every field the #48 suite already pins is still exactly there


def _seed_old_run_dir(runs_dir, name, *, transcript_name="transcript-old.jsonl", age_days=100, size_bytes=10):
    d = runs_dir / name
    d.mkdir(parents=True, exist_ok=True)
    t = d / transcript_name
    t.write_bytes(b"x" * size_bytes)
    old = time.time() - age_days * 86400
    os.utime(t, (old, old))
    u = d / "usage-old.json"
    u.write_text(json.dumps({"stage": "old", "input_tokens": 1}))
    return d, t, u


def test_prune_deletes_old_transcript_but_not_other_artifacts_after_a_successful_run(tmp_path):
    """The runner-owned retention cap fires at the success terminus: an old transcript-*.jsonl elsewhere
    under runs/ is deleted, while every other artifact in that same run dir (a usage-*.json here, standing
    in for any non-transcript run artifact) is left completely untouched."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Prune wiring happy path"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["HOME"] = str(tmp_path / "home")
    runs_dir = pathlib.Path(env["DEV_RUNNER_HOME"]) / "runs"
    _, old_transcript, old_usage = _seed_old_run_dir(runs_dir, "999-oldrun", age_days=100)

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not old_transcript.exists()      # past the default 90-day age cap: pruned
    assert old_usage.exists()               # a non-transcript artifact: never touched


def test_prune_never_fires_before_a_pr_is_ever_created(tmp_path):
    """A Blocked run (no PR ever created) never reaches the success terminus prune is wired into — the
    spec's accepted tolerance ('a failure streak defers pruning to the next successful run')."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Prune deferred on blocked run"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REPAIR_NOFIX": "1"})
    env["HOME"] = str(tmp_path / "home")
    runs_dir = pathlib.Path(env["DEV_RUNNER_HOME"]) / "runs"
    _, old_transcript, _ = _seed_old_run_dir(runs_dir, "999-oldrun", age_days=100)

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    assert old_transcript.exists()          # never pruned — the run never reached the success terminus


def test_prune_respects_the_max_age_env_tunable_through_the_whole_runner(tmp_path):
    """LEDGER_TRANSCRIPT_MAX_AGE_DAYS, set in the runner's own environment, must reach ledger.py's prune
    call unmodified: a transcript younger than the DEFAULT cap (90 days) but older than an explicit,
    tighter override must still be pruned."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Prune env tunable"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["HOME"] = str(tmp_path / "home")
    env["LEDGER_TRANSCRIPT_MAX_AGE_DAYS"] = "5"
    runs_dir = pathlib.Path(env["DEV_RUNNER_HOME"]) / "runs"
    _, young_transcript, young_usage = _seed_old_run_dir(runs_dir, "999-youngrun", age_days=10)  # >5, <90

    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not young_transcript.exists()     # pruned only because of the tighter env override
    assert young_usage.exists()


# ============ Issue #206: ledger — one row per runner invocation at every terminal branch =============
# tools/ledger.py's `append` writes one yr-ledger-row/1 JSONL row to $DEV_RUNNER_HOME/ledger/rows.jsonl
# at whichever terminal branch a run reaches (Needs-info bounce, fail_blocked, env_hold, and the success
# terminus deriving outcome from the merge decision). Unit coverage of build_ledger_row/append_row/the
# CLI lives in tests/test_ledger.py; these tests prove the WIRING into tools/dev-runner.sh itself — the
# exact terminal branches call ledger_append, a hard kill (no terminal branch reached) appends nothing,
# and a ledger failure never affects the run's own outcome.

def _ledger_rows(tmp):
    p = tmp / "drhome" / "ledger" / "rows.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_ledger_row_appended_on_needs_info_bounce(tmp_path):
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp, body="### Goal\njust do it\n")
    env["DEV_RUNNER_HOME"] = str(tmp_path / "drhome")
    env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["schema"] == "yr-ledger-row/1"
    assert row["task"] == "test/repo#7"           # owner/repo#issue — never derived from a run dir
    assert row["repo"] == "test/repo"
    assert row["outcome"] == {"type": "needs-info", "decision": None}
    # the bounce runs BEFORE claim/worktree: base_sha is genuinely unknown at that point (branch is
    # already resolved by then — it's derived from the issue/title alone, no worktree needed).
    assert row["base_sha"] is None
    assert row["stages"] == []                    # no run dir ever existed for this branch


def test_ledger_row_appended_on_fail_blocked(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Cannot fix"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_FAIL": "1", "STUB_REPAIR_NOFIX": "1"})
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["task"] == "test/repo#5"
    assert row["outcome"] == {"type": "blocked", "decision": None}
    assert row["branch"]                                   # claimed -> a real branch name
    assert row["base_sha"] and len(row["base_sha"]) == 40   # resolved from the worktree HEAD
    assert row["repairs"]["check"] == 1                     # the one repair attempt is on record


def test_ledger_row_appended_on_env_hold(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Quota kill on implement"), work)
    env["STUB_IMPL_QUOTA"] = "Error: usage limit reached for this account, try again later"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["outcome"] == {"type": "env-hold", "decision": None}
    # the append itself never disturbed worktree preservation (env_hold_record's own contract).
    assert _wt_dir(tmp_path) is not None
    assert (_state_dir(tmp_path) / "env-hold").exists()


def test_ledger_row_appended_on_shadow_would_merge(tmp_path):
    env = _shadow_env(tmp_path, title="Ledger shadow would-merge", checks=[CR_OK])
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "shadow-would-merge", "decision": "WOULD-MERGE"}
    # criterion: the #79 usage comment is unaffected by the ledger addition.
    assert "### dev-runner usage" in _prcomments(tmp_path)


def test_ledger_row_appended_on_shadow_would_block(tmp_path):
    env = _shadow_env(tmp_path, title="Ledger shadow would-block", checks=[CR_OK, CR_FAIL])
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "shadow-would-block", "decision": "WOULD-BLOCK"}


def test_ledger_row_appended_even_with_zero_usage_artifacts(tmp_path):
    """The plain-text stub (no JSON envelope anywhere) still gets exactly one row, with an empty stage
    array rather than a skipped append."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Plain text degrade"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["stages"] == []
    assert rows[0]["totals"]["weighted_total"] == 0


def test_ledger_row_stage_usage_includes_all_dedup_suffixed_files(tmp_path):
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Ledger dedup suffixes"), work)
    env["STUB_REVIEW_BLOCK"] = "1"           # forces a second review round -> usage-review-2.json
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    stages = {s["stage"]: s for s in rows[0]["stages"]}
    assert "review" in stages and "review-2" in stages
    assert stages["review"]["source"] == "usage-file" and stages["review-2"]["source"] == "usage-file"
    assert stages["review"]["duration_ms"] == 100 and stages["review-2"]["duration_ms"] == 200
    # both rounds counted in the run-wide total, never just one.
    assert rows[0]["totals"]["input_tokens"] >= stages["review"]["input_tokens"] + stages["review-2"]["input_tokens"]


def test_ledger_row_failed_stage_uses_envelope_without_rewriting_the_log(tmp_path):
    """rc != 0: capture_stage_usage never runs, so implement.log still holds the raw envelope when
    fail_blocked's own ledger_append call reads it — via the read-only find_result_envelope fallback,
    never a rewrite."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_json(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Envelope then fail"), work)
    env["STUB_IMPL_JSON_THEN_FAIL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    rd = _run_dir(tmp_path)
    raw_log = (rd / "implement.log").read_text()
    assert raw_log.strip().startswith('{"type":"result"')   # still the raw envelope, unrewritten

    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    stages = {s["stage"]: s for s in rows[0]["stages"]}
    assert stages["implement"]["source"] == "envelope"
    assert stages["implement"]["input_tokens"] == 61   # CLAUDE_STUB_JSON's implement-round token counts

    # ledger.py's own read (via build_ledger_row -> find_result_envelope) is confirmed above to still be
    # untouched — this is the direct, byte-exact assertion the criterion calls for.
    assert (rd / "implement.log").read_text() == raw_log


def test_ledger_row_shares_task_key_across_a_resumed_invocation(tmp_path):
    """A relaunch of a preserved env-hold appends its OWN second row (a fresh run_id — a new pid-keyed
    run dir), sharing the SAME task key as the first — no usage-file recovery, no row merging; that is
    the read side's job."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Broken toolchain"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r1 = _run(["5", "--repo", "test/repo"], env)
    assert r1.returncode != 0
    rows1 = _ledger_rows(tmp_path)
    assert len(rows1) == 1 and rows1[0]["outcome"]["type"] == "env-hold"

    env2 = {**env, "STUB_TIMELINE": str(tmp_path / "timeline2")}
    del env2["STUB_CHECK_ENVFAIL"]
    r2 = _run(["5", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr

    rows2 = _ledger_rows(tmp_path)
    assert len(rows2) == 2                                       # one row per invocation
    assert rows2[0]["run_id"] != rows2[1]["run_id"]               # distinct run ids (separate pids)
    assert rows2[0]["task"] == rows2[1]["task"] == "test/repo#5"  # same task key, both rows
    assert rows2[1]["outcome"]["type"] != "env-hold"               # the resume reached a later terminus


def test_ledger_row_hard_kill_appends_nothing(tmp_path):
    """The accepted gap: a run SIGKILLed mid check-gate (the whole process group — nothing gets a
    chance to run any teardown or terminal-branch path) reaches no ledger_append call at all, so
    rows.jsonl is never even created."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "gh", GH_STUB)
    _exec(binp / "claude", CLAUDE_STUB)
    _exec(binp / "check.sh", CHECK_STUB_HANG)

    reached = tmp_path / "check_reached"
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Hard killed run (ledger)"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CHECK_REACHED"] = str(reached)
    env["STUB_CHECK_TMPDIR_FILE"] = str(tmp_path / "check_tmpdir_hang")

    proc = _run_bg(["5", "--repo", "test/repo"], env)
    try:
        deadline = time.monotonic() + 20
        while not reached.exists():
            assert proc.poll() is None, f"runner exited early (rc={proc.poll()}) before reaching the check gate"
            assert time.monotonic() < deadline, "check gate was never reached within the timeout"
            time.sleep(0.05)
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=10)

    assert _ledger_rows(tmp_path) == []
    assert not (tmp_path / "drhome" / "ledger" / "rows.jsonl").exists()


def test_ledger_append_failure_never_blocks_the_run(tmp_path):
    """Fail-soft: an append failure (here, the ledger dir path is pre-occupied by a plain FILE, so
    ledger.py's own mkdir fails) is warned about but never blocks, fails, or gates the run — the PR
    still opens and In Review is still reached."""
    work, _ = _make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Ledger append failure tolerated"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    drhome = tmp_path / "drhome"; drhome.mkdir(parents=True, exist_ok=True)
    (drhome / "ledger").write_text("not a directory")   # forces ledger.py's own mkdir(parents=True) to fail
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = _timeline(tmp_path)
    assert any(l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l for l in tl)
    assert "ledger append failed" in r.stderr.lower()
    assert "non-fatal" in r.stderr.lower()


# ============ Issue #213: manifest-declared lint tier — blocking, autofix-first repair ============
# The check gate runs a repo's manifest-declared `lint_cmd` as a BLOCKING tier, AFTER `check_cmd` passes.
# The repair scope is ruled: deterministic autofix (`lint_fix_cmd`) FIRST — no LLM — then at most ONE LLM
# repair confined to the lint-flagged files; after ANY repair-path mutation of the tree (the autofix
# alone included) BOTH `check_cmd` and `lint_cmd` re-run before the stage may pass, and either failing
# ends the run Blocked. An absent `lint_cmd` = today's behavior, byte-identical (no probe, no output). A
# lint (or autofix) exit 126/127 is an ENVIRONMENT hold naming the lint command + lint.log (never the
# check command's text / checks.log), with NO LLM repair.
#
# Stubs — self-contained, no live LLM or network. `lint.sh` / `lintfix.sh` are OPAQUE shell commands the
# runner runs verbatim (run_lint), gated on env vars and a `lint_ok` marker they drop in the worktree
# (cwd = $WT for both run_lint and the claude stages). The claude stub gains a `*"lint gate FAILS"*`
# branch (a LINTREPAIR timeline marker), so the LLM lint-repair stage is OBSERVABLE and DISTINCT from the
# check-repair stage (REPAIR) and the implementer (IMPL) — the shipped stub would misroute the lint
# prompt to the implementer (`*)`), collapsing exactly the distinction these tests must prove.

LINT_STUB = '''#!/usr/bin/env bash
echo LINT >> "$STUB_LINT_TL"
[ -n "${STUB_LINT_ENVFAIL:-}" ] && exit "${STUB_LINT_ENVFAIL}"
if [ -n "${STUB_LINT_FAIL:-}" ] && [ ! -f lint_ok ]; then exit 1; fi
exit 0
'''

LINT_FIX_STUB = '''#!/usr/bin/env bash
echo LINTFIX >> "$STUB_LINT_TL"
[ -n "${STUB_FIX_ENVFAIL:-}" ] && exit "${STUB_FIX_ENVFAIL}"
[ -z "${STUB_FIX_NOHEAL:-}" ] && : > lint_ok
exit 0
'''

# the shipped claude stub, plus a lint-repair branch inserted BEFORE the check-repair one. The LLM
# lint-repair task prompt carries "The lint gate FAILS" (never "tests FAIL"/"TESTER"/"REVIEWER"), so it
# routes here and nowhere else. It heals (drops the worktree's `lint_ok` marker) only when
# STUB_LINTREPAIR_HEAL is set, so both the still-broken and the healed paths are exercisable.
LINT_CLAUDE_STUB = CLAUDE_STUB.replace(
    '  *"tests FAIL"*)',
    '''  *"lint gate FAILS"*) echo LINTREPAIR >> "$STUB_TIMELINE"
                        [ -n "${STUB_LINTREPAIR_HEAL:-}" ] && : > lint_ok ;;
  *"tests FAIL"*)''',
)


def _lint_bin(tmp):
    """Stubs for a lint-tier run: the lint-aware claude stub plus the opaque lint.sh / lintfix.sh."""
    binp = tmp / "bin"; _stubs(binp)
    _exec(binp / "claude", LINT_CLAUDE_STUB)
    _exec(binp / "lint.sh", LINT_STUB)
    _exec(binp / "lintfix.sh", LINT_FIX_STUB)
    return binp


def _lint_env(tmp, *, title="Lint tier", declare_fix=True, number=5):
    """A real-git flow env with the lint tier wired via explicit LINT_CMD/LINT_FIX_CMD (env > manifest);
    an end-to-end manifest-declared variant is exercised separately (test_lint_cmd_declared_in_manifest)."""
    work, _ = _make_repo(tmp)
    binp = _lint_bin(tmp)
    env = _real(tmp, _env(tmp, binp, number=number, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_LINT_TL"] = str(tmp / "lint_tl")
    env["LINT_CMD"] = f"bash {binp / 'lint.sh'}"
    if declare_fix:
        env["LINT_FIX_CMD"] = f"bash {binp / 'lintfix.sh'}"
    return env, work, binp


def _lint_tl(tmp):
    p = tmp / "lint_tl"
    return p.read_text().splitlines() if p.exists() else []


def _lint_log(tmp, number=5):
    rd = _run_dir(tmp, number)
    p = rd / "lint.log"
    return p.read_text() if p.exists() else None


# ---- criterion: the dry-run JSON reports lint_cmd / lint_fix_cmd; env overrides manifest (precedence) --

def test_dryrun_reports_lint_cmd_and_fix_from_manifest(tmp_path):
    """A repo's manifest lint_cmd/lint_fix_cmd surface in the dry-run JSON when no env override is set."""
    repo = _manifest_repo(tmp_path, lint_cmd="ruff check .", lint_fix_cmd="ruff check --fix .")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["lint_cmd"] == "ruff check ."
    assert d["lint_fix_cmd"] == "ruff check --fix ."


def test_dryrun_lint_absent_reports_empty(tmp_path):
    """No manifest lint keys and no env override -> both report as empty (absent = off)."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(_manifest_repo(tmp_path))
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["lint_cmd"] == "" and d["lint_fix_cmd"] == ""


def test_dryrun_env_lint_cmd_overrides_manifest(tmp_path):
    """Explicit LINT_CMD/LINT_FIX_CMD in the env win over the manifest (env > manifest > default)."""
    repo = _manifest_repo(tmp_path, lint_cmd="ruff check .", lint_fix_cmd="ruff check --fix .")
    binp = tmp_path / "bin"; _stubs(binp)
    env = _env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env["LINT_CMD"] = "eslint ."; env["LINT_FIX_CMD"] = "eslint --fix ."
    r = _run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["lint_cmd"] == "eslint ." and d["lint_fix_cmd"] == "eslint --fix ."


# ---- criterion: WHEN a repo declares no lint_cmd, behave byte-identically to today (no probe/output) --

def test_no_lint_cmd_is_byte_identical_to_today(tmp_path):
    """With no lint_cmd declared, the lint tier is inert: no probe (lint.sh never runs), no lint.log in
    the run dir, and the check gate runs exactly once — the whole build proceeds to a PR as it always has."""
    work, _ = _make_repo(tmp_path)
    binp = _lint_bin(tmp_path)   # lint.sh EXISTS on disk, but nothing must invoke it
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="No lint declared"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_LINT_TL"] = str(tmp_path / "lint_tl")
    # deliberately NO LINT_CMD / LINT_FIX_CMD in the env and none in the manifest
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert _lint_tl(tmp_path) == []                       # the lint command was never probed
    assert _lint_log(tmp_path) is None                    # no lint.log artifact at all
    tl = _timeline(tmp_path)
    assert tl.count("CHECK") == 1                          # no lint-driven re-check
    assert "LINTREPAIR" not in tl and "REPAIR" not in tl
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)


# ---- criterion: lint_cmd runs AFTER check_cmd passes; green lint proceeds -----------------------------

def test_lint_green_proceeds_after_check(tmp_path):
    """A declared lint_cmd that passes runs once (after the check gate), triggers no autofix and no LLM
    repair and no re-check, and the build proceeds to a PR / In Review."""
    env, work, binp = _lint_env(tmp_path, title="Lint green")
    # lint passes on the first probe (STUB_LINT_FAIL unset)
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    lint_tl = _lint_tl(tmp_path)
    assert lint_tl == ["LINT"]                             # probed once, passed; no autofix, no re-run
    assert "LINTFIX" not in lint_tl
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl                          # no LLM lint repair
    assert tl.count("CHECK") == 1                          # no mutation -> no re-check
    assert _lint_log(tmp_path) is not None                 # the probe produced a lint.log
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)


def test_lint_not_probed_until_check_passes(tmp_path):
    """lint_cmd runs strictly AFTER check_cmd passes: when the check gate fails unrepairably, the run
    Blocks at the check gate and the lint command is NEVER probed (no lint.log, no lint marker)."""
    env, work, binp = _lint_env(tmp_path, title="Lint gated behind check")
    env["STUB_CHECK_FAIL"] = "1"; env["STUB_REPAIR_NOFIX"] = "1"   # check fails, repair can't heal it
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0 and "checks still failing" in r.stderr.lower()
    assert _lint_tl(tmp_path) == []                        # lint never ran — check never passed
    assert _lint_log(tmp_path) is None
    assert "https://stub/pr/1" not in r.stdout


def test_lint_cmd_declared_in_manifest_runs_end_to_end(tmp_path):
    """The manifest-declared path end-to-end (no env override): a green lint_cmd read from origin/main's
    .yr/factory.toml runs and the build proceeds — proving the manifest tuple carries the key, not just
    the env."""
    work, _ = _make_repo(tmp_path)
    binp = _lint_bin(tmp_path)
    lint_marker = tmp_path / "manifest_lint_ran"
    _exec(binp / "mlint.sh", f'#!/usr/bin/env bash\n: > "{lint_marker}"\nexit 0\n')
    (work / ".yr" / "factory.toml").write_text(f'lint_cmd = "bash {binp / "mlint.sh"}"\n')
    _git(["add", "-A"], work); _git(["commit", "-q", "-m", "declare lint"], work)
    _git(["push", "-q", "origin", "main"], work)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Manifest lint"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert lint_marker.exists()                            # the manifest's lint_cmd actually ran
    assert "https://stub/pr/1" in r.stdout


# ---- criterion: lint fail -> deterministic autofix first (no LLM), then re-run BOTH gates -------------

def test_lint_fail_autofix_heals_no_llm_and_rechecks(tmp_path):
    """A lint failure with a declared lint_fix_cmd that heals: the DETERMINISTIC autofix runs (no LLM
    stage), then BOTH check_cmd and lint_cmd re-run against the mutated tree before the stage passes."""
    env, work, binp = _lint_env(tmp_path, title="Autofix heals")
    env["STUB_LINT_FAIL"] = "1"    # lint fails until the autofix drops `lint_ok`
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    lint_tl = _lint_tl(tmp_path)
    assert lint_tl.count("LINTFIX") == 1                   # the autofix ran, exactly once
    assert lint_tl.count("LINT") >= 2                      # probe (fail) + at least one re-run (pass)
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl                          # NO LLM stage ran — the autofix sufficed
    assert tl.count("CHECK") == 2                          # check_cmd RE-RAN after the autofix mutation
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)


def test_lint_autofix_alone_triggers_recheck_even_though_llm_never_runs(tmp_path):
    """The deterministic autofix alone counts as a repair-path mutation: check_cmd must re-run after it
    even though no LLM stage ever fired (the criterion's 'the deterministic autofix alone included')."""
    env, work, binp = _lint_env(tmp_path, title="Autofix alone rechecks")
    env["STUB_LINT_FAIL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl and "REPAIR" not in tl   # no LLM repair of either kind
    assert tl.count("CHECK") == 2                          # yet the check gate re-ran post-autofix


# ---- criterion: autofix that doesn't heal -> ONE LLM repair -> re-run BOTH gates -> Blocked if failing

def test_lint_fail_unfixed_one_llm_repair_then_blocked(tmp_path):
    """Autofix runs but doesn't heal, then the single LLM lint-repair also doesn't heal: exactly ONE LLM
    repair fires, then the run ends Blocked (never a PR)."""
    env, work, binp = _lint_env(tmp_path, title="Unfixable lint")
    env["STUB_LINT_FAIL"] = "1"; env["STUB_FIX_NOHEAL"] = "1"   # neither autofix nor LLM heal it
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "lint still failing" in r.stderr.lower()
    tl = _timeline(tmp_path)
    assert tl.count("LINTREPAIR") == 1                     # exactly ONE LLM repair attempt
    assert _lint_tl(tmp_path).count("LINTFIX") == 1        # the autofix ran first (once), deterministically
    edits = " ".join(_edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits
    assert "https://stub/pr/1" not in r.stdout            # no PR


def test_lint_fail_no_fix_cmd_goes_straight_to_one_llm_repair(tmp_path):
    """With NO lint_fix_cmd declared, the autofix step is skipped entirely — the run goes straight to the
    single LLM lint-repair. Here that repair heals, so both gates re-run and the build proceeds."""
    env, work, binp = _lint_env(tmp_path, title="No fix cmd", declare_fix=False)
    env["STUB_LINT_FAIL"] = "1"; env["STUB_LINTREPAIR_HEAL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    lint_tl = _lint_tl(tmp_path)
    assert "LINTFIX" not in lint_tl                        # no autofix was declared, so none ran
    tl = _timeline(tmp_path)
    assert tl.count("LINTREPAIR") == 1                     # one LLM repair, which healed it
    assert tl.count("CHECK") == 2                          # both gates re-ran after the repair mutation
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)


def test_lint_repaired_but_check_now_fails_ends_blocked(tmp_path):
    """After a repair-path mutation heals lint, the mandatory check_cmd re-run must still pass: if the
    fix broke the check suite, EITHER gate failing ends the run Blocked (the shipped tree is what the
    review bundle attests). No LLM lint stage runs here — the autofix alone healed lint."""
    work, _ = _make_repo(tmp_path)
    binp = _lint_bin(tmp_path)
    # a check that PASSES until the lint autofix drops `lint_ok`, then FAILS (the fix broke the tree)
    _exec(binp / "check.sh", '#!/usr/bin/env bash\n'
                             'echo CHECK >> "$STUB_TIMELINE"\n'
                             '[ -f lint_ok ] && exit 1\n'
                             'exit 0\n')
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Fix breaks checks"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_LINT_TL"] = str(tmp_path / "lint_tl")
    env["LINT_CMD"] = f"bash {binp / 'lint.sh'}"; env["LINT_FIX_CMD"] = f"bash {binp / 'lintfix.sh'}"
    env["STUB_LINT_FAIL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl                          # the autofix healed lint; no LLM stage needed
    assert _lint_tl(tmp_path).count("LINTFIX") == 1
    assert tl.count("CHECK") == 2                          # initial pass + the post-mutation re-run (fail)
    edits = " ".join(_edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits
    assert "https://stub/pr/1" not in r.stdout


# ---- criterion: lint_cmd / lint_fix_cmd exit 126|127 -> env hold naming the lint cmd + log, no LLM ----

def test_lint_env_failure_126_holds_naming_lint_cmd_no_repair(tmp_path):
    """A lint_cmd exit 126 (found-but-not-executable) is an ENVIRONMENT hold: no LLM repair, and the
    record names the LINT command and lint.log — never the check command's text or checks.log."""
    env, work, binp = _lint_env(tmp_path, title="Lint cannot execute")
    env["STUB_LINT_ENVFAIL"] = "126"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl and "REPAIR" not in tl   # NO LLM repair attempt of any kind
    assert _lint_tl(tmp_path) == ["LINT"]                  # probed once, failed closed (no re-run)
    comments = " ".join(_comments(tl))
    assert comments                                        # a hold WAS recorded (never a silent claim)
    assert "hold" in comments.lower()
    assert "lint.log" in comments                          # names the lint log path
    assert f"bash {binp / 'lint.sh'}" in comments          # names the lint COMMAND that failed
    assert "checks.log" not in comments                    # NOT the check command's log
    assert "check command could not execute" not in comments   # NOT the check-gate hold's text
    assert "Blocked" in " ".join(_edits(tl))
    assert "https://stub/pr/1" not in r.stdout


def test_lint_env_failure_127_also_holds_naming_lint_cmd(tmp_path):
    """The other 'cannot execute' code, 127 (command not found), is treated the same way."""
    env, work, binp = _lint_env(tmp_path, title="Lint tool missing")
    env["STUB_LINT_ENVFAIL"] = "127"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl
    comments = " ".join(_comments(tl))
    assert "lint.log" in comments and f"bash {binp / 'lint.sh'}" in comments
    assert "checks.log" not in comments
    assert "Blocked" in " ".join(_edits(tl)) and "https://stub/pr/1" not in r.stdout


def test_lint_autofix_env_failure_holds_naming_the_fix_cmd_no_repair(tmp_path):
    """An autofix (lint_fix_cmd) exit 126/127 is environmental too: the same lint-naming env hold — here
    naming the AUTOFIX command — and NO LLM repair follows."""
    env, work, binp = _lint_env(tmp_path, title="Autofix cannot execute")
    env["STUB_LINT_FAIL"] = "1"; env["STUB_FIX_ENVFAIL"] = "127"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" not in tl                          # no LLM repair on an environmental autofix death
    comments = " ".join(_comments(tl))
    assert "lint.log" in comments
    assert f"bash {binp / 'lintfix.sh'}" in comments       # the hold names the autofix command that failed
    assert "checks.log" not in comments
    assert "Blocked" in " ".join(_edits(tl))
    assert "https://stub/pr/1" not in r.stdout


def test_lint_env_hold_preserves_worktree_for_resume(tmp_path):
    """A lint env hold inherits the check gate's preserve+resume discipline (issue #39): the worktree is
    NOT torn down and the hold marker is dropped, so a relaunch can resume."""
    env, work, binp = _lint_env(tmp_path, title="Lint hold preserves")
    env["STUB_LINT_ENVFAIL"] = "126"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert _wt_dir(tmp_path) is not None                   # worktree preserved
    sd = _state_dir(tmp_path)
    assert sd is not None and (sd / "env-hold").exists()   # the resume marker is present


def test_lint_env_hold_appends_one_env_hold_ledger_row(tmp_path):
    """#211 puts a ledger row at every terminal branch; the lint env hold reuses the existing env-hold
    terminal, so it inherits that row rather than minting a new terminal path."""
    env, work, binp = _lint_env(tmp_path, title="Lint hold ledger")
    env["STUB_LINT_ENVFAIL"] = "126"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "env-hold", "decision": None}


def test_lint_unfixed_block_appends_one_blocked_ledger_row(tmp_path):
    """A lint failure surviving the one repair reuses the existing fail_blocked terminal — one blocked
    ledger row, no new terminal path minted."""
    env, work, binp = _lint_env(tmp_path, title="Lint block ledger")
    env["STUB_LINT_FAIL"] = "1"; env["STUB_FIX_NOHEAL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "blocked", "decision": None}


# ---- criterion: prompt-independence pins (existing check-repair pin unchanged; new lint-repair pin;
#                 a lint failure never triggers the check-repair prompt, nor a test failure the lint one)

def _all_stdin(tmp):
    """Every claude stage's raw stdin (task prompt) content, in call order."""
    return _stdin_raw_calls(tmp)


def test_lint_repair_prompt_text_pinned(tmp_path):
    """A NEW pin fixing the lint-repair prompt's text: it names the failing lint COMMAND, confines the
    fix to exactly the flagged files (test or production), forbids changing a test's assertions, and
    carries the lint output — distinct from the tests-frozen check-repair prompt."""
    env, work, binp = _lint_env(tmp_path, title="Lint prompt pin")
    env["STUB_LINT_FAIL"] = "1"; env["STUB_FIX_NOHEAL"] = "1"   # force the LLM lint-repair to fire
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0                               # unfixed -> Blocked, but the repair prompt was sent
    lint_calls = [c for c in _all_stdin(tmp_path) if "The lint gate FAILS" in c]
    assert len(lint_calls) == 1, "exactly one LLM lint-repair prompt expected"
    prompt = lint_calls[0]
    assert f"The lint gate FAILS (command: bash {binp / 'lint.sh'})." in prompt   # names the lint command
    assert ("Fix ONLY what the lint output flags, in exactly the files it names, test or production; "
            "change no test's assertions; make the linter pass, nothing else.") in prompt
    assert "Lint output:" in prompt


def test_lint_failure_does_not_trigger_the_check_repair_prompt(tmp_path):
    """Direction 1: a lint failure must route to the lint-repair prompt ONLY — never the tests-frozen
    check-repair prompt. The check gate passes clean here, so no check-repair may fire."""
    env, work, binp = _lint_env(tmp_path, title="Lint not check-repair")
    env["STUB_LINT_FAIL"] = "1"; env["STUB_FIX_NOHEAL"] = "1"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = _timeline(tmp_path)
    assert "LINTREPAIR" in tl and "REPAIR" not in tl       # the lint stage fired; the check-repair did not
    # the tests-frozen check-repair prompt never went out on any stage
    assert not any("The project tests FAIL." in c for c in _all_stdin(tmp_path))


def test_test_failure_does_not_trigger_the_lint_prompt(tmp_path):
    """Direction 2: a check (test) failure must route to the check-repair prompt ONLY — never the lint
    prompt — even when a lint_cmd is also declared (and green)."""
    env, work, binp = _lint_env(tmp_path, title="Check not lint-repair")
    env["STUB_CHECK_FAIL"] = "1"    # check fails until the check-repair writes `repaired`; lint stays green
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "REPAIR" in tl and "LINTREPAIR" not in tl       # the check-repair fired; no lint stage
    # the lint prompt never went out on any stage
    assert not any("The lint gate FAILS" in c for c in _all_stdin(tmp_path))


def test_existing_check_repair_prompt_pin_still_passes(tmp_path):
    """The existing check-repair prompt pin's invariant (its load-bearing routing fragment + the scoping
    sentence) must survive this change unchanged — asserted directly here so a regression in the lint
    slice that disturbs the check-repair prompt is caught in this file too."""
    binp = tmp_path / "bin"; _stubs(binp)
    env = _all_stages_env(tmp_path, binp, "Check-repair pin survives")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    by_stage = _stage_calls(tmp_path)
    for call in by_stage["REPAIR"]:
        assert "The project tests FAIL. Fix the PRODUCTION CODE so they pass — do NOT modify the tests." in call
        assert "Reproduce with the failing tests only; the runner re-runs the full check suite after this stage." in call


# ---- criterion: the review verdict, the merge path, and every non-check gate are untouched -----------

def test_lint_tier_leaves_review_and_pr_path_intact(tmp_path):
    """With a (green) lint tier declared, the downstream review verdict and PR/In-Review path are
    unchanged: the reviewer verdict is still posted on the PR and the run still reaches In Review."""
    env, work, binp = _lint_env(tmp_path, title="Lint leaves review intact")
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = _timeline(tmp_path)
    assert "REVIEW" in tl                                  # the reviewer stage ran
    assert "PRCOMMENT" in tl                               # its verdict was attached to the PR
    assert "https://stub/pr/1" in r.stdout
    assert any(l.startswith("EDIT") and "InReview" in l for l in tl)
    assert not any("REASONFIELD" in l and "Blocked" in l for l in tl)


def test_lint_tier_does_not_disturb_the_terminal_merge_record(tmp_path):
    """The terminal (shadow) merge decision — the merge path — is untouched by the lint tier: a green
    lint declared alongside a green build still posts exactly one YR-MERGE-SHADOW record on the PR."""
    work, _ = _make_repo(tmp_path)
    binp = _lint_bin(tmp_path)
    env = _real(tmp_path, _env(tmp_path, binp, number=5, title="Lint vs merge record"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_LINT_TL"] = str(tmp_path / "lint_tl")
    env["LINT_CMD"] = f"bash {binp / 'lint.sh'}"
    env["STUB_ROLLUP_JSON"] = _rollup(tmp_path, [CR_OK])
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    r = _run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert _prcomments(tmp_path).count("YR-MERGE-SHADOW") == 1


# ============================================================================
# The factory's own manifest declares the key this tier reads (issue #215)
# ============================================================================

def test_factory_manifest_declares_lint_cmd():
    import tomllib
    manifest = tomllib.loads((ROOT / ".yr" / "factory.toml").read_text())
    assert manifest.get("lint_cmd") == "ruff check tools/ tests/"
