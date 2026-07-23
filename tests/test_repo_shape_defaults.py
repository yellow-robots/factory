"""Characterization tests for issue #272 — pin today's undeclared-shape defaults BEFORE any seam
change lands (pin-then-change; technical-rfc yellow-robots/factory#271 epic, slice 1).

Three surfaces, each observed at behavior only — block records, persisted diffs, record fields,
resolved commands, exit codes — never prompt-transport bytes (the behavior-anchoring anti-pattern,
qa/lens.py species 1):

  (a) the tester boundary guard's default judgment (tools/dev-runner.sh:1179-1185) — offenders are
      tester-stage paths outside tests/ after excluding __pycache__/ directories and *.pyc files,
      block-and-raise (no silent revert), with the violation diff persisted to the run dir. Covered
      here for BOTH a nested tools/__pycache__/ artifact and a ROOT-LEVEL __pycache__/ artifact —
      the root case guards a matcher-translation trap a later slice of this epic must not regress.
  (b) the merge evaluator's CI condition on an empty check rollup (tools/dev-runner.sh:177-193,
      tools/merge_shadow.py:164,371) — the registration grace, then failure recorded as
      empty_after_grace in the durable record's check_rollup field.
  (c) gate-command resolution precedence (tools/dev-runner.sh:569-571) — env CHECK_CMD over
      manifest check_cmd over the built-in pytest fallback, today's behavior verbatim (a later
      slice of this epic deliberately updates the fallback pin, by name, in its own PR — see
      test_gate_resolution_falls_back_to_builtin_pytest_default below).

Tests-only, accretive: no production code changes. Reuses the shared harness only (tests/harness/
CLAUDE_STUB, GH_STUB, consumed via test_dev_runner.py's fixtures, and test_ci_registration_grace.py's
rollup-sequencing helper) — no new private stub clone. The one derived variant here (ROOT_ARTIFACT_
CLAUDE_STUB, for the root-level __pycache__ case) is spliced into the shared CLAUDE_STUB by locating
its exact existing STUB_TESTER_ARTIFACT_CHANGE line, never by retyping the classifier.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td              # shared stub harness (gh/claude/check stubs + fixtures)
import test_ci_registration_grace as tcg  # the rollup-sequencing gh stub (call-counter driven)
import claude_fake                         # tests/harness/claude_fake.py — the classifier's one legal home

ROOT = td.ROOT


# ============ (a) tester boundary guard: default judgment, block-and-raise, diff persisted ============

def test_boundary_guard_blocks_and_raises_with_diff_persisted(tmp_path):
    """A tester-stage path outside tests/ is an offender: the run ends Blocked (no silent revert), the
    offending filename is named in the block comment, no PR is opened, and the violation diff is
    persisted under the run dir for diagnosis."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Pin: boundary guard offender"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_PROD_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    edits = " ".join(td._edits(tl))
    assert "REASONFIELD" in edits and "Blocked" in edits            # block-and-raise, never a silent revert
    comments = " ".join(td._comments(tl))
    assert "tester_prod.txt" in comments                            # offender named
    assert "https://stub/pr/1" not in r.stdout                       # no PR opened
    diffs = list((tmp_path / "drhome" / "runs").glob("5-*/boundary-violation.diff"))
    assert diffs and "tester_prod.txt" in diffs[0].read_text()       # violation diff persisted in the run dir


