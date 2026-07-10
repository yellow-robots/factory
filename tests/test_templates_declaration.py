"""
Tests for Issue #83 — Templates: product-spec and feature-rfc carry the
declaration (skill/reference text only; no version bump this slice).

Derived from the Issue #83 acceptance criteria (the spec), not from the
implementation internals. This is a doc-pin suite in the house style of
tests/test_check_model_refs.py — read the template file, assert content —
pinning the new `supersedes` scaffold in both authoring templates so it
cannot silently regress:

  - the `supersedes: []` frontmatter scaffold line with its inline guidance
    (targets are quoted wikilinks of the active designs this doc replaces;
    empty is allowed but must be justified in the body; stamped superseded
    at accept)
  - the `**Supersedes:** nothing — <justification>` body slot
  - the HTML comment stating the keep/replace/drop rule for that slot

Plus out-of-scope guards: templates/task.md and templates/technical-rfc.md
must not gain a supersedes scaffold (tasks never declare; the technical-rfc
lives on the epic Issue).

Extended for Issue #92 — Templates: the debt census and the debt-round spec
carry the walls. Per #92's stated precondition, this file only exists once
#83 has merged, so this slice extends it rather than adding a new test
file. The additions below pin templates/debt-round-spec.md (a product-spec
carrying the round's walls: scope-by-name, pin-then-prune ordering, the
per-prune acceptance scaffold, the suite-duration canary, EARS, and the
round-close duties) and templates/debt-census.md (a research doc carrying
the reachability ledger, baselines, duplication sets, unknowns, and the
revisit trigger) — house doc-pin style, reading the template files and
asserting their load-bearing strings.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
PRODUCT_SPEC = TEMPLATES / "product-spec.md"
FEATURE_RFC = TEMPLATES / "feature-rfc.md"
TASK = TEMPLATES / "task.md"
TECHNICAL_RFC = TEMPLATES / "technical-rfc.md"
DEBT_ROUND_SPEC = TEMPLATES / "debt-round-spec.md"
DEBT_CENSUS = TEMPLATES / "debt-census.md"

# Built via concatenation (not a literal) so this file's own source text
# doesn't trip tools/check_model_refs.py's un-allowlisted-reference scan.
_RETIRED_CONVENTIONS_DOC = "01" + "-conventions"


def _text(path):
    return path.read_text(encoding="utf-8")


def _frontmatter(text):
    """Return the lines strictly between the opening and closing '---' fences."""
    lines = text.splitlines()
    assert lines[0] == "---", "template does not open with a '---' frontmatter fence"
    end = next(i for i in range(1, len(lines)) if lines[i] == "---")
    return lines[1:end]


# ---------------------------------------------------------------------------
# product-spec.md — frontmatter scaffold line
# ---------------------------------------------------------------------------

def test_product_spec_frontmatter_has_supersedes_scaffold_line():
    fm = _frontmatter(_text(PRODUCT_SPEC))
    scaffold = next((line for line in fm if line.startswith("supersedes: []")), None)
    assert scaffold, "templates/product-spec.md frontmatter is missing a 'supersedes: []' scaffold line"


def test_product_spec_frontmatter_scaffold_follows_status():
    fm = _frontmatter(_text(PRODUCT_SPEC))
    status_idx = next((i for i, line in enumerate(fm) if line.startswith("status:")), None)
    assert status_idx is not None, "templates/product-spec.md frontmatter is missing a 'status:' line"
    scaffold_idx = next((i for i, line in enumerate(fm) if line.startswith("supersedes: []")), None)
    assert scaffold_idx is not None, "templates/product-spec.md frontmatter is missing a 'supersedes: []' scaffold line"
    assert scaffold_idx == status_idx + 1, (
        "templates/product-spec.md 'supersedes: []' scaffold line does not immediately follow 'status:'"
    )


def test_product_spec_frontmatter_scaffold_has_inline_guidance():
    fm = _frontmatter(_text(PRODUCT_SPEC))
    idx = next(i for i, line in enumerate(fm) if line.startswith("supersedes: []"))
    guidance = " ".join(fm[idx:idx + 2])
    assert "[[wikilinks]]" in guidance, (
        "templates/product-spec.md supersedes scaffold does not name quoted wikilinks as the target format"
    )
    assert "justified in the body" in guidance, (
        "templates/product-spec.md supersedes scaffold does not note an empty list must be justified in the body"
    )
    assert "superseded at accept" in guidance, (
        "templates/product-spec.md supersedes scaffold does not note targets are stamped superseded at accept"
    )


# ---------------------------------------------------------------------------
# product-spec.md — body slot
# ---------------------------------------------------------------------------

def test_product_spec_body_has_supersedes_slot():
    text = _text(PRODUCT_SPEC)
    lines = text.splitlines()
    slot = next((line for line in lines if line.startswith("**Supersedes:** nothing")), None)
    assert slot, "templates/product-spec.md body is missing the '**Supersedes:** nothing — …' slot line"
    assert "justification" in slot, (
        "templates/product-spec.md supersedes slot does not carry a justification placeholder"
    )


def test_product_spec_body_slot_has_justification_rule_comment():
    text = _text(PRODUCT_SPEC)
    lines = text.splitlines()
    slot_idx = next(i for i, line in enumerate(lines) if line.startswith("**Supersedes:** nothing"))
    following = " ".join(lines[slot_idx + 1:slot_idx + 3])
    assert following.strip().startswith("<!--"), (
        "templates/product-spec.md supersedes slot is not followed by an HTML comment stating the rule"
    )
    assert "empty" in following, (
        "templates/product-spec.md supersedes rule comment does not cover the empty-list case"
    )
    assert "non-empty" in following, (
        "templates/product-spec.md supersedes rule comment does not cover the non-empty-list case"
    )
    assert "replace" in following and "drop" in following, (
        "templates/product-spec.md supersedes rule comment does not instruct replacing or dropping the line "
        "once the list is non-empty"
    )


def test_product_spec_supersedes_slot_precedes_why_section():
    text = _text(PRODUCT_SPEC)
    slot_pos = text.find("**Supersedes:** nothing")
    why_pos = text.find("## Why")
    assert slot_pos != -1, "templates/product-spec.md is missing the supersedes slot"
    assert why_pos != -1, "templates/product-spec.md is missing the '## Why' section"
    assert slot_pos < why_pos, (
        "templates/product-spec.md supersedes slot must appear before the '## Why' section"
    )


# ---------------------------------------------------------------------------
# feature-rfc.md — frontmatter scaffold line
# ---------------------------------------------------------------------------

def test_feature_rfc_frontmatter_has_supersedes_scaffold_line():
    fm = _frontmatter(_text(FEATURE_RFC))
    scaffold = next((line for line in fm if line.startswith("supersedes: []")), None)
    assert scaffold, "templates/feature-rfc.md frontmatter is missing a 'supersedes: []' scaffold line"


def test_feature_rfc_frontmatter_scaffold_after_status():
    # feature-rfc.md also carries 'source_spec:' between 'status:' and the
    # supersedes scaffold, so adjacency isn't required here — only ordering.
    fm = _frontmatter(_text(FEATURE_RFC))
    status_idx = next((i for i, line in enumerate(fm) if line.startswith("status:")), None)
    assert status_idx is not None, "templates/feature-rfc.md frontmatter is missing a 'status:' line"
    scaffold_idx = next((i for i, line in enumerate(fm) if line.startswith("supersedes: []")), None)
    assert scaffold_idx is not None, "templates/feature-rfc.md frontmatter is missing a 'supersedes: []' scaffold line"
    assert scaffold_idx > status_idx, (
        "templates/feature-rfc.md 'supersedes: []' scaffold line does not come after 'status:'"
    )


def test_feature_rfc_frontmatter_scaffold_has_inline_guidance():
    fm = _frontmatter(_text(FEATURE_RFC))
    idx = next(i for i, line in enumerate(fm) if line.startswith("supersedes: []"))
    guidance = " ".join(fm[idx:idx + 2])
    assert "[[wikilinks]]" in guidance, (
        "templates/feature-rfc.md supersedes scaffold does not name quoted wikilinks as the target format"
    )
    assert "justified in the body" in guidance, (
        "templates/feature-rfc.md supersedes scaffold does not note an empty list must be justified in the body"
    )
    assert "superseded at accept" in guidance, (
        "templates/feature-rfc.md supersedes scaffold does not note targets are stamped superseded at accept"
    )


# ---------------------------------------------------------------------------
# feature-rfc.md — body slot
# ---------------------------------------------------------------------------

def test_feature_rfc_body_has_supersedes_slot():
    text = _text(FEATURE_RFC)
    lines = text.splitlines()
    slot = next((line for line in lines if line.startswith("**Supersedes:** nothing")), None)
    assert slot, "templates/feature-rfc.md body is missing the '**Supersedes:** nothing — …' slot line"
    assert "justification" in slot, (
        "templates/feature-rfc.md supersedes slot does not carry a justification placeholder"
    )


def test_feature_rfc_body_slot_has_justification_rule_comment():
    text = _text(FEATURE_RFC)
    lines = text.splitlines()
    slot_idx = next(i for i, line in enumerate(lines) if line.startswith("**Supersedes:** nothing"))
    following = " ".join(lines[slot_idx + 1:slot_idx + 3])
    assert following.strip().startswith("<!--"), (
        "templates/feature-rfc.md supersedes slot is not followed by an HTML comment stating the rule"
    )
    assert "empty" in following, (
        "templates/feature-rfc.md supersedes rule comment does not cover the empty-list case"
    )
    assert "non-empty" in following, (
        "templates/feature-rfc.md supersedes rule comment does not cover the non-empty-list case"
    )
    assert "replace" in following and "drop" in following, (
        "templates/feature-rfc.md supersedes rule comment does not instruct replacing or dropping the line "
        "once the list is non-empty"
    )


def test_feature_rfc_supersedes_slot_precedes_outline_section():
    text = _text(FEATURE_RFC)
    slot_pos = text.find("**Supersedes:** nothing")
    outline_pos = text.find("## Outline")
    assert slot_pos != -1, "templates/feature-rfc.md is missing the supersedes slot"
    assert outline_pos != -1, "templates/feature-rfc.md is missing the '## Outline' section"
    assert slot_pos < outline_pos, (
        "templates/feature-rfc.md supersedes slot must appear before the '## Outline' section"
    )


# ---------------------------------------------------------------------------
# Both templates keep their pinned pointer rules green (re-asserted here so
# a regression in either template is caught alongside the new scaffold pins,
# not only by tests/test_check_model_refs.py).
# ---------------------------------------------------------------------------

def test_product_spec_still_has_no_retired_conventions_reference():
    text = _text(PRODUCT_SPEC)
    bad_lines = [line for line in text.splitlines() if _RETIRED_CONVENTIONS_DOC in line]
    assert bad_lines == [], (
        "templates/product-spec.md references the retired vault conventions doc:\n" + "\n".join(bad_lines)
    )


def test_product_spec_still_has_review_output_naming_documentation_model():
    text = _text(PRODUCT_SPEC)
    review_lines = [line for line in text.splitlines() if "Review output" in line]
    assert review_lines, "templates/product-spec.md is missing the 'Review output' footer line"
    assert any("documentation-model" in line for line in review_lines), (
        "templates/product-spec.md Review output line no longer names documentation-model"
    )


def test_feature_rfc_still_has_no_retired_conventions_reference():
    text = _text(FEATURE_RFC)
    bad_lines = [line for line in text.splitlines() if _RETIRED_CONVENTIONS_DOC in line]
    assert bad_lines == [], (
        "templates/feature-rfc.md references the retired vault conventions doc:\n" + "\n".join(bad_lines)
    )


def test_feature_rfc_still_has_review_output_naming_documentation_model():
    text = _text(FEATURE_RFC)
    review_lines = [line for line in text.splitlines() if "Review output" in line]
    assert review_lines, "templates/feature-rfc.md is missing the 'Review output' footer line"
    assert any("documentation-model" in line for line in review_lines), (
        "templates/feature-rfc.md Review output line no longer names documentation-model"
    )


# ---------------------------------------------------------------------------
# Out-of-scope guards — task.md and technical-rfc.md must not declare
# ---------------------------------------------------------------------------

def test_task_template_does_not_carry_supersedes():
    assert "supersedes" not in _text(TASK).lower(), (
        "templates/task.md carries a supersedes scaffold — tasks never declare (out of scope for #83)"
    )


def test_technical_rfc_template_does_not_carry_supersedes():
    assert "supersedes" not in _text(TECHNICAL_RFC).lower(), (
        "templates/technical-rfc.md carries a supersedes scaffold — the technical-rfc lives on the epic "
        "Issue, not this template (out of scope for #83)"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — frontmatter: type, status, supersedes scaffold
# ---------------------------------------------------------------------------

def test_debt_round_spec_frontmatter_is_product_spec_type():
    fm = _frontmatter(_text(DEBT_ROUND_SPEC))
    assert any(line.startswith("type: product-spec") for line in fm), (
        "templates/debt-round-spec.md frontmatter does not declare 'type: product-spec'"
    )
    assert any(line.startswith("status: draft") for line in fm), (
        "templates/debt-round-spec.md frontmatter does not declare 'status: draft'"
    )


def test_debt_round_spec_frontmatter_has_supersedes_scaffold_line():
    fm = _frontmatter(_text(DEBT_ROUND_SPEC))
    scaffold = next((line for line in fm if line.startswith("supersedes: []")), None)
    assert scaffold, "templates/debt-round-spec.md frontmatter is missing a 'supersedes: []' scaffold line"


def test_debt_round_spec_frontmatter_scaffold_has_created_updated():
    fm = _frontmatter(_text(DEBT_ROUND_SPEC))
    assert any(line.startswith("created:") for line in fm), (
        "templates/debt-round-spec.md frontmatter is missing a 'created:' line"
    )
    assert any(line.startswith("updated:") for line in fm), (
        "templates/debt-round-spec.md frontmatter is missing an 'updated:' line"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — Supersedes body slot (the #83 empty-justification rule)
# ---------------------------------------------------------------------------

def test_debt_round_spec_body_has_supersedes_slot():
    text = _text(DEBT_ROUND_SPEC)
    lines = text.splitlines()
    slot = next((line for line in lines if line.startswith("**Supersedes:** nothing")), None)
    assert slot, "templates/debt-round-spec.md body is missing the '**Supersedes:** nothing — …' slot line"
    assert "justification" in slot, (
        "templates/debt-round-spec.md supersedes slot does not carry a justification placeholder"
    )


def test_debt_round_spec_body_slot_has_justification_rule_comment():
    text = _text(DEBT_ROUND_SPEC)
    lines = text.splitlines()
    slot_idx = next(i for i, line in enumerate(lines) if line.startswith("**Supersedes:** nothing"))
    following = " ".join(lines[slot_idx + 1:slot_idx + 3])
    assert following.strip().startswith("<!--"), (
        "templates/debt-round-spec.md supersedes slot is not followed by an HTML comment stating the rule"
    )
    assert "empty" in following, (
        "templates/debt-round-spec.md supersedes rule comment does not cover the empty-list case"
    )
    assert "non-empty" in following, (
        "templates/debt-round-spec.md supersedes rule comment does not cover the non-empty-list case"
    )
    assert "replace" in following and "drop" in following, (
        "templates/debt-round-spec.md supersedes rule comment does not instruct replacing or dropping the "
        "line once the list is non-empty"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — Scope by-name section
# ---------------------------------------------------------------------------

def test_debt_round_spec_has_scope_by_name_section():
    text = _text(DEBT_ROUND_SPEC)
    assert "## Scope" in text and "by name" in text, (
        "templates/debt-round-spec.md is missing a 'Scope — by name' section heading"
    )


def test_debt_round_spec_scope_states_unnamed_item_excluded():
    text = _text(DEBT_ROUND_SPEC)
    assert "item not named here is not in the round" in text, (
        "templates/debt-round-spec.md scope section does not state that an item not named here is not "
        "in the round"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — pin-then-prune ordering duty
# ---------------------------------------------------------------------------

def test_debt_round_spec_has_pin_then_prune_ordering_section():
    text = _text(DEBT_ROUND_SPEC)
    assert "## Pin-then-prune ordering" in text, (
        "templates/debt-round-spec.md is missing a 'Pin-then-prune ordering' section heading"
    )
    assert "ordered pin-then-prune pair" in text, (
        "templates/debt-round-spec.md pin-then-prune section does not state that every behavior-touching "
        "item is an ordered pin-then-prune pair"
    )
    assert "sub-issue order" in text.lower() or "Sub-issue order" in text, (
        "templates/debt-round-spec.md pin-then-prune section does not name sub-issue order as the "
        "enforcement mechanism"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — per-prune acceptance scaffold
# ---------------------------------------------------------------------------

def test_debt_round_spec_has_per_prune_acceptance_scaffold():
    text = _text(DEBT_ROUND_SPEC)
    assert "Per-prune acceptance scaffold" in text, (
        "templates/debt-round-spec.md is missing the 'Per-prune acceptance scaffold' heading"
    )
    assert "Pins green" in text, (
        "templates/debt-round-spec.md per-prune scaffold does not carry a 'Pins green' criterion"
    )
    assert "No new dependencies" in text, (
        "templates/debt-round-spec.md per-prune scaffold does not carry a 'No new dependencies' criterion"
    )
    assert "cites its" in text and "birth" in text, (
        "templates/debt-round-spec.md per-prune scaffold does not require every removal to cite its birth"
    )


def test_debt_round_spec_per_prune_scaffold_has_net_lines_record_fields():
    text = _text(DEBT_ROUND_SPEC)
    assert "YR-DEBT-NET-LINES" in text, (
        "templates/debt-round-spec.md is missing the YR-DEBT-NET-LINES record grammar"
    )
    for field in ("net-lines:", "scope:", "birth:"):
        assert field in text, (
            f"templates/debt-round-spec.md YR-DEBT-NET-LINES record is missing the '{field}' field"
        )


# ---------------------------------------------------------------------------
# debt-round-spec.md — suite-duration canary (recorded, never gated)
# ---------------------------------------------------------------------------

def test_debt_round_spec_has_suite_duration_canary():
    text = _text(DEBT_ROUND_SPEC)
    assert "Suite-duration canary" in text, (
        "templates/debt-round-spec.md is missing the 'Suite-duration canary' heading"
    )
    assert "recorded, never gated" in text, (
        "templates/debt-round-spec.md suite-duration canary does not state it is recorded, never gated"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — EARS acceptance section
# ---------------------------------------------------------------------------

def test_debt_round_spec_has_ears_acceptance_section():
    text = _text(DEBT_ROUND_SPEC)
    assert "Acceptance criteria (EARS)" in text, (
        "templates/debt-round-spec.md is missing the 'Acceptance criteria (EARS)' section heading"
    )
    assert "THE SYSTEM SHALL" in text, (
        "templates/debt-round-spec.md EARS section does not carry a 'THE SYSTEM SHALL' scaffold line"
    )
    assert "WHEN" in text and "SHALL" in text, (
        "templates/debt-round-spec.md EARS section does not carry a 'WHEN … SHALL' event-driven scaffold line"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — Round close duties (seven-field ledger verdict)
# ---------------------------------------------------------------------------

def test_debt_round_spec_has_round_close_section():
    text = _text(DEBT_ROUND_SPEC)
    assert "## Round close" in text, (
        "templates/debt-round-spec.md is missing the 'Round close' section heading"
    )


def test_debt_round_spec_round_close_posts_seven_field_ledger_verdict():
    text = _text(DEBT_ROUND_SPEC)
    assert "YR-DEBT-LEDGER" in text, (
        "templates/debt-round-spec.md Round close section is missing the YR-DEBT-LEDGER grammar"
    )
    seven_fields = (
        "items:", "net-lines:", "files-removed:", "deps-removed:",
        "pins-added:", "suite-duration:", "incidents:",
    )
    for field in seven_fields:
        assert field in text, (
            f"templates/debt-round-spec.md YR-DEBT-LEDGER verdict is missing the '{field}' field"
        )


def test_debt_round_spec_round_close_names_remaining_duties():
    text = _text(DEBT_ROUND_SPEC)
    round_close_idx = text.find("## Round close")
    assert round_close_idx != -1, "templates/debt-round-spec.md is missing the 'Round close' section"
    section = text[round_close_idx:]
    assert "Aggregate the per-slice net-lines records" in section, (
        "templates/debt-round-spec.md Round close duties do not include aggregating the per-slice "
        "net-lines records"
    )
    assert "Close the raise item" in section and "YR-DEBT-DUE" in section, (
        "templates/debt-round-spec.md Round close duties do not include closing the raise item "
        "(YR-DEBT-DUE) that called the round"
    )
    assert "Clear the epic" in section and "Reason" in section, (
        "templates/debt-round-spec.md Round close duties do not include clearing the epic's held Reason"
    )
    assert "Re-census" in section, (
        "templates/debt-round-spec.md Round close duties do not include re-censusing for the next round"
    )


# ---------------------------------------------------------------------------
# debt-round-spec.md — kind record line + retired-conventions guard
# ---------------------------------------------------------------------------

def test_debt_round_spec_states_epic_kind_record_line():
    text = _text(DEBT_ROUND_SPEC)
    assert "YR-ITERATION-KIND: tech-debt" in text, (
        "templates/debt-round-spec.md does not state the debt epic's YR-ITERATION-KIND: tech-debt "
        "record line"
    )


def test_debt_round_spec_has_no_retired_conventions_reference():
    text = _text(DEBT_ROUND_SPEC)
    bad_lines = [line for line in text.splitlines() if _RETIRED_CONVENTIONS_DOC in line]
    assert bad_lines == [], (
        "templates/debt-round-spec.md references the retired vault conventions doc:\n" + "\n".join(bad_lines)
    )


# ---------------------------------------------------------------------------
# debt-census.md — frontmatter: type, status, optional supersedes scaffold
# ---------------------------------------------------------------------------

def test_debt_census_frontmatter_is_research_type():
    fm = _frontmatter(_text(DEBT_CENSUS))
    assert any(line.startswith("type: research") for line in fm), (
        "templates/debt-census.md frontmatter does not declare 'type: research'"
    )
    assert any(line.startswith("status: draft") for line in fm), (
        "templates/debt-census.md frontmatter does not declare 'status: draft'"
    )


def test_debt_census_frontmatter_scaffold_has_created_updated():
    fm = _frontmatter(_text(DEBT_CENSUS))
    assert any(line.startswith("created:") for line in fm), (
        "templates/debt-census.md frontmatter is missing a 'created:' line"
    )
    assert any(line.startswith("updated:") for line in fm), (
        "templates/debt-census.md frontmatter is missing an 'updated:' line"
    )


def test_debt_census_frontmatter_supersedes_scaffold_is_optional_and_names_natural_case():
    fm = _frontmatter(_text(DEBT_CENSUS))
    idx = next((i for i, line in enumerate(fm) if line.startswith("supersedes: []")), None)
    assert idx is not None, "templates/debt-census.md frontmatter is missing a 'supersedes: []' scaffold line"
    guidance = " ".join(fm[idx:idx + 3])
    assert "optional" in guidance, (
        "templates/debt-census.md supersedes scaffold does not note it is optional"
    )
    assert "round-N" in guidance and "N-1" in guidance, (
        "templates/debt-census.md supersedes scaffold comment does not name the natural case of a "
        "round-N census superseding round N-1's"
    )


# ---------------------------------------------------------------------------
# debt-census.md — method/discipline header
# ---------------------------------------------------------------------------

def test_debt_census_has_discipline_header():
    text = _text(DEBT_CENSUS)
    # Header prose wraps across '> ' blockquote lines, so strip the blockquote marker from each line
    # and collapse whitespace before matching phrases that may themselves be split across a line break.
    unquoted = "\n".join(
        line[2:] if line.startswith("> ") else line
        for line in text.splitlines()
    )
    normalized = " ".join(unquoted.split())
    assert "read-only" in normalized, (
        "templates/debt-census.md discipline header does not state the census is read-only"
    )
    assert "Untested is not unused" in normalized, (
        "templates/debt-census.md discipline header does not state untested is not unused"
    )
    assert "Deletion cites its birth" in normalized, (
        "templates/debt-census.md discipline header does not state deletion cites its birth"
    )


# ---------------------------------------------------------------------------
# debt-census.md — Baselines section
# ---------------------------------------------------------------------------

def test_debt_census_has_baselines_section():
    text = _text(DEBT_CENSUS)
    assert "## Baselines" in text, (
        "templates/debt-census.md is missing the 'Baselines' section heading"
    )
    baselines_idx = text.find("## Baselines")
    next_heading = text.find("## ", baselines_idx + 1)
    section = text[baselines_idx:next_heading if next_heading != -1 else len(text)]
    assert "Tracked files" in section and "Tracked lines" in section, (
        "templates/debt-census.md Baselines section does not track files/lines"
    )
    assert "Suite" in section, (
        "templates/debt-census.md Baselines section does not carry a suite meter"
    )


# ---------------------------------------------------------------------------
# debt-census.md — Reachability ledger (table header + nothing-deletable rule)
# ---------------------------------------------------------------------------

def test_debt_census_has_reachability_ledger_table_header():
    text = _text(DEBT_CENSUS)
    assert "## Reachability ledger" in text, (
        "templates/debt-census.md is missing the 'Reachability ledger' section heading"
    )
    header = "| Item | Class | Evidence | Birth | Candidate disposition |"
    assert header in text, (
        "templates/debt-census.md reachability ledger table is missing the expected column header "
        f"{header!r}"
    )


def test_debt_census_reachability_ledger_states_nothing_deletable_rule():
    text = _text(DEBT_CENSUS)
    assert "Nothing is deletable unless the ledger clears it" in text, (
        "templates/debt-census.md reachability ledger is missing the rule that nothing is deletable "
        "unless the ledger clears it"
    )


# ---------------------------------------------------------------------------
# debt-census.md — duplication/consolidation sets, unknowns
# ---------------------------------------------------------------------------

def test_debt_census_has_duplication_consolidation_section():
    text = _text(DEBT_CENSUS)
    assert "Duplication" in text and "consolidation" in text.lower(), (
        "templates/debt-census.md is missing a duplication/consolidation-sets section heading"
    )


def test_debt_census_has_unknowns_section():
    text = _text(DEBT_CENSUS)
    assert "## Unknowns" in text, (
        "templates/debt-census.md is missing the 'Unknowns' section heading"
    )


# ---------------------------------------------------------------------------
# debt-census.md — Revisit trigger slot
# ---------------------------------------------------------------------------

def test_debt_census_has_revisit_trigger_slot():
    text = _text(DEBT_CENSUS)
    assert "## Revisit trigger" in text, (
        "templates/debt-census.md is missing the 'Revisit trigger' section heading"
    )
    revisit_idx = text.find("## Revisit trigger")
    section = text[revisit_idx:]
    assert "first prune merge" in section, (
        "templates/debt-census.md revisit trigger does not state the numbers go stale at the first "
        "prune merge"
    )
    assert "Re-census per round" in section, (
        "templates/debt-census.md revisit trigger does not state re-census happens per round"
    )


# ---------------------------------------------------------------------------
# debt-census.md — kind record line + retired-conventions guard
# ---------------------------------------------------------------------------

def test_debt_census_states_epic_kind_record_line():
    text = _text(DEBT_CENSUS)
    assert "YR-ITERATION-KIND: tech-debt" in text, (
        "templates/debt-census.md does not state the debt epic's YR-ITERATION-KIND: tech-debt record line"
    )


def test_debt_census_has_no_retired_conventions_reference():
    text = _text(DEBT_CENSUS)
    bad_lines = [line for line in text.splitlines() if _RETIRED_CONVENTIONS_DOC in line]
    assert bad_lines == [], (
        "templates/debt-census.md references the retired vault conventions doc:\n" + "\n".join(bad_lines)
    )


# ---------------------------------------------------------------------------
# Out-of-scope guards — the other authoring templates must not gain the
# debt-round walls (they are out of scope for #92; task.md/technical-rfc.md
# already guarded above against a supersedes scaffold, guarded by #83).
# ---------------------------------------------------------------------------

def test_readme_template_does_not_reference_debt_round_ledger_grammar():
    readme = TEMPLATES / "README.md"
    assert "YR-DEBT-LEDGER" not in _text(readme), (
        "templates/README.md carries the debt-round ledger grammar — out of scope for #92"
    )


# ---------------------------------------------------------------------------
# technical-rfc.md — check-gate parity one-liner in the authoring-scaffold
# checklist (#123): the crossing step must carry the same rule as
# authoring.md's task-authoring step, as a one-line reminder where slices
# are decomposed. This is the natural checklist home the issue names — the
# scaffold section, not the filed ISSUE BODY.
# ---------------------------------------------------------------------------

def _technical_rfc_checklist_section():
    """Return the authoring-scaffold checklist portion of technical-rfc.md — the
    text after the filed-body end marker, where the per-task decomposition
    checklist lives."""
    text = _text(TECHNICAL_RFC)
    marker = "END ISSUE BODY"
    idx = text.find(marker)
    assert idx != -1, "templates/technical-rfc.md is missing the 'END ISSUE BODY' marker"
    return text[idx:]


def test_technical_rfc_checklist_states_check_gate_parity_reminder():
    section = _technical_rfc_checklist_section()
    lower = section.lower()
    assert "check_cmd" in section, (
        "templates/technical-rfc.md checklist does not name check_cmd in the check-gate parity reminder"
    )
    assert "server-ci" in lower or "server ci" in lower, (
        "templates/technical-rfc.md checklist does not name the server-CI workflow in the check-gate "
        "parity reminder"
    )
    assert "deliverable" in lower, (
        "templates/technical-rfc.md checklist does not state the check-gate parity reminder as a "
        "deliverables requirement"
    )


def test_technical_rfc_checklist_check_gate_parity_is_one_line_item():
    """The reminder must be a single checklist bullet (`- [ ] ...`), not a new multi-paragraph
    section — the issue calls for a one-line reminder where slices are decomposed."""
    section = _technical_rfc_checklist_section()
    lines = section.splitlines()
    bullet_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("- [ ]") and "check_cmd" in line),
        None,
    )
    assert bullet_idx is not None, (
        "templates/technical-rfc.md check-gate parity reminder is not a checklist bullet item"
    )


def test_technical_rfc_check_gate_parity_reminder_not_in_filed_issue_body():
    """The reminder is authoring scaffold (a self-reminder while decomposing slices), not
    filed content — it must not land inside the ISSUE BODY markers that get pasted to GitHub."""
    text = _text(TECHNICAL_RFC)
    start = text.find("ISSUE BODY · file from here")
    end = text.find("END ISSUE BODY")
    assert start != -1 and end != -1 and start < end, (
        "templates/technical-rfc.md is missing its ISSUE BODY markers"
    )
    issue_body = text[start:end]
    assert "check_cmd" not in issue_body, (
        "templates/technical-rfc.md check-gate parity reminder leaked into the filed ISSUE BODY section"
    )


def test_technical_rfc_check_gate_parity_reminder_not_duplicated():
    """The rule should appear once in technical-rfc.md — as the crossing-step pointer — not
    restated multiple times."""
    text = _text(TECHNICAL_RFC)
    assert text.count("check_cmd") == 1, (
        "templates/technical-rfc.md states check_cmd more than once — the check-gate parity "
        "reminder should appear once, in the authoring-scaffold checklist"
    )
