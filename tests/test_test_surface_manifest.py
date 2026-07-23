"""Acceptance tests for issue #273 — test surface: `test_paths` + `artifact_globs` drive the tester
charter and boundary guard (technical-rfc yellow-robots/factory#271 epic, slice 2).

Derived from the issue's acceptance criteria (the spec), NOT from the implementation's internals:

  1. The tester's legal write surface is read from the repo manifest key `test_paths` (a TOML array of
     repo-relative path prefixes), defaulting to `["tests/"]` — today's behavior (pinned, unmodified, by
     tests/test_repo_shape_defaults.py; not re-covered here).
  2. A tester write confined to the declared surface passes the boundary guard — including a surface
     outside the default `tests/` tree (the colocated-test idiom), and matching is directory-anchored
     (a declared `src/tests` prefix never matches `src/tests_extra/...`).
  3. The guard's build-artifact forgiveness set is read from the manifest key `artifact_globs`,
     defaulting to today's Python set (`__pycache__/`, `*.pyc`).
  4. A boundary-guard block states the offending paths, the effective declared surface, and the
     declaration's source (`manifest` or `default`).
  5. A declared value that fails to parse (not an array of strings, an absolute path, a `..` component,
     an empty list, or an empty-string element) fails closed — bounced to Needs-info, never a silent
     fallback — naming the rejected value.
  6. Neither key takes an environment override (source vocabulary is exactly `manifest|default`).

Reuses the shared harness only (tests/harness/CLAUDE_STUB, GH_STUB, consumed via test_dev_runner.py's
fixtures) — no private clone of the classifier. Three derived flags (STUB_TESTER_COLOCATED_CHANGE,
STUB_TESTER_TESTS_EXTRA_CHANGE, STUB_TESTER_LOG_ARTIFACT_CHANGE) are spliced into the shared CLAUDE_STUB
by locating its exact existing STUB_TESTER_ARTIFACT_CHANGE line, never by retyping the classifier — same
derivation pattern as tests/test_repo_shape_defaults.py's ROOT_ARTIFACT_CLAUDE_STUB.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td   # shared stub harness (gh/claude/check stubs + fixtures)
import claude_fake              # tests/harness/claude_fake.py — the classifier's one legal home

ROOT = td.ROOT


# ============ a CLAUDE_STUB variant with three extra tester-arm write flags ============
# Derived from the shared classifier by locating its exact existing STUB_TESTER_ARTIFACT_CHANGE line
# (never by retyping the classification patterns): adds writes for the colocated-test idiom
# (src/tests/...), the anchored-prefix trap (src/tests_extra/... — must NOT match a declared
# `src/tests` prefix), and a custom-glob-forgiven artifact (debug.log at the repo root).
_ARTIFACT_ANCHOR = ('[ -n "${STUB_TESTER_ARTIFACT_CHANGE:-}" ] && { mkdir -p tools/__pycache__ && '
                    'printf \'bytecode\\n\' > tools/__pycache__/check.cpython-314.pyc; }')
assert _ARTIFACT_ANCHOR in claude_fake.CLAUDE_STUB, "STUB_TESTER_ARTIFACT_CHANGE line moved/changed shape"
_SURFACE_ADDITION = _ARTIFACT_ANCHOR + '''
                        [ -n "${STUB_TESTER_COLOCATED_CHANGE:-}" ] && { mkdir -p src/tests && printf 'colocated\\n' > src/tests/test_colocated.py; }
                        [ -n "${STUB_TESTER_TESTS_EXTRA_CHANGE:-}" ] && { mkdir -p src/tests_extra && printf 'not colocated\\n' > src/tests_extra/evil.py; }
                        [ -n "${STUB_TESTER_LOG_ARTIFACT_CHANGE:-}" ] && printf 'log output\\n' > debug.log'''
SURFACE_CLAUDE_STUB = claude_fake.CLAUDE_STUB.replace(_ARTIFACT_ANCHOR, _SURFACE_ADDITION, 1)


def _stubs_surface(binp):
    binp.mkdir(parents=True, exist_ok=True)
    td._exec(binp / "gh", td.GH_STUB)
    td._exec(binp / "claude", SURFACE_CLAUDE_STUB)
    td._exec(binp / "check.sh", td.CHECK_STUB)


# ============ manifest helpers ============

def _commit_manifest(work, content):
    """Commit+push a `.yr/factory.toml` with the given raw TOML content to origin/main — read by the
    runner's `git show origin/main:...` manifest lookup for a real (non-dry-run) run."""
    (work / ".yr" / "factory.toml").write_text(content)
    td._git(["add", "-A"], work)
    td._git(["commit", "-q", "-m", "set test surface manifest"], work)
    td._git(["push", "-q", "origin", "main"], work)


