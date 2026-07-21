"""Acceptance tests for issue #263 — merge evaluator: the bounded CI wait becomes `merge_ci_timeout`.

Derived from the issue's acceptance criteria (the spec), NOT from the implementation's internals:

  1. The evaluator reads the bounded CI wait from the target repo's `.yr/factory.toml` key
     `merge_ci_timeout` (integer seconds), precedence `MERGE_CI_TIMEOUT` env override > manifest >
     default 1200.
  2. The manifest value is read from the base ref's CURRENT tip at decision time, never a
     start-of-run copy.
  3. When in-flight CI concludes before the window expires, the evaluator proceeds on the concluded
     result without waiting out the remainder (today's poll-and-exit behavior, preserved).
  4. When the window expires with CI still in flight, `ci_green` classifies `timed_out` and the merge
     blocks fail-closed, exactly as today.
  5. A `timed_out` block's durable record states the effective window in seconds and its source
     (`env`, `manifest`, or `default`).
  6. A manifest value that does not parse as a positive integer blocks fail-closed with a record
     stating the rejected value and the governing rule — no silent fallback to the default.
  7. `merge_ci_timeout` is documented on AGENTS.md's manifest-keys line and in
     skills/factory/references/pipeline.md alongside `MERGE_CI_TIMEOUT` and the `timed_out` state.

Reuses the stubbed-runner fixtures from `test_dev_runner.py` (git repo, issue/item JSON, timeline,
gh/claude/check stubs) for the shadow (non-armed) scenarios, and `test_autonomous_merge.py`'s armed-repo
fixtures for the armed-block scenarios. Both suites are the canonical harness home per
tests/harness/contract.md; no private stub is defined here.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json, os, subprocess, sys, time, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td
import test_autonomous_merge as tam

ROOT = td.ROOT
RUNNER = td.RUNNER
READABLE_IDS = td.READABLE_IDS
EMDASH = td.EMDASH
CR_OK, CR_FAIL, CR_INFLIGHT = td.CR_OK, td.CR_FAIL, td.CR_INFLIGHT

sys.path.insert(0, str(ROOT / "tools"))
import merge_shadow  # noqa: E402


# ---- env builders -----------------------------------------------------------------------------------

def _write_manifest(work, content):
    (work / ".yr" / "factory.toml").write_text(content)
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "set merge_ci_timeout"], work)
    td._git(["push", "-q", "origin", "main"], work)


def _shadow_env(tmp_path, *, title, checks, manifest=None, extra=None):
    """A non-armed (shadow-mode) run, optionally with a `.yr/factory.toml` manifest committed to
    origin/main before the run — the only lever an acceptance test needs beyond MERGE_CI_TIMEOUT/env."""
    work, _ = td._make_repo(tmp_path)
    if manifest is not None:
        _write_manifest(work, manifest)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, checks)
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    # NB: MERGE_CI_TIMEOUT is intentionally left UNSET here (unlike td._shadow_env) — precedence
    # among env / manifest / default is exactly what these tests exercise.
    if extra:
        env.update(extra)
    return env, work


def _run(env, *, timeout=60):
    full = {**os.environ, **READABLE_IDS, **env}
    return subprocess.run(["bash", str(RUNNER), "5", "--repo", "test/repo"],
                          capture_output=True, text=True, env=full, cwd=str(ROOT), timeout=timeout)


# ============ criterion 1: precedence — MERGE_CI_TIMEOUT env > manifest > default 1200, source label =

def test_env_override_wins_over_manifest_and_names_env_as_source(tmp_path):
    """An explicit MERGE_CI_TIMEOUT env override wins even when the manifest declares a DIFFERENT
    value — the record carries the env value and labels its source 'env'."""
    env, _ = _shadow_env(tmp_path, title="env wins", checks=[CR_OK],
                         manifest="merge_ci_timeout = 45\n", extra={"MERGE_CI_TIMEOUT": "99"})
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body is not None
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "success"
    assert rec["ci_timeout_seconds"] == 99
    assert rec["ci_timeout_source"] == "env"


def test_manifest_wins_over_default_when_no_env_override(tmp_path):
    """With no env override, the manifest's `merge_ci_timeout` is honored and labeled 'manifest'."""
    env, _ = _shadow_env(tmp_path, title="manifest wins", checks=[CR_OK],
                         manifest="merge_ci_timeout = 45\n")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["ci_timeout_seconds"] == 45
    assert rec["ci_timeout_source"] == "manifest"


