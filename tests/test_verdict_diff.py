"""Acceptance tests for issue #166 — verdict-diff: per-round agreement record, adjudicable on
disagreement (slice E of epic #161).

Derived from the CRITERIA (the spec), NOT tools/verdict_diff.py's internals:

  * tools/verdict_diff.py pairs each gating round's review transcript (tools/review_bundle.py's
    `rounds` list) with its OWN shadow-review.md/-N.md in a run dir, and emits one
    `yr-verdict-diff/1` record per pair: {round, gating, shadow, agree} — both verdicts extracted by
    the SAME exact-match grammar (line-anchored `VERDICT:`, last line wins, trailing whitespace
    stripped) that tools/review_bundle.py / tools/dev-runner.sh already use;
  * WHEN the verdicts disagree, the record carries both transcripts' findings;
  * WHEN a round has no shadow record, nothing is emitted for it — never a synthesized disagreement;
  * tools/dev-runner.sh lands one YR-VERDICT-DIFF PR comment per pair (field lines + blockquoted
    excerpts; no line matches the line-anchored gating token `^VERDICT:`) and keeps the record file
    in the run dir;
  * a repair build (two gating rounds) pairs round 2 with its OWN shadow round, not round 1's;
  * merge outcome is not written by this slice, and the feature is a complete no-op when no shadow
    round ran (dark shadow seat, issue #165).

Two layers:
  1. unit tests against tools/verdict_diff.py's public functions and its `run` CLI, using
     tools/review_bundle.py to build realistic bundles (the same shape the runner produces);
  2. integration tests driving tools/dev-runner.sh end-to-end through the stubbed harness shared
     with tests/test_shadow_review.py (shadow seat armed), proving the PR-comment + record-file
     behaviour the runner itself is responsible for.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tools import review_bundle
from tools.review_bundle import append_round, build_bundle, finalize
from tools import verdict_diff
from tools.verdict_diff import (
    build_records, comment_path, extract_verdict, record_path, render_comment,
    shadow_path_for_round,
)

import test_dev_runner as base
import test_shadow_review as shadow

VERDICT_DIFF_PY = ROOT / "tools" / "verdict_diff.py"

VERDICT_ANCHOR = re.compile(r"^VERDICT:", re.MULTILINE)


def _bundle_sample():
    return dict(
        base_sha="base123", head_sha="head456", diff="diff --git a/x b/x\n+hi\n",
        acceptance_criteria="- [ ] it works\n", check_cmd="pytest -q", check_exit=0,
        checks_log="1 passed\n", build_entry={"name": "sonnet", "rank": 30},
        review_entry={"name": "opus", "rank": 40},
    )


# ---------------------------------------------------------------------------
# extract_verdict — the shared exact-match grammar
# ---------------------------------------------------------------------------

def test_extract_verdict_last_line_wins_trailing_whitespace_stripped():
    text = "some prose\nVERDICT: REQUEST_CHANGES\nmore prose\nVERDICT: APPROVE   \n"
    assert extract_verdict(text) == "APPROVE"


def test_extract_verdict_line_must_be_anchored_at_column_zero():
    text = "the reviewer wrote  VERDICT: APPROVE inline, which must not count\n"
    assert extract_verdict(text) is None


def test_extract_verdict_case_sensitive():
    text = "verdict: approve\n"
    assert extract_verdict(text) is None


def test_extract_verdict_no_verdict_line_returns_none():
    assert extract_verdict("the reviewer crashed before saying anything") is None


def test_extract_verdict_single_clean_line():
    assert extract_verdict("no blockers found\nVERDICT: APPROVE\n") == "APPROVE"


# ---------------------------------------------------------------------------
# build_records — pairing + agreement + findings-on-disagreement
# ---------------------------------------------------------------------------

def test_build_records_agreeing_pair_marks_agree_true_and_omits_transcripts(tmp_path):
    bundle = build_bundle(**_bundle_sample())
    append_round(bundle, "no blockers\nVERDICT: APPROVE\n")
    (tmp_path / "shadow-review.md").write_text("shadow agrees\nVERDICT: APPROVE\n")

    records = build_records(tmp_path, bundle)
    assert len(records) == 1
    r = records[0]
    assert r["round"] == 1 and r["gating"] == "APPROVE" and r["shadow"] == "APPROVE"
    assert r["agree"] is True
    assert "gating_transcript" not in r and "shadow_transcript" not in r
    assert r["schema"] == "yr-verdict-diff/1"


def test_build_records_disagreeing_pair_marks_agree_false_and_carries_both_transcripts(tmp_path):
    bundle = build_bundle(**_bundle_sample())
    gating_transcript = "found a blocker\nVERDICT: REQUEST_CHANGES\n"
    shadow_transcript = "looks fine to me\nVERDICT: APPROVE\n"
    append_round(bundle, gating_transcript)
    (tmp_path / "shadow-review.md").write_text(shadow_transcript)

    records = build_records(tmp_path, bundle)
    assert len(records) == 1
    r = records[0]
    assert r["gating"] == "REQUEST_CHANGES" and r["shadow"] == "APPROVE"
    assert r["agree"] is False
    assert r["gating_transcript"] == gating_transcript
    assert r["shadow_transcript"] == shadow_transcript


def test_build_records_round_with_no_shadow_file_emits_nothing(tmp_path):
    """A round with no shadow record at all -> no record, never a synthesized disagreement."""
    bundle = build_bundle(**_bundle_sample())
    append_round(bundle, "no blockers\nVERDICT: APPROVE\n")
    # no shadow-review.md written for this run dir at all

    records = build_records(tmp_path, bundle)
    assert records == []


def test_build_records_mixed_only_the_round_with_a_shadow_file_is_emitted(tmp_path):
    """Two gating rounds; only round 2 has a shadow file -> exactly one record, for round 2."""
    bundle = build_bundle(**_bundle_sample())
    append_round(bundle, "blockers found\nVERDICT: REQUEST_CHANGES\n")
    append_round(bundle, "fixed now\nVERDICT: APPROVE\n")
    (tmp_path / "shadow-review-2.md").write_text("agrees\nVERDICT: APPROVE\n")

    records = build_records(tmp_path, bundle)
    assert len(records) == 1
    assert records[0]["round"] == 2


def test_build_records_repair_build_pairs_each_round_with_its_own_shadow(tmp_path):
    """A repair build: two gating rounds, two shadow rounds, DIFFERENT verdicts on each side ->
    round 1 pairs with shadow-review.md, round 2 pairs with shadow-review-2.md — never crossed."""
    bundle = build_bundle(**_bundle_sample())
    append_round(bundle, "found a blocker\nVERDICT: REQUEST_CHANGES\n")
    append_round(bundle, "fixed\nVERDICT: APPROVE\n")
    (tmp_path / "shadow-review.md").write_text("round1 shadow says fine\nVERDICT: APPROVE\n")
    (tmp_path / "shadow-review-2.md").write_text("round2 shadow disagrees\nVERDICT: REQUEST_CHANGES\n")

    records = build_records(tmp_path, bundle)
    assert [r["round"] for r in records] == [1, 2]

    r1, r2 = records
    assert r1["gating"] == "REQUEST_CHANGES" and r1["shadow"] == "APPROVE" and r1["agree"] is False
    assert r2["gating"] == "APPROVE" and r2["shadow"] == "REQUEST_CHANGES" and r2["agree"] is False
    # each round's shadow transcript is its OWN file's content, never the other round's
    assert "round1 shadow" in r1["shadow_transcript"]
    assert "round2 shadow" in r2["shadow_transcript"]


def test_shadow_path_for_round_matches_dev_runner_suffix_pattern(tmp_path):
    assert shadow_path_for_round(tmp_path, 1) == tmp_path / "shadow-review.md"
    assert shadow_path_for_round(tmp_path, 2) == tmp_path / "shadow-review-2.md"
    assert shadow_path_for_round(tmp_path, 3) == tmp_path / "shadow-review-3.md"


# ---------------------------------------------------------------------------
# render_comment — inert on the trail: field lines + blockquoted excerpts, never a gating VERDICT: line
# ---------------------------------------------------------------------------

def test_render_comment_agree_has_no_line_matching_the_gating_anchor():
    record = {"round": 1, "gating": "APPROVE", "shadow": "APPROVE", "agree": True}
    comment = render_comment(record)
    assert VERDICT_ANCHOR.search(comment) is None
    assert comment.splitlines()[0] == "YR-VERDICT-DIFF: agree"
    assert "round: 1" in comment and "gating: APPROVE" in comment and "shadow: APPROVE" in comment
    assert "agree: true" in comment


def test_render_comment_disagree_has_no_line_matching_the_gating_anchor_and_blockquotes_both_transcripts():
    record = {
        "round": 1, "gating": "REQUEST_CHANGES", "shadow": "APPROVE", "agree": False,
        "gating_transcript": "found a blocker\nVERDICT: REQUEST_CHANGES\n",
        "shadow_transcript": "looks fine\nVERDICT: APPROVE\n",
    }
    comment = render_comment(record)
    assert VERDICT_ANCHOR.search(comment) is None
    assert comment.splitlines()[0] == "YR-VERDICT-DIFF: disagree"
    assert "agree: false" in comment
    # both transcripts' findings survive, blockquoted (so the anchor never lines up at column 0)
    assert "> found a blocker" in comment
    assert "> VERDICT: REQUEST_CHANGES" in comment
    assert "> looks fine" in comment
    assert "> VERDICT: APPROVE" in comment


# ---------------------------------------------------------------------------
# CLI (`run`) — the entry point tools/dev-runner.sh shells out to
# ---------------------------------------------------------------------------

def _write_bundle(path, rounds):
    bundle = build_bundle(**_bundle_sample())
    for transcript in rounds:
        append_round(bundle, transcript)
    path.write_text(json.dumps(finalize(bundle)))


def test_cli_run_writes_record_and_comment_files_and_prints_comment_paths(tmp_path):
    bundle_path = tmp_path / "review-bundle.json"
    _write_bundle(bundle_path, ["no blockers\nVERDICT: APPROVE\n"])
    (tmp_path / "shadow-review.md").write_text("agrees\nVERDICT: APPROVE\n")

    r = subprocess.run([sys.executable, str(VERDICT_DIFF_PY), "run",
                         "--run-dir", str(tmp_path), "--bundle", str(bundle_path)],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    printed = [line for line in r.stdout.splitlines() if line.strip()]
    assert len(printed) == 1
    comment_file = pathlib.Path(printed[0])
    assert comment_file == tmp_path / "verdict-diff-comment.md"
    assert comment_file.is_file()
    assert VERDICT_ANCHOR.search(comment_file.read_text()) is None

    record_file = tmp_path / "verdict-diff.json"
    assert record_file.is_file()
    data = json.loads(record_file.read_text())
    assert data == {"schema": "yr-verdict-diff/1", "round": 1, "gating": "APPROVE",
                     "shadow": "APPROVE", "agree": True}


def test_cli_run_no_bundle_file_is_a_silent_noop(tmp_path):
    r = subprocess.run([sys.executable, str(VERDICT_DIFF_PY), "run",
                         "--run-dir", str(tmp_path), "--bundle", str(tmp_path / "missing.json")],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""
    assert not list(tmp_path.glob("verdict-diff*"))


def test_cli_run_round_without_shadow_emits_no_files_for_that_round(tmp_path):
    bundle_path = tmp_path / "review-bundle.json"
    _write_bundle(bundle_path, ["blockers found\nVERDICT: REQUEST_CHANGES\n", "fixed\nVERDICT: APPROVE\n"])
    # only round 2 gets a shadow file
    (tmp_path / "shadow-review-2.md").write_text("agrees\nVERDICT: APPROVE\n")

    r = subprocess.run([sys.executable, str(VERDICT_DIFF_PY), "run",
                         "--run-dir", str(tmp_path), "--bundle", str(bundle_path)],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "verdict-diff.json").exists()          # round 1: no shadow -> nothing
    assert not (tmp_path / "verdict-diff-comment.md").exists()
    assert (tmp_path / "verdict-diff-2.json").exists()             # round 2: shadow present -> emitted
    assert (tmp_path / "verdict-diff-2-comment.md").exists()


def test_cli_run_disagreeing_round_record_carries_both_transcripts(tmp_path):
    bundle_path = tmp_path / "review-bundle.json"
    gating_transcript = "found a blocker\nVERDICT: REQUEST_CHANGES\n"
    _write_bundle(bundle_path, [gating_transcript])
    shadow_transcript = "looks fine\nVERDICT: APPROVE\n"
    (tmp_path / "shadow-review.md").write_text(shadow_transcript)

    r = subprocess.run([sys.executable, str(VERDICT_DIFF_PY), "run",
                         "--run-dir", str(tmp_path), "--bundle", str(bundle_path)],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads((tmp_path / "verdict-diff.json").read_text())
    assert data["agree"] is False
    assert data["gating_transcript"] == gating_transcript
    assert data["shadow_transcript"] == shadow_transcript
    comment = (tmp_path / "verdict-diff-comment.md").read_text()
    assert VERDICT_ANCHOR.search(comment) is None
    assert "> found a blocker" in comment and "> looks fine" in comment


# ===========================================================================
# Integration — tools/dev-runner.sh end-to-end, shadow seat armed (reuses the
# stubbed harness from tests/test_shadow_review.py)
# ===========================================================================

def _verdict_diff_comment_blocks(tmp_path):
    return [c for c in shadow._comment_blocks(tmp_path) if c.startswith("YR-VERDICT-DIFF:")]


def test_integration_agreeing_round_posts_one_verdict_diff_comment_and_record(tmp_path):
    binp = tmp_path / "bin"
    env = shadow._env(tmp_path, binp, number=5)
    env.update(shadow.SHADOW_ENV)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    blocks = _verdict_diff_comment_blocks(tmp_path)
    assert len(blocks) == 1
    assert blocks[0].splitlines()[0] == "YR-VERDICT-DIFF: agree"

    rd = shadow._run_dir(tmp_path)
    assert (rd / "verdict-diff.json").is_file()
    data = json.loads((rd / "verdict-diff.json").read_text())
    assert data["round"] == 1 and data["agree"] is True


def test_integration_disagreeing_round_comment_carries_both_findings(tmp_path):
    binp = tmp_path / "bin"
    env = shadow._env(tmp_path, binp, number=5)
    env.update(shadow.SHADOW_ENV)
    env["STUB_SHADOW_VERDICT"] = "VERDICT: REQUEST_CHANGES"  # gating approves, shadow disagrees
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                        # gate is indifferent to the shadow verdict

    blocks = _verdict_diff_comment_blocks(tmp_path)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.splitlines()[0] == "YR-VERDICT-DIFF: disagree"
    assert "gating: APPROVE" in block and "shadow: REQUEST_CHANGES" in block
    assert "> VERDICT: APPROVE" in block            # gating transcript's finding, blockquoted
    assert "> Shadow reviewer notes on the diff." in block   # shadow transcript's finding, blockquoted

    rd = shadow._run_dir(tmp_path)
    data = json.loads((rd / "verdict-diff.json").read_text())
    assert data["agree"] is False
    assert "gating_transcript" in data and "shadow_transcript" in data


def test_integration_repair_build_pairs_round_two_with_its_own_shadow(tmp_path):
    """A gating repair round (STUB_REVIEW_BLOCK) doubles the shadow rounds too (issue #165) — this
    slice must pair round 2's gating transcript with round 2's OWN shadow file, and land TWO
    YR-VERDICT-DIFF comments, one per round."""
    binp = tmp_path / "bin"
    env = shadow._env(tmp_path, binp, number=5)
    env.update(shadow.SHADOW_ENV)
    env["STUB_REVIEW_BLOCK"] = "1"     # gating: blocked once, approved after review-repair
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 2 and tl.count("SHADOWREVIEW") == 2

    blocks = _verdict_diff_comment_blocks(tmp_path)
    assert len(blocks) == 2
    rounds = sorted(int(re.search(r"round:\s*(\d+)", b).group(1)) for b in blocks)
    assert rounds == [1, 2]
    for b in blocks:
        assert "gating: REQUEST_CHANGES" in b or "gating: APPROVE" in b

    round1 = next(b for b in blocks if "round: 1" in b)
    round2 = next(b for b in blocks if "round: 2" in b)
    assert "gating: REQUEST_CHANGES" in round1     # round 1 was blocked
    assert "gating: APPROVE" in round2             # round 2 (post-repair) approved

    rd = shadow._run_dir(tmp_path)
    assert (rd / "verdict-diff.json").is_file()
    assert (rd / "verdict-diff-2.json").is_file()
    d1 = json.loads((rd / "verdict-diff.json").read_text())
    d2 = json.loads((rd / "verdict-diff-2.json").read_text())
    assert d1["round"] == 1 and d2["round"] == 2


def test_integration_dark_shadow_seat_produces_no_verdict_diff_artifacts_or_comments(tmp_path):
    """The shadow seat is dark by default (issue #165) -> no shadow round ever ran, so this slice
    must be a complete no-op: no verdict-diff*.json in the run dir, no YR-VERDICT-DIFF comment."""
    binp = tmp_path / "bin"
    env = shadow._env(tmp_path, binp, number=5)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    assert not _verdict_diff_comment_blocks(tmp_path)
    assert "YR-VERDICT-DIFF" not in base._prcomments(tmp_path)
    rd = shadow._run_dir(tmp_path)
    assert not list(rd.glob("verdict-diff*"))


def test_integration_every_posted_verdict_diff_comment_is_inert_under_line_anchored_grep(tmp_path):
    """No posted YR-VERDICT-DIFF comment body may contain a line matching the gating grammar's own
    anchor `^VERDICT:` — proven both for an agreeing round and a disagreeing repair round."""
    binp = tmp_path / "bin"
    env = shadow._env(tmp_path, binp, number=5)
    env.update(shadow.SHADOW_ENV)
    env["STUB_REVIEW_BLOCK"] = "1"
    env["STUB_SHADOW_VERDICT"] = "VERDICT: REQUEST_CHANGES"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    blocks = _verdict_diff_comment_blocks(tmp_path)
    assert blocks
    for block in blocks:
        assert VERDICT_ANCHOR.search(block) is None, block


def test_integration_merge_evaluator_and_gate_files_untouched():
    """Out of scope for this slice (backfilled by slice F at aggregation time): no evaluator/gate
    module may reference the verdict-diff record or schema."""
    for name in ("merge_shadow.py",):
        text = (ROOT / "tools" / name).read_text()
        assert "verdict_diff" not in text
        assert "yr-verdict-diff" not in text
