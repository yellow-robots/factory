"""Acceptance tests for tools/deploy.sh — the scripted attended act (it-33 slice 6, epic #455,
issue #462).

No live host, no network: every external act deploy.sh performs is overridable (GIT_BIN,
SYSTEMCTL_BIN, GH_BIN, PY_BIN, VENV_PYTHON, DEPLOY_ROOT, DEV_RUNNER_HOME) — real local git fixtures
(a bare "origin" + clones, the same no-mocking-git idiom tests/test_drift.py uses) drive the pull
and the import-closure diff; `gh` is the shared operator-tool fake (tests/harness/gh_fake.py's
GH_STUB_TOOLS, python face, per tests/harness/contract.md); systemctl/py_compile's venv python are
tiny bash stubs local to this file, mirroring tests/test_dev_runner.py's CHECK_STUB pattern.

The quiescence probe reads only the lock files the dispatcher itself writes (a non-blocking flock
test) and a `kill -0` liveness probe on a run dir's own pid — never `ps` — matching
tools/epic_gate.py's `_default_build_lock_held`.
"""
import fcntl
import json
import os
import pathlib
import shutil
import signal
import stat
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "deploy.sh"

sys.path.insert(0, str(ROOT / "tests" / "harness"))
import gh_fake  # noqa: E402
GH_STUB = gh_fake.GH_STUB_TOOLS

sys.path.insert(0, str(ROOT / "tools"))
import check_trail  # noqa: E402
import records      # noqa: E402


def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


SYSTEMCTL_STUB = '''#!/usr/bin/env bash
echo "SYSTEMCTL $*" >> "${STUB_SYSTEMCTL_LOG:-/dev/null}"
echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-unset}" >> "${STUB_SYSTEMCTL_LOG:-/dev/null}"
exit "${STUB_SYSTEMCTL_EXIT:-0}"
'''

VENV_PYTHON_STUB = '''#!/usr/bin/env bash
echo "VENVPY $*" >> "${STUB_VENVPY_LOG:-/dev/null}"
exit "${STUB_VALIDATE_EXIT:-0}"
'''


def _bin(tmp_path):
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    _exec(b / "gh", GH_STUB)
    _exec(b / "systemctl", SYSTEMCTL_STUB)
    _exec(b / "venvpython", VENV_PYTHON_STUB)
    return b


# ── real-git fixture plumbing (no mocking git — the tests/test_drift.py idiom) ─────────────────────

def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _bare(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "--bare"], path)
    _git(["symbolic-ref", "HEAD", "refs/heads/main"], path)
    return path


def _clone(bare, dest):
    subprocess.run(["git", "clone", "-q", str(bare), str(dest)],
                   check=True, capture_output=True, text=True)
    _git(["config", "user.email", "test@example.com"], dest)
    _git(["config", "user.name", "Test"], dest)
    return dest


def _seed_tools(dest):
    """REAL copies of the three import-closure files, so deploy.sh's AST-walk closure computation
    (and its diff against them) behaves exactly as it does against the real repo — plus a trivial
    dev-runner.sh (bash -n only needs valid syntax, never the real pipeline)."""
    tdir = dest / "tools"
    tdir.mkdir(parents=True, exist_ok=True)
    for name in ("dispatch.py", "board_plumbing.py", "provenance.py"):
        shutil.copy(ROOT / "tools" / name, tdir / name)
    (tdir / "dev-runner.sh").write_text("#!/usr/bin/env bash\necho hi\n")


def _commit(dest, msg):
    _git(["add", "-A"], dest)
    _git(["commit", "-q", "-m", msg], dest)
    out = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _push(dest):
    _git(["push", "-q", "origin", "HEAD:main"], dest)


