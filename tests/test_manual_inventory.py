"""
Tests for issue #485 (it-32 slice 4) — the human's manual (docs/manual.md)
renders the workflow taxonomy and the human verbs by citation, the README
points to it, and the manual's inventory tracks the skill router's Operations
table.

Derived from the acceptance criteria (the spec), never from the manual's own
prose: every expectation below is derived from a source OTHER than the
manual — skills/factory/SKILL.md's Operations table, AGENTS.md's Workflow
types table, records.toml's row names — the same "guard derives its
expectation from the tree" pattern as
test_operating_doc_consolidation.py::test_repo_map_lists_every_tracked_tools_path
(issue #397, commit eaec320). A drift test that hardcodes today's manual
text would pass on a stale manual; deriving from the other surfaces is what
actually catches drift.
"""

import datetime
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

MANUAL = ROOT / "docs" / "manual.md"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"
RECORDS = ROOT / "records.toml"


def _text(path):
    return path.read_text(encoding="utf-8")


def _section(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start + len(start_marker))
    return text[start:end]


# ---------------------------------------------------------------------------
# derivation helpers — each pulls its expectation from a surface other than
# the manual
# ---------------------------------------------------------------------------


def _skill_operation_names():
    section = _section(_text(SKILL), "## Operations", "## Invariants")
    names = re.findall(r"^\|\s*\*\*([^*]+)\*\*\s*\|", section, re.MULTILINE)
    assert names, "no Operations table rows parsed from skills/factory/SKILL.md"
    return names


def _agents_workflow_type_names():
    text = _text(AGENTS)
    section = _section(text, "### Workflow types", "## How a change is built")
    names = re.findall(r"^\|\s*\*\*([^*]+)\*\*\s*\|", section, re.MULTILINE)
    assert names, "no Workflow types table rows parsed from AGENTS.md"
    return names


def _records_toml_names():
    return set(re.findall(r'^name = "([^"]+)"', _text(RECORDS), re.MULTILINE))


# ---------------------------------------------------------------------------
# the operation inventory (criterion: "carry an inventory naming every row
# of the skill router's Operations table")
# ---------------------------------------------------------------------------


def test_manual_inventory_lists_every_skill_operation():
    names = _skill_operation_names()
    manual_text = _text(MANUAL)
    missing = [n for n in names if n not in manual_text]
    assert not missing, (
        f"docs/manual.md inventory is missing these skills/factory/SKILL.md "
        f"Operations rows: {missing!r}"
    )


def test_skill_operation_derivation_is_live_against_the_tree():
    """Proves the guard above is live: dropping one derived name from a
    synthetic manual excerpt surfaces exactly that name as missing, the way
    a real newly added Operations row would fail the guard until
    docs/manual.md names it."""
    names = _skill_operation_names()
    assert len(names) >= 5, "sanity: too few Operations rows parsed to be a real derivation"
    dropped = names[0]
    fake_manual = "\n".join(f"- **{n}**" for n in names[1:])
    missing = [n for n in names if n not in fake_manual]
    assert missing == [dropped]


# ---------------------------------------------------------------------------
# the README pointer (criterion: "the README SHALL point a human operator to
# the manual")
# ---------------------------------------------------------------------------


def test_readme_points_a_human_operator_to_the_manual():
    text = _text(README)
    assert re.search(r"docs/manual\.md", text), (
        "README.md does not link docs/manual.md anywhere"
    )
    new_here_match = re.search(r"\*\*New here\?\*\*(.*?)\n\n", text, re.DOTALL)
    assert new_here_match, "README.md is missing its 'New here?' pointer paragraph"
    assert "docs/manual.md" in new_here_match.group(1), (
        "README.md's 'New here?' pointer does not route a human operator to docs/manual.md"
    )


# ---------------------------------------------------------------------------
# the verb line's grammar and date (criterion: "carry the human verb list in
# force at its ship date on a line in the grammar 'Verbs in force at
# <yyyy-mm-dd> — last changed by it-32'")
# ---------------------------------------------------------------------------


def test_manual_verb_line_grammar_and_date_parses():
    text = _text(MANUAL)
    match = re.search(
        r"Verbs in force at (\d{4}-\d{2}-\d{2}) — last changed by it-32", text
    )
    assert match, (
        "docs/manual.md is missing the 'Verbs in force at <yyyy-mm-dd> — "
        "last changed by it-32' line"
    )
    datetime.date.fromisoformat(match.group(1))  # raises ValueError if malformed


VERB_PHRASES = [
    r"design.{0,15}`?active`?",
    r"standalone task to Ready",
    r"WHAT-call",
    r"pull the cord",
    r"PR the runner did not open",
    r"Arm a repo",
    r"Release the skill",
    r"Sanction gate evolution",
]

VERB_HOME_CITATIONS = [
    "AGENTS.md",
    "attended-lane.md",
    "closing.md",
    "records.toml",
]


def _manual_verbs_section():
    return _section(_text(MANUAL), "Verbs in force at", "## The seven workflow types")


def test_manual_carries_exactly_eight_verb_bullets():
    section = _manual_verbs_section()
    bullets = re.findall(r"^- \*\*", section, re.MULTILINE)
    assert len(bullets) == 8, (
        f"docs/manual.md verb list carries {len(bullets)} bullets, expected the eight "
        f"verbs the spec names"
    )


def test_manual_verb_list_names_every_spec_verb():
    section = _manual_verbs_section()
    missing = [p for p in VERB_PHRASES if not re.search(p, section, re.IGNORECASE)]
    assert not missing, (
        f"docs/manual.md verb list is missing these spec-named verbs: {missing!r}"
    )


