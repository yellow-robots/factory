"""Acceptance tests for tools/cross.py — the crossing's deterministic gates and filing act
(it-36 slice G, #472).

Derived from the issue's acceptance criteria and its "Test expectations" section: every test drives
`cross.cross(*, gh=None, vault=None, ...)`, the pure core, with a stateful FakeGh (mirrors
tests/test_design_gate.py's own style) and a fake vault client — no live network, no live vault, no
worktree cut. `check_links`/`check_task` are stubbed via the injectable `check_links_fn`/`check_task_fn`
seams so this suite never touches a real filesystem/git tree for those two gates; a couple of dedicated
tests drive the real `gate_check_links`/`gate_check_task` wrappers directly to prove the wiring holds.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import cross  # noqa: E402

REPO = "yellow-robots/factory"
ARCH_RESULT = {"verdict": "fit", "alternatives": ["a queue-based design instead"],
               "findings_text": "the chosen shape follows the existing pattern"}


# ---- fixtures ---------------------------------------------------------------------------------------

TECHNICAL_RFC_DRAFT = """---
type: technical-rfc
title: "Some Feature"
status: draft
stage: 3
home: epic-issue
target_repo: yellow-robots
base_ref: origin/main
created: "2026-09-06"
---

> airlock preamble prose, never filed.

# Technical RFC — Some Feature

<!-- ═══════════════ ISSUE BODY · file from here ↓ ═══════════════ -->

**Source:** product-spec [[some-spec]] (Obsidian product brain) · written against `origin/main`.

## Touched modules / files
- `tools/x.py` — new

## Per-task context slices
### Slice A — do the thing

<!-- ═══════════════ ↑ END ISSUE BODY · file to here ═══════════════ -->

---
## Authoring scaffold — NOT filed on the Issue
Never reaches the epic.
"""


def _slice_draft(title="Do the thing", *, extra_context="", extra_constraints=""):
    return f"""---
type: task
title: "{title}"
stage: 4
home: github-issue
source_technical_rfc: "#999"
size: "S — one PR"
model: sonnet
target_repo: yellow-robots
---

# Task — {title}

**Filed as:** a GitHub Issue via the Task form.

> Filed via .github/ISSUE_TEMPLATE/task.yml. Authoring aid, never filed.

## Goal
Do the thing.

## Acceptance criteria
- [ ] it works

## Context & links
Self-contained context here.{extra_context}

## Test expectations
Unit tests cover it.

## Constraints / out of scope
{extra_constraints}

## Size
S — one PR

