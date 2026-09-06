"""Acceptance tests for tools/design_gate.py's close sweep (it-36 slice H, #473): `sweep_close`
spawns `tools/close-runner.sh` when a finished epic carries `YR-CLOSE-HOLD` and its own mandated
close records are not already on the trail. Derived from the issue's acceptance criteria:

  - a fixture epic carrying the hold (and none of its own close records yet) earns a spawn.
  - an epic with no hold at all is left alone.
  - an epic whose hold's own mandated records (YR-ROUND-RECORD + YR-SHIP-WALK) are ALREADY on the
    trail is left alone too — idempotent, never a duplicate close-stage spawn once the records land
    but before the next epic-gate tick self-closes it.
  - an epic with a close stage already in flight is left alone (no duplicate spawn).
  - the close arm itself (`tools/epic_gate.py`) is never touched by this module — this suite only
    drives `sweep_close`, never comments/edits a board field.

No live network, no live pidfiles, no real subprocess spawn: every external is injected exactly like
`tests/test_design_gate.py`'s own `FakeGh`/`_sweep` pattern.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import design_gate  # noqa: E402

REPO = "acme/widgets"

CLOSE_HOLD_BODY = (
    "YR-CLOSE-HOLD\n"
    "  commit: abc123\n\n"
    "This Feature epic has no open children left, but its mandated close records are not on the "
    "trail — missing:\n\n"
    "- close: YR-ROUND-RECORD: mandated record absent (marker 'YR-ROUND-RECORD:', mode prefix)\n"
    "- close: YR-SHIP-WALK: mandated record absent (marker 'YR-SHIP-WALK:', mode prefix)\n"
)

ROUND_RECORD_BODY = (
    "YR-ROUND-RECORD: the round's observable counts\n"
    "refusals: 0\nrecords-demanded: 0\ndetector-findings: 0\nescalations: 0\ndeployed: none\n"
)
SHIP_WALK_BODY = "YR-SHIP-WALK: walked at close\nwho: @human\nscope: this epic's slices\n"


class FakeGh:
    """Injectable `gh`. `issues`: `{number: [comment bodies]}` — the epic's own trail, body empty by
    convention (the fixtures below carry every marker as a comment, matching `epic_gate.py`'s own
    posting shape)."""

    def __init__(self, issues):
        self.issues = {str(k): list(v) for k, v in issues.items()}
        self.calls = []

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["issue", "view"]:
            number = argv[2]
            comments = self.issues.get(number, [])
            return {"body": "", "comments": [{"body": b} for b in comments]}
        raise AssertionError(f"FakeGh: unexpected argv {argv}")


def _sweep(gh, epics, *, active_state=None):
    state = dict(active_state or {})
    spawned = []

    def close_active(repo, number):
        return state.get((repo, number), False)

    def spawn_close(repo, number, component_root="", strategy_doc=""):
        spawned.append((repo, number, component_root, strategy_doc))
        state[(repo, number)] = True

    actions = design_gate.sweep_close(gh=gh, epics=epics, close_active=close_active,
                                      spawn_close=spawn_close)
    return actions, spawned, state


def test_a_finished_epic_carrying_the_hold_with_no_close_records_yet_is_spawned():
    gh = FakeGh({100: [CLOSE_HOLD_BODY]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])
    assert spawned == [(REPO, 100, "", "")]
    assert {"repo": REPO, "number": 100, "action": "spawned"} in actions


def test_an_epic_with_no_close_hold_at_all_is_left_alone():
    gh = FakeGh({100: ["just an ordinary comment, no hold"]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])
    assert spawned == []
    assert {"repo": REPO, "number": 100, "action": "no-hold"} in actions


def test_an_epic_whose_close_records_already_landed_is_not_re_spawned():
    """The idempotency the acceptance criteria demand: once the records are on the trail, this
    sweep steps back and lets the NEXT epic-gate tick self-close it — no duplicate close-stage
    spawn in the window between the records landing and that tick running."""
    gh = FakeGh({100: [CLOSE_HOLD_BODY, ROUND_RECORD_BODY, SHIP_WALK_BODY]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])
    assert spawned == []
    assert {"repo": REPO, "number": 100, "action": "already-shipped"} in actions


def test_an_epic_with_a_close_stage_already_in_flight_is_not_re_spawned():
    gh = FakeGh({100: [CLOSE_HOLD_BODY]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}],
                                 active_state={(REPO, 100): True})
    assert spawned == []
    assert {"repo": REPO, "number": 100, "action": "in-flight"} in actions


def test_partial_close_records_still_earn_a_spawn():
    """Only ONE of the two mandated records landed — the detector still finds a missing mandate, so
    this sweep still spawns (mirrors the close arm's own grammar-not-just-presence rule)."""
    gh = FakeGh({100: [CLOSE_HOLD_BODY, ROUND_RECORD_BODY]})   # SHIP-WALK still missing
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])
    assert spawned == [(REPO, 100, "", "")]
    assert {"repo": REPO, "number": 100, "action": "spawned"} in actions


