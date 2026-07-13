#!/usr/bin/env python3
"""Epic-gate promotion engine (the standing-approval sweep).

`sweep_epics(*, gh=None, ...)` is the reusable core: one sweep of the org board that, for each **Ready
epic** carrying a valid standing-approval record, promotes the next open Task child in sub-issue order —
one slice in flight per epic, stopping on any trouble, leaving an accountable record on each promoted
child. The same per-epic pass also self-closes a Ready epic that has run out of open children — the
"finished, not-yet-closed" branch mutually exclusive with promotion/waiting. Stranded-claim detection is a
separate task that extends this same tool.

Design (mirrors `tools/dispatch.py`'s injectable seams so the whole decision tree is unit-testable with no
live `gh`): the one external — the `gh` CLI — is injected as a callable `gh(argv)` that runs a `gh` argv
and returns its stdout (parsed JSON *or* text; `_query` tolerates either). The default runs a real
subprocess; tests pass a fake that serves canned board / subIssues / comments JSON and records writes.

State lives on **native GitHub primitives only** (RFC 0003) — never labels or sidecar files:
  - Issue Type (`Task` / `Feature`); an epic is a `Feature` whose native `subIssues` are its children, and
    the `subIssues` connection order is the canonical promotion order (the board has no sub-issue order).
  - Two Projects single-select fields on org project #1 — Status and Reason — read/written exactly as the
    runner does (`gh project item-edit` / `gh issue comment`), reusing its field/option ids.

Authoritative reads: `gh project item-list` lags ~1 min, so every per-issue Status/Reason decision reads
that issue's own `projectItems` via issue-side GraphQL; promotion order reads the epic's `subIssues`.

CLI: `python -m epic_gate` / `epic_gate.py` runs one real sweep (default `gh`) and prints what it did —
for the `/sweep` dispatch route (separate task) to invoke, and for manual watched switch-on.

Stranded-claim detection (extends the same per-epic busy check): `tools/dev-runner.sh` claims a child
(`Status -> In Progress`) as its first act, then either opens a PR (-> In Review) or fails via
`fail_blocked` (-> `Reason=Blocked`). A hard death (signal/kill) between those two runs no handler,
leaving Status=In Progress with no Reason forever — neither in flight nor off-track, so the epic would
wait on it forever. The sweep raises such a claim (`Reason=Blocked` + an explanatory comment) once it has
stood past a staleness bound with no open PR and no live build holding `dispatch.py`'s lock for THIS
CLAIM'S OWN REPO (`dispatch.repo_lock_path`, imported as the sibling module — never a host-global lock).

Board intake (a third, independent pass over the same sweep): GitHub's Projects auto-add workflow is
one-per-project with a single repository/filter on this org's plan, so it can't serve a board spanning
every registered repo — an issue with no project item has no Status, invisible to the whole state
machine until someone manually adds it. `_sweep_intake` closes that gap: for each registered repo, every
OPEN issue (never a PR — `gh issue list` only returns issues) missing an item on our board gets one
native `item-add`; the board's own item-added workflow then sets Status=Backlog, so intake never writes
Status itself. `sweep_epics(repos=...)` takes the repo list as an explicit input (never filesystem-
discovered inside the pure core, mirroring `_sweep_debt_counters`'s own explicit `repos` param) — `main()`
supplies the real, workspace-discovered list via `_registered_repos()`.
"""
import datetime
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import tomllib

# sibling-module import (never `tools.dispatch`): production runs this file as a bare script
# (`tools/dispatch.py` spawns `tools/epic_gate.py` directly), which puts `tools/` at `sys.path[0]` — a
# `tools.`-prefixed import would only resolve under pytest's repo-root cwd and would crash the sweeper.
import dispatch

# --- Projects field config (reused from the runner; env-overridable, same live defaults) ---------------
ORG = os.environ.get("YR_ORG", "yellow-robots")
PROJECT_NUMBER = int(os.environ.get("PROJECT_NUMBER", "1"))
PROJECT_ID = os.environ.get("PROJECT_ID", "PVT_kwDOEEAo0M4Ba6Ls")
STATUS_FIELD_ID = os.environ.get("STATUS_FIELD_ID", "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw")
REASON_FIELD_ID = os.environ.get("REASON_FIELD_ID", "PVTSSF_lADOEEAo0M4Ba6LszhVzoxI")
STATUS_OPT = {
    "Backlog": os.environ.get("OPT_BACKLOG", "b863a902"),
    "Ready": os.environ.get("OPT_READY", "c85eb5c1"),
    "In Progress": os.environ.get("OPT_INPROGRESS", "14e415a3"),
    "In Review": os.environ.get("OPT_INREVIEW", "da2e6a49"),
    "Done": os.environ.get("OPT_DONE", "e614f531"),
}
REASON_OPT = {
    "Needs-info": os.environ.get("OPT_NEEDSINFO", "803a86fb"),
    "Blocked": os.environ.get("OPT_BLOCKED", "fe4d566c"),
}

# a child is "in flight / off-track" — the line is busy — while it holds any of these
BUSY_STATUS = {"Ready", "In Progress", "In Review"}
BUSY_REASON = {"Blocked", "Needs-info"}

# --- stranded-claim config: how long an unstable In-Progress claim is given before it's suspect. The
#     liveness probe reads dispatch.py's own per-repo lock (dispatch.repo_lock_path) — never a
#     host-global lock, whose retirement (epic #126 — per-repo locks + a global cap) would otherwise
#     make the probe never defer, raising false stranded claims against healthy long builds. -------------
STRANDED_AFTER_MIN = int(os.environ.get("STRANDED_AFTER_MIN", "45"))

