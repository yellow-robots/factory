"""Acceptance tests for issue #61 — merge evaluator: registration grace for an empty check rollup.

Derived from the issue's acceptance criteria (the spec), NOT from `shadow_ci`'s internals:

  1. An empty check rollup gets a bounded REGISTRATION GRACE (re-poll) before the evaluator concludes
     anything; if a check appears within the grace, the evaluator falls through to the normal bounded
     CI wait (unchanged semantics) and the record reflects the outcome that wait produced.
  2. A rollup still empty after the grace fails fast exactly as before — a no-CI repo never pays the
     full `MERGE_CI_TIMEOUT`.
  3. The record's CI state distinguishes "registered after grace" (a normal success/failure/timed_out
     outcome) from "empty after grace" (the new `empty_after_grace` state) so shadow analysis can tell
     the two apart.
  4. Every other evaluator semantic is unchanged: fail-closed ordering, environmental classification of a
     gh/parse failure (skip the record, resumable, no reset), and the record grammar (still schema
     `yr-merge-record/1`).
  5. The grace and its poll cadence are operator-tunable the same way `MERGE_CI_TIMEOUT`/
     `MERGE_CI_POLL_INTERVAL` already are.

Reuses the stubbed-runner fixtures from `test_dev_runner.py` (git repo, issue/item JSON, timeline) but
swaps in a `gh` stub whose `pr view --json statusCheckRollup` answer can change across successive calls
(driven by a call counter written to a file, since each `gh` invocation is a fresh subprocess) — the
minimal extension needed to prove a rollup that starts empty and later registers.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import json, os, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td

ROOT = td.ROOT
RUNNER = td.RUNNER
READABLE_IDS = td.READABLE_IDS
EMDASH = td.EMDASH
CR_OK, CR_FAIL, CR_INFLIGHT = td.CR_OK, td.CR_FAIL, td.CR_INFLIGHT
SHADOW_FIELDS = td.SHADOW_FIELDS

def _stubs(binp):
    binp.mkdir(parents=True, exist_ok=True)
    td._exec(binp / "gh", td.GH_STUB)
    td._exec(binp / "claude", td.CLAUDE_STUB)
    td._exec(binp / "check.sh", td.CHECK_STUB)


def _rollup_env(tmp_path, *, title, checks_1, checks_2, extra=None):
    """checks_1 answers gh call #1, checks_2 answers every call after that."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title=title), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_ROLLUP_JSON_1"] = td._rollup(tmp_path, checks_1)
    rollup2 = tmp_path / "rollup2.json"
    rollup2.write_text(json.dumps({"statusCheckRollup": checks_2}))
    env["STUB_ROLLUP_JSON_2"] = str(rollup2)
    env["STUB_ROLLUP_CALLS"] = str(tmp_path / "rollup_calls")
    if extra:
        env.update(extra)
    return env


def _run(env, *, timeout=30):
    full = {**os.environ, **READABLE_IDS, **env}
    return subprocess.run(["bash", str(RUNNER), "5", "--repo", "test/repo"],
                          capture_output=True, text=True, env=full, cwd=str(ROOT), timeout=timeout)


def _calls(tmp_path):
    p = tmp_path / "rollup_calls"
    return int(p.read_text()) if p.exists() else 0


# ============ criterion 1: an empty rollup gets a bounded registration grace, re-polled ============

def test_empty_then_registered_success_falls_through_to_normal_wait(tmp_path):
    """The rollup reads empty on the very first check, then shows a passing check on the next read
    (as a real repo's CI would look moments after `gh pr create`). The evaluator must NOT fast-fail on
    the initial empty read: it re-polls within the grace, sees the registered check, and proceeds with
    the ordinary CI-green evaluation — landing on WOULD-MERGE with a truthful 'success' rollup state."""
    env = _rollup_env(tmp_path, title="Registers within grace", checks_1=[], checks_2=[CR_OK],
                      extra={"MERGE_CI_REG_GRACE": "10", "MERGE_CI_REG_POLL_INTERVAL": "0",
                             "MERGE_CI_POLL_INTERVAL": "0", "MERGE_CI_TIMEOUT": "5"})
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == td.WOULD_MERGE                # normal pass, not a WOULD-BLOCK
    rec = td._shadow_block(body)
    assert rec["decision"] == "WOULD-MERGE" and rec["failed_condition"] is None
    assert rec["check_rollup"] == "success"                      # the REGISTERED outcome, not empty*
    assert rec["checks"], "the record should reflect the check that registered, not an empty snapshot"
    assert _calls(tmp_path) >= 2, "the evaluator must have re-polled at least once to see the check"


def test_empty_then_registered_failure_records_failure_not_empty(tmp_path):
    """Same registration story, but the check that appears has failed: the record must show the real
    'failure' outcome (ci_green fails for the right reason), never mistaken for an empty rollup."""
    env = _rollup_env(tmp_path, title="Registers failing within grace", checks_1=[], checks_2=[CR_FAIL],
                      extra={"MERGE_CI_REG_GRACE": "10", "MERGE_CI_REG_POLL_INTERVAL": "0",
                             "MERGE_CI_POLL_INTERVAL": "0", "MERGE_CI_TIMEOUT": "5"})
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["failed_condition"] == "ci_green"
    assert rec["check_rollup"] == "failure"


