"""tests/harness/claude_fake.py — the ONE stage-aware `claude` fake, classifier included.

See tests/harness/contract.md for the harness contract (flag families, prompt transport, how a stage
is recognized). CLAUDE_STUB below is the single legal stage-recognition path: every suite needing a
stage-aware `claude` stub consumes this constant directly, or derives a variant from its exact text
(never by re-typing the classification patterns) — see tests/test_shadow_review.py for the derivation
pattern (a shadow-aware REVIEW arm spliced into this same case block by locating, not retyping, its
patterns).

CLAUDE_STUB_JSON is the same classifier's `--output-format json` twin: each arm emits a single-line
result envelope (fixed, distinguishable token counts) instead of plain text, so usage-capture tests can
prove extraction/rewrite/summary end-to-end. It is a second, independent literal (not derived from
CLAUDE_STUB via .replace(), since every arm's body differs) but is still the one legal home for that
JSON-envelope shape — see tests/test_shadow_review.py's CLAUDE_STUB_SHADOW_JSON for the derivation
pattern used to layer shadow-awareness on top of it.
"""

# stage-aware: REVIEWER role -> reviewer (emits VERDICT); "REQUESTED CHANGES" -> review-repair;
# TESTER role -> tester; "tests FAIL" -> check-repair; otherwise implementer.
# Tester file-writing is controlled by separate env vars (STUB_TESTER_PROD_CHANGE /
# STUB_TESTER_TEST_CHANGE) so the boundary guard can be exercised independently of the
# implementer's STUB_CLAUDE_CHANGE, and the happy-path tests don't inadvertently violate
# the boundary by writing a prod file from the tester stage.
CLAUDE_STUB = '''#!/usr/bin/env bash
# Capture stdin byte-exactly: `$(cat)` strips ALL trailing newlines, so append a sentinel before the
# command substitution and strip it after — the byte-exact stdin pin (issue #121) must be able to see a
# stray trailing newline the transport might add, which a naive `$(cat)` would silently swallow.
stdin_content="$(cat; printf x)"; stdin_content="${stdin_content%x}"
# crash mode: simulate a stage killed by a signal before it writes anything (gilda#9 run 9-4131516's
# zero-byte implement.log) — fires before any observation hook so the caller's captured log stays empty.
[ -n "${STUB_CLAUDE_SIGKILL:-}" ] && kill -KILL $$
[ -n "${STUB_CLAUDE_ARGV:-}" ] && printf '%s\\n' "$@" > "$STUB_CLAUDE_ARGV"
[ -n "${STUB_CLAUDE_ARGV_LOG:-}" ] && { printf '===STUB-CALL===\\n'; printf '%s\\n' "$@"; } >> "$STUB_CLAUDE_ARGV_LOG"
[ -n "${STUB_CLAUDE_STDIN:-}" ] && printf '%s' "$stdin_content" > "$STUB_CLAUDE_STDIN"
[ -n "${STUB_CLAUDE_STDIN_LOG:-}" ] && { printf '===STUB-STDIN-BEGIN===\\n'; printf '%s' "$stdin_content"; printf '\\n===STUB-STDIN-END===\\n'; } >> "$STUB_CLAUDE_STDIN_LOG"
# issue #121: the task prompt travels on stdin now, never argv — so stage classification (below) must
# match against the combined argv+stdin text, not argv alone, or every stage whose routing literal lived
# in its task prompt (check-repair's "tests FAIL", review-repair's "REQUESTED CHANGES") misclassifies.
args="$*"$'\\n'"$stdin_content"
[ -n "${STUB_CLAUDE_ENV_FILE:-}" ] && printf 'CLAUDE_CONFIG_DIR=%s\\n' "${CLAUDE_CONFIG_DIR:-}" >> "$STUB_CLAUDE_ENV_FILE"
[ -n "${STUB_CLAUDE_GITENV_FILE:-}" ] && printf 'GIT_CONFIG_GLOBAL=%s GIT_CONFIG_SYSTEM=%s\\n' "${GIT_CONFIG_GLOBAL:-unset}" "${GIT_CONFIG_SYSTEM:-unset}" >> "$STUB_CLAUDE_GITENV_FILE"
# issue #142: an optional observation hook (a no-op unless a test opts in) recording the TMPDIR this
# stage subprocess actually inherited, and whether that directory existed AT CALL TIME — one line pair
# appended per invocation, so a multi-stage build's whole sequence of TMPDIR values can be checked.
[ -n "${STUB_CLAUDE_TMPDIR_FILE:-}" ] && { printf 'TMPDIR=%s\\n' "${TMPDIR:-unset}"; { [ -n "${TMPDIR:-}" ] && [ -d "$TMPDIR" ]; } && echo DIR_EXISTS=1 || echo DIR_EXISTS=0; } >> "$STUB_CLAUDE_TMPDIR_FILE"
# issue #247: backgrounded ahead of the classifying case block (never inside the *REVIEWER* arm's own
# literal text) so tests/test_shadow_review.py's exact-text splice of that arm keeps matching byte-for-byte.
if [ -n "${STUB_REVIEW_GROUP_CHILD_SLEEP:-}" ] && [[ "$args" == *REVIEWER* ]]; then
  ( sleep "${STUB_REVIEW_GROUP_CHILD_SLEEP}"; echo GROUP-CHILD-DONE ) &
fi
case "$args" in
  *REVIEWER*)            echo REVIEW >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REVIEW_QUOTA:-}" ]; then echo "${STUB_REVIEW_QUOTA}" >&2; exit 1; fi
                        if [ -n "${STUB_REVIEW_VERDICT:-}" ]; then printf '%s\\n' "$STUB_REVIEW_VERDICT"
                        elif [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then echo "VERDICT: REQUEST_CHANGES"
                        else echo "VERDICT: APPROVE"; fi ;;
  *"REQUESTED CHANGES"*) echo REVIEWFIX >> "$STUB_TIMELINE"; [ -n "${STUB_REVIEWFIX_CRASH:-}" ] && exit 7; [ -n "${STUB_REVIEWFIX_EDIT:-}" ] && printf 'repaired-by-review\\n' >> feature.txt; [ -z "${STUB_REVIEW_NOFIX:-}" ] && : > review_repaired ;;
  *TESTER*)             echo TEST   >> "$STUB_TIMELINE"
                        if [ -n "${STUB_TESTER_QUOTA:-}" ]; then echo "${STUB_TESTER_QUOTA}" >&2; exit 1; fi
                        [ -n "${STUB_TESTER_PROD_CHANGE:-}" ] && printf 'by tester\\n' > tester_prod.txt
                        [ -n "${STUB_TESTER_TEST_CHANGE:-}" ] && { mkdir -p tests && printf 'pass\\n' > tests/test_stub_output.py; }
                        [ -n "${STUB_TESTER_ARTIFACT_CHANGE:-}" ] && { mkdir -p tools/__pycache__ && printf 'bytecode\\n' > tools/__pycache__/check.cpython-314.pyc; }
                        if [ -n "${STUB_LINGER_PIDFILE:-}" ]; then
                          child_pid="$(cat "$STUB_LINGER_PIDFILE" 2>/dev/null)"
                          [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null && echo LINGERING >> "$STUB_TIMELINE"
                        fi ;;
  *"lint gate FAILS"*)  echo LINTREPAIR >> "$STUB_TIMELINE"
                        [ -n "${STUB_LINTREPAIR_HEAL:-}" ] && : > lint_ok ;;
  *"tests FAIL"*)       echo REPAIR >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REPAIR_QUOTA:-}" ]; then echo "${STUB_REPAIR_QUOTA}" >&2; exit 1; fi
                        [ -z "${STUB_REPAIR_NOFIX:-}" ] && : > repaired ;;
  *)                    echo IMPL   >> "$STUB_TIMELINE"
                        if [ -n "${STUB_IMPL_QUOTA:-}" ]; then echo "${STUB_IMPL_QUOTA}" >&2; exit 1; fi
                        if [ -n "${STUB_IMPL_FAIL:-}" ]; then echo "${STUB_IMPL_FAIL}" >&2; exit 1; fi
                        [ -n "${STUB_CLAUDE_CHANGE:-}" ] && printf 'hello\\n' > feature.txt
                        [ -n "${STUB_LINGER_PIDFILE:-}" ] && { ( exec sleep 5 ) & echo $! > "$STUB_LINGER_PIDFILE"; }
                        if [ -n "${STUB_IMPL_GROUP_CHILD_SLEEP:-}" ]; then
                          ( sleep "${STUB_IMPL_GROUP_CHILD_SLEEP}"; echo GROUP-CHILD-DONE ) &
                        fi ;;
esac
exit 0
'''

