"""tests/harness/gh_fake.py — the shared `gh` fakes, two blessed faces.

See tests/harness/contract.md for the harness contract (flag families, call-shape routing). Two
constants, not one, because the two consumer categories drive `gh` through genuinely different
surfaces:

GH_STUB is a bash script for the tools/dev-runner.sh-based suites (test_dev_runner.py and its siblings
test_autonomous_merge.py / test_ci_registration_grace.py / test_dev_runner_reevaluate.py). It is a
SUPERSET of the five bash stubs it replaces (the base GH_STUB, GH_STUB_PR, GH_STUB_EXT, GH_STUB_SEQ,
GH_STUB_REEVAL) — every extra behavior one of those five needed (sequenced CI-rollup polling, PR-create
retry/idempotence, the re-evaluate PR-state fetch, `pr merge`) is gated behind its own env var or the
actual requested `--json` field, so any one suite only ever lights up the arms its own scenarios drive.
No suite needs a derived variant: unlike the claude fake (whose consumers each need genuinely different
STAGE behavior spliced in), every gh stub here was already just wiring for the same handful of `gh`
subcommands, so one script serves all five consumers directly.

GH_STUB_TOOLS is a python3 script for the three standalone operator-tool suites (test_board.py /
test_promote.py / test_watch_build.py), which drive tools/board.sh / tools/promote.sh /
tools/watch_build.sh — scripts with no `claude` stage and a disjoint `gh` subcommand surface from the
runner (`api graphql`/`api user`, no `project item-list`, a ticking multi-poll `pr list`). A python
script is the natural face for these: state (an org-wide GraphQL shape, a canned issue-side response, a
tick-indexed state list) is far more naturally expressed as `json.loads`/dict-building than as bash
case arms, and these three suites already agreed on that shape independently before this migration.
"""

# Subcommand routing (see contract.md): repo / issue view|comment / project item-list|item-edit /
# pr view|create|list|comment|merge. `pr view` disambiguates by the actual requested --json field
# (statusCheckRollup / mergeCommit / headRefName-bearing re-evaluate fetch), matching how
# tools/dev-runner.sh itself distinguishes those three callers — never by which env var a given test
# happens to set. `pr list` disambiguates by `--head` (the idempotent-create existence check) vs
# everything else (the shadow-completion scan / canned prior-PR records).
GH_STUB = '''#!/usr/bin/env bash
case "$1" in
  repo) echo "test/repo" ;;
  issue)
    case "$2" in
      view)    cat "$STUB_ISSUE_JSON" ;;
      comment) printf 'COMMENT %s\\n' "$*" >> "$STUB_TIMELINE" ;;
      *)       echo "unhandled issue $2" >&2; exit 9 ;;
    esac ;;
  project)
    case "$2" in
      item-list) [ -n "${STUB_ITEMLIST_FAIL:-}" ] && exit 4 || cat "$STUB_ITEM_JSON" ;;
      item-edit) printf 'EDIT %s\\n' "$*" >> "$STUB_TIMELINE" ;;
      *)         echo "unhandled project $2" >&2; exit 9 ;;
    esac ;;
  pr)
    case "$2" in
      view)
        if printf '%s\\n' "$@" | grep -q statusCheckRollup; then
          if [ -n "${STUB_PRVIEW_FAIL:-}" ]; then echo "pr view failed (stub env failure)" >&2; exit 5; fi
          if [ -n "${STUB_ROLLUP_CALLS:-}" ]; then
            n=0
            [ -f "$STUB_ROLLUP_CALLS" ] && n="$(cat "$STUB_ROLLUP_CALLS")"
            n=$((n + 1))
            echo "$n" > "$STUB_ROLLUP_CALLS"
            if [ -n "${STUB_ROLLUP_FAIL_AT:-}" ] && [ "$n" -ge "$STUB_ROLLUP_FAIL_AT" ]; then
              echo "pr view failed (stub)" >&2; exit 5
            fi
            if [ "$n" -eq 1 ]; then cat "$STUB_ROLLUP_JSON_1"; else cat "$STUB_ROLLUP_JSON_2"; fi
          elif [ -n "${STUB_ROLLUP_JSON:-}" ]; then
            cat "$STUB_ROLLUP_JSON"
          else
            printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1"
          fi
        elif printf '%s\\n' "$@" | grep -q mergeCommit; then
          printf '{"mergeCommit":{"oid":"%s"}}\\n' "${STUB_MERGECOMMIT_OID:-}"
        elif printf '%s\\n' "$@" | grep -q headRefName; then
          if [ -n "${STUB_PRFETCH_FAIL:-}" ]; then echo "pr view failed (stub)" >&2; exit 5; fi
          cat "$STUB_REEVAL_PRJSON"
        else
          printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1"
        fi ;;
      create)
        printf 'CALL\\n' >> "${STUB_PRCREATE_CALLS:-/dev/null}"
        n=0
        if [ -n "${STUB_PRCREATE_COUNTER:-}" ] && [ -f "$STUB_PRCREATE_COUNTER" ]; then n=$(cat "$STUB_PRCREATE_COUNTER"); fi
        n=$((n + 1))
        [ -n "${STUB_PRCREATE_COUNTER:-}" ] && printf '%s' "$n" > "$STUB_PRCREATE_COUNTER"
        fail_count="${STUB_PRCREATE_FAIL_COUNT:-0}"
        if [ "$fail_count" = "always" ] || [ "$n" -le "$fail_count" ]; then
          if [ -n "${STUB_PRCREATE_MARKS_EXISTING:-}" ] && [ -n "${STUB_PR_EXISTS_FILE:-}" ]; then
            echo "https://stub/pr/1" > "$STUB_PR_EXISTS_FILE"
          fi
          echo "${STUB_PRCREATE_ERR:-stub pr create error: timeout}" >&2
          exit 1
        fi
        printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"
        echo "https://stub/pr/1" ;;
      list)
        if printf '%s\\n' "$@" | grep -q -- "--head"; then
          if [ -n "${STUB_PR_EXISTS_FILE:-}" ] && [ -f "$STUB_PR_EXISTS_FILE" ]; then
            printf '[{"url": "%s"}]' "$(cat "$STUB_PR_EXISTS_FILE")"
          else
            printf '[]'
          fi
        else
          [ -n "${STUB_PRLIST_FAIL:-}" ] && { echo "pr list failed (stub)" >&2; exit 5; }
          cat "${STUB_PRS_JSON:-/dev/null}"
        fi ;;
      merge)
        printf 'MERGE %s\\n' "$*" >> "$STUB_GH_CALLS"
        [ -n "${STUB_MERGE_FAIL:-}" ] && { echo "merge API failed (stub)" >&2; exit 6; }
        echo "merged" ;;
      comment)
        echo PRCOMMENT >> "$STUB_TIMELINE"
        if [ -n "${STUB_PRCOMMENTS:-}" ]; then
          __p=""; __bf=""; __body=""
          for __a in "$@"; do
            [ "$__p" = "--body-file" ] && __bf="$__a"
            [ "$__p" = "--body" ] && __body="$__a"
            __p="$__a"
          done
          [ -n "$__bf" ] && { echo "=== PRCOMMENT ==="; cat "$__bf"; } >> "$STUB_PRCOMMENTS"
          [ -n "$__body" ] && { echo "=== PRCOMMENT ==="; printf '%s\\n' "$__body"; } >> "$STUB_PRCOMMENTS"
        fi
        true ;;   # a real `gh pr comment` exits 0 regardless of which of --body-file/--body was used —
                  # the two recording checks above are each conditional (false whenever their own flag
                  # wasn't the one passed), so without this the LAST one's false test would leak out as
                  # the stub's own exit code and falsely fail every --body-file-only caller.
      *)       printf '%s ' "$@" >> "$STUB_GH_CALLS"; echo >> "$STUB_GH_CALLS"; echo "https://stub/pr/1" ;;
    esac ;;
  *)  echo "unhandled gh $*" >&2; exit 9 ;;
esac
'''

