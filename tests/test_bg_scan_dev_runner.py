"""Acceptance tests for issue #306's runner wiring — the per-stage disposition table for an unresolved
CLI-managed background-task conversion found in a stage's own archived transcript.

Derived from the CRITERIA (the spec), NOT the runner's internals. Reuses the stubbed harness in
tests/test_dev_runner.py (the real-git happy-path helpers, the session_id-resolved transcript-archiving
fixtures from issue #205, and the PR-comment/timeline capture) and adds one derived `claude` stub that
can inject arbitrary transcript content into the ONE session file every stage in a run resolves to
(STUB_SESSION_ID is fixed for a whole run), keyed by which stage arm is executing — so a single run can
prove "this stage's OWN transcript had an unresolved conversion, that one's didn't" without needing a
live CLI. Derived by locating each arm's own `echo <MARKER> >> "$STUB_TIMELINE"` line in
claude_fake.CLAUDE_STUB_JSON and splicing one hook line after it (never by re-typing the classifier
itself — see tests/harness/contract.md and tests/test_shadow_review.py for the derivation precedent).

Covered:
  * an unresolved conversion in the implement or test stage's OWN transcript fails that stage via the
    named-failure shape instead of advancing;
  * a resolved conversion (a later kill tool_use naming the id) never blocks;
  * check-repair: the deterministic re-check still runs, and the run blocks naming the unresolved
    conversion even when that re-check comes back green;
  * review-repair: the post-repair final.patch salvage still lands before the block, and the block
    names the unresolved conversion alongside the existing text;
  * a review round's unresolved conversion is treated as not a clean APPROVE (routes into the existing
    review-repair path) even when the verdict line itself reads APPROVE, while the verdict record still
    shows what the round actually said;
  * a dedup-suffixed second review round scans its OWN archived file — a hit there never leaks
    backward onto round 1's transcript;
  * the non-gating shadow review round: a hit there is logged but never blocks the build;
  * a missing/heuristically-attributed transcript never gates, even carrying the same marker text.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as base  # the shared stub harness (gh/claude/check stubs + helpers)
import claude_fake  # tests/harness/claude_fake.py — the classifier's one legal home

ROOT = base.ROOT

MARKER = "Command running in background with ID: {tid}. Output is being written to: /tmp/out-{tid}.log"


def _event(role, content):
    return json.dumps({"type": role, "message": {"content": content}})


def _tool_result(text, tool_use_id="toolu_1"):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}


def _tool_use(name, input_obj, tool_id="toolu_x"):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": input_obj}


def transcript_unresolved(tid):
    """A conversion with no later reference to the id at all — the common real shape per the incident
    transcripts named in Context."""
    return _event("user", [_tool_result(MARKER.format(tid=tid))]) + "\n"


def transcript_resolved(tid):
    """A conversion immediately followed by a kill/stop tool_use naming the same id."""
    return "\n".join([
        _event("user", [_tool_result(MARKER.format(tid=tid))]),
        _event("assistant", [_tool_use("KillShell", {"shell_id": tid})]),
    ]) + "\n"


def transcript_clean():
    return _event("assistant", [{"type": "text", "text": "all good, nothing backgrounded"}]) + "\n"


def transcript_near_miss(tid):
    """The conversion phrase present but not structurally qualifying as a true conversion (mid-text,
    not at the start of the block) — a drift-canary near miss (#320), never a true unresolved hit."""
    text = "noise before it\n" + MARKER.format(tid=tid) + "\nnoise after it"
    return _event("user", [_tool_result(text)]) + "\n"


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# The derived stub: one hook line spliced after each single-round arm's own timeline marker (IMPL,
# TEST, REPAIR, REVIEWFIX all run at most once per pipeline run, so there's no residue to reset
# between calls), gated on an env var naming a fixture file to copy into the ONE session transcript
# file every stage's own archive_stage_transcript call resolves to (STUB_SESSION_ID fixed for the
# whole run — see _bg_setup below). The REVIEWER arm is instead replaced WHOLESALE (it can run up to
# three times in one pipeline run — gating round 1, the post-repair gating round 2, and the
# non-gating shadow round — so each call must reset the transcript file to a known-clean baseline
# when its OWN content var isn't set, or an earlier round's injected content would leak forward into
# a later round that never asked for it): it distinguishes the shadow round (ANTHROPIC_BASE_URL set
# on that one subprocess only, the same signal test_shadow_review.py's derivation uses) from the
# gating round, giving the shadow call its own SHADOWREVIEW timeline marker (never REVIEW) so the two
# are never conflated by a plain timeline count — and separately distinguishes the gating round's
# first pass (no `review_repaired` marker yet) from its post-repair second pass.
# ---------------------------------------------------------------------------
_BG_PREAMBLE = 'is_bg_shadow=0\n[ -n "${ANTHROPIC_BASE_URL:-}" ] && is_bg_shadow=1\n'

def _stage_hook(var):
    """Every single-round arm resets the shared transcript file to the known-clean baseline unless
    its OWN content var is set — so an earlier stage's injected content (still sitting in the ONE
    session file every call resolves to) never leaks forward into a stage that never asked for it."""
    return (f'_bgsrc="${{STUB_BG_CONTENT_{var}:-${{STUB_BG_CLEAN_FILE:-}}}}"\n'
            '[ -n "${STUB_BG_TRANSCRIPT_FILE:-}" ] && [ -n "$_bgsrc" ] '
            '&& cp "$_bgsrc" "$STUB_BG_TRANSCRIPT_FILE"\n')


_HOOK_IMPL = _stage_hook("IMPL")
_HOOK_TEST = _stage_hook("TEST")
_HOOK_REPAIR = _stage_hook("REPAIR")
_HOOK_REVIEWFIX = _stage_hook("REVIEWFIX")

_BASE_JSON_REVIEWER_ARM = '''  *REVIEWER*)
    echo REVIEW >> "$STUB_TIMELINE"
    if [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then
      emit_json "VERDICT: REQUEST_CHANGES" 11 12 13 14 100
    else
      emit_json "VERDICT: APPROVE" 21 22 23 24 200
    fi ;;'''

_BG_JSON_REVIEWER_ARM = '''  *REVIEWER*)
    if [ "$is_bg_shadow" = 1 ]; then
      echo SHADOWREVIEW >> "$STUB_TIMELINE"
      _bgsrc="${STUB_BG_CONTENT_SHADOW_REVIEW:-${STUB_BG_CLEAN_FILE:-}}"
      [ -n "${STUB_BG_TRANSCRIPT_FILE:-}" ] && [ -n "$_bgsrc" ] && cp "$_bgsrc" "$STUB_BG_TRANSCRIPT_FILE"
      emit_json "VERDICT: APPROVE" 71 72 73 74 700
    else
      echo REVIEW >> "$STUB_TIMELINE"
      if [ -f review_repaired ]; then _bgsrc="${STUB_BG_CONTENT_REVIEW_ROUND2:-${STUB_BG_CLEAN_FILE:-}}"
      else _bgsrc="${STUB_BG_CONTENT_REVIEW_ROUND1:-${STUB_BG_CLEAN_FILE:-}}"
      fi
      [ -n "${STUB_BG_TRANSCRIPT_FILE:-}" ] && [ -n "$_bgsrc" ] && cp "$_bgsrc" "$STUB_BG_TRANSCRIPT_FILE"
      if [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then
        emit_json "VERDICT: REQUEST_CHANGES" 11 12 13 14 100
      else
        emit_json "VERDICT: APPROVE" 21 22 23 24 200
      fi
    fi ;;'''


def _splice(src, marker, hook):
    assert src.count(marker) == 1, f"expected exactly one occurrence of {marker!r} to splice into"
    return src.replace(marker, marker + hook, 1)


CLAUDE_STUB_JSON_BG = claude_fake.CLAUDE_STUB_JSON.replace(
    'case "$args" in\n', _BG_PREAMBLE + 'case "$args" in\n', 1,
)
assert CLAUDE_STUB_JSON_BG != claude_fake.CLAUDE_STUB_JSON, "preamble splice did not match"
assert claude_fake.CLAUDE_STUB_JSON.count(_BASE_JSON_REVIEWER_ARM) == 1, "REVIEWER arm text drifted"
CLAUDE_STUB_JSON_BG = CLAUDE_STUB_JSON_BG.replace(_BASE_JSON_REVIEWER_ARM, _BG_JSON_REVIEWER_ARM, 1)
CLAUDE_STUB_JSON_BG = _splice(CLAUDE_STUB_JSON_BG, 'echo REVIEWFIX >> "$STUB_TIMELINE"\n', _HOOK_REVIEWFIX)
CLAUDE_STUB_JSON_BG = _splice(CLAUDE_STUB_JSON_BG, 'echo TEST >> "$STUB_TIMELINE"\n', _HOOK_TEST)
CLAUDE_STUB_JSON_BG = _splice(CLAUDE_STUB_JSON_BG, 'echo REPAIR >> "$STUB_TIMELINE"\n', _HOOK_REPAIR)
CLAUDE_STUB_JSON_BG = _splice(CLAUDE_STUB_JSON_BG, 'echo IMPL >> "$STUB_TIMELINE"\n', _HOOK_IMPL)


def _bg_setup(tmp_path, title):
    """A real-git run wired for session_id-resolved transcript archiving (issue #205's positive-evidence
    path — never the heuristic-newest fallback, which the scan never gates on): one fixed session id
    for the whole run, seeded with clean content, so a test only needs to name which stage's own arm
    should overwrite it before that stage's own archive step runs. STUB_BG_CLEAN_FILE is the same clean
    fixture the REVIEWER arm resets to whenever a given round's own content var isn't set."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"
    binp.mkdir(parents=True, exist_ok=True)
    base._exec(binp / "gh", base.GH_STUB)
    base._exec(binp / "claude", CLAUDE_STUB_JSON_BG)
    base._exec(binp / "check.sh", base.CHECK_STUB)
    home = tmp_path / "home"
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title=title), work)
    env["HOME"] = str(home)
    env["STUB_SESSION_ID"] = "bgsess"
    slug = base._resolve_wt_slug(env, "test/repo", 5)
    slug_dir = base._seed_slug_dir(home, slug)
    transcript_path = slug_dir / "bgsess.jsonl"
    transcript_path.write_text(transcript_clean())
    env["STUB_BG_TRANSCRIPT_FILE"] = str(transcript_path)
    env["STUB_BG_CLEAN_FILE"] = str(_write(tmp_path, "clean.jsonl", transcript_clean()))
    env["STUB_CLAUDE_CHANGE"] = "1"
    return env, work, binp


# ============ implement / test: fail the stage via the named-failure shape ============

def test_implement_stage_ends_blocked_on_unresolved_background_conversion(tmp_path):
    env, work, binp = _bg_setup(tmp_path, "Implement unresolved bg task")
    env["STUB_BG_CONTENT_IMPL"] = str(_write(tmp_path, "impl_unresolved.jsonl", transcript_unresolved("bgtaskimpl")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    tl = base._timeline(tmp_path)
    assert "IMPL" in tl and "TEST" not in tl   # never advanced past the failed stage
    comments = " ".join(base._comments(tl))
    assert "implement" in comments.lower()
    assert "bgtaskimpl" in comments
    assert "background" in comments.lower()


def test_test_stage_ends_blocked_on_unresolved_background_conversion(tmp_path):
    """Implement stays clean (no injected content there); only the tester's own archived transcript
    carries the unresolved conversion."""
    env, work, binp = _bg_setup(tmp_path, "Test stage unresolved bg task")
    env["STUB_BG_CONTENT_TEST"] = str(_write(tmp_path, "test_unresolved.jsonl", transcript_unresolved("bgtasktest")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    assert "https://stub/pr/1" not in r.stdout
    tl = base._timeline(tmp_path)
    assert tl.count("IMPL") == 1 and "TEST" in tl
    assert "REPAIR" not in tl and "REVIEW" not in tl   # never advanced past the failed stage
    comments = " ".join(base._comments(tl))
    assert "tester" in comments.lower()
    assert "bgtasktest" in comments


def test_resolved_conversion_via_kill_tool_use_does_not_block(tmp_path):
    """A conversion followed by an observed kill is resolution, not a failure — the build proceeds."""
    env, work, binp = _bg_setup(tmp_path, "Resolved bg conversion")
    env["STUB_BG_CONTENT_IMPL"] = str(_write(tmp_path, "impl_resolved.jsonl", transcript_resolved("bgtaskok")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout


# ============ the near-miss drift canary (issue #320): logged per stage, never gates ============

def test_near_miss_logged_with_count_and_first_index_and_never_blocks(tmp_path):
    """A stage whose OWN transcript contains the conversion phrase mid-text (a near miss, not a true
    conversion) must build clean through to a PR exactly like a stage with no marker at all — the
    canary rides the envelope but never disposes on anything — while the runner's own log still states
    the near-miss count and first event index for that stage."""
    env, work, binp = _bg_setup(tmp_path, "Near miss never blocks")
    env["STUB_BG_CONTENT_IMPL"] = str(_write(tmp_path, "impl_near_miss.jsonl", transcript_near_miss("bgtasknear")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = base._timeline(tmp_path)
    assert tl.count("IMPL") == 1 and "TEST" in tl   # advanced normally, exactly as an unmarked run would
    comments = " ".join(base._comments(tl))
    assert "bgtasknear" not in comments             # never surfaced as a blocking finding
    assert "unresolved background-task conversion" not in r.stderr.lower()
    stderr_lower = r.stderr.lower()
    assert "near-miss" in stderr_lower or "near miss" in stderr_lower
    assert "implement" in stderr_lower
    assert "count=1" in r.stderr or "count: 1" in stderr_lower
    assert "first_index=0" in r.stderr or "first index: 0" in stderr_lower or "index=0" in stderr_lower


def test_zero_near_misses_logged_as_count_zero_when_stage_is_clean(tmp_path):
    """A clean stage (no marker text anywhere) still gets a per-stage canary log line, stating a zero
    count — the log fires on every scan, not only when something was found."""
    env, work, binp = _bg_setup(tmp_path, "Clean stage still logs canary")
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    stderr_lower = r.stderr.lower()
    assert "near-miss" in stderr_lower or "near miss" in stderr_lower
    assert "count=0" in r.stderr or "count: 0" in stderr_lower


def test_multiple_near_misses_in_one_stage_report_count_and_first_index(tmp_path):
    """Two near misses in the same stage's transcript: the log states the total count and the FIRST
    event index only (not every index) — a compact per-stage summary line, not an enumeration."""
    env, work, binp = _bg_setup(tmp_path, "Multiple near misses one stage")
    two_near = transcript_near_miss("bgtaska") + transcript_near_miss("bgtaskb")
    env["STUB_BG_CONTENT_TEST"] = str(_write(tmp_path, "test_two_near.jsonl", two_near))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    stderr_lower = r.stderr.lower()
    assert "count=2" in r.stderr or "count: 2" in stderr_lower
    assert "first_index=0" in r.stderr or "first index: 0" in stderr_lower or "index=0" in stderr_lower


def test_review_round_near_miss_never_triggers_repair_or_touches_verdict(tmp_path):
    """The most sensitive site: a review round's own transcript carries a near miss. The verdict and
    disposition (a single clean APPROVE, no review-repair round) must be byte-unaffected — exactly the
    same shape as a review round with no marker text at all."""
    env, work, binp = _bg_setup(tmp_path, "Review round near miss never gates")
    env["STUB_BG_CONTENT_REVIEW_ROUND1"] = str(_write(tmp_path, "review_near_miss.jsonl", transcript_near_miss("bgtaskreviewnear")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 1 and "REVIEWFIX" not in tl   # a single clean round, no repair triggered
    rd = base._run_dir(tmp_path, 5)
    review_md = (rd / "review.md").read_text()
    assert "VERDICT: APPROVE" in review_md
    assert "unresolved background-task conversion" not in r.stderr.lower()


# ============ check-repair: salvage/re-check ordering preserved, then dispose fail-closed ============

def test_check_repair_unresolved_blocks_even_when_recheck_comes_back_green(tmp_path):
    env, work, binp = _bg_setup(tmp_path, "Check-repair unresolved bg task")
    env["STUB_CHECK_FAIL"] = "1"   # first check fails; the repair heals it; the re-check then passes
    env["STUB_BG_CONTENT_REPAIR"] = str(_write(tmp_path, "repair_unresolved.jsonl", transcript_unresolved("bgtaskrepair")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = base._timeline(tmp_path)
    assert tl.count("CHECK") == 2   # the deterministic re-check still ran despite the eventual block
    assert "REPAIR" in tl
    comments = " ".join(base._comments(tl))
    assert "bgtaskrepair" in comments
    assert "background" in comments.lower()


# ============ review round: unresolved conversion is not a clean APPROVE ============

def test_review_round_unresolved_treated_as_not_clean_approve(tmp_path):
    """The verdict TEXT alone would be a clean APPROVE (STUB_REVIEW_BLOCK unset) — the bg hit must
    still route this into the review-repair path, exactly as the existing fail-closed verdict path
    does for a textual REQUEST_CHANGES. The verdict record still shows what the round actually said."""
    env, work, binp = _bg_setup(tmp_path, "Review round1 unresolved bg task")
    env["STUB_BG_CONTENT_REVIEW_ROUND1"] = str(_write(tmp_path, "review_unresolved.jsonl", transcript_unresolved("bgtaskreview1")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr   # round 2 (no injected content there) approves cleanly
    assert "https://stub/pr/1" in r.stdout
    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 2 and "REVIEWFIX" in tl   # routed into the repair path
    rd = base._run_dir(tmp_path, 5)
    review_md = (rd / "review.md").read_text()
    assert "VERDICT: APPROVE" in review_md   # the round's own verdict record is untouched
    assert "unresolved background-task conversion" in r.stderr.lower()
    assert "bgtaskreview1" in r.stderr


def test_review_second_round_unresolved_scans_its_own_dedup_suffixed_file(tmp_path):
    """Round 1 is blocked on its own TEXTUAL verdict (STUB_REVIEW_BLOCK) — independent of bg_scan —
    triggering review-repair; only round 2's own archived transcript carries the unresolved marker.
    Round 2 must scan transcript-review-2.jsonl, and round 1's own transcript-review.jsonl must stay
    clean — proving a hit never leaks backward onto a prior round's file."""
    env, work, binp = _bg_setup(tmp_path, "Review round2 dedup unresolved")
    env["STUB_REVIEW_BLOCK"] = "1"
    env["STUB_BG_CONTENT_REVIEW_ROUND2"] = str(_write(tmp_path, "review_round2_unresolved.jsonl", transcript_unresolved("bgtaskround2")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    rd = base._run_dir(tmp_path, 5)
    files = base._transcript_files(rd)
    assert "transcript-review.jsonl" in files and "transcript-review-2.jsonl" in files
    assert "Command running in background" not in (rd / "transcript-review.jsonl").read_text()
    assert "Command running in background" in (rd / "transcript-review-2.jsonl").read_text()
    comments = " ".join(base._comments(base._timeline(tmp_path)))
    assert "bgtaskround2" in comments


# ============ review-repair: final.patch salvage still lands first, then dispose fail-closed ========

def test_review_repair_unresolved_blocks_even_after_green_recheck_and_reapprove(tmp_path):
    """The reviewer's own repair round ends its turn with a live background task: the post-repair
    final.patch salvage (issue #172) still lands, the deterministic re-check and re-review still run
    and would otherwise both come back clean — but the run blocks anyway, naming the unresolved
    conversion alongside the salvage pointer."""
    env, work, binp = _bg_setup(tmp_path, "Review-repair unresolved bg task")
    env["STUB_REVIEW_BLOCK"] = "1"   # round 1 REQUEST_CHANGES -> triggers review-repair
    env["STUB_BG_CONTENT_REVIEWFIX"] = str(_write(tmp_path, "reviewfix_unresolved.jsonl", transcript_unresolved("bgtaskreviewfix")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 2 and "REVIEWFIX" in tl   # repaired, re-checked, and re-reviewed regardless
    assert tl.count("CHECK") == 2                          # the deterministic re-check still ran
    rd = base._run_dir(tmp_path, 5)
    assert (rd / "final.patch").exists()                   # salvage still landed before the block
    comments = " ".join(base._comments(tl))
    assert "bgtaskreviewfix" in comments
    assert "final.patch" in comments                       # the block names the salvage pointer too


# ============ the non-gating shadow review round stays fail-soft ============

def test_shadow_review_round_unresolved_conversion_never_blocks(tmp_path):
    """The gating round's own transcript stays clean; only the shadow round's own archived transcript
    carries the unresolved marker — logged, but the build proceeds unchanged (the shadow seat's
    standing non-gating rule, issue #165)."""
    env, work, binp = _bg_setup(tmp_path, "Shadow review unresolved bg task")
    env["YR_SHADOW_MODEL"] = "shadow-test-model"
    env["YR_SHADOW_BASE_URL"] = "https://shadow.example.test/v1"
    env["STUB_BG_CONTENT_SHADOW_REVIEW"] = str(_write(tmp_path, "shadow_unresolved.jsonl", transcript_unresolved("bgtaskshadow")))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 1 and "REVIEWFIX" not in tl   # the gating round approved cleanly
    assert "SHADOWREVIEW" in tl                                # the shadow round still ran
    assert "unresolved background-task conversion" in r.stderr.lower()
    assert "bgtaskshadow" in r.stderr


# ============ missing / heuristically-attributed transcripts never gate ============

def test_heuristic_attributed_transcript_with_marker_never_gates(tmp_path):
    """No STUB_SESSION_ID at all (plain-text stub): archiving falls back to the newest-.jsonl
    heuristic — never session-id resolution — so even a transcript carrying the marker must not gate,
    per the positive-session-attributed-evidence-only rule."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    home = tmp_path / "home"
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Heuristic-attributed unresolved never gates"), work)
    env["HOME"] = str(home)
    env["STUB_CLAUDE_CHANGE"] = "1"
    slug = base._resolve_wt_slug(env, "test/repo", 5)
    slug_dir = base._seed_slug_dir(home, slug)
    (slug_dir / "session-abc.jsonl").write_text(transcript_unresolved("bgtaskheuristic"))
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert "bgtaskheuristic" not in r.stderr   # the scan never even ran on heuristic attribution


def test_missing_slug_dir_never_gates_on_bg_scan(tmp_path):
    """No CLI project slug dir at all: archiving is skipped loudly (issue #205's existing behavior),
    and the bg scan — which only ever runs on an archived, session-id-resolved file — never fires."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"; base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Missing transcript never bg-gates"), work)
    env["HOME"] = str(tmp_path / "home-absent")
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    assert "unresolved background-task conversion" not in r.stderr
