"""Acceptance tests for issue #312 — stage conduct table: a repo teaches every stage its own command
numbers (manifest key `stage_conduct`).

Derived from the issue's acceptance criteria (the spec), NOT the implementation's internals:

  1. `stage_conduct` (a TOML array of non-empty strings) is parsed through a typed emission
     discriminating absent / valid / invalid; a declared value that is not a non-empty array of
     non-empty strings bounces the task to Needs-info BEFORE any claim, naming the rejected value.
  2. When declared, the table is delivered to every `claude -p` stage APPENDED TO THE TASK PROMPT ON
     STDIN, under a one-line header naming the source manifest — never on argv (issue #121's channel
     contract).
  3. A declared line containing one of the four routed stub literals (tests/harness/contract.md:
     `TESTER`, `REVIEWER`, `tests FAIL`, `REQUESTED CHANGES`) bounces to Needs-info naming the
     offending line — enforced at parse time, not advisory.
  4. Absent key: stage prompts are byte-identical to today (pinned).
  5. `stage_conduct` is named on AGENTS.md's manifest-keys line and in pipeline.md's stage-conduct
     note, in the same PR.

Reuses the shared harness only (tests/test_dev_runner.py's stub set, fixtures, and helpers) — no
private clone of the classifier or the gh/claude stubs; the manifest-repo fixture shapes mirror
tests/test_test_surface_manifest.py's and tests/test_check_gate_timeout.py's precedent for the same
kind of typed-array/typed-scalar manifest key.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # shared stub harness (gh/claude/check stubs + fixtures)

ROOT = td.ROOT
HEADER = "Per-repo stage conduct (source: .yr/factory.toml, key stage_conduct):"


# ============ manifest helpers ============

def _conduct_manifest_repo(tmp, content, name="repo"):
    """A minimal, non-git repo dir carrying `.yr/factory.toml` — the runner's manifest read falls back
    to the working-tree file when `git show` yields nothing (no git repo at all), same fallback
    tests/test_test_surface_manifest.py's `_manifest_only_repo` and
    tests/test_check_gate_timeout.py's `_timeout_manifest_repo` rely on. check_cmd is prepended
    (required, issue #275) so a malformed stage_conduct value under test is the ONLY Needs-info reason
    these fixtures can produce."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    (repo / ".yr" / "factory.toml").write_text('check_cmd = "true"\n' + content)
    return repo


def _commit_conduct_manifest(work, content):
    """Commit+push a `.yr/factory.toml` declaring `stage_conduct` to origin/main — read by the
    runner's `git show origin/main:...` manifest lookup for a real (non-dry-run) run through the
    implement/test stages. check_cmd is prepended so the declared table is the only variable in play."""
    (work / ".yr" / "factory.toml").write_text('check_cmd = "true"\n' + content)
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "set stage_conduct"], work)
    td._git(["push", "-q", "origin", "main"], work)


def _assert_needs_info_fail_closed(tmp_path, manifest_toml, needle):
    """A malformed/rejected declared `stage_conduct` value bounces the run to Needs-info (fail closed,
    never a silent default) BEFORE any claim, and the block record names the key and the rejected
    value/offending line."""
    repo = _conduct_manifest_repo(tmp_path, manifest_toml)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=9, title="Malformed stage_conduct")
    env["BASE_REPO"] = str(repo)
    r = td._run(["9", "--repo", "test/repo"], env)
    assert r.returncode == 3, r.stdout + r.stderr
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                                          # never proceeds to any stage
    assert "NeedsInfo" in " ".join(td._edits(tl))
    comments = " ".join(td._comments(tl))
    assert "stage_conduct" in comments
    assert needle.lower() in comments.lower()
    return comments


def _argv_only_stage_calls(tmp):
    """Every recorded `claude` call's raw ARGV TEXT alone (no stdin folded in), grouped by stage —
    mirrors test_dev_runner.py's `_stage_calls`/`_stdin_stage_calls` pairing but keeps the argv channel
    isolated, needed to prove a value never travels there."""
    tl = [l for l in td._timeline(tmp) if l in ("IMPL", "TEST", "REPAIR", "REVIEW", "REVIEWFIX")]
    argv_calls = td._argv_raw_calls(tmp)
    assert len(tl) == len(argv_calls), (tl, len(argv_calls))
    out = {}
    for stage, call in zip(tl, argv_calls):
        out.setdefault(stage, []).append(call)
    return out


# ============ (1) typed emission: absent -> byte-identical stage prompts, pinned ============

def test_absent_key_stage_prompts_byte_identical_to_today(tmp_path):
    """No `stage_conduct` key declared (the seeded manifest from `_make_repo` carries only check_cmd)
    -> the IMPL/TEST stdin task prompt is exactly issue #121's pinned shape (role instruction + SPEC),
    with no conduct block appended at all."""
    binp = tmp_path / "bin"; td._stubs(binp)
    work, _ = td._make_repo(tmp_path)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="No conduct table declared"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    spec = "GitHub issue #5: No conduct table declared\n\n### Acceptance criteria\n- [ ] it works"
    expected = {
        "IMPL": f"Implement the task below against its acceptance criteria. Make the minimal, clean change.\n\n{spec}",
        "TEST": f"Write tests that verify the acceptance criteria below.\n\n{spec}",
    }
    stdin_calls = td._stdin_stage_calls(tmp_path)
    for stage, text in expected.items():
        assert stdin_calls[stage][0] == text, \
            f"stage {stage}: stdin task prompt changed even though stage_conduct is absent"
        assert "Per-repo stage conduct" not in stdin_calls[stage][0]


