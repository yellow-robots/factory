"""Acceptance tests for issue #36 — assemble a hashed review bundle and feed it to the reviewer.

Derived from the CRITERIA (the spec), not the runner's internals. Reuses the stubbed harness in
tests/test_dev_runner.py (the stage-aware `gh`/`claude`/check stubs and the real-git happy-path
helpers) to drive tools/dev-runner.sh end-to-end and inspect the review-bundle.json artifact it
writes to the run directory.

Covered criteria:
  * before the review stage, a pre-review bundle is assembled: staged diff (base+head SHAs),
    acceptance-criteria block, check gate command/exit/output-tail, resolved build/review entries
    with ranks;
  * that pre-review bundle is handed to the reviewer stage as its input (its path is in the
    reviewer's prompt, and at that moment the file already holds the pre-review subset with no
    verdict rounds yet);
  * each review round's verdict is appended to the bundle as it lands;
  * a sha256 is computed over the completed bundle at decision time;
  * the bundle is written to the run directory as a single artifact;
  * canonical serialization makes the hash reproducible for identical inputs.

Runs under `.venv/bin/python -m pytest tests/ -q` (system python3 works too — no third-party deps).
"""
import hashlib
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as base  # the shared stub harness (gh/claude/check stubs + helpers)
import claude_fake  # tests/harness/claude_fake.py — the classifier's one legal home

ROOT = base.ROOT


def _bundle_paths(tmp_path, issue, drhome="drhome"):
    return sorted((tmp_path / drhome / "runs").glob(f"{issue}-*/review-bundle.json"))


def _read_bundle(tmp_path, issue, drhome="drhome"):
    paths = _bundle_paths(tmp_path, issue, drhome)
    assert paths, f"no review-bundle.json found for issue #{issue} under {drhome}/runs"
    return json.loads(paths[0].read_text())


# ---------------------------------------------------------------------------
# A claude stub that snapshots the bundle file's content the moment the REVIEWER stage is
# launched — proving the reviewer is handed the pre-review subset (no verdict rounds yet) rather
# than deriving it itself. DERIVED from the shared classifier (tests/harness/claude_fake.CLAUDE_STUB)
# via .replace(): the snapshot capture is spliced in at the top of the REVIEWER arm, located by its
# exact opening text, never by retyping the classification patterns.
# ---------------------------------------------------------------------------
_BASE_REVIEWER_ARM_HEAD = '  *REVIEWER*)            echo REVIEW >> "$STUB_TIMELINE"'

_SNAPSHOT_REVIEWER_ARM_HEAD = r'''  *REVIEWER*)
    bpath="$(printf '%s' "$args" | grep -oE '[^[:space:]]*review-bundle\.json' | head -n1)"
    if [ -n "$bpath" ] && [ -f "$bpath" ] && [ -n "${STUB_REVIEWER_SNAPSHOT:-}" ]; then
      cp "$bpath" "$STUB_REVIEWER_SNAPSHOT"
    fi
                        echo REVIEW >> "$STUB_TIMELINE"'''

SNAPSHOT_CLAUDE_STUB = claude_fake.CLAUDE_STUB.replace(_BASE_REVIEWER_ARM_HEAD, _SNAPSHOT_REVIEWER_ARM_HEAD, 1)


def _snapshot_stubs(binp):
    binp.mkdir(parents=True, exist_ok=True)
    base._exec(binp / "gh", base.GH_STUB)
    base._exec(binp / "claude", SNAPSHOT_CLAUDE_STUB)
    base._exec(binp / "check.sh", base.CHECK_STUB)


# ============ pre-review bundle: assembled before the review stage, single artifact ============

