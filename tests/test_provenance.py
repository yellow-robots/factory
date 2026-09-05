"""Acceptance tests for tools/provenance.py — the one self-locate helper (it-33 slice 2, epic #455).

Every declared runtime surface states the commit of the whole tree it is executing from, in its own
log line, statement file, or delivered position — never a version string alone. This module is meant
to be the SINGLE home of the git self-locate read and of the declared population of surfaces; no
emission site should need to shell out to `git` on its own. These tests are derived from the GitHub
issue #457 acceptance criteria, not from the module's internals.
"""
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import provenance  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(path, *, name="a.txt", content="hello\n"):
    """A minimal, throwaway git repo with exactly one commit — returns its HEAD sha."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], path)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test"], path)
    (path / name).write_text(content)
    _git(["add", name], path)
    _git(["commit", "-q", "-m", "initial"], path)
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


# ── SURFACES — the declared population ──────────────────────────────────────────────────────────

def test_surfaces_names_exactly_the_four_declared_runtime_surfaces():
    assert set(provenance.SURFACES) == {"dispatch", "dev-runner", "epic-gate", "attended-session"}
    assert len(provenance.SURFACES) == 4


# ── factory_commit — the self-locate read ───────────────────────────────────────────────────────

def test_factory_commit_resolves_to_the_real_head_of_a_git_repo(tmp_path):
    sha = _init_repo(tmp_path / "repo")
    assert provenance.factory_commit(tmp_path / "repo") == sha
    assert SHA_RE.match(sha)


def test_factory_commit_reports_unreadable_for_a_non_git_root(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    got = provenance.factory_commit(plain)
    assert got.startswith("unreadable:")


def test_factory_commit_reports_unreadable_for_a_missing_root_never_raises(tmp_path):
    missing = tmp_path / "does" / "not" / "exist"
    got = provenance.factory_commit(missing)
    assert got.startswith("unreadable:")


def test_factory_commit_never_raises_when_git_binary_is_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))   # no `git` anywhere on PATH
    got = provenance.factory_commit(tmp_path)
    assert got.startswith("unreadable:")


# ── statement — the `commit: <sha>` line every emission site prints verbatim ────────────────────

def test_statement_is_the_commit_form_never_a_bare_version_string(tmp_path):
    sha = _init_repo(tmp_path / "repo")
    assert provenance.statement(tmp_path / "repo") == f"commit: {sha}"


def test_statement_names_the_failure_when_the_read_is_unreadable(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    stmt = provenance.statement(plain)
    assert stmt.startswith("commit: unreadable:")


# ── dispatch_statement_path — where dispatch's statement file lives ────────────────────────────

def test_dispatch_statement_path_is_named_dispatch_statement_under_the_given_home(tmp_path):
    assert provenance.dispatch_statement_path(tmp_path) == tmp_path / "dispatch.statement"
    assert provenance.dispatch_statement_path(str(tmp_path)) == tmp_path / "dispatch.statement"


# ── plugin_cache_root / plugin_cache_statement — the cache half, cross-checked both ways ────────

def _plugins_json(path, **entries):
    path.write_text(json.dumps(entries))
    return path


def test_plugin_cache_root_reads_the_declared_plugin_entry(tmp_path):
    cache_dir = tmp_path / "cache-checkout"
    plugins = _plugins_json(tmp_path / "installed_plugins.json",
                            **{"factory@yellow-robots": {"installPath": str(cache_dir),
                                                          "gitCommitSha": "deadbeef" * 5}})
    root, recorded = provenance.plugin_cache_root(plugins)
    assert root == cache_dir
    assert recorded == "deadbeef" * 5


def test_plugin_cache_root_is_none_none_when_file_missing(tmp_path):
    root, recorded = provenance.plugin_cache_root(tmp_path / "does-not-exist.json")
    assert (root, recorded) == (None, None)


def test_plugin_cache_root_is_none_none_when_file_is_not_valid_json(tmp_path):
    p = tmp_path / "installed_plugins.json"
    p.write_text("not json at all {{{")
    assert provenance.plugin_cache_root(p) == (None, None)


def test_plugin_cache_root_is_none_none_when_entry_absent(tmp_path):
    plugins = _plugins_json(tmp_path / "installed_plugins.json",
                            **{"some-other-plugin": {"installPath": "/x", "gitCommitSha": "abc"}})
    assert provenance.plugin_cache_root(plugins) == (None, None)


def test_plugin_cache_statement_reports_unreadable_with_no_entry(tmp_path):
    plugins = tmp_path / "installed_plugins.json"
    plugins.write_text(json.dumps({}))
    stmt = provenance.plugin_cache_statement(plugins)
    assert stmt.startswith("cache commit: unreadable:")
    assert "factory@yellow-robots" in stmt


def test_plugin_cache_statement_matches_when_cache_head_equals_the_installer_record(tmp_path):
    cache_dir = tmp_path / "cache-checkout"
    sha = _init_repo(cache_dir)
    plugins = _plugins_json(tmp_path / "installed_plugins.json",
                            **{"factory@yellow-robots": {"installPath": str(cache_dir),
                                                          "gitCommitSha": sha}})
    stmt = provenance.plugin_cache_statement(plugins)
    assert stmt == f"cache commit: {sha}"
    assert "MISMATCH" not in stmt


def test_plugin_cache_statement_names_a_mismatch_both_ways(tmp_path):
    cache_dir = tmp_path / "cache-checkout"
    actual_sha = _init_repo(cache_dir)
    recorded_sha = "f" * 40
    assert recorded_sha != actual_sha
    plugins = _plugins_json(tmp_path / "installed_plugins.json",
                            **{"factory@yellow-robots": {"installPath": str(cache_dir),
                                                          "gitCommitSha": recorded_sha}})
    stmt = provenance.plugin_cache_statement(plugins)
    assert "MISMATCH" in stmt
    assert actual_sha in stmt                  # the cache's own HEAD ...
    assert recorded_sha in stmt                # ... cross-checked against the installer's record


def test_plugin_cache_statement_no_false_mismatch_when_cache_root_is_unreadable(tmp_path):
    # the cache dir exists but isn't a git repo: `actual` comes back "unreadable: ..." — the mismatch
    # branch must not fire just because it differs textually from a valid recorded sha.
    cache_dir = tmp_path / "cache-checkout"
    cache_dir.mkdir()
    plugins = _plugins_json(tmp_path / "installed_plugins.json",
                            **{"factory@yellow-robots": {"installPath": str(cache_dir),
                                                          "gitCommitSha": "a" * 40}})
    stmt = provenance.plugin_cache_statement(plugins)
    assert "MISMATCH" not in stmt
    assert "unreadable" in stmt


# ── the CLI — dev-runner's best-effort banner seam ──────────────────────────────────────────────

def test_cli_prints_the_statement_for_the_given_root(tmp_path):
    sha = _init_repo(tmp_path / "repo")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "provenance.py"), str(tmp_path / "repo")],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == f"commit: {sha}"


def test_cli_defaults_root_to_the_current_directory(tmp_path):
    sha = _init_repo(tmp_path / "repo")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "provenance.py")],
                       capture_output=True, text=True, cwd=str(tmp_path / "repo"))
    assert r.returncode == 0
    assert r.stdout.strip() == f"commit: {sha}"


# ── no emission site shells out to git on its own — the helper is the single home of the read ──

def test_no_other_tool_module_reads_head_via_a_direct_git_rev_parse():
    """`factory_commit` (this module) is the only legal `git rev-parse HEAD`-style self-locate read
    for a runtime surface's OWN commit statement; every emission site composes through it instead."""
    for f in (ROOT / "tools").glob("*.py"):
        if f.name == "provenance.py":
            continue
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"rev-parse[^\n]*HEAD", src), \
            f"{f.name} shells out to `git rev-parse HEAD` directly instead of using provenance.py"


def test_dev_runner_banner_shells_out_to_the_helper_not_git_directly():
    src = (ROOT / "tools" / "dev-runner.sh").read_text(encoding="utf-8")
    m = re.search(r"^RUN_COMMIT_STATEMENT=.*$", src, re.MULTILINE)
    assert m, "dev-runner.sh no longer composes a RUN_COMMIT_STATEMENT for its run banner"
    line = m.group(0)
    assert "provenance.py" in line
    assert "rev-parse" not in line and "GIT_BIN" not in line
