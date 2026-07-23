"""Acceptance tests for issue #274 — CI stance: server_ci drives the evaluator condition and the arming
wall.

Derived from the issue's acceptance criteria (the spec), NOT from the implementation's internals:

  1. The evaluator reads the repo's server-CI stance from the manifest key `server_ci`
     (`required`|`none`) at the base ref's tip at DECISION time, defaulting to `required` — today's
     behavior.
  2. `server_ci = none` passes the CI condition BY DECLARATION — a rollup state that names the
     declaration and is distinguishable from a real green rollup (never a bare empty-rollup failure) —
     and the durable record states the declared stance and its source.
  3. `required` or undeclared is judged IDENTICALLY to today, `empty_after_grace` included.
  4. Armed (`auto_merge = true` at decision time) + declared `server_ci = none` is a conflicting pair —
     no independent CI to gate an autonomous merge on — and refuses fail-closed, naming BOTH conflicting
     declarations.
  5. A declared value that is neither `required` nor `none` blocks fail-closed, stating the rejected
     value and the governing rule — never a silent fallback to the default.
  6. The `--re-evaluate` path applies the SAME declaration read (both its record-carrying and its
     record-less shape), never a duplicate/divergent read.

Reuses the stubbed-runner fixtures from test_dev_runner.py (git repo, issue/item JSON, timeline),
test_autonomous_merge.py's armed-repo fixtures (arming/shadow-completion/block helpers), and
test_dev_runner_reevaluate.py's --re-evaluate fixtures (first real build + a second re-evaluate
invocation) — the canonical harness home per tests/harness/contract.md; no private stub is defined here
beyond a `.yr/factory.toml` manifest writer, mirroring test_merge_ci_timeout.py's `_write_manifest` (the
issue #263 precedent this issue is modeled on).

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json, os, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td
import test_autonomous_merge as tam
import test_dev_runner_reevaluate as tdr
import test_merge_ci_timeout as tmc   # reuse _bundle()/_all_pass() for the merge_shadow unit tests

ROOT = td.ROOT
RUNNER = td.RUNNER
READABLE_IDS = td.READABLE_IDS
EMDASH = td.EMDASH
CR_OK, CR_FAIL = td.CR_OK, td.CR_FAIL

sys.path.insert(0, str(ROOT / "tools"))
import merge_shadow  # noqa: E402


# ---- manifest writer ---------------------------------------------------------------------------------

def _write_manifest(work, content):
    # check_cmd is required (issue #275, no built-in fallback) — prepended so every caller's own
    # server_ci content is unaffected while the manifest still satisfies the required-ness gate.
    (work / ".yr" / "factory.toml").write_text('check_cmd = "true"\n' + content)
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "set server_ci"], work)
    td._git(["push", "-q", "origin", "main"], work)


def _shadow_env(tmp_path, *, title, checks, manifest=None, extra=None):
    """A non-armed (shadow-mode) run, optionally with a `.yr/factory.toml` manifest committed to
    origin/main before the run — the only lever an acceptance test needs beyond the manifest itself.
    Registration grace is collapsed to 0 so an empty-checks scenario fails fast, deterministically."""
    work, _ = td._make_repo(tmp_path)
    if manifest is not None:
        _write_manifest(work, manifest)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, checks)
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    env["MERGE_CI_REG_GRACE"] = "0"; env["MERGE_CI_REG_POLL_INTERVAL"] = "0"
    if extra:
        env.update(extra)
    return env, work


def _run(env, *, timeout=60):
    full = {**os.environ, **READABLE_IDS, **env}
    return subprocess.run(["bash", str(RUNNER), "5", "--repo", "test/repo"],
                          capture_output=True, text=True, env=full, cwd=str(ROOT), timeout=timeout)


def _first_build_declaring(tmp_path, *, number, title, manifest, checks=(CR_OK,), extra=None):
    """Like `test_dev_runner_reevaluate.py`'s `_first_build`, but commits `manifest` BEFORE the build
    runs, so the declared server_ci lands on the SAME commit main's tip already carries at build time —
    the branch's recorded base_sha never drifts from main's tip. Committing the manifest change AFTER a
    first build (the way test_merge_ci_timeout.py's armed/manifest tests do for a single build) would
    advance main's tip past the branch's base and trip the UNRELATED freshness condition — a confound
    this suite must not introduce into a --re-evaluate acceptance test."""
    work, origin = td._make_repo(tmp_path)
    _write_manifest(work, manifest)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=number, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, list(checks))
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    if extra:
        env.update(extra)
    r = td._run([str(number), "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    run_dirs = list((tmp_path / "drhome" / "runs").glob(f"{number}-*"))
    assert run_dirs, "the first build created no run dir"
    run_dir = run_dirs[0]
    branch = tdr._branch_name(work, number)
    head_oid = subprocess.run(["git", "-C", str(work), "rev-parse", f"origin/{branch}"],
                              capture_output=True, text=True, check=True).stdout.strip()
    return work, origin, env, run_dir, branch, head_oid


# ============ criterion 1: read from the manifest key `server_ci`, default `required` ==================

def test_default_required_and_source_default_when_no_manifest_key(tmp_path):
    """No `server_ci` key at all (the bare seeded manifest) -> today's behavior: a green rollup passes,
    and the record labels the stance 'required' with source 'default'."""
    env, _ = _shadow_env(tmp_path, title="default required", checks=[CR_OK])
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "success"
    assert rec["server_ci"] == "required"
    assert rec["server_ci_source"] == "default"


def test_explicit_required_manifest_value_labeled_manifest_source(tmp_path):
    """An explicit `server_ci = "required"` behaves exactly like the default, but labels its source
    'manifest' (the source distinguishes an explicit declaration from an absent key)."""
    env, _ = _shadow_env(tmp_path, title="explicit required", checks=[CR_OK],
                         manifest='server_ci = "required"\n')
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "success"
    assert rec["server_ci"] == "required"
    assert rec["server_ci_source"] == "manifest"


def test_manifest_value_read_from_base_ref_tip_not_stale_working_tree(tmp_path):
    """`server_ci = none` is honored from origin/main's CURRENT tip: the value lives ONLY on the ref (the
    base checkout's own working tree has drifted behind and no longer carries it) — proving a
    decision-time read, never a start-of-run/working-tree copy, same convention as
    `test_merge_ci_timeout.py::test_manifest_value_read_from_base_ref_tip_not_stale_working_tree`."""
    work, _ = td._make_repo(tmp_path)
    _write_manifest(work, 'server_ci = "none"\n')
    td._git(["reset", "--hard", "HEAD~1"], work)          # working tree drifts: manifest gone locally
    assert "server_ci" not in (work / ".yr" / "factory.toml").read_text()
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="decision-time read"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, [CR_OK])
    env["MERGE_CI_POLL_INTERVAL"] = "0"; env["MERGE_CI_TIMEOUT"] = "0"
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "not_required_declared"
    assert rec["server_ci"] == "none" and rec["server_ci_source"] == "manifest"


# ============ criterion 2: declared none passes by declaration, distinguishable, record names it =======

def test_declared_none_passes_by_declaration_without_polling_rollup(tmp_path):
    """`server_ci = none` short-circuits BEFORE any rollup poll (issue text): even though the rollup would
    have been readable, the evaluator never asks for it — proven by a call counter that would exist the
    moment even a single `gh pr view --json statusCheckRollup` fired."""
    env, _ = _shadow_env(tmp_path, title="declared none, no poll", checks=[CR_OK],
                         manifest='server_ci = "none"\n')
    env["STUB_ROLLUP_CALLS"] = str(tmp_path / "rollup_calls")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "rollup_calls").exists(), \
        "the rollup was polled even though a declared server_ci=none must short-circuit before any poll"
    body = td._shadow_body(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == td.WOULD_MERGE
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "not_required_declared"


def test_declared_none_state_distinguishable_from_real_green_rollup(tmp_path):
    """The declared-none pass state must never be mistaken for a real green rollup: it is a distinct
    string ('not_required_declared' != 'success'), and the record's checks list stays empty — never the
    real (would-be-green) check list, which proves the rollup itself was never consulted."""
    env, _ = _shadow_env(tmp_path, title="declared none distinguishable", checks=[CR_OK],
                         manifest='server_ci = "none"\n')
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "not_required_declared"
    assert rec["check_rollup"] != "success"
    assert rec["checks"] == []


def test_declared_none_record_states_stance_and_source(tmp_path):
    """The durable record names both the declared stance and where it came from."""
    env, _ = _shadow_env(tmp_path, title="declared none names stance+source", checks=[CR_OK],
                         manifest='server_ci = "none"\n')
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["server_ci"] == "none"
    assert rec["server_ci_source"] == "manifest"
    assert rec["decision"] == "WOULD-MERGE" and rec["failed_condition"] is None


# ============ criterion 3: required/undeclared judged identically to today, empty_after_grace kept ======

def test_undeclared_still_gets_empty_after_grace_state(tmp_path):
    """A repo with no `server_ci` key and genuinely no CI (an empty rollup) must still fail fast with
    'empty_after_grace' exactly as before server_ci existed — server_ci is a no-op on this path."""
    env, _ = _shadow_env(tmp_path, title="undeclared empty after grace", checks=[])
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "empty_after_grace"
    assert rec["server_ci"] == "required" and rec["server_ci_source"] == "default"


def test_required_explicit_still_fails_on_failing_checks(tmp_path):
    """An explicit `server_ci = "required"` still judges a failing rollup as a real failure — byte
    identical to the default/undeclared path other than the source label."""
    env, _ = _shadow_env(tmp_path, title="required explicit failing", checks=[CR_FAIL],
                         manifest='server_ci = "required"\n')
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "failure"
    assert rec["server_ci"] == "required" and rec["server_ci_source"] == "manifest"


# ============ criterion 4: armed + declared none refuses fail-closed, naming both declarations =========

def test_armed_declared_none_refuses_fail_closed_naming_both_declarations(tmp_path):
    """auto_merge = true AND server_ci = none, both read at decision time from the manifest: a conflicting
    pair — no independent CI to gate an autonomous merge on — so the factory refuses to merge, posting a
    durable YR-MERGE: BLOCKED record and a Blocked comment naming BOTH declarations, even with an
    otherwise-complete shadow window (proving the wall fires independent of shadow completion)."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; tam._stubs(binp)
    _write_manifest(work, 'auto_merge = true\nserver_ci = "none"\n')
    env = tam._armed_env(tmp_path, binp, work, origin, prs=tam._complete_prs(), auto_merge=None)
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not tam._merged_stub(tmp_path)                          # never merges on this conflicting pair
    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} server_ci_none_armed"
    rec = tam._block(body)
    assert rec["server_ci"] == "none" and rec["server_ci_source"] == "manifest"
    assert rec["auto_merge"] is True
    tl = td._timeline(tmp_path)
    assert tam._blocked(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "server_ci_none_armed" in comments
    assert "server_ci = none" in comments and "auto_merge = true" in comments   # both declarations named


def test_armed_declared_required_still_merges_normally(tmp_path):
    """A regression guard: armed + an explicit `server_ci = "required"` merges exactly as armed +
    undeclared always has — the new conflicting-pair wall only fires on `none`."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; tam._stubs(binp)
    _write_manifest(work, 'auto_merge = true\nserver_ci = "required"\n')
    env = tam._armed_env(tmp_path, binp, work, origin, prs=tam._complete_prs(), auto_merge=None)
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert tam._merged_stub(tmp_path)
    body = tam._merge_record(tmp_path)
    assert body.splitlines()[0] == "YR-MERGE: MERGED"
    rec = tam._block(body)
    assert rec["server_ci"] == "required" and rec["server_ci_source"] == "manifest"


# ============ criterion 5: a malformed declared value blocks fail-closed, naming it + the rule ==========

def test_malformed_manifest_value_blocks_fail_closed_shadow(tmp_path):
    env, _ = _shadow_env(tmp_path, title="malformed server_ci", checks=[CR_OK],
                         manifest='server_ci = "sometimes"\n')
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "server_ci_invalid"
    assert rec["server_ci_rejected"] == "sometimes"
    assert rec["server_ci"] is None                        # never silently falls back to the default
    td._assert_not_blocked_and_in_review(td._timeline(tmp_path), r)


def test_malformed_non_string_manifest_value_blocks_fail_closed(tmp_path):
    """A type mismatch (a bare boolean, e.g. a typo meant for auto_merge) is rejected the same as any
    other value outside {required, none} — never coerced or silently defaulted."""
    env, _ = _shadow_env(tmp_path, title="malformed boolean server_ci", checks=[CR_OK],
                         manifest="server_ci = true\n")
    r = _run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "server_ci_invalid"
    assert rec["server_ci_rejected"] is not None and "true" in rec["server_ci_rejected"].lower()
    assert rec["server_ci"] is None


def test_armed_malformed_manifest_value_blocks_and_states_rejected_value_and_rule(tmp_path):
    """Acceptance, armed regime: a malformed `server_ci` for an armed, shadow-complete repo BLOCKS (never
    merges), and the posted Blocked comment states the rejected value and the governing rule (must be
    `required` or `none`) — never a silent fallback to the default."""
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; tam._stubs(binp)
    _write_manifest(work, 'server_ci = "sometimes"\n')
    env = tam._armed_env(tmp_path, binp, work, origin, prs=tam._complete_prs())
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not tam._merged_stub(tmp_path)                  # never merges on a malformed declaration
    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} ci_green"
    rec = tam._block(body)
    assert rec["check_rollup"] == "server_ci_invalid"
    assert rec["server_ci_rejected"] == "sometimes"
    assert rec["server_ci"] is None
    tl = td._timeline(tmp_path)
    assert tam._blocked(tl)
    comments = " ".join(td._comments(tl)).lower()
    assert "sometimes" in comments
    assert "'required'" in comments and "'none'" in comments   # the governing rule names both legal values


# ============ criterion 6: --re-evaluate applies the SAME declaration read, both reeval shapes ==========

def test_reevaluate_record_less_declared_none_passes_by_declaration(tmp_path):
    """Issue #239 shape (no prior record), non-armed: the re-evaluate path reads server_ci itself and
    passes by declaration, exactly like the live build path — and never merges (non-armed)."""
    work, origin, env1, run_dir, branch, head_oid = _first_build_declaring(
        tmp_path, number=23, title="Reeval record-less declared none", manifest='server_ci = "none"\n')
    env2 = tdr._reeval_env(tmp_path, env1, pr_number=202, head_ref=branch, head_oid=head_oid, comments=[])
    r = tdr._run_reeval(23, 202, env2)
    assert r.returncode == 0, r.stderr
    body = tdr._reeval_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "not_required_declared"
    assert rec["server_ci"] == "none" and rec["server_ci_source"] == "manifest"
    assert not tdr._merged_stub(tmp_path)


def test_reevaluate_record_less_malformed_server_ci_blocks_fail_closed(tmp_path):
    """Issue #239 shape, a malformed declared value: blocks fail-closed exactly like the live build
    path, naming the rejected value in the record — no silent default."""
    work, origin, env1, run_dir, branch, head_oid = tdr._first_build(
        tmp_path, number=24, title="Reeval record-less malformed server_ci")
    _write_manifest(work, 'server_ci = "sometimes"\n')
    env2 = tdr._reeval_env(tmp_path, env1, pr_number=203, head_ref=branch, head_oid=head_oid, comments=[])
    r = tdr._run_reeval(24, 203, env2)
    assert r.returncode == 0, r.stderr
    body = tdr._reeval_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith(f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "server_ci_invalid"
    assert rec["server_ci_rejected"] == "sometimes"
    assert rec["server_ci"] is None


def test_reevaluate_record_less_armed_declared_none_refuses_fail_closed(tmp_path):
    """Issue #239 shape, armed: the SAME conflicting-pair wall the live build path enforces also fires on
    --re-evaluate — a durable BLOCKED record (the armed-path reeval record file), never a merge."""
    work, origin, env1, run_dir, branch, head_oid = _first_build_declaring(
        tmp_path, number=25, title="Reeval record-less armed declared none",
        manifest='auto_merge = true\nserver_ci = "none"\n')
    env2 = tdr._reeval_env(tmp_path, env1, pr_number=204, head_ref=branch, head_oid=head_oid, comments=[],
                           prs=tam._complete_prs())
    r = tdr._run_reeval(25, 204, env2)
    assert r.returncode == 0, r.stderr
    assert not tdr._merged_stub(tmp_path)
    body = tdr._reeval_record_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith(f"YR-MERGE: BLOCKED {EMDASH} server_ci_none_armed")
    rec = td._shadow_block(body)
    assert rec["server_ci"] == "none" and rec["server_ci_source"] == "manifest"
    assert rec["auto_merge"] is True
    assert tdr._reeval_body(run_dir) is None                # never the shadow-path file on this path


def test_reevaluate_prior_record_declared_none_names_stance_in_shadow_supersession(tmp_path):
    """Issue #70 shape (a prior record exists — always a shadow supersession, an armed repo included):
    the shared declaration read still applies, naming the stance in the superseding record."""
    work, origin, env1, run_dir, branch, head_oid = _first_build_declaring(
        tmp_path, number=26, title="Reeval prior-record declared none", manifest='server_ci = "none"\n')
    run_id = run_dir.name
    comments = [tdr._rec_comment("WOULD-BLOCK", run_id=run_id, failed_condition="freshness")]
    env2 = tdr._reeval_env(tmp_path, env1, pr_number=91, head_ref=branch, head_oid=head_oid, comments=comments)
    r = tdr._run_reeval(26, 91, env2)
    assert r.returncode == 0, r.stderr
    body = tdr._reeval_body(run_dir)
    assert body is not None
    assert body.splitlines()[0].startswith("YR-MERGE-SHADOW: WOULD-MERGE")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "not_required_declared"
    assert rec["server_ci"] == "none" and rec["server_ci_source"] == "manifest"


# ============ unit tests: merge_shadow.py's server_ci fields (module + CLI) ============================

def test_build_record_carries_server_ci_and_source():
    rec = merge_shadow.build_record(
        results=tmc._all_pass(), bundle=tmc._bundle(), base_sha="b" * 40, head_sha="h" * 40,
        main_tip_sha="b" * 40, checks=[], check_rollup="not_required_declared",
        run_id="5-1", timestamp="2026-07-23T00:00:00Z",
        server_ci="none", server_ci_source="manifest",
    )
    assert rec["server_ci"] == "none"
    assert rec["server_ci_source"] == "manifest"
    assert rec["server_ci_rejected"] is None


def test_build_record_carries_server_ci_rejected_without_value():
    r = tmc._all_pass(); r["ci_green"] = "fail"
    rec = merge_shadow.build_record(
        results=r, bundle=tmc._bundle(), base_sha="b" * 40, head_sha="h" * 40,
        main_tip_sha="b" * 40, checks=[], check_rollup="server_ci_invalid",
        run_id="5-1", timestamp="2026-07-23T00:00:00Z",
        server_ci_rejected="sometimes", server_ci_source="manifest",
    )
    assert rec["server_ci"] is None
    assert rec["server_ci_rejected"] == "sometimes"
    assert rec["check_rollup"] == "server_ci_invalid"
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "ci_green"


def test_record_cli_passes_through_server_ci_and_source(tmp_path):
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(tmc._bundle()))
    out = tmp_path / "comment.md"
    subprocess.run([
        sys.executable, str(ROOT / "tools" / "merge_shadow.py"), "record",
        "--ci-green", "pass", "--freshness", "pass", "--terminal-approval", "pass", "--rank-gate", "pass",
        "--bundle", str(bundle), "--base-sha", "b" * 40, "--head-sha", "h" * 40,
        "--main-tip-sha", "m" * 40, "--ci-state", "not_required_declared",
        "--server-ci", "none", "--server-ci-source", "manifest",
        "--run-id", "5-1", "--timestamp", "2026-07-23T00:00:00Z", "--out", str(out),
    ], capture_output=True, text=True, check=True)
    text = out.read_text()
    assert text.splitlines()[0] == "YR-MERGE-SHADOW: WOULD-MERGE"
    start = text.index("```yr-merge-record") + len("```yr-merge-record")
    rec = json.loads(text[start:][: text[start:].index("```")])
    assert rec["server_ci"] == "none"
    assert rec["server_ci_source"] == "manifest"
    assert rec["check_rollup"] == "not_required_declared"


def test_record_cli_passes_through_server_ci_rejected(tmp_path):
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(tmc._bundle()))
    out = tmp_path / "comment.md"
    subprocess.run([
        sys.executable, str(ROOT / "tools" / "merge_shadow.py"), "record",
        "--ci-green", "fail", "--freshness", "pass", "--terminal-approval", "pass", "--rank-gate", "pass",
        "--bundle", str(bundle), "--base-sha", "b" * 40, "--head-sha", "h" * 40,
        "--main-tip-sha", "m" * 40, "--ci-state", "server_ci_invalid",
        "--server-ci-rejected", "sometimes", "--server-ci-source", "manifest",
        "--run-id", "5-1", "--timestamp", "2026-07-23T00:00:00Z", "--out", str(out),
    ], capture_output=True, text=True, check=True)
    text = out.read_text()
    assert text.splitlines()[0] == f"YR-MERGE-SHADOW: WOULD-BLOCK {EMDASH} ci_green"
    start = text.index("```yr-merge-record") + len("```yr-merge-record")
    rec = json.loads(text[start:][: text[start:].index("```")])
    assert rec["server_ci"] is None
    assert rec["server_ci_rejected"] == "sometimes"
    assert rec["check_rollup"] == "server_ci_invalid"


def test_record_cli_rejects_server_ci_value_outside_declared_choices(tmp_path):
    """The CLI's --server-ci flag only ever carries a resolved, legal value ('' / 'required' / 'none') —
    a rejected raw manifest value travels through --server-ci-rejected instead, never through
    --server-ci itself. Guards that boundary at the argparse layer."""
    bundle = tmp_path / "bundle.json"; bundle.write_text(json.dumps(tmc._bundle()))
    r = subprocess.run([
        sys.executable, str(ROOT / "tools" / "merge_shadow.py"), "record",
        "--ci-green", "pass", "--freshness", "pass", "--terminal-approval", "pass", "--rank-gate", "pass",
        "--bundle", str(bundle), "--base-sha", "b" * 40, "--head-sha", "h" * 40,
        "--main-tip-sha", "m" * 40, "--ci-state", "server_ci_invalid",
        "--server-ci", "sometimes",
        "--run-id", "5-1", "--timestamp", "2026-07-23T00:00:00Z",
    ], capture_output=True, text=True)
    assert r.returncode != 0


# ============ documentation: AGENTS.md names the stance, its states, and the armed conflict =============

def test_agents_md_names_server_ci_stance_and_states(tmp_path):
    text = (ROOT / "AGENTS.md").read_text()
    idx = text.index("`server_ci`")
    para = text[idx: idx + 700]
    assert "required" in para and "none" in para
    assert "not_required_declared" in para
    assert "server_ci_none_armed" in para
    assert "#274" in para