# --- debt-round counter config: how many closed-as-completed feature epics (since the last closed debt
#     epic) it takes to raise the need for a round; per-repo override lives in the manifest (see
#     `_resolve_debt_threshold`) ---------------------------------------------------------------------
DEBT_ROUND_EVERY = int(os.environ.get("DEBT_ROUND_EVERY", "10"))

# --- GraphQL (fetch exactly what the algorithm needs; `first: 100` inherits the board-scale pagination
#     TODO in deploy/ready-query.graphql — acceptable at current board size) ----------------------------
BOARD_QUERY = """
query($org: String!, $project: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: 100) {
        nodes {
          id
          content { ... on Issue { number state issueType { name } repository { nameWithOwner } } }
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          reason: fieldValueByName(name: "Reason") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}
"""

EPIC_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      body
      comments(first: 100) { nodes { body } }
      subIssues(first: 100) {
        nodes {
          number
          state
          stateReason
          issueType { name }
          repository { nameWithOwner }
          projectItems(first: 20) {
            nodes {
              id
              project { number }
              status: fieldValueByName(name: "Status") {
                ... on ProjectV2ItemFieldSingleSelectValue { name updatedAt }
              }
              reason: fieldValueByName(name: "Reason") {
                ... on ProjectV2ItemFieldSingleSelectValue { name }
              }
            }
          }
        }
      }
    }
  }
}
"""


# --- debt-counter searches: repo-side, through the search index (search lags a close by minutes — an
#     accepted tradeoff for an idempotent reminder re-swept every few minutes; see `_sweep_debt_counters`)
DEBT_CLOSED_SEARCH_QUERY = """
query($q: String!, $cursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $cursor) {
    nodes {
      ... on Issue {
        number
        closedAt
        stateReason
        body
        issueType { name }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

DEBT_RAISE_SEARCH_QUERY = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 20) {
    nodes {
      ... on Issue {
        number
        body
        url
        projectItems(first: 20) {
          nodes {
            id
            project { number }
            status: fieldValueByName(name: "Status") {
              ... on ProjectV2ItemFieldSingleSelectValue { name }
            }
          }
        }
      }
    }
  }
}
"""


# --- default `gh` runner (the only real external; injected/overridden in tests) -----------------------
def _gh(argv):
    """Run `gh <argv...>`; return stdout text. Raises on a non-zero exit so a broken read/write is loud."""
    proc = subprocess.run(["gh", *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _query(gh, argv):
    """Run a `gh api graphql` read and return the unwrapped `data` object. Tolerates a callable that
    returns either parsed JSON or a JSON string, so a test fake can serve canned dicts directly."""
    out = gh(argv)
    obj = out if isinstance(out, (dict, list)) else json.loads(out)
    if isinstance(obj, dict) and "data" in obj:   # real `gh api graphql` wraps results under "data"
        obj = obj["data"]
    return obj or {}


def _fv_name(node):
    """The `.name` of a single-select field value node (or "" when the field is unset/null)."""
    return (node or {}).get("name") or ""


# --- stranded-claim detection helpers -------------------------------------------------------------
def _parse_dt(iso):
    """Parse a GraphQL DateTime scalar (e.g. `2026-07-03T14:32:10Z`) into a naive UTC datetime,
    comparable against the injectable `now()` clock."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1]
    s = s.split("+", 1)[0]
    if "." in s:
        s = s.split(".", 1)[0]
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")


def _utcnow():
    """Default `now` clock — real wall-clock UTC (tests inject a fake for deterministic ages)."""
    return datetime.datetime.utcnow()


def _default_build_lock_held(repo):
    """Default `build_lock_held` probe — a non-blocking `flock` test on `repo`'s OWN build lock
    (`dispatch.repo_lock_path`, the sibling module). Held (can't acquire) => a build for that repo is
    live. Absent/free => not. Never probes any other repo's lock, so a healthy long build on one repo
    never defers a stranded-claim raise on a different repo."""
    path = pathlib.Path(dispatch.repo_lock_path(repo))
    if not path.exists():
        return False
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:                                     # can't acquire => a build holds it
        return True
    finally:
        os.close(fd)


def _has_open_pr(gh, repo, child_number):
    """True iff an open PR exists whose head branch is `task/<child_number>-…` (the runner's
    `BRANCH="task/${ISSUE}-${SLUG}"`) — a completed build that only missed the In Review status write."""
    out = gh(["pr", "list", "--repo", repo, "--state", "open", "--json", "number,headRefName"])
    prs = out if isinstance(out, list) else json.loads(out)
    prefix = f"task/{child_number}-"
    return any((pr.get("headRefName") or "").startswith(prefix) for pr in prs)


def _is_stranded(gh, child, pi, now, build_lock_held, stranded_after_min):
    """True iff an In-Progress, Reason-less child's claim looks dead: its Status has stood unchanged
    past the staleness bound, no build currently holds THIS CHILD'S OWN REPO's build-lock, and no open
    PR exists for it. Returns `(is_stranded, age_minutes)` — the age is reported even when not (yet)
    stranded is False. `build_lock_held` is called with the claimed child's repo — never a host-global
    lock — so a healthy long build on one repo never defers a raise against a different repo's claim."""
    updated_at = ((pi or {}).get("status") or {}).get("updatedAt")
    if not updated_at:
        return False, 0
    age_min = (now() - _parse_dt(updated_at)).total_seconds() / 60.0
    if age_min <= stranded_after_min:
        return False, age_min
    repo = (child.get("repository") or {}).get("nameWithOwner") or ""
    if build_lock_held(repo):                           # a build for THIS repo is live — defer, don't raise
        return False, age_min
    if _has_open_pr(gh, repo, child["number"]):
        return False, age_min
    return True, age_min


def _stranded_body(age_min):
    return (
        f"YR-EPIC-GATE: stranded claim — In Progress {int(age_min)} min with no live build; likely a "
        "hard runner death (see `deploy/DISPATCH.md`). Recover: clear the Reason and re-Ready if the fix "
        "warrants."
    )


# --- the standing-approval record: a comment on the epic carrying the sentinel + both fields ----------
# --- the debt-epic ledger gate: a body sentinel marking a debt epic, and a comment-borne verdict record
DEBT_KIND_LINE = "YR-ITERATION-KIND: tech-debt"
LEDGER_MARKER = "YR-DEBT-LEDGER"
HOLD_MARKER = "YR-DEBT-HOLD"
DUE_MARKER = "YR-DEBT-DUE"


def _extract_field(body, key):
    """Pull `key`'s value from an approval comment. Accepts both the block form (`design: <v>` on its own
    line) and the one-line form (`... design=<v> review=<v>`), case-insensitive; returns "" if absent."""
    lowkey = key.lower()
    for line in body.splitlines():
        low = line.lower()
        idx = 0
        while True:
            pos = low.find(lowkey, idx)
            if pos == -1:
                break
            # the key must stand on a word boundary (start of line or preceded by whitespace)
            if pos == 0 or line[pos - 1].isspace():
                rest = line[pos + len(key):].lstrip()
                if rest[:1] in (":", "="):
                    val = rest[1:].strip()
                    # one-line form: cut the value off at the next `design`/`review` key
                    for other in ("design", "review"):
                        low_val = val.lower()
                        p = 0
                        while True:
                            q = low_val.find(other, p)
                            if q == -1:
                                break
                            after = val[q + len(other):].lstrip()
                            if (q == 0 or val[q - 1].isspace()) and after[:1] in (":", "="):
                                val = val[:q].strip()
                                break
                            p = q + len(other)
                    return val.strip()
            idx = pos + len(key)
    return ""


def _has_valid_approval(comments):
    """True iff ≥1 epic comment carries the `YR-EPIC-APPROVAL` sentinel with both `design` and `review`
    non-empty. The sweep trusts this named fact — it does not re-run the review."""
    for body in comments:
        if "YR-EPIC-APPROVAL" not in body:
            continue
        if _extract_field(body, "design") and _extract_field(body, "review"):
            return True
    return False


def _is_debt_epic(body):
    """True iff some line of the epic body, stripped, is exactly the debt-kind sentinel line — a substring
    test would also fire on a prose mention or a quoted/backticked example, so this checks whole lines."""
    return any(line.strip() == DEBT_KIND_LINE for line in (body or "").splitlines())


def _has_ledger_verdict(comments):
    """True iff some epic comment carries the `YR-DEBT-LEDGER` marker on its own line AND that same
    comment yields non-empty `items` and `net-lines` fields — the machine-checked pair."""
    for body in comments:
        if not any(line.strip() == LEDGER_MARKER for line in body.splitlines()):
            continue
        if _extract_field(body, "items") and _extract_field(body, "net-lines"):
            return True
    return False


# --- comment bodies (each raise tells the human to clear the epic's Reason to resume) ------------------
def _promoted_body(epic_number):
    return (
        "YR-AUTO-PROMOTED\n\n"
        f"Promoted **automatically** by the epic-gate under epic #{epic_number} "
        "(standing approval on record). This is the next open Task in sub-issue order — one slice in "
        "flight per epic. Promotion is automatic, not a human act."
    )


def _needs_info_body():
    return (
        "YR-EPIC-GATE: no valid standing-approval record found. The epic-gate needs a "
        "`YR-EPIC-APPROVAL` comment carrying non-empty `design:` and `review:` fields before it will "
        "promote any child — nothing was promoted. Add the record, then clear this epic's Reason to resume."
    )


def _not_a_task_body(child_number):
    return (
        f"YR-EPIC-GATE: next open child #{child_number} is not a Task — nested decompositions are out of "
        "scope; promotion stopped. The gate does not skip ahead to a later Task. Reorder so the next open "
        "child is a Task (or split it out), then clear this epic's Reason to resume."
    )


def _not_onboarded_body():
    return (
        "YR-EPIC-GATE: this repo is not onboarded — no `.yr/factory.toml` found at the base ref, so no "
        "build could ever run here. Onboarding (auth, onboarding the repo, arming) is attended, "
        "design-side work — never a slice the factory can pick up itself. Onboard the repo, then "
        "re-promote it (a standalone item) or clear the Reason (an epic) to resume."
    )


def _debt_hold_body():
    # The grammar sample deliberately never spells a field as a bare `key: value` line — that would
    # itself satisfy `_has_ledger_verdict` on the next tick (the hold comment "counting" as its own
    # missing verdict). Field names stay backticked, inline prose instead.
    return (
        f"{HOLD_MARKER}\n\n"
        "This is a debt epic with no open children left, but no valid ledger verdict is on record — the "
        f"epic-gate will not self-close it without one. A verdict is a comment carrying the {LEDGER_MARKER} "
        "marker line plus the fields `items`, `net-lines`, `files-removed`, `deps-removed`, `pins-added`, "
        "`suite-duration`, and `incidents` — naming `items:` and `net-lines:` as the machine-checked pair "
        "(both must be non-empty). Post the verdict and the next sweep self-closes this epic, or close it "
        "attended and clear the Reason."
    )


# --- writes (the runner's exact mechanisms) -----------------------------------------------------------
def _set_field(gh, item_id, field_id, opt):
    gh(["project", "item-edit", "--id", item_id, "--project-id", PROJECT_ID,
        "--field-id", field_id, "--single-select-option-id", opt])


def _comment(gh, repo, number, body):
    gh(["issue", "comment", str(number), "--repo", repo, "--body", body])


def _close_issue(gh, repo, number, reason):
    gh(["issue", "close", str(number), "--repo", repo, "--reason", reason])


def _epic_close_reason(children):
    """completed if any child closed as completed; not planned only if every child closed not-planned."""
    if any((c.get("stateReason") or "").upper() == "COMPLETED" for c in children):
        return "completed"
    return "not planned"


def _pi_node(subissue, project_number):
    """The child's project item for our board (project #project_number), or None if it isn't on the board."""
    for pi in ((subissue.get("projectItems") or {}).get("nodes") or []):
        if ((pi.get("project") or {}).get("number")) == project_number:
            return pi
    return None


# --- org-wide board intake: every OPEN issue in a registered repo gets a board item, idempotently -------
_REMOTE_RE = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")


def _repo_from_git_remote(path):
    """`owner/name` parsed from `path`'s `origin` remote URL (any of the git/ssh/https forms), or None on
    any failure (no `.git`, no `origin`, an unparseable URL) — never fatal to the rest of discovery."""
    try:
        proc = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"],
                               capture_output=True, text=True)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    m = _REMOTE_RE.search(proc.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _registered_repos(workspace=None):
    """Registered repos = subdirectories of `$YR_WORKSPACE` holding a `.yr/factory.toml` manifest — the
    same checkout convention `dev-runner.sh` resolves `BASE_REPO` from (`$YR_WORKSPACE/<name>`, see
    AGENTS.md), rather than a separately-maintained registry list: a repo is "registered" the moment it's
    onboarded (cloned + manifest added, onboarding steps 1-2), with no second place to remember to update.
    The tradeoff is that this requires every registered repo to be checked out on the host running the
    sweep — already true today, since onboarding clones to the workspace before anything else can run.
    Each directory's own git `origin` remote (not the directory name) gives the canonical `owner/name`; a
    directory with no manifest, no `.git`, or an unparseable remote is skipped, never fatal."""
    root = pathlib.Path(workspace) if workspace else pathlib.Path(
        os.environ.get("YR_WORKSPACE") or pathlib.Path(__file__).resolve().parent.parent.parent)
    if not root.is_dir():
        return []
    repos = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / ".yr" / "factory.toml").is_file():
            continue
        repo = _repo_from_git_remote(child)
        if repo:
            repos.append(repo)
    return repos


