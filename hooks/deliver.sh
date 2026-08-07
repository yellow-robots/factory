#!/usr/bin/env bash
# hooks/deliver.sh — unconditional canon delivery (it-30 slice 4, epic #415).
#
# SessionStart (startup|clear|compact|resume): emit the compiled bounded slice + the runtime position
# element, as additionalContext. Delivery is independent of the session recognizing factory work —
# that is the whole point (the recognition gate is what degrades). Infrastructure failure here is
# LOUD AND NON-BLOCKING: a crashed delivery prints a banner and exits 0 — the human is never locked
# out of her own session by the machinery's own defect. The position element composes at delivery
# (board + PR reads, bounded), never cached into the artifact.
set -u

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

emit_context() {
  # SessionStart contract: JSON with hookSpecificOutput.additionalContext.
  python3 - "$1" << 'PYEOF'
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": open(sys.argv[1], encoding="utf-8").read()}}))
PYEOF
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if ! python3 "$ROOT/tools/compile_slice.py" --out "$TMP" 2> "$TMP.err"; then
  # Loud, non-blocking: the banner reaches the session as context; the session proceeds.
  printf '%s\n' "YR-DELIVERY-FAILURE: the attended lane's slice failed to compile — $(tr '\n' ' ' < "$TMP.err" | head -c 300). The lane's canon is skills/factory/references/attended-lane.md; load it by hand. This banner is the loud non-blocking stance (it-30)." > "$TMP"
  emit_context "$TMP"
  exit 0
fi

# The runtime position element — the round's current position, composed at delivery. Bounded and
# loud-non-blocking: a failed read names itself; it never blocks the session.
{
  printf '\n## Position (composed at delivery — %s)\n\n' "$(date -u +%Y-%m-%dT%H:%MZ)"
  if POS="$(timeout 15 gh pr list --repo yellow-robots/factory --state open \
        --json number,title,mergeStateStatus \
        --jq 'map("PR#\(.number) \(.mergeStateStatus): \(.title)") | join("\n")' 2>/dev/null)"; then
    if [ -n "$POS" ]; then printf 'Open factory PRs:\n%s\n' "$POS"; else printf 'No open factory PRs.\n'; fi
  else
    printf 'Position read unavailable (gh failed or timed out) — loud, non-blocking; read the board by hand.\n'
  fi
} >> "$TMP"

emit_context "$TMP"
exit 0
