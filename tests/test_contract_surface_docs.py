"""
Tests for issue #276 — contract surface: invariants written, keys taught, the debt reframe landed
(technical-rfc yellow-robots/factory#271 epic, slice 5 — docs only).

Derived from the issue #276 acceptance criteria (the spec), not from the doc-editor's own prose:
the goal is that every census disposition from slices 2-4 (test_paths/artifact_globs, issue #273;
server_ci, issue #274; check_cmd required, issue #275) lives on the shipped contract surface, so a
cold agent can derive the resolving declaration from the record plus the plugin reference docs
alone. These tests check that:

  1. onboarding.md documents `test_paths`, `artifact_globs`, `server_ci` as declarable keys (a repo
     declares its own shape, never conforms to the factory's), and `check_cmd` as required, its
     absence bouncing legibly.
  2. onboarding.md names the four written invariants, one sentence each: squash merges with
     single-commit PRs; branch layout `task/<issue>-<slug>` on remote `origin`; checkout convention
     `$YR_WORKSPACE/<name>`; the check child runs with no git identity.
  3. pipeline.md's ci_green model section carries the declared-stance vocabulary and record fields,
     and its boundary-guard section carries the declared surface and its source.
  4. debt-rounds.md states a round is the home for refactoring code built with partial
     understanding, not only deletion.
  5. AGENTS.md's manifest conventions line names the three new keys and check_cmd's required status.
  6. tools/check_model_refs.py stays green on the live tree.

Cross-checked, where possible, against the shipped source (tools/dev-runner.sh's TEST_PATHS /
ARTIFACT_GLOBS / read_server_ci defaults) rather than against the doc-editor's own wording, so a
doc that drifts from the actual shipped default fails here.

Runs under `.venv/bin/python -m pytest tests/ -q`.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_model_refs import main as check_model_refs_main

REFS = ROOT / "skills" / "factory" / "references"
ONBOARDING = REFS / "onboarding.md"
PIPELINE = REFS / "pipeline.md"
DEBT_ROUNDS = REFS / "debt-rounds.md"
AGENTS = ROOT / "AGENTS.md"
DEV_RUNNER = ROOT / "tools" / "dev-runner.sh"


def _text(path):
    return path.read_text(encoding="utf-8")


def _onboarding():
    return _text(ONBOARDING)


def _pipeline():
    return _text(PIPELINE)


def _agents():
    return _text(AGENTS)


# ---------------------------------------------------------------------------
# AC1 — onboarding.md: test_paths / artifact_globs / server_ci as declarable keys,
#       check_cmd as required
# ---------------------------------------------------------------------------

def test_onboarding_documents_test_paths_key_and_default():
    text = _onboarding()
    assert "`test_paths`" in text or "test_paths" in text, \
        "onboarding.md does not name the test_paths manifest key"
    assert '["tests/"]' in text, \
        "onboarding.md does not state test_paths' default (['tests/'])"


def test_onboarding_documents_artifact_globs_key_and_default():
    text = _onboarding()
    assert "artifact_globs" in text, \
        "onboarding.md does not name the artifact_globs manifest key"
    assert "__pycache__/" in text and "*.pyc" in text, \
        "onboarding.md does not state artifact_globs' default (__pycache__/, *.pyc)"


def test_onboarding_documents_server_ci_key_and_default():
    text = _onboarding()
    assert "server_ci" in text, \
        "onboarding.md does not name the server_ci manifest key"
    lower = text.lower()
    assert "required" in lower and "none" in lower, \
        "onboarding.md does not name both server_ci values (required/none)"


def test_onboarding_three_keys_declare_own_shape_not_conform_to_factorys():
    """AC: 'declare the repo's shape, never conform to the factory's'."""
    lower = _onboarding().lower()
    assert "declare" in lower and "own shape" in lower, \
        "onboarding.md does not frame test_paths/artifact_globs/server_ci as declaring the repo's own shape"
    assert "conform" in lower, \
        "onboarding.md does not contrast declaring the repo's shape against conforming to the factory's own"


def test_onboarding_states_check_cmd_is_required():
    text = _onboarding()
    lower = text.lower()
    assert "check_cmd" in text and "required" in lower, \
        "onboarding.md does not state check_cmd is required"


def test_onboarding_states_check_cmd_absence_bounces_legibly():
    """AC: check_cmd's absence bounces legibly — Backlog + Needs-info, naming the missing key,
    before claim/worktree/any stage runs."""
    lower = _onboarding().lower()
    assert "backlog" in lower and "needs-info" in lower, \
        "onboarding.md does not state an undeclared check_cmd bounces to Backlog + Needs-info"
    assert "naming the missing key" in lower or "missing key" in lower, \
        "onboarding.md does not state the bounce names the missing key"
    assert "before claim" in lower or "claim/worktree" in lower, \
        "onboarding.md does not state the bounce happens before claim/worktree/any stage"


def test_onboarding_states_check_cmd_env_override_does_not_rescue_undeclared_key():
    lower = _onboarding().lower()
    assert "environment `check_cmd`" in lower or "an environment `check_cmd`" in lower or \
        "env check_cmd" in lower or "environment `check_cmd` overrides" in lower, \
        "onboarding.md does not describe env CHECK_CMD's relationship to a declared check_cmd"
    assert "never substitutes for declaring one" in lower or "never substitute" in lower or \
        "does not rescue" in lower or "does not substitute" in lower, \
        "onboarding.md does not state an env CHECK_CMD never substitutes for declaring the key"


# ---------------------------------------------------------------------------
# AC2 — onboarding.md: the four written invariants, one sentence each
# ---------------------------------------------------------------------------

def test_onboarding_has_written_invariants_section():
    text = _onboarding()
    assert re.search(r"^#+.*written invariant", text, re.IGNORECASE | re.MULTILINE), \
        "onboarding.md has no heading naming the written invariants"


def test_onboarding_states_squash_merge_single_commit_invariant():
    lower = _onboarding().lower()
    assert "squash" in lower, \
        "onboarding.md does not name the squash-merge invariant"
    assert "single-commit" in lower or "single commit" in lower, \
        "onboarding.md does not tie the squash-merge invariant to single-commit PRs"


def test_onboarding_states_branch_layout_invariant():
    text = _onboarding()
    assert "task/<issue" in text or "task/<issue#>-<slug>" in text or "task/<issue>-<slug>" in text, \
        "onboarding.md does not name the task/<issue>-<slug> branch layout"
    assert "`origin`" in text or "origin remote" in text.lower(), \
        "onboarding.md does not name the origin remote for the branch layout invariant"


def test_onboarding_states_checkout_convention_invariant():
    text = _onboarding()
    assert "$YR_WORKSPACE/<name>" in text or "$YR_WORKSPACE" in text, \
        "onboarding.md does not name the $YR_WORKSPACE/<name> checkout convention"


def test_onboarding_states_check_child_no_git_identity_invariant():
    text = _onboarding()
    lower = text.lower()
    assert "git_config_global" in lower and "git_config_system" in lower, \
        "onboarding.md does not name GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM in the no-git-identity invariant"
    assert "no git identity" in lower or "/dev/null" in text, \
        "onboarding.md does not state the check child runs with no git identity"
    assert "fixtures" in lower or "its own" in lower, \
        "onboarding.md does not state a check needing a git identity must set one up itself"


def test_onboarding_written_invariants_are_not_manifest_keys():
    """AC framing: these four are written invariants a repo must meet, distinct from the manifest
    keys documented above them — every registered repo must meet them as given."""
    text = _onboarding()
    heading_idx = text.lower().find("## the written invariants")
    assert heading_idx != -1, "onboarding.md has no '## The written invariants' heading"
    para = text[heading_idx: heading_idx + 400].lower()
    assert "not manifest keys" in para or "not a manifest key" in para, \
        "onboarding.md does not distinguish the written invariants from declarable manifest keys"


# ---------------------------------------------------------------------------
# AC3 — pipeline.md: ci_green model gains declared-stance vocabulary + record fields;
#       boundary-guard section gains declared surface + source
# ---------------------------------------------------------------------------

def _ci_green_section():
    text = _pipeline()
    start = text.index("## The ci_green model")
    nxt = text.find("\n## ", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


def _boundary_guard_section():
    text = _pipeline()
    start = text.index("## The legal test tree")
    nxt = text.find("\n## ", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


def test_pipeline_ci_green_model_names_server_ci_key_and_values():
    section = _ci_green_section().lower()
    assert "server_ci" in section, \
        "pipeline.md's ci_green model does not name the server_ci manifest key"
    assert "`required`" in section or "required" in section, \
        "pipeline.md's ci_green model does not name the 'required' server_ci value"
    assert "`none`" in section or "\"none\"" in section or "'none'" in section, \
        "pipeline.md's ci_green model does not name the 'none' server_ci value"


def test_pipeline_ci_green_model_names_not_required_declared_state():
    section = _ci_green_section()
    assert "not_required_declared" in section, \
        "pipeline.md's ci_green model does not name the not_required_declared check_rollup state"


def test_pipeline_ci_green_model_names_server_ci_invalid_state():
    section = _ci_green_section()
    assert "server_ci_invalid" in section, \
        "pipeline.md's ci_green model does not name the server_ci_invalid check_rollup state"


def test_pipeline_ci_green_model_check_rollup_table_has_both_new_rows():
    text = _pipeline()
    for value in ("not_required_declared", "server_ci_invalid"):
        pattern = re.compile(rf"`{re.escape(value)}`\s*\|\s*(.+?)\s*\|")
        match = pattern.search(text)
        assert match, f"pipeline.md's check_rollup table has no row for `{value}`"
        assert len(match.group(1).strip()) > 10, \
            f"pipeline.md's check_rollup table row for `{value}` gives no real meaning"


def test_pipeline_ci_green_model_names_armed_conflict_wall():
    section = _ci_green_section()
    assert "server_ci_none_armed" in section, \
        "pipeline.md's ci_green model does not name the server_ci_none_armed arming-wall state"
    lower = section.lower()
    assert "auto_merge" in lower, \
        "pipeline.md's ci_green model does not tie the armed-conflict wall to auto_merge"


def test_pipeline_ci_green_model_names_record_fields():
    """AC: the record fields the declared-stance vocabulary carries."""
    section = _ci_green_section()
    for field in ("server_ci", "server_ci_source", "server_ci_rejected"):
        assert field in section, \
            f"pipeline.md's ci_green model does not name the record field {field}"


def test_pipeline_ci_green_model_names_source_vocabulary():
    section = _ci_green_section().lower()
    assert "manifest" in section and "default" in section, \
        "pipeline.md's ci_green model does not name the server_ci_source vocabulary (manifest|default)"


def test_pipeline_boundary_guard_names_test_paths_and_artifact_globs():
    section = _boundary_guard_section()
    assert "test_paths" in section, \
        "pipeline.md's boundary-guard section does not name the test_paths manifest key"
    assert "artifact_globs" in section, \
        "pipeline.md's boundary-guard section does not name the artifact_globs manifest key"


def test_pipeline_boundary_guard_names_declared_surface_and_source():
    section = _boundary_guard_section().lower()
    assert "declared" in section, \
        "pipeline.md's boundary-guard section does not name the declared test surface"
    assert "manifest" in section and "default" in section, \
        "pipeline.md's boundary-guard section does not name the source vocabulary (manifest|default)"


def test_pipeline_boundary_guard_states_block_message_names_surface_and_source():
    section = _boundary_guard_section().lower()
    assert "block" in section and "surface" in section and "source" in section, \
        "pipeline.md's boundary-guard section does not state the block message names the resolved surface and its source"


# ---------------------------------------------------------------------------
# AC4 — debt-rounds.md: a round is the home for refactoring partial-understanding code,
#       not only deletion
# ---------------------------------------------------------------------------

def test_debt_rounds_states_home_for_refactoring_partial_understanding_not_only_deletion():
    lower = _text(DEBT_ROUNDS).lower()
    assert "partial" in lower and "understanding" in lower, \
        "debt-rounds.md does not name partial understanding as a round's subject matter"
    assert "refactor" in lower, \
        "debt-rounds.md does not state a round refactors code, not only removes it"
    assert "not only" in lower, \
        "debt-rounds.md does not state deletion is not the round's only home"


# ---------------------------------------------------------------------------
# AC5 — AGENTS.md's manifest conventions line names the three new keys +
#       check_cmd's required status
# ---------------------------------------------------------------------------

def _agents_manifest_bullet():
    text = _agents()
    idx = text.index("**Workspace & manifest:**")
    nxt = text.find("\n- **", idx + 1)
    return text[idx:] if nxt == -1 else text[idx:nxt]


def test_agents_md_manifest_bullet_names_test_paths_and_artifact_globs():
    bullet = _agents_manifest_bullet()
    assert "test_paths" in bullet, \
        "AGENTS.md's manifest conventions bullet does not name test_paths"
    assert "artifact_globs" in bullet, \
        "AGENTS.md's manifest conventions bullet does not name artifact_globs"


def test_agents_md_manifest_bullet_names_server_ci():
    bullet = _agents_manifest_bullet()
    assert "server_ci" in bullet, \
        "AGENTS.md's manifest conventions bullet does not name server_ci"


def test_agents_md_manifest_bullet_states_check_cmd_required():
    bullet = _agents_manifest_bullet()
    assert "`check_cmd` is **required**" in bullet or "check_cmd` is **required**" in bullet or \
        ("check_cmd" in bullet and "required" in bullet.lower()), \
        "AGENTS.md's manifest conventions bullet does not state check_cmd is required"


def test_agents_md_manifest_bullet_still_names_original_keys():
    """Regression guard: the bullet grows, it doesn't replace the pre-existing keys."""
    bullet = _agents_manifest_bullet()
    for key in ("check_cmd", "model", "base_ref", "auto_merge", "merge_ci_timeout"):
        assert key in bullet, \
            f"AGENTS.md's manifest conventions bullet dropped the pre-existing key {key}"


