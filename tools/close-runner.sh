#!/usr/bin/env bash
# close-runner.sh — the close stage's own stage runner (it-36 slice H, #473): `close-walk` — one
# `claude -p` stage, sourcing tools/stage_lib.sh: byte-identical run_stage machinery to
# tools/dev-runner.sh's own (it-36 slice C). Spawned by tools/design_gate.py's own close sweep
# (`sweep_close`, never invoked directly in production) once a finished epic carries `YR-CLOSE-HOLD`
# and its own mandated close records are not already on the trail. Every deterministic computation
# and every trail/vault write belongs to tools/round_record.py, never re-implemented here — this
# script only runs the close-walk's own judgment call and hands finished files to that tool.
#
# Usage: close-runner.sh <owner/repo> <epic-number> [<component-root> [<strategy-doc>]]
#
#   component-root / strategy-doc — the repo's OWN local vault-mirror paths (#472 fold review, B3):
#                threaded on ARGV by tools/design_gate.py's own close sweep, from the SAME
#                pm-repos.json config entry `_resolve_entry` already reads — never an environment
#                variable (one shared value for every swept repo, and silently stripped by
#                dispatch's own spawn-env allowlist under the PM instance). Either may be empty:
#                an empty component-root skips the close-walk entirely (nothing to ground it
#                against); an empty/unreadable strategy-doc skips only YR-CROSSOVER (advisory,
#                never gate-mandated).
#
#   already-shipped — I3's own idempotence guard, checked right after `fetch`, before any LLM call:
#                if YR-SHIP-WALK already rides the epic trail, the close-walk stage and the vault
#                patch are BOTH skipped (a re-run after a failed round-record/crossover must never
#                re-walk or re-patch) — round-record/crossover still run.
#
#   close-walk — the ship-walk over the grounding list (skills/factory/references/architect.md
#                moment 3 / skills/factory/references/closing.md ss3): the model reads the epic's
#                own technical-rfc body plus the component's CURRENT living reference (the local
#                vault-mirror path given on argv) and names, in the fixed grammar tools/round_
#                record.py's own parser reads, the ONE living-reference section to update (by
#                heading TEXT, outermost first — B1: never '#'/'##'-prefixed, the real vault API's
#                own heading-target rule, verified live 2026-09-06) and any research now
#                superseded.
#
#   Then, in order: `check_supersession.py --sweep` over the component (I10: backs the ship-walk's
#   own "grounding list was walked" claim with an actual deterministic sweep, advisory — never
#   blocks); `tools/round_record.py ship-walk` (applies the close-walk's own directive through
#   tools/vault_api.py — the ONLY vault write path — and posts YR-SHIP-WALK); `tools/round_
#   record.py round-record` (the round's own four counts + deployed, computed from the trails);
#   `tools/round_record.py crossover` (this epic's own merged-PR usage vs. the strategy doc's theme
#   budget — skipped, loudly, when no strategy doc was given: CROSSOVER is not one of the close
#   arm's own gate-mandated records, so its absence never blocks the epic's self-close). The close
#   arm itself (tools/epic_gate.py, unchanged) decides when the epic actually closes, on its own
#   next sweep.
set -euo pipefail

export YR_MACHINERY=1

CLAUDE_BIN="${CLAUDE_BIN:-claude}"; GH_BIN="${GH_BIN:-gh}"
EFFORT="${EFFORT:-high}"
DESIGN_MODEL="${DESIGN_MODEL:-}"
DEV_RUNNER_HOME="${DEV_RUNNER_HOME:-$HOME/.cache/dev-runner}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SELF_DIR/stage_lib.sh"

# ROUND_RECORD_PY / CHECK_SUPERSESSION_PY are test-only overrides (the CROSS_PY precedent,
# tools/cross-runner.sh) — production never sets them, so the real tools run; a test substitutes a
# fake to exercise this script's own orchestration without a live gh/vault/vault-mirror tree.
ROUND_RECORD_PY="${ROUND_RECORD_PY:-$SELF_DIR/round_record.py}"
CHECK_SUPERSESSION_PY="${CHECK_SUPERSESSION_PY:-$SELF_DIR/check_supersession.py}"

