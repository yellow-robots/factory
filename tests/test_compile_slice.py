"""The delivered slice's compiler + the delivery hook config (it-30 slice 4, epic #415)."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import compile_slice  # noqa: E402


def test_compiler_is_deterministic_across_processes():
    """Two fresh interpreters, byte-identical output — the real determinism risk is iteration order
    across processes, which a same-process double call cannot see."""
    runs = [subprocess.run([sys.executable, str(REPO / "tools" / "compile_slice.py")],
                           capture_output=True, text=True, check=True).stdout for _ in range(2)]
    assert runs[0] == runs[1] and runs[0]


def test_slice_is_bounded_and_three_part():
    out = compile_slice.compile_slice()
    assert len(out.encode()) <= compile_slice.MAX_BYTES
    assert "## 1 · The mandatory step set" in out
    assert "## 2 · The walled-act map" in out
    assert "## 3 · Depth, routed — and the human's checkpoints" in out
    # compiled from the canon tables, not restated: spot rows travel through
    assert "YR-EPIC-APPROVAL" in out and "categorical" in out
    # the human's checkpoints are marked (the coordination arm), READ FROM CANON
    assert "cord-pull veto" in out and "ship-walk" in out
    canon = (REPO / "skills" / "factory" / "references" / "attended-lane.md").read_text(encoding="utf-8")
    section = canon.split("## The human's checkpoints")[1].split("\n## ")[0]
    for bullet in [l.rstrip() for l in section.splitlines() if l.startswith("- ")]:
        assert bullet in out, f"checkpoint not carried from canon: {bullet}"
    # position is composed at delivery, never cached into the artifact
    assert "Position" not in out


def test_compiled_artifact_carries_its_never_hand_edited_mark():
    assert "compiled; never hand-edited" in compile_slice.compile_slice()


def test_checkpoints_are_not_authored_in_the_compiler(tmp_path):
    """The drift-twin guard: the checkpoint list must come from canon, so a compiler that stops
    reading canon fails rather than shipping its own hardcoded copy."""
    src = (REPO / "tools" / "compile_slice.py").read_text(encoding="utf-8")
    assert "HUMAN_CHECKPOINTS = (" not in src, "checkpoints are hardcoded in the compiler again"
    assert "_human_checkpoints" in src


def test_a_reshaped_canon_fails_loud_not_silently_wrong(tmp_path):
    """A moved/emptied table must NOT let the next section's table be delivered under this heading."""
    lane = (REPO / "skills" / "factory" / "references" / "attended-lane.md").read_text(encoding="utf-8")
    head = "## The mandatory step set (reified — the existing mandates, not new ones)"
    body = lane.split(head)[1].split("\n## ")[0]
    emptied = lane.replace(body, "\n\n(table moved during a canon reshape)\n\n")
    fake = tmp_path / "attended-lane.md"
    fake.write_text(emptied, encoding="utf-8")
    with mock.patch.object(compile_slice, "LANE_REF", fake):
        with pytest.raises(SystemExit) as e:
            compile_slice.compile_slice()
    assert "no table under heading" in str(e.value)
    # and a reworded heading is loud too
    reworded = lane.replace(head, "## The steps")
    fake.write_text(reworded, encoding="utf-8")
    with mock.patch.object(compile_slice, "LANE_REF", fake):
        with pytest.raises(SystemExit) as e2:
            compile_slice.compile_slice()
    assert "heading not found" in str(e2.value)


def test_the_bound_is_enforced(monkeypatch):
    monkeypatch.setattr(compile_slice, "MAX_BYTES", 100)
    with pytest.raises(SystemExit) as e:
        compile_slice.compile_slice()
    assert "exceeds its bound" in str(e.value)


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
    assert "Position unavailable" in ctx or "read unavailable" in ctx


def test_a_multibyte_error_tail_still_emits_a_loud_banner(tmp_path):
    """B2 regression (cold review, 2026-08-07): the banner used to be truncated with `head -c`,
    which can cut a multi-byte character mid-sequence; the JSON emitter then died on decode and the
    hook wrote ZERO bytes while exiting 0 — non-blocking survived, loud did not. The error text now
    travels as its tail, read with errors replaced."""
    fake_root = tmp_path / "root"
    (fake_root / "tools").mkdir(parents=True)
    (fake_root / "tools" / "compile_slice.py").write_text(
        "import sys; sys.stderr.write('x'*298 + '\\u2014 the real reason lives at the end'); sys.exit(1)",
        encoding="utf-8")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(fake_root))
    out = subprocess.run(["bash", str(REPO / "hooks" / "deliver.sh")],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0
    assert out.stdout.strip(), "the hook emitted nothing — the loud stance was defeated"
    ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "YR-DELIVERY-FAILURE" in ctx
    assert "the real reason lives at the end" in ctx, "the banner truncated away the actual reason"


def test_machinery_gets_no_attended_canon(tmp_path):
    """A cold pipeline stage inherits YR_MACHINERY from the runner: the attended lane's canon is not
    its context, and delivering it would tax every stage of every build."""
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(REPO), YR_MACHINERY="1")
    out = subprocess.run(["bash", str(REPO / "hooks" / "deliver.sh")],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_position_is_repo_aware_not_hardcoded():
    """B5 regression: a hardcoded --repo told a website session the FACTORY's PRs were its position."""
    src = (REPO / "hooks" / "deliver.sh").read_text(encoding="utf-8")
    assert "gh repo view" in src, "the position element no longer resolves the current repo"
    assert "--repo yellow-robots/factory" not in src, "the position element hardcodes a repo again"


def test_deliver_sh_leaves_no_temp_files(tmp_path):
    before = set(Path("/tmp").glob("tmp.*.err"))
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(REPO), PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\nexit 1\n")
    gh.chmod(0o755)
    subprocess.run(["bash", str(REPO / "hooks" / "deliver.sh")], capture_output=True, text=True, env=env)
    assert set(Path("/tmp").glob("tmp.*.err")) <= before, "deliver.sh leaked its stderr temp file"