def _board_issue_keys(nodes):
    """`(repo, number)` for every Issue already present as an item on our board, in any state or Status —
    intake's idempotency check: an issue already on the board is never re-added, closed or open."""
    keys = set()
    for item in nodes:
        content = item.get("content") or {}
        number = content.get("number")
        if number is None:
            continue
        repo = (content.get("repository") or {}).get("nameWithOwner") or ""
        keys.add((repo, number))
    return keys


def _list_open_issues(gh, repo):
    """Every OPEN issue in `repo` — never a PR (`gh issue list` only ever returns issues, unlike `gh pr
    list`) and never closed (`--state open`), so both exclusions intake needs come from the read itself."""
    out = gh(["issue", "list", "--repo", repo, "--state", "open", "--json", "number,url", "--limit", "500"])
    return out if isinstance(out, list) else json.loads(out)


def _sweep_intake(gh, repos, board_nodes, *, project_number, org):
    """For each of `repos`: every OPEN issue missing an item on our board gets one native `item-add`. Sets
    no Status — the board's own item-added workflow does that (item-scoped, so it already covers every
    repo); intake only ever adds the item. A read failure on one repo (deleted repo, no access, …) is
    isolated as an `intake-error` action, never fatal to any other repo's intake."""
    on_board = _board_issue_keys(board_nodes)
    actions = []
    for repo in sorted(repos):
        try:
            issues = _list_open_issues(gh, repo)
        except Exception as exc:
            actions.append({"action": "intake-error", "repo": repo, "error": str(exc)})
            continue
        for issue in issues:
            number = issue.get("number")
            url = issue.get("url")
            if number is None or url is None or (repo, number) in on_board:
                continue
            gh(["project", "item-add", str(project_number), "--owner", org, "--url", url])
            actions.append({"action": "intake", "repo": repo, "issue": number})
    return actions


