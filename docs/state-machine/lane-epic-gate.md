<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The epic gate and standing approval

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `epic:off-board` | An epic Issue exists in a repo but has no item on org project #1, so it carries no Status/Reason at all and is invisible to the whole state machine — the sweep's board query only ever iterates project items. | Absence of a ProjectV2Item for that issue under org project #1 (project number resolved by board_plumbing.project_number(), default 1). | `tools/epic_gate.py:104-128` |
| `epic:Backlog` | On the board, filed, not yet enacted under a standing approval. The sweep never touches it (it filters Status==Ready). | Projects single-select "Status" field on the epic's project item (option id OPT_BACKLOG). | `tools/board_plumbing.py:64-71` |
| `epic:Ready` | The standing approval has been enacted on this epic. This is the only state in which the sweep runs the per-epic algorithm at all — promotion, refusal, hold and self-close all live under it. | Projects "Status" field = Ready on the epic's project item. | `tools/epic_gate.py:1136` |
| `epic:Ready + Reason=Needs-info` | A refusal is on record against this epic: no valid approval, an un-dispositioned open question, an un-onboarded child repo, or a debt-epic close hold. NOTE: this value gates nothing — it is signage plus the per-refusal write-idempotency key. | Projects single-select "Reason" field on the epic's project item (option id OPT_NEEDSINFO). | `tools/epic_gate.py:970, tools/epic_gate.py:985, tools/epic_gate.py:950, tools/epic_gate.py:1066` |
| `epic:Ready + Reason=Blocked` | A refusal is on record: the next open child is not a Task, or that child declares itself gate-touching. Same non-gating semantics as Needs-info. | Projects "Reason" field = Blocked (option id OPT_BLOCKED). | `tools/epic_gate.py:1021, tools/epic_gate.py:1040` |
| `epic:not-Ready (cord-pulled)` | The human's veto: any Status other than Ready. The sweep skips the item entirely, so no child of it is ever visited, promoted, raised or closed; work already promoted or in flight is untouched. | Projects "Status" field on the epic's project item (any value != Ready). | `tools/epic_gate.py:1136` |
| `epic:closed-completed` | The epic is natively closed with stateReason COMPLETED — set when at least one child closed as completed. | Native GitHub issue state + stateReason on the epic Issue. | `tools/epic_gate.py:589-593, tools/epic_gate.py:952-954` |
| `epic:closed-not-planned` | The epic is natively closed as "not planned" — set only when every child closed not-planned. | Native GitHub issue state + stateReason on the epic Issue. | `tools/epic_gate.py:589-593` |
| `epic:Done` | The board's rendering of a closed epic. Written by Projects' built-in close→Done automation, not by any code in this repo. | Projects "Status" field = Done, written by GitHub Projects' native close→Done workflow. | `docs/rfcs/0003-task-state-model.md > Lifecycle` |
| `approval:present` | A standing-approval record exists: some comment on the epic's trail carries a line beginning `YR-EPIC-APPROVAL` at column 0 (raw, no leading-whitespace tolerance) and that same comment yields non-empty `design`, `review` and `who` values. The sweep trusts this named fact; it never re-runs the review. | An issue comment on the epic's trail (surface issue-trail). | `tools/epic_gate.py:429-434, records.toml:55-63` |
| `approval:absent-or-malformed` | No comment carries the marker at column 0, or the first that does is short a field. Promotion of every child is blocked while this holds. | Absence/shape of the comment above on the epic's trail. | `tools/epic_gate.py:437-447` |
| `epic-body:open-question present` | The epic body carries at least one line beginning `YR-OPEN-QUESTION:` at column 0. Presence only — the gate never judges whether the question is really open; a disposition is rewriting the line off the grammar. | The epic Issue body (surface issue-body). | `tools/epic_gate.py:450-457, records.toml:105-112` |
| `epic-body:debt-kind` | Some body line, stripped, is exactly `YR-ITERATION-KIND: tech-debt` — the epic is a debt epic and takes the fail-closed close path instead of self-closing. | The epic Issue body. | `tools/epic_gate.py:474-478, records.toml:198-205` |
| `debt:ledger-verdict present` | Some single epic comment carries the `YR-DEBT-LEDGER` sentinel line AND non-empty `items` and `net-lines` fields — the machine-checked pair that permits a debt epic's self-close. | An issue comment on the debt epic's trail. | `tools/epic_gate.py:481-490` |
| `debt:hold on record` | The gate has posted its `YR-DEBT-HOLD` comment on a finished debt epic; the marker's presence is what stops it re-posting on every tick. | An issue comment on the debt epic's trail. | `tools/epic_gate.py:941-951, tools/epic_gate.py:561-573` |
| `child:not-on-board` | The next open child has no project item on our board, so there is nothing to edit; the tick ends with no write and no record. | Absence of a matching node in the child's `projectItems` for project #1 (selection rule in board_plumbing.select_project_item). | `tools/epic_gate.py:1045-1047, tools/board_plumbing.py:170-179` |
| `child:Backlog` | A pre-approved slice waiting its turn in sub-issue order. Not busy — so it is the promotion candidate when it is first in open order. | Projects "Status" field on the child's project item. | `tools/epic_gate.py:1008, tools/epic_gate.py:1012` |
| `child:Ready (in flight)` | The promoted slice. Counts as the one slice in flight per epic — it blocks any further promotion under the epic until it closes. | Projects "Status" field = Ready on the child's project item. | `tools/epic_gate.py:88, tools/epic_gate.py:1071` |
| `child:In Progress (claimed)` | dev-runner has claimed the slice as its first act after the DoR gate. Busy. | Projects "Status" field = In Progress, written by tools/dev-runner.sh's set_status. | `tools/dev-runner.sh:1153-1154` |
| `child:In Progress, Reason-less, stale (stranded claim)` | A claim that looks in flight but is dead: Status has stood at In Progress past the staleness bound (STRANDED_AFTER_MIN, default 45 min) with no Reason, no live build holding that repo's own dispatch lock, and no open `task/<n>-…` PR. The sweep raises it. | Derived state: Projects Status field + its `updatedAt` timestamp, the per-repo flock at dispatch.repo_lock_path(repo), and the repo's open PR list. | `tools/epic_gate.py:280-297, tools/epic_gate.py:95` |
| `child:In Review` | PR opened. Busy — blocks further promotion. | Projects "Status" field = In Review on the child's project item. | `tools/epic_gate.py:88` |
| `child:off-track (Reason=Blocked \| Needs-info)` | Trouble stops the line: any open child wearing either Reason blocks all further promotion under that epic until a human clears it. The sweep never clears a Reason itself. | Projects "Reason" field on the child's project item. | `tools/epic_gate.py:89, tools/epic_gate.py:1008` |
| `child-body:gate-touching declared` | The child's OWN filed body carries a line beginning `YR-GATE-TOUCHING:` at column 0 with a non-empty reason after the prefix. Read from the child's body only — never the epic's, which legitimately carries the prefix inside per-task context slices. | The child Issue's body (surface issue-body). | `tools/epic_gate.py:460-471, records.toml:96-103` |
| `standalone-Ready item (the admission-wall subject)` | Any OPEN, Status=Ready board item whose Issue Type is not feature/epic — a genuine standalone task OR an epic child that is already Ready. The sweep applies the onboarding probe to it directly, off the Ready poll. | Projects Status field + native Issue Type on the board item. | `tools/epic_gate.py:1139, tools/epic_gate.py:1151-1168` |
| `repo:onboarded` | `.yr/factory.toml` is readable through the GitHub contents API for that repo (no ref argument, so the repo's DEFAULT branch). Cached per repo for one sweep. | A file in the target repo (read live via `gh api repos/<owner>/<name>/contents/.yr/factory.toml`); cached in a sweep-local dict. | `tools/epic_gate.py:762-793` |
| `repo:not-onboarded` | The contents probe returned a confirmed HTTP 404 — a real absence. Work headed here is refused fail-closed rather than sailed into a doomed build. | Same probe; the 404 is matched out of the gh failure text by a `\b404\b` regex. | `tools/epic_gate.py:759, tools/epic_gate.py:777-778` |
| `repo:unprobeable` | Two attempts at the contents probe failed for a non-404 reason (network, 5xx, rate limit, timeout) → ManifestProbeError. Deliberately neither onboarded nor not-onboarded: the item is skipped this tick, nothing is written, nothing is cached. | Transient; raised as an exception and surfaced only as a `probe-error` action line in sweep.log. | `tools/epic_gate.py:749-753, tools/epic_gate.py:780-793` |
| `repo:registered (for intake)` | A DIFFERENT notion of registration from the one above: a subdirectory of $YR_WORKSPACE that holds `.yr/factory.toml` in its working tree and whose git `origin` remote parses to owner/name. This list is what intake sweeps. | The sweep host's filesystem ($YR_WORKSPACE/<name>/.yr/factory.toml) plus each directory's git origin remote. | `tools/epic_gate.py:621-641, tools/epic_gate.py:1179` |
| `sweep:running (lock held)` | A sweep process holds the sweep flock; any tick arriving meanwhile is dropped by `flock -n` and never runs. Separate from every build lock, so a build never blocks a sweep and vice versa. | A lock file on the build host: SWEEP_LOCK, default ~/.cache/dev-runner/epic-sweep.lock. | `tools/dispatch.py:68, tools/dispatch.py:245` |
| `sweep:log` | The only durable trace of a sweep's decisions: every spawn appends to one shared sweep.log under the runs directory (deliberately not one file per tick). | $DEV_RUNNER_HOME/runs/sweep.log on the build host. | `tools/dispatch.py:246, tools/epic_gate.py:1182-1216` |
| `debt:below-threshold` | For a repo holding any Type=Feature issue on the board: fewer closed-as-completed, non-debt feature epics since the anchor than `debt_round_every`. Recorded as a `debt-count` action only; no write. | Derived per sweep from the GitHub search index (closed Type=Feature issues) + the threshold (env > manifest > default 10). | `tools/epic_gate.py:728-743, tools/epic_gate.py:880-882` |
| `debt:raise-open` | A `YR-DEBT-DUE` Type=Task issue exists open for the (repo, anchor) key, keyed on the anchor and never re-keyed on the count, so the same anchor never raises twice. | An open Issue in the target repo whose body carries the DUE sentinel plus matching `repo:`/`anchor:` fields; found via the search index. | `tools/epic_gate.py:822-841, tools/epic_gate.py:849-860` |
| `debt:raise-open-but-off-board` | The raise issue exists but has no item on our board — the sweep repairs it (item-add + Status=Backlog) rather than raising a duplicate. | The raise Issue's `projectItems` (empty for our board). | `tools/epic_gate.py:884-899` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `issue exists in a registered repo, off-board` → `issue has a project item on board #1` | epic-gate sweep (`_sweep_intake`), invoked by `main()` | **prevented** | tools/epic_gate.py `_sweep_intake` (:665-685) — reachable; it is the first pass sweep_epics runs (:1127). A per-repo read failure is isolated as an `intake-error` action and never fatal to another repo (:675-678). |
| 2 | `board item with no Status` → `epic/task at Status=Backlog` | GitHub Projects' own item-added workflow (native automation, configured on the board, not in this repo) | ⚠️ **unenforced** | None in this repo — no code here writes, verifies or records this workflow's existence. |
| 3 | `epic:Backlog` → `epic:Ready` | human, or an attended operator agent session under the design's standing approval (no factory tool performs it) | ⚠️ **unenforced** | No guard on the act itself at tip. `tools/promote.sh` refuses to perform it (:56-62). On the UNMERGED, review-rejected slice-5 branch two would apply: `tools/board_plumbing.py:_attended_wall` (:112-153), reachable only when the flip goes through `set_field`, and `tools/wall.py:decide` via the PreToolUse hook (:244-268, hooks/hooks.json), reachable only when the flip is a Bash command containing `board_plumbing.py … set-field`. A GitHub-UI flip or a raw `gh project item-edit` passes both untouched. |
| 4 | `epic:Ready` → `epic:not-Ready (cord-pull)` | human (her standing veto) | **prevented** | tools/epic_gate.py sweep_epics (:1136) — the Status!=Ready `continue`; reachable on every tick. |
| 5 | `sweep:idle` → `sweep:running` | n8n schedule trigger → dispatch service (`POST /sweep` → `run_sweep`) → detached `flock -n <SWEEP_LOCK> epic_gate.py` | **prevented** | tools/dispatch.py Handler.do_POST (:261-274) for auth/route; the `flock -n` in run_sweep (:245) for single-flight. Both reachable on the path n8n takes. |
| 6 | `approval:absent` → `approval:present` | attended operator session (canon); mechanically, any account that can comment on the epic | *partial* | tools/epic_gate.py `_has_valid_approval` (:429-434) + `_approval_candidates` (:418-426) — reachable at every promotion decision. Nothing checks WHO posted it, nor that the named design is `active`. |
| 7 | `epic:Ready (open question in body)` → `epic:Ready + Reason=Needs-info, nothing promoted` | epic-gate sweep (`_process_epic` step 0) | **prevented** | tools/epic_gate.py `_process_epic` (:963-973), reachable before any Ready write. |
| 8 | `epic:Ready (no valid approval)` → `epic:Ready + Reason=Needs-info, nothing promoted` | epic-gate sweep (`_process_epic` step 1) | **prevented** | tools/epic_gate.py `_process_epic` (:979-988) — reachable before any Ready write. |
| 9 | `epic:Ready, approval valid, some open child busy` → `epic:Ready, no promotion this tick (wait)` | epic-gate sweep (`_process_epic` step 2) | **prevented** | tools/epic_gate.py `_process_epic` (:995-1009) — reachable on every Ready epic that clears steps 0 and 1. |
| 10 | `child:In Progress, Reason-less, stale` → `child:Reason=Blocked (stranded claim raised)` | epic-gate sweep (`_process_epic` step 2's inline check, via `_is_stranded`) | detected | tools/epic_gate.py `_is_stranded` (:280-297) called from `_process_epic` (:1000-1007). Reachable ONLY for epics that pass steps 0 and 1 — an epic blocked on open questions or a missing approval returns before this loop. |
| 11 | `standalone task: In Progress, Reason-less, stale` → `standalone task: Reason=Blocked` | epic-gate sweep (`_sweep_standalone_stranded`, an independent pass straight over the board) | detected | tools/epic_gate.py `_sweep_standalone_stranded` (:309-341), called unconditionally from sweep_epics (:1128-1129). |
| 12 | `epic:Ready, next open child is not Type=Task` → `epic:Ready + Reason=Blocked, nothing promoted` | epic-gate sweep (`_process_epic` step 3) | **prevented** | tools/epic_gate.py `_process_epic` (:1012-1024) — reachable before any Ready write. |
| 13 | `epic:Ready, next open child declares gate-touching` → `epic:Ready + Reason=Blocked, nothing promoted` | epic-gate sweep (`_process_epic` step 3.5) | **prevented** | tools/epic_gate.py `_gate_touching_declaration` (:460-471) called from `_process_epic` (:1033-1043) — reachable before any Ready write. |
| 14 | `epic:Ready, next open child not on the board` → `no change (tick ends silently)` | epic-gate sweep (`_process_epic`) | **prevented** | tools/epic_gate.py `_pi_node` (:596-600) / `_process_epic` (:1045-1047) — reachable. |
| 15 | `epic:Ready, child's repo unprobeable` → `no change (skipped this tick, will re-probe)` | epic-gate sweep (`_process_epic`, admission wall) | **prevented** | tools/epic_gate.py `_repo_has_manifest` (:762-782) / `_process_epic` (:1055-1059) — reachable. |
| 16 | `epic:Ready, child's repo confirmed not onboarded` → `epic:Ready + Reason=Needs-info, child never promoted` | epic-gate sweep (`_process_epic`, admission wall) | **prevented** | tools/epic_gate.py `_process_epic` (:1055-1069) — reachable, and positioned before the Ready write. |
| 17 | `child:Backlog (first open child, all gates clear)` → `child:Ready (promoted)` | epic-gate sweep (`_process_epic` step 3, the promotion itself) | **prevented** | tools/epic_gate.py `_process_epic` (:918-1073) is the whole guard chain; the write at :1071 is reachable only past every check above it. |
| 18 | `standalone-Ready item on an un-onboarded repo` → `Status=Backlog + Reason=Needs-info` | epic-gate sweep (the admission wall applied directly, off the Ready loop) | **prevented** | tools/epic_gate.py sweep_epics (:1151-1168) — reachable on every tick for every Ready non-epic item. |
| 19 | `standalone-Ready item, repo unprobeable` → `no change (skipped, re-probed next tick)` | epic-gate sweep | **prevented** | tools/epic_gate.py sweep_epics (:1158-1162) — reachable. |
| 20 | `epic:Ready, had children, none open, not a debt epic` → `epic:closed (completed \| not planned)` | epic-gate sweep (`_process_epic` step 5, the self-close branch) | **prevented** | tools/epic_gate.py `_process_epic` (:939-954) — reachable; mutually exclusive with promotion/waiting. |
| 21 | `debt epic:Ready, none open, no ledger verdict` → `epic:Ready + Reason=Needs-info (held, not closed)` | epic-gate sweep (`_process_epic`, the fail-closed debt exception) | **prevented** | tools/epic_gate.py `_process_epic` (:941-951) — reachable; takes precedence over the plain close branch. |
| 22 | `debt epic:Ready, none open, valid ledger verdict on record` → `epic:closed` | epic-gate sweep | **prevented** | tools/epic_gate.py `_has_ledger_verdict` (:481-490) — reachable. |
| 23 | `epic:Ready + Reason set (any refusal)` → `epic:Ready, Reason cleared` | human (or an attended session on her instruction) | ⚠️ **unenforced** | None — `board_plumbing.set_field(..., opt=None)` performs the clear (:155-166); on the unmerged slice-5 branch an attended clear through that path is walled by `_attended_wall` (:112-153). |
| 24 | `child:Ready (promoted)` → `child:In Progress (claimed) \| child:Backlog+Needs-info (bounced)` | dev-runner (spawned by dispatch off the n8n Ready poll) | **prevented** | tools/dev-runner.sh DoR gate (:971-990) and the NEEDS_INFO bounce (:1128-1134) — reachable before claim, worktree or any LLM call. |
| 25 | `standalone task:Backlog` → `standalone task:Ready` | attended operator session / human, through `tools/promote.sh` (the sibling input gate the epic lane deliberately does not cover) | *partial* | tools/promote.sh refuse gate (:56-62) — reachable, writes nothing on refusal. The wall call at :68-69 is reachable only on the unmerged branch and only via promote.sh (a hand `gh`/UI flip bypasses it). |
| 26 | `epic on the board` → `refused promote attempt (no write)` | attended operator session running `tools/promote.sh` against an epic | **prevented** | tools/promote.sh (:58-62) — reachable, before any write. |
| 27 | `debt:below-threshold` → `debt:raise-open (a tech-debt round is named as due)` | epic-gate sweep (`_sweep_debt_counters`), over the distinct repos holding any Type=Feature issue on the board | **prevented** | tools/epic_gate.py `_sweep_debt_counters` (:863-915), called from sweep_epics (:1170-1172) — reachable. |
| 28 | `debt:raise-open-but-off-board` → `debt:raise-open on board at Backlog` | epic-gate sweep (`_sweep_debt_counters` repair arm) | **prevented** | tools/epic_gate.py (:884-899) — reachable. |
| 29 | `sweep:running` → `sweep aborted mid-tick (partial work)` | epic-gate sweep (unhandled exception) | ⚠️ **unenforced** | None — no isolation exists at these sites. |
| 30 | `sweep:running (hung)` → `every later tick dropped` | dispatch (`flock -n`) — a silent drop, not an error | **prevented** | tools/dispatch.py run_sweep (:245) — the lock is the guard against concurrent sweeps; nothing guards against a stuck holder. |
| 31 | `child added under a Ready epic (any time, by anyone)` → `that child in the promotion order` | any actor with sub-issue write access (human or agent) | ⚠️ **unenforced** | None. `_process_epic` never compares the child set against anything. |

### Detail

#### 1. `issue exists in a registered repo, off-board` → `issue has a project item on board #1`

`T1`

- **Actor:** epic-gate sweep (`_sweep_intake`), invoked by `main()`
- **Trigger:** A sweep tick (POST /sweep → dispatch.run_sweep → epic_gate.py main)
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_sweep_intake` (:665-685) — reachable; it is the first pass sweep_epics runs (:1127). A per-repo read failure is isolated as an `intake-error` action and never fatal to another repo (:675-678).
- **Records:** `an `{action: intake}` line in sweep.log via main() (`epic-gate: added <repo>#<n> to the board`)`, `no trail record of any kind`
- **Preconditions:** The repo is a $YR_WORKSPACE subdirectory holding `.yr/factory.toml` in its working tree with a parseable git origin remote `[code: tools/epic_gate.py:621-641]`<br>The issue is OPEN (the read itself excludes closed; `gh issue list` never returns PRs) `[code: tools/epic_gate.py:658-662]`<br>(repo, number) is not already a key on the board, in any state or Status `[code: tools/epic_gate.py:644-655, tools/epic_gate.py:681]`<br>Canon: GitHub's one-per-project auto-add cannot serve a board spanning every registered repo, so intake closes the gap `[canon-only: skills/factory/references/onboarding.md > 4. Register on the board]`
- **Postconditions:** Exactly one `gh project item-add` is performed; intake writes NO Status and NO Reason `[code: tools/epic_gate.py:683, tools/epic_gate.py:665-669]`<br>The board's own item-added workflow then sets Status=Backlog `[canon-only: tools/epic_gate.py:44-49]`

#### 2. `board item with no Status` → `epic/task at Status=Backlog`

`T2`

- **Actor:** GitHub Projects' own item-added workflow (native automation, configured on the board, not in this repo)
- **Trigger:** An item being added to project #1
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None in this repo — no code here writes, verifies or records this workflow's existence.
- **Preconditions:** The board carries an item-added workflow (item-scoped, therefore covering every repo) `[canon-only: tools/epic_gate.py:44-49]`<br>RFC 0003 accepts that an issue must be added to the project to carry status and assumes a Projects auto-add rule handles it `[canon-only: docs/rfcs/0003-task-state-model.md > Compromises]`
- **Postconditions:** Status=Backlog on the new item `[canon-only: tools/epic_gate.py:666-668]`

#### 3. `epic:Backlog` → `epic:Ready`

`T3`

- **Actor:** human, or an attended operator agent session under the design's standing approval (no factory tool performs it)
- **Trigger:** The governing product-spec / feature-rfc is `active`, the technical-rfc is filed on the epic Issue and its review has run
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** No guard on the act itself at tip. `tools/promote.sh` refuses to perform it (:56-62). On the UNMERGED, review-rejected slice-5 branch two would apply: `tools/board_plumbing.py:_attended_wall` (:112-153), reachable only when the flip goes through `set_field`, and `tools/wall.py:decide` via the PreToolUse hook (:244-268, hooks/hooks.json), reachable only when the flip is a Bash command containing `board_plumbing.py … set-field`. A GitHub-UI flip or a raw `gh project item-edit` passes both untouched.
- **Records:** ``YR-EPIC-APPROVAL` on the epic trail (canon: before the flip)`, ``YR-BOARD-FLIP` (canon, it-30; no reader at tip)`
- **Preconditions:** The human's input gate: a product-spec or feature-rfc has been set `active` (no agent ever sets `active`) `[canon-only: skills/factory/references/closing.md > 1. Promote to Ready]`<br>Record-before-flip: the standing-approval record is posted on the epic trail before the Status write `[canon-only: AGENTS.md > Conventions (Attended operator sessions)]`<br>Reified as a typed `YR-BOARD-FLIP` record for every board act (it-30 step 9) `[canon-only: skills/factory/references/attended-lane.md > The mandatory step set]`<br>The governing spec's own wording: setting a boarded epic's Status to Ready ENACTS the approval — done by the human, or by an agent under it; the record, not the actor, is the checked fact `[canon-only: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What]`
- **Postconditions:** Status=Ready on the epic's board item; the sweep begins visiting it `[code: tools/epic_gate.py:1136]`<br>The Ready build-poll must NOT dispatch it — the n8n filter drops issueType Feature and Epic, and the runner's own Type gate refuses with no writes `[code+canon: deploy/n8n-dispatch.json:40, tools/dev-runner.sh:982-990]`

#### 4. `epic:Ready` → `epic:not-Ready (cord-pull)`

`T4`

- **Actor:** human (her standing veto)
- **Trigger:** The human takes the epic out of Ready at any time
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py sweep_epics (:1136) — the Status!=Ready `continue`; reachable on every tick.
- **Preconditions:** None — the cord-pull is unconditional and belongs to the human `[canon-only: skills/factory/references/attended-lane.md > The human's checkpoints (what the coordination arm surfaces)]`
- **Postconditions:** The sweep skips the item; no child of it is visited, so none is promoted, raised or examined for a stranded claim `[code: tools/epic_gate.py:1136]`<br>Already-promoted and in-flight work is unaffected `[code+canon: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > Acceptance criteria (EARS)]`<br>A cord-pulled epic with all children closed is never auto-closed `[code+canon: tools/epic_gate.py:1136]`

#### 5. `sweep:idle` → `sweep:running`

`T5`

- **Actor:** n8n schedule trigger → dispatch service (`POST /sweep` → `run_sweep`) → detached `flock -n <SWEEP_LOCK> epic_gate.py`
- **Trigger:** The n8n epic-sweep workflow's schedule tick
- **Enforcement:** **prevented** · **Guard site:** tools/dispatch.py Handler.do_POST (:261-274) for auth/route; the `flock -n` in run_sweep (:245) for single-flight. Both reachable on the path n8n takes.
- **Records:** `sweep.log lines, one per action taken (`epic-gate: …`)`
- **Preconditions:** The request carries the correct bearer token (constant-time compare) and the path is /sweep `[code: tools/dispatch.py:261-266, tools/dispatch.py:273-274]`<br>The sweep lock is free — `flock -n`, non-blocking, on a lock separate from every build lock `[code: tools/dispatch.py:245, tools/dispatch.py:68]`<br>Canon: the sweep takes no issue/repo; it reads and writes the board itself `[code+canon: deploy/DISPATCH.md > Deploying the epic-gate sweep]`
- **Postconditions:** One `epic_gate.py main()` runs with an allowlisted environment and appends its report lines to the shared sweep.log; dispatch answers 202 immediately, before the sweep does anything `[code: tools/dispatch.py:235-249, tools/dispatch.py:180-185]`<br>`main()` supplies the workspace-discovered repo list for intake and always returns 0 `[code: tools/epic_gate.py:1176-1217]`

#### 6. `approval:absent` → `approval:present`

`T6`

- **Actor:** attended operator session (canon); mechanically, any account that can comment on the epic
- **Trigger:** The technical-rfc review has run under the design's standing approval
- **Enforcement:** *partial* · **Guard site:** tools/epic_gate.py `_has_valid_approval` (:429-434) + `_approval_candidates` (:418-426) — reachable at every promotion decision. Nothing checks WHO posted it, nor that the named design is `active`.
- **Records:** ``YR-EPIC-APPROVAL` (records.toml row; surface issue-trail; fields design/review/who)`
- **Preconditions:** A comment whose line begins `YR-EPIC-APPROVAL` at column 0 (block or one-line form) carrying non-empty design/review/who `[code+canon: tools/epic_gate.py:418-434]`<br>Canon: posted by the attended operator session under the design's standing approval, record-before-flip; the human's gate sits at design-active, never per-epic (owner's ruling 2026-08-04) `[canon-only: skills/factory/references/authoring.md > 3. Cross the airlock → technical-rfc]`<br>Canon: `design` names the governing product-spec/feature-rfc, `review` names the technical-rfc review's outcome, `who` names who is attesting `[canon-only: skills/factory/references/authoring.md > 3. Cross the airlock → technical-rfc]`
- **Postconditions:** The next sweep's `_has_valid_approval` returns True and promotion is unblocked — the sweep trusts the named fact and never re-runs the review `[code: tools/epic_gate.py:429-434]`<br>The gate's own refusal comment can never satisfy the key: it names the marker and fields only in backticked prose, never at column 0 `[code+canon: tools/epic_gate.py:503-510, tests/test_epic_gate.py:781]`

#### 7. `epic:Ready (open question in body)` → `epic:Ready + Reason=Needs-info, nothing promoted`

`T7`

- **Actor:** epic-gate sweep (`_process_epic` step 0)
- **Trigger:** A sweep tick reaching a Ready, OPEN, Feature/Epic-typed item that has at least one open child
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:963-973), reachable before any Ready write.
- **Records:** ``YR-EPIC-GATE: open-questions` on the epic trail, naming each marker by line number plus a backticked excerpt — never reproducing a marker at column 0, so the record cannot satisfy its own detector`
- **Preconditions:** The epic body carries ≥1 line beginning `YR-OPEN-QUESTION:` at column 0 (raw startswith — an indented, blockquoted or inline-backticked mention never fires; a fenced content line DOES) `[code: tools/epic_gate.py:450-457]`<br>This runs AFTER the no-open-children branch and BEFORE the approval check — a finished epic's close/hold decision is unaffected by any marker `[code: tools/epic_gate.py:956-963]`<br>Canon: open questions never ride the epic; an unresolved WHAT-call goes back into the governing design doc `[code+canon: skills/factory/references/authoring.md > 3. Cross the airlock → technical-rfc]`
- **Postconditions:** The refusal comment is posted iff its own marker is not already on record; Reason is set to Needs-info iff not already Needs-info — the two keyed independently `[code: tools/epic_gate.py:963-973]`<br>Nothing is promoted this tick or any later tick while a marker line stands `[code: tools/epic_gate.py:972-973]`<br>Recovery is dispositioning the line (rewriting it off the grammar); the comment explicitly says no Reason needs clearing `[code+canon: tools/epic_gate.py:556-557]`

#### 8. `epic:Ready (no valid approval)` → `epic:Ready + Reason=Needs-info, nothing promoted`

`T8`

- **Actor:** epic-gate sweep (`_process_epic` step 1)
- **Trigger:** A sweep tick, past the open-questions gate
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:979-988) — reachable before any Ready write.
- **Records:** ``YR-EPIC-GATE: no-approval` on the epic trail`
- **Preconditions:** No epic comment carries a column-0 `YR-EPIC-APPROVAL` line with all three fields non-empty `[code: tools/epic_gate.py:429-434]`
- **Postconditions:** The comment is posted iff `YR-EPIC-GATE: no-approval` is not already on record; Reason=Needs-info written iff not already `[code: tools/epic_gate.py:979-988]`<br>The refusal names which requirement failed — no marker at all, or which of design/review/who is empty on the FIRST marker-carrying comment `[code: tools/epic_gate.py:437-447]`<br>Canon: absent, unmatched or short a field, it blocks EVERY child's promotion until corrected `[code+canon: skills/factory/references/authoring.md > 3. Cross the airlock → technical-rfc]`

#### 9. `epic:Ready, approval valid, some open child busy` → `epic:Ready, no promotion this tick (wait)`

`T9`

- **Actor:** epic-gate sweep (`_process_epic` step 2)
- **Trigger:** A sweep tick
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:995-1009) — reachable on every Ready epic that clears steps 0 and 1.
- **Preconditions:** Any open child's own project item reads Status in {Ready, In Progress, In Review} or Reason in {Blocked, Needs-info} `[code: tools/epic_gate.py:88-89, tools/epic_gate.py:1008]`<br>Status/Reason are read from the CHILD's own `projectItems` (issue-side authoritative — `gh project item-list` lags ~1 min) `[code: tools/epic_gate.py:22-24, tools/epic_gate.py:596-600]`<br>Canon: one slice in flight per epic; trouble stops the line `[code+canon: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > Acceptance criteria (EARS)]`
- **Postconditions:** The function returns at the FIRST busy child; children after it are never examined this tick `[code: tools/epic_gate.py:1008-1009]`<br>A hand-promoted child counts as the one slice in flight and the guards hold `[canon-only: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What]`

#### 10. `child:In Progress, Reason-less, stale` → `child:Reason=Blocked (stranded claim raised)`

`T10`

- **Actor:** epic-gate sweep (`_process_epic` step 2's inline check, via `_is_stranded`)
- **Trigger:** A sweep tick reaching an In-Progress, Reason-less open child of a Ready epic that has cleared steps 0 and 1
- **Enforcement:** detected · **Guard site:** tools/epic_gate.py `_is_stranded` (:280-297) called from `_process_epic` (:1000-1007). Reachable ONLY for epics that pass steps 0 and 1 — an epic blocked on open questions or a missing approval returns before this loop.
- **Records:** ``YR-EPIC-GATE: stranded claim — In Progress <n> min with no live build…` on the child's trail (advisory to the human)`
- **Preconditions:** The child's project item exists and has an id; Status==In Progress with no Reason `[code: tools/epic_gate.py:1000]`<br>Status `updatedAt` age > STRANDED_AFTER_MIN (default 45, env-overridable, exclusive of the bound) `[code: tools/epic_gate.py:95, tools/epic_gate.py:289-291]`<br>No build holds THIS CHILD'S OWN repo's dispatch lock (`dispatch.repo_lock_path`, never a host-global lock) `[code: tools/epic_gate.py:249-268, tools/epic_gate.py:292-294]`<br>No open PR whose head branch starts `task/<child#>-` `[code: tools/epic_gate.py:271-277]`<br>Canon: a hard runner death between claim and PR/fail_blocked leaves In Progress with no Reason forever — neither in flight nor off-track `[code+canon: tools/epic_gate.py:29-39]`
- **Postconditions:** Reason=Blocked written on the CHILD's item and the stranded comment posted on the child's own repo/issue `[code: tools/epic_gate.py:1004-1005]`<br>The line still stops (In Progress is already busy); the raise is what makes it visibly off-track `[code: tools/epic_gate.py:990-994]`<br>The sweep never clears the Reason it just set — clearing is the human's explicit resume act `[code+canon: tools/epic_gate.py:1091-1092]`

#### 11. `standalone task: In Progress, Reason-less, stale` → `standalone task: Reason=Blocked`

`T11`

- **Actor:** epic-gate sweep (`_sweep_standalone_stranded`, an independent pass straight over the board)
- **Trigger:** A sweep tick — this pass runs before the Ready loop and is independent of the Ready filter
- **Enforcement:** detected · **Guard site:** tools/epic_gate.py `_sweep_standalone_stranded` (:309-341), called unconditionally from sweep_epics (:1128-1129).
- **Records:** ``YR-EPIC-GATE: stranded claim …` (the same body)`
- **Preconditions:** Board item content is an OPEN Issue of Type=Task with NO `parent` (GitHub's own sub-issue relationship) `[code: tools/epic_gate.py:322-328]`<br>Status==In Progress, no Reason, item id present `[code: tools/epic_gate.py:329-333]`<br>`_is_stranded` returns True — the identical check the per-epic pass uses `[code: tools/epic_gate.py:334]`
- **Postconditions:** Reason=Blocked on the item and the byte-identical stranded comment on its trail `[code: tools/epic_gate.py:337-340]`<br>A child WITH a parent is always skipped here, keeping the pass strictly additive to `_process_epic` `[code: tools/epic_gate.py:327-328]`

#### 12. `epic:Ready, next open child is not Type=Task` → `epic:Ready + Reason=Blocked, nothing promoted`

`T12`

- **Actor:** epic-gate sweep (`_process_epic` step 3)
- **Trigger:** A sweep tick where no open child is busy
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:1012-1024) — reachable before any Ready write.
- **Records:** ``YR-EPIC-GATE: not-a-task` on the epic trail`
- **Preconditions:** `open_children[0]`'s issueType name, lowercased, != "task" `[code: tools/epic_gate.py:1012-1013]`<br>Canon: nested decompositions are out of scope; the gate does NOT skip ahead to a later Task `[code+canon: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > Out of scope]`
- **Postconditions:** Comment posted iff `YR-EPIC-GATE: not-a-task` not already on record; Reason=Blocked iff not already Blocked `[code: tools/epic_gate.py:1016-1024]`<br>No later Task in the order is promoted `[code: tools/epic_gate.py:1012-1024]`

#### 13. `epic:Ready, next open child declares gate-touching` → `epic:Ready + Reason=Blocked, nothing promoted`

`T13`

- **Actor:** epic-gate sweep (`_process_epic` step 3.5)
- **Trigger:** A sweep tick past the Type gate
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_gate_touching_declaration` (:460-471) called from `_process_epic` (:1033-1043) — reachable before any Ready write.
- **Records:** ``YR-EPIC-GATE: gate-touching` on the epic trail`
- **Preconditions:** The CHILD's own body carries a column-0 `YR-GATE-TOUCHING:` line whose text after the prefix, stripped, is non-empty (an empty reason keeps the technical-rfc template's shipped slot inert) `[code: tools/epic_gate.py:460-471]`<br>Read from the child's body only, never the epic's — the technical-rfc's per-task context slices legitimately carry the prefix inside the epic body `[code+canon: tools/epic_gate.py:1026-1032, skills/factory/references/authoring.md > 3. Cross the airlock → technical-rfc]`<br>Runs BEFORE the project-item lookup on purpose, so a gate-touching child refuses even when it is not yet on the board `[code: tools/epic_gate.py:1028-1032]`<br>Canon: gate evolution is attended work; the pipeline builds under fixed gates — a duty of the architect's role, not advice `[canon-only: skills/factory/references/architect.md > (2. The crossing)]`
- **Postconditions:** Comment posted iff `YR-EPIC-GATE: gate-touching` not already on record; Reason=Blocked iff not already; the declared reason is backticked in the record so it cannot self-trigger the detector next tick `[code: tools/epic_gate.py:522-531, tools/epic_gate.py:1033-1043]`

#### 14. `epic:Ready, next open child not on the board` → `no change (tick ends silently)`

`T14`

- **Actor:** epic-gate sweep (`_process_epic`)
- **Trigger:** A sweep tick past the Type and gate-touching gates
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_pi_node` (:596-600) / `_process_epic` (:1045-1047) — reachable.
- **Preconditions:** `select_project_item` finds no node for project #1 among the child's `projectItems`, or the node has no id `[code: tools/epic_gate.py:1045-1047, tools/board_plumbing.py:170-179]`
- **Postconditions:** No write, no comment, no action recorded — the epic is silent this tick `[code: tools/epic_gate.py:1046-1047]`

#### 15. `epic:Ready, child's repo unprobeable` → `no change (skipped this tick, will re-probe)`

`T15`

- **Actor:** epic-gate sweep (`_process_epic`, admission wall)
- **Trigger:** Two consecutive non-404 failures of the contents probe (network, 5xx, rate limit, timeout) with a 2s backoff between
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_repo_has_manifest` (:762-782) / `_process_epic` (:1055-1059) — reachable.
- **Records:** `a `probe-error` line in sweep.log naming the epic, the child and the error`
- **Preconditions:** `_repo_has_manifest` exhausted `_MANIFEST_PROBE_ATTEMPTS` (2) without a confirmed 404 → ManifestProbeError `[code: tools/epic_gate.py:757-782]`<br>The failure is NOT cached, so the next same-repo read this sweep, or the next sweep, probes again `[code: tools/epic_gate.py:785-793]`
- **Postconditions:** The epic returns a `probe-error` action; NO comment and NO field write happen on this path (issue #140) `[code: tools/epic_gate.py:1055-1059]`

#### 16. `epic:Ready, child's repo confirmed not onboarded` → `epic:Ready + Reason=Needs-info, child never promoted`

`T16`

- **Actor:** epic-gate sweep (`_process_epic`, admission wall)
- **Trigger:** A sweep tick immediately before the Ready write on the promotion candidate
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:1055-1069) — reachable, and positioned before the Ready write.
- **Records:** ``YR-EPIC-GATE: not-onboarded` on the EPIC's trail`
- **Preconditions:** The contents probe for the CHILD's repo returned a confirmed 404 — no `.yr/factory.toml` `[code: tools/epic_gate.py:762-782, tools/epic_gate.py:1060]`<br>Canon: onboarding cannot ride a build — the manifest and runnable scaffold are attended design-side prerequisites, never a slice the factory promotes for itself `[code+canon: skills/factory/references/onboarding.md > The bootstrap invariant]`
- **Postconditions:** The EPIC bounces (comment iff `YR-EPIC-GATE: not-onboarded` not on record; Reason=Needs-info iff not already); the CHILD is never touched and no Status is written anywhere `[code: tools/epic_gate.py:1050-1069]`<br>The probe result is cached per repo for the rest of the sweep `[code: tools/epic_gate.py:785-793]`

#### 17. `child:Backlog (first open child, all gates clear)` → `child:Ready (promoted)`

`T17`

- **Actor:** epic-gate sweep (`_process_epic` step 3, the promotion itself)
- **Trigger:** A sweep tick where the epic is OPEN + Ready + Feature/Epic-typed, has children and ≥1 open child, no open-question marker, a valid approval record, no busy open child, and the first open child is a Task with no gate-touching declaration, on the board, in an onboarded repo
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:918-1073) is the whole guard chain; the write at :1071 is reachable only past every check above it.
- **Records:** ``YR-AUTO-PROMOTED` on the child's trail ("Promoted **automatically** by the epic-gate under epic #N (standing approval on record)… Promotion is automatic, not a human act.")`
- **Preconditions:** All of T7–T16's negations hold, evaluated in that exact order `[code: tools/epic_gate.py:930-1069]`<br>Promotion order is the epic's native `subIssues` connection order, NOT issue number and not the board (the board has no sub-issue order) `[code: tools/epic_gate.py:17-19, tools/epic_gate.py:1011-1012]`<br>Canon: progressive, ordered, one slice in flight; promotion is automatic, not a human act `[code+canon: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What]`
- **Postconditions:** Exactly one write: Status=Ready on the child's item, via the one field write in the board-plumbing home `[code: tools/epic_gate.py:1071, tools/board_plumbing.py:155-166]`<br>The accountability comment lands on the child's OWN repo/issue naming the authorizing epic `[code: tools/epic_gate.py:1072, tools/epic_gate.py:494-500]`<br>The sweep never sets any Status but Ready (promotion) or Backlog (the standalone bounce and the debt raise), and never clears a Reason `[code: tools/epic_gate.py:1090-1097]`<br>Idempotent across ticks: the child is now Ready, hence busy, so the next tick stops at the busy check `[code: tools/epic_gate.py:1008-1009, tests/test_epic_gate.py:1335]`

