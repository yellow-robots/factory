"""Acceptance tests for issue #243 — the harness gains its one shared home.

Derived from the CRITERIA (the spec: tests/harness/ holds the contract doc and the single stage-aware
claude fake whose classifier is the only legal stage-recognition path, plus the literal-pinning guard
moving in this same slice), NOT from the implementation's internals.

Covered criteria:
  * the contract doc is the one authoritative surface for the flag families, the prompt transport, and
    how a stage is recognized;
  * stage classification flows only through the shared fake's classifier — no re-implementation of the
    case block remains in either consuming suite (tests/test_dev_runner.py, tests/test_shadow_review.py);
  * the literal-pinning guard moved alongside the classifier and still fails loudly when a runner prompt
    literal is dropped.
"""
import ast
import os
import pathlib
import re
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
HARNESS = TESTS / "harness"
RUNNER = ROOT / "tools" / "dev-runner.sh"

sys.path.insert(0, str(HARNESS))
import claude_fake  # noqa: E402
import test_claude_fake_contract as guard_mod  # noqa: E402

# the four routing literals `tools/dev-runner.sh` bakes into its per-stage prompts, in the order the
# shared classifier's case block matches them (see tests/harness/contract.md's table).
ROUTING_LITERALS = ("*REVIEWER*", '*"REQUESTED CHANGES"*', "*TESTER*", '*"tests FAIL"*')


# --------------------------------------------------------------------------------------------------
# The contract doc is one authoritative surface for the flag families, the prompt transport, and how
# a stage is recognized.
# --------------------------------------------------------------------------------------------------

def test_contract_doc_exists_under_the_shared_home():
    assert (HARNESS / "contract.md").is_file(), \
        "tests/harness/contract.md must exist as the one authoritative harness-contract surface"


def test_contract_documents_the_prompt_transport():
    contract = (HARNESS / "contract.md").read_text()
    assert "stdin" in contract.lower(), \
        "the contract must state that the task prompt travels on stdin, not argv"


def test_contract_documents_how_a_stage_is_recognized():
    contract = (HARNESS / "contract.md").read_text()
    for literal in ("REVIEWER", "REQUESTED CHANGES", "TESTER", "tests FAIL"):
        assert literal in contract, \
            f"the contract must document the {literal!r} stage-recognition literal"


def test_contract_documents_every_stub_flag_the_shared_fake_reads():
    """Every STUB_* environment variable the shared fake actually reads must be documented on the
    contract surface — the doc is the flag-family reference, so an undocumented flag defeats it."""
    flags = sorted(set(re.findall(r"STUB_[A-Z_]+", claude_fake.CLAUDE_STUB)))
    assert flags, "expected the shared fake to read at least one STUB_* flag"
    contract = (HARNESS / "contract.md").read_text()
    missing = [f for f in flags if f not in contract]
    assert not missing, f"tests/harness/contract.md fails to document: {missing}"


# --------------------------------------------------------------------------------------------------
# Stage classification flows only through the shared fake's classifier.
# --------------------------------------------------------------------------------------------------

