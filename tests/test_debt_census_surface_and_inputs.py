"""
Tests for issue #358 — Debt round: the census declares the surface it swept, and mines its
inputs before sweeping (technical-RFC slice P1 of epic #357).

Derived from the issue #358 acceptance criteria (the spec), not from the doc-editor's own
wording:

  1. Every census declares its swept surface as three machine-readable fields — a baseline ref,
     an include rule, an exclude rule — and the next round's surface is defined as the tree
     today minus the files of that declared surface unchanged since that ref.
  2. The exclude rule applies to both terms of that subtraction, so an excluded path never
     re-enters the surface in a later round.
  3. An arm whose findings depend on relationships no single change can exhibit is exempt from
     surface reduction and declares that it read the whole tree.
  4. Every census excludes generated evidence (naming each exclusion and its size) and reports
     tests separately from production.
  5. A census mines its four declared inputs — surface, nit clusters, backlog seeds, prior
     carry-forward — in that fixed order, before any sweep, citing the input that already held
     any finding it reports.

Plus the stated constraints: the named template sections that predate this issue (Baselines,
Reachability ledger, Duplication / consolidation sets, Unknowns, Revisit trigger) are added to,
never reordered, and the record-grammar / counter sections of debt-rounds.md are untouched.

House doc-pin style, in the manner of tests/test_templates_declaration.py and
tests/test_contract_surface_docs.py — read the shipped file, assert its load-bearing content.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
DEBT_ROUNDS = REFS / "debt-rounds.md"
DEBT_CENSUS = ROOT / "templates" / "debt-census.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _rounds():
    return _text(DEBT_ROUNDS)


def _census():
    return _text(DEBT_CENSUS)


def _walls_section():
    text = _rounds()
    start = text.find("## The walls")
    end = text.find("## Record grammars")
    assert start != -1, "debt-rounds.md is missing the 'The walls' section heading"
    assert end != -1, "debt-rounds.md is missing the 'Record grammars' section heading"
    assert start < end
    return text[start:end]


# ---------------------------------------------------------------------------
# AC1 — the swept-surface declaration + subtraction definition (debt-rounds.md)
# ---------------------------------------------------------------------------

def test_debt_rounds_states_swept_surface_declared_as_three_fields():
    section = _walls_section()
    lower = section.lower()
    assert "baseline" in lower and "ref" in lower, (
        "debt-rounds.md walls do not name a baseline ref as a declared surface field"
    )
    assert "include" in lower and "rule" in lower, (
        "debt-rounds.md walls do not name an include rule as a declared surface field"
    )
    assert "exclude" in lower and "rule" in lower, (
        "debt-rounds.md walls do not name an exclude rule as a declared surface field"
    )
    assert "three" in lower, (
        "debt-rounds.md walls do not state the surface is declared as exactly three fields"
    )
    assert "machine-readable" in lower, (
        "debt-rounds.md walls do not state the surface declaration is machine-readable"
    )


def test_debt_rounds_states_surface_subtraction_definition():
    section = _walls_section().lower()
    assert "tree today" in section, (
        "debt-rounds.md walls do not define the next round's surface against 'the tree today'"
    )
    assert "unchanged since" in section, (
        "debt-rounds.md walls do not define the subtracted term as files unchanged since the "
        "baseline ref"
    )
    assert re.search(r"[-−]", section), (
        "debt-rounds.md walls do not state the surface as a subtraction"
    )
    assert "boundary" in section, (
        "debt-rounds.md walls do not frame the surface as the round's boundary (coverage-based, "
        "not temporal)"
    )


# ---------------------------------------------------------------------------
# AC2 — the exclude rule applies to both terms of the subtraction
# ---------------------------------------------------------------------------

def test_debt_rounds_states_exclude_rule_applies_to_both_terms():
    section = _walls_section().lower()
    assert "both terms" in section, (
        "debt-rounds.md walls do not state the exclude rule applies to both terms of the "
        "subtraction"
    )
    assert "never re-enter" in section or "never re-enters" in section, (
        "debt-rounds.md walls do not state an excluded path never re-enters the surface in a "
        "later round"
    )


# ---------------------------------------------------------------------------
# AC3 — per-arm exemption for relationship-dependent findings
# ---------------------------------------------------------------------------

def test_debt_rounds_states_per_arm_exemption():
    section = _walls_section().lower()
    assert "per arm" in section or "per-arm" in section, (
        "debt-rounds.md walls do not scope surface reduction per arm of the census"
    )
    assert "no single change" in section, (
        "debt-rounds.md walls do not name findings that depend on relationships no single change "
        "can exhibit"
    )
    assert "exempt" in section, (
        "debt-rounds.md walls do not state such an arm is exempt from surface reduction"
    )
    assert "whole tree" in section, (
        "debt-rounds.md walls do not state the exempt arm declares it read the whole tree"
    )
    assert "declar" in section, (
        "debt-rounds.md walls do not state the whole-tree read is a declared obligation, not an "
        "inferred one"
    )


# ---------------------------------------------------------------------------
# AC4 — generated evidence excluded (named + sized); tests reported apart from production
# ---------------------------------------------------------------------------

def test_debt_rounds_states_generated_evidence_excluded_and_sized():
    section = _walls_section().lower()
    assert "generated evidence" in section, (
        "debt-rounds.md walls do not name generated evidence as excluded from the surface"
    )
    assert "size" in section, (
        "debt-rounds.md walls do not require each generated-evidence exclusion to name its size"
    )


def test_debt_rounds_states_tests_reported_separately_from_production():
    section = _walls_section().lower()
    assert "separately from production" in section or "separately" in section, (
        "debt-rounds.md walls do not require tests to be reported separately from production"
    )
    assert "production" in section and "tests" in section


# ---------------------------------------------------------------------------
# AC5 — fixed input order, mined before any sweep, citing the input that already held a finding
# ---------------------------------------------------------------------------

def test_debt_rounds_states_fixed_input_order_before_sweep():
    section = _walls_section().lower()
    assert "before" in section and "sweep" in section, (
        "debt-rounds.md walls do not state the inputs are mined before any sweep"
    )
    assert "fixed order" in section, (
        "debt-rounds.md walls do not state the inputs are read in a fixed order"
    )
    declared_idx = section.find("declared surface")
    nit_idx = section.find("nit cluster")
    backlog_idx = section.find("backlog seed")
    carry_idx = section.find("carry-forward")
    for name, idx in (
        ("declared surface", declared_idx),
        ("nit clusters", nit_idx),
        ("open backlog seeds", backlog_idx),
        ("prior carry-forward", carry_idx),
    ):
        assert idx != -1, f"debt-rounds.md walls do not name '{name}' as a mined input"
    assert declared_idx < nit_idx < backlog_idx < carry_idx, (
        "debt-rounds.md walls do not name the four mined inputs in the fixed order: declared "
        "surface, nit clusters, open backlog seeds, prior carry-forward"
    )


def test_debt_rounds_states_findings_cited_to_input_never_rederived():
    section = _walls_section().lower()
    assert "cite" in section or "cited" in section, (
        "debt-rounds.md walls do not require a finding already held by an input to be cited to it"
    )
    assert "never re-derived" in section or "never rederived" in section or "re-derives" in section, (
        "debt-rounds.md walls do not state a finding already held by an input must not be "
        "re-derived"
    )


# ---------------------------------------------------------------------------
# Walls numbering stays contiguous (1-10), and walls 1-6 are untouched
# ---------------------------------------------------------------------------

def test_debt_rounds_walls_are_numbered_one_through_ten_contiguous():
    section = _walls_section()
    numbers = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+)\. \*\*", section)]
    assert numbers == list(range(1, 11)), (
        f"debt-rounds.md walls are not numbered 1..10 contiguously: got {numbers}"
    )


def test_debt_rounds_pre_existing_walls_titles_unchanged():
    section = _walls_section()
    pre_existing_titles = [
        "Census with a reachability ledger.",
        "By-name scope.",
        "Pin-then-prune.",
        "Birth citation.",
        "One item = one revertible chain.",
        "The prune review bar.",
    ]
    for title in pre_existing_titles:
        assert title in section, (
            f"debt-rounds.md walls no longer carry the pre-existing wall {title!r} — walls 1-6 "
            "must stay untouched by this slice"
        )


# ---------------------------------------------------------------------------
# Out of scope: the record grammars and counter sections of debt-rounds.md are untouched
# ---------------------------------------------------------------------------

def test_debt_rounds_record_grammars_section_still_declares_five_grammars():
    text = _rounds()
    start = text.find("## Record grammars")
    end = text.find("## The counter")
    assert start != -1 and end != -1 and start < end
    section = text[start:end]
    assert "Five grammars" in section, (
        "debt-rounds.md 'Record grammars' section no longer opens with 'Five grammars' — this "
        "slice must not touch the record grammars"
    )
    assert "YR-DEBT-SURFACE" not in section, (
        "debt-rounds.md 'Record grammars' section carries a new surface-declaration grammar — "
        "the swept-surface block belongs to the census template, not a new record grammar"
    )


def test_debt_rounds_counter_section_untouched():
    text = _rounds()
    start = text.find("## The counter")
    end = text.find("## The raise")
    assert start != -1 and end != -1 and start < end
    section = text[start:end]
    assert "debt_round_every" in section, (
        "debt-rounds.md 'The counter' section no longer names debt_round_every — this slice must "
        "not touch the counter"
    )
    assert "anchor" in section.lower()


# ---------------------------------------------------------------------------
# AC1 — templates/debt-census.md carries the surface-declaration block with all three fields
# ---------------------------------------------------------------------------

def _swept_surface_section():
    text = _census()
    start = text.find("## Swept surface")
    end = text.find("## ", start + 1)
    assert start != -1, "templates/debt-census.md is missing a 'Swept surface' section heading"
    assert end != -1
    return text[start:end]


def _fenced_block_in(section):
    lines = section.splitlines()
    fence_idxs = [i for i, line in enumerate(lines) if line.strip() == "```"]
    assert len(fence_idxs) >= 2, "expected a fenced code block (```...```) in the section"
    start, end = fence_idxs[0], fence_idxs[1]
    return "\n".join(lines[start + 1:end])


def test_debt_census_has_swept_surface_section_with_fenced_declaration_block():
    section = _swept_surface_section()
    block = _fenced_block_in(section)
    assert re.search(r"(?m)^baseline\s*:", block), (
        "templates/debt-census.md swept-surface block is missing a 'baseline:' field"
    )
    assert re.search(r"(?m)^include\s*:", block), (
        "templates/debt-census.md swept-surface block is missing an 'include:' field"
    )
    assert re.search(r"(?m)^exclude\s*:", block), (
        "templates/debt-census.md swept-surface block is missing an 'exclude:' field"
    )


def test_debt_census_swept_surface_section_states_subtraction_and_both_terms_rule():
    section = _swept_surface_section().lower()
    assert "tree today" in section, (
        "templates/debt-census.md swept-surface section does not restate the tree-today term"
    )
    assert "unchanged since" in section, (
        "templates/debt-census.md swept-surface section does not restate the unchanged-since term"
    )
    assert "both terms" in section, (
        "templates/debt-census.md swept-surface section does not restate the both-terms exclude "
        "rule"
    )
    assert "never re-enter" in section or "never re-enters" in section, (
        "templates/debt-census.md swept-surface section does not restate that an excluded path "
        "never re-enters the surface"
    )


def test_debt_census_swept_surface_section_names_generated_evidence_exclusions_with_size():
    section = _swept_surface_section()
    assert "Generated evidence excluded" in section, (
        "templates/debt-census.md swept-surface section is missing the generated-evidence-"
        "excluded slot"
    )
    header = "| Exclusion | Size |"
    assert header in section, (
        "templates/debt-census.md is missing the generated-evidence exclusion table header "
        f"{header!r}"
    )


# ---------------------------------------------------------------------------
# AC5 — templates/debt-census.md carries an Inputs-mined section, fixed order, with citation
# ---------------------------------------------------------------------------

def _inputs_mined_section():
    text = _census()
    start = text.find("## Inputs mined")
    end = text.find("## ", start + 1)
    assert start != -1, "templates/debt-census.md is missing an 'Inputs mined' section heading"
    assert end != -1
    return text[start:end]


def test_debt_census_has_inputs_mined_section_with_citation_table():
    section = _inputs_mined_section()
    header = "| Input | Already held | Cite |"
    assert header in section, (
        f"templates/debt-census.md Inputs mined table is missing the expected header {header!r}"
    )


def test_debt_census_inputs_mined_rows_are_in_the_fixed_order():
    section = _inputs_mined_section()
    declared_idx = section.find("Declared surface")
    nit_idx = section.find("Nit clusters")
    backlog_idx = section.find("Open backlog seeds")
    carry_idx = section.find("Prior carry-forward")
    for name, idx in (
        ("Declared surface", declared_idx),
        ("Nit clusters", nit_idx),
        ("Open backlog seeds", backlog_idx),
        ("Prior carry-forward", carry_idx),
    ):
        assert idx != -1, f"templates/debt-census.md Inputs mined table is missing a {name!r} row"
    assert declared_idx < nit_idx < backlog_idx < carry_idx, (
        "templates/debt-census.md Inputs mined table rows are not in the fixed order: declared "
        "surface, nit clusters, open backlog seeds, prior carry-forward"
    )


def test_debt_census_inputs_mined_section_precedes_baselines():
    text = _census()
    inputs_idx = text.find("## Inputs mined")
    baselines_idx = text.find("## Baselines")
    swept_idx = text.find("## Swept surface")
    assert -1 not in (inputs_idx, baselines_idx, swept_idx)
    assert swept_idx < inputs_idx < baselines_idx, (
        "templates/debt-census.md sections are not ordered Swept surface, then Inputs mined, "
        "then Baselines"
    )


# ---------------------------------------------------------------------------
# AC3 — per-arm exemption reachable from the census template's coverage lines
# ---------------------------------------------------------------------------

def _section(heading, next_headings):
    text = _census()
    start = text.find(heading)
    assert start != -1, f"templates/debt-census.md is missing the {heading!r} section heading"
    end = len(text)
    for nxt in next_headings:
        idx = text.find(nxt, start + 1)
        if idx != -1:
            end = min(end, idx)
    return text[start:end]


def test_debt_census_reachability_ledger_has_per_arm_coverage_declaration():
    section = _section("## Reachability ledger", ["## Duplication"])
    assert "**Coverage:**" in section, (
        "templates/debt-census.md Reachability ledger is missing a 'Coverage:' declaration line"
    )
    assert "whole tree" in section, (
        "templates/debt-census.md Reachability ledger coverage line does not offer the whole-tree "
        "exemption option"
    )
    assert "per-arm exemption" in section or "per arm exemption" in section, (
        "templates/debt-census.md Reachability ledger coverage line does not name the per-arm "
        "exemption"
    )


def test_debt_census_duplication_section_has_per_arm_coverage_declaration():
    section = _section("## Duplication / consolidation sets", ["## Unknowns"])
    assert "**Coverage:**" in section, (
        "templates/debt-census.md Duplication / consolidation sets is missing a 'Coverage:' "
        "declaration line"
    )
    assert "whole tree" in section, (
        "templates/debt-census.md Duplication / consolidation sets coverage line does not offer "
        "the whole-tree exemption option"
    )


# ---------------------------------------------------------------------------
# AC4 — templates/debt-census.md Baselines section reports tests separately from production
# ---------------------------------------------------------------------------

def test_debt_census_baselines_reports_tests_separately_from_production():
    section = _section("## Baselines", ["## Reachability ledger"])
    assert "Tracked files (production)" in section, (
        "templates/debt-census.md Baselines section does not report tracked files for production "
        "separately"
    )
    assert "Tracked files (tests)" in section, (
        "templates/debt-census.md Baselines section does not report tracked files for tests "
        "separately"
    )
    assert "Tracked lines (production)" in section, (
        "templates/debt-census.md Baselines section does not report tracked lines for production "
        "separately"
    )
    assert "Tracked lines (tests)" in section, (
        "templates/debt-census.md Baselines section does not report tracked lines for tests "
        "separately"
    )


# ---------------------------------------------------------------------------
# Constraint — the pre-existing named sections are added to, never reordered
# ---------------------------------------------------------------------------

def test_debt_census_pre_existing_sections_stay_in_original_relative_order():
    text = _census()
    headings = [
        "## Baselines",
        "## Reachability ledger",
        "## Duplication / consolidation sets",
        "## Unknowns",
        "## Revisit trigger",
    ]
    positions = []
    for heading in headings:
        idx = text.find(heading)
        assert idx != -1, f"templates/debt-census.md is missing the {heading!r} section heading"
        positions.append(idx)
    assert positions == sorted(positions), (
        "templates/debt-census.md pre-existing sections were reordered — expected "
        f"{headings} to stay in that relative order, got positions {positions}"
    )


def test_debt_census_new_sections_do_not_follow_the_pre_existing_sections():
    """The new Swept surface / Inputs mined sections must be added ahead of the pre-existing
    block (between Supersedes and Baselines), not appended after Revisit trigger — appending
    them at the end would not read as 'declared before any sweep'."""
    text = _census()
    swept_idx = text.find("## Swept surface")
    inputs_idx = text.find("## Inputs mined")
    baselines_idx = text.find("## Baselines")
    revisit_idx = text.find("## Revisit trigger")
    assert -1 not in (swept_idx, inputs_idx, baselines_idx, revisit_idx)
    assert swept_idx < baselines_idx and inputs_idx < baselines_idx, (
        "templates/debt-census.md's new Swept surface / Inputs mined sections must precede "
        "Baselines, not trail after the pre-existing sections"
    )
    assert swept_idx < revisit_idx and inputs_idx < revisit_idx


# ---------------------------------------------------------------------------
# Constraint — out of scope: this slice does not define the axis set (that is slice P2)
# ---------------------------------------------------------------------------

def test_debt_census_does_not_define_an_axis_set():
    text = _census().lower()
    assert "axis set" not in text and "## axes" not in text, (
        "templates/debt-census.md defines an axis set — that is out of scope for issue #358 "
        "(slice P2's job)"
    )
