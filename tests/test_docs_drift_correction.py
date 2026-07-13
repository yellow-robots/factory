"""
Tests for Issue #152 — docs: correct every named stale fact to the tree's
present truth.

Derived from the Issue #152 acceptance criteria (the spec), not from the
implementation. Scope is letter-only: five README.md facts, the DISPATCH.md
promotion self-contradiction, two stale skill-reference mechanisms, the
redundant templates/README.md (deleted, with its guard test), the task
template's blanket human-merge line, two phantom RFC-0006 citations, and the
AGENTS.md repo map completion.

Per the gotchas recorded at review: no test elsewhere in the suite pins any
of these stale facts (grepped per named fact); the AGENTS.md repo-map test
(test_operating_doc_consolidation.py::test_repo_map_lists_every_core_path)
asserts presence only, so adding rows is safe; the DISPATCH.md diagram pin
(test_dispatch.py::test_dispatch_md_diagram_no_longer_claims_single_flight)
requires "single-flight" stay absent from the diagram line — untouched here,
re-asserted below for this issue's own record.
"""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
DISPATCH_MD = ROOT / "deploy" / "DISPATCH.md"
DISPATCH_ENV_EXAMPLE = ROOT / "deploy" / "dispatch.env.example"
CLOSING = ROOT / "skills" / "factory" / "references" / "closing.md"
ONBOARDING = ROOT / "skills" / "factory" / "references" / "onboarding.md"
TASK_TEMPLATE = ROOT / "templates" / "task.md"
TEMPLATES_README = ROOT / "templates" / "README.md"
TEST_TEMPLATES_DECLARATION = ROOT / "tests" / "test_templates_declaration.py"


def _text(path):
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# README.md — five stale facts
# ---------------------------------------------------------------------------

def test_readme_merge_line_is_not_blanket_human():
    text = _text(README)
    assert "a human merges" not in text, (
        "README.md still claims a human always merges — stale under the "
        "armed/shadow-merge reality"
    )


def test_readme_merge_line_states_armed_vs_human_reality():
    text = _text(README)
    assert re.search(r"factory.executed", text, re.IGNORECASE), (
        "README.md merge line dropped the factory-executed-for-an-armed-repo fact"
    )
    assert re.search(r"human", text, re.IGNORECASE), (
        "README.md merge line dropped the human-merge fallback fact"
    )


def test_readme_rfc_0005_is_not_marked_in_rework():
    text = _text(README)
    assert "in rework" not in text, (
        "README.md still claims RFC 0005 upper-pipeline is in rework — stale, it shipped"
    )
    assert re.search(r"0005 upper-pipeline", text), (
        "README.md dropped the RFC 0005 upper-pipeline citation entirely"
    )


def test_readme_test_count_is_not_the_stale_63():
    text = _text(README)
    assert not re.search(r"\b63 tests\b", text), (
        "README.md still cites the stale '63 tests green' figure"
    )
    match = re.search(r"(\d+) tests green", text)
    assert match, "README.md dropped the '<N> tests green' status fact"
    # Not pinned to an exact count: the suite grows as later slices land (this
    # task's own new tests shift it too), same reasoning as the doc-byte-size
    # non-pin in test_operating_doc_consolidation.py. Just sanity-check it is
    # a plausible, non-stale figure.
    assert int(match.group(1)) > 63


def test_readme_dead_remaining_items_are_gone():
    text = _text(README)
    assert "**Remaining:**" not in text, (
        "README.md still carries the dead 'Remaining:' punch list"
    )
    assert "now-duplicated copy of the" not in text, (
        "README.md still cites the stale yellow-robots duplicated-tooling remaining item"
    )
    assert "repoint the live dispatch service" not in text, (
        "README.md still cites the stale repoint-the-dispatch-service remaining item"
    )


def test_readme_phantom_rfc_0006_is_gone():
    text = _text(README)
    assert "RFC 0006" not in text, (
        "README.md still cites the phantom RFC 0006"
    )
    assert re.search(r"website.*onboarding", text, re.IGNORECASE), (
        "README.md website line lost its surviving 'onboarding' fact when RFC 0006 was stripped"
    )


