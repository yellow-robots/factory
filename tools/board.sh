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
PROJECT_NUMBER="${PROJECT_NUMBER:-1}"

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

BOARD_QUERY='query($org: String!, $project: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: 100) {
        nodes {
          content { ... on Issue { number title state issueType { name } repository { nameWithOwner } } }
          status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          reason: fieldValueByName(name: "Reason") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
        }
      }
    }
  }
}'

OUT="$("$GH_BIN" api graphql -f "query=$BOARD_QUERY" -F "org=$YR_ORG" -F "project=$PROJECT_NUMBER" 2>/dev/null)" \
  || die "could not query project #$PROJECT_NUMBER on $YR_ORG (is the gh 'project' scope granted?)"

printf '%s' "$OUT" | python3 -c '
import json, sys

d = json.load(sys.stdin)
if "data" in d: d = d["data"]
nodes = (((d.get("organization") or {}).get("projectV2") or {}).get("items") or {}).get("nodes") or []
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
'
