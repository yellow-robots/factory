#!/usr/bin/env bash
# cross-runner.sh — the crossing's own stage runner (it-36 slice G, #472): `cross-draft`,
# `rfc-review` (the cold technical-rfc review), `fold` (on REQUEST CHANGES, once), `arch` (the
# architecture review; on `block`, one fold-and-re-review — design-review-runner.sh's own pattern,
# it-36 slice F) — four `claude -p` stages through the SAME sourced harness every PM runner shares
# (tools/stage_lib.sh, it-36 slice C). Every deterministic gate and the filing act itself belong to
# tools/cross.py, never re-implemented here — this script only drafts, reviews, and hands finished
# files to that tool.
#
# NAMED HONESTLY (cold-review I5): tools/design_gate.py's sweep has no `cross` position/spawn point
# today — spawning this script mechanically (the natural next position after F's `activate`) is a
# future slice's own duty. Until then, an attended operator (or a future sweep) invokes it directly
# once a design doc has been drafted (E), reviewed and activated (F).
#
# Usage: cross-runner.sh <owner/repo> <seed> <vault-doc-rel-path> <design-name>
#
#   seed               — the crossing's own ideas-file stem (YR-TRIAGE's own seed= identifier) —
#                        locates the drafting run the SAME way design-review-runner.sh does (below),
#                        and is written back onto the PM config (alongside the filed epic number) so
#                        a LATER promote.sh machinery flip can resolve the owner's own triage license.
#   vault-doc-rel-path — the ALREADY-ACTIVE governing design doc's REST-relative vault path (F's own
#                        activation wrote it there) — never re-derived: `resolve-paths`' own iteration
#                        ordinal is NOT idempotent to recompute after the fact (it scans the tree for
#                        the highest existing folder — calling it again post-activation would find
#                        the folder F's activation just created and return the NEXT one instead).
#   design-name        — the governing design's name, for the `YR-EPIC-APPROVAL` record.
#
# Locates the drafting run through the SAME pointer tools/design-runner.sh leaves at its own exit
# ($DEV_RUNNER_HOME/pm/latest-draft-<repo-slug>.txt naming that run's dir) that design-review-
# runner.sh already reads — never re-derives it; `draft-final.md` there is the design doc's own
# local text (also now active in the vault, per F). DESIGN_COMPONENT_ROOT (optional; F's own
# provisioning) resolves ONLY the architecture home (`tools/design_gate.py resolve-paths` — the
# `architecture_home` half of that call is stable/idempotent, unlike `vault_path`, since it never
# depends on the iteration-ordinal scan) — when unset, the crossing still proceeds, just without a
# real ADR (the epic body still carries the human-facing verdict/alternative prose).
#
#   cross-draft — the design doc + skills/factory/templates/technical-rfc.md +
#                 skills/factory/templates/task.md on stdin -> one combined response, split by
#                 tools/cross.py split-draft into technical-rfc.md + slice-N.md + manifest.json.
#   rfc-review  — skills/factory/references/reviewing.md's own cold-review standard against the
#                 technical-rfc; ends with a VERDICT: APPROVE / REQUEST CHANGES line
#                 (review_bundle.py's own grammar). REQUEST CHANGES earns exactly one
#                 fold-and-re-review (the WHOLE combined draft, re-split); still not APPROVE after
#                 that stops here, unfiled.
#   arch        — the architect's own mandate (Arm A) on the technical-rfc (spec criterion 12: an
#                 argued alternative, a fit/refit/block verdict, an ADR — design_gate.py's own
#                 parse-arch grammar). A `block` verdict earns exactly one fold-and-re-review of the
#                 technical-rfc alone; still block after that stops here, unfiled.
#   file        — `git fetch origin` on the target repo's own shared-clone checkout (never a
#                 worktree cut), then `tools/cross.py file`: check_links, check_task (--base-ref
#                 origin/main), the epic + its sub-issues filed by tool, YR-EPIC-APPROVAL,
#                 crossed_to, the ADR + YR-ARCH-REVIEW when DESIGN_COMPONENT_ROOT resolved one, and
#                 the PM config write-back (epic_issue/seed). This script then leaves its own
#                 output pointer, $DEV_RUNNER_HOME/pm/latest-epic-<repo-slug>.txt (design-runner.sh's
#                 own `latest-draft` pointer's sibling). The flip itself is tools/promote.sh's own
#                 machinery arm — a separate act, on a separate trail event (the triage `go`
#                 disposition, keyed by this SAME seed).
set -euo pipefail

