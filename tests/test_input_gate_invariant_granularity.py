"""
Tests for Issue #19 — Reword the input-gate invariant at its true granularity
in the factory docs and skill (patch release 0.6.2).

Derived from the Issue #19 acceptance criteria (the spec), not from the
implementation internals. These check that AGENTS.md and skills/factory/
SKILL.md state the input-gate invariant at design-artifact granularity —
authority lives at the design artifacts (`active`); flipping a governed
epic Ready, promoting its next slice, and closing a finished epic are
mechanical under a standing approval, fail-closed to the human on doubt;
a standalone task with no governing design keeps per-task human
promotion; the cord-pull (un-Readying an epic) remains the human veto;
and the merge gate / other invariants are unchanged.
"""

import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"


def _agents_text():
    return AGENTS.read_text(encoding="utf-8")


def _skill_text():
    return SKILL.read_text(encoding="utf-8")


def _plugin_data():
    return json.loads(PLUGIN.read_text(encoding="utf-8"))


def _skill_description():
    """Extract SKILL.md frontmatter description, handling YAML >- block scalar."""
    lines = _skill_text().split("\n")
    in_fm = False
    in_desc_block = False
    desc_lines = []
    for line in lines:
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if not in_fm:
            continue
        if line.startswith("description:"):
            rest = line[len("description:"):].strip()
            if rest in (">-", ">", "|", "|-"):
                in_desc_block = True
                continue
            desc_lines.append(rest.strip('"'))
            continue
        if in_desc_block:
            if line.startswith("  ") or line.startswith("\t"):
                desc_lines.append(line.strip())
            else:
                in_desc_block = False
    return " ".join(desc_lines).strip()


def _input_gate_bullet():
    """Pull the 'human owns the input gate' bullet out of SKILL.md's Invariants section."""
    text = _skill_text()
    match = re.search(
        r"^-\s+\*\*The human owns the \*input\* gate\.\*\*.*$", text, re.MULTILINE
    )
    assert match, "SKILL.md is missing the 'The human owns the *input* gate.' invariant bullet"
    return match.group(0)


def _agents_input_gate_paragraph():
    """Pull the paragraph in AGENTS.md that states the human input/output gates,
    identified by proximity to the pipeline diagram rather than exact old wording."""
    text = _agents_text()
    match = re.search(
        r"```\n\n(.*?)\n\n### Task lifecycle", text, re.DOTALL
    )
    assert match, "AGENTS.md is missing the paragraph following the pipeline diagram"
    return match.group(1)


def _ready_transition_row():
    text = _agents_text()
    match = re.search(r"^\|\s*→ Ready\s*\|.*$", text, re.MULTILINE)
    assert match, "AGENTS.md state-machine table is missing the '→ Ready' row"
    return match.group(0)


# ---------------------------------------------------------------------------
# AGENTS.md — input gate reworded at design-artifact granularity
# ---------------------------------------------------------------------------

