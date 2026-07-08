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
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
PRODUCT_SPEC = TEMPLATES / "product-spec.md"
FEATURE_RFC = TEMPLATES / "feature-rfc.md"
TASK = TEMPLATES / "task.md"
TECHNICAL_RFC = TEMPLATES / "technical-rfc.md"

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
