<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The merge decision, arming, and the shadow phase

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `repo-unarmed` | The repo's manifest at the base ref's CURRENT tip has no `auto_merge` key, or its value is not the literal boolean `true`. The evaluator will only ever post a shadow record; the human merges. | git blob `origin/<base_branch>:.yr/factory.toml` in the target repo, re-read at decision time (never the start-of-run copy) | `tools/dev-runner.sh:346-354 (read_auto_merge) + tools/dev-runner.sh:188 (`_manifest_read bool`: true only on a literal boolean true)` |
| `repo-armed` | `auto_merge = true` at the base ref's current tip. The declaration of intent only — 'conditions, not the flag, grant the authority'. | same git blob; live examples: factory/.yr/factory.toml, website/.yr/factory.toml, gilda/.yr/factory.toml, yellow-robots/.yr/factory.toml | `/opt/yellow-robots/factory/.yr/factory.toml (`auto_merge = true`, 'Armed 2026-07-07'); tools/dev-runner.sh:343-354` |
| `repo-armed-conflicted` | `auto_merge = true` AND `server_ci = "none"` in the same manifest — a declared pair with no independent CI to gate an autonomous merge on. Refuses fail-closed at the arming wall. | the same manifest blob (two keys), both re-read at decision time | `tools/dev-runner.sh:2486-2493; tools/dev-runner.sh:252-265 (read_server_ci)` |
| `server-ci-required` | The repo declares (or defaults to) `server_ci = "required"`: `ci_green` is judged by polling the PR's GitHub check rollup. | manifest key `server_ci`, decision-time re-read; absent key or absent manifest defaults to `required` | `tools/dev-runner.sh:257-262` |
| `server-ci-none-declared` | The repo declares it genuinely runs no server CI: `ci_green` passes BY DECLARATION, `check_rollup: not_required_declared`, the rollup poll never runs. | manifest key `server_ci = "none"` | `tools/dev-runner.sh:2468-2470; skills/factory/references/pipeline.md > The ci_green model` |
| `server-ci-invalid` | `server_ci` present but neither `required` nor `none` — a config error, not an environmental one: `ci_green` fails, `check_rollup: server_ci_invalid`, the raw value recorded as `server_ci_rejected`. | manifest key; the rejection is carried in the posted yr-merge-record's `server_ci_rejected` field | `tools/dev-runner.sh:261-264, :2465-2467, :2523; tools/merge_shadow.py:186-189` |
| `ci-timeout-invalid` | `merge_ci_timeout` present but not a positive integer — `ci_green` fails with `check_rollup: timeout_invalid`; the bounded wait never runs and never silently falls back to the 1200s default. | manifest key `merge_ci_timeout`; the rejection rides the record as `ci_timeout_rejected` | `tools/dev-runner.sh:237-240, :2462-2464, :2522` |
| `sentinel-clear` | The host merge kill switch is not thrown; autonomous merges may execute. | ABSENCE of the host file `$DEV_RUNNER_HOME/merge-killswitch` on the build host (yr-host, user `yr-factory`); path overridable via `MERGE_SENTINEL` | `tools/dev-runner.sh:381; deploy/DISPATCH.md > Merge kill switch (the sentinel)` |
| `sentinel-thrown` | The global kill switch is thrown: every armed merge is refused for the very next decision, builds keep flowing to open PRs. | PRESENCE of that same host file; read live by a file stat at decision time, never an inherited env var | `tools/dev-runner.sh:2504-2510; deploy/DISPATCH.md > Merge kill switch (the sentinel)` |
| `shadow-incomplete` | The repo's rolling window over its last N=5 merge-record-bearing PRs holds fewer than K=3 landed unreverted successes, or contains a reset. An armed repo in this state is REFUSED THE HONORING of auto_merge and posts a shadow record with a progress note. | NOWHERE — derived at decision time from the repo's own PR comment trail (`gh pr list --json number,state,mergeCommit,mergedAt,comments`, last 40 PRs on the base) plus `git log origin/<base>` for revert detection. No sidecar state. | `tools/dev-runner.sh:390-400 (compute_shadow_complete); tools/merge_shadow.py:337-356 (shadow_completion)` |
| `shadow-complete` | No reset in the window AND >= 3 landed unreverted successes. Completion PERMITS arming; it does not perform it. | derived, same as above; N/K default 5/3, env-overridable via SHADOW_WINDOW / SHADOW_NEED | `tools/merge_shadow.py:66-67, :337-356; tools/dev-runner.sh:382; skills/factory/references/closing.md > 2. Merge -> Done` |
| `pr-no-record` | An open PR carrying no comment whose RAW column-0 line begins with `YR-MERGE:` or `YR-MERGE-SHADOW:`. The shape of a build whose terminal step never ran or never posted. Such a PR is EXCLUDED from the shadow window entirely (not counted as a failure). | absence of a marker-bearing PR comment | `tools/merge_shadow.py:240-272 (_record_marker_offset / _last_merge_record, `seen`); tools/merge_shadow.py:312-313` |
| `pr-shadow-would-merge` | A `YR-MERGE-SHADOW: WOULD-MERGE` record: every condition passed, but this repo is not armed (or is armed with an incomplete window). Stops for the human. | a PR comment: line 1 the marker, then a fenced ```yr-merge-record JSON block at schema `yr-merge-record/1` | `tools/merge_shadow.py:200-216 (render_comment), :53 (SCHEMA); tools/dev-runner.sh:2481-2484` |
| `pr-shadow-would-block` | `YR-MERGE-SHADOW: WOULD-BLOCK — <first failed condition>`. A NORMAL negative outcome, explicitly NOT Reason=Blocked. | the same PR-comment record; the failed condition is derived by `first_failed` over SHADOW_ORDER | `tools/merge_shadow.py:62-63, :128-133, :209-212; tools/dev-runner.sh:2371-2372` |
| `pr-armed-blocked` | `YR-MERGE: BLOCKED — <reason>` on an armed repo. Reasons actually emitted: server_ci_none_armed, sentinel, terminal_approval, rank_gate, ci_green, freshness, unrecoverable. | a PR comment record (mode `armed`) + `Reason=Blocked` on the board item + a `dev-runner: **Blocked**` comment on the ISSUE trail | `tools/dev-runner.sh:2428-2438 (armed_block); reasons at :2489, :2508, :2514-2516, :2542, :2447` |
| `pr-armed-unrecoverable` | A sub-case of armed-blocked: freshness remediation already force-pushed the branch onto a new base, then a later step failed environmentally — no named recovery lane can locate the run again, so a fact-stating BLOCKED record replaces the usual silent resumable exit. | the same PR record with `failed_condition: "unrecoverable"`, plus Reason=Blocked | `tools/dev-runner.sh:2440-2448, :2534-2539, :2551-2556` |
| `pr-merged-by-factory` | The PR was squash-merged by the evaluator and carries a durable `YR-MERGE: MERGED` record naming the merge commit. | PR state MERGED + mergeCommit oid on GitHub, plus the PR-comment record (`decision: MERGED`, `merge_commit`) | `tools/dev-runner.sh:404-412 (do_squash_merge), :2551-2562` |
| `pr-merged-by-human` | A human clicked merge. Classified from the PR's own state plus its last record: a merged WOULD-MERGE is a success; a merged WOULD-BLOCK/BLOCKED is a RESET of the shadow window. | PR state MERGED on GitHub + the last marker-bearing PR comment | `tools/merge_shadow.py:328-333 (classify_event)` |
| `window-event-success` | One window slot: a landed, unreverted factory MERGED, or a landed, unreverted human-merged WOULD-MERGE. | derived per PR at decision time from the record + PR state + main's revert history | `tools/merge_shadow.py:322-331` |
| `window-event-reset` | One window slot that zeroes qualification: an overridden (merged) WOULD-BLOCK/BLOCKED, a reverted MERGED, a MERGED record on a PR that is not merged (contradiction), a malformed/unparseable record, a `machinery_ok: false` record, or an unknown decision. | derived; revert detection reads `This reverts commit <sha>` / `Reverts [owner/repo]#N` from up to 300 commits of main | `tools/merge_shadow.py:275-291, :307-334` |
| `window-event-neutral` | A WOULD-MERGE the human has not merged, or an unmerged WOULD-BLOCK/BLOCKED: occupies a window slot, advances nothing, resets nothing. | derived | `tools/merge_shadow.py:328-333` |
| `board-in-review` | The task's Status after a PR opens and the factory did NOT merge it. | the Projects v2 single-select `Status` field on the shared board item (field id PVTSSF_lADOEEAo0M4Ba6LszhVuZlw, option `In Review` = da2e6a49) | `tools/dev-runner.sh:2574-2579; tools/board_plumbing.py:56-72` |
| `board-reason-blocked` | Set by an armed block only. A shadow WOULD-BLOCK never sets it. | the Projects v2 `Reason` field (PVTSSF_lADOEEAo0M4Ba6LszhVzoxI, option `Blocked` = fe4d566c) | `tools/dev-runner.sh:2431, :2371-2372; tools/board_plumbing.py:60-78` |
| `board-done` | Terminal. Reached only by GitHub Projects' built-in close->Done automation after the PR (body `Closes #N`) merges. No factory code writes it. | the Projects `Status` field, written by GitHub's own workflow | `docs/rfcs/0003-task-state-model.md > Decision / Lifecycle; tools/dev-runner.sh:2287 (`Closes #%s`); grep of `set_status "` shows only 'In Progress' and 'In Review'` |
| `evaluator-environmental-exit` | The terminal step hit a gh/network/git failure while evaluating, recording, or merging: NO record, NO merge, NO streak reset, NOT Blocked — silently resumable. The single exception is the post-force-push case (pr-armed-unrecoverable). | the run log only (`$DEV_RUNNER_HOME/runs/<issue>-<id>/`), plus the ledger row's `in-review` outcome with an empty decision | `tools/dev-runner.sh:2450-2455, :2569-2571, :2586-2597` |
| `reeval-refusal` | A `--re-evaluate` invocation refused before ANY write: PR not open, branch not this issue's, fetched tip disagrees with the API head, malformed prior record, missing run_id/run dir/review.md/review-bundle.json, or no local run bundle matching the PR's base commit. | stderr / run log only — nothing is posted | `tools/dev-runner.sh:486-496, :509-516, :521-555` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `repo-unarmed` → `repo-armed` | human (the decision) executed by an attended agent session or the human's own commit — in practice all four armed repos were keyed by sessions under explicit instruction | ⚠️ **unenforced** | none on main. The only machine guard is `tools/wall.py::classify` -> `arming-edit` (tools/wall.py:149-150) + `RULES['arming-edit']` (:236) in the UNMERGED, uncommitted, review-rejected slice 5 — and it refuses unconditionally without ever checking for the record its own rule names (`decide()` has an in-flight satisfaction branch only for `crossing-file`, tools/wall.py:252-260). |
| 2 | `repo-armed` → `repo-unarmed` | human / attended agent under instruction | ⚠️ **unenforced** | same as T1 — the unmerged wall would refuse the edit categorically, i.e. it would refuse UN-arming too |
| 3 | `repo-unarmed` → `repo-armed (for one run only)` | an operator running `tools/dev-runner.sh` by hand with `MERGE_AUTO_MERGE` set | *partial* | tools/dispatch.py::_spawn_env (dispatch.py:178-183) — blocks the dispatch path only; a hand-run runner inherits the operator's environment unfiltered |
| 4 | `sentinel-clear` → `sentinel-thrown` | human/operator on the build host as unix user `yr-factory` | ⚠️ **unenforced** | none — no factory code guards who may create or delete this file; filesystem permissions on yr-host are the only control |
| 5 | `sentinel-thrown` → `sentinel-clear` | human/operator on yr-host | ⚠️ **unenforced** | none |
| 6 | `pr-no-record` → `condition `ci_green` resolved (pass/fail)` | merge evaluator (dev-runner.sh terminal_step, deterministic, no LLM stage) | **prevented** | tools/dev-runner.sh::shadow_ci (:270-305) + tools/merge_shadow.py::count_checks/bucket_of (:84-125), reached on every terminal decision and every --re-evaluate |
| 7 | `ci_green resolved` → `condition `freshness` resolved` | merge evaluator | **prevented** | tools/dev-runner.sh::shadow_freshness (:315-323) |
| 8 | `freshness resolved` → `condition `terminal_approval` resolved` | merge evaluator | **prevented** | tools/dev-runner.sh::shadow_terminal_approval (:331-334), sharing `verdict_line` with the review gate |
| 9 | `terminal_approval resolved` → `condition `rank_gate` resolved` | merge evaluator | **prevented** | tools/dev-runner.sh::shadow_rank_gate (:338-342) |
| 10 | `pr-no-record` → `pr-shadow-would-merge \| pr-shadow-would-block` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step (:2481-2484) -> emit_and_post (:359-374) |
| 11 | `repo-armed-conflicted` → `pr-armed-blocked (server_ci_none_armed)` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step (:2486-2493); the --re-evaluate twin at :620-630 |
| 12 | `repo-armed + shadow-incomplete` → `pr-shadow-would-merge/would-block (with progress note)` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step (:2495-2502) -> compute_shadow_complete (:390-400) -> tools/merge_shadow.py::shadow_completion (:337-356) |
| 13 | `repo-armed + shadow-complete + sentinel-thrown` → `pr-armed-blocked (sentinel)` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step (:2504-2510); the --re-evaluate twin at :643-650 |
| 14 | `repo-armed + shadow-complete + sentinel-clear` → `pr-armed-blocked (terminal_approval \| rank_gate \| ci_green)` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step (:2512-2528) -> armed_block (:2429-2438) |
| 15 | `repo-armed, all conditions pass except freshness` → `rebased branch, green re-established` | merge evaluator (the runner is the ONLY actor that rebases outside the attended recovery lane) | **prevented** | tools/dev-runner.sh::rebase_onto_tip (:2396-2424), called only from terminal_step (:2532-2545) |
| 16 | `freshness remediation` → `pr-armed-blocked (freshness)` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step (:2541-2544) |
| 17 | `freshness remediation (force-push already landed)` → `pr-armed-unrecoverable` | merge evaluator | **prevented** | tools/dev-runner.sh::unrecoverable_remote_rewrite_block (:2446-2448), reached from :2534-2539 and :2551-2556 |
| 18 | `repo-armed + shadow-complete + sentinel-clear + all conditions pass` → `pr-merged-by-factory` | merge evaluator (the factory's own `gh` identity) | **prevented** | tools/dev-runner.sh::terminal_step (:2547-2562) -> do_squash_merge (:404-412) |
| 19 | `pr-merged-by-factory \| pr-merged-by-human` → `board-done` | native GitHub automation (Projects' built-in close->Done workflow) | ⚠️ **unenforced** | none in this repo — the automation is GitHub-side configuration |
| 20 | `pr-shadow-would-merge` → `pr-merged-by-human + window-event-success` | human (the merge click on a repo not yet armed — the named transitional exception) | ⚠️ **unenforced** | none — this is the human's click at GitHub |
| 21 | `pr-shadow-would-block \| pr-armed-blocked` → `pr-merged-by-human + window-event-reset` | human | detected | none — detected only afterwards, from the PR's own durable record plus its merged state |
| 22 | `window-event-success` → `window-event-reset` | any actor pushing a revert to main | detected | tools/merge_shadow.py::_reverted_sets / _is_reverted, reached from shadow_completion |
| 23 | `any pr record state` → `pr-merged-by-human (by an AGENT)` | attended agent session | ⚠️ **unenforced** | NONE on main. The only machine wall is `tools/wall.py::classify` -> `hand-merge` (tools/wall.py:121-122) denying via PreToolUse — in the UNMERGED slice 5, registered only in the unmerged `hooks/hooks.json`, in a plugin whose released version (0.10.0) predates all of it; the regex also matches innocuous commands (`gh pr comment N --body "ready to merge"`) and misses `gh api --method PUT .../pulls/N/merge`. |
| 24 | `pr-shadow-would-block (freshness)` → `a content-identical rebased branch` | attended agent session (by hand — the runner never rebases outside its own armed-merge remediation) | ⚠️ **unenforced** | none — nothing verifies the rebase was content-identical |
| 25 | `any pr record state (prior record present)` → `pr-shadow-would-merge \| pr-shadow-would-block (superseding record)` | attended agent session invoking `tools/dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>` | **prevented** | tools/dev-runner.sh::re_evaluate (:474-605); the shadow-only branch is a hard code path at :595-604 |
| 26 | `pr-no-record` → `pr-shadow-* \| pr-armed-blocked \| pr-merged-by-factory` | attended agent session invoking `--re-evaluate` on a PR with no prior record | **prevented** | tools/dev-runner.sh::re_evaluate (:607-671) |
| 27 | `any point inside terminal_step` → `evaluator-environmental-exit` | merge evaluator | **prevented** | tools/dev-runner.sh::terminal_step return-2 sites (:2460, :2461, :2472, :2474, :2476, :2482, :2491, :2496, :2500, :2508, :2526, :2539, :2556) |
| 28 | `board (claimed, Reason cleared)` → `board-in-review [+ board-reason-blocked]` | merge evaluator, through the one board field write | *partial* | tools/board_plumbing.py::_attended_wall (:112-155) — unmerged; exempt for the runner by the YR_MACHINERY declaration |
| 29 | `any pr` → `in-window \| out-of-window` | merge evaluator (shadow-completion computation) | **prevented** | tools/merge_shadow.py::_last_merge_record / shadow_completion |
| 30 | `any terminal merge outcome` → `a ledger row` | dev-runner (fail-soft ledger append) | **prevented** | tools/dev-runner.sh (:2581-2597) |

### Detail

#### 1. `repo-unarmed` → `repo-armed`

`T1-arm`

- **Actor:** human (the decision) executed by an attended agent session or the human's own commit — in practice all four armed repos were keyed by sessions under explicit instruction
- **Trigger:** an `auto_merge = true` line lands on the repo's base ref (merged manifest edit)
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none on main. The only machine guard is `tools/wall.py::classify` -> `arming-edit` (tools/wall.py:149-150) + `RULES['arming-edit']` (:236) in the UNMERGED, uncommitted, review-rejected slice 5 — and it refuses unconditionally without ever checking for the record its own rule names (`decide()` has an in-flight satisfaction branch only for `crossing-file`, tools/wall.py:252-260).
- **Records:** `YR-HUMAN-INSTRUCTION (canon-mandated, it-30; nothing emits or demands it today)`, `in practice: the git commit message and its Co-Authored-By trailer, e.g. yellow-robots commit ef800cd 'arm: auto_merge = true — ordered by Jose, attended session 2026-08-05'`
- **Preconditions:** The repo's shadow phase has completed (>=3 landed unreverted successes, zero resets, over the last 5 merge-record-bearing PRs). Completion PERMITS arming; it never performs it. `[canon-only: skills/factory/references/closing.md > 2. Merge -> Done; skills/factory/references/pipeline.md > Judgment points]`<br>The decision is exclusively the human's; a session may execute it only under her explicit instruction and never decides it. `[canon-only: skills/factory/references/onboarding.md > (non-delegable acts: auth · onboarding · arming); skills/factory/references/attended-lane.md > The walled-act map]`<br>A `YR-HUMAN-INSTRUCTION` record attributing her decision (it-30 canon; merged to main but not released to any session). `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (Arming edit row); records.toml:394-401]`<br>The repo must have server CI, or the arming is self-defeating: `server_ci = none` + `auto_merge = true` refuses fail-closed at every decision. `[code+canon: tools/dev-runner.sh:2486-2493; skills/factory/references/pipeline.md > The ci_green model]`
- **Postconditions:** Every subsequent merge decision on that repo re-reads the key from the base ref's current tip and takes the armed branch. `[code: tools/dev-runner.sh:343-354, :2476-2481]`<br>No ceremony, no state file: the flag can be set at any time and the runner simply refuses to HONOR it until the window completes. `[code+canon: tools/dev-runner.sh:2496-2502; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > Shadow completion — the mechanical condition]`

#### 2. `repo-armed` → `repo-unarmed`

`T2-unarm`

- **Actor:** human / attended agent under instruction
- **Trigger:** the `auto_merge` key is removed or set false on the base ref
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** same as T1 — the unmerged wall would refuse the edit categorically, i.e. it would refuse UN-arming too
- **Preconditions:** None stated anywhere — un-arming has no declared condition, no record, and no wall. `[code: tools/dev-runner.sh:346-354 (a missing manifest or key is simply `false`, 'not armed, not an error')]`
- **Postconditions:** Effective at the VERY NEXT merge decision, including a build already in flight: the flag is never cached from the start-of-run parse. `[code+canon: tools/dev-runner.sh:343-346, :721-724; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > Cord-pulls and the kill switch]`

#### 3. `repo-unarmed` → `repo-armed (for one run only)`

`T3-arm-by-env`

- **Actor:** an operator running `tools/dev-runner.sh` by hand with `MERGE_AUTO_MERGE` set
- **Trigger:** a non-empty `MERGE_AUTO_MERGE` in the runner's environment
- **Enforcement:** *partial* · **Guard site:** tools/dispatch.py::_spawn_env (dispatch.py:178-183) — blocks the dispatch path only; a hand-run runner inherits the operator's environment unfiltered
- **Records:** `the posted yr-merge-record's `auto_merge` field`
- **Preconditions:** None. The env value is taken verbatim with no validation; `MERGE_AUTO_MERGE=true` arms any repo, manifest untouched. `[code: tools/dev-runner.sh:347]`
- **Postconditions:** The decision-time git read of the manifest is skipped entirely; the posted record's `auto_merge` field carries the env value. `[code: tools/dev-runner.sh:347, :371]`<br>A DISPATCHED build cannot reach this state: `MERGE_AUTO_MERGE` is not in the spawn-environment allowlist. `[code: tools/dispatch.py:147-176 (_ENV_ALLOW_KEYS; MERGE_SENTINEL, MERGE_CI_*, SHADOW_* are listed, MERGE_AUTO_MERGE and MERGE_MAIN_TIP are not)]`

#### 4. `sentinel-clear` → `sentinel-thrown`

`T4-throw-sentinel`

- **Actor:** human/operator on the build host as unix user `yr-factory`
- **Trigger:** `touch "$DEV_RUNNER_HOME/merge-killswitch"`
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — no factory code guards who may create or delete this file; filesystem permissions on yr-host are the only control
- **Preconditions:** None — a deliberate operator switch for an incident, a main-branch freeze, or any window where the final merge gate is held by hand. `[canon-only: deploy/DISPATCH.md > Merge kill switch (the sentinel)]`
- **Postconditions:** The very next armed decision that reaches the sentinel check refuses; builds, tests, reviews and PR creation are unaffected; a non-armed repo is unaffected. `[code+canon: tools/dev-runner.sh:2504-2510; deploy/DISPATCH.md > Merge kill switch (the sentinel)]`<br>It is a FILE, not an env var, precisely because a spawned runner carries its spawn-time environment. `[code+canon: tools/dev-runner.sh:376-381; deploy/DISPATCH.md]`

#### 5. `sentinel-thrown` → `sentinel-clear`

`T5-clear-sentinel`

- **Actor:** human/operator on yr-host
- **Trigger:** `rm "$DEV_RUNNER_HOME/merge-killswitch"`
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none
- **Preconditions:** —
- **Postconditions:** Autonomous merges resume at the next decision. PRs blocked while it was thrown STAY at Reason=Blocked until re-run or hand-merged — the human is asked to clear the reason. `[canon-only: deploy/DISPATCH.md > Merge kill switch (the sentinel)]`<br>In code, a stale Reason=Blocked is cleared only by the next claim of that issue, by VALUE not by writer. `[code: tools/dev-runner.sh:1155-1160]`

#### 6. `pr-no-record` → `condition `ci_green` resolved (pass/fail)`

`T6-evaluate-ci`

- **Actor:** merge evaluator (dev-runner.sh terminal_step, deterministic, no LLM stage)
- **Trigger:** the PR has just been opened; terminal_step runs
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::shadow_ci (:270-305) + tools/merge_shadow.py::count_checks/bucket_of (:84-125), reached on every terminal decision and every --re-evaluate
- **Records:** `the record's `check_rollup`, `checks[]`, `ci_timeout_seconds`/`ci_timeout_source`/`ci_timeout_rejected`, `server_ci`/`server_ci_source`/`server_ci_rejected``
- **Preconditions:** `merge_ci_timeout` resolves at decision time, precedence env MERGE_CI_TIMEOUT > manifest > 1200s default; each read does its OWN fresh fetch of origin/<base>. `[code+canon: tools/dev-runner.sh:218-242; skills/factory/references/pipeline.md > The ci_green model]`<br>`server_ci` resolves at decision time, manifest > `required` default, own fresh fetch. `[code+canon: tools/dev-runner.sh:244-265; skills/factory/references/pipeline.md > The ci_green model]`
- **Postconditions:** Four mutually exclusive outcomes before any poll: timeout_invalid (fail), server_ci_invalid (fail), not_required_declared (pass by declaration), else poll. `[code: tools/dev-runner.sh:2462-2473]`<br>Polling: a zero-total rollup gets its own bounded registration grace (MERGE_CI_REG_GRACE, default 10s, poll 5s); still empty at expiry -> `empty_after_grace` fail-fast; otherwise poll every MERGE_CI_POLL_INTERVAL (15s) until nothing is in flight, bounded by the resolved timeout -> `timed_out` on expiry. `[code+canon: tools/dev-runner.sh:143-147, :270-305; skills/factory/references/pipeline.md > The ci_green model]`<br>Bucketing is fail-closed: anything unrecognized is `fail`; SUCCESS/NEUTRAL/SKIPPED are the only successes. `[code: tools/merge_shadow.py:69-103 (bucket_of)]`<br>A gh/parse failure here is environmental: return 2, no record, resumable. `[code: tools/dev-runner.sh:2472]`

#### 7. `ci_green resolved` → `condition `freshness` resolved`

`T7-evaluate-freshness`

- **Actor:** merge evaluator
- **Trigger:** immediately after the CI condition
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::shadow_freshness (:315-323)
- **Records:** `the record's `main_tip_sha`, `base_sha`, `head_sha``
- **Preconditions:** A decision-time re-fetch of origin/<base> is mandatory: the only earlier fetch ran at build start and BASE_SHA is that same base, so without it freshness could never see a moved main. `[code: tools/dev-runner.sh:306-323]`
- **Postconditions:** pass iff the run's BASE_SHA (the worktree's cut point, or the task commit's parent on a resume) equals origin/<base>'s tip; an unresolvable tip is `fail` (indeterminate = failed). `[code: tools/dev-runner.sh:315-323; :2071-2075]`<br>`MERGE_MAIN_TIP` in the environment replaces the fetch+rev-parse outright. `[code: tools/dev-runner.sh:316]`<br>A fetch failure is environmental (return 2), never a false pass. `[code: tools/dev-runner.sh:2474]`

#### 8. `freshness resolved` → `condition `terminal_approval` resolved`

`T8-evaluate-approval`

- **Actor:** merge evaluator
- **Trigger:** same step
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::shadow_terminal_approval (:331-334), sharing `verdict_line` with the review gate
- **Records:** `the record's `review_verdict` (the LAST bundle round's verdict) and `rounds``
- **Preconditions:** The verdict grammar is line-anchored `^VERDICT:`, LAST such line wins, trailing whitespace stripped; pass requires EXACTLY `VERDICT: APPROVE`. Re-approval of a revised diff counts; the first pass need not have been clean. `[code+canon: tools/dev-runner.sh:324-334; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > The merge conditions (condition 3)]`
- **Postconditions:** Read from `$RUN_DIR/review.md` — the run's persisted gating review. A shadow-seat verdict can never satisfy it (shadow comments blockquote their transcript). `[code+canon: tools/dev-runner.sh:331-334, :2299-2303; skills/factory/references/pipeline.md > The shadow review seat]`

#### 9. `terminal_approval resolved` → `condition `rank_gate` resolved`

`T9-evaluate-rank`

- **Actor:** merge evaluator
- **Trigger:** same step
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::shadow_rank_gate (:338-342)
- **Records:** `the record's `build` / `review` role objects, carried from the review bundle`
- **Preconditions:** Both roles ranked, SAME provider, review rank >= build rank. `[code: tools/dev-runner.sh:338-342]`<br>An unranked emergency env override (BUILD_MODEL/REVIEW_MODEL with a raw id) is shadow-only by construction — it can never satisfy this gate. `[code+canon: tools/dev-runner.sh:335-337; skills/factory/references/pipeline.md > Model roles — the registry]`
- **Postconditions:** On --re-evaluate the ranks are REUSED verbatim from the originating run's bundle, never re-resolved. `[code: tools/dev-runner.sh:562-573]`

#### 10. `pr-no-record` → `pr-shadow-would-merge \| pr-shadow-would-block`

`T10-shadow-record`

- **Actor:** merge evaluator
- **Trigger:** `read_auto_merge` returns anything but `true`
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2481-2484) -> emit_and_post (:359-374)
- **Records:** `YR-MERGE-SHADOW (records.toml:44-51)`, `yr-merge-record/1 (records.toml:277-284)`
- **Preconditions:** Repo not armed at the base ref's current tip. `[code+canon: tools/dev-runner.sh:2476-2484; skills/factory/references/gates.md > Gate table (Merge evaluator row)]`
- **Postconditions:** One PR comment: line 1 `YR-MERGE-SHADOW: WOULD-MERGE` or `YR-MERGE-SHADOW: WOULD-BLOCK — <first failed condition>`, then the fenced yr-merge-record/1 JSON block. The failed condition is `first_failed` over SHADOW_ORDER = ci_green, freshness, terminal_approval, rank_gate. `[code: tools/merge_shadow.py:62-63, :128-133, :200-216]`<br>No merge, no rebase, no Reason=Blocked. Status is then set to In Review and the run stops for the human. `[code+canon: tools/dev-runner.sh:2371-2372, :2574-2579]`<br>`shadow_complete`/`shadow_progress`/`sentinel` are null on this path — shadow completion is never computed for a non-armed repo. `[code: tools/dev-runner.sh:2482 (no --shadow-* args), :2496 (compute_shadow_complete lives inside the armed branch)]`

#### 11. `repo-armed-conflicted` → `pr-armed-blocked (server_ci_none_armed)`

`T11-armed-serverci-conflict`

- **Actor:** merge evaluator
- **Trigger:** armed AND `server_ci = none`, checked before shadow completion and before the sentinel
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2486-2493); the --re-evaluate twin at :620-630
- **Records:** `YR-MERGE`, `yr-merge-record/1`
- **Preconditions:** An armed repo needs server CI as ci_green's independent gate; the two declarations conflict. `[code+canon: tools/dev-runner.sh:2486-2493; AGENTS.md > Conventions (server_ci paragraph)]`
- **Postconditions:** `YR-MERGE: BLOCKED — server_ci_none_armed` + Reason=Blocked + an issue-trail comment naming both declarations and both resolutions. `[code+canon: tools/dev-runner.sh:2488-2493, :2428-2438]`<br>The record claims `shadow_complete: false` although shadow completion was never computed on this path (SHADOW_DONE still holds its terminal_step initializer). `[code: tools/dev-runner.sh:2458, :2433]`

