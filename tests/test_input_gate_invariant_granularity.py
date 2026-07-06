"""
Tests for Issue #19 — Reword the input-gate invariant at its true granularity
in the factory docs and skill (patch release 0.6.2) — and Issue #28, which
finishes that reword on the three surfaces #19 left out: the AGENTS.md
pipeline-diagram annotation, closing.md Section 1, and the stale version-pin
test names (patch release 0.6.3).

Derived from the Issue #19 and #28 acceptance criteria (the spec), not from
the implementation internals. These check that AGENTS.md, skills/factory/
SKILL.md, and skills/factory/references/closing.md all state the input-gate
invariant at design-artifact granularity — authority lives at the design
artifacts (`active`); flipping a governed epic Ready, promoting its next
slice, and closing a finished epic are mechanical under a standing approval,
fail-closed to the human on doubt; a standalone task with no governing
design keeps per-task human promotion; the cord-pull (un-Readying an epic)
remains the human veto; and the merge gate / other invariants are unchanged.
"""

import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
SKILL = ROOT / "skills" / "factory" / "SKILL.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CLOSING = ROOT / "skills" / "factory" / "references" / "closing.md"


def _agents_text():
    return AGENTS.read_text(encoding="utf-8")


def _skill_text():
    return SKILL.read_text(encoding="utf-8")


def _closing_text():
    return CLOSING.read_text(encoding="utf-8")


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


def _diagram_ready_annotation():
    """Pull the annotation on the pipeline diagram's 'human sets Status = Ready' line."""
    text = _agents_text()
    match = re.search(
        r"^\s*→\s*human sets Status = Ready\s*(←.*)$", text, re.MULTILINE
    )
    assert match, "AGENTS.md pipeline diagram is missing the 'human sets Status = Ready' line"
    return match.group(1)


def _closing_promote_section():
    """Pull closing.md's '## 1. Promote to Ready' section, up to the next '## ' heading."""
    text = _closing_text()
    match = re.search(
        r"## 1\. Promote to Ready\n(.*?)\n## 2\.", text, re.DOTALL
    )
    assert match, "closing.md is missing the '## 1. Promote to Ready' section"
    return match.group(1)


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


def test_agents_md_output_gate_is_factory_executed_for_armed_repos():
    # Issue #38 (autonomous merge) reworded the output gate that #19/#28 had left untouched: it is no
    # longer 'a human merges every PR'. The merge is now FACTORY-EXECUTED for an armed repo under
    # fail-closed conditions, and human-merged otherwise. The paragraph must still name the output gate.
    para = _agents_input_gate_paragraph()
    assert re.search(r"merge the pr", para, re.IGNORECASE), \
        "AGENTS.md input-gate paragraph must still name 'merge the PR' as the output gate"
    assert re.search(r"factory.executed", para, re.IGNORECASE), \
        "AGENTS.md output gate no longer describes the factory-executed merge for armed repos (#38)"
    assert re.search(r"human.merged|a human merges", para, re.IGNORECASE), \
        "AGENTS.md output gate dropped the human-merged fallback for non-armed repos"
    assert not re.search(r"human merges every pr", para, re.IGNORECASE), \
        "AGENTS.md still asserts 'a human merges every PR', which #38 (autonomous merge) overturns"


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
# AGENTS.md — pipeline-diagram annotation (Issue #28)
# ---------------------------------------------------------------------------

def test_diagram_annotation_no_longer_claims_the_only_human_gated_signal():
    annotation = _diagram_ready_annotation()
    assert "only" not in annotation.lower(), (
        "AGENTS.md pipeline-diagram annotation on 'human sets Status = Ready' still claims "
        "exclusivity ('only'), which is false for a Ready epic's child promoted by the epic-gate"
    )


def test_diagram_annotation_matches_design_active_granularity():
    annotation = _diagram_ready_annotation()
    assert re.search(r"design.?active", annotation, re.IGNORECASE), (
        "AGENTS.md pipeline-diagram annotation does not tie human authority to design-`active`, "
        "so it no longer matches the granularity of the input-gate paragraph below it"
    )
    assert re.search(r"epic", annotation, re.IGNORECASE), (
        "AGENTS.md pipeline-diagram annotation does not mention epics"
    )
    assert re.search(r"auto.?promot\w*|mechanical|automat\w*", annotation, re.IGNORECASE), (
        "AGENTS.md pipeline-diagram annotation does not describe the epic-child path as "
        "auto-promoted/mechanical"
    )


# ---------------------------------------------------------------------------
# skills/factory/references/closing.md — Section 1 "Promote to Ready" (Issue #28)
# ---------------------------------------------------------------------------

def test_closing_md_promote_section_ties_to_design_artifacts():
    section = _closing_promote_section()
    assert re.search(r"design artifact", section, re.IGNORECASE), \
        "closing.md §1 does not mention design artifacts"
    assert re.search(r"`active`", section), \
        "closing.md §1 does not mention setting a design `active`"
    assert re.search(r"product-spec|feature-rfc", section, re.IGNORECASE), \
        "closing.md §1 does not name product-spec/feature-rfc as the design artifact"