log(){ echo "close-runner: $*" >&2; }
usage(){ echo "usage: close-runner.sh <owner/repo> <epic-number> [<component-root> [<strategy-doc>]]" >&2; exit 2; }

REPO="${1:-}"; EPIC="${2:-}"; COMPONENT_ROOT="${3:-}"; STRATEGY_DOC="${4:-}"
[ -n "$REPO" ] && [ -n "$EPIC" ] || usage

resolve_role review "$DESIGN_MODEL" "" "$DESIGN_MODEL"
[ "$R_STATUS" != unknown ] || { log "design model unresolved — refusing"; exit 2; }
BUILD_ID="$R_ID"

APP_SLUG="${YR_GH_APP_SLUG:-yr-pm}"

RUN_ID="close-$(printf '%s' "$REPO" | tr '/.' '--')-$EPIC-$$"
RUN_DIR="$DEV_RUNNER_HOME/runs/$RUN_ID"
mkdir -p "$RUN_DIR"
WT="$RUN_DIR"   # no code worktree: the close stage reads trails and a vault mirror, not a code
                # change; run_stage's own `cd "$WT"` just needs a stable directory to run from.
LEDGER_DIR="$DEV_RUNNER_HOME/ledger"

ledger_row(){   # $1 = stage name, $2 = that stage's outcome ("ok"|"failed")
  local now_iso; now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 "$SELF_DIR/ledger.py" append --ledger-dir "$LEDGER_DIR" --kind design --stage "$1" \
    --run-id "$RUN_ID" --task "$REPO#$EPIC" --repo "$REPO" --run-dir "$RUN_DIR" \
    --build-model "$BUILD_ID" --outcome-type "$2" \
    --ts-start "$now_iso" --ts-end "$now_iso" --wall-seconds 0 >/dev/null 2>&1 \
    || log "warn: ledger row not appended for stage '$1' (non-fatal)"
}

log "fetch: the epic + its children's trails and linked merged-PR numbers"
python3 "$ROUND_RECORD_PY" fetch --repo "$REPO" --epic "$EPIC" > "$RUN_DIR/fetch.json" \
  || { log "fetch failed — stopping"; exit 1; }

# I3: idempotence — if YR-SHIP-WALK already rides the epic trail, a re-run (e.g. after a failed
# round-record/crossover on a prior tick) must never re-run the close-walk stage or re-patch the
# vault a second time. round-record/crossover below still run unconditionally.
if python3 "$ROUND_RECORD_PY" already-shipped --fetch-json "$RUN_DIR/fetch.json"; then
  log "already-shipped: YR-SHIP-WALK already on the trail — skipping the close-walk stage and the vault patch"
