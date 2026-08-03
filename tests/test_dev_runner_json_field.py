"""Acceptance tests for issue #384 — the runner's issue-field extraction uses its own `_json_field`
helper, rather than four fresh ad-hoc `python3 -c` one-liners at the issue-fetch site.

Derived from the issue's acceptance criteria (the spec), NOT the implementation's internals:

  1. The four issue-field extracts that follow the issue fetch (TITLE, BODY, STATE, ITYPE) resolve
     through `_json_field`.
  2. `_json_field` gains an optional second key resolving one level of nesting; its single-argument
     behaviour is byte-identical to today's (booleans as true/false, a missing key as "").
  3. The nested read yields "" when the intermediate value is absent (null) or is not an object.
  4. The Type gate that consumes the Issue Type name behaves identically end-to-end: a typed issue
     resolves its type name, an untyped issue resolves "".
  5. The wall-11 guard: a test fails when an ad-hoc JSON-extract one-liner reappears at the issue-fetch
     site, targeting the JSON-extract SHAPE rather than the `python3 -c` interpreter call, and never
     hardcoding a count of today's remaining call sites.

Reuses the shared harness only (tests/test_dev_runner.py's stub set, fixtures, and helpers) for the
end-to-end Type-gate cases — no private clone of the gh/claude stubs.

Runs under `.venv/bin/python -m pytest tests/ -q` (attended) / `pytest tests/ -q` (build worktree).
"""
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # shared stub harness (gh/claude/check stubs + fixtures)

ROOT = td.ROOT
RUNNER = td.RUNNER


# ============ extracting & driving the real `_json_field` (never a reimplementation) ============

_FUNC_RE = re.compile(r"\n_json_field\(\)\{.*?\n\}\n", re.S)


def _json_field_source():
    """The live `_json_field` function body, sliced straight out of tools/dev-runner.sh — tests drive
    the real function text, never a hand-copied reimplementation that could drift from it."""
    text = RUNNER.read_text()
    m = _FUNC_RE.search(text)
    assert m, "_json_field() definition not found in tools/dev-runner.sh"
    return m.group(0)


def _json_field(json_text, key, nested=None):
    """Calls the extracted `_json_field` in a fresh bash process. When `nested` is None, the THIRD
    positional argument is omitted entirely from the invocation (not passed as ""), so the
    single-argument call shape is exercised exactly as every existing call site in the file uses it."""
    script = _json_field_source() + '\n_json_field "$@"\n'
    argv = ["bash", "-c", script, "_json_field_test", json_text, key]
    if nested is not None:
        argv.append(nested)
    r = subprocess.run(argv, capture_output=True, text=True)
    assert r.returncode == 0, f"_json_field crashed: {r.stderr}"
    return r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout


# ============ single-argument behaviour (byte-identical to today's) ============

def test_single_key_string_value():
    assert _json_field('{"title": "Do a thing"}', "title") == "Do a thing"


def test_single_key_missing_is_empty_string():
    assert _json_field('{"title": "x"}', "state") == ""


def test_single_key_bool_true_renders_lowercase_true():
    assert _json_field('{"flag": true}', "flag") == "true"


def test_single_key_bool_false_renders_lowercase_false():
    assert _json_field('{"flag": false}', "flag") == "false"


def test_single_key_null_value_is_empty_string():
    assert _json_field('{"body": null}', "body") == ""


# ============ the new optional nested key ============

def test_nested_key_present_resolves_one_level_down():
    assert _json_field('{"issueType": {"name": "Task"}}', "issueType", "name") == "Task"


def test_nested_key_present_bug_type():
    assert _json_field('{"issueType": {"name": "Bug"}}', "issueType", "name") == "Bug"


def test_nested_intermediate_null_yields_empty_string():
    """issueType: null (the untyped-issue shape `gh issue view` actually returns) must resolve to ""
    for the nested read — the exact fail direction the old site's own `isinstance(t, dict)` guard
    produced before this migration."""
    assert _json_field('{"issueType": null}', "issueType", "name") == ""


def test_nested_intermediate_absent_key_yields_empty_string():
    assert _json_field('{}', "issueType", "name") == ""


def test_nested_intermediate_non_object_yields_empty_string():
    """A non-dict intermediate (e.g. a string) must never be treated as a container — no AttributeError,
    no stray repr in the output, just the empty string."""
    assert _json_field('{"issueType": "oops"}', "issueType", "name") == ""


def test_nested_intermediate_object_missing_inner_key_yields_empty_string():
    assert _json_field('{"issueType": {}}', "issueType", "name") == ""


def test_nested_intermediate_list_yields_empty_string():
    assert _json_field('{"issueType": [1, 2]}', "issueType", "name") == ""


