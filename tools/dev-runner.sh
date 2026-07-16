#!/usr/bin/env bash
# dev-runner — take a Ready task through one headless implement pass to an open PR, tracking lifecycle
# state on the NATIVE GitHub Projects Status/Reason fields (RFC 0003 rev 2: status belongs to the task,
# via native fields — not labels). Type is the native Issue Type (set by the Issue Form); hierarchy is
# native sub-issues.
#
# Pipeline (each stage a separate cold `claude -p` — builder!=verifier): gate (Status==Ready, Type==Task) ->
#   claim (Status=In Progress) -> fresh worktree -> implement -> independent test (boundary-guarded:
#   tester writing outside tests/ -> Blocked) -> deterministic check gate (CHECK_CMD, one repair) ->
#   independent review (VERDICT gate, one repair) -> commit/push -> open PR -> usage summary comment ->
#   Status=In Review. Each stage's token/cache usage is captured to usage-<stage>.json (tools/stage_usage.py)
#   and rolled up into one PR comment + usage-summary.json in the run dir (issue #48).
#   empty acceptance criteria / a model (build or review) not in the registry / an inverted or
#     cross-provider ranked build/review pair / no `.yr/factory.toml` anywhere (repo never onboarded,
#     the epic-gate's own admission wall's backstop) -> Status=Backlog + Reason=Needs-info (no LLM).
#   any stage failure                                  -> Reason=Blocked + comment (failure stays visible).
#   a claude -p stage killed by a quota/rate-limit signature -> environmental hold (preserve+resume,
#     no LLM repair), same discipline as the check gate's environment failure.
#   a PR-stage remote write (git push / gh pr create) failing transiently -> bounded exponential-backoff
#     retries (PR_STAGE_* below), then the SAME environmental hold on exhaustion (issue #84) — never a
#     teardown; a non-remote PR-stage failure (no changes produced, commit failure) stays a hard Block.
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
# PR-stage remote-write retries (issue #84; conservative defaults, operator-tunable):
#   PR_STAGE_RETRIES (default 3, beyond the first attempt), PR_STAGE_BACKOFF_BASE (default 5s),
#   PR_STAGE_BACKOFF_FACTOR (default 2), PR_STAGE_BACKOFF_MAX (default 60s per-attempt cap) — see the
#   PR stage below for the retry loop these drive.
# STAGE_GROUP_GRACE (issue #247; default 30s, operator-tunable): seconds a stage's process group is given
#   to empty out on its own after its leader exits before a lingering member is reaped and the stage
#   records a refusal — see the constant's own doc comment below for what "still alive after the grace"
#   assumes about the deployment's init.
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"; GH_BIN="${GH_BIN:-gh}"; GIT_BIN="${GIT_BIN:-git}"
EFFORT="${EFFORT:-high}"
# Model roles come from the registry (models.toml via tools/registry.py) — the single model surface;
# the old MODEL/HARD_MODEL tiers are retired. BUILD_MODEL/REVIEW_MODEL are the operator env overrides,
# one per role, sitting ATOP task/manifest/registry-default. Either may name a registry entry (runs
# ranked) OR a raw unregistered id (the ONLY place a non-registry id runs — unranked + loudly warned,
# never bounced). MODELS_REGISTRY overrides the registry file (default: the factory's own models.toml).
BUILD_MODEL="${BUILD_MODEL:-}"; REVIEW_MODEL="${REVIEW_MODEL:-}"
# Shadow review seat (issue #165): a non-gating SECOND verdict on every gating review round, dark by
# default. BOTH keys must be set — YR_SHADOW_MODEL (the model id to run the shadow reviewer under) and
# YR_SHADOW_BASE_URL (an ANTHROPIC_BASE_URL override applied to that ONE shadow subprocess only) — or the
# whole feature is inert: no shadow subprocess, no shadow artifact, no shadow comment. Never wired into
# the review gate, terminal_approval, or the merge evaluator (see shadow_review_round below).
YR_SHADOW_MODEL="${YR_SHADOW_MODEL:-}"; YR_SHADOW_BASE_URL="${YR_SHADOW_BASE_URL:-}"
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
reeval_refuse() { echo "dev-runner: RE-EVALUATE REFUSED: $*" >&2; exit 3; }  # --re-evaluate refusal, same family as gate
log()  { echo "dev-runner: $*" >&2; }
usage(){ echo "usage: dev-runner.sh <issue#> [--repo <owner/name>] [--dry-run] [--re-evaluate <pr#>]" >&2; exit 2; }

# ---- parse args ----
ISSUE=""; REPO=""; DRY_RUN=0; REEVAL_PR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)        REPO="${2:-}"; shift 2;;
    --dry-run)     DRY_RUN=1; shift;;
    --re-evaluate) REEVAL_PR="${2:-}"; shift 2;;
    -h|--help)     usage;;
    -*)            die "unknown flag: $1";;
    *)             if [ -z "$ISSUE" ]; then ISSUE="$1"; shift; else die "unexpected arg: $1"; fi;;
  esac
done
[ -n "$ISSUE" ] || usage
case "$ISSUE" in *[!0-9]*|"") die "issue must be a number, got: '$ISSUE'";; esac
if [ -n "$REEVAL_PR" ]; then
  case "$REEVAL_PR" in *[!0-9]*|"") die "--re-evaluate requires a numeric PR number, got: '$REEVAL_PR'";; esac
  [ "$DRY_RUN" -eq 0 ] || die "--dry-run and --re-evaluate are mutually exclusive"
fi

# ---- resolve repo / owner ----
if [ -z "$REPO" ]; then
  REPO="$("$GH_BIN" repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" \
    || die "could not resolve repo; pass --repo <owner/name>"
fi
OWNER="${REPO%/*}"
# RUN_DIR (per-pid) is computed here, before any DoR/gate exit, purely so the opening line below can name
# it — the directory itself is only created later (unchanged timing, issue #39) so dry-run stays read-only.
# This is also the line that self-identifies the run when dispatch (tools/dispatch.py) has redirected this
# process's stdout+stderr into a per-run log file: an attended invocation just prints it to the terminal.
RUN_DIR="$DEV_RUNNER_HOME/runs/${ISSUE}-$$"
log "run #$ISSUE ($REPO) starting — run dir: $RUN_DIR"
# ledger row (issue #206): wall-clock start, stamped BEFORE the DoR gate — the Needs-info bounce (which
# precedes claim) is itself a terminal branch and must carry a real wall_seconds figure too.
RUN_START_EPOCH="$(date +%s)"
RUN_START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- resolve the target repo's checkout + its build manifest (all relative to the workspace) ----
NAME="${REPO#*/}"
BASE_REPO="${BASE_REPO:-$YR_WORKSPACE/$NAME}"   # checkout convention: $YR_WORKSPACE/<name> (override: BASE_REPO)

# ---- shared terminal-merge-decision helpers (issues #37/#38, hoisted here for #70 --re-evaluate reuse) --
# shadow_ci / shadow_freshness / shadow_terminal_approval / shadow_rank_gate / read_auto_merge /
# emit_and_post are the exact terminal-decision core: the normal end-of-build path calls them from
# terminal_step() (below, after the PR opens); --re-evaluate calls them directly against an EXISTING
# PR's current head, with no DoR gate, no claim, no worktree, no LLM stage. MERGE_GIT_DIR is the git
# checkout freshness/auto_merge are read from — the branch-keyed worktree ($WT) for a live build (set
# right after $WT below), the base checkout ($BASE_REPO) for a re-evaluation (no worktree exists there).
MERGE_CI_POLL_INTERVAL="${MERGE_CI_POLL_INTERVAL:-15}"   # poll cadence for in-flight CI (seconds)
MERGE_CI_TIMEOUT="${MERGE_CI_TIMEOUT:-600}"              # bounded wait for in-flight CI (seconds); timeout = fail
# An empty rollup read moments after `gh pr create` can be a real repo's CI not having registered yet
# (GitHub Actions registers check runs asynchronously) rather than zero configured checks -- so an empty
# read gets its OWN bounded registration grace, distinct from and much shorter than the in-flight wait above.
MERGE_CI_REG_POLL_INTERVAL="${MERGE_CI_REG_POLL_INTERVAL:-5}"  # poll cadence during the registration grace (seconds)
MERGE_CI_REG_GRACE="${MERGE_CI_REG_GRACE:-10}"                 # bounded wait for a check to register (seconds)