def test_default_1200_used_when_neither_env_nor_manifest_key_present(tmp_path):
    """No env override and a manifest that carries no `merge_ci_timeout` key at all -> the built-in
    default of 1200, labeled 'default'. Also proves the huge default never makes an ALREADY-CONCLUDED
    CI read stall (poll-and-exit, criterion 3): the run must still finish quickly."""
    env, _ = _shadow_env(tmp_path, title="default used", checks=[CR_OK])   # bare seeded manifest
    t0 = time.time()
    r = _run(env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 30, f"a concluded rollup must not pay any part of the 1200s default window ({elapsed}s)"
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["ci_timeout_seconds"] == 1200
    assert rec["ci_timeout_source"] == "default"


# ============ criterion 2: the manifest is read from the base ref's CURRENT tip at decision time ======

def test_manifest_value_read_from_base_ref_tip_not_stale_working_tree(tmp_path):
    """The manifest's `merge_ci_timeout` is honored from origin/main's CURRENT tip: the value lives
    ONLY on the ref (the base checkout's own working tree has drifted behind and no longer carries it),
    proving a decision-time read, never a start-of-run/working-tree copy — same convention as
    `read_auto_merge` (test_autonomous_merge.py::test_armed_reads_auto_merge_from_base_ref_tip...)."""
    work, _ = td._make_repo(tmp_path)
    _write_manifest(work, "merge_ci_timeout = 45\n")
    td._git(["reset", "--hard", "HEAD~1"], work)          # working tree drifts: manifest gone locally
    assert "merge_ci_timeout" not in (work / ".yr" / "factory.toml").read_text()
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="decision-time read"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, [CR_OK])
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["ci_timeout_seconds"] == 45
    assert rec["ci_timeout_source"] == "manifest"


# ============ criterion 3: CI concluding mid-poll proceeds without waiting out the window =============

def test_ci_concludes_mid_poll_proceeds_without_waiting_out_the_window(tmp_path):
    """In-flight on the FIRST poll, concluded on the second (as a real CI run finishing between polls
    would look) — with a window far longer than the test itself should take. The evaluator must exit
    the moment it observes the conclusion, not wait out the remainder of the window."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="concludes mid-poll"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON_1"] = td._rollup(tmp_path, [CR_INFLIGHT])
    rollup2 = tmp_path / "rollup2.json"
    rollup2.write_text(json.dumps({"statusCheckRollup": [CR_OK]}))
    env["STUB_ROLLUP_JSON_2"] = str(rollup2)
    env["STUB_ROLLUP_CALLS"] = str(tmp_path / "rollup_calls")
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    env["MERGE_CI_TIMEOUT"] = "300"
    t0 = time.time()
    r = _run(env)
    elapsed = time.time() - t0
    assert r.returncode == 0, r.stderr
    assert elapsed < 30, f"the evaluator waited out (part of) the 300s window instead of exiting on conclusion ({elapsed}s)"
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "success"                       # concluded, not timed_out
    assert rec["ci_timeout_seconds"] == 300 and rec["ci_timeout_source"] == "env"


# ============ criteria 4 & 5: a timed-out window blocks fail-closed, record states window + source ===

def test_timed_out_record_states_effective_window_and_env_source(tmp_path):
    """In-flight CI that never concludes within an env-overridden window -> `ci_green` fails as
    `timed_out`, and the record names the effective window (seconds) and its source ('env')."""
    env, _ = _shadow_env(tmp_path, title="timed out via env", checks=[CR_INFLIGHT],
                         extra={"MERGE_CI_TIMEOUT": "0"})
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "timed_out"
    assert rec["ci_timeout_seconds"] == 0
    assert rec["ci_timeout_source"] == "env"
    td._assert_not_blocked_and_in_review(td._timeline(tmp_path), r)


def test_timed_out_record_states_effective_window_and_manifest_source(tmp_path):
    """Same, but the effective window comes from the MANIFEST (no env override) — the record's source
    label must track the precedence actually used, not just always say 'env'."""
    env, _ = _shadow_env(tmp_path, title="timed out via manifest", checks=[CR_INFLIGHT],
                         manifest="merge_ci_timeout = 1\n")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "timed_out"
    assert rec["ci_timeout_seconds"] == 1
    assert rec["ci_timeout_source"] == "manifest"


def test_armed_timed_out_blocks_and_names_window_and_source_in_the_comment(tmp_path):
    """Acceptance, armed regime: a bounded-wait timeout for an armed, shadow-complete repo BLOCKS
    (never merges) and the posted Blocked comment names the effective window and its source."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; tam._stubs(binp)
    env = tam._armed_env(tmp_path, binp, work, origin, checks=(CR_INFLIGHT,), prs=tam._complete_prs())
    env["MERGE_CI_TIMEOUT"] = "0"       # env override -> fast timeout, source 'env'
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not tam._merged_stub(tmp_path)
    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} ci_green"
    rec = tam._block(body)
    assert rec["check_rollup"] == "timed_out"
    assert rec["ci_timeout_seconds"] == 0 and rec["ci_timeout_source"] == "env"
    tl = td._timeline(tmp_path)
    assert tam._blocked(tl)
    comments = " ".join(td._comments(tl))
    assert "0s" in comments and "source: env" in comments