export YR_MACHINERY=1

CLAUDE_BIN="${CLAUDE_BIN:-claude}"; GH_BIN="${GH_BIN:-gh}"; GIT_BIN="${GIT_BIN:-git}"
EFFORT="${EFFORT:-high}"
DESIGN_MODEL="${DESIGN_MODEL:-}"
DEV_RUNNER_HOME="${DEV_RUNNER_HOME:-$HOME/.cache/dev-runner}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SELF_DIR/stage_lib.sh"

# CROSS_PY is a test-only override (the DESIGN_RUNNER precedent, tools/design_gate.py) — production
# never sets it, so the real tools/cross.py runs; a test substitutes a fake to exercise this script's
# own orchestration without a live gh/vault or a real target-repo checkout.
CROSS_PY="${CROSS_PY:-$SELF_DIR/cross.py}"
YR_WORKSPACE="${YR_WORKSPACE:-$(cd "$SELF_DIR/../.." && pwd)}"

log(){ echo "cross-runner: $*" >&2; }
usage(){ echo "usage: cross-runner.sh <owner/repo> <seed> <vault-doc-rel-path> <design-name>" >&2; exit 2; }

REPO="${1:-}"; SEED="${2:-}"; VAULT_DOC="${3:-}"; DESIGN_NAME="${4:-}"
[ -n "$REPO" ] && [ -n "$SEED" ] && [ -n "$VAULT_DOC" ] && [ -n "$DESIGN_NAME" ] || usage

# I1 (cold review of db47805): never fabricate the App identity — a missing YR_GH_APP_SLUG refuses,
# the same discipline tools/promote.sh's machinery arm holds.
[ -n "${YR_GH_APP_SLUG:-}" ] || { log "YR_GH_APP_SLUG is unset — refusing (never fabricate the App identity)"; exit 2; }
APP_SLUG="$YR_GH_APP_SLUG"

REPO_SLUG="$(printf '%s' "$REPO" | tr '/.' '--')"
POINTER="$DEV_RUNNER_HOME/pm/latest-draft-$REPO_SLUG.txt"
[ -f "$POINTER" ] || { log "no drafting run recorded for $REPO ($POINTER absent) — nothing to cross"; exit 2; }
DRAFT_RUN_DIR="$(cat "$POINTER")"
DESIGN_DOC="$DRAFT_RUN_DIR/draft-final.md"
[ -f "$DESIGN_DOC" ] || { log "no draft-final.md at $DRAFT_RUN_DIR — nothing to cross"; exit 2; }

REPO_NAME="${REPO#*/}"
REPO_CHECKOUT="${CROSS_REPO_CHECKOUT:-$YR_WORKSPACE/$REPO_NAME}"
[ -d "$REPO_CHECKOUT" ] || { log "no checkout at $REPO_CHECKOUT (\$YR_WORKSPACE/$REPO_NAME) — refusing"; exit 2; }

resolve_role review "$DESIGN_MODEL" "" "$DESIGN_MODEL"
[ "$R_STATUS" != unknown ] || { log "design model unresolved — refusing"; exit 2; }
BUILD_ID="$R_ID"

# ADR plumbing (I4): architecture_home is stable/idempotent to recompute (see the header note above
# `vault_path`'s own non-idempotence); ADR_SLUG/ADR_TITLE follow design-review-runner.sh's own
# convention. Absent DESIGN_COMPONENT_ROOT, the crossing still proceeds — just without a real ADR.
ARCHITECTURE_HOME=""
ADR_SLUG=""
ADR_TITLE=""
if [ -n "${DESIGN_COMPONENT_ROOT:-}" ]; then
  PATHS_JSON="$(python3 "$SELF_DIR/design_gate.py" resolve-paths --component-root "$DESIGN_COMPONENT_ROOT" --seed "$SEED")"
  ARCHITECTURE_HOME="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["architecture_home"])' "$PATHS_JSON")"
  ADR_SLUG="$(date -u +%Y-%m-%d)-${SEED}-arch-decision"
  ADR_TITLE="Architecture decision — ${SEED}"
