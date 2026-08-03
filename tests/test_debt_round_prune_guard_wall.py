"""
Tests for issue #360 — Debt round: the wall — every prune slice ships a guard that makes its
own finding non-recurring (technical-RFC slice P3 of epic #357).

Derived from the issue #360 acceptance criteria (the spec), not from the doc-editor's own
wording:

  1. Every prune slice ships a guard that fails when its own finding recurs.
  2. Where a finding admits no deterministic predicate, the slice records why no guard is
     expressible and what would have to be true for one to exist (a recorded impossibility is
     a finding; silence is not).
  3. Where a guard protects an enumerable set, the expected set is derived from the tree rather
     than enumerated as offenders; a hardcoded list appears only as a tombstone for a named
     removal.
  4. Where a guard asserts against a document, it names the surface it reads — the specific
     section or table, not the containing file — so a match found outside that surface can't
     satisfy it.

Plus the stated constraints: the wall names no instrument (an ordinary pytest test is a
legitimate guard), and the three cited exemplars must resolve to real paths/symbols at the
base ref. Only skills/factory/references/debt-rounds.md is amended by this slice —
templates/debt-census.md is untouched and no cardinality runner is built.

House doc-pin style, in the manner of tests/test_debt_census_surface_and_inputs.py — read the
shipped file, assert its load-bearing content.

Runs under `pytest tests/ -q` (no venv in a cut build worktree).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
DEBT_ROUNDS = REFS / "debt-rounds.md"
DEBT_CENSUS = ROOT / "templates" / "debt-census.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _rounds():
    return _text(DEBT_ROUNDS)


def _walls_section():
    text = _rounds()
    start = text.find("## The walls")
    end = text.find("## Record grammars")
    assert start != -1, "debt-rounds.md is missing the 'The walls' section heading"
    assert end != -1, "debt-rounds.md is missing the 'Record grammars' section heading"
    assert start < end
    return text[start:end]


def _wall_11_body():
    section = _walls_section()
    start = re.search(r"(?m)^11\. \*\*", section)
    assert start is not None, "debt-rounds.md walls do not carry a numbered wall 11"
    end = re.search(r"(?m)^12\. \*\*", section)
    body = section[start.start():end.start() if end else len(section)]
    return body


def _norm(text):
    """Collapse whitespace runs (incl. line-wrap newlines) to a single space, so a phrase
    check isn't brittle against where the markdown happens to wrap a line."""
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------------------
# Shape — wall 11 exists, numbered contiguously in the same rule-plus-reason
# shape as the six pre-existing walls (bolded title, then the reason)
# ---------------------------------------------------------------------------

def test_debt_rounds_walls_are_numbered_one_through_eleven_contiguous():
    section = _walls_section()
    numbers = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+)\. \*\*", section)]
    assert numbers == list(range(1, 12)), (
        f"debt-rounds.md walls are not numbered 1..11 contiguously: got {numbers}"
    )


def test_debt_rounds_wall_11_has_a_bolded_title_then_reason():
    body = _wall_11_body()
    m = re.match(r"11\. \*\*([^*]+)\*\*\s+(.+)", body, re.S)
    assert m, (
        "debt-rounds.md wall 11 is not in the numbered rule-plus-reason shape (a bolded title "
        "followed by prose) shared by walls 1-10"
    )
    title, reason = m.group(1), m.group(2)
    assert title.strip().endswith("."), (
        "debt-rounds.md wall 11's bolded title does not end in a period, unlike walls 1-10"
    )
    assert len(reason.strip()) > 40, (
        "debt-rounds.md wall 11's title is not followed by a reason of any substance"
    )


