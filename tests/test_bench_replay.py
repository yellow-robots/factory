"""Acceptance tests for tools/bench_replay.py -- the sealed-checkout replay harness + deterministic
grading, no LLM (slice B, issue #163) plus the live candidate replay driver through the same cold-stage
seam (slice C, issue #164) -- both slices of epic yellow-robots/factory#161.

Real git, no network: `source_repo` fixtures are ordinary local repos built with plain `git` calls (never
bench_replay's own plumbing) so sealing is exercised against the real thing, not a mock of it. Tests are
derived from the acceptance criteria (the spec) -- the three seal properties, the invalid-seal /
ungraded-environmental / pass / fail outcome grammar, and the run-scoped TMPDIR discipline -- never from
bench_replay.py's own internals. `seal_workdir` and `verify_seal` are exercised directly only where the
spec itself names them as the three verified properties; everything else goes through the public `grade()`
entry point.

The slice C tests exercise `run_candidate()` against a stubbed `claude` CLI (a tiny executable script,
never the real network-calling binary) so the driver's contract with the cold-stage seam is checked
without ever making a live model call: the exact argv/stdin shape, the usage-envelope -> result-row
arithmetic, the quota/other-failure -> ungraded-environmental classification, and that nothing lands
outside the sealed workdir and bench/results/. Where the spec pins the charter/prompt shape to
tools/dev-runner.sh by name, the expected literals are read out of dev-runner.sh itself (never
retyped) so the tests fail if bench_replay.py's copy ever drifts from the real implement stage.
"""
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bench_replay  # noqa: E402
import stage_usage  # noqa: E402

NOW = "2026-07-13T00:00:00Z"


def _now():
    return NOW


# --- fixture builders: real git repos, real commits, no bench_replay involved ---------------------------
def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _rev_parse(repo, ref="HEAD"):
    return subprocess.run(["git", "rev-parse", ref], cwd=str(repo),
                           capture_output=True, text=True, check=True).stdout.strip()


TEST_ADD_CONTENT = (
    "import sys\n"
    "sys.path.insert(0, \".\")\n"
    "import mathutils\n\n"
    "assert mathutils.add(2, 3) == 5, \"add() did not return the expected sum\"\n"
    "print(\"OK\")\n"
)


def _make_source_repo(tmp_path, name="source"):
    """A tiny local repo with two commits: PRE (the pre-solution ref -- a buggy `add()` stub, no
    `tests/` directory at all) and its child MERGE (the "source merge commit" -- the correct
    implementation plus the held-out test). Stands in for a real corpus record's `source_repo`: an
    ordinary, already-provisioned local clone the harness must never touch. Returns
    `(repo, record, candidate_patch, pre_sha, merge_sha)`."""
    repo = tmp_path / name
    repo.mkdir()
    _git(["init", "-q", "-b", "main", "."], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "tester"], repo)

    (repo / ".yr").mkdir()
    (repo / ".yr" / "factory.toml").write_text('check_cmd = "python3 tests/test_add.py"\n')
    (repo / "mathutils.py").write_text("def add(a, b):\n    return None\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "pre-solution"], repo)
    pre_sha = _rev_parse(repo)

    (repo / "mathutils.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_add.py").write_text(TEST_ADD_CONTENT)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "solution"], repo)
    merge_sha = _rev_parse(repo)

    diff = subprocess.run(["git", "diff", pre_sha, merge_sha, "--", "mathutils.py"],
                           cwd=str(repo), capture_output=True, text=True, check=True).stdout

    record = {
        "schema": "yr-bench-corpus/1",
        "repo": "yellow-robots/widget",
        "issue": 999,
        "pr": 1,
        "prompt": {"body": "implement add()", "read_at": NOW},
        "pre_solution_ref": pre_sha,
        "held_out_tests": [{"path": "tests/test_add.py", "content": TEST_ADD_CONTENT}],
        "extracted_at": NOW,
    }
    return repo, record, diff, pre_sha, merge_sha


