"""Acceptance tests for tools/cross.py — the crossing's deterministic gates and filing act
(it-36 slice G, #472).

Derived from the issue's acceptance criteria, its "Test expectations" section, and the cold review
of db47805 (five blockers, five improvements — folded here as one commit): every test drives
`cross.cross(*, gh=None, vault=None, ...)`, the pure core, with a stateful FakeGh (mirrors
tests/test_design_gate.py's own style), a fake vault client (read/write/patch_frontmatter), and a
PM-config spy — no live network, no live vault, no worktree cut. `check_links`/`check_task` are
stubbed via the injectable `check_links_fn`/`check_task_fn` seams so this suite never touches a real
filesystem/git tree for those two gates; a couple of dedicated tests drive the real
`gate_check_links`/`gate_check_task` wrappers directly to prove the wiring holds, and a further set
drives the parser functions over the ACTUAL shipped templates (B1/B2), never a fixture shaped away
from their real, load-bearing shape.
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
VAULT_DOC_PATH = "04 projects/factory/iterations/36-pm-agent/01-pm-agent.md"

SHIPPED_TECHNICAL_RFC = (ROOT / "skills" / "factory" / "templates" / "technical-rfc.md").read_text(
    encoding="utf-8")
SHIPPED_TASK = (ROOT / "skills" / "factory" / "templates" / "task.md").read_text(encoding="utf-8")


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

> airlock preamble prose, never filed. It even mentions `ISSUE BODY` markers by name, the way the
> shipped template's own airlock blockquote does — this draft exercises the SAME false-match hazard
> B1 found in the real template, deliberately, alongside the shipped-template tests below.

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


def _slice_draft(title="Do the thing", *, extra_context="", extra_constraints="", preamble_extra=""):
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
{preamble_extra}
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
    """`.read`/`.write`/`.patch_frontmatter` — the ADR write and the YR-ARCH-REVIEW append (I4) both
    round-trip through `.docs`; `initial_doc_text` seeds the governing design doc's own starting text
    (the thing `YR-ARCH-REVIEW` gets appended to)."""

    def __init__(self, *, initial_doc_text="---\nstatus: active\n---\n\nbody\n"):
        self.patches = []
        self.writes = []       # (path, content), in order
        self.docs = {VAULT_DOC_PATH: initial_doc_text}

    def read(self, path):
        return self.docs.get(path, "")

    def write(self, path, content):
        self.writes.append((path, content))
        self.docs[path] = content
        return content

    def patch_frontmatter(self, path, key, value):
        self.patches.append((path, key, value))
        return "ok"


class PMConfigSpy:
    def __init__(self):
        self.calls = []

    def __call__(self, *, repo, epic_issue, seed):
        self.calls.append({"repo": repo, "epic_issue": epic_issue, "seed": seed})


def _cross(gh=None, vault=None, slices=None, pm_config=None, **overrides):
    gh = gh or FakeGh()
    vault = vault or FakeVault()
    pm_config = pm_config if pm_config is not None else PMConfigSpy()
    kwargs = dict(
        gh=gh, vault=vault, technical_rfc_draft=TECHNICAL_RFC_DRAFT,
        slices=slices if slices is not None else [{"draft": _slice_draft(), "runner_built": True}],
        repo=REPO, who="yr-pm[bot]", design="01-pm-agent", review="cold technical-rfc review: APPROVE",
        seed="pm-agent",
        arch_result=ARCH_RESULT, feature_type_id="FEATURETYPE", task_type_id="TASKTYPE",
        vault_root="/tmp/does-not-matter", check_links_fn=_clean_links, check_task_fn=_clean_task,
        vault_doc_path=VAULT_DOC_PATH, update_pm_config=pm_config,
    )
    kwargs.update(overrides)
    return cross.cross(**kwargs), gh, vault, pm_config


# ---- happy path: epic, type, sub-issues, links, approval record, crossed_to -------------------------

def test_epic_is_filed_with_the_technical_rfc_title_and_the_arch_section_appended():
    result, gh, _vault, _pm = _cross()
    assert result["ok"] is True
    epic = gh.issues[result["epic_number"]]
    assert epic["title"] == "Some Feature"
    assert "## Architecture review" in epic["body"]
    assert "**Verdict:** fit" in epic["body"]
    assert "a queue-based design instead" in epic["body"]
    # B3/ruling 2 (cold review): no raw transcript in the human-facing epic body — the findings
    # text (which would carry the stage's own column-0 VERDICT:/ALTERNATIVE: lines) never lands here
    assert "the chosen shape follows the existing pattern" not in epic["body"]
    # the authoring scaffold below the airlock never reaches the filed body
    assert "Authoring scaffold" not in epic["body"]
    assert "airlock preamble" not in epic["body"]
    # B1: the airlock blockquote's own "ISSUE BODY" mention (deliberately present in this fixture,
    # matching the real template's own hazard) must never leak into the filed body either
    assert "false-match hazard" not in epic["body"]


def test_epic_is_typed_feature_and_added_to_the_project():
    result, gh, _vault, _pm = _cross()
    epic = gh.issues[result["epic_number"]]
    assert epic["type_id"] == "FEATURETYPE"
    assert gh.project_adds and gh.project_adds[0][2] == result["epic_url"]


def test_runner_built_slice_is_filed_as_a_sub_issue_typed_task():
    result, gh, _vault, _pm = _cross()
    assert len(result["slices"]) == 1
    slice_number = result["slices"][0]["number"]
    slice_issue = gh.issues[slice_number]
    assert slice_issue["title"] == "Do the thing"
    assert slice_issue["type_id"] == "TASKTYPE"
    assert result["slices"][0]["typed"] is True
    epic_node = gh.node_id_of(result["epic_number"])
    assert (epic_node, gh.node_id_of(slice_number)) in gh.sub_issues


def test_attended_slice_is_filed_untyped():
    result, gh, _vault, _pm = _cross(slices=[{"draft": _slice_draft(), "runner_built": False}])
    slice_number = result["slices"][0]["number"]
    assert gh.issues[slice_number]["type_id"] is None
    assert result["slices"][0]["typed"] is False
    epic_node = gh.node_id_of(result["epic_number"])
    assert (epic_node, gh.node_id_of(slice_number)) in gh.sub_issues


def test_gate_touching_line_is_carried_verbatim_into_the_filed_slice_body():
    draft = _slice_draft(extra_constraints="\nYR-GATE-TOUCHING: raises check_timeout's default\n")
    result, gh, _vault, _pm = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert "YR-GATE-TOUCHING: raises check_timeout's default" in gh.issues[slice_number]["body"]


def test_gate_touching_line_in_the_preamble_is_hoisted_into_the_filed_body():
    """B2 (cold review of db47805): a column-0 declaration ABOVE `## Goal` must still reach the
    filed body — epic_gate.py reads it from the child's own FILED body, never the draft."""
    draft = _slice_draft(preamble_extra="\nYR-GATE-TOUCHING: touches the manifest\n")
    result, gh, _vault, _pm = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert "YR-GATE-TOUCHING: touches the manifest" in gh.issues[slice_number]["body"]


