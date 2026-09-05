"""Acceptance tests for tools/drift.py — the one drift alarm, two moments, per-host population
(it-33 slice 4, epic #455, issue #458).

At attended session start and at each sweep, the alarm reports every declared runtime surface
readable from that host that trails `origin/main`, and names every declared surface it cannot read
from that host — on a path that needs no runner build (the two callers import this module's
functions directly). It is advisory: loud, exit 1 on findings, never a merge gate.

These tests are derived from the GitHub issue #458 acceptance criteria, not from the module's
internals. The population/comparison tests use REAL git repos with a REAL local ("origin") bare
remote (a filesystem path, so `git ls-remote origin main` is fast and needs no network) — the same
no-mocking-git idiom `tests/test_provenance.py` uses for `factory_commit`.
"""
import inspect
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import drift        # noqa: E402
import provenance   # noqa: E402


# ── git fixture plumbing — a real bare "origin" + real clones, no network, no mocking git ──────────

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


def _commit(dest, msg):
    (dest / f"{msg}.txt").write_text(msg)
    _git(["add", "."], dest)
    _git(["commit", "-q", "-m", msg], dest)
    out = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _push(dest):
    _git(["push", "-q", "origin", "HEAD:main"], dest)


def _origin_and_checkout(tmp_path, *, lag=False):
    """A checkout with a real `origin` remote (a local bare repo). With `lag=False` the checkout's
    HEAD equals origin/main's tip; with `lag=True` origin/main is advanced by a THIRD clone after
    the checkout was made, so the checkout provably trails without itself being touched again.
    Returns (checkout_path, checkout_sha, origin_tip_sha)."""
    bare = _bare(tmp_path / "origin.git")
    seed = _clone(bare, tmp_path / "seed")
    sha1 = _commit(seed, "one")
    _push(seed)
    checkout = _clone(bare, tmp_path / "checkout")
    if not lag:
        return checkout, sha1, sha1
    pusher = _clone(bare, tmp_path / "pusher")
    sha2 = _commit(pusher, "two")
    _push(pusher)
    return checkout, sha1, sha2


def _no_origin_checkout(tmp_path):
    """A real git repo with NO `origin` remote at all — `git ls-remote origin main` fails fast
    (no such remote), no network, no timeout wait."""
    repo = tmp_path / "no-origin"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "a.txt").write_text("hi")
    _git(["add", "a.txt"], repo)
    _git(["commit", "-q", "-m", "one"], repo)
    return repo


def _empty_plugins(tmp_path, **entries):
    p = tmp_path / "installed_plugins.json"
    p.write_text(json.dumps(entries))
    return p


# ── workspace_findings — the workspace-host moment (compile_slice.py:position()) ───────────────────

def test_workspace_findings_silent_for_a_clean_checkout_and_matching_cache(tmp_path):
    checkout, sha, _ = _origin_and_checkout(tmp_path)
    # the plugin cache is its OWN clone of the same origin, at the same clean tip
    cache_dir = _clone(tmp_path / "origin.git", tmp_path / "cache")
    plugins = _empty_plugins(tmp_path, **{"factory@yellow-robots": {"installPath": str(cache_dir),
                                                                     "gitCommitSha": sha}})
    findings = drift.workspace_findings(checkout, plugins)
    assert not any("TRAILS" in f for f in findings)
    assert not any("UNREADABLE" in f for f in findings)


def test_workspace_findings_reports_lag_against_origin_main_for_the_checkout(tmp_path):
    checkout, sha, origin_tip = _origin_and_checkout(tmp_path, lag=True)
    assert sha != origin_tip
    findings = drift.workspace_findings(checkout, tmp_path / "no-plugins.json")
    trails = [f for f in findings if f.startswith("attended-session (checkout): TRAILS")]
    assert len(trails) == 1, findings
    assert sha[:12] in trails[0] and origin_tip[:12] in trails[0]


def test_workspace_findings_names_the_plugin_cache_when_it_cannot_be_read(tmp_path):
    checkout, _, _ = _origin_and_checkout(tmp_path)
    plugins = _empty_plugins(tmp_path)   # no factory@yellow-robots entry at all
    findings = drift.workspace_findings(checkout, plugins)
    named = [f for f in findings if f.startswith("attended-session (plugin cache): UNREADABLE")]
    assert len(named) == 1, findings
    assert "factory@yellow-robots" in named[0]


