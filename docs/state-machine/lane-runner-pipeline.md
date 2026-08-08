<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The dev-runner build pipeline

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `Ready` | The lane's entry state: the task is admitted for autonomous build. Consumed by the runner, never set by it. | GitHub Projects v2 single-select `Status` field on the ISSUE's project item (project #1). Option id `c85eb5c1`, env-overridable via OPT_READY. | `tools/board_plumbing.py:64-71` |
| `dispatched (in flight, no board change)` | n8n POSTed the issue to /build and dispatch spawned a detached runner. Nothing durable on the board records this; the task is still Ready until the runner claims. | Host filesystem only: the per-run capture log `$DEV_RUNNER_HOME/runs/dispatch-<issue>-<epoch_ms>.log`, plus the held flocks `dispatch-<owner>--<name>.lock` and `capslot-<i>.lock` in the lock home. | `tools/dispatch.py:224-232` |
| `stood down (lock busy)` | The repo already has a build in flight, or all DISPATCH_MAX_BUILDS capacity slots are taken. The composed command exits 0 politely; the task waits for the next poll tick. | Nowhere durable — only the exit status of the spawned flock chain, captured in the dispatch log. | `tools/dispatch.py:120-137` |
| `In Progress (claimed)` | The runner has claimed the task; the claim drops it off the Ready poll. This is the state for the whole build. | Projects `Status` field, option id `14e415a3` / OPT_INPROGRESS. Written by tools/board_plumbing.py `set-field`. | `tools/dev-runner.sh:1154` |
| `worktree cut` | A fresh git worktree on branch `task/<issue>-<slug>`, cut from WT_CUT_REF (the manifest's pinned sha when base_ref == manifest ref, else BASE_REF). | `$DEV_RUNNER_HOME/wt/<owner>--<name>--task-<issue>-<slug>` on the host, plus a local branch `task/<issue>-<slug>` in $BASE_REPO's git dir. | `tools/dev-runner.sh:1192-1195, tools/dev-runner.sh:1267` |
| `stage-completion checkpoints` | Per-repo+branch durable markers for the five checkpointed stages: 01-implement, 02-test, 03-check, 04-review, 05-commit. A stage with a marker is skipped on a resume. | Empty files `$DEV_RUNNER_HOME/state/<repo-slug>--<branch-slug>/NN-<stage>.done`. | `tools/dev-runner.sh:1195-1198` |
| `env-hold (preserved, resumable)` | An environmental failure (toolchain 126/127, LLM quota signature, PR-stage remote-write exhaustion). Worktree + markers + run dir are PRESERVED; the board carries Reason=Blocked; Status stays In Progress. | Marker file `$STATE_DIR/env-hold` + resume manifest `$STATE_DIR/run.json`, plus Projects `Reason` = Blocked (`fe4d566c` / OPT_BLOCKED) and an issue comment. | `tools/dev-runner.sh:1196, tools/dev-runner.sh:1222-1239` |
| `Blocked (hard, torn down)` | A code/machinery failure. Reason=Blocked + an issue comment; the worktree, branch and stage markers are destroyed after a best-effort salvage patch. Status remains In Progress. | Projects `Reason` field = Blocked; an issue comment; salvage artifacts in the run dir (`block-salvage.patch`, and where applicable `final.patch`, `boundary-violation.diff`, `escalation-residual.diff`). | `tools/dev-runner.sh:1166-1171, tools/dev-runner.sh:1202-1219` |
| `Needs-info (bounced)` | A pre-claim content/config/model refusal. Status is driven back to Backlog and Reason set to Needs-info, with a comment naming every reason concatenated. | Projects `Status` = Backlog (`b863a902` / OPT_BACKLOG) + `Reason` = Needs-info (`803a86fb` / OPT_NEEDSINFO); an issue comment; a `yr-ledger-row/1` row with outcome.type = needs-info. | `tools/dev-runner.sh:1129-1135` |
| `gate-refused (no writes)` | A DoR refusal that writes nothing at all: issue not OPEN, not on the board, Status != Ready, or a typed-but-wrong Issue Type. Exit code 3. | Nowhere durable. Only stderr, captured in the dispatch per-run log. | `tools/dev-runner.sh:85, tools/dev-runner.sh:971-990` |
| `pre-claim environmental die` | An environmental failure BEFORE the claim (run-start fetch fail/timeout, issue fetch failure, project item-list failure). Exit 1, no board write; the task stays Ready for the next poll. | Nowhere durable — stderr into the dispatch log only. | `tools/dev-runner.sh:84, tools/dev-runner.sh:690-693, tools/dev-runner.sh:868-869, tools/dev-runner.sh:952-953` |
| `PR open (In Review)` | The build produced a PR and the terminal merge step did not merge. The lane's normal success terminus for a non-armed repo. | A GitHub PR (branch `task/<issue>-<slug>`, body `Closes #<issue>`); Projects `Status` = In Review (`da2e6a49` / OPT_INREVIEW); the PR trail carries the reviewer verdict, usage summary, and a `YR-MERGE-SHADOW` record. | `tools/dev-runner.sh:2287-2289, tools/dev-runner.sh:2577` |
| `In Review + Reason=Blocked (armed block)` | An armed repo's merge evaluator refused (sentinel, a failed condition, server_ci_none_armed, or the unrecoverable-rewrite case). Reason=Blocked is set inside armed_block; Status is then set In Review at the shared terminus. | Projects `Reason` = Blocked; Projects `Status` = In Review; a `YR-MERGE: BLOCKED — <reason>` PR comment; an issue comment. | `tools/dev-runner.sh:2429-2438, tools/dev-runner.sh:2576-2578` |
| `merged by the factory` | An armed repo, all conditions passing: the runner squash-merged the PR. Status is deliberately NOT set to In Review — the merge supersedes it and native close→Done finishes the lifecycle. | PR merged (squash); a durable `YR-MERGE: MERGED` PR comment carrying the merge commit; Projects `Status` still In Progress until GitHub's close→Done automation fires. | `tools/dev-runner.sh:2551-2562, tools/dev-runner.sh:2573-2575` |
| `Done` | Terminal. Set by GitHub Projects' built-in close→Done automation when the PR (`Closes #N`) merges. No factory code writes it. | Projects `Status` = Done (`e614f531` / OPT_DONE), written by native GitHub automation. | `docs/rfcs/0003-task-state-model.md:41` |
| `stranded claim` | Status=In Progress with an empty Reason, older than STRANDED_AFTER_MIN (default 45 min), with no live build lock for that repo and no open task PR — a hard runner death that left the claim. | Detected off the board's own `status.updatedAt`; the raise writes Projects `Reason` = Blocked and a `YR-EPIC-GATE: stranded claim` issue comment. | `tools/epic_gate.py:280-306, tools/epic_gate.py:95` |
| `run artifacts (per-pid)` | The forensic surface of one invocation: stage logs, transcripts, usage files, the review bundle, diffs, gate durations, merge record bodies. | `$DEV_RUNNER_HOME/runs/<issue>-<pid>/` — implement.log, test.log, checks.log, lint.log, lens.md/lens.log, review.md, repair.log, lint-repair.log, review-repair.log, transcript-<stage>.jsonl, usage-<stage>.json, usage-summary.json, review-bundle.json, diff.patch, acceptance-criteria.txt, gate-durations.json, check-rollup.json, merge-*.md, tmp/. | `tools/dev-runner.sh:119, tools/dev-runner.sh:1184-1191` |
| `ledger row` | One `yr-ledger-row/1` per runner invocation, landed at whichever terminal branch the run reaches. Informs, never gates. | `$DEV_RUNNER_HOME/ledger/rows.jsonl`, appended under a blocking fcntl flock. | `tools/ledger.py:329-346, tools/dev-runner.sh:1105-1126` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `Ready` → `dispatched (in flight, no board change)` | n8n scheduled workflow (deploy/n8n-dispatch.json) — the poller, not the factory | **prevented** | deploy/n8n-dispatch.json — the Code node's two .filter() calls, before the POST node |
| 2 | `dispatched (in flight, no board change)` → `runner process spawned` | dispatch service (tools/dispatch.py, systemd user unit `dispatch` on yr-host) | **prevented** | tools/dispatch.py do_POST (:260-277) and build_task (:215-232) — all validation precedes the spawn |
| 3 | `runner process spawned` → `stood down (lock busy)` | flock (the composed shell command), not the runner | **prevented** | tools/dispatch.py::_compose_build_cmd — `flock -n -E 200` |
| 4 | `runner process spawned` → `pre-claim environmental die` | dev-runner | **prevented** | tools/dev-runner.sh:690-693 (fetch), :868-869 (issue read), :952-953 (project read) |
| 5 | `Ready` → `gate-refused (no writes)` | dev-runner (DoR gate) | **prevented** | tools/dev-runner.sh:971-990 — reachable on the dispatch path, before claim |
| 6 | `Ready` → `Needs-info (bounced)` | dev-runner (DoR content/config/model gate) | **prevented** | tools/dev-runner.sh:1000-1010 (accumulation) and :1129-1135 (disposal) — before claim, before any worktree, before any LLM |
| 7 | `Ready` → `In Progress (claimed)` | dev-runner | ⚠️ **unenforced** | none — the claim is an unconditional write once the gates pass; there is NO second read of Status between the read at :951-962 and the write at :1154 |
| 8 | `In Progress (claimed)` → `worktree cut` | dev-runner | **prevented** | tools/dev-runner.sh:1245-1268 |
| 9 | `env-hold (preserved, resumable)` → `worktree cut (reused) / stages skipped` | dev-runner on a fresh invocation | **prevented** | tools/dev-runner.sh:1245-1261 |
| 10 | `worktree cut` → `implement stage complete (01-implement.done)` | dev-runner spawning one cold `claude -p` (the IMPLEMENTER stage) | *partial* | tools/dev-runner.sh run_stage (:1475-1534) — the process-group reap and archive are unconditional per call |
| 11 | `implement stage running` → `Blocked (hard, torn down)` | dev-runner | **prevented** | tools/dev-runner.sh:1620-1645 |
| 12 | `implement stage complete` → `test stage complete (02-test.done)` | dev-runner spawning one cold `claude -p` (the TESTER stage) | detected | tools/dev-runner.sh:1682-1732 — the tester boundary guard, structural (a tree diff), not a prompt |
| 13 | `test stage running` → `Blocked (hard, torn down)` | dev-runner (tester boundary guard) | detected | tools/dev-runner.sh:1726-1732 |
| 14 | `test stage complete` → `check gate green (03-check.done)` | dev-runner — the RUNNER runs the check, never an LLM | **prevented** | tools/dev-runner.sh run_checks (:1849-1862) + _gate_monitor (:1790-1823) |
| 15 | `check gate red (code failure)` → `check gate green, or Blocked` | dev-runner + one cold `claude -p` repair stage | **prevented** | tools/dev-runner.sh:1949-1968 |
| 16 | `check gate green` → `lint tier green (or Blocked / env-hold)` | dev-runner | **prevented** | tools/dev-runner.sh:1978-2039 |
| 17 | `lint tier green` → `lens artifact written (advisory)` | dev-runner | ⚠️ **unenforced** | none — advisory by construction |
| 18 | `any stage/gate` → `env-hold (preserved, resumable)` | dev-runner | **prevented** | tools/dev-runner.sh env_hold_record (:1232-1239), env_hold (:1933-1936), lint_env_hold (:1941-1944), llm_quota_hold (:1303-1306), pr_stage_hold (:2280-2284) |
| 19 | `check/lint/lens complete` → `review bundle initialised` | dev-runner | **prevented** | tools/dev-runner.sh:2080-2086 |
| 20 | `review bundle initialised` → `review APPROVEd (04-review.done)` | dev-runner spawning one cold `claude -p` (the REVIEWER stage) | **prevented** | tools/dev-runner.sh review_stage (:2112-2138) — the verdict test is the function's own exit status |
| 21 | `review REQUEST_CHANGES` → `review APPROVEd, or Blocked` | dev-runner + one cold `claude -p` review-repair stage, then a second reviewer round | **prevented** | tools/dev-runner.sh:2143-2186 |
| 22 | `review APPROVEd` → `commit made (05-commit.done)` | dev-runner (the runner owns every git write) | **prevented** | tools/dev-runner.sh:2195-2204 |
| 23 | `commit made` → `branch pushed` | dev-runner | **prevented** | tools/dev-runner.sh:2286 |
| 24 | `branch pushed` → `PR open` | dev-runner | **prevented** | tools/dev-runner.sh:2288 |
| 25 | `PR open` → `PR trail populated` | dev-runner | ⚠️ **unenforced** | none — every post is `\|\| true` / `\|\| log warn` |
| 26 | `PR open` → `In Review (shadow record posted)` | dev-runner (terminal_step, deterministic — no LLM) | **prevented** | tools/dev-runner.sh terminal_step (:2456-2563) |
| 27 | `PR open` → `merged by the factory` | dev-runner (merge evaluator inside terminal_step) | **prevented** | tools/dev-runner.sh terminal_step (:2456-2563) — every gate is in code, fail-closed |
| 28 | `PR open` → `In Review + Reason=Blocked (armed block)` | dev-runner (armed_block) | **prevented** | tools/dev-runner.sh armed_block (:2429-2438) |
| 29 | `terminal step` → `terminal step abandoned (environmental)` | dev-runner | ⚠️ **unenforced** | tools/dev-runner.sh:2566-2571 |
| 30 | `any terminus` → `run closed out` | dev-runner | ⚠️ **unenforced** | none — all fail-soft |
| 31 | `In Progress (claimed)` → `stranded claim raised (Reason=Blocked)` | epic-gate sweep (tools/epic_gate.py, fired by dispatch's POST /sweep on its own lock) | detected | tools/epic_gate.py::_is_stranded (:280-297) |
| 32 | `Blocked / env-hold / Needs-info` → `Ready` | human (or an attended agent running tools/promote.sh) | *partial* | tools/promote.sh:55-63 (refuse gate) — on the unmerged slice-5 branch an additional tools/wall.py promote-check runs at :67-70 |
| 33 | `PR open (any prior record state)` → `terminal decision re-posted` | attended agent / human, invoking `dev-runner.sh <issue#> --repo <r> --re-evaluate <pr#>` | **prevented** | tools/dev-runner.sh re_evaluate (:474-672) — every refusal is reeval_refuse, exit 3, before any write |
| 34 | `Ready` → `resolved plan printed (no state change)` | attended agent / human, invoking `--dry-run` | **prevented** | tools/dev-runner.sh:1137-1151 |
| 35 | `stage running` → `stage process group reaped` | dev-runner (run_stage) | *partial* | tools/dev-runner.sh run_stage (:1518-1533) — reachable on every stage, but only DISPOSED by implement/test |
| 36 | `stage running` → `stage forbidden-act performed` | a `claude -p` stage (implementer / tester / repair / reviewer) | ⚠️ **unenforced** | tester only: tools/dev-runner.sh:1682-1732. For every other forbidden act there is no guard on the path the stage takes |

### Detail

#### 1. `Ready` → `dispatched (in flight, no board change)`

`T1`

- **Actor:** n8n scheduled workflow (deploy/n8n-dispatch.json) — the poller, not the factory
- **Trigger:** Schedule tick, every 2 minutes
- **Enforcement:** **prevented** · **Guard site:** deploy/n8n-dispatch.json — the Code node's two .filter() calls, before the POST node
- **Preconditions:** The project item's Status.name == 'Ready' `[code+canon: deploy/n8n-dispatch.json > Extract Ready issue numbers (Code node)]`<br>The issue's content.state == 'OPEN' `[code+canon: deploy/n8n-dispatch.json > Extract Ready issue numbers (Code node)]`<br>The issue's Issue Type is NOT 'Feature' or 'Epic' (EPIC_TYPES filter) — a Bug or an untyped item is NOT filtered out `[code: deploy/n8n-dispatch.json > Extract Ready issue numbers (Code node)]`
- **Postconditions:** One POST /build {issue, repo} per surviving item, bearer-authenticated `[code+canon: deploy/DISPATCH.md > 3. n8n workflow]`

#### 2. `dispatched (in flight, no board change)` → `runner process spawned`

`T2`

- **Actor:** dispatch service (tools/dispatch.py, systemd user unit `dispatch` on yr-host)
- **Trigger:** HTTP POST /build
- **Enforcement:** **prevented** · **Guard site:** tools/dispatch.py do_POST (:260-277) and build_task (:215-232) — all validation precedes the spawn
- **Records:** `dispatch-<issue>-<epoch_ms>.log`
- **Preconditions:** Authorization header equals 'Bearer $DISPATCH_TOKEN', compared with hmac.compare_digest; an unset token refuses everything `[code: tools/dispatch.py:261-264]`<br>issue is an ASCII decimal string `[code: tools/dispatch.py:216-217]`<br>repo is present and matches ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ — fail-closed, there is no default repo `[code+canon: tools/dispatch.py:219-222]`
- **Postconditions:** A detached (start_new_session) child runs `flock -n <repo lock> bash -c '<per-slot flock chain>'`; the runner argv is [DEV_RUNNER, issue, --repo, repo] `[code: tools/dispatch.py:120-137, tools/dispatch.py:228-231]`<br>The child's environment is the ALLOWLIST only (_ENV_ALLOW_KEYS + LC_/STUB_/YR_POOL_ prefixes), never dispatch's own environ — DISPATCH_TOKEN can never reach a stage `[code+canon: tools/dispatch.py:147-183]`<br>stdout+stderr are redirected into `runs/dispatch-<issue>-<epoch_ms>.log`, opened by dispatch before the spawn so a hard kill still leaves the prefix `[code: tools/dispatch.py:200-204]`<br>HTTP 202 returned immediately; the build's fate is invisible to n8n `[code+canon: tools/dispatch.py:277]`

#### 3. `runner process spawned` → `stood down (lock busy)`

`T3`

- **Actor:** flock (the composed shell command), not the runner
- **Trigger:** The target repo's own lock is held, or every capslot-<i>.lock is held
- **Enforcement:** **prevented** · **Guard site:** tools/dispatch.py::_compose_build_cmd — `flock -n -E 200`
- **Preconditions:** repo lock acquired OUTERMOST — a busy repo consumes no capacity slot `[code+canon: tools/dispatch.py:120-137]`<br>DISPATCH_MAX_BUILDS slots (default 2; any unset/non-integer/<1 value silently falls back to 2) `[code+canon: tools/dispatch.py:78-90]`
- **Postconditions:** Exit 0 — a polite no-op; the task waits for the next tick, never dropped, never retried on another slot `[code+canon: tools/dispatch.py:130-137]`<br>A runner exiting with exactly 200 is remapped to 201 so it can never be misread as lock-busy `[code: tools/dispatch.py:74-75, tools/dispatch.py:130]`

#### 4. `runner process spawned` → `pre-claim environmental die`

`T4`

- **Actor:** dev-runner
- **Trigger:** The run-start `git fetch origin` on the base checkout fails or exceeds MANIFEST_FETCH_TIMEOUT (default 15s); or the issue read fails; or the board-wide `gh project item-list` read fails
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:690-693 (fetch), :868-869 (issue read), :952-953 (project read)
- **Preconditions:** The base checkout is a git repo with an `origin` remote (otherwise the fetch is SKIPPED, not environmental) `[code: tools/dev-runner.sh:690]`
- **Postconditions:** die() — exit 1, NO board write, NO comment, NO ledger row; the task stays Ready for the next poll `[code: tools/dev-runner.sh:84, tools/dev-runner.sh:691-692]`

#### 5. `Ready` → `gate-refused (no writes)`

`T5`

- **Actor:** dev-runner (DoR gate)
- **Trigger:** The gate block runs before any LLM call and before any write
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:971-990 — reachable on the dispatch path, before claim
- **Preconditions:** Refuses when: issue state != OPEN; ITEM_ID empty (not on project #PROJECT_NUMBER); ITEM_STATUS != 'Ready'; or ITYPE is non-empty and case-insensitively != REQUIRE_ISSUE_TYPE (default 'Task') `[code: tools/dev-runner.sh:972-990]`<br>REQUIRE_ISSUE_TYPE='' (the no-colon default form) is a true opt-out for repos without Issue Types `[code+canon: tools/dev-runner.sh:63-65]`
- **Postconditions:** gate() — exit code 3, nothing written anywhere, no ledger row `[code: tools/dev-runner.sh:85]`<br>A typed-but-wrong item deliberately stays Ready 'for the epic-gate sweeper' `[code: tools/dev-runner.sh:980-981]`

#### 6. `Ready` → `Needs-info (bounced)`

`T6`

- **Actor:** dev-runner (DoR content/config/model gate)
- **Trigger:** Any of the accumulated NEEDS_INFO reasons is non-empty after the DoR gate passes
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1000-1010 (accumulation) and :1129-1135 (disposal) — before claim, before any worktree, before any LLM
- **Records:** `issue comment: 'dev-runner: bounced to **Needs-info** — …'`, `yr-ledger-row/1 with outcome.type=needs-info`
- **Preconditions:** No `.yr/factory.toml` at the manifest ref NOR in the working tree — the admission wall / un-onboarded repo `[code+canon: tools/dev-runner.sh:712-718]`<br>The `## Acceptance criteria` block (heading to next equal-or-higher heading) has no alphanumeric content `[code+canon: tools/dev-runner.sh:992-1002]`<br>The issue carries NO Issue Type at all (untyped Ready items bounce rather than gate, to avoid starving the board) `[code: tools/dev-runner.sh:983-990]`<br>manifest `check_cmd` undeclared — required-ness judged on the manifest ALONE, regardless of any env CHECK_CMD `[code+canon: tools/dev-runner.sh:743-749]`<br>manifest `test_paths` / `artifact_globs` declared but malformed (not a non-empty array of non-empty, relative, non-`..` strings) `[code+canon: tools/dev-runner.sh:750-763]`<br>manifest `check_timeout` / `check_idle_timeout` declared but not a positive integer `[code+canon: tools/dev-runner.sh:814-858]`<br>manifest `stage_conduct` malformed, or containing one of the four routed stub literals (TESTER, REVIEWER, 'tests FAIL', 'REQUESTED CHANGES') `[code+canon: tools/dev-runner.sh:775-788]`<br>A build or review model name from the task body or manifest is not in models.toml (R_STATUS=unknown) `[code+canon: tools/dev-runner.sh:1069-1074]`<br>A ranked pair that is cross-provider, or inverted (review rank < build rank) `[code+canon: tools/dev-runner.sh:1075-1081]`<br>A Type=Task issue with NO native sub-issue parent lacking a well-formed `YR-TASK-GATES` comment (marker line exactly equal after rstrip; non-empty review:/fit:/who:; fit: not a placeholder) `[code+canon: tools/dev-runner.sh:885-949]`
- **Postconditions:** Status=Backlog, Reason=Needs-info, an issue comment naming every reason, a ledger row (needs-info), exit 3 `[code: tools/dev-runner.sh:1129-1135]`<br>Under --dry-run this is a bare gate() — read-only, no writes `[code: tools/dev-runner.sh:1130]`

#### 7. `Ready` → `In Progress (claimed)`

`T7`

- **Actor:** dev-runner
- **Trigger:** The DoR gate and all content/model gates passed and --dry-run is off
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — the claim is an unconditional write once the gates pass; there is NO second read of Status between the read at :951-962 and the write at :1154
- **Records:** `run log line: 'claimed #<issue> -> In Progress, branch <branch>, build=… review=…'`
- **Preconditions:** Every T5/T6 precondition satisfied `[code: tools/dev-runner.sh:1129-1151]`
- **Postconditions:** Status=In Progress via tools/board_plumbing.py set-field (a failed write only WARNS, never aborts) `[code: tools/dev-runner.sh:966, tools/dev-runner.sh:1154]`<br>A stale Reason of value Blocked or Needs-info is cleared — by VALUE, never by writer; any other Reason value is left untouched `[code: tools/dev-runner.sh:1155-1160]`<br>From here on, every failure sets Reason=Blocked and comments before exiting `[code+canon: tools/dev-runner.sh:1163-1171]`

#### 8. `In Progress (claimed)` → `worktree cut`

`T8`

- **Actor:** dev-runner
- **Trigger:** No valid env-hold state exists for this repo+branch
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1245-1268
- **Preconditions:** NOT (HOLD_MARKER present AND $WT exists AND refs/heads/<branch> exists) `[code: tools/dev-runner.sh:1245-1246]`
- **Postconditions:** Stale STATE_DIR removed; `git fetch origin` (failure → fail_blocked); any wedged prior worktree force-removed; the branch force-deleted; `git worktree add -q -b <branch> $WT $WT_CUT_REF` `[code: tools/dev-runner.sh:1262-1268]`<br>WT_CUT_REF is the manifest's PINNED SHA whenever BASE_REF == MANIFEST_REF — one freshness moment for config and code; otherwise the (freshened) BASE_REF name `[code+canon: tools/dev-runner.sh:790-798]`<br>A failed worktree add → fail_blocked 'worktree add failed' `[code: tools/dev-runner.sh:1267]`

#### 9. `env-hold (preserved, resumable)` → `worktree cut (reused) / stages skipped`

`T9`

- **Actor:** dev-runner on a fresh invocation
- **Trigger:** A human re-sets Status=Ready and the next dispatch tick fires a new runner
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1245-1261
- **Records:** `$STATE_DIR/run.json (branch, base_ref, build_id, review_id, worktree, run_dir)`
- **Preconditions:** HOLD_MARKER file present AND $WT exists AND the local branch exists — all three, or the state is discarded as stale `[code: tools/dev-runner.sh:1245-1246]`
- **Postconditions:** The worktree and branch are reused; every stage with an NN-<stage>.done marker is skipped `[code+canon: tools/dev-runner.sh:1246-1247, tools/dev-runner.sh:1613-1614, :1666-1667, :1945-1946, :2140-2141, :2195-2196]`<br>checks.log and review.md are copied forward from the PRIOR run dir named in run.json, since the new RUN_DIR is per-pid `[code: tools/dev-runner.sh:1253-1261]`<br>On a resume past 05-commit, BASE_SHA is re-derived as HEAD^ rather than HEAD `[code: tools/dev-runner.sh:2071-2075]`

#### 10. `worktree cut` → `implement stage complete (01-implement.done)`

`T10`

- **Actor:** dev-runner spawning one cold `claude -p` (the IMPLEMENTER stage)
- **Trigger:** stage_done 01-implement is false
- **Enforcement:** *partial* · **Guard site:** tools/dev-runner.sh run_stage (:1475-1534) — the process-group reap and archive are unconditional per call
- **Records:** `$RUN_DIR/implement.log`, `$RUN_DIR/transcript-implement.jsonl`, `$RUN_DIR/usage-implement.json`
- **Preconditions:** Model: BUILD_ID — resolved per-task body `model:` > manifest `model` > registry roles.build, with BUILD_MODEL env atop all three (a raw unregistered id runs UNRANKED and loudly warned, never bounced) `[code+canon: tools/dev-runner.sh:1039-1064]`<br>allowedTools = 'Read Edit Write Bash'; --permission-mode bypassPermissions; --effort $EFFORT (default high); --setting-sources project --strict-mcp-config; --output-format json `[code: tools/dev-runner.sh:1486-1500]`<br>The task prompt travels on STDIN, never argv (issue #121's channel contract) `[code+canon: tools/dev-runner.sh:1482-1485, tools/dev-runner.sh:1509-1516]`<br>The CLI runs as leader of its OWN process group via `exec setsid` `[code: tools/dev-runner.sh:1502-1517]`<br>System prompt = IMPL_SYS + STAGE_CHARTER (appended by run_stage for every stage, in every target repo) `[code+canon: tools/dev-runner.sh:1481, tools/dev-runner.sh:1609-1612]`
- **Postconditions:** `git add -A` then `write-tree` records IMPL_TREE — the structural checkpoint the tester boundary guard diffs against `[code: tools/dev-runner.sh:1647-1651]`<br>The stage's transcript is archived (transcript-implement.jsonl) and scanned by bg_scan BEFORE usage capture rewrites the log `[code: tools/dev-runner.sh:1340-1392, tools/dev-runner.sh:1526-1527]`<br>usage-implement.json written on a clean exit (rc 0 and no CLAUDE_OUTPUT_FORMAT override); the log is rewritten in place to the envelope's plain `.result` text `[code: tools/dev-runner.sh:1402-1410, tools/stage_usage.py:83-92]`<br>mark_stage 01-implement `[code: tools/dev-runner.sh:1651]`

#### 11. `implement stage running` → `Blocked (hard, torn down)`

`T11`

- **Actor:** dev-runner
- **Trigger:** Any of: non-zero stage exit; a live process-group member past STAGE_GROUP_GRACE; an unresolved background-task conversion in the archived transcript; a `STAGE-BLOCKED: <reason>` last line
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1620-1645
- **Records:** `issue comment: 'dev-runner: **Blocked** — …'`, `$RUN_DIR/block-salvage.patch`, `$RUN_DIR/escalation-residual.diff`, `yr-ledger-row/1 outcome.type=blocked`
- **Preconditions:** rc != 0 AND the log matches QUOTA_SIGNATURES AND the group was NOT refused → llm_quota_hold instead (env-hold, T18b) `[code+canon: tools/dev-runner.sh:1628, tools/dev-runner.sh:1295-1306]`<br>LAST_STAGE_BG_UNRESOLVED==1 (positive, session-attributed evidence only: archive status==archived AND method==session_id) `[code+canon: tools/dev-runner.sh:1367-1391, tools/bg_scan.py:190-201]`<br>stage_blocked_reason fires only when the log's LAST non-empty line is exactly `STAGE-BLOCKED: <non-empty reason>` — deliberately stricter than verdict_line `[code+canon: tools/dev-runner.sh:1557-1575]`
- **Postconditions:** fail_blocked: Reason=Blocked, an issue comment quoting the cause, a ledger row (blocked), salvage_wt writes block-salvage.patch, cleanup_wt tears down worktree+branch+markers, die (exit 1) `[code: tools/dev-runner.sh:1166-1171]`<br>For a STAGE-BLOCKED escalation the residual diff (vs the branch point) is preserved as escalation-residual.diff and the block message states the tree state `[code: tools/dev-runner.sh:1586-1595, tools/dev-runner.sh:1639-1645]`<br>Status STAYS 'In Progress' — no code moves it back to Ready or to any other Status `[code: tools/dev-runner.sh:1166-1171]`

#### 12. `implement stage complete` → `test stage complete (02-test.done)`

`T12`

- **Actor:** dev-runner spawning one cold `claude -p` (the TESTER stage)
- **Trigger:** stage_done 02-test is false
- **Enforcement:** detected · **Guard site:** tools/dev-runner.sh:1682-1732 — the tester boundary guard, structural (a tree diff), not a prompt
- **Records:** `$RUN_DIR/test.log`, `$RUN_DIR/transcript-test.jsonl`, `$RUN_DIR/usage-test.json`
- **Preconditions:** Model: BUILD_ID (the build role runs implement/test/repairs) `[code+canon: tools/dev-runner.sh:1478, skills/factory/references/pipeline.md > Model roles — the registry]`<br>TEST_SYS names the resolved write surface: the default wording says 'the repo-root tests/ directory'; the manifest-declared wording names TEST_SURFACE_STR — the charter and the guard judge the SAME surface `[code+canon: tools/dev-runner.sh:1658-1665]`
- **Postconditions:** `git add -A` + write-tree → TESTER_TREE; the guard diffs IMPL_TREE→TESTER_TREE by name `[code: tools/dev-runner.sh:1684-1686]`<br>Offenders = changed paths NOT under any directory-anchored TEST_PATHS prefix AND not matching any ARTIFACT_GLOBS pattern (directory-globs match any path component; bare globs match the basename) `[code+canon: tools/dev-runner.sh:1695-1725]`<br>mark_stage 02-test `[code: tools/dev-runner.sh:1746]`

#### 13. `test stage running` → `Blocked (hard, torn down)`

`T13`

- **Actor:** dev-runner (tester boundary guard)
- **Trigger:** TESTER_OFFENDERS non-empty, or the same rc/refusal/bg/STAGE-BLOCKED family as T11
- **Enforcement:** detected · **Guard site:** tools/dev-runner.sh:1726-1732
- **Records:** `$RUN_DIR/boundary-violation.diff`, `issue comment naming offenders + surface + source`
- **Preconditions:** The boundary guard runs BEFORE the STAGE-BLOCKED check — a boundary violation takes priority `[code: tools/dev-runner.sh:1734-1744]`
- **Postconditions:** boundary-violation.diff (the full IMPL_TREE→TESTER_TREE diff) is written before teardown; no auto-revert `[code+canon: tools/dev-runner.sh:1726-1732]`<br>The block message names the offenders AND the resolved surface and its source (manifest\|default) `[code+canon: tools/dev-runner.sh:1731]`

#### 14. `test stage complete` → `check gate green (03-check.done)`

`T14`

- **Actor:** dev-runner — the RUNNER runs the check, never an LLM
- **Trigger:** stage_done 03-check is false
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh run_checks (:1849-1862) + _gate_monitor (:1790-1823)
- **Records:** `$RUN_DIR/checks.log`, `$RUN_DIR/gate-durations.json`, `issue comment (live-gate advisory) only when CHECK_TIMEOUT elapses with output flowing`
- **Preconditions:** CHECK_CMD resolved once at start-of-run: env CHECK_CMD > manifest check_cmd (no built-in fallback); the effective source is logged `[code+canon: tools/dev-runner.sh:799-804]`<br>Runs `cd $WT && PATH=$BASE_REPO/.venv/bin:$BASE_REPO/node_modules/.bin:$PATH GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null exec setsid bash -c "$CHECK_CMD"` — host git config neutralized so the check can never be greener than CI `[code+canon: tools/dev-runner.sh:1852]`<br>Bounded by LIVENESS: _gate_monitor polls checks.log for byte growth; no growth for CHECK_IDLE_TIMEOUT (default 300s) TERMs then KILLs the whole process group and sets _GM_EXPIRED `[code+canon: tools/dev-runner.sh:1790-1823]`<br>CHECK_TIMEOUT elapsing while output still flows fires exactly ONE advisory (run log + one issue comment) and the wait continues — it never kills, never gates `[code+canon: tools/dev-runner.sh:1814-1818]`
- **Postconditions:** An observed idle expiry appends a tail to checks.log naming idle duration, total elapsed and both windows, then disposes as a CODE failure `[code+canon: tools/dev-runner.sh:1856-1859]`<br>One entry appended to gate-durations.json {site, elapsed_seconds, disposition} per invocation; the file is rewritten from the FULL array every call `[code+canon: tools/dev-runner.sh:1832-1848]`<br>mark_stage 03-check (after lint and lens tiers) `[code: tools/dev-runner.sh:2060]`

#### 15. `check gate red (code failure)` → `check gate green, or Blocked`

`T15`

- **Actor:** dev-runner + one cold `claude -p` repair stage
- **Trigger:** CHECK_RC != 0 and not 126/127
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1949-1968
- **Records:** `$RUN_DIR/repair.log`, `$RUN_DIR/checks.log (overwritten by the re-run)`
- **Preconditions:** Exactly ONE repair attempt `[code+canon: tools/dev-runner.sh:1951-1954]`<br>Repair model = CHECK_REPAIR_ID = the registry's roles.stage_tiers.check_repair when set, else BUILD_ID — models.toml declares NO stage_tiers, so today it is BUILD_ID `[code: tools/dev-runner.sh:1084-1090, models.toml:37-39]`<br>The repair prompt is tests-frozen: 'Fix the PRODUCTION CODE so they pass — do NOT modify the tests' and carries only the last 40 lines of checks.log `[code+canon: tools/dev-runner.sh:1954]`
- **Postconditions:** check_cmd is re-run at site `check-repair-recheck`; a still-red re-check → fail_blocked `[code: tools/dev-runner.sh:1957-1966]`<br>An unresolved background task at the repair's own stage end blocks EVEN a green re-check (the kill window overlaps it) `[code+canon: tools/dev-runner.sh:1959-1967]`<br>A 126/127 on either check run → env_hold (preserve+resume), never an LLM repair `[code+canon: tools/dev-runner.sh:1950, tools/dev-runner.sh:1958, tools/dev-runner.sh:1926-1936]`

#### 16. `check gate green` → `lint tier green (or Blocked / env-hold)`

`T16`

- **Actor:** dev-runner
- **Trigger:** LINT_CMD non-empty (env LINT_CMD > manifest lint_cmd; absent = off, byte-identical to no tier)
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1978-2039
- **Records:** `$RUN_DIR/lint.log`, `$RUN_DIR/lint-repair.log`, `gate-durations.json entries: lint, lint-fix, lint-autofix-recheck, lint-repair-recheck`
- **Preconditions:** Runs only AFTER check_cmd passes; the command is OPAQUE, run verbatim, no output parsing `[code+canon: tools/dev-runner.sh:1970-1982, tools/dev-runner.sh:1889-1902]`<br>Ruled repair scope: (1) deterministic LINT_FIX_CMD autofix, no LLM; (2) at most ONE LLM repair confined to the lint-flagged files, at CHECK_REPAIR_ID `[code+canon: tools/dev-runner.sh:1986-2010]`<br>126/127 on lint or autofix → lint_env_hold naming the LINT command and lint.log, never check_cmd's text `[code+canon: tools/dev-runner.sh:1937-1944]`
- **Postconditions:** LINT_MUTATED is a before/after tree_hash comparison, applied around BOTH the autofix and the LLM repair; tree_hash fails SAFE (an `add -A` failure emits a unique sentinel so the comparison differs) `[code+canon: tools/dev-runner.sh:1868-1887, tools/dev-runner.sh:1988-2009]`<br>Only when LINT_MUTATED==1 are check_cmd and lint_cmd re-run (the expensive half); the lint verdict and the bg verdict are enforced UNCONDITIONALLY below the branch `[code+canon: tools/dev-runner.sh:2012-2038]`<br>A still-red lint → fail_blocked `[code: tools/dev-runner.sh:2031]`

#### 17. `lint tier green` → `lens artifact written (advisory)`

`T17`

- **Actor:** dev-runner
- **Trigger:** LENS_CMD non-empty
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — advisory by construction
- **Records:** `$RUN_DIR/lens.md`, `$RUN_DIR/lens.log`, `gate-durations.json entry: lens`
- **Preconditions:** Runs only after check_cmd (and lint_cmd when declared) both pass `[code+canon: tools/dev-runner.sh:2041-2049]`<br>stdout→lens.md and stderr→lens.log are SEPARATE (never the merged 2>&1 of the other two runners), so a stderr traceback can never land in the PR comment; YR_BASE_REF is exported so a lens can be diff-aware `[code+canon: tools/dev-runner.sh:1911-1920]`
- **Postconditions:** The exit code is READ but NEVER gates — a non-zero exit (126/127 and an idle expiry included) appends one legible line to lens.md and the run's terminal state is identical to a passing lens `[code+canon: tools/dev-runner.sh:2050-2058]`

#### 18. `any stage/gate` → `env-hold (preserved, resumable)`

`T18`

- **Actor:** dev-runner
- **Trigger:** An environmental failure: check/lint exit 126 or 127; a `claude -p` stage whose log matches QUOTA_SIGNATURES; or PR-stage remote-write retries exhausted
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh env_hold_record (:1232-1239), env_hold (:1933-1936), lint_env_hold (:1941-1944), llm_quota_hold (:1303-1306), pr_stage_hold (:2280-2284)
- **Records:** `$STATE_DIR/env-hold`, `$STATE_DIR/run.json`, `issue comment: 'dev-runner: **Environmental hold** …' / '**Environmental hold (quota)**' / '**Environmental hold (PR stage)**'`, `yr-ledger-row/1 outcome.type=env-hold`
- **Preconditions:** is_env_failure is exactly rc==126 or rc==127 `[code+canon: tools/dev-runner.sh:1926]`<br>QUOTA_SIGNATURES default `usage limit\|rate limit\|quota\|overloaded\|429`, checked case-insensitively against the stage log — signatures are DATA, not an exit code `[code+canon: tools/dev-runner.sh:1288-1296]`<br>A quota hold is suppressed when the stage was a process-group REFUSAL (LAST_STAGE_GROUP_REFUSED==1) `[code: tools/dev-runner.sh:1628, tools/dev-runner.sh:1675]`
- **Postconditions:** write_run_json + `: > $HOLD_MARKER` + Reason=Blocked + an issue comment marked ENVIRONMENTAL + a ledger row (env-hold) + die. cleanup_wt is deliberately NOT called `[code+canon: tools/dev-runner.sh:1228-1239]`<br>Status stays In Progress; recovery requires a human to set Status=Ready again `[code+canon: tools/dev-runner.sh:1933-1935, deploy/DISPATCH.md > Quota/rate-limit holds on the `claude -p` stages]`

#### 19. `check/lint/lens complete` → `review bundle initialised`

`T19`

- **Actor:** dev-runner
- **Trigger:** Unconditional, on every invocation — including a resume
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2080-2086
- **Records:** `$RUN_DIR/review-bundle.json`, `$RUN_DIR/diff.patch`, `$RUN_DIR/acceptance-criteria.txt`
- **Preconditions:** BASE_SHA = HEAD (or HEAD^ when 05-commit already ran in a prior invocation); HEAD_SHA = write-tree of the staged worktree `[code: tools/dev-runner.sh:2066-2076]`
- **Postconditions:** review-bundle.json holds {diff{base_sha,head_sha,patch}, acceptance_criteria, check{command,exit_code,output_tail(40)}, build, review, rounds:[]} — canonical (sorted keys, compact) so identical inputs hash identically; NO sha256 until a verdict is recorded `[code+canon: tools/review_bundle.py:38-48, tools/review_bundle.py:87-99]`<br>Assembly failure → fail_blocked 'review bundle assembly failed' `[code: tools/dev-runner.sh:2086]`

#### 20. `review bundle initialised` → `review APPROVEd (04-review.done)`

`T20`

- **Actor:** dev-runner spawning one cold `claude -p` (the REVIEWER stage)
- **Trigger:** stage_done 04-review is false
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh review_stage (:2112-2138) — the verdict test is the function's own exit status
- **Records:** `$RUN_DIR/review.md`, `$RUN_DIR/review-bundle.json (rounds + sha256)`, `$RUN_DIR/shadow-review*.md when the seat is lit`
- **Preconditions:** Model: REVIEW_ID — the review role, resolved independently of build (body `review_model:` > manifest `review_model` > registry roles.review), REVIEW_MODEL env atop `[code+canon: tools/dev-runner.sh:1063-1064, tools/dev-runner.sh:2114]`<br>allowedTools = 'Read Bash' only — no Edit, no Write `[code: tools/dev-runner.sh:2114]`<br>The gate is EXACTLY 'VERDICT: APPROVE' as the last line-anchored `^VERDICT:` line, trailing whitespace stripped — a hedge, trailing junk or a mangled token does not pass `[code+canon: tools/dev-runner.sh:328, tools/dev-runner.sh:2135-2138]`
- **Postconditions:** review_bundle record-verdict appends {index, verdict, transcript} and refreshes the bundle's sha256 over its own canonical serialization (self-excluded) `[code+canon: tools/review_bundle.py:51-75, tools/dev-runner.sh:2124-2125]`<br>shadow_review_round runs immediately after (a pure no-op unless BOTH YR_SHADOW_MODEL and YR_SHADOW_BASE_URL are set) — never wired into the gate, terminal_approval, or the evaluator `[code+canon: tools/dev-runner.sh:2100-2110]`<br>An unresolved background task in the REVIEWER's own transcript returns 1 — 'not a clean APPROVE' — routing into the same repair path `[code: tools/dev-runner.sh:2131-2134]`<br>mark_stage 04-review `[code: tools/dev-runner.sh:2187]`

#### 21. `review REQUEST_CHANGES` → `review APPROVEd, or Blocked`

`T21`

- **Actor:** dev-runner + one cold `claude -p` review-repair stage, then a second reviewer round
- **Trigger:** review_stage returned non-zero
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2143-2186
- **Records:** `$RUN_DIR/review-repair.log`, `$RUN_DIR/final.patch`, `$RUN_DIR/review.md (overwritten by round 2)`, `usage-review-2.json`
- **Preconditions:** Exactly ONE repair attempt, at REVIEW_REPAIR_ID (registry stage tier `review_repair` when set, else BUILD_ID — today BUILD_ID, since models.toml declares no stage_tiers) `[code: tools/dev-runner.sh:1090, tools/dev-runner.sh:2148, models.toml:37-39]`<br>The repair prompt runs under IMPL_SYS with 'Read Edit Write Bash' and is bounded to 'production code; only touch a test if the test itself is wrong' `[code+canon: tools/dev-runner.sh:2148]`
- **Postconditions:** final.patch is captured BEFORE the re-check, regardless of the repair's own exit status — a crashed repair's partial edits are exactly what salvage wants `[code+canon: tools/dev-runner.sh:2151-2161]`<br>check_cmd is re-run (site review-repair-recheck); when LINT_CMD is declared, lint is re-run too (site review-repair-lint) — either failing → fail_blocked `[code+canon: tools/dev-runner.sh:2164-2173]`<br>A second REQUEST_CHANGES → fail_blocked 'reviewer still requests changes after one repair' `[code: tools/dev-runner.sh:2174-2181]`<br>An unresolved background task at the review-repair's own stage end blocks even a clean re-check/re-review `[code+canon: tools/dev-runner.sh:2182-2185]`

#### 22. `review APPROVEd` → `commit made (05-commit.done)`

`T22`

- **Actor:** dev-runner (the runner owns every git write)
- **Trigger:** stage_done 05-commit is false
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2195-2204
- **Records:** `one git commit on task/<issue>-<slug>`
- **Preconditions:** `git add -A` then a non-empty staged diff — an empty diff is fail_blocked 'no changes produced' (a hard Block, never retried) `[code+canon: tools/dev-runner.sh:2199-2200]`
- **Postconditions:** One commit: subject = the issue title, body = 'Implements #<issue> (dev-runner, build <BUILD_ID>). Tests by the independent tester stage.' — the model is stamped, never a hardcoded name `[code+canon: tools/dev-runner.sh:2201]`<br>PR_HEAD_SHA recorded; mark_stage 05-commit `[code: tools/dev-runner.sh:2202-2203]`

#### 23. `commit made` → `branch pushed`

`T23`

- **Actor:** dev-runner
- **Trigger:** Unconditional (no .done marker for the PR stage — a resume re-runs it)
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2286
- **Records:** `$RUN_DIR/push-attempt.err`
- **Preconditions:** PR_STAGE_ATTEMPTS = PR_STAGE_RETRIES+1 (default 4) with exponential backoff (base 5s, factor 2, per-attempt cap 60s) `[code+canon: tools/dev-runner.sh:2206-2240]`<br>The push re-pushes the SAME ref, NEVER force — a push that lands but fails to acknowledge is absorbed by the next identical attempt `[code+canon: tools/dev-runner.sh:2242-2249]`
- **Postconditions:** On exhaustion → pr_stage_hold 'push' → the same env-hold preserve+resume core, with the final attempt's stderr tail in the comment `[code+canon: tools/dev-runner.sh:2280-2286]`

#### 24. `branch pushed` → `PR open`

`T24`

- **Actor:** dev-runner
- **Trigger:** Unconditional after the push
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2288
- **Records:** `the PR itself`, `$RUN_DIR/pr-create-attempt.err`
- **Preconditions:** pr_create_attempt is idempotent by construction: find_open_pr (`gh pr list --head <branch> --state open`) REUSES an existing open PR rather than creating a duplicate; a lookup failure reads as 'none found' and falls through to create `[code+canon: tools/dev-runner.sh:2251-2274]`
- **Postconditions:** PR opened with --base $BASE_BRANCH --head $BRANCH --title $TITLE; body = 'Closes #<issue>' plus the build/review model ids `[code: tools/dev-runner.sh:2271, tools/dev-runner.sh:2287]`<br>On exhaustion → pr_stage_hold 'pr create' (env-hold, resumable) `[code+canon: tools/dev-runner.sh:2288]`

#### 25. `PR open` → `PR trail populated`

`T25`

- **Actor:** dev-runner
- **Trigger:** Immediately after the PR exists; every post is best-effort (a failure logs, never blocks)
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — every post is `\|\| true` / `\|\| log warn`
- **Records:** `PR comments: reviewer verdict · YR-SHADOW-REVIEW · YR-VERDICT-DIFF · staleness warning · '### dev-runner usage' · YR-LENS (advisory)`
- **Preconditions:** Every non-gating comment is deliberately clear of the gating grammars: no column-0 `VERDICT:`, no `YR-MERGE` marker `[code+canon: tools/dev-runner.sh:2291-2304, tools/dev-runner.sh:2321-2327, tools/dev-runner.sh:2349-2361]`
- **Postconditions:** The reviewer verdict is attached verbatim (review.md as --body-file) `[code: tools/dev-runner.sh:2289]`<br>One `YR-SHADOW-REVIEW: <token>` comment per shadow round, transcript blockquoted with `> ` so no line can match `^VERDICT:` `[code+canon: tools/dev-runner.sh:2295-2304]`<br>One `YR-VERDICT-DIFF` comment per gating/shadow pair (skipped entirely when the seat is dark) `[code+canon: tools/dev-runner.sh:2306-2319]`<br>A staleness warning when the factory checkout is behind its own origin/main (visibility only, never a gate) `[code+canon: tools/dev-runner.sh:2321-2327, tools/dev-runner.sh:1270-1286]`<br>One usage-summary comment (always produced, even with zero per-stage artifacts) `[code+canon: tools/dev-runner.sh:2329-2347]`<br>One `YR-LENS (advisory)` comment, only when lens.md is non-empty `[code+canon: tools/dev-runner.sh:2349-2361]`

#### 26. `PR open` → `In Review (shadow record posted)`

`T26`

- **Actor:** dev-runner (terminal_step, deterministic — no LLM)
- **Trigger:** terminal_step runs unconditionally after the PR trail is populated
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh terminal_step (:2456-2563)
- **Records:** `PR comment: YR-MERGE-SHADOW: …`, `yr-ledger-row/1`
- **Preconditions:** auto_merge read at DECISION time from the base ref's CURRENT tip, never the start-of-run parse; a missing manifest/key = not armed `[code+canon: tools/dev-runner.sh:343-354]`<br>The four conditions are evaluated in order, in code, indeterminate = failed: ci_green · freshness · terminal_approval · rank_gate `[code+canon: tools/dev-runner.sh:267-342, tools/dev-runner.sh:2456-2476]`
- **Postconditions:** Not armed → one `YR-MERGE-SHADOW: WOULD-MERGE\|WOULD-BLOCK` PR comment, then stop `[code+canon: tools/dev-runner.sh:2480-2484]`<br>Status=In Review; a shadow WOULD-BLOCK is a NORMAL negative outcome and does NOT set Reason=Blocked `[code+canon: tools/dev-runner.sh:2372-2373, tools/dev-runner.sh:2576-2578]`<br>A ledger row: outcome.type = shadow-would-merge \| shadow-would-block, derived from MERGE_MARKER `[code: tools/dev-runner.sh:2586-2597]`

#### 27. `PR open` → `merged by the factory`

`T27`

- **Actor:** dev-runner (merge evaluator inside terminal_step)
- **Trigger:** An armed repo whose gates all pass
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh terminal_step (:2456-2563) — every gate is in code, fail-closed
- **Records:** `PR comment: YR-MERGE: MERGED`, `the squash-merge commit on main`, `yr-ledger-row/1`
- **Preconditions:** auto_merge == true at decision time `[code+canon: tools/dev-runner.sh:2481]`<br>server_ci != none (armed + server_ci=none refuses fail-closed as server_ci_none_armed) `[code+canon: tools/dev-runner.sh:2486-2493]`<br>Shadow completion is TRUE, computed mechanically from the last SHADOW_WINDOW (5) merge-record-bearing PRs + main history, needing SHADOW_NEED (3) landed unreverted successes and no reset `[code+canon: tools/dev-runner.sh:381-400, tools/dev-runner.sh:2495-2502]`<br>The host sentinel file ($DEV_RUNNER_HOME/merge-killswitch) is absent, read LIVE at decision time `[code+canon: tools/dev-runner.sh:376-382, tools/dev-runner.sh:2504-2510]`<br>terminal_approval, rank_gate, ci_green all pass; a failed freshness is REMEDIATED (rebase onto tip, re-run check_cmd, re-run lint, re-wait CI, re-check freshness), not blocked `[code+canon: tools/dev-runner.sh:2512-2545, tools/dev-runner.sh:2396-2424]`
- **Postconditions:** `gh pr merge --squash` passed EXPLICITLY (nothing server-side enforces squash); MERGE_COMMIT read best-effort `[code+canon: tools/dev-runner.sh:402-412]`<br>A durable `YR-MERGE: MERGED` PR comment; Status is NOT set to In Review — native close→Done finishes `[code+canon: tools/dev-runner.sh:2558-2562, tools/dev-runner.sh:2573-2575]`<br>A ledger row: outcome merged/MERGED `[code: tools/dev-runner.sh:2586-2589]`

#### 28. `PR open` → `In Review + Reason=Blocked (armed block)`

`T28`

- **Actor:** dev-runner (armed_block)
- **Trigger:** An armed repo whose sentinel is thrown, whose server_ci/auto_merge pair conflicts, whose terminal_approval/rank_gate/ci_green fails, whose freshness remediation cannot re-green, or whose post-force-push step fails environmentally
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh armed_block (:2429-2438)
- **Records:** `PR comment: YR-MERGE: BLOCKED — <reason>`, `issue comment: 'dev-runner: **Blocked** — autonomous merge refused (<reason>)'`, `yr-ledger-row/1`
- **Preconditions:** Once rebase_onto_tip has force-pushed (REBASE_REWROTE_REMOTE=1), a LATER environmental failure can no longer be silently resumed and posts `YR-MERGE: BLOCKED — unrecoverable` instead `[code+canon: tools/dev-runner.sh:2440-2448, tools/dev-runner.sh:2534-2540, tools/dev-runner.sh:2551-2556]`
- **Postconditions:** Reason=Blocked, a `YR-MERGE: BLOCKED — <condition>` PR comment, an issue comment naming the refused condition `[code+canon: tools/dev-runner.sh:2429-2438]`<br>Status=In Review at the shared terminus; a ledger row typed in-review/BLOCKED `[code: tools/dev-runner.sh:2576-2591]`

#### 29. `terminal step` → `terminal step abandoned (environmental)`

`T29`

- **Actor:** dev-runner
- **Trigger:** terminal_step returns 2 — a gh API blip, a network drop, a merge-API error while evaluating/recording/merging
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tools/dev-runner.sh:2566-2571
- **Records:** `run log line only — nothing on the PR, nothing on the issue`
- **Preconditions:** REBASE_REWROTE_REMOTE == 0 (otherwise T28's unrecoverable record fires instead) `[code+canon: tools/dev-runner.sh:2534-2540]`
- **Postconditions:** A warn log only: 'classified environmental, resumable (no record, no merge, not Blocked)'. The run then proceeds to Status=In Review, a ledger row, and cleanup_wt — the worktree IS torn down `[code: tools/dev-runner.sh:2569-2571, tools/dev-runner.sh:2599]`

#### 30. `any terminus` → `run closed out`

`T30`

- **Actor:** dev-runner
- **Trigger:** The success terminus is reached (a PR exists and terminal_step returned)
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — all fail-soft
- **Records:** `$DEV_RUNNER_HOME/ledger/rows.jsonl`, `stdout: the PR URL`
- **Preconditions:** ledger_append is fail-soft throughout — it never dies, never exits, always returns 0 `[code+canon: tools/dev-runner.sh:1098-1126, tools/ledger.py:264-269]`
- **Postconditions:** One yr-ledger-row/1 appended under a blocking flock; cleanup_wt removes the worktree, deletes the branch, clears STATE_DIR and the run tmp dir; transcript retention prune runs (fail-soft); PR_URL is printed on stdout `[code: tools/dev-runner.sh:2586-2607]`

#### 31. `In Progress (claimed)` → `stranded claim raised (Reason=Blocked)`

`T31`

- **Actor:** epic-gate sweep (tools/epic_gate.py, fired by dispatch's POST /sweep on its own lock)
- **Trigger:** A sweep tick finds an In-Progress, Reason-less item
- **Enforcement:** detected · **Guard site:** tools/epic_gate.py::_is_stranded (:280-297)
- **Records:** `issue comment: YR-EPIC-GATE: stranded claim …`
- **Preconditions:** status.updatedAt older than STRANDED_AFTER_MIN (default 45 minutes) `[code: tools/epic_gate.py:95, tools/epic_gate.py:288-290]`<br>No build currently holds THAT CHILD'S OWN repo build lock (a healthy long build on another repo never defers the raise) `[code: tools/epic_gate.py:249-267, tools/epic_gate.py:291-293]`<br>No open PR whose head branch starts `task/<number>-` `[code: tools/epic_gate.py:270-277]`
- **Postconditions:** Reason=Blocked and a `YR-EPIC-GATE: stranded claim — In Progress <n> min with no live build` comment; recovery is stated as clear-the-Reason-and-re-Ready `[code: tools/epic_gate.py:300-306, tools/epic_gate.py:336-339]`

#### 32. `Blocked / env-hold / Needs-info` → `Ready`

`T32`

- **Actor:** human (or an attended agent running tools/promote.sh)
- **Trigger:** A human decides to retry; nothing in the factory automates this
- **Enforcement:** *partial* · **Guard site:** tools/promote.sh:55-63 (refuse gate) — on the unmerged slice-5 branch an additional tools/wall.py promote-check runs at :67-70
- **Records:** `issue comment: YR-PROMOTED (only via promote.sh; a raw board click leaves no record)`
- **Preconditions:** No code path in the runner or the epic gate sets Status=Ready for a blocked/held task — the runner consumes Ready and never sets it `[code+canon: docs/rfcs/0003-task-state-model.md:43]`<br>tools/promote.sh refuses only on closed / not-on-board / Type=Feature\|Epic — it does NOT check the current Status, so it will flip an In-Progress item to Ready `[code: tools/promote.sh:55-63]`
- **Postconditions:** A `YR-PROMOTED` record lands BEFORE the Status flip, by call order `[code+canon: tools/promote.sh:76-84]`<br>The next dispatch tick re-enters the lane; if the env-hold triple is intact the run RESUMES, otherwise it starts fresh `[code: tools/dev-runner.sh:1245-1268]`

#### 33. `PR open (any prior record state)` → `terminal decision re-posted`

`T33`

- **Actor:** attended agent / human, invoking `dev-runner.sh <issue#> --repo <r> --re-evaluate <pr#>`
- **Trigger:** An explicit attended CLI invocation — never dispatch, never n8n
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh re_evaluate (:474-672) — every refusal is reeval_refuse, exit 3, before any write
- **Records:** `PR comment: YR-MERGE-SHADOW / YR-MERGE record with a note naming what it supersedes`
- **Preconditions:** The PR is OPEN; its head branch matches `task/<issue>-*`; the fetched tip agrees with the PR's live head from the API (a moved branch refuses loudly naming both shas) `[code+canon: tools/dev-runner.sh:486-513]`<br>With a prior record: the record parses, is not malformed_record (recorded base_sha == head_sha, or base_sha not an ancestor of the live head), carries a run_id belonging to this issue, and that run dir still holds review.md + review-bundle.json `[code+canon: tools/dev-runner.sh:518-550]`<br>With no prior record: the originating run is located by matching the PR's base commit against this issue's local run bundles' diff.base_sha `[code+canon: tools/dev-runner.sh:444-472, tools/dev-runner.sh:551-558]`
- **Postconditions:** A prior-record re-evaluation is ALWAYS shadow — never a merge, rebase, or board write, an armed repo included `[code+canon: tools/dev-runner.sh:595-605]`<br>A record-less re-evaluation evaluates exactly as terminal_step does (arming, sentinel, shadow completion) and may squash-merge an armed repo; a moved main is never rebase-remediated (no worktree) — just one more freshness block `[code+canon: tools/dev-runner.sh:607-671]`<br>No board/issue write on either path — the posted PR comment (and, for an armed pass, the merge) are the only writes `[code+canon: tools/dev-runner.sh:429-431]`

#### 34. `Ready` → `resolved plan printed (no state change)`

`T34`

- **Actor:** attended agent / human, invoking `--dry-run`
- **Trigger:** An explicit attended CLI invocation
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1137-1151
- **Records:** `stdout JSON only`
- **Preconditions:** --dry-run and --re-evaluate are mutually exclusive `[code: tools/dev-runner.sh:106]`<br>A NEEDS_INFO reason under --dry-run is a bare gate() — the Backlog/Needs-info writes are skipped `[code: tools/dev-runner.sh:1130]`
- **Postconditions:** A JSON plan on stdout (repo, issue, branch, resolved build/review roles, base_ref, check_cmd, lint/lens cmds, auto_merge) and exit 0; the RUN_DIR is never created `[code: tools/dev-runner.sh:1137-1151]`

#### 35. `stage running` → `stage process group reaped`

`T35`

- **Actor:** dev-runner (run_stage)
- **Trigger:** The stage leader exits
- **Enforcement:** *partial* · **Guard site:** tools/dev-runner.sh run_stage (:1518-1533) — reachable on every stage, but only DISPOSED by implement/test
- **Records:** `run log line: 'stage refused: process group <pid> still had a live member after <n>s grace'`
- **Preconditions:** wait_group_or_refuse polls once a second for up to STAGE_GROUP_GRACE (default 30s) for the group to empty; a still-live member past the grace is a REFUSAL `[code+canon: tools/dev-runner.sh:1426-1472]`
- **Postconditions:** reap_pgid TERMs the group, then escalates to KILL after ~0.5s of polling `[code: tools/dev-runner.sh:1412-1424]`<br>LAST_STAGE_GROUP_REFUSED is set for THIS call; rc is bumped to STAGE_REFUSAL_RC (124) only if the leader's own rc was 0 — and only AFTER capture_stage_usage has already run on the leader's rc `[code: tools/dev-runner.sh:1518-1533]`<br>Only the implement and test stages act on the refusal; the check-repair, lint-repair, review and review-repair stages read LAST_STAGE_GROUP_REFUSED solely to SUPPRESS the quota hold `[code: tools/dev-runner.sh:1628, :1675, :1956, :2005, :2123, :2150]`

#### 36. `stage running` → `stage forbidden-act performed`

`T36`

- **Actor:** a `claude -p` stage (implementer / tester / repair / reviewer)
- **Trigger:** The stage chooses to do what the charter forbids
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tester only: tools/dev-runner.sh:1682-1732. For every other forbidden act there is no guard on the path the stage takes
- **Preconditions:** CHARTER (prose only): write only inside the worktree, never the host; make no git or board writes; never edit checks, CI configuration, or .yr/factory.toml; never edit a test to weaken it; manage processes by PID only, no pkill -f / pgrep -f; the implementer never authors the committed test suite; the reviewer changes nothing `[canon-only: tools/dev-runner.sh:1609]`<br>--permission-mode bypassPermissions is passed on EVERY stage — no interactive permission prompt exists to stop any of it `[code+canon: tools/dev-runner.sh:1486-1489]`
- **Postconditions:** The reviewer's Edit/Write tools are withheld (allowedTools 'Read Bash'), but Bash is allowed and can write files, which the commit stage's `git add -A` would then commit `[code: tools/dev-runner.sh:2114, tools/dev-runner.sh:2199]`<br>The tester's out-of-surface writes ARE caught structurally (T12/T13). The implementer's writes into tests/, any stage's writes to .yr/factory.toml or CI config, host writes, and pattern-kills are caught by nothing `[code: tools/dev-runner.sh:1682-1732]`<br>A stage that git-commits inside the worktree perturbs BASE_SHA/HEAD_SHA and is likely to surface later as 'no changes produced' — an incidental symptom, not a guard `[code: tools/dev-runner.sh:2071-2076, tools/dev-runner.sh:2200]`

## Where the code and the canon disagree

### [material] Documented operator env overrides are stripped by dispatch's spawn allowlist, so they silently have no effect on a dispatched build

- **code:** tools/dispatch.py::_spawn_env hands the runner only _ENV_ALLOW_KEYS + the LC_/STUB_/YR_POOL_ prefixes. STAGE_GROUP_GRACE, MANIFEST_FETCH_TIMEOUT, CHECK_TIMEOUT, CHECK_IDLE_TIMEOUT, STAGE_SETTING_SOURCES and CLAUDE_OUTPUT_FORMAT are all absent from the set, so a value set in ~/.config/dev-runner/dispatch.env never reaches dev-runner.sh and the built-in default applies. Verified by running the allowlist's OWN documented enumeration grep (`grep -oE '[A-Z_][A-Z_0-9]*="\$\{[A-Z_][A-Z_0-9]*:?-'`) against tools/dev-runner.sh: STAGE_GROUP_GRACE (:1437) and MANIFEST_FETCH_TIMEOUT (:689) are found by it and still missing from the set.
- **canon:** deploy/DISPATCH.md: '**Override** `STAGE_GROUP_GRACE` in the dispatch environment to lengthen or shorten the grace for a slower or faster deployment.' AGENTS.md documents `CHECK_TIMEOUT` and `CHECK_IDLE_TIMEOUT` as env overrides with precedence env > manifest > default. tools/dispatch.py:152-156 claims the allowlist was 'mechanically enumerated' from that very grep.
- `tools/dispatch.py:147-183`, `tools/dev-runner.sh:1437`, `tools/dev-runner.sh:689`, `tools/dev-runner.sh:816`, `tools/dev-runner.sh:842`, `deploy/DISPATCH.md > The stage process-group grace (`STAGE_GROUP_GRACE`, issue #247)`, `AGENTS.md > Conventions`

### [blocking] A process-group refusal is dispositioned for only two of the six stage kinds — the review round can pass its gate while refused

- **code:** run_stage bumps rc to 124 and sets LAST_STAGE_GROUP_REFUSED on any refusal, but capture_stage_usage has already rewritten the log using the LEADER's own rc (:1527) before the bump (:1531). Only the implement (:1627-1629) and test (:1674-1676) stages gate on rc/refusal. review_stage (:2112-2138) reads rc only to suppress the quota hold and then judges purely on verdict_line — so a review round that left a live group member, and whose transcript still ends 'VERDICT: APPROVE', passes the gate with nothing but a run-log line recording the refusal. The check-repair, lint-repair and review-repair stages likewise never dispose on the refusal.
- **canon:** deploy/DISPATCH.md: 'A member still alive once the grace is spent is reaped and the stage is recorded as **refused** (`Reason=Blocked`, the same visible-failure path as any other stage failure — never a silent kill …)'. The vault map states the reap is 'observed completion or a recorded refusal, never a silent kill'.
- `tools/dev-runner.sh:1518-1533`, `tools/dev-runner.sh:2112-2138`, `tools/dev-runner.sh:1954-1956`, `tools/dev-runner.sh:2148-2150`, `deploy/DISPATCH.md > The stage process-group grace (`STAGE_GROUP_GRACE`, issue #247)`

### [material] A crashed reviewer is indistinguishable from a reviewer that requested changes

- **code:** review_stage captures rc but the only branch that reads it is the quota check; the function's exit status is the verdict test alone. A reviewer that dies non-zero for a non-quota reason leaves an unrewritten JSON envelope in review.md (capture_stage_usage runs only on rc==0, :1527), no `^VERDICT:` line matches, and the run enters the review-repair path; a second crash produces the Blocked message 'reviewer still requests changes after one repair'.
- **canon:** pipeline.md's stage table gives Review the failure disposition '`Blocked`', and the file's environmental-vs-code section says a stage that *cannot run* is classified environmental and named as such. Neither states that a crashed reviewer is reported as a REQUEST_CHANGES.
- `tools/dev-runner.sh:2112-2138`, `tools/dev-runner.sh:2174-2181`, `tools/dev-runner.sh:1527`, `skills/factory/references/pipeline.md > How the lower pipeline runs`

### [material] A resumed run past the review stage posts a merge record with null review provenance

- **code:** The review-bundle block at :2066-2086 re-runs unconditionally on every invocation, re-initialising review-bundle.json with `rounds: []` and no `sha256` (review_bundle.py `init` never calls finalize). On a resume, 04-review is skipped (:2140-2141) so record-verdict never runs. merge_shadow.build_record then reads `bundle.get('sha256')` → null, `rounds[-1].verdict` → null, `len(rounds)` → 0, while shadow_terminal_approval still passes off the copied review.md.
- **canon:** pipeline.md describes the review bundle as 'the hashed **review bundle** … each round's verdict appended', and the merge record as carrying the decision's inputs. gates.md and AGENTS.md treat `bundle_sha256`/`review_verdict` as the record's provenance fields.
- `tools/dev-runner.sh:2063-2086`, `tools/dev-runner.sh:2140-2141`, `tools/review_bundle.py:87-99`, `tools/merge_shadow.py:165-194`, `skills/factory/references/pipeline.md > How the lower pipeline runs`

### [material] RFC 0003's claimed double-dispatch backstop 'a re-check on claim' does not exist

- **code:** The project item (id, Status, Reason) is read once at :951-962; the DoR gate judges that snapshot at :972-990; the claim writes Status=In Progress at :1154 with no second read in between. The board read itself is the board-wide `gh project item-list`, which board_plumbing's own docstring says 'lags ~1 min'.
- **canon:** docs/rfcs/0003-task-state-model.md:59 — 'Double-dispatch race (two pickups of one Ready item) — serialized dispatch + the `task/<n>-…` branch as backstop + a re-check on claim. v0.5.'
- `tools/dev-runner.sh:951-962`, `tools/dev-runner.sh:1153-1161`, `tools/board_plumbing.py:209-213`, `docs/rfcs/0003-task-state-model.md:59`

### [minor] 'The runner claims as its first act' is not true of the shipped ordering

- **code:** Before the claim at :1154 the runner performs: a bounded `git fetch origin` on the base checkout (:690-693), a manifest read and eight key resolutions (:695-865), a `gh issue view` (:868), a standalone-gates scan of every issue comment (:885-949), a board-wide `gh project item-list --limit 500` (:952), the DoR gate (:971-990), two registry resolutions plus two stage-tier lookups (:1061-1090), and the Needs-info accumulation.
- **canon:** deploy/DISPATCH.md > Safety properties: 'the runner claims (`Ready → In Progress`) as its first act, dropping the task off the Ready query within seconds.' RFC 0004 § 2 repeats it: 'the runner's **claim** (`Ready → In Progress`), its first act'.
- `tools/dev-runner.sh:678-1161`, `deploy/DISPATCH.md > Safety properties (already built)`, `docs/rfcs/0004-dispatch.md > The three things to nail`

### [material] 'Any runner failure → Reason=Blocked + comment' is false for every pre-claim failure

- **code:** fail_blocked (Reason=Blocked + comment) only exists after the claim (:1163-1171). Before it, `die()` exits 1 writing nothing (run-start fetch failure :692, issue read :869, project read :953) and `gate()` exits 3 writing nothing (:972-990). Neither writes a board field, an issue comment, or a ledger row.
- **canon:** deploy/DISPATCH.md > Safety properties: '**Fail-closed:** any runner failure → `Reason=Blocked` + comment, no PR. A bad task can't run wild.'
- `tools/dev-runner.sh:84-85`, `tools/dev-runner.sh:690-693`, `tools/dev-runner.sh:971-990`, `tools/dev-runner.sh:1163-1171`, `deploy/DISPATCH.md > Safety properties (already built)`

### [material] A Bug-typed Ready item loops forever through dispatch with no state change

- **code:** The runner's Type gate refuses any Issue Type that is not REQUIRE_ISSUE_TYPE (default 'Task') with a no-write gate() — deliberately, so the item 'must stay Ready for the epic-gate sweeper' (:980-981). The n8n Code node filters out only 'Feature' and 'Epic'. A Bug-typed Ready item therefore passes the filter, is POSTed every 2-minute tick, wins the repo lock, and exits 3 with nothing changed — indefinitely. Only the UNTYPED case was given the Needs-info bounce that exists precisely to stop this starvation (:978-990).
- **canon:** docs/rfcs/0003-task-state-model.md:13 makes Type a native facet with values 'Task / Bug / Feature'. pipeline.md's Judgment points name only the `REQUIRE_ISSUE_TYPE=''` opt-out; no doc says a Bug-typed Ready item is refused, still less that it re-dispatches forever.
- `tools/dev-runner.sh:976-990`, `deploy/n8n-dispatch.json > Extract Ready issue numbers (Code node)`, `docs/rfcs/0003-task-state-model.md:13`, `skills/factory/references/pipeline.md > Judgment points`

### [minor] RFC 0003's lifecycle diagram contains a transition nothing implements, and names a state the mechanism does not have

- **code:** No code anywhere moves an item from In Review back to In Progress. And the DoR content bounce writes Status=Backlog + Reason=Needs-info (:1131), not a Status value; a hard block writes Reason=Blocked and leaves Status=In Progress (:1168).
- **canon:** docs/rfcs/0003-task-state-model.md:23-39 — 'InReview --> InProgress: changes requested', 'Ready --> NeedsInfo: DoR gate fails', 'InProgress --> Blocked: stage / runtime failure' as Status states. The same RFC's own 'Decided (was open)' section (:70) contradicts the diagram by putting Needs-info/Blocked on the separate Reason field.
- `docs/rfcs/0003-task-state-model.md:23-39`, `docs/rfcs/0003-task-state-model.md:70`, `tools/dev-runner.sh:1131`, `tools/dev-runner.sh:1168`

### [minor] `--dry-run` is documented as read-only but mutates the base checkout's refs

- **code:** The run-start `git fetch origin` at :690-693 runs before any dry-run branch and updates refs/remotes in $BASE_REPO. The code's own comment at :116-119 asserts 'the directory itself is only created later … so dry-run stays read-only', accounting only for RUN_DIR.
- **canon:** pipeline.md > To run by hand: '`--dry-run` … read-only: resolved plan or refusal reason'. dev-runner.sh:1137 comment: 'read-only: report the resolved plan, write nothing'.
- `tools/dev-runner.sh:116-119`, `tools/dev-runner.sh:690-693`, `tools/dev-runner.sh:1137`, `skills/factory/references/pipeline.md > To run by hand`

### [minor] AGENTS.md's repo map presents check_task.py as a runner gate for a Ready task; the runner never invokes it

- **code:** `grep -n 'check_task' tools/dev-runner.sh` returns nothing. The runner's own DoR gate checks state/board/Status/Type/acceptance-criteria/manifest keys/models/YR-TASK-GATES — never self-containedness.
- **canon:** AGENTS.md > Repo map: '`tools/check_task.py` \| the DoR self-containedness gate for a Ready task'. gates.md correctly classifies it as advisory and attended ('Run them yourself before promoting; don't claim CI enforcement that isn't wired').
- `AGENTS.md > Repo map`, `skills/factory/references/gates.md > Advisory vs. blocking`, `tools/dev-runner.sh:971-1010`

### [minor] Per-stage repair tiers are documented as a live capability but resolve to the build model today

- **code:** stage_repair_id shells to `registry.py stage-tier` and falls back to BUILD_ID when the registry names no tier (:1084-1090). models.toml contains `[roles]` with build/review only — no `[roles.stage_tiers]` table — so CHECK_REPAIR_ID and REVIEW_REPAIR_ID both equal BUILD_ID on every shipped build. Separately, the lint-repair stage runs at CHECK_REPAIR_ID (:2003), a tier reuse no document names.
- **canon:** pipeline.md > Model roles: 'Optional per-stage repair tiers (`[roles.stage_tiers]`) let `check_repair` / `review_repair` run cheaper than the build role, never above it.' pipeline.md's Check gate row says the repair runs 'at the registry's `check_repair` stage tier when set, else the build model' — accurate, but the tier is nowhere declared.
- `tools/dev-runner.sh:1084-1090`, `tools/dev-runner.sh:2003`, `models.toml:37-39`, `skills/factory/references/pipeline.md > Model roles — the registry`

### [material] AGENTS.md's confinement invariant overstates what the code enforces for three of the four stage kinds

- **code:** Every stage runs with `--permission-mode bypassPermissions` and inherits the runner's full ambient environment; only cwd is set to the worktree (:1509-1516). The single structural confinement over stage output is the tester boundary guard (:1682-1732). The reviewer's Edit/Write tools are withheld but Bash is granted (:2114), and anything a stage writes is swept into the commit by `git add -A` (:2199). Nothing checks for host writes, git writes, board writes, .yr/factory.toml edits, CI-config edits, test weakening, pkill -f, or the implementer authoring tests.
- **canon:** AGENTS.md > Invariants: 'Confinement is the environment, not intent. The system's *permits* (worktree, scoped creds, deterministic gates) protect, not the model's *plans* — why `bypassPermissions` is safe.' The stage charter states all of the above rules as if they held.
- `AGENTS.md > Invariants — and why`, `tools/dev-runner.sh:1486-1516`, `tools/dev-runner.sh:1609`, `tools/dev-runner.sh:2114`, `tools/dev-runner.sh:2199`

### [minor] Canon line citations into tools/dev-runner.sh are stale across the board

- **code:** STAGE_CHARTER is at :1609 (cited as :1591); shadow_review_round at :2100 (cited as :927); shadow_verdict_token/the posting loop at :2295/:2299 (cited as :1079); YR_SHADOW_MODEL/YR_SHADOW_BASE_URL at :61 (cited as :46-51 in both pipeline.md and the vault map); the claim-time Reason clear at :1155-1160 (the vault map cites :775).
- **canon:** skills/factory/references/pipeline.md > Stage conduct / The shadow review seat, and '04 projects/factory/architecture/factory-map.md' > 2. Mechanism map, cite those line numbers as authoritative anchors.
- `skills/factory/references/pipeline.md > Stage conduct`, `skills/factory/references/pipeline.md > The shadow review seat`, `tools/dev-runner.sh:61`, `tools/dev-runner.sh:1609`, `tools/dev-runner.sh:2100`, `tools/dev-runner.sh:2295`, `04 projects/factory/architecture/factory-map.md > 2. Mechanism map *(load-bearing)*`

### [material] UNMERGED slice 5 touches the runner despite it-30's own non-goal, and exports its machinery declaration to every stage subprocess

- **code:** The task/420-walls branch adds `export YR_MACHINERY=1` at tools/dev-runner.sh:46 (not present on origin/main). run_stage does not scrub the environment (:1509-1516), so every `claude -p` stage inherits YR_MACHINERY=1 — and tools/board_plumbing.py::_attended_wall returns early on that variable (:126-127). A stage that shelled to `python3 tools/board_plumbing.py set-field …` would therefore pass the attended board-write wall. The wall's own docstring asserts 'runner/epic-gate callers are untouched by construction (no CLAUDECODE in their environments)', which is false for the documented attended invocation (`pipeline.md > To run by hand`) — the export, not the absence of CLAUDECODE, is what saves it.
- **canon:** '04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md':107 — '**Lower-pipeline mechanics.** No dispatch, runner, or merge-evaluator behavior changes; the lower pipeline's gates already dispose deterministically.'
- `tools/dev-runner.sh:41-46`, `tools/dev-runner.sh:1509-1516`, `tools/board_plumbing.py:112-160`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md:107`

## Gaps

- **A `gate()` refusal writes nothing anywhere — no board field, no issue comment, no ledger row.**<br>Four refusal classes (issue not OPEN, not on the board, Status != Ready, typed-but-wrong Issue Type) leave the entire system with no durable trace. Dispatch is fire-and-forget (pipeline.md: 'a refused or dying runner is invisible to n8n'), so the only evidence is a host-local file under $DEV_RUNNER_HOME/runs/. There is no way to answer 'how many dispatches were refused this week' from any versioned or queryable surface, and the ledger — the factory's own meter — structurally under-counts invocations because ledger_append is never called on these branches.
- **There is no reviewer write guard, though the tester has one.**<br>The tester's boundary is structural (an IMPL_TREE→TESTER_TREE diff, tools/dev-runner.sh:1682-1732). The reviewer is given Bash, and anything it writes is swept into the commit by `git add -A` at :2199 with no tree comparison anywhere. 'The reviewer changes nothing' is charter prose only. This is the same rule for a sibling stage, enforced for one and not the other.
- **Nothing enforces the implementer half of builder ≠ verifier.**<br>IMPL_TREE is only a checkpoint for the tester guard; no guard asks whether the implementer wrote into tests/ (or into a manifest-declared test_paths). The invariant 'the implementer writes production code and never authors the committed test suite' is asked by the charter and checked by nothing, while its mirror image (the tester writing production code) is blocked structurally.
- **No guard on a stage editing .yr/factory.toml, CI configuration, or a test's assertions.** **← needs an owner ruling**<br>The charter's 'Never weaken a gate' clause covers exactly the edits that would let a later build weaken itself. The manifest edit is the sharpest case: it is committed on the branch and, once merged, changes check_cmd / test_paths / auto_merge / server_ci for every subsequent build of that repo. Nothing in the runner diffs the worktree against the base ref for these paths.
- **The PR stage and the terminal merge step carry no .done markers.**<br>The checkpoint set stops at 05-commit. A resume after a pr_stage_hold re-runs push and pr create, relying entirely on their own idempotency (push is never forced; pr create reuses an existing open PR via find_open_pr). The terminal merge step re-runs from scratch on every invocation with no marker at all, which is what produces the null-provenance merge record described in the disagreements.
- **`--setting-sources project` loads the TARGET repo's own .claude/settings.json into every stage, and no shipped document says so.** **← needs an owner ruling**<br>tools/dev-runner.sh:1489 passes `--setting-sources "${STAGE_SETTING_SOURCES:-project}" --strict-mcp-config`. 'project' scope means the settings file inside the cut worktree — hooks, permissions, env — is active for every stage of every repo the factory builds. This is a real confinement seam (it excludes the operator's user/local scope) and a real attack/mistake surface (a repo's own settings shape the stage). It is pinned only by tests/test_dev_runner.py:2377-2409 and appears in no AGENTS.md, pipeline.md, gates.md or DISPATCH.md sentence, so `.yr/factory.toml` is not actually the only declared repo-shape seam the pipeline reads.
- **Recovery from every failure terminus is an unrecorded human board write.** **← needs an owner ruling**<br>Blocked, env-hold and Needs-info all end with the task off the Ready queue and no automated path back. The runner never sets Ready (RFC 0003:43); the epic gate only *raises* a stranded claim, never resolves one. tools/promote.sh is the one recorded promote path, but it does not check current Status, so a raw board click — which leaves no YR-PROMOTED record — is the ordinary route. The lane therefore has a record-before-flip discipline at entry that is trivially bypassed at re-entry.
- **A shadow WOULD-BLOCK and a clean WOULD-MERGE are indistinguishable on the board.**<br>Both end at Status=In Review with no Reason (deliberately — dev-runner.sh:2372-2373 rules that a WOULD-BLOCK is a normal negative outcome). The difference lives only in a PR comment. Anyone reading the board to decide what to merge cannot see which PRs the evaluator would have refused.
- **The STAGE-BLOCKED escalation channel is read for exactly two stages; a repair or review round emitting it is inert and undetected.**<br>stage_blocked_reason is called only against implement.log (:1640) and test.log (:1740). The charter says 'a repair or review round has no such channel and must never emit it' — true in that nothing routes it, but nothing notices it either, so a repair round that concluded the work cannot ship states that conclusion into a log no disposition reads, and the run continues to a PR.
- **A Blocked run's lens findings and salvage artifacts reach no durable trail.**<br>The lens comment is posted only when a PR exists (:2356) — a Blocked run leaves lens.md in a run dir the next prune may reach. block-salvage.patch is announced only in the host run log (:1218); fail_blocked's issue comment names final.patch when present but never block-salvage.patch (:1166-1167). The 'legible failure, derivable recovery' invariant depends on the human finding artifacts whose existence is stated only on the host.
- **A successful build leaves no run identity on the issue trail.**<br>The run id appears in the merge record's `run_id` field on the PR and in the ledger row, but the issue itself carries nothing tying it to a run dir or worktree unless the run failed. Correlating a merged task back to its transcripts, usage artifacts, or gate durations requires reading the PR's YR-MERGE record or the ledger, not the task.
- **STAGE_REFUSAL_RC (124) collides with a genuine CLI exit code, and the mitigation is only applied where the refusal is disposed.**<br>The code documents this explicitly (:1438-1446) and instructs callers to gate on LAST_STAGE_GROUP_REFUSED rather than the rc value. Only implement and test do so — see the blocking disagreement. Any future caller that gates on rc alone inherits the ambiguity the constant was created to avoid.
- **Nothing ties this document's subject (the tree) to what actually runs (the deployed clone on yr-host).** **← needs an owner ruling**<br>The factory self-freshness check is explicitly 'visibility, never a gate' — any failure skips silently (:1270-1286), and its output is a warning plus a PR comment. The vault map records the deployed clone lagging main by ten commits at the 2026-08-04 walk, with tools/board_plumbing.py not existing there at all. Every behaviour excavated here is a claim about the branch tip, not necessarily about the machine that builds tasks.
- **The lane's own canon is not reaching sessions.** **← needs an owner ruling**<br>The factory skill ships as a plugin at version 0.10.0 (.claude-plugin/plugin.json), and iteration 30's slices 1-4 are merged to main without a version bump — so records.toml, check_trail.py, attended-lane.md and the slice compiler reach no session. For this lane specifically that means the record-registry home that would name the runner's own YR-MERGE / YR-LENS / YR-SHADOW-REVIEW / YR-NIT grammars is merged but invisible, and every consumer still reads those grammars from their emitters.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **State "stood down (lock busy)" — stored_where: "Nowhere durable — only the exit status of the spawned flock chain, captured in the dispatch log."**<br>The exit status is captured NOWHERE. tools/dispatch.py::_spawn_detached fires the child with subprocess.Popen and never waits; main() sets signal.signal(signal.SIGCHLD, signal.SIG_IGN) precisely so children are kernel-auto-reaped, with a comment stating "every child is fire-and-forget (_spawn_detached), so kernel auto-reap under SIG_IGN just cleans up exited children without dispatch ever calling wait()". The log file receives only the child's stdout/stderr, and `flock -n` on a busy lock writes nothing — so a stood-down build leaves a zero-byte dispatch log and an exit code no process ever reads. The cited :120-137 is _compose_build_cmd, which establishes the exit-0 semantics but says nothing about capture. `tools/dispatch.py:186-204 (_spawn_detached, no wait), tools/dispatch.py:290-296 (SIGCHLD SIG_IGN rationale) vs. the claim's citation tools/dispatch.py:120-137`
- **Gap: "The vault map records the deployed clone lagging main by ten commits at the 2026-08-04 walk, with tools/board_plumbing.py not existing there at all."**<br>No such record exists in the cited file. Grepping the factory-map for "commits behind", "ten commits", "10 commits", "deployed clone", "lagging" and "board_plumbing" returns only §31's operator-commands paragraph (board_plumbing as the identifiers home) and the 2026-08-04 it-28 walk entry at :154, which records the round's eight armed merges and says nothing about a deployment lag. The nearest real record is a DIFFERENT artifact and a different subject: an ideas file noting "The workspace checkout sat 26 commits behind at cf03f5b" (2026-08-02, about the workspace checkout, not the yr-host deployed clone). The gap's underlying point — that the tree is not the deployed machine — stands on the code (dev-runner.sh:1270-1286 is best-effort visibility only), but its supporting evidence is fabricated as cited. `/srv/obsidian/vaults/obsidian/04 projects/factory/architecture/factory-map.md (no matching line); cf. 04 projects/factory/ideas/2026-08-02-check-model-refs-scans-worktrees.md:15`
- **T32 citations: "tools/promote.sh:1-95" and postcondition "A YR-PROMOTED record lands BEFORE the Status flip, by call order" cited at tools/promote.sh:76-84.**<br>tools/promote.sh is 83 lines; there is no :1-95 and no :84. The substance is correct — the comment post is at :78-79 and the set-field at :80-81, so record-before-flip holds by call order — but the anchors are wrong, and :76-84 overshoots the file. The guard_site's "an additional tools/wall.py promote-check runs at :67-70" is also off: the call is at :68-69 (:64-67 is its comment block). `tools/promote.sh:75-83 (whole file is 83 lines)`
- **T30 precondition: "ledger_append is fail-soft throughout — it never dies, never exits, always returns 0" cited to tools/dev-runner.sh:1098-1126 and tools/ledger.py:264-269.**<br>The shell half is exactly right (:1123 captures rc, :1124 logs, :1125 `return 0`). The Python citation does not establish the claim: ledger.py:264-269 is build_ledger_row's signature and a docstring about not raising on a missing/empty run_dir — it says nothing about the append path, and append_row (:329-344) can and does raise on an I/O failure. Fail-softness is entirely the shell's `\|\| rc=$?` wrapper, not the module's. `tools/ledger.py:264-269 vs tools/ledger.py:329-344; tools/dev-runner.sh:1123-1125`
- **T14 precondition: "CHECK_TIMEOUT elapsing while output still flows fires exactly ONE advisory (run log + one issue comment) and the wait continues." T14's records list likewise names a single "issue comment (live-gate advisory)".**<br>The `advised` flag is declared `local` inside _gate_monitor (:1793) and reset on every invocation. _gate_monitor is called once per run_checks/run_lint/run_lens call, and a single run can make up to ~a dozen: check, check-repair-recheck, lint, lint-fix, lint-autofix-recheck, lint-repair-recheck (twice — run_checks then run_lint), review-repair-recheck, review-repair-lint, rebase-recheck, rebase-lint, lens. So "exactly ONE" is true per gate invocation and false per run — a chatty repo can post a dozen live-gate advisory comments on one issue. The words "exactly ONE" read as a run-level guarantee that does not exist. `tools/dev-runner.sh:1793 (`local … advised=0`), :1814-1818, vs. the call sites :1949, :1957, :1982, :1989, :1995, :2025, :2028, :2049, :2164, :2170, :2407, :2415`
- **T26 precondition: "The four conditions are evaluated in order, in code, indeterminate = failed: ci_green · freshness · terminal_approval · rank_gate."**<br>That is the COMPUTE order (:2472-2475), not the disposal order, and stating it as "the order" misdescribes what actually decides a block. terminal_step's block-reason precedence is terminal_approval → rank_gate → ci_green (:2514-2516), and freshness is deliberately NOT in that chain at all — it is remediated by rebase_onto_tip (:2532-2545), never blocked on directly. So an armed PR that is both stale and CI-red records `ci_green`, not `freshness`; and a shadow PR's failed_condition is picked by merge_shadow, not by this list. (T27's own preconditions get the real behaviour right, which makes T26's phrasing the odd one out.) `tools/dev-runner.sh:2472-2475 vs tools/dev-runner.sh:2514-2516 and :2532-2545`
- **T33 postcondition: "No board/issue write on either path — the posted PR comment (and, for an armed pass, the merge) are the only writes," cited to the canon comment at :429-431.**<br>True for the board and the issue trail, but "the only writes" is stated flatly and is false on the filesystem: re_evaluate sets RUN_DIR to the ORIGINATING run's directory (:560) and then writes into it — check-rollup.json (:581/:584/:587 and inside shadow_ci at :274), merge-shadow-reeval.md / merge-record-reeval.md (:600, :613, :624, :635, :644, :658, :667), prs.json and main-log.txt (compute_shadow_complete, :391-394). An attended re-evaluation therefore mutates a prior build's forensic artifacts in place. The claim reproduces the code comment's intent ("no board/issue write") but widens it to "the only writes". `tools/dev-runner.sh:560, :581-587, :600-667, :391-394`

## Found by the verifier, missing from the excavation

- ci_green's registration grace and the `empty_after_grace` terminus — the single most consequential precondition of T26/T27, and the reason most shadow records read WOULD-BLOCK. A rollup reading zero total checks starts a bounded registration grace (MERGE_CI_REG_GRACE, default 10s; MERGE_CI_REG_POLL_INTERVAL, default 5s); still empty when it expires, CI_RESULT=fail with CI_STATE=empty_after_grace, fail-fast without paying MERGE_CI_TIMEOUT. Canon states the consequence outright: "A repo with no server CI configured, and no server_ci = none declared, cannot pass ci_green." The excavation names server_ci=none and the timeout but never this, so its account of T26/T27 cannot explain the ordinary outcome for an un-CI'd repo. Both env keys ARE in dispatch's allowlist, unlike the ones its disagreement flags. `tools/dev-runner.sh:143-147, :278-296, :2472; skills/factory/references/pipeline.md:136-201 ("The ci_green model")`
- Every board write and every issue comment in the runner is best-effort and silent on failure — set_status/set_reason only `log warn` (:966-967) and comment() is `\|\| true` (:969). The excavation notes this once, for the claim (T7), but it applies identically to fail_blocked (:1168), env_hold_record (:1235-1236) and armed_block (:2431-2435). Consequence: a hard-Blocked or env-held task whose gh calls fail leaves NO durable trace anywhere — no Reason, no comment, no PR — and the resulting board shape (In Progress, empty Reason) is byte-identical to the stranded-claim signature the epic gate detects. That is a terminal state the excavation's seven-terminal enumeration does not contain. `tools/dev-runner.sh:966-969, :1166-1171, :1232-1239, :2429-2438`
- On a resume that skips the check stage, CHECK_RC is forced to 0 (:1947) and that literal 0 is passed to the review bundle as `--check-exit` (:2083). The bundle — the hashed artifact the merge record's provenance rests on — therefore records a passing check exit for an invocation that never ran check_cmd, alongside a checks.log copied forward from the prior run dir (:1258-1260). This is a second, independent provenance hole in the same artifact the excavation's null-sha256 disagreement is about, and it is not mentioned. `tools/dev-runner.sh:1945-1947, :2083, :1258-1260`
- The review bundle's diff, BASE_SHA and HEAD_SHA are computed BEFORE the reviewer stage runs (:2066-2077), while the commit stage stages the tree AFTER it (:2199). Anything the reviewer writes through its granted Bash tool is therefore committed and shipped, but appears in neither the reviewed diff, the bundle, nor the bundle's sha256 — so the merge record's `bundle_sha256` names inputs that are not the tree being merged. The excavation's gap #2 ("no reviewer write guard") states the weaker half only. `tools/dev-runner.sh:2066-2077, :2114, :2199-2201, tools/merge_shadow.py:179`
- review_stage carries a hard-block path the excavation's T20/T21 omit: `review_bundle.py record-verdict` failing calls fail_blocked "review bundle record-verdict failed" from inside the review function (:2124-2125) — a full Blocked terminus with teardown, reachable on both the first and the post-repair round, and independent of any verdict. `tools/dev-runner.sh:2124-2125`
- The reviewer emits a machine-parsed record grammar the lane's record inventory never lists: REVIEW_SYS mandates one `YR-NIT: tag=<blocker\|nit> path=… — <sentence>` line at column 0 per finding, and review.md is posted verbatim to the PR (:2289). That grammar is tools/nit_harvest.py's input — a record this lane produces on every PR, absent from T20's and T25's `records` lists. `tools/dev-runner.sh:2091, :2289; AGENTS.md repo map (tools/nit_harvest.py)`
- T31's trigger ("a sweep tick finds an In-Progress, Reason-less item") is materially under-specified, and the omitted filters interact with the excavation's own Bug-typed-loop finding. The standalone arm additionally requires content.state == OPEN, issueType == "task" (case-folded) and NO parent (:323-328); the per-epic arm only ever walks an open Ready epic's own children (:996-1007). So an untyped or Bug-typed standalone item stranded In Progress is raised by neither arm — the same two Type shapes the dispatch/DoR path mishandles are also invisible to the sweeper meant to catch its wreckage. `tools/epic_gate.py:319-334, :996-1007`
- The resume and fresh-cut branches treat the same `git fetch origin` failure differently: on resume it is `\|\| true` (:1248), on a fresh cut it is `\|\| fail_blocked "git fetch failed"` (:1264). A resumed build can therefore proceed against stale refs where a fresh one hard-blocks — relevant to T9, which cites :1245-1261 but does not report the asymmetry. `tools/dev-runner.sh:1248 vs tools/dev-runner.sh:1264`

---

SCOPE AND VANTAGE. Read entirely from /opt/yellow-robots/factory/.claude/worktrees/task-420-walls (branch task/420-walls = origin/main + the unmerged, review-rejected slice-5 "walls" branch) plus the read-only vault. All tools/dev-runner.sh line numbers are as of this worktree's HEAD; the slice-5 branch inserts 6 lines at :41-46, so subtract 6 for the equivalent line on origin/main below :41. tools/wall.py also carries uncommitted local edits, but nothing in this lane calls it — the runner never imports or shells to wall.py; the only slice-5 surface inside the lane is the `export YR_MACHINERY=1` line and its consumption by tools/board_plumbing.py::_attended_wall. On origin/main, board_plumbing.set_field has no wall at all and the runner's board writes go straight through unconditionally.  WHAT THE LANE ACTUALLY GUARANTEES. Four things in this pipeline are enforced by a machine on the path the actor takes, and they are worth separating from the much larger body of prose: (1) the DoR/manifest/model gate, which refuses before any claim, worktree, or LLM call and cannot be reached around; (2) the tester boundary guard, a tree diff, block-and-raise, no auto-revert; (3) the deterministic check/lint gates, run by the runner and not by an LLM, with the 126/127 environment split and the liveness-judged bound; (4) the review verdict's exact-match, last-line-wins, fail-closed grammar. Everything else the stage charter states — host writes, git writes, board writes, gate edits, test weakening, pattern-kills, the implementer not authoring tests, the reviewer changing nothing — is asked and not checked. That asymmetry is the single largest structural fact about this lane and it is the reason several disagreements above land as "material": the canon's language ("confinement is the environment, not intent") describes a stronger system than the code implements for three of the four stage kinds.  TERMINAL STATES, ENUMERATED. The lane has exactly seven terminals: gate-refused (exit 3, no writes, no record anywhere); pre-claim environmental die (exit 1, no writes); Needs-info (Status=Backlog + Reason=Needs-info + comment + ledger); Blocked (Reason=Blocked + comment + ledger + teardown, Status stays In Progress); env-hold (Reason=Blocked + comment + ledger + PRESERVED worktree/markers, Status stays In Progress); In Review (± Reason=Blocked when armed-blocked); and merged (Status left In Progress until GitHub's native close→Done fires). Note that "Blocked" is never a Status — it is a Reason, and a hard-blocked task sits on the board as In Progress + Blocked, which is also exactly the shape the epic-gate's stranded-claim detector writes when a runner dies without writing anything.  PER-STAGE MODEL SELECTION, AS RESOLVED TODAY. Two roles resolve independently (build, review), precedence per-task body > per-repo manifest > registry default, with BUILD_MODEL/REVIEW_MODEL env atop all three; only the env override may name an unregistered id, and it then runs unranked, loudly warned, and can never satisfy the merge rank gate. Stage assignment in code: implement → BUILD_ID; test → BUILD_ID; check-repair → CHECK_REPAIR_ID; lint-repair → CHECK_REPAIR_ID; review + re-review → REVIEW_ID; review-repair → REVIEW_REPAIR_ID; shadow review → YR_SHADOW_MODEL with a per-subprocess ANTHROPIC_BASE_URL. Because models.toml declares no [roles.stage_tiers], CHECK_REPAIR_ID and REVIEW_REPAIR_ID both collapse to BUILD_ID on every shipped build — so today the review-repair round runs at the BUILD model under the IMPLEMENTER system prompt, which is correct by design but means the "reviewer is never weaker" rank property does not extend to the stage that acts on the reviewer's findings.  METHOD NOTE. The dispatch-allowlist finding was produced by importing tools/dispatch.py and diffing its actual _ENV_ALLOW_KEYS set against the exact grep the module's own comment claims it was enumerated from; STAGE_GROUP_GRACE and MANIFEST_FETCH_TIMEOUT are found by that grep and absent from the set, so this is an enumeration miss rather than a pattern limitation. CHECK_TIMEOUT and CHECK_IDLE_TIMEOUT are read in a bare `${VAR:-}` test rather than an assignment, so the documented grep would never have found them at all.
