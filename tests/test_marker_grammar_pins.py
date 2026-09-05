"""Characterization pins for the three kept `YR-*` record-marker readers (issue #381).

This is the *pin* half of a pin-then-prune pair (tech-debt round 2). Its whole job is to lock, at the
reader level, exactly the anchoring behaviour that MUST survive the next slice's consolidation of these
readers — and to leave DELIBERATELY UNLOCKED the one tolerance that slice is declared to remove.

Derived from the acceptance CRITERIA (the spec), never from the readers' internals: each test drives the
named reader through its own entry point with crafted comment/body text and asserts only the observable
grammar (matches / does not match). No test re-implements a `startswith`/`.strip()` matcher.

The three readers and their documented anchoring rules (at origin/main 914b4a4):

  * tools/epic_gate.py — COLUMN-0 raw-prefix rule (`line.startswith(PREFIX)`, never stripped): the
    approval reader `_approval_candidates` (YR-EPIC-APPROVAL), `_open_question_lines`
    (YR-OPEN-QUESTION:), `_gate_touching_declaration` (YR-GATE-TOUCHING:).
  * tools/epic_gate.py — WHOLE-STRIPPED-LINE equality rule (`line.strip() == MARKER`): `_is_debt_epic`
    (YR-ITERATION-KIND: tech-debt), `_has_ledger_verdict` (YR-DEBT-LEDGER), `_is_due_raise`
    (YR-DEBT-DUE), and the sweep's own `already_held` read (YR-DEBT-HOLD, exercised end-to-end through
    `sweep_epics` since it has no standalone reader function).
  * tools/nit_harvest.py — COLUMN-0 raw-prefix rule: `parse_nit` (YR-NIT:).
  * tools/merge_shadow.py — genuine merge-record recognition: `_last_merge_record` (armed / shadow
    marker line + fenced `yr-merge-record` block).

The observable difference the two epic_gate rules encode, and which these pins lock: a column-0 rule
rejects an INDENTED marker line, whereas a whole-stripped-line rule ACCEPTS an indented marker line.
Both rules still reject a prose mention / inline-backticked example on a longer line, and the column-0
rule still ACCEPTS a marker line inside a fenced block (the anchoring guarantees indentation, not
fencing).

DELIBERATELY NOT PINNED (drift the next slice removes — a pin here would turn a declared fix into a
failure and block the round):

  * tools/merge_shadow.py's bare two-substring tolerance (`"YR-MERGE" in body or "yr-merge-record" in
    body`): NO test below asserts that a comment merely CONTAINING the text `YR-MERGE`, or merely
    containing `yr-merge-record` outside a fence, or carrying either BLOCKQUOTED, is treated as the PR's
    merge record. A quoted review transcript (e.g. a bench replay's own candidate transcript) is exactly
    the shape that could produce such a blockquote; the next slice tightens this reader to the
    marker-line-plus-fence grammar, so today's tolerant behaviour is left uncharacterized in either
    direction.

Pins added by this file: 35 (distinct grammar cases, across 12 test functions — the parametrized cases
plus the standalone reader tests below). Accretive only — no existing test is modified or removed, and
no production file is touched.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import epic_gate       # noqa: E402
import nit_harvest     # noqa: E402
import merge_shadow    # noqa: E402


# ============================================================================
# tools/epic_gate.py — the COLUMN-0 raw-prefix rule (approval / open-question / gate-touching).
#
# A line carrying the marker at column 0 matches; the same line indented by one space does NOT; the same
# marker inline-backticked in prose does NOT; the same line blockquoted with `> ` does NOT; and a marker
# line inside a fenced block DOES still match (indentation is the guarantee, not fencing).
# ============================================================================

def _column0_cases(marker, *, tail=""):
    """The five canonical column-0 anchoring cases for `marker`, each `(label, body, matches)`.

    `tail` is appended after the marker (a non-empty reason for the gate-touching prefix, which counts a
    line only when the text after the prefix is non-empty)."""
    line = f"{marker}{tail}"
    return [
        ("column-0", f"prose above\n{line}\nprose below", True),
        ("indented-one-space", f"prose above\n {line}\nprose below", False),
        ("inline-backticked", f"See the `{marker}` grammar in the authoring docs for details.", False),
        ("blockquoted", f"> {line}\n> quoted context", False),
        ("fenced-block", f"```\n{line}\n```", True),
    ]


@pytest.mark.parametrize(
    "label,body,matches", _column0_cases(epic_gate.APPROVAL_MARKER),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_epic_approval_column0_prefix_rule(label, body, matches):
    """`_approval_candidates` returns a body only when some line begins YR-EPIC-APPROVAL at column 0."""
    candidates = epic_gate._approval_candidates([body])
    assert bool(candidates) is matches, f"{label}: {body!r}"


@pytest.mark.parametrize(
    "label,body,matches", _column0_cases(epic_gate.OPEN_QUESTION_PREFIX, tail=" is this still open?"),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_open_question_column0_prefix_rule(label, body, matches):
    """`_open_question_lines` reports a line only when it begins YR-OPEN-QUESTION: at column 0."""
    lines = epic_gate._open_question_lines(body)
    assert bool(lines) is matches, f"{label}: {body!r}"


@pytest.mark.parametrize(
    "label,body,matches", _column0_cases(epic_gate.GATE_TOUCHING_PREFIX, tail=" adds a new lint gate"),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_gate_touching_column0_prefix_rule(label, body, matches):
    """`_gate_touching_declaration` returns a reason only for a YR-GATE-TOUCHING: line at column 0."""
    reason = epic_gate._gate_touching_declaration(body)
    assert (reason is not None) is matches, f"{label}: {body!r} -> {reason!r}"


# ============================================================================
# tools/epic_gate.py — the WHOLE-STRIPPED-LINE equality rule (debt-kind / ledger / due).
#
# A line equal to the sentinel AFTER stripping matches — INCLUDING when indented, the observable
# difference from the column-0 rule above — while a prose mention or a backticked example on a longer
# line does not. (The YR-DEBT-HOLD sentinel shares this rule and is pinned end-to-end below.)
# ============================================================================

def _whole_line_cases(marker):
    """`(label, marker_line, matches)` for the whole-stripped-line rule: the bare marker at column 0 and
    indented both match; the marker mentioned mid-line or inline-backticked does not."""
    return [
        ("column-0", marker, True),
        ("indented", f"    {marker}", True),
        ("prose-midline", f"Per {marker} the round is due, see the docs.", False),
        ("inline-backticked", f"See the `{marker}` sentinel grammar for how debt epics are read.", False),
    ]


@pytest.mark.parametrize(
    "label,marker_line,matches", _whole_line_cases(epic_gate.DEBT_KIND_LINE),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_debt_kind_whole_stripped_line_rule(label, marker_line, matches):
    """`_is_debt_epic` fires only when some body line, stripped, equals the debt-kind sentinel."""
    body = f"Some epic description.\n\n{marker_line}\n\nMore prose."
    assert epic_gate._is_debt_epic(body) is matches, f"{label}: {marker_line!r}"


@pytest.mark.parametrize(
    "label,marker_line,matches", _whole_line_cases(epic_gate.LEDGER_MARKER),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_ledger_marker_whole_stripped_line_rule(label, marker_line, matches):
    """`_has_ledger_verdict` fires only when some comment line, stripped, equals YR-DEBT-LEDGER (the
    required `items:`/`net-lines:` fields are present in every case, so only the marker-line grammar
    varies the outcome)."""
    body = f"{marker_line}\nitems: 3\nnet-lines: -412"
    assert epic_gate._has_ledger_verdict([body]) is matches, f"{label}: {marker_line!r}"


@pytest.mark.parametrize(
    "label,marker_line,matches", _whole_line_cases(epic_gate.DUE_MARKER),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_due_marker_whole_stripped_line_rule(label, marker_line, matches):
    """`_is_due_raise` fires only when some body line, stripped, equals YR-DEBT-DUE (the `repo:`/`anchor:`
    key fields match in every case, so only the marker-line grammar varies the outcome)."""
    repo, anchor = "yellow-robots/factory", "#100"
    body = f"{marker_line}\nrepo: {repo}\nanchor: {anchor}\ncount: 10"
    assert epic_gate._is_due_raise(body, repo, anchor) is matches, f"{label}: {marker_line!r}"


# ---- YR-DEBT-HOLD: no standalone reader — pinned end-to-end through `sweep_epics`. --------------------
# The sweep's `already_held` read (tools/epic_gate.py:937) uses the same whole-stripped-line rule: a
# finished debt epic with no ledger verdict HOLDS, and a prior comment already carrying the hold marker
# on its own stripped line suppresses re-posting the hold comment. Reuses test_epic_gate.py's stateful
# `gh` fake and debt-epic fixture rather than re-implementing either (extend, never duplicate).
from test_epic_gate import FakeGh, _sweep, _debt_epic_detail  # noqa: E402


def _hold_comments_posted(prior_comment):
    """The YR-DEBT-HOLD comments a single sweep POSTS on a finished, verdict-less debt epic whose only
    existing comment is `prior_comment`."""
    board, epics = _debt_epic_detail(comments=[prior_comment])
    fake = FakeGh(board, epics)
    _sweep(fake)
    return [c for c in fake.comments if c[1] == "100" and epic_gate.HOLD_MARKER in c[2]]


def test_debt_hold_indented_marker_line_still_counts_as_already_held():
    """An INDENTED prior YR-DEBT-HOLD line, stripped, equals the marker -> the sweep sees the epic as
    already held and posts no duplicate hold comment (the whole-stripped-line rule accepts indentation)."""
    assert _hold_comments_posted(f"    {epic_gate.HOLD_MARKER}") == []


def test_debt_hold_prose_mention_does_not_count_as_already_held():
    """The marker mentioned mid-line, stripped, is not the sentinel -> not already held, so the sweep
    posts its hold comment."""
    posted = _hold_comments_posted(f"Per {epic_gate.HOLD_MARKER} we are waiting on a ledger verdict.")
    assert len(posted) == 1


# ============================================================================
# tools/nit_harvest.py — the COLUMN-0 raw-prefix rule for YR-NIT:.
#
# A YR-NIT: line at column 0 is a record; the same line indented or `> `-quoted is not (the
# bench-transcript guard).
# ============================================================================

_NIT_PAYLOAD = " tag=nit path=tools/x.py line=42 — a duplicated helper"


@pytest.mark.parametrize("label,raw_line,is_record", [
    ("column-0", f"{nit_harvest.NIT_PREFIX}{_NIT_PAYLOAD}", True),
    ("indented", f"    {nit_harvest.NIT_PREFIX}{_NIT_PAYLOAD}", False),
    ("blockquoted", f"> {nit_harvest.NIT_PREFIX}{_NIT_PAYLOAD}", False),
], ids=lambda v: v if isinstance(v, str) else "")
def test_nit_column0_prefix_rule(label, raw_line, is_record):
    """`parse_nit` returns a record row only for a column-0 YR-NIT: line."""
    assert (nit_harvest.parse_nit(raw_line) is not None) is is_record, f"{label}: {raw_line!r}"


# ============================================================================
# tools/merge_shadow.py — genuine merge records are still recognized.
#
# A comment carrying the ARMED marker line plus its fenced block is the PR's merge record; a comment
# carrying the SHADOW marker line plus its fenced block is a merge record for the shadow window; a PR
# trail with no such comment yields "not seen". (`_last_merge_record` returns `(record, malformed,
# seen)`.)
# ============================================================================

def test_armed_marker_line_plus_fence_is_the_merge_record():
    body = merge_shadow.render_comment(
        {"mode": "armed", "decision": "MERGED", "run_id": "run-armed",
         "base_sha": "aaa", "head_sha": "bbb"})
    rec, malformed, seen = merge_shadow._last_merge_record([{"body": body}])
    assert seen is True and malformed is False
    assert rec is not None and rec["decision"] == "MERGED" and rec["run_id"] == "run-armed"


def test_shadow_marker_line_plus_fence_is_a_shadow_merge_record():
    body = merge_shadow.render_comment(
        {"mode": "shadow", "decision": "WOULD-MERGE", "run_id": "run-shadow"})
    rec, malformed, seen = merge_shadow._last_merge_record([{"body": body}])
    assert seen is True and malformed is False
    assert rec is not None and rec["decision"] == "WOULD-MERGE" and rec["run_id"] == "run-shadow"


def test_trail_with_no_merge_record_comment_is_not_seen():
    inert = [{"body": "Looks good to me, shipping it."},
             {"body": "Nice work on the tests."}]
    rec, malformed, seen = merge_shadow._last_merge_record(inert)
    assert seen is False and rec is None
    # an empty trail is likewise not part of the window
    assert merge_shadow._last_merge_record([]) == (None, False, False)
