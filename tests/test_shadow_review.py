"""Acceptance tests for issue #165 — the shadow review seat: a non-gating SECOND verdict on every
gating review round, dark by default.

Derived from the CRITERIA (the spec), NOT the runner's internals. Reuses the stubbed harness in
tests/test_dev_runner.py (the stage-aware `gh`/check stubs, the real-git happy-path helpers, and the
PR-comment capture) and adds one new `claude` stub that is aware of the shadow seat's own signal — the
`ANTHROPIC_BASE_URL` env var run_stage sets on the ONE shadow subprocess only (issue #165 passes it as
run_stage's new $6, never touched by any other caller) — so a test can tell a shadow call apart from a
gating call without depending on any other implementation detail.

Covered criteria:
  * dark by default (either or both of YR_SHADOW_MODEL / YR_SHADOW_BASE_URL unset): byte-identical to
    today — no extra `claude` invocation, no shadow-review*.md artifact, no YR-SHADOW-REVIEW comment;
  * both keys set: one extra `claude -p` call per gating review round, with ANTHROPIC_BASE_URL set on
    THAT call only (never on implement/test/repair/the gating review call itself), writing
    shadow-review.md (round 2: shadow-review-2.md, the existing suffix pattern);
  * the shadow verdict never contributes to the review gate: a gating APPROVE ships even when the
    shadow round says REQUEST_CHANGES;
  * a shadow-stage crash is best-effort logged and the build proceeds green regardless;
  * one inert PR comment per shadow round: first line `YR-SHADOW-REVIEW: <verdict>`, transcript
    blockquoted below, no line matching the line-anchored gating token `^VERDICT:`;
  * shadow usage lands in usage-shadow-review*.json, distinct from the gating usage-review*.json;
  * deploy/dispatch.env.example documents both keys, commented out (dark by default).

Runs under `.venv/bin/python -m pytest tests/ -q` (system python3 works too — no third-party deps).
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as base  # the shared stub harness (gh/claude/check stubs + helpers)

ROOT = base.ROOT


# ---------------------------------------------------------------------------
# A claude stub that tells a shadow call apart from every other call by the ONE signal the spec
# names explicitly: ANTHROPIC_BASE_URL is set in the subprocess's own environment. It also records
# --model and ANTHROPIC_BASE_URL per call (STUB_CALL_LOG) so a test can prove the override lands on
# that one subprocess only, plus the usual stage-aware behaviour (REVIEWER / REQUESTED CHANGES /
# TESTER / tests FAIL / else implement) so the rest of the pipeline reaches a PR.
# ---------------------------------------------------------------------------
CLAUDE_STUB_SHADOW = r'''#!/usr/bin/env bash
model=""; prev=""
for a in "$@"; do
  [ "$prev" = "--model" ] && model="$a"
  prev="$a"
done
stdin_content="$(cat)"
args="$*"$'\n'"$stdin_content"
is_shadow=0
[ -n "${ANTHROPIC_BASE_URL:-}" ] && is_shadow=1
if [ -n "${STUB_CALL_LOG:-}" ]; then
  printf 'model=%s base_url=%s shadow=%s\n' "$model" "${ANTHROPIC_BASE_URL:-}" "$is_shadow" >> "$STUB_CALL_LOG"
fi
case "$args" in
  *REVIEWER*)
    if [ "$is_shadow" = 1 ]; then
      echo SHADOWREVIEW >> "$STUB_TIMELINE"
      if [ -n "${STUB_SHADOW_CRASH:-}" ]; then echo "shadow reviewer crashed" >&2; exit 9; fi
      printf 'Shadow reviewer notes on the diff.\nA second line of transcript.\n%s\n' "${STUB_SHADOW_VERDICT:-VERDICT: APPROVE}"
    else
      echo REVIEW >> "$STUB_TIMELINE"
      if [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then
        echo "VERDICT: REQUEST_CHANGES"
      else
        echo "VERDICT: APPROVE"
      fi
    fi ;;
  *"REQUESTED CHANGES"*) echo REVIEWFIX >> "$STUB_TIMELINE"; : > review_repaired ;;
  *TESTER*)              echo TEST >> "$STUB_TIMELINE" ;;
  *"tests FAIL"*)        echo REPAIR >> "$STUB_TIMELINE"; : > repaired ;;
  *)                     echo IMPL >> "$STUB_TIMELINE"; [ -n "${STUB_CLAUDE_CHANGE:-}" ] && printf 'hello\n' > feature.txt ;;
esac
exit 0
'''

# JSON-envelope variant of the same stub (mirrors base.CLAUDE_STUB_JSON), so a shadow round's usage
# capture (issue #48's machinery — capture_stage_usage keys off the log file's basename) can be proven
# to land in a distinctly-named usage-shadow-review*.json, never colliding with usage-review*.json.
CLAUDE_STUB_SHADOW_JSON = r'''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\n'"$stdin_content"
is_shadow=0
[ -n "${ANTHROPIC_BASE_URL:-}" ] && is_shadow=1
emit_json() {  # $1=result-text $2=input $3=output $4=cache_write $5=cache_read $6=duration_ms
  printf '{"type":"result","subtype":"success","is_error":false,"duration_ms":%s,"result":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":%s}}\n' "$6" "$1" "$2" "$3" "$4" "$5"
}
case "$args" in
  *REVIEWER*)
    if [ "$is_shadow" = 1 ]; then
      echo SHADOWREVIEW >> "$STUB_TIMELINE"
      if [ -f review_repaired ]; then emit_json "VERDICT: APPROVE" 81 82 83 84 800
      else emit_json "VERDICT: APPROVE" 71 72 73 74 700; fi
    else
      echo REVIEW >> "$STUB_TIMELINE"
      if [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then
        emit_json "VERDICT: REQUEST_CHANGES" 11 12 13 14 100
      else
        emit_json "VERDICT: APPROVE" 21 22 23 24 200
      fi
    fi ;;
  *"REQUESTED CHANGES"*)
    echo REVIEWFIX >> "$STUB_TIMELINE"; : > review_repaired
    emit_json "fixed the blockers" 31 32 33 34 300 ;;
  *TESTER*)
    echo TEST >> "$STUB_TIMELINE"
    emit_json "wrote tests" 41 42 43 44 400 ;;
  *"tests FAIL"*)
    echo REPAIR >> "$STUB_TIMELINE"; : > repaired
    emit_json "repaired the code" 51 52 53 54 500 ;;
  *)
    echo IMPL >> "$STUB_TIMELINE"
    printf 'hello\n' > feature.txt
    emit_json "implemented the feature" 61 62 63 64 600 ;;
esac
exit 0
'''


def _shadow_stubs(binp, claude_src=CLAUDE_STUB_SHADOW):
    binp.mkdir(parents=True, exist_ok=True)
    base._exec(binp / "gh", base.GH_STUB)
    base._exec(binp / "claude", claude_src)
    base._exec(binp / "check.sh", base.CHECK_STUB)


def _env(tmp_path, binp, *, claude_src=CLAUDE_STUB_SHADOW, title="Shadow review seat", **kw):
    work, _ = base._make_repo(tmp_path)
    _shadow_stubs(binp, claude_src)
    env = base._real(tmp_path, base._env(tmp_path, binp, title=title, **kw), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_CALL_LOG"] = str(tmp_path / "call_log")
    return env


def _calls(tmp_path):
    """Every claude invocation's (model, base_url, is_shadow), in call order."""
    p = tmp_path / "call_log"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        m = re.match(r"model=(\S*) base_url=(\S*) shadow=(\d)", line)
        assert m, line
        out.append({"model": m.group(1), "base_url": m.group(2), "shadow": m.group(3) == "1"})
    return out