#### 18. `standalone-Ready item on an un-onboarded repo` → `Status=Backlog + Reason=Needs-info`

`T18`

- **Actor:** epic-gate sweep (the admission wall applied directly, off the Ready loop)
- **Trigger:** A sweep tick reaching an OPEN, Status=Ready item whose Issue Type is not feature/epic
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py sweep_epics (:1151-1168) — reachable on every tick for every Ready non-epic item.
- **Records:** ``YR-EPIC-GATE: not-onboarded` on the item's trail`
- **Preconditions:** The item has an id and `_repo_onboarded` returns False for its repo `[code: tools/epic_gate.py:1155-1164]`<br>This branch takes epic children that are ALREADY Ready as well as genuine standalone tasks (unlike `_sweep_standalone_stranded`, which skips parented items) `[code: tools/epic_gate.py:1084-1086, tools/epic_gate.py:327-328]`
- **Postconditions:** Two field writes (Status=Backlog then Reason=Needs-info) plus the not-onboarded comment on the item's own repo — the runner's own DoR bounce shape `[code: tools/epic_gate.py:1165-1168]`<br>Idempotent by construction: the Backlog write drops the item out of the Ready filter, so it is never re-commented `[code: tools/epic_gate.py:1151-1154]`

#### 19. `standalone-Ready item, repo unprobeable` → `no change (skipped, re-probed next tick)`

