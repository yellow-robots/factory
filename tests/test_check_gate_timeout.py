"""Acceptance tests for issue #308 — check gate: the local gate is bounded (`check_timeout`) — and issue
#314 — idle-output liveness: gates judged by liveness; the absolute window informs, never kills.

Derived from the issues' acceptance criteria (the spec), NOT the implementation's internals:

  1. The bounded window is resolved ONCE per run, at the same start-of-run point as `check_cmd` itself,
     precedence `CHECK_TIMEOUT` env > manifest `check_timeout` (a positive integer seconds) > a built-in
     default of 1200 — the effective window and its source (`env`|`manifest`|`default`) logged once.
     `check_idle_timeout` (default 300) shares the same resolution point, precedence, and typed-emission
     discipline against its own env override `CHECK_IDLE_TIMEOUT` (issue #314).
  2. A declared value that does not parse as a positive integer (zero, negative, non-integer) bounces the
     task to Needs-info BEFORE any claim/worktree/stage, naming the rejected value — never a silent
     fallback to the default. A manifest that fails to parse AT ALL is a distinct failure (today's
     check_cmd-required bounce fires for that reason) and must never be misreported as a rejected
     check_timeout/check_idle_timeout value.
  3. Every local-gate invocation (check_cmd, lint_cmd/lint_fix_cmd, lens_cmd, and the armed merge path's
     freshness re-green) is judged by LIVENESS: a log that sits at zero byte growth for `check_idle_timeout`
     kills the whole process TREE with no survivor and disposes an OBSERVED expiry — a CODE failure whose
     log tail names the idle duration, the total elapsed time, and BOTH windows, so the site's existing
     disposition (one repair attempt, then Blocked) engages unchanged — the lens folds it into its
     advisory note instead.
  4. `check_timeout` elapsing while the log is STILL growing no longer kills anything: it fires exactly
     ONE loud advisory (a run-log line plus one issue-trail comment naming the process group, elapsed
     time, both windows, and that output is flowing) and the invocation runs on — the advisory only
     informs, it never gates.
  5. A child that exits 124/137 on its OWN (no observed expiry) disposes exactly as today's plain code
     failure — no expiry tail is ever stamped from a bare exit code alone (the false-124 fixture).
  6. `check_timeout` / `check_idle_timeout` are named on AGENTS.md's manifest-keys line and the
     liveness-judged bounded-gate discipline (including the advisory) is documented in
     skills/factory/references/gates.md and pipeline.md.

Reuses the shared harness only (tests/test_dev_runner.py's stub set, fixtures, and helpers, plus
tests/test_autonomous_merge.py's armed-repo fixtures for the freshness re-green scenario) — no private
clone of the classifier or the gh/claude stubs. The wrapper's real process-group/log-growth behavior is
exercised for real; nothing about the wrapper shape is mocked.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td              # shared stub harness (gh/claude/check stubs + fixtures)
import test_autonomous_merge as tam        # armed-repo fixtures (freshness remediation scenario)

ROOT = td.ROOT
EMDASH = td.EMDASH


# ============ manifest helpers ============

def _timeout_manifest_repo(tmp, content, name="repo"):
    """A minimal, non-git repo dir carrying `.yr/factory.toml` — dry-run reads it straight off the
    working tree (no git needed). check_cmd is prepended (required, issue #275) so a declared
    check_timeout value under test is the only variable in play."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    (repo / ".yr" / "factory.toml").write_text('check_cmd = "true"\n' + content)
    return repo


def _real_repo_with_manifest(tmp, manifest_text, name="work"):
    """A real git repo (bare origin + checkout) carrying `.yr/factory.toml` with EXACTLY the given raw
    text (no automatic check_cmd prepend — a caller controls whether check_cmd is even declared, needed
    for the whole-manifest-parse-failure scenario below)."""
    origin = tmp / f"{name}_origin.git"; origin.mkdir()
    td._git(["init", "--bare", "-b", "main", "."], origin)
    work = tmp / name; work.mkdir()
    td._git(["init", "-b", "main", "."], work)
    td._git(["config", "user.email", "t@t"], work); td._git(["config", "user.name", "tester"], work)
    (work / ".yr").mkdir(parents=True)
    (work / ".yr" / "factory.toml").write_text(manifest_text)
    (work / "README.md").write_text("seed\n")
    td._git(["add", "-A"], work); td._git(["commit", "-q", "-m", "seed"], work)
    td._git(["remote", "add", "origin", str(origin)], work)
    td._git(["push", "-q", "origin", "main"], work)
    return work, origin


# ============ criterion 1: precedence env > manifest > default, source logged once ============

def test_env_override_wins_over_manifest_and_logs_source_env(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "check_timeout = 45\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_TIMEOUT"] = "99"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_timeout: 99s (source: env)" in r.stderr
    assert "check_timeout: 45s" not in r.stderr


def test_manifest_wins_over_default_when_no_env_override(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "check_timeout = 45\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env.pop("CHECK_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_timeout: 45s (source: manifest)" in r.stderr


def test_default_1200_used_when_neither_env_nor_manifest_key_present(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "")   # onboarded, check_cmd only — no check_timeout key
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env.pop("CHECK_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_timeout: 1200s (source: default)" in r.stderr


def test_env_wins_even_with_no_manifest_key_at_all(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_TIMEOUT"] = "7"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_timeout: 7s (source: env)" in r.stderr


def test_effective_window_is_logged_exactly_once(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "check_timeout = 45\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env.pop("CHECK_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert r.stderr.count("check_timeout: 45s (source: manifest)") == 1


# ============ criteria 2 & 3: a malformed declared value bounces before any claim ============

def test_declared_zero_bounces_needs_info_before_claim(tmp_path):
    """Zero is not a positive integer — rejected, never silently defaulted (the bare scalar channel used
    by check_cmd/model would read a declared 0 as absent and silently default; the typed channel used
    here must not make that mistake)."""
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_timeout = 0\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="check_timeout = 0"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3

    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                                     # no stage ever launched — refused pre-claim
    edit = " ".join(td._edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit
    comments = " ".join(td._comments(tl)).lower()
    assert "check_timeout" in comments and "rejected" in comments and "0" in comments
    assert td._wt_dir(tmp_path) is None                        # never got as far as a worktree


def test_declared_negative_bounces_needs_info(tmp_path):
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_timeout = -5\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="check_timeout = -5"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "check_timeout" in comments and "rejected" in comments and "-5" in comments
    assert td._wt_dir(tmp_path) is None


def test_declared_non_integer_bounces_needs_info(tmp_path):
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_timeout = "abc"\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="check_timeout = abc"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "check_timeout" in comments and "rejected" in comments and "abc" in comments
    assert td._wt_dir(tmp_path) is None


def test_malformed_bounce_names_the_governing_rule(tmp_path):
    """The refusal names the rule (a positive integer number of seconds), not just the bare value — so
    recovery is derivable from the message alone."""
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_timeout = -5\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Names the rule"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    comments = " ".join(td._comments(td._timeline(tmp_path))).lower()
    assert "positive integer" in comments
    assert "1200" in comments                                  # the never-silently-defaulted-to value is named


def test_malformed_check_timeout_dryrun_also_bounces(tmp_path):
    """--dry-run's read-only reporting intent doesn't rescue a malformed declared value either."""
    repo = _timeout_manifest_repo(tmp_path, "check_timeout = 0\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    assert "check_timeout" in r.stderr and "rejected" in r.stderr.lower()


# ============ criterion 2 (continued): a whole-manifest parse failure is a DISTINCT failure ============

def test_whole_manifest_parse_failure_never_misreported_as_rejected_check_timeout(tmp_path):
    """A manifest that fails to parse AT ALL (invalid TOML syntax) breaks every key's extraction alike —
    including check_cmd's own (unrelated to this issue), which is what actually bounces the run here. The
    typed check_timeout channel must discriminate this from a declared-but-invalid value: it defaults
    silently (same precedent as test_paths/artifact_globs on a broken manifest) rather than adding its own
    spurious 'check_timeout is rejected' reason to the bounce."""
    broken = 'check_cmd = "true\ncheck_timeout = [[[not valid toml\n'   # unterminated string -> whole parse fails
    work, _ = _real_repo_with_manifest(tmp_path, broken)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Broken manifest"), work)
    del env["CHECK_CMD"]                                       # no env override to mask the check_cmd bounce
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "check_cmd" in comments and "not declared" in comments      # bounces for THIS reason
    assert "'check_timeout' is rejected" not in comments               # never spuriously flagged too
    assert "check_timeout' is rejected" not in comments


# ============ issue #314, criterion 1: check_idle_timeout — same resolution point/precedence/typed- =====
# ============ emission discipline as check_timeout, default 300 =========================================

def test_idle_env_override_wins_over_manifest_and_logs_source_env(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "check_idle_timeout = 45\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_IDLE_TIMEOUT"] = "99"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_idle_timeout: 99s (source: env)" in r.stderr
    assert "check_idle_timeout: 45s" not in r.stderr


def test_idle_manifest_wins_over_default_when_no_env_override(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "check_idle_timeout = 45\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env.pop("CHECK_IDLE_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_idle_timeout: 45s (source: manifest)" in r.stderr


def test_idle_default_300_used_when_neither_env_nor_manifest_key_present(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "")   # onboarded, check_cmd only — no check_idle_timeout key
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env.pop("CHECK_IDLE_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_idle_timeout: 300s (source: default)" in r.stderr


def test_idle_env_wins_even_with_no_manifest_key_at_all(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_IDLE_TIMEOUT"] = "7"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_idle_timeout: 7s (source: env)" in r.stderr


def test_idle_effective_window_is_logged_exactly_once(tmp_path):
    repo = _timeout_manifest_repo(tmp_path, "check_idle_timeout = 45\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env.pop("CHECK_IDLE_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert r.stderr.count("check_idle_timeout: 45s (source: manifest)") == 1


def test_idle_and_absolute_windows_both_logged_independently(tmp_path):
    """The two windows are independent knobs — declaring one never disturbs the other's resolution."""
    repo = _timeout_manifest_repo(tmp_path, "check_timeout = 45\ncheck_idle_timeout = 20\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    env.pop("CHECK_TIMEOUT", None); env.pop("CHECK_IDLE_TIMEOUT", None)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "check_timeout: 45s (source: manifest)" in r.stderr
    assert "check_idle_timeout: 20s (source: manifest)" in r.stderr


# ============ issue #314, criterion 1 (continued): a malformed check_idle_timeout bounces before any ====
# ============ claim, naming the rejected value — never a silent fallback to 300 =========================

def test_idle_declared_zero_bounces_needs_info_before_claim(tmp_path):
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_idle_timeout = 0\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="check_idle_timeout = 0"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3

    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                                     # no stage ever launched — refused pre-claim
    edit = " ".join(td._edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit
    comments = " ".join(td._comments(tl)).lower()
    assert "check_idle_timeout" in comments and "rejected" in comments and "0" in comments
    assert td._wt_dir(tmp_path) is None                        # never got as far as a worktree


def test_idle_declared_negative_bounces_needs_info(tmp_path):
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_idle_timeout = -5\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="check_idle_timeout = -5"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "check_idle_timeout" in comments and "rejected" in comments and "-5" in comments
    assert td._wt_dir(tmp_path) is None


def test_idle_declared_non_integer_bounces_needs_info(tmp_path):
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_idle_timeout = "abc"\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="check_idle_timeout = abc"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "check_idle_timeout" in comments and "rejected" in comments and "abc" in comments
    assert td._wt_dir(tmp_path) is None


def test_idle_malformed_bounce_names_the_governing_rule(tmp_path):
    """The refusal names the rule (a positive integer number of seconds) and the never-silently-defaulted
    value (300), not just the bare rejected value — so recovery is derivable from the message alone."""
    work, _ = _real_repo_with_manifest(tmp_path, 'check_cmd = "true"\ncheck_idle_timeout = -5\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Names the idle rule"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    comments = " ".join(td._comments(td._timeline(tmp_path))).lower()
    assert "positive integer" in comments
    assert "300" in comments                                   # the never-silently-defaulted-to value is named


def test_idle_malformed_check_idle_timeout_dryrun_also_bounces(tmp_path):
    """--dry-run's read-only reporting intent doesn't rescue a malformed declared value either."""
    repo = _timeout_manifest_repo(tmp_path, "check_idle_timeout = 0\n")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 3
    assert "check_idle_timeout" in r.stderr and "rejected" in r.stderr.lower()


def test_idle_whole_manifest_parse_failure_never_misreported_as_rejected_check_idle_timeout(tmp_path):
    """A manifest that fails to parse AT ALL breaks every key's extraction alike — including check_cmd's
    own (unrelated to this issue), which is what actually bounces the run here. The typed
    check_idle_timeout channel must discriminate this from a declared-but-invalid value: it defaults
    silently rather than adding its own spurious 'check_idle_timeout is rejected' reason to the bounce."""
    broken = 'check_cmd = "true\ncheck_idle_timeout = [[[not valid toml\n'   # unterminated string
    work, _ = _real_repo_with_manifest(tmp_path, broken)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Broken manifest, idle"), work)
    del env["CHECK_CMD"]                                       # no env override to mask the check_cmd bounce
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "check_cmd" in comments and "not declared" in comments      # bounces for THIS reason
    assert "'check_idle_timeout' is rejected" not in comments          # never spuriously flagged too
    assert "check_idle_timeout' is rejected" not in comments


# ============ criterion 3 & 4: run_checks is bounded — a wedge with children leaves no survivor,  =======
# ============ disposes as a code failure whose log tail names the expiry, one repair engages     =======

CHECK_STUB_SPAWNS_CHILD = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -f repaired ]; then exit 0; fi
( sleep 60; : > "$STUB_SURVIVE_MARKER" ) &
echo $! > "$STUB_CHILD_PIDFILE"
sleep 300
'''


def test_check_cmd_silent_hang_with_children_is_idle_killed_leaves_no_survivor_and_repairs(tmp_path):
    """A SILENT wedge (writes once, then never again) is judged by liveness: it is killed at the IDLE
    window, not the absolute one — CHECK_TIMEOUT is left at its generous default so only CHECK_IDLE_TIMEOUT
    is in play, proving the idle window (not the absolute clock) is what disposes this fixture (issue
    #314)."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    td._exec(binp / "check.sh", CHECK_STUB_SPAWNS_CHILD)
    survive_marker = tmp_path / "survived"
    child_pidfile = tmp_path / "child_pid"
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Hang with children"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_IDLE_TIMEOUT"] = "1"
    env.pop("CHECK_TIMEOUT", None)                             # generous default (1200s) — never in play here
    env["STUB_SURVIVE_MARKER"] = str(survive_marker)
    env["STUB_CHILD_PIDFILE"] = str(child_pidfile)
    t0 = time.time()
    r = td._run(["5", "--repo", "test/repo"], env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 60, f"a bounded window must not pay any part of the 300s hang ({elapsed}s)"
    assert "https://stub/pr/1" in r.stdout                     # heals after the one repair -> reaches a PR

    tl = td._timeline(tmp_path)
    assert "REPAIR" in tl                                      # the one-repair path engaged
    assert tl.count("CHECK") == 2                              # failed (expired) once, passed after repair

    # no survivor from the invocation's own process group
    assert not survive_marker.exists()
    assert child_pidfile.exists()
    child_pid = int(child_pidfile.read_text().strip())
    dead = False
    try:
        os.kill(child_pid, 0)
    except ProcessLookupError:
        dead = True
    assert dead, "the spawned child must not survive the process-group kill"

    # the repair prompt's embedded failure output (captured before the second call overwrote checks.log)
    # names the observed IDLE expiry, the total elapsed time, and BOTH windows
    repair_call = td._stage_calls(tmp_path)["REPAIR"][0]
    assert "check_idle_timeout expired after 1s idle" in repair_call
    assert "total elapsed" in repair_call
    assert "check_timeout=1200s" in repair_call
    assert "check_idle_timeout=1s" in repair_call
    assert "process group killed" in repair_call
    assert "no observed survivor" in repair_call
    # never conflated with the absolute-window advisory (output was NOT flowing here)
    assert "advisory" not in repair_call.lower()


def test_check_cmd_false_124_is_a_plain_code_failure_never_conflated_with_expiry(tmp_path):
    """A check_cmd that exits 124 ON ITS OWN (no real hang) must dispose exactly like any other code
    failure — no expiry tail is ever stamped from a bare exit code alone, idle or absolute."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    false_124 = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
exit 124
'''
    td._exec(binp / "check.sh", false_124)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="False 124"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_TIMEOUT"] = "30"                                # generous — the child never actually hangs
    env["CHECK_IDLE_TIMEOUT"] = "30"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "checks still failing" in r.stderr.lower()
    tl = td._timeline(tmp_path)
    assert "REPAIR" in tl                                      # still earns the one repair attempt
    assert tl.count("CHECK") == 2
    assert "https://stub/pr/1" not in r.stdout

    checks_log = (td._run_dir(tmp_path, 5) / "checks.log").read_text()
    assert "expired" not in checks_log.lower()
    assert "idle" not in checks_log.lower()
    assert "killed" not in checks_log.lower()
    repair_call = td._stage_calls(tmp_path)["REPAIR"][0]
    assert "check_timeout expired" not in repair_call
    assert "check_idle_timeout expired" not in repair_call
    assert "process group killed" not in repair_call
    assert "advisory" not in repair_call.lower()


def test_environment_failure_126_classification_unchanged_under_the_wrapper(tmp_path):
    """126 (found-but-not-executable) still classifies as an ENVIRONMENT failure (no repair, env_hold)
    with the bounded wrapper in place — the wrapper must never interfere with today's 126/127 discipline."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Env failure under wrapper"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_CHECK_ENVFAIL": "126", "CHECK_TIMEOUT": "5"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    assert "REPAIR" not in tl                                  # no LLM repair on an environment failure
    assert tl.count("CHECK") == 1
    assert "environment" in r.stderr.lower() or "toolchain" in r.stderr.lower()
    checks_log = (td._run_dir(tmp_path, 5) / "checks.log").read_text()
    assert "expired" not in checks_log.lower()


# ============ issue #314, criterion 4: check_timeout elapsing while output is STILL FLOWING is a =========
# ============ one-time loud advisory only — never a kill, the run continues ==============================

CHECK_STUB_CHATTY = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
for i in 1 2 3 4 5 6 7 8; do
  echo "still working ($i)"
  sleep 0.3
done
exit 0
'''


def test_check_timeout_advisory_fires_once_when_output_keeps_flowing_and_never_kills(tmp_path):
    """A CHATTY check_cmd (continuous output, never idle) runs past check_timeout — under the old
    absolute-window discipline this would have been killed; judged by liveness (issue #314) it must NOT
    be killed at all: exactly one loud advisory (a run-log line plus one issue-trail comment, each naming
    the process group, elapsed time, both windows, and that output is flowing) fires, and the invocation
    runs to its own natural completion."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    td._exec(binp / "check.sh", CHECK_STUB_CHATTY)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Chatty gate, never idle"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_TIMEOUT"] = "1"                                 # small — elapses long before the ~2.4s script ends
    env.pop("CHECK_IDLE_TIMEOUT", None)                        # generous default (300s) — the script is never idle
    t0 = time.time()
    r = td._run(["5", "--repo", "test/repo"], env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 30, f"the advisory must never hold up or kill the invocation ({elapsed}s)"
    assert "https://stub/pr/1" in r.stdout                     # runs straight through to a PR — never blocked

    tl = td._timeline(tmp_path)
    assert tl.count("CHECK") == 1                              # ran once, to its own natural exit 0
    assert "REPAIR" not in tl                                  # never failed, so never repaired

    # exactly ONE advisory on the run log — never repeated even though the script keeps running afterward
    # ("live-gate advisory", not the bare word: the test's own name/tmp-dir can otherwise coincidentally
    # contain "advisory" too, e.g. inside a logged path)
    assert r.stderr.count("live-gate advisory") == 1
    log_line = next(l for l in r.stderr.splitlines() if "live-gate advisory" in l)
    assert "check_cmd" in log_line
    assert "flowing" in log_line.lower()
    assert "not killed" in log_line.lower()
    assert "check_timeout" in log_line and "1s" in log_line    # the absolute window is named
    assert "check_idle_timeout=300s" in log_line               # the idle window is named too
    assert re.search(r"pgid \d+", log_line)                    # the process group is named

    # exactly ONE advisory posted to the issue trail, carrying the same facts
    comments = td._comments(tl)
    advisory_comments = [c for c in comments if "live-gate advisory" in c]
    assert len(advisory_comments) == 1
    trail = advisory_comments[0]
    assert "check_cmd" in trail
    assert "flowing" in trail.lower()
    assert "not killed" in trail.lower()
    assert "check_timeout=1s" in trail and "check_idle_timeout=300s" in trail
    assert re.search(r"pgid \d+", trail)

    # never killed: no expiry tail of any kind lands in checks.log, and no survivor-kill markers appear
    checks_log = (td._run_dir(tmp_path, 5) / "checks.log").read_text()
    assert "process group killed" not in checks_log
    assert "no observed survivor" not in checks_log
    assert "check_idle_timeout expired" not in checks_log


# ============ criterion 3 & 4 (lint tier): every run_lint call is bounded too ============

def test_lint_cmd_silent_hang_is_idle_killed_disposes_as_blocked_and_names_facts_in_lint_log(tmp_path):
    """A lint_cmd that hangs SILENTLY (writes once, then never again) is judged by liveness — killed at
    the idle window, not the absolute one (issue #314). CHECK_TIMEOUT is left at its generous default so
    only CHECK_IDLE_TIMEOUT is in play. Bounded on both the probe AND the mandatory post-repair re-run —
    the FINAL run_lint call (with nothing further overwriting lint.log afterward) proves the expiry tail
    lands in lint.log itself, not just in a captured prompt."""
    env, work, binp = td._lint_env(tmp_path, title="Lint gate hangs", declare_fix=False)
    lint_hang = '''#!/usr/bin/env bash
echo LINT >> "$STUB_LINT_TL"
sleep 300
'''
    td._exec(binp / "lint.sh", lint_hang)
    env["CHECK_IDLE_TIMEOUT"] = "1"
    env.pop("CHECK_TIMEOUT", None)
    t0 = time.time()
    r = td._run(["5", "--repo", "test/repo"], env)
    elapsed = time.time() - t0
    assert r.returncode != 0
    assert elapsed < 60, f"bounded lint gate must not pay out the full hang twice over ({elapsed}s)"
    assert "lint still failing" in r.stderr.lower()
    tl = td._timeline(tmp_path)
    assert tl.count("LINTREPAIR") == 1                         # exactly one LLM lint repair attempt
    assert "https://stub/pr/1" not in r.stdout

    lint_log = (td._run_dir(tmp_path, 5) / "lint.log").read_text()
    assert "check_idle_timeout expired after 1s idle" in lint_log
    assert "total elapsed" in lint_log
    assert "check_timeout=1200s" in lint_log
    assert "check_idle_timeout=1s" in lint_log
    assert "process group killed" in lint_log
    assert "no observed survivor" in lint_log


def test_lint_autofix_silent_hang_idle_expires_and_continues_to_the_re_run(tmp_path):
    """The lint autofix (non-gating in its own right) is bounded too: a SILENT expiring autofix is never
    misclassified as an environment failure (killed at the idle window, issue #314), and the flow
    continues on to the mandatory LINT_CMD re-run rather than getting stuck — proven here by the eventual
    LLM lint-repair healing it end to end."""
    env, work, binp = td._lint_env(tmp_path, title="Autofix hangs", declare_fix=True)
    lintfix_hang = '''#!/usr/bin/env bash
echo LINTFIX >> "$STUB_LINT_TL"
sleep 300
'''
    td._exec(binp / "lintfix.sh", lintfix_hang)
    env["STUB_LINT_FAIL"] = "1"          # the probe fails -> triggers the autofix
    env["STUB_LINTREPAIR_HEAL"] = "1"    # autofix can't heal it (it hung) -> the one LLM repair does
    env["CHECK_IDLE_TIMEOUT"] = "1"
    env.pop("CHECK_TIMEOUT", None)
    t0 = time.time()
    r = td._run(["5", "--repo", "test/repo"], env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 60, f"an expiring autofix must not pay out its full 300s hang ({elapsed}s)"
    assert "https://stub/pr/1" in r.stdout

    lint_tl = td._lint_tl(tmp_path)
    assert lint_tl.count("LINTFIX") == 1
    assert lint_tl.count("LINT") >= 2                          # probe + at least one re-run after: continues
    tl = td._timeline(tmp_path)
    assert "LINTREPAIR" in tl                                  # one LLM repair fired (the autofix alone hung)
    edits = " ".join(td._edits(tl))
    assert "Blocked" not in edits                              # never an environment hold either


# ============ criterion 4 (lens tier): an expiring lens folds into its advisory note and proceeds ========

def test_lens_silent_hang_is_idle_killed_folds_into_the_note_and_never_gates(tmp_path):
    """A lens_cmd that hangs SILENTLY (writes once, then never again on either stdout/stderr) is judged
    by liveness — killed at the idle window, not the absolute one (issue #314). CHECK_TIMEOUT is left at
    its generous default so only CHECK_IDLE_TIMEOUT is in play."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    lens_hang = '''#!/usr/bin/env bash
[ -n "${STUB_TIMELINE:-}" ] && echo LENS >> "$STUB_TIMELINE"
sleep 300
'''
    td._exec(binp / "lens.sh", lens_hang)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Lens hangs"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["LENS_CMD"] = f"bash {binp / 'lens.sh'}"
    env["CHECK_IDLE_TIMEOUT"] = "1"
    env.pop("CHECK_TIMEOUT", None)
    t0 = time.time()
    r = td._run(["5", "--repo", "test/repo"], env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 60, f"the advisory lens must never hold up the run ({elapsed}s)"
    assert "https://stub/pr/1" in r.stdout                     # never gates, expiry included

    rd = td._run_dir(tmp_path, 5)
    lens_md = (rd / "lens.md").read_text()
    assert "check_idle_timeout expired after 1s idle" in lens_md
    assert "total elapsed" in lens_md
    assert "check_timeout=1200s" in lens_md
    assert "check_idle_timeout=1s" in lens_md
    assert "process group killed" in lens_md
    lens_log = (rd / "lens.log").read_text() if (rd / "lens.log").exists() else ""
    assert "timeout: sending signal" not in lens_log           # no GNU-`timeout` diagnostic in the new wrapper
    assert "timeout: sending signal" not in lens_md            # never in the PR-trail-bound artifact either


# ============ criterion 3 (continued): the armed merge path's freshness re-green is bounded too =========

_ADVANCE_THEN_HANG = r'''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
if [ -n "${STUB_ADVANCE_MARKER:-}" ] && [ ! -f "$STUB_ADVANCE_MARKER" ]; then
  : > "$STUB_ADVANCE_MARKER"
  wc="$(mktemp -d)"
  git clone -q "$STUB_ORIGIN" "$wc" >/dev/null 2>&1
  ( cd "$wc" && git config user.email t@t && git config user.name t \
    && printf 'unrelated\n' > OTHER.txt && git add -A \
    && git commit -q -m "advance main (no conflict)" && git push -q origin main ) >/dev/null 2>&1
  exit 0
fi
sleep 300
'''


def test_armed_freshness_re_green_bounded_by_start_of_run_window(tmp_path):
    """main advances (non-conflicting) after the first check passes, triggering freshness remediation
    (rebase + re-green). The re-green's check_cmd invocation then wedges SILENTLY (writes once per
    invocation, then never again): without a bound this would hang the whole build for 300s (or
    indefinitely) inside the terminal merge step itself — judged by liveness (issue #314), it is the IDLE
    window (not check_timeout, left at its generous default) that is bounded by the SAME start-of-run
    resolution, and the run blocks (never merges a stale/unrebased PR) instead of hanging."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; tam._stubs(binp)
    adv = binp / "check_adv_hang.sh"; td._exec(adv, _ADVANCE_THEN_HANG)
    env = tam._armed_env(tmp_path, binp, work, origin, prs=tam._complete_prs(),
                         extra={"CHECK_CMD": f"bash {adv}", "STUB_ADVANCE_MARKER": str(tmp_path / "advanced"),
                                "CHECK_IDLE_TIMEOUT": "1"})
    t0 = time.time()
    r = tam._run(["5", "--repo", "test/repo"], env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 90, f"the re-green must not pay out check_adv_hang.sh's full 300s sleep ({elapsed}s)"
    assert not tam._merged_stub(tmp_path)                      # a stale/unrebased PR never merges
    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} freshness"
    tl = td._timeline(tmp_path)
    assert tl.count("CHECK") >= 2                              # the re-green was attempted on the rebased tree
    assert tam._blocked(tl)


# ============ criterion 6: docs name check_timeout/check_idle_timeout, CHECK_TIMEOUT/CHECK_IDLE_TIMEOUT, =
# ============ and the liveness-judged / advisory discipline ==============================================

def test_agents_md_names_check_timeout_on_the_manifest_keys_line():
    text = (ROOT / "AGENTS.md").read_text()
    idx = text.index("`.yr/factory.toml` sets")
    para = text[idx: idx + 2600]
    assert "check_cmd" in para and "auto_merge" in para        # the same bullet as the other manifest keys
    assert "check_timeout" in para
    assert "CHECK_TIMEOUT" in para
    assert "1200" in para                                       # the default is named
    assert "Needs-info" in para                                 # the malformed-value fail-closed state


def test_agents_md_names_check_idle_timeout_and_the_advisory_discipline():
    text = (ROOT / "AGENTS.md").read_text()
    idx = text.index("`.yr/factory.toml` sets")
    para = text[idx: idx + 3000]
    assert "check_idle_timeout" in para
    assert "CHECK_IDLE_TIMEOUT" in para
    assert "300" in para                                        # the idle default is named
    # both windows named together, and the absolute window's advisory (never-gates) discipline is stated
    assert "advisory" in para.lower()
    assert "never gates" in para.lower() or "never kills" in para.lower()


def test_gates_md_documents_the_bounded_gate_discipline():
    text = (ROOT / "skills" / "factory" / "references" / "gates.md").read_text()
    assert "check_timeout" in text
    idx = text.index("bounded")
    nearby = text[max(0, idx - 400): idx + 900]
    assert "check_timeout" in nearby
    assert "1200" in nearby


def test_gates_md_documents_check_idle_timeout_and_the_advisory():
    text = (ROOT / "skills" / "factory" / "references" / "gates.md").read_text()
    assert "check_idle_timeout" in text
    idx = text.index("bounded")
    nearby = text[max(0, idx - 400): idx + 1400]
    assert "check_idle_timeout" in nearby
    assert "300" in nearby
    assert "advisory" in nearby.lower()
    # the check_cmd table row itself names both windows and the advisory, not just the prose bullet below
    row_idx = text.index("| `check_cmd` |")
    row = text[row_idx: row_idx + 500]
    assert "check_idle_timeout" in row and "check_timeout" in row
    assert "advisory" in row.lower()


def test_pipeline_md_describes_check_timeout_on_the_check_gate_row():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text()
    idx = text.index("**Check gate**")
    row = text[idx: idx + 900]
    assert "check_timeout" in row
    assert "1200" in row