def _run_dir(tmp_path, number=5):
    return base._run_dir(tmp_path, number)


def _shadow_artifacts(rundir):
    """Just the shadow-review*.md transcript files — excludes the *-comment.md files the runner also
    writes into the same run dir (comment bodies, not review transcripts)."""
    return sorted(p.name for p in rundir.iterdir() if re.fullmatch(r"shadow-review(-\d+)?\.md", p.name))


def _usage_files_matching(rundir, stage_prefix):
    """usage-<stage_prefix>(.json|-<n>.json) only — excludes any OTHER stage whose name happens to
    start with the same prefix (e.g. usage-review-repair.json is a different stage than usage-review*)."""
    pat = re.compile(rf"usage-{re.escape(stage_prefix)}(-\d+)?\.json")
    return sorted(p.name for p in rundir.iterdir() if pat.fullmatch(p.name))


def _comment_blocks(tmp_path):
    """Split the captured PR-comment log (base._prcomments) into individual comment bodies."""
    raw = base._prcomments(tmp_path)
    if not raw:
        return []
    parts = raw.split("=== PRCOMMENT ===\n")
    return [c for c in parts if c.strip()]


def _shadow_comment_blocks(tmp_path):
    return [c for c in _comment_blocks(tmp_path) if c.startswith("YR-SHADOW-REVIEW:")]


