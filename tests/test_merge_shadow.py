"""Unit tests for tools/merge_shadow.py — the terminal (shadow) merge-condition evaluator + record.

These exercise the pure, deterministic core of issue #37 directly (no runner, no network):
  * classify-checks / count_checks / bucket_of — reduce a PR statusCheckRollup, treating anything
    indeterminate as FAILED (criteria 1 & 2);
  * first_failed — the conditions are evaluated IN ORDER; the first non-'pass' names the block reason
    (criterion 1);
  * build_record / render_comment — the loud marker grammar and the versioned `yr-merge-record/1`
    schema with its fixed fields (criteria 4, 5, 6).

Derived from the acceptance criteria (the spec), not the implementation's internals.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "merge_shadow.py"
sys.path.insert(0, str(ROOT / "tools"))
import merge_shadow  # noqa: E402


EMDASH = "—"  # the marker separator: 'WOULD-BLOCK — <condition>'

# The fields the epic fixes on the record (the versioned contract shadow-completion computes over).
REQUIRED_FIELDS = {
    "schema", "decision", "mode", "machinery_ok", "failed_condition", "bundle_sha256",
    "base_sha", "head_sha", "main_tip_sha", "check_rollup", "checks", "review_verdict",
    "rounds", "build", "review", "run_id", "timestamp",
}

# rollup entry shapes (as `gh pr view --json statusCheckRollup` returns them).
CR_OK = {"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": "SUCCESS"}
CR_FAIL = {"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": "FAILURE"}
CR_INFLIGHT = {"__typename": "CheckRun", "name": "unit", "status": "IN_PROGRESS", "conclusion": None}
CR_QUEUED = {"__typename": "CheckRun", "name": "unit", "status": "QUEUED", "conclusion": None}
SC_OK = {"__typename": "StatusContext", "context": "legacy", "state": "SUCCESS"}
SC_PENDING = {"__typename": "StatusContext", "context": "legacy", "state": "PENDING"}
SC_FAIL = {"__typename": "StatusContext", "context": "legacy", "state": "FAILURE"}


def _bundle():
    return {
        "sha256": "abc123",
        "rounds": [
            {"index": 1, "verdict": "VERDICT: REQUEST_CHANGES", "transcript": "..."},
            {"index": 2, "verdict": "VERDICT: APPROVE", "transcript": "..."},
        ],
        "build": {"name": "sonnet", "id": "claude-sonnet-5", "provider": "anthropic", "rank": 30, "ranked": True},
        "review": {"name": "opus", "id": "claude-opus-4-8", "provider": "anthropic", "rank": 40, "ranked": True},
    }


def _all_pass():
    return {"ci_green": "pass", "freshness": "pass", "terminal_approval": "pass", "rank_gate": "pass"}


def _record(results, **kw):
    args = dict(
        results=results, bundle=_bundle(), base_sha="b" * 40, head_sha="h" * 40,
        main_tip_sha="b" * 40, checks=[], check_rollup="success",
        run_id="5-999", timestamp="2026-07-06T00:00:00Z",
    )
    args.update(kw)
    return merge_shadow.build_record(**args)


# ============ criterion 2 & 1: CI rollup reduction, indeterminate = failed ============

def test_bucket_success_pending_fail():
    assert merge_shadow.bucket_of(CR_OK) == "pass"
    assert merge_shadow.bucket_of(CR_INFLIGHT) == "pending"
    assert merge_shadow.bucket_of(CR_QUEUED) == "pending"
    assert merge_shadow.bucket_of(CR_FAIL) == "fail"


def test_bucket_statuscontext_legacy_states():
    assert merge_shadow.bucket_of(SC_OK) == "pass"
    assert merge_shadow.bucket_of(SC_PENDING) == "pending"
    assert merge_shadow.bucket_of(SC_FAIL) == "fail"


def test_bucket_indeterminate_is_failed():
    """Anything unrecognized -> 'fail' (indeterminate = failed): the loud record must never over-report green."""
    assert merge_shadow.bucket_of({}) == "fail"                                     # empty entry
    assert merge_shadow.bucket_of({"__typename": "CheckRun"}) == "fail"             # no status/conclusion
    assert merge_shadow.bucket_of({"status": "MYSTERY"}) == "fail"                  # unknown status
    assert merge_shadow.bucket_of({"status": "COMPLETED", "conclusion": "CANCELLED"}) == "fail"
    assert merge_shadow.bucket_of({"status": "COMPLETED", "conclusion": "TIMED_OUT"}) == "fail"
    assert merge_shadow.bucket_of({"state": "ERROR"}) == "fail"                     # unknown legacy state


def test_count_checks_all_green():
    c = merge_shadow.count_checks([CR_OK, SC_OK])
    assert (c["total"], c["in_flight"], c["failed"], c["successful"]) == (2, 0, 0, 2)


def test_count_checks_mixed_failure():
    """'every configured check concluded successful' — one failure means the set is not green."""
    c = merge_shadow.count_checks([CR_OK, CR_FAIL])
    assert c["total"] == 2 and c["failed"] == 1


def test_count_checks_in_flight_is_counted():
    c = merge_shadow.count_checks([CR_OK, CR_INFLIGHT])
    assert c["total"] == 2 and c["in_flight"] == 1


def test_count_checks_zero_configured():
    c = merge_shadow.count_checks([])
    assert c["total"] == 0 and c["in_flight"] == 0 and c["failed"] == 0


def test_classify_checks_cli_prints_total_in_flight_failed(tmp_path):
    rollup = tmp_path / "rollup.json"
    rollup.write_text(json.dumps({"statusCheckRollup": [CR_OK, CR_INFLIGHT, CR_FAIL]}))
    out = subprocess.run([sys.executable, str(TOOL), "classify-checks", "--rollup-file", str(rollup)],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "3 1 1"   # total in_flight failed


def test_classify_checks_cli_zero(tmp_path):
    rollup = tmp_path / "rollup.json"
    rollup.write_text(json.dumps({"statusCheckRollup": []}))
    out = subprocess.run([sys.executable, str(TOOL), "classify-checks", "--rollup-file", str(rollup)],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "0 0 0"


# ============ criterion 1: conditions evaluated in order; first non-pass names the reason ============

def test_first_failed_none_when_all_pass():
    assert merge_shadow.first_failed(_all_pass()) is None


def test_first_failed_respects_order():
    order = ["ci_green", "freshness", "terminal_approval", "rank_gate"]
    assert merge_shadow.CONDITION_ORDER == tuple(order)
    for i, cond in enumerate(order):
        results = _all_pass()
        results[cond] = "fail"
        assert merge_shadow.first_failed(results) == cond


def test_first_failed_picks_earliest_when_several_fail():
    r = _all_pass()
    r["freshness"] = "fail"
    r["rank_gate"] = "fail"
    assert merge_shadow.first_failed(r) == "freshness"   # earliest-in-order wins, not the last


def test_first_failed_treats_non_pass_as_failed():
    """indeterminate = failed: any result value that is not exactly 'pass' counts as a failure."""
    r = _all_pass()
    r["ci_green"] = "indeterminate"
    assert merge_shadow.first_failed(r) == "ci_green"


# ============ criteria 4/5/6: record schema, fixed fields, loud marker grammar ============

def test_record_would_merge_all_conditions_pass():
    rec = _record(_all_pass())
    assert rec["decision"] == "WOULD-MERGE"
    assert rec["failed_condition"] is None
    assert merge_shadow.render_comment(rec).splitlines()[0] == "YR-MERGE-SHADOW: WOULD-MERGE"


def test_record_would_block_names_first_failed_condition():
    r = _all_pass()
    r["freshness"] = "fail"
    rec = _record(r)
    assert rec["decision"] == "WOULD-BLOCK"
    assert rec["failed_condition"] == "freshness"
    assert merge_shadow.render_comment(rec).splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} freshness"


def test_record_would_block_terminal_approval():
    """criterion 4: a non-clean terminal review round blocks, and the reason is named."""
    r = _all_pass()
    r["terminal_approval"] = "fail"
    rec = _record(r)
    assert merge_shadow.render_comment(rec).splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} terminal_approval"


def test_record_would_block_rank_gate():
    """criterion 5: the rank gate (strict review>build) failing blocks and is named."""
    r = _all_pass()
    r["rank_gate"] = "fail"
    rec = _record(r)
    assert merge_shadow.render_comment(rec).splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} rank_gate"


def test_record_schema_and_fixed_fields():
    rec = _record(_all_pass())
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["mode"] == "shadow"
    assert rec["machinery_ok"] is True
    assert REQUIRED_FIELDS <= set(rec), f"missing fields: {REQUIRED_FIELDS - set(rec)}"


def test_record_pulls_the_fixed_fields_from_the_bundle():
    rec = _record(_all_pass())
    assert rec["bundle_sha256"] == "abc123"
    assert rec["review_verdict"] == "VERDICT: APPROVE"   # the LAST round's verdict
    assert rec["rounds"] == 2                             # number of review rounds
    assert rec["build"]["id"] == "claude-sonnet-5"
    assert rec["review"]["id"] == "claude-opus-4-8"


def test_record_carries_the_shas_and_ci_state():
    rec = _record(_all_pass(), base_sha="1" * 40, head_sha="2" * 40, main_tip_sha="3" * 40,
                  check_rollup="success")
    assert rec["base_sha"] == "1" * 40
    assert rec["head_sha"] == "2" * 40
    assert rec["main_tip_sha"] == "3" * 40
    assert rec["check_rollup"] == "success"


def test_render_comment_first_line_then_fenced_block():
    """The comment is loud: line 1 is exactly the marker; then a fenced `yr-merge-record` JSON block
    that parses back to the record at schema/1."""
    rec = _record(_all_pass())
    comment = merge_shadow.render_comment(rec)
    lines = comment.splitlines()
    assert lines[0] == "YR-MERGE-SHADOW: WOULD-MERGE"
    assert "```yr-merge-record" in comment
    start = comment.index("```yr-merge-record") + len("```yr-merge-record")
    body = comment[start:]
    parsed = json.loads(body[:body.index("```")])
    assert parsed["schema"] == "yr-merge-record/1"
    assert parsed["decision"] == "WOULD-MERGE"


def test_record_cli_roundtrip(tmp_path):
    """The `record` subcommand emits a comment whose first line is the marker and whose fenced block
    parses at schema/1 with the fixed fields (WOULD-BLOCK on the first failed condition)."""
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(_bundle()))
    out = tmp_path / "comment.md"
    subprocess.run([
        sys.executable, str(TOOL), "record",
        "--ci-green", "pass", "--freshness", "fail",
        "--terminal-approval", "pass", "--rank-gate", "pass",
        "--bundle", str(bundle), "--base-sha", "b" * 40, "--head-sha", "h" * 40,
        "--main-tip-sha", "m" * 40, "--ci-state", "success",
        "--run-id", "5-1", "--timestamp", "2026-07-06T00:00:00Z", "--out", str(out),
    ], capture_output=True, text=True, check=True)
    text = out.read_text()
    assert text.splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} freshness"
    start = text.index("```yr-merge-record") + len("```yr-merge-record")
    rec = json.loads(text[start:][: text[start:].index("```")])
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "freshness"
    assert REQUIRED_FIELDS <= set(rec)
