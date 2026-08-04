"""
Tests for Issue #392 — check_supersession's `§`-style section-anchor rule (#318, narrowed by
#338/#339) learns two more exemptions, on BOTH surfaces (integrity mode's sweep and the draft gate):

  1. an occurrence sitting inside an inline code span or a fenced block — a doc quoting the
     defect shape it describes, not committing it;
  2. an occurrence on a line that backtick-cites a repo file path (a token carrying a known repo
     extension, e.g. `.md`, `.py`, `.sh`, `.toml`, `.yml`) — prose citing a repo file's own
     numbered section was never a brain link.

Derived from the Issue #392 acceptance criteria (the spec), never from `check_supersession.py`'s
own implementation. Fixtures reproduce the shapes of the three named vault exhibits in-repo; none
of these tests reads the live vault.
"""

import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_supersession import check_draft, check_integrity


def _vault_file(root, relpath, content):
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _doc(type_="task", status="active", body="# Body\n"):
    return f"---\ntype: {type_}\nstatus: {status}\n---\n{body}"


def _anchor_lines(tmp_path, body):
    """(anchor_findings, failed) for one doc's body, swept through integrity mode."""
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active", body=body))
    lines, failed = check_integrity(vault_root=tmp_path, scope="proj")
    return [l for l in lines if "§-style anchor reference" in l], failed


def _draft_errors(body):
    return check_draft(_doc(type_="task", body=body), vault_root=pathlib.Path("/nonexistent"))


# =====================================================================================
# exemption 1 — inline code span, both surfaces (issue #392)
# =====================================================================================

def test_integrity_bare_anchor_inside_inline_code_span_not_flagged(tmp_path):
    body = "# Body\n\nExample of the defect: `See §4 for details.`\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_draft_gate_bare_anchor_inside_inline_code_span_not_flagged():
    body = "# Body\n\nExample of the defect: `See §4 for details.`\n"
    assert _draft_errors(body) == []


def test_integrity_anchor_inside_backticked_wikilink_text_not_flagged(tmp_path):
    # a code span quoting the dead-reference wikilink shape itself, not a live link
    body = "# Body\n\nThe broken shape looks like `[[Note#§4]]`, which Obsidian cannot resolve.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_bare_anchor_outside_code_span_on_same_line_still_flagged(tmp_path):
    # the exemption is scoped to the code span itself, not the whole line
    body = "# Body\n\n`See §4 for details.` But §9 here is bare.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§9" in l for l in anchor_lines)
    assert not any("§4" in l for l in anchor_lines)


# =====================================================================================
# exemption 1 — fenced block, both surfaces (issue #392)
# =====================================================================================

def test_integrity_bare_anchor_inside_fenced_block_not_flagged(tmp_path):
    body = "# Body\n\n```\nSee §4 for details.\n```\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_draft_gate_bare_anchor_inside_fenced_block_not_flagged():
    body = "# Body\n\n```\nSee §4 for details.\n```\n"
    assert _draft_errors(body) == []


def test_integrity_bare_anchor_inside_tilde_fenced_block_not_flagged(tmp_path):
    body = "# Body\n\n~~~\nSee §4 for details.\n~~~\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_integrity_anchor_after_closing_fence_still_flagged(tmp_path):
    # fenced state toggles off at the closing delimiter — prose after it scans normally
    body = "# Body\n\n```\nSee §4 in code.\n```\n\nSee §9 for real.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§9" in l for l in anchor_lines)
    assert not any("§4" in l for l in anchor_lines)


# =====================================================================================
# exemption 2 — backticked repo-path citation, both surfaces (issue #392)
# =====================================================================================

def test_integrity_line_citing_backticked_md_path_not_flagged(tmp_path):
    body = "# Body\n\nSee `closing.md` §3 for the freeze checklist.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_draft_gate_line_citing_backticked_md_path_not_flagged():
    body = "# Body\n\nSee `closing.md` §3 for the freeze checklist.\n"
    assert _draft_errors(body) == []


@pytest.mark.parametrize("ext", ["md", "py", "sh", "toml", "yml"])
def test_integrity_repo_path_citation_exempt_for_each_known_extension(tmp_path, ext):
    body = f"# Body\n\nSee `module.{ext}` §2 for the details.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_integrity_repo_path_citation_with_subdirectory_still_exempt(tmp_path):
    body = "# Body\n\nAs documented in `docs/rfcs/0003-task-lifecycle.md` (see §5).\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []


def test_integrity_repo_path_citation_not_exempt_for_unknown_extension(tmp_path):
    # only a KNOWN repo extension exempts the line -- an arbitrary backticked token does not
    body = "# Body\n\nSee `notes.txt` §2 for the details.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§2" in l for l in anchor_lines)