def _manifest_only_repo(tmp, content, name="repo"):
    """A minimal, non-git repo dir carrying a `.yr/factory.toml` — the runner's manifest read falls back
    to the working-tree file when `git show` yields nothing (no git repo at all), the same shape
    test_dev_runner.py's `_manifest_repo` relies on for its own dry-run/needs-info manifest fixtures."""
    repo = tmp / name
    (repo / ".yr").mkdir(parents=True)
    (repo / ".yr" / "factory.toml").write_text(content)
    return repo


def _block_msg(tl):
    """The boundary-guard block comment's MESSAGE portion only — everything before the trailing
    `(diff: <path>)` suffix. The diff path is a RUN_DIR under pytest's own tmp_path, whose directory
    name is derived from the calling test's node id (e.g. a test named ...source_default... yields a
    tmp dir containing the substring "default") — including it in a keyword search would produce a
    false positive unrelated to what the runner actually stated. Stripping it keeps every
    offender/surface/source assertion anchored to the runner's own words."""
    comments = " ".join(td._comments(tl))
    return comments.split("(diff:")[0]


def _assert_needs_info_fail_closed(tmp_path, manifest_toml, key, needle):
    """A malformed declared value for `key` bounces the run to Needs-info (fail closed, never a silent
    default) and the block record names the rejected value/key — never silently falls back and never
    silently proceeds."""
    repo = _manifest_only_repo(tmp_path, manifest_toml)
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=9, title=f"Malformed {key}")
    env["BASE_REPO"] = str(repo)
    r = td._run(["9", "--repo", "test/repo"], env)
    assert r.returncode == 3, r.stdout + r.stderr
    tl = td._timeline(tmp_path)
    assert not td._ran(tl)                                          # never proceeds to any stage
    assert "NeedsInfo" in " ".join(td._edits(tl))
    comments = " ".join(td._comments(tl))
    assert key in comments
    assert needle.lower() in comments.lower()


# ============ (1) declared surface passes, including outside the default tests/ tree ============

def test_declared_colocated_surface_passes_the_boundary_guard(tmp_path):
    """A tester write confined to a manifest-declared surface OUTSIDE the default tests/ tree (the
    colocated-test idiom, e.g. src/tests/) passes the guard: the run reaches a PR."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Colocated surface passes"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_COLOCATED_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    tl = td._timeline(tmp_path)
    assert "TEST" in tl and "CHECK" in tl and "REVIEW" in tl
    assert "https://stub/pr/1" in r.stdout


def test_multiple_declared_prefixes_all_apply(tmp_path):
    """A test_paths array with more than one entry: a tester write confined across BOTH declared
    prefixes passes — the surface is the union of every declared entry, not just the first."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["tests/", "src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Multiple prefixes"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1", "STUB_TESTER_COLOCATED_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout


# ============ (2) a declared surface REPLACES the default — writing the old default tree offends ======

