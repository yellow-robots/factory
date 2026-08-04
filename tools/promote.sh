#!/usr/bin/env bash
# tools/promote.sh — operator command: promote a standalone Type=Task issue to Ready, with the
# promotion-record comment landing BEFORE the Status flip, by construction — the comment call precedes
# the status mutation in code, so record-before-flip is a fact about the call order, not a convention to
# remember. No LLM anywhere.
#
# Refuses (writing nothing — no comment, no status write) when the target issue is closed, absent from
# project #PROJECT_NUMBER's board, or Type=Feature or Type=Epic (matched case-insensitively, both arms of
# the vocabulary — an epic — its Ready flip is the YR-EPIC-APPROVAL record, an attended act handled by
# tools/epic_gate.py, not this command; extending promotion to epics is explicitly out of scope here).
#
# Reads and writes the board through the one home (tools/board_plumbing.py): the identifiers, the
# per-issue project-item read (the authoritative per-issue read — same as tools/epic_gate.py) and its
# selection rule, and the `gh project item-edit` field write all live there. This command restates none
# of them — it obtains PROJECT_NUMBER (its refusal message) through the home's single `sh-exports`
# mechanism, reads the issue via `read-issue`, and flips Status via `set-field`.
set -euo pipefail

GH_BIN="${GH_BIN:-gh}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD_PY="$SELF_DIR/board_plumbing.py"
_board(){ GH_BIN="$GH_BIN" python3 "$BOARD_PY" "$@"; }
eval "$(_board sh-exports)"

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

# The authoritative per-issue read + its selection rule, through the one home (the board-plumbing
# `read-issue`): state, issue type, and the matching board item's id (empty when not on the board).
LINE="$(_board read-issue "$OWNER" "$NAME" "$ISSUE" 2>/dev/null)" \
  || die "could not query issue #$ISSUE from $REPO"
IFS=$'\037' read -r STATE ITYPE ITEM_ID _STATUS _REASON <<<"$LINE"

# ---- refuse gate (before any write; every refusal writes nothing) ----
[ "$STATE" = "OPEN" ] || refuse "issue #$ISSUE is not open (state: ${STATE:-unknown})"
[ -n "$ITEM_ID" ]     || refuse "issue #$ISSUE is not on project #$PROJECT_NUMBER's board"
case "$(printf '%s' "$ITYPE" | tr '[:upper:]' '[:lower:]')" in
  feature|epic)
    refuse "issue #$ISSUE is Type=$ITYPE (an epic) — epic Ready flips remain an attended act (YR-EPIC-APPROVAL via tools/epic_gate.py), not this command's"
    ;;
esac

WHO="$("$GH_BIN" api user --jq .login 2>/dev/null || true)"
[ -n "$WHO" ] || WHO="${USER:-operator}"
DATE="$(date -u +%Y-%m-%d)"

BODY="$(printf 'YR-PROMOTED\nwho: @%s\nwhy: %s\ndate: %s\n\nPromoted to **Ready** via `tools/promote.sh`. Standalone-task promotion is a human decision; this record lands before the Status flip, by construction.' "$WHO" "$REASON" "$DATE")"

# ---- the record, THEN the flip — in that order, by construction ----
"$GH_BIN" issue comment "$ISSUE" --repo "$REPO" --body "$BODY" >/dev/null \
  || die "could not post the promotion-record comment for #$ISSUE — refusing to flip Status without the record landing first"
_board set-field --id "$ITEM_ID" --status Ready >/dev/null 2>&1 \
  || die "promotion record posted, but the Status=Ready write failed for #$ISSUE — set it by hand or retry"

echo "promote: #$ISSUE -> Ready (record posted by @$WHO)"
