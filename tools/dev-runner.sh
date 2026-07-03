#!/usr/bin/env bash
# dev-runner — take a Ready task through one headless implement pass to an open PR, tracking lifecycle
# state on the NATIVE GitHub Projects Status/Reason fields (RFC 0003 rev 2: status belongs to the task,
# via native fields — not labels). Type is the native Issue Type (set by the Issue Form); hierarchy is
# native sub-issues.
#
# Pipeline (each stage a separate cold `claude -p` — builder!=verifier): gate (Status==Ready, Type==Task) ->
#   claim (Status=In Progress) -> fresh worktree -> implement -> independent test (boundary-guarded:
#   tester writing outside tests/ -> Blocked) -> deterministic check gate (CHECK_CMD, one repair) ->
#   independent review (VERDICT gate, one repair) -> commit/push -> open PR -> Status=In Review.
#   empty acceptance criteria / unknown model override -> Status=Backlog + Reason=Needs-info (no LLM).
#   any stage failure                                  -> Reason=Blocked + comment (failure stays visible).
#   merge closes the issue; Projects' close->Done sets Status=Done natively.
# Dispatch: n8n polls Ready -> tools/dispatch.py -> this runner (RFC 0004). Operating model: AGENTS.md.
#
# Confinement is system-level (fresh worktree, scoped creds) so implement runs --permission-mode
# bypassPermissions: the walls are the environment, not an interactive prompt.
#
# Requires: bash, git, gh (>=2.94, authed, with `project` scope), python3, claude.
# Overridable for unit tests (no live LLM / no network): CLAUDE_BIN, GH_BIN, GIT_BIN.
# Project config (defaults = yellow-robots project #1; ids hardcoded below):
#   PROJECT_NUMBER, PROJECT_ID, STATUS_FIELD_ID, REASON_FIELD_ID, OPT_* option ids.
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"; GH_BIN="${GH_BIN:-gh}"; GIT_BIN="${GIT_BIN:-git}"
MODEL="${MODEL:-claude-sonnet-5}"; HARD_MODEL="${HARD_MODEL:-claude-opus-4-8}"; EFFORT="${EFFORT:-high}"
DEV_RUNNER_HOME="${DEV_RUNNER_HOME:-$HOME/.cache/dev-runner}"
# DoR Type gate: build only this native Issue Type. Empty disables it (repos without Issue Types).
# Use the no-colon form so an explicit REQUIRE_ISSUE_TYPE='' stays empty (a true opt-out), not defaulted.
REQUIRE_ISSUE_TYPE="${REQUIRE_ISSUE_TYPE-Task}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The factory builds sibling repos under one workspace root, discovered relative to this script
# (factory/tools/dev-runner.sh -> workspace = SELF_DIR/../..) so no absolute path is baked in. Override
# with YR_WORKSPACE. BASE_REPO / BASE_REF / CHECK_CMD are resolved once the target repo is known (see
# "resolve the target repo" below) from that repo's .yr/factory.toml — the factory carries no per-repo
# knowledge of its own.
YR_WORKSPACE="${YR_WORKSPACE:-$(cd "$SELF_DIR/../.." && pwd)}"

# --- Projects field config (status/reason live on the project item; RFC 0003) ---
PROJECT_NUMBER="${PROJECT_NUMBER:-1}"
PROJECT_ID="${PROJECT_ID:-PVT_kwDOEEAo0M4Ba6Ls}"
STATUS_FIELD_ID="${STATUS_FIELD_ID:-PVTSSF_lADOEEAo0M4Ba6LszhVuZlw}"
REASON_FIELD_ID="${REASON_FIELD_ID:-PVTSSF_lADOEEAo0M4Ba6LszhVzoxI}"
declare -A STATUS_OPT=( [Backlog]="${OPT_BACKLOG:-b863a902}" [Ready]="${OPT_READY:-c85eb5c1}"
                        ["In Progress"]="${OPT_INPROGRESS:-14e415a3}" ["In Review"]="${OPT_INREVIEW:-da2e6a49}"
                        [Done]="${OPT_DONE:-e614f531}" )
declare -A REASON_OPT=( [Needs-info]="${OPT_NEEDSINFO:-803a86fb}" [Blocked]="${OPT_BLOCKED:-fe4d566c}" )

