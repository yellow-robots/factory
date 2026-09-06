"""Acceptance tests for tools/close-runner.sh — the close stage's own stage runner (it-36 slice H,
#473): one `claude -p` close-walk stage, then `tools/round_record.py ship-walk` / `round-record` /
`crossover`, in that order. A stubbed `claude` (no live LLM) and a stubbed `tools/round_record.py`
(via the `ROUND_RECORD_PY` test-only override — no live gh, no live vault, no real epic) drive the
orchestration, mirroring tests/test_cross_runner.py's own `CROSS_PY` pattern.

Criteria under test here (the shell-level orchestration; tests/test_round_record.py covers the
underlying computation/apply logic this script calls out to):
  - `CLOSE_COMPONENT_ROOT` unset stops the runner BEFORE the close-walk stage even runs (nothing to
    ground the walk against) — a loud, non-fatal exit (0), mirroring tools/design-review-runner.sh's
    own `DESIGN_COMPONENT_ROOT` unset case.
  - given a component root, the close-walk stage runs, then `ship-walk`, then `round-record`, then
    `crossover`, in that order.
  - a `ship-walk` failure stops the run SHORT of `round-record`/`crossover` — no partial close is
    ever posted.
  - `CLOSE_STRATEGY_DOC` unset (or unreadable) skips `crossover` only — `ship-walk`/`round-record`
    still post, and the run still exits 0 (crossover is not one of the close arm's own gate-mandated
    records).
"""
import pathlib
import stat
import subprocess
import sys

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
heading: ## Build hosts
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
# subcommand name only, so the SAME timeline file orders it against the claude stub's own
# CLOSE_WALK entry) and into STUB_RR_ARGV_LOG (the full argv, for assertions on what this runner
# handed it). `fetch` must print JSON to stdout (close-runner.sh reads it back for the epic body).
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
if cmd == "ship-walk":
    sys.exit(1 if os.environ.get("STUB_SHIP_WALK_FAIL") else 0)
if cmd == "round-record":
    sys.exit(1 if os.environ.get("STUB_ROUND_RECORD_FAIL") else 0)
if cmd == "crossover":
    sys.exit(1 if os.environ.get("STUB_CROSSOVER_FAIL") else 0)
sys.exit(1)
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
    dev_runner_home = tmp_path / "drhome"

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "ROUND_RECORD_PY": str(rr_py),
        "STUB_TIMELINE": str(tmp_path / "timeline"),
        "STUB_RR_ARGV_LOG": str(tmp_path / "rr_argv_log"),
    }
    if component_root is not None:
        env["CLOSE_COMPONENT_ROOT"] = str(component_root)
    if strategy_doc is not None:
        env["CLOSE_STRATEGY_DOC"] = str(strategy_doc)
    env.update(extra_env or {})
    result = subprocess.run(["bash", str(RUNNER), REPO, EPIC], capture_output=True, text=True,
                            env=env, cwd=str(ROOT), timeout=60)
    return result


# ---- CLOSE_COMPONENT_ROOT unset: a loud, non-fatal stop before the stage even runs --------------------

def test_component_root_unset_stops_before_the_close_walk_stage_runs(tmp_path):
    result = _run(tmp_path, component_root=None)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "CLOSE_COMPONENT_ROOT unset" in result.stderr
    assert _timeline(tmp_path) == ["FETCH"]      # fetch runs unconditionally; the close-walk stage never ran


def test_component_root_unset_still_fetches_but_never_calls_ship_walk(tmp_path):
    # fetch runs unconditionally (round_record.py fetch has no vault dependency); the component-root
    # gate sits strictly between fetch and the close-walk stage.
    result = _run(tmp_path, component_root=None)
    assert result.returncode == 0
    calls = [c[0] for c in _rr_calls(tmp_path)]
    assert calls == ["fetch"]


# ---- the happy path: close-walk, then ship-walk, round-record, crossover, in that order ----------------

def test_close_walk_then_ship_walk_round_record_crossover_run_in_order(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    (component_root / "architecture" / "README.md").write_text("# Living reference\n\n## Build hosts\n\nold text\n")
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("---\n---\n\n```yr-strategy\nthemes = []\n```\n")

    result = _run(tmp_path, component_root=component_root, strategy_doc=strategy_doc)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "CLOSE_WALK", "SHIP_WALK", "ROUND_RECORD", "CROSSOVER"]


def test_ship_walk_is_called_with_the_close_walk_stage_log_and_the_epic_scope(tmp_path):
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


# ---- a ship-walk failure stops SHORT of round-record/crossover — never a partial close -----------------

def test_ship_walk_failure_stops_before_round_record_and_crossover(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root,
                  extra_env={"STUB_SHIP_WALK_FAIL": "1"})
    assert result.returncode == 1
    assert _timeline(tmp_path) == ["FETCH", "CLOSE_WALK", "SHIP_WALK"]


def test_round_record_failure_stops_before_crossover(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("irrelevant — round-record fails first")
    result = _run(tmp_path, component_root=component_root, strategy_doc=strategy_doc,
                  extra_env={"STUB_ROUND_RECORD_FAIL": "1"})
    assert result.returncode == 1
    assert _timeline(tmp_path) == ["FETCH", "CLOSE_WALK", "SHIP_WALK", "ROUND_RECORD"]


# ---- CLOSE_STRATEGY_DOC unset: crossover skipped, but the run still exits 0 (advisory-only) -------------

def test_missing_strategy_doc_skips_crossover_but_still_exits_zero(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    result = _run(tmp_path, component_root=component_root, strategy_doc=None)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "CLOSE_WALK", "SHIP_WALK", "ROUND_RECORD"]
    assert "CLOSE_STRATEGY_DOC unset" in result.stderr


def test_a_crossover_failure_is_non_fatal_the_run_still_exits_zero(tmp_path):
    component_root = tmp_path / "vault-mirror" / "04 projects" / "acme"
    (component_root / "architecture").mkdir(parents=True)
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("some strategy doc")
    result = _run(tmp_path, component_root=component_root, strategy_doc=strategy_doc,
                  extra_env={"STUB_CROSSOVER_FAIL": "1"})
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FETCH", "CLOSE_WALK", "SHIP_WALK", "ROUND_RECORD", "CROSSOVER"]