def test_readme_tools_table_lists_more_than_three_tools():
    # The named drift was "3 of 15 tools" — the table must grow past the
    # stale 3-tool snapshot. Not pinned to the full tools/ listing: the
    # acceptance criteria names an exact addition list for AGENTS.md's repo
    # map (tested below) but not for README's summary table, which points
    # readers at AGENTS.md for the full map.
    text = _text(README)
    what_section_match = re.search(r"## What's here\n(.*?)\n##", text, re.DOTALL)
    assert what_section_match, "README.md is missing the 'What's here' table"
    section = what_section_match.group(1)

    tool_refs = set(re.findall(r"tools/[\w.-]+\.(?:py|sh)", section))
    assert len(tool_refs) > 3, (
        f"README.md 'What's here' table still lists only {len(tool_refs)} tool "
        f"script(s) — the stale '3 of 15 tools' drift wasn't corrected"
    )


# ---------------------------------------------------------------------------
# deploy/DISPATCH.md — promotion self-contradiction resolved to the living
# rule; epic-sweep documentation at :120-122 left intact; "single-flight"
# stays absent from the diagram line
# ---------------------------------------------------------------------------

def test_dispatch_md_grooming_is_not_blanket_stays_human():
    text = _text(DISPATCH_MD)
    assert "Grooming stays human" not in text, (
        "DISPATCH.md still states the blanket 'Grooming stays human' self-contradiction"
    )


def test_dispatch_md_grooming_states_mechanical_epic_and_human_standalone():
    text = _text(DISPATCH_MD)
    grooming_match = re.search(r"\*\*Grooming[^:]*:\*\*(.*?)(?=\n- \*\*|\n##)", text, re.DOTALL)
    assert grooming_match, "DISPATCH.md is missing its Grooming safety-property bullet"
    grooming = grooming_match.group(1)
    assert re.search(r"mechanical", grooming, re.IGNORECASE), (
        "DISPATCH.md Grooming bullet dropped the mechanical-for-a-governed-epic fact"
    )
    assert re.search(r"human", grooming, re.IGNORECASE), (
        "DISPATCH.md Grooming bullet dropped the human-for-a-standalone-task fact"
    )
    assert re.search(r"standing approval", grooming, re.IGNORECASE), (
        "DISPATCH.md Grooming bullet dropped the standing-approval basis for mechanical promotion"
    )


def test_dispatch_md_epic_sweep_section_survives_intact():
    text = _text(DISPATCH_MD)
    assert "## Deploying the epic-gate sweep" in text, (
        "DISPATCH.md dropped the epic-gate sweep section while resolving the grooming contradiction"
    )
    assert "tools/epic_gate.py" in text
    assert "SWEEP_LOCK" in text
    assert "POST /sweep" in text


def test_dispatch_md_diagram_still_omits_single_flight():
    text = _text(DISPATCH_MD)
    diagram_line = next(
        (l for l in text.splitlines() if "dispatch.service" in l), None
    )
    assert diagram_line is not None, "DISPATCH.md is missing its dispatch.service diagram line"
    assert "single-flight" not in diagram_line.lower(), (
        "DISPATCH.md diagram line regained the retired 'single-flight' claim"
    )


# ---------------------------------------------------------------------------
# skills/factory/references/closing.md — drop "a manual grep until it ships"
# ---------------------------------------------------------------------------

def test_closing_md_drops_manual_grep_until_it_ships():
    text = _text(CLOSING)
    assert "a manual grep until it ships" not in text, (
        "closing.md still claims check_model_refs.py's consumer scan is a manual grep "
        "until it ships — it shipped (0422964, #7)"
    )
    assert "check_model_refs.py" in text, (
        "closing.md dropped the check_model_refs.py citation entirely"
    )


# ---------------------------------------------------------------------------
# templates/README.md — deleted, along with its only guard test
# ---------------------------------------------------------------------------

def test_templates_readme_is_deleted():
    assert not TEMPLATES_README.exists(), (
        "templates/README.md still exists — ruled delete 2026-07-13, it is the "
        "redundant template README"
    )


def test_templates_readme_guard_test_is_removed():
    text = _text(TEST_TEMPLATES_DECLARATION)
    assert "test_readme_template_does_not_reference_debt_round_ledger_grammar" not in text, (
        "tests/test_templates_declaration.py still carries the guard test for the "
        "deleted templates/README.md — its only subject is gone, so the guard must "
        "go with it or the suite crashes with FileNotFoundError"
    )


def test_no_other_reference_to_templates_readme_survives():
    text_files = list(ROOT.rglob("*.md")) + list(ROOT.rglob("*.py"))
    offenders = []
    for path in text_files:
        if ".git" in path.parts:
            continue
        if path == pathlib.Path(__file__):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "templates/README.md" in content:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"deleted templates/README.md is still referenced by: {offenders}"
    )


