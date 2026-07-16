"""tests/harness/claude_fake.py — the ONE stage-aware `claude` fake, classifier included.

See tests/harness/contract.md for the harness contract (flag families, prompt transport, how a stage
is recognized). CLAUDE_STUB below is the single legal stage-recognition path: every suite needing a
stage-aware `claude` stub consumes this constant directly, or derives a variant from its exact text
(never by re-typing the classification patterns) — see tests/test_shadow_review.py for the derivation
pattern (a shadow-aware REVIEW arm spliced into this same case block by locating, not retyping, its
patterns).
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
case "$args" in
  *REVIEWER*)            echo REVIEW >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REVIEW_QUOTA:-}" ]; then echo "${STUB_REVIEW_QUOTA}" >&2; exit 1; fi
                        if [ -n "${STUB_REVIEW_VERDICT:-}" ]; then printf '%s\\n' "$STUB_REVIEW_VERDICT"
                        elif [ -n "${STUB_REVIEW_BLOCK:-}" ] && [ ! -f review_repaired ]; then echo "VERDICT: REQUEST_CHANGES"
                        else echo "VERDICT: APPROVE"; fi ;;
  *"REQUESTED CHANGES"*) echo REVIEWFIX >> "$STUB_TIMELINE"; [ -n "${STUB_REVIEWFIX_CRASH:-}" ] && exit 7; [ -z "${STUB_REVIEW_NOFIX:-}" ] && : > review_repaired ;;
  *TESTER*)             echo TEST   >> "$STUB_TIMELINE"
                        if [ -n "${STUB_TESTER_QUOTA:-}" ]; then echo "${STUB_TESTER_QUOTA}" >&2; exit 1; fi
                        [ -n "${STUB_TESTER_PROD_CHANGE:-}" ] && printf 'by tester\\n' > tester_prod.txt
                        [ -n "${STUB_TESTER_TEST_CHANGE:-}" ] && { mkdir -p tests && printf 'pass\\n' > tests/test_stub_output.py; }
                        [ -n "${STUB_TESTER_ARTIFACT_CHANGE:-}" ] && { mkdir -p tools/__pycache__ && printf 'bytecode\\n' > tools/__pycache__/check.cpython-314.pyc; } ;;
  *"tests FAIL"*)       echo REPAIR >> "$STUB_TIMELINE"
                        if [ -n "${STUB_REPAIR_QUOTA:-}" ]; then echo "${STUB_REPAIR_QUOTA}" >&2; exit 1; fi
                        [ -z "${STUB_REPAIR_NOFIX:-}" ] && : > repaired ;;
  *)                    echo IMPL   >> "$STUB_TIMELINE"
                        if [ -n "${STUB_IMPL_QUOTA:-}" ]; then echo "${STUB_IMPL_QUOTA}" >&2; exit 1; fi
                        if [ -n "${STUB_IMPL_FAIL:-}" ]; then echo "${STUB_IMPL_FAIL}" >&2; exit 1; fi
                        [ -n "${STUB_CLAUDE_CHANGE:-}" ] && printf 'hello\\n' > feature.txt ;;
esac
exit 0
'''
