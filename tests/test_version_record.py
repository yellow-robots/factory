"""Position test: the version record (v0.1, step 2 — "what to do next").

A project declares what it wants next as `versions/<n>.toml`: one goal and its acceptance
criteria, each criterion naming the `surface` where it is observed. The next version is derived,
never written down: the lowest declared version that has no `v<n>` tag.

Marked `next` and strict-xfail: `make test` stays green, `make next` shows the real failures, and
the session that makes these pass must remove the marker in the same change.
"""

import pytest

pytestmark = [pytest.mark.next, pytest.mark.xfail(reason="position: v0.1 step 2", strict=True)]

VALID = """
goal = "A static site that says hello"

[[criteria]]
text = "GET / returns a 200 whose body contains 'hello'"
surface = "http"
"""

NO_SURFACE = """
goal = "A static site that says hello"

[[criteria]]
text = "GET / returns a 200 whose body contains 'hello'"
"""


def test_a_version_record_has_a_goal_and_surfaced_criteria():
    from factory.version import parse

    record = parse(VALID)

    assert record.goal == "A static site that says hello"
    assert [c.surface for c in record.criteria] == ["http"]


def test_a_criterion_without_a_surface_is_rejected():
    from factory.version import parse

    with pytest.raises(ValueError, match="surface"):
        parse(NO_SURFACE)


def test_next_version_is_the_lowest_declared_without_a_tag():
    from factory.version import next_version

    assert next_version(declared=["0.1", "0.2", "0.10"], tags=["v0.1"]) == "0.2"
    assert next_version(declared=["0.1", "0.2", "0.10"], tags=["v0.1", "v0.2"]) == "0.10"
    assert next_version(declared=["0.1"], tags=["v0.1"]) is None
