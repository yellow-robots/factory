"""Acceptance tests for tools/close-runner.sh — the close stage's own stage runner (it-36 slice H,
#473, folded #472-review-style 2026-09-06): one `claude -p` close-walk stage, then
`check_supersession.py --sweep`, then `tools/round_record.py ship-walk` / `round-record` /
`crossover`, in that order. A stubbed `claude`, `tools/round_record.py` (via `ROUND_RECORD_PY`) and
`tools/check_supersession.py` (via `CHECK_SUPERSESSION_PY`) drive the orchestration — no live gh, no
live vault, no live vault-mirror tree — mirroring tests/test_cross_runner.py's own `CROSS_PY`
pattern.

Criteria under test here (the shell-level orchestration; tests/test_round_record.py covers the
underlying computation/apply logic this script calls out to):
  - `component-root`/`strategy-doc` ride on ARGV (positional, B3), never an environment variable.
  - an empty component-root stops the runner BEFORE the close-walk stage even runs (nothing to
    ground the walk against) — a loud, non-fatal exit (0), mirroring tools/design-review-runner.sh's
    own `DESIGN_COMPONENT_ROOT` unset case.
  - I3's idempotence guard: when `already-shipped` reports YR-SHIP-WALK is already on the trail, the
    close-walk stage, the supersession sweep, and ship-walk are ALL skipped — round-record/crossover
    still run.
  - given a component root and nothing already shipped: close-walk, then the supersession sweep,
    then ship-walk, then round-record, then crossover, in that order (I10).
  - a `ship-walk` failure stops the run SHORT of `round-record`/`crossover` — no partial close is
    ever posted.
  - an empty/unreadable strategy-doc skips `crossover` only — `ship-walk`/`round-record` still post,
    and the run still exits 0 (crossover is not one of the close arm's own gate-mandated records).
"""
import pathlib
import stat
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "close-runner.sh"

REPO = "acme/widgets"
EPIC = "465"

CLAUDE_STUB = '''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\\n'"$stdin_content"
case "$args" in
  *"close-walk stage"*)
    echo CLOSE_WALK >> "$STUB_TIMELINE"
    [ -n "${STUB_CLOSE_WALK_FAIL:-}" ] && exit 1
    cat <<'EOF'
===LIVING-REFERENCE===
path: 04 projects/acme/architecture/README.md
heading: Build hosts
===CONTENT===
Updated at this round's close.
===END-CONTENT===
===END-LIVING-REFERENCE===
===SUPERSEDED===
===END-SUPERSEDED===
EOF
    ;;
  *)
    echo UNKNOWN >> "$STUB_TIMELINE"
    exit 1 ;;
esac
exit 0
'''

# ROUND_RECORD_PY fake: logs its own argv (one JSON line per call) into STUB_TIMELINE (the
# subcommand name only, so the SAME timeline file orders it against the claude/check_supersession
# stubs' own entries) and into STUB_RR_ARGV_LOG (the full argv, for assertions on what this runner
# handed it). `fetch` must print JSON to stdout (close-runner.sh reads it back for the epic body).
# `already-shipped` exits 0 (shipped) iff STUB_ALREADY_SHIPPED is set.
ROUND_RECORD_PY_STUB = '''#!/usr/bin/env python3
import json, os, sys

argv = sys.argv[1:]
cmd = argv[0] if argv else ""
timeline = os.environ.get("STUB_TIMELINE")
if timeline:
    with open(timeline, "a") as f:
        f.write(cmd.upper().replace("-", "_") + "\\n")
log = os.environ.get("STUB_RR_ARGV_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(argv) + "\\n")

if cmd == "fetch":
    print(json.dumps({"epic_texts": ["the epic's own technical-rfc body"], "child_texts": {}, "pr_refs": []}))
    sys.exit(0)
if cmd == "already-shipped":
    sys.exit(0 if os.environ.get("STUB_ALREADY_SHIPPED") else 1)
if cmd == "ship-walk":
    sys.exit(1 if os.environ.get("STUB_SHIP_WALK_FAIL") else 0)
if cmd == "round-record":
    sys.exit(1 if os.environ.get("STUB_ROUND_RECORD_FAIL") else 0)
if cmd == "crossover":
    sys.exit(1 if os.environ.get("STUB_CROSSOVER_FAIL") else 0)
sys.exit(1)
'''

# CHECK_SUPERSESSION_PY fake: logs SUPERSESSION_SWEEP into the shared timeline; exits 1 (a legacy
# finding) iff STUB_SUPERSESSION_FAIL is set, else 0 (clean) — either way the run proceeds
# (advisory-only, I10).
CHECK_SUPERSESSION_PY_STUB = '''#!/usr/bin/env python3
import os, sys
timeline = os.environ.get("STUB_TIMELINE")
if timeline:
    with open(timeline, "a") as f:
        f.write("SUPERSESSION_SWEEP\\n")
if os.environ.get("STUB_SUPERSESSION_FAIL"):
    print("legacy doc found: some/path.md")
    sys.exit(1)
print("sweep clean")
sys.exit(0)
'''


def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _timeline(tmp):
    p = tmp / "timeline"
    return p.read_text().splitlines() if p.exists() else []


