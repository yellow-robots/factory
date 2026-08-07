"""
Tests for Issue #346 — the architect reconciliation and the four-location
gate contradiction.

Derived from the Issue #346 acceptance criteria (the spec), not from the
implementation. Two independent repairs land together:

1. A standalone task's body is its own design (closing.md's promote
   checklist already mandates an independent adversarial review *and* an
   architect fit check there, record-before-flip). Two other surfaces omitted
   the fit check: architect.md's earn-test (three arms, none of which a bare
   task body can fire) grows a fourth arm that fires for a standalone task's
   body; documentation-model.md's direct-lane sequence names the fit check
   so the lane no longer omits a role the promote checklist mandates.
   closing.md itself is the surface being reconciled *to* and stays
   untouched — that is a separate, out-of-scope constraint checked here too.

2. Four shipped living locations asserted that the technical-rfc is
   human-gated (a per-RFC human sign-off); authoring.md's settled rule says
   the human's structural gate sits upstream, at design-active, and past the
   airlock there is no per-RFC human sign-off. All four are corrected to
   that one consistent statement — the adversarial review discipline they
   each describe stays; only the human-sign-off claim goes.
   docs/rfcs/0005-upper-pipeline.md carries the same superseded claim but is
   a frozen record, deliberately out of scope for this repair.
"""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

ARCHITECT = ROOT / "skills" / "factory" / "references" / "architect.md"
DOC_MODEL = ROOT / "skills" / "factory" / "references" / "documentation-model.md"
CLOSING = ROOT / "skills" / "factory" / "references" / "closing.md"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
REVIEWING = ROOT / "skills" / "factory" / "references" / "reviewing.md"
TECHNICAL_RFC_TEMPLATE = ROOT / "skills" / "factory" / "templates" / "technical-rfc.md"
AUTHORING = ROOT / "skills" / "factory" / "references" / "authoring.md"
RFC_0005 = ROOT / "docs" / "rfcs" / "0005-upper-pipeline.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _normalized(text):
    """Fold whitespace (incl. markdown line wraps) to a single space so a phrase wrapped
    across a line break still matches a plain substring check."""
    return re.sub(r"\s+", " ", text.lower())


def _base_ref_text(rel_path):
    """The base ref's copy of a file (origin/main, falling back to main), so a
    byte-identical claim is checked against the tree this task branched from, not a guess."""
    for ref in ("origin/main", "main"):
        result = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout
    raise AssertionError(f"could not read {rel_path!r} from either origin/main or main")


# ---------------------------------------------------------------------------
# The architect earn-test grows a fourth arm firing for a standalone task body
# ---------------------------------------------------------------------------

def _architect_earn_test_section():
    text = _text(ARCHITECT)
    start = text.find("## The earn-test")
    assert start != -1, "architect.md is missing its '## The earn-test' heading"
    next_heading = text.find("\n## ", start + len("## The earn-test"))
    end = next_heading if next_heading != -1 else len(text)
    return text[start:end]


def test_architect_earn_test_fires_for_a_standalone_task_body():
    section = _architect_earn_test_section().lower()
    assert "standalone task" in section, (
        "architect.md's earn-test does not name an arm firing for a standalone task's "
        "body -- closing.md's promote checklist mandates a fit check there, and the "
        "earn-test must leave no surface that would skip it"
    )


def test_architect_earn_test_keeps_the_original_three_arms():
    section = _architect_earn_test_section().lower()
    assert "supersedes" in section, \
        "architect.md earn-test lost the non-empty supersedes-declaration arm"
    assert "next-stage" in section or "next stage" in section, \
        "architect.md earn-test lost the earned-technical-rfc-from-Next-stage-statement arm"
    assert "load-bearing" in section, \
        "architect.md earn-test lost the load-bearing-sections arm"


def test_architect_earn_test_still_names_the_skip_path():
    section = _architect_earn_test_section().lower()
    assert "skip" in section, (
        "architect.md earn-test dropped the no-arm-holds-the-role-is-skipped path"
    )


def test_architect_earn_test_new_arm_cites_the_mandate_it_answers_to():
    section = _architect_earn_test_section()
    assert "closing.md" in section, (
        "architect.md's fourth (standalone-task) arm does not cite closing.md -- it exists "
        "because closing.md's promote checklist mandates the fit check there, and should "
        "point at that mandate rather than assert it independently"
    )