# --- the per-repo debt counter: closed-as-completed feature epics since the most recent closed debt epic
#     (the anchor), raising the need for a round exactly once at the threshold ------------------------
def _debt_repo_set(nodes):
    """Distinct `repository.nameWithOwner` over board items whose content is an Issue of Type Feature —
    any state, any Status. Reuses the content/type guards of the sweep's own board loop, without its
    OPEN/Ready filters: the counted-repo set is every repo that holds a feature epic on the board at all,
    live or finished."""
    repos = set()
    for item in nodes:
        content = item.get("content") or {}
        if not content:
            continue
        if ((content.get("issueType") or {}).get("name") or "").lower() != "feature":
            continue
        repo = (content.get("repository") or {}).get("nameWithOwner") or ""
        if repo:
            repos.add(repo)
    return repos


def _search_closed_feature_epics(gh, repo):
    """Every closed, Type=Feature issue on `repo`, paginated through the search index."""
    nodes = []
    cursor = None
    while True:
        argv = ["api", "graphql", "-f", "query=" + DEBT_CLOSED_SEARCH_QUERY,
                "-f", f"q=repo:{repo} is:issue state:closed type:Feature"]
        if cursor:
            argv += ["-f", f"cursor={cursor}"]
        data = _query(gh, argv)
        search = data.get("search") or {}
        nodes += search.get("nodes") or []
        page = search.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    return [n for n in nodes if ((n.get("issueType") or {}).get("name") or "").lower() == "feature"]


