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
            return 0, "7\tfactory\tTask\tx\tReady\ta title\n8\twebsite\tTask\tx\tReady\tother\n"
        return 1, ""

    monkeypatch.setattr(compile_slice, "_run", fake_run)
    out = compile_slice.position(REPO)
    assert "## Position (composed at delivery" in out
    assert "Repo: yellow-robots/factory" in out
    assert "PR#7" in out
    assert "#7 [Ready] a title" in out
    assert "website" not in out, "the board excerpt must filter to THIS repo's rows"


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


def test_in_scope_gate_exit_codes(tmp_path):
    inside = subprocess.run([sys.executable, str(REPO / "tools" / "compile_slice.py"),
                             "--in-scope", str(REPO)], capture_output=True, text=True)
    assert inside.returncode == 0
    outside = subprocess.run([sys.executable, str(REPO / "tools" / "compile_slice.py"),
                              "--in-scope", str(tmp_path)], capture_output=True, text=True)
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


def test_delivery_is_silent_outside_the_boundary(tmp_path):
    """The delivery negative: a SessionStart in a non-factory directory gets NOTHING — no slice,
    no banner, no bytes (today's hook injects everywhere)."""
    env = _attended_env(CLAUDE_PLUGIN_ROOT=str(REPO))
    out = _deliver(env, stdin=_hook_json(tmp_path))
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
