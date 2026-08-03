"""Characterization pins for issue #385 — the manifest-read contract every one of the eight inline
`tools/dev-runner.sh` readers implements today (precedence, read time, fail-closed rejection), pinned so
the next slice (collapsing all eight onto one shared reader) is provably behavior-identical.

Derived from the issue's acceptance criteria (the spec), NOT from `tools/dev-runner.sh`'s internals.

This file is PURELY ACCRETIVE — it adds pins only, never modifies or duplicates one. Nine existing suites
already cover most of the per-key contract, read first per the issue's instruction:
`test_merge_ci_timeout.py`, `test_server_ci_stance.py`, `test_check_cmd_required.py`,
`test_check_gate_timeout.py`, `test_stage_conduct_manifest.py`, `test_test_surface_manifest.py`,
`test_repo_shape_defaults.py`, `test_manifest_fetch_freshness.py`, `test_autonomous_merge.py`. This file
adds only what's missing from that set — in particular the CROSS-KEY pins that state a contract spanning
more than one reader, not a single key's own behavior:

  1. Read time, the central pin (issue text: "the read-time pins are the ones that matter most"): each of
     the three decision-time keys (`merge_ci_timeout`, `server_ci`, `auto_merge`) is shown to follow a
     manifest change pushed to the base ref's tip AFTER this run's own start-of-run fetch — never a case
     the existing suites cover (their own read-time tests push the changed value BEFORE the run starts,
     which the run-start fetch would pick up either way, so they prove ref-tip-vs-stale-working-tree, not
     start-of-run-snapshot-vs-later-decision-time). The technique: a `.yr/factory.toml` V1 is committed
     before the run starts; a V2 commit is staged (but not yet pushed) in a separate clone; the CHECK
     stage's own command is swapped for a script that pushes V2 to origin as a side effect — CHECK runs
     strictly after the run-start manifest read and strictly before the terminal merge decision, so this
     reliably moves the tip in the one window that matters. Contrasted against `check_timeout` /
     `check_idle_timeout` (scalar, start-of-run) and `stage_conduct` (array, start-of-run) staying at V1
     in the SAME runs, so the distinction between the two groups is explicit, not asserted separately.
  2. Distinguishability: a whole-manifest TOML parse failure at DECISION time (the three decision-time
     keys) is a THIRD, distinct disposition — environmental/resumable, no record posted, PR still opens —
     never a silent default (as an absent key would be) and never a named fail-closed rejection (as a
     malformed declared value would be). This is genuinely different from `check_timeout`/
     `check_idle_timeout`, which (per `test_check_gate_timeout.py`, already pinned) conflate a parse
     failure with an absent key. That existing pin is the other half of this same contrast; this file
     only adds the decision-time half.
  3. The array channel's delimiter contract: the bulk scalar channel (`check_cmd`/`model`/`base_ref`/
     `review_model`/`lint_cmd`/`lint_fix_cmd`/`lens_cmd`) is newline-delimited on its way from python to
     bash and explicitly flattens an embedded newline in a declared value to a space (dev-runner.sh's own
     `.replace("\n", " ")`) — a real, silent mutation of the declared value. The array channel
     (`test_paths`/`artifact_globs`/`stage_conduct`) is NUL-delimited specifically to avoid this; an
     element carrying an embedded newline survives verbatim, and a later declared element still arrives
     intact. Pinned as a direct, same-shape-input contrast, not a claim about either channel in isolation.
  4. Precedence resolves independently PER KEY within one run, not per run: one run where `check_cmd` is
     env-sourced, `check_timeout` is manifest-sourced, and `check_idle_timeout` is default-sourced, all at
     once — the existing suites each vary exactly one key's precedence in isolation.
  5. Absent-key defaults are coherent all at once: a manifest declaring only the required `check_cmd` still
     resolves every other key's own independent default correctly, observed together in one run (the
     scalar timeouts, the array channel's absence, and the three decision-time keys' own defaults).

Reuses the shared harness only (`tests/test_dev_runner.py`'s fixtures, `tests/test_autonomous_merge.py`'s
armed-repo fixtures) — no private clone of the classifier or the gh/claude stubs.

Runs under `.venv/bin/python -m pytest tests/ -q` (attended); `pytest tests/ -q` in a cut build worktree.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td          # shared stub harness (gh/claude/check stubs + fixtures)
import test_autonomous_merge as tam   # armed-repo fixtures (arming/shadow-completion/block helpers)

ROOT = td.ROOT
EMDASH = td.EMDASH
HEADER = "Per-repo stage conduct (source: .yr/factory.toml, key stage_conduct):"


# ============ shared helpers ============

def _write_manifest(work, content):
    """Commit+push a `.yr/factory.toml` to origin/main — check_cmd is required (issue #275), so it's
    prepended unless the caller's own content already means to break parsing entirely (issue #276's
    whole-manifest-parse-failure pin passes deliberately-invalid TOML that must NOT be prefixed)."""
    (work / ".yr" / "factory.toml").write_text('check_cmd = "true"\n' + content)
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "manifest for cross-key contract pin"], work)
    td._git(["push", "-q", "origin", "main"], work)


CHECK_STUB_MUTATE = '''#!/usr/bin/env bash
echo CHECK >> "$STUB_TIMELINE"
git -C "$STUB_CHECK_PUSH_CLONE" push -q origin main
exit 0
'''


def _prepare_mid_run_mutation(tmp, origin, v2_content, *, name="mutate_clone"):
    """A clone of `origin`, carrying a V2 `.yr/factory.toml` COMMITTED LOCALLY but not yet pushed. Paired
    with `_mutator_check_cmd`, whose script pushes this clone's commit to origin as a side effect of the
    CHECK stage — moving the base ref's tip strictly AFTER the run's own start-of-run manifest read
    (which already ran, well before CHECK) and strictly BEFORE the terminal merge decision's own
    decision-time re-read (which runs after CHECK, PR-open, and review). `v2_content` is raw TOML text,
    exactly as `_write_manifest` writes it (caller's responsibility to include `check_cmd` if the scenario
    needs the manifest to still parse)."""
    clone = tmp / name
    td._git(["clone", "-q", str(origin), str(clone)], tmp)
    td._git(["config", "user.email", "t@t"], clone)
    td._git(["config", "user.name", "tester"], clone)
    (clone / ".yr" / "factory.toml").write_text(v2_content)
    td._git(["add", "-A"], clone)
    td._git(["commit", "-q", "-m", "mid-run manifest mutation"], clone)
    return clone


def _mutator_check_cmd(tmp, clone):
    """The env pair (`CHECK_CMD`, `STUB_CHECK_PUSH_CLONE`) that makes the CHECK stage itself the mid-run
    mutation trigger — install via `env["CHECK_CMD"], env["STUB_CHECK_PUSH_CLONE"] = _mutator_check_cmd(...)`."""
    script = tmp / "check_mutate.sh"
    td._exec(script, CHECK_STUB_MUTATE)
    return f"bash {script}", str(clone)


# ============ (1) read time — the three decision-time keys follow a tip that moves MID-RUN =============
# each case: V1 committed before the run starts; V2 pushed by the CHECK stage itself, after the run's own
# start-of-run manifest read but before the terminal merge decision's own decision-time re-read.

def test_merge_ci_timeout_follows_a_manifest_pushed_mid_run_while_check_timeout_keeps_the_start_of_run_value(tmp_path):
    """`merge_ci_timeout` (decision-time) picks up the value pushed to origin DURING this same run's CHECK
    stage; `check_timeout`/`check_idle_timeout` (start-of-run) do not — both stay at their V1 values, and
    the run's own log proves it, in the SAME run as the decision-time key moving."""
    work, origin = td._make_repo(tmp_path)
    _write_manifest(work, "check_timeout = 111\ncheck_idle_timeout = 113\nmerge_ci_timeout = 222\n")   # V1
    clone = _prepare_mid_run_mutation(tmp_path, origin, 'check_cmd = "true"\nmerge_ci_timeout = 888\n')  # V2

    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Decision-time key follows a mid-run push"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_CMD"], env["STUB_CHECK_PUSH_CLONE"] = _mutator_check_cmd(tmp_path, clone)
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, [td.CR_OK])
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    # start-of-run keys: unchanged by the mid-run push, still V1
    assert "check_timeout: 111s (source: manifest)" in r.stderr
    assert "check_idle_timeout: 113s (source: manifest)" in r.stderr
    assert "check_timeout: 888s" not in r.stderr
    assert "check_idle_timeout: 888s" not in r.stderr

    # decision-time key: DID follow the tip that moved mid-run, to V2
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["ci_timeout_seconds"] == 888
    assert rec["ci_timeout_source"] == "manifest"