#### 12. `repo-armed + shadow-incomplete` → `pr-shadow-would-merge/would-block (with progress note)`

`T12-armed-shadow-incomplete`

- **Actor:** merge evaluator
- **Trigger:** `compute_shadow_complete` returns false
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2495-2502) -> compute_shadow_complete (:390-400) -> tools/merge_shadow.py::shadow_completion (:337-356)
- **Records:** `YR-MERGE-SHADOW with shadow_complete=false, shadow_progress`, `yr-merge-record/1`
- **Preconditions:** The window is computed at decision time from the last 40 PRs on the base (`gh pr list --state all --limit 40 --json number,state,mergeCommit,mergedAt,comments`) plus 300 commits of main for revert detection; the current PR is excluded. `[code: tools/dev-runner.sh:390-400]`<br>Complete iff no reset in the window AND >= SHADOW_NEED successes; window/need are env-overridable (SHADOW_WINDOW=5, SHADOW_NEED=3, SHADOW_SCAN=40). `[code+canon: tools/dev-runner.sh:382; tools/merge_shadow.py:337-356; skills/factory/references/pipeline.md > Judgment points]`
- **Postconditions:** The runner REFUSES TO HONOR auto_merge: a shadow-mode record with `--shadow-complete false --shadow-progress k/5` and the marker note `armed, shadow-incomplete k/5`. `[code+canon: tools/dev-runner.sh:2497-2502; tools/merge_shadow.py:200-206 (the note is display-only, never persisted in the JSON block)]`<br>The sentinel is NEVER consulted on this path — the sentinel check sits after shadow completion. `[code: tools/dev-runner.sh:2504-2510]`<br>`shadow_progress` prints successes over the CONFIGURED window, not the observed window size (the size returned by shadow-complete is discarded). `[code: tools/dev-runner.sh:397-398; tools/merge_shadow.py:467]`