def test_integrity_bare_repo_path_without_backticks_still_flagged(tmp_path):
    # the exemption is for a BACKTICKED path -- prose naming a path without backticks is unaffected
    body = "# Body\n\nSee closing.md §3 for the freeze checklist.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§3" in l for l in anchor_lines)


def test_integrity_repo_citation_exemption_scoped_to_its_own_line(tmp_path):
    # the exemption is a per-line rule -- it must not suppress a bare occurrence on another line
    body = ("# Body\n\nSee `closing.md` §3 for the checklist.\n"
            "But §9 here is bare and unrelated.\n")
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§9" in l for l in anchor_lines)
    assert not any("§3" in l for l in anchor_lines)


# =====================================================================================
# false-positive regression set -- the three named vault exhibits (issue #392 Context)
# =====================================================================================

def test_false_positive_regression_approval_record_authorship(tmp_path):
    """Models 2026-07-15-approval-record-authorship.md: prose citing a repo file's numbered
    section, the shape `closing.md` §N on one line, twice on that same line."""
    body = ("# Body\n\nThe authorship record for this decision lives in `closing.md` §3, and the "
            "close criteria for the same doc-freeze appear again at `closing.md` §4.\n")
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []
    assert failed is False
    assert _draft_errors(body) == []


def test_false_positive_regression_obsidian_section_anchors_seed(tmp_path):
    """Models 2026-07-14-obsidian-section-anchors.md: the seed that first reported the anchor
    problem, whose one rule-matching occurrence sits inside inline backticks."""
    body = ("# Body\n\nThis note first reported the dead-anchor problem: the broken shape reads "
            "like `See §4 for details.`, a reference Obsidian cannot resolve.\n")
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []
    assert failed is False
    assert _draft_errors(body) == []


def test_false_positive_regression_anchor_rule_over_fires_seed(tmp_path):
    """Models 2026-07-30-anchor-rule-over-fires.md: the reporting seed, now quoting the form
    inside inline backticks instead of committing it."""
    body = ("# Body\n\nThe over-firing report quoted the exact defect shape: `Section §4 "
            "discusses the rule`, which the checker wrongly flagged before this fix.\n")
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []
    assert failed is False
    assert _draft_errors(body) == []


# =====================================================================================
# true-positive fixtures -- proving the kept behavior is unchanged (issue #392)
# =====================================================================================

def test_true_positive_bare_occurrence_still_flagged(tmp_path):
    body = "# Body\n\nSee §4 for details.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§4" in l for l in anchor_lines)
    assert any("§4" in e for e in _draft_errors(body))


def test_true_positive_anchor_inside_wikilink_target_slot_still_flagged(tmp_path):
    body = "# Body\n\nSee [[factory-map#§4]] for details.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§4" in l for l in anchor_lines)
    assert any("§4" in e for e in _draft_errors(body))


def test_true_positive_aliased_wrong_repair_target_slot_still_flagged(tmp_path):
    """The likely mis-repair naming a non-existent heading: aliased so it looks sanctioned, but
    the anchor glyph is still sitting in the target/anchor slot, which the scan keeps visible."""
    body = "# Body\n\nSee [[factory-map#§99|§99]] for details.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§99" in l for l in anchor_lines)
    assert any("§99" in e for e in _draft_errors(body))


# =====================================================================================
# the wikilink alias-slot exemption (#338, narrowed by #339) is unchanged (issue #392)
# =====================================================================================

def test_alias_slot_exemption_still_clean_on_its_own(tmp_path):
    body = "# Body\n\nSee [[factory-map#2. Mechanism map|§2]] for details.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []
    assert _draft_errors(body) == []


def test_alias_slot_exemption_coexists_with_the_new_repo_citation_exemption(tmp_path):
    body = "# Body\n\nSee [[factory-map#2. Mechanism map|§2]] and also `closing.md` §3.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []
    assert _draft_errors(body) == []


def test_alias_slot_exemption_coexists_with_the_new_code_span_exemption(tmp_path):
    body = "# Body\n\nSee [[factory-map#2. Mechanism map|§2]], as in the quoted `§7` example.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert anchor_lines == []
    assert _draft_errors(body) == []


def test_alias_slot_exemption_does_not_hide_a_bare_anchor_beside_it(tmp_path):
    body = "# Body\n\nRepaired [[factory-map#2. Mechanism map|§2]], but §7 is still bare.\n"
    anchor_lines, failed = _anchor_lines(tmp_path, body)
    assert failed is True
    assert any("§7" in l for l in anchor_lines)
    assert not any("'§2'" in l for l in anchor_lines)
