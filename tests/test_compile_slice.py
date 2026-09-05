"""Delivery serves the compiled slice, inside the boundary (it-31 slice 8, epic #432 — #440).

`hooks/deliver.sh` serves `build/slice-static.md` (GENERATED from process.toml) plus the live
position; `tools/compile_slice.py` keeps only the position half and the delivery boundary gate.
The old canon-table splice is retired — a hand map beside a generated one is a drift twin. Two
stances hold: LOUD (every failure names itself) and NON-BLOCKING (the hook always exits 0); and a
third joins them: SILENT outside the factory's declared world (the boundary criterion — today's
hook injected into every non-machinery session everywhere).
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import compile_slice  # noqa: E402


def _attended_env(**extra):
    """Delivery is for ATTENDED sessions; the suite declares itself machinery (tests/conftest.py),
    and the hook correctly skips machinery. A delivery test opts back into the attended path."""
    env = dict(os.environ, **extra)
    env.pop("YR_MACHINERY", None)
    return env


def _deliver(env, stdin=""):
    return subprocess.run(["bash", str(REPO / "hooks" / "deliver.sh")],
                          capture_output=True, text=True, env=env, input=stdin)


def _hook_json(cwd):
    return json.dumps({"hookEventName": "SessionStart", "cwd": str(cwd)})


# ── the compiler keeps only the position half ────────────────────────────────────────────────────

def test_compile_slice_no_longer_splices_canon():
    """The slice-4 migration lands: the static half is process.py's compiled surface, and this
    module reads no canon tables — a hand map beside a generated one is a drift twin."""
    src = (REPO / "tools" / "compile_slice.py").read_text(encoding="utf-8")
    assert "attended-lane.md" not in src, "the compiler still splices the canon's hand tables"
    assert "_extract_table" not in src and "_human_checkpoints" not in src


def test_position_composes_repo_prs_and_board(monkeypatch):
    def fake_run(argv, timeout):
        j = " ".join(str(a) for a in argv)
        if "decay" in j:
            return 0, ""
        if "repo view" in j:
            return 0, "yellow-robots/factory\n"
        if "pr list" in j:
            return 0, "PR#7 CLEAN: a title\n"
        if "board.sh" in j:
            # the REAL board.sh column shape: number, nameWithOwner, itype, status, reason, title
            # (the slice-8 review: a stub with the short name matched the bug, not the tool)
            return 0, ("7\tyellow-robots/factory\tTask\tReady\t\ta title\n"
                       "9\tyellow-robots/factory\tTask\tReady\tBlocked\theld one\n"
                       "8\tyellow-robots/website\tTask\tReady\t\tother\n")
        return 1, ""

    monkeypatch.setattr(compile_slice, "_run", fake_run)
    out = compile_slice.position(REPO)
    assert "## Position (composed at delivery" in out
    assert "Repo: yellow-robots/factory" in out
    assert "PR#7" in out
    assert "#7 [Ready] a title" in out
    assert "#9 [Ready · Blocked] held one" in out, "a non-empty Reason must ride the row"
    assert "other" not in out, "the board excerpt must filter to THIS repo's rows"


def test_position_degradation_note_travels(monkeypatch):
    def fake_run(argv, timeout):
        j = " ".join(str(a) for a in argv)
        if "decay" in j:
            return 0, "COVERAGE DEGRADED: gh.pr.surface drifted\n"
        if "repo view" in j:
            return 0, "o/r\n"
        return 0, ""

    monkeypatch.setattr(compile_slice, "_run", fake_run)
    assert "COVERAGE DEGRADED" in compile_slice.position(REPO)


def test_position_failures_are_loud_lines_never_raises(monkeypatch):
    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    out = compile_slice.position(REPO)
    assert "Position unavailable" in out
    monkeypatch.setattr(compile_slice, "_run",
                        lambda argv, timeout: (0, "o/r\n") if "repo view" in " ".join(argv)
                        else (1, ""))
    out2 = compile_slice.position(REPO)
    assert "Repo: o/r" in out2 and "PR read unavailable" in out2


# ── it-33 slice 2 (issue #457) — position states BOTH declared halves: the workspace checkout
# (root taken from the caller, never __file__-relative) and the plugin cache, cross-checked ────────

def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], path)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test"], path)
    (path / "a.txt").write_text("hello\n")
    _git(["add", "a.txt"], path)
    _git(["commit", "-q", "-m", "initial"], path)
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_position_states_the_checkout_commit_of_the_given_root_not_repoself(monkeypatch, tmp_path):
    # a root that is provably NOT where compile_slice.py itself lives, with its own distinct commit —
    # proves the checkout half comes from the given root, never an __file__-relative read.
    other_root = tmp_path / "workspace-checkout"
    sha = _init_repo(other_root)
    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    monkeypatch.setattr(compile_slice.provenance, "plugin_cache_statement", lambda: "cache commit: stub")
    out = compile_slice.position(other_root)
    assert f"Checkout commit: {sha}" in out
    assert sha not in subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                     capture_output=True, text=True, check=True).stdout


def test_position_states_the_plugin_cache_half_verbatim(monkeypatch):
    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    monkeypatch.setattr(compile_slice.provenance, "plugin_cache_statement",
                        lambda: "cache commit: abc123 (installer recorded def456 — MISMATCH)")
    out = compile_slice.position(REPO)
    assert "Plugin cache commit: abc123 (installer recorded def456 — MISMATCH)" in out


def test_position_never_shells_out_to_git_directly_for_either_commit_half():
    src = (REPO / "tools" / "compile_slice.py").read_text(encoding="utf-8")
    assert "provenance.statement(root)" in src
    assert "provenance.plugin_cache_statement()" in src
    assert "rev-parse" not in src


# ── it-33 slice 4 (issue #458) — position folds in the drift alarm's workspace-host moment ─────────

def test_position_folds_in_the_workspace_drift_findings_as_drift_lines(monkeypatch):
    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    monkeypatch.setattr(compile_slice.provenance, "plugin_cache_statement", lambda: "cache commit: stub")
    monkeypatch.setattr(compile_slice.drift, "workspace_findings",
                        lambda root: ["attended-session (checkout): TRAILS origin/main "
                                      "(at aaaaaaaaaaaa, origin/main at bbbbbbbbbbbb)",
                                      "dispatch: not readable from this host — no cross-host read"])
    out = compile_slice.position(REPO)
    assert ("Drift: attended-session (checkout): TRAILS origin/main "
            "(at aaaaaaaaaaaa, origin/main at bbbbbbbbbbbb)") in out
    assert "Drift: dispatch: not readable from this host — no cross-host read" in out


def test_position_has_no_drift_lines_when_the_workspace_moment_is_clean(monkeypatch):
    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    monkeypatch.setattr(compile_slice.provenance, "plugin_cache_statement", lambda: "cache commit: stub")
    monkeypatch.setattr(compile_slice.drift, "workspace_findings", lambda root: [])
    out = compile_slice.position(REPO)
    assert "Drift:" not in out


def test_position_passes_its_own_root_to_workspace_findings_not_repo_self(monkeypatch, tmp_path):
    seen = {}

    def fake_workspace_findings(root):
        seen["root"] = root
        return []

    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    monkeypatch.setattr(compile_slice.provenance, "plugin_cache_statement", lambda: "cache commit: stub")
    monkeypatch.setattr(compile_slice.drift, "workspace_findings", fake_workspace_findings)
    compile_slice.position(tmp_path)
    assert seen["root"] == tmp_path


def test_position_drift_lines_sit_right_after_the_declared_provenance_lines(monkeypatch):
    """The drift findings ride the SAME position element as the checkout/cache statements — not a
    separate, possibly-dropped section."""
    monkeypatch.setattr(compile_slice, "_run", lambda argv, timeout: (1, ""))
    monkeypatch.setattr(compile_slice.provenance, "plugin_cache_statement", lambda: "cache commit: stub")
    monkeypatch.setattr(compile_slice.drift, "workspace_findings", lambda root: ["surface: a finding"])
    lines = compile_slice.position(REPO).splitlines()
    plugin_idx = next(i for i, l in enumerate(lines) if l.startswith("Plugin "))
    assert lines[plugin_idx + 1] == "Drift: surface: a finding"


def test_deliver_sh_passes_the_sessions_cwd_as_the_checkout_root_not_the_plugin_root(tmp_path):
    """The workspace checkout half must name the SESSION's own working directory's commit — never
    the plugin cache's (CLAUDE_PLUGIN_ROOT, where compile_slice.py itself runs from). A fake session
    workspace, marked in-scope and carrying its own distinct commit, proves the two never collude."""
    workspace = tmp_path / "workspace"
    (workspace / ".yr").mkdir(parents=True)
    (workspace / ".yr" / "factory.toml").write_text('check_cmd = "true"\n')
    ws_sha = _init_repo(workspace)

    repo_sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert ws_sha != repo_sha, "the fixture is meaningless if the two repos share a commit"

    binp = tmp_path / "bin"
    binp.mkdir()
    gh = binp / "gh"
    gh.write_text("#!/bin/sh\necho 'stub'\n")
    gh.chmod(0o755)
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(REPO), HOME=str(tmp_path / "fakehome"),
                        PATH=str(binp) + os.pathsep + os.environ["PATH"])
    out = _deliver(env, stdin=_hook_json(workspace))
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert f"Checkout commit: {ws_sha}" in ctx
    assert f"Checkout commit: {repo_sha}" not in ctx


def test_in_scope_gate_exit_codes(outside_cwd):
    inside = subprocess.run([sys.executable, str(REPO / "tools" / "compile_slice.py"),
                             "--in-scope", str(REPO)], capture_output=True, text=True)
    assert inside.returncode == 0
    outside = subprocess.run([sys.executable, str(REPO / "tools" / "compile_slice.py"),
                              "--in-scope", str(outside_cwd)], capture_output=True, text=True)
    assert outside.returncode == 3, "out-of-scope is exit 3 — distinct from a crash, which banners"


# ── delivery: static + position, inside the boundary ─────────────────────────────────────────────

def test_deliver_sh_serves_the_generated_static_plus_position(tmp_path):
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(REPO),
                        PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\necho 'PR#999 CLEAN: stubbed'\n")
    gh.chmod(0o755)
    out = _deliver(env, stdin=_hook_json(REPO))
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "GENERATED from process.toml" in ctx, "the delivered static half is the compiled surface"
    assert "the delivered slice (static half)" in ctx
    assert "## Position (composed at delivery" in ctx
    assert "PR#999" in ctx
    static = (REPO / "build" / "slice-static.md").read_text(encoding="utf-8")
    assert ctx.startswith(static), "delivery serves build/slice-static.md verbatim, position after"


def test_delivery_is_silent_outside_the_boundary(outside_cwd):
    """The delivery negative: a SessionStart in a non-factory directory gets NOTHING — no slice,
    no banner, no bytes (today's hook injects everywhere)."""
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(REPO))
    out = _deliver(env, stdin=_hook_json(outside_cwd))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_boundary_check_crash_banners_loud_never_locks(tmp_path):
    """A crashed delivery stays loud and never locks the human out — and a crash is NOT silence:
    only a clean out-of-scope verdict (exit 3) may suppress delivery."""
    fake_root = tmp_path / "root"
    (fake_root / "tools").mkdir(parents=True)
    (fake_root / "tools" / "compile_slice.py").write_text("import sys; sys.exit('broken on purpose')")
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(fake_root))
    out = _deliver(env, stdin=_hook_json(REPO))
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "YR-DELIVERY-FAILURE" in ctx and "attended-lane.md" in ctx