# ============ criterion 6: a malformed manifest value blocks fail-closed, never silently defaults =====

def test_non_integer_manifest_value_blocks_fail_closed_and_names_rejected_value(tmp_path):
    env, _ = _shadow_env(tmp_path, title="malformed non-integer", checks=[CR_OK],
                         manifest='merge_ci_timeout = "abc"\n')
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "timeout_invalid"
    assert rec["ci_timeout_rejected"] == "abc"
    assert rec["ci_timeout_seconds"] is None                # never silently falls back to the default
    td._assert_not_blocked_and_in_review(td._timeline(tmp_path), r)


def test_zero_manifest_value_blocks_fail_closed(tmp_path):
    """Zero is not a positive integer -> rejected, same as any other malformed value."""
    env, _ = _shadow_env(tmp_path, title="malformed zero", checks=[CR_OK],
                         manifest="merge_ci_timeout = 0\n")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "timeout_invalid"
    assert rec["ci_timeout_rejected"] == "0"
    assert rec["ci_timeout_seconds"] is None


def test_negative_manifest_value_blocks_fail_closed(tmp_path):
    env, _ = _shadow_env(tmp_path, title="malformed negative", checks=[CR_OK],
                         manifest="merge_ci_timeout = -5\n")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "timeout_invalid"
    assert rec["ci_timeout_rejected"] == "-5"
    assert rec["ci_timeout_seconds"] is None


def test_armed_malformed_manifest_value_blocks_and_records_the_governing_rule(tmp_path):
    """Acceptance, armed regime: a malformed `merge_ci_timeout` for an armed, shadow-complete repo
    BLOCKS (never merges), and the posted Blocked comment states the rejected value and the governing
    rule (a positive integer number of seconds) — never a silent fallback to the default."""
    work, origin = td._make_repo(tmp_path)
    _write_manifest(work, "merge_ci_timeout = -5\n")
    binp = tmp_path / "bin"; tam._stubs(binp)
    env = tam._armed_env(tmp_path, binp, work, origin, prs=tam._complete_prs(),
                         extra={"MERGE_CI_TIMEOUT": ""})   # no env override -> the manifest value governs
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not tam._merged_stub(tmp_path)                  # never merges on a malformed timeout
    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} ci_green"
    rec = tam._block(body)
    assert rec["check_rollup"] == "timeout_invalid"
    assert rec["ci_timeout_rejected"] == "-5"
    assert rec["ci_timeout_seconds"] is None
    tl = td._timeline(tmp_path)
    assert tam._blocked(tl)
    comments = " ".join(td._comments(tl))
    assert "-5" in comments
    assert "positive integer" in comments.lower()           # the governing rule is named, not just the value


# ============ criterion 7: docs name merge_ci_timeout / MERGE_CI_TIMEOUT / timed_out ==================

def test_agents_md_names_merge_ci_timeout_on_the_manifest_keys_line(tmp_path):
    text = (ROOT / "AGENTS.md").read_text()
    idx = text.index("`.yr/factory.toml` sets")
    para = text[idx: idx + 700]
    assert "check_cmd" in para and "auto_merge" in para       # the same bullet as the other manifest keys
    assert "merge_ci_timeout" in para
    assert "MERGE_CI_TIMEOUT" in para
    assert "1200" in para                                     # the default is named
    assert "timeout_invalid" in para                          # the malformed-value fail-closed state is named


def test_pipeline_md_describes_merge_ci_timeout_env_and_timed_out_state():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text()
    assert "merge_ci_timeout" in text and "MERGE_CI_TIMEOUT" in text
    assert "timed_out" in text and "timeout_invalid" in text
    # the two concepts are described together, not merely both present somewhere in the doc.
    idx = text.index("`merge_ci_timeout`")
    nearby = text[max(0, idx - 300): idx + 900]
    assert "MERGE_CI_TIMEOUT" in nearby
    assert "default" in nearby.lower()


