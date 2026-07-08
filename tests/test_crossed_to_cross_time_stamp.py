"""
Tests for the crossed_to timing policy (skill 0.7.1) — the stamp is set at the
airlock crossing, not deferred to the iteration close.

Rationale (2026-07-06): epic self-close removed the guaranteed attended close
moment, so a close-time stamp rides on memory and fails silent-and-ambiguous
(not-yet-crossed vs. forgot-to-stamp). A cross-time stamp lives in the one
session that always exists — the attended crossing itself; an epic later
closed *not planned* keeps the stamp as true history and records its own
outcome. Text-property assertions in the house style, against the model,
closing, and authoring references.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"


def _model():
    return (REFS / "documentation-model.md").read_text(encoding="utf-8")


def _closing():
    return (REFS / "closing.md").read_text(encoding="utf-8")


def _authoring():
    return (REFS / "authoring.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# documentation-model.md — the definition site states the timing
# ---------------------------------------------------------------------------

def test_model_defines_crossed_to_as_stamped_at_the_crossing():
    text = _model()
    assert "Stamped at the crossing itself" in text, \
        "documentation-model.md crossed_to definition does not state cross-time stamping"
    assert "never deferred to close" in text, \
        "documentation-model.md does not rule out deferring the stamp to close time"


def test_model_names_the_epic_issue_ref_value_form():
    """Under Model E the crossing target is the epic Issue — the value form
    must show the issue-ref shape, not only the legacy repo path."""
    assert re.search(r"crossed_to[^\n]*owner/repo#N", _model()), \
        "documentation-model.md crossed_to value form does not show the epic issue ref"


# ---------------------------------------------------------------------------
# closing.md §3 — the freeze verifies the stamp; it is no longer the act
# ---------------------------------------------------------------------------

def test_closing_freeze_is_the_backstop_not_the_act():
    text = _closing()
    assert "Verify every doc that crossed carries its `crossed_to` stamp" in text, \
        "closing.md §3 lost the crossed_to verify-backstop bullet"
    assert "set **at the crossing**, not here" in text, \
        "closing.md §3 no longer says the stamp is set at the crossing"
    assert "Record where the design was built" not in text, \
        "closing.md §3 still frames the crossed_to stamp as a close-time act"


# ---------------------------------------------------------------------------
# authoring.md — the crossing step carries the stamp instruction
# ---------------------------------------------------------------------------

def test_authoring_crossing_step_stamps_on_filing():
    text = _authoring()
    assert re.search(r"stamp `crossed_to", text), \
        "authoring.md crossing step has no crossed_to stamp instruction"
    assert "**On filing**" in text, \
        "authoring.md does not tie the stamp to the moment the epic Issue exists"


# ---------------------------------------------------------------------------
# Version bump — .claude-plugin/plugin.json 0.7.0 -> 0.7.1
# ---------------------------------------------------------------------------

def test_plugin_version_is_current():
    data = json.loads(PLUGIN.read_text(encoding="utf-8"))
    assert data["version"] == "0.8.0", \
        f".claude-plugin/plugin.json version is {data['version']!r}, expected '0.8.0'"