---
*Next stage:* the **factory** builds it (implement -> independent test -> check -> independent review -> PR).
"""


def _clean_links(text, *, vault_root, resolve_ref=None):
    return []


def _clean_task(text, *, repo_root, base_ref):
    return []


# ---- FakeGh: mirrors tests/test_design_gate.py's own style ------------------------------------------

def _f_flags(argv):
    out = {}
    for i, tok in enumerate(argv):
        if tok == "-F" and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            out[k] = v
    return out


class FakeGh:
    def __init__(self, *, feature_type_id="FEATURETYPE", task_type_id="TASKTYPE", start_number=100):
        self.feature_type_id = feature_type_id
        self.task_type_id = task_type_id
        self._next_number = start_number
        self.issues = {}          # number -> {title, body, repo, node_id, type_id}
        self.comments = {}        # number -> [body, ...]
        self.sub_issues = []      # (epic_node_id, slice_node_id)
        self.project_adds = []    # (project_number, owner, url)
        self.calls = []

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:2] == ["issue", "create"]:
            title = argv[argv.index("--title") + 1]
            body = argv[argv.index("--body") + 1]
            repo = argv[argv.index("--repo") + 1]
            number = self._next_number
            self._next_number += 1
            self.issues[number] = {"title": title, "body": body, "repo": repo,
                                   "node_id": f"NODE{number}", "type_id": None}
            return f"https://github.com/{repo}/issues/{number}"
        if argv[:2] == ["issue", "view"]:
            number = int(argv[2])
            return {"id": self.issues[number]["node_id"]}
        if argv[:2] == ["issue", "comment"]:
            number = int(argv[2])
            body = argv[argv.index("--body") + 1]
            self.comments.setdefault(number, []).append(body)
            return ""
        if argv[:2] == ["project", "item-add"]:
            project_number = argv[2]
            owner = argv[argv.index("--owner") + 1]
            url = argv[argv.index("--url") + 1]
            self.project_adds.append((project_number, owner, url))
            return ""
        if argv[:2] == ["api", "graphql"]:
            q = argv[argv.index("-f") + 1][len("query="):]
            if "issueTypes" in q:
                return {"data": {"repository": {"issueTypes": {"nodes": [
                    {"id": self.feature_type_id, "name": "Feature"},
                    {"id": self.task_type_id, "name": "Task"},
                ]}}}}
            flags = _f_flags(argv)
            if "updateIssue" in q:
                node_id, type_id = flags["id"], flags["type"]
                for issue in self.issues.values():
                    if issue["node_id"] == node_id:
                        issue["type_id"] = type_id
                return {"data": {"updateIssue": {"issue": {"id": node_id}}}}
            if "addSubIssue" in q:
                self.sub_issues.append((flags["issueId"], flags["subIssueId"]))
                return {"data": {"addSubIssue": {"issue": {"id": flags["issueId"]}}}}
        raise AssertionError(f"FakeGh: unexpected argv {argv}")

    def node_id_of(self, number):
        return self.issues[number]["node_id"]


class FakeVault:
    def __init__(self):
        self.patches = []

    def patch_frontmatter(self, path, key, value):
        self.patches.append((path, key, value))
        return "ok"


def _cross(gh=None, vault=None, slices=None, **overrides):
    gh = gh or FakeGh()
    vault = vault or FakeVault()
    kwargs = dict(
        gh=gh, vault=vault, technical_rfc_draft=TECHNICAL_RFC_DRAFT,
        slices=slices if slices is not None else [{"draft": _slice_draft(), "runner_built": True}],
        repo=REPO, who="yr-pm[bot]", design="01-pm-agent", review="cold technical-rfc review: APPROVE",
        arch_result=ARCH_RESULT, feature_type_id="FEATURETYPE", task_type_id="TASKTYPE",
        vault_root="/tmp/does-not-matter", check_links_fn=_clean_links, check_task_fn=_clean_task,
        vault_doc_path="04 projects/factory/iterations/36-pm-agent/01-pm-agent.md",
    )
    kwargs.update(overrides)
    return cross.cross(**kwargs), gh, vault


# ---- happy path: epic, type, sub-issues, links, approval record, crossed_to -------------------------

def test_epic_is_filed_with_the_technical_rfc_title_and_the_arch_section_appended():
    result, gh, _ = _cross()
    assert result["ok"] is True
    epic = gh.issues[result["epic_number"]]
    assert epic["title"] == "Some Feature"
    assert "## Architecture review" in epic["body"]
    assert "**Verdict:** fit" in epic["body"]
    assert "a queue-based design instead" in epic["body"]
    # the authoring scaffold below the airlock never reaches the filed body
    assert "Authoring scaffold" not in epic["body"]
    assert "airlock preamble" not in epic["body"]


def test_epic_is_typed_feature_and_added_to_the_project():
    result, gh, _ = _cross()
    epic = gh.issues[result["epic_number"]]
    assert epic["type_id"] == "FEATURETYPE"
    assert gh.project_adds and gh.project_adds[0][2] == result["epic_url"]


def test_runner_built_slice_is_filed_as_a_sub_issue_typed_task():
    result, gh, _ = _cross()
    assert len(result["slices"]) == 1
    slice_number = result["slices"][0]["number"]
    slice_issue = gh.issues[slice_number]
    assert slice_issue["title"] == "Do the thing"
    assert slice_issue["type_id"] == "TASKTYPE"
    epic_node = gh.node_id_of(result["epic_number"])
    assert (epic_node, gh.node_id_of(slice_number)) in gh.sub_issues


def test_attended_slice_is_filed_untyped():
    result, gh, _ = _cross(slices=[{"draft": _slice_draft(), "runner_built": False}])
    slice_number = result["slices"][0]["number"]
    assert gh.issues[slice_number]["type_id"] is None
    epic_node = gh.node_id_of(result["epic_number"])
    assert (epic_node, gh.node_id_of(slice_number)) in gh.sub_issues


def test_gate_touching_line_is_carried_verbatim_into_the_filed_slice_body():
    draft = _slice_draft(extra_constraints="\nYR-GATE-TOUCHING: raises check_timeout's default\n")
    result, gh, _ = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert "YR-GATE-TOUCHING: raises check_timeout's default" in gh.issues[slice_number]["body"]


def test_approval_record_is_tool_emitted_with_who_the_app_slug():
    result, gh, _ = _cross(who="yr-pm[bot]", design="01-pm-agent",
                           review="cold technical-rfc review: APPROVE")
    epic_comments = gh.comments[result["epic_number"]]
    assert len(epic_comments) == 1
    body = epic_comments[0]
    assert body.startswith("YR-EPIC-APPROVAL")
    assert "design: 01-pm-agent" in body
    assert "review: cold technical-rfc review: APPROVE" in body
    assert "who: @yr-pm[bot]" in body


def test_crossed_to_is_stamped_through_the_vault_client():
    result, _, vault = _cross(vault_doc_path="04 projects/factory/iterations/36-pm-agent/01-pm-agent.md")
    assert vault.patches == [
        ("04 projects/factory/iterations/36-pm-agent/01-pm-agent.md", "crossed_to",
         f"yellow-robots/factory#{result['epic_number']}"),
    ]


def test_no_vault_doc_path_means_no_vault_write_but_still_crosses():
    result, _, vault = _cross(vault_doc_path=None)
    assert result["ok"] is True
    assert vault.patches == []


def test_multiple_slices_all_file_and_link_to_the_same_epic():
    slices = [{"draft": _slice_draft("Slice one"), "runner_built": True},
             {"draft": _slice_draft("Slice two"), "runner_built": True}]
    result, gh, _ = _cross(slices=slices)
    assert len(result["slices"]) == 2
    epic_node = gh.node_id_of(result["epic_number"])
    for s in result["slices"]:
        assert (epic_node, gh.node_id_of(s["number"])) in gh.sub_issues


# ---- check_links / check_task gate refusals: writes nothing ------------------------------------------

def test_check_links_failure_refuses_and_files_nothing():
    def _bad_links(text, *, vault_root, resolve_ref=None):
        return ["source_feature_rfc: unresolved wikilink [[missing]] — no file named 'missing.md' in vault"]

    result, gh, vault = _cross(check_links_fn=_bad_links)
    assert result == {"ok": False, "stage": "check_links", "errors": [
        "source_feature_rfc: unresolved wikilink [[missing]] — no file named 'missing.md' in vault"]}
    assert gh.calls == []
    assert vault.patches == []


def test_check_task_gates_a_bad_slice_and_refuses_the_whole_crossing():
    def _bad_task(text, *, repo_root, base_ref):
        return ["cited path `tools/does-not-exist.py` does not exist"]

    result, gh, vault = _cross(check_task_fn=_bad_task)
    assert result["ok"] is False
    assert result["stage"] == "check_task"
    assert result["errors"] == {0: ["cited path `tools/does-not-exist.py` does not exist"]}
    assert gh.calls == []
    assert vault.patches == []


def test_check_task_runs_against_every_slice_naming_only_the_bad_one():
    def _selective(text, *, repo_root, base_ref):
        return ["missing"] if "Slice two" in text else []

    slices = [{"draft": _slice_draft("Slice one"), "runner_built": True},
             {"draft": _slice_draft("Slice two"), "runner_built": True}]
    result, gh, _ = _cross(slices=slices, check_task_fn=_selective)
    assert result["ok"] is False
    assert result["stage"] == "check_task"
    assert list(result["errors"].keys()) == [1]
    assert gh.calls == []


def test_a_block_arch_verdict_refuses_and_files_nothing():
    block_result = {"verdict": "block", "alternatives": ["do it differently"], "findings_text": "no"}
    result, gh, vault = _cross(arch_result=block_result)
    assert result == {"ok": False, "stage": "arch", "errors": ["verdict='block'"]}
    assert gh.calls == []
    assert vault.patches == []


def test_a_refit_verdict_still_crosses():
    refit_result = {"verdict": "refit", "alternatives": ["do it differently"], "findings_text": "close"}
    result, _, _ = _cross(arch_result=refit_result)
    assert result["ok"] is True


# ---- escalation declarations: park with YR-ESCALATION; nothing else waits on it -----------------------

def test_external_dependency_declaration_parks_the_slice_with_yr_escalation():
    draft = _slice_draft(extra_context="\nDeclares: external dependency payment-gateway\n")
    result, gh, _ = _cross(slices=[{"draft": draft, "runner_built": True}])
    assert result["ok"] is True
    slice_number = result["slices"][0]["number"]
    assert result["slices"][0]["escalations"] == ["external dependency payment-gateway"]
    comments = gh.comments[slice_number]
    assert len(comments) == 1
    assert comments[0].startswith("YR-ESCALATION: act=park why=external-dependency")
    assert "payment-gateway" in comments[0]


def test_data_migration_declaration_parks_the_slice_with_yr_escalation():
    draft = _slice_draft(extra_context="\nDeclares: data migration\n")
    result, gh, _ = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert result["slices"][0]["escalations"] == ["data migration"]
    assert gh.comments[slice_number][0].startswith("YR-ESCALATION: act=park why=data-migration")


def test_escalation_never_inferred_a_prose_mention_does_not_park():
    draft = _slice_draft(extra_context="\nWe discussed an external dependency once but decided against it.\n")
    result, gh, _ = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert result["slices"][0]["escalations"] == []
    assert slice_number not in gh.comments


def test_escalated_slice_still_epic_flows_and_other_slices_are_unaffected():
    escalated = _slice_draft("Escalated slice",
                             extra_context="\nDeclares: external dependency some-service\n")
    plain = _slice_draft("Plain slice")
    slices = [{"draft": escalated, "runner_built": True}, {"draft": plain, "runner_built": True}]
    result, gh, vault = _cross(slices=slices)
    assert result["ok"] is True
    # the epic still gets its approval record and crossed_to stamp — nothing waits on the escalation
    assert gh.comments[result["epic_number"]][0].startswith("YR-EPIC-APPROVAL")
    assert vault.patches
    escalated_number = result["slices"][0]["number"]
    plain_number = result["slices"][1]["number"]
    assert escalated_number in gh.comments
    assert plain_number not in gh.comments


# ---- escalation_declarations: presence only, never inferred ------------------------------------------

def test_escalation_declarations_reads_declares_lines_at_column_zero():
    text = "prose\nDeclares: external dependency stripe\nmore prose\nDeclares: data migration\n"
    assert cross.escalation_declarations(text) == ["external dependency stripe", "data migration"]


def test_escalation_declarations_ignores_an_indented_line():
    text = "prose\n  Declares: external dependency stripe\n"
    assert cross.escalation_declarations(text) == []


def test_escalation_declarations_empty_when_absent():
    assert cross.escalation_declarations("nothing to see here") == []


# ---- draft parsing: title + filed-body extraction ------------------------------------------------------

def test_technical_rfc_issue_body_extracts_title_and_only_the_marked_span():
    title, body = cross.technical_rfc_issue_body(TECHNICAL_RFC_DRAFT)
    assert title == "Some Feature"
    assert "Touched modules" in body
    assert "Authoring scaffold" not in body
    assert "airlock preamble" not in body


def test_task_issue_body_extracts_title_and_drops_preamble_and_footer():
    title, body = cross.task_issue_body(_slice_draft("Do the thing"))
    assert title == "Do the thing"
    assert body.startswith("## Goal")
    assert "Next stage" not in body
    assert "Filed as:" not in body


def test_technical_rfc_issue_body_raises_on_missing_markers():
    with pytest.raises(ValueError):
        cross.technical_rfc_issue_body("# Technical RFC — X\n\nno markers here\n")


def test_task_issue_body_raises_on_missing_goal_heading():
    with pytest.raises(ValueError):
        cross.task_issue_body("# Task — X\n\nno goal heading\n")


# ---- split_draft: the cross-draft stage's combined output shape ---------------------------------------

RAW_DRAFT = """===TECHNICAL-RFC===
# Technical RFC — Some Feature

