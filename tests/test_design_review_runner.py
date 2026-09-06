"""Acceptance tests for tools/design-review-runner.sh — the PM's own review-stage runner (it-36
slice F, #471): fit, arch, activate. Derived from the issue's acceptance criteria, not the
implementation's internals: a stubbed `claude` (no live LLM) and a stubbed `gh` (no live network),
mirroring tests/test_design_runner.py's own style for the sibling drafting runner.

Criteria under test here (the shell-level orchestration; tests/test_design_gate_arch_review.py
covers the underlying design_gate.py functions this script calls out to):
  - the architect's verdict (`VERDICT: fit|refit|block`) and its argued alternative(s) are recorded;
  - a `block` verdict earns exactly ONE fold-and-re-review, never an unbounded loop;
  - `block` after that one fold returns the draft to the triage issue as a flagged pack line and
    stops SHORT of activation — the activation step never even runs;
  - a `fit`/`refit` verdict (immediately, or after the one fold clears it) proceeds past the arch
    gate towards activation.
"""
import pathlib
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "design-review-runner.sh"

sys.path.insert(0, str(ROOT / "tools"))
import ledger  # noqa: E402

REPO = "acme/widgets"
SEED = "foo-seed"

# tools/design-review-runner.sh's own three system prompts each carry a distinguishing phrase
# (FIT_SYS: "fit stage"; ARCH_SYS: "architect stage"; ARCH_FOLD_SYS: "arch-fold stage") — the stub
# classifies on those, never on dev-runner.sh's own REVIEWER/TESTER literals, which these prompts
# never contain. The arch stage's verdict (and the fold's revised draft) come from files this
# helper writes ahead of the run, so a test can script a whole verdict SEQUENCE across the (up to
# two) arch calls without the stub needing its own state machine beyond a call counter.
CLAUDE_STUB = '''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\\n'"$stdin_content"
[ -n "${STUB_CLAUDE_ARGV_LOG:-}" ] && { printf '===STUB-CALL===\\n'; printf '%s\\n' "$@"; printf '%s' "$stdin_content"; printf '\\n===END-STDIN===\\n'; } >> "$STUB_CLAUDE_ARGV_LOG"
case "$args" in
  *"fit stage"*)
    echo FIT >> "$STUB_TIMELINE"
    [ -n "${STUB_FIT_FAIL:-}" ] && exit 1
    echo "some fit findings"
    printf 'VERDICT: %s\\n' "${STUB_FIT_VERDICT:-fit}" ;;
  *"arch-fold stage"*)
    echo ARCH_FOLD >> "$STUB_TIMELINE"
    [ -n "${STUB_ARCH_FOLD_FAIL:-}" ] && exit 1
    echo "ARCH-FOLDED-DRAFT-CONTENT" ;;
  *"architect stage"*)
    n="$(cat "$STUB_ARCH_CALL_COUNT" 2>/dev/null || echo 0)"
    n=$((n + 1))
    echo "$n" > "$STUB_ARCH_CALL_COUNT"
    echo "ARCH$n" >> "$STUB_TIMELINE"
    [ -n "${STUB_ARCH_FAIL:-}" ] && exit 1
    verdict="$(sed -n "${n}p" "$STUB_ARCH_VERDICTS_FILE")"
    echo "some architecture findings"
    echo "ALTERNATIVE: a queue-based design instead"
    printf 'VERDICT: %s\\n' "$verdict" ;;
  *)
    echo UNKNOWN >> "$STUB_TIMELINE"
    exit 1 ;;
esac
exit 0
'''

def _exec(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


# a --body-aware gh stub: logs the FULL argv, one call per line, JSON-encoded so a test can pull the
# --body value back out losslessly (it may itself contain spaces/newlines).
GH_STUB_PY = '''#!/usr/bin/env python3
import json, os, sys
log = os.environ.get("STUB_GH_ARGV_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(0)
'''


def _timeline(tmp):
    p = tmp / "timeline"
    return p.read_text().splitlines() if p.exists() else []


def _gh_calls(tmp):
    import json as _json
    p = tmp / "gh_argv_log"
    if not p.exists():
        return []
    return [_json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _seed_drafting_run(dev_runner_home, repo, *, adversarial_verdict="VERDICT: APPROVE"):
    """The precondition tools/design-runner.sh leaves behind: a completed drafting run dir plus the
    pointer file design-review-runner.sh locates it through. Built directly (not by actually running
    design-runner.sh) — this test's own scope is the REVIEW runner, not the drafting one (already
    covered by tests/test_design_runner.py)."""
    slug = repo.replace("/", "-").replace(".", "-")
    draft_run_dir = dev_runner_home / "runs" / f"design-{slug}-9999"
    draft_run_dir.mkdir(parents=True)
    (draft_run_dir / "draft-final.md").write_text("# Draft\n\nThe drafted design body.\n")
    (draft_run_dir / "adversarial.log").write_text(f"some notes\n{adversarial_verdict}\n")
    pm_dir = dev_runner_home / "pm"
    pm_dir.mkdir(parents=True, exist_ok=True)
    (pm_dir / f"latest-draft-{slug}.txt").write_text(str(draft_run_dir) + "\n")
    return draft_run_dir


def _run(tmp_path, *, arch_verdicts=("fit",), fit_verdict="fit", extra_env=None):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "claude", CLAUDE_STUB)
    _exec(binp / "gh", GH_STUB_PY)

    dev_runner_home = tmp_path / "drhome"
    _seed_drafting_run(dev_runner_home, REPO)

    verdicts_file = tmp_path / "arch_verdicts.txt"
    verdicts_file.write_text("\n".join(arch_verdicts) + "\n")

    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"),
        "GH_BIN": str(binp / "gh"),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "STUB_TIMELINE": str(tmp_path / "timeline"),
        "STUB_CLAUDE_ARGV_LOG": str(tmp_path / "claude_argv_log"),
        "STUB_GH_ARGV_LOG": str(tmp_path / "gh_argv_log"),
        "STUB_ARCH_CALL_COUNT": str(tmp_path / "arch_call_count"),
        "STUB_ARCH_VERDICTS_FILE": str(verdicts_file),
        "STUB_FIT_VERDICT": fit_verdict,
        **(extra_env or {}),
    }
    result = subprocess.run(["bash", str(RUNNER), REPO, SEED], capture_output=True, text=True,
                            env=env, cwd=str(ROOT), timeout=120)
    return result, dev_runner_home


