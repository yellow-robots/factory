"""Acceptance tests for issue #467 (it-36 slice C): the `claude -p` stage harness moves out of
tools/dev-runner.sh into one sourced library, tools/stage_lib.sh -- a byte-identical extraction, no
behaviour change. Every function/constant the issue names by its pre-move location (a fixed base
commit, the tip of main this task branched from) must reappear character-for-character in the new
library and vanish as a *definition* from the runner; the runner must source the library right after
SELF_DIR is set; and STAGE_CHARTER must stay a single-line, column-0 assignment.

Derived from the acceptance criteria alone: the "byte-identical" claim is checked against the actual
pre-move source text (read via git, not retyped or inferred from the post-move diff), never against
what the moved implementation happens to look like today.
"""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "dev-runner.sh"
STAGE_LIB = ROOT / "tools" / "stage_lib.sh"

# The commit this task branched from (tip of main pre-slice-C) -- the "verbatim" source of truth the
# issue's own line numbers (e.g. `run_stage :1492-1566`) refer to. Fixed by SHA so this test's meaning
# does not drift with whatever HEAD happens to be when it runs.
BASE_SHA = "9d5233e503db04af5261416aa4aff28d4b66e347"

# run_stage is deliberately absent: it moved here verbatim by #467, then was itself edited by #468
# (it-36 slice A deleted the shadow review seat's $6 ANTHROPIC_BASE_URL-override branch from it) — so
# it is no longer byte-identical to its BASE_SHA source, and this test's own verbatim-extraction
# machinery would fail on it by design. Its harness contract (the CLI invocation shape, the
# cred/plain branch pair) is pinned by tests/test_dev_runner.py instead; the extraction's other half
# — that it vanished as a DEFINITION from the runner — is covered separately below, alongside the
# seat's only remaining trace, `base_url`.
FUNCTIONS = [
    "verdict_line",
    "_set_role_from_json",
    "resolve_role",
    "is_quota_failure",
    "llm_quota_hold",
    "pool_for_model_id",
    "pool_credential",
    "wt_slug",
    "archive_stage_transcript",
    "capture_stage_usage",
    "reap_pgid",
    "wait_group_or_refuse",
    "stage_fail_msg",
    "stage_blocked_reason",
    "stage_blocked_dispose",
]

# Single-line constant/var assignments named in the issue, moved alongside the functions that use them.
CONSTANTS = [
    "REGISTRY",
    "QUOTA_SIGNATURES",
    "STAGE_GROUP_GRACE",
    "STAGE_REFUSAL_RC",
    "LAST_STAGE_GROUP_REFUSED",
    "LAST_STAGE_BG_UNRESOLVED",
    "LAST_STAGE_BG_REASON",
    "STAGE_CHARTER",
]


