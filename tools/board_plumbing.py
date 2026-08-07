#!/usr/bin/env python3
"""tools/board_plumbing.py — the one home for the board's plumbing (RFC 0003).

Every board identifier lives here, once: the project number, the project id, the two single-select field
ids (Status / Reason), and the seven status/reason option ids. Each is resolved by ITS OWN function
below — the environment-variable override beats the shipped default, and that resolution lives here and
nowhere else. Both languages that touch the board read from this one home: the Python consumers
(`tools/epic_gate.py`, and this module's own operations) import it; the shell consumers
(`tools/dev-runner.sh`, `tools/promote.sh`, `tools/watch_build.sh`, `tools/board.sh`) reach it through
this module's CLI (`sh-exports` / `read-issue` / `set-field`) instead of restating any default.

Two operations, one implementation each — the two that were hand-rolled at every board-touching site:

  - `set_field(gh, item_id, field_id, opt=None)` — the field write, `gh project item-edit …` with
    `--single-select-option-id <opt>` or, when `opt` is None, the `--clear` variant. Used by all four of
    today's write sites (the runner's Status/Reason setters and its Reason clear, the epic-gate's write,
    the promote flip).
  - `select_project_item(nodes, …)` / `read_issue_item(gh, …)` — the per-issue project-item read and its
    selection rule (the node whose project number matches the configured board). Used by all three of
    today's per-issue reads (the sweep's per-child selection, promote's read, watch's read). This is NOT
    the runner's board-wide `gh project item-list` read, nor `board.sh`'s org-wide items query — those are
    deliberately different reads and stay where they are.

`gh` is always injected as a callable running a gh argv (production passes `_gh`), so the write and the
read are unit-testable with no live `gh` — the same seam `tools/dispatch.py` / `tools/epic_gate.py` use.

Reload/override note: a consumer that must re-read the environment on its OWN `importlib.reload` (the
epic gate, whose pin reloads it alone) binds through the FUNCTIONS here, which read `os.environ` live —
never through the module-level snapshots below, which are frozen at this module's own import.

The wall-11 guard and the option-id half. A guard reading `tools/` and `tests/` can soundly cap the three
PREFIXED identifiers — `PROJECT_ID` (a `PVT_…` token) and the two field ids (`PVTSSF_…` tokens) — to this
one home: their prefixes make a tree-wide predicate unambiguous. No sound guard is expressible for the
seven option-id literals: they are bare eight-character hexadecimal tokens, indistinguishable from the
short commit hashes that appear in comments and test fixtures, so any pattern that matched them would
collide. A guard over the option-id half would become possible only if those ids gained a distinguishing
prefix (a schema change, out of scope) or a declared registry the tree could diff against; absent either,
the option-id half is left unguarded by design, and this paragraph is that recorded impossibility.
"""
import argparse
import json
import os
import subprocess
import sys


# --- the identifiers: env override beats default, resolved HERE and nowhere else ----------------------
def project_number():
    return int(os.environ.get("PROJECT_NUMBER", "1"))


def project_id():
    return os.environ.get("PROJECT_ID", "PVT_kwDOEEAo0M4Ba6Ls")


def status_field_id():
    return os.environ.get("STATUS_FIELD_ID", "PVTSSF_lADOEEAo0M4Ba6LszhVuZlw")


def reason_field_id():
    return os.environ.get("REASON_FIELD_ID", "PVTSSF_lADOEEAo0M4Ba6LszhVzoxI")


def status_opt():
    return {
        "Backlog": os.environ.get("OPT_BACKLOG", "b863a902"),
        "Ready": os.environ.get("OPT_READY", "c85eb5c1"),
        "In Progress": os.environ.get("OPT_INPROGRESS", "14e415a3"),
        "In Review": os.environ.get("OPT_INREVIEW", "da2e6a49"),
        "Done": os.environ.get("OPT_DONE", "e614f531"),
    }


def reason_opt():
    return {
        "Needs-info": os.environ.get("OPT_NEEDSINFO", "803a86fb"),
        "Blocked": os.environ.get("OPT_BLOCKED", "fe4d566c"),
    }


# module-level snapshots (resolved at THIS module's import; a reload of this module re-reads the
# environment). A consumer needing a fresh read on its own reload calls the functions above instead.
PROJECT_NUMBER = project_number()
PROJECT_ID = project_id()
STATUS_FIELD_ID = status_field_id()
REASON_FIELD_ID = reason_field_id()
STATUS_OPT = status_opt()
REASON_OPT = reason_opt()

