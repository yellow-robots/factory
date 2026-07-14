"""Acceptance tests for tools/bench_corpus.py — the replayable-corpus extractor (issue #162).

Stubbed-`gh` style (mirrors test_epic_gate.py / test_dev_runner.py): a fake `gh(argv)` callable is
injected into `extract_corpus`, serving canned `pr list` / contents-API / commits-API responses. No
live `gh`, no network. Tests are derived from the acceptance criteria (the spec) — eligibility, the
record shape, the exclusion-by-name discipline, and the transient-vs-404 retry contract — never from
bench_corpus.py's own internals.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bench_corpus  # noqa: E402

REPO = "yellow-robots/widget"
OWNER, NAME = "yellow-robots", "widget"
MANIFEST_PATH = f"repos/{OWNER}/{NAME}/contents/.yr/factory.toml"

NOW = "2026-07-13T00:00:00Z"


def _now():
    return NOW


def _confirmed_404():
    return RuntimeError("gh api ... failed (404): Not Found")


def _transient():
    return RuntimeError("gh: connection reset by peer")


class FakeGh:
    """Routes `gh(argv)` calls the way `bench_corpus.py` actually issues them: `pr list`, the
    `.yr/factory.toml` contents probe (default branch or a `ref=`), an issue's body, a commit's
    parents, and an arbitrary file's contents at a ref. Every fixture value may be a single
    value/Exception (served on every call) or a list (consumed one entry per call, exhausting into
    an AssertionError so a test that under-provisions responses fails loudly rather than looping)."""

    def __init__(self, *, prs, manifest_default=None, manifest_by_ref=None,
                 issue_bodies=None, commits=None, file_contents=None, pr_list=None):
        self.prs = prs
        self.pr_list = pr_list
        self.manifest_default = manifest_default
        self.manifest_by_ref = dict(manifest_by_ref or {})
        self.issue_bodies = dict(issue_bodies or {})
        self.commits = dict(commits or {})
        self.file_contents = dict(file_contents or {})
        self.calls = []

    @staticmethod
    def _ref_of(argv):
        if "-f" in argv:
            val = argv[argv.index("-f") + 1]
            if val.startswith("ref="):
                return val[len("ref="):]
        return None

    @staticmethod
    def _serve(entry, where):
        if entry is None:
            raise AssertionError(f"FakeGh: no fixture provided for {where}")
        if isinstance(entry, list):
            if not entry:
                raise AssertionError(f"FakeGh: fixture list exhausted for {where}")
            val = entry.pop(0) if len(entry) > 1 else entry[0]
        else:
            val = entry
        if isinstance(val, Exception):
            raise val
        return val

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[0] == "pr" and argv[1] == "list":
            if self.pr_list is not None:
                return self._serve(self.pr_list, "pr list")
            return self.prs
        assert argv[0] == "api", argv
        path = argv[1]
        if path.endswith("contents/.yr/factory.toml"):
            ref = self._ref_of(argv)
            if ref is None:
                return self._serve(self.manifest_default, "default-branch manifest")
            return self._serve(self.manifest_by_ref.get(ref), f"manifest@{ref}")
        if "/issues/" in path:
            issue = int(path.rsplit("/", 1)[-1])
            return self._serve(self.issue_bodies.get(issue), f"issue #{issue} body")
        if "/commits/" in path:
            sha = path.rsplit("/", 1)[-1]
            return self._serve(self.commits.get(sha), f"commit {sha}")
        if "/contents/" in path:
            ref = self._ref_of(argv)
            return self._serve(self.file_contents.get((path, ref)), f"contents {path}@{ref}")
        raise AssertionError(f"FakeGh: unhandled argv {argv}")


def _pr(number, issue, *, merge_sha, head_sha, files):
    return {
        "number": number,
        "headRefName": f"task/{issue}-slug",
        "mergeCommit": {"oid": merge_sha},
        "headRefOid": head_sha,
        "files": [{"path": p} for p in files],
    }


def _content_path(path):
    return f"repos/{OWNER}/{NAME}/contents/{path}"


ELIGIBLE_MANIFEST_DEFAULT = 'bench_test_globs = ["tests/**"]\n'
ELIGIBLE_MANIFEST_PRE = 'check_cmd = "pytest tests/ -q"\n'


def _eligible_gh(**overrides):
    kwargs = dict(
        prs=[_pr(55, 162, merge_sha="mergesha1", head_sha="headsha1",
                 files=["tests/test_foo.py", "tools/foo.py"])],
        manifest_default=ELIGIBLE_MANIFEST_DEFAULT,
        manifest_by_ref={"presha1": ELIGIBLE_MANIFEST_PRE},
        issue_bodies={162: {"body": "Do the thing"}},
        commits={"mergesha1": {"parents": [{"sha": "presha1"}]}},
        file_contents={(_content_path("tests/test_foo.py"), "headsha1"): "def test_x():\n    assert True\n"},
    )
    kwargs.update(overrides)
    return FakeGh(**kwargs)


# ============================================================================
# Eligible PR -> a complete corpus record
# ============================================================================

def test_eligible_pr_yields_a_complete_record(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh()

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["excluded"] == []
    assert len(result["written"]) == 1
    record_path = pathlib.Path(result["written"][0])
    assert record_path == tmp_path / "yellow-robots--widget" / "162-pr55.json"
    record = json.loads(record_path.read_text())
    assert record == {
        "schema": "yr-bench-corpus/1",
        "repo": REPO,
        "issue": 162,
        "pr": 55,
        "prompt": {"body": "Do the thing", "read_at": NOW},
        "pre_solution_ref": "presha1",
        "held_out_tests": [
            {"path": "tests/test_foo.py", "content": "def test_x():\n    assert True\n"},
        ],
        "extracted_at": NOW,
    }


def test_schema_field_is_exact(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh()

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    record = json.loads(pathlib.Path(result["written"][0]).read_text())
    assert record["schema"] == "yr-bench-corpus/1"


def test_held_out_tests_carry_paths_and_file_contents_together(monkeypatch, tmp_path):
    """The held-out set is not just matching paths -- it embeds their PR-head file contents, since a
    sealed replay can never reach git history for them again."""
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(
        prs=[_pr(55, 162, merge_sha="mergesha1", head_sha="headsha1",
                 files=["tests/test_a.py", "tests/test_b.py", "tools/unrelated.py"])],
        file_contents={
            (_content_path("tests/test_a.py"), "headsha1"): "A\n",
            (_content_path("tests/test_b.py"), "headsha1"): "B\n",
        },
    )

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    record = json.loads(pathlib.Path(result["written"][0]).read_text())
    assert record["held_out_tests"] == [
        {"path": "tests/test_a.py", "content": "A\n"},
        {"path": "tests/test_b.py", "content": "B\n"},
    ]


def test_prompt_is_the_issue_body_verbatim_never_authored(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    verbatim_body = "This is the *exact* issue body.\n\n- [ ] a checkbox\n"
    gh = _eligible_gh(issue_bodies={162: {"body": verbatim_body}})

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    record = json.loads(pathlib.Path(result["written"][0]).read_text())
    assert record["prompt"]["body"] == verbatim_body
    assert record["prompt"]["read_at"] == NOW


def test_fielded_api_reads_pin_explicit_get(monkeypatch, tmp_path):
    """`gh api` silently switches to POST whenever a `-f`/`-F` field is present without an explicit
    `-X GET` -- every fielded REST read this tool issues must pin it. This invariant self-extends to
    any future read added to this file, even though a mocked gh cannot observe HTTP semantics."""
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh()

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["excluded"] == []
    assert len(result["written"]) == 1
    for call in gh.calls:
        if "-f" in call or "-F" in call:
            assert "-X" in call and call[call.index("-X") + 1] == "GET", call


def test_pre_solution_ref_is_the_merge_commits_first_parent(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(
        commits={"mergesha1": {"parents": [{"sha": "the-real-parent"}]}},
        manifest_by_ref={"the-real-parent": ELIGIBLE_MANIFEST_PRE},
    )

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    record = json.loads(pathlib.Path(result["written"][0]).read_text())
    assert record["pre_solution_ref"] == "the-real-parent"


# ============================================================================
# Eligibility exclusions -- fail-closed, every one recorded by name
# ============================================================================

def test_no_matching_test_files_yields_an_exclusion_row_with_its_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(
        prs=[_pr(55, 162, merge_sha="mergesha1", head_sha="headsha1", files=["tools/foo.py", "README.md"])],
    )

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["written"] == []
    assert len(result["excluded"]) == 1
    row = result["excluded"][0]
    assert row["repo"] == REPO and row["issue"] == 162 and row["pr"] == 55
    assert row["reason"] == "no PR file matches bench_test_globs"

    exclusions_file = tmp_path / "exclusions.jsonl"
    lines = exclusions_file.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == row


def test_unset_bench_test_globs_excludes_the_pr_with_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(manifest_default='check_cmd = "pytest tests/ -q"\n')  # no bench_test_globs key

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["written"] == []
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == "bench_test_globs is unset for this repo"


def test_missing_manifest_at_default_branch_treated_as_unset_globs(monkeypatch, tmp_path):
    """A repo with no `.yr/factory.toml` at all reads the same as an unset `bench_test_globs` -- no
    manifest can never mean "everything's eligible"."""
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(manifest_default=_confirmed_404())

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["written"] == []
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == "bench_test_globs is unset for this repo"


def test_missing_manifest_at_pre_solution_ref_yields_an_exclusion(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(manifest_by_ref={"presha1": _confirmed_404()})

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["written"] == []
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == "no .yr/factory.toml at the pre-solution ref"


def test_manifest_present_but_missing_check_cmd_at_pre_solution_ref_yields_an_exclusion(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(manifest_by_ref={"presha1": 'model = "sonnet"\n'})  # no check_cmd

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["written"] == []
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == "no check_cmd in the manifest at the pre-solution ref"


def test_a_non_task_branch_merged_pr_is_neither_written_nor_excluded(monkeypatch, tmp_path):
    """A merged PR outside the `task/*` grammar was never a candidate -- it's simply not part of the
    working set, never a recorded exclusion."""
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(prs=[{
        "number": 99, "headRefName": "hotfix/urgent-thing",
        "mergeCommit": {"oid": "somesha"}, "headRefOid": "somehead", "files": [{"path": "tests/x.py"}],
    }])

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["written"] == []
    assert result["excluded"] == []
    assert not (tmp_path / "exclusions.jsonl").exists()


def test_exclusions_file_is_append_only_across_multiple_excluded_prs(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(
        prs=[
            _pr(10, 100, merge_sha="m1", head_sha="h1", files=["tools/a.py"]),
            _pr(11, 101, merge_sha="m2", head_sha="h2", files=["tools/b.py"]),
        ],
    )

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert len(result["excluded"]) == 2
    lines = (tmp_path / "exclusions.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    issues = {json.loads(line)["issue"] for line in lines}
    assert issues == {100, 101}


# ============================================================================
# Transient-vs-404 network discipline (mirrors tools/epic_gate.py's manifest probe)
# ============================================================================

def test_transient_manifest_failure_retries_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(manifest_default=[_transient(), ELIGIBLE_MANIFEST_DEFAULT])

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert result["excluded"] == []
    assert len(result["written"]) == 1


def test_confirmed_404_manifest_excludes_without_retrying(monkeypatch, tmp_path):
    sleeps = []
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: sleeps.append(s))
    gh = _eligible_gh(manifest_by_ref={"presha1": _confirmed_404()})

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert len(result["excluded"]) == 1
    manifest_calls = [c for c in gh.calls if c[1] == MANIFEST_PATH and "ref=presha1" in c]
    assert len(manifest_calls) == 1          # a confirmed 404 burns no retry
    assert sleeps == []


def test_persistent_transient_manifest_failure_raises_and_writes_no_exclusion(monkeypatch, tmp_path):
    """A transient failure that survives every retry attempt must error loudly -- it is never read as
    "no manifest" and must never resolve to a silently-written exclusion row."""
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(manifest_default=[_transient(), _transient()])

    with pytest.raises(Exception):
        bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert not (tmp_path / "exclusions.jsonl").exists()
    assert list(tmp_path.glob("**/*.json")) == []


def test_persistent_transient_pr_list_failure_raises_and_writes_no_exclusion(monkeypatch, tmp_path):
    """A transient failure on any other network read (here: `pr list`) retries with backoff and then
    raises -- never silently dropping the scan or writing a partial/incorrect exclusion."""
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    gh = _eligible_gh(pr_list=[_transient(), _transient()])

    with pytest.raises(Exception):
        bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)

    assert not (tmp_path / "exclusions.jsonl").exists()
    assert list(tmp_path.glob("**/*.json")) == []


def test_transient_pr_list_failure_retries_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_corpus.time, "sleep", lambda s: None)
    prs = [_pr(55, 162, merge_sha="mergesha1", head_sha="headsha1", files=["tests/test_foo.py"])]
    gh = _eligible_gh(prs=prs, pr_list=[_transient(), prs])

    result = bench_corpus.extract_corpus(REPO, gh=gh, now=_now, out_dir=tmp_path)
    assert len(result["written"]) == 1


# ============================================================================
# CLI shape (stdlib JSON CLI, tools/registry.py's shape)
# ============================================================================

def test_cli_extract_forwards_args_and_prints_json(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_extract_corpus(repo, *, out_dir=None, limit=200, **_):
        captured["repo"] = repo
        captured["out_dir"] = out_dir
        captured["limit"] = limit
        return {"written": ["a.json"], "excluded": []}

    monkeypatch.setattr(bench_corpus, "extract_corpus", fake_extract_corpus)

    rc = bench_corpus.main(["extract", "--repo", REPO, "--out", str(tmp_path), "--limit", "7"])

    assert rc == 0
    assert captured == {"repo": REPO, "out_dir": str(tmp_path), "limit": 7}
    out = json.loads(capsys.readouterr().out)
    assert out == {"written": ["a.json"], "excluded": []}


def test_cli_requires_repo_argument():
    with pytest.raises(SystemExit):
        bench_corpus.main(["extract"])


# ============================================================================
# The factory's own manifest declares the key this tool reads
# ============================================================================

def test_factory_manifest_declares_bench_test_globs():
    import tomllib
    manifest = tomllib.loads((ROOT / ".yr" / "factory.toml").read_text())
    assert manifest.get("bench_test_globs") == ["tests/**"]