def test_auto_merge_and_server_ci_follow_a_manifest_pushed_mid_run_the_conflicting_pair_wall_fires_on_the_new_declaration(tmp_path):
    """`auto_merge` and `server_ci` (both decision-time) are declared ONLY by the V2 manifest the CHECK
    stage pushes mid-run — V1 (the start-of-run snapshot) carries neither. The armed conflicting-pair wall
    (issue #274) still fires, naming both declarations, proving BOTH keys were read from the moved tip at
    decision time, not the start-of-run snapshot (which had neither key at all)."""
    work, origin = td._make_repo(tmp_path)
    _write_manifest(work, "")                                                                    # V1: bare
    clone = _prepare_mid_run_mutation(
        tmp_path, origin, 'check_cmd = "true"\nauto_merge = true\nserver_ci = "none"\n')          # V2

    binp = tmp_path / "bin"; tam._stubs(binp)
    env = tam._armed_env(tmp_path, binp, work, origin, prs=tam._complete_prs(), auto_merge=None)
    env["CHECK_CMD"], env["STUB_CHECK_PUSH_CLONE"] = _mutator_check_cmd(tmp_path, clone)
    r = tam._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert not tam._merged_stub(tmp_path)

    body = tam._merge_record(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == f"YR-MERGE: BLOCKED {EMDASH} server_ci_none_armed"
    rec = tam._block(body)
    assert rec["server_ci"] == "none" and rec["server_ci_source"] == "manifest"
    assert rec["auto_merge"] is True


def test_stage_conduct_delivered_block_keeps_the_start_of_run_declaration_despite_a_manifest_pushed_mid_run(tmp_path):
    """A THIRD start-of-run key, of the array (not scalar) shape: `stage_conduct`'s delivered stdin block
    reflects V1's declaration, never V2's — the IMPL/TEST stages' stdin was already sent before CHECK (and
    its mid-run push) ever runs, so this also pins the PIPELINE ORDER the read-time contract depends on."""
    work, origin = td._make_repo(tmp_path)
    _write_manifest(work, 'stage_conduct = ["first table"]\n')                                    # V1
    clone = _prepare_mid_run_mutation(
        tmp_path, origin, 'check_cmd = "true"\nstage_conduct = ["second table"]\n')               # V2

    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Array start-of-run key ignores mid-run push"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_CMD"], env["STUB_CHECK_PUSH_CLONE"] = _mutator_check_cmd(tmp_path, clone)
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    stdin_calls = td._stdin_stage_calls(tmp_path)
    assert "IMPL" in stdin_calls
    assert (HEADER + "\nfirst table") in stdin_calls["IMPL"][0]
    assert (HEADER + "\nsecond table") not in stdin_calls["IMPL"][0]