SHADOW_ENV = {
    "YR_SHADOW_MODEL": "shadow-test-model",
    "YR_SHADOW_BASE_URL": "https://shadow.example.test/v1",
}


# ============ dark by default: byte-identical to today ============

def test_env_unset_no_extra_subprocess_no_artifact_no_comment(tmp_path):
    """Neither YR_SHADOW_MODEL nor YR_SHADOW_BASE_URL set: the shadow seat must be a complete no-op —
    the same three claude calls as always (IMPL, TEST, REVIEW), no shadow-review.md, no comment."""
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout

    calls = _calls(tmp_path)
    assert len(calls) == 3                          # implement, test, gating review — nothing more
    assert not any(c["shadow"] for c in calls)
    assert not any(c["base_url"] for c in calls)

    rd = _run_dir(tmp_path)
    assert not list(rd.glob("shadow-review*.md"))
    assert not list(rd.glob("usage-shadow-review*.json"))
    assert not _shadow_comment_blocks(tmp_path)
    assert "YR-SHADOW-REVIEW" not in base._prcomments(tmp_path)


def test_only_model_set_stays_dark(tmp_path):
    """WHERE the env keys are not BOTH set: YR_SHADOW_MODEL alone must not arm the seat."""
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env["YR_SHADOW_MODEL"] = "shadow-test-model"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert len(_calls(tmp_path)) == 3
    rd = _run_dir(tmp_path)
    assert not list(rd.glob("shadow-review*.md"))
    assert not _shadow_comment_blocks(tmp_path)


def test_only_base_url_set_stays_dark(tmp_path):
    """WHERE the env keys are not BOTH set: YR_SHADOW_BASE_URL alone must not arm the seat."""
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env["YR_SHADOW_BASE_URL"] = "https://shadow.example.test/v1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert len(_calls(tmp_path)) == 3
    rd = _run_dir(tmp_path)
    assert not list(rd.glob("shadow-review*.md"))
    assert not _shadow_comment_blocks(tmp_path)