def _minimal_repo(tmp_path, name, manifest_text=""):
    """A one-commit repo with only a `.yr/factory.toml` (`manifest_text`, possibly key-less) and no
    held-out tests -- for exercising provisioning/environmental outcomes that don't need the add()
    scenario at all."""
    repo = tmp_path / name
    repo.mkdir()
    _git(["init", "-q", "-b", "main", "."], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "tester"], repo)
    if manifest_text is not None:
        (repo / ".yr").mkdir()
        (repo / ".yr" / "factory.toml").write_text(manifest_text)
    (repo / "README.md").write_text("seed\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "seed"], repo)
    sha = _rev_parse(repo)
    record = {
        "schema": "yr-bench-corpus/1", "repo": "yellow-robots/widget", "issue": 1, "pr": 1,
        "prompt": {"body": "x", "read_at": NOW}, "pre_solution_ref": sha,
        "held_out_tests": [], "extracted_at": NOW,
    }
    return repo, record, sha


# ============================================================================
# A fresh seal satisfies all three properties (AC: sealed workdir at the pre-solution ref)
# ============================================================================

def test_fresh_seal_has_no_remote_no_beyond_object_no_credential(tmp_path):
    source_repo, record, _diff, pre_sha, merge_sha = _make_source_repo(tmp_path)
    workdir = tmp_path / "sealed"

    bench_replay.seal_workdir(record, workdir, source_repo)

    remotes = subprocess.run(["git", "remote"], cwd=str(workdir),
                              capture_output=True, text=True, check=True).stdout.strip()
    assert remotes == ""

    revs = subprocess.run(["git", "rev-list", "HEAD"], cwd=str(workdir),
                           capture_output=True, text=True, check=True).stdout.split()
    assert revs == [pre_sha]

    cat = subprocess.run(["git", "cat-file", "-e", merge_sha], cwd=str(workdir),
                          capture_output=True, text=True)
    assert cat.returncode != 0, "the source merge commit's object must never be reachable in the seal"

    clean_env = {"PATH": os.environ.get("PATH", "")}
    verdict = bench_replay.verify_seal(workdir, pre_sha, clean_env, source_repo=source_repo)
    assert verdict.ok, verdict.reasons


# ============================================================================
# Seal-failure paths -- each records invalid-seal and never grades
# ============================================================================

def test_configured_remote_yields_invalid_seal_and_never_grades(tmp_path):
    source_repo, record, diff, pre_sha, _merge_sha = _make_source_repo(tmp_path)
    workdir = tmp_path / "sealed"
    bench_replay.seal_workdir(record, workdir, source_repo)
    _git(["remote", "add", "origin", str(source_repo)], workdir)

    bash_calls = []
    def spy_run(argv, cwd=None, env=None, input=None):
        if argv[:2] == ["bash", "-c"]:
            bash_calls.append(argv)
        return bench_replay._run(argv, cwd=cwd, env=env, input=input)

    result = bench_replay.grade(record, source_repo=source_repo, workdir=workdir,
                                 candidate_patch=diff, run=spy_run, now=_now)

    assert result["outcome"] == "invalid-seal"
    assert "remote" in result["detail"]
    assert result["check_cmd"] is None and result["check_rc"] is None
    assert bash_calls == []  # the check command was never invoked


def test_source_merge_commit_object_reachable_yields_invalid_seal_and_never_grades(tmp_path):
    source_repo, record, diff, pre_sha, merge_sha = _make_source_repo(tmp_path)
    workdir = tmp_path / "sealed"
    bench_replay.seal_workdir(record, workdir, source_repo)
    # simulate a broken seal: the merge commit's own object leaked into the workdir's object store
    _git(["fetch", "-q", "--depth", "1", str(source_repo), merge_sha], workdir)

    result = bench_replay.grade(record, source_repo=source_repo, workdir=workdir,
                                 candidate_patch=diff, now=_now)

    assert result["outcome"] == "invalid-seal"
    assert merge_sha in result["detail"]
    assert result["check_cmd"] is None and result["check_rc"] is None


def test_credential_present_in_env_fails_verify_seal_directly(tmp_path):
    """`verify_seal` is one of the three explicitly-named verified properties -- unit-tested directly
    against a poisoned env, independent of how `grade()` assembles its own child env."""
    source_repo, record, _diff, pre_sha, _merge_sha = _make_source_repo(tmp_path)
    workdir = tmp_path / "sealed"
    bench_replay.seal_workdir(record, workdir, source_repo)

    poisoned_env = {"PATH": os.environ.get("PATH", ""), "GH_TOKEN": "super-secret-token"}
    verdict = bench_replay.verify_seal(workdir, pre_sha, poisoned_env, source_repo=source_repo)

    assert not verdict.ok
    assert any("credential" in reason.lower() for reason in verdict.reasons)


def test_leaked_credential_yields_invalid_seal_end_to_end_and_never_grades(tmp_path, monkeypatch):
    """End-to-end: if the child env `grade()` builds ever carried a GitHub credential, the pipeline
    must catch it before running the check and record invalid-seal, never a graded outcome."""
    source_repo, record, diff, pre_sha, _merge_sha = _make_source_repo(tmp_path)
    real_sealed_env = bench_replay._sealed_env

    def leaking_sealed_env(source_repo_, tmpdir):
        env = real_sealed_env(source_repo_, tmpdir)
        env["GH_TOKEN"] = "leaked-token"
        return env

    monkeypatch.setattr(bench_replay, "_sealed_env", leaking_sealed_env)

    result = bench_replay.grade(record, source_repo=source_repo, candidate_patch=diff, now=_now)

    assert result["outcome"] == "invalid-seal"
    assert result["check_cmd"] is None and result["check_rc"] is None


# ============================================================================
# Grading: pass / fail, output preserved verbatim, held-out tests from the record only
# ============================================================================

def test_correct_candidate_patch_grades_pass(tmp_path):
    source_repo, record, diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)

    result = bench_replay.grade(record, source_repo=source_repo, candidate_patch=diff, now=_now)

    assert result["schema"] == "yr-bench-result/1"
    assert result["outcome"] == "pass"
    assert result["check_rc"] == 0
    assert result["check_cmd"] == "python3 tests/test_add.py"
    assert result["repo"] == record["repo"] and result["issue"] == 999 and result["pr"] == 1
    assert result["graded_at"] == NOW


