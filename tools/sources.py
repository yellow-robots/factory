#!/usr/bin/env python3
"""sources.py — the enforcement layer's ONLY I/O (it-30, the process model; model-design § sources).

Every fetch a predicate needs lives here as a bounded, best-effort function returning
`(ok: bool, payload | reason: str)`. Predicates are pure functions over what a source fetched
(tools/predicates.py imports nothing from here); the engine (tools/process.py) fetches through this
module and hands the payloads down. Removing the fetch from the judges is the design's root-cause
fix for one-grammar-three-implementations — a judge with nothing to parse until it is handed a
payload cannot re-implement the read quietly.

Contract: no function raises; a failure is `(False, "<what could not be read>")`. Timeouts are
per-call and bounded. The test suite stubs at this seam.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

GH_TIMEOUT = int(os.environ.get("YR_WALL_GH_TIMEOUT", "20"))


def _run(argv: list[str], timeout: int = GH_TIMEOUT) -> tuple[bool, str]:
    if argv and argv[0] == "gh":
        argv = [os.environ.get("GH_BIN", "gh"), *argv[1:]]  # the callers' stub seam (promote.sh, tests)
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"{argv[0]}: {e.__class__.__name__}"
    if out.returncode != 0:
        return False, (out.stderr or out.stdout or f"{argv[0]}: exit {out.returncode}").strip()[:200]
    return True, out.stdout


def issue_trail(repo: str, issue: str) -> tuple[bool, list[str]] | tuple[bool, str]:
    """The issue body plus every comment body, as a list of texts (record fields must be complete
    within ONE text, so texts are never joined)."""
    ok, out = _run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body,comments"])
    if not ok:
        return False, out
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"issue-trail unparseable: {e}"
    texts = [data.get("body") or ""]
    for c in data.get("comments") or []:
        texts.append(c.get("body") or "" if isinstance(c, dict) else str(c))
    return True, texts


def issue_trail_timed(repo: str, issue: str) -> tuple[bool, list] | tuple[bool, str]:
    """The trail as (ISO-timestamp, text) pairs — the body stamped with the issue's createdAt, each
    comment with its own. The `window = "since-store-change"` guard compares these against the
    store's change clock; both sides are GitHub ISO-8601 UTC strings, so lexicographic order is
    chronological order."""
    ok, out = _run(["gh", "issue", "view", str(issue), "--repo", repo,
                    "--json", "body,createdAt,comments"])
    if not ok:
        return False, out
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"issue-trail unparseable: {e}"
    rows = [(data.get("createdAt") or "", data.get("body") or "")]
    for c in data.get("comments") or []:
        if isinstance(c, dict):
            rows.append((c.get("createdAt") or "", c.get("body") or ""))
        else:
            rows.append(("", str(c)))
    return True, rows


def pr_trail(repo: str, pr: str) -> tuple[bool, list[str]] | tuple[bool, str]:
    ok, out = _run(["gh", "pr", "view", str(pr), "--repo", repo, "--json", "body,comments"])
    if not ok:
        return False, out
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"pr-trail unparseable: {e}"
    texts = [data.get("body") or ""]
    for c in data.get("comments") or []:
        texts.append(c.get("body") or "" if isinstance(c, dict) else str(c))
    return True, texts


def board_item(item_id: str) -> tuple[bool, dict] | tuple[bool, str]:
    """The ProjectV2 item fronting an issue: Status/Reason values, updatedAt, and the issue it
    fronts (repo + number) so trail guards can route."""
    query = (
        "query($id:ID!){node(id:$id){... on ProjectV2Item{updatedAt "
        "fieldValues(first:20){nodes{... on ProjectV2ItemFieldSingleSelectValue{name field{... on "
        "ProjectV2SingleSelectField{name}}}}} "
        "content{... on Issue{number issueType{name} repository{nameWithOwner}}}}}}"
    )
    ok, out = _run(["gh", "api", "graphql", "-f", f"query={query}", "-F", f"id={item_id}"])
    if not ok:
        return False, out
    try:
        node = json.loads(out)["data"]["node"] or {}
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        return False, f"board-item unparseable: {e}"
    fields = {}
    for fv in ((node.get("fieldValues") or {}).get("nodes") or []):
        f = (fv or {}).get("field") or {}
        if f.get("name"):
            fields[f["name"]] = fv.get("name") or ""
    content = node.get("content") or {}
    return True, {
        "status": fields.get("Status", ""),
        "reason": fields.get("Reason", ""),
        "itype": ((content.get("issueType") or {}).get("name")) or "",
        "updatedAt": node.get("updatedAt") or "",
        "repo": ((content.get("repository") or {}).get("nameWithOwner")) or "",
        "issue": str(content.get("number") or ""),
    }


def issue_board_position(repo: str, issue: str) -> tuple[bool, dict] | tuple[bool, str]:
    """Status/Reason/type for an issue addressed by repo+number (the scope a trail act carries).
    Mirrors board_plumbing's proven per-issue read shape (issueType + projectItems via
    fieldValueByName) AND its selection rule — the node whose project number matches the board's
    (cited from the one home, never copied): a first-item-any-project read would let a foreign
    board's item answer for the Dev board's state (the #436 review's finding)."""
    import board_plumbing
    owner, _, name = repo.partition("/")
    query = (
        "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){"
        "issue(number:$number){issueType{name} projectItems(first:20){nodes{"
        "project{number} "
        'status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}} '
        'reason: fieldValueByName(name:"Reason"){... on ProjectV2ItemFieldSingleSelectValue{name}}'
        "}}}}}"
    )
    ok, out = _run(["gh", "api", "graphql", "-f", f"query={query}", "-F", f"owner={owner}",
                    "-F", f"name={name}", "-F", f"number={issue}"])
    if not ok:
        return False, out
    try:
        node = json.loads(out or "{}")["data"]["repository"]["issue"] or {}
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        return False, f"board position unparseable: {e}"
    items = ((node.get("projectItems") or {}).get("nodes")) or []
    wanted = board_plumbing.project_number()
    matched = [i for i in items if ((i.get("project") or {}).get("number")) == wanted]
    if not matched:
        return False, f"no item on project #{wanted} fronts this issue"
    it = matched[0]
    return True, {"status": ((it.get("status") or {}).get("name")) or "",
                  "reason": ((it.get("reason") or {}).get("name")) or "",
                  "itype": ((node.get("issueType") or {}).get("name")) or ""}


def pr_state(repo: str, pr: str) -> tuple[bool, dict] | tuple[bool, str]:
    ok, out = _run(["gh", "pr", "view", str(pr), "--repo", repo,
                    "--json", "state,reviewDecision,mergedAt"])
    if not ok:
        return False, out
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"pr-state unparseable: {e}"
    return True, data


def vault_doc(path: Path) -> tuple[bool, str]:
    try:
        return True, Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return False, f"vault doc unreadable: {e}"


def manifest_at_base_tip(repo_dir: Path, base_ref: str = "origin/main") -> tuple[bool, str]:
    """The manifest read from the base ref's tip — the merge evaluator's own contract, inherited."""
    ok, out = _run(["git", "-C", str(repo_dir), "show", f"{base_ref}:.yr/factory.toml"])
    return (True, out) if ok else (False, out)


def host_file(path: Path) -> tuple[bool, bool]:
    """Existence of a host file (the merge sentinel). Never raises; existence is the payload."""
    try:
        return True, Path(path).exists()
    except OSError as e:
        return False, str(e)  # type: ignore[return-value]
