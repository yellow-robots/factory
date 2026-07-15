"""Tests for tools/ledger.py — stage transcript archiving + the runner-owned transcript retention cap
(issue #205, slice 1 of epic yellow-robots/factory#204).

Derived from the CRITERIA (the spec), not the implementation's internals:
  * a completed stage's session transcript is resolved from its log's result envelope (session_id,
    extracted via tools/stage_usage.py's find_result_envelope — never a cloned parser) when that names a
    real file under the CLI project slug dir; otherwise the newest .jsonl there (a heuristic, always so
    labeled) — even when a session_id names a file that doesn't exist, or a newer decoy file is present;
    skipping only when that dir is absent or empty;
  * archiving is byte-faithful (no redaction) and fail-soft throughout — never raises, even given a bad
    source, a missing log, or an unwritable destination;
  * prune deletes ONLY transcript-*.jsonl under a runs/ dir: first anything older than the age cap, then
    (oldest mtime first) whatever's left above the size cap — never another run-dir artifact — and is
    itself fail-soft (a delete failure is recorded, never raised, never a nonzero CLI exit);
  * the age/size tunables read LEDGER_TRANSCRIPT_MAX_AGE_DAYS / LEDGER_TRANSCRIPT_MAX_GB from the
    environment as argparse DEFAULTS, so an explicit CLI flag still wins over both.

Exercises the module's public functions directly, and its CLI (`archive` / `prune`) as a subprocess — the
same two entry points tools/dev-runner.sh shells out to.
"""
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ledger  # noqa: E402
import registry  # noqa: E402
import stage_usage  # noqa: E402

LEDGER_PY = ROOT / "tools" / "ledger.py"


def _run_cli(*args, env=None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(LEDGER_PY), *args],
                          capture_output=True, text=True, env=full_env)


def _touch(path, *, days_ago=0, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    t = time.time() - days_ago * 86400
    os.utime(path, (t, t))
    return path


def _envelope_line(**kw):
    d = {"type": "result", "subtype": "success", "is_error": False, "result": "ok",
         "usage": {"input_tokens": 1, "output_tokens": 2}}
    d.update(kw)
    return json.dumps(d)


# ============ resolve_transcript: session_id resolution, heuristic fallback, skip reasons ============

def test_resolve_transcript_uses_session_id_when_it_names_an_existing_file(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = slug_dir / "sess-1.jsonl"; target.write_text("the session transcript\n")
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="sess-1") + "\n")
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == target and method == "session_id"


def test_resolve_transcript_session_id_wins_even_when_a_newer_file_exists(tmp_path):
    """session_id resolution must not be a mere tiebreaker among candidates — it takes priority over the
    heuristic-newest fallback outright, even when a newer, unrelated file sits in the same dir."""
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = _touch(slug_dir / "sess-1.jsonl", days_ago=1, content=b"session file\n")
    _touch(slug_dir / "decoy.jsonl", days_ago=0, content=b"decoy\n")   # newer than target
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="sess-1") + "\n")
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == target and method == "session_id"


def test_resolve_transcript_falls_back_to_heuristic_when_session_id_file_missing(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    newest = _touch(slug_dir / "newest.jsonl", days_ago=0)
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="does-not-exist") + "\n")
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == newest and method == "heuristic-newest"


