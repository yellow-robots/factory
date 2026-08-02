"""
Tests for issue #359 — Debt round: the four census arms, their coverage ledger, and the
reachability arm's third partition (technical-RFC slice P2 of epic #357).

Derived from the issue #359 acceptance criteria (the spec), not from the doc-editor's own
wording:

  1. The census axis set is closed at four — reachability, system shape, tests, performance —
     and every census must report, for each of the four, whether it ran and what it carried
     forward unmeasured.
  2. A candidate axis excluded from that closed set must be recorded with its argument; an
     axis this canon has not mentioned is never treated as excluded by silence.
  3. The reachability arm reports a third partition — reached in production and exercised by
     no test — distinct from "reached by nothing" and "reached only by tests".
  4. A system-scope pass runs as a declared arm of every census, reporting shapes no single
     change can reveal (a contract's consumer count, a grammar's forked conventions, a
     duplicated home), and it rules the intended shape for each rather than only enumerating
     instances.

Plus the stated constraints: no fifth axis is added; `skills/factory/references/architect.md`
is not touched by this slice, and the arm is never called an "architect arm" anywhere in the
touched files.

House doc-pin style, in the manner of tests/test_debt_census_surface_and_inputs.py — read the
shipped file, assert its load-bearing content.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
DEBT_ROUNDS = REFS / "debt-rounds.md"
DEBT_CENSUS = ROOT / "templates" / "debt-census.md"
ARCHITECT = REFS / "architect.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _rounds():
    return _text(DEBT_ROUNDS)


def _census():
    return _text(DEBT_CENSUS)


def _flat(text):
    """Collapse markdown line-wrapping whitespace so a phrase split across a
    soft-wrapped line (e.g. 'the\\n   system') still matches as one run."""
    return re.sub(r"\s+", " ", text)


def _section(text, heading, next_headings):
    start = text.find(heading)
    assert start != -1, f"missing the {heading!r} section heading"
    end = len(text)
    for nxt in next_headings:
        idx = text.find(nxt, start + 1)
        if idx != -1:
            end = min(end, idx)
    return text[start:end]


def _census_arms_section():
    text = _rounds()
    return _section(text, "## Census arms", ["## The counter"])


# ---------------------------------------------------------------------------
# AC1 — the axis set is closed at four, and each arm reports whether it ran /
# what it carried forward unmeasured
# ---------------------------------------------------------------------------

def test_debt_rounds_names_the_four_arms_as_a_closed_set():
    section = _census_arms_section()
    lower = section.lower()
    assert "closed at four" in lower, (
        "debt-rounds.md 'Census arms' section does not declare the axis set closed at four"
    )
    for arm in ("reachability", "system shape", "tests", "performance"):
        assert arm in lower, (
            f"debt-rounds.md 'Census arms' section does not name the {arm!r} arm"
        )


def test_debt_rounds_census_arms_numbered_exactly_four():
    section = _census_arms_section()
    numbers = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+)\. \*\*", section)]
    assert numbers == [1, 2, 3, 4], (
        f"debt-rounds.md 'Census arms' section is not numbered exactly 1..4: got {numbers}"
    )


def test_debt_rounds_requires_every_census_to_report_ran_and_carried_forward_per_arm():
    section = _flat(_census_arms_section()).lower()
    assert "whether that arm ran this round" in section or (
        "whether" in section and "ran" in section
    ), (
        "debt-rounds.md 'Census arms' section does not require every census to report whether "
        "each arm ran this round"
    )
    assert "carried forward unmeasured" in section, (
        "debt-rounds.md 'Census arms' section does not require reporting what an arm carried "
        "forward unmeasured"
    )
    assert "silently absent" in section, (
        "debt-rounds.md 'Census arms' section does not state a silently absent arm reads as a "
        "defect in the census"
    )


def test_debt_census_has_arm_coverage_section_with_all_four_arms():
    text = _census()
    section = _section(text, "## Arm coverage", ["## Baselines"])
    header = "| Arm | Ran this round | Carried forward unmeasured |"
    assert header in section, (
        f"templates/debt-census.md is missing the Arm coverage table header {header!r}"
    )
    for arm in ("Reachability", "System shape", "Tests", "Performance"):
        row = f"| {arm} |"
        assert row in section, (
            f"templates/debt-census.md Arm coverage table is missing the {arm!r} row"
        )


def test_debt_census_arm_coverage_precedes_baselines_and_follows_inputs_mined():
    text = _census()
    arm_idx = text.find("## Arm coverage")
    inputs_idx = text.find("## Inputs mined")
    baselines_idx = text.find("## Baselines")
    assert -1 not in (arm_idx, inputs_idx, baselines_idx)
    assert inputs_idx < arm_idx < baselines_idx, (
        "templates/debt-census.md 'Arm coverage' section is not ordered between 'Inputs mined' "
        "and 'Baselines'"
    )


# ---------------------------------------------------------------------------
# AC2 — an excluded candidate axis carries its argument; an unmentioned axis is
# never treated as excluded
# ---------------------------------------------------------------------------

def test_debt_rounds_states_exclusion_requires_argument_and_silence_is_not_exclusion():
    section = _flat(_census_arms_section()).lower()
    assert "excluded only when this section records the exclusion with its argument" in section \
        or ("excluded" in section and "argument" in section), (
        "debt-rounds.md 'Census arms' section does not require an excluded candidate axis to "
        "carry its argument"
    )
    assert "never by silence" in section, (
        "debt-rounds.md 'Census arms' section does not state exclusion never happens by silence"
    )
    assert "not thereby excluded" in section or "not treated as excluded" in section, (
        "debt-rounds.md 'Census arms' section does not state an axis this canon has not "
        "mentioned is not thereby excluded"
    )


def test_debt_census_has_excluded_candidate_axes_slot_that_defaults_to_none_not_silence():
    text = _census()
    section = _section(text, "## Arm coverage", ["## Baselines"])
    assert "Excluded candidate axes" in section, (
        "templates/debt-census.md 'Arm coverage' section is missing the 'Excluded candidate "
        "axes' slot"
    )
    assert "unmentioned axis is never treated as excluded" in section, (
        "templates/debt-census.md 'Excluded candidate axes' slot does not restate that an "
        "unmentioned axis is never treated as excluded"
    )


# ---------------------------------------------------------------------------
# AC3 — the reachability arm's third partition: reached in production, exercised
# by no test — distinct from the other two partitions
# ---------------------------------------------------------------------------

def test_debt_rounds_reachability_arm_states_three_partitions_not_two():
    section = _flat(_census_arms_section()).lower()
    assert "not two" in section, (
        "debt-rounds.md reachability arm does not state it partitions into three sets, not two"
    )
    assert "reached by nothing" in section, (
        "debt-rounds.md reachability arm does not name the 'reached by nothing' partition"
    )
    assert "reached only by tests" in section, (
        "debt-rounds.md reachability arm does not name the 'reached only by tests' partition"
    )
    assert "reached in production and exercised by no test" in section, (
        "debt-rounds.md reachability arm does not name the third partition — reached in "
        "production and exercised by no test"
    )
    assert "third partition" in section, (
        "debt-rounds.md reachability arm does not call out the third partition as such"
    )


def test_debt_rounds_third_partition_falls_out_of_same_walk_and_is_a_list_not_a_ratio():
    section = _flat(_census_arms_section()).lower()
    assert "same call-graph walk" in section, (
        "debt-rounds.md reachability arm does not state the third partition falls out of the "
        "same call-graph walk as the other two"
    )
    assert "list of names" in section, (
        "debt-rounds.md reachability arm does not require the third partition be reported as a "
        "list of names"
    )
    assert "never collapsed into a ratio" in section or "never a ratio" in section, (
        "debt-rounds.md reachability arm does not state the third partition must not be "
        "collapsed into a ratio"
    )


def test_debt_census_reachability_ledger_reports_third_partition_as_named_list():
    text = _census()
    section = _section(text, "## Reachability ledger", ["## System shape"])
    assert "Reached in production, exercised by no test" in section, (
        "templates/debt-census.md Reachability ledger is missing the third-partition slot "
        "'Reached in production, exercised by no test'"
    )
    header = "| Symbol |"
    assert header in section, (
        f"templates/debt-census.md third-partition slot is missing the {header!r} table header "
        "(a list of names, not a ratio)"
    )
    lower = section.lower()
    assert "distinct from" in lower, (
        "templates/debt-census.md third-partition slot does not state it is distinct from the "
        "other two partitions"
    )


def test_debt_census_reachability_ledger_table_still_has_dead_and_untested_classes():
    text = _census()
    section = _section(text, "## Reachability ledger", ["## System shape"])
    assert "live / untested / dead" in section, (
        "templates/debt-census.md Reachability ledger table no longer offers the live/untested/"
        "dead class options — the pre-existing two partitions must stay, the third is additive"
    )


# ---------------------------------------------------------------------------
# AC4 — the system-shape arm: declared arm of every census, system-scope, rules
# the intended shape rather than only enumerating instances
# ---------------------------------------------------------------------------

def test_debt_rounds_system_shape_arm_is_declared_arm_of_every_census():
    section = _flat(_census_arms_section()).lower()
    assert "system shape" in section
    assert "declared arm of every census" in section, (
        "debt-rounds.md does not state the system-shape arm is a declared arm of every census"
    )
    assert "macro view" in section, (
        "debt-rounds.md does not call the system-shape arm the round's macro view"
    )
    assert "scope is the system" in section, (
        "debt-rounds.md does not state the system-shape arm's scope is the system rather than "
        "any single change"
    )


def test_debt_rounds_system_shape_arm_names_the_three_example_shapes():
    section = _flat(_census_arms_section()).lower()
    for phrase in (
        "consumer count",
        "forked conventions",
        "duplicated home",
    ):
        assert phrase in section, (
            f"debt-rounds.md system-shape arm does not name the example shape {phrase!r}"
        )


def test_debt_rounds_system_shape_arm_rules_intended_shape_not_only_enumerates():
    section = _flat(_census_arms_section()).lower()
    assert "rules the intended shape" in section, (
        "debt-rounds.md system-shape arm does not state it rules the intended shape for each "
        "shape found"
    )
    assert "not only enumerate" in section or "never only enumerate" in section, (
        "debt-rounds.md system-shape arm does not state it must not stop at only enumerating "
        "instances"
    )
    assert "survives the round that made it" in section, (
        "debt-rounds.md system-shape arm does not state the ruling survives the round that made "
        "it (i.e. hands off to a later guard)"
    )


def test_debt_rounds_system_shape_arm_is_exempt_from_surface_reduction_wall_8():
    section = _flat(_census_arms_section()).lower()
    assert "wall 8" in section or "exempt" in section, (
        "debt-rounds.md system-shape arm does not tie itself to the per-arm exemption (wall 8)"
    )


def test_debt_census_system_shape_section_has_ruling_column_not_only_instances():
    text = _census()
    section = _section(text, "## System shape", ["## Duplication"])
    header_line = None
    for line in section.splitlines():
        if line.strip().startswith("| Shape") or line.strip().startswith("|Shape"):
            header_line = line
            break
    assert header_line is not None, (
        "templates/debt-census.md 'System shape' section is missing its table header row"
    )
    assert "Instances found" in header_line, (
        "templates/debt-census.md System shape table is missing an 'Instances found' column"
    )
    assert "Ruling" in header_line and "intended shape" in header_line.lower(), (
        "templates/debt-census.md System shape table is missing a 'Ruling: intended shape' "
        "column — the arm must rule, not only enumerate"
    )


def test_debt_census_system_shape_section_carries_the_three_named_examples():
    text = _census()
    section = _section(text, "## System shape", ["## Duplication"])
    lower = section.lower()
    for phrase in ("consumer count", "forked conventions", "duplicated home"):
        assert phrase in lower, (
            f"templates/debt-census.md 'System shape' section does not carry the example row "
            f"{phrase!r}"
        )


def test_debt_census_system_shape_section_is_marked_whole_tree_exempt():
    text = _census()
    section = _section(text, "## System shape", ["## Duplication"])
    assert "**Coverage:** whole tree" in section, (
        "templates/debt-census.md 'System shape' section does not declare itself whole-tree "
        "exempt per the per-arm exemption"
    )


# ---------------------------------------------------------------------------
# Constraint — never call the arm an "architect arm"; architect.md untouched
# ---------------------------------------------------------------------------

def test_arm_is_never_called_an_architect_arm_in_touched_files():
    for path, text in ((DEBT_ROUNDS, _rounds()), (DEBT_CENSUS, _census())):
        assert "architect arm" not in text.lower(), (
            f"{path} calls the system-shape arm an 'architect arm' — the concern is the "
            "architect's kind, but the name must stay the arm's own"
        )


def test_debt_rounds_names_architect_reference_without_renaming_its_role():
    section = _flat(_census_arms_section()).lower()
    assert "architect.md" in section, (
        "debt-rounds.md system-shape arm does not cite architect.md for the kind of judgment "
        "behind it"
    )
    assert "never a fourth stage" in section or "never a fourth" in section, (
        "debt-rounds.md does not restate that architect.md binds the architect role to three "
        "moments and never a fourth stage"
    )


def test_architect_reference_file_is_not_modified_by_this_slice():
    assert ARCHITECT.exists(), "skills/factory/references/architect.md is expected to exist"
    text = ARCHITECT.read_text(encoding="utf-8")
    assert "three moments" in text.lower() or "three named moments" in text.lower(), (
        "skills/factory/references/architect.md no longer names the architect role's three "
        "moments — this slice must not touch that file"
    )


# ---------------------------------------------------------------------------
# Constraint — no fifth axis is added
# ---------------------------------------------------------------------------

def test_debt_rounds_does_not_add_a_fifth_axis():
    section = _census_arms_section()
    numbers = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+)\. \*\*", section)]
    assert 5 not in numbers, "debt-rounds.md 'Census arms' section adds a fifth numbered arm"
    assert "no fifth" in section.lower() or "closed at four" in section.lower(), (
        "debt-rounds.md 'Census arms' section does not guard against a fifth axis"
    )


def test_debt_census_arm_coverage_table_has_exactly_four_arm_rows():
    text = _census()
    section = _section(text, "## Arm coverage", ["## Baselines"])
    rows = [
        line for line in section.splitlines()
        if line.strip().startswith("|") and "Ran this round" not in line
        and not re.match(r"^\|[-\s|]+\|$", line.strip())
    ]
    arm_rows = [r for r in rows if any(
        arm in r for arm in ("Reachability", "System shape", "Tests", "Performance")
    )]
    assert len(arm_rows) == 4, (
        f"templates/debt-census.md Arm coverage table does not have exactly four arm rows: "
        f"got {arm_rows}"
    )