def test_missing_candidate_patch_grades_fail_with_output_preserved_verbatim(tmp_path):
    """The stub candidate this slice ships (no-op) leaves the pre-solution bug in place -- the check
    must fail, and the failing output (the assertion message) must survive verbatim in the record."""
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)

    result = bench_replay.grade(record, source_repo=source_repo, candidate_patch=None, now=_now)

    assert result["outcome"] == "fail"
    assert result["check_rc"] not in (0, None)
    assert "AssertionError" in result["output"]
    assert "add() did not return the expected sum" in result["output"]


def test_held_out_tests_are_written_from_the_record_not_from_git(tmp_path):
    """Even with the correct fix applied, a record whose held-out test content differs from the one
    that landed in git must grade against the RECORD's content -- the sealed workdir cannot reach git's
    copy anyway, but this proves the harness never tries."""
    source_repo, record, diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    poisoned_test = (
        "import sys\nsys.path.insert(0, \".\")\nimport mathutils\n\n"
        "assert mathutils.add(2, 3) == 999, \"record-supplied test, not git's\"\n"
    )
    record = {**record, "held_out_tests": [{"path": "tests/test_add.py", "content": poisoned_test}]}

    result = bench_replay.grade(record, source_repo=source_repo, candidate_patch=diff, now=_now)

    assert result["outcome"] == "fail"
    assert "record-supplied test, not git's" in result["output"]


def test_check_rc_is_captured_directly_not_masked_by_a_pipe(tmp_path):
    repo, record, _sha = _minimal_repo(tmp_path, "rc5", manifest_text='check_cmd = "exit 5"\n')

    result = bench_replay.grade(record, source_repo=repo, now=_now)

    assert result["outcome"] == "fail"
    assert result["check_rc"] == 5


# ============================================================================
# Setup / provisioning / seal failures -- ungraded-environmental, never a graded fail
# ============================================================================

def test_missing_manifest_at_pre_solution_ref_is_ungraded_environmental(tmp_path):
    repo, record, _sha = _minimal_repo(tmp_path, "nomanifest", manifest_text=None)

    result = bench_replay.grade(record, source_repo=repo, now=_now)

    assert result["outcome"] == "ungraded-environmental"
    assert result["check_cmd"] is None and result["check_rc"] is None