def test_declared_surface_makes_the_old_default_tree_an_offender(tmp_path):
    """Once test_paths is declared, it is the WHOLE surface — a write under the undeclared default
    tests/ tree is now an offender, block-and-raise, naming the offender, the declared surface, and its
    source ('manifest')."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Old default tree now offends"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    assert "REASONFIELD" in " ".join(td._edits(tl)) and "Blocked" in " ".join(td._edits(tl))
    msg = _block_msg(tl)
    assert "tests/test_stub_output.py" in msg                       # offender named
    assert "src/tests" in msg                                       # effective declared surface named
    assert "manifest" in msg.lower()                                # declaration's source named
    assert "https://stub/pr/1" not in r.stdout


# ============ directory-anchored matching: a declared prefix never matches as a raw substring =========

def test_declared_prefix_match_is_directory_anchored_not_substring(tmp_path):
    """A declared `src/tests` prefix must never match `src/tests_extra/...` as a raw substring — the
    match is directory-anchored (a trailing-slash-normalized prefix compared against a path component
    boundary). A write confined to src/tests_extra/ is an offender even though 'src/tests' is a
    substring of its path."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Anchored prefix, not substring"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TESTS_EXTRA_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    assert "REASONFIELD" in " ".join(td._edits(tl)) and "Blocked" in " ".join(td._edits(tl))
    assert "src/tests_extra/evil.py" in _block_msg(tl)
    assert "https://stub/pr/1" not in r.stdout


# ============ (3) artifact_globs: declared forgiveness set REPLACES the default =========================

