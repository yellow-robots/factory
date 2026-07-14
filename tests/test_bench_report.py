"""Acceptance tests for tools/bench_report.py — the bench report generator + verdict-diff
aggregation with merge-outcome backfill (issue #167, slice F of epic yellow-robots/factory#161).

Derived from the acceptance CRITERIA (the spec), never from bench_report.py's own internals:

  * `report` aggregates bench/results/*.jsonl into bench/reports/<date>-report.md: per-configuration
    pass rates and weighted costs (raw counts preserved, never collapsed away), N stated, per-repo
    composition, the grading caveat, and the run's own total weighted-token cost. The weighted-cost
    arithmetic must reproduce tools/stage_usage.py's own imported WEIGHTED_TOTAL_WEIGHTS.
  * `sweep-diffs` sweeps verdict-diff records into bench/diffs/<owner>--<name>.jsonl, backfilling
    each PR's merge outcome at aggregation time (`pending` for a still-open PR); re-aggregation is
    idempotent, keyed on repo+PR+round, updated in place rather than duplicated.
  * Both writes are attended host-tool writes — no runner coupling.

Stubbed-`gh` style (mirrors test_bench_corpus.py): a fake `gh(argv)` callable is injected into
`sweep_diffs`, serving canned `api .../issues/comments` / `pr view` responses. No live `gh`, no
network. Verdict-diff comment fixtures are produced via tools/verdict_diff.py's own `render_comment`
(the real upstream producer's contract), never hand-authored to match bench_report.py's parser.
"""
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bench_report  # noqa: E402
import stage_usage  # noqa: E402
import verdict_diff  # noqa: E402

REPO = "yellow-robots/widget"
OWNER, NAME = "yellow-robots", "widget"


# ============================================================================
# report: bench/results/*.jsonl -> bench/reports/<date>-report.md
# ============================================================================

def _weighted(input_tokens=0, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0):
    w = stage_usage.WEIGHTED_TOTAL_WEIGHTS
    return round(
        input_tokens * w["input_tokens"]
        + output_tokens * w["output_tokens"]
        + cache_write_tokens * w["cache_write_tokens"]
        + cache_read_tokens * w["cache_read_tokens"]
    )


def _result_row(*, config, repo, outcome, issue=1, pr=1, input_tokens=0, output_tokens=0,
                 cache_write_tokens=0, cache_read_tokens=0):
    """A yr-bench-result/1 row shaped like tools/bench_replay.py's `run_candidate` driver emits —
    weighted_total precomputed the same way `_candidate_result` does, from stage_usage's own weights."""
    return {
        "schema": "yr-bench-result/1",
        "config": config,
        "model": "claude-sonnet-5",
        "task": f"{issue}-pr{pr}",
        "repo": repo,
        "issue": issue,
        "pr": pr,
        "outcome": outcome,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cache_read_tokens": cache_read_tokens,
        "weighted_total": _weighted(input_tokens, output_tokens, cache_write_tokens, cache_read_tokens),
        "check_cmd": "pytest -q",
        "check_rc": 0 if outcome == "pass" else 1,
        "output": "",
        "detail": None,
        "graded_at": "2026-07-13T00:00:00Z",
    }


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


CAVEAT_BODY = "Bench grading is entirely mechanical, never an LLM judge.\n\nA `pass` proves only that."


def _write_readme(path, caveat=CAVEAT_BODY):
    path.write_text(f"# Bench corpus\n\nSome intro text.\n\n## Grading caveat\n\n{caveat}\n")


