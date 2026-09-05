#!/usr/bin/env bash
# tools/deploy.sh — the scripted attended act (it-33 slice 6, epic #455, issue #462).
#
# Run BY A HUMAN (or an attended agent under explicit human instruction) as `yr-factory` on the
# build host yr-host. There is no automatic trigger — deploy is attended, always. Pulls the
# factory's own checkout to green `main`, restarts `dispatch` IFF the pull touched a file in the
# dispatcher's own import closure, runs the runbook's post-deploy checks, and leaves exactly ONE
# machine-readable `YR-DEPLOY` record on the deploy trail (yellow-robots/factory#464) — only once
# a deploy act actually completes; a refused or failed act posts nothing.
#
# Refuses (before touching anything) while a build or a sweep is in flight — the same lock files
# `tools/epic_gate.py`'s `_default_build_lock_held` reads (a repo's own build lock
# `dispatch-<owner>--<name>.lock`, a `capslot-<i>.lock` capacity slot, the sweep lock), plus a
# live `runs/<issue>-<pid>` directory under $DEV_RUNNER_HOME (tools/dev-runner.sh's own run-dir
# shape). Never `ps`: only the lock files the dispatcher itself writes (a non-blocking `flock`
# test) and a `kill -0` liveness probe on a run dir's own pid.
#
# Every external act is overridable, so the whole thing is testable with no live host and no
# network: GIT_BIN, SYSTEMCTL_BIN, GH_BIN, PY_BIN, VENV_PYTHON, DEPLOY_ROOT, DEV_RUNNER_HOME,
# DISPATCH_LOCK, SWEEP_LOCK, DEPLOY_REPO, DEPLOY_ISSUE (the same seam tools/dev-runner.sh uses for
# CLAUDE_BIN/GH_BIN/GIT_BIN). `--dry-run` runs the quiescence probe and reports the restart
# decision it WOULD make (previewed against origin/main's tip via a bounded, read-only
# `git fetch` — never touching HEAD or the working tree) without pulling, restarting, or posting.
# `--print-import-closure` is a diagnostic-only hook: prints the dispatcher's import closure and
# exits, no probe, no `--who` required — the seam the test suite pins the closure through.
#
# Exit codes: 0 deployed, 1 refused (quiescence or a post-deploy check failure),
# 2 usage, 3 environmental (git pull / systemctl / gh failure).
set -euo pipefail

GIT_BIN="${GIT_BIN:-git}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
GH_BIN="${GH_BIN:-gh}"
PY_BIN="${PY_BIN:-python3}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${DEPLOY_ROOT:-$(cd "$SELF_DIR/.." && pwd)}"
VENV_PYTHON="${VENV_PYTHON:-$DEPLOY_ROOT/.venv/bin/python}"

DEV_RUNNER_HOME="${DEV_RUNNER_HOME:-$HOME/.cache/dev-runner}"
DISPATCH_LOCK="${DISPATCH_LOCK:-$DEV_RUNNER_HOME/dispatch.lock}"
SWEEP_LOCK="${SWEEP_LOCK:-$DEV_RUNNER_HOME/epic-sweep.lock}"

DEPLOY_REPO="${DEPLOY_REPO:-yellow-robots/factory}"
DEPLOY_ISSUE="${DEPLOY_ISSUE:-464}"

log()    { echo "deploy: $*" >&2; }
usage()  { echo "usage: deploy.sh --who <human|attended-agent> [--dry-run] [--repo owner/name] [--issue N]" >&2; exit 2; }
refuse() { echo "deploy: REFUSED: $*" >&2; exit 1; }
envfail(){ echo "deploy: ENVIRONMENTAL: $*" >&2; exit 3; }