# (1) ci_green — poll the PR check rollup until nothing is in-flight (bounded); a rollup still empty
#     after its own bounded registration grace fails fast, WITHOUT the (much longer) in-flight wait.
#     Server CI is distinct from and additional to the in-build check_cmd.
shadow_ci(){   # sets CI_RESULT (pass|fail) + CI_STATE; returns 2 on an environmental gh/parse failure.
  local rollup="$RUN_DIR/check-rollup.json" start now rc counts total in_flight failed grace_start
  start="$(date +%s)"
  while :; do
    rc=0; "$GH_BIN" pr view "$PR_URL" --repo "$REPO" --json statusCheckRollup >"$rollup" 2>/dev/null || rc=$?
    [ "$rc" -eq 0 ] || return 2
    counts="$(python3 "$SELF_DIR/merge_shadow.py" classify-checks --rollup-file "$rollup" 2>/dev/null)" || return 2
    read -r total in_flight failed <<<"$counts" || true
    if [ "${total:-0}" -eq 0 ]; then
      # a fresh PR's rollup can legitimately read empty for a few seconds -- GitHub Actions registers
      # check runs asynchronously, moments after `gh pr create` -- so re-poll for a bounded REGISTRATION
      # GRACE before concluding "no CI configured" (zero-registered is not zero-configured).
      grace_start="$(date +%s)"
      while :; do
        now="$(date +%s)"
        if [ "$((now - grace_start))" -ge "$MERGE_CI_REG_GRACE" ]; then
          CI_RESULT=fail; CI_STATE=empty_after_grace; return 0      # still empty after grace: fail fast
        fi
        sleep "$MERGE_CI_REG_POLL_INTERVAL"
        rc=0; "$GH_BIN" pr view "$PR_URL" --repo "$REPO" --json statusCheckRollup >"$rollup" 2>/dev/null || rc=$?
        [ "$rc" -eq 0 ] || return 2
        counts="$(python3 "$SELF_DIR/merge_shadow.py" classify-checks --rollup-file "$rollup" 2>/dev/null)" || return 2
        read -r total in_flight failed <<<"$counts" || true
        [ "${total:-0}" -gt 0 ] && break                            # registered -> fall through to the normal wait
      done
      start="$(date +%s)"                                           # the normal bounded CI wait starts fresh here
    fi
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
#     it. MERGE_GIT_DIR is the worktree for a live build, or the base checkout for a --re-evaluate (no
#     worktree exists there) — either way a decision-time re-fetch is required: the only earlier fetch for
#     a live build ran at build start (minutes ago), and BASE_SHA is that same base checkout, so without
#     this re-fetch origin/$BASE_BRANCH would still equal BASE_SHA and freshness could never see a moved
#     main. A fetch failure is environmental (network/API), classified like the CI read (return 2) — never
#     a false pass.
shadow_freshness(){   # sets FRESH_RESULT (pass|fail) + MAIN_TIP; returns 2 on an environmental fetch failure.
  if [ -n "${MERGE_MAIN_TIP:-}" ]; then MAIN_TIP="$MERGE_MAIN_TIP"
  else
    "$GIT_BIN" -C "$MERGE_GIT_DIR" fetch -q origin "$BASE_BRANCH" 2>/dev/null || return 2   # decision-time re-fetch
    MAIN_TIP="$("$GIT_BIN" -C "$MERGE_GIT_DIR" rev-parse "origin/$BASE_BRANCH" 2>/dev/null || true)"
  fi
  [ -n "$MAIN_TIP" ] || { FRESH_RESULT=fail; return 0; }                                    # indeterminate -> fail
  [ "$BASE_SHA" = "$MAIN_TIP" ] && FRESH_RESULT=pass || FRESH_RESULT=fail
}
# The kept VERDICT grammar (issue #151; also cited by review_bundle.py's append_round): line-anchored
# `VERDICT:` (a prose or quoted mention never counts) — the LAST such line wins — trailing whitespace
# stripped. Shared by the review gate below and (3) terminal_approval, since both read the same file
# under the same fail-closed rule: pass requires EXACTLY "VERDICT: APPROVE".
verdict_line(){ grep -E '^VERDICT:' "$1" 2>/dev/null | tail -n1 | sed -E 's/[[:space:]]+$//'; }
# (3) terminal_approval — the LAST review round must be a clean 'VERDICT: APPROVE' (re-approval of a
#     revised diff counts; the first pass need not have been clean). Same exact-match rule as the gate.
shadow_terminal_approval(){
  if [ "$(verdict_line "$RUN_DIR/review.md")" = "VERDICT: APPROVE" ]
  then APPROVE_RESULT=pass; else APPROVE_RESULT=fail; fi
}
# (4) rank_gate — the resolved pair must satisfy review-rank >= build-rank on ONE provider, both ranked
#     (the reviewer is never weaker) — an unranked emergency override fails here -> shadow-only by
#     construction.
shadow_rank_gate(){
  if [ "$BUILD_RANKED" = 1 ] && [ "$REVIEW_RANKED" = 1 ] \
     && [ "$BUILD_PROVIDER" = "$REVIEW_PROVIDER" ] && [ "$REVIEW_RANK" -ge "$BUILD_RANK" ]
  then RANK_RESULT=pass; else RANK_RESULT=fail; fi
}
# (5a) auto_merge — read at DECISION time from the base ref's CURRENT tip (NEVER the start-of-run parse
#      at L~96). The decision-time fetch already ran in shadow_freshness, so origin/$BASE_BRANCH is fresh.
#      A missing manifest/key -> not armed (false), not an error. MERGE_AUTO_MERGE overrides (for tests).
read_auto_merge(){   # sets AUTO_MERGE (true|false); returns 2 on an environmental read/parse failure.
  if [ -n "${MERGE_AUTO_MERGE:-}" ]; then AUTO_MERGE="$MERGE_AUTO_MERGE"; return 0; fi
  local raw
  raw="$("$GIT_BIN" -C "$MERGE_GIT_DIR" show "origin/$BASE_BRANCH:.yr/factory.toml" 2>/dev/null || true)"
  [ -z "$raw" ] && { AUTO_MERGE=false; return 0; }
  AUTO_MERGE="$(printf '%s' "$raw" | python3 -c 'import sys,tomllib
try: d=tomllib.loads(sys.stdin.read())
except Exception: print("error"); sys.exit(0)
print("true" if d.get("auto_merge") is True else "false")' 2>/dev/null || echo error)"
  [ "$AUTO_MERGE" = error ] && return 2
  return 0
}

# emit the yr-merge record and post it on the PR. $1 = body file; the rest = mode-specific record args
# (--mode / --decision / --block-reason / --merge-commit / --note / --shadow-* / --sentinel).
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

# The host sentinel (kill switch): a FILE in the dispatch home, read LIVE at decision time (a file, not an
# inherited env var — a spawned runner carries its spawn-time environment; the file is global + git-free).
# Shadow-completion window defaults (the epic's pinned N/K). Hoisted here (issue #239) alongside the rest
# of the terminal-decision core so a record-less --re-evaluate can reach arming/sentinel/shadow-completion
# too, not just the four base conditions.
MERGE_SENTINEL="${MERGE_SENTINEL:-$DEV_RUNNER_HOME/merge-killswitch}"
SHADOW_WINDOW="${SHADOW_WINDOW:-5}"; SHADOW_NEED="${SHADOW_NEED:-3}"; SHADOW_SCAN="${SHADOW_SCAN:-40}"

# (5b) shadow completion — MECHANICAL, from the repo's prior PR merge records + main history (no sidecar):
#      one unified window over the last N merge records (shadow YR-MERGE-SHADOW and armed YR-MERGE alike),
#      >=K landed unreverted successes and no reset. See tools/merge_shadow.py shadow-complete.
#      MERGE_GIT_DIR is the git checkout main's history is read from — $WT for a live build, $BASE_REPO for
#      --re-evaluate (same convention as shadow_freshness/read_auto_merge above). Callers must set
#      PR_NUMBER (the current PR, excluded from the window) before calling.
compute_shadow_complete(){   # sets SHADOW_DONE (true|false) + SHADOW_PROGRESS (k/N); returns 2 on env failure.
  local prs="$RUN_DIR/prs.json" mainlog="$RUN_DIR/main-log.txt" out succ size
  "$GH_BIN" pr list --repo "$REPO" --base "$BASE_BRANCH" --state all --limit "$SHADOW_SCAN" \
     --json number,state,mergeCommit,mergedAt,comments >"$prs" 2>/dev/null || return 2
  "$GIT_BIN" -C "$MERGE_GIT_DIR" log "origin/$BASE_BRANCH" --max-count=300 --format='%H%x1e%B%x00' >"$mainlog" 2>/dev/null || return 2
  out="$(python3 "$SELF_DIR/merge_shadow.py" shadow-complete --prs-file "$prs" --main-log-file "$mainlog" \
         --repo "$REPO" --exclude-pr "$PR_NUMBER" --window "$SHADOW_WINDOW" --need "$SHADOW_NEED" 2>/dev/null)" || return 2
  read -r SHADOW_DONE succ size <<<"$out" || return 2
  SHADOW_PROGRESS="$succ/$SHADOW_WINDOW"
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

# ---- --re-evaluate <pr#>: re-run the terminal merge decision against an existing PR's CURRENT head — no
# DoR gate, no claim, no worktree, no LLM stage. Two shapes, by whether the PR already carries a prior
# YR-MERGE(-SHADOW) record (issue #70 vs issue #239):
#   a prior record exists — reuse ITS originating run's persisted inputs (review verdict, bundle hash,
#     resolved roles/ranks), recompute the four base conditions LIVE, and post a record that only ever
#     supersedes in shadow mode — NEVER a merge/rebase/board write, an armed repo included (the posted
#     record is the only write). The note names the record it supersedes, so history reads truthfully.
#   no prior record — the record-less state has no owner otherwise (a green, approved PR whose terminal
#     step never ran/recorded — the seed's live incident). There is no run_id to key off, so the
#     originating run is located by matching this PR's base commit against this issue's local run
#     bundles instead (_find_run_by_base); its absence is no longer a refusal — it becomes a fact carried
#     in the new record's note. The conditions, arming, sentinel, and shadow-completion are then evaluated
#     EXACTLY as the end-of-build terminal_step does, via the very same hoisted helpers, so the produced
#     record — shadow WOULD-MERGE/WOULD-BLOCK, or (armed) MERGED/BLOCKED — is exactly what the repo's
#     arming state already permits. Unlike terminal_step, a moved main (freshness) is never
#     rebase-remediated here (no worktree to rebase in) — it is just one more direct block condition, so a
#     stale green still never merges. No board/issue write either way (out of scope, issue #239): the
#     posted PR comment (and, for an armed pass, the merge itself) are the only writes.
_json_field(){   # $1 = JSON text, $2 = top-level key -> its value (bools as true/false, missing as "")
  printf '%s' "$1" | python3 -c "import sys,json
v=json.load(sys.stdin).get(\"$2\")
if isinstance(v, bool): print('true' if v else 'false')
elif v is None: print('')
else: print(v)"
}

# The record-less lookup (issue #239): with no prior record there is no run_id to key off, so locate the
# originating run by matching THIS PR's base commit against this issue's local run bundles instead — a
# real build's review-bundle.json names the commit it branched from (diff.base_sha); that's directly
# comparable to a PR head's own parent commit (the same `head_oid^` re-evaluate already resolves for a
# prior-record PR, single-commit-PR invariant included). The bundle's OWN diff.head_sha is a tree hash
# from before the commit was made, not the commit oid, so it is never a candidate for this match. Prefers
# the most recently modified match. Prints the run dir path, or nothing when no local build matches this
# base at all (a genuinely unbuilt/unlocatable PR — that stays a refusal, same fail-closed spirit as a
# missing run_id).
_find_run_by_base(){
  python3 -c '
import glob, json, os, sys
issue, base, runs_home = sys.argv[1], sys.argv[2], sys.argv[3]
best, best_mtime = "", -1.0
for d in glob.glob(os.path.join(runs_home, f"{issue}-*")):
    bundle_path = os.path.join(d, "review-bundle.json")
    if not os.path.isdir(d) or not os.path.isfile(bundle_path):
        continue
    try:
        bundle = json.load(open(bundle_path))
    except Exception:
        continue
    if (bundle.get("diff") or {}).get("base_sha") != base:
        continue
    mtime = os.path.getmtime(d)
    if mtime >= best_mtime:
        best, best_mtime = d, mtime
print(best)' "$ISSUE" "$1" "$DEV_RUNNER_HOME/runs"
}

re_evaluate(){
  mkdir -p "$DEV_RUNNER_HOME"
  local pr="$REEVAL_PR" prjson
  prjson="$("$GH_BIN" pr view "$pr" --repo "$REPO" \
    --json number,state,url,headRefName,baseRefName,headRefOid,comments 2>/dev/null)" \
    || reeval_refuse "could not fetch PR #$pr from $REPO"

  local state url head_ref base_ref head_oid
  state="$(_json_field "$prjson" state)"; url="$(_json_field "$prjson" url)"
  head_ref="$(_json_field "$prjson" headRefName)"; base_ref="$(_json_field "$prjson" baseRefName)"
  head_oid="$(_json_field "$prjson" headRefOid)"

  [ "$state" = "OPEN" ] || reeval_refuse "PR #$pr is not open (state: ${state:-unknown}) — re-evaluation only runs on an open PR"
  case "$head_ref" in
    "task/${ISSUE}-"*) : ;;
    *) reeval_refuse "PR #$pr's branch ($head_ref) does not belong to issue #$ISSUE (expected task/${ISSUE}-*)" ;;
  esac

  local cfile; cfile="$DEV_RUNNER_HOME/.reeval-comments-$$.json"
  printf '%s' "$prjson" | python3 -c 'import sys,json; json.dump(json.load(sys.stdin).get("comments") or [], sys.stdout)' > "$cfile"
  local origrec; origrec="$(python3 "$SELF_DIR/merge_shadow.py" last-record --comments-file "$cfile" 2>/dev/null)"
  rm -f "$cfile"
  [ -n "$origrec" ] || reeval_refuse "could not evaluate PR #$pr's prior merge records"

  local orig_dir note found; found="$(_json_field "$origrec" found)"
  PR_URL="${url:-$pr}"; BASE_BRANCH="$base_ref"; MERGE_GIT_DIR="$BASE_REPO"; PR_HEAD_SHA="$head_oid"

  "$GIT_BIN" -C "$BASE_REPO" fetch -q origin "$BASE_BRANCH" "$head_ref" 2>/dev/null \
    || reeval_refuse "git fetch of $BASE_BRANCH / $head_ref failed — cannot re-evaluate"
  BASE_SHA="$("$GIT_BIN" -C "$BASE_REPO" rev-parse "${head_oid}^" 2>/dev/null || true)"
  [ -n "$BASE_SHA" ] || reeval_refuse "could not resolve the parent of the PR's current head ($head_oid) — is it a single-commit PR?"

  if [ "$found" = "true" ]; then
    # ---- a prior record exists: reuse ITS originating run, always a shadow supersession (issue #70;
    # unchanged — never a merge/rebase/board write, an armed repo included).
    [ "$(_json_field "$origrec" malformed)" != "true" ] || reeval_refuse "PR #$pr's last merge record is malformed — refusing to guess the originating run"

    local run_id sup_decision sup_cond
    run_id="$(_json_field "$origrec" run_id)"; sup_decision="$(_json_field "$origrec" decision)"
    sup_cond="$(_json_field "$origrec" failed_condition)"
    [ -n "$run_id" ] || reeval_refuse "PR #$pr's last merge record carries no run_id — cannot locate the originating run"
    case "$run_id" in
      "${ISSUE}-"*) : ;;
      *) reeval_refuse "PR #$pr's originating run ($run_id) does not belong to issue #$ISSUE" ;;
    esac

    orig_dir="$DEV_RUNNER_HOME/runs/$run_id"
    [ -d "$orig_dir" ] || reeval_refuse "the originating run dir ($orig_dir) is missing — cannot re-evaluate"
    [ -f "$orig_dir/review.md" ] || reeval_refuse "the originating run's review.md is missing ($orig_dir/review.md)"
    [ -f "$orig_dir/review-bundle.json" ] || reeval_refuse "the originating run's review-bundle.json is missing ($orig_dir/review-bundle.json)"
    note="re-evaluation of run $run_id — supersedes ${sup_decision:-an unknown decision}${sup_cond:+ — $sup_cond}"
  else
    # ---- no prior record (issue #239): the PR's absence of a record is a fact, not a refusal — locate
    # the run by matching this PR's base commit, then evaluate live under the standard conditions below.
    orig_dir="$(_find_run_by_base "$BASE_SHA")"
    [ -n "$orig_dir" ] || reeval_refuse "could not locate a build for PR #$pr's base commit ($BASE_SHA) among issue #$ISSUE's local runs — nothing to evaluate against"
    [ -f "$orig_dir/review.md" ] || reeval_refuse "the located run's review.md is missing ($orig_dir/review.md)"
    note="no prior merge decision record found on PR #$pr — evaluated live against its current head"
  fi

  RUN_DIR="$orig_dir"; BUNDLE="$RUN_DIR/review-bundle.json"

  # resolved roles/ranks: REUSED verbatim from the originating run's bundle, never re-derived or re-resolved.
  local roles; roles="$(python3 -c 'import json,sys
b=json.load(open(sys.argv[1]))
def r(role):
    d=b.get(role) or {}
    print(d.get("provider") or "")
    print(d.get("rank") if d.get("rank") is not None else "")
    print("1" if d.get("ranked") else "0")
r("build"); r("review")' "$BUNDLE" 2>/dev/null)" || reeval_refuse "could not read resolved roles from $BUNDLE"
  mapfile -t _roles <<<"$roles"
  BUILD_PROVIDER="${_roles[0]:-}"; BUILD_RANK="${_roles[1]:-}"; BUILD_RANKED="${_roles[2]:-0}"
  REVIEW_PROVIDER="${_roles[3]:-}"; REVIEW_RANK="${_roles[4]:-}"; REVIEW_RANKED="${_roles[5]:-0}"

  CI_RESULT=fail; CI_STATE=unknown; FRESH_RESULT=fail; APPROVE_RESULT=fail; RANK_RESULT=fail; MAIN_TIP=""
  shadow_ci || reeval_refuse "environmental failure reading CI status for PR #$pr — retry later, no record posted"
  shadow_freshness || reeval_refuse "environmental failure reading $BASE_BRANCH's current tip — retry later, no record posted"
  shadow_terminal_approval
  shadow_rank_gate

  if [ "$found" = "true" ]; then
    # a prior record's re-evaluation NEVER arms: auto_merge is still READ (informational, into the
    # posted record's own auto_merge field) but never gates or selects the mode — this path always
    # posts shadow, whatever it reads.
    AUTO_MERGE=""; read_auto_merge || true
    emit_and_post "$RUN_DIR/merge-shadow-reeval.md" --mode shadow --note "$note" \
      || reeval_refuse "environmental failure posting the re-evaluation record — retry later, no record posted"
    log "re-evaluation posted for PR #$pr (issue #$ISSUE, run $(basename "$orig_dir")) — ${MERGE_MARKER:-<none>}"
    echo "$PR_URL"
    return
  fi

  # ---- no prior record: AUTO_MERGE now DIRECTLY selects the record class — the SAME arming/sentinel/
  # shadow-completion gates the live pipeline's terminal_step applies, via the very same hoisted helpers
  # (issue #239). Freshness is never rebase-remediated here (no worktree) — it is one more direct block.
  read_auto_merge || reeval_refuse "environmental failure reading auto_merge for $REPO — retry later, no record posted"

  if [ "$AUTO_MERGE" != true ]; then
    emit_and_post "$RUN_DIR/merge-shadow-reeval.md" --mode shadow --note "$note" \
      || reeval_refuse "environmental failure posting the re-evaluation record — retry later, no record posted"
    log "re-evaluation posted for PR #$pr (issue #$ISSUE, run $(basename "$orig_dir")) — ${MERGE_MARKER:-<none>}"
    echo "$PR_URL"
    return
  fi

  PR_NUMBER="$pr"
  compute_shadow_complete || reeval_refuse "environmental failure computing shadow completion for PR #$pr — retry later, no record posted"
  if [ "$SHADOW_DONE" != true ]; then
    emit_and_post "$RUN_DIR/merge-shadow-reeval.md" --mode shadow --shadow-complete false --shadow-progress "$SHADOW_PROGRESS" \
      --note "$note — armed, shadow-incomplete $SHADOW_PROGRESS" \
      || reeval_refuse "environmental failure posting the re-evaluation record — retry later, no record posted"
    log "re-evaluation posted for PR #$pr (issue #$ISSUE, run $(basename "$orig_dir")) — ${MERGE_MARKER:-<none>}"
    echo "$PR_URL"
    return
  fi

  if [ -e "$MERGE_SENTINEL" ]; then
    emit_and_post "$RUN_DIR/merge-record-reeval.md" --mode armed --decision BLOCKED --block-reason sentinel \
      --shadow-complete true --shadow-progress "$SHADOW_PROGRESS" --sentinel thrown --note "$note" \
      || reeval_refuse "environmental failure posting the re-evaluation record — retry later, no record posted"
    log "re-evaluation posted for PR #$pr (issue #$ISSUE, run $(basename "$orig_dir")) — ${MERGE_MARKER:-<none>}"
    echo "$PR_URL"
    return
  fi

  local blk=""
  [ "$APPROVE_RESULT" = pass ] || blk=terminal_approval
  [ -z "$blk" ] && { [ "$RANK_RESULT" = pass ] || blk=rank_gate; }
  [ -z "$blk" ] && { [ "$CI_RESULT" = pass ] || blk=ci_green; }
  [ -z "$blk" ] && { [ "$FRESH_RESULT" = pass ] || blk=freshness; }
  if [ -n "$blk" ]; then
    emit_and_post "$RUN_DIR/merge-record-reeval.md" --mode armed --decision BLOCKED --block-reason "$blk" \
      --shadow-complete true --shadow-progress "$SHADOW_PROGRESS" --sentinel ok --note "$note" \
      || reeval_refuse "environmental failure posting the re-evaluation record — retry later, no record posted"
    log "re-evaluation posted for PR #$pr (issue #$ISSUE, run $(basename "$orig_dir")) — ${MERGE_MARKER:-<none>}"
    echo "$PR_URL"
    return
  fi

  do_squash_merge || reeval_refuse "environmental failure merging PR #$pr — retry later, no record posted"
  emit_and_post "$RUN_DIR/merge-record-reeval.md" --mode armed --decision MERGED --merge-commit "${MERGE_COMMIT:-}" \
    --shadow-complete true --shadow-progress "$SHADOW_PROGRESS" --sentinel ok --note "$note" \
    || log "warn: PR #$pr merged but the YR-MERGE: MERGED re-evaluation record failed to post (environmental, resumable)"
  log "re-evaluation squash-merged PR #$pr (issue #$ISSUE, run $(basename "$orig_dir")) — ${MERGE_MARKER:-YR-MERGE: MERGED}"
  echo "$PR_URL"
}
if [ -n "$REEVAL_PR" ]; then
  re_evaluate
  exit 0
