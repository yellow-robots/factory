"""Acceptance tests for issue #327 — build-start snapshot: fetch before the manifest read.

Derived from the issue's acceptance criteria (the spec), NOT the implementation's internals:

  1. A run-start fetch of `origin` (broad — `fetch origin`, no single-branch refspec) happens BEFORE the
     manifest read, so a manifest change pushed to origin between two runs is never masked by whatever
     ref a PREVIOUS run's own (later) fetch happened to leave behind.
  2. The manifest ref is resolved to a single pinned sha after that fetch, read from that sha; when the
     build's base ref names the same ref (the default, and every repo shipped today), the worktree is cut
     from that exact same pinned sha — one snapshot, both reads.
  3. The pinned manifest sha is logged alongside the existing config-resolution lines, so which manifest
     governed a run is readable from the dispatch log alone.
  4. The fetch is bounded, prompt-free, and env-tunable. It is SKIPPED (not environmental) when the
     checkout isn't a git repo or carries no `origin` remote — the working-tree manifest fallback then
     applies unchanged. When `origin` exists but the fetch fails, the run exits environmentally BEFORE
     any claim — no board write.
  5. Docs (skills/factory/references/pipeline.md, and the stale comment in tools/dev-runner.sh) describe
     the contract this task actually ships.

Reuses the shared harness only (tests/test_dev_runner.py's stub set, fixtures, and helpers) — no private
clone of the classifier or the gh/claude stubs. Staleness is produced the way `_make_factory_repo`
already does it in tests/test_dev_runner.py: commits pushed to the fixture origin FROM A SEPARATE CLONE,
never through the `work` checkout under test (pushing through `work` itself would update `work`'s own
`refs/remotes/origin/main` and produce no staleness at all). The delivery-side harness this builds on is
tests/test_stage_conduct_manifest.py's `_commit_conduct_manifest` / delivered-header pattern — the
observable signal for "did the fresh manifest govern this run" is the delivered `stage_conduct` block,
not a `check_cmd (source: manifest)` line (unreachable: the shared harness's base env always sets
CHECK_CMD, which outranks the manifest).

Runs under `.venv/bin/python -m pytest tests/ -q` (attended); `pytest tests/ -q` in a cut build worktree.
"""
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # shared stub harness (gh/claude/check stubs + fixtures)

ROOT = td.ROOT
HEADER = "Per-repo stage conduct (source: .yr/factory.toml, key stage_conduct):"


# ============ shared helper ============

def _push_from_separate_clone(tmp, origin, files, message="fresh push from a separate clone", name="other_clone"):
    """Commit `files` (dict of repo-relative path -> content) to `origin`'s main branch from a SEPARATE
    clone — never through the `work` checkout the run under test reads from. This is exactly how
    tests/test_dev_runner.py's `_make_factory_repo(tmp, behind=N)` produces genuine staleness: `work`'s
    own `refs/remotes/origin/main` does not see this commit until IT fetches. Returns the clone dir."""
    other = tmp / name
    td._git(["clone", "-q", str(origin), str(other)], tmp)
    td._git(["config", "user.email", "t@t"], other)
    td._git(["config", "user.name", "tester"], other)
    for relpath, content in files.items():
        p = other / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    td._git(["add", "-A"], other)
    td._git(["commit", "-q", "-m", message], other)
    td._git(["push", "-q", "origin", "main"], other)
    return other


# ============ (1) the run-start fetch runs BEFORE the manifest read ============

def test_manifest_change_pushed_from_separate_clone_after_last_fetch_governs_next_run(tmp_path):
    """A manifest change pushed to origin from a SEPARATE clone (never touching `work`'s own checkout,
    so `work`'s local origin/main is genuinely stale) still governs the very next run — its delivered
    stage_conduct table matches the `.yr/factory.toml` at the sha the run's own fetch pulls in, never a
    snapshot a previous run's (later) fetch happened to leave behind."""
    work, origin = td._make_repo(tmp_path)
    _push_from_separate_clone(
        tmp_path, origin,
        {".yr/factory.toml": 'check_cmd = "true"\nstage_conduct = ["check_cmd usually finishes within 45s"]\n'},
    )
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Freshness governs next run"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    expected_block = HEADER + "\ncheck_cmd usually finishes within 45s"
    stdin_calls = td._stdin_stage_calls(tmp_path)
    for stage in ("IMPL", "TEST"):
        assert stage in stdin_calls, f"{stage} stage never ran"
        assert expected_block in stdin_calls[stage][0], (
            f"stage {stage}: manifest pushed from a separate clone after work's last fetch did not "
            "govern this run — the run-start fetch isn't freshening origin before the manifest read"
        )


