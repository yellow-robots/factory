"""Acceptance tests for issue #244 — the seven private claude stubs become shared-fake modes.

Derived from the CRITERIA (the spec: exactly one shared claude fake, every suite faking claude obtains
it from tests/harness/claude_fake.py, no private clone of the classifier remains anywhere; a recorder or
thin wrapper derived from the shared fake is lawful extension, a re-implementation beside it is a clone),
NOT from the implementation's internals.

The seven privates named in the issue's corrected census (four files):
  tests/test_dev_runner.py            — CLAUDE_STUB_JSON, REAP_CLAUDE_STUB, SIGNAL_CLAUDE_STUB,
                                         LINT_CLAUDE_STUB
  tests/test_dev_runner_roles.py       — REC_CLAUDE_STUB (a recorder: lawful wrapper)
  tests/test_dev_runner_post_repair_diff.py — a private CLAUDE_STUB_REPAIR
  tests/test_dev_runner_review_bundle.py    — SNAPSHOT_CLAUDE_STUB (a recorder: lawful wrapper)

Covered here:
  * the clone census, generalized across the WHOLE tests/ tree (not just the two files slice 1 —
    issue #243 — checked): no full classifier re-implementation survives anywhere;
  * each of the seven named privates is gone by name from its file;
  * CLAUDE_STUB_JSON now lives in tests/harness/claude_fake.py, the classifier's one legal home;
  * the two still-legitimate derived stubs (REC_CLAUDE_STUB, SNAPSHOT_CLAUDE_STUB) are extensions
    (built via `.replace()` on the shared classifier), never fresh literals;
  * the behavior the removed privates used to provide is now a MODE of the shared fake itself
    (a signal-crash mode, a cross-arm process-reap hook, a lint-repair arm) — proven by running the
    shared fake directly, independent of tools/dev-runner.sh;
  * the byte-exact stdin transport pin (the named transport-anchor exhibit: qa/lens.py species 2 /
    the 2026-07-10 #121-rebuild) still holds on the shared fake after the migration;
  * the consuming suites' scenarios (recording, review-bundle snapshot, post-repair diff) still run
    end-to-end through the shared fake's modes.

Runs under `.venv/bin/python -m pytest tests/ -q` (system python3 works too — no third-party deps).
"""
import ast
import os
import pathlib
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
HARNESS = TESTS / "harness"

sys.path.insert(0, str(HARNESS))
import claude_fake  # noqa: E402

sys.path.insert(0, str(TESTS))
import test_dev_runner as td  # noqa: E402

# the four routing literals every full classifier re-implementation would need to carry to actually
# misroute a stage if it drifted from the shared fake (see tests/harness/contract.md's table).
ROUTING_LITERALS = ("*REVIEWER*", '*"REQUESTED CHANGES"*', "*TESTER*", '*"tests FAIL"*')

CENSUS_FILES = {
    "test_dev_runner.py": TESTS / "test_dev_runner.py",
    "test_dev_runner_roles.py": TESTS / "test_dev_runner_roles.py",
    "test_dev_runner_post_repair_diff.py": TESTS / "test_dev_runner_post_repair_diff.py",
    "test_dev_runner_review_bundle.py": TESTS / "test_dev_runner_review_bundle.py",
}


def _plain_string_assignments(path):
    """Every plain (non-derived) string literal assigned to a module-level name in `path` — i.e. NOT
    the result of a method call like `CLAUDE_STUB.replace(...)`, which derives from an existing value
    rather than retyping one. Returns {name: text}."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _is_full_classifier_reimplementation(text):
    return 'case "$args" in' in text and all(lit in text for lit in ROUTING_LITERALS)


def _all_test_py_files():
    """Every .py file under tests/, excluding the shared fake's own module (its one legal home)."""
    return [p for p in TESTS.rglob("*.py") if p.resolve() != (HARNESS / "claude_fake.py").resolve()]


