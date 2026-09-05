"""Acceptance tests for issue #456 — it-33 slice 1: the canon names the runtime surfaces.

`AGENTS.md`'s "Builds from git refs, not a mutable working tree" invariant gains a runtime
carve-out: an eight-row table naming every factory runtime surface, the act that refreshes it,
whether it may lawfully execute from a mutable working tree, and whether it is a declared runtime
surface (`tools/provenance.py`'s `SURFACES`) or a named configuration surface — plus the
long-lived-process semantics (a resident process holds its import closure, so a pull is not a
deploy for it). `pipeline.md`'s worktree row and `closing.md`'s "merge != ship" bullet each cite
the carve-out in one sentence.

Derived from the issue #456 acceptance criteria (the spec), not from the implementation. The
declared population is read from `provenance.SURFACES` (slice 2, #457) rather than restated here.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import provenance  # noqa: E402

AGENTS = ROOT / "AGENTS.md"
PIPELINE = ROOT / "skills" / "factory" / "references" / "pipeline.md"
CLOSING = ROOT / "skills" / "factory" / "references" / "closing.md"

ROW_RE = re.compile(
    r"^\s*\|\s*\d+\s*\|(?P<surface>[^|]*)\|(?P<refreshed>[^|]*)\|(?P<mutable>[^|]*)\|(?P<status>[^|]*)\|\s*$",
    re.MULTILINE,
)


def _normalized(text):
    """Fold whitespace (incl. markdown line wraps) to a single space so a phrase wrapped across
    a line break still matches a plain substring check."""
    return re.sub(r"\s+", " ", text.lower())


def _agents_text():
    return AGENTS.read_text(encoding="utf-8")


def _git_refs_bullet_section():
    """The full 'Builds from git refs' invariant bullet, from its own dash to the next
    top-level invariant bullet ('One task = one PR')."""
    text = _agents_text()
    start = text.find("- **Builds from git refs")
    assert start != -1, "AGENTS.md is missing the 'Builds from git refs' invariant bullet"
    end = text.find("\n- **One task = one PR", start)
    assert end != -1, "could not find the end of the git-refs invariant bullet"
    return text[start:end]


def _table_rows():
    section = _git_refs_bullet_section()
    rows = ROW_RE.findall(section)
    assert rows, "no table rows found under the git-refs invariant bullet"
    return [
        {"surface": s.strip(), "refreshed": r.strip(), "mutable": m.strip(), "status": st.strip()}
        for (s, r, m, st) in rows
    ]


# ── the eight-row table ──────────────────────────────────────────────────────────────────────────

def test_git_refs_invariant_gains_a_runtime_carveout_mention():
    section = _git_refs_bullet_section()
    norm = _normalized(section)
    assert "runtime" in norm and ("carve-out" in norm or "carveout" in norm), (
        "the git-refs invariant bullet does not mention a runtime carve-out"
    )


def test_table_has_exactly_eight_rows():
    rows = _table_rows()
    assert len(rows) == 8, f"expected 8 runtime-surface rows, found {len(rows)}"


def test_every_row_states_all_four_required_facts():
    for i, row in enumerate(_table_rows(), start=1):
        assert row["surface"], f"row {i} names no surface"
        assert row["refreshed"], f"row {i} names no refreshing act"
        assert row["mutable"], f"row {i} states no mutable-working-tree lawfulness"
        assert row["status"].lower() in ("declared", "named"), (
            f"row {i} status must be 'Declared' or 'Named', got {row['status']!r}"
        )


def test_table_splits_four_declared_four_named():
    rows = _table_rows()
    declared = [r for r in rows if r["status"].lower() == "declared"]
    named = [r for r in rows if r["status"].lower() == "named"]
    assert len(declared) == 4, f"expected 4 declared rows, found {len(declared)}"
    assert len(named) == 4, f"expected 4 named rows, found {len(named)}"


def test_declared_rows_cite_exactly_provenance_surfaces():
    """The declared four are exactly `provenance.SURFACES` — read the constant, don't restate it."""
    rows = _table_rows()
    declared_text = " ".join(r["surface"] for r in rows if r["status"].lower() == "declared")
    named_text = " ".join(r["surface"] for r in rows if r["status"].lower() == "named")

    cited_in_declared = {s for s in provenance.SURFACES if f"`{s}`" in declared_text}
    assert cited_in_declared == set(provenance.SURFACES), (
        f"declared table rows cite {cited_in_declared}, expected all of {set(provenance.SURFACES)}"
    )

    leaked_into_named = {s for s in provenance.SURFACES if f"`{s}`" in named_text}
    assert not leaked_into_named, (
        f"declared surfaces {leaked_into_named} are cited in a Named row, not a Declared one"
    )