def _debt_anchor_and_countable(closed_epics):
    """The anchor (the debt-kind epic with the latest `closedAt`, any `stateReason`, or None when there
    isn't one) and the countable set (`stateReason == COMPLETED`, not debt-kind, closed after the anchor
    — all of them when there is no anchor). Nodes missing `closedAt` are skipped defensively."""
    dated = [(n, _parse_dt(n["closedAt"])) for n in closed_epics if n.get("closedAt")]
    anchor_node, anchor_dt = None, None
    for n, dt in dated:
        if _is_debt_epic(n.get("body") or "") and (anchor_dt is None or dt > anchor_dt):
            anchor_node, anchor_dt = n, dt
    countable = [
        n for n, dt in dated
        if (n.get("stateReason") or "").upper() == "COMPLETED"
        and not _is_debt_epic(n.get("body") or "")
        and (anchor_dt is None or dt > anchor_dt)
    ]
    return anchor_node, countable


# --- the onboarding admission wall: a repo with no `.yr/factory.toml` at the base ref can never build
#     (the runner's own config read would find nothing too, tools/dev-runner.sh:326-350) — the sweep
#     refuses to promote or leave dispatchable any Ready work headed for such a repo, fail-closed ---------
class ManifestProbeError(Exception):
    """Raised by `_repo_has_manifest` when every attempt at the contents-API probe fails for a reason
    other than a confirmed 404 (network error, 5xx, rate limit, timeout). Distinct from a plain `bool`
    result: the wall must not read this as either "onboarded" or "not onboarded" — the caller skips the
    item for this tick instead of guessing (issue #140)."""


# a couple of attempts, bounded backoff — the sweep must not stall on a dead network
_MANIFEST_PROBE_ATTEMPTS = 2
_MANIFEST_PROBE_BACKOFF_S = 2
_HTTP_404_RE = re.compile(r"\b404\b")


def _repo_has_manifest(gh, owner, name):
    """True/False iff `owner/name` definitively carries or lacks a `.yr/factory.toml` at its base ref (the
    default branch), read via the same contents-API pattern `_read_manifest_threshold` uses below. A
    confirmed HTTP 404 (the `gh` failure names the status in its message/stderr) is a real "absent" —
    False, same as always. Any other failure — network error, 5xx, rate limit, timeout — is transient: it
    is retried once with a short bounded backoff, and if it still fails, raises `ManifestProbeError`
    rather than guessing "missing". The wall never guesses a repo is onboarded, and now it never guesses a
    repo is NOT onboarded off a probe error either."""
    last_exc = None
    for attempt in range(_MANIFEST_PROBE_ATTEMPTS):
        try:
            gh(["api", f"repos/{owner}/{name}/contents/.yr/factory.toml",
                "-H", "Accept: application/vnd.github.raw"])
            return True
        except Exception as exc:
            if _HTTP_404_RE.search(str(exc)):
                return False
            last_exc = exc
            if attempt + 1 < _MANIFEST_PROBE_ATTEMPTS:
                time.sleep(_MANIFEST_PROBE_BACKOFF_S)
    raise ManifestProbeError(f"manifest probe failed for {owner}/{name}: {last_exc}") from last_exc


def _repo_onboarded(gh, repo, cache):
    """`_repo_has_manifest`, cached per `repo` in the sweep-local `cache` dict — so a board carrying many
    Ready items/epics on the same repo costs exactly one contents read for it per sweep. A confirmed
    answer (True/False) caches; a `ManifestProbeError` propagates uncached, so the next same-repo read
    this sweep (or the next sweep entirely) probes again instead of the failure freezing in as "absent"."""
    if repo not in cache:
        owner, _, name = repo.partition("/")
        cache[repo] = _repo_has_manifest(gh, owner, name)
    return cache[repo]


def _read_manifest_threshold(gh, repo):
    """`debt_round_every` from `repo`'s `.yr/factory.toml`, read via the gh contents API and parsed with
    stdlib `tomllib`. Raises on any missing/unreadable/unparseable/non-int/<1 value — the caller folds
    every such failure into the same default fallback."""
    owner, _, name = repo.partition("/")
    raw = gh(["api", f"repos/{owner}/{name}/contents/.yr/factory.toml",
              "-H", "Accept: application/vnd.github.raw"])
    text = raw if isinstance(raw, str) else json.dumps(raw)
    value = tomllib.loads(text).get("debt_round_every")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("invalid debt_round_every")
    return value


def _resolve_debt_threshold(gh, repo):
    """`DEBT_ROUND_EVERY` env beats `repo`'s own manifest key `debt_round_every` beats the default — any
    read, parse, or validity failure (missing, non-integer, below 1) falls back to the default, never an
    error or a skipped count."""
    if os.environ.get("DEBT_ROUND_EVERY") is not None:
        return DEBT_ROUND_EVERY
    try:
        return _read_manifest_threshold(gh, repo)
    except Exception:
        return DEBT_ROUND_EVERY


def _is_due_raise(body, repo, anchor_str):
    """True iff `body` carries the due marker on its own whole stripped line AND its own `repo:`/
    `anchor:` fields match the current (repo, anchor) key — a raise whose anchor differs is a *different*
    key, so it never suppresses a new raise."""
    if not any(line.strip() == DUE_MARKER for line in (body or "").splitlines()):
        return False
    return _extract_field(body, "repo") == repo and _extract_field(body, "anchor") == anchor_str


def _search_open_due_raise(gh, repo, anchor_str):
    """The existing open raise issue for (`repo`, `anchor_str`), or None."""
    argv = ["api", "graphql", "-f", "query=" + DEBT_RAISE_SEARCH_QUERY,
            "-f", f"q=repo:{repo} is:issue is:open {DUE_MARKER}"]
    data = _query(gh, argv)
    nodes = ((data.get("search") or {}).get("nodes")) or []
    for n in nodes:
        if _is_due_raise(n.get("body") or "", repo, anchor_str):
            return n
    return None