die()  { echo "dev-runner: ERROR: $*" >&2; exit 1; }
gate() { echo "dev-runner: NOT READY: $*" >&2; exit 3; }   # DoR refusal — distinct exit code
log()  { echo "dev-runner: $*" >&2; }
usage(){ echo "usage: dev-runner.sh <issue#> [--repo <owner/name>] [--dry-run]" >&2; exit 2; }

# ---- parse args ----
ISSUE=""; REPO=""; DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)    REPO="${2:-}"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    -h|--help) usage;;
    -*)        die "unknown flag: $1";;
    *)         if [ -z "$ISSUE" ]; then ISSUE="$1"; shift; else die "unexpected arg: $1"; fi;;
  esac
done
[ -n "$ISSUE" ] || usage
case "$ISSUE" in *[!0-9]*|"") die "issue must be a number, got: '$ISSUE'";; esac

# ---- resolve repo / owner ----
if [ -z "$REPO" ]; then
  REPO="$("$GH_BIN" repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" \
    || die "could not resolve repo; pass --repo <owner/name>"
fi
OWNER="${REPO%/*}"

# ---- resolve the target repo's checkout + its build manifest (all relative to the workspace) ----
NAME="${REPO#*/}"
BASE_REPO="${BASE_REPO:-$YR_WORKSPACE/$NAME}"   # checkout convention: $YR_WORKSPACE/<name> (override: BASE_REPO)
# Per-repo build config lives in the repo, not the factory: .yr/factory.toml (check_cmd / model / base_ref).
MANIFEST="$BASE_REPO/.yr/factory.toml"
# Read the manifest from the build's base ref (origin/main), NOT the base checkout's working tree:
# the worktree is cut from that ref, so the manifest must come from there too — a drifted/dirty
# checkout (e.g. one doubling as a live dev workspace) then can't feed a stale or missing manifest.
# Fall back to the working-tree file when the ref read yields nothing (a repo not yet pushed; or the
# dry-run's non-git manifest dir).
MANIFEST_REF="${MANIFEST_REF:-origin/main}"
MF_RAW="$("$GIT_BIN" -C "$BASE_REPO" show "$MANIFEST_REF:.yr/factory.toml" 2>/dev/null || true)"
[ -z "$MF_RAW" ] && [ -f "$MANIFEST" ] && MF_RAW="$(cat "$MANIFEST")"
MF_CHECK_CMD=""; MF_MODEL=""; MF_BASE_REF=""
if [ -n "$MF_RAW" ]; then
  _mf_out="$(printf '%s' "$MF_RAW" | python3 -c 'import sys,tomllib
d=tomllib.loads(sys.stdin.read())
for k in ("check_cmd","model","base_ref"): print(str(d.get(k) or "").replace("\n"," "))' 2>/dev/null)" \
    || log "warn: could not parse manifest from $MANIFEST_REF"
  mapfile -t _mf <<<"$_mf_out"
  MF_CHECK_CMD="${_mf[0]:-}"; MF_MODEL="${_mf[1]:-}"; MF_BASE_REF="${_mf[2]:-}"
fi
# precedence everywhere: explicit env  >  repo manifest  >  built-in default
BASE_REF="${BASE_REF:-${MF_BASE_REF:-origin/main}}"; BASE_BRANCH="${BASE_REF#origin/}"
CHECK_CMD="${CHECK_CMD:-${MF_CHECK_CMD:-$BASE_REPO/.venv/bin/python -m pytest tests/ -q}}"

# ---- fetch issue (state/title/body) ----
ISSUE_JSON="$("$GH_BIN" issue view "$ISSUE" --repo "$REPO" --json number,title,body,state,issueType 2>/dev/null)" \
  || die "could not fetch issue #$ISSUE from $REPO"
TITLE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("title","") or "")')"
BODY="$(printf '%s' "$ISSUE_JSON"  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("body","") or "")')"
STATE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("state","") or "")')"
# native Issue Type name ("Task"/"Bug"/"Feature"), or "" when the issue is untyped (issueType: null).
ITYPE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import sys,json; t=json.load(sys.stdin).get("issueType") or {}; print((t.get("name","") if isinstance(t,dict) else "") or "")')"

# ---- find the project item id + current Status (status is project-item-resident, RFC 0003) ----
ITEMS_JSON="$("$GH_BIN" project item-list "$PROJECT_NUMBER" --owner "$OWNER" --limit 500 --format json 2>/dev/null)" \
  || die "could not query project #$PROJECT_NUMBER on $OWNER (is the gh 'project' scope granted?)"