else
  CLOSE_WALK_SYS="You are the PM agent's close-walk stage (it-36 slice H) — the ship-walk over the grounding list (skills/factory/references/architect.md moment 3). Read the epic's own technical-rfc body and the component's CURRENT living reference (the one note under its architecture/ home with 'type: note', kept current). Decide the ONE section that needs updating in light of what this round shipped, and any research this round makes superseded. Output EXACTLY this shape and nothing else: a ===LIVING-REFERENCE=== block naming 'path: <vault-relative path to the living reference>' then 'heading: <exact heading TEXT, nested headings joined by ::>' — the heading text ONLY, never a leading '#' or '##' (the real vault API addresses a heading by its bare text, e.g. 'Build hosts', never '## Build hosts') — then the section's full REPLACEMENT content between ===CONTENT=== and ===END-CONTENT===, closed by ===END-LIVING-REFERENCE===; then a ===SUPERSEDED=== block with zero or more 'PATH: TARGET' lines (TARGET is the superseding doc's vault-relative path, or the literal word none), closed by ===END-SUPERSEDED===. If nothing in the living reference needs updating, omit the ===LIVING-REFERENCE=== block entirely rather than inventing a change; if nothing is superseded, the ===SUPERSEDED=== block may be empty or omitted. No commentary, no preamble, no text outside those blocks."

  if [ -z "$COMPONENT_ROOT" ]; then
    log "warn: no component-root given — cannot ground the close-walk against a living reference; stopping short of the walk (no records posted this tick)"
    exit 0
  fi

  epic_body="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["epic_texts"][0])' "$RUN_DIR/fetch.json")"
  living_ref_text=""
  if [ -f "$COMPONENT_ROOT/architecture/README.md" ]; then
    living_ref_text="$(cat "$COMPONENT_ROOT/architecture/README.md")"
  fi

  log "close-walk: $(basename "$CLAUDE_BIN") [$BUILD_ID] repo=$REPO epic=$EPIC"
  run_stage "$CLOSE_WALK_SYS" \
    "$(printf 'Epic technical-rfc body:\n%s\n\nComponent living reference (%s/architecture/README.md):\n%s' \
       "$epic_body" "$COMPONENT_ROOT" "$living_ref_text")" \
    "$RUN_DIR/close-walk.log" "Read Bash" "$BUILD_ID" \
    || { ledger_row close-walk failed; log "close-walk stage failed — stopping"; exit 1; }
  ledger_row close-walk ok

  # I10: back "the grounding list was walked" with an actual run of the existing deterministic
  # sweep — advisory (never blocks: a legacy finding is reported honestly in the record, not
  # treated as a gate). VAULT_ROOT/SCOPE resolve through tools/design_gate.py's own helpers so this
  # never re-derives the vault-relative path rule.
  VAULT_ROOT_VAL="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import design_gate; print(design_gate.VAULT_ROOT)' "$SELF_DIR")"
  SCOPE_VAL="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import design_gate; print(design_gate.vault_rel_path(sys.argv[2]))' "$SELF_DIR" "$COMPONENT_ROOT")"
  log "supersession sweep: check_supersession.py --sweep --scope $SCOPE_VAL"
  if python3 "$CHECK_SUPERSESSION_PY" --sweep --scope "$SCOPE_VAL" --vault-root "$VAULT_ROOT_VAL" \
      > "$RUN_DIR/supersession-sweep.log" 2>&1; then
    SWEEP_STATUS="clean (exit 0)"
  else
    SWEEP_STATUS="$(head -1 "$RUN_DIR/supersession-sweep.log" 2>/dev/null || echo "non-zero exit") — see $RUN_DIR/supersession-sweep.log"
  fi

  log "ship-walk: applying the close-walk's own directive and posting YR-SHIP-WALK"
  python3 "$ROUND_RECORD_PY" ship-walk --in "$RUN_DIR/close-walk.log" --repo "$REPO" --epic "$EPIC" \
    --who "$APP_SLUG" --scope "$REPO#$EPIC" --supersession-sweep "$SWEEP_STATUS" \
    || { log "ship-walk apply/post failed — stopping short of the round-record (a partial close is never posted)"; exit 1; }
fi

log "round-record: computing + posting YR-ROUND-RECORD"
python3 "$ROUND_RECORD_PY" round-record --fetch-json "$RUN_DIR/fetch.json" --repo "$REPO" --epic "$EPIC" \
  || { log "round-record failed — stopping"; exit 1; }

if [ -n "$STRATEGY_DOC" ] && [ -f "$STRATEGY_DOC" ]; then
  log "crossover: computing + posting YR-CROSSOVER"
  python3 "$ROUND_RECORD_PY" crossover --fetch-json "$RUN_DIR/fetch.json" \
    --strategy-doc "$STRATEGY_DOC" --repo "$REPO" --epic "$EPIC" --who "$APP_SLUG" \
    || log "warn: crossover failed to post (non-fatal — not one of the close arm's own gate-mandated records)"
else
  log "warn: no strategy-doc given (or unreadable) — YR-CROSSOVER not posted this tick (advisory only, never blocks self-close)"
fi

log "done: close records posted for $REPO#$EPIC — the next epic-gate sweep decides the self-close"
