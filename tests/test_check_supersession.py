import sys
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_supersession import check_draft, check_sweep, _governed_components


def _vault_file(root, relpath, content):
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _doc(type_="task", status="active", supersedes=None, superseded_by=None,
         source_spec=None, extra_lines=None, body="# Body\n"):
    """A minimal frontmatter'd markdown doc. `supersedes` may be a list (rendered
    block-style, Obsidian's own non-empty-list form, or `[]` when empty) or a raw
    scalar string (to exercise the non-list-value error path)."""
    lines = ["---", f"type: {type_}", f"status: {status}"]
    if supersedes is not None:
        if isinstance(supersedes, list) and supersedes:
            lines.append("supersedes:")
            lines.extend(f"  - {s}" for s in supersedes)
        elif isinstance(supersedes, list):
            lines.append("supersedes: []")
        else:
            lines.append(f"supersedes: {supersedes}")
    if superseded_by is not None:
        lines.append(f'superseded_by: "{superseded_by}"')
    if source_spec is not None:
        lines.append(f'source_spec: "{source_spec}"')
    if extra_lines:
        lines.extend(extra_lines)
    lines.append("---")
    lines.append(body)
    return "\n".join(lines)


# =====================================================================================
# draft mode — presence / parse / empty-justification (product-spec & feature-rfc only)
# =====================================================================================

def test_missing_supersedes_key_fails_for_product_spec(tmp_path):
    errors = check_draft(_doc(type_="product-spec"), vault_root=tmp_path)
    assert any("supersedes" in e.lower() for e in errors)


def test_missing_supersedes_key_fails_for_feature_rfc(tmp_path):
    errors = check_draft(_doc(type_="feature-rfc"), vault_root=tmp_path)
    assert any("supersedes" in e.lower() for e in errors)


def test_supersedes_non_list_value_fails(tmp_path):
    errors = check_draft(_doc(type_="product-spec", supersedes="nothing"), vault_root=tmp_path)
    assert any("list" in e.lower() for e in errors)


def test_empty_supersedes_without_justification_fails(tmp_path):
    errors = check_draft(_doc(type_="product-spec", supersedes=[]), vault_root=tmp_path)
    assert any("nothing" in e.lower() for e in errors)


def test_empty_supersedes_with_justification_passes(tmp_path):
    text = _doc(type_="product-spec", supersedes=[],
                body="# Body\n\n**Supersedes:** nothing — this is a net-new initiative.\n")
    assert check_draft(text, vault_root=tmp_path) == []


def test_empty_supersedes_justification_needs_a_word_after_nothing(tmp_path):
    # "nothing" alone with no justification text after it still fails
    text = _doc(type_="product-spec", supersedes=[], body="# Body\n\n**Supersedes:** nothing\n")
    errors = check_draft(text, vault_root=tmp_path)
    assert errors != []


def test_empty_supersedes_justification_line_must_be_the_right_shape(tmp_path):
    # some other line mentioning "nothing" doesn't count as the justification line
    text = _doc(type_="product-spec", supersedes=[],
                body="# Body\n\nThis supersedes nothing important.\n")
    errors = check_draft(text, vault_root=tmp_path)
    assert errors != []


# =====================================================================================
# draft mode — every other doc type: grammar-checked only if present, never required
# =====================================================================================

def test_other_doc_type_with_no_pair_keys_passes(tmp_path):
    assert check_draft(_doc(type_="task"), vault_root=tmp_path) == []


def test_other_doc_type_missing_supersedes_is_not_an_error(tmp_path):
    errors = check_draft(_doc(type_="research"), vault_root=tmp_path)
    assert errors == []


def test_other_doc_type_bad_supersedes_grammar_fails(tmp_path):
    errors = check_draft(_doc(type_="task", supersedes="not-a-list"), vault_root=tmp_path)
    assert errors != []
    assert any("list" in e.lower() for e in errors)


def test_other_doc_type_empty_superseded_by_fails(tmp_path):
    errors = check_draft(_doc(type_="task", superseded_by=""), vault_root=tmp_path)
    assert any("superseded_by" in e for e in errors)


def test_other_doc_type_valid_supersedes_list_is_not_resolved(tmp_path):
    # other doc types are grammar-checked only — an unresolved target is NOT an error here,
    # unlike product-spec/feature-rfc drafts where resolution is required
    text = _doc(type_="task", supersedes=["[[nonexistent-ghost]]"])
    assert check_draft(text, vault_root=tmp_path) == []


# =====================================================================================
# draft mode — target resolution (wikilink semantics of check_links._resolve_wikilink)
# =====================================================================================

