"""
Tests for Issue #9 — Cross-cutting layer in the documentation model (skill 0.6.0).

Derived from the Issue #9 acceptance criteria (the spec), not from the
implementation internals. These are text-property assertions against
skills/factory/references/documentation-model.md (the model's single living
copy) and the version bump in .claude-plugin/plugin.json.
"""

import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = ROOT / "skills" / "factory" / "references" / "documentation-model.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"


def _text():
    return MODEL.read_text(encoding="utf-8")


def _plugin_data():
    return json.loads(PLUGIN.read_text(encoding="utf-8"))


def _lower():
    return _text().lower()


# ---------------------------------------------------------------------------
# Cross-cutting homes
# ---------------------------------------------------------------------------

def test_defines_cross_cutting_homes_section():
    """A distinct section/heading introduces the cross-cutting homes concept."""
    text = _text()
    assert re.search(r"cross-cutting", text, re.IGNORECASE), \
        "documentation-model.md has no 'cross-cutting' content at all"
    assert re.search(r"^#+.*cross-cutting", text, re.IGNORECASE | re.MULTILINE), \
        "documentation-model.md has no heading naming the cross-cutting layer"


def test_names_example_domain_noun_homes():
    """Example domain-noun homes (architecture/, operations/, strategy/) are named."""
    text = _text()
    for example in ("architecture", "operations", "strategy"):
        assert re.search(rf"\b{example}/", text), \
            f"documentation-model.md does not name an example cross-cutting home: {example}/"


def test_cross_cutting_homes_are_alongside_iterations():
    lower = _lower()
    assert "alongside" in lower and "iterations/" in _text(), \
        "documentation-model.md does not state cross-cutting homes sit alongside iterations/"


def test_cross_cutting_homes_are_fully_governed():
    lower = _lower()
    assert "governed" in lower, \
        "documentation-model.md does not describe cross-cutting homes as governed"
    assert "closed" in lower and "frontmatter" in lower, \
        "documentation-model.md does not tie cross-cutting homes to the closed frontmatter vocabulary"


def test_cross_cutting_homes_supporting_types_only():
    """Homes carry supporting types only (research/note/runbook), never spine types."""
    text = _text()
    lower = text.lower()
    assert "research" in lower and "note" in lower and "runbook" in lower, \
        "documentation-model.md does not list the supporting types (research/note/runbook) for homes"
    assert re.search(r"never\s+spine|not\s+a\s+spine|never\s+.{0,20}spine", lower), \
        "documentation-model.md does not explicitly forbid spine types in cross-cutting homes"
    for spine_type in ("product-spec", "feature-rfc", "technical-rfc", "task"):
        assert spine_type in text, \
            f"documentation-model.md cross-cutting section should name spine type {spine_type} as excluded"


def test_deterministic_marker_for_governed_homes():
    """The deterministic marker: any domain-noun sibling folder of iterations/ is a governed home."""
    lower = _lower()
    assert "governed home" in lower, \
        "documentation-model.md does not use the term 'governed home'"
    # The marker ties folder adjacency to iterations/ deterministically.
    assert re.search(r"folder.{0,40}(draws|is)\s+the\s+line", lower) or \
        re.search(r"alongside\s+`?iterations/`?.{0,60}governed\s+home", lower), \
        "documentation-model.md does not state the deterministic sibling-folder marker for governed homes"


def test_loose_root_files_stay_free_form():
    lower = _lower()
    assert "free-form" in lower, \
        "documentation-model.md does not mention free-form root files"
    assert re.search(r"loose\s+files.{0,60}free-form", lower), \
        "documentation-model.md does not state that loose files at the component root stay free-form"


def test_components_without_homes_stay_on_unmodified_model():
    lower = _lower()
    assert re.search(r"(no\s+cross-cutting\s+homes|none\s+of\s+them).{0,80}(unmodified|stays\s+on)", lower) or \
        re.search(r"unmodified\s+model", lower), \
        "documentation-model.md does not state that components without homes stay on the unmodified model"


def test_operations_home_holds_executed_records():
    lower = _lower()
    assert re.search(r"`?operations/`?.{0,120}(executed\s+records|runbooks)", lower), \
        "documentation-model.md does not state that operations/ holds executed records (runbooks + scripts)"
    assert "script" in lower, \
        "documentation-model.md does not mention companion scripts for operations/"


# ---------------------------------------------------------------------------
# The living reference
# ---------------------------------------------------------------------------