# ── the dispatcher's import closure: tools/dispatch.py plus every sibling tools/*.py module it
#    imports, transitively — a small static AST walk (never an actual `import`, so no module-level
#    side effect runs). One repo-relative path per line, dispatch.py first. ---------------------
_import_closure() {
  "$PY_BIN" - "$DEPLOY_ROOT" <<'PYEOF'
import ast, sys, pathlib

root = pathlib.Path(sys.argv[1]) / "tools"
seen = []


def walk(name):
    if name in seen:
        return
    path = root / f"{name}.py"
    if not path.exists():
        return
    seen.append(name)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                walk(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                walk(node.module.split(".")[0])


walk("dispatch")
for name in seen:
    print(f"tools/{name}.py")
PYEOF
}

# a diagnostic-only early exit — no probe, no --who — the seam tests pin the closure through.
if [ "${1:-}" = "--print-import-closure" ]; then
  _import_closure
  exit 0
fi

# ── quiescence probe: refuse, naming the held lock or the live run, before touching anything ────
_lock_held() {
  # non-blocking flock test on an EXISTING lock file only — a missing lock file is never held, and
  # probing a nonexistent path would otherwise create an empty one as a side effect of the test.
  local lock="$1"
  [ -e "$lock" ] || return 1
  flock -n "$lock" -c true >/dev/null 2>&1 && return 1   # acquired it -> not held
  return 0                                                 # could not acquire -> held
}

_live_run_dirs() {
  # `runs/<issue>-<pid>` (tools/dev-runner.sh's own RUN_DIR shape): liveness is `kill -0` on the
  # trailing pid, never `ps` parsing.
  local runs="$DEV_RUNNER_HOME/runs"
  [ -d "$runs" ] || return 0
  local d base issue_part pid_part
  for d in "$runs"/*/; do
    [ -d "$d" ] || continue
    base="$(basename "${d%/}")"
    issue_part="${base%-*}"
    pid_part="${base##*-}"
    case "$issue_part" in ''|*[!0-9]*) continue ;; esac
    case "$pid_part" in ''|*[!0-9]*) continue ;; esac
    if kill -0 "$pid_part" 2>/dev/null; then
      echo "${d%/} (pid $pid_part)"
    fi
  done
}

probe_quiescence() {
  # the lock HOME is dirname(DISPATCH_LOCK) — dispatch.py's own derivation (repo_lock_path /
  # slot_lock_path both live beside DISPATCH_LOCK, never assumed to equal DEV_RUNNER_HOME
  # directly, even though that IS today's default) — so an operator override of DISPATCH_LOCK
  # alone (matching dispatch.py's own env contract) relocates the probe too.
  local lock_home; lock_home="$(dirname "$DISPATCH_LOCK")"
  local lock
  for lock in "$lock_home"/dispatch-*.lock; do
    [ -e "$lock" ] || continue
    _lock_held "$lock" && refuse "a build lock is held: $lock"
  done
  for lock in "$lock_home"/capslot-*.lock; do
    [ -e "$lock" ] || continue
    _lock_held "$lock" && refuse "a capacity-slot lock is held: $lock"
  done
  _lock_held "$SWEEP_LOCK" && refuse "the sweep lock is held: $SWEEP_LOCK"
  local live msg=""
  live="$(_live_run_dirs)"
  if [ -n "$live" ]; then
    while IFS= read -r line; do
      [ -n "$msg" ] && msg="$msg; $line" || msg="$line"
    done <<<"$live"
    refuse "a build run is live: $msg"
  fi
}

# ── args ──────────────────────────────────────────────────────────────────────────────────────
WHO=""; DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --who)      [ $# -ge 2 ] || { echo "deploy: --who requires a value" >&2; usage; }
                WHO="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --repo)     [ $# -ge 2 ] || { echo "deploy: --repo requires a value" >&2; usage; }
                DEPLOY_REPO="$2"; shift 2 ;;
    --issue)    [ $# -ge 2 ] || { echo "deploy: --issue requires a value" >&2; usage; }
                DEPLOY_ISSUE="$2"; shift 2 ;;
    -h|--help)  usage ;;
    -*)         echo "deploy: unknown flag: $1" >&2; usage ;;
    *)          echo "deploy: unexpected arg: $1" >&2; usage ;;
  esac
done
case "$WHO" in
  human|attended-agent) ;;
  *) echo "deploy: --who must be 'human' or 'attended-agent' (an actor CLASS, never a login) — got: '${WHO:-<none>}'" >&2
     usage ;;
esac

log "probing quiescence at $DEV_RUNNER_HOME"
probe_quiescence
log "quiescence: clean"

OLD_HEAD="$("$GIT_BIN" -C "$DEPLOY_ROOT" rev-parse HEAD)" \
  || envfail "could not read the current HEAD at $DEPLOY_ROOT"

if [ "$DRY_RUN" -eq 1 ]; then
  "$GIT_BIN" -C "$DEPLOY_ROOT" fetch --quiet origin main \
    || envfail "dry-run: git fetch origin main failed"
  NEW_HEAD="$("$GIT_BIN" -C "$DEPLOY_ROOT" rev-parse origin/main)" \
    || envfail "dry-run: could not read origin/main's tip"
  if [ "$OLD_HEAD" = "$NEW_HEAD" ]; then
    echo "deploy: dry-run — already at origin/main's tip ($NEW_HEAD); nothing would be pulled; restart: no"
    exit 0
  fi
  CLOSURE_FILES="$(_import_closure)" \
    || envfail "could not compute the dispatcher's import closure at $DEPLOY_ROOT"
  # shellcheck disable=SC2086 — intentional word-splitting: one path per line, none containing spaces
  CHANGED="$("$GIT_BIN" -C "$DEPLOY_ROOT" diff --name-only "$OLD_HEAD" "$NEW_HEAD" -- $CLOSURE_FILES)"
  if [ -n "$CHANGED" ]; then
    echo "deploy: dry-run — would pull $OLD_HEAD -> $NEW_HEAD; restart: yes (import closure changed: $(echo "$CHANGED" | tr '\n' ' '))"
  else
    echo "deploy: dry-run — would pull $OLD_HEAD -> $NEW_HEAD; restart: no (import closure unchanged)"
  fi
  exit 0
fi

"$GIT_BIN" -C "$DEPLOY_ROOT" pull --ff-only origin main \
  || envfail "git pull --ff-only origin main failed at $DEPLOY_ROOT"
NEW_HEAD="$("$GIT_BIN" -C "$DEPLOY_ROOT" rev-parse HEAD)" \
  || envfail "could not read the new HEAD at $DEPLOY_ROOT after pulling"

# ── the runbook's post-deploy checks, BEFORE any restart — a tree that fails these must never be
#    restarted into: under Restart=on-failure a broken import closure would crash-loop the service
#    while `systemctl restart` itself returns 0, hiding the failure from the act's own exit code.
#    Any failure REFUSES (exit 1) naming both HEADs (the pull already happened; nothing is rolled
#    back — attended, loud, the human decides); no record is posted. ────────────────────────────
"$PY_BIN" -m compileall -q "$DEPLOY_ROOT/tools" \
  || refuse "post-deploy check failed: py_compile over tools/ (pulled $OLD_HEAD -> $NEW_HEAD; the tree is NOT rolled back, dispatch was NOT restarted)"
bash -n "$DEPLOY_ROOT/tools/dev-runner.sh" \
  || refuse "post-deploy check failed: bash -n tools/dev-runner.sh (pulled $OLD_HEAD -> $NEW_HEAD; the tree is NOT rolled back, dispatch was NOT restarted)"
"$VENV_PYTHON" "$DEPLOY_ROOT/tools/process.py" validate \
  || refuse "post-deploy check failed: .venv/bin/python tools/process.py validate (pulled $OLD_HEAD -> $NEW_HEAD; the tree is NOT rolled back, dispatch was NOT restarted)"

RESTARTED="no"
if [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
  CLOSURE_FILES="$(_import_closure)" \
    || envfail "could not compute the dispatcher's import closure at $DEPLOY_ROOT (checks already passed at $NEW_HEAD)"
  # shellcheck disable=SC2086 — intentional word-splitting: one path per line, none containing spaces
  CHANGED="$("$GIT_BIN" -C "$DEPLOY_ROOT" diff --name-only "$OLD_HEAD" "$NEW_HEAD" -- $CLOSURE_FILES)"
  if [ -n "$CHANGED" ]; then
    log "restarting dispatch — import closure changed: $(echo "$CHANGED" | tr '\n' ' ')"
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" "$SYSTEMCTL_BIN" --user restart dispatch \
      || envfail "systemctl --user restart dispatch failed (checks already passed at $NEW_HEAD)"
    RESTARTED="yes"
  else
    log "import closure unchanged — dispatch not restarted"
  fi
else
  log "already at origin/main's tip ($NEW_HEAD) — nothing pulled, dispatch not restarted"
fi

# ── the one record: surface, commit, who (actor class), restart — once, on the deploy trail ─────
# `--body` inline (never `--body-file`): the record is a handful of short field lines — small
# enough to ride argv directly, the same convention tools/promote.sh uses for its own short
# record comments, and it keeps the posted text visible to a test's `gh` stub without a temp-file
# lifecycle to race against this script's own exit.
COMMIT_LINE="$("$PY_BIN" "$DEPLOY_ROOT/tools/provenance.py" "$DEPLOY_ROOT")"   # "commit: <full sha>"

BODY="$(printf 'YR-DEPLOY:\nsurface: dispatch,dev-runner,epic-gate\n%s\nwho: %s\nrestart: %s\n\nDeployed via `tools/deploy.sh` — pulled `%s` -> `%s`; post-deploy checks passed.\n' \
  "$COMMIT_LINE" "$WHO" "$RESTARTED" "$OLD_HEAD" "$NEW_HEAD")"

"$GH_BIN" issue comment "$DEPLOY_ISSUE" --repo "$DEPLOY_REPO" --body "$BODY" >/dev/null \
  || envfail "the deploy completed (commit $NEW_HEAD, restart=$RESTARTED) but the YR-DEPLOY record failed to post to $DEPLOY_REPO#$DEPLOY_ISSUE — post it by hand"

log "deployed: $NEW_HEAD (restart=$RESTARTED, who=$WHO)"
exit 0