`T19`

- **Actor:** epic-gate sweep
- **Trigger:** ManifestProbeError on the standalone branch
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py sweep_epics (:1158-1162) — reachable.
- **Records:** `a `probe-error` line in sweep.log naming the item`
- **Preconditions:** `_repo_onboarded` raised ManifestProbeError `[code: tools/epic_gate.py:1158-1162]`
- **Postconditions:** A `probe-error` action is appended; no Status, no Reason, no comment `[code: tools/epic_gate.py:1160-1162]`

#### 20. `epic:Ready, had children, none open, not a debt epic` → `epic:closed (completed \| not planned)`

`T20`

- **Actor:** epic-gate sweep (`_process_epic` step 5, the self-close branch)
- **Trigger:** A sweep tick where `open_children` is empty and `children` is not
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:939-954) — reachable; mutually exclusive with promotion/waiting.
- **Records:** `a `close` line in sweep.log (`epic-gate: closed epic #N (reason=…)`) — NO trail record of any kind`
- **Preconditions:** The epic has ≥1 child (a childless epic is never "finished" and is left alone) `[code: tools/epic_gate.py:930-931]`<br>No child is OPEN `[code: tools/epic_gate.py:939-940]`<br>The body carries no tech-debt kind line `[code: tools/epic_gate.py:941]`<br>Explicitly INDEPENDENT of the standing-approval record — that record gates promotion only — and it runs before the open-questions gate, so a marker in the body does not stop the close `[code: tools/epic_gate.py:933-938, tools/epic_gate.py:956-958]`<br>Canon: finished epics close themselves while the approval stands; a cord-pulled epic is never closed under the human `[canon-only: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What]`
- **Postconditions:** `gh issue close --reason completed` if ANY child (open or closed) has stateReason COMPLETED, else `--reason "not planned"` `[code: tools/epic_gate.py:589-593, tools/epic_gate.py:952-954]`<br>No comment and no board write are made by the gate at close `[code: tools/epic_gate.py:952-954]`<br>Projects' native close→Done automation then sets Status=Done `[canon-only: docs/rfcs/0003-task-state-model.md > Lifecycle]`

