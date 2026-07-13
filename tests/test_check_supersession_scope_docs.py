"""
Tests for Issue #141 — check_supersession: a scope-less sweep fails loud;
the census names what it skips.

Derived from the Issue #141 acceptance criteria (the spec), not from the
implementation internals: the two skill reference lines that model the
scope-less sweep must be updated to the explicit-scope form — the sweep
synopsis in skills/factory/references/gates.md:15 and the doc-freeze
checklist call in skills/factory/references/closing.md:60.
"""

import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
GATES = REFS / "gates.md"
CLOSING = REFS / "closing.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _gates_supersession_row():
    text = _text(GATES)
    row = next((line for line in text.splitlines()
                if line.strip().startswith("| `check_supersession`")), None)
    assert row, "gates.md gate table is missing the check_supersession row"
    return row


def _closing_freeze_section():
    text = _text(CLOSING)
    match = re.search(r"^## 3\. Doc-side freeze\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "closing.md is missing the '## 3. Doc-side freeze' section"
    return match.group(1)


def test_gates_sweep_synopsis_uses_explicit_scope_form():
    row = _gates_supersession_row()
    assert re.search(r"--sweep\s+--scope\s+REL", row), \
        "gates.md's sweep synopsis does not show the explicit `--sweep --scope REL` form"


def test_gates_sweep_synopsis_no_longer_shows_scope_less_invocation():
    row = _gates_supersession_row()
    # the old scope-less form ended the invocation right after `--sweep` (optionally followed
    # only by `[--vault-root DIR]`) -- guard that `--sweep` is never immediately followed by
    # `[--vault-root` with no `--scope` in between
    assert not re.search(r"--sweep\s+\[--vault-root", row), \
        "gates.md's sweep synopsis still models a scope-less `--sweep` invocation"


def test_gates_draft_mode_synopsis_unaffected():
    row = _gates_supersession_row()
    assert "check_supersession.py <draft.md> [--vault-root DIR]" in row, \
        "gates.md's draft-mode synopsis changed — draft mode must stay untouched by this slice"


def test_closing_doc_freeze_sweep_call_uses_explicit_scope_form():
    body = _closing_freeze_section()
    assert re.search(r"check_supersession\.py --sweep --scope\b", body), \
        "closing.md's doc-freeze checklist still calls check_supersession.py --sweep " \
        "without an explicit --scope"


def test_closing_doc_freeze_sweep_call_no_longer_scope_less():
    body = _closing_freeze_section()
    assert not re.search(r"check_supersession\.py --sweep\s*`", body), \
        "closing.md's doc-freeze checklist still shows a bare, scope-less `--sweep` call"