# --------------------------------------------------------------------------------------------------
# THE SYSTEM SHALL provide exactly one shared claude fake — no private clone of the classifier
# survives anywhere in the tests/ tree (generalized beyond the two files issue #243 targeted).
# --------------------------------------------------------------------------------------------------

def test_no_full_claude_classifier_reimplementation_anywhere_in_tests():
    offenders = []
    for f in _all_test_py_files():
        for name, text in _plain_string_assignments(f).items():
            if _is_full_classifier_reimplementation(text):
                offenders.append(f"{f.relative_to(ROOT)}::{name}")
    assert not offenders, f"private classifier re-implementation(s) found: {offenders}"


# --------------------------------------------------------------------------------------------------
# Each of the seven named privates is gone BY NAME from its file.
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("stub_name", ["REAP_CLAUDE_STUB", "SIGNAL_CLAUDE_STUB", "LINT_CLAUDE_STUB"])
def test_private_stub_removed_from_test_dev_runner(stub_name):
    src = CENSUS_FILES["test_dev_runner.py"].read_text()
    assert stub_name not in src, f"{stub_name} must be gone from tests/test_dev_runner.py — migrated to " \
        "a mode of tests/harness/claude_fake.CLAUDE_STUB"


def test_claude_stub_json_no_longer_a_fresh_literal_in_test_dev_runner():
    assignments = _plain_string_assignments(CENSUS_FILES["test_dev_runner.py"])
    assert "CLAUDE_STUB_JSON" not in assignments, (
        "tests/test_dev_runner.py must import CLAUDE_STUB_JSON from tests/harness/claude_fake, not "
        "define it as its own literal"
    )


def test_private_claude_stub_repair_removed_from_post_repair_diff():
    src = CENSUS_FILES["test_dev_runner_post_repair_diff.py"].read_text()
    assert "CLAUDE_STUB_REPAIR" not in src, (
        "the private CLAUDE_STUB_REPAIR must be gone from tests/test_dev_runner_post_repair_diff.py — "
        "the file must drive the review-repair round via the shared fake's own STUB_REVIEWFIX_EDIT knob"
    )


# --------------------------------------------------------------------------------------------------
# The classifier's one legal home now carries CLAUDE_STUB_JSON too.
# --------------------------------------------------------------------------------------------------

def test_claude_stub_json_lives_in_the_shared_home():
    assert hasattr(claude_fake, "CLAUDE_STUB_JSON"), \
        "tests/harness/claude_fake.py must carry CLAUDE_STUB_JSON, the classifier's json-envelope twin"
    assert 'case "$args" in' in claude_fake.CLAUDE_STUB_JSON
    assert all(lit in claude_fake.CLAUDE_STUB_JSON for lit in ROUTING_LITERALS)


def test_test_dev_runner_claude_stub_json_is_the_shared_object_not_a_copy():
    assert td.CLAUDE_STUB_JSON is claude_fake.CLAUDE_STUB_JSON, \
        "tests/test_dev_runner.py's CLAUDE_STUB_JSON must be the SAME object as the shared home's, not " \
        "a copied string"


# --------------------------------------------------------------------------------------------------
# A recorder/thin wrapper obtained from the shared home is lawful extension, never a re-implementation.
# --------------------------------------------------------------------------------------------------

def test_roles_rec_claude_stub_is_derived_not_a_fresh_literal():
    """REC_CLAUDE_STUB (the model-recording wrapper) must not appear as a plain string constant — it is
    only lawful if built by deriving from claude_fake.CLAUDE_STUB (e.g. via .replace()), which parses as
    a Call expression, never a Constant."""
    assignments = _plain_string_assignments(CENSUS_FILES["test_dev_runner_roles.py"])
    assert "REC_CLAUDE_STUB" not in assignments, (
        "REC_CLAUDE_STUB must be derived from tests/harness/claude_fake.CLAUDE_STUB, not a fresh literal"
    )