def test_missing_static_surface_banners_loud(tmp_path):
    fake_root = tmp_path / "root"
    (fake_root / "tools").mkdir(parents=True)
    (fake_root / "tools" / "compile_slice.py").write_text("import sys; sys.exit(0)")  # in-scope: yes
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(fake_root))
    out = _deliver(env, stdin=_hook_json(REPO))
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "YR-DELIVERY-FAILURE" in ctx and "slice-static" in ctx


def test_a_multibyte_error_tail_still_emits_a_loud_banner(tmp_path):
    """B2 regression (2026-08-07): a truncated multi-byte character must never turn the loud
    banner into silence; the error travels as its tail."""
    fake_root = tmp_path / "root"
    (fake_root / "tools").mkdir(parents=True)
    (fake_root / "tools" / "compile_slice.py").write_text(
        "import sys; sys.stderr.write('x'*298 + '\\u2014 the real reason lives at the end'); sys.exit(1)",
        encoding="utf-8")
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(fake_root))
    out = _deliver(env, stdin=_hook_json(REPO))
    assert out.returncode == 0
    assert out.stdout.strip(), "the hook emitted nothing — the loud stance was defeated"
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "YR-DELIVERY-FAILURE" in ctx
    assert "the real reason lives at the end" in ctx


def test_position_composer_failure_is_loud_non_blocking(tmp_path):
    """The static half still arrives when the position composer dies — with a loud line, never a
    withheld session."""
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(REPO),
                        PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    py = tmp_path / "python3"
    py.write_text("#!/bin/sh\ncase \"$*\" in *--in-scope*) exit 0;; *--position*) exit 7;; *) exec "
                  + sys.executable + " \"$@\";; esac\n")
    py.chmod(0o755)
    out = _deliver(env, stdin=_hook_json(REPO))
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "GENERATED from process.toml" in ctx
    assert "Position unavailable" in ctx