def test_repeated_manifest_changes_from_separate_clones_each_govern_their_own_next_run(tmp_path):
    """Not a one-shot fluke: TWO successive manifest changes, each pushed from its own separate clone
    between runs, each govern their own immediately-following run — proving the fetch happens on every
    run's own start, not just once."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)

    # Each run gets its own tmp-path-rooted STUB_* file set (distinct DEV_RUNNER_HOME too, via `_real`)
    # so the two runs' recorded timelines/claude calls never share a file — same BASE_REPO (`work`) and
    # `origin` throughout, only the recording location differs per run.
    run1_dir = tmp_path / "run1"; run1_dir.mkdir()
    _push_from_separate_clone(
        tmp_path, origin, {".yr/factory.toml": 'check_cmd = "true"\nstage_conduct = ["first table"]\n'},
        name="clone_one",
    )
    env1 = td._real(run1_dir, td._env(run1_dir, binp, number=5, title="First manifest"), work)
    env1["STUB_CLAUDE_CHANGE"] = "1"
    r1 = td._run(["5", "--repo", "test/repo"], env1)
    assert r1.returncode == 0, r1.stderr
    stdin1 = td._stdin_stage_calls(run1_dir)
    assert HEADER + "\nfirst table" in stdin1["IMPL"][0]

    run2_dir = tmp_path / "run2"; run2_dir.mkdir()
    _push_from_separate_clone(
        tmp_path, origin, {".yr/factory.toml": 'check_cmd = "true"\nstage_conduct = ["second table"]\n'},
        name="clone_two",
    )
    env2 = td._real(run2_dir, td._env(run2_dir, binp, number=6, title="Second manifest"), work)
    env2["STUB_CLAUDE_CHANGE"] = "1"
    r2 = td._run(["6", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr
    stdin2 = td._stdin_stage_calls(run2_dir)
    assert HEADER + "\nsecond table" in stdin2["IMPL"][0]
    assert HEADER + "\nfirst table" not in stdin2["IMPL"][0]


# ============ (2) worktree cut from the SAME pinned snapshot as the manifest ============

def test_worktree_is_cut_from_the_same_pinned_snapshot_as_the_manifest(tmp_path):
    """Whenever base_ref names the same ref as the manifest ref (the default, and every repo shipped
    today), the worktree the run cuts is from that SAME pinned sha, not a second, possibly stale read of
    the moving ref. Proven directly: a file pushed alongside the manifest change from a separate clone
    must be visible in the checked-out worktree. STUB_CHECK_ENVFAIL preserves the worktree for
    inspection instead of tearing it down (test_dev_runner.py's own env-hold pattern, e.g.
    test_env_failure_preserves_worktree_markers_and_run_dir)."""
    work, origin = td._make_repo(tmp_path)
    _push_from_separate_clone(
        tmp_path, origin,
        {".yr/factory.toml": 'check_cmd = "true"\n', "canary.txt": "fresh snapshot\n"},
    )
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=7, title="Worktree from pinned sha"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126"})
    r = td._run(["7", "--repo", "test/repo"], env)
    assert r.returncode != 0   # environmental hold, not a clean success — worktree preserved for inspection

    wt = td._wt_dir(tmp_path)
    assert wt is not None, "expected a preserved worktree from the env hold"
    assert (wt / "canary.txt").exists(), (
        "the worktree was not cut from the same freshly-fetched snapshot the manifest was read from"
    )
    assert (wt / "canary.txt").read_text() == "fresh snapshot\n"


# ============ (3) the pinned manifest sha is logged, alongside the config-resolution lines ============

def test_pinned_manifest_sha_is_logged_alongside_config_resolution_lines(tmp_path):
    """Which manifest governed a run must be readable from the dispatch log alone. The exact resolved
    sha (git rev-parse of origin's tip after this run's own fetch) appears on its own log line, carrying
    a `(source: ...)` annotation the same shape as the check_cmd/check_timeout family, and names the
    manifest so the line is self-explanatory without transcript archaeology."""
    work, origin = td._make_repo(tmp_path)
    _push_from_separate_clone(tmp_path, origin, {".yr/factory.toml": 'check_cmd = "true"\n'}, message="bump manifest")
    expected_sha = subprocess.run(
        ["git", "-C", str(origin), "rev-parse", "main"], capture_output=True, text=True, check=True,
    ).stdout.strip()

    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=6, title="Log the pinned sha"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["6", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    assert expected_sha in r.stderr, "the pinned manifest sha never appears in the run log"
    sha_lines = [l for l in r.stderr.splitlines() if expected_sha in l]
    assert sha_lines, "expected the resolved sha on its own log line"
    assert any("(source:" in l for l in sha_lines), (
        "the sha line doesn't carry a (source: ...) annotation like the check_cmd/check_timeout family"
    )
    assert any("manifest" in l.lower() for l in sha_lines), (
        "the sha line doesn't name the manifest, so which manifest governed the run isn't derivable "
        "from the log alone"
    )


# ============ (4) skip (not environmental) when not a git repo / no origin remote ============

def test_no_git_checkout_skips_fetch_and_keeps_working_tree_fallback(tmp_path):
    """A target checkout that isn't a git repo at all (the dry-run manifest-dir shape existing fixtures
    already build on) must not be treated as environmental — the fetch is skipped, the ref read yields
    nothing, and the working-tree manifest fallback applies exactly as before this task."""
    repo = tmp_path / "repo"; (repo / ".yr").mkdir(parents=True)
    (repo / ".yr" / "factory.toml").write_text('check_cmd = "make test"\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); del env["CHECK_CMD"]
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["check_cmd"] == "make test"


def test_git_repo_without_origin_remote_skips_fetch_and_keeps_working_tree_fallback(tmp_path):
    """A real git repo that has never been pushed anywhere (no `origin` remote at all — the never-pushed
    shape existing fixtures build on) also skips the fetch: not environmental. The manifest ref read
    (which needs the now-absent remote) yields nothing and falls back to the working-tree file exactly
    as before this task."""
    repo = tmp_path / "repo"; repo.mkdir()
    td._git(["init", "-b", "main", "."], repo)
    td._git(["config", "user.email", "t@t"], repo)
    td._git(["config", "user.name", "tester"], repo)
    (repo / ".yr").mkdir(parents=True)
    (repo / ".yr" / "factory.toml").write_text('check_cmd = "make test"\n')
    td._git(["add", "-A"], repo)
    td._git(["commit", "-q", "-m", "seed"], repo)

    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp)
    env["BASE_REPO"] = str(repo)
    env["GIT_BIN"] = "git"
    del env["CHECK_CMD"]
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["check_cmd"] == "make test"


# ============ (4, continued) a real fetch failure exits environmentally, BEFORE any claim ============

def test_fetch_failure_with_origin_present_exits_environmentally_before_claim(tmp_path):
    """The remote EXISTS but the fetch itself fails — distinct from 'no origin at all' above. This must
    exit BEFORE claim: no board write (no Status/Reason edit, no issue comment, no gh call whatsoever —
    the run-start fetch sits before even the gh issue-view read), the task stays Ready for the next
    poll. Same pre-claim environmental-exit shape (`die`, rc 1) as an existing failure like 'could not
    fetch issue'."""
    work, _ = td._make_repo(tmp_path)
    td._git(["remote", "set-url", "origin", str(tmp_path / "does-not-exist.git")], work)

    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=8, title="Unreachable origin"), work)
    env["MANIFEST_FETCH_TIMEOUT"] = "5"
    r = td._run(["8", "--repo", "test/repo"], env)

    assert r.returncode == 1, r.stdout + r.stderr
    assert "fetch" in r.stderr.lower()
    assert not td._timeline(tmp_path)                        # no gh/claude call was ever made
    assert not (tmp_path / "gh_calls").exists()               # gh never invoked at all — pre-claim
    assert "https://stub/pr/1" not in r.stdout