def test_workspace_findings_always_names_every_surface_it_cannot_read_from_this_host(tmp_path):
    """Per host population: the workspace host cannot read dispatch, dev-runner, or epic-gate — those
    run on the build host. Named EVERY time, clean or not (no cross-host read, spec callout (k))."""
    checkout, _, _ = _origin_and_checkout(tmp_path)
    findings = drift.workspace_findings(checkout, tmp_path / "no-plugins.json")
    for name in ("dispatch", "dev-runner", "epic-gate"):
        assert any(f == f"{name}: not readable from this host — no cross-host read" for f in findings), \
            (name, findings)
    assert not any(f.startswith("attended-session:") for f in findings), \
        "the workspace host CAN read attended-session (its own surface) — must not name it unreadable"


def test_workspace_findings_names_origin_unreadable_once_and_suppresses_lag_lines(tmp_path):
    checkout = _no_origin_checkout(tmp_path)
    plugins = _empty_plugins(tmp_path)
    findings = drift.workspace_findings(checkout, plugins)
    origin_lines = [f for f in findings if f.startswith("origin/main: UNREADABLE")]
    assert len(origin_lines) == 1, findings
    assert not any("TRAILS" in f for f in findings), \
        "a lag verdict against an unreadable origin/main would be a false claim — must stay silent"
    # the plugin cache is STILL named — a local unreadable surface doesn't depend on origin at all
    assert any(f.startswith("attended-session (plugin cache): UNREADABLE") for f in findings)


# ── build_findings — the build-host moment (epic_gate.py:main(), each sweep) ───────────────────────

def _write_statement(home, sha):
    home.mkdir(parents=True, exist_ok=True)
    provenance.dispatch_statement_path(home).write_text(f"commit: {sha}\n", encoding="utf-8")


def test_build_findings_silent_for_a_clean_checkout_and_matching_dispatch_statement(tmp_path):
    checkout, sha, _ = _origin_and_checkout(tmp_path)
    home = tmp_path / "home"
    _write_statement(home, sha)
    findings = drift.build_findings(checkout, home)
    assert not any("TRAILS" in f for f in findings)
    assert not any("UNREADABLE" in f for f in findings)


def test_build_findings_reports_lag_for_epic_gate_and_dev_runner_and_dispatch(tmp_path):
    checkout, sha, origin_tip = _origin_and_checkout(tmp_path, lag=True)
    home = tmp_path / "home"
    _write_statement(home, sha)   # dispatch's captured statement also trails (same stale checkout)
    findings = drift.build_findings(checkout, home)
    for name in ("epic-gate", "dev-runner", "dispatch"):
        matches = [f for f in findings if f.startswith(f"{name}: TRAILS")]
        assert len(matches) == 1, (name, findings)
        assert sha[:12] in matches[0] and origin_tip[:12] in matches[0]


def test_build_findings_names_dispatch_when_its_statement_file_is_missing(tmp_path):
    checkout, _, _ = _origin_and_checkout(tmp_path)
    home = tmp_path / "home-without-a-statement-file"
    findings = drift.build_findings(checkout, home)
    named = [f for f in findings if f.startswith("dispatch: UNREADABLE")]
    assert len(named) == 1, findings


def test_build_findings_always_names_attended_session_as_unreadable_from_this_host(tmp_path):
    """Per host population: the build host cannot read attended-session — that runs on a workspace
    host. Named EVERY time, clean or not (no cross-host read, spec callout (k))."""
    checkout, sha, _ = _origin_and_checkout(tmp_path)
    home = tmp_path / "home"
    _write_statement(home, sha)
    findings = drift.build_findings(checkout, home)
    assert "attended-session: not readable from this host — no cross-host read" in findings
    for name in ("dispatch", "dev-runner", "epic-gate"):
        assert not any(f.startswith(f"{name}: not readable") for f in findings), \
            "the build host CAN read dispatch/dev-runner/epic-gate — must not name them unreadable"


def test_build_findings_names_origin_unreadable_once_and_suppresses_lag_lines(tmp_path):
    checkout = _no_origin_checkout(tmp_path)
    home = tmp_path / "home-without-a-statement-file"
    findings = drift.build_findings(checkout, home)
    origin_lines = [f for f in findings if f.startswith("origin/main: UNREADABLE")]
    assert len(origin_lines) == 1, findings
    assert not any("TRAILS" in f for f in findings)
    # the missing dispatch statement is STILL named — a local unreadable surface doesn't depend on origin
    assert any(f.startswith("dispatch: UNREADABLE") for f in findings)


