"""Acceptance tests for issue #245 — the eight gh stub definitions become one shared fake.

Derived from the CRITERIA (the spec: exactly one shared `gh` fake lives in tests/harness/gh_fake.py,
every suite faking `gh` obtains it from there, no private clone remains anywhere in tests/; the shared
fake serves both its bash and python consumers with each consuming suite's recorded canned-response
behavior preserved), NOT from the implementation's internals.

The eight definitions named in the issue's 2026-07-16 census (seven files):
  tests/test_dev_runner.py:15            — GH_STUB        (bash face)
  tests/test_dev_runner.py:2844          — GH_STUB_PR     (bash face)
  tests/test_autonomous_merge.py:37      — GH_STUB_EXT    (bash face)
  tests/test_ci_registration_grace.py:44 — GH_STUB_SEQ    (bash face)
  tests/test_dev_runner_reevaluate.py:34 — GH_STUB_REEVAL (bash face)
  tests/test_board.py:12                 — GH_STUB        (python face)
  tests/test_promote.py:13               — GH_STUB        (python face)
  tests/test_watch_build.py:13           — GH_STUB        (python face)

Covered here:
  * the clone census, across the WHOLE tests/ tree (not just the eight named files): no full
    gh-subcommand-dispatch re-implementation — bash- or python-shaped — survives anywhere outside
    tests/harness/gh_fake.py;
  * each of the five named bash privates (GH_STUB_PR/EXT/SEQ/REEVAL) is gone by name from its file;
  * every one of the eight consuming files' GH_STUB is (by identity, not by re-typed text) an object
    obtained from tests/harness/gh_fake.py — GH_STUB for the bash family, GH_STUB_TOOLS for the python
    family;
  * the bash face (GH_STUB) and python face (GH_STUB_TOOLS), run directly and independent of
    tools/dev-runner.sh / tools/merge_shadow.py / tools/board.sh / tools/promote.sh /
    tools/watch_build.sh, reproduce every canned-response scenario contract.md documents for their
    respective consumers;
  * one representative end-to-end run per tool family (dev-runner.sh's happy path and its merge-arm
    extension, board.sh, promote.sh, watch_build.sh) still completes through the shared fake.

Runs under `python3 -m pytest tests/ -q` (system python3 works — no third-party deps).
"""
import ast
import json
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
import gh_fake  # noqa: E402

sys.path.insert(0, str(TESTS))
import test_dev_runner as td  # noqa: E402

# --------------------------------------------------------------------------------------------------
# helpers shared by every section below
# --------------------------------------------------------------------------------------------------


def _plain_string_assignments(path):
    """Every plain (non-derived) string literal assigned to a module-level name in `path` — i.e. NOT
    the result of a method/attribute expression like `gh_fake.GH_STUB` or `GH_STUB.replace(...)`, which
    obtains/derives from an existing value rather than retyping one. Returns {name: text}."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _is_bash_gh_reimplementation(text):
    """A `gh` bash-fake shape: a `$1`-keyed subcommand case block ending in the shared catch-all every
    one of the five retired bash variants (and the shared GH_STUB itself) carries verbatim."""
    return ('case "$1" in' in text and 'pr)' in text
            and 'echo "unhandled gh $*" >&2; exit 9' in text)


def _is_python_gh_reimplementation(text):
    """A `gh` python-fake shape: dispatches `api graphql` by presence of canned input, catch-all exit 9
    — the shape all three retired python variants (and the shared GH_STUB_TOOLS itself) share."""
    return 'argv[:2] == ["api", "graphql"]' in text and "sys.exit(9)" in text


def _all_test_py_files():
    """Every .py file under tests/, excluding the shared fake's own module (its one legal home)."""
    return [p for p in TESTS.rglob("*.py") if p.resolve() != (HARNESS / "gh_fake.py").resolve()]


def _import_sibling(modname):
    if modname in sys.modules:
        return sys.modules[modname]
    return __import__(modname)


def _write_stub(tmp_path, body, name="gh"):
    script = tmp_path / name
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _run_bash_face(tmp_path, argv, extra_env=None):
    script = _write_stub(tmp_path, gh_fake.GH_STUB)
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run([str(script), *argv], capture_output=True, text=True, cwd=tmp_path, env=env)


def _run_python_face(tmp_path, argv, extra_env=None):
    script = _write_stub(tmp_path, gh_fake.GH_STUB_TOOLS)
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run([str(script), *argv], capture_output=True, text=True, cwd=tmp_path, env=env)