fi

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
# The admission wall: raw still empty after BOTH reads above means this repo carries no manifest
# anywhere — never onboarded, as opposed to one whose manifest exists but is merely sparse (individual
# keys absent keep their documented per-key defaults below, unchanged — that path is untouched by this).
# Folded into the NEEDS_INFO bounce below (the runner's existing Backlog+Needs-info shape) rather than a
# separate exit, so it fires after the DoR/Type gate above but before claim/worktree either way.
MF_ONBOARD_MSG=""
[ -z "$MF_RAW" ] && MF_ONBOARD_MSG="this repo is not onboarded — no \`.yr/factory.toml\` found at the base ref ($MANIFEST_REF) or in the working tree ($MANIFEST). Onboarding (auth, onboarding the repo, arming) is attended, design-side work — never a slice the factory can pick up itself. Onboard the repo, then set Status back to Ready to resume."
MF_CHECK_CMD=""; MF_MODEL=""; MF_BASE_REF=""; MF_REVIEW_MODEL=""; MF_LINT_CMD=""; MF_LINT_FIX_CMD=""; MF_LENS_CMD=""; MF_AUTO_MERGE="false"
if [ -n "$MF_RAW" ]; then
  # auto_merge (issue #38) is parsed here alongside the rest, but the MERGE DECISION never trusts this
  # start-of-run value — read_auto_merge re-reads it from the base ref's current tip at decision time.
  # lint_cmd/lint_fix_cmd (issue #213) are the lint tier's opaque commands, lens_cmd (issue #214) the
  # advisory lens tier's — all with no built-in default (absent = off, the auto_merge defaults-off
  # precedent), applied via the same env>manifest precedence below.
  _mf_out="$(printf '%s' "$MF_RAW" | python3 -c 'import sys,tomllib
d=tomllib.loads(sys.stdin.read())
for k in ("check_cmd","model","base_ref","review_model","lint_cmd","lint_fix_cmd","lens_cmd"): print(str(d.get(k) or "").replace("\n"," "))
print("true" if d.get("auto_merge") is True else "false")' 2>/dev/null)" \
    || log "warn: could not parse manifest from $MANIFEST_REF"
  mapfile -t _mf <<<"$_mf_out"
  MF_CHECK_CMD="${_mf[0]:-}"; MF_MODEL="${_mf[1]:-}"; MF_BASE_REF="${_mf[2]:-}"; MF_REVIEW_MODEL="${_mf[3]:-}"; MF_LINT_CMD="${_mf[4]:-}"; MF_LINT_FIX_CMD="${_mf[5]:-}"; MF_LENS_CMD="${_mf[6]:-}"; MF_AUTO_MERGE="${_mf[7]:-false}"
fi
# precedence everywhere: explicit env  >  repo manifest  >  built-in default
BASE_REF="${BASE_REF:-${MF_BASE_REF:-origin/main}}"; BASE_BRANCH="${BASE_REF#origin/}"
CHECK_CMD="${CHECK_CMD:-${MF_CHECK_CMD:-$BASE_REPO/.venv/bin/python -m pytest tests/ -q}}"
# lint tier (issue #213): NO built-in default — an absent key leaves LINT_CMD/LINT_FIX_CMD empty, and an
# empty LINT_CMD is off (byte-identical to today: no probe, no output). env overrides manifest as ever.
LINT_CMD="${LINT_CMD:-${MF_LINT_CMD:-}}"
LINT_FIX_CMD="${LINT_FIX_CMD:-${MF_LINT_FIX_CMD:-}}"
# lens tier (issue #214): NO built-in default either — an absent key leaves LENS_CMD empty, and an empty
# LENS_CMD is off (byte-identical to today: no run, no artifact, no comment). env overrides manifest as ever.
LENS_CMD="${LENS_CMD:-${MF_LENS_CMD:-}}"

# ---- fetch issue (state/title/body) ----
ISSUE_JSON="$("$GH_BIN" issue view "$ISSUE" --repo "$REPO" --json number,title,body,state,issueType 2>/dev/null)" \
  || die "could not fetch issue #$ISSUE from $REPO"
TITLE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("title","") or "")')"
BODY="$(printf '%s' "$ISSUE_JSON"  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("body","") or "")')"
STATE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("state","") or "")')"
# native Issue Type name ("Task"/"Bug"/"Feature"), or "" when the issue is untyped (issueType: null).
ITYPE="$(printf '%s' "$ISSUE_JSON" | python3 -c 'import sys,json; t=json.load(sys.stdin).get("issueType") or {}; print((t.get("name","") if isinstance(t,dict) else "") or "")')"

# ---- find the project item id + current Status/Reason (both project-item-resident, RFC 0003) ----
ITEMS_JSON="$("$GH_BIN" project item-list "$PROJECT_NUMBER" --owner "$OWNER" --limit 500 --format json 2>/dev/null)" \
  || die "could not query project #$PROJECT_NUMBER on $OWNER (is the gh 'project' scope granted?)"
ITEM_LINE="$(printf '%s' "$ITEMS_JSON" | python3 -c 'import sys,json
n=int(sys.argv[1]); repo=sys.argv[2]
for it in json.load(sys.stdin).get("items",[]):
    c=it.get("content") or {}
    if c.get("number") == n and (c.get("repository") or "") == repo:
        print((it.get("id","") or "") + "\t" + (it.get("status","") or "") + "\t" + (it.get("reason","") or "")); break' "$ISSUE" "$REPO")"
ITEM_ID="${ITEM_LINE%%$'\t'*}"; _ITEM_REST="${ITEM_LINE#*$'\t'}"
ITEM_STATUS="${_ITEM_REST%%$'\t'*}"; ITEM_REASON="${_ITEM_REST#*$'\t'}"
[ "$ITEM_ID" = "$ITEM_LINE" ] && { ITEM_STATUS=""; ITEM_REASON=""; }   # no tab => no match

# field setters (best-effort: a failed state write warns, never aborts the actual work)
_set_field(){ "$GH_BIN" project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
              --field-id "$1" --single-select-option-id "$2" >/dev/null 2>&1 || log "warn: could not set $3 on #$ISSUE"; }
set_status(){ local o="${STATUS_OPT[$1]:-}"; [ -n "$o" ] || { log "warn: no option id for Status=$1"; return 0; }
              _set_field "$STATUS_FIELD_ID" "$o" "Status=$1"; }
set_reason(){ local o="${REASON_OPT[$1]:-}"; [ -n "$o" ] || { log "warn: no option id for Reason=$1"; return 0; }
              _set_field "$REASON_FIELD_ID" "$o" "Reason=$1"; }
clear_reason(){ "$GH_BIN" project item-edit --id "$ITEM_ID" --project-id "$PROJECT_ID" \
                --field-id "$REASON_FIELD_ID" --clear >/dev/null 2>&1 || log "warn: could not clear Reason on #$ISSUE"; }
comment(){ "$GH_BIN" issue comment "$ISSUE" --repo "$REPO" --body "$1" >/dev/null 2>&1 || true; }

# ---- DoR gate (refuse before any work; never invokes the LLM on refusal; no writes) ----
[ "$STATE" = "OPEN" ] || gate "issue #$ISSUE is not open (state: ${STATE:-unknown})"
[ -n "$ITEM_ID" ]     || gate "issue #$ISSUE is not in project #$PROJECT_NUMBER"
[ "$ITEM_STATUS" = "Ready" ] || gate "issue #$ISSUE is not Ready (Status: ${ITEM_STATUS:-none})"
# Type gate: build Tasks only. A Feature/epic accidentally set Ready must NOT be built — epics are native
# sub-issue parents, not build units. Case-insensitive; REQUIRE_ISSUE_TYPE='' opts out (repos w/o types).
# An UNTYPED Ready item is not an epic — left as a bare gate() (no-write refusal) it wins the dispatch
# flock every tick with no state change, permanently starving the rest of the board. So it folds into the
# NEEDS_INFO bounce below (Status=Backlog + Reason=Needs-info) instead, same as the admission wall above.
# A typed-but-wrong Type (e.g. Feature) keeps the polite no-write gate() unchanged — it must stay Ready
# for the epic-gate sweeper.
TYPE_NEEDS_INFO=""
if [ -n "$REQUIRE_ISSUE_TYPE" ] \
   && [ "$(printf '%s' "$ITYPE" | tr '[:upper:]' '[:lower:]')" != "$(printf '%s' "$REQUIRE_ISSUE_TYPE" | tr '[:upper:]' '[:lower:]')" ]; then
  if [ -z "$ITYPE" ]; then
    TYPE_NEEDS_INFO="issue #$ISSUE has no Issue Type set — the runner builds Type=$REQUIRE_ISSUE_TYPE only. Set the Issue Type to $REQUIRE_ISSUE_TYPE, then set Status back to Ready to resume."
  else
    gate "issue #$ISSUE is not Type=$REQUIRE_ISSUE_TYPE (Type: ${ITYPE:-none}) — the runner builds Tasks only; track epics/Features as sub-issue parents, not build units."
  fi
fi

# acceptance-criteria block: from its heading to the next heading of equal-or-higher level (#, ##, ###).
AC="$(printf '%s\n' "$BODY" | awk '
  { low=tolower($0) }
  low ~ /^#+[[:space:]]*acceptance criteria/ { grab=1; next }
  grab && /^#(#(#)?)?[[:space:]]/ { grab=0 }
  grab { print }
')"
# real criteria need actual content (the Issue Form default "- [ ]" has no alphanumerics).
NEEDS_INFO="$MF_ONBOARD_MSG"
[ -n "$(printf '%s' "$AC" | tr -dc '[:alnum:]')" ] \
  || NEEDS_INFO="${NEEDS_INFO:+$NEEDS_INFO; }the acceptance-criteria section is empty"
[ -n "$TYPE_NEEDS_INFO" ] && NEEDS_INFO="${NEEDS_INFO:+$NEEDS_INFO; }$TYPE_NEEDS_INFO"

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

# ledger_append (issue #206): one yr-ledger-row/1 JSONL row per runner invocation, appended at whichever
# terminal branch this run reaches. $1 = outcome type (needs-info|blocked|env-hold|merged|
# shadow-would-merge|shadow-would-block|in-review), $2 = outcome decision (may be empty). Fail-soft
# throughout: never dies, never exits, always returns 0 — a failure here must never block, fail, or gate
# the run. base_sha prefers the already-resolved $BASE_SHA (set once the worktree's cut point is known);
# before that it's read fresh from the worktree ($WT), and empty when neither exists yet (e.g. the
# Needs-info bounce, which runs before claim/worktree).
ledger_append(){
  local now_iso wall base_sha out rc=0
  now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || return 0
  wall=$(( $(date +%s 2>/dev/null || printf '%s' "$RUN_START_EPOCH") - RUN_START_EPOCH ))
  base_sha="${BASE_SHA:-}"
  if [ -z "$base_sha" ] && [ -n "${WT:-}" ]; then base_sha="$("$GIT_BIN" -C "$WT" rev-parse HEAD 2>/dev/null || true)"; fi
  out="$(python3 "$SELF_DIR/ledger.py" append \
    --ledger-dir "$DEV_RUNNER_HOME/ledger" \
    --run-id "$(basename "$RUN_DIR")" \
    --task "$REPO#$ISSUE" \
    --repo "$REPO" \
    --branch "${BRANCH:-}" \
    --base-sha "$base_sha" \
    --run-dir "$RUN_DIR" \
    --build-model "${BUILD_ID:-}" --review-model "${REVIEW_ID:-}" \
    --check-repair-model "${CHECK_REPAIR_ID:-}" --review-repair-model "${REVIEW_REPAIR_ID:-}" \
    --shadow-model "${YR_SHADOW_MODEL:-}" \
    --outcome-type "$1" --outcome-decision "${2:-}" \
    --ts-start "${RUN_START_ISO:-$now_iso}" --ts-end "$now_iso" --wall-seconds "$wall" 2>&1)" || rc=$?
  if [ "$rc" -eq 0 ]; then log "ledger: row appended ($1)"; else log "warn: ledger append failed (non-fatal): $out"; fi
  return 0
}