# ---------------------------------------------------------------------------
# templates/task.md — blanket "Final gate: merge (human)" corrected
# ---------------------------------------------------------------------------

def test_task_template_final_gate_is_not_blanket_human():
    text = _text(TASK_TEMPLATE)
    assert "**merge** (human)" not in text, (
        "templates/task.md still states the blanket 'Final gate: merge (human)' line"
    )


def test_task_template_final_gate_states_armed_vs_human_reality():
    text = _text(TASK_TEMPLATE)
    gate_match = re.search(r"Final gate:(.*)", text, re.DOTALL)
    assert gate_match, "templates/task.md dropped the 'Final gate:' line"
    gate_line = gate_match.group(1)
    assert re.search(r"factory.executed", gate_line, re.IGNORECASE), (
        "templates/task.md final-gate line dropped the factory-executed-for-an-armed-repo fact"
    )
    assert re.search(r"human", gate_line, re.IGNORECASE), (
        "templates/task.md final-gate line dropped the human-merge fallback fact"
    )


# ---------------------------------------------------------------------------
# skills/factory/references/onboarding.md — the two false "worktree shares
# built deps" lines removed/corrected; the PATH-injection statement stays
# ---------------------------------------------------------------------------

def test_onboarding_md_drops_worktree_shares_built_deps_claim():
    text = _text(ONBOARDING)
    assert "worktree shares the repo's built deps" not in text, (
        "onboarding.md still claims the worktree shares the repo's built deps via the "
        "normal git worktree mechanism — false, .venv/node_modules are gitignored and "
        "the worktree carries neither"
    )


def test_onboarding_md_path_injection_statement_stays():
    text = _text(ONBOARDING)
    assert re.search(
        r"runs `check_cmd` with `\.venv/bin` and `node_modules/\.bin` on PATH",
        text,
    ), (
        "onboarding.md dropped the correct PATH-injection statement (was already "
        "correct and out of scope for this fix)"
    )


def test_onboarding_md_built_deps_step_states_base_checkout_truth():
    text = _text(ONBOARDING)
    step3_match = re.search(
        r"### 3\. Ensure built deps exist\n(.*?)\n###", text, re.DOTALL
    )
    assert step3_match, "onboarding.md is missing its 'Ensure built deps exist' step"
    step3 = step3_match.group(1)
    assert re.search(r"base checkout", step3, re.IGNORECASE), (
        "onboarding.md built-deps step dropped the base-checkout-is-where-deps-live fact"
    )
    assert re.search(r"gitignored", step3, re.IGNORECASE), (
        "onboarding.md built-deps step dropped the gitignored fact that makes the "
        "old worktree-sharing claim false"
    )


# ---------------------------------------------------------------------------
# Phantom RFC 0006 — two citations stripped, surviving sentence truth kept
# ---------------------------------------------------------------------------

def test_no_phantom_rfc_0006_anywhere_named():
    result = subprocess.run(
        ["grep", "-rn", "RFC 0006", "README.md", "deploy/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and not result.stdout.strip(), (
        f"phantom RFC 0006 citation(s) still present:\n{result.stdout}"
    )


def test_dispatch_env_example_drops_phantom_rfc_0006():
    text = _text(DISPATCH_ENV_EXAMPLE)
    assert "RFC 0006" not in text, (
        "deploy/dispatch.env.example still cites the phantom RFC 0006"
    )
    assert re.search(r"fail.closed", text, re.IGNORECASE), (
        "deploy/dispatch.env.example lost the surviving 'dispatch is fail-closed' "
        "truth when RFC 0006 was stripped"
    )


# ---------------------------------------------------------------------------
# AGENTS.md repo map — completed with the named tool/dir rows
# ---------------------------------------------------------------------------

def _agents_repo_map_section():
    text = _text(AGENTS)
    match = re.search(r"## Repo map\n(.*?)\n---", text, re.DOTALL)
    assert match, "AGENTS.md is missing a '## Repo map' section"
    return match.group(1)


def test_agents_md_repo_map_lists_every_named_addition():
    section = _agents_repo_map_section()
    for path in [
        "tools/epic_gate.py",
        "tools/review_bundle.py",
        "tools/check_task.py",
        "tools/check_links.py",
        "tools/check_model_refs.py",
        "tools/check_supersession.py",
        "tools/promote.sh",
        "tools/watch_build.sh",
        "tools/board.sh",
        "skills/",
        "templates/",
    ]:
        assert path in section, f"AGENTS.md repo map is missing {path!r}"