# ── no cross-host read path (spec callout (k)) ──────────────────────────────────────────────────

def test_workspace_findings_has_no_home_parameter_it_cannot_read_dispatchs_statement():
    """Structural: the workspace-host function has no way to reach `home`/the dispatch statement file
    at all — the population split is enforced by the function's own signature, not just its output."""
    params = list(inspect.signature(drift.workspace_findings).parameters)
    assert "home" not in params and "repo_dir" not in params


def test_build_findings_has_no_plugins_parameter_it_cannot_read_the_plugin_cache():
    params = list(inspect.signature(drift.build_findings).parameters)
    assert "plugins_path" not in params and "plugins" not in params


# ── the CLI — a standalone diagnostic path, advisory: loud, exit 1 on findings ──────────────────────

def test_cli_workspace_mode_prints_drift_prefixed_lines_and_exits_1_on_findings(monkeypatch, capsys):
    monkeypatch.setattr(drift, "workspace_findings", lambda root, plugins: ["surface: a finding"])
    rc = drift.main(["workspace", "/some/root"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "drift: surface: a finding" in out


def test_cli_workspace_mode_exits_0_and_is_silent_when_clean(monkeypatch, capsys):
    monkeypatch.setattr(drift, "workspace_findings", lambda root, plugins: [])
    rc = drift.main(["workspace", "/some/root"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_cli_build_mode_prints_drift_prefixed_lines_and_exits_1_on_findings(monkeypatch, capsys):
    monkeypatch.setattr(drift, "build_findings", lambda root, home: ["surface: a finding"])
    rc = drift.main(["build", "/some/root", "--home", "/some/home"])
    assert rc == 1
    assert "drift: surface: a finding" in capsys.readouterr().out


def test_cli_build_mode_requires_home(capsys):
    with pytest.raises(SystemExit):
        drift.main(["build", "/some/root"])


def test_cli_workspace_mode_passes_root_and_plugins_through(monkeypatch, tmp_path):
    seen = {}

    def fake(root, plugins):
        seen["root"], seen["plugins"] = root, plugins
        return []

    monkeypatch.setattr(drift, "workspace_findings", fake)
    drift.main(["workspace", str(tmp_path), "--plugins", "/x/installed_plugins.json"])
    assert seen == {"root": str(tmp_path), "plugins": "/x/installed_plugins.json"}


def test_cli_build_mode_passes_root_and_home_through(monkeypatch, tmp_path):
    seen = {}

    def fake(root, home):
        seen["root"], seen["home"] = root, home
        return []

    monkeypatch.setattr(drift, "build_findings", fake)
    drift.main(["build", str(tmp_path), "--home", "/x/home"])
    assert seen == {"root": str(tmp_path), "home": "/x/home"}


def test_cli_end_to_end_workspace_mode_against_a_real_clean_checkout(tmp_path):
    """No monkeypatching at all: a real checkout, a real local origin, run as a real subprocess — the
    two-moments contract needs no runner build, so the CLI itself is one legitimate standalone path."""
    checkout, _, _ = _origin_and_checkout(tmp_path)
    plugins = _empty_plugins(tmp_path)
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "drift.py"), "workspace", str(checkout),
                       "--plugins", str(plugins)], capture_output=True, text=True)
    # always >0: dispatch/dev-runner/epic-gate are unconditionally named unreadable from this host
    assert r.returncode == 1
    assert "drift: dispatch: not readable from this host" in r.stdout
    assert "TRAILS" not in r.stdout
    assert "attended-session (plugin cache): UNREADABLE" in r.stdout


# ── advisory tier: never a gate, never check_cmd, never CI, never a merge condition ────────────────

def test_drift_py_is_never_wired_into_check_cmd_or_lint_cmd():
    cfg = (ROOT / ".yr" / "factory.toml").read_text(encoding="utf-8")
    assert "drift.py" not in cfg


def test_drift_py_is_never_wired_into_any_github_workflow():
    workflows_dir = ROOT / ".github" / "workflows"
    for f in workflows_dir.glob("*.yml"):
        assert "drift.py" not in f.read_text(encoding="utf-8"), f"{f.name} references drift.py"


def test_main_module_docstring_or_header_declares_the_advisory_tier():
    src = (ROOT / "tools" / "drift.py").read_text(encoding="utf-8")
    assert "ADVISORY" in src
    assert "never" in src.lower() and ("check_cmd" in src or "merge" in src.lower())
