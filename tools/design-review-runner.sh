#!/usr/bin/env bash
# design-review-runner.sh — the PM's own review-stage runner (it-36 slice F, #471): fit, arch,
# activate — a SEPARATE invocation from tools/design-runner.sh's own product/adversarial/fold, spawned
# only once that drafting run has already finished and exited. Separate invocation is the whole point:
# it naturally carries its OWN run id (its own PID), so the `design-independence` evaluator's own
# author != verifier comparison — held over the PM's own ledger, never the doc's authorship lines —
# has two genuinely distinct run ids to compare, never a same-process naming trick.
#
# Usage: design-review-runner.sh <owner/repo> <seed-stem>
#
# Locates the drafting run through the one pointer tools/design-runner.sh leaves at its own exit
# ($DEV_RUNNER_HOME/pm/latest-draft-<repo-slug>.txt naming that run's dir) — never re-derives it.
#
#   fit         — the architect's spec-ready moment (architect.md, moment 1); its verdict is typed
#                 into the draft as `YR-DESIGN-FIT`. The adversarial round's own verdict (already
#                 decided by design-runner.sh) is typed in here too, as `YR-DESIGN-REVIEW` — this is
#                 the first stage with a vault-write mandate, so it is the first to type either.
#   arch        — the architect's own mandate (Arm A): abstraction/pattern/libraries/language/
#                 boundaries, >=1 argued alternative, a `fit`/`refit`/`block` verdict, and an ADR. A
#                 `block` verdict earns exactly ONE fold-and-re-review; still `block` after that
#                 returns the draft to the triage issue (a flagged pack line) and stops — never
#                 activated.
#   activate    — asks the engine (`process.py transition-check design-doc.draft->active.machinery`)
#                 and writes only on exit 0, through `tools/vault_api.py` (the ADR, the draft, its
#                 `YR-ACCEPT` line, the `status: active` frontmatter set) — never a filesystem write.
set -euo pipefail

export YR_MACHINERY=1

CLAUDE_BIN="${CLAUDE_BIN:-claude}"; GH_BIN="${GH_BIN:-gh}"
EFFORT="${EFFORT:-high}"
DESIGN_MODEL="${DESIGN_MODEL:-}"
DEV_RUNNER_HOME="${DEV_RUNNER_HOME:-$HOME/.cache/dev-runner}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SELF_DIR/stage_lib.sh"

log(){ echo "design-review-runner: $*" >&2; }
usage(){ echo "usage: design-review-runner.sh <owner/repo> <seed-stem>" >&2; exit 2; }

REPO="${1:-}"; SEED="${2:-}"
[ -n "$REPO" ] && [ -n "$SEED" ] || usage

resolve_role review "$DESIGN_MODEL" "" "$DESIGN_MODEL"
[ "$R_STATUS" != unknown ] || { log "design model unresolved — refusing"; exit 2; }
BUILD_ID="$R_ID"

POINTER="$DEV_RUNNER_HOME/pm/latest-draft-$(printf '%s' "$REPO" | tr '/.' '-').txt"
[ -f "$POINTER" ] || { log "no drafting run recorded for $REPO ($POINTER absent) — nothing to review"; exit 2; }
DRAFT_RUN_DIR="$(cat "$POINTER")"
[ -f "$DRAFT_RUN_DIR/draft-final.md" ] || { log "no draft-final.md at $DRAFT_RUN_DIR — nothing to review"; exit 2; }

RUN_ID="design-review-$(printf '%s' "$REPO" | tr '/.' '--')-$$"
RUN_DIR="$DEV_RUNNER_HOME/runs/$RUN_ID"
mkdir -p "$RUN_DIR"
WT="$RUN_DIR"
LEDGER_DIR="$DEV_RUNNER_HOME/ledger"

# the sidecars the deterministic evaluators (invoked later, out-of-process, with only `--path <this
# run dir's draft file>`) read rather than re-derive: this process already knows its own task and its
# own run id.
printf '%s#%s' "$REPO" "$SEED" > "$RUN_DIR/task.txt"
printf '%s' "$RUN_ID" > "$RUN_DIR/review-run-id.txt"

