"""The attended lane's canon ↔ registry agreement, and the it-30 write-path repair's own pins.

Two duties this file owns alone (it-30 slice 3, epic #415):

  1. **Agreement, both directions.** `skills/factory/references/attended-lane.md` states the step set
     and the walled-act map; `records.toml` states the grammars and the lanes. Neither may drift from
     the other: every record the canon's step table names must be a registry row, and every record a
     lane mandates must appear in the canon's step table. Registry authority applied to itself — the
     epic's "one home, no drift twins" contract, pinned rather than asserted in prose.
  2. **The boarded write-path repair** (`2026-08-06-two-step-fs-write-races-stamper`, superseded into
     the round): distinct pins, so the big canon review cannot dilute the repair — the typed-write
     caveat's corrected authority and the two measured race shapes in the hazard list.
"""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import records  # noqa: E402

LANE = REPO / "skills" / "factory" / "references" / "attended-lane.md"
MODEL = REPO / "skills" / "factory" / "references" / "documentation-model.md"


@pytest.fixture(scope="module")
def lane_text():
    return LANE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def reg():
    return records.load()


def _canon_record_names(text: str) -> set[str]:
    """Every backticked `YR-*` token in the canon reference — the records its tables name."""
    return set(re.findall(r"`(YR-[A-Z-]+)`", text))


# ── 1. agreement, both directions ────────────────────────────────────────────────────────────────

def test_every_record_the_canon_names_is_a_registry_row(lane_text, reg):
    registered = {r["name"] for r in records.records(reg)}
    for name in sorted(_canon_record_names(lane_text)):
        assert name in registered, (
            f"{name} is named in attended-lane.md but carries no records.toml row — "
            f"the canon's own rule says a record absent from the registry is unsanctioned"
        )


def test_every_lane_mandated_record_appears_in_the_canon_step_table(lane_text, reg):
    named = _canon_record_names(lane_text)
    for lane, wanted in records.lanes(reg).items():
        for w in wanted:
            assert w in named, (
                f"lanes.{lane} mandates {w}, which attended-lane.md never names — the detector "
                f"would demand a record the canon does not teach"
            )


def test_the_rounds_own_records_carry_rows_and_fields(reg):
    for name, fields in (
        ("YR-DESIGN-REVIEW", {"who", "verdict"}),
        ("YR-DESIGN-FIT", {"who", "verdict"}),
        ("YR-ACCEPT", {"who", "date"}),
        ("YR-BOARD-FLIP", {"who", "to"}),
        ("YR-SHIP-WALK", {"who", "scope"}),
        ("YR-ROUND-RECORD", {"refusals", "records-demanded", "detector-findings", "escalations"}),
        ("YR-ESCALATION", {"act", "why"}),
        ("YR-HUMAN-INSTRUCTION", {"who", "act"}),
    ):
        row = records.get(reg, name)
        assert set(row.get("fields") or []) == fields, name


def test_every_walled_act_carries_condition_and_stance():
    """The map is TOTAL — the spec's own demand, re-anchored to the GENERATED surface (it-31
    slice 8: the canon's hand table retired). Every compiled row carries a condition cell and a
    stance from the closed vocabulary; a row with an empty stance is a gap the walls would guess
    at."""
    text = (REPO / "build" / "walled-acts.md").read_text(encoding="utf-8")
    rows = [l for l in text.splitlines()
            if l.startswith("| transition |") or l.startswith("| invariant |")]
    assert len(rows) >= 40, "the compiled walled-act map lost rows"
    for r in rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        assert len(cells) >= 8 and cells[4] and cells[5], \
            f"compiled row lacks condition or stance: {r[:120]}"
        assert cells[5] in ("refuse", "escalate", "advise", "observe"), \
            f"unknown stance {cells[5]!r}: {r[:120]}"


def test_the_canon_points_at_the_generated_map(lane_text):
    """The hand table retired IN FAVOR OF the splice — the section must route to it, not vanish."""
    block = lane_text.split("## The walled-act map")[1].split("\n## ")[0]
    assert "build/walled-acts.md" in block
    assert not any(l.startswith("| PR merge") or l.startswith("| Act |")
                   for l in block.splitlines()), "the hand table returned beside the generated one"


def test_the_records_the_walls_condition_on_are_registered(reg):
    """A wall condition may not name a record the registry does not carry — judged on the
    GENERATED map, where every condition the walls actually enforce is spelled."""
    text = (REPO / "build" / "walled-acts.md").read_text(encoding="utf-8")
    registered = {r["name"] for r in records.records(reg)}
    for name in set(re.findall(r"`(YR-[A-Z-]+)`", text)):
        assert name in registered, f"{name} conditions a wall but is unregistered"


# ── 2. the write-path repair, distinctly pinned ──────────────────────────────────────────────────

def test_typed_write_caveat_names_the_decision_tables_authority():
    text = MODEL.read_text(encoding="utf-8")
    caveat = next(l for l in text.splitlines() if "typed-write caveat" in l)
    assert "no filesystem row" in caveat.lower(), "the caveat no longer denies a filesystem row"
    assert "never a sanction" in caveat.lower() or "not a sanction" in caveat.lower(), (
        "the caveat no longer states it is a typing statement, never a sanction"
    )
    assert "MCP frontmatter row" in caveat, "the caveat no longer names the sanctioned typed path"


def test_hazard_list_carries_both_measured_race_shapes():
    text = MODEL.read_text(encoding="utf-8")
    assert re.search(r"two-step.{0,80}race", text, re.IGNORECASE | re.S), (
        "the hazard list lost the two-step create/append race shape"
    )
    assert re.search(r"one file, one write in flight", text, re.IGNORECASE), (
        "the hazard list lost the concurrent-typed-patch race shape's rule"
    )
    assert re.search(r"read-back reads the \*\*file\*\*|read-back reads the file", text, re.IGNORECASE), (
        "the hazard list lost the rule that the read-back reads the file, not the patch's OK"
    )