# ====================================================================================================
# THE SYSTEM SHALL provide exactly one shared gh fake in the shared home — no private clone survives
# anywhere in the tests/ tree.
# ====================================================================================================

def test_no_full_gh_fake_reimplementation_anywhere_in_tests():
    offenders = []
    for f in _all_test_py_files():
        for name, text in _plain_string_assignments(f).items():
            if _is_bash_gh_reimplementation(text) or _is_python_gh_reimplementation(text):
                offenders.append(f"{f.relative_to(ROOT)}::{name}")
    assert not offenders, f"private gh fake re-implementation(s) found: {offenders}"


@pytest.mark.parametrize("filename,stub_name", [
    ("test_dev_runner.py", "GH_STUB_PR"),
    ("test_autonomous_merge.py", "GH_STUB_EXT"),
    ("test_ci_registration_grace.py", "GH_STUB_SEQ"),
    ("test_dev_runner_reevaluate.py", "GH_STUB_REEVAL"),
])
def test_named_private_bash_stub_removed(filename, stub_name):
    src = (TESTS / filename).read_text()
    assert stub_name not in src, (
        f"{stub_name} must be gone from tests/{filename} — migrated to a mode of "
        "tests/harness/gh_fake.GH_STUB"
    )


def test_gh_stub_no_longer_a_fresh_literal_in_test_dev_runner():
    assignments = _plain_string_assignments(TESTS / "test_dev_runner.py")
    assert "GH_STUB" not in assignments, (
        "tests/test_dev_runner.py must import GH_STUB from tests/harness/gh_fake, not define it as its "
        "own literal"
    )


@pytest.mark.parametrize("filename", ["test_board.py", "test_promote.py", "test_watch_build.py"])
def test_gh_stub_no_longer_a_fresh_literal_in_python_family(filename):
    assignments = _plain_string_assignments(TESTS / filename)
    assert "GH_STUB" not in assignments, (
        f"tests/{filename} must obtain GH_STUB from tests/harness/gh_fake.GH_STUB_TOOLS, not define "
        "it as its own literal"
    )


# ====================================================================================================
# The shared home carries both faces, and every consumer holds the SAME object (not a copy).
# ====================================================================================================

def test_bash_face_lives_in_the_shared_home():
    assert hasattr(gh_fake, "GH_STUB"), "tests/harness/gh_fake.py must carry GH_STUB, the bash face"
    assert 'case "$1" in' in gh_fake.GH_STUB


def test_python_face_lives_in_the_shared_home():
    assert hasattr(gh_fake, "GH_STUB_TOOLS"), \
        "tests/harness/gh_fake.py must carry GH_STUB_TOOLS, the python face"
    assert 'argv[:2] == ["api", "graphql"]' in gh_fake.GH_STUB_TOOLS


def test_test_dev_runner_gh_stub_is_the_shared_object_not_a_copy():
    assert td.GH_STUB is gh_fake.GH_STUB, \
        "tests/test_dev_runner.py's GH_STUB must be the SAME object as the shared home's, not a copy"


@pytest.mark.parametrize("modname", [
    "test_autonomous_merge", "test_ci_registration_grace", "test_dev_runner_reevaluate",
])
def test_bash_family_sibling_consumes_the_shared_object(modname):
    """These three files no longer bind their own module-level GH_STUB* name at all — they call
    `td._exec(binp / "gh", td.GH_STUB)` directly at each call site. If one DID rebind a local name, it
    must still resolve to the shared object, never a fresh literal."""
    mod = _import_sibling(modname)
    if hasattr(mod, "GH_STUB"):
        assert mod.GH_STUB is gh_fake.GH_STUB


@pytest.mark.parametrize("modname", ["test_board", "test_promote", "test_watch_build"])
def test_python_family_sibling_gh_stub_is_the_shared_object(modname):
    mod = _import_sibling(modname)
    assert mod.GH_STUB is gh_fake.GH_STUB_TOOLS, \
        f"tests/{modname}.py's GH_STUB must be tests/harness/gh_fake.GH_STUB_TOOLS by identity"


# ====================================================================================================
# The bash face serves its five consumers — every canned-response scenario contract.md documents,
# run directly against tests/harness/gh_fake.GH_STUB, independent of tools/dev-runner.sh.
# ====================================================================================================

def test_bash_face_repo_any_subcommand_prints_stub_repo(tmp_path):
    r = _run_bash_face(tmp_path, ["repo", "view"])
    assert r.returncode == 0
    assert r.stdout.strip() == "test/repo"


