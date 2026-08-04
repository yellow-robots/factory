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
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.textutil import is_frozen_bench_evidence
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
DISPATCH_MD = ROOT / "deploy" / "DISPATCH.md"
DISPATCH_ENV_EXAMPLE = ROOT / "deploy" / "dispatch.env.example"
CLOSING = ROOT / "skills" / "factory" / "references" / "closing.md"
ONBOARDING = ROOT / "skills" / "factory" / "references" / "onboarding.md"
TASK_TEMPLATE = ROOT / "skills" / "factory" / "templates" / "task.md"
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


def _readme_has_test_count_claim(text):
    return re.search(r"\b\d+ tests green\b", text) is not None


def test_readme_has_no_hand_maintained_test_count_claim():
    """Declared guard inversion (debt round 2, item D — issue #383): this test
    replaces test_readme_test_count_is_not_the_stale_63, which used to require
    a '<N> tests green' claim to exist and floored it above 63. A
    hand-maintained count is the defect — it drifted twice (63, then 1129) —
    so the new expectation is that README.md carries no such claim at all,
    never a fresh number correcting the old one. This is the wall-11
    micro-guard for the README rider (skills/factory/references/debt-rounds.md,
    wall 11); the floor assertion it replaces retires with the claim it
    floored.

    Surface read: README.md, the whole file — the claim has no fixed section
    to scope a narrower guard to.
    """
    text = _text(README)
    assert not _readme_has_test_count_claim(text), (
        "README.md still carries a hand-maintained '<N> tests green' claim — "
        "removed at debt round 2 item D (issue #383), not to be replaced with "
        "a fresh number"
    )


def test_readme_test_count_claim_detector_flags_a_count_claim_positive_case():
    """Positive case for the detector above: a README-shaped string carrying a
    count claim must be flagged, proving the guard would actually catch a
    regression rather than vacuously passing."""
    assert _readme_has_test_count_claim("... reads that repo's build config ... 1129 tests green.")
    assert _readme_has_test_count_claim("42 tests green")
    assert not _readme_has_test_count_claim("reads that repo's build config from a per-repo file.")


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


def _md_and_py_files(root=ROOT):
    for path in list(root.rglob("*.md")) + list(root.rglob("*.py")):
        if ".git" in path.parts:
            continue
        if path == pathlib.Path(__file__):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if is_frozen_bench_evidence(rel):
            continue  # frozen bench evidence embeds history verbatim by design — not living text
        yield path


def test_no_other_reference_to_templates_readme_survives():
    offenders = []
    for path in _md_and_py_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "templates/README.md" in content:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"deleted templates/README.md is still referenced by: {offenders}"
    )


# --- issue #194: frozen bench evidence excluded from this walker's living-text scan ---
#
# This guard is latent against today's records (they are .json, and _md_and_py_files only globs
# *.md/*.py) but a future dated report (.md, under bench/reports/) quoting an offending path would
# trip it — proven here structurally via the same helper the real-tree test above consults.

def test_md_and_py_files_skips_a_dated_report_quoting_the_offending_path(tmp_path):
    report = tmp_path / "bench" / "reports" / "2026-07-15-report.md"
    report.parent.mkdir(parents=True)
    report.write_text("attended run notes quote templates/README.md verbatim\n", encoding="utf-8")

    found = {str(p.relative_to(tmp_path)).replace("\\", "/") for p in _md_and_py_files(root=tmp_path)}
    assert "bench/reports/2026-07-15-report.md" not in found


def test_md_and_py_files_still_yields_bench_corpus_readme_and_non_bench_files(tmp_path):
    readme = tmp_path / "bench" / "corpus" / "README.md"
    readme.parent.mkdir(parents=True)
    readme.write_text("templates/README.md is still discussed here\n", encoding="utf-8")

    outside = tmp_path / "docs" / "note.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("templates/README.md still shows up here\n", encoding="utf-8")

    found = {str(p.relative_to(tmp_path)).replace("\\", "/") for p in _md_and_py_files(root=tmp_path)}
    assert "bench/corpus/README.md" in found
    assert "docs/note.md" in found


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


def _tracked_tools_paths():
    """Every path git tracks under tools/ — the map's tools/ half is derived from
    this rather than pinned, so a newly added tools/ file fails the guard below
    until AGENTS.md's Repo map names it (issue #383). Follows the same
    subprocess.run(["git", "ls-files", "tools/"]) pattern already used by
    tests/test_readme_public_audience.py::test_whats_here_covers_every_tracked_top_level_tool."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "tools/"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert tracked, "git ls-files tools/ returned nothing — repo checkout looks wrong"
    return tracked


def _missing_tools_paths(section, tracked_paths):
    return [path for path in tracked_paths if path not in section]


def test_agents_md_repo_map_lists_every_tracked_tools_path():
    section = _agents_repo_map_section()
    missing = _missing_tools_paths(section, _tracked_tools_paths())
    assert not missing, (
        f"AGENTS.md repo map is missing these git-tracked tools/ paths: {missing!r}"
    )


def test_agents_md_repo_map_derivation_is_live_against_the_tracked_tree():
    """Proves the derivation above is live, not a re-pinned list in disguise:
    dropping one tracked tools/ path from a synthetic map section must surface
    exactly that path as missing, the same way a real newly added tools/ file
    would fail the guard until AGENTS.md names it."""
    tracked = _tracked_tools_paths()
    dropped = tracked[0]
    fake_section = "\n".join(f"| `{path}` | ... |" for path in tracked[1:])
    assert _missing_tools_paths(fake_section, tracked) == [dropped]


def test_agents_md_repo_map_lists_every_named_non_tools_addition():
    # Tombstone for the pre-#383 hardcoded list (issue #178, #383): these
    # entries are not git-derivable the way tools/ is, so they stay pinned.
    section = _agents_repo_map_section()
    for path in [
        "skills/",
        "templates/",
    ]:
        assert path in section, f"AGENTS.md repo map is missing {path!r}"