# ---- DoR content gate -> Needs-info bounce (Status=Backlog + Reason=Needs-info). Dry-run stays read-only ----
if [ -n "$NEEDS_INFO" ]; then
  [ "$DRY_RUN" = 1 ] && gate "$NEEDS_INFO"
  set_status Backlog; set_reason Needs-info
  comment "dev-runner: bounced to **Needs-info** — $NEEDS_INFO. Fix it, then set Status back to Ready."
  ledger_append needs-info ""
  gate "needs-info: $NEEDS_INFO"
fi

if [ "$DRY_RUN" -eq 1 ]; then        # read-only: report the resolved plan, write nothing
  # Additive: `model` stays = the resolved BUILD id (back-compat); `build`/`review` add the role objects.
  python3 -c 'import json,sys
a=sys.argv
def role(name,mid,prov,rank): return {"name":name or None,"id":mid,"provider":prov or None,"rank":(int(rank) if rank else None)}
print(json.dumps({"repo":a[1],"issue":int(a[2]),"branch":a[3],"model":a[4],"workspace":a[5],
                  "base_repo":a[6],"base_ref":a[7],"check_cmd":a[8],"auto_merge":a[17]=="true",
                  "lint_cmd":a[18],"lint_fix_cmd":a[19],"lens_cmd":a[20],
                  "build":role(a[9],a[10],a[11],a[12]),"review":role(a[13],a[14],a[15],a[16]),"ready":True}))' \
    "$REPO" "$ISSUE" "$BRANCH" "$BUILD_ID" "$YR_WORKSPACE" "$BASE_REPO" "$BASE_REF" "$CHECK_CMD" \
    "$BUILD_NAME" "$BUILD_ID" "$BUILD_PROVIDER" "$BUILD_RANK" \
    "$REVIEW_NAME" "$REVIEW_ID" "$REVIEW_PROVIDER" "$REVIEW_RANK" "$MF_AUTO_MERGE" \
    "$LINT_CMD" "$LINT_FIX_CMD" "$LENS_CMD"
  exit 0
fi

# ---- claim (Status: Ready -> In Progress) as early as possible ----
set_status "In Progress"
# A stale Blocked/Needs-info Reason left over from a prior failed round must not survive a fresh claim
# (issue #241) — cleared by VALUE at claim time, not by writer (a Projects field carries no author). Any
# other Reason value is left untouched.
case "$ITEM_REASON" in
  Blocked|Needs-info) clear_reason ;;
esac
log "claimed #$ISSUE -> In Progress, branch $BRANCH, build=$BUILD_ID review=$REVIEW_ID"

# from here, any failure flags Reason=Blocked (and comments) before exiting — failures are visible.
# If a review-repair round ran this run, $RUN_DIR/final.patch holds the post-repair tree (issue #172) —
# name it in the record so salvage recovers the final tree, not diff.patch's pre-repair snapshot.
fail_blocked(){ local extra=""
                 [ -f "$RUN_DIR/final.patch" ] && extra="  Post-repair artifact: $RUN_DIR/final.patch (the tree after the review-repair round — salvage from this, not diff.patch)."
                 set_reason Blocked; comment "dev-runner: **Blocked** — $1$extra"
                 ledger_append blocked ""
                 cleanup_wt; die "$1"; }

# ---- run dir (per-pid), worktree (repo+branch-keyed, stable), per-repo-branch stage-completion state
#      (issue #39; repo-keyed epic #126) --------------------------------------------------------------
# The worktree + state dir are keyed on repo + branch (stable across runs); the run dir is per-pid. Since
# branches embed only the per-repo issue number (task/<issue>-<slug>), two DIFFERENT repos' same-numbered
# tasks would otherwise collide on one worktree and on each other's resume markers now that builds run
# concurrently across repos (epic #126 — per-repo locks + a global cap) — so both paths are prefixed with
# the target repo's own slug (<owner>--<name>). As each stage completes it drops a durable marker
# (NN-<stage>.done). On an ENVIRONMENTAL failure the worktree + run dir + markers are PRESERVED (env_hold)
# and a relaunch resumes at the first stage without a .done marker; on success or a CODE/MACHINERY failure
# the state is cleared and the worktree torn down (cleanup_wt). Markers + a self-describing run.json live
# under state/<repo-slug>--<branch-slug>.
mkdir -p "$RUN_DIR"   # RUN_DIR itself was computed earlier (see the opening log line above)
# run-scoped TMPDIR (issue #142): every stage/gate subprocess (claude -p, check_cmd, its repair re-runs)
# inherits this exported TMPDIR, so tool temp roots that honor it (pytest's /tmp/pytest-of-* included)
# land under the run dir instead of piling up on /tmp — repo-agnostic, no check_cmd flags involved.
# Bounded even on a hard kill (no teardown runs): the residue sits under THIS run's own dir, never /tmp.
RUN_TMPDIR="$RUN_DIR/tmp"
mkdir -p "$RUN_TMPDIR"
export TMPDIR="$RUN_TMPDIR"
REPO_SLUG="$(printf '%s--%s' "$OWNER" "$NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')"
WT="$DEV_RUNNER_HOME/wt/${REPO_SLUG}--${BRANCH//\//-}"
MERGE_GIT_DIR="$WT"   # the shared terminal-decision helpers' git checkout, for a live build (see above)
STATE_DIR="$DEV_RUNNER_HOME/state/${REPO_SLUG}--${BRANCH//\//-}"
HOLD_MARKER="$STATE_DIR/env-hold"
stage_done(){ [ -f "$STATE_DIR/$1.done" ]; }               # has stage $1 already completed in a prior run?
mark_stage(){ mkdir -p "$STATE_DIR"; : > "$STATE_DIR/$1.done"; }
# cleanup_wt tears the worktree + branch down, clears the stage-completion state, AND removes this run's
# tmp dir (run logs, markers, run.json, usage artifacts are untouched) — the success and code/machinery-
# failure disposal. The environmental-hold path (env_hold) deliberately does NOT call it (preserved for resume).
cleanup_wt(){ "$GIT_BIN" -C "$BASE_REPO" worktree remove --force "$WT" 2>/dev/null || true
              "$GIT_BIN" -C "$BASE_REPO" branch -D "$BRANCH" 2>/dev/null || true
              rm -rf "$STATE_DIR"
              rm -rf "$RUN_TMPDIR"; }
# run.json: the resume manifest (branch, base ref, resolved models, worktree path), written when a hold
# is recorded so the preserved state is self-describing.
write_run_json(){ mkdir -p "$STATE_DIR"
  python3 -c 'import json,sys
json.dump({"branch":sys.argv[1],"base_ref":sys.argv[2],"build_id":sys.argv[3],
           "review_id":sys.argv[4],"worktree":sys.argv[5],"run_dir":sys.argv[6]}, open(sys.argv[7],"w"))' \
    "$BRANCH" "$BASE_REF" "$BUILD_ID" "$REVIEW_ID" "$WT" "$RUN_DIR" "$STATE_DIR/run.json" 2>/dev/null || true; }

# env_hold_record: the shared preserve+record core for an environmental hold — write the resume
# manifest, drop the hold marker, flag Blocked (visible, never a silently stranded claim), post a
# comment naming the hold, and die. Deliberately does NOT call cleanup_wt: that would discard exactly
# what a resume needs. Shared by the check-gate env_hold and the claude-stage llm_quota_hold below.
env_hold_record(){   # $1 = die/log message, $2 = issue comment body
  write_run_json
  mkdir -p "$STATE_DIR"; : > "$HOLD_MARKER"
  set_reason Blocked
  comment "$2"
  ledger_append env-hold ""
  die "$1"
}

# Resume-aware setup: an environmental hold left a marker + the branch-keyed worktree + the branch intact
# -> REUSE them (stages with a .done marker are skipped below, re-entering at the first incomplete one).
# Otherwise a FRESH worktree exactly as before (idempotently clearing any wedged prior worktree/branch and
# any stale, non-hold state so a retry isn't wedged).
branch_exists(){ "$GIT_BIN" -C "$BASE_REPO" show-ref --verify --quiet "refs/heads/$BRANCH"; }
if [ -f "$HOLD_MARKER" ] && [ -e "$WT" ] && branch_exists; then
  log "resume: reusing preserved env-hold worktree ($WT) + branch $BRANCH — skipping completed stages"
  "$GIT_BIN" -C "$BASE_REPO" fetch -q origin || true
  # RUN_DIR is per-pid (a resume gets a FRESH one), but a skipped stage's supporting artifact (checks.log,
  # review.md) lives only in the PRIOR run's dir — recover the ones later steps read unconditionally
  # (the review-bundle assembly, the reviewer-verdict PR comment) from the preserved run.json, so a hold
  # past the check/review stage (any of them — the PR stage included, issue #84) resumes cleanly instead
  # of those steps finding a path that was never populated in the new run dir.
  PRIOR_RUN_DIR="$(python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("run_dir") or "")
except Exception: print("")' "$STATE_DIR/run.json" 2>/dev/null || true)"
  if [ -n "$PRIOR_RUN_DIR" ] && [ "$PRIOR_RUN_DIR" != "$RUN_DIR" ]; then
    for _f in checks.log review.md; do
      [ -f "$PRIOR_RUN_DIR/$_f" ] && cp "$PRIOR_RUN_DIR/$_f" "$RUN_DIR/$_f"
    done
  fi
else
  rm -rf "$STATE_DIR"                                       # no valid hold -> discard any stale markers
  "$GIT_BIN" -C "$BASE_REPO" fetch -q origin || fail_blocked "git fetch failed"
  [ -e "$WT" ] && { "$GIT_BIN" -C "$BASE_REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"; }
  "$GIT_BIN" -C "$BASE_REPO" branch -D "$BRANCH" 2>/dev/null || true
  "$GIT_BIN" -C "$BASE_REPO" worktree add -q -b "$BRANCH" "$WT" "$BASE_REF" || fail_blocked "worktree add failed"
fi

# ---- factory self-freshness (issue #58): a stale deployment must never run invisibly. Best-effort only —
# this is visibility, never a gate: any failure (offline, no origin, whatever) skips silently, and a
# current checkout adds no output at all. SELF_DIR/.. is the factory's own checkout (override for tests:
# FACTORY_DIR). When the build target IS the factory itself (BASE_REPO == FACTORY_DIR), the target-repo
# fetch above already refreshed origin/main here — read the count without fetching again.
FACTORY_DIR="${FACTORY_DIR:-$(cd "$SELF_DIR/.." && pwd)}"
FACTORY_FETCH_TIMEOUT="${FACTORY_FETCH_TIMEOUT:-10}"
STALE_COUNT=""
if [ "$(cd "$BASE_REPO" 2>/dev/null && pwd)" = "$FACTORY_DIR" ]; then
  STALE_COUNT="$("$GIT_BIN" -C "$FACTORY_DIR" rev-list --count HEAD..origin/main 2>/dev/null || true)"
elif GIT_TERMINAL_PROMPT=0 timeout "$FACTORY_FETCH_TIMEOUT" "$GIT_BIN" -C "$FACTORY_DIR" fetch -q origin main 2>/dev/null; then
  STALE_COUNT="$("$GIT_BIN" -C "$FACTORY_DIR" rev-list --count HEAD..origin/main 2>/dev/null || true)"
fi
case "$STALE_COUNT" in ''|*[!0-9]*) STALE_COUNT="";; esac
if [ -n "$STALE_COUNT" ] && [ "$STALE_COUNT" -gt 0 ]; then
  log "WARNING: this dev-runner deployment ($FACTORY_DIR) is $STALE_COUNT commit(s) behind its own origin/main — the machinery that built this task may be stale. Redeploy (git pull) to pick up what's already shipped."
fi

# ---- quota/limit signatures (issue #40): a claude -p stage that dies with one of these in its log is
# an ENVIRONMENTAL ceiling (account/rate limit), never a code failure to hand to LLM repair. CLI exit
# codes for a limit kill are not documented/stable, so the signature is DATA — a default list pinned
# after checking it against the live Claude CLI's own error vocabulary (its auth/limit classifier
# strings: "usage limit reached", "rate limited", "overloaded_error"/"overloaded", and Anthropic API's
# 429 rate_limit_error status) plus "quota" as a conservative catch-all for the quota-exceeded phrasing
# other providers/backends use — fully overridable via QUOTA_SIGNATURES (a single grep -E alternation).
QUOTA_SIGNATURES="${QUOTA_SIGNATURES:-usage limit|rate limit|quota|overloaded|429}"
is_quota_failure(){ grep -qiE -- "$QUOTA_SIGNATURES" "$1" 2>/dev/null; }   # $1 = stage log file

# llm_quota_hold: a claude -p stage exited non-zero AND its log matched a quota/limit signature — an
# ENVIRONMENTAL ceiling (account/rate limit), not a code failure. Never hand it to LLM repair (there is
# nothing wrong with the code) and never silently strand the claim: reuse the exact same preserve+
# resume machinery as the check gate's env_hold (env_hold_record), worded so the Blocked comment marks
# it environmental rather than code.
llm_quota_hold(){   # $1 = stage label (e.g. "implement"), $2 = that stage's log file
  local msg="the $1 stage hit a quota/rate-limit signature in its output (log: $2) — an ENVIRONMENTAL ceiling (account/rate limit), not a code failure. Wait for the limit to reset (or provision the quota_pool's credential — see deploy/DISPATCH.md), then set Ready again — do NOT send it to LLM repair."
  env_hold_record "$msg" "dev-runner: **Environmental hold (quota)** — $msg  The worktree ($WT) and completed-stage checkpoints are preserved; a relaunch resumes at the first incomplete stage (green stages are not re-run)."
}

