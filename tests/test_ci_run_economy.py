"""Acceptance tests for it-25 — CI run economy: one certification per task, minutes not tens.

Derived from the it-25 product-spec's acceptance criteria (04 projects/factory/iterations/
25-ci-run-economy/01-ci-run-economy.md), NOT from the workflow's incidental formatting:

  1. One certification per task — the PR-head run the merge evaluator's `ci_green` judges. The
     post-merge `push: main` re-run (a verdict no reader consumes) is retired: the workflow
     triggers on `pull_request` and NOT on `push`.
  2. A superseded in-flight run on the same PR is canceled, and no other PR's or ref's run ever
     is: a top-level `concurrency` block keyed by `github.ref` with `cancel-in-progress: true`.
  3. The suite runs parallel (`pytest tests/ -n auto`) so a green certification lands in
     single-digit minutes; `pytest-xdist` is declared so the plugin `-n` needs is present.
  4. The certification is present on every PR head the evaluator can be asked to judge — no path
     filter, skip rule, or trigger scope removes it from a PR's rollup (the docs-skip lever was
     rejected at it-25).

File-content pins (same species as test_ci_full_history_checkout.py and the repo's other config
pins): they assert what the workflow and manifest *declare*. The parallel==serial verdict
equivalence and the wall-clock ceiling are proven by the certification run itself (the landing
PR's CI), not by a unit test here. No test shells out to the network.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
REQUIREMENTS_DEV = ROOT / "requirements-dev.txt"


def _ci_text():
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_post_merge_push_run_is_retired():
    """One certification per task: the post-merge push:main re-run — a verdict no reader consumes
    — is retired. The workflow must NOT declare a `push` trigger."""
    # Not end-anchored: also catch an inline re-introduction (`push: {branches: [main]}`,
    # `push:  # ...`), not only the block form that was removed.
    assert not re.search(r"(?m)^\s*push:", _ci_text()), (
        "ci.yml must NOT trigger on push — the post-merge run was retired at it-25 (one "
        "certification per task, on the PR head the evaluator reads)"
    )


def test_certification_triggers_on_pull_request():
    """The one certification lives on the PR head the merge evaluator judges."""
    assert re.search(r"(?m)^\s*pull_request:\s*$", _ci_text()), (
        "ci.yml must trigger on pull_request — the certification the merge evaluator reads"
    )


def _concurrency_block(text):
    match = re.search(r"(?m)^concurrency:\s*$\n(?P<body>(?:^[ \t]+\S.*\n?)+)", text)
    return match.group("body") if match else None


def test_superseded_run_is_canceled_keyed_by_ref():
    """A superseded in-flight run on the same PR is canceled; keying the concurrency group on
    `github.ref` (unique per PR/ref) guarantees no other PR's or ref's run is ever canceled."""
    body = _concurrency_block(_ci_text())
    assert body is not None, "ci.yml must declare a top-level `concurrency:` block"
    assert re.search(r"(?m)^\s*cancel-in-progress:\s*true\s*$", body), (
        "the concurrency block must set `cancel-in-progress: true`"
    )
    assert re.search(r"(?m)^\s*group:.*github\.ref", body), (
        "the concurrency group must be keyed by `github.ref` so it never cancels another PR's "
        "or ref's run"
    )


def test_suite_runs_parallel_scoped_to_tests_dir():
    """The certification runs the suite in parallel (`-n auto`) scoped to tests/ — so xdist never
    collects a stray worktree copy."""
    assert re.search(r"pytest\s+tests/\s+-n\s+auto", _ci_text()), (
        "the test step must run `pytest tests/ -n auto` (parallel, scoped to tests/)"
    )


def test_requirements_declares_xdist_for_parallel():
    """`-n auto` needs the xdist plugin present; it must be a declared dev dependency."""
    lines = REQUIREMENTS_DEV.read_text(encoding="utf-8").splitlines()
    assert any(re.match(r"^pytest-xdist==", line.strip()) for line in lines), (
        "requirements-dev.txt must pin pytest-xdist — the parallel plugin `-n auto` needs"
    )


def test_no_path_or_skip_filter_removes_the_certification():
    """The certification is present on every PR head the evaluator can be asked to judge: no
    `paths:`/`paths-ignore:` trigger filter and no `if:` skip removes it from a PR's rollup (the
    docs-skip lever was rejected at it-25)."""
    text = _ci_text()
    assert not re.search(r"(?m)^\s*paths(-ignore)?:", text), (
        "ci.yml must not path-filter the certification — no `paths:`/`paths-ignore:`"
    )
    assert not re.search(r"(?m)^\s*if:\s", text), (
        "the certification must not carry an `if:` skip condition"
    )
