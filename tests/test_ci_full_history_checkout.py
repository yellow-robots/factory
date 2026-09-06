"""Full-history checkout for the CI certification run (Issue #225, preserved at it-25).

Derived from the Issue #225 acceptance criteria (the spec), NOT from the implementation's
internals: `.github/workflows/ci.yml`'s checkout step must fetch full history
(`fetch-depth: 0`) so that history-pinned tests — any suite that `git diff`s a fixed commit
range — can resolve on the certification run, rather than dying with exit 128 under the shallow
(`fetch-depth: 1`) default.

Contract history: #225 introduced full-history checkout to end the main-push standing red, when
the workflow ran on both `pull_request` and `push: main`. it-25 retired the post-merge `push: main`
run entirely (one certification per task, on the PR head the merge evaluator reads — the trigger
contract is pinned in test_ci_run_economy.py), so the full-history requirement now rides the single
`pull_request` certification run. it-25 preserves it verbatim: "keep full-history checkout for
certification runs."

This module is a file-content pin (same species as the repo's other doc/config pins): it asserts
the workflow *declares* the setting. No test here shells out to the network.

The four pinned-range tests that originally motivated this fix (it-36 slice A: retired alongside
the shadow review seat they exercised) are gone, but the full-history-checkout requirement itself
is independent of any one consuming suite — it stays needed for any future history-pinned test.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _text():
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_ci_workflow_file_exists():
    assert CI_WORKFLOW.exists(), ".github/workflows/ci.yml is missing"


def test_ci_certification_run_triggers_on_pull_request():
    """The certification run — the PR head the merge evaluator judges — triggers on pull_request,
    and full history must be present there. The push:main retirement is pinned in
    test_ci_run_economy.py."""
    text = _text()
    assert re.search(r"(?m)^\s*pull_request:\s*$", text), (
        "ci.yml must trigger on pull_request — the certification run that needs full history"
    )

# The one-checkout cardinality assertion that lived here migrated to a declared rule in
# qa/cardinality.toml (`ci-checkout-step`, max 1, birth #225) at it-27 slice A3, issue #365.
# The fetch-depth assertions below are unaffected: they test a VALUE, not a count.



def _checkout_step_body(text):
    match = re.search(
        r"(?m)^(?P<indent>[ \t]*)-\s*uses:\s*actions/checkout@\S+[ \t]*\n"
        r"(?P<body>(?:(?P=indent)[ \t]+\S.*\n?)*)",
        text,
    )
    assert match, "could not locate the actions/checkout step in ci.yml"
    return match.group("body")


def test_ci_workflow_checkout_step_fetches_full_history():
    """The checkout step SHALL declare `fetch-depth: 0` (full history). A shallow default
    (`fetch-depth: 1`) ships a single commit with no history, so `git diff <pinned-sha>
    <pinned-sha>` over the fixed range dies with exit 128 'bad object' on the pull_request
    certification run — the class #225 diagnosed (originally on the since-retired push-to-main
    run)."""
    step_body = _checkout_step_body(_text())
    assert re.search(r"(?m)^\s*with:\s*$", step_body), (
        "the checkout step has no `with:` block — fetch-depth: 0 must be declared under it"
    )
    assert re.search(r"(?m)^\s*fetch-depth:\s*0\s*$", step_body), (
        "the checkout step must declare `fetch-depth: 0` to fetch full history"
    )


def test_checkout_step_runs_before_the_test_suite_step():
    """Full history must be present before pytest runs the history-pinned tests."""
    text = _text()
    checkout_pos = text.index("actions/checkout@")
    tests_step_pos = text.index("pytest tests/")
    assert checkout_pos < tests_step_pos, (
        "the checkout step (with full history) must run before the test suite step"
    )
