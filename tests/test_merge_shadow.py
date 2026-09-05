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
    """criterion 5: the rank gate (review-rank >= build-rank, the reviewer is never weaker; issue #139
    relaxed this from strict review>build) failing blocks and is named."""
    r = _all_pass()
    r["rank_gate"] = "fail"
    rec = _record(r)
    assert merge_shadow.render_comment(rec).splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} rank_gate"


def test_record_would_merge_when_rank_gate_pass_from_an_equal_rank_pair():
    """criterion 5 (issue #139): an equal-rank pair resolves rank_gate to 'pass' upstream (see
    tools/registry.rank_check and dev-runner.sh's shadow_rank_gate) — fed here as results['rank_gate']
    = 'pass' with build/review both at rank 40, the record still reaches WOULD-MERGE, not a block."""
    r = _all_pass()
    bundle = _bundle()
    bundle["build"] = {"name": "opus", "id": "claude-opus-4-8", "provider": "anthropic", "rank": 40, "ranked": True}
    bundle["review"] = {"name": "opus", "id": "claude-opus-4-8", "provider": "anthropic", "rank": 40, "ranked": True}
    rec = _record(r, bundle=bundle)
    assert rec["decision"] == "WOULD-MERGE"
    assert rec["failed_condition"] is None
    assert rec["build"]["rank"] == rec["review"]["rank"] == 40
    assert merge_shadow.render_comment(rec).splitlines()[0] == "YR-MERGE-SHADOW: WOULD-MERGE"


def test_record_schema_and_fixed_fields():
    rec = _record(_all_pass())
    assert rec["schema"] == "yr-merge-record/1"
    assert rec["mode"] == "shadow"
    assert rec["machinery_ok"] is True
    assert REQUIRED_FIELDS <= set(rec), f"missing fields: {REQUIRED_FIELDS - set(rec)}"


def test_record_carries_the_evaluator_own_commit_statement():
    """it-33 slice 3 (epic #455): every record this evaluator emits states the commit of the tree IT
    runs from (tools/provenance.py), computed once at import — never a per-call re-read."""
    import provenance
    rec = _record(_all_pass())
    assert rec["commit"] == merge_shadow.FACTORY_COMMIT
    assert rec["commit"] == provenance.factory_commit(merge_shadow.FACTORY_ROOT)


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


def test_render_comment_carries_a_plain_text_commit_field_line():
    """it-33 slice 3: `records.toml`'s YR-MERGE(-SHADOW) rows now declare `fields = ["commit"]` —
    `check_trail.py`'s `_missing_fields` wants a line starting `commit:` (lstripped), not merely a
    JSON key (a `"commit":` line never matches, the leading quote defeats `startswith`). Line 2, right
    under the marker, carries it verbatim; the JSON block's own `commit` key agrees with it."""
    rec = _record(_all_pass())
    comment = merge_shadow.render_comment(rec)
    lines = comment.splitlines()
    assert lines[1] == f"commit: {rec['commit']}"
    start = comment.index("```yr-merge-record") + len("```yr-merge-record")
    body = comment[start:]
    parsed = json.loads(body[:body.index("```")])
    assert parsed["commit"] == rec["commit"]


def test_rendered_merge_and_shadow_comments_satisfy_check_trail_s_commit_field(tmp_path):
    """End-to-end pin against the real registry: a rendered YR-MERGE / YR-MERGE-SHADOW comment must
    satisfy `check_trail.check_texts`'s field grammar for the live `commit` field — not just look
    right to the eye."""
    sys.path.insert(0, str(ROOT / "tools"))
    import check_trail
    import records

    reg = records.load()
    shadow_rec = _record(_all_pass())
    shadow_comment = merge_shadow.render_comment(shadow_rec)
    row = records.get(reg, "YR-MERGE-SHADOW")
    assert check_trail._missing_fields(row, [shadow_comment]) == []

    armed_rec = _record(_all_pass(), mode="armed", decision="MERGED")
    armed_comment = merge_shadow.render_comment(armed_rec)
    row = records.get(reg, "YR-MERGE")
    assert check_trail._missing_fields(row, [armed_comment]) == []


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