# ---------------------------------------------------------------------------
# closing.md is the surface being reconciled to; it is not itself edited
# ---------------------------------------------------------------------------

def test_closing_md_keeps_the_reconciled_promote_surface():
    # The original byte-identity form was that issue's OWN scope constraint ("this issue does
    # not edit closing.md") frozen as a standing pin -- state masquerading as rule: it would
    # structurally block every legitimate future closing.md change (first fired by it-30's
    # standalone-close addition, which the governing spec's own EARS mandates). Retired at
    # it-30 to its intent: the reconciled promote surface -- the mandate the earn-test and
    # direct-lane sequence were reconciled TO -- stays present and unweakened.
    text = _text(CLOSING)
    assert "record-before-flip" in text and "promote" in text, (
        "closing.md lost the reconciled promote surface (record-before-flip on the trail "
        "before the Status flip)"
    )


def test_closing_md_promote_checklist_still_mandates_the_architect_fit_check():
    text = _text(CLOSING)
    assert "architect fit check" in text, (
        "closing.md no longer mandates the architect fit check on a standalone task's "
        "body -- the whole point of the reconciliation is that this mandate stays fixed "
        "while the other two surfaces catch up to it"
    )


# ---------------------------------------------------------------------------
# The direct lane's stated sequence names the architect fit check, and the
# five pre-existing pinned stops keep their relative order (mechanical
# constraint: insert the new stop between existing stops, never reorder or
# reword them)
# ---------------------------------------------------------------------------

def _doc_model_ideas_backlog_section():
    text = _text(DOC_MODEL)
    start = text.find("## The ideas-backlog")
    assert start != -1, "documentation-model.md is missing a '## The ideas-backlog' heading"
    next_heading = text.find("\n## ", start + len("## The ideas-backlog"))
    end = next_heading if next_heading != -1 else len(text)
    return text[start:end]


def test_direct_lane_names_the_architect_fit_check():
    section = _normalized(_doc_model_ideas_backlog_section())
    assert "architect" in section and "fit check" in section, (
        "documentation-model.md's direct-lane sequence does not name the architect fit "
        "check -- the lane must not omit a role the promote checklist mandates"
    )


def test_direct_lane_five_pinned_stops_keep_their_relative_order():
    section = _normalized(_doc_model_ideas_backlog_section())
    stops = [
        "drafted task",
        "independent adversarial review",
        "dispositions on the trail",
        "task-delivered arm stamp",
        "human promote",
    ]
    for stop in stops:
        assert stop in section, (
            f"documentation-model.md direct-lane text lost the '{stop}' stop while "
            f"inserting the architect fit check"
        )
    positions = [section.index(stop) for stop in stops]
    assert positions == sorted(positions), (
        f"documentation-model.md direct-lane stops were reordered while inserting the "
        f"architect fit check: {stops} at {positions}"
    )


def test_direct_lane_fit_check_sits_between_existing_stops_not_outside_them():
    section = _normalized(_doc_model_ideas_backlog_section())
    first_stop_pos = section.index("drafted task")
    last_stop_pos = section.index("human promote")
    fit_check_pos = section.index("fit check")
    assert first_stop_pos < fit_check_pos < last_stop_pos, (
        "documentation-model.md's architect fit check must be inserted between the "
        "existing direct-lane stops, not prepended before the first or appended after "
        "the last"
    )


# ---------------------------------------------------------------------------
# The four-location technical-rfc human-gate contradiction: one consistent
# statement survives (no per-RFC human sign-off), the review discipline each
# location describes stays
# ---------------------------------------------------------------------------

def test_technical_rfc_template_pre_gate_no_longer_requires_human_approval():
    text = _text(TECHNICAL_RFC_TEMPLATE)
    assert "approved (human)" not in text, (
        "templates/technical-rfc.md's pre-gate still requires the shape be "
        "'approved (human)' before the body is written -- the technical-rfc is not "
        "human-gated past the airlock"
    )
    assert "pre-gate" in text.lower() or "Pre-gate" in text, (
        "templates/technical-rfc.md dropped the pre-gate step entirely instead of just "
        "its human-approval claim"
    )


