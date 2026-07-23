"""Acceptance tests for issue #275 — gate declaration: check_cmd required, the silent fallback removed
(technical-rfc yellow-robots/factory#271 epic, slice 4).

Derived from the issue's acceptance criteria (the spec), NOT from the implementation's internals:

  1. A manifest that declares no `check_cmd` refuses the work before claim, worktree, or any stage —
     the DoR refusal shape (Status=Backlog + Reason=Needs-info, a comment, exit 3), naming the missing
     key and the governing rule.
  2. Required-ness is judged on the manifest alone: an environment `CHECK_CMD` does not rescue an
     undeclared manifest key from the bounce above.
  3. Where the manifest DOES declare `check_cmd`, today's precedence is unchanged — an environment
     `CHECK_CMD` still overrides the declared value for the session — and the run's log names the
     effective source actually used (`manifest` or `env`).
  4. The built-in pytest fallback command is gone from the source entirely: no code path guesses a
     test command when neither env nor manifest declares one.

Reuses the shared harness only (tests/test_dev_runner.py's stub set, fixtures, and helpers) — no
private clone of the stubs.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # shared stub harness (gh/claude/check stubs + fixtures)

ROOT = td.ROOT
RUNNER = ROOT / "tools" / "dev-runner.sh"


def _make_repo_manifest_no_check_cmd(tmp):
    """A real, onboarded repo (a `.yr/factory.toml` present at the base ref) that declares every OTHER
    key normally but leaves `check_cmd` out — distinct from the un-onboarded case (no manifest at all,
    covered by test_dev_runner.py's `_make_repo_no_manifest`). This is the sparse-but-present manifest
    this issue's required-ness gate must bounce on."""
    origin = tmp / "origin.git"; origin.mkdir()
    td._git(["init", "--bare", "-b", "main", "."], origin)
    work = tmp / "work"; work.mkdir()
    td._git(["init", "-b", "main", "."], work)
    td._git(["config", "user.email", "t@t"], work); td._git(["config", "user.name", "tester"], work)
    (work / ".yr").mkdir(parents=True)
    (work / ".yr" / "factory.toml").write_text(
        '# onboarded, but check_cmd is deliberately withheld\nmodel = "sonnet"\n'
    )
    (work / "README.md").write_text("seed\n")
    td._git(["add", "-A"], work); td._git(["commit", "-q", "-m", "seed"], work)
    td._git(["remote", "add", "origin", str(origin)], work)
    td._git(["push", "-q", "origin", "main"], work)
    return work, origin


# ============ (1) undeclared check_cmd bounces before claim/worktree, naming the key ============

def test_undeclared_check_cmd_bounces_before_claim_and_worktree(tmp_path):
    work, _ = _make_repo_manifest_no_check_cmd(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="No check_cmd declared"), work)
    del env["CHECK_CMD"]                                       # no env override either
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3

    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                                     # no stage ever launched — refused pre-claim
    edit = " ".join(td._edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit            # the runner's existing DoR bounce shape
    comments = " ".join(td._comments(tl)).lower()
    assert "check_cmd" in comments and "not declared" in comments

    assert td._wt_dir(tmp_path) is None                        # never got as far as a worktree


def test_undeclared_check_cmd_bounce_names_the_governing_rule(tmp_path):
    """The refusal names the rule (issue #275 / required-ness), not just the bare key — so recovery is
    derivable from the message alone, without session memory or source archaeology."""
    work, _ = _make_repo_manifest_no_check_cmd(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="No check_cmd, wants the rule named"), work)
    del env["CHECK_CMD"]
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    assert "check_cmd" in r.stderr and "required" in r.stderr.lower()


# ============ (2) required-ness is judged on the manifest ALONE — env does not rescue it ============

def test_undeclared_check_cmd_bounces_even_with_env_check_cmd_present(tmp_path):
    """An env CHECK_CMD does NOT satisfy registration: the same repo as above, but this time an explicit
    CHECK_CMD is set in the environment — the bounce still fires, identically, before claim/worktree."""
    work, _ = _make_repo_manifest_no_check_cmd(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="No check_cmd, env set anyway"), work)
    env["CHECK_CMD"] = "pytest -q"                             # present, deliberately NOT deleted
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3

    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    edit = " ".join(td._edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit
    comments = " ".join(td._comments(tl)).lower()
    assert "check_cmd" in comments and "not declared" in comments
    assert td._wt_dir(tmp_path) is None


def test_undeclared_check_cmd_dryrun_bounces_regardless_of_env(tmp_path):
    """Same fork, via --dry-run (read-only reporting intent doesn't rescue an undeclared gate either):
    a manifest present but check_cmd-less, with CHECK_CMD set in the env, still refuses with exit 3."""
    repo = td._manifest_repo(tmp_path, check_cmd=td.NO_CHECK_CMD, model="sonnet")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_CMD"] = "pytest -q"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    assert "check_cmd" in r.stderr and "not declared" in r.stderr


# ============ (3) declared check_cmd: env still overrides, and the log names the effective source ====

def test_declared_check_cmd_no_env_logs_source_manifest(tmp_path):
    """With no env override, the manifest's declared check_cmd is used, and the run's log names the
    source as `manifest`."""
    repo = td._manifest_repo(tmp_path, check_cmd="make test")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); del env["CHECK_CMD"]
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout)["check_cmd"] == "make test"
    assert "check_cmd" in r.stderr and "make test" in r.stderr and "source: manifest" in r.stderr


def test_declared_check_cmd_env_override_logs_source_env(tmp_path):
    """An env CHECK_CMD still overrides a declared manifest check_cmd for the session (today's
    precedence, unchanged) — and the run's log names the effective source as `env`, not `manifest`."""
    repo = td._manifest_repo(tmp_path, check_cmd="make test")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_CMD"] = "pytest -q"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout)["check_cmd"] == "pytest -q"
    assert "check_cmd" in r.stderr and "pytest -q" in r.stderr and "source: env" in r.stderr
    assert "source: manifest" not in r.stderr


def test_declared_check_cmd_env_override_runs_end_to_end(tmp_path):
    """The env override isn't just reported by --dry-run — it's the command actually executed by the
    check gate on a real (non-dry-run) build, end to end."""
    work, _ = td._make_repo(tmp_path)                          # _make_repo's own seeded manifest declares check_cmd
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Env override runs"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"                            # _base_env already sets CHECK_CMD to the check.sh stub
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    assert "CHECK" in tl and td._ran(tl)
    assert "source: env" in r.stderr


# ============ (4) the built-in pytest fallback is gone — no code path guesses a test command =========

def test_no_builtin_pytest_fallback_command_in_source():
    """PIN: the runner's source carries no hardcoded pytest invocation anywhere — the silent fallback
    (`$BASE_REPO/.venv/bin/python -m pytest tests/ -q`) that issue #275 removes must not reappear under
    any other spelling."""
    text = RUNNER.read_text(encoding="utf-8")
    assert "-m pytest" not in text
    assert "pytest tests/" not in text


def test_sparse_manifest_missing_check_cmd_is_not_the_same_bounce_as_no_manifest_at_all(tmp_path):
    """The two forks stay distinguishable: an un-onboarded repo (no manifest anywhere) names onboarding;
    a manifest present but check_cmd-less names the missing key — never the same message."""
    work, _ = _make_repo_manifest_no_check_cmd(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Sparse, not un-onboarded"), work)
    del env["CHECK_CMD"]
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    assert "not onboarded" not in r.stderr.lower()
    assert "check_cmd" in r.stderr and "not declared" in r.stderr
