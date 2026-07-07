"""
Tests for Issue #52 — Operating-doc consolidation: each fact lives once.

Derived from the Issue #52 acceptance criteria (the spec), not from the
implementation. The task rewrites AGENTS.md (and lets CLAUDE.md stay a thin
import of it) so the combined pair is at most 6,400 bytes, with every fact
from the pre-consolidation doc kept at exactly one surviving authoritative
home, reworded or not.

The existing doc-pin suite already anchors the pipeline diagram's opening
line and the "human sets Status = Ready" annotation, the paragraph
immediately following the diagram, the state-machine "-> Ready" row, the
human-veto/merge language, and the model-surface phrases (model surface,
review_model, build_model, hard_model, retire, convention record) — see
test_input_gate_invariant_granularity.py and test_dev_runner_roles.py. This
file adds the acceptance-criteria facts those pins don't already cover:
every invariant in the Invariants section, the full diagram (not just its
Ready line), the repo map, and the conventions (branches, check command,
authoring-model commit rule, workspace & manifest precedence) — plus a check
that CLAUDE.md stays an import, not a second home for the same facts.

No test here pins the combined byte size: that bar is this task's
acceptance criterion, judged at review, and pinning it in the suite would
forbid legitimate future growth of the docs.
"""

import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
CLAUDE = ROOT / "CLAUDE.md"


def _agents_text():
    return AGENTS.read_text(encoding="utf-8")


def _claude_text():
    return CLAUDE.read_text(encoding="utf-8")


def _section(heading):
    text = _agents_text()
    match = re.search(rf"## {heading}.*?\n(.*?)\n---", text, re.DOTALL)
    assert match, f"AGENTS.md is missing a '## {heading}' section"
    return match.group(1)


def _invariants_section():
    return _section("Invariants")


def _repo_map_section():
    return _section("Repo map")


def _conventions_section():
    return _section("Conventions")


def _diagram_block():
    text = _agents_text()
    match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
    assert match, "AGENTS.md is missing the fenced pipeline diagram"
    return match.group(1)


# ---------------------------------------------------------------------------
# The operating-model diagram carries every stage, not just its Ready line
# ---------------------------------------------------------------------------

def test_diagram_covers_every_pipeline_stage():
    block = _diagram_block()
    assert re.search(r"file a Task", block, re.IGNORECASE), \
        "pipeline diagram dropped the 'file a Task' stage"
    assert re.search(r"human sets Status = Ready", block), \
        "pipeline diagram dropped the 'human sets Status = Ready' line"
    assert re.search(r"n8n poll", block, re.IGNORECASE), \
        "pipeline diagram dropped the n8n poll stage"
    assert re.search(r"dev-runner", block, re.IGNORECASE), \
        "pipeline diagram dropped the dev-runner handoff"
    assert re.search(r"implement", block, re.IGNORECASE) and \
        re.search(r"review", block, re.IGNORECASE), \
        "pipeline diagram dropped the implement/test/check/review stages"
    assert re.search(r"merge", block, re.IGNORECASE), \
        "pipeline diagram dropped the merge stage"
    assert re.search(r"native close", block, re.IGNORECASE), \
        "pipeline diagram dropped the native-close stage"
    assert re.search(r"Status = Done", block), \
        "pipeline diagram dropped the terminal 'Status = Done' state"


# ---------------------------------------------------------------------------
# Every invariant from the Invariants section must survive, reworded or not
# ---------------------------------------------------------------------------

def test_invariant_builder_not_verifier_survives():
    section = _invariants_section()
    assert re.search(r"builder.{0,5}verifier", section, re.IGNORECASE), \
        "AGENTS.md dropped the builder != verifier invariant"
    assert re.search(r"independent cold process", section, re.IGNORECASE), \
        "AGENTS.md dropped the independent-cold-process phrasing for builder != verifier"


def test_invariant_confinement_is_environment_survives():
    section = _invariants_section()
    assert re.search(r"confinement", section, re.IGNORECASE), \
        "AGENTS.md dropped the confinement-is-the-environment invariant"
    assert re.search(r"bypasspermissions", section, re.IGNORECASE), \
        "AGENTS.md dropped the bypassPermissions justification for the confinement invariant"


def test_invariant_native_primitives_survives():
    section = _invariants_section()
    assert re.search(r"native primitives", section, re.IGNORECASE), \
        "AGENTS.md dropped the native-primitives-over-sidecars invariant"
    assert re.search(r"sub-issues", section, re.IGNORECASE), \
        "AGENTS.md native-primitives invariant dropped the sub-issues example"


def test_invariant_deterministic_gates_survives():
    section = _invariants_section()
    assert re.search(r"deterministic gates", section, re.IGNORECASE), \
        "AGENTS.md dropped the deterministic-gates-dispose invariant"
    assert re.search(r"check_cmd|check command", section, re.IGNORECASE), \
        "AGENTS.md deterministic-gates invariant dropped the check-command example"


def test_invariant_repo_agnostic_survives():
    section = _invariants_section()
    assert re.search(r"repo.agnostic", section, re.IGNORECASE), \
        "AGENTS.md dropped the repo-agnostic invariant"
    assert re.search(r"no product holds a copy|holds no copy", section, re.IGNORECASE), \
        "AGENTS.md repo-agnostic invariant dropped the 'no product holds a copy' clause"