def test_defines_living_reference_section():
    text = _text()
    assert re.search(r"living\s+reference", text, re.IGNORECASE), \
        "documentation-model.md has no 'living reference' content"


def test_living_reference_at_most_one_per_component():
    lower = _lower()
    assert re.search(r"at\s+most\s+one", lower), \
        "documentation-model.md does not cap the living reference at one per component"


def test_living_reference_rationale_hub_note_risk():
    """Rationale: one big picture; a second is the first step back toward the banned hub note."""
    lower = _lower()
    assert "big picture" in lower, \
        "documentation-model.md does not state the 'one big picture' rationale for the living reference cap"
    assert re.search(r"second.{0,60}(hub\s+note|step\s+back)", lower), \
        "documentation-model.md does not tie a second living reference to the banned hub note"


def test_living_reference_is_a_note_type_kept_current():
    lower = _lower()
    assert re.search(r"`?note`?.{0,60}kept\s+current|kept\s+current", lower), \
        "documentation-model.md does not state the living reference is a kept-current note"


def test_mirror_line_stated_as_rule():
    """The mirror line: may render facts as navigational summary if every fact cites its
    authoritative home and none is asserted on the reference's own authority."""
    text = _text()
    lower = text.lower()
    assert "mirror line" in lower, \
        "documentation-model.md does not name 'the mirror line'"
    assert "navigational summary" in lower, \
        "documentation-model.md does not describe the living reference as a navigational summary"
    assert re.search(r"cites?\s+its\s+authoritative\s+home", lower), \
        "documentation-model.md mirror line does not require every fact to cite its authoritative home"
    assert re.search(r"none.{0,40}asserted.{0,40}own\s+authority", lower), \
        "documentation-model.md mirror line does not forbid facts asserted on the reference's own authority"


def test_living_reference_cites_never_copies():
    lower = _lower()
    assert re.search(r"cites?,?\s+never\s+copies", lower), \
        "documentation-model.md does not state the living reference cites, never copies"


def test_living_reference_how_sections_become_pointers():
    lower = _lower()
    assert re.search(r"how.{0,40}(section|pointer).{0,60}pointer.{0,20}(repo|code)", lower) or \
        re.search(r"pointers?\s+into\s+the\s+repo", lower), \
        "documentation-model.md does not state that 'how' sections become pointers into the repo when code ships"


# ---------------------------------------------------------------------------
# Shipping still freezes the why (spine docs) — reconciled wording
# ---------------------------------------------------------------------------

def test_freeze_still_binds_spine_docs():
    lower = _lower()
    assert "shipping" in lower and "freeze" in lower, \
        "documentation-model.md does not restate shipping freezes the why"
    assert "spine" in lower, \
        "documentation-model.md does not scope the freeze to spine docs in the cross-cutting section"


def test_living_reference_is_obligation_not_exemption():
    """The model reference must no longer be described as *exempt* from the freeze —
    it is one of the living supporting docs, with an obligation to stay current on top
    of the freeze (not a carve-out from it)."""
    lower = _lower()
    assert re.search(r"not\s+an?\s+exempt(ion)?", lower), \
        "documentation-model.md no longer explicitly rules out framing the living reference as an exemption"
    assert "obligation" in lower, \
        "documentation-model.md does not describe the living reference's kept-current duty as an obligation"
    assert re.search(r"supporting\s+types.{0,40}(were\s+)?always\s+living", lower), \
        "documentation-model.md does not state that supporting types were always living"


# ---------------------------------------------------------------------------
# The admission test
# ---------------------------------------------------------------------------

def test_admission_test_named_update_trigger():
    text = _text()
    lower = text.lower()
    assert "admission test" in lower, \
        "documentation-model.md does not name 'the admission test'"
    assert re.search(r"name.{0,20}its\s+update\s+trigger|update\s+trigger", lower), \
        "documentation-model.md admission test does not require naming an update trigger"


def test_admission_test_requires_refusal():
    lower = _lower()
    assert re.search(r"must\s+\*{0,2}refuse", lower), \
        "documentation-model.md does not require an agent to refuse creating a doc without an update trigger"


# ---------------------------------------------------------------------------
# Grounding — every iteration's 01 cites cross-cutting docs it depends on
# ---------------------------------------------------------------------------

