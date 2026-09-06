#!/usr/bin/env python3
"""cross.py — the crossing's deterministic gates and filing act (it-36 slice G, #472).

`cross(*, gh=None, vault=None, ...)` is the reusable, pure(ish) core — `design_gate.py sweep_designs`'s
own shape: every external is injected (`gh(argv) -> parsed JSON or text`, tolerant either way like
`epic_gate._query`/`design_gate._as_json`; `vault` an object carrying `.patch_frontmatter(path, key,
value)`, `tools/vault_api.VaultClient`'s own shape) so this is unit-testable with a `FakeGh` and a fake
vault client — no live network, no live vault, no worktree cut.

WHAT this does, in order (the acceptance criteria's own sequence): `check_links` on the technical-rfc
draft (its `source_*` frontmatter must resolve); `check_task` on every typed slice draft (self-
containedness, cited paths at `--base-ref`); the architecture review's verdict gates filing itself — a
`block` verdict refuses (the runner's own one-fold-retry lives upstream, in `tools/cross-runner.sh`; this
module never re-implements that loop) — a `fit`/`refit` verdict, its argued alternative(s) and an ADR
section are rendered directly onto the technical-rfc body (no separate vault write: only `crossed_to` is
stamped through the vault client, per the mandate). Only once every gate is clean does this file
anything: the epic (`gh issue create` + `updateIssue` to Type=Feature + `gh project item-add`), then one
sub-issue per slice (`gh issue create` + `addSubIssue`, `updateIssue` to Type=Task on runner-built
slices only — an attended slice stays untyped, the epic-gate's own `not-a-task` hold), the tool-emitted
`YR-EPIC-APPROVAL` (`who` = the App slug) on the epic, and `crossed_to` on the governing design doc
through the vault client.

A slice whose own draft carries a `Declares: external dependency <name>` or `Declares: data migration`
line (column 0, presence only, never inferred) still files normally — "nothing else waits on it" — but
also carries a `YR-ESCALATION: act=park why=...` comment, parking it for the owner's approving review.

The flip itself is `tools/promote.sh`'s machinery arm's job, not this module's — filing an epic at
Backlog is this module's whole mandate; promoting it to Ready is a separate act, on a separate trail
event (the triage `go` disposition licensing it through the engine's own transition-check).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))   # repo root: `tools.*` package imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))       # tools/ itself: bare sibling imports

import board_plumbing  # noqa: E402
import design_gate  # noqa: E402
import textutil  # noqa: E402
import vault_api  # noqa: E402
from tools.check_links import check_links as _check_links  # noqa: E402
from tools.check_task import check_task as _check_task  # noqa: E402

# --- escalation declarations: presence only, never inferred (spec criterion 12's own gotcha) -----------
_ESCALATION_RE = re.compile(r"^Declares:\s*(external dependency\b.*|data migration)\s*$", re.MULTILINE)


def escalation_declarations(draft_text: str) -> list[str]:
    """Every `Declares: external dependency <name>` / `Declares: data migration` line (column 0,
    verbatim, in declared order) — the whole declaration text after `Declares: `, never a boolean."""
    return [m.group(1).strip() for m in _ESCALATION_RE.finditer(draft_text)]


def _escalation_why(declaration: str) -> str:
    return "external-dependency" if declaration.lower().startswith("external dependency") else "data-migration"


def render_escalation_comment(declaration: str) -> str:
    return (
        f"YR-ESCALATION: act=park why={_escalation_why(declaration)}\n\n"
        f"This slice declares `{declaration}` — parked for the owner's approving review before it "
        "proceeds. Nothing else in the epic waits on it."
    )


# --- draft parsing: the templates' own filed-body shape (skills/factory/templates/) --------------------
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _h1_title(body: str, dash_prefix: str) -> str:
    m = _H1_RE.search(body)
    if not m:
        raise ValueError("draft is missing its H1 title heading")
    title = m.group(1).strip()
    marker = f"{dash_prefix} —"
    return title[len(marker):].strip() if title.startswith(marker) else title


_ISSUE_BODY_START_RE = re.compile(r"ISSUE BODY[^\n]*\n")
_ISSUE_BODY_END_RE = re.compile(r"\n<!--[^\n]*END ISSUE BODY")


def technical_rfc_issue_body(draft_text: str) -> tuple[str, str]:
    """(title, filed body) off a `skills/factory/templates/technical-rfc.md`-shaped draft: the
    frontmatter and the authoring scaffold below the airlock never reach the Issue — only the text
    between the template's own `ISSUE BODY` markers does (the template's own instruction, `:19-21`)."""
    _, body = textutil.split_frontmatter(draft_text)
    title = _h1_title(body, "Technical RFC")
    start = _ISSUE_BODY_START_RE.search(body)
    end = _ISSUE_BODY_END_RE.search(body, start.end()) if start else None
    if not start or not end:
        raise ValueError("technical-rfc draft is missing its ISSUE BODY markers")
    return title, body[start.end():end.start()].strip("\n")


_GOAL_RE = re.compile(r"^##\s+Goal\s*$", re.MULTILINE)
_TASK_FOOTER_RE = re.compile(r"\n-{3,}\s*\n\*Next stage:")


def task_issue_body(draft_text: str) -> tuple[str, str]:
    """(title, filed body) off a `skills/factory/templates/task.md`-shaped draft: from `## Goal`
    (the form's own first required field) to just before the authoring-aid footer — the frontmatter,
    the "Filed as" preamble, and the footer are never filed, exactly as the template says."""
    _, body = textutil.split_frontmatter(draft_text)
    title = _h1_title(body, "Task")
    start = _GOAL_RE.search(body)
    if not start:
        raise ValueError("task draft is missing its ## Goal heading")
    end = _TASK_FOOTER_RE.search(body, start.start())
    return title, body[start.start():(end.start() if end else len(body))].strip("\n")


# --- cross-draft's own combined output shape: one technical-rfc + N slices in one stage response
#     (tools/cross-runner.sh's `cross-draft` stage) — split into files the rest of the runner and
#     `cross()` above both read as plain paths, never a second parser for this shape --------------------
_TECH_RFC_BLOCK_RE = re.compile(
    r"^===TECHNICAL-RFC===[ \t]*\r?\n(.*?)\r?\n===END-TECHNICAL-RFC===[ \t]*$", re.DOTALL | re.MULTILINE)
_SLICE_BLOCK_RE = re.compile(
    r"^===SLICE[ \t]+(task|attended)===[ \t]*\r?\n(.*?)\r?\n===END-SLICE===[ \t]*$",
    re.DOTALL | re.MULTILINE)


def split_draft(raw_text: str) -> dict:
    """The cross-draft stage's raw stdout -> `{"technical_rfc": str, "slices": [{"kind", "body"}]}`.
    Raises ValueError (never a partial, silently-accepted result) when the technical-rfc block is
    missing or no slice block is found — a malformed stage output is a loud stop, `design_gate.py
    parse_arch_output`'s own discipline for a stage grammar."""
    m = _TECH_RFC_BLOCK_RE.search(raw_text)
    if not m:
        raise ValueError("cross-draft output is missing its ===TECHNICAL-RFC=== block")
    slices = [{"kind": kind, "body": body} for kind, body in _SLICE_BLOCK_RE.findall(raw_text)]
    if not slices:
        raise ValueError("cross-draft output names no ===SLICE task|attended=== blocks")
    return {"technical_rfc": m.group(1), "slices": slices}


# --- the architecture review: the SAME grammar design_gate.py's own arch stage produces (spec
#     criterion 12 at the crossing too) — rendered onto the technical-rfc body, never a separate vault
#     write (only `crossed_to` crosses through the vault client here) -------------------------------
def render_arch_section(arch_result: dict) -> str:
    alt_md = "\n".join(f"- {a}" for a in arch_result["alternatives"])
    return (
        "## Architecture review\n\n"
        f"**Verdict:** {arch_result['verdict']}\n\n"
        "**Alternatives considered:**\n"
        f"{alt_md}\n\n"
        "### ADR — architecture decision at the crossing\n\n"
        f"{(arch_result.get('findings_text') or '').strip()}\n"
    )


def render_approval_body(*, design: str, review: str, who: str) -> str:
    return (
        "YR-EPIC-APPROVAL\n"
        f"design: {design}\n"
        f"review: {review}\n"
        f"who: @{who}\n\n"
        "Filed and approved by the crossing (`tools/cross.py`), under the App identity: the cold "
        "technical-rfc review and the architecture review both cleared before this epic was filed."
    )


# --- the two deterministic gates, thin wrappers so the core stays injectable/testable -------------------
def gate_check_links(draft_text, *, vault_root, checker=None):
    checker = checker or _check_links
    return checker(draft_text, vault_root=pathlib.Path(vault_root), resolve_ref=None)


def gate_check_task(draft_text, *, repo_root, base_ref, checker=None):
    checker = checker or _check_task
    return checker(draft_text, repo_root=repo_root, base_ref=base_ref)


# --- issue-type resolution: repository.issueTypes, never a hardcoded org-specific id --------------------
_ISSUE_TYPES_QUERY = (
    "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){"
    "issueTypes(first:20){nodes{id name}}}}"
)


def _as_json(out):
    return out if isinstance(out, (dict, list)) else json.loads(out or "null")


def resolve_issue_type_ids(gh, repo: str) -> dict:
    """`{lowercased type name: node id}` for `repo` — the epic gets Type=Feature, a runner-built slice
    Type=Task; an attended slice is filed untyped by design (the epic-gate's own `not-a-task` hold)."""
    owner, _, name = repo.partition("/")
    data = _as_json(gh(["api", "graphql", "-f", f"query={_ISSUE_TYPES_QUERY}",
                       "-F", f"owner={owner}", "-F", f"name={name}"]))
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    nodes = (((data or {}).get("repository") or {}).get("issueTypes") or {}).get("nodes") or []
    return {(n.get("name") or "").lower(): n.get("id") for n in nodes if isinstance(n, dict) and n.get("id")}


# --- gh call shapes: issue create/view, updateIssue, addSubIssue, project item-add ----------------------
_UPDATE_ISSUE_MUTATION = (
    "mutation($id:ID!,$type:ID!){updateIssue(input:{id:$id,issueTypeId:$type}){issue{id}}}"
)
_ADD_SUB_ISSUE_MUTATION = (
    "mutation($issueId:ID!,$subIssueId:ID!){addSubIssue(input:{issueId:$issueId,subIssueId:$subIssueId})"
    "{issue{id}}}"
)


def _issue_number_from_create_output(out):
    text = (out or "").strip().splitlines()[-1].strip() if out else ""
    m = re.search(r"(\d+)\s*$", text)
    if not m:
        raise ValueError(f"cross: could not parse an issue number from gh output {text!r}")
    return int(m.group(1)), text


def _file_issue(gh, *, repo, title, body):
    out = gh(["issue", "create", "--repo", repo, "--title", title, "--body", body])
    number, url = _issue_number_from_create_output(out)
    node = _as_json(gh(["issue", "view", str(number), "--repo", repo, "--json", "id"]))
    return number, url, node["id"]


def _set_issue_type(gh, *, node_id, type_id):
    gh(["api", "graphql", "-f", f"query={_UPDATE_ISSUE_MUTATION}",
       "-F", f"id={node_id}", "-F", f"type={type_id}"])


def _add_sub_issue(gh, *, epic_node_id, slice_node_id):
    gh(["api", "graphql", "-f", f"query={_ADD_SUB_ISSUE_MUTATION}",
       "-F", f"issueId={epic_node_id}", "-F", f"subIssueId={slice_node_id}"])


def _add_to_project(gh, *, project_number, owner, url):
    gh(["project", "item-add", str(project_number), "--owner", owner, "--url", url])


def _comment(gh, *, repo, issue, body):
    gh(["issue", "comment", str(issue), "--repo", repo, "--body", body])


# --- the pure(ish) core ----------------------------------------------------------------------------------
def cross(*, gh, vault, technical_rfc_draft, slices, repo, who, design, review, arch_result,
          feature_type_id, task_type_id, owner=None, project_number=None,
          vault_doc_path=None, vault_root, repo_root=".", base_ref="origin/main",
          check_links_fn=None, check_task_fn=None):
    """Files the epic + its slices when — and only when — every gate is clean; writes nothing on any
    refusal (the promote.sh precedent: a refusal writes nothing).

    `slices`: `[{"draft": <raw text>, "runner_built": bool}, ...]`, in filing order. `arch_result`:
    `{"verdict", "alternatives", "findings_text"}` (`design_gate.parse_arch_output`'s own shape) — a
    `block` verdict refuses here; the runner's own one-fold-retry is upstream of this call, never
    re-implemented here. Returns a result dict; `ok: False` names the `stage` that refused."""
    owner = owner or repo.partition("/")[0]
    project_number = project_number if project_number is not None else board_plumbing.project_number()

    link_errors = gate_check_links(technical_rfc_draft, vault_root=vault_root, checker=check_links_fn)
    if link_errors:
        return {"ok": False, "stage": "check_links", "errors": link_errors}

    parsed_slices = []
    task_errors = {}
    for i, s in enumerate(slices):
        try:
            title, filed_body = task_issue_body(s["draft"])
        except ValueError as e:
            task_errors[i] = [str(e)]
            continue
        errs = gate_check_task(s["draft"], repo_root=repo_root, base_ref=base_ref, checker=check_task_fn)
        if errs:
            task_errors[i] = errs
            continue
        parsed_slices.append({
            "title": title, "body": filed_body,
            "runner_built": bool(s.get("runner_built", True)),
            "escalations": escalation_declarations(s["draft"]),
        })
    if task_errors:
        return {"ok": False, "stage": "check_task", "errors": task_errors}

    if arch_result.get("verdict") not in ("fit", "refit"):
        return {"ok": False, "stage": "arch", "errors": [f"verdict={arch_result.get('verdict')!r}"]}

    epic_title, epic_body_core = technical_rfc_issue_body(technical_rfc_draft)
    epic_body = epic_body_core + "\n\n" + render_arch_section(arch_result)

    epic_number, epic_url, epic_node_id = _file_issue(gh, repo=repo, title=epic_title, body=epic_body)
    _set_issue_type(gh, node_id=epic_node_id, type_id=feature_type_id)
    _add_to_project(gh, project_number=project_number, owner=owner, url=epic_url)

    slice_results = []
    for parsed in parsed_slices:
        s_number, s_url, s_node_id = _file_issue(gh, repo=repo, title=parsed["title"], body=parsed["body"])
        if parsed["runner_built"]:
            _set_issue_type(gh, node_id=s_node_id, type_id=task_type_id)
        _add_sub_issue(gh, epic_node_id=epic_node_id, slice_node_id=s_node_id)
        for declaration in parsed["escalations"]:
            _comment(gh, repo=repo, issue=s_number, body=render_escalation_comment(declaration))
        slice_results.append({
            "number": s_number, "url": s_url, "runner_built": parsed["runner_built"],
            "escalations": parsed["escalations"],
        })

    _comment(gh, repo=repo, issue=epic_number,
             body=render_approval_body(design=design, review=review, who=who))

    crossed_to = f"{repo}#{epic_number}"
    if vault_doc_path:
        vault.patch_frontmatter(vault_doc_path, "crossed_to", crossed_to)

    return {"ok": True, "epic_number": epic_number, "epic_url": epic_url,
            "slices": slice_results, "crossed_to": crossed_to}


# --- CLI -------------------------------------------------------------------------------------------------
def _gh(argv):
    import os
    import subprocess
    proc = subprocess.run([os.environ.get("GH_BIN", "gh"), *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _cli_check_links(argv):
    ap = argparse.ArgumentParser(description="check_links on a technical-rfc draft")
    ap.add_argument("file")
    ap.add_argument("--vault-root", required=True)
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    errors = gate_check_links(text, vault_root=args.vault_root)
    for e in errors:
        print(f"{args.file}: {e}")
    return 1 if errors else 0


def _cli_check_task(argv):
    ap = argparse.ArgumentParser(description="check_task on a slice draft")
    ap.add_argument("file")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--base-ref", default="origin/main")
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    errors = gate_check_task(text, repo_root=args.repo_root, base_ref=args.base_ref)
    for e in errors:
        print(f"{args.file}: {e}")
    return 1 if errors else 0


def _cli_escalations(argv):
    ap = argparse.ArgumentParser(description="list a slice draft's escalation declarations")
    ap.add_argument("file")
    args = ap.parse_args(argv)
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    print(json.dumps(escalation_declarations(text)))
    return 0


def _cli_split_draft(argv):
    ap = argparse.ArgumentParser(description="split the cross-draft stage's raw output into files")
    ap.add_argument("file")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    raw = pathlib.Path(args.file).read_text(encoding="utf-8")
    try:
        parsed = split_draft(raw)
    except ValueError as e:
        print(f"cross: split-draft failed: {e}", file=sys.stderr)
        return 1
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "technical-rfc.md").write_text(parsed["technical_rfc"], encoding="utf-8")
    manifest = []
    for i, s in enumerate(parsed["slices"], start=1):
        name = f"slice-{i}.md"
        (out_dir / name).write_text(s["body"], encoding="utf-8")
        manifest.append({"path": name, "kind": s["kind"]})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({"technical_rfc": "technical-rfc.md", "slices": manifest}))
    return 0


def _cli_resolve_types(argv):
    ap = argparse.ArgumentParser(description="resolve a repo's Issue Type node ids")
    ap.add_argument("--repo", required=True)
    args = ap.parse_args(argv)
    print(json.dumps(resolve_issue_type_ids(_gh, args.repo)))
    return 0


def _parse_slice_arg(raw):
    path, _, kind = raw.partition(":")
    kind = kind or "task"
    if kind not in ("task", "attended"):
        raise ValueError(f"--slice kind must be 'task' or 'attended', got {kind!r} ({raw!r})")
    return path, kind == "task"


def _cli_file(argv):
    ap = argparse.ArgumentParser(description="file the epic and its slices, gated (it-36 slice G)")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--owner", default=None)
    ap.add_argument("--who", required=True, help="the App slug (YR_GH_APP_SLUG)")
    ap.add_argument("--design", required=True, help="the governing design's name")
    ap.add_argument("--review", required=True, help="the cold technical-rfc review's attestation")
    ap.add_argument("--technical-rfc", required=True)
    ap.add_argument("--slice", dest="slices", action="append", default=[],
                    metavar="PATH[:task|:attended]",
                    help="repeatable; 'task' (default) types the filed slice Type=Task, "
                         "'attended' files it untyped")
    ap.add_argument("--arch-result", required=True, help="path to the arch stage's parsed JSON")
    ap.add_argument("--vault-doc", default=None, help="the governing design doc's REST-relative path")
    ap.add_argument("--vault-root", default=None)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--base-ref", default="origin/main")
    args = ap.parse_args(argv)

    technical_rfc_draft = pathlib.Path(args.technical_rfc).read_text(encoding="utf-8")
    slices = []
    for raw in args.slices:
        path, runner_built = _parse_slice_arg(raw)
        slices.append({"draft": pathlib.Path(path).read_text(encoding="utf-8"), "runner_built": runner_built})
    arch_result = json.loads(pathlib.Path(args.arch_result).read_text())

    type_ids = resolve_issue_type_ids(_gh, args.repo)
    feature_type_id = type_ids.get("feature")
    task_type_id = type_ids.get("task")
    if not feature_type_id or (any(s["runner_built"] for s in slices) and not task_type_id):
        print(f"cross: could not resolve this repo's Issue Type ids (found: {sorted(type_ids)})",
              file=sys.stderr)
        return 1

    vault_root = args.vault_root or design_gate.VAULT_ROOT
    result = cross(gh=_gh, vault=vault_api.VaultClient(), technical_rfc_draft=technical_rfc_draft,
                   slices=slices, repo=args.repo, who=args.who, design=args.design, review=args.review,
                   arch_result=arch_result, feature_type_id=feature_type_id, task_type_id=task_type_id,
                   owner=args.owner, vault_doc_path=args.vault_doc, vault_root=vault_root,
                   repo_root=args.repo_root, base_ref=args.base_ref)
    print(json.dumps(result, indent=1))
    return 0 if result.get("ok") else 1


_SUBCOMMANDS = {
    "check-links": _cli_check_links,
    "check-task": _cli_check_task,
    "escalations": _cli_escalations,
    "resolve-types": _cli_resolve_types,
    "split-draft": _cli_split_draft,
    "file": _cli_file,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in _SUBCOMMANDS:
        return _SUBCOMMANDS[argv[0]](argv[1:])
    print(f"usage: cross.py <{'|'.join(_SUBCOMMANDS)}> ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
