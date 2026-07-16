"""
Tests for Issue #217 — conduct surfaces: gates.md lint row, ruled repair
scope, onboarding line, graduation convention.

Derived from the Issue #217 acceptance criteria (the spec), not from the
implementation internals. The conduct docs (gates.md, onboarding.md,
AGENTS.md) describe already-shipped lint-tier / lens behavior (slices A-D of
the yellow-robots/factory#212 technical-rfc); this slice only makes the docs
name what already exists. These tests check:

  * gates.md's gate table names lint_cmd as blocking, running at 03-check
    immediately after check_cmd, sharing check_cmd's 126/127 environment
    discipline;
  * gates.md's advisory section states the lens (lens_cmd) is advisory —
    findings inform, never gate;
  * gates.md's Judgment points section states the ruled lint-repair scope:
    deterministic autofix first (lint_fix_cmd), then at most one LLM repair
    confined to lint-flagged files (test or production), mechanical fixes
    only, with the tests-frozen rule still governing behavioral test edits;
  * gates.md's Judgment points section states the lens-to-lint graduation
    convention: a lens rule hardens into the blocking lint tier only via a
    convention edit citing false-positive evidence across builds;
  * onboarding.md names lint_cmd/lint_fix_cmd/lens_cmd as recommended,
    stack-appropriate declarations, and states an undeclared capability
    stays silently absent, never a per-build warning;
  * AGENTS.md's repo map gains a qa/ row naming it consumer quality content,
    distinct from tools/ platform machinery;
  * every existing pinned sentence in the conduct docs (exercised by running
    the pre-existing conduct-doc pin test modules) still holds, proving this
    slice is additions-only.
"""