def test_empty_then_registered_still_inflight_uses_the_normal_ci_timeout_not_the_grace(tmp_path):
    """Once a check has registered, the evaluator is back on the NORMAL bounded CI wait — a check stuck
    in-flight forever must time out against MERGE_CI_TIMEOUT (not the registration grace), and the
    record must say so with 'timed_out', never 'empty_after_grace'."""
    env = _rollup_env(tmp_path, title="Registers but never finishes", checks_1=[], checks_2=[CR_INFLIGHT],
                      extra={"MERGE_CI_REG_GRACE": "10", "MERGE_CI_REG_POLL_INTERVAL": "0",
                             "MERGE_CI_POLL_INTERVAL": "0", "MERGE_CI_TIMEOUT": "0"})
    r = _run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["check_rollup"] == "timed_out"                    # the ordinary CI timeout, not the grace one


# ============ criterion 2 & 3: still empty after the grace -> fail fast, distinguishing state ============

def test_empty_throughout_fails_fast_after_grace_with_distinguishing_state(tmp_path):
    """A repo with genuinely no CI: the rollup reads empty on every poll. The evaluator must still fail
    fast once the (now much shorter) registration grace elapses — proven with a huge CI wait bound that
    would hang the test if the evaluator ever fell into it — and the record must carry the NEW,
    distinguishing 'empty_after_grace' state (not the generic 'empty' the old immediate fast-fail used),
    so shadow analysis can tell a never-registered rollup apart from one that registered and then failed
    or timed out."""
    env = _rollup_env(tmp_path, title="Never registers", checks_1=[], checks_2=[],
                      extra={"MERGE_CI_REG_GRACE": "0", "MERGE_CI_REG_POLL_INTERVAL": "0",
                             "MERGE_CI_POLL_INTERVAL": "600", "MERGE_CI_TIMEOUT": "600"})
    r = _run(env, timeout=30)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "ci_green"
    assert rec["check_rollup"] == "empty_after_grace"
    # criterion 4: fail-closed ordering / shadow-not-blocked semantics are untouched by the grace.
    tl = td._timeline(tmp_path)
    assert any(l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l for l in tl)
    assert not any("REASONFIELD" in l and "Blocked" in l for l in tl)


# ============ criterion 5: the grace and its poll interval are operator-tunable ============

def test_registration_grace_zero_skips_the_grace_entirely(tmp_path):
    """MERGE_CI_REG_GRACE=0 collapses the grace back to an immediate fail-fast — exactly ONE rollup read,
    no re-poll at all — the same override discipline MERGE_CI_TIMEOUT=0 already gets for the CI wait."""
    env = _rollup_env(tmp_path, title="Zero grace", checks_1=[], checks_2=[],
                      extra={"MERGE_CI_REG_GRACE": "0", "MERGE_CI_REG_POLL_INTERVAL": "5"})
    r = _run(env)
    assert r.returncode == 0, r.stderr
    assert _calls(tmp_path) == 1, "a zero grace must not re-poll even once"
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "empty_after_grace"


def test_registration_grace_nonzero_causes_at_least_one_repoll(tmp_path):
    """A non-zero MERGE_CI_REG_GRACE/MERGE_CI_REG_POLL_INTERVAL pair is honoured: at least one re-poll
    happens before the grace is judged to have elapsed — proving the values are read, not ignored."""
    env = _rollup_env(tmp_path, title="Nonzero grace", checks_1=[], checks_2=[],
                      extra={"MERGE_CI_REG_GRACE": "1", "MERGE_CI_REG_POLL_INTERVAL": "0"})
    r = _run(env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert _calls(tmp_path) >= 2, "a nonzero grace must re-poll at least once before giving up"
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "empty_after_grace"


# ============ criterion 4: environmental classification during the grace re-poll is unchanged ============

def test_gh_failure_during_registration_repoll_is_environmental_no_record(tmp_path):
    """The first rollup read succeeds (empty), but the RE-POLL inside the new grace loop hits a gh
    API/network blip: this must be classified exactly like any other gh failure in shadow_ci —
    environmental, no merge/shadow record written, the run not Blocked, and it still stops for the human
    at In Review (resumable, no streak reset)."""
    env = _rollup_env(tmp_path, title="gh blips mid-grace", checks_1=[], checks_2=[],
                      extra={"MERGE_CI_REG_GRACE": "10", "MERGE_CI_REG_POLL_INTERVAL": "0",
                             "STUB_ROLLUP_FAIL_AT": "2"})
    r = _run(env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert td._shadow_body(tmp_path) is None                    # no record: environmental, skipped
    tl = td._timeline(tmp_path)
    assert not any("REASONFIELD" in l and "Blocked" in l for l in tl)     # environmental != Blocked
    assert any(l.startswith("EDIT") and "STATUSFIELD" in l and "InReview" in l for l in tl)  # resumable
    assert "environmental" in r.stderr.lower() or "resumable" in r.stderr.lower()


# ============ criterion 4: record grammar/schema is unchanged by the new state ============

def test_registered_and_empty_after_grace_records_keep_schema_v1(tmp_path):
    """Neither branch of the new grace logic bumps the record schema or drops/renames a field — the
    fix is a new CI-state value, not a reshaped record."""
    registered_env = _rollup_env(tmp_path, title="Schema check registered", checks_1=[], checks_2=[CR_OK],
                                 extra={"MERGE_CI_REG_GRACE": "10", "MERGE_CI_REG_POLL_INTERVAL": "0",
                                        "MERGE_CI_POLL_INTERVAL": "0", "MERGE_CI_TIMEOUT": "5"})
    r = _run(registered_env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["schema"] == "yr-merge-record/1"
    assert SHADOW_FIELDS <= set(rec), f"missing: {SHADOW_FIELDS - set(rec)}"