def test_bash_face_issue_view_cats_stub_issue_json(tmp_path):
    issue_json = tmp_path / "issue.json"
    issue_json.write_text('{"number": 7}')
    r = _run_bash_face(tmp_path, ["issue", "view", "7", "--json", "number"],
                        {"STUB_ISSUE_JSON": str(issue_json)})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"number": 7}


def test_bash_face_issue_comment_appends_to_timeline(tmp_path):
    timeline = tmp_path / "timeline"
    r = _run_bash_face(tmp_path, ["issue", "comment", "7", "--body", "hi"],
                        {"STUB_TIMELINE": str(timeline)})
    assert r.returncode == 0
    assert timeline.read_text().startswith("COMMENT")


def test_bash_face_project_item_list_ok(tmp_path):
    item_json = tmp_path / "item.json"
    item_json.write_text('{"items": []}')
    r = _run_bash_face(tmp_path, ["project", "item-list", "1"], {"STUB_ITEM_JSON": str(item_json)})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"items": []}


def test_bash_face_project_item_list_fail(tmp_path):
    r = _run_bash_face(tmp_path, ["project", "item-list", "1"], {"STUB_ITEMLIST_FAIL": "1"})
    assert r.returncode == 4


def test_bash_face_project_item_edit_appends_to_timeline(tmp_path):
    timeline = tmp_path / "timeline"
    r = _run_bash_face(tmp_path, ["project", "item-edit", "--id", "X"], {"STUB_TIMELINE": str(timeline)})
    assert r.returncode == 0
    assert timeline.read_text().startswith("EDIT")


def test_bash_face_pr_view_rollup_fail(tmp_path):
    r = _run_bash_face(tmp_path, ["pr", "view", "1", "--json", "statusCheckRollup"],
                        {"STUB_PRVIEW_FAIL": "1"})
    assert r.returncode == 5


def test_bash_face_pr_view_rollup_default_fallback_records_call(tmp_path):
    calls = tmp_path / "gh_calls"
    r = _run_bash_face(tmp_path, ["pr", "view", "1", "--json", "statusCheckRollup"],
                        {"STUB_GH_CALLS": str(calls)})
    assert r.returncode == 0
    assert "https://stub/pr/1" in r.stdout
    assert "statusCheckRollup" in calls.read_text()


def test_bash_face_pr_view_rollup_json_direct(tmp_path):
    rollup = tmp_path / "rollup.json"
    rollup.write_text('{"statusCheckRollup": []}')
    r = _run_bash_face(tmp_path, ["pr", "view", "1", "--json", "statusCheckRollup"],
                        {"STUB_ROLLUP_JSON": str(rollup)})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"statusCheckRollup": []}


def test_bash_face_pr_view_rollup_sequenced_calls_then_fails_at_threshold(tmp_path):
    """test_ci_registration_grace.py's retired GH_STUB_SEQ scenario: call #1 serves _1, later calls
    serve _2, and STUB_ROLLUP_FAIL_AT makes the call AT that number (and after) fail."""
    j1 = tmp_path / "r1.json"; j1.write_text('{"n": 1}')
    j2 = tmp_path / "r2.json"; j2.write_text('{"n": 2}')
    counter = tmp_path / "calls_counter"
    env = {"STUB_ROLLUP_CALLS": str(counter), "STUB_ROLLUP_JSON_1": str(j1), "STUB_ROLLUP_JSON_2": str(j2),
           "STUB_ROLLUP_FAIL_AT": "3"}
    argv = ["pr", "view", "1", "--json", "statusCheckRollup"]
    r1 = _run_bash_face(tmp_path, argv, env)
    assert json.loads(r1.stdout) == {"n": 1}
    r2 = _run_bash_face(tmp_path, argv, env)
    assert json.loads(r2.stdout) == {"n": 2}
    r3 = _run_bash_face(tmp_path, argv, env)
    assert r3.returncode == 5


def test_bash_face_pr_view_mergecommit(tmp_path):
    r = _run_bash_face(tmp_path, ["pr", "view", "1", "--json", "mergeCommit"],
                        {"STUB_MERGECOMMIT_OID": "abc123"})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"mergeCommit": {"oid": "abc123"}}


def test_bash_face_pr_view_reeval_fetch_ok(tmp_path):
    """test_dev_runner_reevaluate.py's re-evaluate PR-state fetch: disambiguated by a --json field list
    containing headRefName, never by which env var happens to be set."""
    prjson = tmp_path / "pr.json"
    prjson.write_text('{"headRefName": "task/7-x"}')
    r = _run_bash_face(tmp_path, ["pr", "view", "1", "--json", "headRefName,state"],
                        {"STUB_REEVAL_PRJSON": str(prjson)})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"headRefName": "task/7-x"}