def test_multiple_epics_are_each_judged_independently():
    gh = FakeGh({
        100: [CLOSE_HOLD_BODY],                                       # spawn
        101: ["no hold here"],                                        # no-hold
        102: [CLOSE_HOLD_BODY, ROUND_RECORD_BODY, SHIP_WALK_BODY],    # already-shipped
    })
    actions, spawned, _ = _sweep(gh, [
        {"repo": REPO, "number": 100}, {"repo": REPO, "number": 101}, {"repo": REPO, "number": 102},
    ])
    assert spawned == [(REPO, 100, "", "")]
    by_number = {a["number"]: a["action"] for a in actions}
    assert by_number == {100: "spawned", 101: "no-hold", 102: "already-shipped"}


def test_sweep_close_never_posts_a_comment_or_edits_a_field_itself():
    """This sweep only spawns — the close arm's own comment/board-field writes
    (`tools/epic_gate.py`, unchanged) are the only writes on this path."""
    gh = FakeGh({100: [CLOSE_HOLD_BODY]})
    _sweep(gh, [{"repo": REPO, "number": 100}])
    assert all(call[:2] == ["issue", "view"] for call in gh.calls)


def test_close_hold_sentinel_requires_the_bare_line_not_a_prose_mention():
    # a comment that merely MENTIONS "YR-CLOSE-HOLD" mid-sentence is never a hold — sentinel mode is
    # whole-line equality, exactly like `tools/textutil.py marker_line_matches`'s own contract.
    gh = FakeGh({100: ["as documented, the sweep would post YR-CLOSE-HOLD if this epic finished"]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])
    assert spawned == []
    assert {"repo": REPO, "number": 100, "action": "no-hold"} in actions


# ---- B3 (#472 fold review): component_root/strategy_doc thread from the epic entry onto spawn_close,
#      never a shared env var (one value for every swept repo) and never stripped by dispatch's own
#      spawn-env allowlist -------------------------------------------------------------------------------

def test_component_root_and_strategy_doc_thread_from_the_epic_entry_to_spawn_close():
    gh = FakeGh({100: [CLOSE_HOLD_BODY]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100,
                                       "component_root": "/vault/04 projects/acme",
                                       "strategy_doc": "/vault/04 projects/acme/strategy/main.md"}])
    assert spawned == [(REPO, 100, "/vault/04 projects/acme",
                       "/vault/04 projects/acme/strategy/main.md")]


def test_missing_component_root_and_strategy_doc_on_the_entry_default_to_empty_never_a_crash():
    gh = FakeGh({100: [CLOSE_HOLD_BODY]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])   # no component_root/strategy_doc key
    assert spawned == [(REPO, 100, "", "")]


def test_default_spawn_close_puts_component_root_and_strategy_doc_on_argv_never_env(tmp_path, monkeypatch):
    """B3's own wire-shape fix: the real seam is ARGV, not an environment variable — an env var
    would be (a) one value shared across every swept repo despite each config entry declaring its
    own, and (b) silently stripped by dispatch's own spawn-env allowlist under the PM instance."""
    import design_gate as dg
    monkeypatch.setattr(dg, "DEV_RUNNER_HOME", str(tmp_path))
    argv_log = tmp_path / "argv.log"
    fake_runner = tmp_path / "fake-close-runner.sh"
    fake_runner.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv_log}"\nexec sleep 300\n')
    fake_runner.chmod(0o755)
    monkeypatch.setattr(dg, "CLOSE_RUNNER", str(fake_runner))

    dg._default_spawn_close(REPO, 100, "/vault/04 projects/acme", "/vault/04 projects/acme/strategy/main.md")
    try:
        import time as _time
        for _ in range(50):
            if argv_log.exists() and argv_log.read_text():
                break
            _time.sleep(0.05)
        lines = argv_log.read_text().splitlines()
        assert lines == [REPO, "100", "/vault/04 projects/acme",
                         "/vault/04 projects/acme/strategy/main.md"]
    finally:
        _kill_close_pidfile(dg, REPO, 100)


def _kill_close_pidfile(dg, repo, epic_number):
    """N6: a robust cleanup — SIGTERM, confirm, SIGKILL if it didn't take — so a spawned test
    fixture never outlives its test even if the first signal is swallowed."""
    import os
    import signal
    import time as _time
    pidfile = dg._close_pidfile(repo, epic_number)
    if not pidfile.is_file():
        return
    try:
        pid = int(pidfile.read_text().strip())
    except (OSError, ValueError):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except OSError:
            return   # already gone
        _time.sleep(0.05)
        try:
            os.killpg(pid, 0)
        except OSError:
            return   # confirmed gone


