"""Tests for issue #303 — split_frontmatter reports out-of-subset frontmatter instead of guessing.

Derived from the acceptance criteria, NOT the implementation's internals:

  * WHEN split_frontmatter receives frontmatter outside its declared subset (the six enumerated
    shapes), THE SYSTEM SHALL report that fact to the caller rather than return a guessed mapping.
  * WHERE a `key: value`-shaped line sits inside a block scalar / continuation, THE SYSTEM SHALL NOT
    create a top-level key from it nor overwrite a real key of the same name (the two reproductions).
  * THE SYSTEM SHALL keep parsing in-subset keys to their true values alongside the signal — the
    report augments a partial parse, never replaces it with an empty mapping.
  * THE SYSTEM SHALL surface the signal in both consumers, non-blocking, without changing the exit
    code for input that passes correctly today; existing hard findings keep their severity.
  * THE SYSTEM SHALL document "outside the declared subset" as an explicit enumerated list where the
    function is defined.

The reporting mechanism is builder's choice, constrained by the consumers' contract. Both shipped
consumers read the signal via ``getattr(meta, "out_of_subset", ())`` — that getattr is the realized
caller-visible contract, so the unit-level "reports" assertions read it the same way. The
mechanism-agnostic guarantees (no fabricated key; in-subset keys preserved; consumer exit codes) are
asserted directly against the returned mapping and the consumers' own behaviour.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.textutil import split_frontmatter
import tools.check_links as check_links
from tools.check_links import check_links as check_links_fn
from tools.check_supersession import check_sweep

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "task_303"


def _reported(meta):
    """The caller-visible signal, read exactly as the shipped consumers read it."""
    return list(getattr(meta, "out_of_subset", ()))


# =====================================================================================
# One unit test per out-of-subset shape (the six enumerated): each REPORTS, none fabricates a key,
# and the in-subset key sitting beside it still parses to its true value.
# =====================================================================================

# Every fixture opens with an in-subset `type: task` line (proving the partial parse survives) and
# carries a probe key that must never surface as a top-level key.
_OUT_OF_SUBSET_SHAPES = [
    (
        "nested-mapping",
        "---\n"
        "type: task\n"
        "config:\n"
        "  injected: bad\n"
        "---\nbody\n",
        # keys that must NOT appear in the returned mapping
        ("config", "injected"),
    ),
    (
        "block-scalar-literal",
        "---\n"
        "type: task\n"
        "notes: |\n"
        "  injected: bad\n"
        "  more prose\n"
        "---\nbody\n",
        ("notes", "injected"),
    ),
    (
        "block-scalar-folded",
        "---\n"
        "type: task\n"
        "notes: >\n"
        "  injected: bad\n"
        "  more prose\n"
        "---\nbody\n",
        ("notes", "injected"),
    ),
    (
        "wrapped-plain-scalar-continuation",
        "---\n"
        "type: task\n"
        "summary: starts here\n"
        "  injected: bad\n"
        "---\nbody\n",
        ("summary", "injected"),
    ),
    (
        "block-list-zero-indent",
        "---\n"
        "type: task\n"
        "- injected: bad\n"
        "- second item\n"
        "---\nbody\n",
        ("injected",),
    ),
    (
        "bracketed-inline-list-unclosed",
        "---\n"
        "type: task\n"
        "tags: [alpha, beta\n"
        "---\nbody\n",
        ("tags",),
    ),
    (
        "anchor-value",
        "---\n"
        "type: task\n"
        "ref: &anchor hello\n"
        "---\nbody\n",
        ("ref",),
    ),
]


@pytest.mark.parametrize("name,text,forbidden", _OUT_OF_SUBSET_SHAPES, ids=[s[0] for s in _OUT_OF_SUBSET_SHAPES])
def test_out_of_subset_shape_is_reported_not_guessed(name, text, forbidden):
    meta, _ = split_frontmatter(text)

    # (a) REPORTED to the caller rather than silently guessed.
    assert _reported(meta), f"{name}: expected an out-of-subset report, got none"

    # (b) never fabricates a top-level key from the out-of-subset shape (its own key or an inner
    #     `key: value`-shaped line).
    for key in forbidden:
        assert key not in meta, f"{name}: fabricated top-level key {key!r} from out-of-subset input"

    # (c) the partial parse survives — the in-subset key beside it keeps its true value; the mapping
    #     is never emptied out.
    assert meta.get("type") == "task", f"{name}: in-subset key lost alongside the signal"


# =====================================================================================
# A `key: value`-shaped line inside a block scalar must not OVERWRITE a real key of the same name.
# =====================================================================================

def test_inner_line_does_not_overwrite_a_real_key():
    text = (
        "---\n"
        "type: task\n"
        "notes: |\n"
        "  type: research\n"      # same name as a real key, but inside a block scalar
        "---\nbody\n"
    )
    meta, _ = split_frontmatter(text)
    assert meta["type"] == "task"       # the real key wins, not the block-scalar impostor
    assert _reported(meta)


# =====================================================================================
# Reproductions (repo-local fixture files, no Obsidian, no live vault).
# =====================================================================================

def test_reproduction_1_inner_source_spec_no_longer_promoted(tmp_path):
    # A resolving outer `source_spec` plus a `notes: |` block whose inner `source_spec:` names a
    # non-existent doc. Today the splitter promotes the inner line and check_links exits 1 on a
    # document Obsidian reads correctly.
    (tmp_path / "real spec.md").write_text("---\ntype: product-spec\n---\n", encoding="utf-8")
    text = (FIXTURES / "repro1_inner_source_spec.md").read_text(encoding="utf-8")

    meta, _ = split_frontmatter(text)
    # the one real source_spec survives; the block-scalar impostor never overwrites it
    assert meta["source_spec"] == "[[real spec]]"
    assert _reported(meta)

    # the consumer no longer errors on the ghost link
    assert check_links_fn(text, vault_root=tmp_path) == []


def test_reproduction_1_check_links_main_exits_zero(tmp_path):
    # end-to-end via the CLI entry point: exit code must be 0 (offline, --no-gh).
    (tmp_path / "real spec.md").write_text("---\ntype: product-spec\n---\n", encoding="utf-8")
    doc = FIXTURES / "repro1_inner_source_spec.md"
    rc = check_links.main([str(doc), "--vault-root", str(tmp_path), "--no-gh"])
    assert rc == 0


def test_reproduction_2_inner_status_no_longer_misreported():
    # `status: draft` plus a `notes: |` block containing `status: superseded`. The splitter must
    # return the real draft status, never the impostor.
    text = (FIXTURES / "repro2_inner_status.md").read_text(encoding="utf-8")
    meta, _ = split_frontmatter(text)
    assert meta["status"] == "draft"
    assert _reported(meta)


# =====================================================================================
# The two pinned behaviours stay green (asserted independently of test_textutil.py, which is
# unmodified): tab-indented list items tolerated, scalar values returned as strings.
# =====================================================================================

def test_pinned_tab_indented_list_items_still_tolerated():
    text = "---\ntags:\n\t- alpha\n\t- beta\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["tags"] == ["alpha", "beta"]
    assert not _reported(meta)          # a valid in-subset shape raises no signal


def test_pinned_scalar_values_stay_strings():
    text = "---\nstage: 4\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["stage"] == "4"
    assert isinstance(meta["stage"], str)


def test_in_subset_document_raises_no_signal():
    # exit-code-unchanged floor: a fully in-subset doc reports nothing.
    text = '---\ntype: task\nstatus: active\nsupersedes:\n  - "[[x]]"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert _reported(meta) == []


# =====================================================================================
# The enumerated list is documented where the function is defined.
# =====================================================================================

def test_out_of_subset_enumeration_documented_at_the_function():
    doc = (split_frontmatter.__doc__ or "").lower()
    for token in ("nested mapping", "block scalar", "continuation", "block list",
                  "inline list", "anchor"):
        assert token in doc, f"docstring is missing the enumerated shape {token!r}"


# =====================================================================================
# Consumer coverage — check_links (exit code unchanged for input that passes today).
# =====================================================================================

def test_check_links_unaffected_for_fully_resolving_doc(tmp_path):
    (tmp_path / "real spec.md").write_text("---\ntype: product-spec\n---\n", encoding="utf-8")
    text = '---\ntype: task\nsource_spec: "[[real spec]]"\n---\nbody\n'
    assert check_links_fn(text, vault_root=tmp_path) == []


# =====================================================================================
# Consumer coverage — check_supersession sweep surfaces the signal, exit code unchanged.
# =====================================================================================

def _write(root, relpath, content):
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_sweep_surfaces_out_of_subset_signal_without_changing_exit(tmp_path):
    # a conformant, out-of-subset doc: the sweep lands the signal in the observation class and does
    # NOT go red for it.
    _write(tmp_path, "proj/compA/iterations/doc1.md",
           "---\ntype: task\nstatus: active\nnotes: |\n  some prose\n---\n# Body\n")
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")

    assert failed is False
    signal = [l for l in lines if "outside the parseable subset" in l]
    assert signal, "sweep did not surface the out-of-subset signal"
    # it is an observation, never an error line
    assert all(not l.startswith("error:") for l in signal)


def test_sweep_out_of_subset_signal_is_not_a_hard_finding(tmp_path):
    # even alongside a genuinely clean space, the signal never flips the exit code.
    _write(tmp_path, "proj/compA/iterations/clean.md",
           "---\ntype: task\nstatus: active\n---\n# Body\n")
    _write(tmp_path, "proj/compA/iterations/oos.md",
           "---\ntype: task\nstatus: active\ndetails: |\n  a block scalar\n---\n# Body\n")
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is False
    assert any("outside the parseable subset" in l for l in lines)


def test_sweep_existing_hard_finding_keeps_its_severity(tmp_path):
    # the pinned example from the criteria: `supersedes` that doesn't parse as a list still fires as
    # a hard finding (exit 1), unaffected by the new signal.
    _write(tmp_path, "proj/compA/iterations/bad.md",
           "---\ntype: task\nstatus: active\nsupersedes: not-a-list\n---\n# Body\n")
    lines, failed = check_sweep(vault_root=tmp_path, scope="proj")
    assert failed is True
    assert any("does not parse as a list" in l for l in lines)