ITEM_LINE="$(printf '%s' "$ITEMS_JSON" | python3 -c 'import sys,json
n=int(sys.argv[1])
for it in json.load(sys.stdin).get("items",[]):
    if ((it.get("content") or {}).get("number")) == n:
        print((it.get("id","") or "") + "\t" + (it.get("status","") or "")); break' "$ISSUE")"
ITEM_ID="${ITEM_LINE%%$'\t'*}"; ITEM_STATUS="${ITEM_LINE#*$'\t'}"
[ "$ITEM_ID" = "$ITEM_LINE" ] && ITEM_STATUS=""   # no tab => no match

# field setters (best-effort: a failed state write warns, never aborts the actual work)
_set_field(){ "$GH_BIN" project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
              --field-id "$1" --single-select-option-id "$2" >/dev/null 2>&1 || log "warn: could not set $3 on #$ISSUE"; }
set_status(){ local o="${STATUS_OPT[$1]:-}"; [ -n "$o" ] || { log "warn: no option id for Status=$1"; return 0; }
              _set_field "$STATUS_FIELD_ID" "$o" "Status=$1"; }
set_reason(){ local o="${REASON_OPT[$1]:-}"; [ -n "$o" ] || { log "warn: no option id for Reason=$1"; return 0; }
              _set_field "$REASON_FIELD_ID" "$o" "Reason=$1"; }
comment(){ "$GH_BIN" issue comment "$ISSUE" --repo "$REPO" --body "$1" >/dev/null 2>&1 || true; }

# ---- DoR gate (refuse before any work; never invokes the LLM on refusal; no writes) ----
[ "$STATE" = "OPEN" ] || gate "issue #$ISSUE is not open (state: ${STATE:-unknown})"
[ -n "$ITEM_ID" ]     || gate "issue #$ISSUE is not in project #$PROJECT_NUMBER"
[ "$ITEM_STATUS" = "Ready" ] || gate "issue #$ISSUE is not Ready (Status: ${ITEM_STATUS:-none})"
# Type gate: build Tasks only. A Feature/epic accidentally set Ready must NOT be built — epics are native
# sub-issue parents, not build units. Case-insensitive; REQUIRE_ISSUE_TYPE='' opts out (repos w/o types).
if [ -n "$REQUIRE_ISSUE_TYPE" ]; then
  [ "$(printf '%s' "$ITYPE" | tr '[:upper:]' '[:lower:]')" = "$(printf '%s' "$REQUIRE_ISSUE_TYPE" | tr '[:upper:]' '[:lower:]')" ] \
    || gate "issue #$ISSUE is not Type=$REQUIRE_ISSUE_TYPE (Type: ${ITYPE:-none}) — the runner builds Tasks only; track epics/Features as sub-issue parents, not build units."
fi

# acceptance-criteria block: from its heading to the next heading of equal-or-higher level (#, ##, ###).
AC="$(printf '%s\n' "$BODY" | awk '
  { low=tolower($0) }
  low ~ /^#+[[:space:]]*acceptance criteria/ { grab=1; next }
  grab && /^#(#(#)?)?[[:space:]]/ { grab=0 }
  grab { print }
')"
# real criteria need actual content (the Issue Form default "- [ ]" has no alphanumerics).
NEEDS_INFO=""
[ -n "$(printf '%s' "$AC" | tr -dc '[:alnum:]')" ] || NEEDS_INFO="the acceptance-criteria section is empty"

# ---- slug + branch ----
SLUG="$(printf '%s' "$TITLE" | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/[^a-z0-9]\+/-/g' -e 's/^-\+//' -e 's/-\+$//' | cut -c1-50 | sed 's/-\+$//')"
[ -n "$SLUG" ] || SLUG="task"
BRANCH="task/${ISSUE}-${SLUG}"

# ---- model resolution: repo manifest sets the default tier; body `model:` override wins. Allowlisted. ----
RESOLVED_MODEL="$MODEL"
case "$MF_MODEL" in
  opus)      RESOLVED_MODEL="$HARD_MODEL";;
  sonnet|"") ;;                                   # sonnet or unset = the global default ($MODEL)
  *)         log "warn: ignoring unknown model '$MF_MODEL' in $MANIFEST (allowed: opus, sonnet)";;