def _review_run_dir_for(dev_runner_home, repo):
    slug = repo.replace("/", "-").replace(".", "-")
    matches = list((dev_runner_home / "runs").glob(f"design-review-{slug}-*"))
    assert len(matches) == 1, f"expected exactly one review run dir for {repo}, found {matches}"
    return matches[0]


# ---- missing drafting run: a loud, early stop -----------------------------------------------------

def test_no_pointer_file_refuses_with_a_clear_message(tmp_path):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True)
    _exec(binp / "claude", CLAUDE_STUB)
    _exec(binp / "gh", GH_STUB_PY)
    dev_runner_home = tmp_path / "drhome"
    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"), "GH_BIN": str(binp / "gh"),
        "DEV_RUNNER_HOME": str(dev_runner_home),
    }
    result = subprocess.run(["bash", str(RUNNER), REPO, SEED], capture_output=True, text=True,
                            env=env, cwd=str(ROOT), timeout=60)
    assert result.returncode == 2
    assert "no drafting run recorded" in result.stderr


# ---- fit + arch: verdict and alternative(s) recorded ------------------------------------------------

def test_fit_and_arch_stages_run_in_order(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("fit",))
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FIT", "ARCH1"]


def test_fit_and_review_verdicts_are_typed_into_the_draft(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("fit",), fit_verdict="refit")
    assert result.returncode == 0, f"stderr={result.stderr}"
    run_dir = _review_run_dir_for(dev_runner_home, REPO)
    draft = (run_dir / "draft-final.md").read_text()
    assert "YR-DESIGN-FIT: who=" in draft
    assert "verdict=refit" in draft
    assert "YR-DESIGN-REVIEW: who=" in draft
    assert "verdict=approve" in draft   # from the drafting run's own adversarial.log VERDICT: APPROVE


def test_adversarial_changes_requested_verdict_is_typed_as_changes_requested(tmp_path):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "claude", CLAUDE_STUB)
    _exec(binp / "gh", GH_STUB_PY)
    dev_runner_home = tmp_path / "drhome"
    _seed_drafting_run(dev_runner_home, REPO, adversarial_verdict="VERDICT: REQUEST CHANGES")
    verdicts_file = tmp_path / "arch_verdicts.txt"
    verdicts_file.write_text("fit\n")
    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"), "GH_BIN": str(binp / "gh"),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "STUB_TIMELINE": str(tmp_path / "timeline"),
        "STUB_CLAUDE_ARGV_LOG": str(tmp_path / "claude_argv_log"),
        "STUB_GH_ARGV_LOG": str(tmp_path / "gh_argv_log"),
        "STUB_ARCH_CALL_COUNT": str(tmp_path / "arch_call_count"),
        "STUB_ARCH_VERDICTS_FILE": str(verdicts_file),
        "STUB_FIT_VERDICT": "fit",
    }
    result = subprocess.run(["bash", str(RUNNER), REPO, SEED], capture_output=True, text=True,
                            env=env, cwd=str(ROOT), timeout=120)
    assert result.returncode == 0, f"stderr={result.stderr}"
    run_dir = _review_run_dir_for(dev_runner_home, REPO)
    assert "verdict=changes-requested" in (run_dir / "draft-final.md").read_text()


def test_arch_result_records_the_argued_alternative(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("fit",))
    assert result.returncode == 0, f"stderr={result.stderr}"
    run_dir = _review_run_dir_for(dev_runner_home, REPO)
    import json
    arch_result = json.loads((run_dir / "arch-result.json").read_text())
    assert arch_result["verdict"] == "fit"
    assert arch_result["alternatives"] == ["a queue-based design instead"]