def test_missing_check_cmd_key_is_ungraded_environmental(tmp_path):
    repo, record, _sha = _minimal_repo(tmp_path, "nocheckcmd", manifest_text='model = "sonnet"\n')

    result = bench_replay.grade(record, source_repo=repo, now=_now)

    assert result["outcome"] == "ungraded-environmental"
    assert result["check_cmd"] is None and result["check_rc"] is None


def test_unapplyable_candidate_patch_is_ungraded_environmental(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)

    result = bench_replay.grade(record, source_repo=source_repo,
                                 candidate_patch="this is not a valid unified diff\n", now=_now)

    assert result["outcome"] == "ungraded-environmental"
    assert result["check_cmd"] is None and result["check_rc"] is None
    assert "patch" in result["detail"].lower()


def test_missing_check_toolchain_binary_is_ungraded_environmental_not_a_graded_fail(tmp_path):
    repo, record, _sha = _minimal_repo(
        tmp_path, "missingbinary",
        manifest_text='check_cmd = "definitely-not-a-real-binary-xyz-123"\n',
    )

    result = bench_replay.grade(record, source_repo=repo, now=_now)

    assert result["outcome"] == "ungraded-environmental"
    assert result["check_rc"] == 127


def test_seal_git_failure_is_ungraded_environmental_not_invalid_seal(tmp_path):
    """A ref that doesn't exist in `source_repo` makes sealing itself fail outright -- that's an
    environmental problem, distinct from a seal that succeeded but failed verification."""
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    bad_record = {**record, "pre_solution_ref": "0" * 40}

    result = bench_replay.grade(bad_record, source_repo=source_repo, now=_now)

    assert result["outcome"] == "ungraded-environmental"
    assert result["check_cmd"] is None and result["check_rc"] is None


def test_nonexistent_source_repo_is_ungraded_environmental(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    bogus_source = tmp_path / "does-not-exist"

    result = bench_replay.grade(record, source_repo=bogus_source, now=_now)

    assert result["outcome"] == "ungraded-environmental"


# ============================================================================
# Run-scoped TMPDIR (#142 discipline) -- removed at teardown
# ============================================================================

def test_run_scoped_tmpdir_is_removed_at_teardown(tmp_path):
    source_repo, record, diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    captured = {}

    def spy_run(argv, cwd=None, env=None, input=None):
        if argv[:2] == ["bash", "-c"]:
            captured["tmpdir"] = env.get("TMPDIR")
        return bench_replay._run(argv, cwd=cwd, env=env, input=input)

    result = bench_replay.grade(record, source_repo=source_repo, candidate_patch=diff,
                                 run=spy_run, now=_now)

    assert result["outcome"] == "pass"
    assert captured.get("tmpdir"), "the check subprocess must run under an exported TMPDIR"
    tmpdir_path = pathlib.Path(captured["tmpdir"])
    assert not tmpdir_path.exists(), "the run-scoped TMPDIR must be removed at teardown"
    assert not tmpdir_path.parent.exists(), "the whole run-scoped root must be removed at teardown"


def test_tmpdir_is_fresh_per_run(tmp_path):
    source_repo, record, diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    seen = []

    def spy_run(argv, cwd=None, env=None, input=None):
        if argv[:2] == ["bash", "-c"]:
            seen.append(env.get("TMPDIR"))
        return bench_replay._run(argv, cwd=cwd, env=env, input=input)

    bench_replay.grade(record, source_repo=source_repo, candidate_patch=diff, run=spy_run, now=_now)
    bench_replay.grade(record, source_repo=source_repo, candidate_patch=diff, run=spy_run, now=_now)

    assert len(seen) == 2
    assert seen[0] != seen[1]


# ============================================================================
# CLI shape (stdlib JSON CLI, tools/registry.py's shape)
# ============================================================================

def test_cli_grade_end_to_end_prints_result_and_appends_to_out_file(tmp_path, capsys):
    source_repo, record, diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record))
    patch_path = tmp_path / "candidate.patch"
    patch_path.write_text(diff)
    out_path = tmp_path / "results.jsonl"

    rc = bench_replay.main(["grade", "--record", str(record_path), "--source", str(source_repo),
                             "--patch", str(patch_path), "--out", str(out_path)])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["outcome"] == "pass"
    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == printed


def test_cli_requires_record_and_source_arguments():
    with pytest.raises(SystemExit):
        bench_replay.main(["grade"])


