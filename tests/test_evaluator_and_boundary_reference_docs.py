"""
Tests for issue #111 — skill 0.9.1: the evaluator and boundary models reach consumers.

Derived from the issue #111 acceptance criteria (the spec), not from the reference files'
own prose. The goal the criteria state: a plugin consumer with no factory-code access must be
able to diagnose a `WOULD-BLOCK — ci_green` record or a tester boundary block by reading
skills/factory/references/pipeline.md and onboarding.md alone — the legibility invariant
(docs teach the model; recovery is derived, never catalogued).

Runs under `.venv/bin/python -m pytest tests/ -q` (or `pytest tests/ -q` on PATH).
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
PIPELINE = REFS / "pipeline.md"
ONBOARDING = REFS / "onboarding.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"

TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".sh", ".txt", ".yml", ".yaml"}
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv"}

CHECK_ROLLUP_VOCABULARY = ["success", "failure", "timed_out", "empty", "empty_after_grace"]


def _pipeline_text():
    return PIPELINE.read_text(encoding="utf-8")


def _onboarding_text():
    return ONBOARDING.read_text(encoding="utf-8")


def _plugin_data():
    return json.loads(PLUGIN.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The ci_green model — pipeline.md
# ---------------------------------------------------------------------------

def test_pipeline_md_has_ci_green_section():
    """The ci_green model is its own citable section (onboarding.md links to it by anchor)."""
    text = _pipeline_text()
    assert re.search(r"^#+.*ci_green", text, re.IGNORECASE | re.MULTILINE), \
        "pipeline.md has no heading naming the ci_green model section"


def test_pipeline_md_states_every_configured_check_must_conclude_successfully():
    lower = _pipeline_text().lower()
    assert "every configured check" in lower, \
        "pipeline.md does not state that every configured check on the PR head must conclude successfully"
    assert "conclude successfully" in lower or "concluded successfully" in lower, \
        "pipeline.md does not state the checks must conclude successfully"


def test_pipeline_md_states_registration_grace_before_fast_fail():
    """An empty rollup gets a bounded registration grace before the evaluator fast-fails."""
    lower = _pipeline_text().lower()
    assert "registration grace" in lower, \
        "pipeline.md does not name the registration grace for an empty check rollup"
    assert "bounded" in lower, \
        "pipeline.md does not state the registration grace is bounded"


def test_pipeline_md_states_still_empty_after_grace_fails():
    text = _pipeline_text()
    lower = text.lower()
    assert "empty_after_grace" in text, \
        "pipeline.md does not name the empty_after_grace terminal state"
    assert "grace expire" in lower or "grace expires" in lower or "expiry" in lower, \
        "pipeline.md does not state what happens once the registration grace expires"


def test_pipeline_md_has_complete_check_rollup_vocabulary_with_meanings():
    """AC: the complete check_rollup record vocabulary, each entry with its meaning."""
    text = _pipeline_text()
    for value in CHECK_ROLLUP_VOCABULARY:
        pattern = re.compile(rf"`{re.escape(value)}`\s*\|\s*(.+?)\s*\|")
        match = pattern.search(text)
        assert match, f"pipeline.md does not document check_rollup value `{value}` in a table row"
        meaning = match.group(1).strip()
        assert len(meaning) > 10, \
            f"pipeline.md names check_rollup value `{value}` but gives no meaning for it"


def test_pipeline_md_check_rollup_meanings_are_specific():
    """Spot-check that each vocabulary entry's meaning is substantively about that state,
    not a copy-pasted placeholder — a consumer must be able to tell the five apart."""
    text = _pipeline_text()

    def _meaning(value):
        m = re.search(rf"`{re.escape(value)}`\s*\|\s*(.+?)\s*\|", text)
        assert m, f"pipeline.md missing a table row for check_rollup value `{value}`"
        return m.group(1).lower()

    assert "success" in _meaning("success") or "no failures" in _meaning("success") or \
        "successfully" in _meaning("success"), \
        "pipeline.md's `success` row does not describe every check succeeding"
    assert "fail" in _meaning("failure"), \
        "pipeline.md's `failure` row does not describe a failed check"
    assert "in-flight" in _meaning("timed_out") or "timeout" in _meaning("timed_out") or \
        "wait" in _meaning("timed_out"), \
        "pipeline.md's `timed_out` row does not describe the bounded-wait expiry"
    assert "transient" in _meaning("empty") or "never" in _meaning("empty"), \
        "pipeline.md's `empty` row does not state it is a transient read, never itself a persisted value"
    assert "grace" in _meaning("empty_after_grace"), \
        "pipeline.md's `empty_after_grace` row does not tie the state to the registration grace"


def test_pipeline_md_states_no_server_ci_cannot_pass_ci_green():
    lower = _pipeline_text().lower()
    assert "cannot pass" in lower and "ci_green" in lower, \
        "pipeline.md does not state that a repo with no server CI configured cannot pass ci_green"
    assert "no server ci" in lower, \
        "pipeline.md does not name the no-server-CI case"


def test_pipeline_md_states_every_pr_records_would_block_empty_after_grace():
    text = _pipeline_text()
    assert "WOULD-BLOCK" in text and "ci_green" in text, \
        "pipeline.md does not connect a no-CI repo to a WOULD-BLOCK — ci_green record"
    assert "empty_after_grace" in text, \
        "pipeline.md does not state the no-CI record carries check_rollup: empty_after_grace"


def test_pipeline_md_states_record_reads_absence_not_failure():
    """AC: 'the record reads the repo's CI absence, not a CI failure.'"""
    lower = _pipeline_text().lower()
    assert "fact" in lower, \
        "pipeline.md does not frame the no-CI record as stating a fact about the repo"
    assert "not a ci run that failed" in lower or "not that a check failed" in lower or \
        "not debugging a broken check" in lower or \
        ("not" in lower and "failed" in lower and "check" in lower), \
        "pipeline.md does not distinguish the no-CI record from a CI run/check failure"