else
  log "warn: DESIGN_COMPONENT_ROOT unset — crossing without a real ADR (the epic body still carries the verdict/alternative prose)"
fi

RUN_ID="cross-$REPO_SLUG-$$"
RUN_DIR="$DEV_RUNNER_HOME/runs/$RUN_ID"
mkdir -p "$RUN_DIR"
WT="$RUN_DIR"   # no code worktree: the crossing files Issues, not a code change; run_stage's own
                # `cd "$WT"` just needs a stable directory to run each stage from.
LEDGER_DIR="$DEV_RUNNER_HOME/ledger"

ledger_row(){   # $1 = stage name, $2 = that stage's outcome ("ok"|"failed")
  local now_iso; now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 "$SELF_DIR/ledger.py" append --ledger-dir "$LEDGER_DIR" --kind design --stage "$1" \
    --run-id "$RUN_ID" --task "$REPO#$SEED" --repo "$REPO" --run-dir "$RUN_DIR" \
    --build-model "$BUILD_ID" --outcome-type "$2" \
    --ts-start "$now_iso" --ts-end "$now_iso" --wall-seconds 0 >/dev/null 2>&1 \
    || log "warn: ledger row not appended for stage '$1' (non-fatal)"
}

CROSS_DRAFT_SYS="You are the PM agent's crossing stage (it-36 slice G). Draft the technical-rfc from skills/factory/templates/technical-rfc.md, projecting the given ACTIVE design doc onto the target repo's own tree (cite exact files, read the tree, never guess). Reproduce the technical-rfc template's own marker comments verbatim, exactly as they appear in skills/factory/templates/technical-rfc.md — <!-- ═══════════════ ISSUE BODY · file from here ↓ ═══════════════ --> and <!-- ═══════════════ ↑ END ISSUE BODY · file to here ═══════════════ --> (the middle dot included) — and keep the task template's own ## Goal / ## Acceptance criteria / ## Context & links / ## Test expectations / ## Constraints / out of scope / ## Size section headings exactly as skills/factory/templates/task.md spells them; the filing tool locates the body by these markers/headings alone. Then draft one task body per anticipated slice from skills/factory/templates/task.md; each slice body must carry its own declared human dependencies and, where earned, a YR-GATE-TOUCHING: <reason> line at column 0 and escalation declarations at column 0 (Declares: external dependency <name> / Declares: data migration — presence only, never inferred). Output EXACTLY this shape and nothing else: the technical-rfc between lines '===TECHNICAL-RFC===' and '===END-TECHNICAL-RFC===', then one block per slice between '===SLICE task===' (a slice the runner will build) or '===SLICE attended===' (an attended slice) and '===END-SLICE==='. No commentary, no preamble, no text outside those blocks."
RFC_REVIEW_SYS="You are the PM agent's cold technical-rfc reviewer (it-36 slice G). Hold the drafted technical-rfc to the cold, rfc-review standard in skills/factory/references/reviewing.md. End your reply with a line beginning exactly VERDICT: APPROVE or VERDICT: REQUEST CHANGES, per review_bundle.py's own grammar."
FOLD_SYS="You are the PM agent's crossing fold stage (it-36 slice G). Fold the cold review's findings into the FULL draft (technical-rfc + every slice), producing a revised draft in the SAME shape you were given (the ===TECHNICAL-RFC===/===SLICE...=== blocks). Write ONLY the revised draft to stdout — no commentary, no preamble."
ARCH_SYS="You are the PM agent's architect stage (it-36 slice G) — the architect's own mandate (Arm A), at the crossing (spec criterion 12). Judge the drafted technical-rfc's architecture: abstraction, pattern, libraries, language, boundaries. Name at least one argued alternative, each on its own line beginning exactly ALTERNATIVE: <the alternative, argued>. End your reply with a line beginning exactly VERDICT: fit, VERDICT: refit, or VERDICT: block."
ARCH_FOLD_SYS="You are the PM agent's crossing arch-fold stage (it-36 slice G). Fold the architect's own findings (one round only) into the technical-rfc, producing a revised technical-rfc. Write ONLY the revised technical-rfc to stdout — no commentary, no preamble."