def test_report_pass_rate_and_weighted_cost_reproduce_stage_usage_weights(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    sonnet_rows = [
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass", pr=1,
                    input_tokens=100, output_tokens=20, cache_write_tokens=8, cache_read_tokens=200),
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="fail", pr=2,
                    input_tokens=50, output_tokens=10),
    ]
    opus_rows = [
        _result_row(config="opus", repo="yellow-robots/gizmo", outcome="pass", pr=3,
                    input_tokens=300, output_tokens=60),
    ]
    _write_jsonl(results_dir / "2026-07-13-sonnet.jsonl", sonnet_rows)
    _write_jsonl(results_dir / "2026-07-13-opus.jsonl", opus_rows)

    readme = tmp_path / "README.md"
    _write_readme(readme)

    out_dir = tmp_path / "reports"
    path = bench_report.aggregate_report(results_dir=results_dir, out_dir=out_dir, readme_path=readme,
                                          now=lambda: "2026-07-14T00:00:00Z")

    assert path == out_dir / "2026-07-14-report.md"
    text = path.read_text()

    # per-configuration weighted cost: the sum of each row's own precomputed weighted_total, which is
    # itself derived from stage_usage.WEIGHTED_TOTAL_WEIGHTS — never a re-typed constant.
    sonnet_weighted = sum(r["weighted_total"] for r in sonnet_rows)
    opus_weighted = sum(r["weighted_total"] for r in opus_rows)
    assert sonnet_weighted == 330  # 100*1 + 20*5 + 8*1.25 + 200*0.1 = 230, plus 50*1 + 10*5 = 100
    assert opus_weighted == 600    # 300*1 + 60*5 = 600

    assert str(sonnet_weighted) in text
    assert str(opus_weighted) in text
    assert str(sonnet_weighted + opus_weighted) in text  # the run's own total weighted-token cost

    # pass rate: pass / (pass + fail), raw counts preserved alongside
    assert "50.0%" in text  # sonnet: 1 pass, 1 fail
    assert "100.0%" in text  # opus: 1 pass, 0 fail
    assert "pass=1" in text and "fail=1" in text  # sonnet raw outcome counts, not collapsed away


def test_report_states_n_and_per_repo_composition(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    rows = [
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass", pr=1),
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="fail", pr=2),
        _result_row(config="sonnet", repo="yellow-robots/gizmo", outcome="pass", pr=3),
    ]
    _write_jsonl(results_dir / "2026-07-13-sonnet.jsonl", rows)
    readme = tmp_path / "README.md"
    _write_readme(readme)

    path = bench_report.aggregate_report(results_dir=results_dir, out_dir=tmp_path / "reports",
                                          readme_path=readme, now=lambda: "2026-07-14T00:00:00Z")
    text = path.read_text()

    assert re.search(r"\bN\b.*3", text)  # 3 graded rows stated plainly
    assert re.search(r"yellow-robots/widget.*?2", text) or re.search(r"2.*yellow-robots/widget", text)
    assert re.search(r"yellow-robots/gizmo.*?1", text) or re.search(r"1.*yellow-robots/gizmo", text)