def test_invariant_builds_from_git_refs_survives():
    section = _invariants_section()
    assert re.search(r"git refs", section, re.IGNORECASE), \
        "AGENTS.md dropped the builds-from-git-refs invariant"
    assert re.search(r"origin/main", section), \
        "AGENTS.md git-refs invariant dropped the origin/main anchor"
    assert re.search(r"working tree", section, re.IGNORECASE), \
        "AGENTS.md git-refs invariant dropped the mutable-working-tree contrast"


def test_invariant_one_task_one_pr_survives():
    section = _invariants_section()
    assert re.search(r"one task.{0,5}one PR", section, re.IGNORECASE), \
        "AGENTS.md dropped the one-task-equals-one-PR invariant"
    assert re.search(r"split", section, re.IGNORECASE), \
        "AGENTS.md one-task-one-PR invariant dropped the split-into-sub-issues guidance"


def test_invariant_docs_consolidated_not_accreted_survives():
    section = _invariants_section()
    assert re.search(r"consolidated", section, re.IGNORECASE), \
        "AGENTS.md dropped the docs-are-consolidated invariant"
    assert re.search(r"accrete", section, re.IGNORECASE), \
        "AGENTS.md consolidated-docs invariant dropped the not-accreted contrast"


# ---------------------------------------------------------------------------
# Repo map — every path from the pre-consolidation table must survive
# ---------------------------------------------------------------------------

def test_repo_map_lists_every_core_path():
    section = _repo_map_section()
    for path in [
        "tools/dev-runner.sh",
        "tools/merge_shadow.py",
        "tools/dispatch.py",
        "tools/stage_usage.py",
        "tools/textutil.py",
        "models.toml",
        "tools/registry.py",
        "tests/",
        "deploy/",
        "docs/rfcs/",
    ]:
        assert path in section, f"AGENTS.md repo map is missing {path!r}"


# ---------------------------------------------------------------------------
# Conventions — branches, check command, authoring-model commit rule,
# workspace & manifest precedence
# ---------------------------------------------------------------------------

def test_conventions_branch_naming_survives():
    section = _conventions_section()
    assert "task/<issue#>-<slug>" in section, \
        "AGENTS.md Conventions dropped the branch-naming convention"


def test_conventions_check_command_survives():
    section = _conventions_section()
    assert ".venv/bin/python -m pytest tests/ -q" in section, \
        "AGENTS.md Conventions dropped the factory's own check command"


def test_conventions_workspace_and_manifest_precedence_survives():
    section = _conventions_section()
    assert "YR_WORKSPACE" in section, \
        "AGENTS.md Conventions dropped the YR_WORKSPACE workspace-resolution fact"
    assert ".yr/factory.toml" in section, \
        "AGENTS.md Conventions dropped the .yr/factory.toml manifest reference"
    assert re.search(r"check_cmd", section), \
        "AGENTS.md Conventions dropped the manifest's check_cmd field"
    assert re.search(r"base_ref", section), \
        "AGENTS.md Conventions dropped the manifest's base_ref field"
    assert re.search(r"auto_merge", section), \
        "AGENTS.md Conventions dropped the manifest's auto_merge field"
    assert re.search(r"default false", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped auto_merge's false default"
    assert re.search(r"env.{0,10}manifest.{0,10}default", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the env > manifest > default precedence order"
    assert re.search(r"decision time", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the auto_merge-re-reads-at-decision-time fact"


def test_conventions_sentinel_killswitch_survives():
    section = _conventions_section()
    assert re.search(r"sentinel", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the sentinel kill-switch fact"
    assert re.search(r"kill switch", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the 'kill switch' phrasing for the sentinel"


def test_conventions_authoring_model_commit_rule_survives():
    section = _conventions_section()
    assert re.search(r"authoring model", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the authoring-model commit-credit rule"
    assert re.search(r"dev-runner", section) and re.search(r"model-id", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the runner's 'dev-runner, <model-id>' commit-body stamp"
    assert "Co-Authored-By" in section, \
        "AGENTS.md Conventions dropped the attended-commit Co-Authored-By trailer"


def test_conventions_auth_is_human_work_survives():
    section = _conventions_section()
    assert re.search(r"auth is human work", section, re.IGNORECASE), \
        "AGENTS.md Conventions dropped the 'auth is human work' rule"


# ---------------------------------------------------------------------------
# CLAUDE.md imports AGENTS.md rather than duplicating any of its sections —
# each fact lives once, and CLAUDE.md is not a second home for it
# ---------------------------------------------------------------------------

def test_claude_md_imports_agents_md():
    text = _claude_text()
    assert "@AGENTS.md" in text, \
        "CLAUDE.md no longer imports AGENTS.md"


def test_claude_md_does_not_duplicate_agents_md_sections():
    text = _claude_text()
    for heading in ["## Invariants", "## Repo map", "## Conventions", "## RFC index",
                     "## The operating model", "## Task lifecycle", "## How a change is built"]:
        assert heading not in text, \
            f"CLAUDE.md duplicates the {heading!r} section instead of relying on the AGENTS.md import"
