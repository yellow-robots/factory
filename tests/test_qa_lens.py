"""Acceptance tests for issue #216 — factory lens v1: qa/lens.py, the three recorded species.

Derived from the issue's ACCEPTANCE CRITERIA (the spec), NOT qa/lens.py's internals: every test here
drives the script exactly as its documented interface promises — a subprocess reading YR_BASE_REF
(default origin/main), diffing a real git working tree against that ref, scanning only the CHANGED
files under tests/, and printing a markdown report to stdout with exit code 0 — never by importing or
calling functions private to the lens module.

  * Each of the three recorded species fires on a purpose-built fixture.
  * The repo's existing test corpus at the slice's tip yields ZERO flags.
  * Named good patterns (line-anchored marker asserts, behavioral stdin asserts) stay unflagged.
  * Only CHANGED files under tests/ are scanned — an untouched tests/ file and a changed non-tests/
    file are both left alone even when they contain a triggering pattern.
  * YR_BASE_REF defaults to origin/main when unset.
  * Exit code is 0 whether or not there are findings.
  * `.yr/factory.toml` declares `lens_cmd = "python3 qa/lens.py"` (tests/test_bench_corpus.py:435-438
    pattern: read the manifest, assert the declared key).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LENS = ROOT / "qa" / "lens.py"

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's fixed empty-tree object, any repo

SPECIES1_TRANSCRIPT_GREP = '''\
def test_transcript_grep():
    transcript = capture()
    assert "please confirm the deployment now" in transcript
'''

SPECIES2_BYTE_EXACT_TRANSPORT = '''\
import subprocess

def test_byte_exact_transport():
    spec = subprocess.run(
        ["bash", "-c", "echo \\"$(printf 'hello\\\\n')\\""],
        capture_output=True, text=True,
    ).stdout
    assert spec == "hello\\n"
'''

SPECIES3_UNANCHORED_MARKER = '''\
def test_marker_unanchored():
    output = get_output()
    assert "VERDICT:" in output
'''

GOOD_LINE_ANCHORED_MARKER = '''\
def test_marker_anchored():
    output = get_output()
    assert any(line.startswith("VERDICT:") for line in output.splitlines())
'''

GOOD_BEHAVIORAL_STDIN_ASSERT = '''\
import subprocess

def test_stdin_behavior():
    result = subprocess.run(["myprog"], input="hello", capture_output=True, text=True)
    assert result.returncode == 0
'''


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30,
    )


def _init_repo(tmp_path, base_files=None):
    """A fresh git repo with an initial commit under tests/ — returns (repo_path, base_sha)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_placeholder.py").write_text("def test_ok():\n    assert True\n")
    for relpath, content in (base_files or {}).items():
        p = repo / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    r = _git(repo, "add", "-A")
    assert r.returncode == 0, r.stderr
    r = _git(repo, "commit", "-q", "-m", "base")
    assert r.returncode == 0, r.stderr
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base_sha


def _write(repo, relpath, content):
    p = repo / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _stage(repo):
    r = _git(repo, "add", "-A")
    assert r.returncode == 0, r.stderr


def _run_lens(repo, base_ref, env_extra=None):
    env = {"PATH": "/usr/bin:/bin"}
    if base_ref is not None:
        env["YR_BASE_REF"] = base_ref
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(LENS)], cwd=repo, capture_output=True, text=True, timeout=30, env=env,
    )


# ============ each species fires on a purpose-built fixture ============

def test_species_raw_argv_transport_grep_fires(tmp_path):
    """A prompt-shaped literal grepped off a captured transcript/argv — instead of an assertion on
    observable behavior — is flagged, with the changed file:line named in the report."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_transcript_grep.py", SPECIES1_TRANSCRIPT_GREP)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert "tests/test_transcript_grep.py:3" in r.stdout


def test_species_byte_exact_transport_artifact_fires(tmp_path):
    """A fixture string ending in a trailing newline, compared for equality inside a test whose
    body captures a bash command-substitution ($(...)) result, is flagged — the #121-rebuild
    exhibit: the shell strips exactly the trailing whitespace this fixture still expects."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_byte_exact.py", SPECIES2_BYTE_EXACT_TRANSPORT)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert "tests/test_byte_exact.py" in r.stdout


def test_species_unanchored_marker_substring_fires(tmp_path):
    """A recorded protocol marker (e.g. VERDICT:) checked with a bare `in` containment test rather
    than line-anchored is flagged."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_marker.py", SPECIES3_UNANCHORED_MARKER)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert "tests/test_marker.py:3" in r.stdout


def test_all_three_species_fire_independently_in_one_diff(tmp_path):
    """One changed-file set carrying all three species yields three distinct findings — proving the
    species are each independently detected, not merged or dropped when they co-occur."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_species1.py", SPECIES1_TRANSCRIPT_GREP)
    _write(repo, "tests/test_species2.py", SPECIES2_BYTE_EXACT_TRANSPORT)
    _write(repo, "tests/test_species3.py", SPECIES3_UNANCHORED_MARKER)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    findings = [l for l in r.stdout.splitlines() if l.startswith("- `tests/")]
    assert len(findings) == 3
    assert "tests/test_species1.py" in r.stdout
    assert "tests/test_species2.py" in r.stdout
    assert "tests/test_species3.py" in r.stdout


# ============ named good patterns stay unflagged ============