def test_review_bundle_snapshot_claude_stub_is_derived_not_a_fresh_literal():
    assignments = _plain_string_assignments(CENSUS_FILES["test_dev_runner_review_bundle.py"])
    assert "SNAPSHOT_CLAUDE_STUB" not in assignments, (
        "SNAPSHOT_CLAUDE_STUB must be derived from tests/harness/claude_fake.CLAUDE_STUB, not a fresh literal"
    )


def _import_sibling(modname):
    """Import one of the test_dev_runner_*.py files as a module (same pattern those files use to
    import each other/test_dev_runner) so this independent test can inspect the actual derived stub
    object they build, not a re-typed copy of it."""
    if modname in sys.modules:
        return sys.modules[modname]
    return __import__(modname)


def test_roles_rec_claude_stub_still_carries_the_shared_classifier_verbatim():
    """The recorder must be an EXTENSION: the shared classifier's case block survives inside it
    untouched (located, not retyped) — proven by checking the exact reviewer-arm text from
    tests/harness/claude_fake.CLAUDE_STUB still appears verbatim inside the derived stub."""
    roles_mod = _import_sibling("test_dev_runner_roles")
    reviewer_arm_anchor = '*REVIEWER*)            echo REVIEW >> "$STUB_TIMELINE"'
    assert reviewer_arm_anchor in claude_fake.CLAUDE_STUB, "sanity: anchor text must exist in the shared fake"
    assert reviewer_arm_anchor in roles_mod.REC_CLAUDE_STUB, (
        "REC_CLAUDE_STUB must still carry the shared classifier's reviewer arm verbatim (an extension "
        "splices in, it doesn't retype)"
    )
    assert roles_mod.REC_CLAUDE_STUB != claude_fake.CLAUDE_STUB, \
        "REC_CLAUDE_STUB must actually add its recording behaviour, not be a no-op copy"


def test_review_bundle_snapshot_stub_still_carries_the_shared_classifier_verbatim():
    bundle_mod = _import_sibling("test_dev_runner_review_bundle")
    tester_arm_anchor = '*TESTER*)             echo TEST   >> "$STUB_TIMELINE"'
    assert tester_arm_anchor in claude_fake.CLAUDE_STUB, "sanity: anchor text must exist in the shared fake"
    assert tester_arm_anchor in bundle_mod.SNAPSHOT_CLAUDE_STUB, (
        "SNAPSHOT_CLAUDE_STUB must still carry the shared classifier's tester arm verbatim (an extension "
        "splices in, it doesn't retype)"
    )
    assert bundle_mod.SNAPSHOT_CLAUDE_STUB != claude_fake.CLAUDE_STUB, \
        "SNAPSHOT_CLAUDE_STUB must actually add its snapshot behaviour, not be a no-op copy"


# --------------------------------------------------------------------------------------------------
# The behavior the removed privates used to provide is now a MODE of the shared fake itself — proven
# by running tests/harness/claude_fake.CLAUDE_STUB directly, independent of tools/dev-runner.sh.
# --------------------------------------------------------------------------------------------------