def test_absent_key_produces_no_header_anywhere_in_the_run(tmp_path):
    """Belt-and-braces: with no declared key, the header text never appears on ANY channel (argv or
    stdin) of ANY stage across a full run."""
    binp = tmp_path / "bin"; td._stubs(binp)
    work, _ = td._make_repo(tmp_path)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="No header without declaration"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    by_stage = td._stage_calls(tmp_path)
    assert by_stage, "expected at least one recorded claude call"
    for stage, calls in by_stage.items():
        for call in calls:
            assert "Per-repo stage conduct" not in call, f"stage {stage} unexpectedly carries a conduct header"


# ============ (2) typed emission: valid -> delivered on stdin, under a header, every stage ============

def test_declared_table_lands_on_stdin_of_every_stage_under_header(tmp_path):
    """A declared stage_conduct table is appended to the TASK PROMPT, delivered on STDIN, under a
    one-line header naming the source manifest — for both the implementer and the tester stage (the
    two `claude -p` stages a plain green run exercises)."""
    work, _ = td._make_repo(tmp_path)
    _commit_conduct_manifest(
        work,
        'stage_conduct = ["check_cmd usually finishes within 45s", "lint_cmd runs in under 10s"]\n',
    )
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Declared stage_conduct"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    expected_block = HEADER + "\ncheck_cmd usually finishes within 45s\nlint_cmd runs in under 10s"
    stdin_calls = td._stdin_stage_calls(tmp_path)
    for stage in ("IMPL", "TEST"):
        assert stage in stdin_calls, f"{stage} stage never ran"
        text = stdin_calls[stage][0]
        assert expected_block in text, f"stage {stage}: conduct block missing/malformed on stdin"
        # appended AFTER the task's own SPEC (acceptance criteria), not prepended or interleaved
        assert text.index(expected_block) > text.index("Acceptance criteria")