# ---- block after one fold: flagged back to triage, activation never runs --------------------------

def test_block_then_still_block_folds_exactly_once_and_flags_the_triage_issue(tmp_path):
    result, dev_runner_home = _run(
        tmp_path, arch_verdicts=("block", "block"),
        extra_env={"DESIGN_TRIAGE_ISSUE": "42", "DESIGN_COMPONENT_ROOT": "/should/never/be/used"},
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    # exactly one fold: FIT, ARCH1 (block), ARCH_FOLD, ARCH2 (still block) — then stop.
    assert _timeline(tmp_path) == ["FIT", "ARCH1", "ARCH_FOLD", "ARCH2"]

    gh_calls = _gh_calls(tmp_path)
    comment_calls = [c for c in gh_calls if c[:2] == ["issue", "comment"]]
    assert len(comment_calls) == 1
    body = comment_calls[0][comment_calls[0].index("--body") + 1]
    import design_gate
    assert design_gate.BLOCKED_MARKER in body
    assert SEED in body
    assert "a queue-based design instead" in body

    # activation never ran: the script's own "activate: path=..." log line (emitted right before it
    # invokes `design_gate.py activate`) never fires — a persisted block stops strictly before it,
    # even though DESIGN_COMPONENT_ROOT was deliberately set here to prove that.
    assert "activate: path=" not in result.stderr


def test_block_then_fit_after_the_fold_proceeds_past_the_arch_gate(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("block", "fit"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["FIT", "ARCH1", "ARCH_FOLD", "ARCH2"]
    # no block-flag comment posted — the fold recovered a clean verdict.
    gh_calls = _gh_calls(tmp_path)
    assert not any(c[:2] == ["issue", "comment"] for c in gh_calls)


def test_fold_stage_sees_the_architects_own_findings_and_the_draft(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("block", "fit"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    log = (tmp_path / "claude_argv_log").read_text()
    calls = [c for c in log.split("===STUB-CALL===\n") if c]
    # calls: [fit, arch1, arch-fold, arch2] — arch-fold is the 3rd
    fold_call = calls[2]
    assert "some architecture findings" in fold_call
    assert "a queue-based design instead" in fold_call


def test_block_with_no_triage_issue_set_still_stops_short_of_activation(tmp_path):
    # DESIGN_TRIAGE_ISSUE unset: the runner warns and cannot post the pack line, but must still stop
    # (never fall through to activation) — the flagged-pack POST is best-effort, the STOP is not.
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("block", "block"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "DESIGN_TRIAGE_ISSUE unset" in result.stderr
    assert _timeline(tmp_path) == ["FIT", "ARCH1", "ARCH_FOLD", "ARCH2"]
    gh_calls = _gh_calls(tmp_path)
    assert not any(c[:2] == ["issue", "comment"] for c in gh_calls)


# ---- activation gate: unresolved component root stops short, loudly, never faking a write --------

def test_fit_verdict_with_no_component_root_stops_short_of_activation_loudly(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("fit",))
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert "DESIGN_COMPONENT_ROOT unset" in result.stderr
    assert "stopping short of activation" in result.stderr


def test_fit_verdict_with_component_root_reaches_and_is_refused_by_the_real_engine(tmp_path):
    # DESIGN_COMPONENT_ROOT set: the runner DOES reach activation and asks the real engine
    # (`process.py transition-check design-doc.draft->active.machinery`) — which refuses here
    # because this repo/seed carries no triage-license configuration at all (YR_PM_CONFIG unset,
    # defaulting to a file that does not exist), never because of a bash re-implementation of the
    # guard. The refusal must be loud (non-zero exit) and never fall through to a filesystem write.
    component_root = tmp_path / "vault-component"
    component_root.mkdir()
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("fit",),
                                    extra_env={"DESIGN_COMPONENT_ROOT": str(component_root)})
    assert result.returncode != 0
    assert "activate: path=" in result.stderr
    assert "activation refused or failed" in result.stderr
    run_dir = _review_run_dir_for(dev_runner_home, REPO)
    # the draft in the run dir is untouched — no local mutation stands in for the refused vault write.
    draft = (run_dir / "draft-final.md").read_text()
    assert "YR-ACCEPT" not in draft


# ---- ledger: fit/arch(/arch-fold) each leave their own row --------------------------------------------

def test_each_review_stage_leaves_its_own_ledger_row(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("block", "fit"))
    assert result.returncode == 0, f"stderr={result.stderr}"
    rows = ledger.load_rows(str(dev_runner_home / "ledger"))
    stages = [r.get("stage") for r in rows]
    assert stages == ["fit", "arch", "arch-fold", "arch"]
    for r in rows:
        assert r.get("kind") == "design"
        assert r.get("task") == f"{REPO}#{SEED}"


def test_a_failed_fit_stage_stops_before_any_arch_call(tmp_path):
    result, dev_runner_home = _run(tmp_path, arch_verdicts=("fit",), extra_env={"STUB_FIT_FAIL": "1"})
    assert result.returncode != 0
    assert _timeline(tmp_path) == ["FIT"]