#### 21. `debt epic:Ready, none open, no ledger verdict` → `epic:Ready + Reason=Needs-info (held, not closed)`

`T21`

- **Actor:** epic-gate sweep (`_process_epic`, the fail-closed debt exception)
- **Trigger:** A sweep tick on a finished epic whose body carries `YR-ITERATION-KIND: tech-debt`
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_process_epic` (:941-951) — reachable; takes precedence over the plain close branch.
- **Records:** ``YR-DEBT-HOLD` on the debt epic's trail`
- **Preconditions:** `_is_debt_epic(body)` true and `_has_ledger_verdict(comments)` false — the verdict needs the sentinel line AND non-empty `items` and `net-lines` in the SAME comment `[code: tools/epic_gate.py:474-490, tools/epic_gate.py:941]`<br>Canon: the close-time duty (counting the ledger) can never be skipped by a same-tick self-close `[code+canon: skills/factory/references/debt-rounds.md > The close-hold and recovery]`
- **Postconditions:** The hold comment is posted at most once (keyed on the HOLD sentinel already being on record); Reason=Needs-info written iff not already `[code: tools/epic_gate.py:941-951]`<br>The hold body deliberately never spells a field as a bare `key: value` line, so it cannot count as its own missing verdict next tick `[code: tools/epic_gate.py:561-573]`<br>Recovery: post the verdict (next sweep self-closes) or close attended and clear the Reason — the gate never clears it `[code+canon: skills/factory/references/debt-rounds.md > Round-close duties]`