def _fixture(tmp_path, *, touch_closure):
    """A bare origin + a checkout at commit 1 (real closure files); a second push (commit 2) that
    either touches tools/dispatch.py (`touch_closure=True`) or only an unrelated file
    (`touch_closure=False`). Returns (checkout, sha1, sha2)."""
    bare = _bare(tmp_path / "origin.git")
    seed = _clone(bare, tmp_path / "seed")
    _seed_tools(seed)
    sha1 = _commit(seed, "one")
    _push(seed)
    checkout = _clone(bare, tmp_path / "checkout")
    if touch_closure:
        with open(seed / "tools" / "dispatch.py", "a") as f:
            f.write("\n# a deliberate closure-touching change\n")
    else:
        (seed / "tools" / "unrelated.py").write_text("print('unrelated')\n")
    sha2 = _commit(seed, "two")
    _push(seed)
    return checkout, sha1, sha2


def _env(tmp_path, *, deploy_root, dev_runner_home, binp, systemctl_log=None, venvpy_log=None,
         calls_log=None, extra=None):
    env = {
        **os.environ,
        "DEPLOY_ROOT": str(deploy_root),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "GH_BIN": str(binp / "gh"),
        "SYSTEMCTL_BIN": str(binp / "systemctl"),
        "VENV_PYTHON": str(binp / "venvpython"),
        "PY_BIN": sys.executable,
        "GIT_BIN": "git",
    }
    if systemctl_log is not None:
        env["STUB_SYSTEMCTL_LOG"] = str(systemctl_log)
    if venvpy_log is not None:
        env["STUB_VENVPY_LOG"] = str(venvpy_log)
    if calls_log is not None:
        env["STUB_CALLS_LOG"] = str(calls_log)
    if extra:
        env.update(extra)
    return env


def _run(args, env):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)


def _calls(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l]


def _comment_bodies(calls):
    bodies = []
    for c in calls:
        if c[:2] != ["issue", "comment"]:
            continue
        for i, tok in enumerate(c):
            if tok == "--body" and i + 1 < len(c):
                bodies.append(c[i + 1])
    return bodies


# ============ usage / --who validation ============

def test_no_who_is_usage_error(tmp_path):
    r = _run([], {**os.environ, "DEV_RUNNER_HOME": str(tmp_path / "home")})
    assert r.returncode == 2
    assert "usage" in r.stderr.lower()


def test_invalid_who_is_usage_error(tmp_path):
    r = _run(["--who", "operator"], {**os.environ, "DEV_RUNNER_HOME": str(tmp_path / "home")})
    assert r.returncode == 2
    assert "actor CLASS" in r.stderr


def test_who_with_no_value_is_a_clean_usage_error_not_a_bare_shift_failure(tmp_path):
    """`--who` as the LAST argument (no following value) must hit `usage` (exit 2, a clear
    message) — not a bare, unmessaged failure out of `shift 2` running past the argument list."""
    r = _run(["--who"], {**os.environ, "DEV_RUNNER_HOME": str(tmp_path / "home")})
    assert r.returncode == 2
    assert "usage" in r.stderr.lower()
    assert "requires a value" in r.stderr


def test_who_human_and_attended_agent_both_pass_validation(tmp_path):
    # neither reaches a real repo (DEPLOY_ROOT absent) -> environmental (3), never usage (2)
    home = tmp_path / "home"
    for who in ("human", "attended-agent"):
        env = {**os.environ, "DEV_RUNNER_HOME": str(home), "DEPLOY_ROOT": str(tmp_path / "nope")}
        r = _run(["--who", who], env)
        assert r.returncode == 3, (who, r.stderr)


# ============ quiescence probe: held locks refuse, naming them ============

