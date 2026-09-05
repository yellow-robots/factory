"""
Tests for GitHub issue #483 — it-32 slice 2: the feature-rfc layer retires
for new work across the canon.

Derived from the issue's acceptance criteria (the spec), not from the
implementation internals:

  - documentation-model.md presents one earned layer (technical-rfc), marks
    the feature-rfc row legacy, states the live chain
    `product-spec -1:1-> technical-rfc -1:N-> task` plus the floor, and names
    the legacy chain in one sentence for existing docs.
  - `source_feature_rfc` stays in the closed frontmatter vocabulary, and
    tools/check_links.py stays unchanged and still verifies it for existing
    docs.
  - authoring.md step 2, SKILL.md, templates/feature-rfc.md, and AGENTS.md's
    input-gate sentence follow the model: each marks the layer legacy,
    none owns its own copy of the rule.
"""

import re
import subprocess
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = ROOT / "skills" / "factory" / "references" / "documentation-model.md"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
AUTHORING = ROOT / "skills" / "factory" / "references" / "authoring.md"
TEMPLATE = ROOT / "skills" / "factory" / "templates" / "feature-rfc.md"
AGENTS = ROOT / "AGENTS.md"
CHECK_LINKS = ROOT / "tools" / "check_links.py"

# Arrow glyph the model uses for chain notation (e.g. "—1:1→"): an em-dash or
# hyphen lead-in, then the arrowhead itself (→ or ->), tolerating either form
# so the test isn't glyph-brittle.
DASH = r"[—-]"
HEAD = r"(?:→|->)"


def _model_text():
    return MODEL.read_text(encoding="utf-8")


def _type_table_section():
    text = _model_text()
    match = re.search(
        r"^## The document types\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL
    )
    assert match, "documentation-model.md is missing '## The document types'"
    return match.group(1)


def _feature_rfc_row(table_text):
    for line in table_text.splitlines():
        if line.strip().startswith("|") and "`feature-rfc`" in line:
            return line
    raise AssertionError("type table has no `feature-rfc` row")


def _technical_rfc_row(table_text):
    for line in table_text.splitlines():
        if line.strip().startswith("|") and "`technical-rfc`" in line:
            return line
    raise AssertionError("type table has no `technical-rfc` row")


# ---------------------------------------------------------------------------
# The canon: one earned layer, feature-rfc marked legacy
# ---------------------------------------------------------------------------

def test_model_states_one_earned_layer_the_technical_rfc():
    section = _type_table_section()
    intro = section.split("|")[0]  # prose before the table
    assert re.search(r"one\s+is\s+\*?earned\*?", intro, re.IGNORECASE), \
        "documentation-model.md no longer states exactly one layer is earned"
    assert re.search(r"technical-rfc", intro, re.IGNORECASE), \
        "documentation-model.md's earned-layer statement does not name the technical-rfc"


def test_feature_rfc_row_marked_legacy_zero_for_new_work():
    row = _feature_rfc_row(_type_table_section())
    assert re.search(r"legacy", row, re.IGNORECASE), \
        "type table's feature-rfc row is not marked legacy"
    assert re.search(r"\b0\b.{0,25}new\s+work", row, re.IGNORECASE), \
        "type table's feature-rfc row does not state 0 for new work"
    assert re.search(r"existing\s+docs?\s+stand", row, re.IGNORECASE), \
        "type table's feature-rfc row does not say existing docs stand"


def test_technical_rfc_row_describes_direct_product_spec_pairing_as_norm():
    row = _technical_rfc_row(_type_table_section())
    assert re.search(r"per\s+product-spec\s+directly", row, re.IGNORECASE), \
        "type table's technical-rfc row does not describe pairing directly off product-spec"
    assert re.search(r"norm", row, re.IGNORECASE), \
        "type table's technical-rfc row does not call the direct pairing the norm"


def test_live_chain_is_product_spec_to_technical_rfc_to_task():
    section = _type_table_section()
    assert re.search(
        r"Live\s+chain.{0,15}product-spec\s*" + DASH + r"1:1" + HEAD +
        r"\s*technical-rfc\s*" + DASH + r"1:N" + HEAD + r"\s*task",
        section,
    ), "documentation-model.md does not state the live chain product-spec -1:1-> technical-rfc -1:N-> task"


def test_floor_is_still_stated():
    section = _type_table_section()
    assert re.search(r"floor.{0,40}product-spec\s*" + HEAD + r"\s*task", section, re.IGNORECASE), \
        "documentation-model.md dropped the product-spec -> task(s) floor statement"