def test_debt_rounds_pre_existing_walls_1_through_10_titles_unchanged():
    section = _walls_section()
    pre_existing_titles = [
        "Census with a reachability ledger.",
        "By-name scope.",
        "Pin-then-prune.",
        "Birth citation.",
        "One item = one revertible chain.",
        "The prune review bar.",
        "Swept surface, not clock.",
        "Per-arm exemption, declared.",
        "Generated evidence out, tests apart.",
        "Inputs mined before swept.",
    ]
    for title in pre_existing_titles:
        assert title in section, (
            f"debt-rounds.md walls no longer carry the pre-existing wall {title!r} — walls "
            "1-10 must stay untouched by this slice"
        )


# ---------------------------------------------------------------------------
# AC1 — every prune slice ships a guard that fails when its own finding recurs
# ---------------------------------------------------------------------------

def test_debt_rounds_wall_11_requires_every_prune_slice_to_ship_a_guard():
    body = _norm(_wall_11_body()).lower()
    assert "every prune slice" in body, (
        "debt-rounds.md wall 11 does not scope the guard requirement to every prune slice"
    )
    assert "guard" in body, "debt-rounds.md wall 11 does not name the deliverable a 'guard'"
    assert "fails when" in body or "fails if" in body, (
        "debt-rounds.md wall 11 does not state the guard must fail on recurrence"
    )
    assert "recur" in body, (
        "debt-rounds.md wall 11 does not tie the guard's failure condition to the finding "
        "recurring"
    )


def test_debt_rounds_wall_11_names_no_instrument():
    body = _wall_11_body()
    assert "ordinary" in body.lower() and "test" in body.lower(), (
        "debt-rounds.md wall 11 does not state an ordinary test is a legitimate guard — the "
        "wall must name no specific instrument (shape, not tier)"
    )
    forbidden_instruments = [
        "coverage tool",
        "mypy",
        "flake8",
        "pylint",
        "eslint",
        "custom linter",
    ]
    lower = body.lower()
    for instrument in forbidden_instruments:
        assert instrument not in lower, (
            f"debt-rounds.md wall 11 names a specific instrument ({instrument!r}) — the wall "
            "must state shape, not tier"
        )


# ---------------------------------------------------------------------------
# AC2 — the escape hatch: no deterministic predicate -> record why + what would
# have to be true; a recorded impossibility is a finding, silence is not
# ---------------------------------------------------------------------------

def test_debt_rounds_wall_11_escape_hatch_requires_why_no_guard():
    body = _norm(_wall_11_body()).lower()
    assert "no deterministic predicate" in body, (
        "debt-rounds.md wall 11 does not name the escape-hatch trigger: a finding admitting no "
        "deterministic predicate"
    )
    assert "why" in body, (
        "debt-rounds.md wall 11 does not require the slice to record why no guard is expressible"
    )


def test_debt_rounds_wall_11_escape_hatch_requires_what_would_have_to_be_true():
    body = _norm(_wall_11_body()).lower()
    assert "what would have to be true" in body, (
        "debt-rounds.md wall 11 does not require the slice to record what would have to be "
        "true for a guard to exist"
    )


def test_debt_rounds_wall_11_states_recorded_impossibility_is_a_finding_not_silence():
    body = _norm(_wall_11_body()).lower()
    assert "recorded impossibility" in body, (
        "debt-rounds.md wall 11 does not name the recorded impossibility itself"
    )
    assert "is a finding" in body, (
        "debt-rounds.md wall 11 does not state a recorded impossibility counts as a finding"
    )
    assert "silence is not" in body, (
        "debt-rounds.md wall 11 does not state silence is not a finding — both halves of the "
        "escape-hatch sentence must be present"
    )


# ---------------------------------------------------------------------------
# AC3 — tree-derivation rule + tombstone exception for enumerable-set guards
# ---------------------------------------------------------------------------

def test_debt_rounds_wall_11_states_enumerable_set_derived_from_tree():
    body = _norm(_wall_11_body()).lower()
    assert "enumerable set" in body, (
        "debt-rounds.md wall 11 does not name the enumerable-set guard case"
    )
    assert "derived from the tree" in body or "derive" in body and "tree" in body, (
        "debt-rounds.md wall 11 does not require the expected set to be derived from the tree"
    )
    assert "never enumerate" in body or "never enumerated" in body, (
        "debt-rounds.md wall 11 does not forbid enumerating the set as a list of offenders"
    )