def test_manifest_fetch_timeout_is_env_tunable(tmp_path):
    """The run-start fetch's bound is env-tunable (MANIFEST_FETCH_TIMEOUT): different override values
    surface in the environmental exit's own message, proving the bound actually used is the one the
    environment set, not a hardcoded constant — the 'env-tunable bound with a small default' criterion,
    checked black-box via the run's own visible output."""
    work, _ = td._make_repo(tmp_path)
    td._git(["remote", "set-url", "origin", str(tmp_path / "does-not-exist.git")], work)
    binp = tmp_path / "bin"; td._stubs(binp)

    for i, bound in enumerate(("3", "9")):
        env = td._real(tmp_path, td._env(tmp_path, binp, number=8, title="Tunable bound"), work)
        env["MANIFEST_FETCH_TIMEOUT"] = bound
        env["STUB_TIMELINE"] = str(tmp_path / f"timeline-{i}")
        r = td._run(["8", "--repo", "test/repo"], env)
        assert r.returncode == 1, r.stdout + r.stderr
        assert bound in r.stderr, f"expected the {bound}s override reflected in the exit message"


# ============ (5) docs: pipeline.md + the rewritten dev-runner.sh comment, in the same PR ============

def test_pipeline_md_documents_the_run_start_fetch_and_pinned_sha_manifest_read():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text()
    assert "#327" in text
    assert "pinned" in text.lower() and "sha" in text.lower()
    low = text.lower()
    idx = low.index("pinned")
    nearby = text[max(0, idx - 800): idx + 800]
    assert "fetch" in nearby.lower()
    assert "origin" in nearby.lower()
    assert "manifest" in nearby.lower()


def test_pipeline_md_worktree_row_states_the_shared_pinned_sha_contract():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text()
    idx = text.index("| **Worktree** |")
    row = text[idx: idx + 800]
    assert "base_ref" in row
    assert "manifest" in row.lower()
    assert "pinned" in row.lower() or "same snapshot" in row.lower() or "one snapshot" in row.lower()


def test_dev_runner_manifest_read_comment_no_longer_makes_the_stale_claim():
    """The old comment on the manifest-read block ('the worktree is cut from that ref, so the manifest
    must come from there too') is untrue whenever base_ref diverges from the manifest ref — it must be
    gone, replaced by language describing the pinned-sha contract this task actually ships."""
    text = (ROOT / "tools" / "dev-runner.sh").read_text()
    assert "the worktree is cut from that ref, so the manifest must come from there too" not in text
    idx = text.index("Per-repo build config lives in the repo")
    nearby = text[idx: idx + 2000]
    assert "pinned" in nearby.lower()
    assert "sha" in nearby.lower()