def test_approval_record_is_tool_emitted_with_who_the_app_slug():
    result, gh, _vault, _pm = _cross(who="yr-pm[bot]", design="01-pm-agent",
                                     review="cold technical-rfc review: APPROVE")
    epic_comments = gh.comments[result["epic_number"]]
    assert len(epic_comments) == 1
    body = epic_comments[0]
    assert body.startswith("YR-EPIC-APPROVAL")
    assert "design: 01-pm-agent" in body
    assert "review: cold technical-rfc review: APPROVE" in body
    assert "who: @yr-pm[bot]" in body


def test_crossed_to_is_stamped_through_the_vault_client():
    result, _gh, vault, _pm = _cross(vault_doc_path=VAULT_DOC_PATH)
    assert (VAULT_DOC_PATH, "crossed_to", f"yellow-robots/factory#{result['epic_number']}") \
        in vault.patches


def test_no_vault_doc_path_means_no_vault_write_but_still_crosses():
    result, _gh, vault, _pm = _cross(vault_doc_path=None)
    assert result["ok"] is True
    assert vault.patches == []
    assert vault.writes == []


def test_multiple_slices_all_file_and_link_to_the_same_epic():
    slices = [{"draft": _slice_draft("Slice one"), "runner_built": True},
             {"draft": _slice_draft("Slice two"), "runner_built": True}]
    result, gh, _vault, _pm = _cross(slices=slices)
    assert len(result["slices"]) == 2
    epic_node = gh.node_id_of(result["epic_number"])
    for s in result["slices"]:
        assert (epic_node, gh.node_id_of(s["number"])) in gh.sub_issues