def test_machinery_gets_no_attended_canon():
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(REPO), YR_MACHINERY="1")
    out = _deliver(env, stdin=_hook_json(REPO))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_hooks_json_shape():
    cfg = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    starts = cfg["hooks"]["SessionStart"]
    assert len(starts) == 1
    matcher = starts[0]["matcher"]
    for m in ("startup", "clear", "compact", "resume"):
        assert m in matcher, f"SessionStart matcher missing {m!r} — the believes-already-read hazard"
    cmd = starts[0]["hooks"][0]["command"]
    assert "deliver.sh" in cmd and "CLAUDE_PLUGIN_ROOT" in cmd


def test_deliver_sh_is_executable():
    assert (REPO / "hooks" / "deliver.sh").stat().st_mode & stat.S_IXUSR


def test_position_is_repo_aware_not_hardcoded():
    """B5 regression: a hardcoded --repo told a website session the FACTORY's PRs were its
    position — the resolver moved into the composer with the position half."""
    src = (REPO / "tools" / "compile_slice.py").read_text(encoding="utf-8")
    assert "repo" in src and "view" in src, "the position element no longer resolves the current repo"
    assert "--repo yellow-robots/factory" not in src
    sh = (REPO / "hooks" / "deliver.sh").read_text(encoding="utf-8")
    assert "--repo yellow-robots/factory" not in sh


def test_deliver_sh_leaves_no_temp_files(tmp_path):
    before = set(Path("/tmp").glob("tmp.*.err"))
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(REPO),
                        PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\nexit 1\n")
    gh.chmod(0o755)
    _deliver(env, stdin=_hook_json(REPO))
    assert set(Path("/tmp").glob("tmp.*.err")) <= before, "deliver.sh leaked its stderr temp file"
