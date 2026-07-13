"""Tests for issue #139 — registry: rank_check admits an equal-rank pair (the reviewer is never weaker).

Derived from the issue #139 acceptance criteria (the spec), not from the implementation's internals:
  * every surface that states the rank-gate contract in prose must state the NEW contract
    ("review-rank >= build-rank — the reviewer is never weaker"), not the old strict form
    ("review-rank > build-rank" / "strictly outranks");
  * the runner and merge-evaluator unit tests (tools.registry.rank_check, tests/test_merge_shadow.py)
    cover the behavioural half of this issue — this file is the documentation/prose half plus one
    full end-to-end proof that an equal-rank pair auto-merges through the real runner.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

REGISTRY_PY = (ROOT / "tools" / "registry.py").read_text(encoding="utf-8")
DEV_RUNNER_SH = (ROOT / "tools" / "dev-runner.sh").read_text(encoding="utf-8")
MERGE_SHADOW_PY = (ROOT / "tools" / "merge_shadow.py").read_text(encoding="utf-8")
GATES_MD = (ROOT / "skills" / "factory" / "references" / "gates.md").read_text(encoding="utf-8")
CLOSING_MD = (ROOT / "skills" / "factory" / "references" / "closing.md").read_text(encoding="utf-8")

# The old strict form the issue says every surface must stop stating.
OLD_STRICT_PHRASES = ("strict review>build", "strict review > build", "review.rank > build.rank")


def _no_old_strict_phrasing(text):
    lowered = text.lower()
    return all(p.lower() not in lowered for p in OLD_STRICT_PHRASES)


# ---------------------------------------------------------------------------
# tools/registry.py — rank_check() docstring (issue text: tools/registry.py:45-47)
# ---------------------------------------------------------------------------

def test_registry_rank_check_docstring_states_ge_not_strict_gt():
    assert "review.rank >= build.rank" in REGISTRY_PY
    assert _no_old_strict_phrasing(REGISTRY_PY)


# ---------------------------------------------------------------------------
# tools/dev-runner.sh — the rank_gate comment (issue text: tools/dev-runner.sh:189-191)
# ---------------------------------------------------------------------------

def test_dev_runner_rank_gate_comment_states_ge_not_strict_gt():
    assert "review-rank >= build-rank" in DEV_RUNNER_SH
    assert _no_old_strict_phrasing(DEV_RUNNER_SH)


def test_dev_runner_shadow_rank_gate_uses_ge_comparison():
    """The predicate itself: shadow_rank_gate must compare with -ge, never -gt."""
    assert '"$REVIEW_RANK" -ge "$BUILD_RANK"' in DEV_RUNNER_SH
    assert '"$REVIEW_RANK" -gt "$BUILD_RANK"' not in DEV_RUNNER_SH


# ---------------------------------------------------------------------------
# tools/merge_shadow.py — the evaluator's header line (issue text: tools/merge_shadow.py:18)
# ---------------------------------------------------------------------------

def test_merge_shadow_header_states_ge_not_strict_gt():
    assert "review-rank >= build-rank" in MERGE_SHADOW_PY
    assert _no_old_strict_phrasing(MERGE_SHADOW_PY)


# ---------------------------------------------------------------------------
# skills/factory/references/gates.md and closing.md (issue text: gates.md:18, closing.md:33)
# ---------------------------------------------------------------------------

def test_gates_md_states_ge_not_strict_gt():
    assert "review-rank >= build-rank" in GATES_MD
    assert _no_old_strict_phrasing(GATES_MD)


def test_closing_md_states_ge_not_strict_gt():
    assert "review-rank >= build-rank" in CLOSING_MD
    assert _no_old_strict_phrasing(CLOSING_MD)


# ---------------------------------------------------------------------------
# End-to-end: an equal-rank same-provider pair auto-merges through the real (stubbed) runner
# ---------------------------------------------------------------------------

import test_autonomous_merge as tam  # noqa: E402  (reuses the armed-merge stub harness)


def test_armed_equal_rank_pair_auto_merges(tmp_path):
    """A `model: opus` / `review_model: opus` pair (same provider, both rank 40) is EQUAL-rank: it
    clears intake (already true before this issue) AND now clears the merge evaluator's rank_gate
    (issue #139's relaxation), so an armed repo squash-merges it exactly like the default sonnet/opus
    pair — no BLOCKED on rank_gate."""
    work, origin = tam.td._make_repo(tmp_path)
    binp = tmp_path / "bin"
    tam._stubs(binp)
    env = tam._armed_env(
        tmp_path, binp, work, origin, prs=tam._complete_prs(),
        body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: opus\n",
    )
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert tam._merged_stub(tmp_path), "an equal-rank pair must still auto-merge, not block on rank_gate"
    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == "YR-MERGE: MERGED"
    rec = tam._block(body)
    assert rec["decision"] == "MERGED"
    assert rec["build"]["rank"] == 40 and rec["review"]["rank"] == 40   # equal rank, both opus
    assert rec["failed_condition"] is None


def test_armed_review_weaker_than_build_still_bounces_before_merge(tmp_path):
    """The other side of issue #139: a ranked pair where review is strictly WEAKER than build must
    keep failing exactly as before — bounced to Needs-info at intake (it never even reaches the
    merge evaluator), so the factory never merges it."""
    work, origin = tam.td._make_repo(tmp_path)
    binp = tmp_path / "bin"
    tam._stubs(binp)
    env = tam._armed_env(
        tmp_path, binp, work, origin, prs=tam._complete_prs(),
        body="### Acceptance criteria\n- [ ] x\n\nmodel: opus\nreview_model: sonnet\n",
    )
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 3
    assert not tam._merged_stub(tmp_path)
    assert tam._merge_record(tmp_path) is None
    tl = tam.td._timeline(tmp_path)
    edits = " ".join(tam.td._edits(tl))
    assert "Backlog" in edits and "NeedsInfo" in edits