def test_refuses_when_a_repo_build_lock_is_held(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    lock_path = home / "dispatch-yellow--robots.lock"
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        r = _run(["--who", "human"], {**os.environ, "DEV_RUNNER_HOME": str(home)})
        assert r.returncode == 1
        assert "REFUSED" in r.stderr
        assert str(lock_path) in r.stderr
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_refuses_when_a_capacity_slot_lock_is_held(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    lock_path = home / "capslot-0.lock"
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        r = _run(["--who", "human"], {**os.environ, "DEV_RUNNER_HOME": str(home)})
        assert r.returncode == 1
        assert "REFUSED" in r.stderr
        assert str(lock_path) in r.stderr
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_refuses_when_the_sweep_lock_is_held(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    lock_path = home / "epic-sweep.lock"
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        r = _run(["--who", "human"], {**os.environ, "DEV_RUNNER_HOME": str(home)})
        assert r.returncode == 1
        assert "REFUSED" in r.stderr
        assert str(lock_path) in r.stderr
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_refuses_when_a_run_dir_names_a_live_pid(tmp_path):
    home = tmp_path / "home"
    (home / "runs").mkdir(parents=True)
    proc = subprocess.Popen(["sleep", "30"])
    try:
        time.sleep(0.2)
        rundir = home / "runs" / f"7-{proc.pid}"
        rundir.mkdir()
        r = _run(["--who", "human"], {**os.environ, "DEV_RUNNER_HOME": str(home)})
        assert r.returncode == 1
        assert "REFUSED" in r.stderr
        assert "a build run is live" in r.stderr
        assert str(proc.pid) in r.stderr
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait()


def test_a_dead_pid_run_dir_does_not_refuse_quiescence(tmp_path):
    """A stale run dir whose pid is no longer alive must NOT be read as a live run — this proves
    the probe checks liveness (kill -0), not mere directory presence."""
    home = tmp_path / "home"
    (home / "runs").mkdir(parents=True)
    dead = subprocess.Popen(["true"])
    dead.wait()
    rundir = home / "runs" / f"7-{dead.pid}"
    rundir.mkdir()
    env = {**os.environ, "DEV_RUNNER_HOME": str(home), "DEPLOY_ROOT": str(tmp_path / "nope")}
    r = _run(["--who", "human"], env)
    assert "a build run is live" not in r.stderr
    assert r.returncode == 3   # falls through to the (unrelated) environmental failure instead


def test_clean_quiescence_proceeds_past_the_probe(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "DEV_RUNNER_HOME": str(home), "DEPLOY_ROOT": str(tmp_path / "nope")}
    r = _run(["--who", "human"], env)
    assert "REFUSED" not in r.stderr
    assert "quiescence: clean" in r.stderr
    assert r.returncode == 3   # no repo at DEPLOY_ROOT -> environmental, past the probe


def test_dispatch_lock_override_relocates_the_probes_lock_home(tmp_path):
    """The probe's lock globs live beside DISPATCH_LOCK (dispatch.py's own derivation), never
    hardcoded to DEV_RUNNER_HOME — a lock held at a DISPATCH_LOCK-relocated home must still refuse,
    even though DEV_RUNNER_HOME itself points elsewhere (and holds nothing)."""
    home = tmp_path / "home"
    home.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    lock_path = elsewhere / "dispatch-yellow--robots.lock"
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        env = {**os.environ, "DEV_RUNNER_HOME": str(home),
              "DISPATCH_LOCK": str(elsewhere / "dispatch.lock")}
        r = _run(["--who", "human"], env)
        assert r.returncode == 1
        assert "REFUSED" in r.stderr
        assert str(lock_path) in r.stderr
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ============ dry-run: probes and reports, never mutates/posts ============

def test_dry_run_reports_restart_yes_without_pulling_or_posting(tmp_path):
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=True)
    binp = _bin(tmp_path)
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              systemctl_log=tmp_path / "sysctl.log", calls_log=tmp_path / "calls.log")
    r = _run(["--who", "human", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "restart: yes" in r.stdout
    assert sha1 in r.stdout and sha2 in r.stdout
    # HEAD never moved
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert head == sha1
    assert not _calls(tmp_path / "calls.log")
    assert not (tmp_path / "sysctl.log").exists() or not (tmp_path / "sysctl.log").read_text()


def test_dry_run_reports_restart_no_for_an_unrelated_change(tmp_path):
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=False)
    binp = _bin(tmp_path)
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp)
    r = _run(["--who", "human", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert "restart: no" in r.stdout


def test_a_broken_import_closure_computation_is_environmental_not_a_bare_set_e_crash(tmp_path):
    """`CLOSURE_FILES="$(_import_closure)"` under `set -e`, left unguarded, would abort with a
    bare, unmessaged exit 1 — indistinguishable from a deliberate `refuse`. Guarded with
    `|| envfail`, a broken PY_BIN here must land as a clearly-messaged exit 3 instead. Exercised
    via --dry-run, whose only PY_BIN use IS the closure computation (the real-run path guards the
    identical call the same way, right after the same checks that already exercise PY_BIN)."""
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=True)
    binp = _bin(tmp_path)
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              extra={"PY_BIN": str(tmp_path / "no-such-python")})
    r = _run(["--who", "human", "--dry-run"], env)
    assert r.returncode == 3
    assert "ENVIRONMENTAL" in r.stderr
    assert "import closure" in r.stderr


# ============ the real act: pull, conditional restart, checks, the one record ============

def test_real_run_restart_no_posts_one_complete_record_and_never_restarts(tmp_path):
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=False)
    binp = _bin(tmp_path)
    sysctl_log = tmp_path / "sysctl.log"
    calls_log = tmp_path / "calls.log"
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              systemctl_log=sysctl_log, calls_log=calls_log,
              extra={"DEPLOY_REPO": "test/repo", "DEPLOY_ISSUE": "999"})
    r = _run(["--who", "human"], env)
    assert r.returncode == 0, r.stderr

    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert head == sha2

    assert not sysctl_log.exists() or not sysctl_log.read_text()

    calls = _calls(calls_log)
    comments = [c for c in calls if c[:2] == ["issue", "comment"]]
    assert len(comments) == 1
    assert comments[0][2] == "999" and "test/repo" in comments[0]

    bodies = _comment_bodies(calls)
    assert len(bodies) == 1
    body = bodies[0]
    assert body.startswith("YR-DEPLOY:")
    assert f"commit: {sha2}" in body
    assert "who: human" in body
    assert "restart: no" in body
    assert "surface:" in body

    # the emitted record satisfies check_trail.py's own field grammar, exactly the wall a reader runs
    reg = records.load()
    row = records.get(reg, "YR-DEPLOY")
    assert check_trail._marker_present(row, [body])
    assert check_trail._missing_fields(row, [body]) == []