# ---- B5: the PM config write-back (epic_issue/seed), the seam a later promote.sh flip needs -----------

def test_pm_config_is_updated_with_the_filed_epic_number_and_seed():
    result, _gh, _vault, pm = _cross(seed="pm-agent")
    assert pm.calls == [{"repo": REPO, "epic_issue": result["epic_number"], "seed": "pm-agent"}]


def test_pm_config_is_not_updated_on_a_gate_refusal():
    result, _gh, _vault, pm = _cross(
        arch_result={"verdict": "block", "alternatives": ["x"], "findings_text": ""})
    assert result["ok"] is False
    assert pm.calls == []


def test_pm_config_update_is_optional_and_never_required():
    result, _gh, _vault, _pm = _cross(update_pm_config=None)
    assert result["ok"] is True


# ---- check_links / check_task gate refusals: writes nothing ------------------------------------------

def test_check_links_failure_refuses_and_files_nothing():
    def _bad_links(text, *, vault_root, resolve_ref=None):
        return ["source_feature_rfc: unresolved wikilink [[missing]] — no file named 'missing.md' in vault"]

    result, gh, vault, pm = _cross(check_links_fn=_bad_links)
    assert result == {"ok": False, "stage": "check_links", "errors": [
        "source_feature_rfc: unresolved wikilink [[missing]] — no file named 'missing.md' in vault"]}
    assert gh.calls == []
    assert vault.patches == []
    assert pm.calls == []


def test_check_task_gates_a_bad_slice_and_refuses_the_whole_crossing():
    def _bad_task(text, *, repo_root, base_ref):
        return ["cited path `tools/does-not-exist.py` does not exist"]

    result, gh, vault, _pm = _cross(check_task_fn=_bad_task)
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
    result, gh, _vault, _pm = _cross(slices=slices, check_task_fn=_selective)
    assert result["ok"] is False
    assert result["stage"] == "check_task"
    assert list(result["errors"].keys()) == [1]
    assert gh.calls == []


def test_check_task_never_runs_against_an_attended_slice():
    """I2 (cold review of db47805): check_task is the automated DoR gate for a RUNNER-BUILT slice
    only — the mandate's own "each typed slice" wording."""
    calls = []

    def _tracking(text, *, repo_root, base_ref):
        calls.append(text)
        return []

    slices = [{"draft": _slice_draft("Attended one"), "runner_built": False}]
    result, gh, _vault, _pm = _cross(slices=slices, check_task_fn=_tracking)
    assert result["ok"] is True
    assert calls == []


def test_check_task_still_runs_against_a_runner_built_slice():
    calls = []

    def _tracking(text, *, repo_root, base_ref):
        calls.append(text)
        return []

    result, gh, _vault, _pm = _cross(check_task_fn=_tracking)
    assert len(calls) == 1


def test_a_block_arch_verdict_refuses_and_files_nothing():
    block_result = {"verdict": "block", "alternatives": ["do it differently"], "findings_text": "no"}
    result, gh, vault, pm = _cross(arch_result=block_result)
    assert result == {"ok": False, "stage": "arch", "errors": ["verdict='block'"]}
    assert gh.calls == []
    assert vault.patches == []
    assert pm.calls == []


def test_a_refit_verdict_still_crosses():
    refit_result = {"verdict": "refit", "alternatives": ["do it differently"], "findings_text": "close"}
    result, _gh, _vault, _pm = _cross(arch_result=refit_result)
    assert result["ok"] is True


# ---- I3: a mid-filing exception is caught, never an unhandled traceback -------------------------------

def test_mid_filing_exception_before_slices_reports_what_the_epic_already_has():
    class RaisingGh(FakeGh):
        def __call__(self, argv):
            out = super().__call__(argv)
            if argv[:2] == ["project", "item-add"]:
                raise RuntimeError("gh project item-add failed (stub)")
            return out

    result, gh, vault, pm = _cross(gh=RaisingGh())
    assert result["ok"] is False
    assert result["stage"] == "file"
    assert "epic_number" in result["filed"]
    assert "gh project item-add failed" in result["error"]
    # the epic WAS filed and typed before the raise — but nothing past that point ran
    assert result["filed"]["epic_number"] in gh.issues
    assert pm.calls == []          # update_pm_config runs after item-add, never reached
    assert vault.patches == []     # crossed_to never reached either