def test_target_resolves_by_explicit_vault_relative_path(tmp_path):
    _vault_file(tmp_path, "04 projects/factory/rfcs/old-spec.md",
                _doc(type_="product-spec", status="active"))
    text = _doc(type_="feature-rfc", supersedes=["[[04 projects/factory/rfcs/old-spec]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_target_resolves_by_unique_basename(tmp_path):
    _vault_file(tmp_path, "a/b/old-note.md", _doc(type_="feature-rfc", status="active"))
    text = _doc(type_="feature-rfc", supersedes=["[[old-note]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_target_unresolved_fails(tmp_path):
    text = _doc(type_="feature-rfc", supersedes=["[[ghost-target]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("unresolved" in e.lower() for e in errors)


def test_target_ambiguous_basename_fails(tmp_path):
    # two same-named files in different iteration folders
    _vault_file(tmp_path, "iterations/1-first/dup.md", _doc(type_="feature-rfc", status="active"))
    _vault_file(tmp_path, "iterations/2-second/dup.md", _doc(type_="feature-rfc", status="active"))
    text = _doc(type_="feature-rfc", supersedes=["[[dup]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("ambiguous" in e.lower() for e in errors)


def test_target_dot_dir_match_does_not_count(tmp_path):
    _vault_file(tmp_path, ".trash/note.md", _doc(type_="feature-rfc", status="active"))
    text = _doc(type_="feature-rfc", supersedes=["[[note]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("unresolved" in e.lower() for e in errors)


def test_target_already_superseded_fails_naming_replacer(tmp_path):
    _vault_file(tmp_path, "old.md", _doc(type_="product-spec", status="superseded",
                                          superseded_by="[[replacer]]"))
    text = _doc(type_="feature-rfc", supersedes=["[[old]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("superseded" in e.lower() and "replacer" in e for e in errors)


def test_target_status_draft_fails(tmp_path):
    _vault_file(tmp_path, "draft-target.md", _doc(type_="product-spec", status="draft"))
    text = _doc(type_="feature-rfc", supersedes=["[[draft-target]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("active" in e.lower() for e in errors)


def test_target_status_rejected_fails(tmp_path):
    _vault_file(tmp_path, "rejected-target.md", _doc(type_="product-spec", status="rejected"))
    text = _doc(type_="feature-rfc", supersedes=["[[rejected-target]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("active" in e.lower() for e in errors)


def test_target_with_no_frontmatter_is_indeterminate(tmp_path):
    _vault_file(tmp_path, "weird.md", "no frontmatter here at all\n")
    text = _doc(type_="feature-rfc", supersedes=["[[weird]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("indeterminate" in e.lower() for e in errors)


def test_target_with_alien_type_is_indeterminate(tmp_path):
    _vault_file(tmp_path, "alien.md", "---\ntype: something-else\nstatus: active\n---\nbody\n")
    text = _doc(type_="feature-rfc", supersedes=["[[alien]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert errors != []


def test_target_with_alien_status_is_indeterminate(tmp_path):
    _vault_file(tmp_path, "alien.md", "---\ntype: product-spec\nstatus: something-else\n---\nbody\n")
    text = _doc(type_="feature-rfc", supersedes=["[[alien]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert errors != []


def test_multiple_targets_all_checked(tmp_path):
    _vault_file(tmp_path, "good.md", _doc(type_="feature-rfc", status="active"))
    text = _doc(type_="feature-rfc", supersedes=["[[good]]", "[[ghost]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("ghost" in e for e in errors)
    assert not any("good" in e for e in errors)


# =====================================================================================
# draft mode — down-flow disposition when a target is a product-spec
# =====================================================================================

def test_undispositioned_child_fails_listing_child(tmp_path):
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-task.md",
                _doc(type_="task", status="active", source_spec="[[spec/target-spec]]"))
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-spec]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("child-task" in e for e in errors)
    assert any("undispositioned" in e.lower() for e in errors)


def test_child_named_in_declaration_passes(tmp_path):
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-task.md",
                _doc(type_="task", status="active", source_spec="[[spec/target-spec]]"))
    text = _doc(type_="feature-rfc",
                supersedes=["[[spec/target-spec]]", "[[spec/child-task]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_child_cited_in_body_wikilink_passes(tmp_path):
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-task.md",
                _doc(type_="task", status="active", source_spec="[[spec/target-spec]]"))
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-spec]]"],
                body="# Body\n\nAlso disposes [[spec/child-task]] directly.\n")
    assert check_draft(text, vault_root=tmp_path) == []


def test_indeterminate_child_fails_listed_for_human(tmp_path):
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-weird.md",
                '---\nsource_spec: "[[spec/target-spec]]"\ntype: mystery\nstatus: active\n---\nbody\n')
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-spec]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("child-weird" in e for e in errors)
    assert any("indeterminate" in e.lower() for e in errors)


def test_indeterminate_child_still_fails_even_if_named_in_declaration(tmp_path):
    # an unclassifiable child must never pass silently, even if it happens to be listed
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-weird.md",
                '---\nsource_spec: "[[spec/target-spec]]"\ntype: mystery\nstatus: active\n---\nbody\n')
    text = _doc(type_="feature-rfc",
                supersedes=["[[spec/target-spec]]", "[[spec/child-weird]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("child-weird" in e and "indeterminate" in e.lower() for e in errors)


def test_draft_status_child_not_required(tmp_path):
    # only ACTIVE spine children are required to be dispositioned
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-draft.md",
                _doc(type_="task", status="draft", source_spec="[[spec/target-spec]]"))
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-spec]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_non_spine_type_child_not_required(tmp_path):
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-note.md",
                _doc(type_="research", status="active", source_spec="[[spec/target-spec]]"))
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-spec]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_child_of_different_spec_not_required(tmp_path):
    _vault_file(tmp_path, "spec/target-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/other-spec.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "spec/child-of-other.md",
                _doc(type_="task", status="active", source_spec="[[spec/other-spec]]"))
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-spec]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_target_not_product_spec_has_no_downflow_requirement(tmp_path):
    _vault_file(tmp_path, "spec/target-rfc.md", _doc(type_="feature-rfc", status="active"))
    _vault_file(tmp_path, "spec/child-task.md",
                _doc(type_="task", status="active", source_spec="[[spec/target-rfc]]"))
    # note: child's source_spec points at a feature-rfc, so it's irrelevant to disposition anyway;
    # the point of this test is that a feature-rfc target triggers no down-flow scan at all
    text = _doc(type_="feature-rfc", supersedes=["[[spec/target-rfc]]"])
    assert check_draft(text, vault_root=tmp_path) == []


# =====================================================================================
# sweep mode — governed space enumeration (the pinned rule)
# =====================================================================================

def test_sweep_non_component_sibling_now_scanned_under_parent_tier(tmp_path):
    # a sibling with no iterations/ child of its own no longer sits outside the governed space
    # entirely -- ruling (b) folds it into the parent tier's own scan (unless it's archive/)
    _vault_file(tmp_path, "proj/compA/iterations/doc1.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/compB/doc-outside.md", _doc(status="active"))  # no iterations/ child
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "2 docs" in lines[0]
    assert failed is False


def test_sweep_dot_directories_excluded(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc1.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/compA/.hidden/doc2.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "1 docs" in lines[0]


def test_sweep_underscore_sibling_directories_included(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc1.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/compA/_tasks_pending/doc2.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "2 docs" in lines[0]


def test_sweep_sibling_subtree_walked_recursively(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc1.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/compA/_extra/nested/deep/doc2.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "2 docs" in lines[0]


# =====================================================================================
# sweep mode — a component-rooted scope (the scope itself has an `iterations/` child)
# =====================================================================================

def test_sweep_component_rooted_scope_sweeps_as_one_component(tmp_path):
    # scope "proj/factory" has iterations/ directly under it — no parent-of-components shape
    _vault_file(tmp_path, "proj/factory/iterations/spec1.md",
                _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "proj/factory/iterations/legacy1.md", "no frontmatter here\n")
    _vault_file(tmp_path, "proj/factory/_extra/doc.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/factory/root-doc.md", _doc(type_="task", status="active"))

    lines, failed = check_sweep(vault_root=tmp_path, scope="proj/factory")
    census = lines[0]
    assert failed is False
    assert "4 docs" in census
    assert "1 spine-active" in census
    assert "factory 1" in census
    assert "1 legacy" in census


def test_sweep_component_rooted_scope_named_by_scope_basename(tmp_path):
    _vault_file(tmp_path, "proj/widget/iterations/task1.md", _doc(type_="task", status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj/widget")
    assert "widget 1" in lines[0]


def test_sweep_component_rooted_scope_pair_integrity_still_runs(tmp_path):
    _vault_file(tmp_path, "proj/factory/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[ghost]]"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj/factory")
    assert failed is True


def test_sweep_component_rooted_scope_census_output_pinned_byte_identical(tmp_path):
    # ruling (b) only changes parent-shaped scopes -- a component-rooted scope's output (including
    # its root docs and siblings) must stay byte-identical to today
    _vault_file(tmp_path, "proj/factory/iterations/spec1.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "proj/factory/iterations/legacy1.md", "no frontmatter here\n")
    _vault_file(tmp_path, "proj/factory/_extra/doc.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/factory/root-doc.md", _doc(type_="task", status="active"))

    lines, failed = check_sweep(vault_root=tmp_path, scope="proj/factory")
    assert lines[0] == "census [proj/factory]: 4 docs / 1 spine-active (factory 1) / 1 legacy"
    assert failed is False
    assert not any(l.startswith("skip:") for l in lines)


# =====================================================================================
# sweep mode — the parent-shaped scope regression pin (default scope shape unchanged)
# =====================================================================================

def test_sweep_parent_shaped_scope_census_output_pinned(tmp_path):
    # identical fixture to test_census_headline_arithmetic — pins the exact output line so a
    # component-rooted-scope change can never alter the parent-shaped scope's byte-for-byte output.
    # compC has no iterations/ child of its own, so ruling (b) folds its doc into the parent tier's
    # own scan (named "proj", not "compC") — it counts toward the total but not spine-active, since
    # it never sat inside an iterations/ subtree.
    _vault_file(tmp_path, "proj/compA/iterations/spec1.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "proj/compA/iterations/task1.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/compA/iterations/note1.md", _doc(type_="research", status="active"))
    _vault_file(tmp_path, "proj/compA/iterations/legacy1.md", "no frontmatter\n")
    _vault_file(tmp_path, "proj/compA/_extra/spec2.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "proj/compB/iterations/task2.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/compC/plain/doc.md", _doc(type_="task", status="active"))

    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert lines[0] == "census [proj]: 7 docs / 3 spine-active (compA 2, compB 1) / 1 legacy"
    assert failed is False


# =====================================================================================
# sweep mode — pair integrity, forward (supersedes → target)
# =====================================================================================

def test_sweep_forward_pair_properly_marked_passes(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[proj/compA/iterations/old-doc]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md",
                _doc(status="superseded", superseded_by="[[proj/compA/iterations/new-doc]]"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False


def test_sweep_forward_target_not_yet_superseded_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[proj/compA/iterations/old-doc]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


def test_sweep_forward_missing_back_pointer_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[proj/compA/iterations/old-doc]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md", _doc(status="superseded"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True
    assert any("back-pointer" in l.lower() or "back pointer" in l.lower() for l in lines)


def test_sweep_forward_wrong_back_pointer_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[proj/compA/iterations/old-doc]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md",
                _doc(status="superseded", superseded_by="[[proj/compA/iterations/someone-else]]"))
    _vault_file(tmp_path, "proj/compA/iterations/someone-else.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


def test_sweep_forward_unresolved_target_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[ghost-target]]"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


def test_sweep_unjustified_empty_declaration_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active", supersedes=[]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


def test_sweep_justified_empty_declaration_passes(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md",
                _doc(status="active", supersedes=[],
                     body="# Body\n\n**Supersedes:** nothing — greenfield.\n"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False


def test_sweep_supersedes_non_list_value_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active", supersedes="nothing"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


# =====================================================================================
# sweep mode — pair integrity, backward (superseded doc → superseded_by replacer)
# =====================================================================================

def test_sweep_superseded_with_no_superseded_by_is_advisory_not_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md", _doc(status="superseded"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any("superseded_by" in l.lower() for l in lines)


def test_sweep_replacer_with_no_supersedes_key_is_advisory_not_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md",
                _doc(status="superseded", superseded_by="[[proj/compA/iterations/new-doc]]"))
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md", _doc(status="active"))  # no supersedes key
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any("pre-grammar" in l.lower() for l in lines)


def test_sweep_replacer_declares_supersedes_but_not_back_to_this_doc_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md",
                _doc(status="superseded", superseded_by="[[proj/compA/iterations/new-doc]]"))
    _vault_file(tmp_path, "proj/compA/iterations/unrelated.md", _doc(status="superseded"))
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[proj/compA/iterations/unrelated]]"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


def test_sweep_downflow_gap_under_declaring_replacer_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-spec.md",
                _doc(type_="product-spec", status="active",
                     supersedes=["[[proj/compA/iterations/old-spec]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/old-spec.md",
                _doc(type_="product-spec", status="superseded",
                     superseded_by="[[proj/compA/iterations/new-spec]]"))
    _vault_file(tmp_path, "proj/compA/iterations/orphan-child.md",
                _doc(type_="task", status="active", source_spec="[[proj/compA/iterations/old-spec]]"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True
    assert any("orphan-child" in l for l in lines)


def test_sweep_downflow_complete_when_child_cited_in_body_passes(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-spec.md",
                _doc(type_="product-spec", status="active",
                     supersedes=["[[proj/compA/iterations/old-spec]]"],
                     body="# Body\n\nAlso disposes [[proj/compA/iterations/child]].\n"))
    _vault_file(tmp_path, "proj/compA/iterations/old-spec.md",
                _doc(type_="product-spec", status="superseded",
                     superseded_by="[[proj/compA/iterations/new-spec]]"))
    _vault_file(tmp_path, "proj/compA/iterations/child.md",
                _doc(type_="task", status="active", source_spec="[[proj/compA/iterations/old-spec]]"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False


def test_sweep_downflow_indeterminate_child_is_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-spec.md",
                _doc(type_="product-spec", status="active",
                     supersedes=["[[proj/compA/iterations/old-spec]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/old-spec.md",
                _doc(type_="product-spec", status="superseded",
                     superseded_by="[[proj/compA/iterations/new-spec]]"))
    _vault_file(tmp_path, "proj/compA/iterations/mystery-child.md",
                '---\nsource_spec: "[[proj/compA/iterations/old-spec]]"\ntype: mystery\nstatus: active\n---\nbody\n')
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


def test_sweep_downflow_gap_under_pregrammar_replacer_is_advisory_not_hard(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/old-spec.md",
                _doc(type_="product-spec", status="superseded",
                     superseded_by="[[proj/compA/iterations/new-spec]]"))
    _vault_file(tmp_path, "proj/compA/iterations/new-spec.md",
                _doc(type_="product-spec", status="active"))  # no supersedes key at all
    _vault_file(tmp_path, "proj/compA/iterations/orphan-child.md",
                _doc(type_="task", status="active", source_spec="[[proj/compA/iterations/old-spec]]"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any("orphan-child" in l for l in lines)


# =====================================================================================
# sweep mode — advisory signals that must never move the exit code
# =====================================================================================

def test_sweep_pair_adjacent_signal_is_advisory(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md",
                _doc(status="superseded", superseded_by="[[proj/compA/iterations/new-doc]]"))
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[proj/compA/iterations/old-doc]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/other-doc.md",
                _doc(status="active", source_spec="[[proj/compA/iterations/old-doc]]"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any("other-doc" in l and "old-doc" in l for l in lines)


def test_sweep_spine_doc_in_governed_home_is_advisory(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc1.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/compA/_docs/misplaced-spec.md",
                _doc(type_="product-spec", status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any("misplaced-spec" in l for l in lines)


# =====================================================================================
# sweep mode — legacy aggregation (never itemized) and alien-key observations
# =====================================================================================

def test_sweep_legacy_docs_aggregated_per_folder_with_counts(tmp_path):
    for i in range(5):
        _vault_file(tmp_path, f"proj/compA/iterations/legacy-{i}.md", "no frontmatter here\n")
    _vault_file(tmp_path, "proj/compA/iterations/normal.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    legacy_lines = [l for l in lines if "legacy" in l.lower() and "iterations" in l.lower()]
    # aggregated as ONE line for the folder, never one line per doc
    assert len(legacy_lines) == 1
    assert "5" in legacy_lines[0]


def test_sweep_legacy_alien_type_counts_as_legacy(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/alien.md",
                "---\ntype: something-else\nstatus: active\n---\nbody\n")
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "1 legacy" in lines[0]


def test_sweep_legacy_alien_status_counts_as_legacy(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/alien.md",
                "---\ntype: task\nstatus: something-else\n---\nbody\n")
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "1 legacy" in lines[0]


def test_sweep_alien_frontmatter_key_is_one_observation_line_not_itemized(tmp_path):
    for i in range(3):
        _vault_file(tmp_path, f"proj/compA/iterations/doc{i}.md",
                    _doc(status="active", extra_lines=["weird_key: foo"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    obs_lines = [l for l in lines if "weird_key" in l]
    assert len(obs_lines) == 1
    assert "3" in obs_lines[0]


# =====================================================================================
# sweep mode — exit-code matrix
# =====================================================================================

def test_sweep_exit_zero_with_only_advisory_and_legacy_findings(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/old-doc.md", _doc(status="superseded"))
    _vault_file(tmp_path, "proj/compA/iterations/legacy.md", "no frontmatter here\n")
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False


def test_sweep_exit_one_with_a_hard_finding_present(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[ghost]]"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True


# =====================================================================================
# sweep mode — census headline arithmetic
# =====================================================================================

def test_census_headline_arithmetic(tmp_path):
    # compA/iterations: 2 active spine docs + 1 non-spine active doc + 1 legacy doc
    _vault_file(tmp_path, "proj/compA/iterations/spec1.md", _doc(type_="product-spec", status="active"))
    _vault_file(tmp_path, "proj/compA/iterations/task1.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/compA/iterations/note1.md", _doc(type_="research", status="active"))
    _vault_file(tmp_path, "proj/compA/iterations/legacy1.md", "no frontmatter\n")
    # compA/_extra: a spine doc OUTSIDE iterations — counted in total, not in spine-active
    _vault_file(tmp_path, "proj/compA/_extra/spec2.md", _doc(type_="product-spec", status="active"))
    # compB/iterations: 1 active spine doc
    _vault_file(tmp_path, "proj/compB/iterations/task2.md", _doc(type_="task", status="active"))
    # compC has no iterations/ child of its own — scanned under the parent tier (named "proj")
    # instead: counted in the total but not spine-active, since it never sits in an iterations/ subtree
    _vault_file(tmp_path, "proj/compC/plain/doc.md", _doc(type_="task", status="active"))

    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    census = lines[0]
    assert "7 docs" in census
    assert "3 spine-active" in census
    assert "compA 2" in census
    assert "compB 1" in census
    assert "1 legacy" in census


def test_census_headline_always_printed_even_when_clean(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert lines[0].startswith("census ")
    assert failed is False


def test_census_headline_printed_on_empty_governed_space(tmp_path):
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert lines[0].startswith("census ")
    assert "0 docs" in lines[0]
    assert failed is False


# =====================================================================================
# sweep mode — the verdict line always names the scope it scanned (issue #141)
# =====================================================================================

def test_sweep_verdict_names_the_scanned_scope_parent_shaped(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "[proj]" in lines[0]


def test_sweep_verdict_names_the_scanned_scope_component_rooted(tmp_path):
    _vault_file(tmp_path, "proj/widget/iterations/task1.md", _doc(type_="task", status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj/widget")
    assert "[proj/widget]" in lines[0]


def test_sweep_verdict_names_scope_even_on_a_hard_finding(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[ghost]]"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True
    assert "[proj]" in lines[0]


def test_sweep_verdict_names_scope_on_empty_governed_space(tmp_path):
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert "[proj]" in lines[0]


# =====================================================================================
# sweep mode — a parent-shaped scope reports what it structurally skips (issue #141)
# =====================================================================================

def test_sweep_parent_shaped_reports_excluded_non_component_subtree(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/archive/old-doc.md", _doc(status="active"))  # no iterations/ child
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    skip_lines = [l for l in lines if l.startswith("skip:")]
    assert any("archive" in l for l in skip_lines)
    # a named skip-report line, not a widened scan -- archive/ contents are never counted
    assert "1 docs" in lines[0]
    assert failed is False


def test_sweep_parent_shaped_scans_loose_root_docs_into_parent_component(tmp_path):
    # ruling (b): the parent root's own loose docs no longer just get named in a skip line --
    # they scan into the census as the parent tier's own component, named by the scope's basename
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/strategy.md", _doc(type_="task", status="active"))  # org-tier loose root doc
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    skip_lines = [l for l in lines if l.startswith("skip:")]
    assert not any("strategy.md" in l for l in skip_lines)
    assert "2 docs" in lines[0]
    assert failed is False


def test_sweep_parent_shaped_only_archive_skip_line_remains(tmp_path):
    # archive/ is the only thing still reported as skipped -- every other non-component
    # sibling and every loose root doc now scans in as the parent tier's own component, so the
    # skip report narrows to exactly that one line
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/archive/old.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/brand.md", _doc(type_="task", status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    skip_lines = [l for l in lines if l.startswith("skip:")]
    assert len(skip_lines) == 1
    assert "archive" in skip_lines[0]
    assert "brand" not in skip_lines[0]
    # brand.md now scanned into the census; archive/old.md stays excluded and uncounted
    assert "2 docs" in lines[0]
    assert failed is False


def test_sweep_parent_shaped_scans_children_and_root_docs_as_named_parent_component(tmp_path):
    # the org tier itself: brand/, strategy/, ideas/ children plus a root loose doc all scan in as
    # one parent-tier component named by the scope's basename; archive/ is the only exclusion, and
    # the skip report narrows to exactly that one line
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/root-note.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/brand/brand-note.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/strategy/strategy-note.md", _doc(type_="task", status="active"))
    _vault_file(tmp_path, "proj/ideas/idea1.md",
                _doc(type_="note", status="open",
                     extra_lines=["summary: x", "value: high", "effort: low"]))
    _vault_file(tmp_path, "proj/archive/old-note.md", _doc(status="active"))

    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    census = lines[0]
    assert failed is False
    assert "5 docs" in census  # compA doc + root-note + brand-note + strategy-note + idea1
    assert "0 legacy" in census
    assert "[proj]" in census

    skip_lines = [l for l in lines if l.startswith("skip:")]
    assert len(skip_lines) == 1
    assert "archive" in skip_lines[0]


def test_sweep_parent_shaped_no_skip_lines_when_nothing_to_skip(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert not any(l.startswith("skip:") for l in lines)


def test_sweep_component_rooted_scope_has_no_skip_lines(tmp_path):
    # a component-rooted scope already picks up its own root docs directly -- nothing
    # structurally excluded the way a parent-shaped scope excludes archive/-style subtrees
    _vault_file(tmp_path, "proj/factory/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "proj/factory/root-doc.md", _doc(type_="task", status="active"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj/factory")
    assert not any(l.startswith("skip:") for l in lines)


def test_governed_components_docstring_rewritten_to_new_contract(tmp_path):
    # the aged assumption ("a parent-shaped scope's children carry no loose root docs today")
    # must be gone -- the docstring now records that the parent tier scans as its own component
    doc = _governed_components.__doc__ or ""
    assert "carry no loose root docs today" not in doc
    assert "archive" in doc.lower()


# =====================================================================================
# CLI
# =====================================================================================

def test_cli_draft_mode_fails_loud_on_missing_supersedes(tmp_path):
    artifact = tmp_path / "draft.md"
    artifact.write_text(_doc(type_="product-spec"), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         str(artifact), "--vault-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "supersedes" in r.stdout.lower()
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_draft_mode_passes_clean_draft(tmp_path):
    artifact = tmp_path / "draft.md"
    artifact.write_text(
        _doc(type_="feature-rfc", supersedes=[],
             body="# Body\n\n**Supersedes:** nothing — greenfield.\n"),
        encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         str(artifact), "--vault-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_sweep_mode_passes_clean_tree(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc.md", _doc(status="active"))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         "--sweep", "--vault-root", str(tmp_path), "--scope", "proj"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "census" in r.stdout.lower()
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_sweep_mode_fails_loud_on_hard_finding(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/new-doc.md",
                _doc(status="active", supersedes=["[[ghost]]"]))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         "--sweep", "--vault-root", str(tmp_path), "--scope", "proj"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_requires_file_unless_sweep(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         "--vault-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "Traceback" not in (r.stdout + r.stderr)


# =====================================================================================
# CLI — a scope-less --sweep fails loud, naming what's visible (issue #141)
# =====================================================================================

def test_cli_sweep_without_scope_fails_loud_naming_component_roots(tmp_path):
    _vault_file(tmp_path, "04 projects/factory/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "04 projects/yellow-robots/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "04 projects/gilda/iterations/doc.md", _doc(status="active"))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         "--sweep", "--vault-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "04 projects/factory" in r.stdout
    assert "04 projects/yellow-robots" in r.stdout
    assert "04 projects/gilda" in r.stdout
    # it never silently sweeps some pinned default -- no census/verdict is ever produced
    assert "census" not in r.stdout.lower()
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_sweep_without_scope_and_no_component_roots_still_fails_loud(tmp_path):
    # an empty/unrecognized vault must not be silently treated as a clean sweep
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         "--sweep", "--vault-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert r.stdout.strip() != ""
    assert "census" not in r.stdout.lower()
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_sweep_with_explicit_scope_still_works_after_scope_less_form_retired(tmp_path):
    # explicit --scope sweeps pass/fail exactly as before, scope named on the verdict line
    _vault_file(tmp_path, "04 projects/factory/iterations/doc.md", _doc(status="active"))
    _vault_file(tmp_path, "04 projects/yellow-robots/iterations/doc.md", _doc(status="active"))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         "--sweep", "--vault-root", str(tmp_path), "--scope", "04 projects/factory"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "1 docs" in r.stdout
    assert "[04 projects/factory]" in r.stdout
    assert "Traceback" not in (r.stdout + r.stderr)


def test_cli_draft_mode_needs_no_scope_and_is_unaffected(tmp_path):
    # draft mode's defaults are untouched by the sweep-mode scope requirement
    artifact = tmp_path / "draft.md"
    artifact.write_text(_doc(type_="task"), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_supersession.py"),
         str(artifact), "--vault-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "Traceback" not in (r.stdout + r.stderr)


# =====================================================================================
# ideas-folder vocabulary — location-aware status/closed-keys (issue #197)
# =====================================================================================
#
# An "ideas-folder note" is any doc whose vault-relative path has an `ideas/` directory
# segment. Inside `ideas/`: `open`/`rejected`/`superseded` are the known statuses (`draft`
# is deliberately NOT tolerated there — ruling (c)), and `summary`/`value`/`effort` join
# the closed keys. Outside `ideas/`, the spine vocabulary and closed-key set are unchanged.

def test_sweep_ideas_note_open_with_scoring_keys_is_conformant_no_observations(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/ideas/idea-good.md",
                _doc(type_="note", status="open",
                     extra_lines=["summary: a neat idea", "value: high", "effort: low"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert "0 legacy" in lines[0]
    assert not any(l.startswith("observation:") for l in lines)


def test_sweep_value_key_on_product_spec_outside_ideas_still_an_observation(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/spec-with-value.md",
                _doc(type_="product-spec", status="active", extra_lines=["value: high"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any(l.startswith("observation:") and "'value'" in l for l in lines)


def test_sweep_draft_status_inside_ideas_folder_is_alien_status_legacy(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/ideas/idea-draft.md",
                _doc(type_="note", status="draft"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert "1 legacy" in lines[0]


def test_sweep_open_status_outside_ideas_folder_is_alien_status_legacy(tmp_path):
    _vault_file(tmp_path, "proj/compA/iterations/doc-open.md",
                _doc(type_="note", status="open"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert "1 legacy" in lines[0]


def test_draft_gate_accepts_pending_open_ideas_seed(tmp_path):
    # a draft spine document (product-spec/feature-rfc) declaring supersedes against a
    # pending ideas-folder note (status "open") must be accepted — its legitimate
    # pre-accept state, in place of the spine's "active".
    _vault_file(tmp_path, "ideas/idea-pending.md",
                _doc(type_="note", status="open",
                     extra_lines=["summary: a neat idea", "value: high", "effort: low"]))
    text = _doc(type_="product-spec", supersedes=["[[ideas/idea-pending]]"])
    assert check_draft(text, vault_root=tmp_path) == []


def test_draft_gate_rejects_a_rejected_ideas_seed_exactly_as_today(tmp_path):
    _vault_file(tmp_path, "ideas/idea-rejected.md", _doc(type_="note", status="rejected"))
    text = _doc(type_="product-spec", supersedes=["[[ideas/idea-rejected]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("rejected" in e.lower() and "open" in e.lower() for e in errors)


def test_draft_gate_rejects_an_already_superseded_ideas_seed_naming_replacer(tmp_path):
    _vault_file(tmp_path, "ideas/idea-done.md",
                _doc(type_="note", status="superseded", superseded_by="[[ideas/promoted-spec]]"))
    text = _doc(type_="product-spec", supersedes=["[[ideas/idea-done]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("superseded" in e.lower() and "promoted-spec" in e for e in errors)


def test_draft_gate_target_status_draft_inside_ideas_is_indeterminate(tmp_path):
    # `draft` is not tolerated in ideas/ — a draft-status target there is alien status,
    # not a legitimate pending state, so it's indeterminate exactly like any other
    # unclassifiable target (never silently accepted).
    _vault_file(tmp_path, "ideas/idea-draft.md", _doc(type_="note", status="draft"))
    text = _doc(type_="product-spec", supersedes=["[[ideas/idea-draft]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("indeterminate" in e.lower() for e in errors)


def test_draft_gate_target_status_open_outside_ideas_is_indeterminate(tmp_path):
    _vault_file(tmp_path, "not-ideas/doc-open.md", _doc(type_="note", status="open"))
    text = _doc(type_="product-spec", supersedes=["[[not-ideas/doc-open]]"])
    errors = check_draft(text, vault_root=tmp_path)
    assert any("indeterminate" in e.lower() for e in errors)


def test_sweep_still_draft_declaring_doc_targets_pending_ideas_seed_no_hard_finding(tmp_path):
    # a still-draft spine doc already living in the vault (not yet accepted) that declares
    # supersedes against a pending ("open") ideas note must not be treated as indeterminate —
    # location awareness must reach the classifier _lookup uses in sweep mode too, not only
    # the draft-mode entry point.
    _vault_file(tmp_path, "proj/compA/iterations/draft-spec.md",
                _doc(type_="product-spec", status="draft",
                     supersedes=["[[proj/compA/iterations/ideas/idea-pending]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/ideas/idea-pending.md",
                _doc(type_="note", status="open",
                     extra_lines=["summary: x", "value: high", "effort: low"]))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert not any("indeterminate" in l.lower() for l in lines)


def test_sweep_completed_promotion_pair_verifies_both_directions(tmp_path):
    # once the pair completes (declarer accepted, ideas target superseded with a correct
    # back-pointer), sweep-mode pair verification runs exactly as it does for spine targets.
    _vault_file(tmp_path, "proj/compA/iterations/promoted-spec.md",
                _doc(type_="feature-rfc", status="active",
                     supersedes=["[[proj/compA/iterations/ideas/idea-promoted]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/ideas/idea-promoted.md",
                _doc(type_="note", status="superseded",
                     superseded_by="[[proj/compA/iterations/promoted-spec]]"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False


def test_sweep_completed_promotion_pair_missing_back_pointer_is_still_hard(tmp_path):
    # the ideas target is not exempted from ordinary pair-integrity enforcement once
    # superseded — a missing back-pointer is a hard finding exactly as for any other pair.
    _vault_file(tmp_path, "proj/compA/iterations/promoted-spec2.md",
                _doc(type_="feature-rfc", status="active",
                     supersedes=["[[proj/compA/iterations/ideas/idea-promoted2]]"]))
    _vault_file(tmp_path, "proj/compA/iterations/ideas/idea-promoted2.md",
                _doc(type_="note", status="superseded"))
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True
