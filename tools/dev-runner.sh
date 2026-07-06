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
#   empty acceptance criteria / a model (build or review) not in the registry / an inverted or
#     cross-provider ranked build/review pair -> Status=Backlog + Reason=Needs-info (no LLM).
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
EFFORT="${EFFORT:-high}"
# Model roles come from the registry (models.toml via tools/registry.py) — the single model surface;
# the old MODEL/HARD_MODEL tiers are retired. BUILD_MODEL/REVIEW_MODEL are the operator env overrides,
# one per role, sitting ATOP task/manifest/registry-default. Either may name a registry entry (runs
# ranked) OR a raw unregistered id (the ONLY place a non-registry id runs — unranked + loudly warned,
# never bounced). MODELS_REGISTRY overrides the registry file (default: the factory's own models.toml).
BUILD_MODEL="${BUILD_MODEL:-}"; REVIEW_MODEL="${REVIEW_MODEL:-}"
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
MF_CHECK_CMD=""; MF_MODEL=""; MF_BASE_REF=""; MF_REVIEW_MODEL=""; MF_AUTO_MERGE="false"
if [ -n "$MF_RAW" ]; then
  # auto_merge (issue #38) is parsed here alongside the rest, but the MERGE DECISION never trusts this
  # start-of-run value — read_auto_merge re-reads it from the base ref's current tip at decision time.
  _mf_out="$(printf '%s' "$MF_RAW" | python3 -c 'import sys,tomllib
d=tomllib.loads(sys.stdin.read())
for k in ("check_cmd","model","base_ref","review_model"): print(str(d.get(k) or "").replace("\n"," "))
print("true" if d.get("auto_merge") is True else "false")' 2>/dev/null)" \
    || log "warn: could not parse manifest from $MANIFEST_REF"
  mapfile -t _mf <<<"$_mf_out"
  MF_CHECK_CMD="${_mf[0]:-}"; MF_MODEL="${_mf[1]:-}"; MF_BASE_REF="${_mf[2]:-}"; MF_REVIEW_MODEL="${_mf[3]:-}"; MF_AUTO_MERGE="${_mf[4]:-false}"
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

# ---- model roles from the registry: build (implement/test/repair) + review (reviewer). ----
# Precedence per role: per-task (body model:/review_model:) > per-repo (manifest model/review_model) >
# registry per-role default, with the operator env override (BUILD_MODEL/REVIEW_MODEL) ATOP all three.
# Resolution shells to tools/registry.py — the same shell-to-python3 seam as the manifest parse above.
REGISTRY="${MODELS_REGISTRY:-$SELF_DIR/../models.toml}"

# body selectors: bare-line, case-insensitive (`model:` = build, `review_model:` = review). Same parser.
body_select(){ printf '%s\n' "$BODY" | sed -n -E "s/^$1:[[:space:]]*([^[:space:]]+).*/\1/Ip" | head -n1 | tr '[:upper:]' '[:lower:]'; }
BODY_BUILD="$(body_select model)"; BODY_REVIEW="$(body_select review_model)"