# ---------------------------------------------------------------------------
# The legal test tree — pipeline.md
# ---------------------------------------------------------------------------

def test_pipeline_md_has_legal_test_tree_section():
    text = _pipeline_text()
    assert re.search(r"^#+.*legal test tree", text, re.IGNORECASE | re.MULTILINE), \
        "pipeline.md has no heading naming the legal test tree section"


def test_pipeline_md_defines_legal_test_tree_as_root_tests():
    text = _pipeline_text()
    lower = text.lower()
    assert "tests/" in text, "pipeline.md does not name the tests/ tree"
    assert "repo-root" in lower or "repo root" in lower, \
        "pipeline.md does not scope the legal test tree to the repo root (vs. e.g. app/tests/)"


def test_pipeline_md_states_build_artifact_exclusions():
    text = _pipeline_text()
    assert "__pycache__" in text, \
        "pipeline.md does not name the __pycache__ build-artifact exclusion"
    assert "*.pyc" in text or ".pyc" in text, \
        "pipeline.md does not name the *.pyc build-artifact exclusion"


def test_pipeline_md_states_tester_changes_outside_tree_are_blocked_as_boundary_violation():
    lower = _pipeline_text().lower()
    assert "boundary violation" in lower, \
        "pipeline.md does not name a change outside the legal test tree a boundary violation"
    assert "blocked" in lower, \
        "pipeline.md does not state a boundary violation is Blocked"


def test_pipeline_md_test_tree_example_names_a_non_root_tests_dir():
    """A consumer diagnosing gilda#2's block needs to see why app/src/ or app/tests/ (not the
    repo-root tests/ tree) still counts as outside the legal tree."""
    lower = _pipeline_text().lower()
    assert "app/src" in lower or "app/tests" in lower or \
        ("not" in lower and "root" in lower and "tests/" in lower), \
        "pipeline.md does not illustrate a legitimate-looking test file outside the repo-root tests/ tree"