def test_table_row_count_matches_neither_more_nor_fewer_than_declared_population():
    """Exactly `len(provenance.SURFACES)` rows are marked Declared — never more, never fewer,
    even if the table grows unrelated rows later."""
    rows = _table_rows()
    declared = [r for r in rows if r["status"].lower() == "declared"]
    assert len(declared) == len(provenance.SURFACES)


# ── long-lived-process semantics ────────────────────────────────────────────────────────────────

def test_canon_states_the_long_lived_process_semantics():
    section = _git_refs_bullet_section()
    norm = _normalized(section)
    assert "resident process" in norm, (
        "the canon does not name a resident process in its long-lived-process semantics"
    )
    assert "import closure" in norm, (
        "the canon does not state that a resident process holds its import closure"
    )
    assert "pull" in norm and "deploy" in norm, (
        "the canon does not relate a pull to a deploy for the resident-process semantics"
    )
    assert "a pull is not a deploy for it" in norm or "not a deploy for it" in norm, (
        "the canon does not state that a pull is not a deploy for the resident process"
    )


def test_long_lived_process_semantics_names_the_declared_dispatch_surface():
    """The long-lived-process semantics apply to `dispatch`, one of the four declared surfaces."""
    section = _git_refs_bullet_section()
    assert "dispatch" in provenance.SURFACES
    assert "dispatch" in section.lower()


# ── pipeline.md and closing.md cite the carve-out, restate nothing ─────────────────────────────

def _pipeline_worktree_row():
    text = PIPELINE.read_text(encoding="utf-8")
    m = re.search(r"^\|\s*\*\*Worktree\*\*\s*\|(?P<cell>.*)\|[^|]*\|\s*$", text, re.MULTILINE)
    assert m, "pipeline.md is missing its Worktree row"
    return m.group("cell")


def test_pipeline_worktree_row_cites_the_carveout():
    cell = _pipeline_worktree_row()
    norm = _normalized(cell)
    assert "eight" in norm and "runtime surface" in norm, (
        "pipeline.md's Worktree row does not cite the eight runtime surfaces"
    )
    assert "agents.md" in norm, (
        "pipeline.md's Worktree row does not cite AGENTS.md as the carve-out's home"
    )


def test_pipeline_worktree_row_restates_nothing_from_the_table():
    cell = _pipeline_worktree_row()
    for leaked in ("Deploy act", "Attended fast-forward", "Declared / named",
                   "Refreshed by", "Mutable working tree"):
        assert leaked not in cell, (
            f"pipeline.md's Worktree row restates canon table content ({leaked!r}) "
            f"instead of just citing it"
        )


def _closing_merge_ship_bullet():
    text = CLOSING.read_text(encoding="utf-8")
    start = text.find("\n- Merge ≠ ship")
    assert start != -1, "closing.md is missing its 'Merge ≠ ship' bullet"
    end = text.find("\n- ", start + 1)
    assert end != -1
    return text[start:end]


def test_closing_merge_ship_bullet_cites_the_carveout():
    bullet = _closing_merge_ship_bullet()
    norm = _normalized(bullet)
    assert "eight" in norm and "runtime surface" in norm, (
        "closing.md's 'merge != ship' bullet does not cite the eight runtime surfaces"
    )
    assert "agents.md" in norm, (
        "closing.md's 'merge != ship' bullet does not cite AGENTS.md as the carve-out's home"
    )


def test_closing_merge_ship_bullet_restates_nothing_from_the_table():
    bullet = _closing_merge_ship_bullet()
    for leaked in ("Deploy act", "Attended fast-forward", "Declared / named",
                   "Refreshed by", "Mutable working tree"):
        assert leaked not in bullet, (
            f"closing.md's 'merge != ship' bullet restates canon table content ({leaked!r}) "
            f"instead of just citing it"
        )


def test_carveout_citation_appears_once_per_file():
    """One citing sentence each — not a restatement scattered across the file."""
    pipeline_text = PIPELINE.read_text(encoding="utf-8")
    closing_text = CLOSING.read_text(encoding="utf-8")
    assert pipeline_text.lower().count("eight runtime surface") == 1
    assert closing_text.lower().count("eight runtime surface") == 1


# ── the repo-map row for provenance.py still names the declared population ─────────────────────

def test_repo_map_still_describes_provenance_as_the_surfaces_home():
    text = _agents_text()
    m = re.search(r"\|\s*`tools/provenance\.py`\s*\|(?P<cell>.*)\|\s*$", text, re.MULTILINE)
    assert m, "AGENTS.md repo map is missing its tools/provenance.py row"
    assert "SURFACES" in m.group("cell")