def test_boundary_guard_offenders_are_exactly_paths_outside_tests(tmp_path):
    """A tester-stage path under tests/ is never an offender: the guard's default judgment excludes
    tests/ entirely, and the run proceeds past check/review to a PR."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Pin: tests/ is never an offender"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    assert "TEST" in tl and "CHECK" in tl and "REVIEW" in tl
    assert "https://stub/pr/1" in r.stdout


def test_boundary_guard_excludes_nested_pycache_artifact(tmp_path):
    """A nested build artifact (tools/__pycache__/*.pyc) is excluded from the offender set — it is
    compiled FROM source the tester cannot change, not an implementation change."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Pin: nested pycache excluded"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1", "STUB_TESTER_ARTIFACT_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    assert "TEST" in tl and "CHECK" in tl and "REVIEW" in tl
    assert "https://stub/pr/1" in r.stdout


# A CLAUDE_STUB variant that also writes a build artifact at the REPO ROOT's __pycache__/ (not nested
# under tools/), gated by its own env var — derived from the shared classifier by locating its exact
# existing STUB_TESTER_ARTIFACT_CHANGE line, never by retyping the classification patterns.
_ARTIFACT_ANCHOR = ('[ -n "${STUB_TESTER_ARTIFACT_CHANGE:-}" ] && { mkdir -p tools/__pycache__ && '
                    'printf \'bytecode\\n\' > tools/__pycache__/check.cpython-314.pyc; }')
_ROOT_ARTIFACT_ADDITION = _ARTIFACT_ANCHOR + '''
                        [ -n "${STUB_TESTER_ROOT_ARTIFACT_CHANGE:-}" ] && { mkdir -p __pycache__ && printf 'bytecode\\n' > __pycache__/check.cpython-314.pyc; }'''
assert _ARTIFACT_ANCHOR in claude_fake.CLAUDE_STUB, "STUB_TESTER_ARTIFACT_CHANGE line moved/changed shape"
ROOT_ARTIFACT_CLAUDE_STUB = claude_fake.CLAUDE_STUB.replace(_ARTIFACT_ANCHOR, _ROOT_ARTIFACT_ADDITION, 1)


def _stubs_root_artifact(binp):
    binp.mkdir(parents=True, exist_ok=True)
    td._exec(binp / "gh", td.GH_STUB)
    td._exec(binp / "claude", ROOT_ARTIFACT_CLAUDE_STUB)
    td._exec(binp / "check.sh", td.CHECK_STUB)


def test_boundary_guard_excludes_root_level_pycache_artifact(tmp_path):
    """A build artifact at the REPO ROOT (__pycache__/*.pyc, with no nesting under tools/) must be
    excluded exactly like a nested one — pins the root-anchored arm of the exclusion match
    ('(^|/)__pycache__/'), the case a later slice's matcher-translation change must not regress."""
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"; _stubs_root_artifact(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Pin: root pycache excluded"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1",
                "STUB_TESTER_ROOT_ARTIFACT_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    assert "TEST" in tl and "CHECK" in tl and "REVIEW" in tl
    assert "https://stub/pr/1" in r.stdout


# ============ (b) merge evaluator: empty-rollup CI condition -> empty_after_grace ============

def test_empty_rollup_grace_then_fails_fast_as_empty_after_grace(tmp_path):
    """A check rollup that stays empty through the registration grace fails fast, and the durable
    record's check_rollup reads the distinguishing 'empty_after_grace' state — not a bare 'empty' or
    any ordinary CI outcome (success/failure/timed_out)."""
    env = tcg._rollup_env(tmp_path, title="Pin: never registers", checks_1=[], checks_2=[],
                           extra={"MERGE_CI_REG_GRACE": "0", "MERGE_CI_REG_POLL_INTERVAL": "0"})
    r = tcg._run(env)
    assert r.returncode == 0, r.stderr
    body = td._shadow_body(tmp_path)
    assert body is not None
    assert body.splitlines()[0] == td._would_block("ci_green")
    rec = td._shadow_block(body)
    assert rec["decision"] == "WOULD-BLOCK" and rec["failed_condition"] == "ci_green"
    assert rec["check_rollup"] == "empty_after_grace"


def test_rollup_registering_within_grace_is_not_empty_after_grace(tmp_path):
    """Contrast pin: a check that registers WITHIN the grace falls through to the ordinary CI-green
    evaluation, and the record reflects that real outcome ('success') — the grace is a bounded
    re-poll window, not an unconditional failure."""
    env = tcg._rollup_env(tmp_path, title="Pin: registers within grace", checks_1=[], checks_2=[tcg.CR_OK],
                           extra={"MERGE_CI_REG_GRACE": "10", "MERGE_CI_REG_POLL_INTERVAL": "0",
                                  "MERGE_CI_POLL_INTERVAL": "0", "MERGE_CI_TIMEOUT": "5"})
    r = tcg._run(env)
    assert r.returncode == 0, r.stderr
    rec = td._shadow_block(td._shadow_body(tmp_path))
    assert rec["check_rollup"] == "success"


# ============ (c) gate-command resolution precedence: env > manifest > pytest fallback ============

def test_gate_resolution_env_overrides_manifest(tmp_path):
    """Explicit CHECK_CMD in the env wins over a repo's manifest check_cmd."""
    repo = td._manifest_repo(tmp_path, check_cmd="make test")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); env["CHECK_CMD"] = "pytest -q"
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout)["check_cmd"] == "pytest -q"


def test_gate_resolution_manifest_overrides_builtin_default(tmp_path):
    """A repo's manifest check_cmd is used when CHECK_CMD is not set in the env — manifest wins over
    the built-in fallback."""
    repo = td._manifest_repo(tmp_path, check_cmd="make test")
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); del env["CHECK_CMD"]
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout)["check_cmd"] == "make test"


def test_gate_resolution_falls_back_to_builtin_pytest_default(tmp_path):
    """PIN, BY NAME: with neither an env CHECK_CMD nor a manifest check_cmd, the runner falls back to
    its built-in default, `$BASE_REPO/.venv/bin/python -m pytest tests/ -q` — today's fallback,
    verbatim. A later slice of this epic deliberately updates this exact pin, by this exact test
    name, in its own PR; until then this is the byte-for-byte fallback command."""
    repo = td._manifest_repo(tmp_path)   # no check_cmd key at all
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp); env["BASE_REPO"] = str(repo); del env["CHECK_CMD"]
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout)["check_cmd"] == f"{repo}/.venv/bin/python -m pytest tests/ -q"