def test_manual_verb_bullets_each_cite_a_rule_home():
    section = _manual_verbs_section()
    bullet_blocks = re.split(r"\n(?=- \*\*)", section)
    bullet_blocks = [b for b in bullet_blocks if b.strip().startswith("- **")]
    assert len(bullet_blocks) == 8
    uncited = [
        b.splitlines()[0]
        for b in bullet_blocks
        if not any(home in b for home in VERB_HOME_CITATIONS)
    ]
    assert not uncited, (
        f"docs/manual.md verb bullets missing a rule-home citation: {uncited!r}"
    )


# ---------------------------------------------------------------------------
# the seven workflow types, by citation (criterion: "render the seven
# workflow types for a human operator by citation from AGENTS.md's Workflow
# types table, restating no rule that another surface owns")
# ---------------------------------------------------------------------------


def _manual_workflow_types_section():
    return _section(_text(MANUAL), "## The seven workflow types", "## Reading a trail")


def test_manual_workflow_types_match_agents_table_by_name():
    names = _agents_workflow_type_names()
    assert len(names) == 7, (
        f"AGENTS.md Workflow types table has {len(names)} rows, expected seven "
        f"(slice 3's taxonomy) — this test's premise assumes seven"
    )
    section = _manual_workflow_types_section()
    missing = [n for n in names if n not in section]
    assert not missing, (
        f"docs/manual.md workflow-types section is missing these AGENTS.md rows: {missing!r}"
    )
    bullets = re.findall(r"^- \*\*", section, re.MULTILINE)
    assert len(bullets) == 7, (
        f"docs/manual.md workflow-types section carries {len(bullets)} bullets, expected "
        f"exactly the seven rows AGENTS.md names — no more, no fewer"
    )


def test_workflow_type_derivation_is_live_against_the_tree():
    """Proves the derivation above is live: dropping one derived type name
    from a synthetic manual excerpt surfaces exactly that name as missing."""
    names = _agents_workflow_type_names()
    dropped = names[0]
    fake_manual = "\n".join(f"- **{n}**" for n in names[1:])
    missing = [n for n in names if n not in fake_manual]
    assert missing == [dropped]


def test_manual_workflow_types_do_not_restate_the_actor_column():
    # AGENTS.md's table owns the "actors in order" column; the manual's
    # citation-only bullets must not re-list it (a re-told actor chain is a
    # drift twin waiting to happen).
    section = _manual_workflow_types_section()
    assert "epic gate (refusal)" not in section, (
        "docs/manual.md workflow-types section re-tells an AGENTS.md actors-column "
        "entry instead of citing the table"
    )


# ---------------------------------------------------------------------------
# reading a trail (criterion: "explain the records a human meets on a trail
# as the fact and the rule that judged it, cited by row name from
# records.toml, never as a cure catalogue")
# ---------------------------------------------------------------------------


TRAIL_RECORD_NAMES = [
    "YR-MERGE",
    "YR-CLOSE-HOLD",
    "YR-DEBT-HOLD",
    "STAGE-BLOCKED",
    "VERDICT",
    "YR-ESCALATION",
]

EPIC_GATE_SENTINEL_SUFFIXES = [
    "no-approval",
    "not-a-task",
    "not-onboarded",
    "open-questions",
    "gate-touching",
    "stranded claim",
]


def _manual_trail_section():
    return _section(_text(MANUAL), "## Reading a trail", "## Operation inventory")


def test_trail_record_names_still_exist_in_records_toml():
    records_names = _records_toml_names()
    missing = [n for n in TRAIL_RECORD_NAMES if n not in records_names]
    epic_gate_missing = [
        s for s in EPIC_GATE_SENTINEL_SUFFIXES if f"YR-EPIC-GATE: {s}" not in records_names
    ]
    assert not missing, f"records.toml no longer names these rows: {missing!r}"
    assert not epic_gate_missing, (
        f"records.toml no longer names these YR-EPIC-GATE sentinel rows: {epic_gate_missing!r}"
    )


def test_manual_reading_a_trail_cites_every_named_record():
    section = _manual_trail_section()
    missing = [n for n in TRAIL_RECORD_NAMES if n not in section]
    assert not missing, (
        f"docs/manual.md 'Reading a trail' section is missing citations for: {missing!r}"
    )
    assert "YR-EPIC-GATE" in section, (
        "docs/manual.md 'Reading a trail' section drops the YR-EPIC-GATE sentinel family"
    )
    missing_sentinels = [s for s in EPIC_GATE_SENTINEL_SUFFIXES if s not in section]
    assert not missing_sentinels, (
        f"docs/manual.md 'Reading a trail' section is missing these YR-EPIC-GATE "
        f"sentinels: {missing_sentinels!r}"
    )
    assert re.search(r"Needs-info", section), (
        "docs/manual.md 'Reading a trail' section drops the board's Needs-info reason"
    )
    assert re.search(r"Blocked", section), (
        "docs/manual.md 'Reading a trail' section drops the board's Blocked reason"
    )


# ---------------------------------------------------------------------------
# the declared update trigger (criterion: "declare its update trigger — the
# release act's manual_current condition (slice 5) and the drift guard
# tests/test_manual_inventory.py")
# ---------------------------------------------------------------------------


def test_manual_declares_its_update_trigger():
    text = _text(MANUAL)
    assert "manual_current" in text, (
        "docs/manual.md does not name the release act's manual_current condition"
    )
    assert "tests/test_manual_inventory.py" in text, (
        "docs/manual.md does not name this guard test (tests/test_manual_inventory.py) "
        "as one of its update triggers"
    )
