#!/usr/bin/env bash
# tools/promote.sh — operator command: promote a standalone Type=Task issue to Ready, with the
# promotion-record comment landing BEFORE the Status flip, by construction — the comment call precedes
# the status mutation in code, so record-before-flip is a fact about the call order, not a convention to
# remember. No LLM anywhere.
#
# Refuses (writing nothing — no comment, no status write) when the target issue is closed, absent from
# project #PROJECT_NUMBER's board, or Type=Feature (an epic — its Ready flip is the YR-EPIC-APPROVAL
# record, an attended act handled by tools/epic_gate.py, not this command; extending promotion to epics is
# explicitly out of scope here).
#
# Reuses tools/dev-runner.sh's Projects field config (same ids, same env overrides) and its
# `gh project item-edit` setter shape, and reads the issue-side `projectItems` via GraphQL — the
# authoritative per-issue read, same pattern as tools/epic_gate.py.
set -euo pipefail

GH_BIN="${GH_BIN:-gh}"
PROJECT_NUMBER="${PROJECT_NUMBER:-1}"
PROJECT_ID="${PROJECT_ID:-PVT_kwDOEEAo0M4Ba6Ls}"
STATUS_FIELD_ID="${STATUS_FIELD_ID:-PVTSSF_lADOEEAo0M4Ba6LszhVuZlw}"
READY_OPT="${OPT_READY:-c85eb5c1}"

die()   { echo "promote: ERROR: $*" >&2; exit 1; }
refuse(){ echo "promote: REFUSED: $*" >&2; exit 3; }
usage() { echo "usage: promote.sh <issue#> [--repo <owner/name>] [--reason <text>]" >&2; exit 2; }

ISSUE=""; REPO=""; REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)   REPO="${2:-}"; shift 2;;
    --reason) REASON="${2:-}"; shift 2;;
    -h|--help) usage;;
    -*)       die "unknown flag: $1";;
    *)        if [ -z "$ISSUE" ]; then ISSUE="$1"; shift; else die "unexpected arg: $1"; fi;;
  esac
done
[ -n "$ISSUE" ] || usage
case "$ISSUE" in *[!0-9]*|"") die "issue must be a number, got: '$ISSUE'";; esac
[ -n "$REASON" ] || REASON="DoR met"

if [ -z "$REPO" ]; then
  REPO="$("$GH_BIN" repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" \
    || die "could not resolve repo; pass --repo <owner/name>"
fi
OWNER="${REPO%/*}"; NAME="${REPO#*/}"

ISSUE_QUERY='query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      state
      issueType { name }
      projectItems(first: 20) {
        nodes {
          id
          project { number }
        }
      }
    }
  }
}'

OUT="$("$GH_BIN" api graphql -f "query=$ISSUE_QUERY" -F "owner=$OWNER" -F "name=$NAME" -F "number=$ISSUE" 2>/dev/null)" \
  || die "could not query issue #$ISSUE from $REPO"

IFS=$'\t' read -r STATE ITYPE ITEM_ID <<<"$(printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if "data" in d: d = d["data"]
issue = ((d.get("repository") or {}).get("issue")) or {}
state = issue.get("state") or ""
itype = (issue.get("issueType") or {}).get("name") or ""
item_id = ""
for pi in ((issue.get("projectItems") or {}).get("nodes") or []):
    if (pi.get("project") or {}).get("number") == int(sys.argv[1]):
        item_id = pi.get("id") or ""
        break
print("\t".join([state, itype, item_id]))
' "$PROJECT_NUMBER")"

# ---- refuse gate (before any write; every refusal writes nothing) ----
[ "$STATE" = "OPEN" ] || refuse "issue #$ISSUE is not open (state: ${STATE:-unknown})"
[ -n "$ITEM_ID" ]     || refuse "issue #$ISSUE is not on project #$PROJECT_NUMBER's board"
[ "$(printf '%s' "$ITYPE" | tr '[:upper:]' '[:lower:]')" = "feature" ] \
  && refuse "issue #$ISSUE is Type=Feature (an epic) — epic Ready flips remain an attended act (YR-EPIC-APPROVAL via tools/epic_gate.py), not this command's"

WHO="$("$GH_BIN" api user --jq .login 2>/dev/null || true)"
[ -n "$WHO" ] || WHO="${USER:-operator}"
DATE="$(date -u +%Y-%m-%d)"

BODY="$(printf 'YR-PROMOTED\nwho: @%s\nwhy: %s\ndate: %s\n\nPromoted to **Ready** via `tools/promote.sh`. Standalone-task promotion is a human decision; this record lands before the Status flip, by construction.' "$WHO" "$REASON" "$DATE")"

# ---- the record, THEN the flip — in that order, by construction ----
"$GH_BIN" issue comment "$ISSUE" --repo "$REPO" --body "$BODY" >/dev/null \
  || die "could not post the promotion-record comment for #$ISSUE — refusing to flip Status without the record landing first"
"$GH_BIN" project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
  --field-id "$STATUS_FIELD_ID" --single-select-option-id "$READY_OPT" >/dev/null \
  || die "promotion record posted, but the Status=Ready write failed for #$ISSUE — set it by hand or retry"

echo "promote: #$ISSUE -> Ready (record posted by @$WHO)"
