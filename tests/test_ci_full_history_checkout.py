"""Tests for Issue #225 — ci: full-history checkout — end the main-push standing red.

Derived from the Issue #225 acceptance criteria (the spec), NOT from the implementation's
internals: `.github/workflows/ci.yml`'s checkout step must fetch full history
(`fetch-depth: 0`) so that history-pinned tests — e.g. the four pinned-range scope checks in
tests/test_shadow_seat_and_bench_docs.py, which `git diff` a fixed commit range — can resolve on
every push-to-main run, rather than dying with exit 128 under the shallow (`fetch-depth: 1`)
default. The workflow has a single job with one checkout step serving both the `pull_request`
and `push` triggers, so one `fetch-depth: 0` setting on that step covers both events.

This module is a file-content pin (same species as the repo's other doc/config pins): it asserts
the workflow *declares* the setting. It does not — and, per the issue, cannot — prove a live
push-to-main run is green; that recovery proof is observed attended, post-merge, since post-merge
main CI feeds no gate. No test here shells out to the network.

The four pinned-range tests in test_shadow_seat_and_bench_docs.py are the behavioral acceptance
for this fix and are left byte-identical; they are not modified or duplicated here.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _text():
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_ci_workflow_file_exists():
    assert CI_WORKFLOW.exists(), ".github/workflows/ci.yml is missing"


def test_ci_workflow_triggers_on_both_pull_request_and_push_to_main():
    text = _text()
    assert re.search(r"(?m)^\s*pull_request:\s*$", text), (
        "ci.yml must still trigger on pull_request"
    )
    assert re.search(r"(?m)^\s*push:\s*$", text), "ci.yml must still trigger on push"
    assert re.search(r"(?m)^\s*branches:\s*\[main\]\s*$", text), (
        "ci.yml's push trigger must still be scoped to main"
    )


def test_ci_workflow_has_exactly_one_checkout_step():
    """A single checkout step, shared by both triggers, is what lets one fetch-depth setting
    unambiguously cover pull_request and push alike."""
    text = _text()
    checkout_uses = re.findall(r"(?m)^\s*-\s*uses:\s*actions/checkout@", text)
    assert len(checkout_uses) == 1, (
        "expected exactly one actions/checkout step so a single fetch-depth setting "
        f"unambiguously covers both pull_request and push events; found {len(checkout_uses)}"
    )


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
    <pinned-sha>` over the fixed range dies with exit 128 'bad object' on a push-to-main run —
    the diagnosed cause of the standing red."""
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
