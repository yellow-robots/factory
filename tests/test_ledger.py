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
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ledger  # noqa: E402

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
