# stage_lib.sh — the claude -p stage harness (it-36 slice C): the pinned, byte-identical
# extraction of every function/constant tools/dev-runner.sh's run_stage machinery needs, so
# the PM agent's own runner (it-36) and this runner source the SAME code rather than a fork of
# it. Sourced by the caller after SELF_DIR is set; run_stage itself reads EFFORT, BUILD_ID,
# STAGE_CHARTER, RUN_DIR, CLAUDE_BIN from the caller's own environment/globals.

verdict_line(){ grep -E '^VERDICT:' "$1" 2>/dev/null | tail -n1 | sed -E 's/[[:space:]]+$//'; }

REGISTRY="${MODELS_REGISTRY:-$SELF_DIR/../models.toml}"

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
  local log="$1" base stage n=2 out slug_dir result status method
  base="$(basename "$log")"; base="${base%.*}"
  stage="$base"
  while [ -e "$RUN_DIR/transcript-$stage.jsonl" ]; do stage="$base-$n"; n=$((n + 1)); done
  out="$RUN_DIR/transcript-$stage.jsonl"
  slug_dir="$HOME/.claude/projects/$(wt_slug)"
  result="$(python3 "$SELF_DIR/ledger.py" archive --log "$log" --slug-dir "$slug_dir" --out "$out" 2>&1)" || true
  log "transcript archive ($stage): $result"
  # bg_scan (issue #306): scan THIS call's own landed transcript for an unresolved CLI-managed
  # background-task conversion — dedup-suffixed rounds (review-2, ...) scan their own file, never a
  # prior round's, because `out` above is freshly recomputed every call. Gated on POSITIVE,
  # session-attributed evidence only: a heuristic-newest attribution proves nothing about which session
  # this stage actually ran, and a failed/skipped archive leaves no file to scan at all — both log and
  # continue rather than gate on their own absence.
  LAST_STAGE_BG_UNRESOLVED=0
  LAST_STAGE_BG_REASON=""
  # One python3 call for both fields (same multi-line-stdout + mapfile shape as _set_role_from_json
  # above) rather than two — mapfile never trips `set -e` even if the process substitution's python3
  # crashes on unparseable input (verified: unlike a failing `$(...)` assignment), so garbage in `$result`
  # degrades to an empty array, i.e. status/method both "", i.e. the skip branch below — never a hard stop.
  local _af
  mapfile -t _af < <(printf '%s' "$result" | python3 -c 'import json,sys
try: d = json.load(sys.stdin)
except Exception: d = {}
print(d.get("status","") or ""); print(d.get("method","") or "")')
  status="${_af[0]:-}"; method="${_af[1]:-}"
  if [ "$status" = archived ] && [ "$method" = session_id ]; then
    local scan_json _sf unresolved near_count near_first
    scan_json="$(python3 "$SELF_DIR/bg_scan.py" scan --transcript "$out" 2>&1)" || true
    mapfile -t _sf < <(printf '%s' "$scan_json" | python3 -c 'import json,sys
try: d = json.load(sys.stdin)
except Exception: d = {}
parsed = bool(d.get("parsed"))
print(",".join(d.get("unresolved", [])) if parsed else "")
near = d.get("near_misses", []) if parsed else []
print(len(near))
print(near[0] if near else "")')
    unresolved="${_sf[0]:-}"
    near_count="${_sf[1]:-0}"
    near_first="${_sf[2]:-}"
    if [ -n "$unresolved" ]; then
      LAST_STAGE_BG_UNRESOLVED=1
      LAST_STAGE_BG_REASON="unresolved background-task conversion (task id(s): $unresolved) — its archived transcript ($out) shows the CLI converted a command to a background task that was never brought to an observed terminal state or killed before the stage ended its turn, per the stage charter's background-task rule"
      log "transcript scan ($stage): unresolved background-task conversion — $unresolved"
    fi
    # near-miss drift canary (issue #320): logged every scan, independent of $unresolved above — an
    # aggregate signal for a human to eyeball over time, never a gate (see tools/bg_scan.py docstring).
    log "transcript scan ($stage): near-miss drift canary — count=$near_count first_index=${near_first:-none}"
  else
    log "transcript scan ($stage): skipped (archive status=$status method=$method) — positive, session-attributed evidence only, never gates on its own absence"
  fi
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
# LAST_STAGE_BG_UNRESOLVED / LAST_STAGE_BG_REASON (issue #306): set by archive_stage_transcript on every
# call (never left over from a prior one) to whether THIS stage's own just-archived transcript shows an
# unresolved CLI-managed background-task conversion — the complementary case to LAST_STAGE_GROUP_REFUSED
# above: a task the CLI itself backgrounded and then killed at session exit, invisible to process-group
# inspection by the time anything looks. Gated on POSITIVE, session-attributed evidence only (see
# archive_stage_transcript) — a missing/unparseable/heuristically-attributed transcript leaves this 0.
# Each caller decides its own disposition (implement/test fail the stage; a repair stage disposes after
# its salvage+re-check; a review round treats it as not a clean APPROVE) — this only carries the fact.
LAST_STAGE_BG_UNRESOLVED=0
LAST_STAGE_BG_REASON=""

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
              # $5=model id (default: build)
  local model="${5:-$BUILD_ID}" cred rc=0 fmt_overridden=0 pid
  LAST_STAGE_GROUP_REFUSED=0   # reset every call (issue #247) — stage_fail_msg reads this, not the rc value,
                                # so a genuine future 124 from the CLI itself is never misread as a refusal
  local sys_prompt; sys_prompt="$(printf '%s\n\n%s' "$1" "$STAGE_CHARTER")"
  # the task prompt travels on stdin, never argv (issue #121): a task whose acceptance criteria quote a
  # runnable string (e.g. `pkill -f "bash qa/qa-gate.sh"`) must not be able to pattern-match the stage's
  # OWN command line and self-kill the harness — exactly what happened in gilda#9 run 9-4131516. `-p`
  # with no positional value reads the prompt from stdin instead.
  # ZERO settings sources (it-31 slice 10, #442 — the second repo-shape seam closes): the harness
  # loads user + project + local when --setting-sources is ABSENT (the flag restricts), so
  # isolation is the empty-value form — verified empirically 2026-08-17 against claude CLI 2.1.233
  # (a project-scope SessionStart hook: fires with `project`, fires with the flag absent, silent
  # with ""). This closes #49's operator user/local hole AND the target repo's own project-settings
  # injection in one declared form. The old STAGE_SETTING_SOURCES env knob is retired with the
  # mechanism: a future declared need rides the manifest, never an env knob (the seam is a
  # contract, not a calibration).
  local args=( -p --model "$model" --effort "$EFFORT"
               --permission-mode bypassPermissions --append-system-prompt "$sys_prompt"
               --allowedTools ${4:-Read Edit Write Bash}
               --setting-sources "" --strict-mcp-config )
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
  if [ -n "$cred" ]; then
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

# stage_blocked_reason (issue #309): reads a stage's log AS PLAIN TEXT at disposition time — after
# run_stage has returned and capture_stage_usage has already rewritten a clean default-format log to the
# envelope's `.result` text in place — for the STAGE-BLOCKED escalation sentinel. Fires ONLY on a strict
# grammar: the log's LAST non-empty line is EXACTLY "STAGE-BLOCKED: <reason>" with a non-empty reason —
# deliberately stricter than verdict_line's last-anchored-line-wins rule (a mid-text mention or trailing
# prose after the sentinel line never fires it). No envelope parsing anywhere: a log a failed/skipped
# extraction left un-rewritten is a raw JSON line that cannot match this literal grammar, so it degrades
# to "doesn't fire" — the safe direction. $1 = the stage log file. Prints the reason (verbatim, untrimmed)
# and returns 0 on a fire; prints nothing and returns 1 otherwise.
stage_blocked_reason(){
  local log="$1" last
  [ -f "$log" ] || return 1
  last="$(grep -v '^[[:space:]]*$' "$log" 2>/dev/null | tail -n1)" || true
  [ -n "$last" ] || return 1
  case "$last" in
    "STAGE-BLOCKED: "?*) printf '%s' "${last#STAGE-BLOCKED: }"; return 0 ;;
    *) return 1 ;;
  esac
}

