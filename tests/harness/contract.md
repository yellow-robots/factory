# The harness contract

`tests/harness/` is the shared home for the pytest suite's fakes of the two external CLIs the pipeline
shells out to: `claude` (`claude_fake.py`'s `CLAUDE_STUB`, one stage-aware stub whose classifier is the
only legal way a test recognizes which stage of `tools/dev-runner.sh` is currently running) and `gh`
(`gh_fake.py`'s `GH_STUB`/`GH_STUB_TOOLS`, covered in "The gh fake" below). This doc is the authoritative
surface for both contracts — the flag families each exposes, how each CLI's input reaches it, and how it
tells one call/stage from another. It documents `STUB_*` behavior as it exists; changing what a flag does
is out of scope for the slices that added this doc (issues #243/#244/#245).

## Prompt transport

The runner never puts the task prompt on `claude`'s argv — it travels on stdin (issue #121). The stub
reads stdin byte-exactly (a trailing-newline-preserving `$(cat; printf x)` capture, since a naive
`$(cat)` strips all trailing newlines) and classifies against the **combined** text:

```bash
args="$*"$'\n'"$stdin_content"
```

Any routing literal that lives only in the task prompt (not argv) — `tests FAIL`, `REQUESTED CHANGES` —
would be invisible to a classifier that only inspected `$*`. Matching against `$args` is what keeps
classification correct once the prompt moved to stdin.

## How a stage is recognized

`CLAUDE_STUB`'s classifier is a single ordered `case "$args" in ... esac`, matched in this order:

| Pattern | Stage | Notes |
|---|---|---|
| `*REVIEWER*` | reviewer | emits a `VERDICT: …` line |
| `*"REQUESTED CHANGES"*` | review-repair | the reviewer's own repair loop |
| `*TESTER*` | tester | writes test files, gated by its own flag family |
| `*"lint gate FAILS"*` | lint-repair | the lint tier's own LLM repair loop (issue #213) |
| `*"tests FAIL"*` | check-repair | the check gate's own repair loop |
| (no match) | implement | the default arm |

The four routing literals `tools/dev-runner.sh` bakes into its per-stage prompts unconditionally
(`TESTER`, `REVIEWER`, `tests FAIL`, `REQUESTED CHANGES`) are pinned by
`tests/harness/test_claude_fake_contract.py::test_runner_prompts_contain_stub_markers` against the
runner's source directly — if one is ever dropped from `tools/dev-runner.sh`, that guard fails loudly
rather than letting the stub silently misclassify a stage as `implement`. `lint gate FAILS` is a fifth
literal the runner emits only when a repo declares a `lint_cmd` (the lint tier is otherwise inert), so it
is not part of that guard's pin set.

This classifier is the single legal stage-recognition path. A suite that needs stage-aware behavior
consumes `CLAUDE_STUB` as-is, or derives a variant from its exact text (locating the arm to change by
its pattern, never by re-typing the classification patterns themselves) — see
`tests/test_shadow_review.py` for the derivation pattern used to add shadow-review awareness on top of
the same classifier.

## Flag families

Every flag below is read as an environment variable by the subprocess; unset/empty means "off". Flags
are grouped by which stage's arm reads them.

### Observation hooks (any stage, no-op unless opted in)

| Flag | Effect |
|---|---|
| `STUB_CLAUDE_ARGV` | write this call's argv (one arg per line) to the given path |
| `STUB_CLAUDE_ARGV_LOG` | append this call's argv to the given path, `===STUB-CALL===`-delimited |
| `STUB_CLAUDE_STDIN` | write this call's raw stdin to the given path |
| `STUB_CLAUDE_STDIN_LOG` | append this call's raw stdin to the given path, begin/end-delimited |
| `STUB_CLAUDE_ENV_FILE` | append the subprocess's own `CLAUDE_CONFIG_DIR` to the given path |
| `STUB_CLAUDE_GITENV_FILE` | append the subprocess's own `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` |
| `STUB_CLAUDE_TMPDIR_FILE` | append the subprocess's own `TMPDIR` and whether it existed at call time |

### Crash mode (any stage, no-op unless opted in)

| Flag | Effect |
|---|---|
| `STUB_CLAUDE_SIGKILL` | `kill -KILL` itself immediately after consuming stdin, before any other hook or classification runs — simulates a stage terminated by a signal before it writes anything (the zero-byte-log class of failure) |

### Process-reap observation (spans the implement and tester arms)

| Flag | Effect |
|---|---|
| `STUB_LINGER_PIDFILE` | implement arm: background a `sleep 5` and write its pid to the given path; tester arm: read that pid back and, if the process is still alive, append `LINGERING` to `STUB_TIMELINE` — proves a stray background child from one stage is dead before the next stage starts |

### Stage-group grace observation (issue #247; implement and reviewer arms, both stubs)

| Flag | Effect |
|---|---|
| `STUB_IMPL_GROUP_CHILD_SLEEP` | implement arm: background `sleep <n>; echo GROUP-CHILD-DONE` (no wait) before the arm returns — the marker lands in the stage log only once the child actually wakes and writes it, so it proves whether the runner waited for that write or reaped the child first |
| `STUB_REVIEW_GROUP_CHILD_SLEEP` | reviewer arm: same shape, backgrounded before the verdict is emitted |

### Shared timeline

`STUB_TIMELINE` is not a flag but the shared recorder: every arm appends its own stage token (`IMPL`,
`TEST`, `REPAIR`, `REVIEW`, `REVIEWFIX`, `LINTREPAIR`) to this file, in call order — the primitive every
ordering assertion in the consuming suites is built on. The tester arm can additionally append
`LINGERING` (see the process-reap observation hook above).

### reviewer arm

| Flag | Effect |
|---|---|
| `STUB_REVIEW_QUOTA` | print this to stderr and exit 1 (simulates a quota/rate-limit failure) |
| `STUB_REVIEW_VERDICT` | print this exact line as the verdict, overriding the block logic below |
| `STUB_REVIEW_BLOCK` | emit `VERDICT: REQUEST_CHANGES` until a `review_repaired` marker file exists |

### review-repair arm

| Flag | Effect |
|---|---|
| `STUB_REVIEWFIX_CRASH` | exit 7 before touching the repair marker |
| `STUB_REVIEWFIX_EDIT` | append a content-visible line (`repaired-by-review`) to `feature.txt` |
| `STUB_REVIEW_NOFIX` | skip creating the `review_repaired` marker (repair "fails" to heal) |

### tester arm

| Flag | Effect |
|---|---|
| `STUB_TESTER_QUOTA` | print this to stderr and exit 1 |
| `STUB_TESTER_PROD_CHANGE` | write a production file (`tester_prod.txt`) — for the boundary guard |
| `STUB_TESTER_TEST_CHANGE` | write a test file under `tests/` |
| `STUB_TESTER_ARTIFACT_CHANGE` | write a build artifact under `tools/__pycache__/` |

`STUB_TESTER_PROD_CHANGE`/`STUB_TESTER_TEST_CHANGE` are deliberately separate from the implement arm's
`STUB_CLAUDE_CHANGE`, so the boundary guard (tester must not touch production files) can be exercised
independently of the happy-path implement change.

### lint-repair arm

| Flag | Effect |
|---|---|
| `STUB_LINTREPAIR_HEAL` | create a `lint_ok` marker (repair "fixes" the lint gate) |

### check-repair arm

| Flag | Effect |
|---|---|
| `STUB_REPAIR_QUOTA` | print this to stderr and exit 1 |
| `STUB_REPAIR_NOFIX` | skip creating the `repaired` marker (repair "fails" to heal) |

### implement arm (default)

| Flag | Effect |
|---|---|
| `STUB_IMPL_QUOTA` | print this to stderr and exit 1 |
| `STUB_IMPL_FAIL` | print this to stderr and exit 1 (a distinct failure reason) |
| `STUB_CLAUDE_CHANGE` | write `feature.txt` — the stand-in for "the implementer changed something" |

## The gh fake

`gh_fake.py` carries two constants, one per consumer category (see its module docstring for why two
faces rather than one):

- `GH_STUB` — a bash script for the `tools/dev-runner.sh`-based suites (`test_dev_runner.py` and its
  siblings `test_autonomous_merge.py`, `test_ci_registration_grace.py`, `test_dev_runner_reevaluate.py`).
  It is a SUPERSET stub: every scenario any one of those suites needs is a mode gated by its own env var
  (or, for `pr view`/`pr list`, by the actual requested `--json` field / flag — never by which env var a
  test happens to set, so the routing matches the real call shapes `tools/dev-runner.sh` issues).
- `GH_STUB_TOOLS` — a python3 script for the three standalone operator-tool suites (`test_board.py`,
  `test_promote.py`, `test_watch_build.py`), which drive `tools/board.sh`/`tools/promote.sh`/
  `tools/watch_build.sh` — no `claude` stage, and a disjoint `gh` subcommand surface from the runner.

Both are installed identically to how the runner's own stubs are: written to an executable file (any
name, conventionally `gh`) and wired in via the `GH_BIN` environment variable — never PATH-shimmed, never
a `subprocess.run` monkeypatch.

### `GH_STUB` subcommand routing (bash face)

| Call | Behavior |
|---|---|
| `repo` (any subcommand) | prints `test/repo` |
| `issue view` | cats `$STUB_ISSUE_JSON` |
| `issue comment` | appends `COMMENT <argv>` to `$STUB_TIMELINE` |
| `project item-list` | exit 4 if `STUB_ITEMLIST_FAIL`, else cats `$STUB_ITEM_JSON` |
| `project item-edit` | appends `EDIT <argv>` to `$STUB_TIMELINE` |
| `pr view --json statusCheckRollup` | `STUB_PRVIEW_FAIL` → exit 5; else, if `STUB_ROLLUP_CALLS` is set, a call-counter sequence (call 1 → `STUB_ROLLUP_JSON_1`, later calls → `STUB_ROLLUP_JSON_2`, with `STUB_ROLLUP_FAIL_AT=<n>` failing calls ≥ n); else if `STUB_ROLLUP_JSON` is set, cats it; else records the call to `STUB_GH_CALLS` and echoes the stub PR URL |
| `pr view --json mergeCommit` | prints `{"mergeCommit":{"oid": "$STUB_MERGECOMMIT_OID"}}` |
| `pr view` (a `--json` field list containing `headRefName`, i.e. the `--re-evaluate` PR-state fetch) | `STUB_PRFETCH_FAIL` → exit 5; else cats `$STUB_REEVAL_PRJSON` |
| `pr view` (anything else) | records the call to `STUB_GH_CALLS`, echoes `https://stub/pr/1` |
| `pr create` | idempotent-retry simulator: counts attempts via `STUB_PRCREATE_COUNTER`/logs to `STUB_PRCREATE_CALLS`, fails the first `STUB_PRCREATE_FAIL_COUNT` calls (or `always`), optionally marks `STUB_PR_EXISTS_FILE` on a failing attempt (`STUB_PRCREATE_MARKS_EXISTING`) — else records to `STUB_GH_CALLS` and echoes the stub PR URL |
| `pr list --head ...` (the idempotent-create existence check) | `[{"url": ...}]` if `STUB_PR_EXISTS_FILE` exists, else `[]` |
| `pr list` (anything else — the shadow-completion scan) | `STUB_PRLIST_FAIL` → exit 5; else cats `${STUB_PRS_JSON:-/dev/null}` |
| `pr merge` | records `MERGE <argv>` to `STUB_GH_CALLS`; `STUB_MERGE_FAIL` → exit 6; else prints `merged` |
| `pr comment` | appends `PRCOMMENT` to `$STUB_TIMELINE`; if `STUB_PRCOMMENTS` is set, extracts `--body-file`/`--body`'s value from argv and appends it (delimited) to `$STUB_PRCOMMENTS` |
| anything unhandled | `unhandled ... $*` to stderr, exit 9 |

### `GH_STUB_TOOLS` subcommand routing (python face)

Every call is logged as a JSON argv array to `$STUB_CALLS_LOG` (if set) before dispatch.

| Call | Behavior |
|---|---|
| `repo view` | prints `$STUB_REPO` (default `test/repo`) |
| `api graphql` | dispatches on which canned input is present: `STUB_NODES` (set) → the board-scan org-wide `organization.projectV2.items.nodes` shape; else `STUB_ISSUE_RESPONSE` (set) → echoed verbatim (already-built promote issue-side shape); else `STUB_STATES` (set) → the tick-indexed watch-build issue-status shape (index from `$STUB_COUNTER`, default 0) |
| `api user` | prints `$STUB_WHO` (default `operator`) |
| `issue comment` | exit 1 if `STUB_COMMENT_FAIL`, else 0 |
| `project item-edit` | exit 1 if `STUB_EDIT_FAIL`, else 0 |
| `pr list` | the watch-build tick: reads `$STUB_STATES`/`$STUB_COUNTER`, prints an open-PR array if the current tick's `pr_open` is set, then advances the counter |
| `issue view` | prints `{"comments": $STUB_COMMENTS}` (default `[]`) |
| anything unhandled | exit 9, no output |

## Scope note

Slice 1 of the 19-harness-seam epic (issue #243) relocated the classifier and this contract doc, and
retired the two hand-typed classifier re-implementations in `tests/test_shadow_review.py`. Slice 2
(issue #244) finished the job: `CLAUDE_STUB_JSON` moved here alongside `CLAUDE_STUB`, and every other
private stub that used to live beside it in `tests/test_dev_runner.py` (`REAP_CLAUDE_STUB`,
`SIGNAL_CLAUDE_STUB`, `LINT_CLAUDE_STUB`) is gone — their behavior is now either a mode of `CLAUDE_STUB`
itself (the crash mode, the process-reap hook, the lint-repair arm — all above) or, where a suite needs
its own extra observation (e.g. `tests/test_dev_runner_roles.py`'s model-recording stub,
`tests/test_dev_runner_review_bundle.py`'s bundle-snapshot stub), a variant derived from `CLAUDE_STUB` via
`.replace()` — locating an arm to splice into, never retyping the classifier. No private clone of the
classifier remains anywhere in the suite.

Slice 3 (issue #245) did the same for `gh`: the eight independent `gh` stub definitions across
`test_dev_runner.py` (two), `test_autonomous_merge.py`, `test_ci_registration_grace.py`,
`test_dev_runner_reevaluate.py`, `test_board.py`, `test_promote.py`, and `test_watch_build.py` are gone,
replaced by the two faces documented above. No private clone of a `gh` fake remains anywhere in the
suite.