def _due_title(count, anchor_node):
    since = f"#{anchor_node['number']}" if anchor_node else "the first countable epic"
    return f"Tech-debt round due ({count} feature epics since {since})"


def _due_body(repo, anchor_str, count, counted_numbers):
    counted_str = ", ".join(f"#{n}" for n in counted_numbers)
    return (
        f"{DUE_MARKER}\n"
        f"repo: {repo}\n"
        f"anchor: {anchor_str}\n"
        f"count: {count}\n"
        f"counted: {counted_str}\n\n"
        f"A tech-debt round is due on **{repo}**: {count} feature epic(s) have closed as completed since "
        "the anchor above with no debt epic of their own. See `skills/factory/references/debt-rounds.md` "
        "for the round protocol. Promotion stays a human act — this issue only names the need."
    )


def _sweep_debt_counters(gh, repos, *, project_number, status_field_id, status_opt, org):
    """Per repo holding a Feature epic on the board: count closed-as-completed feature epics since the
    most recent closed debt epic (the anchor), and at the threshold raise the need exactly once — as a
    Type=Task Backlog issue keyed on (repo, anchor), never re-keyed on the count. Never sets Ready, never
    promotes, never closes, never clears a Reason.

    A failure on one repo is isolated: caught here, surfaced as a `debt-error` action, and never touches
    epic processing or any other repo's counting."""
    actions = []
    for r in sorted(repos):
        try:
            closed = _search_closed_feature_epics(gh, r)
            anchor_node, countable = _debt_anchor_and_countable(closed)
            threshold = _resolve_debt_threshold(gh, r)
            count = len(countable)
            anchor_str = f"#{anchor_node['number']}" if anchor_node else "none"

            if count < threshold:
                actions.append({"action": "debt-count", "repo": r, "count": count, "threshold": threshold})
                continue

            existing = _search_open_due_raise(gh, r, anchor_str)
            if existing is not None:
                pi = _pi_node(existing, project_number)
                if pi and pi.get("id"):
                    continue                       # already fully on the board -- never touched
                url = existing.get("url")
                if not url:
                    continue
                added = gh(["project", "item-add", str(project_number), "--owner", org,
                            "--url", url, "--format", "json"])
                added = added if isinstance(added, dict) else json.loads(added)
                item_id = added.get("id")
                if item_id:
                    _set_field(gh, item_id, status_field_id, status_opt["Backlog"])
                actions.append({"action": "debt-repair", "repo": r, "issue": existing.get("number")})
                continue

            counted_numbers = sorted(n["number"] for n in countable)
            title = _due_title(count, anchor_node)
            body = _due_body(r, anchor_str, count, counted_numbers)
            out = gh(["issue", "create", "--repo", r, "--title", title, "--type", "Task", "--body", body])
            url = out.strip() if isinstance(out, str) else out
            added = gh(["project", "item-add", str(project_number), "--owner", org,
                        "--url", url, "--format", "json"])
            added = added if isinstance(added, dict) else json.loads(added)
            item_id = added.get("id")
            if item_id:
                _set_field(gh, item_id, status_field_id, status_opt["Backlog"])
            actions.append({"action": "debt-raise", "repo": r, "count": count, "anchor": anchor_str})
        except Exception as exc:
            actions.append({"action": "debt-error", "repo": r, "error": str(exc)})
    return actions