def _plain_string_assignments(path):
    """Every plain (non-derived) string literal assigned to a module-level name in `path` — i.e. NOT
    the result of a method call like `CLAUDE_STUB.replace(...)`, which derives from an existing value
    rather than retyping one. Returns [(name, text), ...]."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.append((target.id, node.value.value))
    return out


def _is_full_classifier_reimplementation(text):
    return 'case "$args" in' in text and all(lit in text for lit in ROUTING_LITERALS)


def test_dev_runner_claude_stub_is_imported_not_reimplemented():
    """Acceptance: the primary stage-aware stub's case block in tests/test_dev_runner.py is gone — the
    module's own CLAUDE_STUB (the name every other stub in that file, and the whole suite, keys off)
    must come from the shared fake, not a fresh literal. This slice only targets the primary stub —
    the derived/private stubs (CLAUDE_STUB_JSON, REAP_CLAUDE_STUB, SIGNAL_CLAUDE_STUB, LINT_CLAUDE_STUB)
    are explicitly out of scope and migrate later, so only the exact name `CLAUDE_STUB` is checked."""
    assignments = dict(_plain_string_assignments(TESTS / "test_dev_runner.py"))
    assert "CLAUDE_STUB" not in assignments, (
        "tests/test_dev_runner.py must import CLAUDE_STUB from tests/harness/claude_fake, not define "
        "it as its own literal"
    )


def test_dev_runner_imports_the_shared_claude_fake():
    src = (TESTS / "test_dev_runner.py").read_text()
    assert "import claude_fake" in src, \
        "tests/test_dev_runner.py must import tests/harness/claude_fake, the classifier's one legal home"


def test_shadow_review_does_not_reimplement_the_base_classifier():
    """Acceptance: the two shadow re-implementations in tests/test_shadow_review.py (CLAUDE_STUB_SHADOW
    and its JSON twin) are gone — the shadow suite must derive its shadow-aware stub from the shared
    fake's classifier (e.g. by locating an arm to splice into, the way tests/test_dev_runner.py's
    LINT_CLAUDE_STUB derives via .replace() rather than retyping), never by hand-typing a fresh copy of
    the full case block."""
    assignments = dict(_plain_string_assignments(TESTS / "test_shadow_review.py"))
    reimplemented = [name for name, text in assignments.items() if _is_full_classifier_reimplementation(text)]
    assert not reimplemented, (
        f"tests/test_shadow_review.py hand-types its own full classifier case block in {reimplemented}; "
        "it must derive from tests/harness/claude_fake.CLAUDE_STUB instead"
    )


def test_shadow_review_consumes_the_shared_claude_fake():
    src = (TESTS / "test_shadow_review.py").read_text()
    assert "claude_fake" in src, (
        "tests/test_shadow_review.py must consume tests/harness/claude_fake (directly or via "
        "test_dev_runner's import of it), the classifier's one legal home, rather than defining its own"
    )


# --------------------------------------------------------------------------------------------------
# The shared fake's classifier actually recognizes each stage, matched against combined argv+stdin —
# proven by running it directly, independent of tools/dev-runner.sh.
# --------------------------------------------------------------------------------------------------

def _run_stub(tmp_path, argv, stdin_text):
    script = tmp_path / "claude"
    script.write_text(claude_fake.CLAUDE_STUB)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    timeline = tmp_path / "timeline"
    env = dict(os.environ)
    env["STUB_TIMELINE"] = str(timeline)
    r = subprocess.run([str(script), *argv], input=stdin_text, capture_output=True, text=True,
                        cwd=tmp_path, env=env)
    assert r.returncode == 0, r.stderr
    return timeline.read_text().split()


@pytest.mark.parametrize("argv,stdin_text,expected_token", [
    (["you are the REVIEWER"], "", "REVIEW"),
    ([], "the review noted REQUESTED CHANGES to make", "REVIEWFIX"),
    (["you are the TESTER"], "", "TEST"),
    ([], "the check gate says tests FAIL", "REPAIR"),
    (["implement the feature"], "", "IMPL"),
])
def test_classifier_routes_each_stage(tmp_path, argv, stdin_text, expected_token):
    assert _run_stub(tmp_path, argv, stdin_text) == [expected_token]


def test_classifier_matches_against_combined_argv_and_stdin_not_argv_alone(tmp_path):
    """issue #121: the task prompt travels on stdin, never argv — a literal that lives only in the
    prompt (e.g. "tests FAIL") must still route correctly, and must NOT be visible on argv alone."""
    assert _run_stub(tmp_path, [], "the check gate says tests FAIL") == ["REPAIR"]


def test_classifier_precedence_matches_the_documented_order(tmp_path):
    """contract.md's table documents REVIEWER matching before the other three literals — prove the
    first-match-wins order live when several literals appear in the same call."""
    combined = "REVIEWER TESTER tests FAIL REQUESTED CHANGES"
    assert _run_stub(tmp_path, [], combined) == ["REVIEW"]


# --------------------------------------------------------------------------------------------------
# The literal-pinning guard moved alongside the classifier, and still fails loudly when a runner
# prompt literal is dropped.
# --------------------------------------------------------------------------------------------------

def test_guard_lives_under_the_shared_home():
    assert (HARNESS / "test_claude_fake_contract.py").is_file(), \
        "the literal-pinning guard must live under tests/harness/, alongside the classifier it pins"
    assert hasattr(guard_mod, "test_runner_prompts_contain_stub_markers")


def test_guard_no_longer_duplicated_in_test_dev_runner():
    src = (TESTS / "test_dev_runner.py").read_text()
    assert "def test_runner_prompts_contain_stub_markers" not in src, \
        "the guard must have moved, not been copied — no duplicate definition should remain"


def test_guard_actually_fails_when_a_pinned_literal_is_missing(tmp_path, monkeypatch):
    """The guard is only worth moving if it still does its job: prove it fails loudly against synthetic
    runner text missing a pinned literal. Never edits the real tools/dev-runner.sh."""
    real_src = RUNNER.read_text()
    assert "TESTER" in real_src, "sanity: the real runner still carries the TESTER literal today"

    mutated = tmp_path / "dev-runner.sh"
    mutated.write_text(real_src.replace("TESTER", ""))
    monkeypatch.setattr(guard_mod, "RUNNER", mutated)
    with pytest.raises(AssertionError):
        guard_mod.test_runner_prompts_contain_stub_markers()


def test_guard_passes_against_the_real_runner():
    """The guard itself, exercised directly here (not just via pytest collection), stays green against
    the actual tools/dev-runner.sh."""
    guard_mod.test_runner_prompts_contain_stub_markers()
