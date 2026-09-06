"""Acceptance tests for tools/design-runner.sh — the PM's own stage runner (it-36 slice E, #470):
product, adversarial, fold — three cold `claude -p` stages, sequenced, each leaving its own row in
the PM instance's ledger (kind: design). Stubbed `claude`, no live LLM and no network — mirrors
tests/test_dev_runner.py's own stubbed-CLI style, with a fake tailored to this runner's own three
system prompts (which carry none of dev-runner.sh's REVIEWER/TESTER routing literals).
"""
import json
import pathlib
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "design-runner.sh"

sys.path.insert(0, str(ROOT / "tools"))
import ledger  # noqa: E402

# design-runner.sh's own three system prompts each carry a distinguishing, non-overlapping phrase
# (tools/design-runner.sh: PRODUCT_SYS/ADVERSARIAL_SYS/FOLD_SYS) — the fake classifies on those,
# never on dev-runner.sh's REVIEWER/TESTER literals, which this runner's prompts never contain.
CLAUDE_STUB = '''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\\n'"$stdin_content"
[ -n "${STUB_CLAUDE_ARGV_LOG:-}" ] && { printf '===STUB-CALL===\\n'; printf '%s\\n' "$@"; printf '%s' "$stdin_content"; printf '\\n===END-STDIN===\\n'; } >> "$STUB_CLAUDE_ARGV_LOG"
case "$args" in
  *"product stage"*)
    echo PRODUCT >> "$STUB_TIMELINE"
    [ -n "${STUB_PRODUCT_FAIL:-}" ] && exit 1
    echo "PRODUCT-DRAFT-CONTENT" ;;
  *"adversarial reviewer"*)
    echo ADVERSARIAL >> "$STUB_TIMELINE"
    [ -n "${STUB_ADVERSARIAL_FAIL:-}" ] && exit 1
    echo "some adversarial notes"
    echo "VERDICT: APPROVE" ;;
  *"fold stage"*)
    echo FOLD >> "$STUB_TIMELINE"
    [ -n "${STUB_FOLD_FAIL:-}" ] && exit 1
    echo "FINAL-DRAFT-CONTENT" ;;
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


def _timeline(tmp):
    p = tmp / "timeline"
    return p.read_text().splitlines() if p.exists() else []


def _run(repo, seed, tmp_path, *, extra_env=None):
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    _exec(binp / "claude", CLAUDE_STUB)
    seed_doc = tmp_path / "seed.md"
    seed_doc.write_text(f"# seed: {seed}\nsome seed body text\n")
    strategy_doc = tmp_path / "strategy.md"
    strategy_doc.write_text("# strategy\nsome strategy body text\n")
    dev_runner_home = tmp_path / "drhome"
    env = {
        **{k: v for k, v in __import__("os").environ.items()},
        "CLAUDE_BIN": str(binp / "claude"),
        "DEV_RUNNER_HOME": str(dev_runner_home),
        "DESIGN_SEED_DOC": str(seed_doc),
        "DESIGN_STRATEGY_DOC": str(strategy_doc),
        "STUB_TIMELINE": str(tmp_path / "timeline"),
        "STUB_CLAUDE_ARGV_LOG": str(tmp_path / "claude_argv_log"),
        **(extra_env or {}),
    }
    result = subprocess.run(["bash", str(RUNNER), repo, seed], capture_output=True, text=True,
                            env=env, cwd=str(ROOT), timeout=60)
    return result, dev_runner_home


def _run_dir_for(dev_runner_home, repo):
    slug = repo.replace("/", "-").replace(".", "-")
    matches = list((dev_runner_home / "runs").glob(f"design-{slug}-*"))
    assert len(matches) == 1, f"expected exactly one run dir for {repo}, found {matches}"
    return matches[0]


def _ledger_rows(dev_runner_home):
    return ledger.load_rows(str(dev_runner_home / "ledger"))


REPO = "acme/widgets"
SEED = "foo-seed"


def test_stages_run_in_order_product_then_adversarial_then_fold(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert _timeline(tmp_path) == ["PRODUCT", "ADVERSARIAL", "FOLD"]


def test_product_stage_input_carries_the_seed_and_strategy_and_template(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    log = (tmp_path / "claude_argv_log").read_text()
    calls = [c for c in log.split("===STUB-CALL===\n") if c]
    product_call = calls[0]
    assert SEED in product_call
    assert "some seed body text" in product_call
    assert "some strategy body text" in product_call


def test_draft_and_final_draft_land_in_the_run_dir(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    run_dir = _run_dir_for(dev_runner_home, REPO)
    assert (run_dir / "draft.md").read_text().strip() == "PRODUCT-DRAFT-CONTENT"
    assert (run_dir / "draft-final.md").read_text().strip() == "FINAL-DRAFT-CONTENT"


def test_adversarial_stage_sees_the_product_draft_and_ends_with_a_verdict_line(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    log = (tmp_path / "claude_argv_log").read_text()
    calls = [c for c in log.split("===STUB-CALL===\n") if c]
    adversarial_call = calls[1]
    assert "PRODUCT-DRAFT-CONTENT" in adversarial_call        # the draft travels into the adversarial stage
    run_dir = _run_dir_for(dev_runner_home, REPO)
    assert "VERDICT: APPROVE" in (run_dir / "adversarial.log").read_text()


def test_fold_stage_sees_both_the_draft_and_the_adversarial_review(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    log = (tmp_path / "claude_argv_log").read_text()
    calls = [c for c in log.split("===STUB-CALL===\n") if c]
    fold_call = calls[2]
    assert "PRODUCT-DRAFT-CONTENT" in fold_call
    assert "VERDICT: APPROVE" in fold_call


# ---- the ledger: one row per stage, kind=design, the run's own id ---------------------------------------

def test_each_stage_leaves_its_own_ledger_row_kind_design(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    rows = _ledger_rows(dev_runner_home)
    assert len(rows) == 3
    stages = [r.get("stage") for r in rows]
    assert stages == ["product", "adversarial", "fold"]
    for r in rows:
        assert r.get("kind") == "design"
        assert r.get("repo") == REPO
        assert r.get("task") == f"{REPO}#{SEED}"
        assert r.get("schema") == ledger.ROW_SCHEMA


def test_every_stage_row_shares_the_same_run_id(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    rows = _ledger_rows(dev_runner_home)
    run_ids = {r.get("run_id") for r in rows}
    assert len(run_ids) == 1
    (run_id,) = run_ids
    assert run_id.startswith("design-acme-widgets-")


def test_ledger_row_run_id_matches_the_actual_run_dir(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path)
    assert result.returncode == 0, f"stderr={result.stderr}"
    run_dir = _run_dir_for(dev_runner_home, REPO)
    rows = _ledger_rows(dev_runner_home)
    assert all(r.get("run_id") == run_dir.name for r in rows)


def test_a_failed_stage_stops_the_pipeline_and_only_that_far_is_ledgered(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path, extra_env={"STUB_ADVERSARIAL_FAIL": "1"})
    assert result.returncode != 0
    assert _timeline(tmp_path) == ["PRODUCT", "ADVERSARIAL"]     # fold never ran
    rows = _ledger_rows(dev_runner_home)
    stages = [r.get("stage") for r in rows]
    assert stages == ["product", "adversarial"]
    outcomes = [((r.get("outcome") or {}).get("type")) for r in rows]
    assert outcomes == ["ok", "failed"]


def test_product_stage_failure_ledgers_nothing_past_it(tmp_path):
    result, dev_runner_home = _run(REPO, SEED, tmp_path, extra_env={"STUB_PRODUCT_FAIL": "1"})
    assert result.returncode != 0
    assert _timeline(tmp_path) == ["PRODUCT"]
    rows = _ledger_rows(dev_runner_home)
    assert [r.get("stage") for r in rows] == ["product"]
    assert (rows[0].get("outcome") or {}).get("type") == "failed"