# ============ issue #319: last-record surfaces a parsed record's OWN base_sha/head_sha verbatim ============
# --re-evaluate (tools/dev-runner.sh) judges whether a prior record itself carries the observed incident
# shape (its base_sha equal to its head_sha, or a base_sha that is not an ancestor of the PR's live head)
# using exactly these two fields, read from the `last-record` CLI's own output — so that data must be
# surfaced verbatim from whatever the parsed record actually carries, not derived or defaulted away.

def _comment(decision, *, run_id="5-1", base_sha=None, head_sha=None, mode="shadow",
             failed_condition=None, malformed=False):
    if malformed:
        block = "{ this is not valid json"
    else:
        d = {"schema": "yr-merge-record/1", "decision": decision, "run_id": run_id,
             "failed_condition": failed_condition, "mode": mode, "machinery_ok": True}
        if base_sha is not None:
            d["base_sha"] = base_sha
        if head_sha is not None:
            d["head_sha"] = head_sha
        block = json.dumps(d)
    prefix = "YR-MERGE" if mode == "armed" else "YR-MERGE-SHADOW"
    marker = f"{prefix}: {decision}" if failed_condition is None else f"{prefix}: {decision} — {failed_condition}"
    return {"body": f"{marker}\n\n```yr-merge-record\n{block}\n```\n"}


def _last_record_cli(tmp_path, comments):
    cfile = tmp_path / "comments.json"
    cfile.write_text(json.dumps(comments))
    out = subprocess.run([sys.executable, str(TOOL), "last-record", "--comments-file", str(cfile)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_last_record_cli_surfaces_base_and_head_sha_verbatim(tmp_path):
    same_sha = "a" * 40
    rec = _last_record_cli(tmp_path, [_comment("WOULD-MERGE", run_id="5-1", base_sha=same_sha, head_sha=same_sha)])
    assert rec == {
        "found": True, "malformed": False, "run_id": "5-1", "decision": "WOULD-MERGE",
        "failed_condition": None, "mode": "shadow", "base_sha": same_sha, "head_sha": same_sha,
    }


def test_last_record_cli_base_and_head_sha_differ_when_the_record_carries_distinct_ones(tmp_path):
    rec = _last_record_cli(tmp_path, [_comment("WOULD-MERGE", run_id="5-1", base_sha="b" * 40, head_sha="h" * 40)])
    assert rec["base_sha"] == "b" * 40 and rec["head_sha"] == "h" * 40


def test_last_record_cli_base_and_head_sha_absent_from_an_older_record_shape(tmp_path):
    """A record predating issue #319 (no base_sha/head_sha keys at all) surfaces both as null — the
    caller's guard for 'nothing to judge' must see null, never a stringified default that could compare
    equal to something."""
    rec = _last_record_cli(tmp_path, [_comment("WOULD-MERGE", run_id="5-1")])
    assert rec["base_sha"] is None and rec["head_sha"] is None


def test_last_record_cli_still_flags_malformed_before_any_sha_is_read(tmp_path):
    """An unparseable last record still surfaces only {found: true, malformed: true} — no base_sha/
    head_sha keys at all, since there is no parsed record to read them from."""
    rec = _last_record_cli(tmp_path, [_comment("WOULD-MERGE", run_id="5-1", malformed=True)])
    assert rec == {"found": True, "malformed": True}


# ============ issue #146: the back-compat alias for the condition order is gone ============
# NB: the retired name is built via concatenation, never spelled out literally, so this file
# itself doesn't trip its own "nothing left in the tree" scan below.
_RETIRED_ALIAS = "CONDITION" + "_ORDER"


def test_condition_order_alias_removed_from_module():
    """SHADOW_ORDER is the one name for the evaluator's condition order — no back-compat alias."""
    assert not hasattr(merge_shadow, _RETIRED_ALIAS)


def test_condition_order_absent_from_source_tree():
    """grep -rn '<the retired alias>' tools/ tests/ returns nothing (issue #146 test expectation)."""
    for base in (ROOT / "tools", ROOT / "tests"):
        for path in base.rglob("*.py"):
            text = path.read_text()
            assert _RETIRED_ALIAS not in text, f"found the retired alias in {path}"


def test_shadow_order_is_the_condition_order():
    """SHADOW_ORDER itself is untouched: the four conditions, in the fixed evaluation order."""
    assert merge_shadow.SHADOW_ORDER == ("ci_green", "freshness", "terminal_approval", "rank_gate")