def test_default_close_active_and_spawn_close_use_a_real_pidfile(tmp_path, monkeypatch):
    """The production seams (`_default_close_active`/`_default_spawn_close`) mirror
    `_default_design_active`/`_default_spawn_stage`'s own pidfile shape — exercised here with a
    fake `CLOSE_RUNNER` binary and a scratch `DEV_RUNNER_HOME`, never a real close-runner.sh."""
    import design_gate as dg
    monkeypatch.setattr(dg, "DEV_RUNNER_HOME", str(tmp_path))
    fake_runner = tmp_path / "fake-close-runner.sh"
    fake_runner.write_text("#!/bin/sh\nexec sleep 300\n")   # N6: exec'd, so proc.pid stays valid
    fake_runner.chmod(0o755)
    monkeypatch.setattr(dg, "CLOSE_RUNNER", str(fake_runner))

    try:
        assert dg._default_close_active(REPO, 100) is False
        dg._default_spawn_close(REPO, 100)
        assert dg._default_close_active(REPO, 100) is True
    finally:
        _kill_close_pidfile(dg, REPO, 100)


# ---- I11: _default_discover_close_hold — --limit 200, --match comments, and a Feature/Epic Type ---------
#      check before any candidate is ever returned (and so, before any spawn) -----------------------------

class FakeGhSearch:
    """Injectable `gh` for `_default_discover_close_hold`: `search_results` is the canned
    `gh search issues --json number` payload; `issue_types` maps issue number -> Issue Type name
    (a number absent from this map has NO `issueType`, matching an untyped issue's own real JSON
    shape). Records every argv for the argv-shape assertions."""

    def __init__(self, *, search_results, issue_types=None, raise_on_view=None):
        self.search_results = list(search_results)
        self.issue_types = dict(issue_types or {})
        self.raise_on_view = set(raise_on_view or ())
        self.calls = []

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["search", "issues"]:
            return self.search_results
        if argv[:2] == ["issue", "view"]:
            number = int(argv[2])
            if number in self.raise_on_view:
                raise RuntimeError(f"gh issue view {number} failed")
            name = self.issue_types.get(number)
            return {"issueType": ({"name": name} if name else None)}
        raise AssertionError(f"FakeGhSearch: unexpected argv {argv}")


def test_discover_close_hold_searches_with_match_comments_and_limit_200():
    gh = FakeGhSearch(search_results=[])
    design_gate._default_discover_close_hold(gh, REPO)
    search_call = gh.calls[0]
    assert search_call[:2] == ["search", "issues"]
    assert "--match" in search_call and search_call[search_call.index("--match") + 1] == "comments"
    assert "--limit" in search_call and search_call[search_call.index("--limit") + 1] == "200"
    assert "--state" in search_call and search_call[search_call.index("--state") + 1] == "open"


def test_discover_close_hold_keeps_only_feature_and_epic_typed_candidates():
    gh = FakeGhSearch(
        search_results=[{"number": 100}, {"number": 101}, {"number": 102}, {"number": 103}],
        issue_types={100: "Feature", 101: "Epic", 102: "Task"},   # 103 left untyped (no issueType)
    )
    found = design_gate._default_discover_close_hold(gh, REPO)
    assert found == [{"repo": REPO, "number": 100}, {"repo": REPO, "number": 101}]


def test_discover_close_hold_type_check_is_case_insensitive():
    gh = FakeGhSearch(search_results=[{"number": 100}], issue_types={100: "feature"})
    assert design_gate._default_discover_close_hold(gh, REPO) == [{"repo": REPO, "number": 100}]


def test_discover_close_hold_a_probe_failure_skips_only_that_candidate():
    gh = FakeGhSearch(
        search_results=[{"number": 100}, {"number": 101}],
        issue_types={101: "Feature"},
        raise_on_view={100},
    )
    found = design_gate._default_discover_close_hold(gh, REPO)
    assert found == [{"repo": REPO, "number": 101}]


def test_discover_close_hold_a_probe_failure_is_named_on_stderr_never_silent(capsys):
    """#473 fold review round 3: a probe failure must never empty discovery invisibly — the
    candidate and the error land on stderr, so a SYSTEMATIC failure (a renamed field, a narrowed
    token scope) is visible, not a silently-shrinking result."""
    gh = FakeGhSearch(
        search_results=[{"number": 100}],
        issue_types={},
        raise_on_view={100},
    )
    design_gate._default_discover_close_hold(gh, REPO)
    err = capsys.readouterr().err
    assert REPO in err
    assert "100" in err


def test_discover_close_hold_returns_nothing_when_search_is_empty():
    gh = FakeGhSearch(search_results=[])
    assert design_gate._default_discover_close_hold(gh, REPO) == []