#### 13. `repo-armed + shadow-complete + sentinel-thrown` → `pr-armed-blocked (sentinel)`

`T13-armed-sentinel-block`

- **Actor:** merge evaluator
- **Trigger:** `[ -e "$MERGE_SENTINEL" ]` — a live file stat, no git round-trip
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2504-2510); the --re-evaluate twin at :643-650
- **Records:** `YR-MERGE (failed_condition `sentinel`, `sentinel: "thrown"`)`
- **Preconditions:** Read live at decision time so a change made after the runner spawned is honoured. `[code+canon: tools/dev-runner.sh:2504-2506, :376-381; deploy/DISPATCH.md > Merge kill switch (the sentinel)]`
- **Postconditions:** `YR-MERGE: BLOCKED — sentinel` with `sentinel: thrown`, Reason=Blocked, an issue comment naming the path and how to clear it, Status=In Review. `[code+canon: tools/dev-runner.sh:2506-2510, :2428-2438; deploy/DISPATCH.md]`

#### 14. `repo-armed + shadow-complete + sentinel-clear` → `pr-armed-blocked (terminal_approval \| rank_gate \| ci_green)`

`T14-armed-condition-block`

- **Actor:** merge evaluator
- **Trigger:** one of the reviewed-diff conditions failed
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2512-2528) -> armed_block (:2429-2438)
- **Records:** `YR-MERGE`, `yr-merge-record/1`
- **Preconditions:** Evaluated in the ARMED order terminal_approval, then rank_gate, then ci_green — freshness is deliberately excluded here because it is remediated, not blocked. `[code: tools/dev-runner.sh:2512-2516]`
- **Postconditions:** `YR-MERGE: BLOCKED — <condition>` + Reason=Blocked + an issue comment; a `ci_green` block substitutes a state-specific detail for timed_out / timeout_invalid / server_ci_invalid. `[code: tools/dev-runner.sh:2517-2528]`