esac
OVERRIDE="$(printf '%s\n' "$BODY" | sed -n -E 's/^model:[[:space:]]*([^[:space:]]+).*/\1/Ip' | head -n1 | tr '[:upper:]' '[:lower:]')"
if [ -n "$OVERRIDE" ]; then
  case "$OVERRIDE" in
    opus)   RESOLVED_MODEL="$HARD_MODEL";;
    sonnet) RESOLVED_MODEL="$MODEL";;
    *)      NEEDS_INFO="${NEEDS_INFO:+$NEEDS_INFO; }unknown model override '$OVERRIDE' (allowed: opus, sonnet)";;
  esac
fi

# ---- DoR content gate -> Needs-info bounce (Status=Backlog + Reason=Needs-info). Dry-run stays read-only ----
if [ -n "$NEEDS_INFO" ]; then
  [ "$DRY_RUN" = 1 ] && gate "$NEEDS_INFO"
  set_status Backlog; set_reason Needs-info
  comment "dev-runner: bounced to **Needs-info** — $NEEDS_INFO. Fix it, then set Status back to Ready."
  gate "needs-info: $NEEDS_INFO"
fi

if [ "$DRY_RUN" -eq 1 ]; then        # read-only: report the resolved plan, write nothing
  python3 -c 'import json,sys; print(json.dumps({"repo":sys.argv[1],"issue":int(sys.argv[2]),"branch":sys.argv[3],"model":sys.argv[4],"workspace":sys.argv[5],"base_repo":sys.argv[6],"base_ref":sys.argv[7],"check_cmd":sys.argv[8],"ready":True}))' \
    "$REPO" "$ISSUE" "$BRANCH" "$RESOLVED_MODEL" "$YR_WORKSPACE" "$BASE_REPO" "$BASE_REF" "$CHECK_CMD"
  exit 0
fi

# ---- claim (Status: Ready -> In Progress) as early as possible ----
set_status "In Progress"
log "claimed #$ISSUE -> In Progress, branch $BRANCH, model $RESOLVED_MODEL"

# from here, any failure flags Reason=Blocked (and comments) before exiting — failures are visible
fail_blocked(){ set_reason Blocked; comment "dev-runner: **Blocked** — $1"; cleanup_wt; die "$1"; }

# ---- fresh worktree (idempotent: clear any prior worktree AND branch so a retry isn't wedged) ----
RUN_DIR="$DEV_RUNNER_HOME/runs/${ISSUE}-$$"; mkdir -p "$RUN_DIR"
WT="$DEV_RUNNER_HOME/wt/${BRANCH//\//-}"
cleanup_wt(){ "$GIT_BIN" -C "$BASE_REPO" worktree remove --force "$WT" 2>/dev/null || true
              "$GIT_BIN" -C "$BASE_REPO" branch -D "$BRANCH" 2>/dev/null || true; }
"$GIT_BIN" -C "$BASE_REPO" fetch -q origin || fail_blocked "git fetch failed"
[ -e "$WT" ] && { "$GIT_BIN" -C "$BASE_REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"; }
"$GIT_BIN" -C "$BASE_REPO" branch -D "$BRANCH" 2>/dev/null || true
"$GIT_BIN" -C "$BASE_REPO" worktree add -q -b "$BRANCH" "$WT" "$BASE_REF" || fail_blocked "worktree add failed"

# ---- a claude -p stage in the worktree (cold process; the runner owns git + the gates) ----
run_stage(){  # $1=role system-prompt, $2=task prompt, $3=log file, $4=allowedTools (default: full edit set)
  local args=( -p "$2" --model "$RESOLVED_MODEL" --effort "$EFFORT"
               --permission-mode bypassPermissions --append-system-prompt "$1"
               --allowedTools ${4:-Read Edit Write Bash} )
  [ -n "${CLAUDE_OUTPUT_FORMAT:-}" ] && args+=( --output-format "$CLAUDE_OUTPUT_FORMAT" --verbose )
  ( cd "$WT" && "$CLAUDE_BIN" "${args[@]}" ) >"$3" 2>&1
}
SPEC="$(printf 'GitHub issue #%s: %s\n\n%s' "$ISSUE" "$TITLE" "$BODY")"

# implementer — production code only
IMPL_SYS="You are the IMPLEMENTER stage of an automated dev pipeline. Implement the task so it satisfies every acceptance criterion. Write PRODUCTION CODE ONLY — do not author the committed test suite (an independent tester stage does that). Do NOT run git or open PRs — the runner handles git. Work only inside this repository."
log "implement: $(basename "$CLAUDE_BIN") [$RESOLVED_MODEL] in $WT"
run_stage "$IMPL_SYS" "$(printf 'Implement the task below against its acceptance criteria. Make the minimal, clean change.\n\n%s' "$SPEC")" "$RUN_DIR/implement.log" \
  || fail_blocked "implement stage failed (log: $RUN_DIR/implement.log)"

