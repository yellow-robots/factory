# The harness contract

`tests/harness/` is the shared home for the pytest suite's fake `claude` CLI: one stage-aware stub
(`claude_fake.py`'s `CLAUDE_STUB`) whose classifier is the only legal way a test recognizes which stage
of `tools/dev-runner.sh` is currently running. This doc is the authoritative surface for that contract —
the flag families it exposes, how the runner's prompt reaches it, and how it tells one stage from
another. It documents `STUB_*` behavior as it exists; changing what a flag does is out of scope for the
slice that added this doc (issue #243).

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
| `*"tests FAIL"*` | check-repair | the check gate's own repair loop |
| (no match) | implement | the default arm |

These five literals are exactly the ones `tools/dev-runner.sh` bakes into its own per-stage prompts.
`tests/harness/test_claude_fake_contract.py::test_runner_prompts_contain_stub_markers` pins them against
the runner's source directly — if a prompt literal is ever dropped from `tools/dev-runner.sh`, that guard
fails loudly rather than letting the stub silently misclassify a stage as `implement`.

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

### Shared timeline

`STUB_TIMELINE` is not a flag but the shared recorder: every arm appends its own stage token (`IMPL`,
`TEST`, `REPAIR`, `REVIEW`, `REVIEWFIX`) to this file, in call order — the primitive every ordering
assertion in the consuming suites is built on.

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

## Scope note

Slice 1 of the 19-harness-seam epic (issue #243) relocates the classifier and this contract doc, and
retires the two hand-typed classifier re-implementations in `tests/test_shadow_review.py`. It
deliberately leaves the JSON-envelope variant (`CLAUDE_STUB_JSON`) and the other derived/private stubs
(`REAP_CLAUDE_STUB`, `SIGNAL_CLAUDE_STUB`, `LINT_CLAUDE_STUB`) in `tests/test_dev_runner.py` — those
migrate in a later slice.
