"""Acceptance tests for it-27 slice A2 (issue #364) — lint on every mutation path, and the
mutation flag as a tree-changed predicate.

Derived from the it-27 product-spec's acceptance criteria:

  20. THE SYSTEM SHALL run the repo's declared lint command on every path that mutates code before
      that code is committed.
  21. WHEN an autofix command runs without changing any bytes, THE SYSTEM SHALL NOT force a re-run
      of the check gate.

Criterion 21's letter names only the autofix. The accepted disposition of improvement I1 is that
the right predicate is *the tree changed* and that it must apply at BOTH flag sites — the
deterministic autofix and the LLM lint repair — because the LLM path may equally end in a reasoned
no-fix having changed nothing. Fixing only the autofix site corrects the cheaper half and leaves the
LLM path paying a full suite (761-812 s on the build host). So the criterion's letter is a subset of
what is asserted here, never a contradiction of it.

The two uncovered paths criterion 20 closes, both of which ran `run_checks` only:
  - review-repair (`tools/dev-runner.sh`), which runs with `Read Edit Write Bash` and may rewrite
    any file;
  - `rebase_onto_tip`, which rebases onto a moved base and force-pushes — this one sits on the
    MERGE path, so an armed merge shipped the rebased tree unlinted.

The load-bearing regression guard is `test_lint_verdict_is_enforced_outside_the_mutation_branch`.
Making the whole post-repair block conditional on LINT_MUTATED is the obvious way to implement
criterion 21 and it is WRONG: a repair ending in a reasoned no-fix leaves lint red, and nothing else
re-tests it, so the red lint would reach the commit — the exact inverse of the tier's purpose.
"""

import pathlib
import re
import subprocess

RUNNER = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dev-runner.sh"


def _runner_text():
    return RUNNER.read_text(encoding="utf-8")


