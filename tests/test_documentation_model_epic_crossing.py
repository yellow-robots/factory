"""
Tests for Issue #13 — Bless the product-spec -> technical-rfc-on-the-epic
crossing variant in the documentation model (skill 0.6.1).

Derived from the Issue #13 acceptance criteria (the spec), not from the
implementation internals. These are text-property assertions against
skills/factory/references/documentation-model.md (the model's single living
copy), the version bump in .claude-plugin/plugin.json, and an out-of-scope
guard on skills/factory/SKILL.md.
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


def _lower():
    return _text().lower()


def _plugin_data():
    return json.loads(PLUGIN.read_text(encoding="utf-8"))


def _airlock_section():
    text = _text()
    match = re.search(
        r"^## The airlock.*?\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL
    )
    assert match, "documentation-model.md is missing the '## The airlock' section"
    return match.group(1)


# ---------------------------------------------------------------------------
# The airlock names the new crossing variant
# ---------------------------------------------------------------------------

def test_airlock_names_product_spec_to_technical_rfc_variant():
    """The airlock section must name a crossing directly from product-spec to
    technical-rfc, distinct from the feature-rfc -> technical-rfc crossing and
    the product-spec -> task floor."""
    body = _airlock_section()
    assert re.search(r"product-spec.{0,10}(→|->|to)\s*technical-rfc", body, re.IGNORECASE), \
        "airlock section does not name a product-spec -> technical-rfc crossing"
    assert re.search(r"epic\s+issue", body, re.IGNORECASE), \
        "airlock section does not tie the new crossing to the epic Issue"


def test_airlock_variant_skips_feature_rfc():
    """The variant must be framed as earned without a feature-rfc (settled in
    the spec), skipping the feature-rfc layer."""
    body = _airlock_section().lower()
    assert re.search(r"no\s+feature-rfc\s+(is\s+)?earned", body) or \
        re.search(r"skip(s|ping)?\s+the\s+feature-rfc", body), \
        "airlock section does not state the variant skips/has no earned feature-rfc"


def test_airlock_variant_still_cites_never_copies():
    """cites, never copies must apply to the new variant too (no mirror to drift)."""
    body = _airlock_section().lower()
    occurrences = len(re.findall(r"cites?,?\s+never\s+copies", body))
    assert occurrences >= 2, (
        "airlock section should restate 'cites, never copies' for the new "
        f"product-spec -> technical-rfc variant (found {occurrences} occurrence(s), expected >= 2)"
    )


def test_airlock_variant_present_alongside_existing_two():
    """All three crossing variants — feature-rfc -> technical-rfc,
    product-spec -> task, and the new product-spec -> technical-rfc — are
    named in the same airlock section."""
    body = _airlock_section()
    assert re.search(r"feature-rfc.{0,10}(→|->).{0,10}technical-rfc", body), \
        "airlock section lost the existing feature-rfc -> technical-rfc crossing"
    assert re.search(r"product-spec.{0,10}(→|->).{0,10}task", body), \
        "airlock section lost the existing product-spec -> task floor crossing"
    assert re.search(r"product-spec.{0,10}(→|->).{0,10}technical-rfc", body), \
        "airlock section is missing the new product-spec -> technical-rfc crossing"


def test_airlock_variant_uses_source_spec_not_source_feature_rfc():
    """The new variant's up-spine link must be named as source_spec, explicitly
    contrasted with source_feature_rfc (which the classic crossing uses)."""
    body = _airlock_section()
    assert "`source_spec`" in body or "source_spec" in body, \
        "airlock section does not name source_spec as the new variant's up-spine link"
    assert re.search(r"not\s+`?source_feature_rfc`?", body), \
        "airlock section does not explicitly contrast source_spec with source_feature_rfc"


def test_airlock_variant_reuses_existing_vocabulary_no_new_key():
    """The variant must state it introduces no new frontmatter key — it reuses
    the closed vocabulary's existing source_spec."""
    body = _airlock_section().lower()
    assert re.search(r"no\s+new\s+key", body), \
        "airlock section does not state that no new frontmatter key is introduced"


# ---------------------------------------------------------------------------
# The document-types table / chain acknowledges the direct crossing
# ---------------------------------------------------------------------------

def test_document_types_table_allows_technical_rfc_direct_from_spec():
    """The technical-rfc row's cardinality must allow a technical-rfc earned
    directly per product-spec (not only per feature-rfc)."""
    text = _text()
    table_match = re.search(r"^## The document types\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert table_match, "documentation-model.md is missing the '## The document types' section"
    table_body = table_match.group(1)
    technical_rfc_row = next(
        (line for line in table_body.splitlines() if line.strip().startswith("| `technical-rfc`")),
        None,
    )
    assert technical_rfc_row, "document types table is missing the technical-rfc row"
    assert re.search(r"product-spec", technical_rfc_row), \
        "technical-rfc row cardinality does not acknowledge a direct product-spec crossing"


# ---------------------------------------------------------------------------
# Frontmatter vocabulary stays closed — no new keys introduced
# ---------------------------------------------------------------------------

def test_frontmatter_vocabulary_still_closed_and_unchanged():
    """The closed frontmatter vocabulary's key lists must not have grown a new
    key as part of this change (the variant reuses source_spec only)."""
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
    assert "source_spec" in found_keys, \
        "documentation-model.md Frontmatter section dropped source_spec from the crossing-links keys"


# ---------------------------------------------------------------------------
# Version bump — .claude-plugin/plugin.json 0.6.0 -> 0.6.1
# ---------------------------------------------------------------------------

def test_plugin_version_is_current():
    assert _plugin_data()["version"] == "0.6.3", \
        f".claude-plugin/plugin.json version is {_plugin_data()['version']!r}, expected '0.6.3'"


def test_plugin_version_is_not_the_old_0_6_0():
    assert _plugin_data()["version"] != "0.6.0"


def test_plugin_and_skill_description_still_match_exactly():
    """.claude-plugin/plugin.json description must still match SKILL.md's
    frontmatter description exactly (this is a patch release; the description
    is not part of this change, but the two must stay in lockstep)."""
    plugin_desc = _plugin_data()["description"]

    lines = SKILL.read_text(encoding="utf-8").split("\n")
    in_fm = False
    in_desc_block = False
    desc_lines = []
    skill_desc = None
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
    assert normalize(skill_desc) == normalize(plugin_desc), (
        f"Description mismatch:\n  SKILL.md: {skill_desc!r}\n  plugin.json: {plugin_desc!r}"
    )


# ---------------------------------------------------------------------------
# Out-of-scope guard — SKILL.md is not repurposed to restate the model
# ---------------------------------------------------------------------------

def test_skill_md_does_not_restate_the_new_crossing_variant():
    """SKILL.md defers to the reference on demand; it must not restate the
    new product-spec -> technical-rfc (on the epic Issue) crossing variant
    or its source_spec-vs-source_feature_rfc distinction introduced by this
    change."""
    text = SKILL.read_text(encoding="utf-8")
    lower = text.lower()
    assert not re.search(r"no\s+feature-rfc\s+(is\s+)?earned", lower), \
        "SKILL.md restates the new crossing variant's 'no feature-rfc earned' framing"
    assert not re.search(r"source_spec.{0,40}not.{0,20}source_feature_rfc", lower), \
        "SKILL.md restates the new variant's source_spec-vs-source_feature_rfc distinction"