body here
===END-TECHNICAL-RFC===
===SLICE task===
# Task — Slice one

## Goal
g
===END-SLICE===
===SLICE attended===
# Task — Slice two

## Goal
g2
===END-SLICE===
"""


def test_split_draft_extracts_the_technical_rfc_and_every_slice_in_order():
    parsed = cross.split_draft(RAW_DRAFT)
    assert "# Technical RFC — Some Feature" in parsed["technical_rfc"]
    assert [s["kind"] for s in parsed["slices"]] == ["task", "attended"]
    assert "Slice one" in parsed["slices"][0]["body"]
    assert "Slice two" in parsed["slices"][1]["body"]


def test_split_draft_raises_when_the_technical_rfc_block_is_missing():
    with pytest.raises(ValueError):
        cross.split_draft("===SLICE task===\nbody\n===END-SLICE===\n")


def test_split_draft_raises_when_no_slice_block_is_present():
    with pytest.raises(ValueError):
        cross.split_draft("===TECHNICAL-RFC===\nbody\n===END-TECHNICAL-RFC===\n")


def test_cli_split_draft_writes_technical_rfc_slices_and_a_manifest(tmp_path):
    raw_path = tmp_path / "raw.txt"
    raw_path.write_text(RAW_DRAFT)
    out_dir = tmp_path / "out"
    rc = cross.main(["split-draft", str(raw_path), "--out-dir", str(out_dir)])
    assert rc == 0
    assert (out_dir / "technical-rfc.md").read_text().strip().startswith("# Technical RFC")
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest == [{"path": "slice-1.md", "kind": "task"}, {"path": "slice-2.md", "kind": "attended"}]
    assert "Slice one" in (out_dir / "slice-1.md").read_text()
    assert "Slice two" in (out_dir / "slice-2.md").read_text()


def test_cli_split_draft_returns_1_on_malformed_output(tmp_path, capsys):
    raw_path = tmp_path / "raw.txt"
    raw_path.write_text("nonsense, no markers")
    rc = cross.main(["split-draft", str(raw_path), "--out-dir", str(tmp_path / "out")])
    assert rc == 1


# ---- resolve_issue_type_ids -----------------------------------------------------------------------------

def test_resolve_issue_type_ids_lowercases_names():
    gh = FakeGh(feature_type_id="FT", task_type_id="TT")
    types = cross.resolve_issue_type_ids(gh, REPO)
    assert types == {"feature": "FT", "task": "TT"}


# ---- render_approval_body / render_escalation_comment: exact grammar ------------------------------------

def test_render_approval_body_grammar():
    body = cross.render_approval_body(design="01-pm-agent", review="APPROVE", who="yr-pm[bot]")
    lines = body.splitlines()
    assert lines[0] == "YR-EPIC-APPROVAL"
    assert "design: 01-pm-agent" in lines
    assert "review: APPROVE" in lines
    assert "who: @yr-pm[bot]" in lines


def test_render_escalation_comment_names_the_declaration():
    body = cross.render_escalation_comment("external dependency stripe")
    assert body.startswith("YR-ESCALATION: act=park why=external-dependency")
    assert "external dependency stripe" in body


# ---- gate_check_links / gate_check_task real wiring (no fakes) -----------------------------------------

def test_gate_check_links_wires_to_the_real_check_links(tmp_path):
    text = "---\nsource_spec: \"[[missing note]]\"\n---\n\nbody\n"
    errors = cross.gate_check_links(text, vault_root=tmp_path)
    assert errors and "missing note" in errors[0]


def test_gate_check_task_wires_to_the_real_check_task(tmp_path):
    text = ("# Task — X\n\n## Goal\ng\n\n## Acceptance criteria\n- [ ] a\n\n"
           "## Context & links\n\n## Test expectations\nt\n")
    errors = cross.gate_check_task(text, repo_root=str(tmp_path), base_ref=None)
    assert any("Context & links is empty" in e for e in errors)