# checkpoint: record the worktree tree state after the implementer so the tester boundary guard can
# detect violations structurally (confinement principle — not advisory / prompt-only).
"$GIT_BIN" -C "$WT" add -A
IMPL_TREE="$("$GIT_BIN" -C "$WT" write-tree)"

# tester — independent cold process: tests derived from the CRITERIA, not the implementation (builder≠verifier).
# Writes to tests/** only — enforced below by diffing against IMPL_TREE (block-and-raise, no silent revert).
TEST_SYS="You are the TESTER stage, independent of the implementer. Write automated tests that verify the ACCEPTANCE CRITERIA below, against the code now in this repository. Derive the tests from the CRITERIA (the spec), NOT from the implementation's internals. Do NOT modify production code — only add or extend tests. Do NOT run git. Work only inside this repository."
log "test: independent tester stage"
run_stage "$TEST_SYS" "$(printf 'Write tests that verify the acceptance criteria below.\n\n%s' "$SPEC")" "$RUN_DIR/test.log" \
  || fail_blocked "tester stage failed (log: $RUN_DIR/test.log)"

# tester boundary guard: block if tester modified anything outside tests/**
# Block-and-raise (no auto-revert) so the violation is visible for diagnosis.
"$GIT_BIN" -C "$WT" add -A
TESTER_TREE="$("$GIT_BIN" -C "$WT" write-tree)"
TESTER_DIFF="$("$GIT_BIN" -C "$WT" diff-tree --no-commit-id -r --name-only "$IMPL_TREE" "$TESTER_TREE")"
# Build artifacts (e.g. __pycache__/*.pyc from running the gate) are compiled FROM source the tester
# cannot change, so they can't smuggle an implementation change past builder≠verifier — exclude them
# from the offender set rather than false-block on them (a repo's .gitignore is the first line; this
# is the backstop so a repo that forgets it still builds).
TESTER_OFFENDERS="$(printf '%s' "$TESTER_DIFF" | grep -v '^tests/' | grep -vE '(^|/)__pycache__/|\.pyc$' || true)"
if [ -n "$TESTER_OFFENDERS" ]; then
  OFFENDER_LIST="$(printf '%s\n' "$TESTER_OFFENDERS" | tr '\n' ' ' | sed 's/ *$//')"
  # preserve WHAT the tester changed (not just which files) before fail_blocked cleans the
  # worktree — so a blocked run stays diagnosable ("understand the why").
  "$GIT_BIN" -C "$WT" diff "$IMPL_TREE" "$TESTER_TREE" > "$RUN_DIR/boundary-violation.diff" 2>/dev/null || true
  fail_blocked "tester modified files outside tests/: $OFFENDER_LIST (diff: $RUN_DIR/boundary-violation.diff)"
fi

# deterministic check gate — the RUNNER runs the checks, not the LLM. One repair attempt.
# The worktree is ephemeral (no .venv / node_modules — both gitignored, they live in the base checkout),
# so put the base repo's toolchain dirs on PATH: a manifest names tools plainly (`pytest`, `vitest`) and
# the runner supplies them, instead of hardcoding a venv path the worktree doesn't have.
run_checks(){ ( cd "$WT" && PATH="$BASE_REPO/.venv/bin:$BASE_REPO/node_modules/.bin:$PATH" bash -c "$CHECK_CMD" ) >"$RUN_DIR/checks.log" 2>&1; }
# Distinguish a CODE failure (the harness ran and tests failed) from an ENVIRONMENT failure (the harness
# could not execute at all: 127=command not found, 126=found-but-not-executable — e.g. a venv whose
# console-script shebang points at a moved/rebuilt interpreter). An env failure is NOT the implementer's
# to fix; handing it to the LLM repair invites host-mutating "fixes" (pip --break-system-packages) that
# paper over it. Fail closed and report it as an environment problem, never an LLM repair.
is_env_failure(){ [ "$1" -eq 126 ] || [ "$1" -eq 127 ]; }
env_blocked(){ fail_blocked "check command could not execute (exit $1)$2 — an ENVIRONMENT/toolchain failure, not a code failure. The check harness (e.g. $BASE_REPO/.venv) is missing or broken; rebuild it, then set Ready again — do not paper over it. (log: $RUN_DIR/checks.log)"; }
CHECK_RC=0; run_checks || CHECK_RC=$?
if is_env_failure "$CHECK_RC"; then env_blocked "$CHECK_RC" ""; fi
if [ "$CHECK_RC" -ne 0 ]; then
  log "checks failed (exit $CHECK_RC) — one repair attempt"
  run_stage "$IMPL_SYS" "$(printf 'The project tests FAIL. Fix the PRODUCTION CODE so they pass — do NOT modify the tests. Failure output:\n\n%s\n\nTask:\n%s' "$(tail -n 40 "$RUN_DIR/checks.log")" "$SPEC")" "$RUN_DIR/repair.log" || true
  CHECK_RC=0; run_checks || CHECK_RC=$?
  if is_env_failure "$CHECK_RC"; then env_blocked "$CHECK_RC" " after the repair attempt"; fi
  [ "$CHECK_RC" -eq 0 ] || fail_blocked "checks still failing after one repair (log: $RUN_DIR/checks.log)"
