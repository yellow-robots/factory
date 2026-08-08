<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The deterministic gates

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `gate-params-unresolved` | A runner process exists but has not yet read `.yr/factory.toml`; no gate parameter is bound. Only the opening self-identifying log line exists. | Nothing durable. The runner's stderr, which dispatch redirects into a per-run log file under `$DEV_RUNNER_HOME/runs/<issue>-<pid>/`; RUN_DIR is computed but not yet created. | `tools/dev-runner.sh:115-120` |
| `gate-params-bound` | All gate parameters resolved once, at start-of-run, from the manifest snapshot: CHECK_CMD + its source, CHECK_TIMEOUT, CHECK_IDLE_TIMEOUT, LINT_CMD, LINT_FIX_CMD, LENS_CMD, TEST_PATHS, ARTIFACT_GLOBS, STAGE_CONDUCT_BLOCK. Never re-read at decision time (unlike auto_merge/merge_ci_timeout/server_ci). | Shell variables of the live runner process only; echoed as `check_cmd: … (source: …)` / `check_timeout: …s (source: …)` / `check_idle_timeout: …s (source: …)` lines into the run log. Not persisted to any file, board field, or trail. | `tools/dev-runner.sh:803-866` |
| `manifest-absent (un-onboarded)` | `.yr/factory.toml` read yielded nothing at the pinned manifest sha AND nothing in the working tree — the repo was never onboarded, distinct from a manifest that exists but is sparse. | MF_RAW empty in the runner process; becomes the MF_ONBOARD_MSG text folded into the Needs-info bounce. Server-side, the absence of the file at the repo's default branch (probed by the epic gate via the contents API). | `tools/dev-runner.sh:708-718; tools/epic_gate.py:762-781` |
| `dor-refused-nowrite` | The runner refused before any board write and before any LLM call: issue not open, not on the board, Status != Ready, or a typed-but-wrong Issue Type. Exit code 3 (`gate()`), distinct from `die()`'s 1. | Nothing durable at all — no board field change, no comment, no ledger row. Only the runner's exit code and its stderr line in the run log. | `tools/dev-runner.sh:87, tools/dev-runner.sh:970-984` |
| `needs-info-bounced` | A DoR content or manifest-key gate rejected the work before claim: empty acceptance criteria, untyped Ready item, un-onboarded repo, undeclared `check_cmd`, rejected `check_timeout`/`check_idle_timeout`/`test_paths`/`artifact_globs`/`stage_conduct`, unknown/inverted/cross-provider model pair, or a missing standalone `YR-TASK-GATES` record. All reasons are concatenated into one message. | Projects fields on the issue's project item: Status=Backlog, Reason=Needs-info. Plus one issue-trail comment (`dev-runner: bounced to **Needs-info** — …`) and one ledger row (`outcome-type: needs-info`) in `$DEV_RUNNER_HOME/ledger/rows.jsonl`. | `tools/dev-runner.sh:1128-1135` |
| `claimed-gates-pending` | Task claimed (Status=In Progress), worktree cut, implement and test stages complete; the check/lint/lens tier has not yet run for this branch. | Projects Status field = In Progress; stage markers `01-implement.done` / `02-test.done` under `$DEV_RUNNER_HOME/state/<owner>--<name>--<branch-slug>/`; the worktree at `$DEV_RUNNER_HOME/wt/<owner>--<name>--<branch-slug>`. | `tools/dev-runner.sh:1152-1160, tools/dev-runner.sh:1215-1222, tools/dev-runner.sh:1651, tools/dev-runner.sh:1748` |
| `tester-boundary-violated` | The tester stage changed a path that is neither under the declared `test_paths` surface nor matched by `artifact_globs` — computed structurally by diffing the tester's tree against the implementer's checkpoint tree, not by prompt. | `$RUN_DIR/boundary-violation.diff` (the full tester diff), then the Blocked disposition below. | `tools/dev-runner.sh:1682-1732` |
| `check-green` | `check_cmd` exited 0 in the worktree at some site (initial `check`, `check-repair-recheck`, `lint-repair-recheck`, `review-repair-recheck`, or `rebase-recheck`). | `$RUN_DIR/checks.log` (overwritten by each invocation — only the LAST run's output survives); one entry in `$RUN_DIR/gate-durations.json` `{site, elapsed_seconds, disposition:"pass"}`, which `ledger.py append` folds into the ledger row's `gates` list. | `tools/dev-runner.sh:1849-1862, tools/dev-runner.sh:1833-1840` |
| `check-red-first-round` | `check_cmd` exited non-zero (and not 126/127) on its first pass; exactly one LLM repair attempt is licensed, run at the registry's `check_repair` stage tier when set, else the build model. | `$RUN_DIR/checks.log` + `$RUN_DIR/repair.log`; a gate-durations entry with disposition `fail` (or `timeout` on an observed idle expiry). | `tools/dev-runner.sh:1950-1956, tools/dev-runner.sh:1842-1848` |
| `gate-idle-killed (observed expiry)` | The wrapper itself killed a check/lint/lens process group because its log(s) grew zero bytes for `check_idle_timeout` seconds. Distinguished by construction from a child that exited 124/137 on its own — only the monitor's own decision sets the expired flag. | A tail appended to that gate's own log (`checks.log` / `lint.log` / `lens.md`) naming the idle duration, total elapsed and BOTH windows; a gate-durations entry with disposition `timeout`. | `tools/dev-runner.sh:1804-1812, tools/dev-runner.sh:1854-1859, tools/dev-runner.sh:1894-1899, tools/dev-runner.sh:2051-2054` |
| `live-gate-advised` | `check_timeout` elapsed while the gate's log was still growing. Nothing is killed and nothing gates; exactly one advisory fires per invocation. | One run-log line AND one comment on the **issue** trail (not the PR) — `comment()` is `gh issue comment`. The comment carries no registered `YR-` marker. | `tools/dev-runner.sh:1814-1818, tools/dev-runner.sh:969` |
| `gate-env-hold` | A check (126/127), lint (126/127) or autofix (126/127) command could not execute at all. The toolchain, not the code, is at fault; no LLM repair is attempted. | Projects Reason=Blocked; `$STATE_DIR/env-hold` marker file; `$STATE_DIR/run.json` resume manifest; the worktree + stage markers PRESERVED (no cleanup_wt); one issue-trail comment naming the failing command and its own log; a ledger row `outcome-type: env-hold`. | `tools/dev-runner.sh:1194-1201, tools/dev-runner.sh:1933-1944` |
| `gate-blocked-terminal` | A gate's verdict is terminal-negative after its licensed repair: checks still failing, lint still failing, checks/lint failing after review-repair, boundary violation, or an unresolved background task making a green re-read untrustworthy. | Projects Reason=Blocked; one issue-trail comment (`dev-runner: **Blocked** — …`); `$RUN_DIR/block-salvage.patch` (and `final.patch`/`boundary-violation.diff` where those paths wrote one); a ledger row `outcome-type: blocked`; the worktree, branch and stage markers are torn down. | `tools/dev-runner.sh:1166-1172, tools/dev-runner.sh:1203-1211, tools/dev-runner.sh:1961-1967, tools/dev-runner.sh:2032-2039` |
| `lint-tier-off` | The repo declares no `lint_cmd` (and no env override). The tier is a complete no-op — no probe, no output, no warning. | LINT_CMD empty in the runner process; nothing anywhere else. `.yr/factory.toml` simply lacks the key. | `tools/dev-runner.sh:859-862, tools/dev-runner.sh:1978` |
| `lint-green` | `lint_cmd` exited 0 at some site (`lint`, `lint-autofix-recheck`, `lint-repair-recheck`, `review-repair-lint`, `rebase-lint`). | `$RUN_DIR/lint.log` (overwritten per invocation); a gate-durations entry with disposition `pass`. | `tools/dev-runner.sh:1889-1902, tools/dev-runner.sh:1982` |
| `lens-tier-off` | The repo declares no `lens_cmd`. No run, no artifact, no PR comment. | LENS_CMD empty in the runner process; the key absent from `.yr/factory.toml`. | `tools/dev-runner.sh:863-865, tools/dev-runner.sh:2048` |
| `lens-artifact-present` | The lens ran and wrote non-empty markdown to stdout (findings, or an appended did-not-run-cleanly note). Its exit code was read and recorded but never gated. | `$RUN_DIR/lens.md` (stdout) and `$RUN_DIR/lens.log` (stderr, deliberately separate so a traceback never reaches the trail); a gate-durations entry. Once a PR exists, `$RUN_DIR/lens-comment.md` is posted as a PR-trail comment whose first line is `YR-LENS (advisory)`. | `tools/dev-runner.sh:1911-1920, tools/dev-runner.sh:2356-2361` |
| `gates-complete-for-branch` | The whole check→lint→lens tier passed for this branch. Durable across runner invocations: a later relaunch skips the entire tier. | The marker file `$DEV_RUNNER_HOME/state/<owner>--<name>--<branch-slug>/03-check.done`. | `tools/dev-runner.sh:2060, tools/dev-runner.sh:1218-1219` |
| `gates-skipped-on-resume` | A relaunch found `03-check.done` present. `check_cmd`, `lint_cmd` and `lens_cmd` are ALL skipped for this invocation and CHECK_RC is set to 0 by assertion, not by observation. | `03-check.done` marker; `checks.log` copied forward from the prior run dir named in `$STATE_DIR/run.json`; the value 0 is then written into `review-bundle.json` as `check.exit_code`. | `tools/dev-runner.sh:1945-1948, tools/dev-runner.sh:1257-1262, tools/dev-runner.sh:2080-2086` |
| `server-ci-verdict` | The PR head's GitHub check rollup: the `test` job runs `pytest tests/ -n auto -q` then the manifest-read Lint backstop. One certification per head; a superseded in-flight run is cancelled. | GitHub-side check runs on the PR head SHA, read back by the merge evaluator via `gh pr view --json statusCheckRollup` into `$RUN_DIR/check-rollup.json`. | `.github/workflows/ci.yml:1-51, tools/dev-runner.sh:271-276` |
| `artifact-advisory-unrecorded` | The state of an upper-pipeline artifact with respect to `check_links` / `check_task` / `check_supersession`: run or not run, green or red. There is no third state, because there is no place the answer is written. | NOWHERE. These tools print `<file>: <message>` lines to the operator's stdout and set an exit code; no caller in the tree records, reads, or gates on that result. Grep confirms zero callers outside the tools' own files and their tests. | `tools/check_links.py:129-140, tools/check_task.py:296-312, tools/check_supersession.py:882-921` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `gate-params-unresolved` → `gate-params-bound` | dev-runner (tools/dev-runner.sh, the runner process itself) | **prevented** | tools/dev-runner.sh:684-691 (run-start fetch) + tools/dev-runner.sh:151-215 `_manifest_read` (the one parameterized manifest reader). Reachable on the only path a dispatched build takes. |
| 2 | `gate-params-bound` → `dor-refused-nowrite` | dev-runner | **prevented** | tools/dev-runner.sh:970-984, in the runner's main path. Reachable: every dispatched build passes through it. |
| 3 | `gate-params-bound` → `needs-info-bounced` | dev-runner | **prevented** | tools/dev-runner.sh:1002-1010 (accumulation) + tools/dev-runner.sh:1128-1135 (disposal). Reachable on the dispatched path. |
| 4 | `claimed-gates-pending` → `tester-boundary-violated` | dev-runner (the boundary guard, not the tester stage) | **prevented** | tools/dev-runner.sh:1682-1732 (structural tree diff, not a prompt). Reachable on every build that reaches the tester stage. |
| 5 | `claimed-gates-pending` → `check-green` | dev-runner (`run_checks`, the runner not the LLM) | **prevented** | tools/dev-runner.sh:1849-1862 + 1945-1949. Reachable on every build. |
| 6 | `check-green` → `check-red-first-round` | dev-runner | **prevented** | tools/dev-runner.sh:1950-1957. Reachable. |
| 7 | `check-red-first-round` → `gate-blocked-terminal` | dev-runner | **prevented** | tools/dev-runner.sh:1961-1967. Reachable. |
| 8 | `check-green` → `gate-env-hold` | dev-runner (`env_hold` → `env_hold_record`) | **prevented** | tools/dev-runner.sh:1926 (`is_env_failure`) called at 1950, 1958, 2026, 2410. Reachable at every check site. |
| 9 | `check-green` → `gate-idle-killed` | dev-runner (`_gate_monitor`, the liveness wait loop) | **prevented** | tools/dev-runner.sh:1790-1831 `_gate_monitor`, shared by run_checks / run_lint / run_lens. Reachable at all eight gate invocation sites. |
| 10 | `check-green` → `live-gate-advised` | dev-runner (`_gate_monitor`) | detected | tools/dev-runner.sh:1814-1818. Reachable; but it only informs — by construction it gates nothing. |
| 11 | `check-green` → `lint-green` | dev-runner (`run_lint`) | *partial* | tools/dev-runner.sh:1978-1982. Reachable when the manifest declares lint_cmd; entirely absent otherwise. |
| 12 | `lint-green` → `lint-green` | dev-runner (the ruled lint-repair scope) | **prevented** | tools/dev-runner.sh:1983-2039. Reachable. |
| 13 | `lint-green` → `gate-blocked-terminal` | dev-runner | **prevented** | tools/dev-runner.sh:2032-2039. Reachable. |
| 14 | `lint-green` → `gate-env-hold` | dev-runner (`lint_env_hold`) | **prevented** | tools/dev-runner.sh:1940-1944, called at 1983/1991/1996/2029/2171. Reachable. |
| 15 | `lint-green` → `lint-green` | dev-runner (`run_lint` invoking this repo's declared `lint_cmd`, whose SECOND arm is the cardinality guard) | **prevented** | qa/cardinality.py:184-227 `main`, reached through `.yr/factory.toml:36 lint_cmd` → tools/dev-runner.sh:1982. Also reached by server CI at .github/workflows/ci.yml:43-51. |
| 16 | `lint-green` → `lens-artifact-present` | dev-runner (`run_lens`) | ⚠️ **unenforced** | tools/dev-runner.sh:2048-2059. Reachable when lens_cmd is declared; nothing enforces its findings anywhere. |
| 17 | `lens-artifact-present` → `lens-artifact-present` | dev-runner (post-PR trail posting) | detected | tools/dev-runner.sh:2356-2361. Reachable only after a successful PR open. |
| 18 | `lens-artifact-present` → `gates-complete-for-branch` | dev-runner | **prevented** | tools/dev-runner.sh:2060. Reachable. |
| 19 | `gates-complete-for-branch` → `gates-skipped-on-resume` | dev-runner (resume path) | **prevented** | tools/dev-runner.sh:1945-1948. Reachable on every env-hold resume. |
| 20 | `gates-complete-for-branch` → `check-green` | dev-runner (the review-repair mutation path) | **prevented** | tools/dev-runner.sh:2164-2174. Reachable on any build whose first review round was not a clean APPROVE. |
| 21 | `gates-complete-for-branch` → `check-green` | dev-runner (`rebase_onto_tip`, the armed-merge freshness remediation) | **prevented** | tools/dev-runner.sh:2407-2418. Reachable only on the armed-merge path when main moved. |
| 22 | `gates-complete-for-branch` → `server-ci-verdict` | GitHub Actions (the `ci` workflow), triggered by native GitHub automation on `pull_request` | **prevented** | .github/workflows/ci.yml:29-51 (server-side, outside the runner's process). Reachable for every PR. |
| 23 | `check-green` → `check-green` | dev-runner (indirectly: `check_model_refs` runs INSIDE the pytest suite that is `check_cmd`) | **prevented** | tests/test_check_model_refs.py:200-212 riding `check_cmd` at tools/dev-runner.sh:1949 and `.github/workflows/ci.yml:30`. Reachable on both hosts. |
| 24 | `artifact-advisory-unrecorded` → `artifact-advisory-unrecorded` | an attended agent or human operator, by hand | ⚠️ **unenforced** | No guard. Verified by grep: no `.sh`, `.py`, `.json`, `.yml` or `.toml` file in the tree outside the tools themselves and `tests/` invokes check_links, check_task or check_supersession. `tools/promote.sh` — the operator promote command — does not call any of them. |
| 25 | `gate-params-unresolved` → `needs-info-bounced` | epic-gate (tools/epic_gate.py, the org-wide `/sweep` pass) | **prevented** | tools/epic_gate.py:1050-1067 (epic child) and tools/epic_gate.py:1151-1167 (standalone). Reachable on every sweep tick. |
| 26 | `gate-params-unresolved` → `dor-refused-nowrite` | epic-gate (the gate-touching wall — gate EVOLUTION is attended, the pipeline builds under fixed gates) | *partial* | tools/epic_gate.py:1026-1042, placed deliberately before the `_pi_node` board lookup so a child not yet on the board still refuses. Reachable only on the epic-child promotion path. |
| 27 | `check-green` → `check-green` | dev-runner (the review bundle assembly) | **prevented** | tools/dev-runner.sh:2080-2086. Reachable on every build that reaches review. |
| 28 | `gate-params-bound` → `gate-params-bound` | dev-runner (`--dry-run`) | **prevented** | tools/dev-runner.sh:1137-1150. Reachable only on the explicit attended flag. |

### Detail

#### 1. `gate-params-unresolved` → `gate-params-bound`

`G1`

- **Actor:** dev-runner (tools/dev-runner.sh, the runner process itself)
- **Trigger:** Start of every non-`--re-evaluate` run, immediately after the bounded run-start `git fetch origin`.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:684-691 (run-start fetch) + tools/dev-runner.sh:151-215 `_manifest_read` (the one parameterized manifest reader). Reachable on the only path a dispatched build takes.
- **Records:** `run-log lines only (`manifest sha: …`, `check_cmd: … (source: …)`, `check_timeout: …s (source: …)`, `check_idle_timeout: …s (source: …)`) — no registered record grammar`
- **Preconditions:** A bounded, prompt-free `fetch origin` (MANIFEST_FETCH_TIMEOUT, default 15s) succeeded, or the checkout is not a git repo / has no origin (skipped, not environmental). `[code+canon: tools/dev-runner.sh:684-691]`<br>The manifest is read from a single sha pinned off MANIFEST_REF (default `origin/main`), never the base checkout's working tree, falling back to the working-tree file only when the sha read yields nothing. `[code+canon: tools/dev-runner.sh:706-712]`
- **Postconditions:** CHECK_CMD (env > manifest, no built-in fallback), CHECK_TIMEOUT (env > manifest > 1200), CHECK_IDLE_TIMEOUT (env > manifest > 300), LINT_CMD / LINT_FIX_CMD / LENS_CMD (env > manifest, absent = off), TEST_PATHS (default `["tests/"]`), ARTIFACT_GLOBS (default `["__pycache__/","*.pyc"]`), STAGE_CONDUCT_BLOCK are all bound for the whole run. `[code+canon: tools/dev-runner.sh:799-866]`<br>Each resolved value and its source is logged; the manifest sha is logged. `[code: tools/dev-runner.sh:711, tools/dev-runner.sh:804, tools/dev-runner.sh:831, tools/dev-runner.sh:857]`

#### 2. `gate-params-bound` → `dor-refused-nowrite`

`G2`

- **Actor:** dev-runner
- **Trigger:** The structural DoR gate, run after the issue and project-item reads and before any board write or LLM call.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:970-984, in the runner's main path. Reachable: every dispatched build passes through it.
- **Records:** `none — stderr only (`dev-runner: NOT READY: …`)`
- **Preconditions:** Issue state != OPEN, OR the issue has no project item on PROJECT_NUMBER, OR Status != Ready, OR the issue carries a non-empty Issue Type that is not REQUIRE_ISSUE_TYPE (default `Task`). `[code+canon: tools/dev-runner.sh:971-984]`
- **Postconditions:** Exit 3. No Status write, no Reason write, no comment, no ledger row, no worktree, no LLM invocation. `[code+canon: tools/dev-runner.sh:87, tools/dev-runner.sh:970]`<br>A typed-but-wrong Type (e.g. Feature) deliberately stays Ready so the epic-gate sweeper can see it. `[code: tools/dev-runner.sh:975-984]`

#### 3. `gate-params-bound` → `needs-info-bounced`

`G3`

- **Actor:** dev-runner
- **Trigger:** The DoR content gate: any of nine accumulated NEEDS_INFO reasons is non-empty at tools/dev-runner.sh:1129.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1002-1010 (accumulation) + tools/dev-runner.sh:1128-1135 (disposal). Reachable on the dispatched path.
- **Records:** `an issue-trail comment `dev-runner: bounced to **Needs-info** — …` (NO registered `YR-` grammar)`, `a `yr-ledger-row/1` row with `outcome-type: needs-info``
- **Preconditions:** MF_ONBOARD_MSG — no `.yr/factory.toml` at the manifest ref or in the working tree (the runner's backstop to the epic gate's admission wall). `[code+canon: tools/dev-runner.sh:717-718]`<br>Acceptance-criteria section contains no alphanumeric character (the Issue Form's bare `- [ ]` default does not count). `[code+canon: tools/dev-runner.sh:994-1002]`<br>TYPE_NEEDS_INFO — the item is Ready and UNTYPED (an untyped item would otherwise win the dispatch lock every tick with no state change). `[code+canon: tools/dev-runner.sh:985-993]`<br>`check_cmd` not declared in the manifest — judged on the manifest ALONE, regardless of any environment CHECK_CMD. `[code+canon: tools/dev-runner.sh:743-749]`<br>`check_timeout` declared but not a positive integer (parsed through the typed `__absent__`/`__error__` channel so a declared 0 and a whole-manifest parse failure stay distinct from an absent key). `[code+canon: tools/dev-runner.sh:805-831]`<br>`check_idle_timeout` declared but not a positive integer — same discipline. `[code+canon: tools/dev-runner.sh:833-857]`<br>`test_paths` or `artifact_globs` declared but not a non-empty array of non-empty, repo-relative strings (none absolute, none containing a `..` component). `[code+canon: tools/dev-runner.sh:731-762, tools/dev-runner.sh:196-207]`<br>`stage_conduct` declared but malformed, or containing one of the four routed stub literals (`TESTER`, `REVIEWER`, `tests FAIL`, `REQUESTED CHANGES`). `[code+canon: tools/dev-runner.sh:764-786, tools/dev-runner.sh:208-213]`<br>Build or review model unknown to the registry, or a ranked pair that is inverted or cross-provider. `[code+canon: tools/dev-runner.sh:1073-1090]`<br>A Type=Task issue with NO native sub-issue parent whose trail carries no well-formed `YR-TASK-GATES` record (marker on its own line, non-empty `review:`/`fit:`/`who:`, `fit:` not a placeholder). `[code+canon: tools/dev-runner.sh:879-946]`
- **Postconditions:** Status=Backlog and Reason=Needs-info written to the project item; one issue comment naming every accumulated reason; one ledger row `needs-info`; exit 3. Under `--dry-run` this is a read-only `gate()` refusal instead — nothing is written. `[code: tools/dev-runner.sh:1129-1135]`<br>Fires before claim, before the worktree, before any stage — no LLM is ever invoked. `[code+canon: tools/dev-runner.sh:1128, AGENTS.md > Conventions]`

#### 4. `claimed-gates-pending` → `tester-boundary-violated`

`G4`

- **Actor:** dev-runner (the boundary guard, not the tester stage)
- **Trigger:** Immediately after the tester stage returns, the runner stages the worktree and diffs `IMPL_TREE` against `TESTER_TREE`.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1682-1732 (structural tree diff, not a prompt). Reachable on every build that reaches the tester stage.
- **Records:** `issue-trail comment `dev-runner: **Blocked** — tester modified files outside the declared test surface (…)``, ``$RUN_DIR/boundary-violation.diff``, `ledger row `blocked``
- **Preconditions:** The tester stage exited 0 and left no unresolved background-task conversion. `[code: tools/dev-runner.sh:1668-1680]`<br>At least one changed path is neither under a declared `test_paths` prefix (directory-anchored: normalized to a trailing slash, so `src/tests` never matches `src/tests_extra/`) nor matched by an `artifact_globs` pattern (a trailing-slash glob matches any path COMPONENT). `[code+canon: tools/dev-runner.sh:1687-1725]`
- **Postconditions:** `$RUN_DIR/boundary-violation.diff` written before teardown; run ends Blocked with a message naming the resolved surface AND its source (`manifest` or `default`). No auto-revert. `[code+canon: tools/dev-runner.sh:1726-1732]`

#### 5. `claimed-gates-pending` → `check-green`

`G5`

- **Actor:** dev-runner (`run_checks`, the runner not the LLM)
- **Trigger:** The check gate site: `run_checks check` at tools/dev-runner.sh:1949, once `03-check.done` is absent.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1849-1862 + 1945-1949. Reachable on every build.
- **Records:** ``$RUN_DIR/checks.log``, ``$RUN_DIR/gate-durations.json` entry (folded into the ledger row's `gates` list; informs window calibration only, never gates)`
- **Preconditions:** The child runs `cd $WT` with `$BASE_REPO/.venv/bin` and `$BASE_REPO/node_modules/.bin` prepended to PATH, and GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM neutralized to /dev/null so host-ambient git config can never make the check greener than CI. `[code+canon: tools/dev-runner.sh:1852]`<br>The child is `setsid`'d into its own process group so the liveness monitor can kill the whole tree. `[code+canon: tools/dev-runner.sh:1852, tools/dev-runner.sh:1758-1772]`
- **Postconditions:** CHECK_RC=0; `$RUN_DIR/checks.log` holds the merged stdout+stderr; one gate-durations entry `{site:"check", disposition:"pass"}`. `[code: tools/dev-runner.sh:1849-1862]`

#### 6. `check-green` → `check-red-first-round`

`G6`

- **Actor:** dev-runner
- **Trigger:** `run_checks check` returned non-zero and not 126/127.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1950-1957. Reachable.
- **Records:** ``$RUN_DIR/repair.log``, `gate-durations entry with disposition `fail` or `timeout``
- **Preconditions:** `is_env_failure` is false — the exit code is neither 126 nor 127. `[code+canon: tools/dev-runner.sh:1926, tools/dev-runner.sh:1950]`
- **Postconditions:** Exactly ONE repair stage runs, under CHECK_REPAIR_ID (the registry's `check_repair` stage tier when set, else the build model), with a tests-frozen prompt: fix production code, do not modify tests. `[code+canon: tools/dev-runner.sh:1951-1955]`<br>A quota/rate-limit signature in the repair log routes to `llm_quota_hold` (environmental) instead of counting as a repair. `[code: tools/dev-runner.sh:1956]`

#### 7. `check-red-first-round` → `gate-blocked-terminal`

`G7`

- **Actor:** dev-runner
- **Trigger:** `run_checks check-repair-recheck` returned non-zero after the single repair, OR the repair stage ended its turn with an unresolved background-task conversion.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1961-1967. Reachable.
- **Records:** `issue-trail comment `dev-runner: **Blocked** — checks still failing after one repair (log: …)``, ``$RUN_DIR/block-salvage.patch``, `ledger row `blocked``
- **Preconditions:** Exactly one repair attempt has been made; there is no second. `[code+canon: tools/dev-runner.sh:1957, skills/factory/references/gates.md > Judgment points]`<br>An unresolved background task at the repair's own stage end blocks even a re-check that came back GREEN — the abandoned task's kill window overlaps the re-check. `[code+canon: tools/dev-runner.sh:1960-1967]`
- **Postconditions:** Reason=Blocked, a Blocked comment naming checks.log, `block-salvage.patch` staged before teardown, ledger row `blocked`, worktree + branch + state torn down. `[code+canon: tools/dev-runner.sh:1166-1172, tools/dev-runner.sh:1203-1211]`

#### 8. `check-green` → `gate-env-hold`

`G8`

- **Actor:** dev-runner (`env_hold` → `env_hold_record`)
- **Trigger:** `run_checks` returned exit 126 or 127 at ANY of its five sites (check, check-repair-recheck, lint-repair-recheck, review-repair-recheck is a bare fail_blocked, rebase-recheck returns 2).
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1926 (`is_env_failure`) called at 1950, 1958, 2026, 2410. Reachable at every check site.
- **Records:** `issue-trail comment `dev-runner: **Environmental hold** — check command could not execute (exit N)…``, ``$STATE_DIR/env-hold`, `$STATE_DIR/run.json``, `ledger row `env-hold``
- **Preconditions:** Exit code is exactly 126 (found-but-not-executable) or 127 (command not found) — the harness could not execute at all. `[code+canon: tools/dev-runner.sh:1921-1926]`<br>No LLM repair is attempted on an environment failure — handing it to the LLM invites host-mutating fixes. `[code+canon: tools/dev-runner.sh:1921-1926, skills/factory/references/gates.md > Judgment points]`
- **Postconditions:** `$STATE_DIR/run.json` written, `$STATE_DIR/env-hold` marker dropped, Reason=Blocked, an Environmental-hold comment naming the preserved worktree, ledger row `env-hold`, then `die`. `cleanup_wt` is deliberately NOT called. `[code+canon: tools/dev-runner.sh:1194-1201, tools/dev-runner.sh:1933-1939]`<br>A relaunch reuses the preserved worktree and skips every stage carrying a `.done` marker. `[code+canon: tools/dev-runner.sh:1244-1248]`

#### 9. `check-green` → `gate-idle-killed`

`G9`

- **Actor:** dev-runner (`_gate_monitor`, the liveness wait loop)
- **Trigger:** The monitor observes zero byte growth in the invocation's log(s) for `check_idle_timeout` seconds while the child is still alive.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1790-1831 `_gate_monitor`, shared by run_checks / run_lint / run_lens. Reachable at all eight gate invocation sites.
- **Records:** `the appended log tail in checks.log / lint.log / lens.md`, `gate-durations entry `{disposition:"timeout"}``
- **Preconditions:** The child was backgrounded via `setsid`, so its pgid equals its pid and the whole tree is killable. `[code+canon: tools/dev-runner.sh:1758-1772, tools/dev-runner.sh:1852]`<br>Liveness is judged on FILE BYTE GROWTH of the primary log (plus a secondary log for the lens), polled every 0.05s via an absolute-path `sleep` that a PATH override cannot redirect. `[code: tools/dev-runner.sh:1774-1803]`<br>`_GM_EXPIRED` is set ONLY when this loop itself decides to kill — a child that independently exits 124 or 137 never sets it. `[code+canon: tools/dev-runner.sh:1783-1789, skills/factory/references/gates.md > Judgment points]`
- **Postconditions:** TERM to the process group, a fixed 10s grace (CHECK_TIMEOUT_KILL_AFTER, not manifest-configurable), then KILL to the group. `[code: tools/dev-runner.sh:1772, tools/dev-runner.sh:1804-1812]`<br>A tail is appended to that gate's own log naming the idle duration, total elapsed, and BOTH windows; the gate-durations disposition is `timeout`, which outranks the exit code. `[code+canon: tools/dev-runner.sh:1854-1859, tools/dev-runner.sh:1842-1848]`<br>The expiry then disposes through that site's EXISTING path: check → one repair then Blocked; lint → the lint repair path; lens → folded into its advisory note, run continues. `[code+canon: tools/dev-runner.sh:1950, tools/dev-runner.sh:1982, tools/dev-runner.sh:2050-2054]`<br>A `setsid`-escaping grandchild survives even the group KILL — accepted residue, stated in the code comment. `[code: tools/dev-runner.sh:1769-1771]`

#### 10. `check-green` → `live-gate-advised`

`G10`

- **Actor:** dev-runner (`_gate_monitor`)
- **Trigger:** Total elapsed reaches `check_timeout` while the log IS still growing.
- **Enforcement:** detected · **Guard site:** tools/dev-runner.sh:1814-1818. Reachable; but it only informs — by construction it gates nothing.
- **Records:** `issue-trail comment `dev-runner: **live-gate advisory** — …` (NO registered `YR-` grammar; no row in records.toml)`
- **Preconditions:** The advisory fires at most once per invocation (an `advised` flag), and only while the child is alive. `[code+canon: tools/dev-runner.sh:1814-1818]`
- **Postconditions:** One run-log line and one ISSUE-trail comment naming the pgid, elapsed time, both windows, and that output is flowing. Nothing is killed; the wait continues; the run's terminal state is unchanged. `[code+canon: tools/dev-runner.sh:1814-1818, tools/dev-runner.sh:969]`

#### 11. `check-green` → `lint-green`

`G11`

- **Actor:** dev-runner (`run_lint`)
- **Trigger:** `check_cmd` passed AND LINT_CMD is non-empty; `run_lint "$LINT_CMD" lint` at tools/dev-runner.sh:1982.
- **Enforcement:** *partial* · **Guard site:** tools/dev-runner.sh:1978-1982. Reachable when the manifest declares lint_cmd; entirely absent otherwise.
- **Records:** ``$RUN_DIR/lint.log``, `gate-durations entry`
- **Preconditions:** The lint tier runs ONLY after check_cmd passes. An absent `lint_cmd` makes the tier a complete no-op — no probe, no output. `[code+canon: tools/dev-runner.sh:1970-1978, skills/factory/references/gates.md > Gate table]`<br>$1 is an OPAQUE command run verbatim under the same confinement as run_checks — no lint-output parsing, no language assumption. `[code+canon: tools/dev-runner.sh:1863-1868, tools/dev-runner.sh:1890]`
- **Postconditions:** `$RUN_DIR/lint.log` written; a gate-durations entry recorded. `[code: tools/dev-runner.sh:1889-1902]`

#### 12. `lint-green` → `lint-green`

`G12`

- **Actor:** dev-runner (the ruled lint-repair scope)
- **Trigger:** `lint_cmd` exited non-zero (not 126/127).
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1983-2039. Reachable.
- **Records:** ``$RUN_DIR/lint.log`, `$RUN_DIR/lint-repair.log``, `gate-durations entries for sites `lint`, `lint-fix`, `lint-autofix-recheck`, `lint-repair-recheck``
- **Preconditions:** Step 1 is a DETERMINISTIC autofix (`lint_fix_cmd`), no LLM, itself bounded by the same liveness windows. `[code+canon: tools/dev-runner.sh:1986-1996, skills/factory/references/gates.md > Judgment points]`<br>Step 2, only if lint still fails, is at most ONE LLM repair confined to exactly the lint-flagged files, forbidden from changing test assertions. `[code+canon: tools/dev-runner.sh:1998-2010]`<br>Mutation is judged by a before/after `tree_hash` comparison (git add -A + write-tree), applied at BOTH the autofix site and the LLM-repair site; an `add` failure emits a unique sentinel so the comparison differs and the conservative full re-run is bought. `[code: tools/dev-runner.sh:1869-1887, tools/dev-runner.sh:1993, tools/dev-runner.sh:2009]`
- **Postconditions:** If and only if the tree actually changed, BOTH `check_cmd` and `lint_cmd` are re-run against the shipped tree (`lint-repair-recheck`); a check failure there ends the run Blocked. `[code+canon: tools/dev-runner.sh:2012-2030]`<br>The lint verdict and the bg_scan verdict are enforced UNCONDITIONALLY, below the mutation branch — a reasoned no-fix cannot carry a red lint to the commit. `[code: tools/dev-runner.sh:2016-2039]`

#### 13. `lint-green` → `gate-blocked-terminal`

`G13`

- **Actor:** dev-runner
- **Trigger:** LINT_RC still non-zero after the ruled repair scope, or an unresolved background task at the lint-repair's stage end.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2032-2039. Reachable.
- **Records:** `issue-trail comment `dev-runner: **Blocked** — lint still failing after one repair (log: …)``
- **Preconditions:** The repair scope has been exhausted (autofix + at most one LLM repair). `[code+canon: tools/dev-runner.sh:1983-2011]`
- **Postconditions:** Reason=Blocked with a message naming lint.log; salvage patch; ledger row `blocked`; teardown. `[code: tools/dev-runner.sh:2032-2039]`

#### 14. `lint-green` → `gate-env-hold`

`G14`

- **Actor:** dev-runner (`lint_env_hold`)
- **Trigger:** `lint_cmd` OR `lint_fix_cmd` exited 126/127 at any of its five sites.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1940-1944, called at 1983/1991/1996/2029/2171. Reachable.
- **Records:** `issue-trail comment `dev-runner: **Environmental hold** — lint command could not execute (exit N) … command: <cmd> …``, ``$STATE_DIR/env-hold`, `$STATE_DIR/run.json``, `ledger row `env-hold``
- **Preconditions:** Exit 126/127 on the lint or autofix command. `[code+canon: tools/dev-runner.sh:1926, tools/dev-runner.sh:1983, tools/dev-runner.sh:1991, tools/dev-runner.sh:1996, tools/dev-runner.sh:2029, tools/dev-runner.sh:2171]`
- **Postconditions:** Same preserve+resume machinery as env_hold, but the record NAMES the lint command that failed and lint.log — never the check command's text or checks.log. No LLM repair. `[code+canon: tools/dev-runner.sh:1940-1944]`

#### 15. `lint-green` → `lint-green`

`G15`

- **Actor:** dev-runner (`run_lint` invoking this repo's declared `lint_cmd`, whose SECOND arm is the cardinality guard)
- **Trigger:** This repo declares `lint_cmd = "ruff check tools/ tests/ && python3 qa/cardinality.py"`; the cardinality arm runs only if ruff exits 0.
- **Enforcement:** **prevented** · **Guard site:** qa/cardinality.py:184-227 `main`, reached through `.yr/factory.toml:36 lint_cmd` → tools/dev-runner.sh:1982. Also reached by server CI at .github/workflows/ci.yml:43-51.
- **Records:** `cardinality failure block on stderr, folded into `$RUN_DIR/lint.log` by run_lint's `2>&1``
- **Preconditions:** `qa/cardinality.toml` parses and every rule carries all six required fields (id, pattern, paths, max, reason, birth), a unique non-empty id, a non-empty repo-relative `paths` list with no absolute path and no `..`, a non-negative-integer `max`, and a compilable regex — otherwise ConfigError, exit 2, the whole run refused rather than the parsable subset enforced. `[code: qa/cardinality.py:58-107]`<br>Every rule's `paths` globs must resolve to at least one file; an empty surface is FATAL (exit 2), never a silent green. `[code: qa/cardinality.py:157-167, qa/cardinality.py:191-199]`<br>The surface is enumerated by `git ls-files -z --cached --others --exclude-standard` — tracked PLUS untracked-but-not-ignored, because the tier runs before the commit; a filtered filesystem walk (excluding .git/.venv/node_modules/.claude/__pycache__) is the non-git fallback. `[code: qa/cardinality.py:110-136]`
- **Postconditions:** count > max → exit 1 naming pattern, count, maximum, reason, birth, surface, and every matching file:line. count == max → silent pass. count < max → ONE advisory line on stdout, exit 0. `[code: qa/cardinality.py:170-181, qa/cardinality.py:201-224]`<br>Three rules ship today: `verdict-extraction-pipeline` (max 1 on tools/dev-runner.sh), `ci-checkout-step` (max 1 on .github/workflows/*.yml), `workflow-manifest-read` (max 1 on .github/workflows/*.yml). Observed green (exit 0, no advisory) at this HEAD. `[code: qa/cardinality.toml:25-45]`

#### 16. `lint-green` → `lens-artifact-present`

`G16`

- **Actor:** dev-runner (`run_lens`)
- **Trigger:** check_cmd and (when declared) lint_cmd both passed AND LENS_CMD is non-empty.
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tools/dev-runner.sh:2048-2059. Reachable when lens_cmd is declared; nothing enforces its findings anywhere.
- **Records:** ``$RUN_DIR/lens.md`, `$RUN_DIR/lens.log``, `gate-durations entry for site `lens``
- **Preconditions:** The lens runs LAST in the tier, only after both blocking gates pass. Absent `lens_cmd` = off, byte-identical to no feature. `[code+canon: tools/dev-runner.sh:2041-2048, skills/factory/references/gates.md > Advisory vs. blocking]`<br>Two deliberate deviations from the run_checks shape: stdout→lens.md and stderr→lens.log are SEPARATE (a traceback must never reach the PR comment), and `YR_BASE_REF` is exported so a lens can be diff-aware. `[code: tools/dev-runner.sh:1903-1920]`
- **Postconditions:** The exit code is READ but NEVER gates. A non-zero exit (126/127 included, an observed idle expiry included) appends a one-line note to lens.md; the run's terminal state is identical to the same run with a passing lens — no fail_blocked, no env hold, no repair. `[code+canon: tools/dev-runner.sh:2048-2059, skills/factory/references/gates.md > Advisory vs. blocking]`<br>This repo's own lens (`qa/lens.py`) diffs the working tree against YR_BASE_REF, scans only CHANGED `tests/*.py` files for four closed species, and its `main` returns 0 unconditionally. Observed exit 0 at this HEAD. `[code: qa/lens.py:283-296, qa/lens.py:339-346]`

#### 17. `lens-artifact-present` → `lens-artifact-present`

`G17`

- **Actor:** dev-runner (post-PR trail posting)
- **Trigger:** The PR exists and `$RUN_DIR/lens.md` is non-empty.
- **Enforcement:** detected · **Guard site:** tools/dev-runner.sh:2356-2361. Reachable only after a successful PR open.
- **Records:** ``YR-LENS (advisory)` PR-trail comment (registered: records.toml:219-226, readers = humans, no machine reader at tip)`
- **Preconditions:** Posted exactly ONCE; an empty or absent artifact posts nothing; a Blocked run (no PR) leaves lens.md unposted in the run dir. `[code+canon: tools/dev-runner.sh:2352-2361]`
- **Postconditions:** One PR-trail comment whose first line is `YR-LENS (advisory)`. Best-effort: a post failure logs and never blocks. It carries no `YR-MERGE`/`VERDICT:` grammar so it can never be mistaken for a gating record. `[code+canon: tools/dev-runner.sh:2355-2361, records.toml:219-226]`

#### 18. `lens-artifact-present` → `gates-complete-for-branch`

`G18`

- **Actor:** dev-runner
- **Trigger:** The whole tier (check → lint → lens) completed without a block or hold.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2060. Reachable.
- **Records:** ``$DEV_RUNNER_HOME/state/<owner>--<name>--<branch-slug>/03-check.done``
- **Preconditions:** Every blocking arm of the tier passed for this branch. `[code: tools/dev-runner.sh:1945-2060]`
- **Postconditions:** The durable marker `$STATE_DIR/03-check.done` is written; a later relaunch on the same repo+branch will skip the ENTIRE tier. `[code: tools/dev-runner.sh:2060, tools/dev-runner.sh:1218-1219]`

#### 19. `gates-complete-for-branch` → `gates-skipped-on-resume`

`G19`

- **Actor:** dev-runner (resume path)
- **Trigger:** A relaunch finds `$HOLD_MARKER` + the worktree + the branch intact, and `03-check.done` present.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1945-1948. Reachable on every env-hold resume.
- **Records:** `run-log line `resume: skipping check (03-check.done present)``, ``review-bundle.json` `check.exit_code: 0``
- **Preconditions:** The hold marker, the worktree and the branch all exist. `[code: tools/dev-runner.sh:1244-1247]`
- **Postconditions:** check_cmd, lint_cmd AND lens_cmd are all skipped for this invocation (all three sit inside the same `else` arm), and CHECK_RC is set to 0 by assertion. `[code: tools/dev-runner.sh:1945-1948, tools/dev-runner.sh:1978, tools/dev-runner.sh:2048, tools/dev-runner.sh:2060]`<br>`checks.log` and `review.md` are copied forward from the prior run dir named in run.json; that asserted CHECK_RC=0 is then written into review-bundle.json as `check.exit_code`. `[code: tools/dev-runner.sh:1253-1262, tools/dev-runner.sh:2080-2086]`

#### 20. `gates-complete-for-branch` → `check-green`

`G20`

- **Actor:** dev-runner (the review-repair mutation path)
- **Trigger:** The reviewer requested changes; the review-repair stage ran with `Read Edit Write Bash` and may have rewritten any file.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2164-2174. Reachable on any build whose first review round was not a clean APPROVE.
- **Records:** ``$RUN_DIR/final.patch``, `gate-durations entries for sites `review-repair-recheck` and `review-repair-lint``
- **Preconditions:** The post-repair diff is pinned to `$RUN_DIR/final.patch` BEFORE the re-check, regardless of the repair's own exit status. `[code: tools/dev-runner.sh:2153-2159]`
- **Postconditions:** `run_checks review-repair-recheck` runs; failure → Blocked naming checks.log. `[code: tools/dev-runner.sh:2164]`<br>When LINT_CMD is declared, `run_lint … review-repair-lint` ALSO runs; a 126/127 → lint_env_hold, a non-zero → Blocked naming lint.log. Before issue #364 only run_checks re-ran here, so an LLM edit landing after the lint tier had passed shipped unlinted. `[code+canon: tools/dev-runner.sh:2165-2174, skills/factory/references/gates.md > Gate table]`<br>The LENS is NOT re-run on this path — the artifact already posted describes the pre-review-repair tree. `[code: tools/dev-runner.sh:2048 (the only run_lens call site, inside the 03-check block)]`

#### 21. `gates-complete-for-branch` → `check-green`

`G21`

- **Actor:** dev-runner (`rebase_onto_tip`, the armed-merge freshness remediation)
- **Trigger:** The merge evaluator found the reviewed base != main's tip on an armed repo; the branch is rebased and force-pushed, producing a tree no gate has seen.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2407-2418. Reachable only on the armed-merge path when main moved.
- **Records:** `gate-durations entries for sites `rebase-recheck` and `rebase-lint``, `on failure, a `YR-MERGE: BLOCKED` record via armed_block (merge lane)`
- **Preconditions:** The rebase succeeded (a conflict returns 1 → block) and the force-with-lease push landed (a failure returns 2 → environmental). `[code: tools/dev-runner.sh:2396-2404]`<br>The re-green reuses the START-OF-RUN check_timeout / check_idle_timeout values, never re-resolved at decision time. `[code+canon: tools/dev-runner.sh:805-808, AGENTS.md > Conventions]`
- **Postconditions:** `run_checks rebase-recheck` runs: 126/127 → return 2 (environmental), non-zero → return 1 (block; never merge a stale/red PR). `[code: tools/dev-runner.sh:2407-2409]`<br>When LINT_CMD is declared, `run_lint … rebase-lint` runs with the identical contract — a lint failure blocks exactly like a red check. `[code+canon: tools/dev-runner.sh:2410-2418, skills/factory/references/gates.md > Gate table]`<br>The lens is NOT re-run here either. `[code: tools/dev-runner.sh:2048]`

#### 22. `gates-complete-for-branch` → `server-ci-verdict`

`G22`

- **Actor:** GitHub Actions (the `ci` workflow), triggered by native GitHub automation on `pull_request`
- **Trigger:** The PR opens or its head is pushed.
- **Enforcement:** **prevented** · **Guard site:** .github/workflows/ci.yml:29-51 (server-side, outside the runner's process). Reachable for every PR.
- **Records:** `GitHub check runs on the PR head, read back by the merge evaluator into `$RUN_DIR/check-rollup.json``
- **Preconditions:** Only `on: pull_request` — there is no push/main trigger, so a merged tree is never certified post-merge. `[code: .github/workflows/ci.yml:2-3]`<br>`concurrency: cancel-in-progress: true`, keyed by workflow+ref, so a superseded head's in-flight run is cancelled. `[code: .github/workflows/ci.yml:9-11]`
- **Postconditions:** One `test` job: full-history checkout (fetch-depth 0), Python 3.11, `pip install -r requirements-dev.txt`, `pytest tests/ -n auto -q`, then the Lint backstop. `[code: .github/workflows/ci.yml:14-30]`<br>The Lint step READS `lint_cmd` from the checked-out `.yr/factory.toml` with tomllib and runs it verbatim under `bash -c`; an absent key makes the step a logged no-op with exit 0. This is the workflow's ONE manifest read, capped at one by the `workflow-manifest-read` cardinality rule. `[code+canon: .github/workflows/ci.yml:31-51, qa/cardinality.toml:39-45]`

#### 23. `check-green` → `check-green`

`G23`

- **Actor:** dev-runner (indirectly: `check_model_refs` runs INSIDE the pytest suite that is `check_cmd`)
- **Trigger:** Every `pytest tests/ -q` run — the check gate, the CI test step, and any attended run.
- **Enforcement:** **prevented** · **Guard site:** tests/test_check_model_refs.py:200-212 riding `check_cmd` at tools/dev-runner.sh:1949 and `.github/workflows/ci.yml:30`. Reachable on both hosts.
- **Records:** ``$RUN_DIR/checks.log` (as an ordinary pytest failure)`
- **Preconditions:** `tools/check_model_refs.py` scans the whole repo tree for un-allowlisted `01-conventions` occurrences, skipping .git/.venv/node_modules, binary suffixes, three named self-referential files, one allowlisted line substring, and frozen bench evidence. `[code: tools/check_model_refs.py:20-72]`<br>Three separate tests run it against the LIVE repo root (not a fixture tree). `[code: tests/test_check_model_refs.py:200-212, tests/test_backlog_canon_docs.py:809, tests/test_contract_surface_docs.py:381]`
- **Postconditions:** A stale reference fails the pytest suite, which is `check_cmd`, which blocks the build and fails server CI. Observed exit 0 at this HEAD. `[code: tools/check_model_refs.py:74-92, .yr/factory.toml:3]`

#### 24. `artifact-advisory-unrecorded` → `artifact-advisory-unrecorded`

`G24`

- **Actor:** an attended agent or human operator, by hand
- **Trigger:** A prose checklist item read before promoting a task, filing an RFC, or accepting a superseding doc.
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** No guard. Verified by grep: no `.sh`, `.py`, `.json`, `.yml` or `.toml` file in the tree outside the tools themselves and `tests/` invokes check_links, check_task or check_supersession. `tools/promote.sh` — the operator promote command — does not call any of them.
- **Records:** `none`
- **Preconditions:** The canon asks that `check_links` be green on the technical-rfc and `check_task` green on the task before promoting. `[canon-only: skills/factory/references/closing.md > Promote to Ready (checklist)]`<br>The canon states plainly that these are advisory and inform the human gate: 'Run them yourself before promoting; don't claim CI enforcement that isn't wired.' `[canon-only: skills/factory/references/gates.md > Advisory vs. blocking]`<br>check_supersession's own module docstring states it is 'an attended-session check like its siblings: advisory-first, wired into nothing.' `[code: tools/check_supersession.py:88]`
- **Postconditions:** Exit 0 or 1 and some lines on the operator's terminal. NOTHING is written: no board field, no trail comment, no run-dir artifact, no ledger row. A later actor cannot tell whether the check ran. `[code: tools/check_links.py:129-140, tools/check_task.py:296-312, tools/check_supersession.py:914-921]`<br>check_task's fourth pass (pin-collision) is advisory even within the tool: warnings never move the exit code unless `--strict` is passed, and no caller passes it. `[code: tools/check_task.py:200-228, tools/check_task.py:305-312]`

#### 25. `gate-params-unresolved` → `needs-info-bounced`

`G25`

- **Actor:** epic-gate (tools/epic_gate.py, the org-wide `/sweep` pass)
- **Trigger:** The sweep visits an OPEN Ready standalone item, or is about to promote an epic's next child, into a repo whose default branch carries no `.yr/factory.toml`.
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py:1050-1067 (epic child) and tools/epic_gate.py:1151-1167 (standalone). Reachable on every sweep tick.
- **Records:** ``YR-EPIC-GATE: not-onboarded` issue-trail comment (registered: records.toml:132-139)`
- **Preconditions:** The probe is a `gh api repos/<owner>/<name>/contents/.yr/factory.toml` read; a confirmed HTTP 404 is a real absence, and any other failure is retried once with a bounded backoff then raises ManifestProbeError. `[code: tools/epic_gate.py:756-781]`<br>A ManifestProbeError never guesses either way — the item is skipped for this tick, uncached, so the next sweep re-probes. `[code+canon: tools/epic_gate.py:749-754, tools/epic_gate.py:784-792, tools/epic_gate.py:1159-1163]`
- **Postconditions:** Standalone item: Status=Backlog + Reason=Needs-info on the item itself + a `YR-EPIC-GATE: not-onboarded` comment on its trail. Epic child: the EPIC is bounced (Reason=Needs-info + comment), never the child. `[code: tools/epic_gate.py:1151-1167, tools/epic_gate.py:1050-1093]`<br>The runner's own manifest-absent bounce (MF_ONBOARD_MSG) is the backstop for an item already Ready. `[code+canon: tools/dev-runner.sh:713-718, skills/factory/references/pipeline.md > How the lower pipeline runs]`

#### 26. `gate-params-unresolved` → `dor-refused-nowrite`

`G26`

- **Actor:** epic-gate (the gate-touching wall — gate EVOLUTION is attended, the pipeline builds under fixed gates)
- **Trigger:** The sweep is about to promote an epic's next open child whose own body carries a `YR-GATE-TOUCHING:` line at column 0 with a non-empty reason.
- **Enforcement:** *partial* · **Guard site:** tools/epic_gate.py:1026-1042, placed deliberately before the `_pi_node` board lookup so a child not yet on the board still refuses. Reachable only on the epic-child promotion path.
- **Records:** ``YR-EPIC-GATE: gate-touching` issue-trail comment (registered: records.toml:150-157)`, ``YR-GATE-TOUCHING:` in the child's issue body (registered: records.toml:96-103)`
- **Preconditions:** The declaration is read from the CHILD's own body only, never the epic's (an epic legitimately carries such lines inside its per-task context slices). `[code: tools/epic_gate.py:460-472, tools/epic_gate.py:1026-1033]`<br>The marker must begin at column 0 (`line.startswith`, never `.strip()`), and the text after the prefix must be non-empty — this keeps the technical-rfc template's shipped marker-only slot inert. `[code+canon: tools/epic_gate.py:460-472, skills/factory/templates/technical-rfc.md:102]`
- **Postconditions:** Nothing is promoted; the EPIC gets Reason=Blocked and a `YR-EPIC-GATE: gate-touching` comment quoting the reason back (backticked, never at column 0, so the record cannot satisfy its own detector next sweep). `[code: tools/epic_gate.py:1034-1042, tools/epic_gate.py:522-532]`<br>A STANDALONE Ready task declaring the same line is NOT checked — the standalone arm of the sweep applies only the admission wall, and neither `tools/promote.sh` nor the runner's DoR gate reads the marker. `[code: tools/epic_gate.py:1151-1167, tools/promote.sh:56-63, tools/dev-runner.sh:970-1010]`

#### 27. `check-green` → `check-green`

`G27`

- **Actor:** dev-runner (the review bundle assembly)
- **Trigger:** The tier completed; the bundle is built before the review stage.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:2080-2086. Reachable on every build that reaches review.
- **Records:** ``$RUN_DIR/review-bundle.json` (a run-internal artifact, excluded from records.toml by its own exclusion rule)`
- **Preconditions:** `$RUN_DIR/checks.log` exists (written by the last run_checks invocation, or copied forward from the prior run dir on a resume). `[code: tools/dev-runner.sh:1257-1262, tools/dev-runner.sh:2082]`
- **Postconditions:** The check command text, its exit code and a tail of its log are frozen into `review-bundle.json`, which the reviewer reads as input. The LINT and LENS results are NOT in the bundle. `[code: tools/dev-runner.sh:2080-2086, tools/review_bundle.py:38-44]`<br>A bundle assembly failure ends the run Blocked. `[code: tools/dev-runner.sh:2086]`

#### 28. `gate-params-bound` → `gate-params-bound`

`G28`

- **Actor:** dev-runner (`--dry-run`)
- **Trigger:** `dev-runner.sh <issue> --repo <r> --dry-run`.
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh:1137-1150. Reachable only on the explicit attended flag.
- **Records:** `stdout JSON only`
- **Preconditions:** No NEEDS_INFO reason accumulated (otherwise the dry run exits 3 with the reason, still writing nothing). `[code: tools/dev-runner.sh:1130]`
- **Postconditions:** The resolved plan is printed as JSON including `check_cmd`, `lint_cmd`, `lint_fix_cmd`, `lens_cmd`, `base_ref` and `auto_merge`, then exit 0. No board write, no worktree, no gate execution. `check_timeout` / `check_idle_timeout` / `test_paths` / `artifact_globs` / `stage_conduct` are NOT in the emitted plan. `[code: tools/dev-runner.sh:1137-1150]`

## Where the code and the canon disagree

### [material] pipeline.md attributes the gate KILL to `check_timeout` and never names `check_idle_timeout` at all.

- **code:** `check_timeout` elapsing kills nothing — it fires one advisory (a run-log line plus one issue-trail comment) and the wait continues. The ONLY thing that kills a gate's process group is `check_idle_timeout`: zero byte growth in the invocation's log for that many seconds.
- **canon:** 'Runner (not LLM) runs `check_cmd` from `.yr/factory.toml`, bounded by `check_timeout` (issue #308; env > manifest > 1200s default…). An OBSERVED expiry (the wrapper itself firing…) disposes as a code failure through this same path — a wedged process tree is killed with no survivor.' The word `check_idle_timeout` appears nowhere in pipeline.md.
- `tools/dev-runner.sh:1804-1818`, `skills/factory/references/pipeline.md > How the lower pipeline runs (Check gate row)`, `skills/factory/references/gates.md > Judgment points`, `AGENTS.md > Conventions`

### [material] pipeline.md's canonical stage table omits the lint tier and the lens tier entirely — two live gates, one of them BLOCKING — jumping straight from the Check gate row to the Review row.

- **code:** Between `run_checks` and the review stage the runner runs a blocking `lint_cmd` tier with a ruled repair scope (tools/dev-runner.sh:1978-2039) and an advisory `lens_cmd` tier (tools/dev-runner.sh:2048-2059). `lint_cmd` also runs at two further sites the stage table's Review and Merge rows describe (review-repair, rebase re-green).
- **canon:** pipeline.md's stage table lists Config read · DoR gate · Claim · Worktree · Implement · Test · Check gate · Review · PR · Merge evaluator. `lint` appears only in the `stage_conduct` prose (:95) and the gate-durations paragraph (:375-378); `lens` only in that same paragraph. gates.md carries both tiers correctly.
- `skills/factory/references/pipeline.md > How the lower pipeline runs`, `skills/factory/references/pipeline.md > The ledger (Gate durations)`, `tools/dev-runner.sh:1978-2039`, `tools/dev-runner.sh:2048-2059`, `skills/factory/references/gates.md > Gate table`

### [minor] The it-17 product spec's lens EARS criterion describes a delivery shape the code does not implement.

- **code:** The lens artifact is posted as its OWN PR-trail comment (`YR-LENS (advisory)` first line), deliberately kept clear of PR_BODY and the review bundle; the check gate's own output artifact (`review-bundle.json` / `checks.log`) never contains it.
- **canon:** 'WHEN a repo's manifest declares a lens command and it runs over a build's test changes, THE SYSTEM SHALL land each flagged assertion — location plus behavioral-alternative class — as a named section of the check gate's output artifact, visible on the PR trail…'. The doc is `status: active` and the criterion was never amended; the it-17 ship-walk records the shipped form instead ('lens_cmd (advisory, `YR-LENS (advisory)` PR comment, exit never gates)').
- `04 projects/factory/iterations/17-lint-tier/01-lint-tier.md > Acceptance criteria (EARS)`, `04 projects/factory/iterations/17-lint-tier/02-ship-walk.md`, `tools/dev-runner.sh:2352-2361`, `records.toml:219-226`

### [minor] gates.md's gate table lists `check_supersession` alongside `check_links` / `check_task` as 'advisory → blocking today', but omits `check_model_refs` — the ONE member of the check_* family that actually blocks.

- **code:** `tools/check_model_refs.py` is executed against the LIVE repo tree by three tests inside the pytest suite that IS this repo's `check_cmd`, so a stale reference blocks the build and fails server CI. `check_links` / `check_task` / `check_supersession` are invoked by no caller anywhere.
- **canon:** gates.md's gate table has no row for `check_model_refs`; it is named only in closing.md's skill-release scan as '(`tools/check_model_refs.py`, fail-closed)'. The reader of gates.md — the stated 'load this reference for any gate' surface — never learns the one check_* tool that is wired.
- `skills/factory/references/gates.md > Gate table`, `skills/factory/references/closing.md > Skill release`, `tests/test_check_model_refs.py:200-212`, `tests/test_backlog_canon_docs.py:809`, `.yr/factory.toml:3`

### [minor] gates.md claims the post-repair re-run makes the bundle's `--check-exit` describe the tree AS SHIPPED; on an env-hold resume past the tier it does not.

- **code:** When `03-check.done` is present the runner sets `CHECK_RC=0` without running anything and skips check, lint and lens for that invocation; that asserted 0 is then passed to `review_bundle.py init --check-exit`.
- **canon:** '(3) unconditionally after ANY repair-path mutation (the autofix alone included) re-run BOTH check_cmd and lint_cmd, so checks.log/lint.log and the bundle's --check-exit describe the tree AS SHIPPED'. The resume-skip case is not carved out anywhere.
- `skills/factory/references/gates.md > Judgment points (Ruled lint-repair scope)`, `tools/dev-runner.sh:1945-1948`, `tools/dev-runner.sh:2080-2086`

## Gaps

- **`check_links`, `check_task` and `check_supersession` have no caller anywhere in the tree and write nothing durable. Their result has no storage — a later actor cannot tell whether they ever ran, let alone what they said. `tools/promote.sh`, the operator command that performs the promote act, does not invoke check_task.** **← needs an owner ruling**<br>The DoR/self-containedness gate is named in the lane's own title and in closing.md's promote checklist, but the only thing stopping a non-self-contained task from reaching Ready is a document asking nicely. The runner's DoR gate re-checks structure (open/Ready/Type/AC-non-empty/models/YR-TASK-GATES) but never self-containedness: it does not read the task body for wikilinks, obsidian:// links, cited-path existence, or an empty Context & links section. closing.md's 'Gate disposes: the DoR gate in the runner re-checks these structurally on claim' overstates what the runner re-checks.
- **The env-override branch of `check_timeout` and `check_idle_timeout` performs NO validation, unlike the manifest branch which bounces a non-positive-integer to Needs-info. The unvalidated value flows straight into the monitor's integer comparisons.**<br>The two windows are the only thing bounding a wedged gate. A malformed operator env value bypasses the fail-closed discipline the manifest path enforces, with no bounce and no log line naming a rejection. The canon scopes the bounce to the manifest value, so this is a hole rather than a contradiction — but it is the hole in the liveness rule's own guard.
- **Three manifest keys that can bounce a task to Needs-info — `check_timeout`, `check_idle_timeout`, `stage_conduct` — appear nowhere in onboarding.md's manifest template or key list.**<br>onboarding.md is the surface a joining repo reads. A repo can be onboarded exactly as documented and still hit a fail-closed bounce on a key the onboarding surface never named. The seam contract ('every repo-shape assumption is a declared key with a fail-closed default') is met in code but not on the onboarding surface.
- **The two files that CONSTITUTE the lens tier and the cardinality tier — `qa/lens.py` and `qa/cardinality.py`, the only Python in the repo outside tools/ and tests/ — are outside this repo's own `lint_cmd` scope (`ruff check tools/ tests/`).**<br>The blocking lint tier does not lint the code that implements the blocking cardinality guard. The instrument is exempt from itself, in the repo that ships the exemplar other repos copy.
- **`qa/cardinality.py` returns exit 2 for a config error or a blind (empty-surface) rule, but the runner's `is_env_failure` recognises only 126/127, so exit 2 is indistinguishable from exit 1 (a rule exceeded) at the gate.** **← needs an owner ruling**<br>A malformed `qa/cardinality.toml` or a rule whose globs stopped resolving is handed to the deterministic autofix and then to an LLM lint repair, whose prompt is 'fix ONLY what the lint output flags, in exactly the files it names' — a prompt that does not fit a rule-set config error. The failure surface names the right fact; the disposal path does not match its class.
- **The lens does not re-run after the two later code-mutating paths (review-repair and the armed rebase re-green), both of which the lint tier WAS extended to cover in #364.**<br>The `YR-LENS (advisory)` comment posted on the PR describes the pre-review-repair tree. The asymmetry is a rule that exists for one tier and not its sibling on the same mutation paths — and nothing in gates.md, pipeline.md or AGENTS.md states which tree the posted lens artifact describes.
- **The gate lane's own failure surfaces carry no registered record grammar. `dev-runner: bounced to **Needs-info**`, `dev-runner: **Blocked**`, `dev-runner: **Environmental hold**` and `dev-runner: **live-gate advisory**` are plain issue-trail comments with no `YR-` marker and no row in records.toml.** **← needs an owner ruling**<br>Every OTHER refusal on the board — the epic gate's five, the merge evaluator's two, the promotion records — carries a registered, machine-parseable marker. The runner's four gate dispositions, which are the most frequent refusals the system produces, are unparseable by `tools/check_trail.py` or any census. records.toml's exclusion rule covers run-internal artifacts, not trail comments, so this is an omission rather than a ruled exclusion.
- **The gate-touching wall exists only on the epic-child promotion path. A STANDALONE task declaring `YR-GATE-TOUCHING:` is refused by nothing: the epic-gate's standalone arm applies only the admission wall, `tools/promote.sh` does not read the marker, and the runner's DoR gate does not either.** **← needs an owner ruling**<br>'The pipeline builds under fixed gates' is stated as an invariant in AGENTS.md and enforced only for governed epic children. The standalone lane — the one with no governing design above it — is the lane where an unreviewed gate change is most likely, and it is the unenforced one.
- **Server CI reads `lint_cmd` from the CHECKED-OUT tree's `.yr/factory.toml`, whereas the runner reads the manifest from a sha pinned off `MANIFEST_REF` (default `origin/main`).** **← needs an owner ruling**<br>The two hosts the canon calls 'one contract on two hosts' resolve that contract from different refs. A PR that edits `lint_cmd` changes the CI backstop's own command for its own certification run, while the same PR's runner-side lint tier still uses main's declared command.
- **There is no post-merge certification: `.github/workflows/ci.yml` is `on: pull_request` only, so the tree that actually lands on main is never itself run through check or lint.**<br>Every gate in this lane certifies a PR head, never the merge result. The it-27 ship-walk already recorded one live instance ('the tree verified green here, because CI never certified it' — acd8cfd had no CI run at all, and two heads were certified before the Lint step existed). Recorded in the vault log; not stated on any repo-side gate surface.
- **`gate-durations.json`, the check/lint/lens invocation record, is explicitly excluded from records.toml as a run-internal artifact, and `check.exit_code` inside `review-bundle.json` likewise — so the gate lane's own per-invocation evidence has no registered schema.**<br>The ledger folds gate durations into the row as a top-level `gates` list, which IS a registered surface (`yr-ledger-row/1`), but the shape of that list is defined only by a printf in the runner. A reader of the ledger has no registry row telling it what `site` or `disposition` may contain.
- **On an env-hold resume past `03-check.done`, all three tiers are skipped for that invocation and `CHECK_RC` is asserted 0; `checks.log` is copied forward from the prior run dir, but `lint.log` and `lens.md` are NOT in the copy-forward list.**<br>The resumed run's run dir carries no lint or lens artifact at all, so the `YR-LENS (advisory)` PR comment is never posted for a build that held and resumed past the tier — silently, with no log line saying so.
- **`checks.log` and `lint.log` are overwritten by every invocation of their gate (five and five sites respectively), so only the LAST run's output survives in the run dir.**<br>A run that failed check, repaired, and passed leaves only the passing output; the Blocked comment and the review bundle both point at a file that no longer holds the failure they describe. Legible failure depends on the log the message names.
- **`tools/check_trail.py` declares in its own module docstring that it is 'advisory-tier: never wired into check_cmd, CI, or the manifest' — and grep confirms it has no caller. It is merged to main but, like the rest of iteration 30, reaches no session (the plugin version was never bumped past 0.10.0).**<br>The detector named as the enforcement arm of the attended lane's record vocabulary is, for the gates lane, a fifth unwired check_* tool — the same shape as check_links/check_task/check_supersession, declared honestly this time.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **State `gate-params-unresolved` — stored_where: "The runner's stderr, which dispatch redirects into a per-run log file under `$DEV_RUNNER_HOME/runs/<issue>-<pid>/`".**<br>dispatch does not write into the per-pid run DIRECTORY. `build_task` composes `log_path = RUNS_DIR / f"dispatch-{issue}-{int(time.time()*1000)}.log"` — a flat file directly under `$DEV_RUNNER_HOME/runs/`, named by epoch-milliseconds, not by pid, and created by dispatch before the runner exists. `$DEV_RUNNER_HOME/runs/<issue>-<pid>/` is RUN_DIR, which the runner itself mkdir's much later (dev-runner.sh:1184). The cited dev-runner.sh:115-120 shows RUN_DIR being computed and does not establish anything about where dispatch redirects; dispatch.py:230 contradicts the claim. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dispatch.py:230 (and :69 RUNS_DIR); contra the claim's /opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:115-120`
- **G9 guard_site: "`_gate_monitor`, shared by run_checks / run_lint / run_lens. Reachable at all eight gate invocation sites."**<br>There are twelve, not eight. run_checks is invoked at 5 sites (1949, 1957, 2025, 2164, 2407), run_lint at 6 (1982, 1989, 1995, 2028, 2170, 2415), run_lens at 1 (2049). The undercount is the same one that produces the excavation's "five" lint sites elsewhere: the deterministic autofix invocation `run_lint "$LINT_FIX_CMD" lint-fix` (1989) is a full monitored gate invocation — same setsid, same liveness windows, same gate-durations entry — and is missing from every list in the lane. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1949,1957,1982,1989,1995,2025,2028,2049,2164,2170,2407,2415`
- **Disagreement #5 attributes to gates.md the sentence: "(3) unconditionally after ANY repair-path mutation (the autofix alone included) re-run BOTH check_cmd and lint_cmd, so checks.log/lint.log and the bundle's --check-exit describe the tree AS SHIPPED", cited to `gates.md > Judgment points (Ruled lint-repair scope)`.**<br>That sentence is not in gates.md — it is verbatim the CODE COMMENT at dev-runner.sh:1973-1975. gates.md's actual Ruled lint-repair scope bullet reads "Any repair-path mutation (the autofix alone included) forces a re-run of both `check_cmd` and `lint_cmd` against the shipped tree; either failing ends the run `Blocked`" — it never mentions the bundle or `--check-exit`. `grep -rn "check-exit" skills/ docs/ AGENTS.md` returns nothing. So the doc-vs-code disagreement is built on a quote the doc does not contain; the underlying code fact (resume asserts CHECK_RC=0 into `--check-exit`) is real, but the canon says nothing to contradict. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/skills/factory/references/gates.md:62-67 vs /opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1973-1975`
- **G15 precondition: "Every rule's `paths` globs must resolve to at least one file; an empty surface is FATAL (exit 2), never a silent green" — cited to qa/cardinality.py:157-167, 191-199.**<br>The claim is true, but neither cited range shows it. 157-167 is `matches_for` (regex scan of a rule's surface); 191-199 is `main`'s opening plus the ConfigError branch (a different exit-2 cause). The empty-surface rule lives at `empty_surfaces` (170-178) and its disposal at main:204-211. A reader following the citation cannot verify the claim. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/qa/cardinality.py:170-178, 204-211`
- **State `gate-params-bound` (cited 803-866) and G1's postcondition (cited 799-866) list TEST_PATHS, ARTIFACT_GLOBS and STAGE_CONDUCT_BLOCK among the values bound in that range.**<br>Those three are resolved at 750-788 — before the cited window opens. The cited 799-866 covers only CHECK_CMD, CHECK_TIMEOUT, CHECK_IDLE_TIMEOUT, LINT_CMD, LINT_FIX_CMD, LENS_CMD. The substance (all bound once at start-of-run, never re-read at decision time) holds; the citation does not reach three of the named parameters. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:750-788 vs the cited 799-866`
- **State `gate-env-hold` stored_where and G8's postcondition ("run.json written, env-hold marker dropped, Reason=Blocked, comment, ledger row, then die; cleanup_wt deliberately NOT called") — cited to tools/dev-runner.sh:1194-1201.**<br>1194-1201 is MERGE_GIT_DIR/STATE_DIR/HOLD_MARKER assignment plus the prose comment above `cleanup_wt`. The preserve+record core the claim describes is `env_hold_record` at 1232-1239 (write_run_json; `: > "$HOLD_MARKER"`; set_reason Blocked; comment; ledger_append env-hold; die), with `write_run_json` at 1222-1226. Only the "not cleanup_wt" half is visible in the cited range. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1222-1239`
- **G8 guard_site: "`is_env_failure` called at 1950, 1958, 2026, 2410."**<br>2410 is a comment line; the rebase-site call is 2408 (`is_env_failure "$rc" && return 2`). The list also omits every lint-side call the same predicate serves — 1983, 1990, 1996, 2029, 2171, 2416 — which G14 depends on. Ten call sites exist in total. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1950,1958,1983,1990,1996,2026,2029,2171,2408,2416`
- **State `lint-green` enumerates the lint sites as (`lint`, `lint-autofix-recheck`, `lint-repair-recheck`, `review-repair-lint`, `rebase-lint`), and the gap says checks.log/lint.log are overwritten at "five and five sites respectively".**<br>lint.log is truncated and rewritten at SIX sites — the deterministic autofix (`run_lint "$LINT_FIX_CMD" lint-fix`, 1989) writes to the same `>"$RUN_DIR/lint.log"` as every lint probe. That matters exactly where the excavation's own legibility gap points: on a lint failure with an autofix declared, the lint output the run was blocked on is overwritten twice before anyone reads the file the Blocked comment names. The claim understates its own finding. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1889-1892, 1989`
- **G6, G8, G9 and G10 all declare `from: check-green`.**<br>None of these four departs from a green check. A 126/127 env hold, an idle-window kill, a live-gate advisory and a red first round all depart from the SAME act — an in-flight `run_checks` invocation whose result is not yet known (1949, 1852-1861). As drawn, the machine asserts that a check which already exited 0 can transition to an environmental hold or an idle kill, which the code cannot produce: CHECK_EXPIRED and the 126/127 branch are both read off the same invocation that would have had to set CHECK_RC=0. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1849-1862, 1945-1958`
- **State `gate-env-hold`: "one issue-trail comment naming the failing command and its own log".**<br>True only for the lint arm. `lint_env_hold` interpolates the failing command text ("command: $1") and lint.log (1942); the check arm's `env_hold` names neither the command nor CHECK_CMD's text — it names only the exit code and `$RUN_DIR/checks.log`, pointing the reader at `$BASE_REPO/.venv` as the suspected cause (1934). G14 gets this right for lint; the shared state description generalises the lint behaviour onto the check arm. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1933-1944`
- **G23 `check_model_refs` — enforcement "prevented"; disagreement #4 calls it "the ONE member of the check_* family that actually blocks".**<br>It blocks only builds of yellow-robots/factory, and only transitively: it is a test inside THIS repo's suite, and this repo's manifest happens to declare `check_cmd = "pytest tests/ -q"`. Nothing in the runner, the manifest schema, or CI knows the tool exists — a second registered repo gets no such gate. Verified: `grep` finds no non-test caller. Stated as a lane-level property ("the one check_* tool that is wired") it reads as factory machinery when it is repo-local consumer content, the same category as qa/lens.py. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/.yr/factory.toml:3 + /opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tests/test_check_model_refs.py:202-212`

## Found by the verifier, missing from the excavation

- An entire blocking deterministic gate is absent from the state machine: the empty-diff gate. After the tier and the review, `git diff --cached --quiet` on the worktree ends the run `fail_blocked "no changes produced"`. It is runner-side, deterministic, unrepairable, and disposes exactly like the tier's blocks (Reason=Blocked, salvage, teardown) — and it is the only gate that judges the build's OUTPUT rather than its correctness. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:2199-2200`
- The `site` vocabulary in gate-durations.json is not injective. `run_checks lint-repair-recheck` (2025) and `run_lint "$LINT_CMD" lint-repair-recheck` (2028) both call `record_gate_duration` with the literal `lint-repair-recheck`, so one run emits two entries with identical `site` and no field distinguishing check from lint. This sharpens the excavation's own gap ("a reader of the ledger has no registry row telling it what `site` may contain"): even with a schema, that value cannot identify which gate ran. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:2025, 2028, 1833-1836`
- The tester boundary guard's baseline is not the implementer's checkpoint on a resume. When `01-implement.done` is present the runner re-derives IMPL_TREE by `git add -A` + `write-tree` on the REUSED worktree, so any out-of-surface file a previous, held tester attempt already wrote is baked into the baseline and can never appear in the diff. Reachable: a tester-stage quota hold (llm_quota_hold at 1675) preserves the worktree with 01-implement.done set and 02-test.done absent. G4's structural claim ("diffing the tester's tree against the implementer's checkpoint tree") holds only on a fresh run. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:1613-1617, 1675, 1682-1686`
- Server CI never runs the repo's declared `check_cmd`. ci.yml hardcodes `pytest tests/ -n auto -q` while the manifest declares `pytest tests/ -q` — a different command, a different execution model (xdist), certifying the same tree. The Lint step is manifest-read precisely so there is "one contract on two hosts"; the test step is a second, independent declaration of the check gate. This is the inverse of the ref-mismatch gap the excavation did report, and it is the larger of the two: a repo whose check_cmd is not pytest gets no server-side check at all. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/.github/workflows/ci.yml:29-30 vs /opt/yellow-robots/factory/.claude/worktrees/task-420-walls/.yr/factory.toml:3`
- A malformed env `CHECK_IDLE_TIMEOUT` does not merely "flow into integer comparisons" — it silently disables the only kill in the lane. `[ "$idle" -ge "$CHECK_IDLE_TIMEOUT" ]` with a non-numeric right operand exits 2 ("integer expression expected"), and because it sits in an `if` condition `set -e` does not fire, so the loop polls forever, never kills, and never logs a rejection. The same shape disables the advisory at 1814. The gap is correctly identified; its consequence (guard off, not guard misbehaving) is not. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:816-817, 842-843, 1804, 1814`
- `server_ci` — named in the lane's own title — has no state, transition, or key row anywhere in the excavation. It is a manifest key with a fail-closed default (`required`), a declared enumeration, a pass-by-declaration branch (`not_required_declared`, CI_STATE at 586), an invalid-value refusal (`server_ci_invalid`, 583) and a conflicting-pair refusal on an armed repo (`server_ci_none_armed`, ~620). The notes defer it to the merge lane, but it is the one declaration that decides whether server CI gates at all. `/opt/yellow-robots/factory/.claude/worktrees/task-420-walls/tools/dev-runner.sh:244-262, 578-590, 618-624`

---

SCOPE AND PROVENANCE. Read from the worktree at /opt/yellow-robots/factory/.claude/worktrees/task-420-walls (HEAD = origin/main + the unmerged slice-5 branch). I diffed against origin/main: within this lane, slice 5 changes NOTHING — its only touches are `export YR_MACHINERY=1` in tools/dev-runner.sh:39-44 and os.environ.setdefault in tools/epic_gate.py:69-70 (walls-lane plumbing, no gate behaviour), the board-write wall in tools/board_plumbing.py, and a `tools/wall.py promote-check` call added to tools/promote.sh:65-70. That promote-wall call is UNMERGED and failed independent review at 0/5 criteria — I treated origin/main's promote.sh (no wall, no gate beyond open/on-board/not-epic) as the live behaviour, and G24's finding that promote.sh runs no check_task holds either way, since wall.py checks the YR-TASK-GATES record, not self-containedness. tools/wall.py additionally carries uncommitted local edits; nothing in this lane reads it.  WHAT IS AND IS NOT LIVE, restated for this lane: nothing from iteration 30 reaches a session (plugin still 0.10.0), so tools/check_trail.py and records.toml are merged-but-dark. Everything else in this lane — the DoR gate, check_cmd, the lint tier, the cardinality guards, the lens, the boundary guard, the liveness windows, the CI backstop — is live on main and running.  THE LANE'S SHAPE, in one sentence: the gates that actually dispose are all INSIDE the runner or inside server CI (check_cmd, lint_cmd, the boundary guard, the liveness kill, the manifest-key bounces, and — transitively, through the pytest suite — check_model_refs); every gate that carries the word "check_" in its filename and lives outside that path (check_links, check_task, check_supersession, check_trail) is invoked by no machine at all.  ONE OBSERVED PROPERTY OF THE LIVENESS GUARD, stated as fact rather than as a finding: `_gate_monitor` judges liveness by polling the byte size of the invocation's LOG FILE (tools/dev-runner.sh:1795-1801), and the initial `last_growth` is set to t0 (tools/dev-runner.sh:1793), so a gate that emits nothing at all begins accruing idle time immediately. Whether any given check command's output reaches that file promptly is a property of that command, not of this code; I did not test it.  VERIFIED BY EXECUTION at this HEAD (not inferred): `python3 qa/cardinality.py` → exit 0, no advisories (all three rules at exactly their declared max); `YR_BASE_REF=origin/main python3 qa/lens.py` → exit 0; `python3 tools/check_model_refs.py --scan-root .` → exit 0. I did not run the full pytest suite (the manifest's own stage_conduct records it at 761-812s).  TWO THINGS I DELIBERATELY LEFT TO ADJACENT LANES: the review verdict gate (gates.md lists it in the gate table, but its grammar, rounds and repair belong to the review lane — I recorded only its bundle input at G27), and the merge evaluator's four conditions plus `auto_merge` / `server_ci` / `merge_ci_timeout` (the three keys re-read at DECISION time rather than start-of-run, which is precisely what distinguishes them from every key in this lane).