def test_nested_key_empty_string_behaves_as_no_nesting_requested():
    """An explicit empty-string third argument (as opposed to omitting it) must not be mistaken for a
    real nesting key — `${3:-}` and the empty-string falsy check both collapse it to "no nesting"."""
    assert _json_field('{"title": "x"}', "title", "") == "x"


def test_nested_call_on_boolean_top_level_value_still_renders_correctly():
    """Nesting is opt-in per call: a plain boolean top-level field, read with no nested key, still
    renders as today (true/false), proving the new optional parameter didn't disturb the existing
    single-key path for a non-string value type."""
    assert _json_field('{"flag": true}', "flag", None) == "true"


# ============ the Type gate end-to-end (a wrong migration breaks this silently) ============

def test_typed_task_issue_clears_the_type_gate(tmp_path):
    """A Task-typed Ready issue resolves its Issue Type name through the (now shared) extraction and
    clears the default REQUIRE_ISSUE_TYPE=Task gate, reported read-only via --dry-run."""
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, issue_type="Task")
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    r = td._run(["7", "--repo", "test/repo", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ready"] is True


def test_typed_non_matching_issue_is_refused_at_the_gate(tmp_path):
    """A Feature-typed issue must still resolve its type name (not corrupt into a dict repr or empty
    string) so the Type gate can compare it against REQUIRE_ISSUE_TYPE and refuse it by name."""
    binp = tmp_path / "bin"; td._stubs(binp)
    r = td._run(["7", "--repo", "test/repo"], td._env(tmp_path, binp, issue_type="Feature"))
    assert r.returncode == 3
    assert "feature" in r.stderr.lower()
    tl = td._timeline(tmp_path)
    assert not td._ran(tl) and not td._edits(tl) and not td._comments(tl)


def test_untyped_issue_resolves_empty_string_and_bounces_to_needs_info(tmp_path):
    """An untyped issue (issueType: null in the real `gh` shape) must resolve ITYPE to "" — exactly what
    a broken nested read (e.g. a dict repr, or a crash) would NOT produce — driving the existing
    Needs-info bounce rather than a bare gate refusal."""
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, issue_type=None)
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    r = td._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)
    edit = " ".join(td._edits(tl))
    assert "Backlog" in edit and "NeedsInfo" in edit


# ============================================================================
# The wall-11 guard: a tombstone over the issue-fetch block (issue #384) — it FAILS if an ad-hoc
# JSON-extract one-liner reappears there. It targets the single-line JSON-extract SHAPE
# (`json.load(sys.stdin).get(`), never the `python3 -c` interpreter call (which appears dozens of times
# in this file for unrelated multi-line programs, so capping IT would be the wrong surface), and it
# never hardcodes a count of today's remaining call sites elsewhere in the file.
# ============================================================================

_FETCH_ISSUE_BLOCK_RE = re.compile(r"\n# ---- fetch issue.*?(?=\n# ---- )", re.S)
_ONE_LINER_SHAPE_RE = re.compile(r"json\.load\(sys\.stdin\)\.get\(")


def _fetch_issue_block():
    text = RUNNER.read_text()
    m = _FETCH_ISSUE_BLOCK_RE.search(text)
    assert m, "could not locate the '# ---- fetch issue' section in tools/dev-runner.sh"
    return m.group(0)


def test_wall_11_no_ad_hoc_json_one_liner_in_the_issue_fetch_block():
    block = _fetch_issue_block()
    hits = _ONE_LINER_SHAPE_RE.findall(block)
    assert not hits, (
        "an ad-hoc JSON-extract one-liner (the `json.load(sys.stdin).get(` shape) reappeared in the "
        "'# ---- fetch issue' block of tools/dev-runner.sh — every issue-field extract there must "
        "resolve through _json_field instead"
    )


def test_wall_11_issue_fetch_block_still_routes_every_field_through_json_field():
    """Guards the guard above: the no-one-liner assertion can't vacuously pass just because the block
    was gutted, renamed, or the fields moved somewhere this test can't see — each of TITLE/BODY/STATE/
    ITYPE must still be visibly assigned via `_json_field` inside the named block."""
    block = _fetch_issue_block()
    for var in ("TITLE", "BODY", "STATE", "ITYPE"):
        assert re.search(rf'{var}="\$\(_json_field ', block), (
            f"{var} is not assigned via _json_field in the '# ---- fetch issue' block"
        )


def test_wall_11_itype_nests_through_issue_type_name():
    """The one field of the four that isn't a top-level string: ITYPE must route through _json_field's
    nested-key argument against issueType/name, not a bare top-level `_json_field ... issueType` (which
    would print a Python dict repr into the shell variable and silently corrupt the Type gate)."""
    block = _fetch_issue_block()
    assert re.search(r'ITYPE="\$\(_json_field "\$ISSUE_JSON" issueType name\)"', block), (
        "ITYPE is not extracted via _json_field's nested key against issueType/name"
    )
