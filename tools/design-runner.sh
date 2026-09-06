#!/usr/bin/env bash
# design-runner.sh — the PM's own stage runner (it-36 slice E, #470): product, adversarial, fold —
# three cold `claude -p` stages, sequenced, each leaving its own row in the PM instance's ledger
# (kind: design). Sourced stage library: byte-identical run_stage machinery to tools/dev-runner.sh's
# own (tools/stage_lib.sh, it-36 slice C) — the PM agent runs the SAME harness, never a fork of it.
#
# Usage: design-runner.sh <owner/repo> <seed-stem>
#
# Spawned by tools/design_gate.py's sweep (never invoked directly in production) once a seed carries
# a licensed `go` disposition and no design is already in flight for the repo — that exclusivity is
# the SWEEP's own rule (one pidfile per repo), not this script's: it assumes it was launched at most
# once per repo at a time, and that killing its process group (SIGTERM) is how a reversal stops it.
#
# Drafts only — never writes to the vault (a later slice's own duty, through the vault client):
#   product     — the seed + the strategy doc + skills/factory/templates/product-spec.md on stdin ->
#                 a draft written to the run dir (draft.md).
#   adversarial — skills/factory/references/reviewing.md's own cold-review standard against the
#                 draft; ends with a `VERDICT:` line, review_bundle.py's own grammar.
#   fold        — folds the adversarial round's findings into the draft (draft-final.md).
set -euo pipefail

export YR_MACHINERY=1

CLAUDE_BIN="${CLAUDE_BIN:-claude}"; GH_BIN="${GH_BIN:-gh}"; GIT_BIN="${GIT_BIN:-git}"
EFFORT="${EFFORT:-high}"
# Upper-pipeline convention (models.toml's own header comment): strategy/product-definition work runs
# on the strongest available class — the registry's "review" role default (today: opus) — never the
# lower "build" tier the implement/test/check stages use. DESIGN_MODEL is the one operator override,
# atop that same role.
DESIGN_MODEL="${DESIGN_MODEL:-}"
DEV_RUNNER_HOME="${DEV_RUNNER_HOME:-$HOME/.cache/dev-runner}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SELF_DIR/stage_lib.sh"

log(){ echo "design-runner: $*" >&2; }
usage(){ echo "usage: design-runner.sh <owner/repo> <seed-stem>" >&2; exit 2; }

REPO="${1:-}"; SEED="${2:-}"
[ -n "$REPO" ] && [ -n "$SEED" ] || usage

resolve_role review "$DESIGN_MODEL" "" "$DESIGN_MODEL"
[ "$R_STATUS" != unknown ] || { log "design model unresolved — refusing"; exit 2; }
BUILD_ID="$R_ID"   # run_stage's own default-model global

RUN_ID="design-$(printf '%s' "$REPO" | tr '/.' '--')-$$"
RUN_DIR="$DEV_RUNNER_HOME/runs/$RUN_ID"
mkdir -p "$RUN_DIR"
WT="$RUN_DIR"   # no repo worktree: the PM drafts a vault note, not a code change; run_stage's own
                # `cd "$WT"` just needs a stable directory to run each stage from.
LEDGER_DIR="$DEV_RUNNER_HOME/ledger"

# ledger_row (it-36 slice E, #470): one yr-ledger-row/1 JSONL row per STAGE (kind=design, stage=$1),
# appended right after that stage finishes — distinct from dev-runner.sh's own ledger_append, which
# writes exactly one row per whole invocation. Fail-soft: never blocks or fails the run.
ledger_row(){   # $1 = stage name, $2 = that stage's outcome ("ok"|"failed")
  local now_iso; now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 "$SELF_DIR/ledger.py" append --ledger-dir "$LEDGER_DIR" --kind design --stage "$1" \
    --run-id "$RUN_ID" --task "$REPO#$SEED" --repo "$REPO" --run-dir "$RUN_DIR" \
    --build-model "$BUILD_ID" --outcome-type "$2" \
    --ts-start "$now_iso" --ts-end "$now_iso" --wall-seconds 0 >/dev/null 2>&1 \
    || log "warn: ledger row not appended for stage '$1' (non-fatal)"
}

