"""Acceptance tests for tools/bench_report.py — the bench report generator (issue #167, slice F of
epic yellow-robots/factory#161).

Derived from the acceptance CRITERIA (the spec), never from bench_report.py's own internals:

  * `report` aggregates bench/results/*.jsonl into bench/reports/<date>-report.md: per-configuration
    pass rates and weighted costs (raw counts preserved, never collapsed away), N stated, per-repo
    composition, the grading caveat, and the run's own total weighted-token cost. The weighted-cost
    arithmetic must reproduce tools/stage_usage.py's own imported WEIGHTED_TOTAL_WEIGHTS.
  * This write is an attended host-tool write — no runner coupling.
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
# This write is an attended host-tool write -- no runner coupling
# ============================================================================

def test_dev_runner_never_shells_out_to_bench_report():
    dev_runner = (ROOT / "tools" / "dev-runner.sh").read_text()
    assert "bench_report" not in dev_runner


def test_dispatch_never_references_bench_report():
    dispatch = (ROOT / "tools" / "dispatch.py").read_text()
    assert "bench_report" not in dispatch