def _rr_calls(tmp):
    import json as _json
    p = tmp / "rr_argv_log"
    if not p.exists():
        return []
    return [_json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _run(tmp_path, *, component_root=None, strategy_doc=None, extra_env=None):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "claude", CLAUDE_STUB)
    rr_py = tmp_path / "round_record_stub.py"
    _exec(rr_py, ROUND_RECORD_PY_STUB)
    cs_py = tmp_path / "check_supersession_stub.py"
    _exec(cs_py, CHECK_SUPERSESSION_PY_STUB)
    dev_runner_home = tmp_path / "drhome"

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "ROUND_RECORD_PY": str(rr_py),
        "CHECK_SUPERSESSION_PY": str(cs_py),
        "STUB_TIMELINE": str(tmp_path / "timeline"),
        "STUB_RR_ARGV_LOG": str(tmp_path / "rr_argv_log"),
    }
    # I4: pop the calling shell's own values for everything this runner reads, rather than let a
    # real dev machine's env leak into the test (moot for the old CLOSE_* env vars post-B3, since
    # they are argv now — still done for the rest).
    for key in ("CLOSE_COMPONENT_ROOT", "CLOSE_STRATEGY_DOC", "DESIGN_MODEL", "EFFORT",
               "YR_GH_APP_SLUG", "YR_VAULT_ROOT"):
        env.pop(key, None)
    env.update(extra_env or {})
    argv = ["bash", str(RUNNER), REPO, EPIC]
    if component_root is not None:
        argv.append(str(component_root))
        if strategy_doc is not None:
            argv.append(str(strategy_doc))
    result = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=60)
    return result


# ---- empty component-root: a loud, non-fatal stop before the stage even runs --------------------------

def test_empty_component_root_stops_before_the_close_walk_stage_runs(tmp_path):
    result = _run(tmp_path, component_root=None)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "no component-root given" in result.stderr
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED"]   # the close-walk stage never ran


def test_empty_component_root_still_fetches_and_checks_already_shipped_only(tmp_path):
    result = _run(tmp_path, component_root=None)
    assert result.returncode == 0
    calls = [c[0] for c in _rr_calls(tmp_path)]
    assert calls == ["fetch", "already-shipped"]


# ---- I3: already-shipped skips the close-walk stage, the supersession sweep, and ship-walk -------------

def test_already_shipped_skips_close_walk_sweep_and_ship_walk_but_still_runs_round_record(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root,
                  extra_env={"STUB_ALREADY_SHIPPED": "1"})
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED", "ROUND_RECORD"]
    assert "already-shipped" in result.stderr
    calls = [c[0] for c in _rr_calls(tmp_path)]
    assert "ship-walk" not in calls


# ---- the happy path: close-walk, supersession sweep, ship-walk, round-record, crossover, in order ------

def test_close_walk_then_sweep_then_ship_walk_round_record_crossover_run_in_order(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    (component_root / "architecture" / "README.md").write_text("# Living reference\n\n## Build hosts\n\nold text\n")
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("---\n---\n\n```yr-strategy\nthemes = []\n```\n")

    result = _run(tmp_path, component_root=component_root, strategy_doc=strategy_doc)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED", "CLOSE_WALK", "SUPERSESSION_SWEEP",
                                   "SHIP_WALK", "ROUND_RECORD", "CROSSOVER"]


def test_ship_walk_is_called_with_the_supersession_sweep_status_and_the_epic_scope(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root)
    assert result.returncode == 0, f"stderr={result.stderr}"
    calls = {c[0]: c for c in _rr_calls(tmp_path)}
    ship_walk_argv = calls["ship-walk"]
    assert "--repo" in ship_walk_argv and REPO in ship_walk_argv
    assert "--epic" in ship_walk_argv and EPIC in ship_walk_argv
    assert "--scope" in ship_walk_argv
    scope_val = ship_walk_argv[ship_walk_argv.index("--scope") + 1]
    assert scope_val == f"{REPO}#{EPIC}"
    assert "--supersession-sweep" in ship_walk_argv
    sweep_val = ship_walk_argv[ship_walk_argv.index("--supersession-sweep") + 1]
    assert "clean" in sweep_val


def test_a_failed_supersession_sweep_is_reported_but_never_blocks_the_run(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root,
                  extra_env={"STUB_SUPERSESSION_FAIL": "1"})
    assert result.returncode == 0, f"stderr={result.stderr}"
    calls = {c[0]: c for c in _rr_calls(tmp_path)}
    sweep_val = calls["ship-walk"][calls["ship-walk"].index("--supersession-sweep") + 1]
    assert "legacy doc found" in sweep_val


# ---- a ship-walk failure stops SHORT of round-record/crossover — never a partial close -----------------

def test_ship_walk_failure_stops_before_round_record_and_crossover(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root,
                  extra_env={"STUB_SHIP_WALK_FAIL": "1"})
    assert result.returncode == 1
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED", "CLOSE_WALK", "SUPERSESSION_SWEEP",
                                   "SHIP_WALK"]


def test_round_record_failure_stops_before_crossover(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("irrelevant — round-record fails first")
    result = _run(tmp_path, component_root=component_root, strategy_doc=strategy_doc,
                  extra_env={"STUB_ROUND_RECORD_FAIL": "1"})
    assert result.returncode == 1
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED", "CLOSE_WALK", "SUPERSESSION_SWEEP",
                                   "SHIP_WALK", "ROUND_RECORD"]


# ---- empty/unreadable strategy-doc: crossover skipped, but the run still exits 0 (advisory-only) -------

def test_missing_strategy_doc_skips_crossover_but_still_exits_zero(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root, strategy_doc=None)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED", "CLOSE_WALK", "SUPERSESSION_SWEEP",
                                   "SHIP_WALK", "ROUND_RECORD"]
    assert "no strategy-doc given" in result.stderr


def test_a_crossover_failure_is_non_fatal_the_run_still_exits_zero(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("some strategy doc")
    result = _run(tmp_path, component_root=component_root, strategy_doc=strategy_doc,
                  extra_env={"STUB_CROSSOVER_FAIL": "1"})
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "ALREADY_SHIPPED", "CLOSE_WALK", "SUPERSESSION_SWEEP",
                                   "SHIP_WALK", "ROUND_RECORD", "CROSSOVER"]