PRODUCT_SYS="You are the PM agent's product stage (it-36). Draft a product spec for the given ideas-backlog seed, honoring the strategy doc's own themes/constraints, following the shape of skills/factory/templates/product-spec.md exactly. Write ONLY the draft to stdout — no commentary, no preamble."
ADVERSARIAL_SYS="You are the PM agent's adversarial reviewer (it-36). Hold the draft to the cold, rfc-review standard in skills/factory/references/reviewing.md. End your reply with a line beginning exactly VERDICT: APPROVE or VERDICT: REQUEST CHANGES, per review_bundle.py's own grammar."
FOLD_SYS="You are the PM agent's fold stage (it-36). Fold the adversarial round's findings into the draft, producing the final draft. Write ONLY the final draft to stdout — no commentary, no preamble."

TEMPLATE_PATH="$SELF_DIR/../skills/factory/templates/product-spec.md"
REVIEWING_PATH="$SELF_DIR/../skills/factory/references/reviewing.md"
# the seed text + strategy doc travel as plain text on stdin, resolved by the sweep's own spawn
# (DESIGN_SEED_DOC/DESIGN_STRATEGY_DOC) — reads only, never a vault write (F's own duty).
seed_text=""; [ -n "${DESIGN_SEED_DOC:-}" ] && [ -f "$DESIGN_SEED_DOC" ] && seed_text="$(cat "$DESIGN_SEED_DOC")"
strategy_text=""; [ -n "${DESIGN_STRATEGY_DOC:-}" ] && [ -f "$DESIGN_STRATEGY_DOC" ] && strategy_text="$(cat "$DESIGN_STRATEGY_DOC")"
template_text=""; [ -f "$TEMPLATE_PATH" ] && template_text="$(cat "$TEMPLATE_PATH")"
reviewing_text=""; [ -f "$REVIEWING_PATH" ] && reviewing_text="$(cat "$REVIEWING_PATH")"

log "product: $(basename "$CLAUDE_BIN") [$BUILD_ID] repo=$REPO seed=$SEED"
run_stage "$PRODUCT_SYS" \
  "$(printf 'Seed (%s):\n%s\n\nStrategy doc:\n%s\n\nTemplate (skills/factory/templates/product-spec.md):\n%s' \
     "$SEED" "$seed_text" "$strategy_text" "$template_text")" \
  "$RUN_DIR/product.log" "Read Bash" "$BUILD_ID" \
  || { ledger_row product failed; log "product stage failed — stopping"; exit 1; }
cp "$RUN_DIR/product.log" "$RUN_DIR/draft.md"
ledger_row product ok

log "adversarial: $(basename "$CLAUDE_BIN") [$BUILD_ID]"
run_stage "$ADVERSARIAL_SYS" \
  "$(printf 'Reviewing standard:\n%s\n\nDraft:\n%s' "$reviewing_text" "$(cat "$RUN_DIR/draft.md")")" \
  "$RUN_DIR/adversarial.log" "Read Bash" "$BUILD_ID" \
  || { ledger_row adversarial failed; log "adversarial stage failed — stopping"; exit 1; }
ledger_row adversarial ok

log "fold: $(basename "$CLAUDE_BIN") [$BUILD_ID]"
run_stage "$FOLD_SYS" \
  "$(printf 'Draft:\n%s\n\nAdversarial review:\n%s' "$(cat "$RUN_DIR/draft.md")" "$(cat "$RUN_DIR/adversarial.log")")" \
  "$RUN_DIR/fold.log" "Read Bash" "$BUILD_ID" \
  || { ledger_row fold failed; log "fold stage failed — stopping"; exit 1; }
cp "$RUN_DIR/fold.log" "$RUN_DIR/draft-final.md"
ledger_row fold ok

log "done: final draft at $RUN_DIR/draft-final.md (the vault write is a later slice's own duty)"