def test_declared_artifact_glob_forgives_a_custom_pattern(tmp_path):
    """A manifest-declared artifact_globs pattern (e.g. *.log) forgives a matching path outside the
    surface — the run reaches a PR even though the file sits outside tests/."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'artifact_globs = ["*.log"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Custom artifact glob forgiven"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1", "STUB_TESTER_LOG_ARTIFACT_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout


def test_declared_artifact_globs_replace_the_default_pycache_forgiveness(tmp_path):
    """Once artifact_globs is declared, it is the WHOLE forgiveness set — a __pycache__/*.pyc artifact
    that the undeclared default would silently forgive now offends, because the declared set no longer
    includes it."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'artifact_globs = ["*.log"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Declared globs replace default"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1", "STUB_TESTER_ARTIFACT_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    tl = td._timeline(tmp_path)
    assert "REASONFIELD" in " ".join(td._edits(tl)) and "Blocked" in " ".join(td._edits(tl))
    assert "tools/__pycache__/check.cpython-314.pyc" in _block_msg(tl)
    assert "https://stub/pr/1" not in r.stdout


# ============ (4) block record names offenders + effective surface + source (manifest|default) ========

def test_default_block_states_source_default_and_default_surface(tmp_path):
    """WHERE neither key is declared, a block still states the effective surface (tests/) and its source
    (default) alongside the offender — today's judgment, now legible."""
    work, _ = td._make_repo(tmp_path)   # _make_repo seeds a bare, key-less manifest
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Default source stated"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_PROD_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    msg = _block_msg(td._timeline(tmp_path))
    assert "tester_prod.txt" in msg
    assert "default" in msg.lower()
    assert "tests/" in msg


def test_manifest_block_states_source_manifest_and_declared_surface(tmp_path):
    """A block under a declared surface states 'manifest' as the source, alongside the declared surface
    value and the offender."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Manifest source stated"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_PROD_CHANGE": "1"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    msg = _block_msg(td._timeline(tmp_path))
    assert "tester_prod.txt" in msg
    assert "manifest" in msg.lower()
    assert "src/tests" in msg


# ============ (5) malformed declared values fail closed, never a silent fallback =======================
# The five rejected shapes named by the acceptance criteria: not an array of strings, an absolute path,
# a `..` path component, an empty list, an empty-string element. Covered for BOTH test_paths and
# artifact_globs — the criteria draw no distinction between the two keys' validation.

def test_test_paths_scalar_string_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'test_paths = "tests/"\n', "test_paths", "tests/")


def test_test_paths_absolute_path_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'test_paths = ["/etc/passwd"]\n', "test_paths", "/etc/passwd")


def test_test_paths_dotdot_component_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'test_paths = ["tests/../secret"]\n', "test_paths", "..")


def test_test_paths_empty_list_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'test_paths = []\n', "test_paths", "empty")


def test_test_paths_empty_string_element_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'test_paths = [""]\n', "test_paths", "empty")


def test_artifact_globs_scalar_string_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'artifact_globs = "*.pyc"\n', "artifact_globs", "*.pyc")


def test_artifact_globs_absolute_path_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'artifact_globs = ["/*.pyc"]\n', "artifact_globs", "/*.pyc")


def test_artifact_globs_dotdot_component_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'artifact_globs = ["a/../b.pyc"]\n', "artifact_globs", "..")


def test_artifact_globs_empty_list_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'artifact_globs = []\n', "artifact_globs", "empty")


def test_artifact_globs_empty_string_element_is_rejected(tmp_path):
    _assert_needs_info_fail_closed(tmp_path, 'artifact_globs = [""]\n', "artifact_globs", "empty")


def test_malformed_value_never_silently_falls_back(tmp_path):
    """A malformed declared value never silently falls back to the built-in default: a scalar
    (non-array) test_paths never leaves the guard running against ['tests/'] unannounced — the run stops
    at Needs-info, unconditionally, before any stage runs."""
    repo = _manifest_only_repo(tmp_path, 'test_paths = "tests/"\n')
    binp = tmp_path / "bin"; td._stubs(binp)
    env = td._env(tmp_path, binp, number=9, title="No silent fallback")
    env["BASE_REPO"] = str(repo)
    r = td._run(["9", "--repo", "test/repo"], env)
    assert r.returncode == 3
    tl = td._timeline(tmp_path)
    assert not td._ran(tl) and "CHECK" not in tl
    assert "https://stub/pr/1" not in r.stdout


# ============ (6) no environment override — manifest still governs even if an env var is set ===========

def test_env_test_paths_has_no_effect_manifest_still_governs(tmp_path):
    """Setting a plausible env override (TEST_PATHS, matching the CHECK_CMD/MERGE_CI_TIMEOUT env>manifest
    convention used elsewhere in this manifest) has NO effect: the guard still judges against the
    manifest-declared surface, not the env value. A tester write confined to the manifest's declared
    surface still passes even though the env value names something else entirely."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Env test_paths ignored"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_COLOCATED_CHANGE": "1",
                "TEST_PATHS": "some/unrelated/dir"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout


def test_env_artifact_globs_has_no_effect_manifest_still_governs(tmp_path):
    """Same as above for artifact_globs: an env ARTIFACT_GLOBS is ignored, the manifest-declared
    forgiveness set still governs — a custom glob the manifest declares still forgives its match even
    though the env value names something unrelated."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'artifact_globs = ["*.log"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Env artifact_globs ignored"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_TEST_CHANGE": "1",
                "STUB_TESTER_LOG_ARTIFACT_CHANGE": "1", "ARTIFACT_GLOBS": "*.unrelated"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode == 0, r.stderr
    assert "https://stub/pr/1" in r.stdout


def test_source_vocabulary_is_never_env(tmp_path):
    """The declaration-source vocabulary is exactly manifest|default — never 'env', even when an env
    var of the same plausible name is set alongside a declared manifest value. Checked against the
    block record's stated source for a declared surface."""
    work, _ = td._make_repo(tmp_path)
    _commit_manifest(work, 'test_paths = ["src/tests"]\n')
    binp = tmp_path / "bin"; _stubs_surface(binp)
    env = td._real(tmp_path, td._env(tmp_path, binp, number=5, title="Source vocabulary check"), work)
    env.update({"STUB_CLAUDE_CHANGE": "1", "STUB_TESTER_PROD_CHANGE": "1", "TEST_PATHS": "ignored/"})
    r = td._run(["5", "--repo", "test/repo"], env)
    assert r.returncode != 0
    msg = _block_msg(td._timeline(tmp_path))
    assert "tester_prod.txt" in msg
    assert "manifest" in msg.lower()
    assert " env" not in msg.lower() and "(env" not in msg.lower()