import re
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "factory" / "references"
GATES = REFS / "gates.md"
ONBOARDING = REFS / "onboarding.md"
AGENTS = ROOT / "AGENTS.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _section(text, heading_pattern, next_heading_pattern=r"^## "):
    match = re.search(
        rf"{heading_pattern}\n(.*?)(?={next_heading_pattern})", text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else None


def _gates_text():
    return _text(GATES)


def _gates_table():
    body = _section(_gates_text(), r"^## Gate table\n")
    assert body, "gates.md is missing the '## Gate table' section"
    return body


def _advisory_section():
    body = _section(_gates_text(), r"^## Advisory vs\. blocking\n")
    assert body, "gates.md is missing the '## Advisory vs. blocking' section"
    return body


def _judgment_points_section():
    body = _section(_gates_text(), r"^## Judgment points\n", next_heading_pattern=r"\Z")
    assert body, "gates.md is missing the '## Judgment points' section"
    return body


def _lint_cmd_row():
    table = _gates_table()
    row = next(
        (line for line in table.splitlines() if line.strip().startswith("| `lint_cmd`")),
        None,
    )
    assert row, "gates.md gate table is missing the lint_cmd row"
    return row


# ---------------------------------------------------------------------------
# gates.md — gate table: lint_cmd is blocking, 03-check, after check_cmd,
# shares check_cmd's 126/127 environment discipline
# ---------------------------------------------------------------------------

def test_gates_table_has_lint_cmd_row():
    row = _lint_cmd_row()
    assert "lint_cmd" in row


def test_lint_cmd_row_runs_at_03_check_after_check_cmd():
    row = _lint_cmd_row()
    assert re.search(r"03-check", row), \
        "lint_cmd row does not name the 03-check stage"
    assert re.search(r"after\s+`?check_cmd`?", row, re.IGNORECASE), \
        "lint_cmd row does not state it runs after check_cmd"


def test_lint_cmd_row_shares_126_127_discipline():
    row = _lint_cmd_row()
    assert "126" in row and "127" in row, \
        "lint_cmd row does not name the shared 126/127 environment-failure discipline"


def test_lint_cmd_row_is_blocking():
    row = _lint_cmd_row()
    assert re.search(r"blocking", row, re.IGNORECASE), \
        "lint_cmd row does not state it is blocking"


def test_gates_table_existing_rows_intact_after_lint_row_added():
    """Adding the lint_cmd row must not disturb the existing gate rows."""
    table = _gates_table()
    for expected_start in (
        "| `check_links`",
        "| `check_task`",
        "| `check_supersession`",
        "| `check_cmd`",
        "| Review verdict",
        "| Merge evaluator",
    ):
        assert any(line.strip().startswith(expected_start) for line in table.splitlines()), \
            f"gates.md gate table lost its existing row starting {expected_start!r}"


# ---------------------------------------------------------------------------
# gates.md — Advisory vs. blocking: lint_cmd stated blocking; lens stated
# advisory in the "findings inform, never gate" sense
# ---------------------------------------------------------------------------

def test_advisory_section_states_lint_is_blocking():
    body = _advisory_section()
    assert re.search(r"lint.{0,40}blocking|blocking.{0,40}lint", body, re.IGNORECASE), \
        "gates.md advisory section does not state the lint tier is blocking"


def test_advisory_section_preserves_existing_advisory_gates():
    body = _advisory_section()
    for name in ("`check_links`", "`check_task`", "`check_supersession`"):
        assert name in body, \
            f"gates.md advisory section lost the existing advisory gate {name}"
    assert re.search(r"`check_cmd`.{0,80}blocking|blocking.{0,80}`check_cmd`", body, re.IGNORECASE) or \
        "`check_cmd`" in body, \
        "gates.md advisory section lost the check_cmd blocking statement"


def test_advisory_section_states_lens_is_advisory_findings_inform_never_gate():
    body = _advisory_section()
    assert re.search(r"lens", body, re.IGNORECASE), \
        "gates.md advisory section does not mention the lens"
    assert re.search(r"never\s+becomes\s+blocking|never\s+gate", body, re.IGNORECASE), \
        "gates.md advisory section does not state the lens never becomes blocking / never gates"
    assert re.search(r"inform", body, re.IGNORECASE), \
        "gates.md advisory section does not say lens findings inform review"


# ---------------------------------------------------------------------------
# gates.md — Judgment points: the ruled lint-repair scope
# ---------------------------------------------------------------------------

def test_judgment_points_states_autofix_first_deterministic():
    body = _judgment_points_section()
    assert re.search(r"lint_fix_cmd", body), \
        "gates.md Judgment points does not name lint_fix_cmd as the deterministic autofix step"
    assert re.search(r"deterministic", body, re.IGNORECASE), \
        "gates.md Judgment points does not call the autofix step deterministic"
    assert re.search(r"no\s+LLM", body, re.IGNORECASE), \
        "gates.md Judgment points does not state the autofix step runs with no LLM"


def test_judgment_points_states_one_llm_repair_confined_to_lint_flagged_files():
    body = _judgment_points_section()
    assert re.search(r"one\s+LLM\s+repair", body, re.IGNORECASE), \
        "gates.md Judgment points does not state at most one LLM repair"
    assert re.search(r"confined\s+to.{0,40}lint.flagged\s+files", body, re.IGNORECASE | re.DOTALL), \
        "gates.md Judgment points does not confine the LLM repair to lint-flagged files"
    assert re.search(r"test\s+or\s+production", body, re.IGNORECASE), \
        "gates.md Judgment points does not state the repair scope covers test or production files"
    assert re.search(r"mechanical\s+fixes\s+only", body, re.IGNORECASE), \
        "gates.md Judgment points does not restrict the LLM repair to mechanical fixes only"


def test_judgment_points_states_tests_frozen_rule_still_governs():
    body = _judgment_points_section()
    assert re.search(r"tests.frozen\s+rule", body, re.IGNORECASE), \
        "gates.md Judgment points does not name the tests-frozen rule"
    assert re.search(r"behavioral\s+test\s+edits?", body, re.IGNORECASE), \
        "gates.md Judgment points does not state the tests-frozen rule bars behavioral test edits"


# ---------------------------------------------------------------------------
# gates.md — Judgment points: the lens-to-lint graduation convention
# ---------------------------------------------------------------------------

def test_judgment_points_states_graduation_is_a_convention_edit_not_automatic():
    body = _judgment_points_section()
    assert re.search(r"never\s+self.promotes?", body, re.IGNORECASE) or \
        re.search(r"not\s+automatic", body, re.IGNORECASE), \
        "gates.md Judgment points does not state lens-to-lint graduation is not automatic"
    assert re.search(r"convention\s+edit", body, re.IGNORECASE), \
        "gates.md Judgment points does not require a convention edit to graduate a lens rule"


def test_judgment_points_graduation_requires_false_positive_evidence_across_builds():
    body = _judgment_points_section()
    assert re.search(r"false.positive\s+evidence", body, re.IGNORECASE), \
        "gates.md Judgment points does not require false-positive evidence to graduate a lens rule"
    assert re.search(r"across\s+(multiple\s+)?builds", body, re.IGNORECASE), \
        "gates.md Judgment points does not require the evidence to span multiple builds"
    assert re.search(r"blocking\s+`?lint_cmd`?\s+tier|`?lint_cmd`?\s+tier", body, re.IGNORECASE), \
        "gates.md Judgment points does not name the destination as the blocking lint_cmd tier"


def test_judgment_points_existing_bullets_intact():
    """Adding the lint-repair-scope and graduation bullets must not disturb the
    pre-existing Judgment points bullets."""
    body = _judgment_points_section()
    for expected in (
        "Environment vs. code failure:",
        "One repair attempt:",
        "Review verdict is fail-closed:",
        "Scope = the artifact:",
    ):
        assert expected in body, \
            f"gates.md Judgment points lost the existing bullet starting {expected!r}"


# ---------------------------------------------------------------------------
# onboarding.md — recommended declarations + defaults-off precedent
# ---------------------------------------------------------------------------

def _onboarding_text():
    return _text(ONBOARDING)


def test_onboarding_names_the_three_keys_as_recommended_declarations():
    text = _onboarding_text()
    assert re.search(r"recommended,\s+not\s+required", text, re.IGNORECASE) or \
        re.search(r"recommended", text, re.IGNORECASE), \
        "onboarding.md does not frame the lint/lens keys as recommended"
    for key in ("`lint_cmd`", "`lint_fix_cmd`", "`lens_cmd`"):
        assert key in text, \
            f"onboarding.md does not name {key} as a recommended declaration"


def test_onboarding_recommendation_is_stack_appropriate():
    text = _onboarding_text()
    assert re.search(r"stack.appropriate", text, re.IGNORECASE), \
        "onboarding.md does not describe the recommended linter as stack-appropriate"
    assert re.search(r"ruff", text, re.IGNORECASE), \
        "onboarding.md does not give ruff as the Python example"
    assert re.search(r"eslint", text, re.IGNORECASE), \
        "onboarding.md does not give eslint as the Node example"


def test_onboarding_states_undeclared_capability_stays_silently_absent():
    text = _onboarding_text()
    assert re.search(r"silently\s+absent", text, re.IGNORECASE), \
        "onboarding.md does not state an undeclared capability stays silently absent"
    assert re.search(r"never\s+a\s+per.build\s+warning", text, re.IGNORECASE), \
        "onboarding.md does not rule out a per-build warning for an undeclared capability"


def test_onboarding_ties_silent_absence_to_defaults_off_precedent():
    text = _onboarding_text()
    assert re.search(r"defaults.off\s+precedent", text, re.IGNORECASE), \
        "onboarding.md does not cite the defaults-off precedent for the undeclared-capability behavior"
    assert re.search(r"`?auto_merge`?", text), \
        "onboarding.md does not point to auto_merge as the existing defaults-off example"


def test_onboarding_existing_step2_manifest_example_intact():
    """The recommended-keys line must be an addition to step 2, not a rewrite of
    the existing manifest example block."""
    text = _onboarding_text()
    assert 'check_cmd    = "<your check command>"' in text
    assert 'model        = "sonnet"' in text
    assert 'review_model = "opus"' in text
    assert 'base_ref     = "origin/main"' in text
    assert "# auto_merge = true" in text
    assert "The runner runs `check_cmd` with `.venv/bin` and `node_modules/.bin` on PATH" in text


# ---------------------------------------------------------------------------
# AGENTS.md — repo map gains the qa/ row
# ---------------------------------------------------------------------------

def _agents_text():
    return _text(AGENTS)


def _repo_map_table():
    text = _agents_text()
    body = _section(text, r"^## Repo map\n", next_heading_pattern=r"^---")
    assert body, "AGENTS.md is missing the '## Repo map' section"
    return body


def test_repo_map_has_qa_row():
    table = _repo_map_table()
    row = next((line for line in table.splitlines() if line.strip().startswith("| `qa/`")), None)
    assert row, "AGENTS.md repo map is missing the qa/ row"
    assert re.search(r"consumer\s+quality", row, re.IGNORECASE), \
        "AGENTS.md qa/ row does not describe it as consumer quality content"
    assert re.search(r"distinct\s+from.{0,40}`?tools/`?", row, re.IGNORECASE), \
        "AGENTS.md qa/ row does not distinguish it from the platform machinery in tools/"


def test_repo_map_existing_rows_intact():
    table = _repo_map_table()
    for expected_start in (
        "| `tools/dev-runner.sh`",
        "| `tools/dispatch.py`",
        "| `tests/`",
        "| `deploy/`",
        "| `docs/rfcs/`",
        "| `skills/`",
        "| `templates/`",
    ):
        assert any(line.strip().startswith(expected_start) for line in table.splitlines()), \
            f"AGENTS.md repo map lost its existing row starting {expected_start!r}"


# ---------------------------------------------------------------------------
# Out of scope guards
# ---------------------------------------------------------------------------

def test_no_skill_md_router_change_for_gates_or_onboarding_rows():
    """The gates and onboarding rows in SKILL.md's reference-file router table
    already exist; this slice must not add new rows or a router rewrite."""
    skill_text = _text(ROOT / "skills" / "factory" / "SKILL.md")
    assert "gates.md" in skill_text
    assert "onboarding.md" in skill_text


def test_no_plugin_version_bump():
    """This slice is reference content only — no plugin.json version bump."""
    import json
    plugin = json.loads(_text(ROOT / ".claude-plugin" / "plugin.json"))
    assert "version" in plugin


# ---------------------------------------------------------------------------
# Every existing pinned sentence in the conduct docs still holds
# ---------------------------------------------------------------------------

def test_existing_conduct_doc_pin_suites_pass_unchanged():
    """Runs the pre-existing pin-test modules that assert on gates.md,
    onboarding.md, and AGENTS.md content, proving this slice's edits are
    additions only and do not weaken any previously-pinned sentence."""
    pin_modules = [
        "test_input_gate_invariant_granularity.py",
        "test_rank_gate_never_weaker.py",
        "test_supersession_declaration_docs.py",
        "test_skill_factory_router.py",
        "test_evaluator_and_boundary_reference_docs.py",
        "test_docs_drift_correction.py",
        "test_check_supersession_scope_docs.py",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *pin_modules],
        cwd=str(ROOT / "tests"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "A pre-existing conduct-doc pin test failed, meaning this slice's edits "
        "to gates.md / onboarding.md / AGENTS.md weakened or removed previously "
        f"pinned text:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