def test_closing_md_promote_section_still_forbids_agent_setting_active():
    section = _closing_promote_section()
    assert re.search(r"no agent ever sets `active`|no agent may set `active`", section, re.IGNORECASE), \
        "closing.md §1 dropped the guarantee that no agent ever sets a design `active`"


def test_closing_md_promote_section_describes_mechanical_epic_path():
    section = _closing_promote_section()
    assert re.search(r"mechanical", section, re.IGNORECASE), \
        "closing.md §1 does not call epic-slice promotion/closing mechanical"
    assert re.search(r"standing approval", section, re.IGNORECASE), \
        "closing.md §1 does not tie the mechanical path to a standing approval"
    assert re.search(r"fail.closed", section, re.IGNORECASE), \
        "closing.md §1 does not state the mechanical path is fail-closed"
    assert re.search(r"epic", section, re.IGNORECASE), \
        "closing.md §1 does not mention epics"


def test_closing_md_promote_section_keeps_standalone_task_carveout():
    section = _closing_promote_section()
    assert re.search(r"standalone task", section, re.IGNORECASE), \
        "closing.md §1 does not carve out standalone tasks with no governing design"
    assert re.search(r"human promotion|human touch|per-task human", section, re.IGNORECASE), \
        "closing.md §1 does not say standalone tasks keep human promotion"


def test_closing_md_promote_section_no_longer_says_status_ready_is_always_human():
    section = _closing_promote_section()
    assert "a human — always" not in section, (
        "closing.md §1 still asserts promote-to-Ready is human, always — too coarse "
        "post-epic-gate and inconsistent with the SKILL.md Invariants bullet"
    )
    assert "the only dispatch" not in section.lower(), (
        "closing.md §1 still claims Status=Ready is the only dispatch signal"
    )


def test_closing_md_promote_section_matches_skill_md_granularity():
    """closing.md §1 and the SKILL.md input-gate bullet must describe the same
    granularity — same load-bearing terms, not necessarily identical prose."""
    section = _closing_promote_section()
    bullet = _input_gate_bullet()
    shared_terms = [
        r"design artifact",
        r"`active`",
        r"mechanical",
        r"standing approval",
        r"fail.closed",
        r"standalone task",
    ]
    for pattern in shared_terms:
        in_section = re.search(pattern, section, re.IGNORECASE)
        in_bullet = re.search(pattern, bullet, re.IGNORECASE)
        assert in_section and in_bullet, (
            f"closing.md §1 and the SKILL.md input-gate bullet disagree on granularity term "
            f"{pattern!r}: in closing.md={bool(in_section)}, in SKILL.md bullet={bool(in_bullet)}"
        )


def test_closing_md_checklist_before_promoting_unchanged():
    """The promote checklist itself is out of scope for #28 — only the 'Who' prose changes."""
    section = _closing_promote_section()
    assert "`check_links` is green on the technical-rfc" in section
    assert "`check_task` is green on the task" in section
    assert "The task is self-contained" in section
    assert "Size is declared" in section


def test_closing_md_sections_2_through_4_unchanged():
    """Issue #28 was wording-alignment only for §1, and this test froze §2-4 to prove it.
    The 0.7.0 release (iteration 6 shipped: the factory-executed output gate) legitimately
    retargeted §2 — this pin now anchors the NEW §2 semantics; §3-4 and the release
    checklist stay frozen as before."""
    text = _closing_text()
    assert "**Who:** the **factory itself, for an armed repo** — otherwise a human." in text, \
        "closing.md §2 'Merge → Done' Who line lost the factory-executed output gate"
    assert "squash-merged by the factory with a durable `YR-MERGE: MERGED` record" in text, \
        "closing.md §2 lost the armed-merge record semantics"
    assert "The **durable rule** is *a human decides what to build*" in text, \
        "closing.md §2 durable-rule sentence changed unexpectedly"
    assert "Set `status: active` on any doc still at `draft`" in text, \
        "closing.md §3 'Doc-side freeze' content changed unexpectedly"
    assert "This is **shipping freezes the why**" in text, \
        "closing.md §3 closing sentence changed unexpectedly"
    assert "1. **Version bump** — update `version` in `.claude-plugin/plugin.json`" in text, \
        "closing.md skill-release block step 1 changed unexpectedly"
    assert "2. **Release scan** — verify all of the following are true before shipping:" in text, \
        "closing.md skill-release block step 2 changed unexpectedly"
    assert "3. **Ship before demote**" in text, \
        "closing.md skill-release block step 3 changed unexpectedly"
    assert "The release scan must be fully green." in text, \
        "closing.md release-checklist Gate section changed unexpectedly"


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

def test_plugin_version_is_current():
    assert _plugin_data()["version"] == "0.7.0", \
        f".claude-plugin/plugin.json version is {_plugin_data()['version']!r}, expected '0.7.0'"


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