# ---- pool -> credential seam (issue #40): an entry's quota_pool selects a host credential via
# YR_POOL_<POOL_UPPER_SNAKE> in the dispatch environment (documented in deploy/DISPATCH.md), falling
# back to the ambient default (today's single-account behavior) when unset. This iteration only NAMES
# the seam: both shipping registry entries share one pool, so no env var is set and no stage's
# credential changes — pool_credential resolves empty and run_stage takes the no-override branch.
pool_for_model_id(){   # $1 = model id -> its registry entry's quota_pool, or "" (unranked/unknown id)
  python3 "$SELF_DIR/registry.py" --registry "$REGISTRY" pool-for-id --id "$1" 2>/dev/null \
    | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("quota_pool") or "")
except Exception: print("")' 2>/dev/null || true
}
pool_credential(){   # $1 = pool name -> the resolved YR_POOL_<POOL> value, or "" (ambient default)
  local pool="$1" var
  [ -n "$pool" ] || return 0
  var="YR_POOL_$(printf '%s' "$pool" | tr '[:lower:]-' '[:upper:]_')"
  printf '%s' "${!var:-}"
}

# wt_slug: the CLI's own project-slug transform for this run's worktree path (every '/' and '.' -> '-')
# — shared by archive_stage_transcript (the transcript's on-disk location) and stage_fail_msg (its
# pointer in a Blocked message) so the expression lives once, not as two copies free to drift apart.
wt_slug(){ printf '%s' "$WT" | tr '/.' '-'; }

# archive_stage_transcript (issue #205): at every stage's end, copy its CLI session transcript into the
# run dir as transcript-<stage>.jsonl (dedup suffix -2/-3 on repair re-runs — same convention as
# capture_stage_usage's usage-<stage>.json below) — a run artifact independent of the CLI's own
# retention. Reads the stage log READ-ONLY via tools/ledger.py (which imports tools/stage_usage.py's
# find_result_envelope for session_id — never a cloned parser), so it must run BEFORE
# capture_stage_usage rewrites the log in place on a clean exit; on a failed stage the log was never
# rewritten, so read order doesn't matter there. No envelope/session_id (e.g. signal-killed) falls back
# to the newest .jsonl in the CLI project slug dir (stages serialize per worktree, so "newest at stage
# end" IS this stage's own transcript) — logged either way. Fail-soft: never blocks or fails the run.
archive_stage_transcript(){   # $1 = stage log file
  local log="$1" base stage n=2 out slug_dir result
  base="$(basename "$log")"; base="${base%.*}"
  stage="$base"
  while [ -e "$RUN_DIR/transcript-$stage.jsonl" ]; do stage="$base-$n"; n=$((n + 1)); done
  out="$RUN_DIR/transcript-$stage.jsonl"
  slug_dir="$HOME/.claude/projects/$(wt_slug)"
  result="$(python3 "$SELF_DIR/ledger.py" archive --log "$log" --slug-dir "$slug_dir" --out "$out" 2>&1)" || true
  log "transcript archive ($stage): $result"
}

# capture_stage_usage (issue #48): on a stage's clean exit, best-effort extract the CLI's JSON result
# envelope from its log via tools/stage_usage.py — rewriting the log to the plain reply text (every
# downstream consumer: the verdict gate, review_bundle.py, the repair prompts, the PR-attached review
# must keep seeing exactly that) and filing the token/cache usage + model id + duration as
# usage-<stage>.json in the run dir. A log that never held an envelope (plain text, e.g. the stubbed
# test suite's `claude`) is left completely untouched and no usage file is written. The reviewer can run
# TWICE into the same log file (review.md, then again after a review-repair) — suffix the second round's
# artifact (usage-review-2.json) rather than overwrite, so the summary counts both rounds.
capture_stage_usage(){   # $1 = stage log file, $2 = model id used for this stage
  local log="$1" model="$2" base stage out n=2
  base="$(basename "$log")"; base="${base%.*}"
  stage="$base"
  while [ -e "$RUN_DIR/usage-$stage.json" ]; do stage="$base-$n"; n=$((n + 1)); done
  out="$RUN_DIR/usage-$stage.json"
  python3 "$SELF_DIR/stage_usage.py" extract --log "$log" --stage "$stage" --model "$model" --out "$out" \
    >/dev/null 2>&1 || true
}

# reap_pgid: kill every process still alive in a just-finished stage's process group — TERM first, then
# a bounded escalation to KILL — so a stray child a stage forgot to stop (the class that motivated the
# fatal pkill in gilda#9 run 9-4131516: a leftover Playwright run from an EARLIER attempt) is dead
# before the next stage starts, never surviving to contaminate it (issue #121).
reap_pgid(){   # $1 = the stage's pgid (== its pid; see run_stage)
  local pgid="$1" i
  kill -TERM -- "-$pgid" 2>/dev/null || return 0   # ESRCH: no group left, nothing to reap
  for i in 1 2 3 4 5; do
    kill -0 -- "-$pgid" 2>/dev/null || return 0
    sleep 0.1
  done
  kill -KILL -- "-$pgid" 2>/dev/null || true
}

# STAGE_GROUP_GRACE (issue #247): the stage leader ($pid == the group's pgid, see run_stage) exiting does
# not mean the group is empty — a child it backgrounded and returned without waiting on is still a member
# of that SAME group (setsid keeps the whole tree together), and reap_pgid above would kill it on sight:
# a silent orphaning, not an observed completion or a recorded refusal (the 2026-07-10 pair — #121's
# implementer and #125's tester — and run 171-200682 all lost a stage exactly this way, with the "works in
# the foreground only" charter line already live). Give a non-empty group this many seconds to finish
# naturally — long enough for the backgrounded child's own output to land in the stage log before the
# runner advances — before concluding it was abandoned and reaping it. `kill -0` cannot distinguish a
# live process from an unreaped zombie, so "still alive after the grace" below assumes an init that reaps
# zombies (true under systemd, this deployment's init); without one, a zombie would pin the wait for the
# full grace even after its actual work finished.
STAGE_GROUP_GRACE="${STAGE_GROUP_GRACE:-30}"
# STAGE_REFUSAL_RC: the sentinel exit code run_stage reports when a stage leader exited cleanly (rc 0)
# but left a live group member past the grace — a REFUSAL, not the leader's own (already-nonzero) exit
# code, so a caller that gates on rc (`|| X_RC=$?`) still sees a failure instead of a silent success.
STAGE_REFUSAL_RC=124
# LAST_STAGE_GROUP_REFUSED: set by run_stage on every call (never left over from a prior one) to whether
# THIS call's group needed reaping past the grace — the authoritative source callers gate on, since a rc
# equal to STAGE_REFUSAL_RC could in principle also be a genuine future CLI exit code (set -u: initialize
# before the first read, in case a caller ever inspects it before any stage has run).
LAST_STAGE_GROUP_REFUSED=0

# wait_group_or_refuse: after the stage leader has exited, poll (once a second) for up to
# STAGE_GROUP_GRACE seconds for its process group to empty out on its own. Returns 0 immediately if the
# group is already empty (the overwhelmingly common case: nothing to wait for). Returns 1 if a member is
# still alive once the grace is spent — the caller reaps the group either way; this only decides whether
# that reap is a silent cleanup after an observed completion or a recorded refusal.
wait_group_or_refuse(){   # $1 = pgid
  local pgid="$1" waited=0
  kill -0 -- "-$pgid" 2>/dev/null || return 0
  while kill -0 -- "-$pgid" 2>/dev/null; do
    [ "$waited" -ge "$STAGE_GROUP_GRACE" ] && return 1
    sleep 1
    waited=$((waited + 1))
  done
  return 0
}

# ---- a claude -p stage in the worktree (cold process; the runner owns git + the gates) ----
run_stage(){  # $1=role system-prompt, $2=task prompt, $3=log file, $4=allowedTools (default: full edit set),
              # $5=model id (default: build), $6=ANTHROPIC_BASE_URL override for THIS subprocess only (default: unset;
              # the shadow review seat, issue #165, is the one caller that passes it — every other call is untouched)
  local model="${5:-$BUILD_ID}" base_url="${6:-}" cred rc=0 fmt_overridden=0 pid
  LAST_STAGE_GROUP_REFUSED=0   # reset every call (issue #247) — stage_fail_msg reads this, not the rc value,
                                # so a genuine future 124 from the CLI itself is never misread as a refusal
  local sys_prompt; sys_prompt="$(printf '%s\n\n%s' "$1" "$STAGE_CHARTER")"
  # the task prompt travels on stdin, never argv (issue #121): a task whose acceptance criteria quote a
  # runnable string (e.g. `pkill -f "bash qa/qa-gate.sh"`) must not be able to pattern-match the stage's
  # OWN command line and self-kill the harness — exactly what happened in gilda#9 run 9-4131516. `-p`
  # with no positional value reads the prompt from stdin instead.
  local args=( -p --model "$model" --effort "$EFFORT"
               --permission-mode bypassPermissions --append-system-prompt "$sys_prompt"
               --allowedTools ${4:-Read Edit Write Bash}
               --setting-sources "${STAGE_SETTING_SOURCES:-project}" --strict-mcp-config )
  if [ -n "${CLAUDE_OUTPUT_FORMAT:-}" ]; then
    # explicit operator override wins over the new default, verbatim (old pairing) — no usage capture
    # is attempted on this path, so its output stays exactly as it always has.
    args+=( --output-format "$CLAUDE_OUTPUT_FORMAT" --verbose ); fmt_overridden=1
  else
    # single JSON result envelope (issue #48). Deliberately WITHOUT --verbose: pairing it with
    # `--output-format json` turns the output into a JSON ARRAY of stream events instead of the single
    # object this parses (verified against the live CLI) — --verbose is only for the stream-json
    # override above, never the default.
    args+=( --output-format json )
  fi
  cred="$(pool_credential "$(pool_for_model_id "$model")")"
  # run the CLI as the leader of its OWN process group (setsid) so it — and anything it spawns — can be
  # reaped as a unit once the stage exits (issue #121), instead of a stray child surviving into the next
  # stage. Backgrounding a pipeline in a non-interactive script (no job control) does not itself create a
  # new process group, so `exec setsid` succeeds in-place (no extra fork): `$!` IS the CLI's pid, and
  # that pid IS the new group's pgid. The task prompt is piped in via `printf '%s'` (no here-string) so
  # no trailing newline is added — byte-identical to what argv used to carry.
  if [ -n "$cred" ] && [ -n "$base_url" ]; then
    printf '%s' "$2" | ( cd "$WT" && CLAUDE_CONFIG_DIR="$cred" ANTHROPIC_BASE_URL="$base_url" exec setsid "$CLAUDE_BIN" "${args[@]}" ) >"$3" 2>&1 &
  elif [ -n "$base_url" ]; then
    printf '%s' "$2" | ( cd "$WT" && ANTHROPIC_BASE_URL="$base_url" exec setsid "$CLAUDE_BIN" "${args[@]}" ) >"$3" 2>&1 &
  elif [ -n "$cred" ]; then
    printf '%s' "$2" | ( cd "$WT" && CLAUDE_CONFIG_DIR="$cred" exec setsid "$CLAUDE_BIN" "${args[@]}" ) >"$3" 2>&1 &
  else
    printf '%s' "$2" | ( cd "$WT" && exec setsid "$CLAUDE_BIN" "${args[@]}" ) >"$3" 2>&1 &
  fi
  pid=$!
  wait "$pid" || rc=$?
  # a live group member past the grace is a refusal (wait_group_or_refuse), not the leader's own rc — but
  # usage capture below is keyed to the LEADER's own rc, unaffected by a sibling's refusal, so a stage
  # whose gate reads the log content rather than rc (the reviewer's verdict line) still sees a correctly
  # rewritten log either way (recovery amendment #1/#3, issue #247).
  local group_refused=0
  wait_group_or_refuse "$pid" || group_refused=1
  reap_pgid "$pid"
  archive_stage_transcript "$3"
  if [ "$rc" -eq 0 ] && [ "$fmt_overridden" -eq 0 ]; then capture_stage_usage "$3" "$model"; fi
  if [ "$group_refused" -eq 1 ]; then
    log "stage refused: process group $pid still had a live member after ${STAGE_GROUP_GRACE}s grace (log: $3) — reaped"
    LAST_STAGE_GROUP_REFUSED=1
    [ "$rc" -eq 0 ] && rc=$STAGE_REFUSAL_RC
  fi
  return "$rc"
}

# stage_fail_msg: a diagnosable Blocked message for a run_stage failure — always states the exit code;
# when the log is EMPTY (the CLI died before writing its output envelope, e.g. a pattern-matching pkill
# from inside the stage self-hitting its own process group, or any other external kill), name signal
# termination as the likely class (bash reports a signal-killed child as 128+N — 144 = 128+16 — never
# invent a signal name from the number) and point at the preserved session transcript instead of leaving
# the record naming only a zero-byte file (issue #121; gilda#9 run 9-4131516).
stage_fail_msg(){   # $1 = stage label, $2 = log file, $3 = exit code, $4 = 1 iff run_stage's own
                     # LAST_STAGE_GROUP_REFUSED (not the rc value — a future genuine 124 from the CLI
                     # itself must not be misread as a refusal, issue #247)
  local label="$1" log="$2" rc="$3" refused="${4:-0}"
  if [ "$refused" -eq 1 ]; then
    printf '%s stage refused (exit %s; log: %s) — it backgrounded a process and returned before that process finished; the runner gave the group %ss to complete on its own, then reaped it rather than let it run unobserved past the stage boundary' \
      "$label" "$rc" "$log" "$STAGE_GROUP_GRACE"
  elif [ -s "$log" ]; then
    printf '%s stage failed (exit %s; log: %s)' "$label" "$rc" "$log"
  else
    printf '%s stage failed: signal-terminated (exit %s) — the log is empty (log: %s), so the CLI likely died before writing anything; check the preserved session transcript under %s for what happened before the kill' \
      "$label" "$rc" "$log" "$HOME/.claude/projects/$(wt_slug)"
  fi
}
SPEC="$(printf 'GitHub issue #%s: %s\n\n%s' "$ISSUE" "$TITLE" "$BODY")"