def test_real_run_restart_yes_restarts_dispatch_with_the_runtime_dir(tmp_path):
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=True)
    binp = _bin(tmp_path)
    sysctl_log = tmp_path / "sysctl.log"
    calls_log = tmp_path / "calls.log"
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              systemctl_log=sysctl_log, calls_log=calls_log)
    r = _run(["--who", "attended-agent"], env)
    assert r.returncode == 0, r.stderr

    log = sysctl_log.read_text()
    assert "--user restart dispatch" in log
    assert "XDG_RUNTIME_DIR=unset" not in log   # deploy.sh sets a real value when unset in its own env

    bodies = _comment_bodies(_calls(calls_log))
    assert len(bodies) == 1
    assert "restart: yes" in bodies[0]
    assert "who: attended-agent" in bodies[0]


def test_a_failing_post_deploy_check_refuses_and_posts_nothing(tmp_path):
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=False)
    binp = _bin(tmp_path)
    calls_log = tmp_path / "calls.log"
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              calls_log=calls_log, extra={"STUB_VALIDATE_EXIT": "1"})
    r = _run(["--who", "human"], env)
    assert r.returncode == 1
    assert "REFUSED" in r.stderr
    assert "process.py validate" in r.stderr
    assert sha1 in r.stderr and sha2 in r.stderr   # both HEADs named -- recovery is derivable
    assert not _calls(calls_log)   # no record posted on a refused act