# ============ (2) distinguishability — decision time: a parse failure is a THIRD, distinct disposition ==

def test_decision_time_whole_manifest_parse_failure_is_environmental_never_a_default_or_a_named_rejection(tmp_path):
    """A manifest that fails to parse AT ALL, pushed mid-run so it lands only at DECISION time (never at
    the start-of-run read, which still saw a valid V1): `read_ci_timeout` (and `read_server_ci` behind it,
    same shape) return an environmental failure, not a fail-closed rejection and not a silent default —
    the run finishes with NO merge-shadow record posted at all, a plain warning naming the disposition,
    and the PR still opens normally (never Blocked). Contrast: an EQUIVALENT whole-manifest parse failure
    at the start-of-run scalar/typed channels is already pinned (test_check_gate_timeout.py) to silently
    default instead — this is the decision-time half of that same three-way distinction."""
    work, origin = td._make_repo(tmp_path)
    _write_manifest(work, "merge_ci_timeout = 45\n")                             # V1: valid
    broken = 'check_cmd = "true\nmerge_ci_timeout = [[[not valid toml\n'         # unterminated string -> whole parse fails
    clone = _prepare_mid_run_mutation(tmp_path, origin, broken)                  # V2: unparseable

    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Decision-time parse failure is environmental"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["CHECK_CMD"], env["STUB_CHECK_PUSH_CLONE"] = _mutator_check_cmd(tmp_path, clone)
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, [td.CR_OK])
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    assert "terminal merge step hit an environmental failure" in r.stderr
    assert "classified environmental" in r.stderr
    assert td._shadow_body(tmp_path) is None            # no record posted at all -- neither shadow nor block
    assert "https://stub/pr/1" in r.stdout               # the PR still opened normally
    tl = td._timeline(tmp_path)
    assert not any("REASONFIELD" in l and "Blocked" in l for l in td._edits(tl))   # never Blocked by this