#### 22. `debt epic:Ready, none open, valid ledger verdict on record` → `epic:closed`

`T22`

- **Actor:** epic-gate sweep
- **Trigger:** A sweep tick after the closing session posted the verdict
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_has_ledger_verdict` (:481-490) — reachable.
- **Records:** `a `close` line in sweep.log`
- **Preconditions:** `_has_ledger_verdict` true — one comment carries the sentinel plus non-empty `items` and `net-lines` `[code: tools/epic_gate.py:481-490]`
- **Postconditions:** Falls through to the ordinary close branch, byte-for-byte as a feature epic `[code: tools/epic_gate.py:941-954, tests/test_epic_gate.py:1683]`

#### 23. `epic:Ready + Reason set (any refusal)` → `epic:Ready, Reason cleared`

`T23`

- **Actor:** human (or an attended session on her instruction)
- **Trigger:** The human decides the refusal is resolved
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None — `board_plumbing.set_field(..., opt=None)` performs the clear (:155-166); on the unmerged slice-5 branch an attended clear through that path is walled by `_attended_wall` (:112-153).
- **Preconditions:** Canon: clearing a Reason is the human's explicit resume act; the system never clears one itself `[code+canon: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > Acceptance criteria (EARS)]`<br>Three of the four epic refusal bodies instruct the human to clear the Reason "to resume" `[canon-only: tools/epic_gate.py:509-510, tools/epic_gate.py:518, tools/epic_gate.py:530]`
- **Postconditions:** Mechanically: NOTHING changes for promotion. The epic's own Reason is read only to decide whether a refusal's field write is needed; it is never a promotion gate, and a stale Reason neither blocks nor is cleared `[code: tools/epic_gate.py:981, tools/epic_gate.py:1020, tools/epic_gate.py:1062, tests/test_epic_gate.py:1157-1172]`<br>Clearing it does re-arm the field-write half of the refusal's idempotency, so the next matching refusal re-sets it `[code: tools/epic_gate.py:966, tools/epic_gate.py:981]`

#### 24. `child:Ready (promoted)` → `child:In Progress (claimed) \| child:Backlog+Needs-info (bounced)`

`T24`

- **Actor:** dev-runner (spawned by dispatch off the n8n Ready poll)
- **Trigger:** The build poll finds Status=Ready and issueType not in {Feature, Epic}
- **Enforcement:** **prevented** · **Guard site:** tools/dev-runner.sh DoR gate (:971-990) and the NEEDS_INFO bounce (:1128-1134) — reachable before claim, worktree or any LLM call.
- **Records:** `the runner's bounce comment`, `no epic-lane record`
- **Preconditions:** The n8n filter drops Feature/Epic-typed items so a Ready epic never consumes build dispatch `[code+canon: deploy/n8n-dispatch.json:40, tests/test_ready_query_excludes_epics.py:60-67]`<br>DoR gate: open, on the board, Status==Ready at claim time, Type==Task (REQUIRE_ISSUE_TYPE), non-empty acceptance criteria, resolvable ranked model pair `[code: tools/dev-runner.sh:971-990]`<br>The standalone gates record (`YR-TASK-GATES`) is re-checked at claim ONLY for a Task with no native parent — a child of ANY parent type is exempt, so the epic lane gets no claim-time approval re-check `[code: tools/dev-runner.sh:876-949]`<br>Admission-wall backstop: the manifest is read from MANIFEST_REF (default origin/main) in the local base checkout, falling back to the working tree `[code: tools/dev-runner.sh:706-719]`
- **Postconditions:** On pass: Status=In Progress as the runner's first act, dropping the task off the Ready poll within seconds `[code+canon: tools/dev-runner.sh:1153-1154, deploy/DISPATCH.md > (No double-pickup)]`<br>On a content/manifest/model bounce: Status=Backlog + Reason=Needs-info + a comment — which, being a Reason on an open child, also stops the epic's line `[code: tools/dev-runner.sh:1128-1134, tools/epic_gate.py:89]`<br>A typed-but-wrong Type (Feature/Epic) keeps a polite no-write refusal so the item stays Ready for the epic-gate sweeper `[code: tools/dev-runner.sh:976-990]`

#### 25. `standalone task:Backlog` → `standalone task:Ready`

`T25`

- **Actor:** attended operator session / human, through `tools/promote.sh` (the sibling input gate the epic lane deliberately does not cover)
- **Trigger:** The human's per-task decision — a standalone task has no governing design, so no standing approval exists to run on
- **Enforcement:** *partial* · **Guard site:** tools/promote.sh refuse gate (:56-62) — reachable, writes nothing on refusal. The wall call at :68-69 is reachable only on the unmerged branch and only via promote.sh (a hand `gh`/UI flip bypasses it).
- **Records:** ``YR-PROMOTED` (who/why/date) on the task's trail`
- **Preconditions:** Issue is OPEN, on project #PROJECT_NUMBER's board, and NOT Type=Feature or Type=Epic (both arms refused case-insensitively) `[code: tools/promote.sh:56-62]`<br>UNMERGED slice 5 only: the promote-act wall demands the `YR-TASK-GATES` record (marker as a whole line after rstrip, plus review/fit/who field lines) on the trail before anything is written `[code: tools/promote.sh:64-69, tools/wall.py:360-376]`<br>Canon: check_links green on the technical-rfc, check_task green, the body's design gates ran cold and are recorded (record-before-flip), the task is self-contained and sized `[canon-only: skills/factory/references/closing.md > 1. Promote to Ready]`
- **Postconditions:** The `YR-PROMOTED` record is posted BEFORE the Status flip, by call order in code, not by convention `[code: tools/promote.sh:75-81]`<br>Status=Ready via the board home's single field write; a failed comment refuses the flip entirely `[code: tools/promote.sh:78-81]`

#### 26. `epic on the board` → `refused promote attempt (no write)`

`T26`

- **Actor:** attended operator session running `tools/promote.sh` against an epic
- **Trigger:** An operator tries to use the standalone promote command on a Feature- or Epic-typed issue
- **Enforcement:** **prevented** · **Guard site:** tools/promote.sh (:58-62) — reachable, before any write.
- **Preconditions:** Issue Type lowercases to feature or epic `[code: tools/promote.sh:58-62]`
- **Postconditions:** Exit 3, nothing written — no comment, no field write; the message asserts epic Ready flips are "an attended act (YR-EPIC-APPROVAL via tools/epic_gate.py)" `[code: tools/promote.sh:26, tools/promote.sh:58-62]`

#### 27. `debt:below-threshold` → `debt:raise-open (a tech-debt round is named as due)`

`T27`

- **Actor:** epic-gate sweep (`_sweep_debt_counters`), over the distinct repos holding any Type=Feature issue on the board
- **Trigger:** A sweep tick, after epic processing
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py `_sweep_debt_counters` (:863-915), called from sweep_epics (:1170-1172) — reachable.
- **Records:** ``YR-DEBT-DUE` in the raise issue's body, carrying repo/anchor/count/counted`
- **Preconditions:** The countable set (closed-as-completed, non-debt Feature epics closed after the anchor) reaches `debt_round_every`; the anchor is the debt-kind epic with the latest closedAt, any stateReason `[code: tools/epic_gate.py:728-743, tools/epic_gate.py:880-882]`<br>Threshold precedence env > manifest `debt_round_every` > default 10; any read/parse/validity failure falls back to the default rather than erroring `[code+canon: tools/epic_gate.py:796-819, skills/factory/references/debt-rounds.md > The counter]`<br>No open raise already exists for the (repo, anchor) key `[code: tools/epic_gate.py:822-841, tools/epic_gate.py:884]`<br>The repo set is Feature-scoped on its own authority — Type=Epic items are deliberately out of scope here even though the promotion router matches both `[code: tools/epic_gate.py:690-706]`
- **Postconditions:** Three writes: `gh issue create --type Task`, `project item-add`, and Status=Backlog on the new item `[code: tools/epic_gate.py:901-912]`<br>The counter never sets Ready, never promotes, never closes, never clears a Reason — promotion of the raise stays a human act `[code+canon: tools/epic_gate.py:866-867, skills/factory/references/debt-rounds.md > The raise]`<br>A failure on one repo is isolated as a `debt-error` action and never touches epic processing or another repo `[code: tools/epic_gate.py:913-915]`