# ============================================================================
# The candidate replay driver (slice C, issue #164) -- claude -p through the same cold-stage seam
# ============================================================================

def _extract_dev_runner_literal(pattern):
    """One named literal out of tools/dev-runner.sh's own source, so the expected value in these tests
    is read from the real implement stage rather than retyped -- a drift between the two shows up as a
    test failure, not a silent divergence."""
    text = (ROOT / "tools" / "dev-runner.sh").read_text()
    m = re.search(pattern, text)
    assert m, f"could not find pattern {pattern!r} in tools/dev-runner.sh"
    return m.group(1)


DEV_RUNNER_STAGE_CHARTER = _extract_dev_runner_literal(r'STAGE_CHARTER="(.*)"\n')
DEV_RUNNER_IMPL_SYS = _extract_dev_runner_literal(r'IMPL_SYS="(.*)"\n')
DEV_RUNNER_TASK_PREFIX = _extract_dev_runner_literal(
    r"printf '(Implement the task below against its acceptance criteria\. Make the minimal, clean change\.\\n\\n)%s'"
).replace("\\n", "\n")


def _write_claude_stub(tmp_path, *, fix=False, usage=None, exit_code=0, message=None, name="claude-stub"):
    """A stand-in `claude` CLI, invoked exactly the way the real one would be by `run_candidate_stage`:
    consumes stdin (the task prompt), optionally "implements" the fix by editing `mathutils.py` in its
    own cwd (the sealed workdir the candidate stage runs in, per `_make_source_repo`'s scenario),
    optionally prints a single `--output-format json` result envelope, and exits with `exit_code` -- the
    shapes `run_candidate` must classify (usage capture on a clean exit; a quota/other non-zero exit ->
    always ungraded-environmental, never a graded fail)."""
    path = tmp_path / name
    lines = ["#!/bin/sh", "cat > /dev/null"]
    if fix:
        lines.append(
            "python3 -c \"import pathlib; "
            "pathlib.Path('mathutils.py').write_text('def add(a, b):\\n    return a + b\\n')\""
        )
    if message:
        lines.append(f"echo {shlex.quote(message)}")
    if usage is not None:
        envelope = json.dumps({"type": "result", "result": "ok", "usage": usage, "duration_ms": 1234})
        lines.append(f"echo {shlex.quote(envelope)}")
    lines.append(f"exit {exit_code}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o755)
    return path


# --- model resolution goes through tools/registry.py, never a re-guessed id --------------------------

def test_resolve_candidate_model_resolves_config_through_the_registry():
    entry = bench_replay.resolve_candidate_model("sonnet")
    assert entry["id"] == "claude-sonnet-5"


def test_resolve_candidate_model_unknown_config_raises_loud():
    with pytest.raises(KeyError):
        bench_replay.resolve_candidate_model("no-such-config-in-models-toml")


# --- the candidate stage's own argv/stdin shape --------------------------------------------------------

def test_candidate_stage_argv_shapes_model_effort_permissions_and_tool_allowlist(tmp_path):
    captured = {}

    def spy_run(argv, cwd=None, env=None, input=None):
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["input"] = input
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    bench_replay.run_candidate_stage(tmp_path, "TASK PROMPT BODY", "claude-sonnet-5",
                                      claude_bin="claude", effort="high", env={"PATH": "/x"}, run=spy_run)

    argv = captured["argv"]
    assert argv[0] == "claude"
    assert argv[1] == "-p"
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"
    assert argv[argv.index("--effort") + 1] == "high"
    assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"
    tools_idx = argv.index("--allowedTools")
    assert argv[tools_idx + 1:tools_idx + 5] == ["Read", "Edit", "Write", "Bash"]
    assert argv[argv.index("--output-format") + 1] == "json"
    assert captured["cwd"] == str(tmp_path)
    # the task prompt travels on stdin, never argv -- the same self-pattern-match discipline
    # tools/dev-runner.sh's run_stage observes (issue #121) -- so it must never appear on the command line.
    assert captured["input"] == "TASK PROMPT BODY"
    assert not any("TASK PROMPT BODY" in arg for arg in argv)


def test_candidate_system_prompt_matches_dev_runner_implement_stage_verbatim(tmp_path):
    captured = {}

    def spy_run(argv, cwd=None, env=None, input=None):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    bench_replay.run_candidate_stage(tmp_path, "task", "claude-sonnet-5", claude_bin="claude",
                                      effort="high", env={}, run=spy_run)

    sys_prompt = captured["argv"][captured["argv"].index("--append-system-prompt") + 1]
    assert DEV_RUNNER_IMPL_SYS in sys_prompt
    assert DEV_RUNNER_STAGE_CHARTER in sys_prompt


def test_run_candidate_passes_task_prefix_plus_corpus_prompt_body_on_stdin_never_argv(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=True)
    captured = {}

    def spy_run(argv, cwd=None, env=None, input=None):
        if str(stub) in argv:
            captured["argv"] = argv
            captured["input"] = input
        return bench_replay._run(argv, cwd=cwd, env=env, input=input)

    bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                out_dir=tmp_path / "results", claude_bin=str(stub),
                                run=spy_run, now=_now)

    assert captured["input"] == DEV_RUNNER_TASK_PREFIX + record["prompt"]["body"]
    assert not any(record["prompt"]["body"] in arg for arg in captured["argv"])