def _process_epic(gh, epic, project_number, status_field_id, reason_field_id, status_opt, reason_opt,
                   now, build_lock_held, stranded_after_min, manifest_cache):
    """Run the per-epic algorithm for one Ready epic; return a list of the actions taken."""
    owner, _, name = (epic["repo"] or "").partition("/")
    detail = _query(gh, ["api", "graphql", "-f", "query=" + EPIC_QUERY,
                         "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={epic['number']}"])
    issue = ((detail.get("repository") or {}).get("issue")) or {}
    body = issue.get("body") or ""
    comments = [(c or {}).get("body") or "" for c in ((issue.get("comments") or {}).get("nodes") or [])]
    children = (issue.get("subIssues") or {}).get("nodes") or []

    # (4) childless epic → do nothing (an un-decomposed epic is never "finished").
    if not children:
        return []

    # (5) no open child left → the epic is finished. Ordinarily that self-closes natively and lets the
    #     board's native close→Done automation set Status — mutually exclusive with promoting/waiting
    #     below, and independent of the standing-approval record (that record only gates promotion). A
    #     *debt* epic (its body carries the tech-debt kind line) is the fail-closed exception: it holds for
    #     an attended close until a valid ledger verdict comment is on record, so the close-time duty
    #     (counting the ledger) can never be skipped by a same-tick self-close.
    open_children = [c for c in children if (c.get("state") or "").upper() == "OPEN"]
    if not open_children:
        if _is_debt_epic(body) and not _has_ledger_verdict(comments):
            already_held = any(
                any(line.strip() == HOLD_MARKER for line in c.splitlines()) for c in comments
            )
            if not already_held:
                _comment(gh, epic["repo"], epic["number"], _debt_hold_body())
            if epic["reason"] != "Needs-info":
                _set_field(gh, epic["item_id"], reason_field_id, reason_opt["Needs-info"])
            return [{"epic": epic["number"], "action": "hold"}]
        reason = _epic_close_reason(children)
        _close_issue(gh, epic["repo"], epic["number"], reason)
        return [{"epic": epic["number"], "action": "close", "reason": reason}]

    # (1) no valid approval record → raise Needs-info + stop; promote nothing. Idempotent: never re-raise
    #     (or re-comment) when the epic already carries the Reason this raise would set.
    if not _has_valid_approval(comments):
        if epic["reason"] != "Needs-info":
            _set_field(gh, epic["item_id"], reason_field_id, reason_opt["Needs-info"])
            _comment(gh, epic["repo"], epic["number"], _needs_info_body())
            return [{"epic": epic["number"], "action": "raise", "reason": "Needs-info"}]
        return []

    # (2) line busy / trouble → wait: any open child in flight or off-track blocks a new promotion.
    #     Along the way, catch a *stranded claim*: an In-Progress child with no Reason whose Status has
    #     stood past the staleness bound, with no open PR and no live build — a hard runner death left no
    #     handler to set Reason=Blocked, so the sweep raises it itself (still stops the line either way,
    #     since In Progress is already BUSY_STATUS; the raise is what makes it visibly off-track).
    stranded_actions = []
    for c in open_children:
        pi = _pi_node(c, project_number)
        status = _fv_name(pi and pi.get("status"))
        reason = _fv_name(pi and pi.get("reason"))
        if status == "In Progress" and not reason and pi and pi.get("id"):
            stranded, age_min = _is_stranded(gh, c, pi, now, build_lock_held, stranded_after_min)
            if stranded:
                child_repo = (c.get("repository") or {}).get("nameWithOwner") or epic["repo"]
                _set_field(gh, pi["id"], reason_field_id, reason_opt["Blocked"])
                _comment(gh, child_repo, c["number"], _stranded_body(age_min))
                stranded_actions.append({"epic": epic["number"], "action": "raise",
                                         "child": c["number"], "reason": "Blocked"})
        if status in BUSY_STATUS or reason in BUSY_REASON:
            return stranded_actions

    # (3) promote the first open child in sub-issue order.
    first = open_children[0]
    if ((first.get("issueType") or {}).get("name") or "").lower() != "task":
        # not a Task → raise Blocked + stop; do NOT skip ahead to a later Task. Idempotent as in (1).
        if epic["reason"] != "Blocked":
            _set_field(gh, epic["item_id"], reason_field_id, reason_opt["Blocked"])
            _comment(gh, epic["repo"], epic["number"], _not_a_task_body(first["number"]))
            return [{"epic": epic["number"], "action": "raise", "reason": "Blocked"}]
        return []

    pi = _pi_node(first, project_number)
    if not pi or not pi.get("id"):
        return []   # child not on the board yet → no item to edit; nothing to do this tick
    child_repo = (first.get("repository") or {}).get("nameWithOwner") or epic["repo"]

    # the admission wall: a child about to be promoted into an un-onboarded repo is a doomed build —
    # refuse before the Ready write. Bounces the EPIC (Needs-info + comment), never the child itself;
    # idempotent as in (1)/(4) above (never re-raise once the epic already carries this Reason). A probe
    # failure (non-404 — network/5xx/timeout, not a confirmed absence) is neither: skip this tick writing
    # nothing, so the next sweep re-probes instead of a false bounce (issue #140).
    try:
        onboarded = _repo_onboarded(gh, child_repo, manifest_cache)
    except ManifestProbeError as exc:
        return [{"epic": epic["number"], "action": "probe-error", "child": first["number"],
                 "error": str(exc)}]
    if not onboarded:
        if epic["reason"] != "Needs-info":
            _set_field(gh, epic["item_id"], reason_field_id, reason_opt["Needs-info"])
            _comment(gh, epic["repo"], epic["number"], _not_onboarded_body())
            return [{"epic": epic["number"], "action": "raise", "reason": "Needs-info"}]
        return []

    _set_field(gh, pi["id"], status_field_id, status_opt["Ready"])
    _comment(gh, child_repo, first["number"], _promoted_body(epic["number"]))
    return [{"epic": epic["number"], "action": "promote", "child": first["number"]}]


