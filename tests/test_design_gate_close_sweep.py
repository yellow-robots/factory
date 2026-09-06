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

    def spawn_close(repo, number):
        spawned.append((repo, number))
        state[(repo, number)] = True

    actions = design_gate.sweep_close(gh=gh, epics=epics, close_active=close_active,
                                      spawn_close=spawn_close)
    return actions, spawned, state


def test_a_finished_epic_carrying_the_hold_with_no_close_records_yet_is_spawned():
    gh = FakeGh({100: [CLOSE_HOLD_BODY]})
    actions, spawned, _ = _sweep(gh, [{"repo": REPO, "number": 100}])
    assert spawned == [(REPO, 100)]
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
    assert spawned == [(REPO, 100)]
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
    assert spawned == [(REPO, 100)]
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


def test_default_close_active_and_spawn_close_use_a_real_pidfile(tmp_path, monkeypatch):
    """The production seams (`_default_close_active`/`_default_spawn_close`) mirror
    `_default_design_active`/`_default_spawn_stage`'s own pidfile shape — exercised here with a
    fake `CLOSE_RUNNER` binary and a scratch `DEV_RUNNER_HOME`, never a real close-runner.sh."""
    import design_gate as dg
    monkeypatch.setattr(dg, "DEV_RUNNER_HOME", str(tmp_path))
    fake_runner = tmp_path / "fake-close-runner.sh"
    fake_runner.write_text("#!/bin/sh\nsleep 5\n")
    fake_runner.chmod(0o755)
    monkeypatch.setattr(dg, "CLOSE_RUNNER", str(fake_runner))

    assert dg._default_close_active(REPO, 100) is False
    dg._default_spawn_close(REPO, 100)
    assert dg._default_close_active(REPO, 100) is True

    # cleanup: kill the spawned process group so the test suite leaves nothing running.
    import os
    import signal
    pidfile = dg._close_pidfile(REPO, 100)
    pid = int(pidfile.read_text().strip())
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