# ---------------------------------------------------------------------------
# onboarding.md — current assumptions
# ---------------------------------------------------------------------------

def test_onboarding_md_has_current_assumptions_section():
    text = _onboarding_text()
    assert re.search(r"^#+.*assumption", text, re.IGNORECASE | re.MULTILINE), \
        "onboarding.md has no heading naming the factory's current assumptions about a repo"


def test_onboarding_md_assumptions_include_server_ci():
    lower = _onboarding_text().lower()
    assert "server ci" in lower, \
        "onboarding.md's current-assumptions statement does not name server CI"


def test_onboarding_md_assumptions_include_root_tests_tree():
    lower = _onboarding_text().lower()
    assert ("root" in lower and "tests/" in lower), \
        "onboarding.md's current-assumptions statement does not name the root tests/ tree"


def test_onboarding_md_assumptions_include_existing_built_deps_and_check_cmd():
    """AC: the new assumptions sit alongside the existing built-deps and check-command requirements."""
    text = _onboarding_text()
    lower = text.lower()
    assert "built deps" in lower or "built-deps" in lower, \
        "onboarding.md's current-assumptions statement dropped the existing built-deps requirement"
    assert "check_cmd" in text, \
        "onboarding.md's current-assumptions statement dropped the existing check_cmd requirement"


def test_onboarding_md_assumptions_framed_as_future_manifest_declarations():
    lower = _onboarding_text().lower()
    assert "manifest" in lower, \
        "onboarding.md does not frame the current assumptions as future manifest declarations"
    assert "seam-completion" in lower or "seam completion" in lower, \
        "onboarding.md does not cite the queued seam-completion design that will formalize these assumptions"


def test_onboarding_md_assumptions_cite_pipeline_md():
    text = _onboarding_text()
    assert "pipeline.md" in text, \
        "onboarding.md's current-assumptions statement does not cite pipeline.md"


# ---------------------------------------------------------------------------
# onboarding.md — step 5 verification list, extended through the merge verdict
# ---------------------------------------------------------------------------

def test_onboarding_md_step5_expects_would_merge():
    text = _onboarding_text()
    assert "WOULD-MERGE" in text, \
        "onboarding.md's smoke-test verification does not expect a WOULD-MERGE record"


def test_onboarding_md_step5_expects_would_block_ci_green_without_server_ci():
    text = _onboarding_text()
    assert "WOULD-BLOCK" in text and "ci_green" in text, \
        "onboarding.md's smoke-test verification does not expect WOULD-BLOCK — ci_green on a repo without server CI"


def test_onboarding_md_step5_states_what_fact_the_block_record_states():
    lower = _onboarding_text().lower()
    assert "fact" in lower or "not that a check failed" in lower or "not a check that failed" in lower, \
        "onboarding.md's step 5 does not say which fact the WOULD-BLOCK — ci_green record states"
    assert "no server ci" in lower or "no ci" in lower, \
        "onboarding.md's step 5 does not name the missing-server-CI fact the record states"


def test_onboarding_md_merge_verdict_step_cites_pipeline_ci_green_model():
    text = _onboarding_text()
    assert "pipeline.md" in text and "ci_green" in text, \
        "onboarding.md's merge-evaluator verification step does not cite pipeline.md's ci_green model"


# ---------------------------------------------------------------------------
# No 0.9.0 pin remains anywhere
# ---------------------------------------------------------------------------

THIS_FILE = pathlib.Path(__file__).resolve()


def _tracked_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == THIS_FILE:
            continue  # this file's own docstrings/messages discuss the old pin as text, not a pin
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        yield path


def test_no_0_9_0_version_pin_remains_anywhere_in_the_tree():
    """AC: 'confirm by grep that no 0.9.0 version pin remains anywhere in the tree.'"""
    offenders = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "0.9.0" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, \
        f"'0.9.0' still present in: {offenders} — should read '0.9.1' after the skill 0.9.1 release"