#### 28. `debt:raise-open-but-off-board` → `debt:raise-open on board at Backlog`

`T28`

- **Actor:** epic-gate sweep (`_sweep_debt_counters` repair arm)
- **Trigger:** A sweep tick where the (repo, anchor) raise exists open but has no item on project #1
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py (:884-899) — reachable.
- **Records:** `a `debt-repair` line in sweep.log`
- **Preconditions:** `_search_open_due_raise` found the issue and `_pi_node` finds no board item with an id `[code: tools/epic_gate.py:884-889]`
- **Postconditions:** item-add + Status=Backlog; no duplicate raise is created `[code: tools/epic_gate.py:890-898]`

#### 29. `sweep:running` → `sweep aborted mid-tick (partial work)`

`T29`

- **Actor:** epic-gate sweep (unhandled exception)
- **Trigger:** Any `gh` failure inside `_process_epic`, `_sweep_standalone_stranded`, or the board query — `_gh` raises RuntimeError on any non-zero exit
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None — no isolation exists at these sites.
- **Records:** `a Python traceback appended to sweep.log`
- **Preconditions:** No try/except wraps the per-epic loop or the standalone-stranded pass (unlike intake and the debt counter, which isolate per repo) `[code: tools/epic_gate.py:208-213, tools/epic_gate.py:1130-1168]`
- **Postconditions:** The remaining epics, the standalone admission wall and the whole debt counter are skipped for that tick; already-performed writes stand `[code: tools/epic_gate.py:1122-1172]`<br>The traceback lands in sweep.log only; dispatch already answered 202 and nothing else observes it `[code: tools/dispatch.py:235-249]`

#### 30. `sweep:running (hung)` → `every later tick dropped`

`T30`

- **Actor:** dispatch (`flock -n`) — a silent drop, not an error
- **Trigger:** A sweep tick arriving while the lock is held
- **Enforcement:** **prevented** · **Guard site:** tools/dispatch.py run_sweep (:245) — the lock is the guard against concurrent sweeps; nothing guards against a stuck holder.
- **Records:** `nothing — the drop is invisible in sweep.log and to n8n`
- **Preconditions:** `flock -n` cannot acquire SWEEP_LOCK `[code: tools/dispatch.py:245]`
- **Postconditions:** The spawned command exits immediately; the whole lane stalls for as long as the holder lives `[code: tools/dispatch.py:245-249]`<br>`run_sweep` still returns `{ok: True, dispatched: True}` and dispatch answers 202 to n8n regardless `[code: tools/dispatch.py:248-249, tools/dispatch.py:273-278]`

#### 31. `child added under a Ready epic (any time, by anyone)` → `that child in the promotion order`

`T31`

- **Actor:** any actor with sub-issue write access (human or agent)
- **Trigger:** Creating a sub-issue under an already-Ready epic
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. `_process_epic` never compares the child set against anything.
- **Preconditions:** Canon: a child added under a Ready epic must be within the approved design's scope; scope expansion goes back through the design artifacts, never in through a quiet child `[canon-only: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What]`<br>Canon, same spec: mechanized enforcement of that scope-fidelity rule is explicitly OUT OF SCOPE — it is checked at decomposition review only `[canon-only: 04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > Out of scope]`
- **Postconditions:** The child joins `subIssues` order and is promoted mechanically on a later tick with no re-approval — the sweep re-reads `subIssues` fresh every tick and holds no snapshot `[code: tools/epic_gate.py:130-161, tools/epic_gate.py:1011-1012]`

## Where the code and the canon disagree

### [material] Canon calls the epic Ready flip "mechanical"; no machine performs it, and the tool the operator is pointed at cannot.

- **code:** No code in the tree writes Status=Ready on an epic. `tools/epic_gate.py` only ever writes Ready on a CHILD's item (:1071), Backlog on a bounced standalone item (:1165) and on a debt raise (:897, :911), and Reason on an epic (:950, :970, :985, :1021, :1040, :1066). `tools/promote.sh` refuses Feature/Epic outright (:58-62) with the message "epic Ready flips remain an attended act (YR-EPIC-APPROVAL via tools/epic_gate.py), not this command's" — which points at a tool that never writes an epic's Status. The only mechanism left is a raw board write (GitHub UI or `board_plumbing.py set-field --status Ready`).
- **canon:** "Below that standing approval, flipping a governed epic to Ready, promoting its next pre-approved slice, and closing a finished epic are **mechanical**" (closing.md); "the epic-gate promotes pre-approved slices to Ready mechanically" (AGENTS.md). The governing spec is narrower and closer to the code: "Setting a boarded epic's Status to Ready *enacts* that approval — done by the human, or by an agent under it."
- `skills/factory/references/closing.md > 1. Promote to Ready`, `AGENTS.md > How work happens`, `tools/promote.sh:58-62`, `tools/epic_gate.py:1071`, `04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What`

### [material] Three of the four epic refusal records tell the human to clear the epic's Reason "to resume", but the epic's Reason gates nothing.

- **code:** The epic's own Reason value is read at exactly three kinds of site (:981, :1020, :1036, :1062, :949, :966) and only to decide whether a refusal's FIELD WRITE is still needed. It is never consulted as a precondition for promotion: `_process_epic` proceeds through steps 0-3 and writes Status=Ready on the child while the epic still wears a stale Needs-info — pinned by a test. Resumption is caused by fixing the underlying condition, not by clearing the Reason.
- **canon:** `_needs_info_body` ("Add the record, then clear this epic's Reason to resume"), `_not_a_task_body` ("then clear this epic's Reason to resume"), `_not_onboarded_body` ("clear the Reason (an epic) to resume") — all shipped record text. The fourth, `_open_questions_body`, says the opposite and is correct: "the next sweep resumes promotion on its own — no Reason to clear." debt-rounds.md repeats the clear-to-resume framing for the hold.
- `tools/epic_gate.py:509-510`, `tools/epic_gate.py:518`, `tools/epic_gate.py:540`, `tools/epic_gate.py:556-557`, `tests/test_epic_gate.py:1157-1172`, `skills/factory/references/debt-rounds.md > Round-close duties`

### [material] Canon states the admission wall bounces the work to Backlog + Needs-info at the epic-gate sweep for "a child about to be promoted"; the code bounces the EPIC's Reason only and never writes any Status on that path.

- **code:** On the epic-child arm the sweep writes ONLY `Reason=Needs-info` on the EPIC's item plus a comment on the EPIC's trail; the child is never touched and no Status is written anywhere (:1050-1069). Only the standalone arm writes Backlog+Needs-info (:1165-1167).
- **canon:** "the **admission wall** refuses a repo carrying no `.yr/factory.toml` at its base ref … bouncing to `Backlog` + `Reason=Needs-info` naming onboarding, both at the epic-gate sweep (a child about to be promoted) and as `dev-runner.sh`'s own read as the backstop" (pipeline.md); "it bounces the work to `Backlog` + `Reason=Needs-info`" (onboarding.md).
- `tools/epic_gate.py:1050-1069`, `tools/epic_gate.py:1165-1167`, `skills/factory/references/pipeline.md > How the lower pipeline runs`, `skills/factory/references/onboarding.md > The bootstrap invariant`

### [minor] The admission probe reads the repo's DEFAULT branch, not the base ref the docstring and the canon both name.

- **code:** `_repo_has_manifest` calls `gh api repos/<owner>/<name>/contents/.yr/factory.toml` with no `ref` parameter — GitHub serves the repository's default branch. The runner's own backstop instead reads `MANIFEST_REF` (default `origin/main`) from the local base checkout, falling back to the working-tree file.
- **canon:** The function's own docstring: "definitively carries or lacks a `.yr/factory.toml` at its base ref (the default branch)" — equating two things the manifest can separate (`base_ref` is a declared manifest key). onboarding.md: "The pipeline reads a repo's build contract — `.yr/factory.toml` — from the **base ref**."
- `tools/epic_gate.py:762-782`, `tools/dev-runner.sh:706-719`, `skills/factory/references/onboarding.md > The bootstrap invariant`

### [material] UNMERGED slice 5, as built: `wall.py.board_check`'s docstring claims two callers; it has none, and the raw-evasion path it names does not exist.

- **code:** `board_check` (tools/wall.py:325-357) is referenced nowhere in the tree — not by `main()`'s subparsers (:381-399), not by `board_plumbing.py` (which re-implements the check inline at :112-153 with a literal `l.startswith("YR-BOARD-FLIP:")`), not by `classify`. `classify` recognises a board write only when a Bash command literally contains both `board_plumbing.py` and `set-field` (:133-134); a raw `gh project item-edit` is classified as nothing. Its `--jq` joins on ` ` but the parser splits on a single space (:351).
- **canon:** The docstring: "One implementation, two callers: the funnel shells out to this, and the hook's raw-evasion classification resolves the same item." attended-lane.md mandates the board-write wall as fail-closed with condition "`YR-BOARD-FLIP` record on the trail before the flip".
- `tools/wall.py:325-357`, `tools/wall.py:133-134`, `tools/wall.py:381-399`, `tools/board_plumbing.py:112-153`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [material] UNMERGED slice 5, as built: the PreToolUse hook refuses a board write unconditionally — the record condition is never evaluated on that path.

- **code:** `decide()` looks the act up in RULES and denies; only `crossing-file` has an in-flight satisfiable branch (:253-258). For `board-write` no trail is read and no `pass` event is possible, so an attended epic Ready flip through `board_plumbing.py set-field` is denied even with `YR-BOARD-FLIP` already on the trail — and the Stop close-check then treats that refusal as an unresolved trace (:284-292).
- **canon:** The walled-act map gives board Status/Reason writes a CONDITION (the record on the trail before the flip), not a categorical stance; categorical is reserved for hand-merge, main pushes and the write-path class.
- `tools/wall.py:244-268`, `tools/wall.py:284-292`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [minor] `board_plumbing.set_field`'s docstring gives the wrong reason for the machinery exemption.

- **code:** `set_field` docstring: "runner/epic-gate callers are untouched by construction (no CLAUDECODE in their environments)". The actual mechanism is an explicit declaration — `os.environ.setdefault("YR_MACHINERY", "1")` at tools/epic_gate.py:72 and `export YR_MACHINERY=1` at tools/dev-runner.sh:46 — and `_attended_wall`'s own docstring says in full why the CLAUDECODE-sniff form was wrong (it refused the runner's own integration tests under pytest inside an attended session).
- **canon:** attended-lane.md: "runner and epic-gate callers exempt — their records are their own". records.toml's YR-BOARD-FLIP note says the same.
- `tools/board_plumbing.py:155-160`, `tools/board_plumbing.py:112-126`, `tools/epic_gate.py:72`, `tools/dev-runner.sh:46`