TEMPLATE_RFC_PATH="$SELF_DIR/../skills/factory/templates/technical-rfc.md"
TEMPLATE_TASK_PATH="$SELF_DIR/../skills/factory/templates/task.md"
REVIEWING_PATH="$SELF_DIR/../skills/factory/references/reviewing.md"
ARCHITECT_PATH="$SELF_DIR/../skills/factory/references/architect.md"
design_text="$(cat "$DESIGN_DOC")"
rfc_template_text=""; [ -f "$TEMPLATE_RFC_PATH" ] && rfc_template_text="$(cat "$TEMPLATE_RFC_PATH")"
task_template_text=""; [ -f "$TEMPLATE_TASK_PATH" ] && task_template_text="$(cat "$TEMPLATE_TASK_PATH")"
reviewing_text=""; [ -f "$REVIEWING_PATH" ] && reviewing_text="$(cat "$REVIEWING_PATH")"
architect_text=""; [ -f "$ARCHITECT_PATH" ] && architect_text="$(cat "$ARCHITECT_PATH")"

split_and_check(){   # $1 = raw combined-draft path -> (re)populates technical-rfc.md, slice-N.md,
                     # manifest.json in $RUN_DIR — the ONE parser for the combined shape (tools/cross.py)
  python3 "$CROSS_PY" split-draft "$1" --out-dir "$RUN_DIR" >/dev/null \
    || { log "cross-draft output malformed — stopping"; exit 1; }
}

log "cross-draft: $(basename "$CLAUDE_BIN") [$BUILD_ID] repo=$REPO seed=$SEED"
run_stage "$CROSS_DRAFT_SYS" \
  "$(printf 'Design doc (%s):\n%s\n\nTechnical-rfc template:\n%s\n\nTask template:\n%s' \
     "$DESIGN_NAME" "$design_text" "$rfc_template_text" "$task_template_text")" \
  "$RUN_DIR/cross-draft.log" "Read Bash" "$BUILD_ID" \
  || { ledger_row cross-draft failed; log "cross-draft stage failed — stopping"; exit 1; }
cp "$RUN_DIR/cross-draft.log" "$RUN_DIR/draft-raw.txt"
ledger_row cross-draft ok
split_and_check "$RUN_DIR/draft-raw.txt"

rfc_review_once(){   # $1 = log path -> sets RFC_VERDICT (APPROVE | REQUEST CHANGES)
  log "rfc-review: $(basename "$CLAUDE_BIN") [$BUILD_ID]"
  run_stage "$RFC_REVIEW_SYS" \
    "$(printf 'Reviewing standard:\n%s\n\nTechnical-rfc draft:\n%s' \
       "$reviewing_text" "$(cat "$RUN_DIR/technical-rfc.md")")" \
    "$1" "Read Bash" "$BUILD_ID" \
    || { ledger_row rfc-review failed; log "rfc-review stage failed — stopping"; exit 1; }
  ledger_row rfc-review ok
  case "$(verdict_line "$1")" in
    "VERDICT: APPROVE") RFC_VERDICT="APPROVE" ;;
    *)                  RFC_VERDICT="REQUEST CHANGES" ;;
  esac
}

rfc_review_once "$RUN_DIR/rfc-review.log"

if [ "$RFC_VERDICT" = "REQUEST CHANGES" ]; then
  log "rfc-review verdict: REQUEST CHANGES — one fold-and-re-review"
  run_stage "$FOLD_SYS" \
    "$(printf 'Draft:\n%s\n\nCold review:\n%s' "$(cat "$RUN_DIR/draft-raw.txt")" "$(cat "$RUN_DIR/rfc-review.log")")" \
    "$RUN_DIR/fold.log" "Read Bash" "$BUILD_ID" \
    || { ledger_row fold failed; log "fold stage failed — stopping"; exit 1; }
  cp "$RUN_DIR/fold.log" "$RUN_DIR/draft-raw.txt"
  ledger_row fold ok
  split_and_check "$RUN_DIR/draft-raw.txt"
  rfc_review_once "$RUN_DIR/rfc-review2.log"