def test_mid_filing_exception_during_slice_filing_still_names_the_filed_epic_and_pm_config():
    class RaisingGh(FakeGh):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._creates = 0

        def __call__(self, argv):
            if argv[:2] == ["issue", "create"]:
                self._creates += 1
                if self._creates == 2:   # the epic's own create succeeded; the first slice's fails
                    raise RuntimeError("gh issue create failed for the slice (stub)")
            return super().__call__(argv)

    result, gh, vault, pm = _cross(gh=RaisingGh())
    assert result["ok"] is False
    assert result["stage"] == "file"
    assert result["filed"]["slices"] == []
    assert "gh issue create failed for the slice" in result["error"]
    # update_pm_config already ran (it fires right after the epic itself is filed)
    assert pm.calls == [{"repo": REPO, "epic_issue": result["filed"]["epic_number"], "seed": "pm-agent"}]


# ---- I4: the real ADR through the vault client + YR-ARCH-REVIEW on the vault-doc surface ---------------

def test_no_architecture_home_skips_the_adr_but_still_crosses():
    result, _gh, vault, _pm = _cross()   # no architecture_home/adr_slug/adr_title given
    assert result["ok"] is True
    assert vault.writes == []
    assert vault.patches   # crossed_to still lands


def test_adr_is_written_through_the_vault_client_with_the_findings_text():
    result, _gh, vault, _pm = _cross(
        architecture_home="04 projects/factory/architecture",
        adr_slug="2026-09-06-pm-agent-arch-decision",
        adr_title="Architecture decision — pm-agent")
    assert result["ok"] is True
    adr_path = "04 projects/factory/architecture/2026-09-06-pm-agent-arch-decision.md"
    assert adr_path in vault.docs
    adr_text = vault.docs[adr_path]
    assert "type: research" in adr_text
    assert "**Update trigger:** Write at ship" in adr_text
    assert "**Verdict:** fit" in adr_text
    assert "a queue-based design instead" in adr_text
    # the raw findings text lives in the ADR (vault-only), never the epic body (B3/ruling 2)
    assert "the chosen shape follows the existing pattern" in adr_text


def test_yr_arch_review_is_appended_to_the_design_doc_never_the_issue_trail():
    result, gh, vault, _pm = _cross(
        architecture_home="04 projects/factory/architecture",
        adr_slug="2026-09-06-pm-agent-arch-decision",
        adr_title="Architecture decision — pm-agent")
    doc_text = vault.docs[VAULT_DOC_PATH]
    assert "YR-ARCH-REVIEW: who=yr-pm[bot] verdict=fit adr=" in doc_text
    assert "2026-09-06-pm-agent-arch-decision.md" in doc_text
    epic_comments = gh.comments[result["epic_number"]]
    assert not any("YR-ARCH-REVIEW" in c for c in epic_comments)


def test_epic_body_names_the_adr_when_one_was_written():
    result, gh, _vault, _pm = _cross(
        architecture_home="04 projects/factory/architecture",
        adr_slug="2026-09-06-pm-agent-arch-decision",
        adr_title="Architecture decision — pm-agent")
    epic_body = gh.issues[result["epic_number"]]["body"]
    assert "2026-09-06-pm-agent-arch-decision.md" in epic_body


# ---- escalation declarations: park with YR-ESCALATION; nothing else waits on it -----------------------

def test_external_dependency_declaration_parks_the_slice_with_yr_escalation():
    draft = _slice_draft(extra_context="\nDeclares: external dependency payment-gateway\n")
    result, gh, _vault, _pm = _cross(slices=[{"draft": draft, "runner_built": True}])
    assert result["ok"] is True
    slice_number = result["slices"][0]["number"]
    assert result["slices"][0]["escalations"] == ["external dependency payment-gateway"]
    comments = gh.comments[slice_number]
    assert len(comments) == 1
    assert comments[0].startswith("YR-ESCALATION: act=park why=external-dependency")
    assert "payment-gateway" in comments[0]