def _write_stub(tmp_path):
    script = tmp_path / "claude"
    script.write_text(claude_fake.CLAUDE_STUB)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _run_stub(tmp_path, script, argv, stdin_text="", extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run([str(script), *argv], input=stdin_text, capture_output=True, text=True,
                          cwd=tmp_path, env=env)


def test_signal_crash_mode_kills_before_any_hook_writes(tmp_path):
    """Acceptance: SIGNAL_CLAUDE_STUB (the three-line crash simulator) is gone; STUB_CLAUDE_SIGKILL is
    now a mode of the shared fake — it must kill the process by signal, before any timeline/argv/stdin
    hook fires, so the caller observes exactly the zero-byte-log class of failure the crash mode
    simulates."""
    script = _write_stub(tmp_path)
    timeline = tmp_path / "timeline"
    r = _run_stub(tmp_path, script, ["you are the IMPLEMENTER"], "do the thing",
                  extra_env={"STUB_CLAUDE_SIGKILL": "1", "STUB_TIMELINE": str(timeline)})
    assert r.returncode != 0
    assert r.returncode < 0 or r.returncode > 128, \
        f"expected signal termination, got returncode {r.returncode}"
    assert not timeline.exists() or timeline.read_text() == "", \
        "the crash mode must fire before the timeline hook writes anything"


def test_signal_crash_mode_is_a_noop_when_the_flag_is_unset(tmp_path):
    script = _write_stub(tmp_path)
    timeline = tmp_path / "timeline"
    r = _run_stub(tmp_path, script, ["you are the IMPLEMENTER"], "",
                  extra_env={"STUB_TIMELINE": str(timeline)})
    assert r.returncode == 0
    assert timeline.read_text().strip() == "IMPL"


def test_process_reap_hook_implement_arm_backgrounds_and_records_a_pid(tmp_path):
    """Acceptance: REAP_CLAUDE_STUB is gone; STUB_LINGER_PIDFILE is now a hook spanning the implement
    and tester arms of the ONE shared fake. The implement arm's half: background a sleep and record its
    pid, readable by the very next stage."""
    script = _write_stub(tmp_path)
    pidfile = tmp_path / "linger.pid"
    r = _run_stub(tmp_path, script, ["implement the feature"], "",
                  extra_env={"STUB_LINGER_PIDFILE": str(pidfile), "STUB_TIMELINE": str(tmp_path / "timeline")})
    assert r.returncode == 0
    assert pidfile.exists(), "the implement arm must record the backgrounded child's pid"
    assert int(pidfile.read_text().strip()) > 0, "the recorded pid must be a real, parseable process id"


def test_process_reap_hook_tester_arm_marks_lingering_when_the_pid_is_alive(tmp_path):
    """The tester arm's half, exercised directly (a live pid — this very test process — stands in for
    a stray background child that is STILL alive when the tester stage starts): the tester arm must
    mark the timeline LINGERING."""
    script = _write_stub(tmp_path)
    pidfile = tmp_path / "linger.pid"
    timeline = tmp_path / "timeline"
    pidfile.write_text(str(os.getpid()))  # this test process: guaranteed alive for the duration of the call
    r = _run_stub(tmp_path, script, ["you are the TESTER"], "",
                  extra_env={"STUB_LINGER_PIDFILE": str(pidfile), "STUB_TIMELINE": str(timeline)})
    assert r.returncode == 0
    assert "LINGERING" in timeline.read_text().splitlines()


def test_process_reap_hook_tester_arm_silent_when_the_pid_is_dead(tmp_path):
    """The other half of the same hook: a pid that no longer exists (already reaped by the time the
    tester arm starts — the state the runner's process-group reap is supposed to guarantee) must NOT
    be marked LINGERING — the hook observes reality, it doesn't always fire."""
    script = _write_stub(tmp_path)
    pidfile = tmp_path / "linger.pid"
    timeline = tmp_path / "timeline"
    dead = subprocess.Popen(["true"])
    dead.wait()  # reaped: this pid slot is now free
    pidfile.write_text(str(dead.pid))
    r = _run_stub(tmp_path, script, ["you are the TESTER"], "",
                  extra_env={"STUB_LINGER_PIDFILE": str(pidfile), "STUB_TIMELINE": str(timeline)})
    assert r.returncode == 0
    assert "LINGERING" not in timeline.read_text().splitlines()


@pytest.mark.parametrize("heal,expect_healed", [(None, False), ("1", True)])
def test_lint_repair_arm_is_a_mode_of_the_shared_fake(tmp_path, heal, expect_healed):
    """Acceptance: LINT_CLAUDE_STUB (previously derived beside the shared fake via .replace() in
    tests/test_dev_runner.py) is gone entirely — its `*"lint gate FAILS"*` arm is now baked directly
    into tests/harness/claude_fake.CLAUDE_STUB itself, gated by STUB_LINTREPAIR_HEAL exactly as the
    private stub used to be."""
    script = _write_stub(tmp_path)
    timeline = tmp_path / "timeline"
    env = {"STUB_TIMELINE": str(timeline)}
    if heal is not None:
        env["STUB_LINTREPAIR_HEAL"] = heal
    r = _run_stub(tmp_path, script, [], "the lint gate FAILS, please repair it", extra_env=env)
    assert r.returncode == 0
    assert timeline.read_text().strip() == "LINTREPAIR"
    assert (tmp_path / "lint_ok").exists() == expect_healed


def test_lint_repair_arm_is_distinct_from_check_repair_and_implement():
    """The lint-repair literal must route to its own arm, never collapsing into check-repair
    ('tests FAIL') or the implement default — contract.md documents this as a fifth routing literal."""
    assert '*"lint gate FAILS"*' in claude_fake.CLAUDE_STUB
    contract = (HARNESS / "contract.md").read_text()
    assert "lint gate FAILS" in contract


# --------------------------------------------------------------------------------------------------
# The named transport-anchor exhibit (qa/lens.py species 2 / the 2026-07-10 #121-rebuild) still holds
# on the shared fake after the migration: stdin is captured byte-exact, including a trailing newline.
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("stdin_text", [
    "implement the feature\n",
    "implement the feature\n\n",
    "implement the feature",
])
def test_shared_fake_captures_stdin_byte_exact_including_trailing_newlines(tmp_path, stdin_text):
    script = _write_stub(tmp_path)
    stdin_capture = tmp_path / "stdin_out"
    r = _run_stub(tmp_path, script, [], stdin_text,
                  extra_env={"STUB_CLAUDE_STDIN": str(stdin_capture),
                             "STUB_TIMELINE": str(tmp_path / "timeline")})
    assert r.returncode == 0
    assert stdin_capture.read_bytes() == stdin_text.encode(), \
        "the shared fake must preserve stdin byte-exact (including any trailing newline), the exact " \
        "class of fixture the 2026-07-10 #121-rebuild exhibit hinges on"


# --------------------------------------------------------------------------------------------------
# The consuming suites' scenarios still run end-to-end through the shared fake's modes (not just the
# lower-level unit checks above) — one representative end-to-end run per migrated suite.
# --------------------------------------------------------------------------------------------------

def test_roles_recording_scenario_runs_end_to_end_through_the_shared_fake(tmp_path):
    roles_mod = _import_sibling("test_dev_runner_roles")
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"
    roles_mod._rec_stubs(binp)
    env = td._real(tmp_path, roles_mod._env(tmp_path, binp, number=5, title="Migration smoke"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    env["STUB_STAGE_MODELS"] = str(tmp_path / "stage_models")
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    sm = roles_mod._stage_models(tmp_path)
    assert sm.get("IMPL") and sm.get("TEST") and sm.get("REVIEW"), \
        "the model-recording wrapper (derived from the shared fake) must still observe every stage"


def test_review_bundle_snapshot_scenario_runs_end_to_end_through_the_shared_fake(tmp_path):
    bundle_mod = _import_sibling("test_dev_runner_review_bundle")
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"
    bundle_mod._snapshot_stubs(binp)
    snapshot = tmp_path / "snapshot.json"
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Migration smoke"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEWER_SNAPSHOT": str(snapshot)})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert snapshot.is_file(), "the snapshot wrapper (derived from the shared fake) must still fire"


def test_post_repair_diff_scenario_runs_end_to_end_through_the_shared_fake(tmp_path):
    """No private stub remains for this suite at all: it now drives the review-repair round purely
    through td.CLAUDE_STUB's own STUB_REVIEWFIX_EDIT knob."""
    diff_mod = _import_sibling("test_dev_runner_post_repair_diff")
    env = diff_mod._setup(tmp_path, title="Migration smoke")
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_REVIEW_BLOCK": "1", "STUB_REVIEWFIX_EDIT": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    rd = td._run_dir(tmp_path)
    assert (rd / "final.patch").exists() and "repaired-by-review" in (rd / "final.patch").read_text()