# ============ unit tests: merge_shadow.py's ci_timeout fields (module + CLI) ===========================

def _bundle():
    return {
        "sha256": "abc123",
        "rounds": [{"index": 1, "verdict": "VERDICT: APPROVE", "transcript": "..."}],
        "build": {"name": "sonnet", "id": "claude-sonnet-5", "provider": "anthropic", "rank": 30, "ranked": True},
        "review": {"name": "opus", "id": "claude-opus-4-8", "provider": "anthropic", "rank": 40, "ranked": True},
    }


def _all_pass():
    return {"ci_green": "pass", "freshness": "pass", "terminal_approval": "pass", "rank_gate": "pass"}


def test_build_record_carries_ci_timeout_seconds_and_source():
    rec = merge_shadow.build_record(
        results=_all_pass(), bundle=_bundle(), base_sha="b" * 40, head_sha="h" * 40,
        main_tip_sha="b" * 40, checks=[], check_rollup="success",
        run_id="5-1", timestamp="2026-07-21T00:00:00Z",
        ci_timeout_seconds=45, ci_timeout_source="manifest",
    )
    assert rec["ci_timeout_seconds"] == 45
    assert rec["ci_timeout_source"] == "manifest"
    assert rec["ci_timeout_rejected"] is None


def test_build_record_carries_ci_timeout_rejected_without_seconds():
    r = _all_pass(); r["ci_green"] = "fail"
    rec = merge_shadow.build_record(
        results=r, bundle=_bundle(), base_sha="b" * 40, head_sha="h" * 40,
        main_tip_sha="b" * 40, checks=[], check_rollup="timeout_invalid",
        run_id="5-1", timestamp="2026-07-21T00:00:00Z",
        ci_timeout_rejected="abc", ci_timeout_source="manifest",
    )
    assert rec["ci_timeout_seconds"] is None
    assert rec["ci_timeout_rejected"] == "abc"
    assert rec["check_rollup"] == "timeout_invalid"
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "ci_green"


def test_record_cli_passes_through_ci_timeout_seconds_and_source(tmp_path):
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(_bundle()))
    out = tmp_path / "comment.md"
    subprocess.run([
        sys.executable, str(ROOT / "tools" / "merge_shadow.py"), "record",
        "--ci-green", "pass", "--freshness", "pass", "--terminal-approval", "pass", "--rank-gate", "pass",
        "--bundle", str(bundle), "--base-sha", "b" * 40, "--head-sha", "h" * 40,
        "--main-tip-sha", "m" * 40, "--ci-state", "success",
        "--ci-timeout-seconds", "45", "--ci-timeout-source", "manifest",
        "--run-id", "5-1", "--timestamp", "2026-07-21T00:00:00Z", "--out", str(out),
    ], capture_output=True, text=True, check=True)
    text = out.read_text()
    start = text.index("```yr-merge-record") + len("```yr-merge-record")
    rec = json.loads(text[start:][: text[start:].index("```")])
    assert rec["ci_timeout_seconds"] == 45
    assert rec["ci_timeout_source"] == "manifest"
    assert rec["ci_timeout_rejected"] is None


def test_record_cli_passes_through_ci_timeout_rejected(tmp_path):
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(_bundle()))
    out = tmp_path / "comment.md"
    subprocess.run([
        sys.executable, str(ROOT / "tools" / "merge_shadow.py"), "record",
        "--ci-green", "fail", "--freshness", "pass", "--terminal-approval", "pass", "--rank-gate", "pass",
        "--bundle", str(bundle), "--base-sha", "b" * 40, "--head-sha", "h" * 40,
        "--main-tip-sha", "m" * 40, "--ci-state", "timeout_invalid",
        "--ci-timeout-rejected", "abc", "--ci-timeout-source", "manifest",
        "--run-id", "5-1", "--timestamp", "2026-07-21T00:00:00Z", "--out", str(out),
    ], capture_output=True, text=True, check=True)
    text = out.read_text()
    assert text.splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} ci_green"
    start = text.index("```yr-merge-record") + len("```yr-merge-record")
    rec = json.loads(text[start:][: text[start:].index("```")])
    assert rec["ci_timeout_seconds"] is None
    assert rec["ci_timeout_rejected"] == "abc"
    assert rec["check_rollup"] == "timeout_invalid"
