"""The delivered slice's compiler + the delivery hook config (it-30 slice 4, epic #415)."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import compile_slice  # noqa: E402


def test_compiler_is_deterministic():
    assert compile_slice.compile_slice() == compile_slice.compile_slice()


def test_slice_is_bounded_and_three_part():
    out = compile_slice.compile_slice()
    assert len(out.encode()) <= compile_slice.MAX_BYTES
    assert "## 1 · The mandatory step set" in out
    assert "## 2 · The walled-act map" in out
    assert "## 3 · Depth, routed — and the human's checkpoints" in out
    # compiled from the canon tables, not restated: spot rows travel through
    assert "YR-EPIC-APPROVAL" in out and "categorical" in out
    # the human's checkpoints are marked (the coordination arm)
    assert "ship-walk trigger" in out and "cord-pull veto" in out
    # position is composed at delivery, never cached into the artifact
    assert "Position" not in out


def test_compiled_artifact_carries_its_never_hand_edited_mark():
    assert "compiled; never hand-edited" in compile_slice.compile_slice()


def test_cli_writes_and_prints():
    out = subprocess.run([sys.executable, str(REPO / "tools" / "compile_slice.py")],
                         capture_output=True, text=True, check=True)
    assert "The attended lane — the delivered slice" in out.stdout


def test_hooks_json_shape():
    cfg = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    starts = cfg["hooks"]["SessionStart"]
    assert len(starts) == 1
    matcher = starts[0]["matcher"]
    for m in ("startup", "clear", "compact", "resume"):
        assert m in matcher, f"SessionStart matcher missing {m!r} — the believes-already-read hazard"
    cmd = starts[0]["hooks"][0]["command"]
    assert "deliver.sh" in cmd and "CLAUDE_PLUGIN_ROOT" in cmd


def test_deliver_sh_is_executable_and_loud_non_blocking_on_compile_failure(tmp_path):
    script = REPO / "hooks" / "deliver.sh"
    assert script.stat().st_mode & stat.S_IXUSR, "deliver.sh must be executable"
    # Break the compiler by pointing CLAUDE_PLUGIN_ROOT at an empty root: the hook must still
    # exit 0 and emit the loud banner as additionalContext — never lock the session.
    fake_root = tmp_path / "root"
    (fake_root / "tools").mkdir(parents=True)
    (fake_root / "tools" / "compile_slice.py").write_text("import sys; sys.exit('broken on purpose')")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(fake_root))
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
    assert out.returncode == 0
    payload = json.loads(out.stdout)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "YR-DELIVERY-FAILURE" in ctx and "attended-lane.md" in ctx


def test_deliver_sh_happy_path_carries_slice_and_position(tmp_path):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(REPO), PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    # stub gh so the position element is deterministic and offline
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\necho 'PR#999 CLEAN: stubbed'\n")
    gh.chmod(0o755)
    out = subprocess.run(["bash", str(REPO / "hooks" / "deliver.sh")], capture_output=True, text=True, env=env)
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "## 1 · The mandatory step set" in ctx
    assert "## Position (composed at delivery" in ctx
    assert "PR#999" in ctx


def test_deliver_sh_position_failure_is_loud_non_blocking(tmp_path):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(REPO), PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\nexit 1\n")
    gh.chmod(0o755)
    out = subprocess.run(["bash", str(REPO / "hooks" / "deliver.sh")], capture_output=True, text=True, env=env)
    assert out.returncode == 0
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Position read unavailable" in ctx