def test_line_anchored_marker_assert_unflagged(tmp_path):
    """A marker check anchored to a split line (str.startswith) never fires, even though it checks
    the same marker text the unanchored-substring species flags."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_good_marker.py", GOOD_LINE_ANCHORED_MARKER)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_behavioral_stdin_assert_unflagged(tmp_path):
    """Asserting an observable outcome (a process's exit code) rather than a raw captured string
    never fires."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_good_stdin.py", GOOD_BEHAVIORAL_STDIN_ASSERT)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_good_patterns_alongside_firing_species_stay_silent(tmp_path):
    """In a diff carrying both a firing species and a good pattern, only the firing species is
    named — the good pattern contributes nothing to the report."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_species3.py", SPECIES3_UNANCHORED_MARKER)
    _write(repo, "tests/test_good_marker.py", GOOD_LINE_ANCHORED_MARKER)
    _write(repo, "tests/test_good_stdin.py", GOOD_BEHAVIORAL_STDIN_ASSERT)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    findings = [l for l in r.stdout.splitlines() if l.startswith("- `tests/")]
    assert len(findings) == 1
    assert "tests/test_species3.py" in r.stdout
    assert "tests/test_good_marker.py" not in r.stdout
    assert "tests/test_good_stdin.py" not in r.stdout


# ============ only CHANGED files under tests/ are scanned ============

def test_unchanged_tests_file_with_triggering_pattern_stays_quiet(tmp_path):
    """A tests/ file already present at the base ref, carrying a species-shaped pattern but left
    untouched by the diff, is never scanned — changed-only, not corpus-wide."""
    repo, base = _init_repo(
        tmp_path, base_files={"tests/test_preexisting.py": SPECIES3_UNANCHORED_MARKER}
    )
    # a genuinely unrelated change elsewhere in the working tree — the preexisting file itself is
    # never touched again.
    _write(repo, "tests/test_new_unrelated.py", "def test_ok():\n    assert True\n")
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_changed_non_tests_file_is_not_scanned(tmp_path):
    """A changed file outside tests/ carrying a species-shaped pattern is never scanned, no matter
    how it changed — the lens's scope is tests/ only."""
    repo, base = _init_repo(
        tmp_path, base_files={"qa/other.py": SPECIES1_TRANSCRIPT_GREP}
    )
    _write(repo, "qa/other.py", SPECIES1_TRANSCRIPT_GREP + "\n# touched\n")
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


# ============ the repo's existing test corpus at the slice's tip yields ZERO flags ============

def test_existing_repo_corpus_yields_zero_flags():
    """Scanning every tracked file under this repo's own tests/ (diffed against the empty-tree
    object, so every tracked test file reads as 'changed') produces no findings — the graduation
    evidence base's core claim: the lens does not false-positive on the corpus it ships next to."""
    r = _run_lens(ROOT, EMPTY_TREE)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


# ============ exit code is always 0, findings or not ============

def test_exit_code_zero_with_findings(tmp_path):
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_species1.py", SPECIES1_TRANSCRIPT_GREP)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0
    assert r.stdout.strip() != ""


def test_exit_code_zero_with_no_findings(tmp_path):
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_more_good.py", "def test_ok():\n    assert 1 + 1 == 2\n")
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


# ============ report shape: markdown, file:line, species, behavioral-alternative class ============

def test_report_is_markdown_with_file_line_species_and_alternative(tmp_path):
    """Each flag line names the changed file:line, some species identifier, and an alternative
    behavioral class to assert instead — not just a bare location."""
    repo, base = _init_repo(tmp_path)
    _write(repo, "tests/test_species3.py", SPECIES3_UNANCHORED_MARKER)
    _stage(repo)
    r = _run_lens(repo, base)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.startswith("- `tests/test_species3.py:")]
    assert len(lines) == 1
    line = lines[0]
    assert "tests/test_species3.py:3" in line
    # something beyond the bare location is reported: a species label plus a behavioral alternative.
    remainder = line.split("`", 2)[-1]
    assert len(remainder.strip()) > 20


# ============ YR_BASE_REF defaults to origin/main when unset ============

def test_default_base_ref_is_origin_main(tmp_path):
    """With YR_BASE_REF unset, the lens diffs against origin/main — proven by pushing a base commit
    to a remote named origin, then adding a firing fixture with no env override."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    repo, _base = _init_repo(tmp_path)
    r = _git(repo, "remote", "add", "origin", str(bare))
    assert r.returncode == 0, r.stderr
    r = _git(repo, "push", "-q", "origin", "main")
    assert r.returncode == 0, r.stderr

    _write(repo, "tests/test_species3.py", SPECIES3_UNANCHORED_MARKER)
    _stage(repo)
    r = _run_lens(repo, base_ref=None)  # YR_BASE_REF unset -> must default to origin/main
    assert r.returncode == 0, r.stderr
    assert "tests/test_species3.py:3" in r.stdout


def test_default_base_ref_sees_no_changes_when_none_exist(tmp_path):
    """Sanity check on the default: with origin/main current and nothing further changed, the
    default-base-ref run reports nothing (rules out a default that always diffs against nothing,
    i.e. that would spuriously flag everything as 'changed')."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    repo, _base = _init_repo(
        tmp_path, base_files={"tests/test_preexisting.py": SPECIES3_UNANCHORED_MARKER}
    )
    r = _git(repo, "remote", "add", "origin", str(bare))
    assert r.returncode == 0, r.stderr
    r = _git(repo, "push", "-q", "origin", "main")
    assert r.returncode == 0, r.stderr

    r = _run_lens(repo, base_ref=None)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


# ============ .yr/factory.toml declares lens_cmd (tests/test_bench_corpus.py:435-438 pattern) ============

def test_factory_manifest_declares_lens_cmd():
    import tomllib
    manifest = tomllib.loads((ROOT / ".yr" / "factory.toml").read_text())
    assert manifest.get("lens_cmd") == "python3 qa/lens.py"