fi

if [ "$RFC_VERDICT" != "APPROVE" ]; then
  log "cold technical-rfc review still REQUEST CHANGES after one fold — stopping short of filing, unfiled"
  exit 1
fi

run_arch_review(){   # $1 = arch log path, $2 = arch-result JSON path
  log "arch: $(basename "$CLAUDE_BIN") [$BUILD_ID]"
  run_stage "$ARCH_SYS" \
    "$(printf 'Architect charter:\n%s\n\nTechnical-rfc draft:\n%s' "$architect_text" "$(cat "$RUN_DIR/technical-rfc.md")")" \
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
    "$(printf 'Architect findings:\n%s\n\nTechnical-rfc draft:\n%s' "$(cat "$RUN_DIR/arch.log")" "$(cat "$RUN_DIR/technical-rfc.md")")" \
    "$RUN_DIR/arch-fold.log" "Read Bash" "$BUILD_ID" \
    || { ledger_row arch-fold failed; log "arch-fold stage failed — stopping"; exit 1; }
  cp "$RUN_DIR/arch-fold.log" "$RUN_DIR/technical-rfc.md"
  ledger_row arch-fold ok

  run_arch_review "$RUN_DIR/arch2.log" "$RUN_DIR/arch-result.json"
  ARCH_VERDICT="$(python3 -c 'import json; print(json.load(open("'"$RUN_DIR"'/arch-result.json"))["verdict"])')"
fi

if [ "$ARCH_VERDICT" = "block" ]; then
  log "arch verdict remains block after one fold — stopping short of filing, unfiled"
  exit 1
fi

log "fetch: git fetch origin ($REPO_CHECKOUT) — never a worktree cut in the shared clones"
"$GIT_BIN" -C "$REPO_CHECKOUT" fetch origin \
  || { log "git fetch origin failed at $REPO_CHECKOUT — stopping"; exit 1; }

SLICE_ARGS=()
while IFS=$'\t' read -r path kind; do
  [ -n "$path" ] || continue
  SLICE_ARGS+=("--slice" "$RUN_DIR/$path:$kind")
done < <(python3 -c '
import json, sys
for entry in json.load(open(sys.argv[1])):
    print(entry["path"] + "\t" + entry["kind"])
' "$RUN_DIR/manifest.json")

ADR_ARGS=()
if [ -n "$ARCHITECTURE_HOME" ]; then
  ADR_ARGS=(--architecture-home "$ARCHITECTURE_HOME" --adr-slug "$ADR_SLUG" --adr-title "$ADR_TITLE")
fi

log "file: filing the epic and ${#SLICE_ARGS[@]} slice arg(s) via tools/cross.py"
python3 "$CROSS_PY" file --repo "$REPO" --who "$APP_SLUG" --design "$DESIGN_NAME" --seed "$SEED" \
  --review "cold technical-rfc review: $RFC_VERDICT" \
  --technical-rfc "$RUN_DIR/technical-rfc.md" "${SLICE_ARGS[@]}" "${ADR_ARGS[@]}" \
  --arch-result "$RUN_DIR/arch-result.json" --vault-doc "$VAULT_DOC" \
  --repo-root "$REPO_CHECKOUT" --base-ref origin/main \
  > "$RUN_DIR/cross-result.json" \
  || { log "filing refused or failed — see $RUN_DIR/cross-result.json"; exit 1; }

EPIC_NUMBER="$(python3 -c 'import json; print(json.load(open("'"$RUN_DIR"'/cross-result.json")).get("epic_number", ""))')"
if [ -n "$EPIC_NUMBER" ]; then
  mkdir -p "$DEV_RUNNER_HOME/pm"
  printf '%s\n' "$EPIC_NUMBER" > "$DEV_RUNNER_HOME/pm/latest-epic-$REPO_SLUG.txt"
fi

log "done: crossed — $(cat "$RUN_DIR/cross-result.json")"