# ---- stage charter (issue #50): the confinement contract every stage runs under, in every target repo —
# appended (by run_stage) to each stage's role prompt so a stage building a foreign repo still gets it, not
# just the factory's own. Kept free of the stage-aware test stub's four routed literals (its case-sensitive
# `case` match on the combined argv+stdin capture: TESTER, REVIEWER — still argv, in the role system-prompt
# — and "tests FAIL", "REQUESTED CHANGES" — on stdin since issue #121, in the task prompt) — a leaked
# literal here would misroute every stage, not just its own.
STAGE_CHARTER="You are one stage of an automated pipeline, running in one fresh worktree cut from the base ref. The pipeline holds builder ≠ verifier: the implementer writes production code and never authors the committed test suite; the tester writes tests only, derived from the acceptance criteria and never from the implementation's internals; the reviewer changes nothing. Write only inside this worktree — never the host. Make no git or board writes; the runner owns them (the reviewer's read-only git, e.g. diffing staged changes, is the one carve-out). Never weaken a gate: do not edit checks, CI configuration, .yr/factory.toml, or any test you were told not to touch. Manage processes by PID only — pattern-kills such as PKILL -f or PGREP -f are forbidden, because a stage's own command environment can contain the task text, and a pattern match can hit and kill the stage's own process instead of its intended target. If the task cannot be done within these rules, stop and say so — a Blocked run is a correct outcome, not a failure to route around. This pipeline produces a pull request only; deploy and host work are never a stage's. In-stage verification exercises only the scope this stage's change touches, with targeted tests; the repo's full check suite belongs to the deterministic check gate and server CI, never an in-stage inner loop. A stage works in the foreground only: it never polls, watches, or sleeps on external state, and when it cannot proceed it stops and says so. The task in front of it is self-contained by design; standing documents are not this stage's context."

# implementer — production code only
IMPL_SYS="You are the IMPLEMENTER stage of an automated dev pipeline. Implement the task so it satisfies every acceptance criterion. Write PRODUCTION CODE ONLY — do not author the committed test suite (an independent tester stage does that)."
if stage_done 01-implement; then
  log "resume: skipping implement (01-implement.done present)"
  # the prior run's implementer output is already in the reused worktree; recover a tree for the guard.
  "$GIT_BIN" -C "$WT" add -A
  IMPL_TREE="$("$GIT_BIN" -C "$WT" write-tree)"
else
  log "implement: $(basename "$CLAUDE_BIN") [$BUILD_ID] in $WT"
  IMPL_RC=0
  run_stage "$IMPL_SYS" "$(printf 'Implement the task below against its acceptance criteria. Make the minimal, clean change.\n\n%s' "$SPEC")" "$RUN_DIR/implement.log" || IMPL_RC=$?
  if [ "$IMPL_RC" -ne 0 ]; then
    [ "$LAST_STAGE_GROUP_REFUSED" -eq 0 ] && is_quota_failure "$RUN_DIR/implement.log" && llm_quota_hold "implement" "$RUN_DIR/implement.log"
    fail_blocked "$(stage_fail_msg "implement" "$RUN_DIR/implement.log" "$IMPL_RC" "$LAST_STAGE_GROUP_REFUSED")"
  fi

  # checkpoint: record the worktree tree state after the implementer so the tester boundary guard can
  # detect violations structurally (confinement principle — not advisory / prompt-only).
  "$GIT_BIN" -C "$WT" add -A
  IMPL_TREE="$("$GIT_BIN" -C "$WT" write-tree)"
  mark_stage 01-implement
fi

# tester — independent cold process: tests derived from the CRITERIA, not the implementation (builder≠verifier).
# Writes to tests/** only — enforced below by diffing against IMPL_TREE (block-and-raise, no silent revert).
TEST_SYS="You are the TESTER stage, independent of the implementer. Write automated tests that verify the ACCEPTANCE CRITERIA below, against the code now in this repository. Derive the tests from the CRITERIA (the spec), NOT from the implementation's internals. Do NOT modify production code — only add or extend tests. Your only legal write surface is the repo-root tests/ directory — not a same-named directory nested inside a deliverable (e.g. qa/tests/), which is outside it."
if stage_done 02-test; then
  log "resume: skipping test (02-test.done present)"
else
  log "test: independent tester stage"
  TEST_RC=0
  run_stage "$TEST_SYS" "$(printf 'Write tests that verify the acceptance criteria below.\n\n%s' "$SPEC")" "$RUN_DIR/test.log" || TEST_RC=$?
  if [ "$TEST_RC" -ne 0 ]; then
    [ "$LAST_STAGE_GROUP_REFUSED" -eq 0 ] && is_quota_failure "$RUN_DIR/test.log" && llm_quota_hold "test" "$RUN_DIR/test.log"
    fail_blocked "$(stage_fail_msg "tester" "$RUN_DIR/test.log" "$TEST_RC" "$LAST_STAGE_GROUP_REFUSED")"
  fi

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
  mark_stage 02-test
fi

# deterministic check gate — the RUNNER runs the checks, not the LLM. One repair attempt.
# The worktree is ephemeral (no .venv / node_modules — both gitignored, they live in the base checkout),
# so put the base repo's toolchain dirs on PATH: a manifest names tools plainly (`pytest`, `vitest`) and
# the runner supplies them, instead of hardcoding a venv path the worktree doesn't have.
# GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM are neutralized to /dev/null so host-ambient git config (e.g. an
# operator's global user.email) can never make this check greener than CI (PR #65: a helper that needed
# git identity passed here on host config but failed in CI with no identity). A check that genuinely
# needs git identity/config must set it up in its own fixtures, same as CI. This is scoped to the check
# child only — LLM stages and the runner's own git operations (worktree/commit/push) keep full host config.
run_checks(){ ( cd "$WT" && PATH="$BASE_REPO/.venv/bin:$BASE_REPO/node_modules/.bin:$PATH" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null bash -c "$CHECK_CMD" ) >"$RUN_DIR/checks.log" 2>&1; }
# run_lint (issue #213): the lint tier's runner, cloned from run_checks — same confinement (worktree cd,
# the venv + node bin dirs on PATH, host git config neutralized), output to lint.log in the run dir. $1 is
# an OPAQUE command run verbatim: python repos declare ruff, node repos eslint — no lint-output parsing, no
# language assumption anywhere. Used for both LINT_CMD (the probe / re-run) and LINT_FIX_CMD (the autofix).
run_lint(){ ( cd "$WT" && PATH="$BASE_REPO/.venv/bin:$BASE_REPO/node_modules/.bin:$PATH" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null bash -c "$1" ) >"$RUN_DIR/lint.log" 2>&1; }
# run_lens (issue #214): the advisory lens tier's runner — the run_checks/run_lint confinement shape
# (worktree cd, the venv + node bin dirs on PATH, host git config neutralized) with two DELIBERATE
# deviations: (1) stdout -> the run dir's lens.md and stderr -> lens.log are SEPARATE, never the shape's
# merged 2>&1 — a stderr traceback must never land in the PR-trail comment; and (2) YR_BASE_REF="$BASE_REF"
# is exported so a lens can be diff-aware. $1 is an OPAQUE command run verbatim — any stack's lens works,
# no lens-output parsing, no language assumption. The exit code is READ BUT NEVER GATES (see below).
run_lens(){ ( cd "$WT" && PATH="$BASE_REPO/.venv/bin:$BASE_REPO/node_modules/.bin:$PATH" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null YR_BASE_REF="$BASE_REF" bash -c "$1" ) >"$RUN_DIR/lens.md" 2>"$RUN_DIR/lens.log"; }
# Distinguish a CODE failure (the harness ran and tests failed) from an ENVIRONMENT failure (the harness
# could not execute at all: 127=command not found, 126=found-but-not-executable — e.g. a venv whose
# console-script shebang points at a moved/rebuilt interpreter). An env failure is NOT the implementer's
# to fix; handing it to the LLM repair invites host-mutating "fixes" (pip --break-system-packages) that
# paper over it. Fail closed and report it as an environment problem, never an LLM repair.
is_env_failure(){ [ "$1" -eq 126 ] || [ "$1" -eq 127 ]; }
# env_hold: an environmental failure is NOT the implementer's to fix and is transient (rebuild the
# toolchain, not the code). Rather than tear the run down, PRESERVE the worktree + run dir + stage
# markers and record a VISIBLE hold on the issue (never a silently stranded claim) — a relaunch then
# resumes at the first incomplete stage instead of re-paying every green stage (issue #39). It does NOT
# call cleanup_wt (that would discard exactly what a resume needs). Reason=Blocked keeps the failure
# visible on the board exactly as before; the hold marker + preserved worktree are what enable resume.
env_hold(){   # $1 = check exit code, $2 = context suffix
  local msg="check command could not execute (exit $1)$2 — an ENVIRONMENT/toolchain failure, not a code failure. The check harness (e.g. $BASE_REPO/.venv) is missing or broken; rebuild it, then set Ready again — do not paper over it. (log: $RUN_DIR/checks.log)"
  env_hold_record "$msg" "dev-runner: **Environmental hold** — $msg  The worktree ($WT) and completed-stage checkpoints are preserved; a relaunch resumes at the first incomplete stage (green stages are not re-run)."
}
# lint_env_hold (issue #213): the lint tier's sibling of env_hold — same preserve+resume machinery, but the
# record NAMES THE LINT COMMAND that failed and lint.log, never the check command's text or checks.log. A
# failure surface is read as a fact; a hold naming the wrong command would misdirect the rebuild. No LLM
# repair is attempted on a 126/127 lint or autofix failure — it is environmental, not the code's to fix.
lint_env_hold(){   # $1 = the lint (or autofix) command that failed, $2 = exit code, $3 = context suffix
  local msg="lint command could not execute (exit $2)$3 — command: $1 — an ENVIRONMENT/toolchain failure, not a code failure. The lint toolchain is missing or broken; rebuild it, then set Ready again — do not paper over it. (log: $RUN_DIR/lint.log)"
  env_hold_record "$msg" "dev-runner: **Environmental hold** — $msg  The worktree ($WT) and completed-stage checkpoints are preserved; a relaunch resumes at the first incomplete stage (green stages are not re-run)."
}
if stage_done 03-check; then
  log "resume: skipping check (03-check.done present)"
  CHECK_RC=0
else
  CHECK_RC=0; run_checks || CHECK_RC=$?
  if is_env_failure "$CHECK_RC"; then env_hold "$CHECK_RC" ""; fi
  if [ "$CHECK_RC" -ne 0 ]; then
    log "checks failed (exit $CHECK_RC) — one repair attempt [$CHECK_REPAIR_ID]"
    REPAIR_RC=0
    run_stage "$IMPL_SYS" "$(printf 'The project tests FAIL. Fix the PRODUCTION CODE so they pass — do NOT modify the tests. Reproduce with the failing tests only; the runner re-runs the full check suite after this stage. Failure output:\n\n%s\n\nTask:\n%s' "$(tail -n 40 "$RUN_DIR/checks.log")" "$SPEC")" "$RUN_DIR/repair.log" "Read Edit Write Bash" "$CHECK_REPAIR_ID" || REPAIR_RC=$?
    if [ "$REPAIR_RC" -ne 0 ] && [ "$LAST_STAGE_GROUP_REFUSED" -eq 0 ] && is_quota_failure "$RUN_DIR/repair.log"; then llm_quota_hold "check repair" "$RUN_DIR/repair.log"; fi
    CHECK_RC=0; run_checks || CHECK_RC=$?
    if is_env_failure "$CHECK_RC"; then env_hold "$CHECK_RC" " after the repair attempt"; fi
    [ "$CHECK_RC" -eq 0 ] || fail_blocked "checks still failing after one repair (log: $RUN_DIR/checks.log)"
  fi

  # ---- lint tier (issue #213): a manifest-declared, BLOCKING lint gate, run only AFTER check_cmd passes.
  # Absent LINT_CMD = off, byte-identical to today (no probe, no warning, no output). Ruled repair scope:
  # (1) deterministic autofix (LINT_FIX_CMD) first, NO LLM; then (2) at most ONE LLM repair confined to the
  # lint-flagged files; then (3) unconditionally after ANY repair-path mutation (the autofix alone
  # included) re-run BOTH check_cmd and lint_cmd, so checks.log/lint.log and the bundle's --check-exit
  # describe the tree AS SHIPPED — either failing ends the run Blocked. A lint 126/127 (and an autofix
  # 126/127) is environmental: lint_env_hold, no LLM. The lint-repair prompt is distinct from the
  # tests-frozen check-repair prompt so neither failure can trigger the other's stage.
  if [ -n "$LINT_CMD" ]; then
    LINT_MUTATED=0
    LINT_RC=0; run_lint "$LINT_CMD" || LINT_RC=$?
    if is_env_failure "$LINT_RC"; then lint_env_hold "$LINT_CMD" "$LINT_RC" ""; fi
    if [ "$LINT_RC" -ne 0 ]; then
      log "lint failed (exit $LINT_RC) — lint-repair: deterministic autofix${LINT_FIX_CMD:+ ($LINT_FIX_CMD)}, then at most one LLM repair"
      # (1) deterministic autofix first (no LLM). A 126/127 here is environmental too — same lint hold.
      if [ -n "$LINT_FIX_CMD" ]; then
        FIX_RC=0; run_lint "$LINT_FIX_CMD" || FIX_RC=$?
        if is_env_failure "$FIX_RC"; then lint_env_hold "$LINT_FIX_CMD" "$FIX_RC" " (autofix)"; fi
        LINT_MUTATED=1
        LINT_RC=0; run_lint "$LINT_CMD" || LINT_RC=$?
        if is_env_failure "$LINT_RC"; then lint_env_hold "$LINT_CMD" "$LINT_RC" " after the autofix"; fi
      fi
      # (2) if lint still fails, ONE LLM repair — a NEW prompt, confined to the lint-flagged files.
      if [ "$LINT_RC" -ne 0 ]; then
        log "lint still failing — one LLM repair attempt [$CHECK_REPAIR_ID]"
        LINT_REPAIR_RC=0
        run_stage "$IMPL_SYS" "$(printf 'The lint gate FAILS (command: %s). Fix ONLY what the lint output flags, in exactly the files it names, test or production; change no test'"'"'s assertions; make the linter pass, nothing else. Lint output:\n\n%s\n\nTask:\n%s' "$LINT_CMD" "$(tail -n 40 "$RUN_DIR/lint.log")" "$SPEC")" "$RUN_DIR/lint-repair.log" "Read Edit Write Bash" "$CHECK_REPAIR_ID" || LINT_REPAIR_RC=$?
        if [ "$LINT_REPAIR_RC" -ne 0 ] && [ "$LAST_STAGE_GROUP_REFUSED" -eq 0 ] && is_quota_failure "$RUN_DIR/lint-repair.log"; then llm_quota_hold "lint repair" "$RUN_DIR/lint-repair.log"; fi
        LINT_MUTATED=1
      fi
    fi
    # (3) after ANY repair-path mutation, re-run BOTH gates against the shipped tree. Either failing → Blocked.
    if [ "$LINT_MUTATED" -eq 1 ]; then
      CHECK_RC=0; run_checks || CHECK_RC=$?
      if is_env_failure "$CHECK_RC"; then env_hold "$CHECK_RC" " after the lint repair"; fi
      [ "$CHECK_RC" -eq 0 ] || fail_blocked "lint still failing after one repair (checks failed after the lint fix; log: $RUN_DIR/checks.log)"
      LINT_RC=0; run_lint "$LINT_CMD" || LINT_RC=$?
      if is_env_failure "$LINT_RC"; then lint_env_hold "$LINT_CMD" "$LINT_RC" " after the lint repair"; fi
      [ "$LINT_RC" -eq 0 ] || fail_blocked "lint still failing after one repair (log: $RUN_DIR/lint.log)"
    fi
  fi

  # ---- lens tier (issue #214): a manifest-declared, purely ADVISORY tier, run only AFTER check_cmd (and
  # lint_cmd, when declared) both pass. Absent LENS_CMD = off, byte-identical to today (no run, no
  # artifact, no comment). The lens exit code is READ BUT NEVER GATES — a non-zero exit (126/127 included)
  # becomes a one-line legible note appended to lens.md, and the run's terminal state is IDENTICAL to the
  # same run with a passing lens (no fail_blocked, no env hold, no repair). The artifact lands on the PR
  # trail as its own comment after the PR exists (below); it never enters PR_BODY or the review bundle.
  if [ -n "$LENS_CMD" ]; then
    LENS_RC=0; run_lens "$LENS_CMD" || LENS_RC=$?
    [ "$LENS_RC" -eq 0 ] || printf '\nlens did not run cleanly (exit %s)\n' "$LENS_RC" >> "$RUN_DIR/lens.md"
    log "lens ran (advisory, exit $LENS_RC) — never gating; artifact: $RUN_DIR/lens.md"
  fi
  mark_stage 03-check
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
REVIEW_SYS="You are the REVIEWER stage, independent of the implementer and tester. Review the STAGED changes (run: git diff --cached) against the ACCEPTANCE CRITERIA below — for correctness, maintainability, simplicity, and security. Tag each finding 'blocker' or 'nit'. Do NOT modify any files. End your reply with a final line that is exactly 'VERDICT: APPROVE' if there are zero blockers, or 'VERDICT: REQUEST_CHANGES' otherwise."