fi

# ---- review stage (independent cold process: quality verdict on the diff; gate = no blockers) ----
# Review is a judgment, so the gate is the reviewer's own verdict — but a separate cold process with
# no stake, and fail-closed (anything but a clear APPROVE blocks). The verdict is attached to the PR.
REVIEW_SYS="You are the REVIEWER stage, independent of the implementer and tester. Review the STAGED changes (run: git diff --cached) against the ACCEPTANCE CRITERIA below — for correctness, maintainability, simplicity, and security. Tag each finding 'blocker' or 'nit'. Do NOT modify any files and do NOT run git commit or push. End your reply with a final line that is exactly 'VERDICT: APPROVE' if there are zero blockers, or 'VERDICT: REQUEST_CHANGES' otherwise."
review_stage(){ "$GIT_BIN" -C "$WT" add -A
                run_stage "$REVIEW_SYS" "$(printf 'Review the staged changes against the acceptance criteria below.\n\n%s' "$SPEC")" "$RUN_DIR/review.md" "Read Bash"
                # fail-closed: the LAST verdict line must be exactly "VERDICT: APPROVE" (only trailing whitespace
                # trimmed) — a hedge ("APPROVE" then "REQUEST_CHANGES"), trailing junk, or a mangled token does NOT pass.
                [ "$(grep -E '^VERDICT:' "$RUN_DIR/review.md" | tail -n1 | sed -E 's/[[:space:]]+$//')" = "VERDICT: APPROVE" ]; }
log "review: independent reviewer stage"
if ! review_stage; then
  log "review requested changes — one repair attempt"
  run_stage "$IMPL_SYS" "$(printf 'A reviewer REQUESTED CHANGES. Fix the blocking findings (production code; only touch a test if the test itself is wrong). Reviewer notes:\n\n%s\n\nTask:\n%s' "$(cat "$RUN_DIR/review.md")" "$SPEC")" "$RUN_DIR/review-repair.log" || true
  run_checks  || fail_blocked "checks failing after review-repair (log: $RUN_DIR/checks.log)"
  review_stage || fail_blocked "reviewer still requests changes after one repair"
fi

# ---- commit / push / open PR ----
"$GIT_BIN" -C "$WT" add -A
if "$GIT_BIN" -C "$WT" diff --cached --quiet; then fail_blocked "no changes produced"; fi
"$GIT_BIN" -C "$WT" commit -q -m "$(printf '%s\n\nImplements #%s (dev-runner, %s). Tests by the independent tester stage.' "$TITLE" "$ISSUE" "$RESOLVED_MODEL")"
"$GIT_BIN" -C "$WT" push -q -u origin "$BRANCH" || fail_blocked "push failed"
PR_BODY="$(printf 'Closes #%s\n\nProduced by **dev-runner** (model: %s): implementer + independent **tester** + independent **reviewer** stages — checks green, review approved. Reviewer verdict attached below.' "$ISSUE" "$RESOLVED_MODEL")"
PR_URL="$("$GH_BIN" pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$BRANCH" --title "$TITLE" --body "$PR_BODY")" \
  || fail_blocked "pr create failed"
"$GH_BIN" pr comment "$PR_URL" --body-file "$RUN_DIR/review.md" >/dev/null 2>&1 || true   # attach reviewer verdict

# ---- PR open -> Status: In Review ----
set_status "In Review"
log "PR opened: $PR_URL  (#$ISSUE -> In Review)"
cleanup_wt
echo "$PR_URL"