# --- the GitHub credential is withheld from the candidate's own environment ----------------------------

def test_candidate_subprocess_env_carries_no_github_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "super-secret-should-never-reach-the-candidate")
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=True)
    captured_envs = []

    def spy_run(argv, cwd=None, env=None, input=None):
        if str(stub) in argv:
            captured_envs.append(env)
        return bench_replay._run(argv, cwd=cwd, env=env, input=input)

    bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                out_dir=tmp_path / "results", claude_bin=str(stub),
                                run=spy_run, now=_now)

    assert captured_envs, "expected the candidate stage subprocess to be invoked"
    for env in captured_envs:
        for cred_var in bench_replay.CREDENTIAL_ENV_VARS:
            assert cred_var not in env


# --- the result row: complete, and its weighted total reproduces from the raw counts -------------------

def test_result_row_is_complete_and_weighted_total_reproduces_from_stub_usage(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    usage_cli = {"input_tokens": 1000, "output_tokens": 200,
                 "cache_creation_input_tokens": 300, "cache_read_input_tokens": 400}
    stub = _write_claude_stub(tmp_path, fix=True, usage=usage_cli)
    out_dir = tmp_path / "results"

    result = bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                         out_dir=out_dir, claude_bin=str(stub), now=_now)

    assert result["schema"] == "yr-bench-result/1"
    assert result["outcome"] == "pass"
    assert result["config"] == "sonnet"
    assert result["model"] == "claude-sonnet-5"
    assert result["task"] == "999-pr1"
    assert result["repo"] == record["repo"]
    assert result["issue"] == 999 and result["pr"] == 1
    assert result["graded_at"] == NOW

    expected_counts = {out_key: usage_cli[cli_key] for cli_key, out_key in stage_usage.USAGE_FIELDS}
    for out_key, value in expected_counts.items():
        assert result[out_key] == value

    expected_weighted = round(sum(expected_counts[k] * w for k, w in stage_usage.WEIGHTED_TOTAL_WEIGHTS.items()))
    assert result["weighted_total"] == expected_weighted

    out_path = out_dir / "2026-07-13-sonnet.jsonl"
    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == result


def test_missing_usage_envelope_on_clean_exit_defaults_all_four_counts_to_zero(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=True, usage=None)

    result = bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                         out_dir=tmp_path / "results", claude_bin=str(stub), now=_now)

    assert result["outcome"] == "pass"
    for out_key in stage_usage.WEIGHTED_TOTAL_WEIGHTS:
        assert result[out_key] == 0
    assert result["weighted_total"] == 0


# --- quota/rate-limit and other candidate death -- always ungraded-environmental, never a graded fail --

def test_quota_signature_candidate_death_is_ungraded_environmental_never_a_graded_fail(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, exit_code=1, message="Error: rate limit reached, try again later")
    out_dir = tmp_path / "results"

    result = bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                         out_dir=out_dir, claude_bin=str(stub), now=_now)

    assert result["outcome"] == "ungraded-environmental"
    assert result["check_cmd"] is None and result["check_rc"] is None
    lines = (out_dir / "2026-07-13-sonnet.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["outcome"] == "ungraded-environmental"


def test_non_quota_candidate_failure_is_also_ungraded_environmental_not_a_graded_fail(tmp_path):
    """No trustworthy candidate state exists to grade after ANY non-zero candidate exit -- not just a
    quota/rate-limit one."""
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, exit_code=1, message="candidate crashed: unexpected exception")

    result = bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                         out_dir=tmp_path / "results", claude_bin=str(stub), now=_now)

    assert result["outcome"] == "ungraded-environmental"