# CLAUDE_STUB_JSON is a second claude stub, stage-aware like CLAUDE_STUB, but each branch emits a
# single-line `--output-format json` result envelope (fixed, distinguishable token counts per stage)
# instead of plain text — proving extraction, the rewrite, and the summary end-to-end (issue #48).
CLAUDE_STUB_JSON = '''#!/usr/bin/env bash
stdin_content="$(cat)"
args="$*"$'\\n'"$stdin_content"   # issue #121: classification must see stdin too (the task prompt lives there)
[ -n "${STUB_CLAUDE_ARGV:-}" ] && printf '%s\\n' "$@" > "$STUB_CLAUDE_ARGV"
# issue #205: emit_json optionally adds a "session_id" key when STUB_SESSION_ID is set — no pre-existing
# exact-dict-equality assertion in this suite ever sets that var, so this stays byte-for-byte
# backward-compatible there; new tests opt in to exercise session_id-based transcript resolution.
emit_json() {  # $1=result-text $2=input $3=output $4=cache_write $5=cache_read $6=duration_ms
  if [ -n "${STUB_SESSION_ID:-}" ]; then
    printf '{"type":"result","subtype":"success","is_error":false,"duration_ms":%s,"result":"%s","session_id":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":%s}}\\n' "$6" "$1" "$STUB_SESSION_ID" "$2" "$3" "$4" "$5"
  else
    printf '{"type":"result","subtype":"success","is_error":false,"duration_ms":%s,"result":"%s","usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":%s}}\\n' "$6" "$1" "$2" "$3" "$4" "$5"
  fi
}
if [ -n "${STUB_REVIEW_GROUP_CHILD_SLEEP:-}" ] && [[ "$args" == *REVIEWER* ]]; then
  ( sleep "${STUB_REVIEW_GROUP_CHILD_SLEEP}"; echo GROUP-CHILD-DONE ) &
fi
case "$args" in
  *REVIEWER*)
    echo REVIEW >> "$STUB_TIMELINE"
    if [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then
      emit_json "VERDICT: REQUEST_CHANGES" 11 12 13 14 100
    else
      emit_json "VERDICT: APPROVE" 21 22 23 24 200
    fi ;;
  *"REQUESTED CHANGES"*)
    echo REVIEWFIX >> "$STUB_TIMELINE"
    : > review_repaired
    emit_json "fixed the blockers" 31 32 33 34 300 ;;
  *TESTER*)
    echo TEST >> "$STUB_TIMELINE"
    mkdir -p tests && printf 'pass\\n' > tests/test_stub_output.py
    emit_json "wrote tests" 41 42 43 44 400 ;;
  *"tests FAIL"*)
    echo REPAIR >> "$STUB_TIMELINE"
    : > repaired
    emit_json "repaired the code" 51 52 53 54 500 ;;
  *)
    echo IMPL >> "$STUB_TIMELINE"
    printf 'hello\\n' > feature.txt
    emit_json "implemented the feature" 61 62 63 64 600
    if [ -n "${STUB_IMPL_JSON_THEN_FAIL:-}" ]; then exit 1; fi ;;
esac
exit 0
'''
