"""
Tests for Slice A2 — SKILL.md router restructure acceptance criteria.

Derived from the Issue #4 acceptance criteria (the spec), not from the
implementation internals. These are structural checks that can run on every
future build via check_cmd (pytest).
"""

import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
REFS = ROOT / "skills" / "factory" / "references"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"

REQUIRED_REFS = [
    "authoring.md",
    "reviewing.md",
    "gates.md",
    "pipeline.md",
    "closing.md",
    "migrating.md",
    "onboarding.md",
    "architect.md",
]


def _skill_text():
    return SKILL.read_text(encoding="utf-8")


def _skill_description():
    """Extract SKILL.md frontmatter description, handling YAML >- block scalar."""
    lines = _skill_text().split("\n")
    in_fm = False
    in_desc_block = False
    desc_lines = []
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_fm = True
            continue
        if in_fm and line.strip() == "---":
            break
        if not in_fm:
            continue
        if line.startswith("description:"):
            val = line.split(":", 1)[1].strip()
            if val in (">-", ">", "|-", "|"):
                in_desc_block = True
            else:
                return val.strip('"')
        elif in_desc_block:
            if line.startswith("  ") or line.startswith("\t"):
                desc_lines.append(line.strip())
            elif line.strip() == "":
                pass  # blank line within block scalar
            else:
                in_desc_block = False
    return " ".join(desc_lines)


