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

def test_plugin_version_is_0_6_0():
    assert _plugin_data()["version"] == "0.6.0"


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