# parse a registry entry JSON ({name,id,provider,rank,...}) into the R_* globals.
_set_role_from_json(){
  mapfile -t _rf < <(printf '%s' "$1" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print(d.get("name","") or "")
print(d.get("id","") or "")
print(d.get("provider","") or "")
r=d.get("rank"); print(r if isinstance(r,int) and not isinstance(r,bool) else "")')
  R_NAME="${_rf[0]:-}"; R_ID="${_rf[1]:-}"; R_PROVIDER="${_rf[2]:-}"; R_RANK="${_rf[3]:-}"
  [ -n "$R_RANK" ] && R_RANKED=1 || R_RANKED=0
}
# resolve_role ROLE TASK_VAL MANIFEST_VAL ENV_VAL -> sets R_STATUS (ok|unknown|raw) + R_* fields.
#   env override wins: a registry name resolves ranked; a raw unregistered id runs UNRANKED (R_STATUS=raw,
#   no bounce — the only non-registry id allowed). Otherwise task>manifest>default; an unknown name from
#   task/manifest is R_STATUS=unknown (bounced to Needs-info below).
resolve_role(){
  local role="$1" tval="$2" mval="$3" eval_="$4" out rc
  R_NAME=""; R_ID=""; R_PROVIDER=""; R_RANK=""; R_RANKED=0
  # && rc=0 || rc=$? keeps a non-zero registry exit (unknown name) from tripping `set -e` — it's a
  # signal here, not a fatal error.
  if [ -n "$eval_" ]; then
    out="$(python3 "$SELF_DIR/registry.py" --registry "$REGISTRY" resolve --role "$role" --task "$eval_" 2>/dev/null)" && rc=0 || rc=$?
    if [ "$rc" -eq 0 ]; then _set_role_from_json "$out"; R_STATUS=ok
    else
      R_NAME="$eval_"; R_ID="$eval_"; R_PROVIDER=""; R_RANK=""; R_RANKED=0; R_STATUS=raw
      log "WARNING: $role model '$eval_' (operator env override) is not in the registry — running it UNRANKED and rank-unchecked."
    fi
    return 0
  fi
  out="$(python3 "$SELF_DIR/registry.py" --registry "$REGISTRY" resolve --role "$role" --task "$tval" --manifest "$mval" 2>/dev/null)" && rc=0 || rc=$?
  if [ "$rc" -eq 0 ]; then _set_role_from_json "$out"; R_STATUS=ok; else R_STATUS=unknown; fi
}

resolve_role build "$BODY_BUILD" "$MF_MODEL" "$BUILD_MODEL"
BUILD_STATUS="$R_STATUS"; BUILD_NAME="$R_NAME"; BUILD_ID="$R_ID"; BUILD_PROVIDER="$R_PROVIDER"; BUILD_RANK="$R_RANK"; BUILD_RANKED="$R_RANKED"
resolve_role review "$BODY_REVIEW" "$MF_REVIEW_MODEL" "$REVIEW_MODEL"
REVIEW_STATUS="$R_STATUS"; REVIEW_NAME="$R_NAME"; REVIEW_ID="$R_ID"; REVIEW_PROVIDER="$R_PROVIDER"; REVIEW_RANK="$R_RANK"; REVIEW_RANKED="$R_RANKED"

# fail-closed intake (before claiming): an unknown name from task body or manifest bounces; a ranked
# pair that is inverted (review rank < build rank) or cross-provider bounces, naming the pair. A raw
# env id (R_STATUS=raw) is unranked and exempt from both — it runs shadow-only, never at intake.
if [ "$BUILD_STATUS" = unknown ]; then
  NEEDS_INFO="${NEEDS_INFO:+$NEEDS_INFO; }unknown build model '${BODY_BUILD:-$MF_MODEL}' — not in the registry (models.toml)"
fi
if [ "$REVIEW_STATUS" = unknown ]; then
  NEEDS_INFO="${NEEDS_INFO:+$NEEDS_INFO; }unknown review model '${BODY_REVIEW:-$MF_REVIEW_MODEL}' — not in the registry (models.toml)"
fi
if [ -z "$NEEDS_INFO" ] && [ "$BUILD_RANKED" = 1 ] && [ "$REVIEW_RANKED" = 1 ]; then
  if [ "$BUILD_PROVIDER" != "$REVIEW_PROVIDER" ]; then
    NEEDS_INFO="cross-provider model pair — build '$BUILD_NAME' (${BUILD_PROVIDER}) vs review '$REVIEW_NAME' (${REVIEW_PROVIDER}); ranks are not comparable across providers, so the reviewer can't be shown to be no weaker than the build"
  elif [ "$REVIEW_RANK" -lt "$BUILD_RANK" ]; then
    NEEDS_INFO="inverted model pair — review '$REVIEW_NAME' (rank $REVIEW_RANK) is weaker than build '$BUILD_NAME' (rank $BUILD_RANK); an independent reviewer must never run below the build"
  fi
fi

# per-stage repair model: a repair stage runs at its registry stage tier when set, else the build id.
stage_repair_id(){
  local out id
  out="$(python3 "$SELF_DIR/registry.py" --registry "$REGISTRY" stage-tier --stage "$1" 2>/dev/null)" || out=""
  id="$(printf '%s' "$out" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("id","") or "")' 2>/dev/null || true)"
  [ -n "$id" ] && printf '%s' "$id" || printf '%s' "$BUILD_ID"
}
CHECK_REPAIR_ID="$(stage_repair_id check_repair)"; REVIEW_REPAIR_ID="$(stage_repair_id review_repair)"

# a resolved role (name/id/provider/rank/ranked) as JSON, for the review bundle (tools/review_bundle.py).
role_json(){ python3 -c 'import json,sys
a=sys.argv
print(json.dumps({"name":a[1] or None,"id":a[2],"provider":a[3] or None,
                  "rank":(int(a[4]) if a[4] else None),"ranked":a[5]=="1"}))' "$1" "$2" "$3" "$4" "$5"; }

# ---- DoR content gate -> Needs-info bounce (Status=Backlog + Reason=Needs-info). Dry-run stays read-only ----
if [ -n "$NEEDS_INFO" ]; then
  [ "$DRY_RUN" = 1 ] && gate "$NEEDS_INFO"
  set_status Backlog; set_reason Needs-info
  comment "dev-runner: bounced to **Needs-info** — $NEEDS_INFO. Fix it, then set Status back to Ready."
  gate "needs-info: $NEEDS_INFO"
fi

if [ "$DRY_RUN" -eq 1 ]; then        # read-only: report the resolved plan, write nothing
  # Additive: `model` stays = the resolved BUILD id (back-compat); `build`/`review` add the role objects.
  python3 -c 'import json,sys
a=sys.argv
def role(name,mid,prov,rank): return {"name":name or None,"id":mid,"provider":prov or None,"rank":(int(rank) if rank else None)}
print(json.dumps({"repo":a[1],"issue":int(a[2]),"branch":a[3],"model":a[4],"workspace":a[5],
                  "base_repo":a[6],"base_ref":a[7],"check_cmd":a[8],"auto_merge":a[17]=="true",
                  "build":role(a[9],a[10],a[11],a[12]),"review":role(a[13],a[14],a[15],a[16]),"ready":True}))' \
    "$REPO" "$ISSUE" "$BRANCH" "$BUILD_ID" "$YR_WORKSPACE" "$BASE_REPO" "$BASE_REF" "$CHECK_CMD" \
    "$BUILD_NAME" "$BUILD_ID" "$BUILD_PROVIDER" "$BUILD_RANK" \
    "$REVIEW_NAME" "$REVIEW_ID" "$REVIEW_PROVIDER" "$REVIEW_RANK" "$MF_AUTO_MERGE"
  exit 0
fi

# ---- claim (Status: Ready -> In Progress) as early as possible ----
set_status "In Progress"
log "claimed #$ISSUE -> In Progress, branch $BRANCH, build=$BUILD_ID review=$REVIEW_ID"

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
run_stage(){  # $1=role system-prompt, $2=task prompt, $3=log file, $4=allowedTools (default: full edit set), $5=model id (default: build)
  local args=( -p "$2" --model "${5:-$BUILD_ID}" --effort "$EFFORT"
               --permission-mode bypassPermissions --append-system-prompt "$1"
               --allowedTools ${4:-Read Edit Write Bash} )
  [ -n "${CLAUDE_OUTPUT_FORMAT:-}" ] && args+=( --output-format "$CLAUDE_OUTPUT_FORMAT" --verbose )
  ( cd "$WT" && "$CLAUDE_BIN" "${args[@]}" ) >"$3" 2>&1
}
SPEC="$(printf 'GitHub issue #%s: %s\n\n%s' "$ISSUE" "$TITLE" "$BODY")"

# implementer — production code only
IMPL_SYS="You are the IMPLEMENTER stage of an automated dev pipeline. Implement the task so it satisfies every acceptance criterion. Write PRODUCTION CODE ONLY — do not author the committed test suite (an independent tester stage does that). Do NOT run git or open PRs — the runner handles git. Work only inside this repository."
log "implement: $(basename "$CLAUDE_BIN") [$BUILD_ID] in $WT"
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
  log "checks failed (exit $CHECK_RC) — one repair attempt [$CHECK_REPAIR_ID]"
  run_stage "$IMPL_SYS" "$(printf 'The project tests FAIL. Fix the PRODUCTION CODE so they pass — do NOT modify the tests. Failure output:\n\n%s\n\nTask:\n%s' "$(tail -n 40 "$RUN_DIR/checks.log")" "$SPEC")" "$RUN_DIR/repair.log" "Read Edit Write Bash" "$CHECK_REPAIR_ID" || true
  CHECK_RC=0; run_checks || CHECK_RC=$?
  if is_env_failure "$CHECK_RC"; then env_blocked "$CHECK_RC" " after the repair attempt"; fi
  [ "$CHECK_RC" -eq 0 ] || fail_blocked "checks still failing after one repair (log: $RUN_DIR/checks.log)"
fi

# ---- assemble the pre-review bundle: diff (base->head), acceptance criteria, check output, resolved
# build/review pair — one canonical, hashed artifact (tools/review_bundle.py) that the reviewer reads
# as input and each round's verdict is appended to.
"$GIT_BIN" -C "$WT" add -A
BASE_SHA="$("$GIT_BIN" -C "$WT" rev-parse HEAD)"
HEAD_SHA="$("$GIT_BIN" -C "$WT" write-tree)"
"$GIT_BIN" -C "$WT" diff --cached > "$RUN_DIR/diff.patch"
printf '%s\n' "$AC" > "$RUN_DIR/acceptance-criteria.txt"
BUNDLE="$RUN_DIR/review-bundle.json"
python3 "$SELF_DIR/review_bundle.py" init --bundle "$BUNDLE" \
  --base-sha "$BASE_SHA" --head-sha "$HEAD_SHA" --diff-file "$RUN_DIR/diff.patch" \
  --criteria-file "$RUN_DIR/acceptance-criteria.txt" --checks-log "$RUN_DIR/checks.log" \
  --check-cmd "$CHECK_CMD" --check-exit "$CHECK_RC" \
  --build-json "$(role_json "$BUILD_NAME" "$BUILD_ID" "$BUILD_PROVIDER" "$BUILD_RANK" "$BUILD_RANKED")" \
  --review-json "$(role_json "$REVIEW_NAME" "$REVIEW_ID" "$REVIEW_PROVIDER" "$REVIEW_RANK" "$REVIEW_RANKED")" \
  || fail_blocked "review bundle assembly failed"

# ---- review stage (independent cold process: quality verdict on the diff; gate = no blockers) ----
# Review is a judgment, so the gate is the reviewer's own verdict — but a separate cold process with
# no stake, and fail-closed (anything but a clear APPROVE blocks). The verdict is attached to the PR.
REVIEW_SYS="You are the REVIEWER stage, independent of the implementer and tester. Review the STAGED changes (run: git diff --cached) against the ACCEPTANCE CRITERIA below — for correctness, maintainability, simplicity, and security. Tag each finding 'blocker' or 'nit'. Do NOT modify any files and do NOT run git commit or push. End your reply with a final line that is exactly 'VERDICT: APPROVE' if there are zero blockers, or 'VERDICT: REQUEST_CHANGES' otherwise."
review_stage(){ "$GIT_BIN" -C "$WT" add -A
                run_stage "$REVIEW_SYS" "$(printf 'Review the staged changes against the acceptance criteria below. The full review bundle (diff with base/head SHAs, acceptance criteria, check output, resolved build/review models) is at: %s\n\n%s' "$BUNDLE" "$SPEC")" "$RUN_DIR/review.md" "Read Bash" "$REVIEW_ID"
                python3 "$SELF_DIR/review_bundle.py" record-verdict --bundle "$BUNDLE" --file "$RUN_DIR/review.md" \
                  || fail_blocked "review bundle record-verdict failed"
                # fail-closed: the LAST verdict line must be exactly "VERDICT: APPROVE" (only trailing whitespace
                # trimmed) — a hedge ("APPROVE" then "REQUEST_CHANGES"), trailing junk, or a mangled token does NOT pass.
                [ "$(grep -E '^VERDICT:' "$RUN_DIR/review.md" | tail -n1 | sed -E 's/[[:space:]]+$//')" = "VERDICT: APPROVE" ]; }
log "review: independent reviewer stage"
if ! review_stage; then
  log "review requested changes — one repair attempt [$REVIEW_REPAIR_ID]"
  run_stage "$IMPL_SYS" "$(printf 'A reviewer REQUESTED CHANGES. Fix the blocking findings (production code; only touch a test if the test itself is wrong). Reviewer notes:\n\n%s\n\nTask:\n%s' "$(cat "$RUN_DIR/review.md")" "$SPEC")" "$RUN_DIR/review-repair.log" "Read Edit Write Bash" "$REVIEW_REPAIR_ID" || true
  run_checks  || fail_blocked "checks failing after review-repair (log: $RUN_DIR/checks.log)"
  review_stage || fail_blocked "reviewer still requests changes after one repair"
fi

# ---- commit / push / open PR ----
"$GIT_BIN" -C "$WT" add -A
if "$GIT_BIN" -C "$WT" diff --cached --quiet; then fail_blocked "no changes produced"; fi
"$GIT_BIN" -C "$WT" commit -q -m "$(printf '%s\n\nImplements #%s (dev-runner, build %s). Tests by the independent tester stage.' "$TITLE" "$ISSUE" "$BUILD_ID")"
PR_HEAD_SHA="$("$GIT_BIN" -C "$WT" rev-parse HEAD)"   # the pushed PR head commit (for the shadow merge record)
"$GIT_BIN" -C "$WT" push -q -u origin "$BRANCH" || fail_blocked "push failed"
PR_BODY="$(printf 'Closes #%s\n\nProduced by **dev-runner** (build: %s, review: %s): implementer + independent **tester** + independent **reviewer** stages — checks green, review approved. Reviewer verdict attached below.' "$ISSUE" "$BUILD_ID" "$REVIEW_ID")"
PR_URL="$("$GH_BIN" pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$BRANCH" --title "$TITLE" --body "$PR_BODY")" \
  || fail_blocked "pr create failed"
"$GH_BIN" pr comment "$PR_URL" --body-file "$RUN_DIR/review.md" >/dev/null 2>&1 || true   # attach reviewer verdict

# ---- terminal merge-condition evaluator + autonomous merge (issues #37 shadow, #38 arming) ----------
# The runner's terminal post-PR responsibility: a DETERMINISTIC step (no new LLM stage) that evaluates
# the fail-closed merge conditions IN ORDER, IN CODE, indeterminate = failed. A repo is ARMED when its
# manifest sets auto_merge=true (read at DECISION time from the base ref's current tip), the host sentinel
# is not thrown, and shadow is complete (computed mechanically from prior PR merge records + main history).
# An armed repo whose conditions all pass is squash-merged BY THE FACTORY into main — freshness remediation
# (rebase + re-green) first if main moved — and recorded as a durable YR-MERGE: MERGED, letting native
# close->Done finish the lifecycle (so the merge supersedes set_status "In Review"). Everything else stays
# in shadow (YR-MERGE-SHADOW, stop for the human) or armed-blocked (YR-MERGE: BLOCKED + Reason=Blocked).
# A shadow WOULD-BLOCK is a NORMAL negative outcome, NOT Reason=Blocked. The step's OWN environmental
# failures (a gh API blip / network drop / merge API error while evaluating, recording, or merging) are
# classified environmental — no machinery-error record, resumable — and never reset a streak or hard-Block.
MERGE_CI_POLL_INTERVAL="${MERGE_CI_POLL_INTERVAL:-15}"   # poll cadence for in-flight CI (seconds)
MERGE_CI_TIMEOUT="${MERGE_CI_TIMEOUT:-600}"              # bounded wait for in-flight CI (seconds); timeout = fail
# The host sentinel (kill switch): a FILE in the dispatch home, read LIVE at decision time (a file, not an
# inherited env var — a spawned runner carries its spawn-time environment; the file is global + git-free).
MERGE_SENTINEL="${MERGE_SENTINEL:-$DEV_RUNNER_HOME/merge-killswitch}"
SHADOW_WINDOW="${SHADOW_WINDOW:-5}"; SHADOW_NEED="${SHADOW_NEED:-3}"; SHADOW_SCAN="${SHADOW_SCAN:-40}"
PR_NUMBER="${PR_URL##*/}"                                # the current PR number (excluded from the window)

# (1) ci_green — poll the PR check rollup until nothing is in-flight (bounded); zero configured checks
#     fails fast, WITHOUT the wait. Server CI is distinct from and additional to the in-build check_cmd.
shadow_ci(){   # sets CI_RESULT (pass|fail) + CI_STATE; returns 2 on an environmental gh/parse failure.
  local rollup="$RUN_DIR/check-rollup.json" start now rc counts total in_flight failed
  start="$(date +%s)"
  while :; do
    rc=0; "$GH_BIN" pr view "$PR_URL" --repo "$REPO" --json statusCheckRollup >"$rollup" 2>/dev/null || rc=$?
    [ "$rc" -eq 0 ] || return 2
    counts="$(python3 "$SELF_DIR/merge_shadow.py" classify-checks --rollup-file "$rollup" 2>/dev/null)" || return 2
    read -r total in_flight failed <<<"$counts" || true
    if [ "${total:-0}" -eq 0 ]; then CI_RESULT=fail; CI_STATE=empty; return 0; fi          # zero checks: fail fast
    if [ "${in_flight:-0}" -eq 0 ]; then
      if [ "${failed:-0}" -eq 0 ]; then CI_RESULT=pass; CI_STATE=success; else CI_RESULT=fail; CI_STATE=failure; fi
      return 0
    fi
    now="$(date +%s)"
    if [ "$((now - start))" -ge "$MERGE_CI_TIMEOUT" ]; then CI_RESULT=fail; CI_STATE=timed_out; return 0; fi
    sleep "$MERGE_CI_POLL_INTERVAL"
  done
}
# (2) freshness — the reviewed base SHA must equal main's tip at decision time (a boolean here; the
#     rebase/re-green remediation is the arming task's, since only a factory-executed merge mutates the
#     branch). MERGE_MAIN_TIP overrides the decision-time tip; else FETCH origin/$BASE_BRANCH now and read
#     it. The only earlier fetch ran at build start (minutes ago, before implement/test/review + the CI
#     wait), and BASE_SHA is that same base checkout — so without a decision-time re-fetch the local
#     origin/$BASE_BRANCH still equals BASE_SHA and freshness is a structural no-op that can never see a
#     moved main. A fetch failure is environmental (network/API), classified like the CI read (return 2) —
#     never a false pass.
shadow_freshness(){   # sets FRESH_RESULT (pass|fail) + MAIN_TIP; returns 2 on an environmental fetch failure.
  if [ -n "${MERGE_MAIN_TIP:-}" ]; then MAIN_TIP="$MERGE_MAIN_TIP"
  else
    "$GIT_BIN" -C "$WT" fetch -q origin "$BASE_BRANCH" 2>/dev/null || return 2               # decision-time re-fetch
    MAIN_TIP="$("$GIT_BIN" -C "$WT" rev-parse "origin/$BASE_BRANCH" 2>/dev/null || true)"
  fi
  [ -n "$MAIN_TIP" ] || { FRESH_RESULT=fail; return 0; }                                    # indeterminate -> fail
  [ "$BASE_SHA" = "$MAIN_TIP" ] && FRESH_RESULT=pass || FRESH_RESULT=fail
}
# (3) terminal_approval — the LAST review round must be a clean 'VERDICT: APPROVE' (re-approval of a
#     revised diff counts; the first pass need not have been clean). Same exact-match rule as the gate.
shadow_terminal_approval(){
  if [ "$(grep -E '^VERDICT:' "$RUN_DIR/review.md" 2>/dev/null | tail -n1 | sed -E 's/[[:space:]]+$//')" = "VERDICT: APPROVE" ]
  then APPROVE_RESULT=pass; else APPROVE_RESULT=fail; fi
}
# (4) rank_gate — the resolved pair must satisfy STRICT review-rank > build-rank on ONE provider, both
#     ranked (an unranked emergency override fails here -> shadow-only by construction; an equal-rank pair
#     that cleared intake also fails here — strict > is the merge bar, not the intake bar).
shadow_rank_gate(){
  if [ "$BUILD_RANKED" = 1 ] && [ "$REVIEW_RANKED" = 1 ] \
     && [ "$BUILD_PROVIDER" = "$REVIEW_PROVIDER" ] && [ "$REVIEW_RANK" -gt "$BUILD_RANK" ]
  then RANK_RESULT=pass; else RANK_RESULT=fail; fi
}
# (5a) auto_merge — read at DECISION time from the base ref's CURRENT tip (NEVER the start-of-run parse
#      at L~96). The decision-time fetch already ran in shadow_freshness, so origin/$BASE_BRANCH is fresh.
#      A missing manifest/key -> not armed (false), not an error. MERGE_AUTO_MERGE overrides (for tests).
read_auto_merge(){   # sets AUTO_MERGE (true|false); returns 2 on an environmental read/parse failure.
  if [ -n "${MERGE_AUTO_MERGE:-}" ]; then AUTO_MERGE="$MERGE_AUTO_MERGE"; return 0; fi
  local raw
  raw="$("$GIT_BIN" -C "$WT" show "origin/$BASE_BRANCH:.yr/factory.toml" 2>/dev/null || true)"
  [ -z "$raw" ] && { AUTO_MERGE=false; return 0; }
  AUTO_MERGE="$(printf '%s' "$raw" | python3 -c 'import sys,tomllib
try: d=tomllib.loads(sys.stdin.read())
except Exception: print("error"); sys.exit(0)
print("true" if d.get("auto_merge") is True else "false")' 2>/dev/null || echo error)"
  [ "$AUTO_MERGE" = error ] && return 2
  return 0
}

# (5b) shadow completion — MECHANICAL, from the repo's prior PR merge records + main history (no sidecar):
#      one unified window over the last N merge records (shadow YR-MERGE-SHADOW and armed YR-MERGE alike),
#      >=K landed unreverted successes and no reset. See tools/merge_shadow.py shadow-complete.
compute_shadow_complete(){   # sets SHADOW_DONE (true|false) + SHADOW_PROGRESS (k/N); returns 2 on env failure.
  local prs="$RUN_DIR/prs.json" mainlog="$RUN_DIR/main-log.txt" out succ size
  "$GH_BIN" pr list --repo "$REPO" --base "$BASE_BRANCH" --state all --limit "$SHADOW_SCAN" \
     --json number,state,mergeCommit,mergedAt,comments >"$prs" 2>/dev/null || return 2
  "$GIT_BIN" -C "$WT" log "origin/$BASE_BRANCH" --max-count=300 --format='%H%x1e%B%x00' >"$mainlog" 2>/dev/null || return 2
  out="$(python3 "$SELF_DIR/merge_shadow.py" shadow-complete --prs-file "$prs" --main-log-file "$mainlog" \
         --repo "$REPO" --exclude-pr "$PR_NUMBER" --window "$SHADOW_WINDOW" --need "$SHADOW_NEED" 2>/dev/null)" || return 2
  read -r SHADOW_DONE succ size <<<"$out" || return 2
  SHADOW_PROGRESS="$succ/$SHADOW_WINDOW"
  return 0
}

# emit the yr-merge record and post it on the PR. $1 = body file; the rest = mode-specific record args
# (--mode / --decision / --block-reason / --merge-commit / --armed-note / --shadow-* / --sentinel).
# returns 2 on an environmental record/post failure. Sets MERGE_MARKER to the record's marker line.
emit_and_post(){
  local body="$1"; shift
  python3 "$SELF_DIR/merge_shadow.py" record \
    --ci-green "$CI_RESULT" --freshness "$FRESH_RESULT" \
    --terminal-approval "$APPROVE_RESULT" --rank-gate "$RANK_RESULT" \
    --bundle "$BUNDLE" --base-sha "$BASE_SHA" --head-sha "$PR_HEAD_SHA" --main-tip-sha "${MAIN_TIP:-}" \
    --rollup-file "$RUN_DIR/check-rollup.json" --ci-state "$CI_STATE" \
    --run-id "$(basename "$RUN_DIR")" --timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --auto-merge "${AUTO_MERGE:-false}" --out "$body" "$@" || return 2
  "$GH_BIN" pr comment "$PR_URL" --repo "$REPO" --body-file "$body" >/dev/null 2>&1 || return 2
  MERGE_MARKER="$(head -n1 "$body")"
}

# freshness remediation: main moved, so rebase the branch onto the tip and RE-ESTABLISH green (re-run the
# check gate + re-wait CI) before merging — the reviewed diff is unchanged so the verdict stands. A stale
# green SHALL NOT merge. Returns 0 (remediated, ready to merge) / 1 (block: conflict or cannot re-green) /
# 2 (environmental). Updates PR_HEAD_SHA/BASE_SHA/MAIN_TIP to the rebased state.
rebase_onto_tip(){
  "$GIT_BIN" -C "$WT" fetch -q origin "$BASE_BRANCH" 2>/dev/null || return 2
  if ! "$GIT_BIN" -C "$WT" rebase "origin/$BASE_BRANCH" >/dev/null 2>&1; then
    "$GIT_BIN" -C "$WT" rebase --abort >/dev/null 2>&1 || true
    return 1                                   # rebase conflict -> block for the human
  fi
  "$GIT_BIN" -C "$WT" push -q --force-with-lease origin "$BRANCH" 2>/dev/null || return 2
  PR_HEAD_SHA="$("$GIT_BIN" -C "$WT" rev-parse HEAD)"
  BASE_SHA="$("$GIT_BIN" -C "$WT" rev-parse "origin/$BASE_BRANCH" 2>/dev/null || echo "$BASE_SHA")"
  local rc=0; run_checks || rc=$?             # re-run the deterministic check gate on the rebased tree
  is_env_failure "$rc" && return 2
  [ "$rc" -eq 0 ] || return 1                  # cannot re-establish green -> block (never merge a stale/red PR)
  shadow_ci || return 2                        # re-wait CI on the rebased head
  [ "$CI_RESULT" = pass ] || return 1
  shadow_freshness || return 2                 # base==tip now
  [ "$FRESH_RESULT" = pass ] || return 1
  return 0
}

# squash-merge the PR into main ONLY (never a deploy/release target), passing --squash EXPLICITLY (nothing
# server-side enforces it). Sets MERGE_COMMIT (best-effort). Returns 2 only if the merge API itself fails.
do_squash_merge(){
  "$GH_BIN" pr merge "$PR_URL" --repo "$REPO" --squash >/dev/null 2>&1 || return 2
  MERGE_COMMIT="$("$GH_BIN" pr view "$PR_URL" --repo "$REPO" --json mergeCommit 2>/dev/null \
    | python3 -c 'import sys,json
try: d=json.load(sys.stdin)
except Exception: d={}
print((d.get("mergeCommit") or {}).get("oid","") or "")' 2>/dev/null || true)"
  return 0
}

# armed-blocked: record YR-MERGE: BLOCKED — <reason>, flag Reason=Blocked, comment. Sets ARMED_BLOCKED.
armed_block(){   # $1 = block reason (condition id), $2 = human-facing detail
  local body="$RUN_DIR/merge-record.md"
  set_reason Blocked
  emit_and_post "$body" --mode armed --decision BLOCKED --block-reason "$1" \
    --shadow-complete "${SHADOW_DONE:-false}" --shadow-progress "${SHADOW_PROGRESS:-}" \
    --sentinel "${SENTINEL_STATE:-ok}" || return 2
  comment "dev-runner: **Blocked** — autonomous merge refused ($1): $2"
  ARMED_BLOCKED=1
  return 0
}

# The terminal decision. Returns 2 on ANY environmental failure (resumable — no record, no merge, no
# streak reset, no Block). Sets MERGED=1 on a factory squash-merge; sets ARMED_BLOCKED=1 on an armed block.
terminal_step(){
  CI_RESULT=fail; CI_STATE=unknown; FRESH_RESULT=fail; APPROVE_RESULT=fail; RANK_RESULT=fail; MAIN_TIP=""
  SENTINEL_STATE=ok; SHADOW_DONE=false; SHADOW_PROGRESS=""; MERGE_COMMIT=""
  shadow_ci || return 2                        # bounded CI wait (env gh/parse failure -> skip)
  shadow_freshness || return 2                 # decision-time fetch of main's tip (env fetch failure -> skip)
  shadow_terminal_approval; shadow_rank_gate
  read_auto_merge || return 2                  # decision-time read of auto_merge from the base ref tip

  local shadow_body="$RUN_DIR/merge-shadow.md"

  # Not armed -> plain shadow (issue #37): the loud YR-MERGE-SHADOW record, then stop for the human.
  if [ "$AUTO_MERGE" != true ]; then
    emit_and_post "$shadow_body" --mode shadow || return 2
    return 0
  fi

  # Armed regime. Shadow completion is computed at decision time from prior records + main history.
  compute_shadow_complete || return 2
  if [ "$SHADOW_DONE" != true ]; then
    # Refuse to HONOR auto_merge until shadow is complete — a loud shadow record with the progress note.
    emit_and_post "$shadow_body" --mode shadow --shadow-complete false --shadow-progress "$SHADOW_PROGRESS" \
      --armed-note "armed, shadow-incomplete $SHADOW_PROGRESS" || return 2
    return 0
  fi

  # Armed + shadow complete. The sentinel is a GLOBAL kill switch, read LIVE (a file stat, no git round-
  # trip): if thrown, refuse this merge for the very next decision and hard-block for the human.
  if [ -e "$MERGE_SENTINEL" ]; then
    SENTINEL_STATE=thrown
    armed_block sentinel "the host sentinel ($MERGE_SENTINEL) is thrown — clear it to resume autonomous merges" || return 2
    return 0
  fi

  # The reviewed-diff conditions must hold; a moved main (freshness) is REMEDIATED below, not blocked.
  local blk=""
  [ "$APPROVE_RESULT" = pass ] || blk=terminal_approval
  [ -z "$blk" ] && { [ "$RANK_RESULT" = pass ] || blk=rank_gate; }
  [ -z "$blk" ] && { [ "$CI_RESULT" = pass ] || blk=ci_green; }
  if [ -n "$blk" ]; then
    armed_block "$blk" "the merge condition '$blk' failed — see the YR-MERGE record on the PR" || return 2
    return 0
  fi

  # Freshness: if main advanced since the checks passed, rebase onto the tip and re-establish green before
  # merging; a rebase conflict (or a failure to re-green) hard-blocks for the human — a stale green never merges.
  if [ "$FRESH_RESULT" != pass ]; then
    local rc=0; rebase_onto_tip || rc=$?
    if [ "$rc" -eq 2 ]; then return 2; fi
    if [ "$rc" -ne 0 ]; then
      armed_block freshness "main advanced and the rebase onto ${MAIN_TIP:-the tip} could not be re-established green — resolve by hand" || return 2
      return 0
    fi
  fi

  # Full armed pass: squash-merge into main, post the durable YR-MERGE: MERGED, let native close->Done finish.
  do_squash_merge || return 2                  # merge API failure -> environmental, resumable (no reset)
  MERGED=1
  emit_and_post "$RUN_DIR/merge-record.md" --mode armed --decision MERGED --merge-commit "${MERGE_COMMIT:-}" \
    --shadow-complete true --shadow-progress "$SHADOW_PROGRESS" --sentinel ok \
    || log "warn: PR merged but the YR-MERGE: MERGED record failed to post (environmental, resumable)"
  return 0
}

MERGED=0; ARMED_BLOCKED=0; MERGE_MARKER=""
if terminal_step; then
  if [ "$MERGED" -eq 1 ]; then log "autonomous squash-merge complete — ${MERGE_MARKER:-YR-MERGE: MERGED}"
  else log "terminal merge record posted — ${MERGE_MARKER:-<none>}"; fi
else
  log "warn: terminal merge step hit an environmental failure — classified environmental, resumable (no record, no merge, not Blocked)"
fi

# ---- lifecycle: a factory merge supersedes In Review (native close->Done finishes); else stop for the human ----
if [ "$MERGED" -eq 1 ]; then
  log "PR squash-merged by the factory: $PR_URL  (#$ISSUE -> native close -> Done)"
else
  set_status "In Review"
  log "PR opened: $PR_URL  (#$ISSUE -> In Review${ARMED_BLOCKED:+, Reason=Blocked})"
fi
cleanup_wt
echo "$PR_URL"