### [minor] The record registry's line citations for this lane are stale against the tree.

- **code:** `_has_valid_approval` is at tools/epic_gate.py:429 (registry says :420); `_promoted_body` at :494 (registry :491); `_open_question_lines` at :450 (registry :452); `_gate_touching_declaration` at :460 (registry :462); `_stranded_body` at :300 (registry :297); `_is_debt_epic` at :474 (registry :472); `_has_ledger_verdict` at :481-490 (registry :478-483); `_due_body` at :849 (registry :847); the HOLD read at :943 (registry :938); the `_has_marker` dedup sites are at :965/:980/:1016/:1035/:1061 (registry "~:1011"). Slice 5 added 5 lines at :66-70 but the drift predates it.
- **canon:** records.toml's stated contract: "The tree is the territory — every row cites its emitter and reader sites; the agreement tests in tests/test_records.py pin the inline literals that predate this file to their rows." The agreement tests pin literals, not line numbers.
- `records.toml:55-63`, `records.toml:85-92`, `records.toml:105-112`, `records.toml:159-166`, `tools/epic_gate.py:429`, `tools/epic_gate.py:494`

### [minor] The self-close is stated as conditional on the standing approval in the governing spec's bullet heading, and the code states its independence outright.

- **code:** "the no-open-child branch … is mutually exclusive with promoting/waiting below, and independent of the standing-approval record (that record only gates promotion)" — and the branch runs at :939-954, before the open-questions gate (:956-958) and before the approval check (:975-988). A Ready epic with no approval record at all, or with an un-dispositioned open question in its body, still self-closes; a test pins the latter.
- **canon:** "**Finished epics close themselves — while the approval stands.**" The bullet's own elaboration then requires only "has had children, is still Ready, and has no open child left", so the canon is self-ambiguous; closing.md's blanket framing is that closing a finished epic is mechanical, "fail-closed back to the human on any doubt".
- `tools/epic_gate.py:933-954`, `tests/test_epic_gate.py:1468`, `04 projects/factory/iterations/7-epic-gates/01-epic-gates.md > What`, `skills/factory/references/closing.md > 1. Promote to Ready`

### [minor] records.toml's reader lists for this lane's two walled records describe slice 5 as "future … not at tip", which is false on this branch and true on main.

- **code:** On this branch `tools/promote.sh:68` DOES call `wall.py promote-check` (which reads YR-TASK-GATES through the registry, tools/wall.py:360-376), and `tools/board_plumbing.py:145` DOES read YR-BOARD-FLIP — but inline, with a hand-spelled literal, not through the registry, so the registry's own "one home" claim holds only for the promote arm.
- **canon:** records.toml: YR-TASK-GATES readers include "tools/promote.sh promote-act wall (slice 5 — future reader, not at tip)"; YR-BOARD-FLIP readers include "tools/board_plumbing.py wall (slice 5 — future reader, not at tip)".
- `records.toml:65-73`, `records.toml:345-353`, `tools/promote.sh:64-69`, `tools/board_plumbing.py:140-147`

## Gaps

- **The enacting act of the whole lane — flipping an epic to Ready — has no guard, no tool, and no machine-checked record. `promote.sh` refuses it; `epic_gate.py` never performs it; the only path is a raw board write (GitHub UI or `board_plumbing.py set-field --status Ready`), and only the latter is even visible to the unmerged slice-5 wall.** **← needs an owner ruling**<br>This is the single act that converts a design-active standing approval into autonomous building. Everything downstream (promotion, dispatch, claim, PR, and — on an armed repo — merge) runs off it, and it is the one step in the chain that no machine disposes.
- **The standing-approval record is never checked for provenance or for the truth of what it names: `_has_valid_approval` accepts any comment on the epic trail from any account, `who:` is self-asserted, and nothing resolves whether the `design:` doc is actually `status: active` in the vault. Field extraction also scans the whole comment body, so the three values need not sit near the marker.** **← needs an owner ruling**<br>The canon's whole gate model is "the human's authority sits at design-active, and the epic-gate trusts the record naming it". Presence-of-a-string is the only thing between an inactive/nonexistent design and mechanical promotion. The unmerged slice-5 wall does resolve a design's `status: active` from the vault — but only for the crossing-file act, never for the approval record.
- **Stranded-claim detection is unreachable for a child of any epic that is blocked earlier in the algorithm. Steps 0 (open questions) and 1 (no approval) return unconditionally, before the busy/stranded loop; and `_sweep_standalone_stranded` skips every item that has a `parent`. Same hole for a cord-pulled epic, whose children are never visited at all.**<br>The exact scenario the stranded check exists for — a hard runner death leaving In Progress with no Reason forever — becomes invisible precisely when the epic is also in trouble, which is when it is most likely. Neither pass owns these children.
- **An OPEN child whose Status is Done (the shape a reopened issue leaves — reopening does not reset the Projects field) is neither busy nor skipped: `Done` is absent from BUSY_STATUS, so the loop falls through, `open_children[0]` is that child, and the sweep writes Status=Ready on it and posts a second `YR-AUTO-PROMOTED`. No test covers a Done-status open child.**<br>A reopened slice is silently re-promoted and re-dispatched, with a duplicate promotion record on its trail and no signal that it is a repeat.
- **The epic's mechanical self-close emits no trail record at all — only the native `gh issue close --reason`. The lane's close records (`records.toml [lanes] close` = YR-SHIP-WALK, YR-ROUND-RECORD) are neither emitted by the closer nor checked before the close, and `tools/check_trail.py` is advisory-tier, wired into no check_cmd, CI or manifest.** **← needs an owner ruling**<br>The close is the moment the ship-walk and the round record are due (attended-lane.md steps 10-11, closing.md's freeze checklist), and it is also the moment the epic stops being a surface anyone looks at. Nothing connects the two.
- **The epic lane has no claim-time backstop for its own gate. The runner re-checks the standalone lane's `YR-TASK-GATES` at claim, but exempts any issue carrying a native parent of any type — so a child flipped Ready by hand (bypassing the sweep, and therefore the approval check) is built with no approval check anywhere in the system.** **← needs an owner ruling**<br>Asymmetry with the sibling lane: the standalone lane is checked twice (promote wall + claim), the epic lane once, at a step a human can trivially skip. The 2026-07-29 promotion-gates review recorded exactly this shape live — eight website children flipped Ready by hand carrying no promotion record.
- **Two incompatible definitions of "registered/onboarded" coexist inside one sweep: intake enumerates $YR_WORKSPACE subdirectories whose WORKING TREE holds `.yr/factory.toml` with a parseable origin remote, while the admission wall probes GitHub's contents API on the DEFAULT branch, and the runner's backstop reads MANIFEST_REF from the local base checkout.**<br>A repo can be intaken but refused promotion (manifest unpushed), or promoted but never intaken (not cloned on the sweep host). Neither divergence is detected or reported.
- **The postcondition that makes intake useful — the board's item-added workflow setting Status=Backlog — is asserted only in the sweep's own docstring. Nothing in the repo configures it, verifies it, or records its absence, and intake deliberately writes no Status itself.**<br>If that board workflow is off or scoped wrong, every intaken issue sits with no Status: invisible to the Ready poll, invisible to the sweep, and indistinguishable from a healthy Backlog item on the board.
- **No error isolation in the per-epic loop or the standalone-stranded pass. `_gh` raises on any non-zero exit; one failing epic (deleted repo, permissions, transient 5xx on the EPIC_QUERY) aborts the whole tick, skipping every later epic, the standalone admission wall and the entire debt counter. Intake and the debt counter DO isolate per repo. `main()` returns 0 regardless.**<br>One sick epic silently stops the whole board's promotion, and the exit code carries no signal — the only trace is a traceback in a shared append-only log nothing watches.
- **The lane's liveness is unobservable. `run_sweep` returns `{ok: True}` whether or not `flock -n` acquired, so a hung sweep silently drops every subsequent tick forever with n8n seeing 202 each time; the shipped n8n workflow is `"active": false` by design and its real state lives only in n8n; and there is no health record anywhere on the board or the trail.**<br>A dead or wedged sweep looks exactly like a board with nothing to do. The failure mode is silence, in a lane whose whole purpose is to remove the human from the loop.
- **The sweeper runs from the deploy checkout's mutable working tree (`EPIC_SWEEPER = SELF.parent / "epic_gate.py"`), not from a pinned git ref.**<br>The factory's stated invariant is "builds from git refs, not a mutable working tree" — a stale/dirty/live-dev checkout cannot affect a build. The promotion engine that decides what gets built is exempt from that invariant, by construction and without a written carve-out.
- **`YR_MACHINERY` is an inheritable, unauthenticated environment declaration that exempts a process from the (unmerged) attended board-write wall — any process that exports it is machinery, including an attended session that types it.**<br>The exemption is the seam between the two lanes' board-write rules. Its integrity rests entirely on nobody setting the variable, and it is not carried in dispatch's spawn allowlist either, so the mechanism is invisible where the environment is otherwise itemized.
- **`records.toml [lanes] epic = ["YR-EPIC-APPROVAL"]` — the detector's epic lane mandates one record only. Neither the epic Ready flip's `YR-BOARD-FLIP` nor the close lane's records are checked for an epic, and the detector never runs automatically anywhere.**<br>The lane's own reified duties (steps 9-11) exist in the registry but are outside the detector's epic scope, so even the advisory instrument would not find them missing.
- **Nothing from iteration 30 reaches any session: the plugin ships version 0.10.0 and was never bumped, so `attended-lane.md` — the canon that names this lane's records, its walled acts and its human checkpoints — is on main but not delivered. Slice 5 (the walls) is unmerged and failed independent review at 0 of 5 acceptance criteria.** **← needs an owner ruling**<br>Every it-30 statement about this lane (record-before-flip as a typed record, the walled board write, the promote-act wall, the close check) is currently prose that no session is handed and no machine enforces. Read this whole lane's it-30 column as intent, not behaviour.
- **Pagination is unbounded everywhere in the lane: BOARD_QUERY items `first: 100` (with a TODO inherited from deploy/ready-query.graphql), EPIC_QUERY's `comments(first: 100)` and `subIssues(first: 100)`, `projectItems(first: 20)`, and the raise search `first: 20`.**<br>Past 100 board items, epics silently vanish from the sweep; past 100 comments, a valid approval or ledger verdict silently reads as absent and the gate refuses; past 100 sub-issues, promotion order is silently truncated. Every one of these fails toward a wrong answer with no signal.
- **`_approval_failure_reason` names missing fields from `candidates[0]` only, so with more than one marker-carrying comment the refusal can name a field that is present in the comment the operator is actually looking at.**<br>The refusal record is the whole recovery surface under the legibility invariant ("states the observed fact and the rule that judged it"); naming the wrong field sends the human to fix the wrong comment.
- **Scope fidelity of children added under an already-Ready epic is unenforced — the governing spec declares mechanized enforcement explicitly out of scope, and the sweep re-reads `subIssues` fresh every tick with no snapshot to diff against.**<br>The standing approval covers the decomposition the human activated. A slice added afterwards inherits that approval automatically. This is a known, ruled-acceptable hole, recorded here so the next version of the factory does not rediscover it as a surprise.
- **The close-vs-grow race is unguarded and explicitly accepted: between the last child closing and the next child being added, the self-close fires on a still-growing decomposition.**<br>Also ruled acceptable in the spec ("reopen is cheap, and a sub-issue added under an already-boarded epic re-boards natively") — but note it composes badly with the Done-status re-promotion hole above: a reopened epic's reopened child is not just re-boarded, it is re-promoted.
- **The stranded-claim scan stops at the first busy child: the loop raises-then-returns, so a stranded child sitting later in sub-issue order behind an earlier busy child is never examined on that tick (and never at all while the earlier child stays busy).**<br>In practice one slice is in flight per epic so this is usually moot; it stops being moot exactly when a human has hand-promoted a second child, which the spec explicitly permits.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **gaps[9]: one failing epic aborts the whole tick "and the exit code carries no signal — `main()` returns 0 regardless."**<br>`main()` has no try/except: `actions = sweep_epics(...)` at :1179 is followed by the print loop and `return 0` only at :1217, and the module exits via `sys.exit(main())` at :1221. On the exact crash path the gap describes, `return 0` is never reached — the interpreter dies with a traceback and a NON-zero exit. The gap's real support is that nothing reads the code at all (`_spawn_detached` fires and forgets, tools/dispatch.py:194-204), not that the code is 0. `tools/epic_gate.py:1176-1221; tools/dispatch.py:194-204`
- **gaps[8]: if the board's item-added workflow is off, "every intaken issue sits with no Status: invisible to the Ready poll, invisible to the sweep."**<br>Half of it is contradicted for the case that matters most in this lane. An epic CHILD's Status is not read off the board's Ready filter — it is read from that child's own `projectItems` (tools/epic_gate.py:997-998 via `_pi_node` :596-600). An unset Status yields `""` (`_fv_name` :226-228), and `""` is not in `BUSY_STATUS` (:88), so a Status-less child is NOT busy, is not skipped, and — if it is first in `subIssues` order and a Task — is promoted outright at :1071. So a missing item-added workflow leaves epic children fully visible AND promotable by the sweep; only board-level Ready items (the :1136 filter) go invisible. `tools/epic_gate.py:88, 596-600, 997-1009, 1071, 1136`
- **T1 precondition 4: "Canon: GitHub's one-per-project auto-add cannot serve a board spanning every registered repo, so intake closes the gap" — sourced `canon`, cited to onboarding.md > 4. Register on the board.**<br>That section says only: "Ensure the shared board … can see the repo, and that new Issues filed in the repo can be added to it via the board's auto-add or manual intake rules." It states no one-per-project limitation, no gap, and does not mention `_sweep_intake`. The only place that assertion exists is tools/epic_gate.py's own module docstring (:41-49) — code, not canon. `skills/factory/references/onboarding.md:90-94; tools/epic_gate.py:41-49`
- **T2 postcondition: "Status=Backlog on the new item" — sourced `canon`, cited to tools/epic_gate.py:666-668.**<br>The citation is `_sweep_intake`'s own docstring asserting what an external GitHub workflow does. Nothing in the repo configures, queries, or tests that workflow, so the citation cannot establish the postcondition. (The excavation's own gaps[8] concedes exactly this, but the transition table reads as if canon backs it.) `tools/epic_gate.py:665-669, 683-684`
- **T5 postcondition: "dispatch answers 202 immediately, before the sweep does anything" — cited to tools/dispatch.py:235-249, 180-185.**<br>Neither range contains the 202. `run_sweep` (:235-249) returns a dict; `_spawn_env` (:179-183) builds an environment. The 202 is written at `self._send(202 if res["ok"] else 400, res)` — tools/dispatch.py:277. The substance is right; the citation does not carry it. `tools/dispatch.py:277`
- **disagreements[2]: "Three of the four epic refusal bodies instruct the human to clear the Reason 'to resume'."**<br>`_process_epic` emits FIVE refusal bodies, and FOUR carry the instruction — the excavation omits `_gate_touching_body`, whose closing sentence is "Land the change by hand, then clear this epic's Reason to resume" (tools/epic_gate.py:530). The finding is real and understated, but the enumeration is wrong against the tree, and the omitted one is the newest of the family. `tools/epic_gate.py:503-541 (esp. :509-510, :518, :530, :540) and :556-557`
- **T3 records: "`YR-BOARD-FLIP` (canon, it-30; no reader at tip)".**<br>The excavation defines "tip" as the branch it read (HEAD dc67cbb = main + slice 5), and at that tip `tools/board_plumbing.py:145` DOES read the marker (`any(l.startswith("YR-BOARD-FLIP:") …)`) on every attended `set_field` call. Its own disagreements[10] says so. A reader of the transition table alone concludes the record is inert on this branch when it is the wall's only condition. `tools/board_plumbing.py:140-152`
- **T30 enforcement: "prevented" for "sweep:running (hung) → every later tick dropped".**<br>Nothing is prevented in the transition being described — the drop is what happens, silently and forever, and the row's own guard_site admits "nothing guards against a stuck holder". The enforcement field is scoring a different proposition (that concurrent sweeps are prevented), which reads as if the failure mode were guarded. `tools/dispatch.py:245-249`