def test_candidate_failing_check_grades_fail_not_ungraded(tmp_path):
    """A candidate that runs clean but never actually fixes the bug must grade fail -- distinct from the
    environmental outcomes above."""
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=False)  # exits 0 but never touches mathutils.py

    result = bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                         out_dir=tmp_path / "results", claude_bin=str(stub), now=_now)

    assert result["outcome"] == "fail"
    assert result["check_rc"] not in (0, None)


# --- nothing is written outside the sealed workdir and bench/results/ ----------------------------------

def test_source_repo_is_never_touched_and_only_the_results_dir_persists(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=True, usage={"input_tokens": 1})
    out_dir = tmp_path / "results"

    def _snapshot(repo):
        return sorted(str(p.relative_to(repo)) for p in pathlib.Path(repo).rglob("*"))

    before = _snapshot(source_repo)

    bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                out_dir=out_dir, claude_bin=str(stub), now=_now)

    assert _snapshot(source_repo) == before
    assert [p.name for p in out_dir.iterdir()] == ["2026-07-13-sonnet.jsonl"]


def test_default_workdir_is_torn_down_after_the_run(tmp_path, monkeypatch):
    """Like grade()'s own run-scoped TMPDIR discipline (#142): a caller who does not supply --workdir
    gets a throwaway sealed workdir, cleaned up before run_candidate returns."""
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=True)
    roots = []
    real_mkdtemp = tempfile.mkdtemp

    def spy_mkdtemp(*a, **kw):
        p = real_mkdtemp(*a, **kw)
        roots.append(p)
        return p

    monkeypatch.setattr(bench_replay.tempfile, "mkdtemp", spy_mkdtemp)

    bench_replay.run_candidate(record, source_repo=source_repo, config="sonnet",
                                out_dir=tmp_path / "results", claude_bin=str(stub), now=_now)

    assert roots, "expected a run-scoped root to have been created"
    for root in roots:
        assert not pathlib.Path(root).exists()


# --- CLI shape -------------------------------------------------------------------------------------------

def test_cli_run_candidate_end_to_end(tmp_path, capsys):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    stub = _write_claude_stub(tmp_path, fix=True, usage={"input_tokens": 5, "output_tokens": 5})
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record))
    out_dir = tmp_path / "results"

    rc = bench_replay.main(["run-candidate", "--record", str(record_path), "--source", str(source_repo),
                             "--config", "sonnet", "--out-dir", str(out_dir), "--claude-bin", str(stub)])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["outcome"] == "pass"
    assert printed["config"] == "sonnet"
    run_date = printed["graded_at"].split("T", 1)[0]
    lines = (out_dir / f"{run_date}-sonnet.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == printed


def test_cli_run_candidate_requires_config_argument(tmp_path):
    source_repo, record, _diff, _pre_sha, _merge_sha = _make_source_repo(tmp_path)
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record))
    with pytest.raises(SystemExit):
        bench_replay.main(["run-candidate", "--record", str(record_path), "--source", str(source_repo)])


# ============================================================================
# Attended host CLI only -- no dispatch coupling, no capacity-slot claims, no network calls
# ============================================================================

def test_module_imports_no_dispatch_or_network_machinery():
    source = (ROOT / "tools" / "bench_replay.py").read_text()
    # line-anchored: bench_replay.py's own docstring cites tools/epic_gate.py's `import dispatch` as a
    # naming-convention EXAMPLE for its own sibling imports -- a real `import dispatch` here would be an
    # actual dispatch-coupling regression, but that citation in prose is not one.
    assert not re.search(r"^\s*import\s+dispatch\b", source, re.MULTILINE)
    assert not re.search(r"^\s*import\s+(requests|urllib|http\.client|socket)\b", source, re.MULTILINE)
    assert "n8n" not in source.lower()
