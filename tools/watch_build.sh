#!/usr/bin/env bash
# tools/watch_build.sh — operator command: poll one issue's board Status/Reason + PR presence until a
# terminal state is reached, printing each transition as it happens. No LLM anywhere.
#
# Reads the issue-side `projectItems` via GraphQL (authoritative — `gh project item-list` lags ~1 min,
# same reasoning as tools/epic_gate.py's per-epic reads), same Projects field config as
# tools/dev-runner.sh (PROJECT_NUMBER, same env overrides).
#
# Exit codes:
#   0 — a PR is open and Status is In Review (prints the PR URL)
#   2 — Status is Done
#   3 — Reason is off-track (Blocked / Needs-info); prints the latest dev-runner comment for diagnosis
#   4 — --timeout reached with no terminal state
set -euo pipefail

GH_BIN="${GH_BIN:-gh}"
PROJECT_NUMBER="${PROJECT_NUMBER:-1}"

die()  { echo "watch-build: ERROR: $*" >&2; exit 1; }
usage(){ echo "usage: watch_build.sh <issue#> [--repo <owner/name>] [--interval N] [--timeout N]" >&2; exit 2; }

ISSUE=""; REPO=""; INTERVAL="${INTERVAL:-15}"; TIMEOUT="${TIMEOUT:-1800}"
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)     REPO="${2:-}"; shift 2;;
    --interval) INTERVAL="${2:-}"; shift 2;;
    --timeout)  TIMEOUT="${2:-}"; shift 2;;
    -h|--help)  usage;;
    -*)         die "unknown flag: $1";;
    *)          if [ -z "$ISSUE" ]; then ISSUE="$1"; shift; else die "unexpected arg: $1"; fi;;
  esac
done
[ -n "$ISSUE" ] || usage
case "$ISSUE" in *[!0-9]*|"") die "issue must be a number, got: '$ISSUE'";; esac

if [ -z "$REPO" ]; then
  REPO="$("$GH_BIN" repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" \
    || die "could not resolve repo; pass --repo <owner/name>"
fi
OWNER="${REPO%/*}"; NAME="${REPO#*/}"

STATUS_QUERY='query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      state
      projectItems(first: 20) {
        nodes {
          project { number }
          status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          reason: fieldValueByName(name: "Reason") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
        }
      }
    }
  }
}'

# sets ISSUE_STATE / ITEM_STATUS / ITEM_REASON from the issue-side GraphQL read (the authoritative one).
fetch_state(){
  local out
  out="$("$GH_BIN" api graphql -f "query=$STATUS_QUERY" -F "owner=$OWNER" -F "name=$NAME" -F "number=$ISSUE" 2>/dev/null)" \
    || die "could not query issue #$ISSUE from $REPO"
  IFS=$'\t' read -r ISSUE_STATE ITEM_STATUS ITEM_REASON <<<"$(printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if "data" in d: d = d["data"]
issue = ((d.get("repository") or {}).get("issue")) or {}
state = issue.get("state") or ""
status = ""; reason = ""
for pi in ((issue.get("projectItems") or {}).get("nodes") or []):
    if (pi.get("project") or {}).get("number") == int(sys.argv[1]):
        status = (pi.get("status") or {}).get("name") or ""
        reason = (pi.get("reason") or {}).get("name") or ""
        break
print("\t".join([state, status, reason]))
' "$PROJECT_NUMBER")"
}

# sets PR_URL to the open PR whose head branch is task/<issue>-… (dev-runner.sh's BRANCH convention), or "".
fetch_pr(){
  local out
  out="$("$GH_BIN" pr list --repo "$REPO" --state open --json number,headRefName,url 2>/dev/null)" || out="[]"
  PR_URL="$(printf '%s' "$out" | python3 -c '
import json, sys
prefix = "task/" + sys.argv[1] + "-"
try:
    prs = json.load(sys.stdin)
except Exception:
    prs = []
for pr in prs:
    if (pr.get("headRefName") or "").startswith(prefix):
        print(pr.get("url") or "")
        break
' "$ISSUE")"
}

# the latest issue comment posted by the runner (body starting "dev-runner:" — its own comment prefix),
# falling back to the issue's last comment if none matches.
latest_runner_comment(){
  local out
  out="$("$GH_BIN" issue view "$ISSUE" --repo "$REPO" --json comments 2>/dev/null)" || return 0
  printf '%s' "$out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
comments = [(c.get("body") or "") for c in (d.get("comments") or [])]
runner = [b for b in comments if b.lower().startswith("dev-runner:")]
pick = runner[-1] if runner else (comments[-1] if comments else "")
if pick:
    print(pick)
'
}

START="$(date +%s)"
PREV_STATUS=""; PREV_REASON=""; PREV_PR=""
while :; do
  fetch_state
  fetch_pr
  if [ "$ITEM_STATUS" != "$PREV_STATUS" ] || [ "$ITEM_REASON" != "$PREV_REASON" ] || [ "$PR_URL" != "$PREV_PR" ]; then
    echo "watch-build: #$ISSUE status=${ITEM_STATUS:-none} reason=${ITEM_REASON:-none} pr=${PR_URL:-none}" >&2
    PREV_STATUS="$ITEM_STATUS"; PREV_REASON="$ITEM_REASON"; PREV_PR="$PR_URL"
  fi

  if [ -n "$PR_URL" ] && [ "$ITEM_STATUS" = "In Review" ]; then
    echo "$PR_URL"
    exit 0
  fi
  if [ "$ITEM_STATUS" = "Done" ]; then
    exit 2
  fi
  case "$ITEM_REASON" in
    Blocked|Needs-info)
      latest_runner_comment
      exit 3
      ;;
  esac

  NOW="$(date +%s)"
  if [ "$((NOW - START))" -ge "$TIMEOUT" ]; then
    exit 4
  fi
  sleep "$INTERVAL"
done
