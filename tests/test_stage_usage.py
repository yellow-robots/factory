"""Tests for tools/stage_usage.py — per-stage usage capture + the PR usage-summary (issue #48).

Derived from the CRITERIA (the spec), not the implementation's internals:
  * on a stage's clean exit, extract the CLI's `--output-format json` single-object result envelope
    from its log, rewrite the log to the plain reply text, and file the token/cache usage (fresh
    input / output / cache write / cache read) + model id + duration as a per-stage artifact;
  * a log that is not a JSON envelope (plain text) is left completely untouched and yields no artifact
    — degrade, never mask a failure or success;
  * extraction tolerates surrounding non-JSON noise (stray hook/MCP warning lines) mixed into the log;
  * the aggregate summary rolls up every per-stage artifact into totals and a PR comment that never
    carries the merge-shadow machinery's `YR-`/`YR-MERGE` marker grammar.

Exercises the module's public functions directly, and its CLI (`extract` / `summarize`) as a
subprocess — the same two entry points tools/dev-runner.sh shells out to.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import stage_usage
from tools.stage_usage import (
    build_summary, find_result_envelope, load_usage_records, process_stage_log,
    render_summary_comment, usage_record,
)

STAGE_USAGE_PY = ROOT / "tools" / "stage_usage.py"


def _envelope(result="hello", input_tokens=10, output_tokens=20, cache_write=3, cache_read=4,
              duration_ms=1234, **extra):
    d = {
        "type": "result", "subtype": "success", "is_error": False,
        "result": result, "duration_ms": duration_ms,
        "usage": {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_write, "cache_read_input_tokens": cache_read,
        },
    }
    d.update(extra)
    return d


def _envelope_line(**kw):
    return json.dumps(_envelope(**kw))


# ============ find_result_envelope: extraction, noise tolerance ============

def test_find_result_envelope_parses_single_line_envelope():
    env = find_result_envelope(_envelope_line(result="the reply") + "\n")
    assert env is not None
    assert env["result"] == "the reply"


def test_find_result_envelope_none_for_plain_text():
    assert find_result_envelope("just a plain reply, no JSON here\n") is None


def test_find_result_envelope_none_for_empty_text():
    assert find_result_envelope("") is None


def test_find_result_envelope_ignores_non_result_json():
    """A JSON line present but not `"type": "result"` (e.g. a stream event) must not be mistaken
    for the envelope."""
    noise = json.dumps({"type": "system", "subtype": "init"})
    assert find_result_envelope(noise + "\n") is None


def test_find_result_envelope_tolerates_surrounding_noise():
    """run_stage merges stderr into the log, and hook/MCP warnings can precede/follow the envelope —
    extraction must not require a byte-clean file."""
    text = "Warning: some hook fired\n" + _envelope_line(result="ok") + "\nMCP server disconnected\n"
    env = find_result_envelope(text)
    assert env is not None and env["result"] == "ok"


def test_find_result_envelope_last_line_wins_when_multiple_present():
    """Documented behavior: the LAST line that parses as a result envelope wins (the reviewer can
    append a second round's envelope into the same text)."""
    text = _envelope_line(result="round one") + "\n" + _envelope_line(result="round two") + "\n"
    env = find_result_envelope(text)
    assert env["result"] == "round two"


def test_find_result_envelope_ignores_malformed_json_line():
    """A line that merely starts/ends with braces but isn't valid JSON must not crash extraction."""
    text = "{not valid json at all}\n" + _envelope_line(result="ok") + "\n"
    env = find_result_envelope(text)
    assert env is not None and env["result"] == "ok"


# ============ usage_record: field mapping, missing fields omitted (not zeroed) ============

def test_usage_record_maps_cli_usage_fields_to_output_names():
    env = _envelope(input_tokens=61, output_tokens=62, cache_write=63, cache_read=64, duration_ms=600)
    rec = usage_record(env, stage="implement", model="claude-sonnet-5")
    assert rec["stage"] == "implement"
    assert rec["model"] == "claude-sonnet-5"
    assert rec["duration_ms"] == 600
    assert rec["input_tokens"] == 61
    assert rec["output_tokens"] == 62
    assert rec["cache_write_tokens"] == 63
    assert rec["cache_read_tokens"] == 64


def test_usage_record_model_none_when_falsy():
    env = _envelope()
    rec = usage_record(env, stage="test", model="")
    assert rec["model"] is None


def test_usage_record_omits_missing_usage_fields_rather_than_zeroing():
    """A field the CLI omitted from `usage` is left OUT of the record (additive/forward-compatible),
    not defaulted to 0 — that distinction matters so a later summary sum doesn't silently invent data."""
    env = {"type": "result", "result": "x", "usage": {"input_tokens": 5}}
    rec = usage_record(env, stage="check_repair", model="claude-sonnet-5")
    assert rec["input_tokens"] == 5
    assert "output_tokens" not in rec
    assert "cache_write_tokens" not in rec
    assert "cache_read_tokens" not in rec


def test_usage_record_omits_duration_when_absent():
    env = {"type": "result", "result": "x", "usage": {}}
    rec = usage_record(env, stage="review", model="claude-opus-4-8")
    assert "duration_ms" not in rec


def test_usage_record_handles_missing_usage_object_entirely():
    env = {"type": "result", "result": "x"}
    rec = usage_record(env, stage="review", model="claude-opus-4-8")
    assert rec["stage"] == "review" and rec["model"] == "claude-opus-4-8"
    for k in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens", "duration_ms"):
        assert k not in rec


# ============ process_stage_log: rewrite on success, untouched on failure to parse ============

def test_process_stage_log_rewrites_to_plain_result_text(tmp_path):
    log = tmp_path / "review.md"
    log.write_text(_envelope_line(result="VERDICT: APPROVE") + "\n")
    rec = process_stage_log(log, stage="review", model="claude-opus-4-8")
    assert rec is not None
    assert log.read_text() == "VERDICT: APPROVE"   # rewritten to EXACTLY the plain reply text


def test_process_stage_log_leaves_plain_text_log_untouched(tmp_path):
    log = tmp_path / "review.md"
    original = "VERDICT: APPROVE\n"
    log.write_text(original)
    rec = process_stage_log(log, stage="review", model="claude-opus-4-8")
    assert rec is None
    assert log.read_text() == original             # byte-identical, nothing rewritten


def test_process_stage_log_untouched_with_surrounding_noise_but_no_envelope(tmp_path):
    """Plain-text output mixed with non-JSON noise (the stubbed suite's shape) still yields no
    artifact and no rewrite — degrade, don't guess."""
    log = tmp_path / "implement.log"
    original = "some hook warning\nIMPL did the thing\nanother line\n"
    log.write_text(original)
    rec = process_stage_log(log, stage="implement", model="claude-sonnet-5")
    assert rec is None
    assert log.read_text() == original


def test_process_stage_log_rewrite_survives_surrounding_noise(tmp_path):
    log = tmp_path / "implement.log"
    log.write_text("hook warning line\n" + _envelope_line(result="did the thing") + "\ntrailer noise\n")
    rec = process_stage_log(log, stage="implement", model="claude-sonnet-5")
    assert rec is not None
    assert log.read_text() == "did the thing"


def test_process_stage_log_empty_result_field_rewrites_to_empty_string(tmp_path):
    log = tmp_path / "x.log"
    log.write_text(json.dumps({"type": "result", "usage": {}}) + "\n")
    rec = process_stage_log(log, stage="x", model="m")
    assert rec is not None
    assert log.read_text() == ""


# ============ load_usage_records: aggregate discovery, skip the summary + corrupt files ============

def test_load_usage_records_reads_all_usage_files_sorted(tmp_path):
    (tmp_path / "usage-test.json").write_text(json.dumps({"stage": "test"}))
    (tmp_path / "usage-implement.json").write_text(json.dumps({"stage": "implement"}))
    (tmp_path / "usage-review.json").write_text(json.dumps({"stage": "review"}))
    records = load_usage_records(tmp_path)
    assert [r["stage"] for r in records] == ["implement", "review", "test"]   # filename-sorted


def test_load_usage_records_excludes_the_aggregate_summary_file(tmp_path):
    (tmp_path / "usage-implement.json").write_text(json.dumps({"stage": "implement"}))
    (tmp_path / "usage-summary.json").write_text(json.dumps({"stages": [], "totals": {}}))
    records = load_usage_records(tmp_path)
    assert len(records) == 1 and records[0]["stage"] == "implement"


def test_load_usage_records_skips_corrupt_file_without_crashing(tmp_path):
    (tmp_path / "usage-implement.json").write_text(json.dumps({"stage": "implement"}))
    (tmp_path / "usage-broken.json").write_text("{not valid json")
    records = load_usage_records(tmp_path)
    assert len(records) == 1 and records[0]["stage"] == "implement"


def test_load_usage_records_empty_when_no_artifacts(tmp_path):
    assert load_usage_records(tmp_path) == []


def test_load_usage_records_suffixed_second_review_round_both_counted(tmp_path):
    """The reviewer can run twice into the same log; the second round's artifact is suffixed
    (usage-review-2.json) rather than overwriting the first, so both are counted."""
    (tmp_path / "usage-review.json").write_text(json.dumps({"stage": "review", "input_tokens": 10}))
    (tmp_path / "usage-review-2.json").write_text(json.dumps({"stage": "review-2", "input_tokens": 20}))
    records = load_usage_records(tmp_path)
    assert len(records) == 2
    assert sum(r["input_tokens"] for r in records) == 30


# ============ build_summary: totals ============

def test_build_summary_sums_totals_across_stages():
    records = [
        {"stage": "implement", "input_tokens": 10, "output_tokens": 20, "cache_write_tokens": 1, "cache_read_tokens": 2},
        {"stage": "test", "input_tokens": 5, "output_tokens": 6, "cache_write_tokens": 0, "cache_read_tokens": 1},
    ]
    summary = build_summary(records)
    assert summary["stages"] == records
    assert summary["totals"] == {
        "input_tokens": 15, "output_tokens": 26, "cache_write_tokens": 1, "cache_read_tokens": 3,
    }


def test_build_summary_treats_missing_fields_as_zero_in_totals():
    records = [{"stage": "implement"}]   # no usage fields at all (e.g. the CLI omitted them)
    summary = build_summary(records)
    assert summary["totals"] == {
        "input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0,
    }


def test_build_summary_empty_records_yields_zero_totals():
    summary = build_summary([])
    assert summary["stages"] == []
    assert all(v == 0 for v in summary["totals"].values())


# ============ render_summary_comment: no YR- marker grammar, degrade message ============

def test_render_summary_comment_opens_with_the_dev_runner_usage_header():
    summary = build_summary([])
    comment = render_summary_comment(summary)
    assert comment.splitlines()[0] == "### dev-runner usage"


def test_render_summary_comment_never_contains_yr_marker_grammar():
    """The usage comment must never contain the string YR-MERGE (nor open with any YR- marker line)
    — that grammar belongs solely to tools/merge_shadow.py."""
    records = [{"stage": "implement", "model": "claude-sonnet-5", "input_tokens": 1, "output_tokens": 2,
                "cache_write_tokens": 3, "cache_read_tokens": 4, "duration_ms": 500}]
    comment = render_summary_comment(build_summary(records))
    assert "YR-MERGE" not in comment
    assert "YR-" not in comment
    assert not comment.splitlines()[0].startswith("YR-")


def test_render_summary_comment_says_so_when_zero_artifacts():
    comment = render_summary_comment(build_summary([]))
    assert "no per-stage usage artifacts" in comment.lower()


def test_render_summary_comment_includes_per_stage_row_and_totals():
    records = [{"stage": "implement", "model": "claude-sonnet-5", "input_tokens": 61, "output_tokens": 62,
                "cache_write_tokens": 63, "cache_read_tokens": 64, "duration_ms": 600}]
    comment = render_summary_comment(build_summary(records))
    assert "implement" in comment and "claude-sonnet-5" in comment
    assert "61" in comment and "62" in comment and "63" in comment and "64" in comment


def test_render_summary_comment_includes_fenced_raw_json():
    summary = build_summary([{"stage": "implement", "input_tokens": 1}])
    comment = render_summary_comment(summary)
    assert "```json" in comment and "```" in comment.split("```json", 1)[1]
    fenced = comment.split("```json", 1)[1].rsplit("```", 1)[0]
    assert json.loads(fenced) == summary


# ============ CLI: extract / summarize (the exact entry points dev-runner.sh shells out to) ============

def _run_cli(*args):
    return subprocess.run([sys.executable, str(STAGE_USAGE_PY), *args],
                          capture_output=True, text=True)


def test_cli_extract_writes_usage_artifact_and_rewrites_log_on_envelope(tmp_path):
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(result="did it", input_tokens=1, output_tokens=2,
                                   cache_write=3, cache_read=4, duration_ms=99) + "\n")
    out = tmp_path / "usage-implement.json"
    r = _run_cli("extract", "--log", str(log), "--stage", "implement", "--model", "claude-sonnet-5", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert log.read_text() == "did it"
    artifact = json.loads(out.read_text())
    assert artifact == {"stage": "implement", "model": "claude-sonnet-5", "duration_ms": 99,
                         "input_tokens": 1, "output_tokens": 2, "cache_write_tokens": 3, "cache_read_tokens": 4}


def test_cli_extract_nonzero_exit_and_no_artifact_on_plain_text(tmp_path):
    log = tmp_path / "implement.log"
    log.write_text("plain reply, no envelope\n")
    out = tmp_path / "usage-implement.json"
    r = _run_cli("extract", "--log", str(log), "--stage", "implement", "--model", "claude-sonnet-5", "--out", str(out))
    assert r.returncode != 0
    assert not out.exists()
    assert log.read_text() == "plain reply, no envelope\n"   # untouched


def test_cli_summarize_aggregates_run_dir_into_json_and_comment(tmp_path):
    (tmp_path / "usage-implement.json").write_text(json.dumps(
        {"stage": "implement", "model": "claude-sonnet-5", "input_tokens": 61, "output_tokens": 62,
         "cache_write_tokens": 63, "cache_read_tokens": 64, "duration_ms": 600}))
    (tmp_path / "usage-review.json").write_text(json.dumps(
        {"stage": "review", "model": "claude-opus-4-8", "input_tokens": 21, "output_tokens": 22,
         "cache_write_tokens": 23, "cache_read_tokens": 24, "duration_ms": 200}))
    out_json = tmp_path / "usage-summary.json"
    out_comment = tmp_path / "usage-summary.md"
    r = _run_cli("summarize", "--run-dir", str(tmp_path), "--out-json", str(out_json), "--out-comment", str(out_comment))
    assert r.returncode == 0, r.stderr
    summary = json.loads(out_json.read_text())
    assert summary["totals"] == {"input_tokens": 82, "output_tokens": 84, "cache_write_tokens": 86, "cache_read_tokens": 88}
    comment = out_comment.read_text()
    assert comment.splitlines()[0] == "### dev-runner usage"
    assert "YR-MERGE" not in comment
    assert "implement" in comment and "review" in comment


def test_cli_summarize_with_zero_artifacts_still_succeeds_and_says_so(tmp_path):
    out_json = tmp_path / "usage-summary.json"
    out_comment = tmp_path / "usage-summary.md"
    r = _run_cli("summarize", "--run-dir", str(tmp_path), "--out-json", str(out_json), "--out-comment", str(out_comment))
    assert r.returncode == 0, r.stderr
    assert json.loads(out_json.read_text())["stages"] == []
    assert "no per-stage usage artifacts" in out_comment.read_text().lower()
