"""
Tests for Issue #199 — docs: the backlog canon, the sweep duty, and the
crossover test reach the shipped references.

Derived from the Issue #199 acceptance criteria (the spec) and the epic's
(yellow-robots/factory#196) slice C enumeration of the complete carried
ideas-backlog contract, not from the implementation. Prose-only PR: three
reference files gain content, no frontmatter, no checker changes.

The slice C enumeration (18 items) is the complete contract for the
ideas-backlog per-file shape: folder, naming, capture form, statuses with
their meanings, summary, scoring keys (with the axes tie and the
effort-letter meanings), computed Rank, the stamping rule, the typed-write
caveat, the scoring conduct, custody-not-progress, body form, the
append-only-mined-at-spec-time conduct, promotion pairs, the deletion rule,
the board boundary, computed views, and census inclusion. Nothing from that
enumeration may be dropped.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_model_refs import main as check_model_refs_main

MODEL = ROOT / "skills" / "factory" / "references" / "documentation-model.md"
AUTHORING = ROOT / "skills" / "factory" / "references" / "authoring.md"
CLOSING = ROOT / "skills" / "factory" / "references" / "closing.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _lower(path):
    return _text(path).lower()


def _section(text, heading_pattern):
    """Return the body of the first section whose heading matches heading_pattern,
    up to (not including) the next heading of any level."""
    heading_re = re.compile(rf"^#+\s*{heading_pattern}\s*$", re.MULTILINE)
    match = heading_re.search(text)
    assert match, f"missing a section matching heading /{heading_pattern}/"
    start = match.end()
    next_heading = re.search(r"^#{1,6}\s", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def _ideas_backlog_section():
    return _section(_text(MODEL), r"The ideas-backlog")


# ---------------------------------------------------------------------------
# No frontmatter, no checker changes — constraints
# ---------------------------------------------------------------------------

def test_references_carry_no_frontmatter():
    for path in (MODEL, AUTHORING, CLOSING):
        text = _text(path)
        assert not text.startswith("---"), (
            f"{path.relative_to(ROOT)} gained frontmatter — references stay frontmatter-free"
        )


def test_checker_source_untouched():
    # Slices A/B/D are explicitly out of scope for this docs-only issue.
    checker = ROOT / "tools" / "check_supersession.py"
    assert checker.exists(), "tools/check_supersession.py should not have been removed"


# ---------------------------------------------------------------------------
# documentation-model.md — The ideas-backlog: the complete per-file shape
# (epic #196 slice C, 18-item enumeration; nothing dropped)
# ---------------------------------------------------------------------------

def test_ideas_backlog_section_exists():
    text = _text(MODEL)
    assert re.search(r"^##\s+The ideas-backlog\s*$", text, re.MULTILINE), (
        "documentation-model.md is missing a '## The ideas-backlog' section"
    )


def test_ideas_backlog_folder():
    body = _ideas_backlog_section()
    assert re.search(r"`?ideas/`?\s+folder.{0,40}alongside\s+`?iterations/`?", body), (
        "ideas-backlog section does not state the ideas/ folder sits alongside iterations/"
    )


def test_ideas_backlog_naming():
    body = _ideas_backlog_section()
    assert "yyyy-mm-dd-slug.md" in body, (
        "ideas-backlog section does not state the yyyy-mm-dd-slug.md naming convention"
    )
    assert re.search(r"date\s+orders?\s+seeds?\s+born\s+in\s+parallel", body, re.IGNORECASE), (
        "ideas-backlog section does not explain why the date orders parallel-born seeds"
    )


def test_ideas_backlog_capture_form():
    body = _ideas_backlog_section()
    assert re.search(r"pinned\s+frontmatter\s+only", body, re.IGNORECASE), (
        "ideas-backlog section does not state capture creates the file with pinned frontmatter only"
    )
    assert re.search(r"`?type:\s*note`?", body), (
        "ideas-backlog section does not pin type: note on capture"
    )


def test_ideas_backlog_statuses_with_meanings():
    body = _ideas_backlog_section()
    assert re.search(r"`?open`?.{0,40}pending.{0,40}(folder.s\s+custody|custody)", body, re.IGNORECASE), (
        "ideas-backlog section does not state 'open' means pending / the folder's custody"
    )
    assert re.search(r"`?rejected`?.{0,60}died\s+at\s+mining", body, re.IGNORECASE), (
        "ideas-backlog section does not state 'rejected' means died at mining"
    )
    assert re.search(r"rejected.{0,80}tombstone\s+kept", body, re.IGNORECASE), (
        "ideas-backlog section does not state a rejected seed keeps a tombstone"
    )
    assert re.search(r"dated\s+reason.{0,20}(the\s+)?body", body, re.IGNORECASE), (
        "ideas-backlog section does not state the rejected tombstone carries a dated reason in the body"
    )
    assert re.search(r"`?superseded`?\s*\+\s*`?superseded_by`?.{0,40}promoted", body, re.IGNORECASE), (
        "ideas-backlog section does not state superseded + superseded_by means promoted"
    )
    assert re.search(r"pair\s+the\s+sweep\s+verifies", body, re.IGNORECASE), (
        "ideas-backlog section does not tie the superseded/superseded_by pair to the sweep verification"
    )


def test_ideas_backlog_summary_field():
    body = _ideas_backlog_section()
    assert re.search(r"`?summary`?.{0,60}plain-speech\s+scan\s+line", body, re.IGNORECASE), (
        "ideas-backlog section does not describe `summary` as the plain-speech scan line"
    )
    assert re.search(r"so-what\s+a\s+human\s+prioritizes\s+by", body, re.IGNORECASE), (
        "ideas-backlog section does not state summary is the so-what a human prioritizes by"
    )


def test_ideas_backlog_scoring_keys_axes_tie_and_effort_letters():
    body = _ideas_backlog_section()
    # value: 1-5, magnitude, standing axes tie
    assert re.search(r"`?value`?\s*\(?1.5\)?", body), (
        "ideas-backlog section does not state value is scored 1-5"
    )
    assert re.search(r"so-what\s+magnitude.{0,60}standing\s+axes", body, re.IGNORECASE), (
        "ideas-backlog section does not tie value to the so-what magnitude against the standing axes"
    )
    for axis in ("cost control", "quality per iteration", "incremental understanding"):
        assert axis in body.lower(), (
            f"ideas-backlog section does not name the standing axis: {axis!r}"
        )
    assert re.search(r"breadth\s+across\s+repos\s+counts", body, re.IGNORECASE), (
        "ideas-backlog section does not state breadth across repos counts toward value"
    )
    # effort: S/M/L with meanings
    assert re.search(r"`?effort`?", body)
    assert re.search(r"`?S`?\s*\(a\s+slice\)", body), (
        "ideas-backlog section does not state effort S means a slice"
    )
    assert re.search(r"`?M`?\s*\(a\s+few\s+slices\)", body), (
        "ideas-backlog section does not state effort M means a few slices"
    )
    assert re.search(r"`?L`?\s*\(an\s+iteration\s+or\s+more\)", body), (
        "ideas-backlog section does not state effort L means an iteration or more"
    )


def test_ideas_backlog_computed_rank():
    body = _ideas_backlog_section()
    assert re.search(r"rank\*{0,2}\s*=\s*value\s*(÷|/)\s*effort", body, re.IGNORECASE), (
        "ideas-backlog section does not define Rank = value / effort"
    )
    assert re.search(r"computed\s+by\s+the\s+views,?\s+never\s+stored", body, re.IGNORECASE), (
        "ideas-backlog section does not state Rank is computed by the views and never stored"
    )


def test_ideas_backlog_stamping_rule():
    body = _ideas_backlog_section()
    assert re.search(r"never\s+hand-stamp\s+`?created`?/`?updated`?", body, re.IGNORECASE), (
        "ideas-backlog section does not state the never-hand-stamp rule"
    )
    assert re.search(r"update-time\s+plugin\s+stamps", body, re.IGNORECASE), (
        "ideas-backlog section does not attribute stamping to the vault's update-time plugin"
    )
    assert re.search(r"`?created`?\s+only\s+to\s+backdate", body, re.IGNORECASE), (
        "ideas-backlog section does not state created is supplied only to backdate"
    )
    assert re.search(r"5\s*minutes?", body, re.IGNORECASE), (
        "ideas-backlog section does not state the 5-minute re-stamp throttle"
    )


def test_ideas_backlog_typed_write_caveat():
    body = _ideas_backlog_section()
    assert re.search(r"YAML\s+numbers?", body, re.IGNORECASE), (
        "ideas-backlog section does not state scores land as YAML numbers"
    )
    assert re.search(r"CLI\s+property\s+write.{0,40}quotes?.{0,20}strings?", body, re.IGNORECASE), (
        "ideas-backlog section does not state the CLI property write quotes scores to strings"
    )
    assert "processFrontMatter" in body, (
        "ideas-backlog section does not name processFrontMatter as a typed write path"
    )
    assert re.search(r"FS\s+creation", body, re.IGNORECASE), (
        "ideas-backlog section does not name FS creation as a typed write path"
    )


def test_ideas_backlog_scoring_conduct():
    body = _ideas_backlog_section()
    assert re.search(r"capturing\s+session\s+proposes", body, re.IGNORECASE), (
        "ideas-backlog section does not state the capturing session proposes value/effort"
    )
    assert re.search(r"human\s+adjusts\s+inline", body, re.IGNORECASE), (
        "ideas-backlog section does not state the human adjusts inline"
    )
    assert re.search(r"spec\s+session.{0,60}re-ranks", body, re.IGNORECASE), (
        "ideas-backlog section does not state the spec session that sweeps the backlog re-ranks"
    )


def test_ideas_backlog_custody_not_progress():
    body = _ideas_backlog_section()
    assert re.search(r"custody", body, re.IGNORECASE), (
        "ideas-backlog section does not name the custody-not-progress rule"
    )
    assert re.search(r"`?open`?\s+is\s+the\s+folder.s", body, re.IGNORECASE), (
        "ideas-backlog section does not state open is the folder's custody"
    )
    assert re.search(r"`?superseded`?\s+is\s+a\s+named\s+spec.s", body, re.IGNORECASE), (
        "ideas-backlog section does not state superseded is a named spec's"
    )
    assert re.search(r"`?rejected`?\s+is\s+nobody.s", body, re.IGNORECASE), (
        "ideas-backlog section does not state rejected is nobody's"
    )
    assert re.search(r"(never|ever)\s+means?\s+.{0,3}implemented", body, re.IGNORECASE), (
        "ideas-backlog section does not state nothing in the backlog ever means implemented"
    )


def test_ideas_backlog_body_form():
    body = _ideas_backlog_section()
    assert re.search(r"entry\s+verbatim", body, re.IGNORECASE), (
        "ideas-backlog section does not state the body is the entry verbatim"
    )
    for token in ("date", "idea", "provenance"):
        assert token in body.lower(), (
            f"ideas-backlog section body form is missing {token!r}"
        )
    assert re.search(r"dated-in-place", body, re.IGNORECASE), (
        "ideas-backlog section does not state corrections edit the seed's file dated-in-place"
    )
    assert re.search(r"never\s+a\s+new\s+annex", body, re.IGNORECASE), (
        "ideas-backlog section does not forbid a new annex for corrections"
    )


def test_ideas_backlog_append_only_mined_at_spec_time():
    body = _ideas_backlog_section()
    assert re.search(r"append-only", body, re.IGNORECASE), (
        "ideas-backlog section does not state the append-only conduct"
    )
    assert re.search(r"never\s+silently\s+rewritten", body, re.IGNORECASE), (
        "ideas-backlog section does not forbid silent rewrites"
    )
    assert re.search(r"sweeps\s+Pending", body, re.IGNORECASE), (
        "ideas-backlog section does not state each iteration's design sweeps Pending"
    )
    assert re.search(r"promotes\s+what.s\s+earned", body, re.IGNORECASE), (
        "ideas-backlog section does not state the sweep promotes what's earned"
    )
    assert re.search(r"dispositions?\s+the\s+rest", body, re.IGNORECASE), (
        "ideas-backlog section does not state the sweep dispositions the rest"
    )


def test_ideas_backlog_promotion_pairs():
    body = _ideas_backlog_section()
    assert re.search(r"mining\s+spec.s\s+`?supersedes`?\s+names\s+the\s+seed", body, re.IGNORECASE), (
        "ideas-backlog section does not state the mining spec's supersedes names the seed"
    )
    assert re.search(r"seed.s\s+`?superseded_by`?\s+names\s+it\s+back", body, re.IGNORECASE), (
        "ideas-backlog section does not state the seed's superseded_by names the spec back"
    )


def test_ideas_backlog_deletion_rule():
    body = _ideas_backlog_section()
    assert re.search(r"promoting\s+iteration\s+ships", body, re.IGNORECASE), (
        "ideas-backlog section does not tie the deletion rule to the promoting iteration shipping"
    )
    assert re.search(r"spine\s+freezes", body, re.IGNORECASE), (
        "ideas-backlog section does not tie the deletion rule to the spine freezing"
    )
    assert re.search(r"promoted\s+seed.s\s+now-`?superseded`?\s+file\s+is\s+\*{0,2}deleted\*{0,2}", body, re.IGNORECASE), (
        "ideas-backlog section does not state the promoted seed's superseded file is deleted"
    )
    assert re.search(r"rejected.{0,40}seed.{0,40}keeps?\s+its\s+dated\s+tombstone", body, re.IGNORECASE), (
        "ideas-backlog section does not contrast: a rejected seed still keeps its dated tombstone"
    )


def test_ideas_backlog_board_boundary():
    body = _ideas_backlog_section()
    assert re.search(r"not\s+a\s+backlog\s+of\s+tasks", body, re.IGNORECASE), (
        "ideas-backlog section does not state it is not a backlog of tasks"
    )
    assert re.search(r"board\s+stays\s+lean", body, re.IGNORECASE), (
        "ideas-backlog section does not state the board stays lean"
    )
    assert re.search(r"idea\s+earns?\s+a\s+task\s+only\s+once\s+a\s+spec\s+mines\s+it", body, re.IGNORECASE), (
        "ideas-backlog section does not state an idea earns a task only once a spec mines it"
    )


def test_ideas_backlog_computed_views():
    body = _ideas_backlog_section()
    assert re.search(r"Bases\s+views", body, re.IGNORECASE), (
        "ideas-backlog section does not name the Bases views as the computed-views mechanism"
    )
    assert re.search(r"only\s+sanctioned\s+dashboard", body, re.IGNORECASE), (
        "ideas-backlog section does not tie the computed views to the hub/index-note ban"
    )
    assert re.search(r"hold\s+no\s+facts\s+of\s+their\s+own", body, re.IGNORECASE), (
        "ideas-backlog section does not state the views hold no facts of their own"
    )
    assert re.search(r"AI\s+mines\s+the\s+folder\s+directly,?\s+never\s+the\s+view", body, re.IGNORECASE), (
        "ideas-backlog section does not state an AI mines the folder directly, never the view"
    )


def test_ideas_backlog_census_inclusion():
    body = _ideas_backlog_section()
    assert re.search(r"joins?\s+the\s+supersession\s+census", body, re.IGNORECASE), (
        "ideas-backlog section does not state an ideas folder joins the supersession census"
    )
    assert re.search(r"like\s+any\s+other\s+governed\s+location", body, re.IGNORECASE), (
        "ideas-backlog section does not state census inclusion is like any other governed location"
    )


def test_ideas_backlog_vocabulary_is_per_location_not_global():
    """Gotcha guard: state the vocabulary per-location and totalled across the three
    doc classes — a global restatement recreates the ambiguity this iteration kills."""
    text = _text(MODEL)
    # Somewhere after the ideas-backlog section (or within it), the per-location scoping
    # must be reasserted so summary/value/effort/open don't read as globally legal.
    assert re.search(
        r"per-location,?\s+not\s+a\s+global\s+grant", text, re.IGNORECASE
    ), (
        "documentation-model.md does not reassert the ideas vocabulary is per-location, "
        "not a global grant"
    )
    assert re.search(
        r"outside\s+`?ideas/`?.{0,80}(summary|value|effort).{0,80}alien",
        text,
        re.IGNORECASE,
    ), (
        "documentation-model.md does not state summary/value/effort stay alien-key "
        "observations outside ideas/"
    )


# ---------------------------------------------------------------------------
# documentation-model.md — the three self-contradictions reconciled
# ---------------------------------------------------------------------------

def test_boundary_sentence_names_ideas_backlog_as_named_lightly_governed_class():
    """Old text (:18) listed an ideas-backlog among the ungoverned free-form brain
    (business, legal, marketing, an ideas-backlog). It must now be carved out as its
    own named, lightly-governed class."""
    unit_body = _section(_text(MODEL), r"The unit: an iteration")
    assert re.search(r"named,?\s+lightly-governed\s+class", unit_body, re.IGNORECASE), (
        "'The unit: an iteration' section does not name the ideas-backlog as a "
        "named, lightly-governed class"
    )
    assert re.search(r"free-form\s+in\s+spirit", unit_body, re.IGNORECASE), (
        "'The unit: an iteration' section does not describe the ideas-backlog as "
        "free-form in spirit"
    )
    assert re.search(r"pinned\s+frontmatter\s+in\s+letter", unit_body, re.IGNORECASE), (
        "'The unit: an iteration' section does not describe the ideas-backlog as "
        "pinned frontmatter in letter"
    )
    # The old free-form-brain list must no longer bundle the ideas-backlog in with
    # business/legal/marketing as an ungoverned example.
    assert not re.search(
        r"business,\s*legal,\s*marketing,\s*an\s+ideas-backlog", unit_body, re.IGNORECASE
    ), (
        "'The unit: an iteration' section still lists the ideas-backlog as an "
        "ungoverned free-form-brain example alongside business/legal/marketing"
    )


def test_frontmatter_key_count_is_scoped_not_global():
    """Old text (:75) claimed the frontmatter set 'grown by exactly one key this
    iteration' with no scoping — false once ideas/ adds three more keys. The
    reconciled text must scope the one-key claim to spine/supporting-outside-ideas
    and total four keys across all three doc classes."""
    fm_body = _section(_text(MODEL), r"Frontmatter.*")
    assert re.search(
        r"spine\s+docs\s+and\s+supporting\s+docs\s+outside\s+`?ideas/`?", fm_body, re.IGNORECASE
    ), (
        "Frontmatter section does not scope the 'whole set' claim to spine docs and "
        "supporting docs outside ideas/"
    )
    assert re.search(r"grown\s+by\s+exactly\s+one\s+key", fm_body, re.IGNORECASE), (
        "Frontmatter section dropped the exactly-one-key claim for spine/supporting docs"
    )
    assert re.search(
        r"inside\s+`?ideas/`?.{0,60}(grows|three\s+more)", fm_body, re.IGNORECASE
    ), (
        "Frontmatter section does not state the ideas/ location grows the set by three more keys"
    )
    assert re.search(r"total\s+across\s+the\s+three\s+doc\s+classes", fm_body, re.IGNORECASE), (
        "Frontmatter section does not total across the three doc classes"
    )
    assert re.search(r"adds\s+four\s+keys", fm_body, re.IGNORECASE), (
        "Frontmatter section does not state this iteration adds four keys in total"
    )
    assert re.search(r"never\s+a\s+global\s+fifth", fm_body, re.IGNORECASE), (
        "Frontmatter section does not rule out a global fifth key"
    )


def test_no_new_status_value_carves_ideas_folder_exception():
    """Old text (:101) claimed 'no new status value is introduced' unconditionally
    — false once ideas/ adds `open`. The reconciled text must carve the exception,
    scoped to the ideas-folder only."""
    lifecycle_body = _section(_text(MODEL), r"Lifecycle")
    assert re.search(r"no\s+new\s+status\s+value\s+is\s+introduced", lifecycle_body, re.IGNORECASE), (
        "Lifecycle section dropped the 'no new status value is introduced' generic claim"
    )
    assert re.search(r"generically", lifecycle_body, re.IGNORECASE), (
        "Lifecycle section does not scope the no-new-status claim to 'generically'"
    )
    assert re.search(
        r"ideas-folder\s+`?note`?,?\s+which\s+adds\s+`?open`?", lifecycle_body, re.IGNORECASE
    ), (
        "Lifecycle section does not carve the named exception: the ideas-folder note adds `open`"
    )
    assert re.search(r"ideas-folder\s+only", lifecycle_body, re.IGNORECASE), (
        "Lifecycle section does not scope the `open` exception to ideas-folder only"
    )


def test_model_accept_act_sweep_call_uses_explicit_scope():
    """The accept-act bullet (:99, 'The accept act stamps the pair') must model
    check_supersession.py --sweep with the explicit --scope <component> form, not bare."""
    lifecycle_body = _section(_text(MODEL), r"Lifecycle")
    assert re.search(
        r"check_supersession\.py\s+--sweep\s+--scope\s+<component>", lifecycle_body
    ), (
        "Lifecycle section's accept-act bullet does not model the explicit "
        "--sweep --scope <component> form"
    )


def test_documentation_model_never_calls_sweep_bare():
    """No occurrence of --sweep anywhere in documentation-model.md should be bare
    (unscoped) — every sweep invocation must carry --scope."""
    text = _text(MODEL)
    for match in re.finditer(r".{0,10}--sweep.{0,30}", text):
        window = match.group(0)
        assert "--scope" in window, (
            f"documentation-model.md models a bare (unscoped) --sweep call: {window!r}"
        )


# ---------------------------------------------------------------------------
# authoring.md — the backlog-sweep duty + explicit --scope accept-act lines
# ---------------------------------------------------------------------------

def test_product_spec_step_names_backlog_sweep_duty():
    step_body = _section(_text(AUTHORING), r"1\. product-spec")
    assert re.search(r"sweep", step_body, re.IGNORECASE), (
        "authoring.md's product-spec step does not mention sweeping the backlog"
    )
    assert re.search(r"Pending", step_body), (
        "authoring.md's product-spec step does not name the Pending view"
    )
    assert re.search(r"promotes?\s+what.s\s+earned", step_body, re.IGNORECASE), (
        "authoring.md's product-spec step does not state the sweep promotes what's earned"
    )
    assert re.search(r"dispositions?\s+the\s+rest", step_body, re.IGNORECASE), (
        "authoring.md's product-spec step does not state the sweep dispositions the rest"
    )
    assert re.search(r"each\s+spec\s+session", step_body, re.IGNORECASE), (
        "authoring.md's product-spec step does not scope the sweep duty to each spec session"
    )


def test_authoring_accept_act_lines_use_explicit_scope():
    text = _text(AUTHORING)
    sweep_calls = re.findall(r"check_supersession\.py\s+--sweep[^\n`]*", text)
    assert len(sweep_calls) >= 2, (
        f"authoring.md should model at least two --sweep accept-act calls, found {sweep_calls}"
    )
    for call in sweep_calls:
        assert "--scope" in call, (
            f"authoring.md models a bare (unscoped) --sweep call: {call!r}"
        )
        assert "--scope <component>" in call, (
            f"authoring.md --sweep call does not use the explicit --scope <component> form: {call!r}"
        )


def test_authoring_never_calls_sweep_bare():
    text = _text(AUTHORING)
    for match in re.finditer(r".{0,10}--sweep.{0,30}", text):
        window = match.group(0)
        assert "--scope" in window, (
            f"authoring.md models a bare (unscoped) --sweep call: {window!r}"
        )


# ---------------------------------------------------------------------------
# closing.md — the crossover test, carried whole in the ruling's own wording
# ---------------------------------------------------------------------------

def test_crossover_test_section_exists():
    text = _text(CLOSING)
    assert re.search(r"^##.*crossover\s+test", text, re.MULTILINE | re.IGNORECASE), (
        "closing.md is missing a section naming 'the crossover test'"
    )


def _crossover_section():
    return _section(_text(CLOSING), r"\d?\.?\s*The crossover test")


def test_crossover_test_ruled_2026_07_06_carried_whole():
    body = _crossover_section()
    assert "2026-07-06" in body, (
        "closing.md's crossover test does not cite the 2026-07-06 ruling date"
    )
    assert re.search(r"carried\s+here\s+whole", body, re.IGNORECASE), (
        "closing.md's crossover test does not state it is carried here whole"
    )
    assert re.search(r"ruling.s\s+own\s+wording", body, re.IGNORECASE), (
        "closing.md's crossover test does not state it is in the ruling's own wording"
    )


def test_crossover_test_candidate_set_includes_product_iterations():
    body = _crossover_section()
    assert re.search(r"candidate\s+set", body, re.IGNORECASE), (
        "closing.md's crossover test does not name the candidate set"
    )
    assert re.search(r"includes?\s+product\s+iterations", body, re.IGNORECASE), (
        "closing.md's crossover test does not state the candidate set includes product iterations"
    )


def test_crossover_test_three_standing_axes_in_rulings_order():
    body = _crossover_section()
    assert re.search(r"beat\s+the\s+product\s+line", body, re.IGNORECASE), (
        "closing.md's crossover test does not state factory work must beat the product line"
    )
    assert re.search(r"three\s+standing\s+axes", body, re.IGNORECASE), (
        "closing.md's crossover test does not name the three standing axes"
    )
    # The ruling's own order: quality control per iteration, incremental understanding,
    # cost control — kept verbatim, and deliberately NOT harmonized with the
    # ideas-backlog value-scoring line's front-door order (cost control first).
    quality_pos = body.lower().find("quality control per iteration")
    understanding_pos = body.lower().find("incremental understanding")
    cost_pos = body.lower().find("cost control")
    assert -1 not in (quality_pos, understanding_pos, cost_pos), (
        "closing.md's crossover test is missing one of the three standing axes"
    )
    assert quality_pos < understanding_pos < cost_pos, (
        "closing.md's crossover test does not carry the three axes in the ruling's own "
        "order (quality control per iteration - incremental understanding - cost control)"
    )
    assert re.search(r"ruling.s\s+own\s+order,?\s+kept\s+verbatim", body, re.IGNORECASE), (
        "closing.md's crossover test does not flag the axis order as the ruling's own, kept verbatim"
    )


def test_crossover_test_axes_not_harmonized_with_ideas_backlog_wording():
    body = _crossover_section()
    assert re.search(r"not\s+harmonized", body, re.IGNORECASE), (
        "closing.md's crossover test does not note the two axis orderings are deliberately not harmonized"
    )


def test_crossover_test_factory_ready_when_no_candidate_wins():
    body = _crossover_section()
    assert re.search(r"factory\s+is\s+ready\s+when\s+no\s+factory\s+candidate\s+wins", body, re.IGNORECASE), (
        "closing.md's crossover test does not state the factory is ready when no factory candidate wins"
    )


def test_crossover_test_re_entry_clause():
    body = _crossover_section()
    assert re.search(r"gap\s+surfacing\s+mid-product", body, re.IGNORECASE), (
        "closing.md's crossover test does not state the re-entry trigger (a gap surfacing mid-product)"
    )
    assert re.search(r"re-enters\s+the\s+candidate\s+set", body, re.IGNORECASE), (
        "closing.md's crossover test does not state the gap re-enters the candidate set"
    )
    assert re.search(r"having\s+just\s+proven\s+its\s+value", body, re.IGNORECASE), (
        "closing.md's crossover test does not carry the 'having just proven its value' clause"
    )


def test_crossover_test_is_iteration_close_conduct():
    """AC: closing.md SHALL state the crossover test as iteration-close conduct —
    it must live under the closing reference, tied to 'at each close'."""
    body = _crossover_section()
    assert re.search(r"at\s+each\s+close", body, re.IGNORECASE), (
        "closing.md's crossover test does not tie itself to 'at each close'"
    )
    # And the reference's own load-when banner should mention it, since it's now
    # part of what this reference is loaded for.
    banner = _text(CLOSING).split("---", 1)[0]
    assert re.search(r"crossover\s+test", banner, re.IGNORECASE), (
        "closing.md's load-when banner does not mention the crossover test"
    )


# ---------------------------------------------------------------------------
# tests/test_check_model_refs.py stays green; the live tree passes its gate
# ---------------------------------------------------------------------------

def test_check_model_refs_gate_is_green_on_the_repo():
    """The independent-tester operationalization of 'tests/test_check_model_refs.py
    SHALL stay green': run the actual gate against this repo's real tree (not a
    tmp fixture) and confirm the three edited references introduced no stale
    legacy vault-doc reference (the literal name this gate scans for)."""
    assert check_model_refs_main(["--scan-root", str(ROOT)]) == 0, (
        "tools/check_model_refs.py is not green against the live tree after the "
        "backlog-canon reference edits"
    )


def test_check_model_refs_suite_passes():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_check_model_refs.py", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"tests/test_check_model_refs.py is not green:\n{result.stdout}\n{result.stderr}"
    )
