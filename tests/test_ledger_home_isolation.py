"""Acceptance tests for issue #236 — ledger: the suite can never write the production meter.

Derived from the issue's acceptance criteria (the spec), NOT from tests/conftest.py's own internals:

  1. A full factory test-suite run must leave the operator's real usage ledger (the rows file under the
     runner's default home, $HOME/.cache/dev-runner/ledger/rows.jsonl) untouched, on any host -- whether
     run under the check gate or by hand. Proved hermetically under a sentinel HOME rather than by
     diffing the operator's own (shared, concurrently-written) ledger file, which would false-positive
     whenever another build's terminal row lands mid-comparison.
  2. That isolation is itself a tested guard, not a hope: a runner-invoking test executed WITHOUT opting
     into an explicit DEV_RUNNER_HOME (the exact shape of the vulnerable suites named in the issue --
     their env dicts never set the key) must land its ledger row in a test-owned home, or fail loudly --
     never silently fall through to the operator's default.

Reuses the stubbed-runner fixtures from test_dev_runner.py (gh/claude/check stubs, issue/item JSON,
_run/_env/_manifest_repo) -- the same convention test_ci_registration_grace.py already uses to extend
that suite rather than cloning its scaffolding.
"""
import json, os, pathlib, site, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_dev_runner as td

ROOT = td.ROOT


def _real_default_home():
    return pathlib.Path.home() / ".cache" / "dev-runner"


def test_conftest_autouse_fixture_never_leaves_the_real_default_home():
    """tests/conftest.py's autouse fixture must set DEV_RUNNER_HOME for every test before its body
    runs, to a path that is never the operator's real default. If that fixture were ever removed,
    mis-scoped, or short-circuited, DEV_RUNNER_HOME would either be absent (dev-runner.sh then falls
    back to the real default) or -- worse -- silently equal to it. Assert both away directly here, so a
    regression fails loudly in this test instead of only surfacing as extra rows on someone's real
    meter."""
    home = os.environ.get("DEV_RUNNER_HOME")
    assert home, "DEV_RUNNER_HOME must be set for every test (tests/conftest.py's autouse fixture)"
    real_default = _real_default_home()
    assert pathlib.Path(home) != real_default, (
        f"DEV_RUNNER_HOME resolved to the operator's real default ({real_default}) -- a runner-invoking "
        "test would append rows to the production ledger"
    )


def test_runner_invocation_without_explicit_isolation_lands_its_row_in_a_test_owned_home(tmp_path):
    """A representative runner-invoking test, run exactly the way the vulnerable suites named in issue
    #236 ran (no DEV_RUNNER_HOME key in the test's own env dict at all -- relying entirely on whatever
    _run's os.environ merge picks up): its ledger row must land under the ambient DEV_RUNNER_HOME the
    suite-level fixture already put in the environment -- not get silently dropped, and not fall through
    to the operator's real default."""
    binp = tmp_path / "bin"
    td._stubs(binp)
    env = td._env(tmp_path, binp, body="### Goal\njust do it\n")
    env["BASE_REPO"] = str(td._manifest_repo(tmp_path))
    # the exact vulnerable pattern: no opt-in in the test's own env dict -- isolation must come from the
    # ambient os.environ the suite-level fixture already populated, not from this test asserting it away

    ambient_home = os.environ.get("DEV_RUNNER_HOME")
    assert ambient_home, "the suite-level fixture must already have set this before the test body ran"
    assert pathlib.Path(ambient_home) != _real_default_home()

    r = td._run(["7", "--repo", "test/repo"], env)
    assert r.returncode == 3  # empty acceptance criteria -> needs-info bounce (tools/dev-runner.sh:570)

    rows_path = pathlib.Path(ambient_home) / "ledger" / "rows.jsonl"
    assert rows_path.exists(), "the bounce's ledger_append call must have landed somewhere test-owned"
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["outcome"] == {"type": "needs-info", "decision": None}


def _subprocess_env_with_sentinel_home(sentinel_home):
    env = dict(os.environ)
    env["HOME"] = str(sentinel_home)
    env.pop("DEV_RUNNER_HOME", None)
    # HOME also drives Python's *user* site-packages resolution (site.getusersitepackages()),
    # independent of PATH -- overriding it for the child would otherwise hide an interpreter's own
    # user-installed pytest. Pin the parent's already-resolved site dirs onto PYTHONPATH so the child
    # keeps finding its test dependencies no matter which HOME it's asked to simulate.
    site_dirs = [d for d in ([site.getusersitepackages()] + site.getsitepackages()) if d]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(site_dirs + ([existing] if existing else []))
    return env


def test_representative_runner_test_leaves_a_sentinel_home_untouched(tmp_path):
    """The issue's own reproduction, made deterministic: point HOME at a sentinel standing in for an
    operator's real home, run one representative runner-invoking test the same way the check gate would
    (`pytest <path>::<test>`) -- test_dev_runner.py's own empty-criteria needs-info bounce, which is
    exactly the shape of the vulnerable tests named in issue #236 since its env dict never sets
    DEV_RUNNER_HOME -- and confirm nothing at all gets created under that sentinel home. (Verified by
    hand while developing this test: with tests/conftest.py removed, this exact scenario reproducibly
    creates a synthetic ledger row under the sentinel home -- the live-host defect from the issue.)"""
    sentinel_home = tmp_path / "sentinel-home"
    sentinel_home.mkdir()
    env = _subprocess_env_with_sentinel_home(sentinel_home)

    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_dev_runner.py::test_needs_info_on_empty_criteria", "-q"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    real_rows = sentinel_home / ".cache" / "dev-runner" / "ledger" / "rows.jsonl"
    assert not real_rows.exists(), (
        "a runner-invoking test run without explicit isolation must never write a row to the "
        "operator's default ledger ($HOME/.cache/dev-runner/ledger/rows.jsonl)"
    )