# ============ (3) the array channel's delimiter contract, contrasted against the scalar channel =========

def test_bulk_scalar_channel_flattens_an_embedded_newline_in_a_declared_value_to_a_space(tmp_path):
    """The bulk scalar channel (`check_cmd`/`model`/`base_ref`/`review_model`/`lint_cmd`/`lint_fix_cmd`/
    `lens_cmd`) is newline-delimited on its way from python to bash — dev-runner.sh's own
    `str(d.get(k) or "").replace("\\n", " ")` -- so a declared value carrying an embedded newline is
    silently flattened to a space before it ever reaches a bash variable. Baseline for the array channel's
    contrasting behavior (next test)."""
    repo = td._manifest_repo(tmp_path, lint_cmd="eslint .\\nreally")   # TOML-escaped \n -> a real newline once parsed
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo)
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["lint_cmd"] == "eslint . really"


def test_array_channel_preserves_an_embedded_newline_within_a_declared_stage_conduct_element(tmp_path):
    """The array channel (`test_paths`/`artifact_globs`/`stage_conduct`) is NUL-delimited (`mapfile -d
    ''`) precisely to avoid the scalar channel's own flattening above: a declared element carrying an
    embedded newline survives to delivery VERBATIM (the newline is not flattened to a space, nor does it
    truncate or corrupt the declaration), and a subsequent declared element still arrives intact
    afterward — same-shape input (an embedded `\\n` inside a declared string), directly opposite
    behavior from the scalar channel."""
    work, _ = td._make_repo(tmp_path)
    _write_manifest(work, 'stage_conduct = ["eslint .\\nreally", "second entry"]\n')   # same escaped \n as above
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Array channel preserves an embedded newline"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    stdin_calls = td._stdin_stage_calls(tmp_path)
    expected = HEADER + "\neslint .\nreally\nsecond entry"   # the embedded newline survives, unflattened
    assert expected in stdin_calls["IMPL"][0]


# ============ (4) precedence resolves independently PER KEY within one run ==============================

def test_precedence_resolves_independently_per_key_within_a_single_run(tmp_path):
    """One run, three keys, three different precedence tiers at once: `check_cmd` from env, `check_timeout`
    from the manifest (no env override), `check_idle_timeout` from neither (the built-in default) — each
    key's own source is judged independently, not inherited from whichever tier another key in the same
    run happens to resolve at."""
    work, _ = td._make_repo(tmp_path)
    _write_manifest(work, "check_timeout = 77\n")   # check_idle_timeout stays entirely undeclared
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Mixed precedence tiers, one run"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    # env["CHECK_CMD"] is already set by the harness's own _base_env -> env-sourced by construction
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    assert f"check_cmd: '{env['CHECK_CMD']}' (source: env)" in r.stderr
    assert "check_timeout: 77s (source: manifest)" in r.stderr
    assert "check_idle_timeout: 300s (source: default)" in r.stderr


# ============ (5) absent-key defaults, coherent all at once =============================================

def test_sparse_manifest_defaults_every_other_key_coherently_in_one_run(tmp_path):
    """A manifest declaring only the required `check_cmd` (today's minimum) still resolves every other
    key's own default correctly, all observed together in ONE run: the two start-of-run scalar timeouts,
    the array channel's absence (no stage_conduct header at all — not even an empty one), and the three
    decision-time keys' own defaults (1200s/`default`, `required`/`default`, not armed)."""
    work, _ = td._make_repo(tmp_path)   # _make_repo seeds a bare manifest: check_cmd = "true" only
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Every other key defaults coherently"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON"] = td._rollup(tmp_path, [td.CR_OK])
    env["MERGE_CI_POLL_INTERVAL"] = "0"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    assert "check_timeout: 1200s (source: default)" in r.stderr
    assert "check_idle_timeout: 300s (source: default)" in r.stderr

    stdin_calls = td._stdin_stage_calls(tmp_path)
    assert HEADER not in stdin_calls["IMPL"][0]

    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["ci_timeout_seconds"] == 1200 and rec["ci_timeout_source"] == "default"
    assert rec["server_ci"] == "required" and rec["server_ci_source"] == "default"
    assert rec["auto_merge"] is False