def test_legacy_chain_named_in_one_sentence_for_existing_docs():
    section = _type_table_section()
    # find the sentence naming the legacy chain
    sentence_match = re.search(r"[^.]*existing[^.]*feature-rfc[^.]*\.", section, re.IGNORECASE)
    assert sentence_match, \
        "documentation-model.md does not name the legacy chain in a sentence about existing docs"
    sentence = sentence_match.group(0)
    assert re.search(
        r"product-spec\s*" + DASH + r"1:N" + HEAD + r"\s*feature-rfc\s*" + DASH +
        r"1:1" + HEAD + r"\s*technical-rfc\s*" + DASH + r"1:N" + HEAD + r"\s*task",
        sentence,
    ), "the legacy-chain sentence does not spell out product-spec -1:N-> feature-rfc -1:1-> technical-rfc -1:N-> task"


def test_airlock_legacy_crossing_named_existing_docs_only():
    text = _model_text()
    match = re.search(r"^## The airlock.*?\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert match, "documentation-model.md is missing '## The airlock'"
    body = match.group(1)
    assert re.search(r"legacy\s+crossing.{0,40}existing\s+docs\s+only", body, re.IGNORECASE), \
        "airlock section does not name the legacy crossing as existing-docs-only"
    assert re.search(r"feature-rfc\s*" + DASH + r"?\s*" + HEAD + r"?\s*technical-rfc", body), \
        "airlock section does not keep the feature-rfc -> technical-rfc legacy crossing sentence"


# ---------------------------------------------------------------------------
# source_feature_rfc stays in the closed frontmatter vocabulary
# ---------------------------------------------------------------------------

def test_source_feature_rfc_stays_in_frontmatter_vocabulary():
    text = _model_text()
    match = re.search(r"^## Frontmatter.*?\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert match, "documentation-model.md is missing '## Frontmatter'"
    body = match.group(1)
    assert "source_feature_rfc" in body, \
        "the Frontmatter section no longer lists source_feature_rfc in the closed vocabulary"


def test_check_links_unchanged_against_base():
    """tools/check_links.py must not be touched by this iteration."""
    base_sha = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    base_content = subprocess.run(
        ["git", "show", f"{base_sha}:tools/check_links.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert CHECK_LINKS.read_text(encoding="utf-8") == base_content, \
        "tools/check_links.py changed — this iteration is not supposed to touch it"


def test_check_links_still_verifies_source_feature_rfc():
    """Behavioral check that check_links generically covers any source_* key,
    including source_feature_rfc, for existing docs."""
    sys_path_root = str(ROOT)
    import sys
    if sys_path_root not in sys.path:
        sys.path.insert(0, sys_path_root)
    from tools.check_links import check_links

    ok_doc = (
        "---\n"
        "type: technical-rfc\n"
        "source_feature_rfc: \"[[02-some-feature]]\"\n"
        "---\n"
        "body\n"
    )
    errors = check_links(ok_doc, vault_root=ROOT)  # no vault match -> unresolved wikilink
    assert any("source_feature_rfc" in e for e in errors), \
        "check_links no longer inspects source_feature_rfc frontmatter"

    empty_doc = (
        "---\n"
        "type: technical-rfc\n"
        "source_feature_rfc: \"\"\n"
        "---\n"
        "body\n"
    )
    errors = check_links(empty_doc, vault_root=ROOT)
    assert any("source_feature_rfc" in e and "empty" in e for e in errors), \
        "check_links no longer flags an empty source_feature_rfc crossing-link"


# ---------------------------------------------------------------------------
# Followers mark the layer legacy without owning a copy of the rule
# ---------------------------------------------------------------------------

def test_authoring_step2_heading_marks_feature_rfc_legacy():
    text = AUTHORING.read_text(encoding="utf-8")
    match = re.search(r"^### 2\. feature-rfc\s*(.*)$", text, re.MULTILINE)
    assert match, "authoring.md is missing its '### 2. feature-rfc' step heading"
    assert re.search(r"legacy", match.group(1), re.IGNORECASE), \
        "authoring.md step 2 heading does not mark feature-rfc legacy"
    assert re.search(r"not\s+authored\s+for\s+new\s+work", match.group(1), re.IGNORECASE), \
        "authoring.md step 2 heading does not say 'not authored for new work'"


def test_authoring_step2_does_not_own_a_copy_of_the_live_chain_rule():
    """The rule (cardinalities / chain notation) lives in documentation-model.md
    alone; authoring.md should point there rather than restate the chain."""
    text = AUTHORING.read_text(encoding="utf-8")
    step2_start = text.find("### 2. feature-rfc")
    step3_start = text.find("### 3.", step2_start)
    assert step2_start != -1 and step3_start != -1
    step2_body = text[step2_start:step3_start]
    assert not re.search(r"1:1" + HEAD, step2_body), \
        "authoring.md step 2 restates the chain-notation rule instead of citing documentation-model.md"
    assert re.search(r"documentation-model\.md", step2_body), \
        "authoring.md step 2 does not cite documentation-model.md for the legacy rule"


def test_authoring_step2_keeps_outline_pre_gate_sentence():
    text = AUTHORING.read_text(encoding="utf-8")
    step2_start = text.find("### 2. feature-rfc")
    step3_start = text.find("### 3.", step2_start)
    assert step2_start != -1 and step3_start != -1
    step2_body = text[step2_start:step3_start]
    assert re.search(r"send\s+the\s+outline\s+to\s+the\s+human\s+first", step2_body, re.IGNORECASE), \
        "authoring.md step 2 lost the outline pre-gate sentence"


def test_skill_md_marks_feature_rfc_legacy_in_authoring_row():
    text = SKILL.read_text(encoding="utf-8")
    match = re.search(r"^\|\s*\*\*Authoring\*\*\s*\|.*\|.*\|\s*$", text, re.MULTILINE)
    assert match, "SKILL.md is missing its Authoring operations row"
    row = match.group(0)
    assert re.search(r"feature-rfc.{0,40}legacy", row, re.IGNORECASE), \
        "SKILL.md's Authoring row does not mark feature-rfc legacy"


def test_skill_md_diagram_drops_feature_rfc_bracket():
    text = SKILL.read_text(encoding="utf-8")
    match = re.search(r"^```\nUPPER.*?\n```", text, re.MULTILINE | re.DOTALL)
    assert match, "SKILL.md is missing the two-pipelines diagram"
    diagram = match.group(0)
    assert "[feature-rfc" not in diagram, \
        "SKILL.md diagram still brackets the feature-rfc layer"
    # UPPER's two lines are the left-hand column of a two-pipeline diagram:
    # one line's left side ends at product-spec's arrow, the very next
    # line's left side opens on technical-rfc directly (no feature-rfc row
    # between them).
    lines = diagram.splitlines()
    product_spec_line = next((i for i, l in enumerate(lines) if l.strip().startswith("product-spec")), None)
    assert product_spec_line is not None, "SKILL.md diagram is missing its product-spec line"
    left_column = re.split(r"\s{2,}", lines[product_spec_line].strip())[0]
    assert re.fullmatch(r"product-spec\s*" + HEAD, left_column), \
        "SKILL.md diagram's product-spec line does not end its left column on a lone arrow"
    next_line = lines[product_spec_line + 1]
    assert re.match(r"\s*technical-rfc\s*" + HEAD + r"\s*task", next_line), \
        "SKILL.md diagram's line after product-spec does not open directly on technical-rfc -> task"


def test_skill_md_description_stays_byte_equal_to_plugin_manifest():
    plugin = ROOT / ".claude-plugin" / "plugin.json"
    import json
    plugin_desc = json.loads(plugin.read_text(encoding="utf-8"))["description"]

    text = SKILL.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0].strip() == "---", "SKILL.md is missing its opening frontmatter fence"
    desc_lines = []
    in_desc_block = False
    skill_desc = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("description:"):
            val = line.split(":", 1)[1].strip()
            if val in (">-", ">", "|-", "|"):
                in_desc_block = True
            else:
                skill_desc = val.strip('"')
        elif in_desc_block:
            if line.startswith("  ") or line.startswith("\t"):
                desc_lines.append(line.strip())
            elif line.strip() == "":
                pass
            else:
                in_desc_block = False
    if skill_desc is None:
        skill_desc = " ".join(desc_lines)

    normalize = lambda s: re.sub(r"\s+", " ", s).strip()
    assert normalize(skill_desc) == normalize(plugin_desc), \
        "SKILL.md description drifted from .claude-plugin/plugin.json's description"


def test_template_frontmatter_fence_stays_on_line_1():
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", \
        "templates/feature-rfc.md no longer opens with '---' on line 1"


def test_template_gains_legacy_banner_after_closing_fence():
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    close_idx = next(i for i in range(1, len(lines)) if lines[i] == "---")
    # first non-fence line after frontmatter closes
    banner = lines[close_idx + 1]
    assert re.search(r"legacy", banner, re.IGNORECASE), \
        "templates/feature-rfc.md does not carry a LEGACY banner right after its frontmatter fence"
    assert re.search(r"not\s+authored\s+for\s+new\s+work", banner, re.IGNORECASE), \
        "templates/feature-rfc.md legacy banner does not say 'not authored for new work'"


def test_template_keeps_supersedes_scaffold():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r"^supersedes:\s*\[\]", text, re.MULTILINE), \
        "templates/feature-rfc.md dropped its supersedes: [] frontmatter scaffold"


def test_agents_md_input_gate_names_feature_rfc_as_legacy():
    text = AGENTS.read_text(encoding="utf-8")
    match = re.search(r"input.{0,10}gate sits at the design artifacts.*?veto", text, re.DOTALL)
    assert match, "AGENTS.md is missing the input-gate paragraph"
    para = match.group(0)
    assert re.search(r"product-spec", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph no longer names product-spec"
    assert re.search(r"legacy\s+feature-rfc", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not name feature-rfc as legacy"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