def test_bash_face_pr_view_reeval_fetch_fail(tmp_path):
    r = _run_bash_face(tmp_path, ["pr", "view", "1", "--json", "headRefName,state"],
                        {"STUB_PRFETCH_FAIL": "1"})
    assert r.returncode == 5


def test_bash_face_pr_view_fallback_records_and_echoes(tmp_path):
    calls = tmp_path / "gh_calls"
    r = _run_bash_face(tmp_path, ["pr", "view", "1"], {"STUB_GH_CALLS": str(calls)})
    assert r.returncode == 0
    assert "https://stub/pr/1" in r.stdout


def test_bash_face_pr_create_retries_then_succeeds_and_marks_existing(tmp_path):
    counter = tmp_path / "pr_create_counter"
    exists_file = tmp_path / "pr_exists"
    calls_log = tmp_path / "pr_create_calls"
    env = {
        "STUB_PRCREATE_COUNTER": str(counter),
        "STUB_PRCREATE_CALLS": str(calls_log),
        "STUB_PRCREATE_FAIL_COUNT": "1",
        "STUB_PRCREATE_MARKS_EXISTING": "1",
        "STUB_PR_EXISTS_FILE": str(exists_file),
    }
    argv = ["pr", "create", "--title", "t", "--body", "b"]
    r1 = _run_bash_face(tmp_path, argv, env)
    assert r1.returncode == 1
    assert exists_file.exists(), "a failing attempt marks the PR as already existing"
    r2 = _run_bash_face(tmp_path, argv, env)
    assert r2.returncode == 0
    assert "https://stub/pr/1" in r2.stdout
    assert calls_log.read_text().count("CALL") == 2


def test_bash_face_pr_create_always_fails(tmp_path):
    r = _run_bash_face(tmp_path, ["pr", "create", "--title", "t", "--body", "b"],
                        {"STUB_PRCREATE_FAIL_COUNT": "always", "STUB_PRCREATE_ERR": "stub: 502 Bad Gateway"})
    assert r.returncode == 1
    assert "502 Bad Gateway" in r.stderr


def test_bash_face_pr_list_head_existence_check(tmp_path):
    r_empty = _run_bash_face(tmp_path, ["pr", "list", "--head", "task/7-x", "--json", "url"])
    assert json.loads(r_empty.stdout) == []
    exists_file = tmp_path / "pr_exists"
    exists_file.write_text("https://stub/pr/9")
    r_found = _run_bash_face(tmp_path, ["pr", "list", "--head", "task/7-x", "--json", "url"],
                              {"STUB_PR_EXISTS_FILE": str(exists_file)})
    assert json.loads(r_found.stdout) == [{"url": "https://stub/pr/9"}]


def test_bash_face_pr_list_shadow_scan_ok(tmp_path):
    prs = tmp_path / "prs.json"; prs.write_text('[{"number": 3}]')
    r = _run_bash_face(tmp_path, ["pr", "list", "--state", "open"], {"STUB_PRS_JSON": str(prs)})
    assert r.returncode == 0
    assert json.loads(r.stdout) == [{"number": 3}]


def test_bash_face_pr_list_shadow_scan_fail(tmp_path):
    r = _run_bash_face(tmp_path, ["pr", "list", "--state", "open"], {"STUB_PRLIST_FAIL": "1"})
    assert r.returncode == 5


def test_bash_face_pr_merge_ok_records_call(tmp_path):
    calls = tmp_path / "gh_calls"
    r = _run_bash_face(tmp_path, ["pr", "merge", "1", "--squash"], {"STUB_GH_CALLS": str(calls)})
    assert r.returncode == 0
    assert r.stdout.strip() == "merged"
    assert "MERGE" in calls.read_text()


def test_bash_face_pr_merge_fail(tmp_path):
    r = _run_bash_face(tmp_path, ["pr", "merge", "1", "--squash"], {"STUB_MERGE_FAIL": "1"})
    assert r.returncode == 6


def test_bash_face_pr_comment_records_body_file(tmp_path):
    timeline = tmp_path / "timeline"
    bodyfile = tmp_path / "body.txt"; bodyfile.write_text("hello world")
    prcomments = tmp_path / "prcomments"
    r = _run_bash_face(tmp_path, ["pr", "comment", "1", "--body-file", str(bodyfile)],
                        {"STUB_TIMELINE": str(timeline), "STUB_PRCOMMENTS": str(prcomments)})
    assert r.returncode == 0
    assert "PRCOMMENT" in timeline.read_text()
    assert "hello world" in prcomments.read_text()