def test_a_failing_post_deploy_check_never_restarts_dispatch_even_when_the_closure_changed(tmp_path):
    """Checks run BEFORE any restart: a tree that fails py_compile/validate must never be
    restarted into (Restart=on-failure would otherwise crash-loop it while `systemctl restart`
    itself still returns 0) — even when the pulled change DID touch the import closure."""
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=True)
    binp = _bin(tmp_path)
    sysctl_log = tmp_path / "sysctl.log"
    calls_log = tmp_path / "calls.log"
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              systemctl_log=sysctl_log, calls_log=calls_log, extra={"STUB_VALIDATE_EXIT": "1"})
    r = _run(["--who", "human"], env)
    assert r.returncode == 1
    assert "REFUSED" in r.stderr
    assert not sysctl_log.exists() or not sysctl_log.read_text()
    assert not _calls(calls_log)


def test_git_pull_failure_is_environmental_not_refused(tmp_path):
    # a checkout whose HEAD diverges from origin/main (both sides advanced independently from the
    # same base) can't --ff-only — neither is an ancestor of the other.
    bare = _bare(tmp_path / "origin.git")
    seed = _clone(bare, tmp_path / "seed")
    _seed_tools(seed)
    _commit(seed, "one")
    _push(seed)
    checkout = _clone(bare, tmp_path / "checkout")
    # origin advances one way
    (seed / "tools" / "origin-side.py").write_text("print('origin side')\n")
    _commit(seed, "origin advances")
    _push(seed)
    # the checkout advances a DIFFERENT way, off the same base — a genuine fork
    (checkout / "tools" / "local-side.py").write_text("print('local side')\n")
    _commit(checkout, "local divergence")

    binp = _bin(tmp_path)
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp)
    r = _run(["--who", "human"], env)
    assert r.returncode == 3
    assert "ENVIRONMENTAL" in r.stderr
    assert "REFUSED" not in r.stderr


def test_gh_post_failure_is_environmental_after_a_completed_deploy(tmp_path):
    checkout, sha1, sha2 = _fixture(tmp_path, touch_closure=False)
    binp = _bin(tmp_path)
    env = _env(tmp_path, deploy_root=checkout, dev_runner_home=tmp_path / "home", binp=binp,
              extra={"STUB_COMMENT_FAIL": "1"})
    r = _run(["--who", "human"], env)
    assert r.returncode == 3
    assert "ENVIRONMENTAL" in r.stderr
    assert "YR-DEPLOY record failed to post" in r.stderr
    # the pull itself DID happen — the failure is purely the record, not the deploy
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert head == sha2


# ============ the dispatcher's import closure — pinned against the REAL repo ============

def test_import_closure_is_pinned_against_the_real_tools_dispatch_py():
    """A new import in tools/dispatch.py (or a sibling it pulls in) must show up here as a diff —
    the closure is computed live from the real source, never hardcoded twice."""
    env = {**os.environ, "DEPLOY_ROOT": str(ROOT), "PY_BIN": sys.executable}
    r = subprocess.run(["bash", str(SCRIPT), "--print-import-closure"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert set(lines) == {"tools/dispatch.py", "tools/board_plumbing.py", "tools/provenance.py"}
    assert lines[0] == "tools/dispatch.py"   # the entry point, always first


# ============ the unit file's paths ============

def test_dispatch_service_paths_use_the_yr_factory_home_not_opt():
    text = (ROOT / "deploy" / "dispatch.service").read_text()
    assert "%h/yellow-robots/factory" in text
    assert "/opt/yellow-robots/factory" not in text
    assert "ExecStart=%h/yellow-robots/factory/.venv/bin/python %h/yellow-robots/factory/tools/dispatch.py" in text
    assert "WorkingDirectory=%h/yellow-robots/factory" in text


def test_dispatch_md_names_the_deploy_trail_issue():
    text = (ROOT / "deploy" / "DISPATCH.md").read_text()
    assert "#464" in text
    assert "tools/deploy.sh" in text


def test_deploy_sh_is_named_in_agents_md_repo_map():
    text = (ROOT / "AGENTS.md").read_text()
    assert "tools/deploy.sh" in text