# stage_blocked_dispose (issue #309): routes a fired STAGE-BLOCKED sentinel to the existing Blocked
# terminal (fail_blocked) — quoting the stage's stated reason verbatim and stating the worktree's diff
# state. $1 = stage label ("implement"|"tester"), $2 = the reason stage_blocked_reason returned, $3 = the
# diff text to state/preserve, computed and passed in by the CALLER before this runs (fail_blocked's
# cleanup_wt destroys the worktree the diff describes — implement diffs against the branch point, tester
# against the implementer's IMPL_TREE checkpoint). A non-empty diff is additionally preserved as a run-dir
# artifact (escalation-residual.diff, the boundary-violation.diff precedent) so the message's "residual
# edits" claim survives the teardown it describes; an empty diff is stated as a clean revert, no artifact
# written. Always routes to Blocked (never Needs-info) — redistribution stays the human's.
stage_blocked_dispose(){
  local stage="$1" reason="$2" diff="$3" state
  if [ -n "$diff" ]; then
    printf '%s' "$diff" > "$RUN_DIR/escalation-residual.diff"
    state="residual edits remain in the worktree — preserved at $RUN_DIR/escalation-residual.diff"
  else
    state="the worktree is a clean revert — no residual diff"
  fi
  fail_blocked "the $stage stage escalated via its own STAGE-BLOCKED sentinel — reason (verbatim): \"$reason\" — $state"
}