def test_resolve_transcript_falls_back_to_heuristic_when_no_envelope_at_all(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    newest = _touch(slug_dir / "newest.jsonl", days_ago=0)
    log = tmp_path / "implement.log"
    log.write_text("plain text, no envelope\n")
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == newest and method == "heuristic-newest"


def test_resolve_transcript_falls_back_to_heuristic_when_envelope_has_no_session_id(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    newest = _touch(slug_dir / "newest.jsonl", days_ago=0)
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line() + "\n")   # a well-formed envelope, but no session_id key at all
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == newest and method == "heuristic-newest"


def test_resolve_transcript_heuristic_picks_the_most_recently_modified_file(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    _touch(slug_dir / "older.jsonl", days_ago=2)
    newest = _touch(slug_dir / "newer.jsonl", days_ago=0)
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == newest and method == "heuristic-newest"


def test_resolve_transcript_none_when_slug_dir_absent(tmp_path):
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    path, reason = ledger.resolve_transcript(log, tmp_path / "does-not-exist")
    assert path is None and "absent" in reason


def test_resolve_transcript_none_when_slug_dir_empty(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    path, reason = ledger.resolve_transcript(log, slug_dir)
    assert path is None and "empty" in reason


def test_resolve_transcript_tolerates_surrounding_noise_around_the_envelope(tmp_path):
    """Envelope extraction goes through tools/stage_usage.py's find_result_envelope, so the same
    noise-tolerance (stray hook/MCP warning lines mixed into a stage log) applies here too."""
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = slug_dir / "sess-2.jsonl"; target.write_text("noisy-log transcript\n")
    log = tmp_path / "implement.log"
    log.write_text("Warning: some hook fired\n" + _envelope_line(session_id="sess-2") + "\nMCP disconnected\n")
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == target and method == "session_id"


# ============ archive_transcript: byte-faithful copy, skip/error reporting, never raises ============

def test_archive_transcript_copies_byte_faithfully(tmp_path):
    """No redaction (ruled 2026-07-15): the archive copies the source byte-for-byte, including
    non-ASCII content a naive text round-trip could mangle."""
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = slug_dir / "sess-1.jsonl"
    content = '{"type":"assistant","message":{"content":[{"type":"text","text":"hello ☃"}]}}\n'
    target.write_text(content, encoding="utf-8")
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="sess-1") + "\n")
    dest = tmp_path / "transcript-implement.jsonl"
    result = ledger.archive_transcript(log, slug_dir, dest)
    assert result["status"] == "archived" and result["method"] == "session_id"
    assert dest.read_text(encoding="utf-8") == content


def test_archive_transcript_skipped_status_and_reason_when_nothing_resolvable(tmp_path):
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    dest = tmp_path / "transcript-implement.jsonl"
    result = ledger.archive_transcript(log, tmp_path / "absent-slug", dest)
    assert result["status"] == "skipped"
    assert "absent" in result["reason"]
    assert not dest.exists()


def test_archive_transcript_skipped_reason_distinguishes_empty_dir(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    dest = tmp_path / "transcript-implement.jsonl"
    result = ledger.archive_transcript(log, slug_dir, dest)
    assert result["status"] == "skipped"
    assert "empty" in result["reason"]
    assert not dest.exists()


def test_archive_transcript_never_raises_on_nonexistent_log_path(tmp_path):
    result = ledger.archive_transcript(tmp_path / "does-not-exist.log", tmp_path / "slug", tmp_path / "out.jsonl")
    assert result["status"] == "error"
    assert "reason" in result


def test_archive_transcript_never_raises_when_source_is_unreadable(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = slug_dir / "sess-1.jsonl"; target.write_text("secret\n")
    try:
        target.chmod(0o000)
        log = tmp_path / "implement.log"
        log.write_text(_envelope_line(session_id="sess-1") + "\n")
        dest = tmp_path / "transcript-implement.jsonl"
        result = ledger.archive_transcript(log, slug_dir, dest)
        assert result["status"] == "error"
        assert not dest.exists()
    finally:
        target.chmod(0o644)


def test_archive_transcript_never_raises_when_dest_parent_missing(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = slug_dir / "sess-1.jsonl"; target.write_text("x\n")
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="sess-1") + "\n")
    dest = tmp_path / "no-such-dir" / "transcript-implement.jsonl"
    result = ledger.archive_transcript(log, slug_dir, dest)
    assert result["status"] == "error"


def test_archive_transcript_reports_heuristic_method_on_fallback(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    _touch(slug_dir / "newest.jsonl", days_ago=0, content=b"latest\n")
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    dest = tmp_path / "transcript-implement.jsonl"
    result = ledger.archive_transcript(log, slug_dir, dest)
    assert result["status"] == "archived" and result["method"] == "heuristic-newest"
    assert dest.read_bytes() == b"latest\n"


# ============ prune_transcripts: age rule, then size rule oldest-first, touches nothing else ============

def test_prune_deletes_transcripts_older_than_max_age(tmp_path):
    runs = tmp_path / "runs"
    old = _touch(runs / "1-run" / "transcript-implement.jsonl", days_ago=100)
    young = _touch(runs / "2-run" / "transcript-implement.jsonl", days_ago=1)
    result = ledger.prune_transcripts(runs, max_age_days=90, max_gb=10)
    assert not old.exists()
    assert young.exists()
    assert str(old) in result["deleted"]


def test_prune_never_touches_non_transcript_files(tmp_path):
    runs = tmp_path / "runs"
    old_transcript = _touch(runs / "1-run" / "transcript-implement.jsonl", days_ago=100)
    old_usage = _touch(runs / "1-run" / "usage-implement.json", days_ago=100)
    old_log = _touch(runs / "1-run" / "implement.log", days_ago=100)
    ledger.prune_transcripts(runs, max_age_days=90, max_gb=10)
    assert not old_transcript.exists()
    assert old_usage.exists()
    assert old_log.exists()


def test_prune_size_rule_deletes_oldest_first_above_the_cap(tmp_path):
    runs = tmp_path / "runs"
    # three same-size, recent (within the age cap) files; a tiny max_gb forces the size rule to act
    oldest = _touch(runs / "1-run" / "transcript-a.jsonl", days_ago=3, content=b"x" * 1000)
    middle = _touch(runs / "2-run" / "transcript-b.jsonl", days_ago=2, content=b"x" * 1000)
    newest = _touch(runs / "3-run" / "transcript-c.jsonl", days_ago=1, content=b"x" * 1000)
    max_gb = 1500 / (1024 ** 3)   # room for only one of the three files
    result = ledger.prune_transcripts(runs, max_age_days=90, max_gb=max_gb)
    assert not oldest.exists()
    assert not middle.exists()
    assert newest.exists()             # the newest survives — oldest-first deletion order
    assert str(oldest) in result["deleted"]
    assert str(middle) in result["deleted"]


def test_prune_size_rule_only_applies_after_age_rule_removes_expired_files(tmp_path):
    """An old, oversized file is removed by the AGE rule; the size rule then only has to consider what's
    left, so a young file within budget survives even though the pre-age-prune total would have exceeded
    the cap."""
    runs = tmp_path / "runs"
    ancient = _touch(runs / "1-run" / "transcript-old.jsonl", days_ago=200, content=b"x" * 10_000)
    young = _touch(runs / "2-run" / "transcript-young.jsonl", days_ago=1, content=b"x" * 10)
    max_gb = 10_000 / (1024 ** 3)   # exceeded by ancient+young together, not by young alone
    ledger.prune_transcripts(runs, max_age_days=90, max_gb=max_gb)
    assert not ancient.exists()   # removed by the AGE rule
    assert young.exists()         # never touched by the size rule once ancient is already gone


def test_prune_keeps_everything_within_both_caps(tmp_path):
    kept = _touch(tmp_path / "runs" / "1-run" / "transcript-implement.jsonl", days_ago=1, content=b"x" * 10)
    result = ledger.prune_transcripts(tmp_path / "runs", max_age_days=90, max_gb=10)
    assert kept.exists()
    assert result["deleted"] == []


def test_prune_empty_runs_dir_yields_no_deletions_and_no_errors(tmp_path):
    runs = tmp_path / "runs"; runs.mkdir()
    result = ledger.prune_transcripts(runs, max_age_days=90, max_gb=10)
    assert result["deleted"] == [] and result["errors"] == []


def test_prune_never_raises_on_an_undeletable_file(tmp_path):
    stale = _touch(tmp_path / "runs" / "1-run" / "transcript-locked.jsonl", days_ago=100)
    run_dir = stale.parent
    try:
        run_dir.chmod(0o500)   # r-x only: listing still works, but unlink() (needs write) fails
        result = ledger.prune_transcripts(tmp_path / "runs", max_age_days=90, max_gb=10)
        assert result["errors"]
        assert stale.exists()   # the failed delete leaves the file in place — never raises
    finally:
        run_dir.chmod(0o755)


# ============ CLI: archive / prune (the exact entry points tools/dev-runner.sh shells out to) ============

def test_cli_archive_writes_transcript_and_exits_zero_on_success(tmp_path):
    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    (slug_dir / "sess-1.jsonl").write_text("cli transcript\n")
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="sess-1") + "\n")
    out = tmp_path / "transcript-implement.jsonl"
    r = _run_cli("archive", "--log", str(log), "--slug-dir", str(slug_dir), "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert out.read_text() == "cli transcript\n"
    printed = json.loads(r.stdout)
    assert printed["status"] == "archived"


def test_cli_archive_nonzero_exit_on_skip(tmp_path):
    log = tmp_path / "implement.log"
    log.write_text("plain text\n")
    out = tmp_path / "transcript-implement.jsonl"
    r = _run_cli("archive", "--log", str(log), "--slug-dir", str(tmp_path / "absent"), "--out", str(out))
    assert r.returncode != 0
    assert json.loads(r.stdout)["status"] == "skipped"
    assert not out.exists()


def test_cli_prune_exits_zero_even_when_nothing_to_prune(tmp_path):
    runs = tmp_path / "runs"; runs.mkdir()
    r = _run_cli("prune", "--runs-dir", str(runs))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["deleted"] == []


def test_cli_prune_exits_zero_even_when_a_delete_fails(tmp_path):
    """Fail-soft at the CLI boundary too: a per-file delete error is reported in the JSON payload, never
    turned into a nonzero exit — dev-runner.sh's own `|| true` around this call is belt-and-suspenders,
    not load-bearing."""
    stale = _touch(tmp_path / "runs" / "1-run" / "transcript-locked.jsonl", days_ago=200)
    run_dir = stale.parent
    try:
        run_dir.chmod(0o500)
        r = _run_cli("prune", "--runs-dir", str(tmp_path / "runs"))
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["errors"]
    finally:
        run_dir.chmod(0o755)


def test_cli_prune_default_tunables_match_documented_values():
    assert ledger.DEFAULT_MAX_AGE_DAYS == 90
    assert ledger.DEFAULT_MAX_GB == 10


def test_cli_prune_env_max_age_tunable_overrides_default(tmp_path):
    runs = tmp_path / "runs"
    young = _touch(runs / "1-run" / "transcript-implement.jsonl", days_ago=10)   # < default 90, > env 5
    r = _run_cli("prune", "--runs-dir", str(runs), env={"LEDGER_TRANSCRIPT_MAX_AGE_DAYS": "5"})
    assert r.returncode == 0, r.stderr
    assert not young.exists()


def test_cli_prune_explicit_max_age_flag_wins_over_env_override(tmp_path):
    runs = tmp_path / "runs"
    kept = _touch(runs / "1-run" / "transcript-implement.jsonl", days_ago=10)
    r = _run_cli("prune", "--runs-dir", str(runs), "--max-age-days", "90",
                 env={"LEDGER_TRANSCRIPT_MAX_AGE_DAYS": "5"})
    assert r.returncode == 0, r.stderr
    assert kept.exists()   # the explicit --max-age-days=90 wins over the tighter env default


def test_cli_prune_env_max_gb_tunable_overrides_default(tmp_path):
    runs = tmp_path / "runs"
    oldest = _touch(runs / "1-run" / "transcript-a.jsonl", days_ago=1, content=b"x" * 1000)
    newest = _touch(runs / "2-run" / "transcript-b.jsonl", days_ago=0, content=b"x" * 1000)
    tiny_gb = str(1500 / (1024 ** 3))
    r = _run_cli("prune", "--runs-dir", str(runs), env={"LEDGER_TRANSCRIPT_MAX_GB": tiny_gb})
    assert r.returncode == 0, r.stderr
    assert not oldest.exists()
    assert newest.exists()


def test_cli_prune_explicit_max_gb_flag_wins_over_env_override(tmp_path):
    runs = tmp_path / "runs"
    kept = _touch(runs / "1-run" / "transcript-a.jsonl", days_ago=1, content=b"x" * 1000)
    r = _run_cli("prune", "--runs-dir", str(runs), "--max-gb", "10",
                 env={"LEDGER_TRANSCRIPT_MAX_GB": str(1500 / (1024 ** 3))})
    assert r.returncode == 0, r.stderr
    assert kept.exists()   # the explicit --max-gb=10 wins over the tiny env override


def test_cli_prune_only_deletes_transcript_files_never_other_run_dir_artifacts(tmp_path):
    runs = tmp_path / "runs"
    old_transcript = _touch(runs / "1-run" / "transcript-implement.jsonl", days_ago=200)
    old_usage = _touch(runs / "1-run" / "usage-implement.json", days_ago=200)
    old_toplevel_log = _touch(runs / "dispatch.log", days_ago=200)
    r = _run_cli("prune", "--runs-dir", str(runs))
    assert r.returncode == 0, r.stderr
    assert not old_transcript.exists()
    assert old_usage.exists()
    assert old_toplevel_log.exists()


# ============ import discipline: never a cloned envelope parser ============

def test_ledger_imports_stage_usage_and_never_defines_its_own_envelope_parser():
    """Acceptance: envelope parsing must import tools/stage_usage.py's find_result_envelope — never a
    cloned parser. A source-level guard (the same technique this suite's shared dev-runner tests already
    use for stub-marker guards): ledger.py imports the stage_usage module and calls its
    find_result_envelope, and never defines a same-named function of its own."""
    src = (ROOT / "tools" / "ledger.py").read_text()
    assert "import stage_usage" in src
    assert "stage_usage.find_result_envelope" in src
    assert "def find_result_envelope" not in src


def test_ledger_resolve_transcript_delegates_to_the_real_stage_usage_module(monkeypatch, tmp_path):
    """A behavioral companion to the source guard above: monkeypatching the actual
    tools.stage_usage.find_result_envelope must change resolve_transcript's outcome — proving the
    dependency is real, not merely textual."""
    import stage_usage as real_stage_usage

    slug_dir = tmp_path / "slug"; slug_dir.mkdir()
    target = slug_dir / "sess-1.jsonl"; target.write_text("x\n")
    log = tmp_path / "implement.log"
    log.write_text(_envelope_line(session_id="sess-1") + "\n")

    calls = []
    original = real_stage_usage.find_result_envelope

    def spy(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(real_stage_usage, "find_result_envelope", spy)
    path, method = ledger.resolve_transcript(log, slug_dir)
    assert path == target and method == "session_id"
    assert calls, "ledger.resolve_transcript never called stage_usage.find_result_envelope"


# ============ append (issue #206): one yr-ledger-row/1 JSONL row per runner invocation ==============
# Derived from the CRITERIA (the spec), not the implementation's internals:
#   * the row carries schema/run_id/task/repo/branch/base_sha/models/per-stage usage/totals/outcome/
#     repairs/wall_seconds/ts_start/ts_end, and `task` is whatever the caller passes — NEVER derived
#     from run_dir (build_ledger_row must never raise on a missing/empty run_dir, since the Needs-info
#     bounce calls it before the run dir even exists);
#   * usage covers every usage-*.json artifact (dedup-suffixed rounds included, usage-summary.json
#     excluded — tools/stage_usage.py's own loader), PLUS a read-only envelope fallback for a stage
#     whose log still holds an unextracted result envelope (an rc != 0 stage), assigned the next free
#     dedup suffix when its stage name is already taken — never overwriting or double-counting;
#   * weighted totals use stage_usage.WEIGHTED_TOTAL_WEIGHTS/build_summary unchanged;
#   * a shadow-review-seat stage (shadow-review*.md, scanned only when shadow_model is set) is recorded
#     in the per-stage array but excluded from totals.weighted_total, and never causes the row to be
#     skipped even carrying an unregistered model id;
#   * repairs are counted by ARTIFACT NAME (repair.log / review-repair.log), never by usage-*-N.json
#     suffix (a second review round is not itself a "review repair");
#   * append_row holds a blocking flock so concurrent writers each land exactly one, uninterleaved row.

def _usage_file(run_dir, stage, **kw):
    d = {"stage": stage, "model": "claude-sonnet-5", "duration_ms": 100,
         "input_tokens": 10, "output_tokens": 20, "cache_write_tokens": 0, "cache_read_tokens": 0}
    d.update(kw)
    pathlib.Path(run_dir).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(run_dir) / f"usage-{stage}.json").write_text(json.dumps(d))
    return d


def _build_row(run_dir, *, outcome_type="merged", outcome_decision="MERGED", **overrides):
    kw = dict(run_id="5-1234", task="acme/widgets#5", repo="acme/widgets", branch="task/5-x",
              base_sha="a" * 40, run_dir=run_dir, build_model="claude-sonnet-5",
              review_model="claude-opus-4-8", check_repair_model="", review_repair_model="",
              shadow_model="", outcome_type=outcome_type, outcome_decision=outcome_decision,
              ts_start="2026-01-01T00:00:00Z", ts_end="2026-01-01T00:05:00Z", wall_seconds=300)
    kw.update(overrides)
    return ledger.build_ledger_row(**kw)


def test_build_ledger_row_basic_shape_and_schema(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement")
    row = _build_row(run_dir)
    assert row["schema"] == "yr-ledger-row/1"
    assert row["run_id"] == "5-1234"
    assert row["task"] == "acme/widgets#5"
    assert row["repo"] == "acme/widgets"
    assert row["branch"] == "task/5-x"
    assert row["base_sha"] == "a" * 40
    assert row["models"] == {"build": "claude-sonnet-5", "review": "claude-opus-4-8"}
    assert row["outcome"] == {"type": "merged", "decision": "MERGED"}
    assert row["repairs"] == {"check": 0, "review": 0}
    assert row["wall_seconds"] == 300
    assert row["ts_start"] == "2026-01-01T00:00:00Z" and row["ts_end"] == "2026-01-01T00:05:00Z"
    assert len(row["stages"]) == 1
    stage = row["stages"][0]
    assert stage["stage"] == "implement" and stage["source"] == "usage-file"
    assert "weighted_total" in stage


def test_build_ledger_row_task_is_never_derived_from_run_dir(tmp_path):
    """The run dir basename ('999-9999') carries no repo/issue semantics of its own — task must be
    exactly whatever the caller passes, never parsed or reconstructed from the run dir path."""
    run_dir = tmp_path / "runs" / "999-9999"
    row = _build_row(run_dir, task="other-owner/other-repo#42", outcome_type="needs-info",
                      outcome_decision="")
    assert row["task"] == "other-owner/other-repo#42"


def test_build_ledger_row_never_raises_on_missing_run_dir(tmp_path):
    """The Needs-info bounce calls this BEFORE the run dir is ever created (tools/dev-runner.sh mkdirs
    RUN_DIR only after claim) — an absent run_dir must yield an empty stage array, never an error."""
    row = _build_row(tmp_path / "does-not-exist", outcome_type="needs-info", outcome_decision="")
    assert row["schema"] == "yr-ledger-row/1"
    assert row["stages"] == []
    assert row["totals"]["weighted_total"] == 0


def test_build_ledger_row_weighted_totals_use_stage_usage_census_weights(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", input_tokens=100, output_tokens=10, cache_write_tokens=8,
                cache_read_tokens=1000)
    row = _build_row(run_dir)
    expected = round(sum(stage_usage.WEIGHTED_TOTAL_WEIGHTS[k] * v for k, v in
                          {"input_tokens": 100, "output_tokens": 10, "cache_write_tokens": 8,
                           "cache_read_tokens": 1000}.items()))
    assert row["stages"][0]["weighted_total"] == expected
    assert row["totals"]["weighted_total"] == expected
    assert row["totals"]["input_tokens"] == 100   # build_summary's own totals carried through too


def test_build_ledger_row_includes_all_dedup_suffixed_usage_files(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "review", input_tokens=11)
    _usage_file(run_dir, "review-2", input_tokens=21)
    _usage_file(run_dir, "review-3", input_tokens=31)
    row = _build_row(run_dir, outcome_type="in-review", outcome_decision="")
    stages = {s["stage"] for s in row["stages"]}
    assert stages == {"review", "review-2", "review-3"}
    assert row["totals"]["input_tokens"] == 11 + 21 + 31


def test_build_ledger_row_excludes_the_aggregate_usage_summary_file(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement")
    (run_dir / "usage-summary.json").write_text(json.dumps({"stages": [], "totals": {}, "weighted_total": 0}))
    row = _build_row(run_dir)
    assert {s["stage"] for s in row["stages"]} == {"implement"}


def test_build_ledger_row_reads_failed_stage_via_envelope_without_rewriting_log(tmp_path):
    """rc != 0: capture_stage_usage never ran, so implement.log still holds the raw result envelope —
    the fallback must read it (never rewrite it) and still produce a per-stage record."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    envelope_text = _envelope_line(session_id="s1") + "\n"
    log = run_dir / "implement.log"
    log.write_text(envelope_text)
    row = _build_row(run_dir, outcome_type="blocked", outcome_decision="")
    assert log.read_text() == envelope_text   # byte-identical — never rewritten
    stages = {s["stage"]: s for s in row["stages"]}
    assert "implement" in stages
    assert stages["implement"]["source"] == "envelope"
    assert stages["implement"]["input_tokens"] == 1   # _envelope_line's default usage


def test_build_ledger_row_envelope_fallback_gets_next_dedup_suffix_when_stage_name_taken(tmp_path):
    """A second review round that failed after the first round already succeeded: usage-review.json
    (round 1, extracted) plus a still-raw review.md (round 2, rc != 0, overwritten in place — the same
    dedup-on-write convention capture_stage_usage's OWN output filename uses) must land as review AND
    review-2, never overwriting or double-counting the first round."""
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "review", input_tokens=11)
    (run_dir / "review.md").write_text(_envelope_line(session_id="s2") + "\n")
    row = _build_row(run_dir, outcome_type="blocked", outcome_decision="")
    stages = {s["stage"]: s for s in row["stages"]}
    assert stages["review"]["input_tokens"] == 11 and stages["review"]["source"] == "usage-file"
    assert stages["review-2"]["input_tokens"] == 1 and stages["review-2"]["source"] == "envelope"


def test_build_ledger_row_repairs_counted_by_artifact_presence(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "repair.log").write_text("x")
    (run_dir / "review-repair.log").write_text("x")
    row = _build_row(run_dir)
    assert row["repairs"] == {"check": 1, "review": 1}


def test_build_ledger_row_repairs_zero_when_no_repair_artifacts(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    row = _build_row(run_dir)
    assert row["repairs"] == {"check": 0, "review": 0}


def test_build_ledger_row_repairs_never_confused_with_a_suffixed_review_round(tmp_path):
    """A second review round's own usage-review-2.json (a normal repair cycle, or the shadow seat) must
    NOT itself be counted as a review repair — only review-repair.log/usage-review-repair.json does."""
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "review", input_tokens=1)
    _usage_file(run_dir, "review-2", input_tokens=1)
    row = _build_row(run_dir)
    assert row["repairs"]["review"] == 0


def test_build_ledger_row_shadow_stage_recorded_but_excluded_from_totals(tmp_path):
    """A shadow-review-seat stage is recorded in the per-stage array (tagged with its own, possibly
    unregistered, model) but excluded from the run's weighted total — and never causes the row itself
    to be skipped."""
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", input_tokens=100)
    (run_dir / "shadow-review.md").write_text(_envelope_line(session_id="sh1") + "\n")
    row = _build_row(run_dir, shadow_model="some-unregistered-cross-vendor-model")
    stages = {s["stage"]: s for s in row["stages"]}
    assert "shadow-review" in stages
    assert stages["shadow-review"]["model"] == "some-unregistered-cross-vendor-model"
    assert stages["shadow-review"]["source"] == "envelope"
    # totals reflect ONLY the non-shadow stage — the shadow stage never folds into the census total.
    assert row["totals"]["weighted_total"] == stages["implement"]["weighted_total"]
    assert row["totals"]["input_tokens"] == 100


def test_build_ledger_row_shadow_files_ignored_when_the_seat_is_dark(tmp_path):
    """Dark by default (no shadow_model passed): a stray shadow-review*.md is never even scanned."""
    run_dir = tmp_path / "run"
    (run_dir / "shadow-review.md").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "shadow-review.md").write_text(_envelope_line(session_id="sh1") + "\n")
    row = _build_row(run_dir, shadow_model="")
    assert row["stages"] == []


def test_build_ledger_row_second_shadow_round_dedup_suffixed(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir).mkdir(parents=True, exist_ok=True)
    (run_dir / "shadow-review.md").write_text(_envelope_line(session_id="sh1") + "\n")
    (run_dir / "shadow-review-2.md").write_text(_envelope_line(session_id="sh2") + "\n")
    row = _build_row(run_dir, shadow_model="acme/shadow-model")
    stages = {s["stage"] for s in row["stages"]}
    assert stages == {"shadow-review", "shadow-review-2"}
    assert row["totals"]["weighted_total"] == 0   # both shadow rounds excluded from the census total


def test_append_row_creates_ledger_dir_and_writes_one_line(tmp_path):
    ledger_dir = tmp_path / "nested" / "ledger"
    row = {"schema": ledger.ROW_SCHEMA, "run_id": "x"}
    path = ledger.append_row(ledger_dir, row)
    assert path == ledger_dir / "rows.jsonl"
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == row


def test_append_row_appends_without_clobbering_prior_rows(tmp_path):
    ledger_dir = tmp_path / "ledger"
    ledger.append_row(ledger_dir, {"schema": ledger.ROW_SCHEMA, "run_id": "a"})
    ledger.append_row(ledger_dir, {"schema": ledger.ROW_SCHEMA, "run_id": "b"})
    lines = (ledger_dir / "rows.jsonl").read_text().splitlines()
    assert [json.loads(l)["run_id"] for l in lines] == ["a", "b"]


def test_append_row_concurrent_appends_never_interleave(tmp_path):
    """Acceptance: the append holds a BLOCKING flock because a row can exceed PIPE_BUF — proven here by
    padding every row well past the typical 4096-byte PIPE_BUF, firing N writers at once (a Barrier so
    they all hit the lock together, not staggered), and requiring every line to still parse as valid,
    distinct JSON."""
    ledger_dir = tmp_path / "ledger"
    n = 12
    barrier = threading.Barrier(n)
    errors = []

    def worker(i):
        try:
            barrier.wait(timeout=10)
            ledger.append_row(ledger_dir, {"schema": ledger.ROW_SCHEMA, "run_id": f"run-{i}",
                                            "pad": "x" * 20000})
        except Exception as e:  # pragma: no cover - surfaced via `errors` below
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    lines = (ledger_dir / "rows.jsonl").read_text().splitlines()
    assert len(lines) == n   # every writer landed exactly one line — none lost, none interleaved
    parsed = [json.loads(l) for l in lines]   # raises if any line got corrupted by interleaving
    assert sorted(r["run_id"] for r in parsed) == sorted(f"run-{i}" for i in range(n))


def test_cli_append_concurrent_processes_never_interleave(tmp_path):
    """The same guarantee across independent OS processes (concurrent builds), through the exact CLI
    entry point tools/dev-runner.sh shells out to."""
    ledger_dir = tmp_path / "ledger"
    n = 8
    procs = []
    for i in range(n):
        run_dir = tmp_path / f"run-{i}"
        run_dir.mkdir()
        procs.append(subprocess.Popen(
            [sys.executable, str(LEDGER_PY), "append",
             "--ledger-dir", str(ledger_dir), "--run-id", f"run-{i}", "--task", f"test/repo#{i}",
             "--repo", "test/repo", "--run-dir", str(run_dir), "--outcome-type", "merged",
             "--outcome-decision", "MERGED", "--ts-start", "t0", "--ts-end", "t1", "--wall-seconds", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    for p in procs:
        rc = p.wait(timeout=30)
        assert rc == 0, p.stderr.read()
    lines = (ledger_dir / "rows.jsonl").read_text().splitlines()
    assert len(lines) == n
    parsed = [json.loads(l) for l in lines]
    assert sorted(r["run_id"] for r in parsed) == sorted(f"run-{i}" for i in range(n))


def test_cli_append_writes_a_row_and_exits_zero(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger_dir = tmp_path / "ledger"
    r = _run_cli("append", "--ledger-dir", str(ledger_dir), "--run-id", "5-123",
                 "--task", "acme/widgets#5", "--repo", "acme/widgets", "--branch", "task/5-x",
                 "--base-sha", "a" * 40, "--run-dir", str(run_dir),
                 "--build-model", "claude-sonnet-5", "--review-model", "claude-opus-4-8",
                 "--outcome-type", "merged", "--outcome-decision", "MERGED",
                 "--ts-start", "2026-01-01T00:00:00Z", "--ts-end", "2026-01-01T00:05:00Z",
                 "--wall-seconds", "300")
    assert r.returncode == 0, r.stderr
    rows = [json.loads(l) for l in (ledger_dir / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "5-123" and rows[0]["task"] == "acme/widgets#5"
    assert rows[0]["outcome"] == {"type": "merged", "decision": "MERGED"}


def test_cli_append_optional_fields_default_to_none_not_empty_string(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger_dir = tmp_path / "ledger"
    r = _run_cli("append", "--ledger-dir", str(ledger_dir), "--run-id", "7-1", "--task", "o/r#7",
                 "--repo", "o/r", "--run-dir", str(run_dir), "--outcome-type", "needs-info",
                 "--ts-start", "t0", "--ts-end", "t1", "--wall-seconds", "0")
    assert r.returncode == 0, r.stderr
    row = json.loads((ledger_dir / "rows.jsonl").read_text().splitlines()[0])
    assert row["branch"] is None and row["base_sha"] is None and row["outcome"]["decision"] is None


def test_cli_append_succeeds_even_when_run_dir_does_not_exist(tmp_path):
    """The Needs-info bounce calls this before RUN_DIR is ever created — the CLI must still append a
    (empty-stages) row rather than fail."""
    ledger_dir = tmp_path / "ledger"
    r = _run_cli("append", "--ledger-dir", str(ledger_dir), "--run-id", "1-1", "--task", "o/r#1",
                 "--repo", "o/r", "--run-dir", str(tmp_path / "no-such-run-dir"),
                 "--outcome-type", "needs-info", "--ts-start", "t0", "--ts-end", "t1",
                 "--wall-seconds", "0")
    assert r.returncode == 0, r.stderr
    rows = [json.loads(l) for l in (ledger_dir / "rows.jsonl").read_text().splitlines()]
    assert rows[0]["stages"] == []


# ============ issue #207: the price snapshot + shadow_cost_usd (build_ledger_row) ====================
# Derived from the CRITERIA (the spec), not the implementation's internals:
#   * each stage's `price` is the registry's input_price_per_mtok for that stage's OWN model id — never
#     the role — null when the id is unregistered (never an error, never skips the stage or the row);
#   * totals.shadow_cost_usd = sum(weighted_total x price) over non-shadow, priced stages only — an
#     unpriced or shadow-review-seat stage contributes nothing to the sum, but is never dropped from
#     `stages` or from the raw-count totals;
#   * the price is snapshotted onto the row itself, so shadow_cost_usd is reproducible by summing the
#     row's own stored per-stage price x weighted_total — a read over the row, not a re-run of the build.

def test_build_ledger_row_stage_price_snapshot_matches_registry_list_price(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="claude-sonnet-5")
    row = _build_row(run_dir)
    assert row["stages"][0]["price"] == 3.00


def test_build_ledger_row_stage_price_is_null_for_an_unregistered_model(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="some-unregistered-model")
    row = _build_row(run_dir)
    assert row["stages"][0]["price"] is None


def test_build_ledger_row_append_never_skips_a_row_over_an_unpriceable_model(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="some-unregistered-model", input_tokens=100)
    row = _build_row(run_dir)
    assert len(row["stages"]) == 1
    assert row["stages"][0]["stage"] == "implement"
    assert row["totals"]["shadow_cost_usd"] == 0


def test_build_ledger_row_shadow_cost_usd_is_weighted_total_times_registry_price(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="claude-sonnet-5", input_tokens=100, output_tokens=10,
                cache_write_tokens=8, cache_read_tokens=1000)
    row = _build_row(run_dir)
    weighted_total = row["stages"][0]["weighted_total"]
    assert row["totals"]["shadow_cost_usd"] == weighted_total * 3.00


def test_build_ledger_row_shadow_cost_usd_sums_multiple_priced_stages(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="claude-sonnet-5", input_tokens=1000, output_tokens=0,
                cache_write_tokens=0, cache_read_tokens=0)
    _usage_file(run_dir, "review", model="claude-opus-4-8", input_tokens=0, output_tokens=200,
                cache_write_tokens=0, cache_read_tokens=0)
    row = _build_row(run_dir, outcome_type="in-review", outcome_decision="")
    stages = {s["stage"]: s for s in row["stages"]}
    expected = stages["implement"]["weighted_total"] * 3.00 + stages["review"]["weighted_total"] * 5.00
    assert row["totals"]["shadow_cost_usd"] == expected


def test_build_ledger_row_shadow_cost_usd_excludes_unpriced_stage_but_keeps_its_raw_counts(tmp_path):
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="claude-sonnet-5", input_tokens=1000)
    _usage_file(run_dir, "check", model="some-unregistered-model", input_tokens=5000)
    row = _build_row(run_dir, outcome_type="in-review", outcome_decision="")
    stages = {s["stage"]: s for s in row["stages"]}
    assert stages["check"]["price"] is None
    # only the dollar figure excludes the unpriced stage — its raw tokens still land in totals.
    assert row["totals"]["shadow_cost_usd"] == stages["implement"]["weighted_total"] * 3.00
    assert row["totals"]["input_tokens"] == 1000 + 5000


def test_build_ledger_row_shadow_cost_usd_excludes_shadow_review_seat_stage(tmp_path):
    """Shadow-review-seat stages are already excluded from weighted_total (issue #206); #207 must keep
    them out of shadow_cost_usd too, even when the shadow model happens to carry a registry price."""
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="claude-sonnet-5", input_tokens=1000)
    (run_dir / "shadow-review.md").write_text(_envelope_line(session_id="sh1") + "\n")
    row = _build_row(run_dir, shadow_model="claude-opus-4-8")
    stages = {s["stage"]: s for s in row["stages"]}
    assert "shadow-review" in stages
    assert row["totals"]["shadow_cost_usd"] == stages["implement"]["weighted_total"] * 3.00


def test_build_ledger_row_shadow_cost_recomputable_purely_from_the_rows_own_stored_fields(tmp_path):
    """"the price snapshot SHALL be stored beside the raw counts so rows re-weight as a read, not a
    re-run": summing each non-shadow, priced stage's own stored price x weighted_total, straight off the
    row already on disk, must reproduce totals.shadow_cost_usd exactly — no registry lookup, no
    re-running the build."""
    run_dir = tmp_path / "run"
    _usage_file(run_dir, "implement", model="claude-sonnet-5", input_tokens=1000, output_tokens=50)
    _usage_file(run_dir, "review", model="claude-opus-4-8", input_tokens=10, output_tokens=5)
    row = _build_row(run_dir)
    recomputed = sum(s["weighted_total"] * s["price"] for s in row["stages"]
                      if not s["stage"].startswith("shadow-review") and s.get("price") is not None)
    assert recomputed == row["totals"]["shadow_cost_usd"]


# ============ issue #207: per_model_view — the per-model aggregate view, computable from rows alone ===
# Derived from the CRITERIA: runs, merged (armed 'merged' outcome only — 'shadow-would-merge' lands in
# its own verdict_outcomes bucket, never conflated), weighted-cost-per-merged-task, repair rate (from
# repairs counts), verdict outcomes — keyed by the row's build model, over fixture rows alone (no
# run_dir, no registry, no I/O).

def _row(*, repo="acme/widgets", build_model="claude-sonnet-5", outcome_type="merged",
         shadow_cost_usd=0.0, weighted_total=0, repairs_check=0, repairs_review=0,
         ts_end="2026-01-01T00:00:00Z"):
    return {
        "schema": "yr-ledger-row/1",
        "repo": repo,
        "models": {"build": build_model, "review": "claude-opus-4-8"},
        "outcome": {"type": outcome_type, "decision": None},
        "totals": {"shadow_cost_usd": shadow_cost_usd, "weighted_total": weighted_total},
        "repairs": {"check": repairs_check, "review": repairs_review},
        "ts_end": ts_end,
    }


def test_per_model_view_separates_merged_from_shadow_would_merge():
    rows = [
        _row(build_model="claude-sonnet-5", outcome_type="merged", shadow_cost_usd=10),
        _row(build_model="claude-sonnet-5", outcome_type="merged", shadow_cost_usd=20),
        _row(build_model="claude-sonnet-5", outcome_type="needs-info", shadow_cost_usd=0),
        _row(build_model="claude-opus-4-8", outcome_type="shadow-would-merge", shadow_cost_usd=15,
             repairs_check=1, repairs_review=1),
        _row(build_model="claude-opus-4-8", outcome_type="merged", shadow_cost_usd=5),
    ]
    view = ledger.per_model_view(rows)

    sonnet = view["claude-sonnet-5"]
    assert sonnet["runs"] == 3
    assert sonnet["merged"] == 2
    assert sonnet["weighted_cost_per_merged_task"] == 15   # (10 + 20 + 0) / 2
    assert sonnet["verdict_outcomes"] == {"merged": 2, "needs-info": 1}

    opus = view["claude-opus-4-8"]
    assert opus["runs"] == 2
    assert opus["merged"] == 1   # shadow-would-merge is NEVER counted as merged
    assert opus["weighted_cost_per_merged_task"] == 20   # (15 + 5) / 1
    assert opus["verdict_outcomes"] == {"shadow-would-merge": 1, "merged": 1}


def test_per_model_view_repair_rate_from_repairs_counts():
    rows = [
        _row(build_model="claude-sonnet-5", repairs_check=1, repairs_review=0),
        _row(build_model="claude-sonnet-5", repairs_check=0, repairs_review=1),
        _row(build_model="claude-sonnet-5", repairs_check=0, repairs_review=0),
        _row(build_model="claude-sonnet-5", repairs_check=0, repairs_review=0),
    ]
    view = ledger.per_model_view(rows)
    assert view["claude-sonnet-5"]["repair_rate"] == 0.5   # 2 repairs (check+review) across 4 runs


def test_per_model_view_cost_per_merged_task_is_none_when_nothing_merged():
    rows = [_row(outcome_type="needs-info", shadow_cost_usd=0)]
    view = ledger.per_model_view(rows)
    assert view["claude-sonnet-5"]["merged"] == 0
    assert view["claude-sonnet-5"]["weighted_cost_per_merged_task"] is None


def test_per_model_view_is_computable_from_rows_alone():
    """No run_dir, no registry access, no filesystem I/O — a pure aggregation over the rows list."""
    view = ledger.per_model_view([_row(), _row()])
    assert view["claude-sonnet-5"]["runs"] == 2


# ============ issue #207: the four standing reads, each an executable query over rows alone ==========

# ---- standing read 1: the close-time cost line (total + per-merged-task cost for a repo/window) -----

def test_standing_read_close_time_cost_total_and_per_merged_task():
    rows = [
        _row(repo="acme/widgets", outcome_type="merged", shadow_cost_usd=10, ts_end="2026-01-01T00:00:00Z"),
        _row(repo="acme/widgets", outcome_type="merged", shadow_cost_usd=20, ts_end="2026-01-02T00:00:00Z"),
        _row(repo="acme/widgets", outcome_type="needs-info", shadow_cost_usd=0, ts_end="2026-01-03T00:00:00Z"),
        _row(repo="other/repo", outcome_type="merged", shadow_cost_usd=999, ts_end="2026-01-01T00:00:00Z"),
    ]
    windowed = ledger.filter_rows(rows, repo="acme/widgets")
    result = ledger.close_time_cost(windowed)
    assert result["total_shadow_cost_usd"] == 30
    assert result["merged_count"] == 2
    assert result["cost_per_merged_task"] == 15


def test_standing_read_close_time_cost_windowed_by_ts_end():
    rows = [
        _row(shadow_cost_usd=10, outcome_type="merged", ts_end="2026-01-01T00:00:00Z"),
        _row(shadow_cost_usd=20, outcome_type="merged", ts_end="2026-02-01T00:00:00Z"),
    ]
    windowed = ledger.filter_rows(rows, since="2026-01-15T00:00:00Z")
    result = ledger.close_time_cost(windowed)
    assert result["total_shadow_cost_usd"] == 20
    assert result["merged_count"] == 1


def test_standing_read_close_time_cost_none_per_task_when_nothing_merged():
    rows = [_row(outcome_type="needs-info", shadow_cost_usd=0)]
    result = ledger.close_time_cost(rows)
    assert result["cost_per_merged_task"] is None


# ---- standing read 2: the crossover cost axis (factory-repo vs product-repo, same window) -----------

def test_standing_read_crossover_cost_axis_splits_factory_vs_product_repo():
    rows = [
        _row(repo="yellow-robots/factory", outcome_type="merged", shadow_cost_usd=100),
        _row(repo="yellow-robots/factory", outcome_type="merged", shadow_cost_usd=50),
        _row(repo="acme/widgets", outcome_type="merged", shadow_cost_usd=10),
        _row(repo="other/product", outcome_type="merged", shadow_cost_usd=30),
    ]
    result = ledger.crossover_cost_axis(rows)
    assert result["factory"]["total_shadow_cost_usd"] == 150
    assert result["factory"]["cost_per_merged_task"] == 75
    assert result["product"]["total_shadow_cost_usd"] == 40
    assert result["product"]["cost_per_merged_task"] == 20


def test_standing_read_crossover_cost_axis_respects_a_custom_factory_repo_name():
    rows = [
        _row(repo="mine/factory-fork", outcome_type="merged", shadow_cost_usd=42),
        _row(repo="acme/widgets", outcome_type="merged", shadow_cost_usd=8),
    ]
    result = ledger.crossover_cost_axis(rows, factory_repo="mine/factory-fork")
    assert result["factory"]["total_shadow_cost_usd"] == 42
    assert result["product"]["total_shadow_cost_usd"] == 8


# ---- standing read 3: a trial's before/after (per-model aggregates across two windows) ---------------

def test_standing_read_before_after_trial_compares_per_model_aggregates_across_two_windows():
    rows = [
        _row(build_model="claude-sonnet-5", outcome_type="merged", shadow_cost_usd=10,
             ts_end="2026-01-05T00:00:00Z"),
        _row(build_model="claude-sonnet-5", outcome_type="merged", shadow_cost_usd=30,
             ts_end="2026-02-05T00:00:00Z"),
    ]
    before = ledger.per_model_view(ledger.filter_rows(rows, until="2026-01-31T23:59:59Z"))
    after = ledger.per_model_view(ledger.filter_rows(rows, since="2026-02-01T00:00:00Z"))
    assert before["claude-sonnet-5"]["runs"] == 1
    assert before["claude-sonnet-5"]["weighted_cost_per_merged_task"] == 10
    assert after["claude-sonnet-5"]["runs"] == 1
    assert after["claude-sonnet-5"]["weighted_cost_per_merged_task"] == 30


# ---- standing read 4: the concurrency headroom (weighted tokens per day, across repos) ---------------

def test_standing_read_concurrency_headroom_weighted_tokens_per_day_across_repos():
    rows = [
        _row(repo="a/a", weighted_total=100, ts_end="2026-01-01T10:00:00Z"),
        _row(repo="b/b", weighted_total=50, ts_end="2026-01-01T20:00:00Z"),
        _row(repo="a/a", weighted_total=200, ts_end="2026-01-02T00:00:00Z"),
    ]
    result = ledger.daily_weighted_tokens(rows)
    assert result == {"2026-01-01": 150, "2026-01-02": 200}


def test_standing_read_concurrency_headroom_ignores_rows_with_no_ts_end():
    rows = [_row(weighted_total=100, ts_end="")]
    assert ledger.daily_weighted_tokens(rows) == {}


# ============ issue #207: load_rows / filter_rows — the read-only substrate over rows.jsonl ===========

def test_load_rows_missing_ledger_dir_returns_empty_list(tmp_path):
    assert ledger.load_rows(tmp_path / "does-not-exist") == []


def test_load_rows_skips_unparseable_lines_without_raising(tmp_path):
    ledger_dir = tmp_path / "ledger"; ledger_dir.mkdir()
    (ledger_dir / "rows.jsonl").write_text('{"a": 1}\nnot json\n{"a": 2}\n')
    rows = ledger.load_rows(ledger_dir)
    assert rows == [{"a": 1}, {"a": 2}]


# ============ issue #207: the `per-model` / `report` CLI subcommands over rows.jsonl ===================

def test_cli_per_model_aggregates_over_rows_jsonl(tmp_path):
    ledger_dir = tmp_path / "ledger"; ledger_dir.mkdir()
    rows = [_row(build_model="claude-sonnet-5", outcome_type="merged", shadow_cost_usd=10),
            _row(build_model="claude-sonnet-5", outcome_type="merged", shadow_cost_usd=20)]
    (ledger_dir / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = _run_cli("per-model", "--ledger-dir", str(ledger_dir))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["claude-sonnet-5"]["runs"] == 2
    assert out["claude-sonnet-5"]["weighted_cost_per_merged_task"] == 15


def test_cli_per_model_filters_by_repo(tmp_path):
    ledger_dir = tmp_path / "ledger"; ledger_dir.mkdir()
    rows = [_row(repo="a/a", build_model="claude-sonnet-5"), _row(repo="b/b", build_model="claude-opus-4-8")]
    (ledger_dir / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = _run_cli("per-model", "--ledger-dir", str(ledger_dir), "--repo", "a/a")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert list(out.keys()) == ["claude-sonnet-5"]


def test_cli_report_close_time_cost(tmp_path):
    ledger_dir = tmp_path / "ledger"; ledger_dir.mkdir()
    rows = [_row(repo="a/a", outcome_type="merged", shadow_cost_usd=10),
            _row(repo="a/a", outcome_type="merged", shadow_cost_usd=20)]
    (ledger_dir / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = _run_cli("report", "--kind", "close-time-cost", "--ledger-dir", str(ledger_dir), "--repo", "a/a")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["total_shadow_cost_usd"] == 30
    assert out["cost_per_merged_task"] == 15


def test_cli_report_crossover_cost(tmp_path):
    ledger_dir = tmp_path / "ledger"; ledger_dir.mkdir()
    rows = [_row(repo="yellow-robots/factory", outcome_type="merged", shadow_cost_usd=100),
            _row(repo="acme/widgets", outcome_type="merged", shadow_cost_usd=10)]
    (ledger_dir / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = _run_cli("report", "--kind", "crossover-cost", "--ledger-dir", str(ledger_dir))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["factory"]["total_shadow_cost_usd"] == 100
    assert out["product"]["total_shadow_cost_usd"] == 10


def test_cli_report_concurrency_headroom(tmp_path):
    ledger_dir = tmp_path / "ledger"; ledger_dir.mkdir()
    rows = [_row(repo="a/a", weighted_total=100, ts_end="2026-01-01T00:00:00Z"),
            _row(repo="b/b", weighted_total=50, ts_end="2026-01-01T12:00:00Z")]
    (ledger_dir / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = _run_cli("report", "--kind", "concurrency-headroom", "--ledger-dir", str(ledger_dir))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out == {"2026-01-01": 150}


def test_cli_report_unknown_kind_is_an_error():
    r = _run_cli("report", "--kind", "not-a-real-kind", "--ledger-dir", "/tmp/whatever")
    assert r.returncode != 0


# ============ issue #207: docs reach the shipped references ===========================================

def test_agents_md_repo_map_lists_the_ledger_tool():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "| `tools/ledger.py` |" in text


def test_agents_md_conventions_gains_the_ledger_informs_never_gates_line():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "ledger informs, never gates" in text.lower()
    assert "DEV_RUNNER_HOME" in text


def test_pipeline_md_gains_a_the_ledger_section_citing_the_tool_and_the_four_reads():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text(encoding="utf-8")
    assert "## The ledger" in text
    section = text.split("## The ledger", 1)[1].split("\n## ", 1)[0]
    assert "tools/ledger.py" in section
    assert "never gates" in section.lower()
    lowered = section.lower()
    assert "close-time cost" in lowered
    assert "crossover cost" in lowered
    assert "concurrency headroom" in lowered