def test_grounding_requires_01_to_cite_cross_cutting_docs():
    text = _text()
    lower = text.lower()
    assert "grounding" in lower, \
        "documentation-model.md does not name grounding"
    assert re.search(r"\b01\b", text), \
        "documentation-model.md grounding rule does not reference the iteration's 01 doc"
    assert re.search(r"wikilink", lower), \
        "documentation-model.md grounding rule does not require prose wikilinks"
    assert re.search(r"relies\s+on\s+or\s+affects|depends\s+on", lower), \
        "documentation-model.md grounding rule does not scope citations to docs relied on or affected"


def test_grounding_does_not_open_frontmatter_vocabulary():
    lower = _lower()
    assert re.search(r"no\s+new\s+key|vocabulary\s+stays\s+closed|stays\s+closed", lower), \
        "documentation-model.md does not state grounding citations keep the frontmatter vocabulary closed"


# ---------------------------------------------------------------------------
# The maintenance contract
# ---------------------------------------------------------------------------

def test_maintenance_contract_named():
    lower = _lower()
    assert "maintenance contract" in lower, \
        "documentation-model.md does not name 'the maintenance contract'"


def test_maintenance_contract_enforcement_is_procedural_not_automated():
    lower = _lower()
    assert "procedural" in lower, \
        "documentation-model.md does not state maintenance-contract enforcement is procedural"
    assert re.search(r"not\s+automated", lower), \
        "documentation-model.md does not explicitly state enforcement is not automated"


def test_maintenance_contract_has_all_five_triggers():
    text = _text()
    lower = text.lower()
    triggers_and_bindings = {
        "grounding": r"authoring\s+the\s+`?01`?",
        "read at spec-ready": r"spec-ready\s+gate",
        "write at ship": r"iteration\s+close",
        "executed records": r"operations/.{0,60}(appends|execution)|operation.{0,40}execution",
        "framing events": r"framing\s+conversation",
    }
    for trigger, binding_pattern in triggers_and_bindings.items():
        assert trigger in lower, \
            f"documentation-model.md maintenance contract is missing the '{trigger}' trigger"
        assert re.search(binding_pattern, lower), \
            f"documentation-model.md does not bind '{trigger}' to its named factory moment"


def test_advisory_defaults_for_free_form_root():
    text = _text()
    lower = text.lower()
    assert "advisory" in lower, \
        "documentation-model.md does not name the advisory defaults for the free-form root"
    assert re.search(r"strategy/.{0,80}(program-level|program\s+decisions)", lower), \
        "documentation-model.md advisory defaults do not cover strategy/ before program-level decisions"
    assert re.search(r"ideas[\s-]backlog.{0,60}append-only|append-only.{0,60}ideas", lower), \
        "documentation-model.md advisory defaults do not cover the append-only ideas backlog"
    assert re.search(r"orientation\s+note.{0,80}co-evolves?", lower), \
        "documentation-model.md advisory defaults do not cover the orientation note co-evolving"
    assert "convention" in lower, \
        "documentation-model.md does not mark the free-form-root defaults as convention, not governance"


# ---------------------------------------------------------------------------
# Hub/index-note ban retained
# ---------------------------------------------------------------------------

def test_hub_note_ban_retained():
    lower = _lower()
    assert re.search(r"hub[/\s-]*(index[\s-]*)?note.{0,30}ban", lower) or \
        re.search(r"ban.{0,40}hub", lower), \
        "documentation-model.md does not retain the hub/index-note ban"


def test_computed_views_are_sanctioned_dashboard_form():
    lower = _lower()
    assert "computed view" in lower, \
        "documentation-model.md does not name computed views as the sanctioned dashboard form"
    assert re.search(r"only\s+sanctioned\s+dashboard\s+form", lower), \
        "documentation-model.md does not state computed views are the ONLY sanctioned dashboard form"
    assert re.search(r"maintained\s+frontmatter", lower), \
        "documentation-model.md does not tie computed views to maintained frontmatter"
    assert re.search(r"hold(s)?\s+no\s+facts\s+of\s+its\s+own|no\s+facts\s+of\s+their\s+own", lower), \
        "documentation-model.md does not state computed views hold no facts of their own"


# ---------------------------------------------------------------------------
# Grounding-integrity gap — a named, accepted limitation
# ---------------------------------------------------------------------------

def test_grounding_integrity_gap_is_named():
    lower = _lower()
    assert "grounding" in lower and "gap" in lower, \
        "documentation-model.md does not name the grounding-integrity gap"
    assert re.search(r"nothing\s+machine-gates|not\s+machine-gated", lower) or \
        re.search(r"machine-gate", lower), \
        "documentation-model.md does not state grounding citations are not machine-gated"