ledger_row(){   # $1 = stage name, $2 = outcome ("ok"|"failed")
  local now_iso; now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 "$SELF_DIR/ledger.py" append --ledger-dir "$LEDGER_DIR" --kind design --stage "$1" \
    --run-id "$RUN_ID" --task "$REPO#$SEED" --repo "$REPO" --run-dir "$RUN_DIR" \
    --build-model "$BUILD_ID" --outcome-type "$2" \
    --ts-start "$now_iso" --ts-end "$now_iso" --wall-seconds 0 >/dev/null 2>&1 \
    || log "warn: ledger row not appended for stage '$1' (non-fatal)"
}

FIT_SYS="You are the PM agent's fit stage (it-36 slice F) — the architect's spec-ready moment (skills/factory/references/architect.md, moment 1). Verify the draft's grounding against the current tree and its supersession disposition. End your reply with a line beginning exactly VERDICT: fit, VERDICT: refit, or VERDICT: block."
ARCH_SYS="You are the PM agent's architect stage (it-36 slice F) — the architect's own mandate (Arm A). Judge the drafted design's architecture for the feature at hand: abstraction, pattern, libraries, language, boundaries. Name at least one argued alternative, each on its own line beginning exactly ALTERNATIVE: <the alternative, argued>. End your reply with a line beginning exactly VERDICT: fit, VERDICT: refit, or VERDICT: block."
ARCH_FOLD_SYS="You are the PM agent's arch-fold stage (it-36 slice F). Fold the architect's own findings (one round only) into the draft, producing a revised draft. Write ONLY the revised draft to stdout — no commentary, no preamble."

ARCHITECT_PATH="$SELF_DIR/../skills/factory/references/architect.md"
architect_text=""; [ -f "$ARCHITECT_PATH" ] && architect_text="$(cat "$ARCHITECT_PATH")"
APP_SLUG="${YR_GH_APP_SLUG:-yr-pm}"

cp "$DRAFT_RUN_DIR/draft-final.md" "$RUN_DIR/draft-final.md"

log "fit: $(basename "$CLAUDE_BIN") [$BUILD_ID]"
run_stage "$FIT_SYS" \
  "$(printf 'Architect charter:\n%s\n\nDraft:\n%s' "$architect_text" "$(cat "$RUN_DIR/draft-final.md")")" \
  "$RUN_DIR/fit.log" "Read Bash" "$BUILD_ID" \
  || { ledger_row fit failed; log "fit stage failed — stopping"; exit 1; }
ledger_row fit ok
python3 "$SELF_DIR/design_gate.py" parse-fit --in "$RUN_DIR/fit.log" > "$RUN_DIR/fit-result.json" \
  || { log "fit stage output malformed — stopping"; exit 1; }
FIT_VERDICT="$(python3 -c 'import json; print(json.load(open("'"$RUN_DIR"'/fit-result.json"))["verdict"])')"

# the adversarial round's verdict (already decided by design-runner.sh's own log) plus the fit
# verdict, typed into the draft — records.toml's own YR-DESIGN-REVIEW / YR-DESIGN-FIT (who/verdict).
case "$( [ -f "$DRAFT_RUN_DIR/adversarial.log" ] && verdict_line "$DRAFT_RUN_DIR/adversarial.log" )" in
  "VERDICT: APPROVE") ADV_VERDICT="approve" ;;
  *)                  ADV_VERDICT="changes-requested" ;;
esac
printf '\nYR-DESIGN-REVIEW: who=%s verdict=%s\nYR-DESIGN-FIT: who=%s verdict=%s\n' \
  "$APP_SLUG" "$ADV_VERDICT" "$APP_SLUG" "$FIT_VERDICT" >> "$RUN_DIR/draft-final.md"