def test_dark_run_bytewise_matches_a_plain_stub_baseline(tmp_path):
    """A second, independent proof of byte-identical dark behaviour, using the SAME plain `claude`
    stub the rest of the suite already trusts (base.CLAUDE_STUB) rather than this file's own stub —
    the vanilla happy path must reach a PR exactly as it does with no knowledge of this feature."""
    work, _ = base._make_repo(tmp_path)
    binp = tmp_path / "bin"
    base._stubs(binp)
    env = base._real(tmp_path, base._env(tmp_path, binp, number=5, title="Dark baseline"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = base._run_dir(tmp_path)
    assert not list(rd.glob("shadow-review*.md"))
    assert "YR-SHADOW-REVIEW" not in base._prcomments(tmp_path)


# ============ armed: one shadow round per gating round, base_url scoped to it alone ============

def test_shadow_round_runs_with_scoped_base_url_and_writes_artifact(tmp_path):
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env.update(SHADOW_ENV)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout

    calls = _calls(tmp_path)
    assert len(calls) == 4                                       # + one shadow call
    shadow_calls = [c for c in calls if c["shadow"]]
    gating_calls = [c for c in calls if not c["shadow"]]
    assert len(shadow_calls) == 1 and len(gating_calls) == 3
    # the base_url override landed on the shadow subprocess ONLY
    assert all(c["base_url"] == SHADOW_ENV["YR_SHADOW_BASE_URL"] for c in shadow_calls)
    assert all(c["base_url"] == "" for c in gating_calls)
    # the shadow model id is the one actually used for that call — never the gating review's own model
    assert all(c["model"] == SHADOW_ENV["YR_SHADOW_MODEL"] for c in shadow_calls)
    assert all(c["model"] != SHADOW_ENV["YR_SHADOW_MODEL"] for c in gating_calls)

    rd = _run_dir(tmp_path)
    assert _shadow_artifacts(rd) == ["shadow-review.md"]
    content = (rd / "shadow-review.md").read_text()
    assert "VERDICT: APPROVE" in content


def test_shadow_verdict_never_gates_build_ships_on_gating_approve_despite_shadow_request_changes(tmp_path):
    """The shadow verdict must never contribute to the review gate: a gating APPROVE ships even when
    the shadow round's own verdict is REQUEST_CHANGES."""
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env.update(SHADOW_ENV)
    env["STUB_SHADOW_VERDICT"] = "VERDICT: REQUEST_CHANGES"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                # gate is indifferent to the shadow verdict
    assert "https://stub/pr/1" in r.stdout
    tl = base._timeline(tmp_path)
    assert "REVIEWFIX" not in tl                       # no repair triggered by the shadow's disapproval

    blocks = _shadow_comment_blocks(tmp_path)
    assert len(blocks) == 1
    first_line = blocks[0].splitlines()[0]
    assert first_line == "YR-SHADOW-REVIEW: REQUEST_CHANGES"


def test_shadow_comment_is_inert_first_line_marker_blockquoted_transcript_no_gating_token(tmp_path):
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env.update(SHADOW_ENV)
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    blocks = _shadow_comment_blocks(tmp_path)
    assert len(blocks) == 1
    block = blocks[0]
    lines = block.splitlines()
    assert lines[0] == "YR-SHADOW-REVIEW: APPROVE"
    # transcript is blockquoted below the marker (blank line, then every transcript line prefixed "> ")
    transcript_lines = [l for l in lines[1:] if l != ""]
    assert transcript_lines                            # the stub's multi-line transcript survived
    assert all(l.startswith("> ") for l in transcript_lines)
    # no line of the SHADOW comment matches the line-anchored gating token
    assert re.search(r"^VERDICT:", block, re.MULTILINE) is None
    # sanity: the real gating verdict WAS extracted correctly (proves the same last-line rule ran) —
    # the blockquoting is what breaks the line anchor, not a different/weaker extraction rule
    assert "> VERDICT: APPROVE" in block


def test_shadow_crash_is_logged_and_build_stays_green(tmp_path):
    """IF the shadow stage fails in any way THEN the build SHALL proceed unchanged with the failure
    logged — a nonzero-exit shadow subprocess must never touch the gating outcome."""
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env.update(SHADOW_ENV)
    env["STUB_SHADOW_CRASH"] = "1"
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr                 # build proceeds unchanged
    assert "https://stub/pr/1" in r.stdout
    assert "shadow" in r.stderr.lower() and "fail" in r.stderr.lower()   # logged, best-effort

    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 1                     # the gating review itself ran exactly once
    assert "REVIEWFIX" not in tl                        # never treated as a gating rejection

    # no usage artifact for a failed capture (capture_stage_usage only fires on a clean exit)
    rd = _run_dir(tmp_path)
    assert not list(rd.glob("usage-shadow-review*.json"))
    # whatever comment (if any) the crash produced still carries no gating-anchored VERDICT line
    for block in _shadow_comment_blocks(tmp_path):
        assert re.search(r"^VERDICT:", block, re.MULTILINE) is None


# ============ multi-round: the reviewer's own repair loop doubles the shadow rounds too ============

def test_two_gating_rounds_suffix_both_shadow_artifacts_and_comments(tmp_path):
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5)
    env.update(SHADOW_ENV)
    env["STUB_REVIEW_BLOCK"] = "1"     # gating: blocked once, approved after the review-repair
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    tl = base._timeline(tmp_path)
    assert tl.count("REVIEW") == 2 and tl.count("SHADOWREVIEW") == 2

    calls = _calls(tmp_path)
    shadow_calls = [c for c in calls if c["shadow"]]
    assert len(shadow_calls) == 2
    assert all(c["base_url"] == SHADOW_ENV["YR_SHADOW_BASE_URL"] for c in shadow_calls)

    rd = _run_dir(tmp_path)
    assert _shadow_artifacts(rd) == ["shadow-review-2.md", "shadow-review.md"]

    blocks = _shadow_comment_blocks(tmp_path)
    assert len(blocks) == 2
    assert all(re.search(r"^VERDICT:", b, re.MULTILINE) is None for b in blocks)


def test_shadow_usage_suffixed_and_never_collides_with_gating_review_usage(tmp_path):
    binp = tmp_path / "bin"
    env = _env(tmp_path, binp, number=5, claude_src=CLAUDE_STUB_SHADOW_JSON)
    env.update(SHADOW_ENV)
    env["STUB_REVIEW_BLOCK"] = "1"     # two gating rounds -> two shadow rounds
    r = base._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    rd = _run_dir(tmp_path)
    gating_usage = _usage_files_matching(rd, "review")
    shadow_usage = _usage_files_matching(rd, "shadow-review")
    assert gating_usage == ["usage-review-2.json", "usage-review.json"]
    assert shadow_usage == ["usage-shadow-review-2.json", "usage-shadow-review.json"]
    assert set(gating_usage).isdisjoint(shadow_usage)   # no filename collision between the two stages

    round1 = json.loads((rd / "usage-shadow-review.json").read_text())
    round2 = json.loads((rd / "usage-shadow-review-2.json").read_text())
    assert round1["input_tokens"] == 71 and round2["input_tokens"] == 81   # distinct, both captured

    gating1 = json.loads((rd / "usage-review.json").read_text())
    gating2 = json.loads((rd / "usage-review-2.json").read_text())
    assert gating1["input_tokens"] == 11 and gating2["input_tokens"] == 21  # gating rounds untouched

    # the aggregate summary rolls up every stage's artifact under its own distinct name
    summary = json.loads((rd / "usage-summary.json").read_text())
    stages = {s["stage"] for s in summary["stages"]}
    assert {"review", "review-2", "shadow-review", "shadow-review-2"} <= stages


# ============ deploy/dispatch.env.example: documented, dark by default ============

def test_dispatch_env_example_documents_both_keys_commented_out(tmp_path):
    text = (ROOT / "deploy" / "dispatch.env.example").read_text()
    # both keys are present as commented-out (dark-by-default) lines, never an active assignment
    assert re.search(r"^#\s*YR_SHADOW_MODEL=\S+", text, re.MULTILINE)
    assert re.search(r"^#\s*YR_SHADOW_BASE_URL=\S+", text, re.MULTILINE)
    assert not re.search(r"^YR_SHADOW_MODEL=", text, re.MULTILINE)       # never active
    assert not re.search(r"^YR_SHADOW_BASE_URL=", text, re.MULTILINE)    # never active