def test_debt_rounds_wall_11_states_tombstone_exception_for_named_removal():
    body = _norm(_wall_11_body()).lower()
    assert "tombstone" in body, (
        "debt-rounds.md wall 11 does not name the tombstone exception for a hardcoded list"
    )
    assert "named removal" in body, (
        "debt-rounds.md wall 11 does not scope the tombstone exception to a named removal"
    )
    assert "hardcoded list" in body, (
        "debt-rounds.md wall 11 does not name the hardcoded list the tombstone exception "
        "applies to"
    )


# ---------------------------------------------------------------------------
# AC4 — the named-surface rule for document-asserting guards
# ---------------------------------------------------------------------------

def test_debt_rounds_wall_11_states_named_surface_rule_for_document_guards():
    body = _norm(_wall_11_body()).lower()
    assert "asserts against a document" in body or "against a document" in body, (
        "debt-rounds.md wall 11 does not scope the named-surface rule to guards that assert "
        "against a document"
    )
    assert "surface it reads" in body, (
        "debt-rounds.md wall 11 does not require the guard to name the surface it reads"
    )
    assert "section" in body and "table" in body, (
        "debt-rounds.md wall 11 does not give 'section' and 'table' as examples of a surface "
        "narrower than the containing file"
    )
    assert "containing file" in body, (
        "debt-rounds.md wall 11 does not contrast the named surface against the containing "
        "file"
    )
    assert "outside that surface" in body, (
        "debt-rounds.md wall 11 does not state a match found outside the named surface cannot "
        "satisfy the guard"
    )


# ---------------------------------------------------------------------------
# Exemplars — the three cited guards, and their claimed shapes
# ---------------------------------------------------------------------------

def test_debt_rounds_wall_11_cites_the_three_exemplars_by_name():
    body = _wall_11_body()
    exemplars = [
        "tests/harness/test_gh_fake_migration.py",
        "test_no_full_gh_fake_reimplementation_anywhere_in_tests",
        # The cardinality exemplar migrated from a bespoke test to a declared rule at it-27
        # slice A3 (#365). The wall cites the shape's new home, so this cites it too.
        "qa/cardinality.toml",
        "verdict-extraction-pipeline",
        "tests/test_docs_drift_correction.py",
    ]
    for exemplar in exemplars:
        assert exemplar in body, f"debt-rounds.md wall 11 does not cite the exemplar {exemplar!r}"


def test_gh_fake_migration_exemplar_resolves_to_a_real_test():
    path = ROOT / "tests" / "harness" / "test_gh_fake_migration.py"
    assert path.is_file(), f"exemplar path does not exist: {path}"
    text = _text(path)
    assert re.search(
        r"(?m)^def test_no_full_gh_fake_reimplementation_anywhere_in_tests\(", text
    ), (
        "tests/harness/test_gh_fake_migration.py no longer defines "
        "test_no_full_gh_fake_reimplementation_anywhere_in_tests — the wall 11 exemplar has "
        "gone stale"
    )


def test_verdict_grammar_exemplar_resolves_to_a_real_guard():
    """The wall's cardinality exemplar must resolve to something that actually enforces it.

    It began as a bespoke test (#151) and migrated to a declared rule at it-27 slice A3 (#365) --
    the same shape, one tier down, which is what the wall now recommends. The guard follows the
    exemplar to its new home rather than pinning the old one, or the wall would cite a test the
    repo deliberately deleted.
    """
    config = ROOT / "qa" / "cardinality.toml"
    assert config.is_file(), f"exemplar path does not exist: {config}"
    text = _text(config)
    assert 'id = "verdict-extraction-pipeline"' in text, (
        "qa/cardinality.toml no longer declares the `verdict-extraction-pipeline` rule -- the "
        "wall 11 exemplar has gone stale"
    )
    runner = ROOT / "qa" / "cardinality.py"
    assert runner.is_file(), "qa/cardinality.py is missing -- the declared rule enforces nothing"


