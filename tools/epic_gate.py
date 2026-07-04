#!/usr/bin/env python3
"""Epic-gate promotion engine (the standing-approval sweep).

`sweep_epics(*, gh=None, ...)` is the reusable core: one sweep of the org board that, for each **Ready
epic** carrying a valid standing-approval record, promotes the next open Task child in sub-issue order —
one slice in flight per epic, stopping on any trouble, leaving an accountable record on each promoted
child. This is the *promotion engine only*; self-close of a finished epic and stranded-claim detection are
separate tasks that extend this same tool.

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
"""
import json
import os
import subprocess
import sys

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
      comments(first: 100) { nodes { body } }
      subIssues(first: 100) {
        nodes {
          number
          state
          issueType { name }
          repository { nameWithOwner }
          projectItems(first: 20) {
            nodes {
              id
              project { number }
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


# --- the standing-approval record: a comment on the epic carrying the sentinel + both fields ----------
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


# --- writes (the runner's exact mechanisms) -----------------------------------------------------------
def _set_field(gh, item_id, field_id, opt):
    gh(["project", "item-edit", "--id", item_id, "--project-id", PROJECT_ID,
        "--field-id", field_id, "--single-select-option-id", opt])


def _comment(gh, repo, number, body):
    gh(["issue", "comment", str(number), "--repo", repo, "--body", body])


def _pi_node(subissue, project_number):
    """The child's project item for our board (project #project_number), or None if it isn't on the board."""
    for pi in ((subissue.get("projectItems") or {}).get("nodes") or []):
        if ((pi.get("project") or {}).get("number")) == project_number:
            return pi
    return None


def _process_epic(gh, epic, project_number, status_field_id, reason_field_id, status_opt, reason_opt):
    """Run the per-epic algorithm for one Ready epic; return a list of the actions taken."""
    owner, _, name = (epic["repo"] or "").partition("/")
    detail = _query(gh, ["api", "graphql", "-f", "query=" + EPIC_QUERY,
                         "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={epic['number']}"])
    issue = ((detail.get("repository") or {}).get("issue")) or {}
    comments = [(c or {}).get("body") or "" for c in ((issue.get("comments") or {}).get("nodes") or [])]
    children = (issue.get("subIssues") or {}).get("nodes") or []

    # (4) childless epic → do nothing (self-close is a separate task and also excludes childless epics).
    if not children:
        return []

    # (1) no valid approval record → raise Needs-info + stop; promote nothing. Idempotent: never re-raise
    #     (or re-comment) when the epic already carries the Reason this raise would set.
    if not _has_valid_approval(comments):
        if epic["reason"] != "Needs-info":
            _set_field(gh, epic["item_id"], reason_field_id, reason_opt["Needs-info"])
            _comment(gh, epic["repo"], epic["number"], _needs_info_body())
            return [{"epic": epic["number"], "action": "raise", "reason": "Needs-info"}]
        return []

    open_children = [c for c in children if (c.get("state") or "").upper() == "OPEN"]
    if not open_children:
        return []

    # (2) line busy / trouble → wait: any open child in flight or off-track blocks a new promotion.
    for c in open_children:
        pi = _pi_node(c, project_number)
        if _fv_name(pi and pi.get("status")) in BUSY_STATUS or _fv_name(pi and pi.get("reason")) in BUSY_REASON:
            return []

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
    _set_field(gh, pi["id"], status_field_id, status_opt["Ready"])
    _comment(gh, child_repo, first["number"], _promoted_body(epic["number"]))
    return [{"epic": epic["number"], "action": "promote", "child": first["number"]}]


def sweep_epics(*, gh=None, org=ORG, project_number=PROJECT_NUMBER,
                status_field_id=STATUS_FIELD_ID, reason_field_id=REASON_FIELD_ID,
                status_opt=None, reason_opt=None):
    """Run one sweep of the org board. For each OPEN, `Type=Feature`, `Status=Ready` epic (candidates,
    interleaved with no prioritization), apply the per-epic algorithm. Returns the list of actions taken.

    The sweep only ever *sets* Status/Reason and posts comments — it never clears a Reason (clearing is
    the human's explicit resume act), never builds, and never sets any Status but `Ready` (promotion).
    Standalone tasks and children of non-Ready epics are never visited, so never touched (cord-pull)."""
    gh = gh or _gh
    status_opt = status_opt or STATUS_OPT
    reason_opt = reason_opt or REASON_OPT

    board = _query(gh, ["api", "graphql", "-f", "query=" + BOARD_QUERY,
                        "-F", f"org={org}", "-F", f"project={project_number}"])
    nodes = (((board.get("organization") or {}).get("projectV2") or {}).get("items") or {}).get("nodes") or []

    actions = []
    for item in nodes:
        content = item.get("content") or {}
        if not content:                                                   # non-issue / draft item
            continue
        if (content.get("state") or "").upper() != "OPEN":                # epic not Ready-and-open → skip
            continue
        if ((content.get("issueType") or {}).get("name") or "").lower() != "feature":
            continue
        if _fv_name(item.get("status")) != "Ready":                       # cord-pull: only Ready epics
            continue
        epic = {
            "number": content["number"],
            "repo": (content.get("repository") or {}).get("nameWithOwner") or "",
            "item_id": item.get("id"),
            "reason": _fv_name(item.get("reason")),
        }
        actions += _process_epic(gh, epic, project_number, status_field_id, reason_field_id,
                                 status_opt, reason_opt)
    return actions


def main(argv=None):
    """CLI entrypoint: run one real sweep with the default `gh` runner and print what it did."""
    actions = sweep_epics()
    if not actions:
        print("epic-gate: nothing to do")
    for a in actions:
        if a["action"] == "promote":
            print(f"epic-gate: promoted #{a['child']} under epic #{a['epic']}")
        else:
            print(f"epic-gate: raised epic #{a['epic']} (Reason={a['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
