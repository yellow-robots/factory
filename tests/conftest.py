"""Suite-level isolation home (issue #236).

Every runner-invoking test's subprocess env is built by spreading `os.environ` first and a test-specific
dict last (see the `_run`/`_env`/`_base_env` helpers across `test_dev_runner*.py`, `test_autonomous_
merge.py`, `test_ci_registration_grace.py`); none of those dicts sets `DEV_RUNNER_HOME` unless a test
opts in explicitly. Left alone, `tools/dev-runner.sh:52` defaults it to `$HOME/.cache/dev-runner` —
the operator's real usage ledger — and `ledger_append` fires on every terminal branch, including the
bounce paths (needs-info, blocked, env-hold), not just a full happy-path run. This autouse fixture sets
`DEV_RUNNER_HOME` to a per-test tmp_path before any test body runs, so every subprocess spawned via
`os.environ` inherits a test-owned home by default; a test that sets its own `DEV_RUNNER_HOME` in its
env dict still wins, since that dict is spread after `os.environ`.
"""
import pytest


@pytest.fixture(autouse=True)
def _dev_runner_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DEV_RUNNER_HOME", str(tmp_path / "drhome"))


@pytest.fixture(autouse=True)
def _suite_is_machinery(monkeypatch):
    """The suite declares itself machinery (it-30, epic #415 — the attended board-write wall).

    The wall in `tools/board_plumbing.set_field` walls ATTENDED board writes: callers running under a
    Claude session (`CLAUDECODE`) that have not declared themselves machinery (`YR_MACHINERY`). The
    suite runs the factory's own machinery — and it runs *inside* attended sessions, inheriting
    `CLAUDECODE`, which is precisely how the first sniff-only form of that wall refused the runner's
    own integration tests. So the declaration is made once, here, for every test: a test that means
    to exercise the ATTENDED path opts in explicitly (`monkeypatch.delenv("YR_MACHINERY")` plus
    `setenv("CLAUDECODE", "1")` — see `tests/test_wall.py`), the same opt-in shape the fixture above
    uses for `DEV_RUNNER_HOME`."""
    monkeypatch.setenv("YR_MACHINERY", "1")