# ---------------------------------------------------------------------------
# Docs match the shipped code (slices 2-4), not just each other
# ---------------------------------------------------------------------------

def _dev_runner_text():
    return _text(DEV_RUNNER)


def test_documented_test_paths_default_matches_shipped_source():
    runner = _dev_runner_text()
    assert 'TEST_PATHS=("tests/")' in runner, \
        "tools/dev-runner.sh's TEST_PATHS default has moved — re-check onboarding.md/pipeline.md against it"
    assert '["tests/"]' in _onboarding()
    assert '["tests/"]' in _pipeline()


def test_documented_artifact_globs_default_matches_shipped_source():
    runner = _dev_runner_text()
    assert 'ARTIFACT_GLOBS=("__pycache__/" "*.pyc")' in runner, \
        "tools/dev-runner.sh's ARTIFACT_GLOBS default has moved — re-check onboarding.md/pipeline.md against it"
    for doc in (_onboarding(), _pipeline()):
        assert "__pycache__/" in doc and "*.pyc" in doc


def test_documented_server_ci_default_matches_shipped_source():
    runner = _dev_runner_text()
    assert "SERVER_CI=required; SERVER_CI_SOURCE=default" in runner, \
        "tools/dev-runner.sh's server_ci default has moved — re-check onboarding.md/pipeline.md against it"


def test_documented_check_cmd_required_matches_shipped_source():
    runner = _dev_runner_text()
    assert "check_cmd" in runner and "is not declared" in runner, \
        "tools/dev-runner.sh no longer states an undeclared check_cmd bounce — re-check onboarding.md/AGENTS.md against it"
    assert "-m pytest" not in runner and "pytest tests/" not in runner, \
        "tools/dev-runner.sh appears to have regained a built-in pytest fallback, contradicting the required-check_cmd docs"


# ---------------------------------------------------------------------------
# AC6 — tools/check_model_refs.py stays green
# ---------------------------------------------------------------------------

def test_check_model_refs_gate_is_green_on_the_live_tree():
    assert check_model_refs_main(["--scan-root", str(ROOT)]) == 0, \
        "tools/check_model_refs.py is not green against the live tree after the #276 doc edits"


def test_check_model_refs_own_suite_passes():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_check_model_refs.py", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"tests/test_check_model_refs.py is not green:\n{result.stdout}\n{result.stderr}"