#### 15. `repo-armed, all conditions pass except freshness` → `rebased branch, green re-established`

`T15-freshness-remediation`

- **Actor:** merge evaluator (the runner is the ONLY actor that rebases outside the attended recovery lane)
- **Trigger:** `FRESH_RESULT != pass` on an otherwise-armed pass
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::rebase_onto_tip (:2396-2424), called only from terminal_step (:2532-2545)
- **Preconditions:** A clean rebase leaves the reviewed diff unchanged, so the verdict stands; what must be re-proven is the deterministic green. `[code+canon: tools/dev-runner.sh:2389-2392; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > The merge conditions (condition 2)]`<br>The freshness remediation assumes a SINGLE-COMMIT PR (it resolves the head's parent to find the pre-rebase base). `[canon-only: skills/factory/references/onboarding.md > The written invariants]`
- **Postconditions:** fetch -> rebase -> `push --force-with-lease` (sets REBASE_REWROTE_REMOTE=1) -> re-run check_cmd (`rebase-recheck`) -> re-run lint_cmd when declared (`rebase-lint`, issue #364) -> re-wait CI -> re-read freshness. PR_HEAD_SHA and BASE_SHA are updated to the rebased state. `[code: tools/dev-runner.sh:2396-2424]`<br>The tester and reviewer stages are NOT re-run; the review bundle is not re-hashed. `[code: tools/dev-runner.sh:2396-2424 (no reviewer/tester invocation); tools/dev-runner.sh:364 (emit_and_post still cites the original $BUNDLE)]`

#### 16. `freshness remediation` → `pr-armed-blocked (freshness)`

`T16-remediation-block`

- **Actor:** merge evaluator
- **Trigger:** rebase conflict, a failed re-check, a failed re-lint, red CI on the rebased head, or freshness still failing
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2541-2544)
- **Records:** `YR-MERGE (failed_condition `freshness`)`
- **Preconditions:** A stale green SHALL NOT merge; a conflict or a failure to re-green hard-blocks for the human. `[code+canon: tools/dev-runner.sh:2389-2392, :2399-2422; skills/factory/references/gates.md > Gate table]`
- **Postconditions:** `YR-MERGE: BLOCKED — freshness` + Reason=Blocked, naming the moved tip. `[code: tools/dev-runner.sh:2541-2544]`

#### 17. `freshness remediation (force-push already landed)` → `pr-armed-unrecoverable`

`T17-unrecoverable-block`

- **Actor:** merge evaluator
- **Trigger:** an ENVIRONMENTAL failure after REBASE_REWROTE_REMOTE=1 — inside the remediation's own re-green wait, or at the squash-merge call
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::unrecoverable_remote_rewrite_block (:2446-2448), reached from :2534-2539 and :2551-2556
- **Records:** `YR-MERGE (failed_condition `unrecoverable`)`
- **Preconditions:** The PR's remote head no longer matches any local run's recorded base commit, so --re-evaluate's record-less base-commit match cannot locate the run, and the env-hold resume cannot engage (the worktree is torn down). `[code+canon: tools/dev-runner.sh:2440-2448; skills/factory/references/pipeline.md > Shadow merge choreography (issue #240 bullet)]`
- **Postconditions:** A fact-stating `YR-MERGE: BLOCKED — unrecoverable` + Reason=Blocked instructing: close the PR, delete the branch, re-Ready the issue for a clean rebuild. Never a machinery error, never a streak reset. `[code+canon: tools/dev-runner.sh:2446-2448, :2534-2539, :2551-2556]`

#### 18. `repo-armed + shadow-complete + sentinel-clear + all conditions pass` → `pr-merged-by-factory`

`T18-factory-merge`

- **Actor:** merge evaluator (the factory's own `gh` identity)
- **Trigger:** the full armed pass at the end of terminal_step
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step (:2547-2562) -> do_squash_merge (:404-412)
- **Records:** `YR-MERGE: MERGED (records.toml:35-42)`, `yr-merge-record/1 with `merge_commit``, `yr-ledger-row/1 outcome merged`
- **Preconditions:** ci_green pass (or declared away by server_ci=none, which is itself refused on an armed repo), freshness pass or remediated, terminal clean APPROVE, rank gate holding, shadow complete, sentinel clear. `[code+canon: tools/dev-runner.sh:2456-2557; skills/factory/references/gates.md > Gate table (Merge evaluator row)]`
- **Postconditions:** `gh pr merge --squash`, passed EXPLICITLY because nothing server-side enforces squash (the org's repos are private on the free plan, so branch protection and native auto-merge are unavailable). `[code+canon: tools/dev-runner.sh:402-412; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > Context]`<br>MERGED=1; the durable `YR-MERGE: MERGED` record is posted AFTER the merge with the merge commit oid, `shadow_complete: true`, `sentinel: ok`. `[code: tools/dev-runner.sh:2558-2562]`<br>Status is NOT written: the merge supersedes `set_status "In Review"` and native close->Done finishes the lifecycle. `[code+canon: tools/dev-runner.sh:2573-2579; skills/factory/references/closing.md > 2. Merge -> Done]`<br>The ledger row's outcome is `merged` / `MERGED`. `[code: tools/dev-runner.sh:2586-2597]`<br>A failure to POST the record after a successful merge is only a warn — the PR is merged with no record. `[code: tools/dev-runner.sh:2559-2561]`

#### 19. `pr-merged-by-factory \| pr-merged-by-human` → `board-done`

`T19-native-close-done`

- **Actor:** native GitHub automation (Projects' built-in close->Done workflow)
- **Trigger:** the PR body's `Closes #<issue>` closes the issue on merge
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none in this repo — the automation is GitHub-side configuration
- **Preconditions:** The PR body carries `Closes #N` — written unconditionally by the PR stage. `[code: tools/dev-runner.sh:2287]`<br>The issue is on the shared board (a Projects auto-add rule is assumed). `[canon-only: docs/rfcs/0003-task-state-model.md > Compromises (1)]`
- **Postconditions:** Status=Done. No factory code performs or verifies this write. `[code+canon: docs/rfcs/0003-task-state-model.md > Decision; grep of `set_status "` in tools/dev-runner.sh yields only 'In Progress' (:1154) and 'In Review' (:2577)]`

#### 20. `pr-shadow-would-merge` → `pr-merged-by-human + window-event-success`

`T20-human-merge-shadow`

- **Actor:** human (the merge click on a repo not yet armed — the named transitional exception)
- **Trigger:** the human merges the PR on GitHub
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — this is the human's click at GitHub
- **Preconditions:** Merge only while no build is in flight — a human-merge click races the next dispatch's worktree cut the moment main moves, producing an honest but avoidable freshness WOULD-BLOCK. `[canon-only: skills/factory/references/pipeline.md > Shadow merge choreography]`
- **Postconditions:** The next decision's window counts this PR as a success (landed, unreverted WOULD-MERGE). `[code: tools/merge_shadow.py:328-331]`<br>A WOULD-MERGE the human has NOT merged is neutral — it cannot reset the streak, and cannot advance it either. `[code+canon: tools/merge_shadow.py:331; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > Shadow completion]`

#### 21. `pr-shadow-would-block \| pr-armed-blocked` → `pr-merged-by-human + window-event-reset`

`T21-human-merge-over-block`

- **Actor:** human
- **Trigger:** the human merges a PR whose last record is a WOULD-BLOCK/BLOCKED
- **Enforcement:** detected · **Guard site:** none — detected only afterwards, from the PR's own durable record plus its merged state
- **Preconditions:** There is NO reason carve-out: a freshness-stale WOULD-BLOCK merged anyway resets the streak exactly like an overridden CI failure. classify_event does not distinguish WHY the PR was blocked. `[code+canon: tools/merge_shadow.py:332-333; skills/factory/references/pipeline.md > Shadow merge choreography]`
- **Postconditions:** The window resets: `complete` becomes false for the whole 5-PR window, on an ARMED repo too — the armed repo silently falls back to posting shadow records until 3 fresh successes accumulate. `[code: tools/merge_shadow.py:353-356; tools/dev-runner.sh:2496-2502]`

#### 22. `window-event-success` → `window-event-reset`

`T22-revert`

- **Actor:** any actor pushing a revert to main
- **Trigger:** a commit on main whose message matches `This reverts commit <sha>` or `Reverts [owner/repo]#N`
- **Enforcement:** detected · **Guard site:** tools/merge_shadow.py::_reverted_sets / _is_reverted, reached from shadow_completion
- **Preconditions:** Ambiguity counts as reverted (a partial-SHA prefix match either way), fail-closed. `[code: tools/merge_shadow.py:294-304]`
- **Postconditions:** A reverted MERGED is a reset; a reverted human-merged WOULD-MERGE is a reset. Detection scans 300 commits of origin/<base>. `[code: tools/merge_shadow.py:275-291, :322-331; tools/dev-runner.sh:394]`

#### 23. `any pr record state` → `pr-merged-by-human (by an AGENT)`

`T23-attended-hand-merge`

- **Actor:** attended agent session
- **Trigger:** an agent runs `gh pr merge` (or the equivalent API call)
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** NONE on main. The only machine wall is `tools/wall.py::classify` -> `hand-merge` (tools/wall.py:121-122) denying via PreToolUse — in the UNMERGED slice 5, registered only in the unmerged `hooks/hooks.json`, in a plugin whose released version (0.10.0) predates all of it; the regex also matches innocuous commands (`gh pr comment N --body "ready to merge"`) and misses `gh api --method PUT .../pulls/N/merge`.
- **Preconditions:** CATEGORICALLY REFUSED — no record licenses it; merges execute through the evaluator. `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (PR merge row); AGENTS.md > Conventions ('Never: set a design active, arm a repo, or hand-merge a PR')]`
- **Postconditions:** If it happened anyway, it would be classified after the fact by the shadow window exactly like any human merge (success or reset by the last record). `[code: tools/merge_shadow.py:307-334]`

#### 24. `pr-shadow-would-block (freshness)` → `a content-identical rebased branch`

`T24-attended-rebase-recovery`

- **Actor:** attended agent session (by hand — the runner never rebases outside its own armed-merge remediation)
- **Trigger:** a freshness-stale but otherwise-clean shadow record
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — nothing verifies the rebase was content-identical
- **Preconditions:** The rebase must be content-identical so the diff is unchanged and the existing review verdict still applies. `[canon-only: skills/factory/references/pipeline.md > Shadow merge choreography (recovery bullet)]`
- **Postconditions:** Followed by `--re-evaluate`, which posts a fresh record; the eventual merge then counts as a success rather than a reset. `[canon-only: skills/factory/references/pipeline.md > Shadow merge choreography]`

#### 25. `any pr record state (prior record present)` → `pr-shadow-would-merge \| pr-shadow-would-block (superseding record)`

`T25-reeval-with-prior-record`

- **Actor:** attended agent session invoking `tools/dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>`
- **Trigger:** the operator command
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::re_evaluate (:474-605); the shadow-only branch is a hard code path at :595-604
- **Records:** `YR-MERGE-SHADOW (superseding)`, `yr-merge-record/1`
- **Preconditions:** PR OPEN; branch matches `task/<issue>-*`; the fetched tip of the branch must EQUAL the PR's live head from the API (a branch that moved between the two reads refuses loudly, naming both shas); the head must have a resolvable parent (single-commit-PR invariant). `[code: tools/dev-runner.sh:486-516]`<br>The prior record must parse; its recorded base_sha must not equal its head_sha; its base_sha must be an ancestor of the PR's live head; it must carry a run_id belonging to this issue; the originating run dir, review.md and review-bundle.json must exist. `[code: tools/dev-runner.sh:521-549]`
- **Postconditions:** ALWAYS mode=shadow — never a merge, rebase, or board write, an armed repo with shadow complete included. auto_merge is still READ but only lands in the record's informational field. `[code+canon: tools/dev-runner.sh:595-604; skills/factory/references/pipeline.md > Shadow merge choreography]`<br>The note names the record it supersedes, so history reads truthfully; the note is display-only and never persisted in the JSON block. `[code+canon: tools/dev-runner.sh:550; tools/merge_shadow.py:200-206]`<br>The four base conditions are recomputed LIVE; the verdict, bundle hash and resolved ranks are reused verbatim from the originating run. `[code: tools/dev-runner.sh:560-593]`

#### 26. `pr-no-record` → `pr-shadow-* \| pr-armed-blocked \| pr-merged-by-factory`

`T26-reeval-record-less`

- **Actor:** attended agent session invoking `--re-evaluate` on a PR with no prior record
- **Trigger:** the operator command on a green, approved PR whose terminal step never ran or never recorded
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::re_evaluate (:607-671)
- **Records:** `YR-MERGE-SHADOW or YR-MERGE`, `yr-merge-record/1`
- **Preconditions:** The originating run is located by matching the PR's base commit (head^) against this issue's local run bundles' `diff.base_sha`; no match at all is still a refusal. `[code+canon: tools/dev-runner.sh:444-472, :552-557; skills/factory/references/pipeline.md > Shadow merge choreography]`
- **Postconditions:** AUTO_MERGE now directly selects the record class: the same arming / server_ci-conflict / shadow-completion / sentinel / condition gates the live pipeline applies, via the same hoisted helpers — up to and including a real squash-merge. `[code+canon: tools/dev-runner.sh:607-671; skills/factory/references/pipeline.md > Shadow merge choreography]`<br>The ONE difference from the live pipeline: freshness is never rebase-remediated here (no worktree) — it is one more direct block condition, evaluated LAST in the armed order. `[code+canon: tools/dev-runner.sh:652-664]`<br>No board/issue write either way: the posted PR comment and (on an armed pass) the merge call are the only writes — so an armed BLOCKED from this path does NOT set Reason=Blocked. `[code+canon: tools/dev-runner.sh:428-431, :657-664 (emit_and_post only, no set_reason)]`

#### 27. `any point inside terminal_step` → `evaluator-environmental-exit`

`T27-evaluator-environmental`

- **Actor:** merge evaluator
- **Trigger:** a gh API blip, network drop, git fetch failure, or merge-API error while evaluating, recording, or merging
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh::terminal_step return-2 sites (:2460, :2461, :2472, :2474, :2476, :2482, :2491, :2496, :2500, :2508, :2526, :2539, :2556)
- **Records:** `yr-ledger-row/1 with outcome in-review and no decision`
- **Preconditions:** Classified environmental: no record, no merge, no streak reset, no hard Block — resumable. Only a genuine machinery/logic error resets or Blocks. `[code+canon: tools/dev-runner.sh:2372-2374, :2450-2455; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > The merge conditions (I4 disposition)]`
- **Postconditions:** A warn line in the run log; Status is still set to In Review; the ledger row records `in-review` with an EMPTY decision. `[code: tools/dev-runner.sh:2569-2571, :2574-2579, :2584-2597]`<br>Exception: after REBASE_REWROTE_REMOTE=1 this path becomes T17 instead. `[code: tools/dev-runner.sh:2534-2539, :2551-2556]`

#### 28. `board (claimed, Reason cleared)` → `board-in-review [+ board-reason-blocked]`

`T28-board-writes-by-evaluator`

- **Actor:** merge evaluator, through the one board field write
- **Trigger:** the terminal step finishing without a factory merge (In Review), or an armed block (Reason=Blocked, set BEFORE the record is posted)
- **Enforcement:** *partial* · **Guard site:** tools/board_plumbing.py::_attended_wall (:112-155) — unmerged; exempt for the runner by the YR_MACHINERY declaration
- **Records:** `a `dev-runner: **Blocked** — autonomous merge refused (<reason>): <detail>` comment on the ISSUE trail (not the PR)`, `YR-BOARD-FLIP is NOT emitted by the runner — machinery is exempt`
- **Preconditions:** Every Status/Reason write goes through tools/board_plumbing.py's single `set_field`. `[code+canon: tools/dev-runner.sh:966-968, :80; tools/board_plumbing.py:155-170; AGENTS.md > Repo map]`<br>Under it-30 slice 5 an attended caller would need a `YR-BOARD-FLIP` record first; the runner declares `YR_MACHINERY=1` and passes untouched. Both halves are UNMERGED. `[code: tools/board_plumbing.py:112-155 (unmerged); tools/dev-runner.sh:42-44 (`export YR_MACHINERY=1`, unmerged)]`
- **Postconditions:** A shadow WOULD-BLOCK never sets Reason=Blocked; only an armed block does. `[code+canon: tools/dev-runner.sh:2371-2372, :2431]`<br>A board write failure is a warn only, never fatal. `[code: tools/dev-runner.sh:966-967]`

#### 29. `any pr` → `in-window \| out-of-window`

`T29-record-window-membership`

- **Actor:** merge evaluator (shadow-completion computation)
- **Trigger:** an armed decision computing shadow completion
- **Enforcement:** **prevented** · **Guard site:** tools/merge_shadow.py::_last_merge_record / shadow_completion
- **Preconditions:** A PR enters the window only if some comment carries a WHOLE marker token (`YR-MERGE:` or `YR-MERGE-SHADOW:`) at RAW column 0. A prose mention of YR-MERGE, the bare fence word `yr-merge-record`, a longer marker name, or a blockquoted record leaves the PR OUT of the window rather than flagging it malformed. `[code: tools/merge_shadow.py:54-61, :240-272; tools/textutil.py:46-68 (prefix mode)]`<br>The LAST marker-bearing comment wins; its fenced block is parsed from the marker line onward, so a record that blockquotes an older one parses its OWN block. `[code: tools/merge_shadow.py:252-272]`
- **Postconditions:** PRs are ordered by PR NUMBER descending (not by merge or record time), the current PR excluded, and the first `window` record-bearing PRs form the window. `[code: tools/merge_shadow.py:337-356]`

#### 30. `any terminal merge outcome` → `a ledger row`

`T30-usage-ledger-terminus`

- **Actor:** dev-runner (fail-soft ledger append)
- **Trigger:** the success terminus after the terminal step
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh (:2581-2597)
- **Records:** `yr-ledger-row/1 (records.toml:268-275)`
- **Preconditions:** The ledger informs, never gates; the append is fail-soft. `[code+canon: AGENTS.md > Conventions (the usage ledger informs, never gates); tools/dev-runner.sh:2581-2597]`
- **Postconditions:** Outcome type/decision derived from the merge decision: merged/MERGED, in-review/BLOCKED (armed block), shadow-would-merge/WOULD-MERGE, shadow-would-block/WOULD-BLOCK, or in-review with no decision (environmental). `[code: tools/dev-runner.sh:2586-2597]`

## Where the code and the canon disagree

### [material] "Once armed, no shadow merges" — the it-30 canon says the shadow phase is strictly PRE-arming qualification; the evaluator re-computes the window on EVERY armed decision and drops an already-armed repo back to shadow records whenever the window degrades.

- **code:** The armed branch calls compute_shadow_complete at every decision (tools/dev-runner.sh:2495-2496); when SHADOW_DONE != true it posts a mode=shadow record with the note `armed, shadow-incomplete k/5` and returns (tools/dev-runner.sh:2497-2502). A window degrades post-arming whenever a human merges over a WOULD-BLOCK/BLOCKED record or a merge is reverted (tools/merge_shadow.py:332-333, :322-331), so a repo armed months ago can silently return to shadow with no separate signal beyond the note.
- **canon:** "the shadow phase is pre-arming qualification (once armed, no shadow merges)" (AGENTS.md:31); "The shadow phase is pre-arming qualification: once armed, merges are real, never shadow" (skills/factory/references/attended-lane.md > The output-gate model); the it-30 spec ruled the same and explicitly stated the ruling changes only the canon's statement, not the evaluator's code. The it-6 feature RFC, by contrast, DOES describe the refuse-to-honor mechanism the code implements.
- `tools/dev-runner.sh:2495-2502`, `tools/merge_shadow.py:307-356`, `AGENTS.md:26-33`, `skills/factory/references/attended-lane.md > The output-gate model`, `/srv/obsidian/vaults/obsidian/04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md (the output-gate ruling; 'Lower-pipeline mechanics: No dispatch, runner, or merge-evaluator behavior changes')`, `/srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > Shadow completion — the mechanical condition`

### [material] The attended hand-merge ban is stated as if a machine refuses it. Nothing does.

- **code:** No code on main classifies, intercepts, or records an attended `gh pr merge`. The only refusal exists in tools/wall.py:121-122 (`hand-merge`) plus its RULES entry (:231), registered through hooks/hooks.json's PreToolUse block — all UNMERGED (slice 5), the file additionally carrying uncommitted local edits, and the released plugin is 0.10.0, which predates every it-30 artifact. Even as built the classifier is a regex over the Bash command string: it fires on `gh pr comment N --body "ready to merge"` and does not fire on `gh api --method PUT /repos/o/r/pulls/N/merge`.
- **canon:** "PR merge (attended hand-merge) \| categorical — no record licenses it; merges execute through the evaluator \| fail-closed" (attended-lane.md > The walled-act map); "an attended hand-merge is categorically refused" (AGENTS.md:31); "Never: set a design active, arm a repo, or hand-merge a PR" (AGENTS.md:205).
- `tools/wall.py:112-122, :231`, `hooks/hooks.json (PreToolUse; unmerged)`, `.claude-plugin/plugin.json (version 0.10.0)`, `skills/factory/references/attended-lane.md > The walled-act map`, `AGENTS.md:26-33, :203-207`

### [material] The arming-edit wall as built refuses unconditionally, ignoring the very record its own rule text names — and refuses ANY manifest edit, not just `auto_merge`.

- **code:** `classify` returns `arming-edit` for any Write/Edit whose path ends in `.yr/factory.toml` (tools/wall.py:149-150) — a `check_cmd`, `stage_conduct` or `lint_cmd` edit included. `decide()` has an in-flight condition-satisfaction branch for `crossing-file` ONLY (tools/wall.py:252-260); `arming-edit` falls straight through to the deny at :261-268. `YR-HUMAN-INSTRUCTION` is never read by wall.py.
- **canon:** "Arming edit (`auto_merge`) \| `YR-HUMAN-INSTRUCTION` attributing her decision — arming is decided exclusively by the human, executed only under that instruction \| fail-closed" (attended-lane.md > The walled-act map); records.toml:394-401 names tools/wall.py as the reader of that record for "the arming and shared-branch wall conditions".
- `tools/wall.py:145-153`, `tools/wall.py:244-268`, `records.toml:394-401`, `skills/factory/references/attended-lane.md > The walled-act map`

### [material] wall.py's `in_scope()` scope guard is defined and never called.

- **code:** `in_scope` (tools/wall.py:48-72, added in the UNCOMMITTED local edit) has no caller anywhere in the tree — `decide()` (:244) and `close_check()` (:273) never consult it, and `main()` (:381-407) does not either. Its own docstring states that without this check "the walls fire in every session in every directory". As shipped it would.
- **canon:** "a wall that cannot evaluate a fail-closed act's condition refuses" and "a crashed delivery is loud and never locks the human out of her own session" (attended-lane.md > The lane protects itself, and its limits are named) — the lane's authority is scoped to factory work.
- `tools/wall.py:46-72`, `tools/wall.py:244-268`, `tools/wall.py:381-407`, `skills/factory/references/attended-lane.md > The lane protects itself, and its limits are named`

### [material] The armed BLOCKED path evaluates the conditions in a DIFFERENT order from the one the canon and the shadow record use, so the same failing state can be named by two different `failed_condition` values depending on arming.

- **code:** Shadow: `first_failed` walks SHADOW_ORDER = ci_green, freshness, terminal_approval, rank_gate (tools/merge_shadow.py:62-63, :128-133). Armed: terminal_approval, then rank_gate, then ci_green (tools/dev-runner.sh:2512-2516), with freshness excluded because it is remediated. A PR failing both ci_green and terminal_approval records `ci_green` in shadow and `terminal_approval` when armed.
- **canon:** "in order, in code, indeterminate = failed" with the order given as CI-green · freshness · terminal clean APPROVE · rank gate (skills/factory/references/gates.md > Gate table; skills/factory/references/pipeline.md > How the lower pipeline runs, Merge evaluator row); merge_shadow.py's own module docstring calls SHADOW_ORDER "the WOULD-BLOCK / BLOCKED reason" for both modes.
- `tools/merge_shadow.py:12-19, :62-63, :128-133`, `tools/dev-runner.sh:2512-2516`, `skills/factory/references/gates.md > Gate table`, `skills/factory/references/pipeline.md > How the lower pipeline runs`

### [material] `machinery_ok` is hardcoded true by the only emitter, so the reset branch that reads it is unreachable from any record the factory writes.

- **code:** `build_record` sets `"machinery_ok": True` as a literal (tools/merge_shadow.py:171); no code path anywhere writes false (a tree-wide grep finds only test fixtures constructing it). `classify_event`'s `if rec.get("machinery_ok") is False: return "reset"` (tools/merge_shadow.py:320-321) therefore fires only on a hand-authored record.
- **canon:** "a machinery contradiction resets the shadow streak" (pipeline.md > How the lower pipeline runs, Environmental vs code failure); the feature RFC's completion condition: "Any overridden WOULD-BLOCK, malformed record, or machinery error resets the streak" (04-merge-gate.md > Shadow completion — the mechanical condition).
- `tools/merge_shadow.py:167-197`, `tools/merge_shadow.py:307-334`, `skills/factory/references/pipeline.md > How the lower pipeline runs`, `/srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > Shadow completion — the mechanical condition`

### [material] `MERGE_AUTO_MERGE` arms any repo from the environment, bypassing the manifest read the canon calls the arming declaration.

- **code:** `read_auto_merge` returns the raw env value unvalidated and skips the git read entirely when MERGE_AUTO_MERGE is non-empty (tools/dev-runner.sh:347); the inline comment calls it "(for tests)" but nothing confines it to a test mode. `MERGE_MAIN_TIP` has the same shape for freshness (tools/dev-runner.sh:316).
- **canon:** "the manifest flag is re-read from the base ref's current tip at the moment of decision — never carried from the start-of-run manifest read — so a mid-run disable-by-PR cannot complete a merge under the prior setting"; "The manifest flag is a PR-audited declaration of intent" (04-merge-gate.md > The merge conditions, condition 5). AGENTS.md states auto_merge "re-read[s] the base ref's tip at decision time, never a start value".
- `tools/dev-runner.sh:343-354`, `tools/dev-runner.sh:306-323`, `tools/dispatch.py:147-183 (neither key is in the spawn allowlist, so the dispatch path is closed)`, `AGENTS.md:133-137`, `/srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > The merge conditions`

### [minor] `do_squash_merge`'s own comment claims it merges "into main ONLY (never a deploy/release target)"; the code merges the PR into whatever branch its manifest `base_ref` named.

- **code:** `gh pr merge "$PR_URL" --repo "$REPO" --squash` merges into the PR's base (tools/dev-runner.sh:404-405); the PR was created with `--base "$BASE_BRANCH"` where BASE_BRANCH is `${BASE_REF#origin/}` and BASE_REF is `${BASE_REF:-${MF_BASE_REF:-origin/main}}` (tools/dev-runner.sh:790, :2271). A repo declaring `base_ref = "origin/release"` would be squash-merged into `release`.
- **canon:** The comment at tools/dev-runner.sh:402 asserts main-only; "Merge ≠ ship: the factory merges only to the repo's integration branch" (pipeline.md > Judgment points) is the accurate statement, and the two do not agree.
- `tools/dev-runner.sh:402-405`, `tools/dev-runner.sh:790`, `tools/dev-runner.sh:2271`, `skills/factory/references/pipeline.md > Judgment points`

### [minor] The rank gate's bar differs between the active feature RFC and everything shipped.

- **code:** `[ "$REVIEW_RANK" -ge "$BUILD_RANK" ]` — an equal-rank pair passes (tools/dev-runner.sh:338-342).
- **canon:** The active feature RFC's condition 4: "the resolved pair still satisfies review-rank > build-rank, same provider, both ranked" (04-merge-gate.md > The merge conditions). The shipped canon says >= and explicitly blesses the equal-rank case: "an equal-rank pair that cleared intake also auto-merges cleanly" (pipeline.md > Model roles — the registry); gates.md and AGENTS.md likewise say >=.
- `tools/dev-runner.sh:335-342`, `/srv/obsidian/vaults/obsidian/04 projects/factory/iterations/6-autonomous-merge/04-merge-gate.md > The merge conditions`, `skills/factory/references/pipeline.md > Model roles — the registry`, `skills/factory/references/gates.md > Gate table`

### [minor] The registry says an armed YR-MERGE record is "never overturned by a re-evaluation"; the readers' rule is last-marker-wins, so a later shadow record IS the record every reader reads.

- **code:** `_last_merge_record` keeps the LAST marker-bearing comment (tools/merge_shadow.py:252-272); both `last-record` (used by --re-evaluate) and `classify_event` (used by shadow completion) read that one. A shadow re-evaluation posted after an armed MERGED/BLOCKED therefore becomes the record in force for the window and for the next re-evaluation.
- **canon:** records.toml:42 — "The armed output gate's record; never overturned by a re-evaluation (issue #70)." pipeline.md is more careful: the supersession "is a routing decision about which record is newest, not a retraction of the unrecoverable finding".
- `records.toml:35-42`, `tools/merge_shadow.py:252-272, :307-334`, `skills/factory/references/pipeline.md > Shadow merge choreography`

### [minor] The `server_ci_none_armed` record's shadow fields differ between the two code paths that emit it.

- **code:** terminal_step routes through `armed_block`, which always passes `--shadow-complete "${SHADOW_DONE:-false}"` — at that point still the initializer `false`, because compute_shadow_complete has not run (tools/dev-runner.sh:2458, :2432-2434, :2488-2491). The --re-evaluate twin emits the same block reason with no `--shadow-complete` at all, so the field is null (tools/dev-runner.sh:623-630).
- **canon:** The record schema is "a versioned contract" whose fields are "machine-parseable, not prose" and are what shadow completion computes over (tools/merge_shadow.py:2-42, :139-157).
- `tools/dev-runner.sh:2456-2493`, `tools/dev-runner.sh:620-630`, `tools/merge_shadow.py:139-197`

## Gaps

- **Nothing verifies the PR's head is still the head that was evaluated at the moment of the squash-merge. `do_squash_merge` calls `gh pr merge` with no head-oid match (tools/dev-runner.sh:404-405); a push landing between the CI wait and the merge call merges an unreviewed head. The --re-evaluate path DOES carry a head-agreement guard (tools/dev-runner.sh:509-513) — the live pipeline does not.** **← needs an owner ruling**<br>The whole gate model rests on 'the reviewed diff'. This is the one window in which the merged tree can differ from the judged tree, on the only path that writes to main autonomously.
- **A factory merge whose record post fails leaves a merged PR with NO merge record (tools/dev-runner.sh:2559-2561 logs a warn only). Such a PR is `seen == False` and is silently EXCLUDED from the shadow window rather than counted (tools/merge_shadow.py:260-272, :312-313).**<br>A successful autonomous merge can vanish from the qualification evidence, and the window quietly reaches further back in history than the canon's 'last 5 PRs' describes.
- **Shadow completion is only ever computed inside the ARMED branch (tools/dev-runner.sh:2495-2496). A non-armed repo's record carries null shadow_complete/shadow_progress, so the number that PERMITS arming is invisible until after the repo is armed.**<br>The canon makes completion the precondition for arming (closing.md > 2. Merge -> Done), but the only way to read the count from the machinery is to arm first and read the refusal note.
- **There is no state, record or canon sentence for 'armed but currently de-honoured' — the only trace is a display-only marker note (`armed, shadow-incomplete k/5`) that merge_shadow deliberately never persists into the JSON block (tools/merge_shadow.py:200-206).**<br>A machine reading only the record blocks cannot distinguish a never-armed repo from an armed repo whose window reset; the distinction is only in prose on line 1 of a comment.
- **The `sentinel` field is only populated on the armed path after shadow completion (tools/dev-runner.sh:2504-2510, :2432-2434). A shadow record never carries it.**<br>A reader auditing a stretch of shadow records cannot tell from them whether the global merge kill switch was thrown during that period.
- **Un-arming has no declared precondition, no record, and no wall — a missing key is simply `false, not an error` (tools/dev-runner.sh:350). The canon names a record for the arming edit (attended-lane.md > The walled-act map) but says nothing about removing the key. Likewise nothing names who may throw or clear the host sentinel, or requires a record for it (deploy/DISPATCH.md > Merge kill switch).** **← needs an owner ruling**<br>Both directions of the output gate's master switch are unrecorded acts; the sibling rule (arming) has a mandated record and its opposite does not.
- **`Reason=Blocked` set by an armed block is cleared only by the next CLAIM of that issue, by value (tools/dev-runner.sh:1155-1160). DISPATCH.md asks the human to clear it after the sentinel is lifted (deploy/DISPATCH.md > Merge kill switch); nothing enforces or detects a stale Blocked.**<br>The board's signal degrades: a Blocked left from a lifted sentinel is indistinguishable from a live block.
- **Freshness remediation rewrites the tree (rebase) and re-runs check_cmd and lint_cmd, but not the tester or the reviewer, and does not re-hash the review bundle (tools/dev-runner.sh:2396-2424; emit_and_post still cites the original $BUNDLE at :364). The record's base_sha/head_sha are post-rebase while bundle_sha256 names the pre-rebase artifact whose own diff.base_sha is the old base.**<br>The bundle hash is canonised as the artifact that 'names the decision's exact inputs' (04-merge-gate.md > The review bundle); after remediation it names inputs computed against a different base.
- **The window is ordered by PR NUMBER descending (tools/merge_shadow.py:342) and bounded by SHADOW_SCAN=40 PRs on that base (tools/dev-runner.sh:392), not by record or merge time. The canon says 'the repo's last 5 merge-record-bearing PRs' (pipeline.md > Judgment points).**<br>PR number order and merge order diverge whenever PRs land out of sequence; with >40 non-record-bearing PRs on the base the window can come back empty (successes 0, complete false) with no distinct signal.
- **records.toml's [lanes] table (design / epic / standalone / close, records.toml:387-392) has no lane covering the merge records, so tools/check_trail.py never presence-checks YR-MERGE / YR-MERGE-SHADOW even though both are registered.**<br>The detector built in it-30 slice 2 to find missing mandated records is blind to exactly the records the output gate depends on — a rule that exists for one lane and not its sibling.
- **The Done transition is owned entirely by GitHub Projects' built-in close->Done automation; no factory code writes or verifies it (docs/rfcs/0003-task-state-model.md > Decision; the runner writes only 'In Progress' and 'In Review').**<br>The terminal state of the whole lane depends on a GitHub-side setting nothing in the repo asserts, tests, or monitors — a silently disabled automation would leave every merged task at In Review.
- **The armed sentinel check and the merge call are separated by the whole freshness-remediation path (tools/dev-runner.sh:2506-2557), which can take minutes (rebase + full check_cmd + lint + a bounded CI re-wait). The sentinel is not re-read before `do_squash_merge`.** **← needs an owner ruling**<br>The kill switch is canonised as 'effective for the very next merge decision' (deploy/DISPATCH.md); a switch thrown during remediation does not stop the merge it was thrown to stop.
- **As-built slice 5 has no wall for the act of MERGING via a non-`gh pr merge` route, and its Bash classifier is a regex over the command string only (tools/wall.py:114-122): `gh api --method PUT /repos/o/r/pulls/N/merge` is not classified, while `gh pr comment N --body "ready to merge"` is refused as a hand-merge.**<br>The one categorical wall of this lane is both over- and under-inclusive on the paths an agent actually takes.
- **The canon names four repos as armed and names arming a non-delegable human act, yet every armed manifest in the workspace was keyed by a session (e.g. yellow-robots commit ef800cd 'arm: auto_merge = true — ordered by Jose, attended session 2026-08-05', Co-Authored-By Claude Fable 5; website #90; gilda 36520c9). The attribution lives in a git commit message, not in the YR-HUMAN-INSTRUCTION record the canon names, and no record grammar existed when three of the four were keyed.**<br>The evidence that arming was the human's decision is unstructured prose in four different repos' git histories; nothing can verify it mechanically, and check_trail has no lane that would.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **Gap 4: "There is no state, record or canon sentence for 'armed but currently de-honoured' — the only trace is a display-only marker note (`armed, shadow-incomplete k/5`)... A machine reading only the record blocks cannot distinguish a never-armed repo from an armed repo whose window reset; the distinction is only in prose on line 1 of a comment."**<br>The JSON block carries exactly that distinction. `build_record` persists `auto_merge`, `shadow_complete` and `shadow_progress` as top-level fields (tools/merge_shadow.py:175-177); `emit_and_post` always passes `--auto-merge "${AUTO_MERGE:-false}"` (tools/dev-runner.sh:371); and the armed-but-incomplete branch passes `--shadow-complete false --shadow-progress "$SHADOW_PROGRESS"` (tools/dev-runner.sh:2499). So a never-armed record reads `auto_merge:false, shadow_complete:null, shadow_progress:null` (no --shadow-* args at :2482) and an armed-de-honoured record reads `auto_merge:true, shadow_complete:false, shadow_progress:"k/5"` — fully machine-separable from the block alone. What is display-only is the NOTE, not the state; the excavation conflated the two (it cites merge_shadow.py:200-206, which is about the note). `tools/merge_shadow.py:167-197 (fields), :200-206 (note); tools/dev-runner.sh:371, :2482, :2497-2502`
- **T3 postcondition: "The decision-time git read of the manifest is skipped entirely; the posted record's `auto_merge` field carries the env value." (cited tools/dev-runner.sh:347, :371)**<br>First half verified (:347 returns the raw env value and skips the git read). Second half is not established: `--auto-merge` is argparse-constrained to `("", "true", "false")` (tools/merge_shadow.py:511) and `_tribool` maps anything else to None (:359-364). A `MERGE_AUTO_MERGE=yes` therefore makes the `record` subcommand exit non-zero, so `emit_and_post` returns 2 (an environmental exit, no record at all) rather than carrying the env value into the record. The headline claim — an unvalidated env value arms any repo for the arming BRANCH (`[ "$AUTO_MERGE" != true ]`) — does hold. `tools/dev-runner.sh:346-348, :371; tools/merge_shadow.py:359-364, :511`
- **T28 precondition citation "tools/dev-runner.sh:42-44 (`export YR_MACHINERY=1`, unmerged)"**<br>Lines 42-45 are the explanatory comment; the `export YR_MACHINERY=1` statement is at line 46. The substance (the runner declares itself machinery, unmerged in slice 5) is correct — `git diff origin/main...HEAD` shows tools/dev-runner.sh +6 — but the cited lines do not contain the declaration. `tools/dev-runner.sh:42-46; git diff --stat origin/main...HEAD`
- **Disagreement 5: "The armed BLOCKED path evaluates the conditions in a DIFFERENT order... A PR failing both ci_green and terminal_approval records `ci_green` in shadow and `terminal_approval` when armed."**<br>The order difference is real and correctly cited, but the failure scenario is unreachable on the live pipeline. The PR stage only runs downstream of the review gate, which requires `verdict_line "$RUN_DIR/review.md" = "VERDICT: APPROVE"` (:2138) and hard-blocks before any PR on a second failure (:2180). `shadow_terminal_approval` (:331-334) re-reads that same file under the same rule, so on a live armed build terminal_approval passes by construction and the armed order collapses to rank_gate -> ci_green. The divergence bites only on the record-less `--re-evaluate` path (:652-656), where `_find_run_by_base` may locate a run whose review.md never approved. Presented as a live naming divergence, it reads as a much larger defect than it is. `tools/dev-runner.sh:2135-2138, :2174-2181, :331-334, :2512-2516, :652-656`
- **Disagreement 10: "The registry says an armed YR-MERGE record is 'never overturned by a re-evaluation'; the readers' rule is last-marker-wins, so a later shadow record IS the record every reader reads."**<br>Overstated for the record the note is actually about. `re_evaluate` refuses before any read or write when the PR is not OPEN (`[ "$state" = "OPEN" ] \|\| reeval_refuse`, tools/dev-runner.sh:486), so a `YR-MERGE: MERGED` record — on a merged PR by definition — can never be superseded by any re-evaluation. Only an armed BLOCKED on a still-open PR is supersedable, and pipeline.md states that case explicitly and calls it "a routing decision about which record is newest, not a retraction" — which the excavation itself quotes as the canon side. The registry note is defensible as written. `tools/dev-runner.sh:486; records.toml:35-42; skills/factory/references/pipeline.md > Shadow merge choreography (issue #240 bullet)`
- **Gap 3: "...the only way to read the count from the machinery is to arm first and read the refusal note."**<br>The code fact is right — `compute_shadow_complete` is called only inside the armed branch of `terminal_step` (:2495-2496) and of `re_evaluate` (:633). But `tools/merge_shadow.py shadow-complete` is a documented standalone subcommand that prints `<complete> <successes> <window_size>` from a `gh pr list` dump plus a main-history dump, with no arming and no runner involved. The count is readable by anyone at any time; the gap should be "no runner path surfaces it", not "invisible until after the repo is armed". `tools/merge_shadow.py:35-38, :458-468, :526-534; tools/dev-runner.sh:2495-2496`
- **T15 precondition: "The freshness remediation assumes a SINGLE-COMMIT PR (it resolves the head's parent to find the pre-rebase base)." (source: canon, onboarding.md > The written invariants)**<br>The canon sentence is quoted accurately, but it does not describe the code at the cited site. `rebase_onto_tip` (:2396-2424) never resolves a parent — it fetches, rebases, force-pushes, then `rev-parse HEAD` and `rev-parse origin/$BASE_BRANCH`. The `head^` resolution the invariant describes lives in `--re-evaluate` (:515-516) and in the resume BASE_SHA branch (:2071-2075). Listing it as a precondition of T15 attributes to the remediation a mechanic it does not have; the canon/code mismatch itself went unflagged. `tools/dev-runner.sh:2396-2424, :515-516, :2071-2075; skills/factory/references/onboarding.md:138-140`
- **Gap 13: "The canon names four repos as armed and names arming a non-delegable human act, yet every armed manifest in the workspace was keyed by a session..."**<br>Framed as an unreconciled contradiction; the canon reconciled it explicitly. onboarding.md states "arming is the human's decision alone — a session may *execute* setting `auto_merge = true` only under the human's explicit instruction, and never decides it (the practiced norm: all four armed repos were keyed by sessions under explicit instruction; aligned at it-30)", and the it-30 spec records the alignment as a mandate. The residue — attribution living in a commit trailer rather than a YR-HUMAN-INSTRUCTION record — is real; the "canon says X, practice does Y" framing is not. `skills/factory/references/onboarding.md:20-25; /srv/obsidian/vaults/obsidian/04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md:65`

## Found by the verifier, missing from the excavation

- `tools/wall.py::board_check` (:325-357) has ZERO callers anywhere in the tree — not `main()`, not `decide()`, not `tools/promote.sh`, not `tests/test_wall.py` (a full-tree scan finds the definition only). Its own docstring asserts "One implementation, two callers: the funnel shells out to this, and the hook's raw-evasion classification resolves the same item." Neither exists. The board-write condition is instead spelled a SECOND time, inline, in `board_plumbing._attended_wall` (:130-152). The excavation flagged only `in_scope` as defined-and-never-called; there are three such sites, and this one is the guard for T28's own act. `tools/wall.py:325-357 (sole occurrence); tools/board_plumbing.py:130-152; tools/promote.sh:64-69 (calls promote-check only)`
- `tools/wall.py::_trail_has` (:205-211) is also dead, and `_gh_lines` (:195-202) is used only by it — so the entire trail-reading half of the wall engine is unreachable. Of the walled-act map's stated conditions, `_design_status_from_body` (crossing-file) is the ONLY one any code path ever evaluates. `tools/wall.py:195-211, :253-260 (the sole in-flight condition branch)`
- The unconditional deny in `decide()` is not specific to `arming-edit`. `board-write`, `push-shared`, `lifecycle-stamp` and `release-edit` all carry record conditions in the canon map yet fall through the same deny at :261-268. As built, a session that HAS posted `YR-BOARD-FLIP` is still refused a Bash `board_plumbing.py … set-field` call at the PreToolUse layer — so T28's "enforcement: partial" understates it: the record-satisfiable board wall exists only inside board_plumbing, and the layer above it is categorical. `tools/wall.py:133-134, :230-241, :244-268; skills/factory/references/attended-lane.md:55-62`
- A live path on which the armed `terminal_approval` block IS reachable — and is a false negative. `RUN_DIR` is per-PID (`runs/${ISSUE}-$$`, :119), an env-hold resume skips the review stage (:2140-2141), and `review.md` is carried into the new run dir only best-effort from `run.json`'s recorded prior dir (`[ -f "$PRIOR_RUN_DIR/$_f" ] && cp …`, :1254-1261). If that copy does not happen, `shadow_terminal_approval` reads a missing file, `APPROVE_RESULT=fail`, and an armed repo posts `YR-MERGE: BLOCKED — terminal_approval` + `Reason=Blocked` on a PR whose review actually approved. `tools/dev-runner.sh:119, :1249-1261, :2140-2141, :331-334, :2514, :2428-2438`
- The record's `review_verdict` and `rounds` come from the review BUNDLE (`rounds[-1].verdict`), which `review_bundle.py init` re-creates unconditionally on every invocation and which is NOT in the resume copy list. A resumed run past the review stage can therefore post a merge record carrying `review_verdict: null, rounds: 0` while `terminal_approval` reads pass from the copied review.md — the two halves of the record disagree about the same review. `tools/merge_shadow.py:165-166, :191-192; tools/dev-runner.sh:2079-2086, :1258`
- `armed_block` always passes `--sentinel "${SENTINEL_STATE:-ok}"` from terminal_step's initializer. The excavation caught the equivalent `shadow_complete: false` fiction on the `server_ci_none_armed` path (T11) but not this one: that same record asserts `sentinel: "ok"` although the sentinel file was never stat'd — the check sits downstream at :2506. `tools/dev-runner.sh:2458, :2432-2434, :2486-2493, :2504-2506`
- PR reuse (issue #84): `pr_create_attempt` adopts an already-open PR for the branch instead of creating a duplicate, so a re-dispatched build runs `terminal_step` against a PR that may already carry a merge record and posts a SECOND one. With last-marker-wins (merge_shadow.py:252-272) the newer record is what the shadow window and any later `--re-evaluate` read. No state or transition covers a second live-pipeline record on one PR — the excavation treats `--re-evaluate` as the only supersession route. `tools/dev-runner.sh:2255-2274, :2286-2288; tools/merge_shadow.py:252-272`
- `--dry-run` (:91-96, :1137-1150) reports the resolved plan — including `MF_AUTO_MERGE`, which is the START-OF-RUN bulk manifest parse (:729) that the merge decision explicitly never trusts (:721-722) — and exits before claim. It is the one operator surface that displays an arming value which is by design not the value any merge decision uses. `tools/dev-runner.sh:91-96, :721-722, :729, :1137-1150`

---

LIVENESS, stated precisely for this lane. Everything in tools/merge_shadow.py, the terminal-decision core of tools/dev-runner.sh, deploy/DISPATCH.md, docs/rfcs/*, and the four repos' .yr/factory.toml files is MERGED AND LIVE — the merge evaluator described here is what runs today. Everything from iteration 30 is NOT live: slices 1-4 (records.toml, tools/check_trail.py, skills/factory/references/attended-lane.md, tools/compile_slice.py + hooks/deliver.sh) are on main but the plugin version was never bumped (.claude-plugin/plugin.json is still 0.10.0, last touched by commit a6b9990 for skill 0.10.0), so no session receives them; slice 5 (tools/wall.py, the PreToolUse/Stop registrations in hooks/hooks.json, tools/board_plumbing.py::_attended_wall, the promote-check call in tools/promote.sh, and the `export YR_MACHINERY=1` in tools/dev-runner.sh:42-44) is UNMERGED on branch task/420-walls, failed its independent review at 0 of 5 acceptance criteria, and tools/wall.py additionally carries uncommitted local edits (git diff shows +90/-11: in_scope, the fail-soft _emit_event, the tolerant read_counts, and board_check). I have therefore recorded every wall in this lane at its main-branch enforcement level (unenforced), and described the slice-5 behaviour only as "as built, rejected".  WHAT THE ATTENDED LANE MAY DO AT A PR, as the tree actually states it. Permitted and canonised: run `tools/dev-runner.sh <issue#> --repo <owner/name> --re-evaluate <pr#>` (pipeline.md > Shadow merge choreography); rebase a freshness-stale branch by hand, content-identically, before that re-evaluation (same section — "the runner never rebases outside its own armed-merge remediation"); post comments. Forbidden by prose alone: merging (attended-lane.md > The walled-act map; AGENTS.md:203-207). Deliberately restricted in code: a re-evaluation of a PR that already carries a record can NEVER merge, rebase, or write board state, on an armed repo included — that is a hard code path (tools/dev-runner.sh:595-604), the one genuinely prevented restriction on the attended lane in this whole lane. Note the asymmetry: a re-evaluation of a RECORD-LESS PR on an armed repo CAN squash-merge (tools/dev-runner.sh:666-671), and it does so without any board write, so an armed BLOCKED produced that way never sets Reason=Blocked.  TWO ENGINES, ONE CORE. terminal_step (the live pipeline) and re_evaluate (the recovery lane) share the hoisted helpers (shadow_ci / shadow_freshness / shadow_terminal_approval / shadow_rank_gate / read_ci_timeout / read_server_ci / read_auto_merge / compute_shadow_complete / emit_and_post / do_squash_merge, tools/dev-runner.sh:130-412) but arrange them differently in three ways worth carrying forward: (1) freshness is remediated in terminal_step and is a plain block condition in re_evaluate; (2) terminal_step writes board state, re_evaluate never does; (3) the server_ci_none_armed record's shadow fields differ between them. MERGE_GIT_DIR is the seam that lets both run — the branch worktree for a live build, the base checkout for a re-evaluation.  FAIL-CLOSED SHAPE, verified in code rather than assumed: bucket_of returns "fail" for anything unrecognised (tools/merge_shadow.py:84-103); an unresolvable main tip is a freshness fail (tools/dev-runner.sh:321); an unparseable record is a window RESET (tools/merge_shadow.py:318-321); an ambiguous partial-SHA revert match counts as reverted (tools/merge_shadow.py:294-304); a malformed merge_ci_timeout or server_ci blocks rather than defaulting (tools/dev-runner.sh:237-240, :261-264). The one direction that fails OPEN by design is the sentinel — `[ -e "$MERGE_SENTINEL" ]` on an unset override reads as clear, which is exactly why MERGE_SENTINEL is in dispatch's spawn allowlist (tools/dispatch.py:154-157, :164).