def _func_source(name):
    """The source of shell function `name`, from `name(){` to the closing `}` at column 0."""
    text = _runner_text()
    m = re.search(rf"^{re.escape(name)}\(\)\{{$", text, re.MULTILINE)
    assert m, f"tools/dev-runner.sh defines no function {name}()"
    lines = text[m.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        out.append(ln)
        if ln == "}":
            return "\n".join(out)
    raise AssertionError(f"{name}() has no closing brace at column 0")


def _lint_tier():
    """The lint tier's body — from the LINT_MUTATED initializer to the lens tier that follows."""
    text = _runner_text()
    start = text.index("    LINT_MUTATED=0")
    end = text.index("# ---- lens tier", start)
    return text[start:end]


# --- criterion 21: the predicate is "the tree changed", at BOTH sites -----------------------

def test_tree_hash_helper_exists_and_hashes_the_worktree():
    src = _func_source("tree_hash")
    assert "write-tree" in src, "tree_hash() does not hash a tree"
    assert "add -A" in src, "tree_hash() does not stage before hashing, so it would miss new files"


def test_tree_hash_is_stable_when_nothing_changes(tmp_path):
    a, b = _run_tree_hash_twice(tmp_path, mutate=False)
    assert a == b, (
        f"tree_hash() returned different values ({a!r} vs {b!r}) for an unchanged tree — the "
        "predicate would report every repair as a mutation and nothing would be saved"
    )


def test_tree_hash_changes_when_a_file_changes(tmp_path):
    a, b = _run_tree_hash_twice(tmp_path, mutate=True)
    assert a != b, (
        "tree_hash() returned the same value after a file changed — the predicate would skip the "
        "re-run of both gates on a real mutation, shipping unverified code"
    )


def test_tree_hash_notices_a_new_untracked_file(tmp_path):
    a, b = _run_tree_hash_twice(tmp_path, mutate=True, new_file=True)
    assert a != b, (
        "tree_hash() missed a newly created file — a repair that ADDS a module would read as "
        "'changed nothing' and skip its verification"
    )


def _run_tree_hash_twice(tmp_path, *, mutate, new_file=False):
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    (wt / "a.py").write_text("x = 1\n", encoding="utf-8")
    mutation = ""
    if mutate and new_file:
        mutation = "printf 'y = 2\\n' > \"$WT/b.py\""
    elif mutate:
        mutation = "printf 'x = 2\\n' > \"$WT/a.py\""
    script = f"""
    GIT_BIN=git
    WT={wt}
    {_func_source("tree_hash")}
    tree_hash
    {mutation}
    tree_hash
    """
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert r.returncode == 0, f"tree_hash harness failed: {r.stderr}"
    out = r.stdout.split()
    assert len(out) == 2, f"expected two hashes, got {out!r} (stderr: {r.stderr})"
    return out[0], out[1]


def test_the_mutation_flag_is_never_set_unconditionally():
    """Both `LINT_MUTATED=1` sites must be guarded by the tree comparison."""
    tier = _lint_tier()
    sets = [ln.strip() for ln in tier.splitlines() if re.search(r"\bLINT_MUTATED=1\b", ln)]
    assert sets, "no LINT_MUTATED=1 assignment found — has the lint tier been restructured?"
    unguarded = [ln for ln in sets if "tree_hash" not in ln]
    assert not unguarded, (
        "LINT_MUTATED is set unconditionally at:\n  " + "\n  ".join(unguarded) +
        "\nThe predicate must be 'the tree changed', never 'a repair path was entered'"
    )


def test_the_predicate_is_applied_at_both_repair_sites():
    """The autofix site and the LLM-repair site — fixing one leaves the other paying."""
    tier = _lint_tier()
    guarded = [ln for ln in tier.splitlines() if re.search(r"\bLINT_MUTATED=1\b", ln)]
    assert len(guarded) == 2, (
        f"expected exactly 2 guarded mutation sites (deterministic autofix, LLM repair), found "
        f"{len(guarded)}:\n" + "\n".join(guarded)
    )


# --- the regression guard: criterion 21 must not weaken the gate ---------------------------

def test_lint_verdict_is_enforced_outside_the_mutation_branch():
    """A repair that changes nothing and leaves lint RED must still block.

    If the `fail_blocked` on LINT_RC sits inside `if [ "$LINT_MUTATED" -eq 1 ]`, then a reasoned
    no-fix produces: flag stays 0 -> block skipped -> nothing else re-tests lint -> a red lint
    reaches the commit. This test pins the verdict at the tier's own indent level, outside it.
    """
    tier = _lint_tier()
    verdict = [ln for ln in tier.splitlines()
               if 'fail_blocked "lint still failing after one repair (log:' in ln]
    assert len(verdict) == 1, f"expected one lint verdict line, found {len(verdict)}"
    indent = len(verdict[0]) - len(verdict[0].lstrip())
    assert indent == 4, (
        f"the lint verdict is indented {indent} spaces, expected 4 (the tier's own level). A "
        "deeper indent means it sits inside the LINT_MUTATED branch, so a repair that changed "
        "nothing would carry a red lint to the commit."
    )


def test_background_task_check_is_also_unconditional():
    """An abandoned background task is untrustworthy whether or not the repair changed bytes."""
    tier = _lint_tier()
    line = [ln for ln in tier.splitlines() if "LINT_REPAIR_BG_UNRESOLVED" in ln and "fail_blocked" in ln]
    assert len(line) == 1, f"expected one bg_scan block line, found {len(line)}"
    indent = len(line[0]) - len(line[0].lstrip())
    assert indent == 4, f"the bg_scan verdict is indented {indent}, expected 4 (outside the branch)"


# --- criterion 20: every mutation path re-lints ---------------------------------------------

def test_review_repair_path_relints():
    text = _runner_text()
    i = text.index("run_checks review-repair-recheck")
    window = text[i:i + 1200]
    assert "run_lint" in window, (
        "the review-repair path re-runs only the check gate — an LLM edit made after the lint tier "
        "passed would ship unlinted, which is why 'the runner guarantees a lint-clean head' was false"
    )


def test_review_repair_lint_failure_blocks():
    text = _runner_text()
    i = text.index("run_checks review-repair-recheck")
    window = text[i:i + 1200]
    assert "fail_blocked" in window and "lint failing after review-repair" in window, (
        "the review-repair lint runs but its failure does not block — an advisory lint on a "
        "mutation path is not a gate"
    )


def test_rebase_path_relints():
    """The merge path: an armed merge must never ship a rebased tree no lint has seen."""
    src = _func_source("rebase_onto_tip")
    assert "run_lint" in src, (
        "rebase_onto_tip() does not re-lint. It rebases onto a moved base and force-pushes, so the "
        "resulting tree has never met the lint gate — and it sits on the merge path"
    )
    lint_at = src.index("run_lint")
    checks_at = src.index("run_checks rebase-recheck")
    assert lint_at > checks_at, "the rebase re-lint runs before the check gate; mirror the tier's order"


def test_rebase_lint_failure_returns_the_blocking_code():
    """rebase_onto_tip's contract: 1 = block for the human, 2 = environmental."""
    src = _func_source("rebase_onto_tip")
    tail = src[src.index("run_lint"):]
    assert "return 1" in tail, "a lint failure in rebase_onto_tip does not block (no `return 1`)"
    assert "return 2" in tail, "an environmental lint failure in rebase_onto_tip is not rc 2"


def test_every_mutation_path_uses_the_shared_run_lint():
    """No hand-rolled invocation: run_lint carries the worktree confinement and 126/127 discipline."""
    text = _runner_text()
    for site in ("review-repair-lint", "rebase-lint"):
        assert f'run_lint "$LINT_CMD" {site}' in text, (
            f"the {site} site does not go through run_lint(), losing its worktree cd, PATH setup, "
            "liveness-judged wait and environment-failure discipline"
        )


def test_new_lint_sites_are_guarded_by_a_declared_lint_cmd():
    """Absent lint_cmd the tier is absent — capability-defaults-off must hold on the new paths too."""
    text = _runner_text()
    for site in ("review-repair-lint", "rebase-lint"):
        i = text.index(f'run_lint "$LINT_CMD" {site}')
        preceding = text[max(0, i - 500):i]
        assert '[ -n "$LINT_CMD" ]' in preceding, (
            f"the {site} site is not guarded by a declared lint_cmd — a repo that declares none "
            "would run an empty command on a mutation path"
        )