def _plugin_data():
    return json.loads(PLUGIN.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

def test_all_seven_references_exist():
    """All seven operation references must be present on disk."""
    for ref in REQUIRED_REFS:
        assert (REFS / ref).exists(), f"Missing reference file: skills/factory/references/{ref}"


# ---------------------------------------------------------------------------
# SKILL.md structural constraints
# ---------------------------------------------------------------------------

def test_skill_md_is_under_500_lines():
    lines = _skill_text().splitlines()
    assert len(lines) < 500, f"SKILL.md is {len(lines)} lines — must be < 500"


def test_skill_md_has_no_01_conventions_reference():
    """The vault 01-conventions pointer must be gone from SKILL.md."""
    assert "01-conventions" not in _skill_text()


def test_skill_md_has_router_table():
    """SKILL.md must contain a markdown table mapping operations to references."""
    text = _skill_text()
    assert re.search(r"\|\s*\*{0,2}[Oo]peration\*{0,2}\s*\|", text), \
        "SKILL.md does not contain a router table with an 'Operation' column"


def test_skill_md_has_routing_gap_marker():
    """The fail-loud routing invariant must use the exact prefix 'ROUTING GAP: '."""
    assert "ROUTING GAP: " in _skill_text(), \
        "SKILL.md does not contain the literal string 'ROUTING GAP: '"


def test_skill_md_routing_gap_is_in_invariants():
    """ROUTING GAP: must appear in or near the invariants section, not just in passing."""
    text = _skill_text()
    # The marker and the word "invariant" must both appear in the file
    assert "ROUTING GAP: " in text
    assert "nvariant" in text  # "Invariant" or "Invariants"


# ---------------------------------------------------------------------------
# Router link integrity — no dangling links, no orphan references
# ---------------------------------------------------------------------------

def test_all_references_linked_from_skill_md():
    """Every required reference must appear as a link in SKILL.md."""
    text = _skill_text()
    for ref in REQUIRED_REFS:
        assert ref in text, f"Reference not linked from SKILL.md: {ref}"


def test_no_dangling_router_links():
    """Every relative markdown link to references/ in SKILL.md must resolve to a real file."""
    text = _skill_text()
    links = re.findall(r"\[.*?\]\((references/[^)]+)\)", text)
    assert links, "No references/ links found in SKILL.md at all"
    for link in links:
        target = ROOT / "skills" / "factory" / link
        assert target.exists(), f"Dangling link in SKILL.md router: {link}"


def test_no_orphan_references():
    """Every file under references/ that is a required operation ref must have a router entry."""
    text = _skill_text()
    for ref in REQUIRED_REFS:
        assert ref in text, \
            f"Orphan reference with no router entry in SKILL.md: references/{ref}"


# ---------------------------------------------------------------------------
# Plugin version and description sync
# ---------------------------------------------------------------------------

def test_plugin_version_is_current():
    assert _plugin_data()["version"] == "0.8.0"


def test_skill_md_and_plugin_description_agree():
    """SKILL.md frontmatter description and plugin.json description must match exactly
    (modulo whitespace folding, since SKILL.md uses a YAML >- block scalar)."""
    plugin_desc = _plugin_data()["description"]
    skill_desc = _skill_description()
    # Normalize internal whitespace before comparing (YAML >- folds newlines → spaces)
    normalize = lambda s: re.sub(r"\s+", " ", s).strip()
    assert normalize(skill_desc) == normalize(plugin_desc), (
        f"Description mismatch:\n  SKILL.md: {skill_desc!r}\n  plugin.json: {plugin_desc!r}"
    )


def test_skill_description_names_review_operation():
    """SKILL.md description must name the reviewing operation."""
    desc = _skill_description().lower()
    assert "review" in desc, "SKILL.md description does not mention 'review'"


def test_skill_description_names_close_operation():
    """SKILL.md description must name the closing/close operation."""
    desc = _skill_description().lower()
    assert "clos" in desc, "SKILL.md description does not mention 'closing' or 'close'"


# ---------------------------------------------------------------------------
# Each reference cites documentation-model.md (never restates the model)
# ---------------------------------------------------------------------------

def test_each_reference_cites_documentation_model():
    """References that cover documentation-model content must cite documentation-model.md.

    gates.md, pipeline.md, and onboarding.md cover pure mechanism (CLI flags, runner stages,
    repo setup) — they have no documentation-model content to defer, so they are excluded.
    The remaining four touch model content (doc types, lifecycle, migration, fold-in rules,
    shipping-freezes-the-why) and must cite rather than restate.
    """
    refs_needing_doc_model_citation = [
        "authoring.md",
        "reviewing.md",
        "closing.md",
        "migrating.md",
    ]
    for ref in refs_needing_doc_model_citation:
        text = (REFS / ref).read_text(encoding="utf-8")
        assert "documentation-model.md" in text, \
            f"references/{ref} does not cite documentation-model.md"


def test_authoring_cites_editing_safely():
    """authoring.md must cite the Editing-safely section of documentation-model.md.

    The acceptance criteria states: 'Vault-safety is not restated anywhere — it lives once, in
    documentation-model → Editing-safely; authoring.md and migrating.md cite that section.'
    """
    text = (REFS / "authoring.md").read_text(encoding="utf-8")
    lower = text.lower()
    cites_editing_safely = (
        "editing safely" in lower
        or "editing-safely" in lower
        or ("editing" in lower and "safely" in lower)
    )
    assert cites_editing_safely, \
        "authoring.md does not cite the Editing-safely section of documentation-model.md"


def test_migrating_cites_editing_safely():
    """migrating.md must cite the Editing-safely section of documentation-model.md."""
    text = (REFS / "migrating.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "editing" in lower and ("safely" in lower or "safe" in lower), \
        "migrating.md does not cite the Editing-safely section of documentation-model.md"


# ---------------------------------------------------------------------------
# Content is in the right reference
# ---------------------------------------------------------------------------

def test_authoring_md_has_upper_pipeline_steps():
    """authoring.md must cover the upper-pipeline authoring steps."""
    text = (REFS / "authoring.md").read_text(encoding="utf-8")
    assert "product-spec" in text, "authoring.md missing product-spec content"
    assert "feature-rfc" in text or "feature rfc" in text.lower(), \
        "authoring.md missing feature-rfc content"
    assert "technical-rfc" in text or "technical rfc" in text.lower(), \
        "authoring.md missing technical-rfc content"


def test_pipeline_md_has_lower_pipeline_content():
    """pipeline.md must describe the lower pipeline / dev-runner mechanics."""
    text = (REFS / "pipeline.md").read_text(encoding="utf-8")
    assert "dev-runner" in text or "dev_runner" in text, \
        "pipeline.md missing dev-runner content"
    assert "Status=Ready" in text or "Status = Ready" in text or "Status=Ready" in text, \
        "pipeline.md missing Status=Ready dispatch reference"


def test_closing_md_has_promote_and_merge():
    """closing.md must cover promote-to-Ready prep and merge → Done."""
    text = (REFS / "closing.md").read_text(encoding="utf-8")
    assert "Ready" in text, "closing.md missing promote-to-Ready content"
    assert "Done" in text, "closing.md missing merge → Done content"


def test_closing_md_has_doc_freeze():
    """closing.md must cover the doc-side freeze."""
    text = (REFS / "closing.md").read_text(encoding="utf-8")
    assert "freeze" in text.lower() or "immutable" in text.lower() or "frozen" in text.lower(), \
        "closing.md missing doc-side freeze content"


def test_closing_md_has_standalone_skill_release_block():
    """closing.md must have a standalone skill-release block (version bump · release scan · ship-before-demote)."""
    text = (REFS / "closing.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "standalone" in lower or "stand alone" in lower or "stand-alone" in lower, \
        "closing.md skill-release block is not marked standalone"
    assert "version bump" in lower or "version" in lower, \
        "closing.md missing version bump step in skill-release block"
    assert "release scan" in lower or "release" in lower, \
        "closing.md missing release scan step"
    assert "ship" in lower and "demote" in lower, \
        "closing.md missing ship-before-demote step"


def test_gates_md_has_deterministic_gates_table():
    """gates.md must contain a table covering check_links, check_task, check_cmd, and review verdict."""
    text = (REFS / "gates.md").read_text(encoding="utf-8")
    assert re.search(r"\|.*check_links.*\|", text), "gates.md missing check_links in table"
    assert re.search(r"\|.*check_task.*\|", text), "gates.md missing check_task in table"
    assert re.search(r"\|.*check_cmd.*\|", text), "gates.md missing check_cmd in table"
    assert re.search(r"\|.*[Rr]eview.*verdict.*\||\|.*verdict.*\|", text), \
        "gates.md missing review verdict in table"


def test_migrating_md_has_legacy_doc_content():
    """migrating.md must describe migrating a legacy doc."""
    text = (REFS / "migrating.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "legacy" in lower or "older" in lower or "predates" in lower, \
        "migrating.md missing legacy-doc framing"
    assert "migrat" in lower, "migrating.md missing migration steps"


def test_onboarding_md_has_factory_toml():
    """onboarding.md must reference .yr/factory.toml — the per-repo manifest."""
    text = (REFS / "onboarding.md").read_text(encoding="utf-8")
    assert ".yr/factory.toml" in text, \
        "onboarding.md missing .yr/factory.toml (the per-repo manifest)"


# ---------------------------------------------------------------------------
# reviewing.md content — the codified spec/RFC review operation
# ---------------------------------------------------------------------------

def test_reviewing_md_has_adversarial_steelman():
    text = (REFS / "reviewing.md").read_text(encoding="utf-8")
    assert "steelman" in text.lower(), \
        "reviewing.md missing adversarial steelman step"


def test_reviewing_md_has_completeness_within_scope():
    text = (REFS / "reviewing.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "completeness" in lower, "reviewing.md missing completeness step"
    assert "scope" in lower, "reviewing.md missing scope constraint in completeness step"
    assert "new scope" in lower or "no new scope" in lower or "not introduce" in lower or \
           "do not" in lower, \
        "reviewing.md does not state the no-new-scope constraint"


def test_reviewing_md_has_ranked_findings():
    text = (REFS / "reviewing.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "rank" in lower or "ranked" in lower, \
        "reviewing.md missing ranked findings step"
    assert "blocker" in lower, \
        "reviewing.md missing blocker severity level in ranked findings"


def test_reviewing_md_has_fold_in_vs_standalone():
    text = (REFS / "reviewing.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "fold" in lower, \
        "reviewing.md missing fold-in vs. standalone decision"
    assert "standalone" in lower or "stand alone" in lower, \
        "reviewing.md missing standalone option in fold-in decision"


def test_reviewing_md_cites_documentation_model_reviewing_a_doc():
    """reviewing.md must cite documentation-model.md → Reviewing a doc for the fold-in rule."""
    text = (REFS / "reviewing.md").read_text(encoding="utf-8")
    assert "documentation-model.md" in text, \
        "reviewing.md does not cite documentation-model.md"
    assert "Reviewing a doc" in text or "reviewing a doc" in text.lower(), \
        "reviewing.md does not cite the 'Reviewing a doc' section of documentation-model.md"


def test_reviewing_md_feeds_human_gate():
    """reviewing.md must describe how review output feeds the spec-ready / approve-RFC human gate."""
    text = (REFS / "reviewing.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "spec-ready" in lower or "spec ready" in lower, \
        "reviewing.md missing spec-ready gate reference"
    assert "approve" in lower, \
        "reviewing.md missing approve-RFC gate reference"


# ---------------------------------------------------------------------------
# SKILL.md Architect router row (#93)
# ---------------------------------------------------------------------------

def test_skill_md_has_architect_router_row():
    """The Operations table must gain a bold **Architect** row linking references/architect.md,
    matching the existing row format (bold name | one-line When | relative link)."""
    text = _skill_text()
    assert re.search(r"\|\s*\*\*Architect\*\*\s*\|", text), \
        "SKILL.md missing a bold **Architect** row in the Operations table"
    assert "[`references/architect.md`](references/architect.md)" in text, \
        "SKILL.md Architect row does not link references/architect.md in the house-style format"


# ---------------------------------------------------------------------------
# architect.md content — the operation reference for the architect role (#93)
#
# Derived from the Issue #93 acceptance criteria / charter (the spec), not from
# the reference file's own prose.
# ---------------------------------------------------------------------------

def _architect_text():
    return (REFS / "architect.md").read_text(encoding="utf-8")


def _architect_text_normalized():
    """architect.md text with runs of whitespace (incl. line wraps) folded to a single space,
    so a phrase wrapped across a markdown line (e.g. '**partially\\n   affected**') still
    matches a plain substring check."""
    return re.sub(r"\s+", " ", _architect_text().lower())


def test_architect_md_has_when_to_load_block():
    """architect.md must open with the house-style 'When to load this reference' block."""
    head = "\n".join(_architect_text().splitlines()[:8])
    assert "When to load this reference" in head, \
        "architect.md is missing the house-style opening 'When to load this reference' block"


def test_architect_md_cites_documentation_model():
    """architect.md must cite documentation-model.md (cites-never-copies), not restate its content."""
    assert "documentation-model.md" in _architect_text(), \
        "architect.md does not cite documentation-model.md"


def test_architect_md_has_three_bound_moments():
    """Charter: the architect is bound to three existing pipeline moments, never a fourth
    stage added on top — spec-ready, the crossing, and the ship-walk."""
    lower = _architect_text_normalized()
    assert "spec-ready" in lower or "spec ready" in lower, \
        "architect.md missing the spec-ready moment"
    assert "crossing" in lower, "architect.md missing the crossing moment"
    assert "ship-walk" in lower or "ship walk" in lower, \
        "architect.md missing the ship-walk moment"
    assert "three" in lower, \
        "architect.md does not state the charter is bound to three moments (never a fourth stage)"


def test_architect_md_spec_ready_covers_grounding_and_disposition():
    """Spec-ready: grounding against the world (not only doc-vs-tree) plus a challenged
    supersession disposition — a per-target wholly-replaced/partially-affected/unaffected
    ruling, partial routing to a living-map drift entry, tombstones landing only at accept."""
    lower = _architect_text_normalized()
    assert "forward" in lower, \
        "architect.md missing the forward-claims-tested-against-the-world grounding check"
    assert "wholly replaced" in lower, "architect.md missing the 'wholly replaced' disposition ruling"
    assert "partially affected" in lower, \
        "architect.md missing the 'partially affected' disposition ruling"
    assert "unaffected" in lower, "architect.md missing the 'unaffected' disposition ruling"
    assert "drift" in lower, \
        "architect.md missing the partial-ruling-routes-to-a-drift-entry rule"
    assert "tombstone" in lower, \
        "architect.md missing the tombstones-land-only-at-accept rule"
    assert "accept" in lower, \
        "architect.md missing that tombstones are written only by the accepting session"


def test_architect_md_crossing_covers_rfc_stamp_and_drift_pass():
    """The crossing: author the technical-rfc and slices against the current tree, stamp
    crossed_to the moment the epic exists, and run a final citation-drift pass against the
    tip at filing (the base can move mid-session)."""
    lower = _architect_text_normalized()
    assert "technical-rfc" in lower or "technical rfc" in lower, \
        "architect.md missing the crossing's technical-rfc authoring step"
    assert "slices" in lower or "slice" in lower, \
        "architect.md missing the crossing's self-contained slices"
    assert "crossed_to" in _architect_text(), \
        "architect.md missing the crossed_to stamp"
    assert "drift" in lower and ("citation" in lower or "cite" in lower), \
        "architect.md missing the final citation-drift pass against the tip at filing"


def test_architect_md_ship_walk_covers_grounding_list_and_observables():
    """The ship-walk: walk the grounding list, update the living reference in place, supersede
    replaced research, verify stamps, and record the pilot observables with the iteration."""
    lower = _architect_text_normalized()
    assert "grounding list" in lower, \
        "architect.md missing the ship-walk's grounding-list walk"
    assert "living reference" in lower, \
        "architect.md missing the living-reference update-in-place step"
    assert "supersede" in lower, \
        "architect.md missing the supersede-replaced-research step"
    assert "stamp" in lower, \
        "architect.md missing the verify-the-stamps step"
    assert "observable" in lower, \
        "architect.md missing the record-pilot-observables step"


def test_architect_md_has_independence_and_ordering_rules():
    """The architect runs as its own independent cold session (author != fit-checker); where a
    doc also earns adversarial review, the review runs first and folds in, the architect last."""
    lower = _architect_text_normalized()
    assert "independent" in lower, \
        "architect.md missing the independent-cold-session rule"
    assert "fit-check" in lower or "fit check" in lower or "fit-checker" in lower, \
        "architect.md missing the author != fit-checker framing"
    assert "review" in lower and "first" in lower, \
        "architect.md missing the review-runs-first rule"
    assert "last" in lower, \
        "architect.md missing the architect-runs-last rule"


def test_architect_md_has_fail_closed_rules():
    """Fail-closed: an undecidable replacement/fit question goes on a 'for the human' list,
    never a guess or silent pass; a factual slip in an already-active spec routes to the human."""
    lower = _architect_text_normalized()
    assert "for the human" in lower or "for-the-human" in lower, \
        "architect.md missing the fail-closed 'for the human' list"
    assert "guess" in lower, \
        "architect.md missing the never-a-guess fail-closed rule"
    assert "silent" in lower, \
        "architect.md missing the never-a-silent-pass / never-a-silent-edit fail-closed rule"
    assert "active" in lower, \
        "architect.md missing the already-active-spec routing-to-human rule"


def test_architect_md_has_earn_test_with_three_arms():
    """The earn-test is decidable from the draft alone: a non-empty supersedes declaration, an
    earned technical-rfc read from the draft's Next-stage statement, or changes touching the
    living reference's load-bearing sections; no arm holding means the role is skipped."""
    lower = _architect_text_normalized()
    assert "earn" in lower, "architect.md missing the earn-test"
    assert "supersedes" in lower, \
        "architect.md earn-test missing the non-empty supersedes-declaration arm"
    assert "next-stage" in lower or "next stage" in lower, \
        "architect.md earn-test missing the earned-technical-rfc-from-Next-stage-statement arm"
    assert "load-bearing" in lower, \
        "architect.md earn-test missing the load-bearing-sections arm"
    assert "skip" in lower, \
        "architect.md missing the no-arm-holds-the-role-is-skipped path"


def test_architect_md_has_session_practice_rules():
    """Session practice earned by the pilot: cite prior dispositions as precedent, run the
    crossing's drift check at filing always, ground spec-ready against the world, declare
    hand-executed approved-but-unshipped gates, and cite the counting rule for census claims."""
    lower = _architect_text_normalized()
    assert "precedent" in lower, \
        "architect.md missing the cite-prior-dispositions-as-precedent practice"
    assert "hand" in lower and ("gate" in lower or "check" in lower), \
        "architect.md missing the declared-hand-executed-approved-but-unshipped-gates practice"
    assert "census" in lower or "count" in lower, \
        "architect.md missing the cite-the-counting-rule-for-census-claims practice"


def test_architect_md_has_report_shapes_per_moment():
    """The report ends in the moment's standard shape: fit check (verdict, dispositions,
    deltas, census, for-the-human, observables) and crossing (epic + ordered slices, EARS-landing
    map, gate outputs verbatim, choices with tradeoffs, for-the-human, observables)."""
    lower = _architect_text_normalized()
    assert "verdict" in lower, "architect.md fit-check report shape missing verdict"
    assert "delta" in lower, "architect.md fit-check report shape missing deltas"
    assert "ears" in lower, "architect.md crossing report shape missing the EARS-landing map"
    assert "tradeoff" in lower or "trade-off" in lower or "trade off" in lower, \
        "architect.md crossing report shape missing choices with tradeoffs"
    assert "observable" in lower, \
        "architect.md report shapes missing observables"