def test_data_migration_declaration_parks_the_slice_with_yr_escalation():
    draft = _slice_draft(extra_context="\nDeclares: data migration\n")
    result, gh, _vault, _pm = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert result["slices"][0]["escalations"] == ["data migration"]
    assert gh.comments[slice_number][0].startswith("YR-ESCALATION: act=park why=data-migration")


def test_escalation_never_inferred_a_prose_mention_does_not_park():
    draft = _slice_draft(extra_context="\nWe discussed an external dependency once but decided against it.\n")
    result, gh, _vault, _pm = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert result["slices"][0]["escalations"] == []
    assert slice_number not in gh.comments


def test_escalated_runner_built_slice_files_untyped_not_just_commented():
    """B4 (cold review of db47805): the park is a MECHANISM (the epic-gate's own `not-a-task`
    hold), never merely a comment beside an otherwise freely-promotable Type=Task."""
    draft = _slice_draft(extra_context="\nDeclares: external dependency payment-gateway\n")
    result, gh, _vault, _pm = _cross(slices=[{"draft": draft, "runner_built": True}])
    slice_number = result["slices"][0]["number"]
    assert gh.issues[slice_number]["type_id"] is None
    assert result["slices"][0]["typed"] is False
    assert result["slices"][0]["runner_built"] is True   # the declared kind is preserved as data


def test_escalated_slice_still_epic_flows_and_other_slices_are_unaffected():
    escalated = _slice_draft("Escalated slice",
                             extra_context="\nDeclares: external dependency some-service\n")
    plain = _slice_draft("Plain slice")
    slices = [{"draft": escalated, "runner_built": True}, {"draft": plain, "runner_built": True}]
    result, gh, vault, _pm = _cross(slices=slices)
    assert result["ok"] is True
    # the epic still gets its approval record and crossed_to stamp — nothing waits on the escalation
    assert gh.comments[result["epic_number"]][0].startswith("YR-EPIC-APPROVAL")
    assert vault.patches
    escalated_number = result["slices"][0]["number"]
    plain_number = result["slices"][1]["number"]
    assert escalated_number in gh.comments
    assert plain_number not in gh.comments
    # the sibling is typed normally — the escalation touches only its own slice's typing
    assert gh.issues[escalated_number]["type_id"] is None
    assert gh.issues[plain_number]["type_id"] == "TASKTYPE"


# ---- escalation_declarations: presence only, never inferred; data migration is exact -------------------

def test_escalation_declarations_reads_declares_lines_at_column_zero():
    text = "prose\nDeclares: external dependency stripe\nmore prose\nDeclares: data migration\n"
    assert cross.escalation_declarations(text) == ["external dependency stripe", "data migration"]


def test_escalation_declarations_ignores_an_indented_line():
    text = "prose\n  Declares: external dependency stripe\n"
    assert cross.escalation_declarations(text) == []


def test_escalation_declarations_empty_when_absent():
    assert cross.escalation_declarations("nothing to see here") == []


def test_escalation_declarations_data_migration_requires_exact_match_no_extra_tail():
    """cold-review notes item: 'data migration' is the one exact literal (no arbitrary tail) —
    'external dependency' takes a name, 'data migration' does not."""
    assert cross.escalation_declarations("Declares: data migration\n") == ["data migration"]
    assert cross.escalation_declarations("Declares: data migration of the ledger\n") == []


# ---- draft parsing: title + filed-body extraction ------------------------------------------------------

def test_technical_rfc_issue_body_extracts_title_and_only_the_marked_span():
    title, body = cross.technical_rfc_issue_body(TECHNICAL_RFC_DRAFT)
    assert title == "Some Feature"
    assert "Touched modules" in body
    assert "Authoring scaffold" not in body
    assert "airlock preamble" not in body
    assert "false-match hazard" not in body   # B1: the blockquote's bare "ISSUE BODY" mention


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


def test_h1_title_strips_a_plain_hyphen_separator_too():
    assert cross._h1_title("# Task - My Title\n", "Task") == "My Title"
    assert cross._h1_title("# Task — My Title\n", "Task") == "My Title"


# ---- B1: the parser driven over the ACTUAL shipped templates, not a fixture shaped away from them -----