def test_docs_drift_exemplar_resolves_to_the_retirement_record():
    """Second declared guard move (debt round 2, item D — issue #383): the wall 11
    exemplar paragraph itself was rewritten into a dated retirement record once the
    floor assertion it used to cite live (`assert int(match.group(1)) > 63`) was
    retired along with the README claim it floored. This pins that the exemplar
    paragraph still names the retired assertion (so the exhibit stays identifiable)
    and now frames it as retired by debt round 2, citing issue #383 — the live
    citation this test used to require is gone by design, replaced by the
    retirement record.
    """
    body = _wall_11_body()
    assert "assert int(match.group(1)) > 63" in body, (
        "debt-rounds.md wall 11's docs-drift exemplar dropped its citation of the "
        "specific floor assertion it retired — the exhibit needs the code snippet "
        "to stay identifiable"
    )
    assert "retired by debt round 2" in _norm(body), (
        "debt-rounds.md wall 11's docs-drift exemplar no longer frames the cited "
        "floor assertion as retired by debt round 2 — the exhibit has gone stale "
        "against its own retirement"
    )
    assert "#383" in body, (
        "debt-rounds.md wall 11's docs-drift exemplar dropped the issue #383 "
        "citation for its own retirement record"
    )


def test_docs_drift_floor_assertion_no_longer_lives_in_the_test_file():
    """The retirement record in debt-rounds.md is only accurate once the floor
    assertion it describes as retired is actually gone from the live test suite —
    proving the exhibit, its guard, and the floor moved together in one PR
    (debt round 2 item D, issue #383)."""
    path = ROOT / "tests" / "test_docs_drift_correction.py"
    assert path.is_file(), f"exemplar path does not exist: {path}"
    text = _text(path)
    assert "assert int(match.group(1)) > 63" not in text, (
        "tests/test_docs_drift_correction.py still carries the floor assertion "
        "debt-rounds.md's wall 11 exemplar now records as retired"
    )


# ---------------------------------------------------------------------------
# Constraint — only debt-rounds.md is amended; templates/debt-census.md and
# the cardinality runner (slice A3) are untouched by this slice
# ---------------------------------------------------------------------------

def test_debt_census_template_has_no_guard_wall_addition():
    text = _text(DEBT_CENSUS)
    assert "## Guard" not in text and "## Guards" not in text, (
        "templates/debt-census.md carries a new Guard(s) section — issue #360 amends only "
        "skills/factory/references/debt-rounds.md"
    )


def test_no_cardinality_runner_script_is_introduced():
    for candidate in ROOT.glob("tools/*cardinality*"):
        raise AssertionError(
            f"a cardinality runner {candidate} exists — slice A3 builds the cardinality "
            "runner, not this slice (issue #360)"
        )


# ---------------------------------------------------------------------------
# Out of scope — the record grammars and counter sections of debt-rounds.md
# stay untouched by this slice
# ---------------------------------------------------------------------------

def test_debt_rounds_record_grammars_section_still_declares_five_grammars():
    text = _rounds()
    start = text.find("## Record grammars")
    end = text.find("## Census arms")
    assert start != -1 and end != -1 and start < end
    section = text[start:end]
    assert "Five grammars" in section, (
        "debt-rounds.md 'Record grammars' section no longer opens with 'Five grammars' — this "
        "slice must not touch the record grammars"
    )


def test_debt_rounds_counter_section_untouched():
    text = _rounds()
    start = text.find("## The counter")
    end = text.find("## The raise")
    assert start != -1 and end != -1 and start < end
    section = text[start:end]
    assert "debt_round_every" in section, (
        "debt-rounds.md 'The counter' section no longer names debt_round_every — this slice "
        "must not touch the counter"
    )