def test_declared_table_never_reaches_argv_or_the_system_prompt(tmp_path):
    """The declared table must never travel on argv or inside `--append-system-prompt` — issue #121's
    channel contract exists precisely so repo-authored text naming commands can't pattern-match a
    stage's own command line. Checked on the SAME run that proves it lands on stdin."""
    work, _ = td._make_repo(tmp_path)
    _commit_conduct_manifest(work, 'stage_conduct = ["a self-hitting command like: pkill -f myproc"]\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Never on argv"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    # sanity: it DID land on stdin (else the argv-absence assertion below would be vacuous)
    stdin_calls = td._stdin_stage_calls(tmp_path)
    for stage in ("IMPL", "TEST"):
        assert "a self-hitting command like: pkill -f myproc" in stdin_calls[stage][0]

    argv_only = _argv_only_stage_calls(tmp_path)
    for stage in ("IMPL", "TEST"):
        for call in argv_only[stage]:
            assert "a self-hitting command like: pkill -f myproc" not in call
            assert HEADER not in call
            prompt = td._extract_append_system_prompt(call)
            assert "a self-hitting command like: pkill -f myproc" not in prompt
            assert HEADER not in prompt


def test_single_line_table_still_gets_the_header(tmp_path):
    """A one-element table still gets the full header + its one line — the header isn't conditioned on
    a multi-line table."""
    work, _ = td._make_repo(tmp_path)
    _commit_conduct_manifest(work, 'stage_conduct = ["build takes about 90s cold, 20s warm"]\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Single line table"), work)
    env["STUB_CLAUDE_CHANGE"] = "1"
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr

    expected_block = HEADER + "\nbuild takes about 90s cold, 20s warm"
    stdin_calls = td._stdin_stage_calls(tmp_path)
    assert expected_block in stdin_calls["IMPL"][0]
    assert expected_block in stdin_calls["TEST"][0]


# ============ (3) parse-time content screening: a routed stub literal bounces Needs-info ============

def test_stub_literal_tester_bounces_needs_info_naming_the_line(tmp_path):
    comments = _assert_needs_info_fail_closed(
        tmp_path, 'stage_conduct = ["ask the TESTER to double-check timing"]\n',
        "ask the TESTER to double-check timing",
    )
    assert "routed stub literal" in comments.lower()


def test_stub_literal_reviewer_bounces_needs_info_naming_the_line(tmp_path):
    comments = _assert_needs_info_fail_closed(
        tmp_path, 'stage_conduct = ["the REVIEWER should allow 30s"]\n',
        "the REVIEWER should allow 30s",
    )
    assert "routed stub literal" in comments.lower()


def test_stub_literal_tests_fail_bounces_needs_info_naming_the_line(tmp_path):
    comments = _assert_needs_info_fail_closed(
        tmp_path, 'stage_conduct = ["retry once if tests FAIL under load"]\n',
        "retry once if tests FAIL under load",
    )
    assert "routed stub literal" in comments.lower()


def test_stub_literal_requested_changes_bounces_needs_info_naming_the_line(tmp_path):
    comments = _assert_needs_info_fail_closed(
        tmp_path, 'stage_conduct = ["allow extra time for REQUESTED CHANGES"]\n',
        "allow extra time for REQUESTED CHANGES",
    )
    assert "routed stub literal" in comments.lower()


def test_stub_literal_bounce_only_flags_the_offending_line_not_a_clean_sibling(tmp_path):
    """When the array has more than one line and only one contains a routed literal, the bounce still
    fires (fail-closed on the whole declaration) and names the actual offending line, not a clean one."""
    comments = _assert_needs_info_fail_closed(
        tmp_path,
        'stage_conduct = ["check_cmd takes 45s", "the REVIEWER should allow 30s"]\n',
        "the REVIEWER should allow 30s",
    )
    assert "the REVIEWER should allow 30s" in comments


# ============ (1, continued) typed emission: malformed shapes fail closed, naming the rejected value ==

def test_scalar_string_is_rejected(tmp_path):
    """Not an array at all (a bare TOML string) — rejected, naming the declared value."""
    _assert_needs_info_fail_closed(
        tmp_path, 'stage_conduct = "check_cmd takes 45s"\n', "check_cmd takes 45s",
    )


def test_empty_array_is_rejected(tmp_path):
    """An empty array is declared-but-empty, not absent — must still bounce, never silently treated as
    absent (which would carry no conduct table at all with no record of why)."""
    _assert_needs_info_fail_closed(tmp_path, "stage_conduct = []\n", "[]")


def test_non_string_element_is_rejected(tmp_path):
    """An array of non-strings (e.g. integers) is rejected — every element must be a string."""
    _assert_needs_info_fail_closed(tmp_path, "stage_conduct = [1, 2]\n", "[1, 2]")


def test_empty_string_element_is_rejected(tmp_path):
    """An empty-string element inside an otherwise well-formed array is rejected too — every element
    must be NON-empty."""
    _assert_needs_info_fail_closed(tmp_path, 'stage_conduct = [""]\n', "['']")


def test_mixed_type_array_is_rejected(tmp_path):
    """An array mixing strings and a non-string element is rejected — the whole declaration fails
    closed, not just the offending element silently dropped."""
    _assert_needs_info_fail_closed(
        tmp_path, 'stage_conduct = ["check_cmd takes 45s", 7]\n', "check_cmd takes 45s",
    )


def test_malformed_value_never_silently_falls_back_to_absent(tmp_path):
    """A malformed declared value never silently falls back to "absent" (no conduct table, run
    proceeds unannounced) — the run stops at Needs-info, unconditionally, before any stage runs, and no
    worktree is ever created."""
    repo = _conduct_manifest_repo(tmp_path, 'stage_conduct = "not an array"\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=9, title="No silent fallback")
    env["BASE_REPO"] = str(repo)
    r = td._run(["9", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl) and "CHECK" not in tl
    assert "https://stub/pr/1" not in r.stdout


def test_malformed_bounce_names_the_governing_rule(tmp_path):
    """The refusal names the rule (a non-empty TOML array of non-empty strings), not just the bare
    rejected value, so recovery is derivable from the message alone."""
    comments = _assert_needs_info_fail_closed(tmp_path, "stage_conduct = []\n", "[]")
    assert "non-empty" in comments.lower()
    assert "array" in comments.lower()
    assert "string" in comments.lower()


# ============ (5) docs: AGENTS.md + pipeline.md name stage_conduct, in the same PR ============

def test_agents_md_names_stage_conduct_on_the_manifest_keys_line():
    text = (ROOT / "AGENTS.md").read_text()
    idx = text.index("`.yr/factory.toml` sets")
    para = text[idx: idx + 4000]
    assert "check_cmd" in para and "auto_merge" in para        # the same bullet as the other manifest keys
    assert "stage_conduct" in para
    assert "issue #312" in para or "#312" in para
    assert "stdin" in para.lower()
    assert "argv" in para.lower()
    assert "Needs-info" in para


def test_pipeline_md_documents_the_stage_conduct_manifest_key():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text()
    idx = text.index("manifest key `stage_conduct`")
    nearby = text[max(0, idx - 500): idx + 1200]
    assert "stage_conduct" in nearby
    assert "task prompt" in nearby.lower()
    assert "stdin" in nearby.lower()
    assert "argv" in nearby.lower()
    assert "Needs-info" in nearby


def test_pipeline_md_stage_conduct_note_names_the_four_routed_literals():
    text = (ROOT / "skills" / "factory" / "references" / "pipeline.md").read_text()
    idx = text.index("manifest key `stage_conduct`")
    nearby = text[max(0, idx - 200): idx + 1500]
    for literal in ("TESTER", "REVIEWER", "tests FAIL", "REQUESTED CHANGES"):
        assert literal in nearby, f"pipeline.md stage_conduct note missing routed literal {literal!r}"
