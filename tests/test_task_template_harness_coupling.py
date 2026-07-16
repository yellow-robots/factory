"""Acceptance tests for issue #246 — the task template gains a harness-coupling section.

Derived from the issue's ACCEPTANCE CRITERIA (the spec), NOT the implementation's internals: a
doc-pin suite in the house style of tests/test_templates_declaration.py — read templates/task.md,
assert its load-bearing content, pinning it so it cannot silently regress.

  * templates/task.md carries guidance instructing the author to name the coupled suites when a
    change touches the harness seam (tests/harness/, the shared fakes' home).
  * The guidance is teaching content only — it states plainly that no promotion or check gate
    evaluates it, and it lives inside the existing Context & links authoring-aid comment (between
    that heading and Test expectations), never inside the filed body-as-schema fields themselves.
  * The worked example is wrapped in inline backticks — never a bare, stand-alone line a
    line-anchored scanner (the debt-hold non-triggering-phrasing precedent qa/lens.py's own
    unanchored-marker-substring species guards against) could mistake for a literal record.
  * Out of scope stays out of scope: no gate (tools/check_task.py) references this new guidance.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK = ROOT / "templates" / "task.md"
CHECK_TASK = ROOT / "tools" / "check_task.py"


def _text(path):
    return path.read_text(encoding="utf-8")


def _context_links_comment_span(text):
    """Return the (start, end) offsets of the '## Context & links' section's guidance body — from
    that heading to the next '## ' heading (Test expectations)."""
    start = text.find("## Context & links")
    assert start != -1, "templates/task.md is missing the '## Context & links' section heading"
    end = text.find("## ", start + len("## Context & links"))
    assert end != -1, "templates/task.md is missing a section heading after '## Context & links'"
    return start, end


def test_task_template_names_the_harness_seam_home():
    text = _text(TASK)
    start, end = _context_links_comment_span(text)
    section = text[start:end]
    assert "harness seam" in section, (
        "templates/task.md Context & links guidance does not name the harness seam"
    )
    assert "tests/harness/" in section, (
        "templates/task.md Context & links guidance does not name tests/harness/ as the shared fakes' home"
    )
    assert "contract.md" in section, (
        "templates/task.md Context & links guidance does not point at tests/harness/contract.md"
    )


def test_task_template_instructs_naming_coupled_suites_inline():
    text = _text(TASK)
    start, end = _context_links_comment_span(text)
    section = text[start:end]
    assert "coupled suites" in section.lower(), (
        "templates/task.md Context & links guidance does not instruct naming the coupled suites"
    )
    assert "every consuming test file" in section, (
        "templates/task.md guidance does not tell the author to list every consuming test file "
        "the change couples to"
    )
    assert "before editing" in section, (
        "templates/task.md guidance does not state the coupled-suites list exists so a builder "
        "checks them before editing"
    )


def test_task_template_worked_example_is_inline_backticked_not_a_bare_line():
    """The worked example ('Blast radius (coupled suites): ...') must appear wrapped in backticks —
    never as a bare, stand-alone markdown line that a line-anchored scanner could mistake for an
    actual filed record."""
    text = _text(TASK)
    backticked = "`Blast radius (coupled suites): tests/test_x.py, tests/test_y.py`"
    assert backticked in text, (
        "templates/task.md is missing the inline-backticked 'Blast radius (coupled suites)' worked "
        "example"
    )
    for line in text.splitlines():
        stripped = line.strip()
        assert stripped != "Blast radius (coupled suites): tests/test_x.py, tests/test_y.py", (
            "templates/task.md carries the worked example as a bare, unbackticked stand-alone line"
        )


def test_task_template_guidance_states_teaching_content_only_no_gate():
    text = _text(TASK)
    start, end = _context_links_comment_span(text)
    section = text[start:end]
    assert "Teaching content only" in section, (
        "templates/task.md harness-coupling guidance does not state it is teaching content only"
    )
    assert "no promotion or check gate evaluates this line" in section, (
        "templates/task.md harness-coupling guidance does not disclaim gate evaluation"
    )


def test_task_template_harness_guidance_lives_inside_context_links_html_comment():
    """The guidance is an authoring aid, not filed content: it must sit inside the existing HTML
    comment under '## Context & links', before the '## Test expectations' heading — not carved out
    as its own new promoted section."""
    text = _text(TASK)
    context_idx = text.find("## Context & links")
    guidance_idx = text.find("harness seam")
    test_expectations_idx = text.find("## Test expectations")
    assert context_idx != -1 and guidance_idx != -1 and test_expectations_idx != -1
    assert context_idx < guidance_idx < test_expectations_idx, (
        "templates/task.md harness-coupling guidance is not positioned inside the Context & links "
        "section, ahead of Test expectations"
    )
    comment_open = text.rfind("<!--", context_idx, guidance_idx)
    comment_close = text.find("-->", guidance_idx)
    assert comment_open != -1 and comment_close != -1 and comment_open < guidance_idx < comment_close, (
        "templates/task.md harness-coupling guidance does not sit inside the Context & links "
        "authoring-aid HTML comment"
    )


def test_task_template_does_not_gain_a_new_promoted_heading():
    """No new '## ' section heading was added for this — the guidance is inline teaching content
    inside the existing Context & links comment, not a new filed field."""
    text = _text(TASK)
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Goal",
        "## Acceptance criteria",
        "## Context & links",
        "## Test expectations",
        "## Constraints / out of scope",
        "## Size",
    ], f"templates/task.md section headings changed unexpectedly: {headings}"


def test_check_task_gate_does_not_evaluate_the_harness_coupling_guidance():
    """Out of scope per #246: no check gate anywhere evaluates the harness-coupling line."""
    text = _text(CHECK_TASK)
    assert "Blast radius" not in text
    assert "harness seam" not in text
    assert "coupled suites" not in text.lower()