def test_agents_md_ties_input_gate_to_design_artifacts():
    para = _agents_input_gate_paragraph()
    assert re.search(r"design artifact", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not mention design artifacts"
    assert re.search(r"`active`", para), \
        "AGENTS.md input-gate paragraph does not mention setting a design `active`"
    assert re.search(r"product-spec|feature-rfc", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not name product-spec/feature-rfc as the design artifact"


def test_agents_md_makes_epic_promotion_mechanical_under_standing_approval():
    para = _agents_input_gate_paragraph()
    assert re.search(r"mechanical", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not call epic-slice promotion mechanical"
    assert re.search(r"standing approval", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not name the standing-approval basis for mechanical promotion"
    assert re.search(r"epic", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not mention epics"
    assert re.search(r"slice", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not mention slice promotion"
    assert re.search(r"clos\w*", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not mention closing a finished epic"


def test_agents_md_is_fail_closed_on_doubt():
    para = _agents_input_gate_paragraph()
    assert re.search(r"fail.closed", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not state the mechanical path is fail-closed"
    assert re.search(r"doubt|needs.info", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not describe falling back to the human on doubt"


def test_agents_md_retains_the_cord_pull_veto():
    para = _agents_input_gate_paragraph()
    assert re.search(r"un.?read", para, re.IGNORECASE) or re.search(r"veto", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not retain the un-Ready / veto language"


def test_agents_md_keeps_standalone_task_promotion_human():
    para = _agents_input_gate_paragraph()
    assert re.search(r"standalone task", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not carve out standalone tasks"
    assert re.search(r"human promotion|human touch", para, re.IGNORECASE) or \
        re.search(r"per-task human", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph does not say standalone tasks keep human promotion"


def test_agents_md_merge_gate_wording_unchanged():
    para = _agents_input_gate_paragraph()
    assert re.search(r"merge the pr", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph must still name 'merge the PR' as the output gate"
    assert re.search(r"human merges every pr", para, re.IGNORECASE), \
        "AGENTS.md must still assert a human merges every PR"


def test_agents_md_no_longer_states_pertask_promote_as_the_sole_human_gate():
    para = _agents_input_gate_paragraph()
    assert "The two human gates" not in para, \
        "AGENTS.md still frames promote-to-Ready and merge as two flat, undifferentiated human gates"


# ---------------------------------------------------------------------------
# AGENTS.md — state-machine "→ Ready" row acknowledges the epic-gate path
# ---------------------------------------------------------------------------

def test_ready_row_distinguishes_standalone_from_epic_child():
    row = _ready_transition_row()
    assert re.search(r"human", row, re.IGNORECASE), \
        "→ Ready row dropped human promotion entirely"
    assert re.search(r"epic", row, re.IGNORECASE), \
        "→ Ready row does not mention epics at all"
    assert re.search(r"automat\w*|mechanical|epic-gate", row, re.IGNORECASE), \
        "→ Ready row does not describe the epic-child path as automatic/mechanical"


# ---------------------------------------------------------------------------
# skills/factory/SKILL.md — input-gate invariant bullet reworded
# ---------------------------------------------------------------------------

def test_skill_md_input_gate_bullet_ties_to_design_artifacts():
    bullet = _input_gate_bullet()
    assert re.search(r"design artifact", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet does not mention design artifacts"
    assert re.search(r"`active`", bullet), \
        "SKILL.md input-gate bullet does not mention setting a design `active`"


def test_skill_md_input_gate_bullet_still_forbids_auto_decide():
    bullet = _input_gate_bullet()
    assert re.search(r"no agent ever sets `active`|no auto-promote|always", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet dropped the 'no auto-deciding the design' guarantee"


def test_skill_md_input_gate_bullet_describes_mechanical_epic_path():
    bullet = _input_gate_bullet()
    assert re.search(r"mechanical", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet does not call epic-gate promotion mechanical"
    assert re.search(r"standing approval", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet does not tie mechanical promotion to a standing approval"
    assert re.search(r"fail.closed", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet does not state the mechanical path is fail-closed"


def test_skill_md_input_gate_bullet_keeps_standalone_task_carveout():
    bullet = _input_gate_bullet()
    assert re.search(r"standalone task", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet does not carve out standalone tasks with no governing design"


def test_skill_md_input_gate_bullet_merge_wording_unchanged():
    bullet = _input_gate_bullet()
    assert re.search(r"output.*gate.*merge|merge.*human in v1", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet no longer describes the output/merge gate"
    assert re.search(r"a human decides what to build", bullet, re.IGNORECASE), \
        "SKILL.md input-gate bullet dropped the durable-rule closer"


def test_skill_md_no_longer_says_promote_to_ready_is_always_human():
    bullet = _input_gate_bullet()
    assert "Promote-to-Ready" not in bullet or "always" not in bullet.split("Promote-to-Ready")[-1][:80], \
        "SKILL.md input-gate bullet still asserts promote-to-Ready is human, always (too coarse post-epic-gate)"


# ---------------------------------------------------------------------------
# Other invariant bullets in SKILL.md must remain intact (not weakened)
# ---------------------------------------------------------------------------

def test_other_invariants_still_present_and_unweakened():
    text = _skill_text()
    expectations = [
        r"builder\s*≠\s*verifier|independent cold processes",
        r"deterministic gates",
        r"native primitives",
        r"repo-agnostic",
        r"build from git refs",
        r"prs only",
        r"auth is human work",
    ]
    lowered = text.lower()
    for pattern in expectations:
        assert re.search(pattern, lowered), \
            f"SKILL.md Invariants section is missing expected content matching {pattern!r}"


# ---------------------------------------------------------------------------
# Version bump to 0.6.2 and description agreement
# ---------------------------------------------------------------------------

def test_plugin_version_is_0_6_2():
    assert _plugin_data()["version"] == "0.6.2", \
        f".claude-plugin/plugin.json version is {_plugin_data()['version']!r}, expected '0.6.2'"


def test_skill_md_and_plugin_description_agree():
    assert _skill_description() == _plugin_data()["description"], (
        "SKILL.md frontmatter description and plugin.json description have drifted apart:\n"
        f"SKILL.md:     {_skill_description()!r}\n"
        f"plugin.json:  {_plugin_data()['description']!r}"
    )


# ---------------------------------------------------------------------------
# Out of scope: the org-level workspace-root AGENTS.md is untouched here
# ---------------------------------------------------------------------------

def test_repo_agents_md_does_not_claim_to_be_the_github_org_doc():
    """This task must not attempt to edit yellow-robots/.github's canonical
    org AGENTS.md; the in-repo AGENTS.md should remain the factory's own
    operating manual, not a copy/fork of the org doc."""
    text = _agents_text()
    assert text.startswith("# AGENTS.md — how the Yellow Robots dev factory works"), \
        "AGENTS.md header changed unexpectedly — this task should only reword the input-gate paragraph"