def test_technical_rfc_template_final_gate_no_longer_names_a_human():
    text = _text(TECHNICAL_RFC_TEMPLATE)
    assert "review the technical RFC** (human)" not in text, (
        "templates/technical-rfc.md still states 'Gate before then: review the technical "
        "RFC (human)' -- the technical-rfc review is not a human sign-off"
    )
    assert "review the technical RFC" in text, (
        "templates/technical-rfc.md dropped the review-the-technical-RFC gate statement "
        "entirely instead of just its human-sign-off claim"
    )


def test_skill_md_no_longer_claims_a_human_approves_at_each_step():
    text = _text(SKILL)
    assert "a human approves at each step" not in text, (
        "SKILL.md still claims 'a human approves at each step' for the upper pipeline -- "
        "the human's structural approval sits upstream at design-active, not at every step"
    )
    assert "run the gates" in text, (
        "SKILL.md dropped the run-the-gates statement entirely instead of just the "
        "human-approves-at-each-step claim"
    )


def test_reviewing_md_technical_rfc_gate_is_not_named_human():
    text = _text(REVIEWING)
    assert "the human review-the-technical-rfc gate" not in text.lower(), (
        "reviewing.md still calls the technical-rfc gate 'the human review-the-technical-rfc "
        "gate' -- the technical-rfc review is not a human sign-off"
    )
    assert "review-the-technical-rfc" in text.lower(), (
        "reviewing.md dropped the review-the-technical-rfc gate citation entirely instead "
        "of just its human-sign-off claim"
    )


def test_no_shipped_reference_still_asserts_a_human_gate_on_the_technical_rfc():
    """All four named locations, checked together: none may still claim a per-RFC human
    sign-off on the technical-rfc specifically (the settled rule the other three tests
    check individually, verified again here as a single cross-cutting assertion)."""
    offending_phrases = {
        TECHNICAL_RFC_TEMPLATE: ["approved (human)", "review the technical RFC** (human)"],
        SKILL: ["a human approves at each step"],
        REVIEWING: ["the human review-the-technical-rfc gate", "the human *review-the-technical-rfc* gate"],
    }
    offenders = []
    for path, phrases in offending_phrases.items():
        text = _text(path)
        for phrase in phrases:
            if phrase in text:
                offenders.append(f"{path.relative_to(ROOT)} still contains {phrase!r}")
    assert not offenders, "\n".join(offenders)


def test_authoring_md_settled_rule_stays_the_one_source_of_truth():
    text = _text(AUTHORING)
    assert "no per-RFC" in text and "human" in text, (
        "authoring.md's settled rule -- the human's structural gate sits at design-active, "
        "upstream; past the airlock there is no per-RFC human sign-off -- must survive as "
        "the one statement the other four locations are being reconciled to"
    )


# ---------------------------------------------------------------------------
# Two things this repair must not touch
# ---------------------------------------------------------------------------

def test_skill_md_no_agent_ever_sets_a_design_active_is_unchanged():
    text = _text(SKILL)
    assert "no agent ever sets `active`" in text, (
        "SKILL.md dropped the rule that no agent ever sets a design `active` -- this rule "
        "the whole input gate rests on must be left untouched by this repair"
    )


def test_authoring_md_feature_rfc_outline_pre_gate_is_unchanged():
    text = _text(AUTHORING)
    step2_start = text.find("### 2. feature-rfc")
    assert step2_start != -1, "authoring.md is missing its '### 2. feature-rfc' step"
    step3_start = text.find("### 3.", step2_start)
    step2 = text[step2_start:step3_start if step3_start != -1 else len(text)]
    assert "send the outline to the human first" in step2, (
        "authoring.md's feature-rfc step lost its outline pre-gate ('send the outline to "
        "the human first') -- this survives because a feature-rfc carries WHAT/WHY, the "
        "human-gated side of the line, unlike the technical-rfc"
    )


# ---------------------------------------------------------------------------
# docs/rfcs/0005-upper-pipeline.md is a frozen record and is not repaired
# ---------------------------------------------------------------------------

def test_rfc_0005_upper_pipeline_is_byte_identical_to_the_base_ref():
    base = _base_ref_text("docs/rfcs/0005-upper-pipeline.md")
    assert _text(RFC_0005) == base, (
        "docs/rfcs/0005-upper-pipeline.md changed -- it carries the same superseded "
        "human-gate claim as the four living locations, but it is a frozen record and is "
        "deliberately out of scope for this repair"
    )
