#!/usr/bin/env bash
# hooks/deliver.sh — canon delivery from the compiled surfaces, inside the boundary
# (it-31 slice 8, epic #432; the it-30 slice-4 canon splice is retired).
#
# SessionStart (startup|clear|compact|resume): emit build/slice-static.md (GENERATED from
# process.toml, committed with the model) plus the runtime position element composed by
# tools/compile_slice.py — as additionalContext. Delivery is independent of the session
# recognizing factory work; that is the whole point (the recognition gate is what degrades).
#
# Three stances, all load-bearing:
#   * LOUD — every failure says what failed, in words that carry the reason (the tail of the
#     error, never its head). A silent delivery is a failed delivery.
#   * NON-BLOCKING — the hook always exits 0 and never withholds the session; the human is never
#     locked out by the machinery's own defect.
#   * SILENT OUTSIDE THE BOUNDARY — the engine's own in_scope rule (via compile_slice --in-scope)
#     judges the session's cwd; outside the factory's declared world, no slice, no banner, no
#     bytes. Only a CLEAN out-of-scope verdict (exit 3) suppresses delivery — a crashed boundary
#     check banners loudly instead (a crash is never silence).
#
# The machinery is not attended: a cold pipeline stage inherits YR_MACHINERY from the runner and
# gets no attended-lane canon — the same one declaration that governs the walls.
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
  printf 'YR-DELIVERY-FAILURE: the attended lane%s slice was not delivered — %s. Load the canon by hand: %s/build/slice-static.md (+ %s/skills/factory/references/attended-lane.md) (loud, non-blocking).' \
    "'s" "$1" "$ROOT" "$ROOT"
}

if [ -z "$TMP" ]; then
  emit_literal "$(banner "no temp file could be created")"
  exit 0
fi

# The session's cwd rides the SessionStart payload on stdin; absent, the hook's own cwd stands in.
HOOK_JSON="$(cat 2>/dev/null || true)"
CWD="$(printf '%s' "$HOOK_JSON" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("cwd") or "")
except Exception:
    print("")' 2>/dev/null || true)"
[ -n "$CWD" ] || CWD="$PWD"

# The boundary gate: 0 = inside; 3 = a CLEAN outside verdict (silence); anything else banners.
python3 "$ROOT/tools/compile_slice.py" --in-scope "$CWD" 2> "$ERR"
RC=$?
if [ "$RC" = "3" ]; then exit 0; fi
if [ "$RC" != "0" ]; then
  reason="$(tr '\n' ' ' < "$ERR" | tail -c 400)"
  banner "the boundary check failed: ${reason:-no message}" > "$TMP"
  emit "$TMP"
  exit 0
fi

# The static half: the model's own compiled surface, served verbatim.
if ! cat "$ROOT/build/slice-static.md" > "$TMP" 2> "$ERR"; then
  reason="$(tr '\n' ' ' < "$ERR" | tail -c 400)"
  banner "the compiled surface build/slice-static.md is unreadable: ${reason:-no message}" > "$TMP"
  emit "$TMP"
  exit 0
fi

# The position half — composed at delivery, never cached into the artifact; loud, non-blocking.
if ! python3 "$ROOT/tools/compile_slice.py" --position "$CWD" >> "$TMP" 2> "$ERR"; then
  {
    printf '\n## Position (composed at delivery)\n\n'
    printf 'Position unavailable (the composer failed) — loud, non-blocking; read the board by hand.\n'
  } >> "$TMP"
fi

emit "$TMP"
exit 0