def test_bash_face_pr_comment_records_inline_body(tmp_path):
    """--body-file and --body are each independently tracked (the recorder is a real gh pr comment
    which exits 0 regardless of which flag was actually passed) — this is the exact class of
    transport-anchored assertion the shared fake's own docstring calls out as needing the trailing
    `true` guard, so both flag shapes are exercised here rather than just one."""
    timeline = tmp_path / "timeline"
    prcomments = tmp_path / "prcomments"
    r = _run_bash_face(tmp_path, ["pr", "comment", "1", "--body", "inline text"],
                        {"STUB_TIMELINE": str(timeline), "STUB_PRCOMMENTS": str(prcomments)})
    assert r.returncode == 0
    assert "inline text" in prcomments.read_text()


def test_bash_face_unhandled_subcommand_exits_nonzero(tmp_path):
    r = _run_bash_face(tmp_path, ["release", "list"])
    assert r.returncode == 9


# ====================================================================================================
# The python face serves its three consumers — every canned-response scenario contract.md documents,
# run directly against tests/harness/gh_fake.GH_STUB_TOOLS, independent of the tool scripts.
# ====================================================================================================

def test_python_face_repo_view_prints_default(tmp_path):
    r = _run_python_face(tmp_path, ["repo", "view"])
    assert r.returncode == 0
    assert r.stdout.strip() == "test/repo"


def test_python_face_repo_view_prints_stub_repo_override(tmp_path):
    r = _run_python_face(tmp_path, ["repo", "view"], {"STUB_REPO": "yr/other"})
    assert r.stdout.strip() == "yr/other"


def test_python_face_graphql_nodes_board_shape(tmp_path):
    nodes = [{"content": {"number": 1}}]
    r = _run_python_face(tmp_path, ["api", "graphql", "-f", "query=..."],
                          {"STUB_NODES": json.dumps(nodes)})
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["data"]["organization"]["projectV2"]["items"]["nodes"] == nodes


def test_python_face_graphql_issue_response_echoed_verbatim(tmp_path):
    payload = '{"data": {"repository": {"issue": {"state": "OPEN"}}}}'
    r = _run_python_face(tmp_path, ["api", "graphql", "-f", "query=..."],
                          {"STUB_ISSUE_RESPONSE": payload})
    assert r.returncode == 0
    assert r.stdout.strip() == payload


def test_python_face_graphql_states_tick_indexed_shape(tmp_path):
    states = [{"status": "Ready", "reason": None, "issue_state": "OPEN"}]
    r = _run_python_face(tmp_path, ["api", "graphql", "-f", "query=..."],
                          {"STUB_STATES": json.dumps(states), "PROJECT_NUMBER": "5"})
    assert r.returncode == 0
    data = json.loads(r.stdout)
    node = data["data"]["repository"]["issue"]["projectItems"]["nodes"][0]
    assert node["project"]["number"] == 5
    assert node["status"] == {"name": "Ready"}
    assert node["reason"] is None


def test_python_face_graphql_no_canned_input_exits_nonzero(tmp_path):
    r = _run_python_face(tmp_path, ["api", "graphql", "-f", "query=..."])
    assert r.returncode == 9


def test_python_face_api_user_prints_default_and_override(tmp_path):
    r = _run_python_face(tmp_path, ["api", "user"])
    assert r.stdout.strip() == "operator"
    r2 = _run_python_face(tmp_path, ["api", "user"], {"STUB_WHO": "alice"})
    assert r2.stdout.strip() == "alice"


def test_python_face_issue_comment_fail_flag(tmp_path):
    r = _run_python_face(tmp_path, ["issue", "comment", "7", "--body", "x"])
    assert r.returncode == 0
    r2 = _run_python_face(tmp_path, ["issue", "comment", "7", "--body", "x"], {"STUB_COMMENT_FAIL": "1"})
    assert r2.returncode == 1


def test_python_face_project_item_edit_fail_flag(tmp_path):
    r = _run_python_face(tmp_path, ["project", "item-edit", "--id", "X"])
    assert r.returncode == 0
    r2 = _run_python_face(tmp_path, ["project", "item-edit", "--id", "X"], {"STUB_EDIT_FAIL": "1"})
    assert r2.returncode == 1