# arch: the architect's own mandate. A `block` verdict earns exactly ONE fold-and-re-review
# (architect.md's own charter: earned work, not an unbounded loop) before the draft returns to the
# triage issue, unactivated.
run_arch_review(){   # $1 = arch log path, $2 = arch-result JSON path
  log "arch: $(basename "$CLAUDE_BIN") [$BUILD_ID]"
  run_stage "$ARCH_SYS" \
    "$(printf 'Architect charter:\n%s\n\nDraft:\n%s' "$architect_text" "$(cat "$RUN_DIR/draft-final.md")")" \
    "$1" "Read Bash" "$BUILD_ID" \
    || { ledger_row arch failed; log "arch stage failed — stopping"; exit 1; }
  ledger_row arch ok
  python3 "$SELF_DIR/design_gate.py" parse-arch --in "$1" > "$2" \
    || { log "arch stage output malformed — stopping"; exit 1; }
}

run_arch_review "$RUN_DIR/arch.log" "$RUN_DIR/arch-result.json"
ARCH_VERDICT="$(python3 -c 'import json; print(json.load(open("'"$RUN_DIR"'/arch-result.json"))["verdict"])')"

if [ "$ARCH_VERDICT" = "block" ]; then
  log "arch verdict: block — one fold-and-re-review"
  run_stage "$ARCH_FOLD_SYS" \
    "$(printf 'Architect findings:\n%s\n\nDraft:\n%s' "$(cat "$RUN_DIR/arch.log")" "$(cat "$RUN_DIR/draft-final.md")")" \
    "$RUN_DIR/arch-fold.log" "Read Bash" "$BUILD_ID" \
    || { ledger_row arch-fold failed; log "arch-fold stage failed — stopping"; exit 1; }
  cp "$RUN_DIR/arch-fold.log" "$RUN_DIR/draft-final.md"
  ledger_row arch-fold ok

  run_arch_review "$RUN_DIR/arch2.log" "$RUN_DIR/arch-result.json"
  ARCH_VERDICT="$(python3 -c 'import json; print(json.load(open("'"$RUN_DIR"'/arch-result.json"))["verdict"])')"
fi

if [ "$ARCH_VERDICT" = "block" ]; then
  log "arch verdict remains block after one fold — returning the draft to the triage issue, unactivated"
  if [ -n "${DESIGN_TRIAGE_ISSUE:-}" ]; then
    python3 "$SELF_DIR/design_gate.py" flag-block --repo "$REPO" --triage-issue "$DESIGN_TRIAGE_ISSUE" \
      --seed "$SEED" --arch-result "$RUN_DIR/arch-result.json" \
      || log "warn: could not post the blocked pack line (non-fatal)"
  else
    log "warn: DESIGN_TRIAGE_ISSUE unset — cannot post the blocked pack line"
  fi
  exit 0
fi

# activate: the engine decides (process.py transition-check design-doc.draft->active.machinery); the
# vault client (tools/vault_api.py) writes only on its say-so. DESIGN_COMPONENT_ROOT names the vault
# component's own local mirror root (item P's own provisioning) — with no root to resolve a
# destination from, activation cannot proceed and stops here, loudly.
if [ -z "${DESIGN_COMPONENT_ROOT:-}" ]; then
  log "warn: DESIGN_COMPONENT_ROOT unset — cannot resolve the activation's vault paths; stopping short of activation"
  exit 0
fi
PATHS_JSON="$(python3 "$SELF_DIR/design_gate.py" resolve-paths --component-root "$DESIGN_COMPONENT_ROOT" --seed "$SEED")"
VAULT_PATH="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["vault_path"])' "$PATHS_JSON")"
ARCHITECTURE_HOME="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["architecture_home"])' "$PATHS_JSON")"
ADR_SLUG="$(date -u +%Y-%m-%d)-${SEED}-arch-decision"
ADR_TITLE="Architecture decision — ${SEED}"

log "activate: path=$VAULT_PATH"
python3 "$SELF_DIR/design_gate.py" activate --path "$RUN_DIR/draft-final.md" --vault-path "$VAULT_PATH" \
  --architecture-home "$ARCHITECTURE_HOME" --adr-slug "$ADR_SLUG" --adr-title "$ADR_TITLE" \
  --arch-result "$RUN_DIR/arch-result.json" --who "$APP_SLUG" \
  || { log "activation refused or failed — the draft stays draft"; exit 1; }

log "done: activated at $VAULT_PATH"