# GH_STUB_TOOLS's `api graphql` dispatch is presence-of-canned-input, not requested-field grepping (the
# three consumers' GraphQL bodies are opaque `-f query=...` strings, unlike the bash face's --json flag
# which is easy to grep): STUB_NODES selects the board-scan shape, STUB_ISSUE_RESPONSE the promote
# issue-side shape (already fully pre-built JSON text, so it is just echoed), STUB_STATES the watch-build
# tick-indexed shape. Exactly one is ever set per consuming suite.
GH_STUB_TOOLS = '''#!/usr/bin/env python3
import sys, os, json

argv = sys.argv[1:]
log = os.environ.get("STUB_CALLS_LOG")
if log:
    with open(log, "a") as f:
        print(json.dumps(argv), file=f)


def _tick_index():
    try:
        return int(open(os.environ["STUB_COUNTER"]).read().strip())
    except Exception:
        return 0


def _tick_advance(states):
    i = _tick_index()
    if i < len(states) - 1:
        open(os.environ["STUB_COUNTER"], "w").write(str(i + 1))


if argv[:2] == ["repo", "view"]:
    print(os.environ.get("STUB_REPO", "test/repo"))
    sys.exit(0)

if argv[:2] == ["api", "graphql"]:
    if "STUB_NODES" in os.environ:
        nodes = json.loads(os.environ["STUB_NODES"])
        print(json.dumps({"data": {"organization": {"projectV2": {"items": {"nodes": nodes}}}}}))
        sys.exit(0)
    if "STUB_ISSUE_RESPONSE" in os.environ:
        print(os.environ["STUB_ISSUE_RESPONSE"])
        sys.exit(0)
    if "STUB_STATES" in os.environ:
        states = json.loads(os.environ["STUB_STATES"])
        st = states[_tick_index()]
        print(json.dumps({"data": {"repository": {"issue": {
            "state": st.get("issue_state", "OPEN"),
            "projectItems": {"nodes": [{
                "project": {"number": int(os.environ.get("PROJECT_NUMBER", "1"))},
                "status": ({"name": st["status"]} if st.get("status") else None),
                "reason": ({"name": st["reason"]} if st.get("reason") else None),
            }]},
        }}}}))
        sys.exit(0)
    sys.exit(9)

if argv[:2] == ["api", "user"]:
    print(os.environ.get("STUB_WHO", "operator"))
    sys.exit(0)

if argv[:2] == ["issue", "comment"]:
    sys.exit(1 if os.environ.get("STUB_COMMENT_FAIL") else 0)

if argv[:2] == ["project", "item-edit"]:
    sys.exit(1 if os.environ.get("STUB_EDIT_FAIL") else 0)

if argv[:2] == ["pr", "list"]:
    states = json.loads(os.environ["STUB_STATES"])
    st = states[_tick_index()]
    prs = []
    if st.get("pr_open"):
        prs = [{"number": 1, "headRefName": "task/%s-x" % os.environ["STUB_ISSUE"], "url": "https://example/pr/1"}]
    print(json.dumps(prs))
    _tick_advance(states)
    sys.exit(0)

if argv[:2] == ["issue", "view"]:
    comments = json.loads(os.environ.get("STUB_COMMENTS", "[]"))
    print(json.dumps({"comments": comments}))
    sys.exit(0)

sys.exit(9)
'''