## Found by the verifier, missing from the excavation

- On the branch the excavation read, `tools/promote.sh`'s OWN Status flip is walled and would fail after the record is posted. `_board set-field` (promote.sh:22, :80) runs `board_plumbing.py set-field` as a subprocess → `set_field` → `_attended_wall`. In an attended Claude session CLAUDECODE is set and YR_MACHINERY is not, so the wall demands a `YR-BOARD-FLIP` record on the trail — a record promote.sh never posts (it posts `YR-PROMOTED`, :75). The run therefore posts the promotion record and dies at :81 ("promotion record posted, but the Status=Ready write failed"). T25 reports the flip as a clean postcondition and never mentions the interaction. The suite cannot catch it: tests/conftest.py:21-33 declares every test machinery. `tools/promote.sh:22, 75, 80-81; tools/board_plumbing.py:126-152, 155-166; tests/conftest.py:21-33`
- A second, unnamed bypass of the (unmerged) board-write wall: `_attended_wall` returns immediately when CLAUDECODE is absent. gaps[12] names only the `YR_MACHINERY` declaration as the seam, but the wall is opt-IN on session provenance — a plain-shell `python3 tools/board_plumbing.py set-field --status Ready` by a human or any non-Claude agent is never walled at all, no declaration required. `tools/board_plumbing.py:126-129`
- The (unmerged) promote wall grades `YR-TASK-GATES` more loosely than the runner's claim-time gate, so the two graders can disagree. `wall.py promote_check` flattens ALL comment bodies into one line list and accepts each field with `l.lstrip().startswith(f"{f}:")` — fields may sit in different comments and may be indented — and it applies no placeholder rejection. The runner requires marker + all three fields in the SAME comment and refuses the placeholder set for `fit:`. A record that clears the promote wall can still bounce at claim. `tools/wall.py:360-376; tools/dev-runner.sh:892, 895-918, 941-948`
- The bogus "clear the Reason to resume" rule is not confined to the shipped comment strings — it is stated as canon in the delivered skill reference: "the epic-gate reads the declaration off the CHILD's own body only … and refuses to promote that child — `Reason=Blocked` on the epic, nothing promoted — until the declaration line is resolved by hand **and the epic's Reason is cleared**." disagreements[2] cites only code bodies plus debt-rounds.md, so it understates where the false rule lives. `skills/factory/references/authoring.md:117-125`
- The pagination gap misses one truncating read: intake's per-repo issue list is capped at `--limit 500`. A registered repo with more than 500 open issues silently intakes only a prefix, with no signal — the same fail-toward-a-wrong-answer shape the gap catalogues for the GraphQL `first:` bounds. `tools/epic_gate.py:658-662`

---

SCOPE AND PROVENANCE. Read at /opt/yellow-robots/factory/.claude/worktrees/task-420-walls, HEAD dc67cbb = origin/main + the unmerged slice-5 "walls" branch, with tools/wall.py additionally carrying uncommitted local edits (90 insertions). Everything I attribute to slice 5 — tools/wall.py in full, the PreToolUse/Stop registrations in hooks/hooks.json, `_attended_wall` + its call in tools/board_plumbing.py:112-166, the promote-check call at tools/promote.sh:64-69, `os.environ.setdefault("YR_MACHINERY","1")` at tools/epic_gate.py:72, and `export YR_MACHINERY=1` at tools/dev-runner.sh:46 — is UNMERGED and failed independent review at 0/5 criteria: treat it as "as built, rejected", never as factory behaviour. Slices 1-4 (records.toml, tools/check_trail.py, skills/factory/references/attended-lane.md, tools/compile_slice.py + hooks/deliver.sh) are on main but .claude-plugin/plugin.json still reads 0.10.0, so none of that canon is delivered to any session.  WHAT ACTUALLY RUNS TODAY IN THIS LANE. Exactly one program: tools/epic_gate.py, spawned detached under `flock -n ~/.cache/dev-runner/epic-sweep.lock` by tools/dispatch.py's POST /sweep, on the n8n epic-sweep workflow's cadence. Per tick it runs four passes in this order — board intake (:1127), the standalone stranded-claim pass (:1128), the Ready loop routing Feature/Epic items to `_process_epic` and everything else to the admission wall (:1130-1168), and the per-repo debt counter (:1170). `_process_epic`'s decision order is load-bearing and worth reading as the lane's spine: childless → do nothing; no open child → close or debt-hold; open-question marker → refuse; no approval → refuse; any busy child → wait (raising a stranded claim on the way); first open child not a Task → refuse; that child gate-touching → refuse; child not on board → silent; repo unprobeable → skip; repo not onboarded → refuse; else promote.  THE THREE MOST LOAD-BEARING FACTS. (1) The epic's own Reason is not a gate — it is signage plus a per-refusal write-idempotency key. Three of the four refusal records say otherwise. (2) The epic Ready flip is the lane's entry act and nothing performs, guards or records it. (3) The approval check is presence-and-grammar only, by design ("walls check existence and grammar only"), so the authority chain from design-active to autonomous build is carried by a string on a comment that anyone can post and nothing corroborates.  ENFORCEMENT SHAPE. Every refusal inside `_process_epic` is genuinely "prevented" — each sits above the Status=Ready write at :1071 on the only path the sweep takes. The refusals are also uniformly keyed on two independent conditions (its own marker's presence for the comment, the current Reason value for the field write), so a stale Reason from a different refusal never silences a new one. What is NOT prevented is everything at the lane's edges: the Ready flip in, the Reason clear, the close out, the children added mid-flight, and the liveness of the sweep itself.  I did not read the whole 3,425-line tests/test_epic_gate.py; I read the test index and the specific tests I cite. I read the vault read-only (no writes, no obsidian CLI) — the governing product-spec 7-epic-gates/01-epic-gates.md and the 2026-07-29 adversarial re-verification 23-open-questions-gate/02-promotion-gates-review.md were the two most useful, and note that the review's N4 finding (promote.sh blind to Type=Epic) has since been fixed at tools/promote.sh:58-62.