# ---- stage charter (issue #50): the confinement contract every stage runs under, in every target repo —
# appended (by run_stage) to each stage's role prompt so a stage building a foreign repo still gets it, not
# just the factory's own. Kept free of the stage-aware test stub's four routed literals (its case-sensitive
# `case` match on the combined argv+stdin capture: TESTER, REVIEWER — still argv, in the role system-prompt
# — and "tests FAIL", "REQUESTED CHANGES" — on stdin since issue #121, in the task prompt) — a leaked
# literal here would misroute every stage, not just its own.
STAGE_CHARTER="You are one stage of an automated pipeline, running in one fresh worktree cut from the base ref. The pipeline holds builder ≠ verifier: the implementer writes production code and never authors the committed test suite; the tester writes tests only, derived from the acceptance criteria and never from the implementation's internals; the reviewer changes nothing. Write only inside this worktree — never the host. Make no git or board writes; the runner owns them (the reviewer's read-only git, e.g. diffing staged changes, is the one carve-out). Never weaken a gate: do not edit checks, CI configuration, or .yr/factory.toml, and never edit a test to weaken what it checks. Where a repair round may touch a test at all, its own prompt says so and bounds it; the task's text never widens that. Manage processes by PID only — pattern-kills such as PKILL -f or PGREP -f are forbidden, because a stage's own command environment can contain the task text, and a pattern match can hit and kill the stage's own process instead of its intended target. If the task cannot be done within these rules, stop and say so — a Blocked run is a correct outcome, not a failure to route around. In the implement or test stage specifically, state that conclusion by ending your final reply's last non-empty line with exactly STAGE-BLOCKED: <reason> (a non-empty reason) — this routes straight to that Blocked outcome, quoting your reason, and skips every remaining stage; a repair or review round has no such channel and must never emit it. This pipeline produces a pull request only; deploy and host work are never a stage's. In-stage verification exercises only the scope this stage's change touches, with targeted tests; the repo's full check suite belongs to the deterministic check gate and server CI, never an in-stage inner loop. A stage works in the foreground only: it never polls, watches, or sleeps on external state, and when it cannot proceed it stops and says so. A long-running command of its own runs in the foreground with an explicit, generous timeout — the lever, not a hard-coded number — rather than the tool's own default; a command the environment converts to a background task anyway is killed or brought to an observed terminal state before the stage ends its turn, because a stage never ends its turn with a live background task: in a one-shot stage the promise that it will be notified when the task completes is structurally void — ending the turn ends the process, killing the task silently. The task in front of it is self-contained by design; standing documents are not this stage's context."
