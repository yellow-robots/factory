"""
Tests for Issue #82 — Model text: the supersession declaration enters the
closed vocabulary (skill 0.7.2, no version bump this slice).

Derived from the Issue #82 acceptance criteria (the spec), not from the
implementation internals. These are text-property assertions against the
four skill references — documentation-model.md, authoring.md, closing.md,
gates.md — plus out-of-scope guards (no new reference file, no template
change, no version bump, no tools/ change visible from the doc layer).

The `supersedes` growth of the closed-vocabulary pin sets in
test_documentation_model_cross_cutting.py and
test_documentation_model_epic_crossing.py is this slice's one authorized
test change — this file adds new, independent pins alongside it and does
not touch those two files.
"""

import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
MODEL = REFS / "documentation-model.md"
AUTHORING = REFS / "authoring.md"
CLOSING = REFS / "closing.md"
GATES = REFS / "gates.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
TEMPLATES = ROOT / "templates"


def _text(path):
    return path.read_text(encoding="utf-8")


def _lower(path):
    return _text(path).lower()


def _section(text, heading_pattern, next_heading_pattern=r"^## "):
    match = re.search(
        rf"{heading_pattern}\n(.*?)(?={next_heading_pattern})", text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# documentation-model.md — Frontmatter: the `supersedes` declaration
# ---------------------------------------------------------------------------

def test_frontmatter_documents_supersedes_declaration():
    text = _text(MODEL)
    fm_body = _section(text, r"^## Frontmatter.*?")
    assert fm_body, "documentation-model.md is missing the ## Frontmatter section"
    assert "`supersedes`" in fm_body, \
        "Frontmatter section does not name the `supersedes` key"
    assert re.search(r"required\s+on\s+`?product-spec`?\s+and\s+`?feature-rfc`?", fm_body), \
        "Frontmatter section does not state supersedes is required on product-spec and feature-rfc"
    assert re.search(r"list\s+of\s+`?\[\[wikilink\]\]`?s", fm_body), \
        "Frontmatter section does not describe supersedes as a list of wikilinks"
    assert re.search(r"empty.{0,20}(`\[\]`|allowed).{0,60}(justification|one-line)", fm_body) or \
        re.search(r"one-line\s+body\s+justification", fm_body), \
        "Frontmatter section does not allow an empty declaration with a one-line body justification"
    assert re.search(r"never\s+on\s+a\s+task", fm_body), \
        "Frontmatter section does not forbid supersedes on a task"


def test_frontmatter_superseded_by_remains_the_reverse_edge():
    text = _text(MODEL)
    fm_body = _section(text, r"^## Frontmatter.*?")
    assert fm_body, "documentation-model.md is missing the ## Frontmatter section"
    assert re.search(r"`superseded_by`.{0,40}reverse\s+edge", fm_body), \
        "Frontmatter section no longer names superseded_by as the reverse edge"


def test_frontmatter_states_vocabulary_grows_by_exactly_one_key():
    lower = _lower(MODEL)
    assert re.search(r"grow(n|s)\s+by\s+exactly\s+one\s+key", lower), \
        "documentation-model.md does not state the closed vocabulary grows by exactly one key"


# ---------------------------------------------------------------------------
# documentation-model.md — Lifecycle: the accept act and the down-flow rule
# ---------------------------------------------------------------------------

def test_lifecycle_documents_the_accept_act():
    text = _text(MODEL)
    lifecycle_body = _section(text, r"^## Lifecycle\n")
    assert lifecycle_body, "documentation-model.md is missing the ## Lifecycle section"
    assert re.search(r"accept\s+act", lifecycle_body, re.IGNORECASE), \
        "Lifecycle section does not name 'the accept act'"
    assert re.search(r"same\s+session", lifecycle_body), \
        "Lifecycle section does not tie the accept-stamp to the same attended session"
    assert "`status: superseded`" in lifecycle_body, \
        "Lifecycle section does not stamp status: superseded at accept"
    assert re.search(r"superseded_by.{0,40}back-pointer", lifecycle_body), \
        "Lifecycle section does not stamp a superseded_by back-pointer to the replacer at accept"
    assert re.search(r"tombstones\s+land\s+at\s+accept", lifecycle_body), \
        "Lifecycle section does not state tombstones land at accept"
    assert re.search(r"never\s+deferred\s+to\s+close", lifecycle_body), \
        "Lifecycle section does not rule out deferring the supersession tombstone to close"
    assert re.search(r"sweep", lifecycle_body, re.IGNORECASE), \
        "Lifecycle section does not mention running the supersession sweep to verify the pairs"


def test_lifecycle_documents_the_down_flow_rule():
    text = _text(MODEL)
    lifecycle_body = _section(text, r"^## Lifecycle\n")
    assert lifecycle_body, "documentation-model.md is missing the ## Lifecycle section"
    assert re.search(r"down-flow\s+rule", lifecycle_body, re.IGNORECASE), \
        "Lifecycle section does not name 'the down-flow rule'"
    assert re.search(r"superseded\s+`?product-spec`?", lifecycle_body), \
        "down-flow rule is not scoped to a superseded product-spec"
    assert re.search(r"active.{0,20}spine\s+doc", lifecycle_body), \
        "down-flow rule does not scope its obligation to every active spine doc"
    assert "`source_spec`" in lifecycle_body, \
        "down-flow rule does not key off source_spec resolving to the superseded product-spec"
    assert re.search(r"disposition", lifecycle_body), \
        "down-flow rule does not oblige a disposition for each affected child"
    assert re.search(r"named.{0,30}declaration|declaring\s+doc", lifecycle_body), \
        "down-flow rule does not allow the disposition to be named in the declaration"
    assert re.search(r"cited.{0,40}carried\s+forward", lifecycle_body), \
        "down-flow rule does not allow the disposition to be cited as carried forward from the replacing intent"


# ---------------------------------------------------------------------------
# documentation-model.md — the research-active gloss for supporting docs
# ---------------------------------------------------------------------------

def test_supporting_doc_active_gloss_is_documented():
    text = _text(MODEL)
    lifecycle_body = _section(text, r"^## Lifecycle\n")
    assert lifecycle_body, "documentation-model.md is missing the ## Lifecycle section"
    assert re.search(r"research.{0,10}note.{0,10}runbook", lifecycle_body) or \
        re.search(r"supporting\s+docs?", lifecycle_body, re.IGNORECASE), \
        "Lifecycle section does not scope the active gloss to the supporting types"
    assert re.search(r"concluded-and-citable", lifecycle_body), \
        "Lifecycle section does not define supporting-doc active as concluded-and-citable dated testimony"
    assert re.search(r"never\s+a\s+claim\s+about\s+the\s+present", lifecycle_body), \
        "Lifecycle section does not rule out reading supporting-doc active as a claim about the present"


def test_supporting_doc_freshness_is_event_driven_not_gated():
    text = _text(MODEL)
    lifecycle_body = _section(text, r"^## Lifecycle\n")
    assert lifecycle_body, "documentation-model.md is missing the ## Lifecycle section"
    assert re.search(r"event-driven", lifecycle_body), \
        "Lifecycle section does not describe supporting-doc freshness as event-driven"
    assert re.search(r"revisit\s+trigger", lifecycle_body), \
        "Lifecycle section does not name an optional named revisit trigger in the body"
    assert re.search(r"never\s+gated", lifecycle_body), \
        "Lifecycle section does not rule out gating supporting-doc freshness on a clock"


def test_research_superseded_only_by_newer_research():
    text = _text(MODEL)
    lifecycle_body = _section(text, r"^## Lifecycle\n")
    assert lifecycle_body, "documentation-model.md is missing the ## Lifecycle section"
    assert re.search(r"research.{0,40}superseded\s+only\s+by\s+newer\s+research", lifecycle_body), \
        "Lifecycle section does not restrict research supersession to newer research only"


def test_no_new_status_value_introduced_for_the_gloss():
    text = _text(MODEL)
    lifecycle_body = _section(text, r"^## Lifecycle\n")
    assert lifecycle_body, "documentation-model.md is missing the ## Lifecycle section"
    assert re.search(r"no\s+new\s+status\s+value", lifecycle_body), \
        "Lifecycle section does not state that no new status value is introduced for the supporting-doc gloss"


# ---------------------------------------------------------------------------
# documentation-model.md — living reference: load-bearing sections
# ---------------------------------------------------------------------------

def test_living_reference_names_load_bearing_sections():
    text = _text(MODEL)
    living_body = _section(text, r"^### The living reference\n", r"^### |^## ")
    assert living_body, "documentation-model.md is missing the '### The living reference' section"
    assert re.search(r"load-bearing", living_body, re.IGNORECASE), \
        "living reference section does not name 'load-bearing' sections"
    assert re.search(r"architect\s+charter", living_body, re.IGNORECASE), \
        "living reference section does not attribute the load-bearing set to the component's architect charter"


def test_maintenance_contract_write_at_ship_names_architect_and_closing_session():
    text = _text(MODEL)
    contract_body = _section(text, r"^### The maintenance contract\n", r"^### |^## ")
    assert contract_body, "documentation-model.md is missing the '### The maintenance contract' section"
    write_row = next(
        (line for line in contract_body.splitlines() if "Write at ship" in line),
        None,
    )
    assert write_row, "maintenance contract table is missing the 'Write at ship' row"
    assert re.search(r"architect", write_row, re.IGNORECASE), \
        "Write at ship row does not attribute the ship-walk to the architect where the role is earned"
    assert re.search(r"closing\s+session", write_row, re.IGNORECASE), \
        "Write at ship row does not fall back to the closing session's ship-walk otherwise"
    # The pinned trigger phrase and its bound moment must survive the attribution addition.
    assert "**Write at ship**" in contract_body, \
        "maintenance contract lost the pinned 'Write at ship' trigger phrase"
    assert re.search(r"iteration\s+close", write_row, re.IGNORECASE), \
        "Write at ship row lost its bound-moment wording (the iteration close)"


def test_maintenance_contract_five_triggers_all_still_present():
    """All five trigger phrases and their bound-moment wordings must survive this
    slice's Write-at-ship attribution addition — the same set test_documentation_model_
    cross_cutting.py pins, checked again here at the acceptance-criteria level."""
    text = _text(MODEL)
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


# ---------------------------------------------------------------------------
# authoring.md — steps 1-2 carry the declaration procedure and the accept act
# ---------------------------------------------------------------------------

def _authoring_step(step_heading):
    text = _text(AUTHORING)
    match = re.search(
        rf"^### {re.escape(step_heading)}\n(.*?)(?=^### |^## |\Z)", text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"authoring.md is missing the '### {step_heading}' step"
    return match.group(1)


def test_authoring_step1_product_spec_declares_supersedes():
    body = _authoring_step("1. product-spec")
    assert re.search(r"carry\s+`?supersedes`?", body, re.IGNORECASE), \
        "authoring.md step 1 does not instruct carrying supersedes from the template"
    assert re.search(r"one-line\s+body\s+justification|justification", body), \
        "authoring.md step 1 does not require a justification for an empty declaration"
    assert re.search(r"check_supersession", body), \
        "authoring.md step 1 does not name check_supersession.py"
    assert re.search(r"draft\s+mode", body, re.IGNORECASE), \
        "authoring.md step 1 does not run check_supersession.py in draft mode while authoring"


def test_authoring_step1_gate_documents_the_accept_act():
    body = _authoring_step("1. product-spec")
    assert re.search(r"accept\s+act", body, re.IGNORECASE), \
        "authoring.md step 1 gate paragraph does not name 'the accept act'"
    assert re.search(r"same\s+session", body), \
        "authoring.md step 1 accept act is not tied to the same session"
    assert "`status: superseded`" in body, \
        "authoring.md step 1 accept act does not stamp status: superseded"
    assert re.search(r"superseded_by.{0,40}back-point", body), \
        "authoring.md step 1 accept act does not stamp the superseded_by back-pointer"
    assert re.search(r"--sweep", body), \
        "authoring.md step 1 accept act does not run check_supersession.py --sweep to verify the pairs"


def test_authoring_step2_feature_rfc_declares_supersedes():
    body = _authoring_step("2. feature-rfc *(only if earned)*")
    assert re.search(r"carry\s+`?supersedes`?", body, re.IGNORECASE), \
        "authoring.md step 2 does not instruct carrying supersedes from the template"
    assert re.search(r"one-line\s+body\s+justification|justification", body), \
        "authoring.md step 2 does not require a justification for an empty declaration"
    assert re.search(r"check_supersession", body), \
        "authoring.md step 2 does not name check_supersession.py"
    assert re.search(r"draft\s+mode", body, re.IGNORECASE), \
        "authoring.md step 2 does not run check_supersession.py in draft mode while authoring"


def test_authoring_step2_gate_documents_the_accept_act():
    body = _authoring_step("2. feature-rfc *(only if earned)*")
    assert re.search(r"accept\s+act", body, re.IGNORECASE), \
        "authoring.md step 2 gate paragraph does not name 'the accept act'"
    assert re.search(r"same\s+session", body), \
        "authoring.md step 2 accept act is not tied to the same session"
    assert "`status: superseded`" in body, \
        "authoring.md step 2 accept act does not stamp status: superseded"
    assert re.search(r"superseded_by.{0,40}back-point", body), \
        "authoring.md step 2 accept act does not stamp the superseded_by back-pointer"
    assert re.search(r"--sweep", body), \
        "authoring.md step 2 accept act does not run check_supersession.py --sweep to verify the pairs"


def test_authoring_on_filing_anchor_preserved():
    """Out-of-scope guard: the crossed_to cross-time-stamp anchor this slice must not disturb."""
    text = _text(AUTHORING)
    assert "**On filing**" in text, \
        "authoring.md lost the '**On filing**' crossed_to stamp anchor (out of scope for issue #82)"


# ---------------------------------------------------------------------------
# closing.md §3 — stamp-verification replaces the retire-at-close act
# ---------------------------------------------------------------------------

def _closing_freeze_section():
    text = _text(CLOSING)
    match = re.search(r"^## 3\. Doc-side freeze\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "closing.md is missing the '## 3. Doc-side freeze' section"
    return match.group(1)


def test_closing_section3_directs_stamp_verification_as_the_backstop():
    body = _closing_freeze_section()
    assert re.search(r"tombstones.{0,20}land.{0,20}at\s+accept", body, re.IGNORECASE), \
        "closing.md §3 does not state tombstones landed at accept"
    assert re.search(r"verif(y|ies).{0,60}pair", body, re.IGNORECASE), \
        "closing.md §3 does not direct verifying the supersession pairs"
    assert re.search(r"stamps?\s+(any|only\s+what.s)\s+(pair\s+)?found\s+missing", body, re.IGNORECASE), \
        "closing.md §3 does not scope stamping to what's found missing, not the act itself"
    assert re.search(r"check_supersession", body), \
        "closing.md §3 does not name check_supersession.py for the sweep"
    assert re.search(r"backstop", body, re.IGNORECASE), \
        "closing.md §3 does not call the close-time check a backstop, not the act"


def test_closing_section3_no_longer_frames_retire_at_close_as_the_supersession_act():
    body = _closing_freeze_section()
    assert not re.search(r"if\s+the\s+shipped\s+change\s+replaces\s+an\s+older\s+doc,\s+retire\s+it\s+\*\*by\s+kind\*\*",
                          body, re.IGNORECASE), \
        "closing.md §3 still frames retire-by-kind as the close-time supersession act (should be accept-time now)"


def test_closing_section3_preserves_crossed_to_backstop_bullet():
    """Out-of-scope guard: the pre-existing crossed_to verify-backstop bullet (0.7.1)
    must survive this slice's supersession-backstop addition untouched."""
    body = _closing_freeze_section()
    assert "Verify every doc that crossed carries its `crossed_to` stamp" in body, \
        "closing.md §3 lost the pre-existing crossed_to verify-backstop bullet"
    assert "set **at the crossing**, not here" in body, \
        "closing.md §3 lost the pre-existing crossed_to timing wording"


# ---------------------------------------------------------------------------
# gates.md — the check_supersession row
# ---------------------------------------------------------------------------

def _gates_table():
    text = _text(GATES)
    body = _section(text, r"^## Gate table\n", r"^## ")
    assert body, "gates.md is missing the '## Gate table' section"
    return body


def test_gates_table_has_check_supersession_row():
    table = _gates_table()
    row = next((line for line in table.splitlines() if line.strip().startswith("| `check_supersession`")), None)
    assert row, "gates.md gate table is missing the check_supersession row"
    assert re.search(r"declaration\s+grammar", row, re.IGNORECASE), \
        "check_supersession row does not check declaration grammar"
    assert re.search(r"justification", row, re.IGNORECASE), \
        "check_supersession row does not check the empty-declaration justification"
    assert re.search(r"pair\s+integrity", row, re.IGNORECASE), \
        "check_supersession row does not check pair integrity both directions"
    assert re.search(r"down-flow\s+disposition", row, re.IGNORECASE), \
        "check_supersession row does not check the down-flow disposition"
    assert re.search(r"draft", row, re.IGNORECASE), \
        "check_supersession row does not document a draft-mode run"
    assert "--sweep" in row, \
        "check_supersession row does not document the --sweep run mode"


def test_gates_table_existing_rows_intact():
    """Adding the check_supersession row must not disturb the existing gate rows."""
    table = _gates_table()
    for expected_start in (
        "| `check_links`",
        "| `check_task`",
        "| `check_cmd`",
        "| Review verdict",
        "| Merge evaluator",
    ):
        assert any(line.strip().startswith(expected_start) for line in table.splitlines()), \
            f"gates.md gate table lost its existing row starting {expected_start!r}"


def test_gates_advisory_paragraph_includes_check_supersession():
    text = _text(GATES)
    advisory_body = _section(text, r"^## Advisory vs\. blocking\n", r"^## ")
    assert advisory_body, "gates.md is missing the '## Advisory vs. blocking' section"
    assert "`check_supersession`" in advisory_body, \
        "gates.md advisory paragraph does not name check_supersession alongside check_links/check_task"
    assert "`check_links`" in advisory_body and "`check_task`" in advisory_body, \
        "gates.md advisory paragraph lost check_links/check_task while adding check_supersession"


# ---------------------------------------------------------------------------
# Out-of-scope guards — this slice is doc-text only
# ---------------------------------------------------------------------------

def test_no_new_reference_file_added():
    expected = {
        "authoring.md", "closing.md", "documentation-model.md", "gates.md",
        "migrating.md", "onboarding.md", "pipeline.md", "reviewing.md",
        "architect.md", "debt-rounds.md",
    }
    actual = {p.name for p in REFS.iterdir() if p.is_file()}
    assert actual == expected, \
        f"skills/factory/references/ gained or lost a file: {actual - expected} extra, {expected - actual} missing"


def test_skill_md_does_not_restate_supersession_declaration():
    """SKILL.md defers to the references on demand; it must not restate the
    supersedes declaration grammar or the accept-act stamping semantics
    introduced by this change."""
    lower = SKILL.read_text(encoding="utf-8").lower()
    assert "supersedes" not in lower, \
        "SKILL.md restates the supersedes declaration — it should defer to documentation-model.md instead"
    assert "accept act" not in lower, \
        "SKILL.md restates the accept act — it should defer to documentation-model.md/authoring.md instead"


def test_templates_scope_handed_off_to_83():
    """Historical note: #82 kept templates supersedes-free ('template changes
    are a later slice'). #83 is that slice and lands the scaffold — pinned
    authoritatively by tests/test_templates_declaration.py. This test only
    confirms the handoff landed, so this file doesn't keep asserting a claim
    #83 was explicitly scoped to make false."""
    for name in ("product-spec.md", "feature-rfc.md"):
        path = TEMPLATES / name
        if path.exists():
            assert "supersedes" in path.read_text(encoding="utf-8").lower(), \
                f"templates/{name} should carry supersedes now that #83 has landed it"