def test_bundle_written_to_run_dir_as_single_artifact(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Bundle artifact"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    paths = _bundle_paths(tmp_path, 5)
    assert len(paths) == 1                            # exactly one bundle artifact for the run


def test_bundle_diff_has_base_and_head_sha_and_patch_content(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Diff shas"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    diff = bundle["diff"]
    assert diff["base_sha"] and isinstance(diff["base_sha"], str)
    assert diff["head_sha"] and isinstance(diff["head_sha"], str)
    assert diff["base_sha"] != diff["head_sha"]        # base and head are distinct points
    assert "feature.txt" in diff["patch"]              # the actual staged diff content


def test_bundle_acceptance_criteria_matches_issue_body(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    ac_body = "### Acceptance criteria\n- [ ] the widget spins\n- [ ] the widget stops\n"
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="AC block", body=ac_body), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    assert "the widget spins" in bundle["acceptance_criteria"]
    assert "the widget stops" in bundle["acceptance_criteria"]


def test_bundle_check_section_reflects_check_gate_command_exit_and_output(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Check content"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_CMD"] = "printf 'ALPHA\\nBETA\\n'"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    check = bundle["check"]
    assert check["command"] == "printf 'ALPHA\\nBETA\\n'"
    assert check["exit_code"] == 0
    assert "ALPHA" in check["output_tail"] and "BETA" in check["output_tail"]


def test_bundle_check_output_tail_is_truncated_to_the_tail(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Long check output"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    # 100 lines of check output; only the tail should survive into the bundle.
    env["CHECK_CMD"] = "python3 -c \"[print('L%d' % i) for i in range(1, 101)]\""
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    tail_lines = bundle["check"]["output_tail"].splitlines()
    assert "L1" not in tail_lines                      # early lines dropped
    assert tail_lines[-1] == "L100"                     # the last line survives


def test_bundle_has_resolved_build_and_review_entries_with_ranks(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Resolved pair"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    # registry defaults (models.toml): build=sonnet(rank 30), review=opus(rank 40), both anthropic.
    assert bundle["build"]["name"] == "sonnet" and bundle["build"]["rank"] == 30
    assert bundle["build"]["provider"] == "anthropic" and bundle["build"]["ranked"] is True
    assert bundle["review"]["name"] == "opus" and bundle["review"]["rank"] == 40
    assert bundle["review"]["provider"] == "anthropic" and bundle["review"]["ranked"] is True


def test_bundle_resolved_pair_reflects_task_body_model_overrides(tmp_path):
    """An equal-rank override pair (`model:`/`review_model:` both opus) is a legal pair and must show
    up in the bundle's resolved entries — proving the bundle names the ACTUAL resolved roles, not a
    hardcoded default."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    body = "### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: opus\n"
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Override pair", body=body), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    assert bundle["build"]["name"] == "opus" and bundle["build"]["rank"] == 40
    assert bundle["review"]["name"] == "opus" and bundle["review"]["rank"] == 40


# ============ the pre-review bundle is fed to the reviewer as its input ============

def test_reviewer_prompt_contains_the_bundle_path(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Reviewer input"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle_path = _bundle_paths(tmp_path, 5)[0]
    # the happy path's LAST claude invocation is the reviewer (implement -> test -> check -> review), so
    # claude_stdin (overwritten per call) holds the reviewer's stdin here — the bundle path travels in
    # the task prompt (issue #121: stdin, never argv).
    stdin_text = (tmp_path / "claude_stdin").read_text()
    assert str(bundle_path) in stdin_text


def test_reviewer_receives_bundle_before_any_verdict_recorded(tmp_path):
    """At the moment the reviewer stage is launched, the bundle on disk already holds the pre-review
    subset (diff/AC/check/resolved pair) with NO verdict rounds yet and no decision-time hash — the
    reviewer is handed the bundle as INPUT, not asked to help build it."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; _snapshot_stubs(binp)
    snapshot = tmp_path / "bundle_seen_by_reviewer.json"
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Snapshot"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEWER_SNAPSHOT": str(snapshot)})
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert snapshot.is_file(), "the reviewer was never handed a path to an existing bundle file"
    seen = json.loads(snapshot.read_text())
    assert seen["rounds"] == []
    assert "sha256" not in seen
    assert "diff" in seen and "acceptance_criteria" in seen and "check" in seen
    assert "build" in seen and "review" in seen


# ============ each review round's verdict is appended as it lands ============

def test_bundle_records_single_round_on_first_time_approve(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="One round"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    assert [rd["verdict"] for rd in bundle["rounds"]] == ["VERDICT: APPROVE"]


def test_bundle_accumulates_verdicts_across_a_review_repair_round(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Two rounds"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1"})  # blocked once, approved after repair
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    assert [rd["verdict"] for rd in bundle["rounds"]] == ["VERDICT: REQUEST_CHANGES", "VERDICT: APPROVE"]
    assert [rd["index"] for rd in bundle["rounds"]] == [1, 2]


def test_bundle_still_records_the_blocking_round_even_when_unfixable(tmp_path):
    """Even when the run ultimately fails closed (Blocked), the bundle on disk still shows the
    request-changes round that landed before the failure — the append happens as each round lands."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Unfixable"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEW_NOFIX": "1"})
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    bundle = _read_bundle(tmp_path, 5)
    assert [rd["verdict"] for rd in bundle["rounds"]] == ["VERDICT: REQUEST_CHANGES", "VERDICT: REQUEST_CHANGES"]


# ============ decision-time sha256 + canonical, reproducible serialization ============

def test_bundle_sha256_matches_recomputed_canonical_digest(tmp_path):
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Hash check"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    bundle = _read_bundle(tmp_path, 5)
    assert "sha256" in bundle and len(bundle["sha256"]) == 64
    without_hash = {k: v for k, v in bundle.items() if k != "sha256"}
    expected = hashlib.sha256(
        json.dumps(without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert bundle["sha256"] == expected


def test_bundle_hash_reproducible_across_independent_runs_with_identical_inputs(tmp_path):
    """Two independent runs against the same base repo state, issue content, and stub behaviour
    produce byte-identical bundle contents and therefore identical decision-time hashes — the point
    of canonical serialization."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)

    env1 = base._real(tmp_path, base._env(tmp_path, binp, number=11, title="Reproducible"), work)
    env1["DEV_RUNNER_HOME"] = str(tmp_path / "drhome1")
    env1["STUB_CLAUDE_CHANGE"] = "1"
    r1 = base._run(["11", "--repo", "test/repo"], env1)
    assert r1.returncode == 0, r1.stderr

    env2 = base._real(tmp_path, base._env(tmp_path, binp, number=12, title="Reproducible"), work)
    env2["DEV_RUNNER_HOME"] = str(tmp_path / "drhome2")
    env2["STUB_CLAUDE_CHANGE"] = "1"
    r2 = base._run(["12", "--repo", "test/repo"], env2)
    assert r2.returncode == 0, r2.stderr

    b1 = _read_bundle(tmp_path, 11, drhome="drhome1")
    b2 = _read_bundle(tmp_path, 12, drhome="drhome2")
    assert b1["sha256"] == b2["sha256"]