# ---- shadow review seat (issue #165): a non-gating SECOND verdict on the SAME review bundle every
# gating round produces. Dark unless BOTH YR_SHADOW_MODEL and YR_SHADOW_BASE_URL are set — then a pure
# no-op: no subprocess, no artifact, no comment (byte-identical to before this feature existed). Any
# failure here is best-effort logged and NEVER escalated — this must not touch the review gate below,
# terminal_approval, or the merge evaluator. Artifact naming mirrors the capture_stage_usage suffix
# pattern (:683-698 above): round 1 -> shadow-review.md, round 2 -> shadow-review-2.md.
SHADOW_ROUNDS=()
shadow_review_round(){
  [ -n "$YR_SHADOW_MODEL" ] && [ -n "$YR_SHADOW_BASE_URL" ] || return 0
  local out="$RUN_DIR/shadow-review.md" n=2
  while [ -e "$out" ]; do out="$RUN_DIR/shadow-review-$n.md"; n=$((n + 1)); done
  local rc=0
  run_stage "$REVIEW_SYS" "$(printf 'Review the staged changes against the acceptance criteria below. The full review bundle (diff with base/head SHAs, acceptance criteria, check output, resolved build/review models) is at: %s\n\n%s' "$BUNDLE" "$SPEC")" \
    "$out" "Read Bash" "$YR_SHADOW_MODEL" "$YR_SHADOW_BASE_URL" || rc=$?
  [ "$rc" -ne 0 ] && log "shadow review stage failed (exit $rc; log: $out) — non-gating, build proceeds unchanged"
  SHADOW_ROUNDS+=("$out")
  return 0
}

review_stage(){ "$GIT_BIN" -C "$WT" add -A
                local rc=0
                run_stage "$REVIEW_SYS" "$(printf 'Review the staged changes against the acceptance criteria below. The full review bundle (diff with base/head SHAs, acceptance criteria, check output, resolved build/review models) is at: %s\n\n%s' "$BUNDLE" "$SPEC")" "$RUN_DIR/review.md" "Read Bash" "$REVIEW_ID" || rc=$?
                if [ "$rc" -ne 0 ] && [ "$LAST_STAGE_GROUP_REFUSED" -eq 0 ] && is_quota_failure "$RUN_DIR/review.md"; then llm_quota_hold "review" "$RUN_DIR/review.md"; fi
                python3 "$SELF_DIR/review_bundle.py" record-verdict --bundle "$BUNDLE" --file "$RUN_DIR/review.md" \
                  || fail_blocked "review bundle record-verdict failed"
                shadow_review_round   # non-gating second opinion (issue #165) — never affects the verdict below
                # fail-closed: the LAST verdict line must be exactly "VERDICT: APPROVE" (only trailing whitespace
                # trimmed) — a hedge ("APPROVE" then "REQUEST_CHANGES"), trailing junk, or a mangled token does NOT pass.
                # Shared grammar: verdict_line() above.
                [ "$(verdict_line "$RUN_DIR/review.md")" = "VERDICT: APPROVE" ]; }
log "review: independent reviewer stage"
if stage_done 04-review; then
  log "resume: skipping review (04-review.done present)"
else
  if ! review_stage; then
    log "review requested changes — one repair attempt [$REVIEW_REPAIR_ID]"
    REVIEWREPAIR_RC=0
    run_stage "$IMPL_SYS" "$(printf 'A reviewer REQUESTED CHANGES. Fix the blocking findings (production code; only touch a test if the test itself is wrong). Reviewer notes:\n\n%s\n\nTask:\n%s' "$(cat "$RUN_DIR/review.md")" "$SPEC")" "$RUN_DIR/review-repair.log" "Read Edit Write Bash" "$REVIEW_REPAIR_ID" || REVIEWREPAIR_RC=$?
    if [ "$REVIEWREPAIR_RC" -ne 0 ] && [ "$LAST_STAGE_GROUP_REFUSED" -eq 0 ] && is_quota_failure "$RUN_DIR/review-repair.log"; then llm_quota_hold "review repair" "$RUN_DIR/review-repair.log"; fi
    # ---- persist the post-repair diff (issue #172) ----
    # Capture the repair's edits BEFORE the check re-run below, regardless of the repair's own exit
    # status (REVIEWREPAIR_RC) — a crashed repair's partial edits are exactly what salvage wants. The
    # repair stage itself stages nothing, so stage the worktree here first. This pins the artifact ahead
    # of BOTH blocked-after-repair paths (checks failing after repair; the second review round blocking),
    # so a teardown on either path still leaves the final tree recoverable from $RUN_DIR/final.patch —
    # unlike diff.patch above, which is the PRE-repair snapshot.
    "$GIT_BIN" -C "$WT" add -A
    "$GIT_BIN" -C "$WT" diff --cached > "$RUN_DIR/final.patch"
    run_checks  || fail_blocked "checks failing after review-repair (log: $RUN_DIR/checks.log)"
    review_stage || fail_blocked "reviewer still requests changes after one repair"
  fi
  mark_stage 04-review
fi

# ---- commit / push / open PR ----
# The commit itself is gated behind a stage marker (unlike push/create below): a resumed run reuses the
# SAME worktree with that commit already made, so re-running `add -A` + the empty-diff check would
# misread "already committed" as "no changes produced". Non-remote failures here (no changes produced,
# the commit itself failing) are UNCHANGED hard Blocks — only the remote writes below get retried.
if stage_done 05-commit; then
  log "resume: skipping commit (05-commit.done present)"
  PR_HEAD_SHA="$("$GIT_BIN" -C "$WT" rev-parse HEAD)"
else
  "$GIT_BIN" -C "$WT" add -A
  if "$GIT_BIN" -C "$WT" diff --cached --quiet; then fail_blocked "no changes produced"; fi
  "$GIT_BIN" -C "$WT" commit -q -m "$(printf '%s\n\nImplements #%s (dev-runner, build %s). Tests by the independent tester stage.' "$TITLE" "$ISSUE" "$BUILD_ID")"
  PR_HEAD_SHA="$("$GIT_BIN" -C "$WT" rev-parse HEAD)"   # the pushed PR head commit (for the shadow merge record)
  mark_stage 05-commit
fi

# PR-stage remote writes (issue #84): `git push` and `gh pr create` each get PR_STAGE_ATTEMPTS total
# attempts (first try + PR_STAGE_RETRIES) with exponential backoff between them before falling back to
# the SAME preserve+resume environmental hold as env_hold/llm_quota_hold above (never cleanup_wt) — a
# one-shot transient GitHub/network failure must never cost a full rebuild (factory#81). Defaults are
# conservative and documented in the file header; cumulative worst-case delay is bounded to minutes by
# PR_STAGE_BACKOFF_MAX, never unbounded.
PR_STAGE_RETRIES="${PR_STAGE_RETRIES:-3}"
PR_STAGE_BACKOFF_BASE="${PR_STAGE_BACKOFF_BASE:-5}"
PR_STAGE_BACKOFF_FACTOR="${PR_STAGE_BACKOFF_FACTOR:-2}"
PR_STAGE_BACKOFF_MAX="${PR_STAGE_BACKOFF_MAX:-60}"
PR_STAGE_ATTEMPTS=$((PR_STAGE_RETRIES + 1))

# retry_with_backoff: call the function named $1 up to PR_STAGE_ATTEMPTS times with exponential backoff
# between attempts (capped at PR_STAGE_BACKOFF_MAX/attempt). $1 must set RETRY_ERR (its captured stderr
# tail) and return non-zero on failure; on exhaustion RETRY_ERR holds the LAST attempt's tail. $2 = a
# label for the log lines (the retry count this way lands in the run's log output, per issue #84).
retry_with_backoff(){
  local fn="$1" label="$2" attempt=1 delay="$PR_STAGE_BACKOFF_BASE" rc=0
  while :; do
    rc=0; "$fn" || rc=$?
    if [ "$rc" -eq 0 ]; then
      [ "$attempt" -gt 1 ] && log "$label succeeded on attempt $attempt/$PR_STAGE_ATTEMPTS ($((attempt - 1)) retr$([ "$((attempt - 1))" -eq 1 ] && echo y || echo ies))"
      return 0
    fi
    if [ "$attempt" -ge "$PR_STAGE_ATTEMPTS" ]; then
      log "$label failed after $attempt attempt(s) — retries exhausted"
      return 1
    fi
    log "$label attempt $attempt/$PR_STAGE_ATTEMPTS failed (rc=$rc) — retrying in ${delay}s"
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * PR_STAGE_BACKOFF_FACTOR))
    [ "$delay" -gt "$PR_STAGE_BACKOFF_MAX" ] && delay="$PR_STAGE_BACKOFF_MAX"
  done
}

# push_attempt: re-push the SAME ref, NEVER force — a push that lands server-side but fails to
# acknowledge is naturally absorbed by the next identical attempt (idempotency note, issue #84).
push_attempt(){
  local errfile="$RUN_DIR/push-attempt.err" rc=0
  "$GIT_BIN" -C "$WT" push -q -u origin "$BRANCH" 2>"$errfile" || rc=$?
  RETRY_ERR="$(tail -n 20 "$errfile" 2>/dev/null || true)"
  return "$rc"
}

# find_open_pr: the URL of an existing OPEN PR for $BRANCH, or empty (a lookup failure reads as "none
# found", so the caller falls through to create — never a false reuse). Deliberately `pr list --head`,
# NOT `pr view` — the latter is also how shadow_ci polls the CI rollup and how --re-evaluate reads a PR,
# so reusing it here would tangle this existence check up with those unrelated reads.
find_open_pr(){
  local out
  out="$("$GH_BIN" pr list --repo "$REPO" --head "$BRANCH" --state open --json url 2>/dev/null)" || { printf ''; return 0; }
  printf '%s' "$out" | python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d=[]
print((d[0].get("url") or "") if isinstance(d, list) and d else "")' 2>/dev/null || true
}

# pr_create_attempt: idempotent creation — `gh pr create` is NOT naturally idempotent, so an existing
# open PR for the branch (e.g. one a prior attempt created server-side but failed to report) is REUSED,
# never re-created as a duplicate (issue #84).
pr_create_attempt(){
  local errfile="$RUN_DIR/pr-create-attempt.err" rc=0 existing
  existing="$(find_open_pr)"
  if [ -n "$existing" ]; then PR_URL="$existing"; RETRY_ERR=""; return 0; fi
  PR_URL="$("$GH_BIN" pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$BRANCH" --title "$TITLE" --body "$PR_BODY" 2>"$errfile")" || rc=$?
  RETRY_ERR="$(tail -n 20 "$errfile" 2>/dev/null || true)"
  return "$rc"
}

# pr_stage_hold: retries exhausted on a PR-stage remote write -> the SAME preserve+resume core the check
# gate and quota holds use (env_hold_record) — hold marker + resume manifest written, Reason=Blocked, a
# comment carrying an ENVIRONMENTAL marker and the final attempt's captured stderr tail, and deliberately
# no cleanup_wt so a relaunch resumes at this same PR stage (issue #84).
pr_stage_hold(){   # $1 = which write ("push"/"pr create"), $2 = final attempt's captured stderr tail
  local what="$1" errtail="${2:-<no stderr captured>}"
  local msg="the $what step of the PR stage failed after $PR_STAGE_ATTEMPTS attempts with exponential backoff — an ENVIRONMENTAL failure (transient GitHub/network), not a code failure. Wait for it to clear, then set Ready again — do NOT send it to LLM repair. Final attempt's stderr: $errtail"
  env_hold_record "$msg" "$(printf 'dev-runner: **Environmental hold (PR stage)** — the %s step failed after %s attempts with exponential backoff (ENVIRONMENTAL: transient GitHub/network, not a code failure). The worktree (%s) and completed-stage checkpoints are preserved; a relaunch resumes at the PR stage (green stages are not re-run).\n\nFinal attempt'"'"'s stderr:\n```\n%s\n```' "$what" "$PR_STAGE_ATTEMPTS" "$WT" "$errtail")"
}