def test_technical_rfc_issue_body_on_the_shipped_template_skips_the_airlock_blockquote():
    """The airlock's own blockquote (technical-rfc.md's own prose) carries the bare phrase
    'ISSUE BODY' seven lines above the real marker comment — a naive first-match regex would file
    the blockquote's own tail + the H1 + its HTML comment as if they were the filed body."""
    title, body = cross.technical_rfc_issue_body(SHIPPED_TECHNICAL_RFC)
    assert title == "<feature name>"           # the shipped template's own unfilled placeholder
    assert "What gets filed" not in body       # the airlock blockquote's own prose
    assert "the Issue TITLE" not in body       # the H1's own HTML comment
    assert "**Source:**" in body               # the real filed body starts here
    assert "Authoring scaffold" not in body    # the footer scaffold, correctly excluded


def test_task_issue_body_on_the_shipped_template_extracts_from_goal():
    title, body = cross.task_issue_body(SHIPPED_TASK)
    assert title == "<one-line title>"
    assert body.startswith("## Goal")
    assert "Next stage" not in body


def test_task_issue_body_hoists_a_gate_touching_line_from_the_shipped_templates_own_preamble():
    """B2, on the shipped template's own shape: a column-0 declaration inserted right after the H1
    (before the form's own preamble prose, before ## Goal) must still reach the filed body."""
    draft = SHIPPED_TASK.replace(
        "# Task — <one-line title>\n",
        "# Task — <one-line title>\n\nYR-GATE-TOUCHING: this slice touches check_cmd\n",
        1,
    )
    _title, body = cross.task_issue_body(draft)
    assert body.startswith("YR-GATE-TOUCHING: this slice touches check_cmd\n\n## Goal")


def test_task_issue_body_hoists_a_declares_line_from_the_shipped_templates_own_preamble():
    draft = SHIPPED_TASK.replace(
        "# Task — <one-line title>\n",
        "# Task — <one-line title>\n\nDeclares: external dependency stripe\n",
        1,
    )
    _title, body = cross.task_issue_body(draft)
    assert body.startswith("Declares: external dependency stripe\n\n## Goal")


def test_task_issue_body_hoists_from_both_placements_preserving_order():
    """B2's own gotcha at BOTH placements at once: a preamble declaration is hoisted; an ordinary
    in-body one (already inside the ## Goal..footer span) is never dropped either."""
    draft = _slice_draft(extra_context="\nYR-GATE-TOUCHING: also touches CI\n",
                         preamble_extra="\nDeclares: data migration\n")
    _title, body = cross.task_issue_body(draft)
    lines = body.splitlines()
    assert lines[0] == "Declares: data migration"
    assert "YR-GATE-TOUCHING: also touches CI" in body


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


# ---- render_approval_body / render_escalation_comment / render_arch_section: exact grammar -----------

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


def test_render_arch_section_never_carries_the_raw_findings_text():
    body = cross.render_arch_section(ARCH_RESULT)
    assert "the chosen shape follows the existing pattern" not in body
    assert "**Verdict:** fit" in body
    assert "a queue-based design instead" in body


def test_render_arch_section_names_the_adr_when_given_a_path():
    body = cross.render_arch_section(ARCH_RESULT, adr_path="04 projects/x/architecture/foo.md")
    assert "04 projects/x/architecture/foo.md" in body


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


# ---- notes: _parse_slice_arg / _cli_file refuse cleanly, never a traceback -----------------------------

def test_parse_slice_arg_defaults_to_task_kind():
    path, runner_built = cross._parse_slice_arg("path/to/file.md")
    assert path == "path/to/file.md"
    assert runner_built is True


def test_parse_slice_arg_reads_attended_kind():
    path, runner_built = cross._parse_slice_arg("path/to/file.md:attended")
    assert path == "path/to/file.md"
    assert runner_built is False


def test_parse_slice_arg_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        cross._parse_slice_arg("path/to/file.md:bogus")


def test_cli_file_refuses_cleanly_on_a_bad_slice_kind_no_traceback(tmp_path, capsys):
    rfc = tmp_path / "rfc.md"
    rfc.write_text(TECHNICAL_RFC_DRAFT)
    slice_path = tmp_path / "slice.md"
    slice_path.write_text(_slice_draft())
    rc = cross.main(["file", "--repo", REPO, "--who", "yr-pm[bot]", "--design", "x", "--review", "y",
                     "--seed", "pm-agent", "--technical-rfc", str(rfc),
                     "--slice", f"{slice_path}:bogus",
                     "--arch-result", str(tmp_path / "arch.json")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "bogus" in captured.err