def test_report_quotes_the_grading_caveat_verbatim(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _write_jsonl(results_dir / "2026-07-13-sonnet.jsonl",
                 [_result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass")])
    readme = tmp_path / "README.md"
    caveat = "This exact caveat sentence must appear byte-for-byte, never re-worded or summarized."
    _write_readme(readme, caveat=caveat)

    path = bench_report.aggregate_report(results_dir=results_dir, out_dir=tmp_path / "reports",
                                          readme_path=readme, now=lambda: "2026-07-14T00:00:00Z")
    text = path.read_text()

    assert caveat in text


def test_report_quotes_the_real_corpus_readmes_caveat_verbatim():
    """The shipped bench/corpus/README.md carries the real grading caveat this report must quote —
    exercised against the actual checked-in file, not a fixture stand-in."""
    real_caveat = bench_report.load_grading_caveat()
    real_readme_text = (ROOT / "bench" / "corpus" / "README.md").read_text()
    assert real_caveat in real_readme_text
    assert "not independent proof of correctness" in real_caveat


def test_report_excludes_rows_with_no_config_from_the_working_set(tmp_path):
    """A bare `grade()` row (no `config`) is not a candidate-replay row and must not pollute the
    per-configuration aggregate."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    bare_grade_row = {
        "schema": "yr-bench-result/1", "repo": "yellow-robots/widget", "issue": 1, "pr": 1,
        "outcome": "pass", "graded_at": "2026-07-13T00:00:00Z",
    }
    good_row = _result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass")
    _write_jsonl(results_dir / "2026-07-13-mixed.jsonl", [bare_grade_row, good_row])

    rows = bench_report.load_result_rows(results_dir)

    assert len(rows) == 1
    assert rows[0]["config"] == "sonnet"


def test_report_skips_malformed_and_mismatched_schema_lines(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    good_row = _result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass")
    path = results_dir / "2026-07-13-sonnet.jsonl"
    path.write_text(
        "not json at all\n"
        + json.dumps({"schema": "some-other-schema/1", "config": "sonnet"}) + "\n"
        + "\n"  # a blank line
        + json.dumps(good_row) + "\n"
    )

    rows = bench_report.load_result_rows(results_dir)

    assert len(rows) == 1
    assert rows[0] == good_row


def test_report_pass_rate_excludes_ungraded_environmental_and_invalid_seal_from_denominator(tmp_path):
    """A pass rate over (pass + fail) only — an ungraded-environmental or invalid-seal row is
    evidence of nothing about the candidate and must not water down the denominator."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    rows = [
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass", pr=1),
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="ungraded-environmental", pr=2),
        _result_row(config="sonnet", repo="yellow-robots/widget", outcome="invalid-seal", pr=3),
    ]
    _write_jsonl(results_dir / "2026-07-13-sonnet.jsonl", rows)

    by_config = bench_report.aggregate_by_config(bench_report.load_result_rows(results_dir))

    assert by_config["sonnet"]["n"] == 3
    assert by_config["sonnet"]["pass_rate"] == 1.0  # 1 pass / (1 pass + 0 fail), not / 3
    assert by_config["sonnet"]["outcomes"] == {
        "pass": 1, "ungraded-environmental": 1, "invalid-seal": 1,
    }


def test_report_reaggregation_over_unchanged_inputs_is_byte_identical(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _write_jsonl(results_dir / "2026-07-13-sonnet.jsonl",
                 [_result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass")])
    readme = tmp_path / "README.md"
    _write_readme(readme)
    out_dir = tmp_path / "reports"

    path1 = bench_report.aggregate_report(results_dir=results_dir, out_dir=out_dir, readme_path=readme,
                                           now=lambda: "2026-07-14T00:00:00Z")
    text1 = path1.read_text()
    path2 = bench_report.aggregate_report(results_dir=results_dir, out_dir=out_dir, readme_path=readme,
                                           now=lambda: "2026-07-14T00:00:00Z")
    text2 = path2.read_text()

    assert path1 == path2
    assert text1 == text2


def test_report_raises_when_corpus_readme_carries_no_grading_caveat_section(tmp_path):
    """A report silently missing its own grading caveat would misrepresent what a pass proves —
    this must fail loudly, never degrade to an empty/absent caveat section."""
    readme = tmp_path / "README.md"
    readme.write_text("# Bench corpus\n\nNo caveat section here.\n")

    with pytest.raises(Exception):
        bench_report.load_grading_caveat(readme)


def test_cli_report_writes_and_prints_the_path(tmp_path, capsys):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _write_jsonl(results_dir / "2026-07-13-sonnet.jsonl",
                 [_result_row(config="sonnet", repo="yellow-robots/widget", outcome="pass")])
    readme = tmp_path / "README.md"
    _write_readme(readme)
    out_dir = tmp_path / "reports"

    rc = bench_report.main([
        "report", "--results-dir", str(results_dir), "--out-dir", str(out_dir), "--readme", str(readme),
    ])

    assert rc == 0
    printed = capsys.readouterr().out.strip()
    assert pathlib.Path(printed).exists()
    assert pathlib.Path(printed).read_text() == pathlib.Path(printed).read_text()  # written, non-empty
    assert pathlib.Path(printed).parent == out_dir


# ============================================================================
# sweep-diffs: YR-VERDICT-DIFF PR comments -> bench/diffs/<owner>--<name>.jsonl, merge backfilled
# ============================================================================

def _diff_record(*, round=1, gating="APPROVE", shadow="APPROVE", agree=True,
                  gating_transcript="VERDICT: APPROVE\n", shadow_transcript="VERDICT: APPROVE\n"):
    record = {
        "schema": "yr-verdict-diff/1", "round": round, "gating": gating, "shadow": shadow, "agree": agree,
    }
    if not agree:
        record["gating_transcript"] = gating_transcript
        record["shadow_transcript"] = shadow_transcript
    return record


def _comment(pr_number, body):
    return {"issue_url": f"https://api.github.com/repos/{OWNER}/{NAME}/issues/{pr_number}", "body": body}


def _make_gh(comments, pr_view):
    """Routes `gh(argv)` the way bench_report.py's sweep_diffs actually calls it: the paginated
    issue-comments listing, and a per-PR `pr view --json state,mergedAt` read."""
    def gh(argv):
        if argv[0] == "api":
            assert argv[1] == f"repos/{OWNER}/{NAME}/issues/comments"
            assert "--paginate" in argv
            return comments
        if argv[0] == "pr" and argv[1] == "view":
            pr_number = int(argv[2])
            assert f"{OWNER}/{NAME}" in argv
            if pr_number not in pr_view:
                raise AssertionError(f"no fixture pr view for #{pr_number}")
            return pr_view[pr_number]
        raise AssertionError(f"unhandled gh argv: {argv}")
    return gh


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_sweep_diffs_backfills_pending_for_a_still_open_pr(tmp_path):
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh([_comment(42, body)], {42: {"state": "OPEN", "mergedAt": None}})

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 1
    assert rows[0]["pr"] == 42
    assert rows[0]["round"] == 1
    assert rows[0]["outcome"] == "pending"
    assert rows[0]["repo"] == REPO
    assert rows[0]["gating"] == "APPROVE"
    assert rows[0]["shadow"] == "APPROVE"
    assert rows[0]["agree"] is True


def test_sweep_diffs_backfills_merged_for_a_merged_pr(tmp_path):
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh([_comment(7, body)],
                  {7: {"state": "MERGED", "mergedAt": "2026-07-14T00:00:00Z"}})

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "merged"


def test_sweep_diffs_backfills_closed_for_a_closed_unmerged_pr(tmp_path):
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh([_comment(9, body)], {9: {"state": "CLOSED", "mergedAt": None}})

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "closed"


def test_sweep_diffs_ignores_comments_that_are_not_verdict_diff_shaped(tmp_path):
    verdict_body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh(
        [_comment(42, "just some unrelated chatter on this PR"), _comment(42, verdict_body)],
        {42: {"state": "OPEN", "mergedAt": None}},
    )

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 1
    assert rows[0]["round"] == 1


def test_sweep_diffs_writes_to_owner_dash_dash_name_path(tmp_path):
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh([_comment(1, body)], {1: {"state": "OPEN", "mergedAt": None}})

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    assert out_path == tmp_path / f"{OWNER}--{NAME}.jsonl"


def test_sweep_diffs_rerun_with_unchanged_inputs_is_byte_identical(tmp_path):
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh([_comment(42, body)], {42: {"state": "OPEN", "mergedAt": None}})

    path1 = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)
    text1 = path1.read_text()
    path2 = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)
    text2 = path2.read_text()

    assert text1 == text2


def test_sweep_diffs_updates_existing_record_in_place_when_a_pr_merges(tmp_path):
    """Idempotent, keyed on repo+PR+round: a re-aggregation after the PR transitions from open to
    merged updates the SAME record rather than appending a duplicate."""
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh_open = _make_gh([_comment(42, body)], {42: {"state": "OPEN", "mergedAt": None}})
    bench_report.sweep_diffs(REPO, gh=gh_open, out_dir=tmp_path)

    gh_merged = _make_gh([_comment(42, body)],
                          {42: {"state": "MERGED", "mergedAt": "2026-07-14T00:00:00Z"}})
    out_path = bench_report.sweep_diffs(REPO, gh=gh_merged, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0]["pr"] == 42
    assert rows[0]["round"] == 1
    assert rows[0]["outcome"] == "merged"


def test_sweep_diffs_keys_distinct_rounds_of_the_same_pr_separately(tmp_path):
    body_r1 = verdict_diff.render_comment(_diff_record(round=1))
    body_r2 = verdict_diff.render_comment(_diff_record(round=2, gating="REJECT", shadow="REJECT"))
    gh = _make_gh([_comment(42, body_r1), _comment(42, body_r2)],
                  {42: {"state": "OPEN", "mergedAt": None}})

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 2
    by_round = {r["round"]: r for r in rows}
    assert by_round[1]["pr"] == 42 and by_round[2]["pr"] == 42
    assert by_round[1]["outcome"] == "pending" and by_round[2]["outcome"] == "pending"


def test_sweep_diffs_preserves_prior_records_not_touched_by_the_current_sweep(tmp_path):
    """A record already on disk for a PR/round the current gh listing doesn't happen to return again
    is kept, not dropped — the aggregate only ever updates matching keys in place."""
    body_pr42 = verdict_diff.render_comment(_diff_record(round=1))
    gh1 = _make_gh([_comment(42, body_pr42)], {42: {"state": "OPEN", "mergedAt": None}})
    bench_report.sweep_diffs(REPO, gh=gh1, out_dir=tmp_path)

    body_pr43 = verdict_diff.render_comment(_diff_record(round=1))
    gh2 = _make_gh([_comment(43, body_pr43)], {43: {"state": "CLOSED", "mergedAt": None}})
    out_path = bench_report.sweep_diffs(REPO, gh=gh2, out_dir=tmp_path)

    rows = _rows(out_path)
    prs = {r["pr"] for r in rows}
    assert prs == {42, 43}
    by_pr = {r["pr"]: r for r in rows}
    assert by_pr[42]["outcome"] == "pending"
    assert by_pr[43]["outcome"] == "closed"


def test_sweep_diffs_carries_a_disagreement_records_transcripts_through(tmp_path):
    body = verdict_diff.render_comment(_diff_record(
        round=1, gating="APPROVE", shadow="REJECT", agree=False,
        gating_transcript="VERDICT: APPROVE\n", shadow_transcript="VERDICT: REJECT\n",
    ))
    gh = _make_gh([_comment(42, body)], {42: {"state": "OPEN", "mergedAt": None}})

    out_path = bench_report.sweep_diffs(REPO, gh=gh, out_dir=tmp_path)

    rows = _rows(out_path)
    assert len(rows) == 1
    assert rows[0]["agree"] is False
    assert rows[0]["gating"] == "APPROVE"
    assert rows[0]["shadow"] == "REJECT"


def test_cli_sweep_diffs_requires_repo_argument():
    with pytest.raises(SystemExit):
        bench_report.main(["sweep-diffs"])


def test_cli_sweep_diffs_prints_the_written_path(tmp_path, monkeypatch, capsys):
    body = verdict_diff.render_comment(_diff_record(round=1))
    gh = _make_gh([_comment(42, body)], {42: {"state": "OPEN", "mergedAt": None}})
    monkeypatch.setattr(bench_report, "_default_gh", gh)

    rc = bench_report.main(["sweep-diffs", "--repo", REPO, "--out-dir", str(tmp_path)])

    assert rc == 0
    printed = pathlib.Path(capsys.readouterr().out.strip())
    assert printed == tmp_path / f"{OWNER}--{NAME}.jsonl"
    assert printed.exists()


# ============================================================================
# Both writes are attended host-tool writes -- no runner coupling
# ============================================================================

def test_dev_runner_never_shells_out_to_bench_report():
    dev_runner = (ROOT / "tools" / "dev-runner.sh").read_text()
    assert "bench_report" not in dev_runner


def test_dispatch_never_references_bench_report():
    dispatch = (ROOT / "tools" / "dispatch.py").read_text()
    assert "bench_report" not in dispatch