def test_grounding_gap_scopes_check_links_to_spine_only():
    lower = _lower()
    assert re.search(r"check_links\s+verifies\s+spine\s+crossing", lower) or \
        re.search(r"check_links.{0,60}spine", lower), \
        "documentation-model.md does not state check_links verifies spine crossings only"


def test_grounding_gap_checked_procedurally():
    lower = _lower()
    assert re.search(r"checked\s+(only\s+)?procedurally|procedurally,?\s+at", lower), \
        "documentation-model.md does not state the grounding gap is checked procedurally at the bound moments"


# ---------------------------------------------------------------------------
# Structure — the tree shows optional domain-noun homes alongside iterations/
# ---------------------------------------------------------------------------

def test_structure_section_shows_optional_cross_cutting_homes():
    text = _text()
    structure_match = re.search(r"^## Structure\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert structure_match, "documentation-model.md is missing a ## Structure section"
    structure_body = structure_match.group(1)
    assert "iterations/" in structure_body, \
        "Structure section does not show the iterations/ folder"
    assert re.search(r"architecture/|operations/|strategy/", structure_body), \
        "Structure section does not show example cross-cutting homes alongside iterations/"
    assert re.search(r"optional", structure_body, re.IGNORECASE), \
        "Structure section does not mark the cross-cutting homes as optional"


def test_iteration_unit_bullet_reconciled_with_cross_cutting_homes():
    """The 'iteration unit' bullet (## The unit: an iteration) must acknowledge governed
    cross-cutting homes rather than asserting everything outside iterations/ is free-form."""
    text = _text()
    unit_match = re.search(r"^## The unit: an iteration\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert unit_match, "documentation-model.md is missing a '## The unit: an iteration' section"
    unit_body = unit_match.group(1)
    assert re.search(r"cross-cutting", unit_body, re.IGNORECASE), \
        "The 'iteration unit' bullet does not acknowledge cross-cutting homes"


# ---------------------------------------------------------------------------
# Frontmatter vocabulary stays closed — no new keys introduced by this change
# ---------------------------------------------------------------------------

def test_frontmatter_vocabulary_unchanged():
    """The closed frontmatter vocabulary's Base/Crossing-links key lists under ## Frontmatter
    must not have grown new keys as part of the cross-cutting layer (grounding/homes are
    prose-only, per the criteria: 'no new keys')."""
    text = _text()
    fm_match = re.search(r"^## Frontmatter.*?\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert fm_match, "documentation-model.md is missing the ## Frontmatter section"
    fm_body = fm_match.group(1)
    key_list_lines = [
        line for line in fm_body.splitlines()
        if line.strip().startswith("- **Base") or line.strip().startswith("- **Crossing-links")
    ]
    assert key_list_lines, \
        "documentation-model.md Frontmatter section is missing the Base/Crossing-links key-list bullets"
    known_keys = {
        "type", "status", "created", "updated",
        "source_spec", "source_feature_rfc", "source_technical_rfc",
        "crossed_to", "superseded_by", "retired_reason",
    }
    found_keys = set()
    for line in key_list_lines:
        found_keys |= set(re.findall(r"`([a-z_]+)`", line))
    unexpected = found_keys - known_keys
    assert not unexpected, \
        f"documentation-model.md Frontmatter key lists introduce unexpected keys: {unexpected}"


# ---------------------------------------------------------------------------
# Version bump — .claude-plugin/plugin.json 0.5.0 -> 0.6.0
# ---------------------------------------------------------------------------

def test_plugin_version_is_0_6_0():
    assert _plugin_data()["version"] == "0.6.1", \
        f".claude-plugin/plugin.json version is {_plugin_data()['version']!r}, expected '0.6.1'"


def test_plugin_version_is_not_the_old_0_5_0():
    assert _plugin_data()["version"] != "0.5.0"


# ---------------------------------------------------------------------------
# Out-of-scope guard — SKILL.md is not touched by this change's restatement
# ---------------------------------------------------------------------------

def test_skill_md_does_not_restate_cross_cutting_maintenance_contract():
    """SKILL.md defers to the reference on demand; it must not restate the maintenance
    contract table introduced by this change."""
    text = SKILL.read_text(encoding="utf-8")
    assert "maintenance contract" not in text.lower(), \
        "SKILL.md restates the maintenance contract — it should defer to documentation-model.md instead"
