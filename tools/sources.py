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
import re
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


def pr_trail_texts_from_json(data: dict) -> list[str]:
    """The pure half of `pr_trail`: an already-fetched `body,comments` JSON object -> the body plus
    every comment body, as a list of texts. Shared with `pr_usage`/`pr_usage_from_texts` (and any
    caller that fetches this same JSON through an injected `gh`, e.g. tools/design_gate.py's own
    FakeGh-testable sweep) so the one parse lives here, never cloned."""
    texts = [data.get("body") or ""]
    for c in data.get("comments") or []:
        texts.append(c.get("body") or "" if isinstance(c, dict) else str(c))
    return texts


def pr_trail(repo: str, pr: str) -> tuple[bool, list[str]] | tuple[bool, str]:
    ok, out = _run(["gh", "pr", "view", str(pr), "--repo", repo, "--json", "body,comments"])
    if not ok:
        return False, out
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"pr-trail unparseable: {e}"
    return True, pr_trail_texts_from_json(data)


def triage_rows_from_json(data: dict) -> list[tuple[str, str]]:
    """The pure half of `triage_surface`: an already-fetched `body,comments` JSON object -> `(author
    login, text)` pairs — the issue body first (author `""`; GitHub exposes no comparable author
    query for the body itself, so it can never satisfy an owner-only reader) then each comment, in
    the trail's own chronological order. Shared with `tools/design_gate.py`'s FakeGh-testable sweep,
    which fetches the same JSON through its own injected `gh` rather than this module's subprocess."""
    rows = [("", data.get("body") or "")]
    for c in data.get("comments") or []:
        if isinstance(c, dict):
            login = ((c.get("author") or {}).get("login")) or ""
            rows.append((login, c.get("body") or ""))
        else:
            rows.append(("", str(c)))
    return rows


def triage_surface(repo: str, issue: str) -> tuple[bool, list[tuple[str, str]]] | tuple[bool, str]:
    """`issue_trail`'s contract (repo+issue -> trail texts) widened to also carry each comment's
    author login: a `YR-TRIAGE` disposition (records.toml) is trusted only when it rides a comment
    whose author is `YR_OWNER_LOGIN` — the design sweep's own read, human-only by the record's own
    grammar."""
    ok, out = _run(["gh", "issue", "view", str(issue), "--repo", repo, "--json", "body,comments"])
    if not ok:
        return False, out
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"triage-surface unparseable: {e}"
    return True, triage_rows_from_json(data)


def pr_usage_from_texts(texts: list[str]) -> tuple[bool, dict] | tuple[bool, str]:
    """The pure half of `pr_usage`: an already-fetched PR trail (`pr_trail_texts_from_json`'s own
    shape) -> the `### dev-runner usage` comment's fenced ```json summary block (tools/stage_usage.py
    `render_summary_comment`, :119-144), re-priced into a per-stage weighted total and the true-dollar
    shadow cost — the same weights/pricing tools/ledger.py's own `build_ledger_row` uses (census
    weights, price is $/Mtok, /1_000_000 for true dollars). The LAST such comment in the trail wins
    (a re-run posts a fresh one; the newest is authoritative). False when no comment carries the
    block, or its JSON is unparseable."""
    import registry
    import stage_usage
    for body in reversed(texts):
        i = body.find("```json") if "### dev-runner usage" in body else -1
        if i < 0:
            continue
        rest = body[i + len("```json"):]
        j = rest.find("```")
        if j < 0:
            continue
        try:
            summary = json.loads(rest[:j])
        except (json.JSONDecodeError, ValueError):
            continue
        reg = registry.load()
        stages = summary.get("stages") or []
        cost_usd = 0.0
        for s in stages:
            weighted = round(sum(int(s.get(k) or 0) * w
                                 for k, w in stage_usage.WEIGHTED_TOTAL_WEIGHTS.items()))
            price = registry.price_for_id(reg, s.get("model"))
            if price is not None:
                cost_usd += weighted * price
        cost_usd /= 1_000_000
        return True, {"stages": stages, "weighted_total": summary.get("weighted_total"),
                      "cost_usd": cost_usd}
    return False, "no dev-runner usage comment found"


def pr_usage(repo: str, pr: str) -> tuple[bool, dict] | tuple[bool, str]:
    """`pr_usage_from_texts` over a freshly-fetched PR trail — the design sweep's cost-per-PR input
    (the seed pack's cost estimate: the mean of a repo's recent runner PRs' `cost_usd`, times the
    seed's own effort factor)."""
    ok, texts = pr_trail(repo, pr)
    if not ok:
        return False, texts
    return pr_usage_from_texts(texts)


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


def origin_repo(cwd=None) -> tuple[bool, str]:
    """The owner/name of the current checkout's `origin` — the repo scope a git act carries
    (it-31 slice 5). Bounded like every fetch; never raises."""
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                             text=True, timeout=5, cwd=str(cwd) if cwd else None)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if out.returncode != 0:
        return False, (out.stderr or "no origin remote").strip()
    url = out.stdout.strip()
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return (True, m.group(1)) if m else (False, f"origin url unparseable: {url}")


def pr_for_branch(repo: str, branch: str) -> tuple[bool, str]:
    """The number of the open PR whose head is `branch` — the routable trail a shared-branch
    push's instruction record lives on (it-31 slice 5)."""
    ok, out = _run(["gh", "pr", "list", "--repo", repo, "--head", branch, "--state", "open",
                    "--json", "number", "--limit", "2"])
    if not ok:
        return False, out
    try:
        prs = json.loads(out or "[]")
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"pr-for-branch unparseable: {e}"
    if not prs:
        return False, "no open PR fronts this branch"
    if len(prs) > 1:
        return False, "two open PRs front this branch — ambiguous route, fail-closed"
    return True, str(prs[0].get("number") or "")


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


def releases(repo: str) -> tuple[bool, list[str]] | tuple[bool, str]:
    """The repo's GitHub Releases as one text per Release — tag name line + body (the YR-RELEASE
    record rides the body; fields must be complete within ONE text, so texts are never joined).
    Paged explicitly: `--paginate` concatenates top-level arrays across pages, which a single
    json.loads cannot parse (the slice-7 review) — the page loop is the comment fetcher's own
    discipline. Bounded like every fetcher; the walk tooling and the bench read this surface."""
    texts: list[str] = []
    page = 1
    while True:
        ok, out = _run(["gh", "api", f"repos/{repo}/releases",
                        "-X", "GET", "-f", "per_page=100", "-f", f"page={page}"],
                       timeout=GH_TIMEOUT)
        if not ok:
            return False, out
        try:
            data = json.loads(out or "[]")
        except (json.JSONDecodeError, ValueError) as e:
            return False, f"releases unparseable: {e}"
        if not isinstance(data, list):
            return False, "releases unparseable: not a list"
        texts.extend(f"{r.get('tag_name') or ''}\n{r.get('body') or ''}"
                     for r in data if isinstance(r, dict))
        if len(data) < 100:
            return True, texts
        page += 1