# the env-var name of every board identifier, in one tuple, so a consumer that must enumerate them (the
# spawn-environment allowlist in tools/dispatch.py) derives the names here — adding an identifier is one
# edit, made here.
IDENTIFIER_ENV_NAMES = (
    "PROJECT_NUMBER", "PROJECT_ID", "STATUS_FIELD_ID", "REASON_FIELD_ID",
    "OPT_BACKLOG", "OPT_READY", "OPT_INPROGRESS", "OPT_INREVIEW", "OPT_DONE",
    "OPT_NEEDSINFO", "OPT_BLOCKED",
)


# --- default `gh` runner (the only real external; injected/overridden in tests) -----------------------
def _gh(argv):
    """Run `<GH_BIN> <argv…>`; return stdout text. Raises on a non-zero exit so a broken read/write is
    loud (the shell callers turn that into their own `die`/best-effort warning)."""
    gh_bin = os.environ.get("GH_BIN", "gh")
    proc = subprocess.run([gh_bin, *argv], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


# --- the one field write (the runner's exact `gh project item-edit` mechanism) ------------------------
def _attended_wall(item_id):
    """The board-write wall's agnostic half (it-30, attended-lane.md): an ATTENDED caller needs the
    typed record-before-flip (`YR-BOARD-FLIP`) somewhere on the trail of the issue this item fronts,
    before the write.

    **Caller class is DECLARED, never sniffed.** The machinery — the runner, the epic gate, the
    dispatch service — declares itself with `YR_MACHINERY=1`; its own records are its trail, so it
    passes untouched. Everything else that runs under a Claude session (`CLAUDECODE`) is attended and
    walled. The declaration is load-bearing: an early sniff-only form keyed on `CLAUDECODE` alone
    refused the runner's OWN integration tests, because pytest inside an attended session inherits
    that variable — the machinery must be able to say what it is rather than be guessed at.

    Fail-closed: an attended caller whose record cannot be verified is refused with the rule named.
    `YR_BOARD_WALL_OFF=1` is the explicit, single-purpose escape for the wall's own repair work."""
    if os.environ.get("YR_MACHINERY") or os.environ.get("YR_BOARD_WALL_OFF"):
        return
    if not os.environ.get("CLAUDECODE"):
        return
    try:
        out = subprocess.run(
            ["gh", "api", "graphql", "-f",
             "query=query($id:ID!){node(id:$id){... on ProjectV2Item{content{... on Issue{number repository{nameWithOwner} body comments(last:100){nodes{body}}}}}}}",
             "-F", f"id={item_id}",
             "--jq", "[.data.node.content.body, (.data.node.content.comments.nodes[].body)] | join(\"\\u0000\")"],
            capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip())
        texts = out.stdout.split("\u0000")
        lines = [l for t in texts for l in t.splitlines()]
        # `records.toml`'s YR-BOARD-FLIP row is mode=prefix: the RAW line begins with the marker at
        # column 0. Spelled inline rather than through `textutil` because this home imports stdlib
        # only, by standing invariant — the agreement test in tests/test_wall.py pins this literal
        # to the registry row so the two can never drift.
        if any(l.startswith("YR-BOARD-FLIP:") for l in lines):
            return
        raise RuntimeError("no YR-BOARD-FLIP record on the trail")
    except Exception as e:  # noqa: BLE001 — every unevaluable path refuses, naming what it could not read
        raise RuntimeError(
            f"board_plumbing: REFUSED [board-write] — an attended board write requires the "
            f"YR-BOARD-FLIP record on the issue's trail first (record-before-flip, typed; "
            f"attended-lane.md). Could not verify: {e}")


def set_field(gh, item_id, field_id, opt=None):
    """Set (or, when `opt` is None, clear) a single-select field on a board item — the one field write.
    `--single-select-option-id <opt>` for a set; `--clear` for the clear variant. `gh` runs a gh argv.
    Attended callers pass the it-30 wall first (`_attended_wall`); runner/epic-gate callers are
    untouched by construction (no CLAUDECODE in their environments)."""
    _attended_wall(item_id)
    argv = ["project", "item-edit", "--id", item_id, "--project-id", project_id(), "--field-id", field_id]
    if opt is None:
        argv.append("--clear")
    else:
        argv += ["--single-select-option-id", opt]
    gh(argv)


# --- the one per-issue read + its selection rule ------------------------------------------------------
def select_project_item(nodes, project_num=None):
    """The selection rule: the first projectItems node whose project number matches the configured board
    (env-overridable, resolved here when `project_num` is not passed), or None. The single implementation
    behind the sweep's per-child selection and the two operator scripts' reads."""
    if project_num is None:
        project_num = project_number()
    for pi in (nodes or []):
        if ((pi.get("project") or {}).get("number")) == project_num:
            return pi
    return None


_ISSUE_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      state
      issueType { name }
      projectItems(first: 20) {
        nodes {
          id
          project { number }
          status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          reason: fieldValueByName(name: "Reason") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
        }
      }
    }
  }
}
"""


# the CLI `read-issue` field separator: a unit-separator (US, non-whitespace), NOT a tab — a tab is
# IFS-whitespace, so a shell `IFS=$'\t' read` collapses the empty middle fields (itype/item_id/status/
# reason a given caller doesn't fill) and silently shifts every column. A non-whitespace delimiter keeps
# every field, empty ones included, so the shell split is exact. The shell callers set `IFS=$'\037'`.
_READ_SEP = "\x1f"


def read_issue_item(gh, owner, name, number):
    """The one per-issue project-item read: query the issue's own `projectItems` (authoritative for a
    single issue — `gh project item-list` lags ~1 min), select the node for our board, and return
    `(state, issue_type, item_id, status, reason)`. A missing/unmatched item yields "" for
    item_id/status/reason. `gh` runs a gh argv and returns stdout (parsed JSON or a JSON string)."""
    out = gh(["api", "graphql", "-f", "query=" + _ISSUE_QUERY,
              "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={number}"])
    obj = out if isinstance(out, (dict, list)) else json.loads(out)
    if isinstance(obj, dict) and "data" in obj:            # real `gh api graphql` wraps under "data"
        obj = obj["data"]
    issue = (((obj or {}).get("repository") or {}).get("issue")) or {}
    state = issue.get("state") or ""
    itype = (issue.get("issueType") or {}).get("name") or ""
    pi = select_project_item((issue.get("projectItems") or {}).get("nodes") or [])
    item_id = (pi or {}).get("id") or ""
    status = ((pi or {}).get("status") or {}).get("name") or ""
    reason = ((pi or {}).get("reason") or {}).get("name") or ""
    return state, itype, item_id, status, reason


# --- the CLI: the single mechanism the shell consumers reach this home through ------------------------
def _shq(s):
    """Single-quote `s` for safe shell `eval` (the identifier values are alnum/`_`/`-`, but quote anyway)."""
    return "'" + s.replace("'", "'\\''") + "'"


def _cli(argv):
    parser = argparse.ArgumentParser(prog="board_plumbing.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sh-exports", help="print shell identifier assignments for `eval`")

    p_read = sub.add_parser("read-issue", help="read one issue's board item (TSV: state itype id status reason)")
    p_read.add_argument("owner")
    p_read.add_argument("name")
    p_read.add_argument("number")

    p_set = sub.add_parser("set-field", help="set or clear a board item's Status/Reason")
    p_set.add_argument("--id", dest="item_id", required=True)
    group = p_set.add_mutually_exclusive_group(required=True)
    group.add_argument("--status")
    group.add_argument("--reason")
    group.add_argument("--clear-reason", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "sh-exports":
        print(f"PROJECT_NUMBER={_shq(str(project_number()))}")
        print(f"PROJECT_ID={_shq(project_id())}")
        print(f"STATUS_FIELD_ID={_shq(status_field_id())}")
        print(f"REASON_FIELD_ID={_shq(reason_field_id())}")
        return 0

    if args.cmd == "read-issue":
        print(_READ_SEP.join(read_issue_item(_gh, args.owner, args.name, args.number)))
        return 0

    # set-field
    if args.clear_reason:
        set_field(_gh, args.item_id, reason_field_id(), None)
        return 0
    if args.status is not None:
        opt = status_opt().get(args.status)
        if not opt:
            raise RuntimeError(f"no option id for Status={args.status}")
        set_field(_gh, args.item_id, status_field_id(), opt)
        return 0
    opt = reason_opt().get(args.reason)
    if not opt:
        raise RuntimeError(f"no option id for Reason={args.reason}")
    set_field(_gh, args.item_id, reason_field_id(), opt)
    return 0


def main(argv=None):
    try:
        return _cli(sys.argv[1:] if argv is None else argv)
    except RuntimeError as exc:                             # a gh failure or an unresolvable option name
        print(f"board_plumbing: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