def _base_dev_runner_text():
    return subprocess.run(
        ["git", "show", f"{BASE_SHA}:tools/dev-runner.sh"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout


def _extract_func(text, name):
    """The exact source text of a `name(){ ... }` bash function definition, found by scanning brace
    depth from the opening `{` rather than a regex .*} (functions here contain their own nested
    `{`/`}` -- `if`/embedded python dict literals/`${...}` expansions -- so a non-greedy regex would
    stop at the first stray `}` instead of the function's own closing brace)."""
    m = re.search(rf'(?m)^{re.escape(name)}\(\)\{{', text)
    assert m, f"no `{name}(){{` definition found"
    i = m.end()
    depth = 1
    while depth > 0:
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    return text[m.start():i]


def _extract_const_line(text, name):
    m = re.search(rf'(?m)^{re.escape(name)}=.*$', text)
    assert m, f"no single-line assignment for {name}"
    return m.group(0)


@pytest.fixture(scope="module")
def base_text():
    return _base_dev_runner_text()


@pytest.fixture(scope="module")
def lib_text():
    return STAGE_LIB.read_text()


@pytest.fixture(scope="module")
def runner_text():
    return RUNNER.read_text()


def test_stage_lib_file_exists():
    assert STAGE_LIB.is_file(), "tools/stage_lib.sh must exist"


@pytest.mark.parametrize("name", FUNCTIONS)
def test_function_moved_verbatim_into_stage_lib(name, base_text, lib_text, runner_text):
    original = _extract_func(base_text, name)
    assert original in lib_text, f"{name}() is not byte-identical (or missing) in tools/stage_lib.sh"
    assert not re.search(rf'(?m)^{re.escape(name)}\(\)\{{', runner_text), \
        f"{name}() must no longer be DEFINED in tools/dev-runner.sh (it moved to stage_lib.sh)"


@pytest.mark.parametrize("name", CONSTANTS)
def test_constant_moved_verbatim_into_stage_lib(name, base_text, lib_text, runner_text):
    original = _extract_const_line(base_text, name)
    assert original in lib_text.splitlines(), \
        f"{name}'s assignment is not byte-identical (or missing) in tools/stage_lib.sh"
    assert original not in runner_text.splitlines(), \
        f"{name} must no longer be assigned in tools/dev-runner.sh (it moved to stage_lib.sh)"


def test_stage_charter_is_a_single_line_column_zero_assignment(lib_text):
    matches = [m for m in re.finditer(r'(?m)^STAGE_CHARTER=', lib_text)]
    assert len(matches) == 1, "STAGE_CHARTER must be assigned exactly once"
    line = lib_text.splitlines()[lib_text[:matches[0].start()].count("\n")]
    assert line.startswith('STAGE_CHARTER="') and line.endswith('"'), \
        "STAGE_CHARTER must remain a single physical line, column 0, double-quoted assignment"
    assert not re.search(r'(?m)^STAGE_CHARTER=', RUNNER.read_text()), \
        "STAGE_CHARTER must no longer be assigned in tools/dev-runner.sh"


def test_runner_sources_stage_lib_after_self_dir(runner_text):
    self_dir_match = re.search(r'(?m)^SELF_DIR=', runner_text)
    source_match = re.search(r'(?m)^source\s+"\$SELF_DIR/stage_lib\.sh"\s*$', runner_text)
    assert self_dir_match, "tools/dev-runner.sh must assign SELF_DIR"
    assert source_match, 'tools/dev-runner.sh must contain: source "$SELF_DIR/stage_lib.sh"'
    assert source_match.start() > self_dir_match.start(), \
        "stage_lib.sh must be sourced AFTER SELF_DIR is assigned"


def test_resolve_role_call_site_stays_in_the_runner(runner_text):
    """The functions moved; the one call site that invokes resolve_role for the build role stays
    behind in the runner (it reads runner-local vars BODY_BUILD/MF_MODEL/BUILD_MODEL)."""
    assert re.search(r'(?m)^resolve_role build ', runner_text), \
        "the resolve_role call for the build role must remain in tools/dev-runner.sh"


def test_run_stage_lives_only_in_stage_lib_and_carries_no_shadow_seat_trace(lib_text, runner_text):
    """run_stage() is excluded from the verbatim FUNCTIONS pin above (it-36 slice A edited it after
    #467's move), so this test covers what that pin would otherwise have covered: the extraction's
    "vanished from the runner" half still holds for run_stage specifically, and `base_url` — the
    shadow review seat's only trace in this function ($6, the ANTHROPIC_BASE_URL override) — is gone
    from both files, not just renamed or shuffled."""
    assert re.search(r'(?m)^run_stage\(\)\{', lib_text), \
        "run_stage() must be DEFINED in tools/stage_lib.sh"
    assert not re.search(r'(?m)^run_stage\(\)\{', runner_text), \
        "run_stage() must no longer be DEFINED in tools/dev-runner.sh (it moved to stage_lib.sh)"
    assert "base_url" not in lib_text, \
        "tools/stage_lib.sh must carry no base_url — the shadow review seat's only trace in run_stage"
    assert "base_url" not in runner_text, \
        "tools/dev-runner.sh must carry no base_url — the shadow review seat's only trace in run_stage"


def test_stage_lib_is_valid_bash_syntax():
    r = subprocess.run(["bash", "-n", str(STAGE_LIB)], capture_output=True, text=True)
    assert r.returncode == 0, f"tools/stage_lib.sh has a syntax error:\n{r.stderr}"


def test_runner_is_valid_bash_syntax():
    r = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True, text=True)
    assert r.returncode == 0, f"tools/dev-runner.sh has a syntax error:\n{r.stderr}"