retry_with_backoff push_attempt "push" || pr_stage_hold "push" "$RETRY_ERR"
PR_BODY="$(printf 'Closes #%s\n\nProduced by **dev-runner** (build: %s, review: %s): implementer + independent **tester** + independent **reviewer** stages — checks green, review approved. Reviewer verdict attached below.' "$ISSUE" "$BUILD_ID" "$REVIEW_ID")"
retry_with_backoff pr_create_attempt "pr create" || pr_stage_hold "pr create" "$RETRY_ERR"
"$GH_BIN" pr comment "$PR_URL" --body-file "$RUN_DIR/review.md" >/dev/null 2>&1 || true   # attach reviewer verdict

# ---- shadow review comments (issue #165): one inert comment per shadow round recorded above. Never
# posted at all when the feature is dark (SHADOW_ROUNDS stays empty). The transcript is blockquoted so no
# line can match the line-anchored gating token (`^VERDICT:`) — the first line names the extracted verdict
# (same last-line exact-match rule as verdict_line()) under a marker that is never the gating grammar.
shadow_verdict_token(){   # $1 = a shadow-review file -> its bare verdict token, or NONE if no VERDICT: line landed
  local line; line="$(verdict_line "$1")"
  [ -n "$line" ] && printf '%s' "${line#VERDICT: }" || printf 'NONE'
}
for shadow_file in "${SHADOW_ROUNDS[@]}"; do
  shadow_comment="${shadow_file%.md}-comment.md"
  { printf 'YR-SHADOW-REVIEW: %s\n\n' "$(shadow_verdict_token "$shadow_file")"
    sed 's/^/> /' "$shadow_file"; } > "$shadow_comment"
  "$GH_BIN" pr comment "$PR_URL" --body-file "$shadow_comment" >/dev/null 2>&1 || true
done

# ---- verdict-diff records (issue #166): pairs each gating round (tools/review_bundle.py's `rounds`
# list — the only per-round store, since review.md itself is overwritten each round) with its OWN
# shadow round from SHADOW_ROUNDS above, and lands one inert `YR-VERDICT-DIFF` PR comment + one
# yr-verdict-diff/1 record file per pair. A round with no shadow record is skipped by
# tools/verdict_diff.py itself — never a synthesized disagreement. Best-effort like the shadow seat
# above: never touches the gate, terminal_approval, or the merge evaluator, and never blocks the
# build. Merge outcome is NOT written here (slice F backfills it at aggregation time). A complete
# no-op when the shadow seat is dark (SHADOW_ROUNDS empty) — no subprocess, no artifact, no comment.
if [ "${#SHADOW_ROUNDS[@]}" -gt 0 ]; then
  while IFS= read -r vdiff_comment; do
    [ -n "$vdiff_comment" ] || continue
    "$GH_BIN" pr comment "$PR_URL" --body-file "$vdiff_comment" >/dev/null 2>&1 || true
  done < <(python3 "$SELF_DIR/verdict_diff.py" run --run-dir "$RUN_DIR" --bundle "$BUNDLE" 2>/dev/null || true)
fi

# staleness warning (issue #58): additive alongside the reviewer verdict + usage summary, and deliberately
# clear of every parsed comment grammar (no `YR-` marker line, no `YR-MERGE` anywhere) — visibility only,
# never a gate.
if [ -n "$STALE_COUNT" ] && [ "$STALE_COUNT" -gt 0 ]; then
  "$GH_BIN" pr comment "$PR_URL" --repo "$REPO" --body "dev-runner: **staleness warning** — the factory deployment that built this PR was $STALE_COUNT commit(s) behind its own origin/main at build time. Redeploy it to pick up already-shipped capability." >/dev/null 2>&1 \
    || log "warn: could not post the staleness-warning comment (non-fatal, PR already open)"
fi

# ---- usage summary: aggregate the per-stage usage artifacts + post one PR comment (issue #48) --------
# Always produced, even with zero per-stage artifacts (a degraded capture, e.g. every stage ran under
# an explicit CLAUDE_OUTPUT_FORMAT override) — the aggregate + comment just say so, per
# tools/stage_usage.py's render_summary_comment. Never touches the merge-shadow marker grammar
# (tools/merge_shadow.py) or its YR-/YR-MERGE-prefixed records.
USAGE_SUMMARY_JSON="$RUN_DIR/usage-summary.json"; USAGE_SUMMARY_COMMENT="$RUN_DIR/usage-summary.md"
if python3 "$SELF_DIR/stage_usage.py" summarize --run-dir "$RUN_DIR" \
     --out-json "$USAGE_SUMMARY_JSON" --out-comment "$USAGE_SUMMARY_COMMENT" 2>/dev/null; then
  USAGE_STAGE_COUNT="$(python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
print(len(d.get("stages") or []))' "$USAGE_SUMMARY_JSON" 2>/dev/null || echo 0)"
  if [ "${USAGE_STAGE_COUNT:-0}" -eq 0 ]; then
    log "WARNING: zero per-stage usage artifacts were recorded for this run — usage capture degraded (check CLAUDE_OUTPUT_FORMAT and the stage logs under $RUN_DIR)"
  fi
  "$GH_BIN" pr comment "$PR_URL" --repo "$REPO" --body-file "$USAGE_SUMMARY_COMMENT" >/dev/null 2>&1 \
    || log "warn: could not post the usage-summary comment (non-fatal, PR already open)"
else
  log "warn: usage summary aggregation failed (non-fatal, PR already open)"
fi

# ---- lens advisory comment (issue #214): the manifest-declared lens tier's artifact lands on the PR trail
# as its OWN comment via the usage-summary --body-file pattern, first line `YR-LENS (advisory)` — purely
# advisory, never a gate, and deliberately clear of PR_BODY and the review bundle (the reviewer consumes
# the bundle before any PR exists). Posted exactly ONCE, only when lens.md is non-empty and the PR exists;
# an empty (or absent, LENS_CMD off) artifact posts nothing, and a Blocked run (no PR) leaves lens.md
# unposted in the run dir — correct behavior. Best-effort like the usage summary: a post failure logs, never
# blocks. No `YR-MERGE`/`VERDICT:` grammar, so it can never be mistaken for a gating record.
if [ -s "$RUN_DIR/lens.md" ]; then
  LENS_COMMENT="$RUN_DIR/lens-comment.md"
  { printf 'YR-LENS (advisory)\n\n'; cat "$RUN_DIR/lens.md"; } > "$LENS_COMMENT"
  "$GH_BIN" pr comment "$PR_URL" --repo "$REPO" --body-file "$LENS_COMMENT" >/dev/null 2>&1 \
    || log "warn: could not post the lens advisory comment (non-fatal, PR already open)"
fi

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
# The one exception (issue #240): once freshness remediation has force-pushed the branch onto a new base
# (rebase_onto_tip, below), the PR's remote head no longer matches any local run's recorded base commit —
# a LATER environmental failure in that same remediation can no longer be silently resumed, because
# --re-evaluate's record-less base-commit match (issue #239) would never locate this run again. That one
# case posts a fact-stating YR-MERGE: BLOCKED — unrecoverable record instead of a silent exit, naming the
# rewrite and routing to a manual close+rebuild — never a machinery error, never a streak reset.
# shadow_ci / shadow_freshness / shadow_terminal_approval / shadow_rank_gate / read_auto_merge /
# emit_and_post / compute_shadow_complete / do_squash_merge — conditions (1)-(4), auto_merge, shadow
# completion, the record post, and the merge call — are defined earlier (hoisted right after BASE_REPO
# resolution, issues #70/#239) so --re-evaluate can reuse them without a worktree.
# The host sentinel (kill switch): a FILE in the dispatch home, read LIVE at decision time (a file, not an
# inherited env var — a spawned runner carries its spawn-time environment; the file is global + git-free).
PR_NUMBER="${PR_URL##*/}"                                # the current PR number (excluded from the window)

# freshness remediation: main moved, so rebase the branch onto the tip and RE-ESTABLISH green (re-run the
# check gate + re-wait CI) before merging — the reviewed diff is unchanged so the verdict stands. A stale
# green SHALL NOT merge. Returns 0 (remediated, ready to merge) / 1 (block: conflict or cannot re-green) /
# 2 (environmental). Updates PR_HEAD_SHA/BASE_SHA/MAIN_TIP to the rebased state. Sets REBASE_REWROTE_REMOTE
# (issue #240) the moment the force-push lands — the caller's marker for "an environmental failure past
# this point can no longer be silently resumed" (below), since the remote head's parent is no longer the
# base commit any local run recorded.
rebase_onto_tip(){
  REBASE_REWROTE_REMOTE=0
  "$GIT_BIN" -C "$WT" fetch -q origin "$BASE_BRANCH" 2>/dev/null || return 2
  if ! "$GIT_BIN" -C "$WT" rebase "origin/$BASE_BRANCH" >/dev/null 2>&1; then
    "$GIT_BIN" -C "$WT" rebase --abort >/dev/null 2>&1 || true
    return 1                                   # rebase conflict -> block for the human
  fi
  "$GIT_BIN" -C "$WT" push -q --force-with-lease origin "$BRANCH" 2>/dev/null || return 2
  REBASE_REWROTE_REMOTE=1                       # the remote head is now rewritten -- see caller
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

# do_squash_merge is defined earlier (hoisted alongside compute_shadow_complete, issue #239).

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

# The unrecoverable-rewrite record (issue #240): once rebase_onto_tip has force-pushed the branch onto a
# new base (REBASE_REWROTE_REMOTE=1), NO later environmental failure in this run — whether inside
# rebase_onto_tip's own re-green wait or in the squash-merge call further down — can be silently resumed:
# --re-evaluate's record-less base-commit match (issue #239) can never locate this run again, since the
# recorded base_sha no longer matches head^ on the PR. Posts a fact-stating BLOCKED record naming the
# rewrite and routing to a manual rebuild. Returns 0 (record posted) or 2 (posting itself failed environmentally).
unrecoverable_remote_rewrite_block(){
  armed_block unrecoverable "the freshness-remediation rebase already force-pushed $PR_URL onto a new base before a later step failed environmentally — the PR's remote head no longer matches any local build's recorded base commit, so no named recovery lane (re-evaluation's base-commit match, the already-torn-down environmental-hold resume, or a plain re-Ready re-dispatch, which would collide with the existing branch) can locate or resume this run. Close this PR, delete branch $BRANCH, and set #$ISSUE back to Ready to rebuild from scratch."
}

# The terminal decision. Returns 2 on an environmental failure (resumable — no record, no merge, no
# streak reset, no Block) EXCEPT the one case where a prior environmental failure is no longer honestly
# resumable (issue #240: an env failure after freshness remediation already rewrote the PR's remote head,
# whether that failure surfaces inside the remediation itself or later at the squash-merge call) — that
# one posts a fact-stating BLOCKED record instead (unrecoverable_remote_rewrite_block, above). Sets
# MERGED=1 on a factory squash-merge; sets ARMED_BLOCKED=1 on an armed block (the unrecoverable case included).
terminal_step(){
  CI_RESULT=fail; CI_STATE=unknown; FRESH_RESULT=fail; APPROVE_RESULT=fail; RANK_RESULT=fail; MAIN_TIP=""
  SENTINEL_STATE=ok; SHADOW_DONE=false; SHADOW_PROGRESS=""; MERGE_COMMIT=""; REBASE_REWROTE_REMOTE=0
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
      --note "armed, shadow-incomplete $SHADOW_PROGRESS" || return 2
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
    if [ "$rc" -eq 2 ]; then
      if [ "${REBASE_REWROTE_REMOTE:-0}" = 1 ]; then
        unrecoverable_remote_rewrite_block || return 2
        return 0
      fi
      return 2
    fi
    if [ "$rc" -ne 0 ]; then
      armed_block freshness "main advanced and the rebase onto ${MAIN_TIP:-the tip} could not be re-established green — resolve by hand" || return 2
      return 0
    fi
  fi

  # Full armed pass: squash-merge into main, post the durable YR-MERGE: MERGED, let native close->Done finish.
  # A merge-API failure here is normally environmental/resumable (no reset) -- UNLESS freshness remediation
  # already force-pushed this branch onto a new base above, in which case the same unrecoverable-rewrite
  # record applies (issue #240): the remote head no longer matches any local run's recorded base commit.
  if ! do_squash_merge; then
    if [ "${REBASE_REWROTE_REMOTE:-0}" = 1 ]; then
      unrecoverable_remote_rewrite_block || return 2
      return 0
    fi
    return 2
  fi
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

# ledger row (issue #206): the success terminus — one row, deriving the outcome from the merge decision.
# The armed-BLOCKED case is pinned as type in-review / decision BLOCKED (armed_block itself never
# appends — this is the one append for that path, at the shared terminus). An armed_block's own
# environmental failure inside terminal_step (MERGE_MARKER never set) falls through to the same
# in-review/no-decision default as an ungoverned (non-armed) build.
LEDGER_OUTCOME_TYPE="in-review"; LEDGER_OUTCOME_DECISION=""
if [ "$MERGED" -eq 1 ]; then
  LEDGER_OUTCOME_TYPE="merged"; LEDGER_OUTCOME_DECISION="MERGED"
elif [ "$ARMED_BLOCKED" -eq 1 ]; then
  LEDGER_OUTCOME_TYPE="in-review"; LEDGER_OUTCOME_DECISION="BLOCKED"
else
  case "$MERGE_MARKER" in
    *WOULD-MERGE*) LEDGER_OUTCOME_TYPE="shadow-would-merge"; LEDGER_OUTCOME_DECISION="WOULD-MERGE";;
    *WOULD-BLOCK*) LEDGER_OUTCOME_TYPE="shadow-would-block"; LEDGER_OUTCOME_DECISION="WOULD-BLOCK";;
  esac
fi
ledger_append "$LEDGER_OUTCOME_TYPE" "$LEDGER_OUTCOME_DECISION"

cleanup_wt

# ---- transcript retention (issue #205): the runner-owned age/size cap on archived transcripts, wired
# into this success terminus only — a failure streak simply defers pruning to the next successful run
# (the cap sizing tolerates it). Fail-soft: never affects this run's outcome or its PR_URL output.
PRUNE_OUT="$(python3 "$SELF_DIR/ledger.py" prune --runs-dir "$DEV_RUNNER_HOME/runs" 2>&1)" || true
log "transcript retention prune: $PRUNE_OUT"

echo "$PR_URL"
