#!/usr/bin/env bash
# hooks/deliver.sh — unconditional canon delivery (it-30 slice 4, epic #415).
#
# SessionStart (startup|clear|compact|resume): emit the compiled bounded slice + the runtime position
# element, as additionalContext. Delivery is independent of the session recognizing factory work —
# that is the whole point (the recognition gate is what degrades).
#
# Two stances, both load-bearing:
#   * LOUD — every failure says what failed, in words that carry the reason (the tail of the error,
#     never its head: a truncated traceback names nothing). A silent delivery is a failed delivery.
#   * NON-BLOCKING — the hook always exits 0 and never withholds the session; the human is never
#     locked out by the machinery's own defect.
#
# The machinery is not attended: a cold pipeline stage inherits YR_MACHINERY from the runner and gets
# no attended-lane canon — the same one declaration that governs the walls (slice 5).
set -u

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Cold pipeline stages declare themselves machinery; the attended lane's canon is not theirs.
if [ -n "${YR_MACHINERY:-}" ]; then exit 0; fi

TMP="$(mktemp 2>/dev/null)" || TMP=""
ERR="${TMP:+$TMP.err}"
trap 'rm -f "$TMP" "$ERR"' EXIT

emit() {
  # SessionStart contract: JSON with hookSpecificOutput.additionalContext. Read with errors
  # replaced so a truncated multi-byte character can never turn a loud banner into silence.
  python3 - "$1" << 'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    body = f.read()
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart", "additionalContext": body}}))
PYEOF
}

emit_literal() {  # last-resort path: no temp file available
  python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))' "$1"
}

banner() {  # loud, non-blocking, and derivable: the reason plus where the canon lives
  printf 'YR-DELIVERY-FAILURE: the attended lane%s slice was not delivered — %s. Load the canon by hand: %s/skills/factory/references/attended-lane.md (loud, non-blocking — it-30).' \
    "'s" "$1" "$ROOT"
}

if [ -z "$TMP" ]; then
  emit_literal "$(banner "no temp file could be created")"
  exit 0
fi

if ! python3 "$ROOT/tools/compile_slice.py" --out "$TMP" 2> "$ERR"; then
  # The TAIL of the error carries the reason; the head of a traceback carries nothing.
  reason="$(tr '\n' ' ' < "$ERR" | tail -c 400)"
  banner "${reason:-the compiler failed with no message}" > "$TMP"
  emit "$TMP"
  exit 0
fi

# The runtime position element — composed at delivery, never cached into the artifact. Repo-aware:
# the position of the round in THIS repo, not a hardcoded one (a factory-hardcoded read told a
# website session the factory's PRs were its position).
{
  printf '\n## Position (composed at delivery — %s)\n\n' "$(date -u +%Y-%m-%dT%H:%MZ)"
  REPO="$(timeout 10 gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
  if [ -z "$REPO" ]; then
    printf 'Position unavailable: this directory resolves to no GitHub repo (loud, non-blocking) — read the board by hand.\n'
  else
    printf 'Repo: %s\n' "$REPO"
    if PRS="$(timeout 15 gh pr list --repo "$REPO" --state open \
          --json number,title,mergeStateStatus \
          --jq 'map("PR#\(.number) \(.mergeStateStatus): \(.title)") | join("\n")' 2>/dev/null)"; then
      if [ -n "$PRS" ]; then printf 'Open PRs:\n%s\n' "$PRS"; else printf 'No open PRs.\n'; fi
    else
      printf 'PR read unavailable (gh failed or timed out) — loud, non-blocking.\n'
    fi
    if BOARD="$(timeout 20 bash "$ROOT/tools/board.sh" 2>/dev/null | awk -F'\t' -v r="${REPO#*/}" '$2==r {print "  #" $1" ["$5"] "$6}' | head -12)"; then
      if [ -n "$BOARD" ]; then printf 'Board (this repo, open items):\n%s\n' "$BOARD"; fi
    fi
  fi
} >> "$TMP"

emit "$TMP"
exit 0