def test_python_face_pr_list_tick_advances(tmp_path):
    states = json.dumps([{"pr_open": False}, {"pr_open": True}])
    counter = tmp_path / "counter"
    env = {"STUB_STATES": states, "STUB_COUNTER": str(counter), "STUB_ISSUE": "7"}
    r1 = _run_python_face(tmp_path, ["pr", "list"], env)
    assert json.loads(r1.stdout) == []
    r2 = _run_python_face(tmp_path, ["pr", "list"], env)
    prs = json.loads(r2.stdout)
    assert len(prs) == 1 and prs[0]["headRefName"] == "task/7-x"


def test_python_face_issue_view_prints_comments(tmp_path):
    r = _run_python_face(tmp_path, ["issue", "view", "7"], {"STUB_COMMENTS": json.dumps(["a", "b"])})
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"comments": ["a", "b"]}


def test_python_face_unhandled_call_exits_nonzero_no_output(tmp_path):
    r = _run_python_face(tmp_path, ["repo", "list"])
    assert r.returncode == 9
    assert r.stdout == ""


def test_python_face_logs_every_call_when_calls_log_set(tmp_path):
    log = tmp_path / "calls.log"
    _run_python_face(tmp_path, ["repo", "view"], {"STUB_CALLS_LOG": str(log)})
    _run_python_face(tmp_path, ["api", "user"], {"STUB_CALLS_LOG": str(log)})
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert lines == [["repo", "view"], ["api", "user"]]


# ====================================================================================================
# The consuming suites' scenarios still run end-to-end through the shared fake's faces (not just the
# lower-level unit checks above) — one representative run per tool family.
# ====================================================================================================

def test_dev_runner_happy_path_runs_end_to_end_through_the_shared_bash_face(tmp_path):
    work, _ = td._make_repo(tmp_path)
    binp = tmp_path / "bin"
    td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Migration smoke — gh bash face"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    tl = td._timeline(tmp_path)
    assert "IMPL" in tl and "TEST" in tl and "REVIEW" in tl


def test_autonomous_merge_scenario_runs_end_to_end_through_the_shared_bash_face(tmp_path):
    """test_autonomous_merge.py's own extended-`gh`-only behaviors (pr merge/list, pr view --json
    mergeCommit) are now modes of the ONE shared GH_STUB — proven by driving an armed, shadow-complete,
    all-green PR to a squash-merge using that suite's own scenario helpers."""
    am = _import_sibling("test_autonomous_merge")
    work, origin = td._make_repo(tmp_path)
    binp = tmp_path / "bin"
    am._stubs(binp)
    env = am._armed_env(tmp_path, binp, work, origin, number=5, title="Migration smoke — merge",
                         prs=am._complete_prs())
    r = am._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout
    body = am._merge_record(tmp_path)
    assert body is not None, "no durable YR-MERGE record was written"
    assert body.splitlines()[0] == "YR-MERGE: MERGED"
    calls = (tmp_path / "gh_calls").read_text()
    assert "MERGE" in calls and "--squash" in calls


def test_board_scenario_runs_end_to_end_through_the_shared_python_face(tmp_path):
    tb = _import_sibling("test_board")
    nodes = [tb._node(7, repo="yr/alpha", itype="Task", status="In Progress", reason=None,
                       title="Migration smoke")]
    r = tb._run(tmp_path, nodes)
    assert r.returncode == 0, r.stderr
    rows = tb._rows(r.stdout)
    assert len(rows) == 1
    assert rows[0][0] == "7" and rows[0][1] == "yr/alpha"


def test_promote_scenario_runs_end_to_end_through_the_shared_python_face(tmp_path):
    tp = _import_sibling("test_promote")
    binp = tp._bin(tmp_path)
    r = tp._run(["7", "--repo", "test/repo"], tp._env(tmp_path, binp))
    assert r.returncode == 0, r.stderr
    calls = tp._calls(tmp_path)
    assert any(c[:2] == ["issue", "comment"] for c in calls)
    assert any(c[:2] == ["project", "item-edit"] for c in calls)


def test_watch_build_scenario_runs_end_to_end_through_the_shared_python_face(tmp_path):
    twb = _import_sibling("test_watch_build")
    binp = twb._bin(tmp_path)
    states = [{"status": "In Review", "pr_open": True}]
    r = twb._run(["7", "--repo", "test/repo", "--interval", "0", "--timeout", "10"],
                 twb._base_env(tmp_path, binp, states))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "https://example/pr/1"
