"""Acceptance tests for issue #474 (it-36 slice I) — the merge evaluator's `fragment_present`
condition, exercised through the FULL runner + `--re-evaluate` (never a bare unit test of
tools/merge_shadow.py, which tests/test_merge_shadow.py already covers exhaustively).

Two of the mandate's four named cases, proven end to end:
  * a runner-built PR always carries the fragment (the implement stage's own act) — PASS;
  * an attended edit (or a PR predating this slice) that strips/never adds the fragment — FAIL,
    legibly named on the record, never a silent block.
(The other two — "an attended PR with a fragment" and "an attended PR without one, at the point the
PR first opens" — are the SAME diff-based mechanism as the second case here: dev-runner.sh's
`shadow_fragment_present` never distinguishes WHO opened the PR, only whether `changelog_dir`
changed between base and head.)

Reuses test_dev_runner_reevaluate.py's own harness verbatim (`_first_build`, `_reeval_env`,
`_run_reeval`, `_reeval_body`) — a REAL first build (stubbed LLM/gh) produces an actual pushed
single-commit branch carrying the fragment the implement-stage act wrote; the second test then
pushes one more commit directly to `origin` (bypassing the runner entirely) that deletes the
fragment, simulating exactly what an attended session's own duty failure — or a PR that predates
this slice's changelog_dir key — looks like on the wire: a diff with nothing under changelog_dir.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td                    # noqa: E402
import test_dev_runner_reevaluate as tdr         # noqa: E402

ROOT = td.ROOT
EMDASH = tdr.EMDASH


def test_fragment_present_passes_for_a_runner_built_pr_via_reevaluate(tmp_path):
    """The implement stage always writes the fragment before its single commit — a record-less
    re-evaluation of that SAME branch reads `fragment_present: pass` in the posted record."""
    work, origin, env1, run_dir, branch, head_oid = tdr._first_build(
        tmp_path, number=60, title="Fragment present, runner-built")
    frag = subprocess.run(["git", "-C", str(work), "show", f"{head_oid}:changelog.d/60.md"],
                          capture_output=True, text=True, check=True).stdout
    assert "Source: test/repo#60" in frag

    env2 = tdr._reeval_env(tmp_path, env1, pr_number=600, head_ref=branch, head_oid=head_oid, comments=[])
    r = tdr._run_reeval(60, 600, env2)
    assert r.returncode == 0, r.stderr
    body = tdr._reeval_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    rec = td._shadow_block(body)
    assert rec["conditions"]["fragment_present"] == "pass"


def test_fragment_present_fails_when_the_changelog_dir_carries_nothing_in_the_diff(tmp_path):
    """A follow-up commit pushed straight to `origin` (never through the runner) deletes the
    fragment — the shape of an attended edit that skipped the duty, or a PR whose base predates
    changelog_dir entirely. `--re-evaluate` against that new head names fragment_present as the
    (sole) failed condition, never silently passing."""
    work, origin, env1, run_dir, branch, head_oid = tdr._first_build(
        tmp_path, number=61, title="Fragment stripped by an attended edit")
    # AMEND (never a new commit): re_evaluate's record-less lookup matches the run bundle's
    # recorded base_sha against `<new head>^` — a new commit on top would shift that parent to the
    # OLD head_oid, not the branch's true fork point from main, and the lookup would find nothing.
    # An amend keeps the same parent (the same base_sha) while changing the tree, exactly what a
    # real attended edit stripping the fragment before the diff. Line-for-line the "PR predating
    # this slice" case is the same: a diff with nothing under changelog_dir.
    td._git(["fetch", "-q", "origin", branch], work)
    td._git(["checkout", "-q", branch], work)
    (work / "changelog.d" / "61.md").unlink()
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "--amend", "--no-edit"], work)
    td._git(["push", "-q", "--force", "origin", branch], work)
    new_head = subprocess.run(["git", "-C", str(work), "rev-parse", branch],
                              capture_output=True, text=True, check=True).stdout.strip()
    td._git(["checkout", "-q", "main"], work)

    env2 = tdr._reeval_env(tmp_path, env1, pr_number=610, head_ref=branch, head_oid=new_head, comments=[])
    r = tdr._run_reeval(61, 610, env2)
    assert r.returncode == 0, r.stderr
    body = tdr._reeval_body(run_dir)
    assert body is not None
    first = body.splitlines()[0]
    assert first.startswith(f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} fragment_present")
    rec = td._shadow_block(body)
    assert rec["conditions"]["fragment_present"] == "fail"
    assert rec["conditions"]["ci_green"] == "pass"          # every OTHER condition still passes —
    assert rec["conditions"]["terminal_approval"] == "pass"  # fragment_present is the ONLY failure


# ============ I9 (cold review of #474): the fragment write itself, through the full runner =========

def _write_changelog_dir_manifest(work, changelog_dir_value):
    (work / ".yr" / "factory.toml").write_text(
        f'check_cmd = "true"\nchangelog_dir = "{changelog_dir_value}"\n')
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "declare changelog_dir"], work)
    td._git(["push", "-q", "origin", "main"], work)


def _bare_manifest_repo(tmp, content, name="bare_manifest_repo"):
    """A `.yr/factory.toml`-only directory, no git at all — the manifest read's own working-tree
    fallback (test_stage_conduct_manifest.py's `_conduct_manifest_repo` precedent), so a malformed
    changelog_dir is the ONLY variable in play."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    (repo / ".yr" / "factory.toml").write_text(content)
    return repo


def test_manifest_declared_changelog_dir_end_to_end(tmp_path):
    """I9(a): a manifest-declared changelog_dir changes WHERE the implement stage writes the
    fragment — the seam's own point (never a hardcoded changelog.d/)."""
    work, origin = td._make_repo(tmp_path)
    _write_changelog_dir_manifest(work, "notes/")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=70, title="Declared changelog_dir"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["70", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "changelog_dir: 'notes/' (source: manifest)" in r.stderr
    branch = tdr._branch_name(work, 70)
    frag = subprocess.run(["git", "-C", str(work), "show", f"origin/{branch}:notes/70.md"],
                          capture_output=True, text=True, check=True).stdout
    assert "Source: test/repo#70" in frag
    rc = subprocess.run(["git", "-C", str(work), "show", f"origin/{branch}:changelog.d/70.md"],
                        capture_output=True, text=True).returncode
    assert rc != 0, "the fragment must land under the DECLARED directory, never the default too"


def test_no_fragment_written_when_implementer_changes_nothing_hard_block_still_fires(tmp_path):
    """I9(b): the `git status --porcelain` guard — no fragment is written when the implementer
    produced NOTHING, and the pre-existing 'no changes produced' hard block still fires (the
    regression an earlier, unconditional fragment write reintroduced — caught by the full
    tests/test_dev_runner.py run and fixed before this fold)."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=71, title="Produces nothing"), work)
    r = td._run(["71", "--repo", "test/repo"], env)   # no STUB_CLAUDE_CHANGE: the implementer writes nothing
    assert r.returncode != 0 and "no changes" in r.stderr.lower()
    run_dirs = list((tmp_path / "drhome" / "runs").glob("71-*"))
    assert run_dirs, "no run dir was created"
    salvage = run_dirs[0] / "block-salvage.patch"
    assert not salvage.exists(), "an empty diff (no fragment either) writes no salvage patch"


def test_malformed_changelog_dir_bounces_needs_info(tmp_path):
    """I9(c): a rejected changelog_dir value (a leading '/', the seam's own path-safety check)
    bounces the run to Needs-info BEFORE any claim, naming the key and the rejected value — never a
    silent default (test_stage_conduct_manifest.py's `_assert_needs_info_fail_closed` shape)."""
    repo = _bare_manifest_repo(tmp_path, 'check_cmd = "true"\nchangelog_dir = "/etc/passwd"\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=72, title="Malformed changelog_dir")
    env["BASE_REPO"] = str(repo)
    r = td._run(["72", "--repo", "test/repo"], env)
    assert r.returncode == 3, r.stdout + r.stderr
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                       # never proceeds to any stage
    assert "NeedsInfo" in " ".join(td._edits(tl))
    comments = " ".join(td._comments(tl))
    assert "changelog_dir" in comments
    assert "/etc/passwd" in comments


def test_pr_body_cites_the_changelog_fragment_path(tmp_path):
    """I9(d): PR_BODY names the fragment's own path, so a human (or a future changelog compiler)
    can find it without re-deriving changelog_dir."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=73, title="Cites its own fragment"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["73", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    calls = (tmp_path / "gh_calls").read_text()
    assert "Changelog fragment: `changelog.d/73.md`" in calls
