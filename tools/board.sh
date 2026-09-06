#!/usr/bin/env bash
# tools/board.sh — operator command: a one-shot TSV of every open board item (issue, repo, type, status,
# reason, title), read via one org-wide GraphQL query — the same projectV2 items read tools/epic_gate.py's
# sweep uses (BOARD_QUERY). No LLM anywhere.
#
# NOTE: `gh project item-list` is eventually consistent (~a minute behind); this script reads the same
# GraphQL `organization.projectV2.items` shape epic_gate.py's sweep does instead. The per-issue
# `projectItems` read (used by watch_build.sh / promote.sh) is the authoritative read for a SINGLE issue —
# this org-wide items query is the authoritative read for a BOARD SCAN.
set -euo pipefail

GH_BIN="${GH_BIN:-gh}"
YR_ORG="${YR_ORG:-yellow-robots}"
# The project number (this script's one board identifier) comes from the one home
# (tools/board_plumbing.py) through the single `sh-exports` mechanism — no default restated here. The
# org-wide `projectV2.items` read below is a deliberately different read and stays as it is.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(GH_BIN="$GH_BIN" python3 "$SELF_DIR/board_plumbing.py" sh-exports)"

die()  { echo "board: ERROR: $*" >&2; exit 1; }
usage(){ echo "usage: board.sh [--org <org>] [--project <number>]" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --org)      YR_ORG="${2:-}"; shift 2;;
    --project)  PROJECT_NUMBER="${2:-}"; shift 2;;
    -h|--help)  usage;;
    *)          die "unknown arg: $1";;
  esac
done

# `createdAt` rides the Issue fragment (it-36 slice J, #475): the backlog-age KPI's own read needs
# each item's age, and this org-wide query is the one authoritative board-scan shape (BOARD_QUERY,
# same read tools/epic_gate.py's sweep uses) — never a second, parallel query for the same items.
BOARD_QUERY='query($org: String!, $project: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: 100, after: $cursor) {
        nodes {
          content { ... on Issue { number title state createdAt issueType { name } repository { nameWithOwner } } }
          status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          reason: fieldValueByName(name: "Reason") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}'

# A board past 100 items must not silently lose everything past the first page (the gotcha this
# slice names explicitly) — page until the query's own `pageInfo.hasNextPage` says stop. A capped
# loop (100 pages, 10k items) keeps a malformed/looping response from spinning forever.
PAGES_FILE="$(mktemp)"
trap 'rm -f "$PAGES_FILE"' EXIT
CURSOR=""
PAGE_COUNT=0
while :; do
  PAGE_COUNT=$((PAGE_COUNT + 1))
  [ "$PAGE_COUNT" -le 100 ] || die "board query did not terminate after 100 pages (project #$PROJECT_NUMBER on $YR_ORG)"
  ARGS=(api graphql -f "query=$BOARD_QUERY" -F "org=$YR_ORG" -F "project=$PROJECT_NUMBER")
  [ -n "$CURSOR" ] && ARGS+=(-F "cursor=$CURSOR")
  PAGE_OUT="$("$GH_BIN" "${ARGS[@]}" 2>/dev/null)" \
    || die "could not query project #$PROJECT_NUMBER on $YR_ORG (is the gh 'project' scope granted?)"
  printf '%s\n' "$PAGE_OUT" >> "$PAGES_FILE"
  CURSOR="$(printf '%s' "$PAGE_OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if "data" in d: d = d["data"]
items = (((d.get("organization") or {}).get("projectV2") or {}).get("items") or {})
page = items.get("pageInfo") or {}
print(page.get("endCursor") or "" if page.get("hasNextPage") else "")
')"
  [ -n "$CURSOR" ] || break
done

python3 -c '
import json, sys

nodes = []
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if "data" in d: d = d["data"]
        items = (((d.get("organization") or {}).get("projectV2") or {}).get("items") or {})
        nodes += items.get("nodes") or []

for it in nodes:
    c = it.get("content") or {}
    if not c or (c.get("state") or "").upper() != "OPEN":
        continue
    number = c.get("number")
    repo = (c.get("repository") or {}).get("nameWithOwner") or ""
    itype = (c.get("issueType") or {}).get("name") or ""
    status = (it.get("status") or {}).get("name") or ""
    reason = (it.get("reason") or {}).get("name") or ""
    title = c.get("title") or ""
    print("\t".join([str(number), repo, itype, status, reason, title]))
' "$PAGES_FILE"