def sweep_epics(*, gh=None, org=ORG, project_number=PROJECT_NUMBER,
                status_field_id=STATUS_FIELD_ID, reason_field_id=REASON_FIELD_ID,
                status_opt=None, reason_opt=None,
                now=None, build_lock_held=None, stranded_after_min=None,
                repos=None):
    """Run one sweep of the org board. First, board intake over `repos` (see `_sweep_intake`). Then, for
    each OPEN, `Status=Ready` item: a `Type=Feature` epic (candidates, interleaved with no prioritization)
    gets the per-epic algorithm; any other OPEN Ready item — a standalone task, or an epic child already
    Ready — gets the admission wall directly (see below). Then run the per-repo debt counter over the
    distinct repositories holding any Type=Feature issue on the board (any state, any Status). Returns the
    list of actions taken.

    The sweep only ever *sets* Status/Reason and posts comments — it never clears a Reason (clearing is
    the human's explicit resume act), never builds, and never sets any Status but `Ready` (promotion) or,
    for the admission-wall bounce below, `Backlog`. Children of non-Ready epics are never visited, so
    never touched (cord-pull). The debt counter adds exactly three write kinds on top — create the raise
    issue, add it to the board, set its Status to Backlog — and still never sets Ready, never promotes,
    never closes, never clears a Reason. Intake adds exactly one write kind — `item-add` — and never
    touches Status/Reason at all.

    The admission wall (this task): un-onboarded work — a repo with no `.yr/factory.toml` at its base ref
    — is refused fail-closed instead of sailing to a doomed build. An epic child about to be promoted is
    probed BEFORE the Ready write; on a miss the EPIC bounces (Reason=Needs-info + a comment), the child
    is never promoted. An already-Ready standalone item bounces itself, off the Ready poll (the poll reads
    Status only): Status=Backlog + Reason=Needs-info + the same comment — the runner's own DoR bounce
    shape (`tools/dev-runner.sh:493`). Both are idempotent via the existing Reason-guard pattern, and the
    manifest probe is cached per repo within one sweep (`_repo_onboarded`).

    `now` (a `() -> datetime.datetime` clock), `build_lock_held` (a `(repo) -> bool` probe), and
    `stranded_after_min` are injectable for the stranded-claim check — each defaults to a real read.
    `repos` is the explicit list of registered repos to sweep for intake (never filesystem-discovered
    inside this core, mirroring the debt counter's own explicit `repos` param) — defaults to `()` (no
    intake) when omitted; `main()` supplies the real, workspace-discovered list."""
    gh = gh or _gh
    status_opt = status_opt or STATUS_OPT
    reason_opt = reason_opt or REASON_OPT
    now = now or _utcnow
    build_lock_held = build_lock_held or _default_build_lock_held
    stranded_after_min = STRANDED_AFTER_MIN if stranded_after_min is None else stranded_after_min
    repos = () if repos is None else repos

    board = _query(gh, ["api", "graphql", "-f", "query=" + BOARD_QUERY,
                        "-F", f"org={org}", "-F", f"project={project_number}"])
    nodes = (((board.get("organization") or {}).get("projectV2") or {}).get("items") or {}).get("nodes") or []

    manifest_cache = {}
    actions = _sweep_intake(gh, repos, nodes, project_number=project_number, org=org)
    for item in nodes:
        content = item.get("content") or {}
        if not content:                                                   # non-issue / draft item
            continue
        if (content.get("state") or "").upper() != "OPEN":                # not open → skip
            continue
        if _fv_name(item.get("status")) != "Ready":                       # cord-pull: only Ready items
            continue
        repo = (content.get("repository") or {}).get("nameWithOwner") or ""
        if ((content.get("issueType") or {}).get("name") or "").lower() == "feature":
            epic = {
                "number": content["number"],
                "repo": repo,
                "item_id": item.get("id"),
                "reason": _fv_name(item.get("reason")),
            }
            actions += _process_epic(gh, epic, project_number, status_field_id, reason_field_id,
                                     status_opt, reason_opt, now, build_lock_held, stranded_after_min,
                                     manifest_cache)
            continue

        # a standalone Ready item (not an epic): the admission wall applies directly, off the Ready poll
        # (deploy/ready-query.graphql reads Status only — a Reason-only bounce would leave it re-posted
        # and re-commented on every poll tick). Idempotent: once bounced its Status is no longer Ready,
        # so it drops out of this filter on the next sweep and is never re-commented.
        item_id = item.get("id")
        if not item_id:
            continue
        try:
            onboarded = _repo_onboarded(gh, repo, manifest_cache)
        except ManifestProbeError as exc:
            actions.append({"item": content["number"], "action": "probe-error", "error": str(exc)})
            continue
        if onboarded:
            continue
        _set_field(gh, item_id, status_field_id, status_opt["Backlog"])
        _set_field(gh, item_id, reason_field_id, reason_opt["Needs-info"])
        _comment(gh, repo, content["number"], _not_onboarded_body())
        actions.append({"item": content["number"], "action": "bounce-standalone", "reason": "Needs-info"})

    debt_repos = _debt_repo_set(nodes)
    actions += _sweep_debt_counters(gh, debt_repos, project_number=project_number,
                                    status_field_id=status_field_id, status_opt=status_opt, org=org)
    return actions


def main(argv=None):
    """CLI entrypoint: run one real sweep with the default `gh` runner over the workspace-discovered
    registered repos, and print what it did."""
    actions = sweep_epics(repos=_registered_repos())
    if not actions:
        print("epic-gate: nothing to do")
    for a in actions:
        if a["action"] == "intake":
            print(f"epic-gate: added {a['repo']}#{a['issue']} to the board")
        elif a["action"] == "intake-error":
            print(f"epic-gate: intake-error on {a['repo']}: {a.get('error', '')}")
        elif a["action"] == "promote":
            print(f"epic-gate: promoted #{a['child']} under epic #{a['epic']}")
        elif a["action"] == "close":
            print(f"epic-gate: closed epic #{a['epic']} (reason={a['reason']})")
        elif a["action"] == "hold":
            print(f"epic-gate: held epic #{a['epic']} (debt epic awaiting a ledger verdict)")
        elif a["action"] == "bounce-standalone":
            print(f"epic-gate: bounced #{a['item']} to Backlog/Needs-info (repo not onboarded)")
        elif a["action"] == "probe-error" and "child" in a:
            print(f"epic-gate: probe failure under epic #{a['epic']} on child #{a['child']} — "
                  f"skipped, will re-probe next sweep: {a.get('error', '')}")
        elif a["action"] == "probe-error":
            print(f"epic-gate: probe failure on #{a['item']} — "
                  f"skipped, will re-probe next sweep: {a.get('error', '')}")
        elif a["action"] == "raise" and "child" in a:
            print(f"epic-gate: raised stranded child #{a['child']} under epic #{a['epic']} "
                  f"(Reason={a['reason']})")
        elif a["action"] == "debt-count":
            print(f"epic-gate: debt-count {a['repo']} = {a['count']}/{a['threshold']}")
        elif a["action"] == "debt-raise":
            print(f"epic-gate: raised a tech-debt round for {a['repo']} "
                  f"(count={a['count']}, anchor={a['anchor']})")
        elif a["action"] == "debt-repair":
            print(f"epic-gate: repaired tech-debt raise #{a['issue']} onto the board for {a['repo']}")
        elif a["action"] == "debt-error":
            print(f"epic-gate: debt-error on {a['repo']}: {a.get('error', '')}")
        else:
            print(f"epic-gate: raised epic #{a['epic']} (Reason={a['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
