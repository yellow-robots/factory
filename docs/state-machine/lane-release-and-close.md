<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The release and round-close lane

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `epic-open-with-open-children` | An iteration's epic (Type=Feature or Type=Epic) is live: at least one sub-issue is still OPEN, so the round is not finished. | GitHub issue state + native sub-issue links; Status on the shared 'Yellow Robots — Dev' Projects field (org project #1), read per-issue via projectItems GraphQL | `tools/epic_gate.py:939` |
| `epic-finished-unclosed` | The epic has children and none is OPEN — the round's build work is done, the epic is still open. The transient state the sweep disposes of on its next tick. | GitHub issue state (open) + native subIssues connection | `tools/epic_gate.py:939-940` |
| `epic-closed-completed / epic-closed-not-planned` | The epic is natively closed; reason is 'completed' if any child closed as completed, 'not planned' only if every child closed not-planned. | GitHub issue closed state + stateReason | `tools/epic_gate.py:589-593` |
| `epic-done` | The board reflects the close: Status=Done, set by Projects' built-in close→Done automation, never by the factory. | Status single-select on org project #1 | `docs/rfcs/0003-task-state-model.md:41` |
| `debt-epic-held` | A debt epic ran out of open children but carries no valid ledger verdict: the epic-gate refuses to self-close it and parks it for an attended close. | A YR-DEBT-HOLD comment on the epic trail + Reason=Needs-info on the board | `tools/epic_gate.py:941-951` |
| `doc-draft / doc-active / doc-superseded` | An iteration doc's lifecycle. At close, any doc still at draft is set active and thereby frozen: the body is never edited to match later reality (a functional defect is the one repairable exception). | `status` key in the vault doc's YAML frontmatter | `skills/factory/references/closing.md > 3. Doc-side freeze` |
| `crossed_to-stamped` | A doc that crossed the airlock carries its epic pointer. Stamped AT the crossing, not at close; the close only verifies and back-fills a missing one. | `crossed_to` key in vault frontmatter | `skills/factory/references/closing.md > 3. Doc-side freeze` |
| `ship-walk-pending / ship-walk-recorded` | The close's grounding walk (living reference updated in place, replaced research superseded, stamps verified, pilot observables recorded) is owed or has left its trace. | Canon-designated: a `YR-SHIP-WALK:` comment on the epic (or standalone task) trail, fields who/scope. No emitter exists in code; today the only durable evidence is the prose walk entry appended to the living reference. | `records.toml:355-363` |
| `round-record-emitted` | The close's observable counts — refusals issued, records demanded, detector findings, escalations — posted for the human to price against attended attention. | Canon-designated: a `YR-ROUND-RECORD:` comment on the epic (or standalone task) trail | `records.toml:365-373` |
| `escalation-recorded` | The severity valve fired: the agent routed a one-way-door decision to the human, and the escalation is counted in the round record. | Canon-designated: a `YR-ESCALATION:` comment (issue-trail), fields act/why | `records.toml:375-383` |
| `living-reference-current / -stale` | The component's map of the present either was walked at this close or was not; its own freshness marker is a single `Last walked:` line. | `04 projects/factory/architecture/factory-map.md` § 5 Maintenance, one prose line inside the section | `04 projects/factory/architecture/factory-map.md > 5. Maintenance` |
| `content-merged-unreleased` | Skill content (SKILL.md, references/, templates/) is on origin/main while `.claude-plugin/plugin.json` still carries the previous version string — merged, and reaching no session. This is the tree's state TODAY for all of iteration 30 slices 1-4. | git ref origin/main + the `version` string in `.claude-plugin/plugin.json` | `.claude-plugin/plugin.json:5` |
| `release-cut-on-a-branch` | A release exists as a two-file change on a task branch: the bumped version plus the single canonical pin. 0.11.0 sits here today, unmerged, on a branch stacked on the rejected walls branch. | git branch origin/task/421-release; `.claude-plugin/plugin.json` + `tests/test_plugin_packaging.py` on it | `tests/test_plugin_packaging.py:26-28` |
| `released-on-main` | The bumped version is merged to the factory repo's default branch. Because the marketplace entry pins no ref, main IS the publication channel — nothing else is published. | `version` in `.claude-plugin/plugin.json` at origin/main | `04 projects/factory/architecture/factory-map.md > 2. Mechanism map` |
| `installed-on-a-host` | A consumer machine holds an extracted copy of the plugin at a version-keyed path, plus a registry row naming the version. The install path is keyed by the VERSION STRING — this is what makes a released version visible. | ~/.claude/plugins/cache/yellow-robots/factory/<version>/ (a plain extracted tree, no .git) and a row in ~/.claude/plugins/installed_plugins.json (scope, installPath, version, installedAt, lastUpdated, gitCommitSha) | `~/.claude/plugins/installed_plugins.json` |
| `loaded-in-a-session` | The running session actually reads the installed content. Bundled reference files do not hot-reload: a version already installed reaches a session only at `/reload-plugins` or a fresh session. | In-session harness state; the per-session marker files under <installPath>/.in_use/<pid> | `skills/factory/references/closing.md > Skill-release block` |
| `release-scan-green / -red` | The four-arm shape check on the skill: no dangling router row, no orphan reference, SKILL.md < 500 lines, description agreement, plus the consumer scan. It is a pytest run — it produces no durable artifact of its own. | Nowhere durable. Computed by the suite at check-gate/CI time; the only trace is a green CI check on the release PR. | `skills/factory/references/closing.md > Skill-release block` |
| `debt-countable-below-threshold` | Fewer closed-as-completed Feature epics have accumulated since the anchor than the repo's `debt_round_every` threshold, so no round is due. | Nowhere durable — recomputed each sweep from GitHub's search index; emitted only as a `debt-count` action in the sweep's return value | `tools/epic_gate.py:880-882` |
| `debt-due-raised` | A tech-debt round is owed: an open Type=Task, Backlog-only issue keyed on (repo, anchor) names the need without scoping the round. | A GitHub issue whose body carries the YR-DEBT-DUE record (repo/anchor/count/counted), plus a board item at Status=Backlog | `tools/epic_gate.py:849-860` |
| `debt-epic-open` | The round is running: an epic whose body carries the kind sentinel, making it a debt (not feature) epic — excluded from the countable set and subject to the close-hold. | The literal line `YR-ITERATION-KIND: tech-debt` on its own whole stripped line in the epic body | `tools/epic_gate.py:474-478` |
| `debt-ledger-verdict-on-record` | A comment on the debt epic carries the YR-DEBT-LEDGER marker line AND non-empty `items` and `net-lines` in that same comment — the machine-checked pair. | A comment on the debt epic's issue trail | `tools/epic_gate.py:481-491` |
| `prune-net-lines-recorded` | A prune PR declares its own items/net-lines so the close can aggregate rather than hand-sum diffs. | A YR-DEBT-NET-LINES block in the prune PR's own body | `skills/factory/references/debt-rounds.md > Record grammars` |
| `wall-session-has-unresolved-refusals` | (Unmerged, slice 5) The session was refused on a walled act and no later 'pass' event for that act followed — the state the Stop close-check reads. | JSONL rows in $YR_WALL_STATE/counts.jsonl (default ~/.cache/yr-attended/counts.jsonl), one object per event | `tools/wall.py:91-107` |
| `close-override-recorded` | (Unmerged, slice 5) A second consecutive close with traces unchanged proceeded loud; the override is written to the counts the round record reads. | A `close-override` row in $YR_WALL_STATE/counts.jsonl | `tools/wall.py:288-291` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `epic-finished-unclosed` → `epic-closed-completed / epic-closed-not-planned` | epic-gate (tools/epic_gate.py, the standing-approval sweep running on the host) | **prevented** | tools/epic_gate.py::_process_epic:939-954 — reachable on the only path the sweep takes to a finished epic |
| 2 | `epic-closed-completed` → `epic-done` | native GitHub Projects automation (the built-in close→Done workflow on org project #1) | ⚠️ **unenforced** | none in this repo — the workflow lives in GitHub Projects configuration |
| 3 | `doc-draft` → `doc-active (frozen)` | attended closing session (a human-directed agent) | ⚠️ **unenforced** | prose only in closing.md. tools/wall.py's `lifecycle-stamp` act (unmerged) would intercept ONLY the mcp__obsidian__vault_patch frontmatter path (tools/wall.py:154-160); a `vault_write`, a Bash `sed -i` or a filesystem write are not classified as a lifecycle stamp at all |
| 4 | `epic-closed-completed` → `crossed_to-stamped (verified)` | attended closing session | ⚠️ **unenforced** | none — closing.md prose; check_links gates spine crossing-links on a draft, not close-time stamps |
| 5 | `epic-closed-completed` → `supersession pairs verified` | attended closing session | detected | tools/check_supersession.py exists and is deterministic (advisory tier per gates.md); nothing invokes it at close |
| 6 | `ship-walk-pending` → `ship-walk-recorded` | the architect where the role is earned on the component; the closing session otherwise | detected | tools/check_trail.py --lane close would find its absence (records.toml:391 puts YR-SHIP-WALK in the close lane) — but check_trail has NO caller anywhere in the tree and is advisory-tier by declaration (tools/check_trail.py:16) |
| 7 | `epic-finished-unclosed` → `round-record-emitted` | the closing session (attended) | detected | tools/check_trail.py close lane (records.toml:391) — no caller; the counts themselves come only from `wall.py counts` (tools/wall.py:391-399), which is unmerged, and even it emits only kinds refusal/pass/close-block/close-override — never 'records-demanded' or 'detector-findings' |
| 8 | `epic-open-with-open-children` → `escalation-recorded` | the agent, at a decision surface, when implications are severe (a one-way door) | ⚠️ **unenforced** | none — YR-ESCALATION appears in NO lane in records.toml:387-391, so even check_trail never asks for it |
| 9 | `epic-closed-completed` → `crossover judged` | the closing session with the human | ⚠️ **unenforced** | none |
| 10 | `living-reference-stale` → `living-reference-current` | the architect (ship-walk) or the closing session | ⚠️ **unenforced** | none — the maintenance contract states enforcement is procedural, 'a named step of the operation that owns the moment — not automated' |
| 11 | `content-merged-unreleased` → `release-cut-on-a-branch` | dev-runner (the release is normally filed as a Task and built by the pipeline) OR an attended session (the 0.9.15 and 0.10.0 cuts were attended) | **prevented** | tests/test_plugin_version_pin_canonical.py::test_canonical_pin_tracks_plugin_json_current_version and tests/test_plugin_packaging.py::test_plugin_version_is_current — both ride check_cmd (`pytest tests/ -q`) and the CI 'Tests' step, so a bump without the pin fails the gate |
| 12 | `release-cut-on-a-branch` → `release-scan-green` | the releasing session (canon) — in practice the pytest suite executes four of the five arms | *partial* | tests/test_skill_factory_router.py + tests/test_check_model_refs.py::test_real_tree_scan_is_green (tests/test_check_model_refs.py:202-207), all riding check_cmd and CI 'Tests' |
| 13 | `release-cut-on-a-branch` → `released-on-main` | the merge evaluator on an armed repo (auto_merge = true in .yr/factory.toml) OR the human's click on an attended release PR | *partial* | tools/merge_shadow.py (the deterministic evaluator) for the armed path; nothing for the attended path |
| 14 | `released-on-main` → `installed-on-a-host` | the Claude Code plugin installer / marketplace auto-update on each consumer host — no factory actor is involved | ⚠️ **unenforced** | none — nothing in the factory repo reads, verifies or gates on any host's install state |
| 15 | `installed-on-a-host` → `loaded-in-a-session` | the human or the session itself | ⚠️ **unenforced** | none |
| 16 | `released-on-main` → `consumers repointed / old home demoted` | attended session | ⚠️ **unenforced** | tools/check_model_refs.py catches ONE historical case afterwards (the `01-conventions` literal) — it cannot express any other demotion |
| 17 | `any attended session` → `release edit refused` | tools/wall.py PreToolUse hook (UNMERGED — slice 5, failed independent review at 0 of 5 acceptance criteria; tools/wall.py additionally carries uncommitted local edits) | *partial* | tools/wall.py::classify:151-152 → decide:244-268, registered as a PreToolUse hook on Bash\|Write\|Edit\|mcp__obsidian__vault_patch in hooks/hooks.json. NOT reachable today: the registration exists only on the unmerged branch (origin/main's hooks/hooks.json carries SessionStart alone), and the installed 0.10.0 plugin ships no hooks/ directory at all |
| 18 | `wall-session-has-unresolved-refusals` → `close-override-recorded` | tools/wall.py Stop hook (UNMERGED) | *partial* | tools/wall.py::close_check:273-299 via the Stop registration in hooks/hooks.json — unmerged and unreleased, so unreachable in any session today |
| 19 | `debt-countable-below-threshold` → `debt-due-raised` | epic-gate (the per-repo debt counter sweep) | **prevented** | tools/epic_gate.py::_sweep_debt_counters:863-913 — reachable on every sweep tick |
| 20 | `debt-due-raised` → `debt-epic-open` | human (promote) + attended session (round-spec + census authoring) | *partial* | tools/epic_gate.py::_is_debt_epic:474-478 reads the kind line; the walls themselves (census, by-name scope, birth citation, prune review bar, guards) are prose only |
| 21 | `debt-epic-open` → `prune-net-lines-recorded` | the prune slice's author (dev-runner or attended) | ⚠️ **unenforced** | none — no tool in the tree reads YR-DEBT-NET-LINES (verified by tree-wide search); it is not even a row in records.toml |
| 22 | `epic-finished-unclosed (debt)` → `debt-epic-held` | epic-gate | **prevented** | tools/epic_gate.py::_process_epic:940-951 — reachable, and it is the branch that would otherwise self-close |
| 23 | `debt-epic-held` → `epic-closed-completed` | attended closer (posts the verdict) then epic-gate (closes on the next sweep) | **prevented** | tools/epic_gate.py::_has_ledger_verdict:481-491, consulted at _process_epic:941 |
| 24 | `debt-epic-held` → `Reason cleared` | the attended closer | ⚠️ **unenforced** | tools/board_plumbing.py is the single field-write home; the record-before-flip wall is unmerged slice-5 code |
| 25 | `debt-due-raised` → `raise closed` | the attended closer | ⚠️ **unenforced** | none — the counter explicitly 'never closes' anything, and no other code path closes a raise |
| 26 | `debt-epic-open` → `round meters reported` | the attended closer | ⚠️ **unenforced** | tests/test_debt_round_standing_arms_and_close_meters.py:269 pins the DOC's wording (that all six meters are named, in order) — it verifies the canon text, never a round's execution |
| 27 | `epic-closed-completed (debt)` → `next round's census seeded` | the attended closer / the next round's census author | ⚠️ **unenforced** | none — no tool reads a census's surface declaration |
| 28 | `debt-epic-open` → `census duplication section populated` | attended session running tools/nit_harvest.py | ⚠️ **unenforced** | none at close — the harvest is an attended CLI; the reviewer-side emission is a prompt instruction in the stage charter, not a gate |

### Detail

#### 1. `epic-finished-unclosed` → `epic-closed-completed / epic-closed-not-planned`

`CLOSE-1-epic-self-close`

- **Actor:** epic-gate (tools/epic_gate.py, the standing-approval sweep running on the host)
- **Trigger:** A sweep tick reaches a Status=Ready epic in its per-epic pass
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py::_process_epic:939-954 — reachable on the only path the sweep takes to a finished epic
- **Records:** `none — a feature epic's self-close emits no comment and no trail record`
- **Preconditions:** The epic has at least one sub-issue (a childless epic is never 'finished') `[code: tools/epic_gate.py:935-937]`<br>No sub-issue is in state OPEN `[code: tools/epic_gate.py:939-940]`<br>The epic is NOT a debt epic, or a valid ledger verdict is already on record `[code: tools/epic_gate.py:941]`<br>Closing a finished epic is mechanical under the design's standing approval, fail-closed to the human on any doubt `[canon-only: AGENTS.md > The operating model (ticket-driven SDLC)]`<br>The self-close is independent of the standing-approval record — that record gates promotion only `[code: tools/epic_gate.py:930-938]`
- **Postconditions:** The issue is closed with reason 'completed' if any child closed as completed, else 'not planned' `[code: tools/epic_gate.py:589-593]`<br>The sweep returns one {'action': 'close'} entry; nothing else is written `[code: tools/epic_gate.py:954]`

#### 2. `epic-closed-completed` → `epic-done`

`CLOSE-2-native-close-to-done`

- **Actor:** native GitHub Projects automation (the built-in close→Done workflow on org project #1)
- **Trigger:** The issue transitions to closed
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none in this repo — the workflow lives in GitHub Projects configuration
- **Records:** `none`
- **Preconditions:** The issue is natively closed (Done is never written by the factory) `[canon-only: docs/rfcs/0003-task-state-model.md:41]`
- **Postconditions:** Status = Done on the board; Cancelled = closed-not-planned `[canon-only: docs/rfcs/0003-task-state-model.md:41]`

#### 3. `doc-draft` → `doc-active (frozen)`

`CLOSE-3-doc-freeze`

- **Actor:** attended closing session (a human-directed agent)
- **Trigger:** The iteration's PR merges
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** prose only in closing.md. tools/wall.py's `lifecycle-stamp` act (unmerged) would intercept ONLY the mcp__obsidian__vault_patch frontmatter path (tools/wall.py:154-160); a `vault_write`, a Bash `sed -i` or a filesystem write are not classified as a lifecycle stamp at all
- **Records:** `the status transition itself is the record — a review appendix never survives into a shipped doc`
- **Preconditions:** The PR merged — 'when the PR merges, the iteration's Obsidian docs become immutable records' `[canon-only: skills/factory/references/closing.md > 3. Doc-side freeze]`
- **Postconditions:** `status: active` on every doc still at draft; the body is NOT edited to match later reality `[canon-only: skills/factory/references/closing.md > 3. Doc-side freeze]`<br>A functional defect (dead link, unresolvable anchor) is the one repair permitted, and the repair records itself in the walk entry `[canon-only: skills/factory/references/documentation-model.md > Two principles]`

#### 4. `epic-closed-completed` → `crossed_to-stamped (verified)`

`CLOSE-4-crossed-to-backstop`

- **Actor:** attended closing session
- **Trigger:** The close checklist runs
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — closing.md prose; check_links gates spine crossing-links on a draft, not close-time stamps
- **Records:** `the `crossed_to` frontmatter key itself`
- **Preconditions:** The stamp was set AT the crossing, not here — the close is the backstop, not the act `[canon-only: skills/factory/references/closing.md > 3. Doc-side freeze]`
- **Postconditions:** Any doc found missing a `crossed_to` stamp is stamped `[canon-only: skills/factory/references/closing.md > 3. Doc-side freeze]`

#### 5. `epic-closed-completed` → `supersession pairs verified`

`CLOSE-5-supersession-sweep`

- **Actor:** attended closing session
- **Trigger:** The close checklist runs
- **Enforcement:** detected · **Guard site:** tools/check_supersession.py exists and is deterministic (advisory tier per gates.md); nothing invokes it at close
- **Records:** ``status: superseded` + `superseded_by` frontmatter pairs in the vault`
- **Preconditions:** Tombstones landed at ACCEPT, in the accepting session — this checklist only verifies `[code+canon: skills/factory/references/documentation-model.md > Lifecycle]`
- **Postconditions:** `check_supersession.py --sweep --scope <component>` run over the iteration's declarations; only what is found missing is stamped `[canon-only: skills/factory/references/closing.md > 3. Doc-side freeze]`

#### 6. `ship-walk-pending` → `ship-walk-recorded`

`CLOSE-6-ship-walk`

- **Actor:** the architect where the role is earned on the component; the closing session otherwise
- **Trigger:** The iteration close — canon says the trigger is a surfaced checkpoint, never a memory; in practice the human triggers it in almost every round
- **Enforcement:** detected · **Guard site:** tools/check_trail.py --lane close would find its absence (records.toml:391 puts YR-SHIP-WALK in the close lane) — but check_trail has NO caller anywhere in the tree and is advisory-tier by declaration (tools/check_trail.py:16)
- **Records:** `YR-SHIP-WALK (registry row exists; no emitter in code)`
- **Preconditions:** The 'write at ship' maintenance-contract trigger binds the walk to the iteration close `[canon-only: skills/factory/references/documentation-model.md > The maintenance contract]`<br>The role runs as its own independent cold session, and runs LAST, after any adversarial review folded in `[canon-only: skills/factory/references/architect.md > Independence and ordering]`
- **Postconditions:** Grounding list walked; living reference updated in place; replaced research superseded (never edited); the crossing stamp and every declared pair verified; pilot observables recorded `[canon-only: skills/factory/references/architect.md > Charter]`<br>The report ends in the moment's standard shape: grounding walk → living-reference diff → sweep-vs-view agreement check → stamp verification → pilot observables `[canon-only: skills/factory/references/architect.md > Running a session — practice the pilot earned]`<br>A `YR-SHIP-WALK:` record (who, scope) lands on the epic or standalone-task trail `[canon-only: records.toml:355-363]`

#### 7. `epic-finished-unclosed` → `round-record-emitted`

`CLOSE-7-round-record`

- **Actor:** the closing session (attended)
- **Trigger:** The round closes
- **Enforcement:** detected · **Guard site:** tools/check_trail.py close lane (records.toml:391) — no caller; the counts themselves come only from `wall.py counts` (tools/wall.py:391-399), which is unmerged, and even it emits only kinds refusal/pass/close-block/close-override — never 'records-demanded' or 'detector-findings'
- **Records:** `YR-ROUND-RECORD`
- **Preconditions:** WHEN the round closes THE ROUND RECORD SHALL state the observable counts — the pricing judgment against attended attention staying the human's `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria]`
- **Postconditions:** A `YR-ROUND-RECORD:` comment carrying refusals, records-demanded, detector-findings, escalations `[canon-only: records.toml:365-373]`

#### 8. `epic-open-with-open-children` → `escalation-recorded`

`CLOSE-8-escalation`

- **Actor:** the agent, at a decision surface, when implications are severe (a one-way door)
- **Trigger:** The severity valve — agent-initiated, optional
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — YR-ESCALATION appears in NO lane in records.toml:387-391, so even check_trail never asks for it
- **Records:** `YR-ESCALATION`
- **Preconditions:** Severe means a one-way door judged by consequences, not diffs `[canon-only: skills/factory/references/attended-lane.md > The output-gate model (ruled 2026-08-06, clarified same day)]`
- **Postconditions:** A `YR-ESCALATION:` record (act, why) lands, and is counted in the round record so the valve is measured `[canon-only: records.toml:375-383]`

#### 9. `epic-closed-completed` → `crossover judged`

`CLOSE-9-crossover-test`

- **Actor:** the closing session with the human
- **Trigger:** Each close
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none
- **Records:** `none — the crossover judgment leaves no record of any kind`
- **Preconditions:** At each close the candidate set includes product iterations; factory work must beat the product line on quality control per iteration · incremental understanding · cost control (the ruling's own order, verbatim) `[canon-only: skills/factory/references/closing.md > 4. The crossover test]`
- **Postconditions:** 'The factory is ready when no factory candidate wins'; a gap surfacing mid-product re-enters the candidate set `[canon-only: skills/factory/references/closing.md > 4. The crossover test]`<br>The cost axis is computable from the ledger rows alone (`ledger.py report`: the close-time cost line and the crossover cost axis) `[code: skills/factory/references/pipeline.md:383-385]`

#### 10. `living-reference-stale` → `living-reference-current`

`CLOSE-10-living-reference-update`

- **Actor:** the architect (ship-walk) or the closing session
- **Trigger:** 'Write at ship' — the iteration close
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — the maintenance contract states enforcement is procedural, 'a named step of the operation that owns the moment — not automated'
- **Records:** `the dated walk entry appended to the living reference`
- **Preconditions:** The reference cites, never copies: every fact names its authoritative home and none is asserted on the reference's own authority `[canon-only: skills/factory/references/documentation-model.md > The living reference]`
- **Postconditions:** The map is updated in place; replaced research is superseded, never edited `[canon-only: skills/factory/references/documentation-model.md > The maintenance contract]`<br>The `Last walked:` line moves — but no sanctioned agent write path reaches that single line inside a ~100 KB heading, so the one-line edit routes to the human `[canon-only: 04 projects/factory/architecture/factory-map.md > 5. Maintenance]`

#### 11. `content-merged-unreleased` → `release-cut-on-a-branch`

`REL-1-version-bump`

- **Actor:** dev-runner (the release is normally filed as a Task and built by the pipeline) OR an attended session (the 0.9.15 and 0.10.0 cuts were attended)
- **Trigger:** A close duty ('the version cut that surfaces to plugin consumers the skill content merged since <prev>') or a hotfix
- **Enforcement:** **prevented** · **Guard site:** tests/test_plugin_version_pin_canonical.py::test_canonical_pin_tracks_plugin_json_current_version and tests/test_plugin_packaging.py::test_plugin_version_is_current — both ride check_cmd (`pytest tests/ -q`) and the CI 'Tests' step, so a bump without the pin fails the gate
- **Records:** `none — no YR- record marks a release; the version string and the PR are the whole trail`
- **Preconditions:** Update `version` in `.claude-plugin/plugin.json` to the new semver; keep the plugin.json description in sync with SKILL.md's `[canon-only: skills/factory/references/closing.md > Skill-release block]`<br>Per-release precondition carried in the task body, not in canon: the tree's current version must equal the expected predecessor, else stop and report rather than guess `[canon-only: bench/corpus/yellow-robots--factory/136-pr137.json]`
- **Postconditions:** The single canonical version pin moves with it — a release is a two-file commit, plugin.json plus tests/test_plugin_packaging.py `[code+canon: tests/test_plugin_packaging.py:23-29]`<br>Exactly one `== "0.x"` positive pin exists suite-wide, and it must read plugin.json's live current version `[code: tests/test_plugin_version_pin_canonical.py:52-77]`

#### 12. `release-cut-on-a-branch` → `release-scan-green`

`REL-2-release-scan`

- **Actor:** the releasing session (canon) — in practice the pytest suite executes four of the five arms
- **Trigger:** Before shipping (canon: 'verify all of the following are true before shipping')
- **Enforcement:** *partial* · **Guard site:** tests/test_skill_factory_router.py + tests/test_check_model_refs.py::test_real_tree_scan_is_green (tests/test_check_model_refs.py:202-207), all riding check_cmd and CI 'Tests'
- **Records:** `none — the scan produces no durable artifact; only a green CI check on the release PR`
- **Preconditions:** No dangling router row: every Operations-table row links a file that exists under references/ `[code+canon: tests/test_skill_factory_router.py:126-135]`<br>No orphan reference: every file under references/ has a router entry — enumerated from disk, not a static list `[code+canon: tests/test_skill_factory_router.py:145-155]`<br>SKILL.md is < 500 lines (73 today) `[code+canon: tests/test_skill_factory_router.py:85-87]`<br>The description in SKILL.md frontmatter and in plugin.json agree exactly `[code+canon: tests/test_skill_factory_router.py:162-171]`<br>The consumer scan is green: 'nothing in the repo or org docs still cites a superseded content home as the living copy (tools/check_model_refs.py, fail-closed)' `[canon-only: skills/factory/references/closing.md > Skill-release block]`<br>As coded, the consumer scan matches exactly one hardcoded literal, `01-conventions`, over one scan-root defaulting to the factory repo `[code: tools/check_model_refs.py:21]`
- **Postconditions:** 'The release scan must be fully green. A dangling link, orphan reference, or description mismatch is a blocker — do not ship until resolved.' `[canon-only: skills/factory/references/closing.md > Skill-release block]`

#### 13. `release-cut-on-a-branch` → `released-on-main`

`REL-3-release-merge`

- **Actor:** the merge evaluator on an armed repo (auto_merge = true in .yr/factory.toml) OR the human's click on an attended release PR
- **Trigger:** The release PR is green, fresh, approved and rank-holding (armed path); or the human clicks (attended path)
- **Enforcement:** *partial* · **Guard site:** tools/merge_shadow.py (the deterministic evaluator) for the armed path; nothing for the attended path
- **Records:** `YR-MERGE: MERGED (armed path only)`
- **Preconditions:** Armed repo: CI-green · freshness vs main's tip · terminal clean APPROVE · review-rank >= build-rank · sentinel clear `[code+canon: skills/factory/references/closing.md > 2. Merge → Done]`<br>The factory repo is armed: `auto_merge = true`, shadow window complete 2026-07-07 `[code: .yr/factory.toml:16]`<br>An attended hand-merge is categorically refused by the walled-act map `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`
- **Postconditions:** Armed merge leaves a durable `YR-MERGE: MERGED` record; an attended merge leaves no evaluator record at all `[code+canon: records.toml:35-42]`<br>main now carries the new version string — and main IS the publication channel `[canon-only: 04 projects/factory/architecture/factory-map.md > 2. Mechanism map]`

#### 14. `released-on-main` → `installed-on-a-host`

`REL-4-publish-to-install`

- **Actor:** the Claude Code plugin installer / marketplace auto-update on each consumer host — no factory actor is involved
- **Trigger:** A marketplace refresh (the yellow-robots marketplace carries autoUpdate: true) or an explicit plugin refresh
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — nothing in the factory repo reads, verifies or gates on any host's install state
- **Records:** `the installed_plugins.json row (version, installedAt, lastUpdated, gitCommitSha)`
- **Preconditions:** The marketplace entry sources the factory repo by bare git URL with no ref, tag or version pin — so it tracks main; no second repo needs editing to publish `[canon-only: 04 projects/factory/architecture/factory-map.md > 2. Mechanism map]`<br>As observed on this host: the marketplace is the separate repo yellow-robots/skills, cloned at ~/.claude/plugins/marketplaces/yellow-robots, whose marketplace.json lists factory with source {source: url, url: https://github.com/yellow-robots/factory.git} and no version field `[code: ~/.claude/plugins/marketplaces/yellow-robots/.claude-plugin/marketplace.json]`<br>THE VISIBILITY KEY IS THE VERSION STRING: the install cache is version-keyed (~/.claude/plugins/cache/yellow-robots/factory/<version>/), so a main that moved without a bump materializes no new directory and refreshes no content `[code: ~/.claude/plugins/cache/yellow-robots/factory/]`
- **Postconditions:** A new version-named directory is materialized and installed_plugins.json records {version, installPath, lastUpdated} `[code: ~/.claude/plugins/installed_plugins.json]`<br>Observed latency: the 0.10.0 release commit a6b9990 merged 2026-08-05 00:39:53 +0200 and the cache dir .../factory/0.10.0/.claude-plugin/plugin.json was written 00:41:21 — 88 seconds. The vault records the same for 0.9.14: install stamped three minutes after its own merge `[code+canon: 04 projects/factory/architecture/factory-map.md > 2. Mechanism map]`<br>Counter-evidence for the version key: it-30 slices 1-4 merged to main on 2026-08-07 08:28-08:50 with no bump; the installed 0.10.0 tree still has no records.toml, no tools/check_trail.py, no tools/compile_slice.py, no hooks/ and no references/attended-lane.md `[code: ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/tools/]`

#### 15. `installed-on-a-host` → `loaded-in-a-session`

`REL-5-install-to-session`

- **Actor:** the human or the session itself
- **Trigger:** `/reload-plugins` or a fresh session
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none
- **Records:** `none in the factory; the host writes a per-pid marker under <installPath>/.in_use/`
- **Preconditions:** Bundled reference files hot-reload only via /reload-plugins or a fresh session — 'ship as one coherent version so router and references never split' `[canon-only: skills/factory/references/closing.md > Skill-release block]`
- **Postconditions:** The session reads the new router + references; cold sessions reach the new version at their next plugin refresh `[canon-only: 04 projects/factory/architecture/factory-map.md > 2. Mechanism map]`

#### 16. `released-on-main` → `consumers repointed / old home demoted`

`REL-6-ship-before-demote`

- **Actor:** attended session
- **Trigger:** After the release merges
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tools/check_model_refs.py catches ONE historical case afterwards (the `01-conventions` literal) — it cannot express any other demotion
- **Records:** `none`
- **Preconditions:** The release ships the new content BEFORE any dependent consumer is repointed and before the superseded source is demoted — 'the living content must never exist nowhere authoritative' `[canon-only: skills/factory/references/closing.md > Skill-release block]`
- **Postconditions:** Consumers repointed; the superseded home demoted `[canon-only: skills/factory/references/closing.md > Skill-release block]`

#### 17. `any attended session` → `release edit refused`

`REL-7-release-wall`

- **Actor:** tools/wall.py PreToolUse hook (UNMERGED — slice 5, failed independent review at 0 of 5 acceptance criteria; tools/wall.py additionally carries uncommitted local edits)
- **Trigger:** A Write or Edit whose file_path ends `.claude-plugin/plugin.json`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py::classify:151-152 → decide:244-268, registered as a PreToolUse hook on Bash\|Write\|Edit\|mcp__obsidian__vault_patch in hooks/hooks.json. NOT reachable today: the registration exists only on the unmerged branch (origin/main's hooks/hooks.json carries SessionStart alone), and the installed 0.10.0 plugin ships no hooks/ directory at all
- **Records:** `counts.jsonl refusal row (not a registry-sanctioned record; YR-WALL is a marker minted outside records.toml)`
- **Preconditions:** Canon: the act's condition is 'the freeze checks' records (the release scan's results, recorded)', stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>Code: NO condition is evaluated. `release-edit` is not in decide()'s in-flight-condition branch (only `crossing-file` is), so the deny is unconditional with no satisfiable path `[code: tools/wall.py:244-268]`
- **Postconditions:** permissionDecision 'deny' with reason 'YR-WALL [release-edit] — a skill release requires the freeze checks' records (attended-lane.md; closing.md's release block)' `[code: tools/wall.py:238]`<br>A `refusal` row appended to $YR_WALL_STATE/counts.jsonl, best-effort and silent on failure `[code: tools/wall.py:77-88]`

#### 18. `wall-session-has-unresolved-refusals` → `close-override-recorded`

`REL-8-session-close-check`

- **Actor:** tools/wall.py Stop hook (UNMERGED)
- **Trigger:** Session close (Stop)
- **Enforcement:** *partial* · **Guard site:** tools/wall.py::close_check:273-299 via the Stop registration in hooks/hooks.json — unmerged and unreleased, so unreachable in any session today
- **Records:** `close-block / close-override rows in counts.jsonl`
- **Preconditions:** Canon: a session that executed a walled act OR emitted a mandated record is refused a silent close while mandatory traces are missing (the refusal names each) `[canon-only: skills/factory/references/attended-lane.md > Delivery, the slice, and the close]`<br>Code: the check reads ONLY $YR_WALL_STATE/counts.jsonl for this session and blocks when a refusal has no later 'pass' event for the same act; it never reads a trail, never consults records.toml lanes, and never names a missing record `[code: tools/wall.py:273-299]`
- **Postconditions:** First close: {'decision': 'block'} naming the acts refused; a close-block row written `[code: tools/wall.py:292-299]`<br>Second consecutive close with traces unchanged: proceeds and writes a close-override row — the close check never hard-locks `[code: tools/wall.py:288-291]`

#### 19. `debt-countable-below-threshold` → `debt-due-raised`

`DEBT-1-counter-raise`

- **Actor:** epic-gate (the per-repo debt counter sweep)
- **Trigger:** A sweep tick, per repo holding a Type=Feature epic on the board
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py::_sweep_debt_counters:863-913 — reachable on every sweep tick
- **Records:** `YR-DEBT-DUE`
- **Preconditions:** Count of closed-as-completed Feature epics that are not debt-kind and closed after the anchor (the debt-kind epic with the latest closedAt, or none) `[code: tools/epic_gate.py:728-746]`<br>count >= threshold, resolved env DEBT_ROUND_EVERY > manifest debt_round_every > default 10; any read/parse/validity failure falls back to the default rather than erroring `[code+canon: tools/epic_gate.py:810-819]`<br>No open raise already exists for this (repo, anchor) key — never re-keyed on the count, so the same anchor never raises twice `[code+canon: tools/epic_gate.py:822-841]`
- **Postconditions:** A Type=Task issue is created carrying the YR-DEBT-DUE record (repo/anchor/count/counted) and added to the board at Status=Backlog — never Ready, never promoted, never closed `[code: tools/epic_gate.py:895-910]`<br>The raise is deliberately not DoR-complete: it names the need, it does not scope the round; promotion stays a human act `[code+canon: tools/epic_gate.py:849-860]`<br>A failure on one repo is isolated as a debt-error action and never touches epic processing `[code: tools/epic_gate.py:911-913]`

#### 20. `debt-due-raised` → `debt-epic-open`

`DEBT-2-raise-to-round`

- **Actor:** human (promote) + attended session (round-spec + census authoring)
- **Trigger:** The human decides to run the round
- **Enforcement:** *partial* · **Guard site:** tools/epic_gate.py::_is_debt_epic:474-478 reads the kind line; the walls themselves (census, by-name scope, birth citation, prune review bar, guards) are prose only
- **Records:** `YR-ITERATION-KIND: tech-debt`
- **Preconditions:** The round opens on a `research` census with a reachability ledger; nothing is deletable unless the ledger clears it `[canon-only: skills/factory/references/debt-rounds.md > The walls]`<br>By-name scope: the round-spec is a product-spec naming the items; an item not named is not in the round `[canon-only: skills/factory/references/debt-rounds.md > The walls]`<br>The census reads four inputs in fixed order before sweeping: declared surface, nit clusters, open backlog seeds, prior carry-forward `[canon-only: skills/factory/references/debt-rounds.md > The walls]`
- **Postconditions:** The epic body carries `YR-ITERATION-KIND: tech-debt` on its own whole stripped line, making it a debt epic to the counter and the close-hold `[code+canon: tools/epic_gate.py:474-478]`<br>Pin-then-prune ordering is enforced mechanically by the sweep's sub-issue serialization (one open child at a time, in sub-issue order) `[code+canon: skills/factory/references/debt-rounds.md > The walls]`

#### 21. `debt-epic-open` → `prune-net-lines-recorded`

`DEBT-3-prune-net-lines`

- **Actor:** the prune slice's author (dev-runner or attended)
- **Trigger:** A prune PR is filed
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — no tool in the tree reads YR-DEBT-NET-LINES (verified by tree-wide search); it is not even a row in records.toml
- **Records:** `YR-DEBT-NET-LINES`
- **Preconditions:** One item = one revertible chain; each round item squash-merges as its own commit `[canon-only: skills/factory/references/debt-rounds.md > The walls]`<br>The prune review bar: behavior-identical (the pin slice's tests pass unchanged) and net-negative `[canon-only: skills/factory/references/debt-rounds.md > The walls]`<br>Every prune slice ships a guard that fails when its own finding recurs, or records why no guard is expressible `[canon-only: skills/factory/references/debt-rounds.md > The walls]`
- **Postconditions:** A YR-DEBT-NET-LINES block (items, net-lines) in the PR's own body `[canon-only: skills/factory/references/debt-rounds.md > Record grammars]`

#### 22. `epic-finished-unclosed (debt)` → `debt-epic-held`

`DEBT-4-close-hold`

- **Actor:** epic-gate
- **Trigger:** A sweep tick finds a debt epic with no open child and no valid ledger verdict
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py::_process_epic:940-951 — reachable, and it is the branch that would otherwise self-close
- **Records:** `YR-DEBT-HOLD`
- **Preconditions:** The epic body carries the kind sentinel AND no comment satisfies _has_ledger_verdict `[code: tools/epic_gate.py:941]`<br>A valid verdict is ONE comment carrying the YR-DEBT-LEDGER marker line plus non-empty `items` and `net-lines` in that same comment — fields pooled across comments never count `[code+canon: tools/epic_gate.py:481-491]`
- **Postconditions:** The hold comment is posted once (keyed on its own marker) and Reason is set to Needs-info if not already `[code: tools/epic_gate.py:942-951]`<br>The hold body deliberately never spells a field as a bare `key: value` line, so it cannot satisfy _has_ledger_verdict on the next tick `[code: tools/epic_gate.py:561-575]`<br>The close-time duty (counting the ledger) can never be skipped by a same-tick self-close `[code+canon: tools/epic_gate.py:934-941]`

#### 23. `debt-epic-held` → `epic-closed-completed`

`DEBT-5-ledger-then-self-close`

- **Actor:** attended closer (posts the verdict) then epic-gate (closes on the next sweep)
- **Trigger:** The verdict comment lands; the next sweep tick runs
- **Enforcement:** **prevented** · **Guard site:** tools/epic_gate.py::_has_ledger_verdict:481-491, consulted at _process_epic:941
- **Records:** `YR-DEBT-LEDGER`
- **Preconditions:** A comment carries the YR-DEBT-LEDGER marker on its own stripped line and yields non-empty items and net-lines `[code: tools/epic_gate.py:481-491]`<br>Canon states seven fields (items, net-lines, files-removed, deps-removed, pins-added, suite-duration, incidents), of which items and net-lines are the machine-checked pair `[canon-only: skills/factory/references/debt-rounds.md > Record grammars]`
- **Postconditions:** The next sweep self-closes the epic (or the human closed it attended and the sweep leaves it as found) `[code+canon: tools/epic_gate.py:952-954]`

#### 24. `debt-epic-held` → `Reason cleared`

`DEBT-6-clear-held-reason`

- **Actor:** the attended closer
- **Trigger:** Round close
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tools/board_plumbing.py is the single field-write home; the record-before-flip wall is unmerged slice-5 code
- **Records:** `canon-designated YR-BOARD-FLIP would be required for any attended board write (attended-lane.md), but YR-BOARD-FLIP is in no lane in records.toml:387-391`
- **Preconditions:** The epic-gate posts the hold and sets Needs-info but never clears a Reason itself; clearing is the attended closer's act, the same fail-closed shape as every other epic-gate hold `[code+canon: skills/factory/references/debt-rounds.md > Round-close duties]`
- **Postconditions:** Reason is empty on the board item `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`

#### 25. `debt-due-raised` → `raise closed`

`DEBT-7-dispose-the-raise`

- **Actor:** the attended closer
- **Trigger:** Round close
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — the counter explicitly 'never closes' anything, and no other code path closes a raise
- **Records:** `none`
- **Preconditions:** 'Dispose of the round's raise issue — close it now that its need is met; it is never left open past the round it named' `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`
- **Postconditions:** The raise issue is closed `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`

#### 26. `debt-epic-open` → `round meters reported`

`DEBT-8-six-close-meters`

- **Actor:** the attended closer
- **Trigger:** Round close
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tests/test_debt_round_standing_arms_and_close_meters.py:269 pins the DOC's wording (that all six meters are named, in order) — it verifies the canon text, never a round's execution
- **Records:** `the seven-field YR-DEBT-LEDGER comment (only items and net-lines are machine-checked)`
- **Preconditions:** Six meters in fixed order: recurrence · coverage over the four declared axes · guard yield · per-test cost with its protocol · cluster conversion within the round that found them · the detection locus as two counts, never a ratio `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`<br>Net-lines records from every prune PR are aggregated into the verdict's items and net-lines totals `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`
- **Postconditions:** The meters are reported alongside the ledger verdict `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`

#### 27. `epic-closed-completed (debt)` → `next round's census seeded`

`DEBT-9-recensus-trigger`

- **Actor:** the attended closer / the next round's census author
- **Trigger:** The census's own named revisit trigger (event-driven, never clock-gated)
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none — no tool reads a census's surface declaration
- **Records:** `the three machine-readable surface fields (baseline ref, include rule, exclude rule) in the census's own fenced block`
- **Preconditions:** Freshness for a research doc is event-driven via an optional named revisit trigger in the doc's body `[canon-only: skills/factory/references/documentation-model.md > Lifecycle]`<br>The next round's surface is (the tree today) − (files matching the declared surface unchanged since that baseline ref); the exclude rule applies to both terms `[canon-only: skills/factory/references/debt-rounds.md > The walls]`
- **Postconditions:** The next round starts from the trigger the last one named, not from scratch `[canon-only: skills/factory/references/debt-rounds.md > Round-close duties]`

#### 28. `debt-epic-open` → `census duplication section populated`

`DEBT-10-nit-harvest`

- **Actor:** attended session running tools/nit_harvest.py
- **Trigger:** Census authoring (wall 10's nit-clusters input)
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** none at close — the harvest is an attended CLI; the reviewer-side emission is a prompt instruction in the stage charter, not a gate
- **Records:** `YR-NIT (emitted by reviewers under the runner's review stage charter, tools/dev-runner.sh:2091)`
- **Preconditions:** A record row is a line beginning YR-NIT: at column 0 on the RAW line — no strip, no whitespace tolerance; column-0 anchoring is exactly what keeps blockquoted shadow nits out `[code+canon: tools/nit_harvest.py:56]`<br>A cluster requires recurrence across two or more separate PRs and a path/symbol that still resolves in the tree `[code+canon: skills/factory/references/debt-rounds.md > The nit harvest]`
- **Postconditions:** Output lands as a census row, never as an issue — a harvested-nit issue would be swept onto the board by the intake pass and flood the state machine `[code+canon: tools/nit_harvest.py:6-9]`<br>Two arms returned: by_symbol and by_path; a stored line number is provenance only and is consulted by neither `[code: tools/nit_harvest.py:33-40]`

## Where the code and the canon disagree

### [blocking] The skill-release wall's condition has no satisfiable path

- **code:** classify() returns 'release-edit' for any Write/Edit whose path ends `.claude-plugin/plugin.json` (tools/wall.py:151-152), and decide() denies it immediately: only `crossing-file` is handled in the in-flight-condition branch (tools/wall.py:253-260), so no record can ever satisfy the release act. `_trail_has` — the helper that would read a condition off a trail — is defined at tools/wall.py:205 and called nowhere in the tree.
- **canon:** The walled-act map states the release act's condition as 'the freeze checks' records (the release scan's results, recorded)' with stance fail-closed, and the governing spec's criterion reads 'WHEN a skill release is attempted without the freeze checks' records THE ENFORCEMENT LAYER SHALL refuse the release, naming the missing checks' — i.e. a conditional refusal that names what is missing, not a categorical one.
- `tools/wall.py:151-152`, `tools/wall.py:205`, `tools/wall.py:244-268`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria`

### [material] 'The freeze checks' records' names a record that does not exist anywhere

- **code:** records.toml carries no row for any freeze-check or release-scan record; the release scan is a pytest run that writes nothing durable. The registry's own closing note states 'The record a wall condition names must itself be registered' (records.toml:401). The agreement test that is supposed to enforce this only scans backtick-quoted `YR-…` tokens inside the walled-act map (tests/test_attended_lane_canon.py:92-99), so a condition phrased in bare prose passes it vacuously.
- **canon:** Every walled act carries a stated condition — a required record set — and 'a record absent from the registry is unsanctioned'.
- `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`, `records.toml:393-401`, `tests/test_attended_lane_canon.py:92-99`

### [blocking] The wall engine has no scope guard and no machinery guard, though its own docstring describes both

- **code:** in_scope() (tools/wall.py:48-72) checks YR_MACHINERY and factory-tree membership and is never called — a tree-wide search finds only its definition. decide() and close_check() consult neither. Since plugin hooks are user-scoped, the walls would fire in every session in every directory, and inside the runner's cold stages (tools/dev-runner.sh:46 exports YR_MACHINERY=1, which hooks/deliver.sh:21 honours and wall.py does not). The direct consequence for this lane: a release cut built by the pipeline edits `.claude-plugin/plugin.json`, and that implement stage would be denied.
- **canon:** 'Machinery is not attended: a cold pipeline stage inherits YR_MACHINERY from the runner, exactly as delivery already honours it — one declaration, both halves' (the docstring); and the ship-walk recorded the same finding independently: 'The wall engine lacks the machinery guard delivery has… Fail-dangerous.'
- `tools/wall.py:48-72`, `tools/dev-runner.sh:46`, `hooks/deliver.sh:21`, `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications`

### [blocking] The close check does not check the traces the canon says it checks

- **code:** close_check() reads only $YR_WALL_STATE/counts.jsonl for the current session and blocks when a `refusal` event has no later `pass` event for the same act (tools/wall.py:279-292). It never loads records.toml, never resolves a lane, never reads an issue trail, and never names a missing record — a session that emitted no walled act but owes YR-SHIP-WALK and YR-ROUND-RECORD closes silently.
- **canon:** 'Session close is checked: a session that executed a walled act **or emitted a mandated record** is refused a silent close while **mandatory traces are missing** (the refusal names each)'.
- `tools/wall.py:273-299`, `skills/factory/references/attended-lane.md > Delivery, the slice, and the close`

### [material] The delivered slice carries no round position

- **code:** compile_slice() emits the two canon tables verbatim, the lane mandates, the router rows and the checkpoint bullets — no position marker of any kind (tools/compile_slice.py:80-119). The 'Position' element deliver.sh appends is the repo name, open PRs and up to twelve board rows (hooks/deliver.sh:71-92) — never the round's current step or next step.
- **canon:** '…composed at delivery with the round's current position and next step (the state-machine view): (1) the step set **with position**'.
- `tools/compile_slice.py:80-119`, `hooks/deliver.sh:71-92`, `skills/factory/references/attended-lane.md > Delivery, the slice, and the close`

### [material] The release scan's consumer-scan arm is far narrower than closing.md claims

- **code:** tools/check_model_refs.py matches exactly one hardcoded literal, `_PATTERN = "01-conventions"` (tools/check_model_refs.py:21), over a single --scan-root defaulting to the factory repo root (tools/check_model_refs.py:81-84). It cannot express 'a superseded content home' generally, and it never reads the org-docs repo (yellow-robots/.github, a separate clone).
- **canon:** 'The consumer scan is green: nothing in the repo **or org docs** still cites **a superseded content home** as the living copy (tools/check_model_refs.py, fail-closed).'
- `tools/check_model_refs.py:21`, `tools/check_model_refs.py:77-91`, `skills/factory/references/closing.md > Skill-release block`

### [material] The close reference never names the close-side records the registry mandates

- **code:** records.toml:391 sets `close = ["YR-SHIP-WALK", "YR-ROUND-RECORD"]`, and check_trail's close lane checks exactly those two. The epic self-close (tools/epic_gate.py:952-953) reads neither.
- **canon:** closing.md — the reference the router points at for 'Closing' — never mentions YR-SHIP-WALK or YR-ROUND-RECORD; its §3 checklist has no such step. The mandate lives only in attended-lane.md's step table (steps 10 and 11), and closing.md cites it for the STANDALONE case only ('a standalone task is a round of one').
- `records.toml:391`, `skills/factory/references/closing.md > 3. Doc-side freeze`, `skills/factory/references/closing.md > 1. Promote to Ready`, `skills/factory/references/attended-lane.md > The mandatory step set (reified — the existing mandates, not new ones)`

### [minor] The ledger verdict's declared surface includes the epic body; the reader only reads comments

- **code:** _has_ledger_verdict(comments) iterates comment bodies only; _process_epic passes it the issue's comment nodes, never the body (tools/epic_gate.py:481-491, :926). A verdict typed into the epic body would not count.
- **canon:** records.toml's YR-DEBT-LEDGER row declares the emitter as 'the debt round's census/scaffold (**epic body**/trail)'. debt-rounds.md is narrower and agrees with the code ('a comment on the debt epic').
- `tools/epic_gate.py:481-491`, `records.toml:170-178`, `skills/factory/references/debt-rounds.md > Record grammars`

### [minor] records.toml's reader annotations describe a tip this branch has already moved past

- **code:** On this branch tools/wall.py::promote_check (tools/wall.py:360-376) and tools/wall.py::board_check (tools/wall.py:325-357) exist and are called by promote.sh / board_plumbing.py.
- **canon:** records.toml still annotates those readers as 'slice 5 — future reader, not at tip' on the YR-TASK-GATES, YR-BOARD-FLIP and YR-HUMAN-INSTRUCTION rows.
- `records.toml:71`, `records.toml:351`, `records.toml:399`, `tools/wall.py:325-376`

### [minor] Two YR- markers were minted outside the registry by the round that ratified one marker with one home

- **code:** tools/wall.py emits 'YR-WALL [<act>] — …' in every refusal reason (tools/wall.py:266) and hooks/deliver.sh emits 'YR-DELIVERY-FAILURE: …' in its banner (hooks/deliver.sh:43-45). Neither is a row in records.toml.
- **canon:** 'A record absent from this registry is unsanctioned' — and the marker table declares one umbrella, `YR-`, changed by one edit plus a migration round.
- `tools/wall.py:266`, `hooks/deliver.sh:43-45`, `records.toml:4-5`, `records.toml:28-31`, `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications`

## Gaps

- **Nothing couples a change to shipped skill content with a version bump. No test, gate, CI step or hook compares a diff touching skills/ or templates/ against `.claude-plugin/plugin.json`; a tree-wide search of tests/ finds no such guard.**<br>This is the lane's live failure right now: iteration 30 slices 1-4 (records.toml, tools/check_trail.py, references/attended-lane.md, tools/compile_slice.py + hooks/) merged to main on 2026-08-07 08:28-08:50 with plugin.json still at 0.10.0, so none of it exists in the installed plugin — the 0.10.0 cache tree carries no records.toml, no attended-lane.md and no hooks/ directory. The only detector is a human reading plugin.json at tip during the ship-walk, and the living map already records this as a *standing failure mode of the walk*: three consecutive walks reported a release as owed that had already shipped, and one reported shipped what was owed.
- **A skill release leaves no record of any kind. There is no YR- record, no registry row, no trail comment and no lane for a release; the release scan produces nothing durable; and the merge record (YR-MERGE: MERGED) exists only when the release PR merges through the armed evaluator — an attended release merge leaves no evaluator record at all.**<br>The release is the only transition in this lane with real external consequence (it changes what every consumer session reads) and it is the one with the thinnest trail. Nothing can be asked afterwards, by machine, about whether a release happened, what scan arms were run, or what content it carried.
- **A FEATURE epic self-closes with zero close-side duty checks, while its DEBT sibling is held. tools/epic_gate.py:941 holds a debt epic for its ledger verdict; the very next lines close a feature epic unconditionally, with no check for a ship-walk trace, a round record, a doc freeze, a crossed_to sweep, or an owed release.** **← needs an owner ruling**<br>This is the same rule existing for one lane and not its sibling. Every close-side duty in closing.md §3-4, architect.md's ship-walk and attended-lane.md's steps 10-11 sits downstream of a transition that has already fired. The epic is Done before anyone asks whether the close happened.
- **tools/check_trail.py — the only machine that can find a missing YR-SHIP-WALK or YR-ROUND-RECORD — has no caller anywhere in the tree (only its own tests import it), is advisory-tier by declaration ('never wired into check_cmd, CI, or the manifest'), and is named by no procedure: closing.md does not mention it.**<br>The close lane's detection is real code that nothing runs. Both close-side records are therefore 'detected' only in the sense that a human who chooses to run a CLI could find them missing.
- **The round record's counts have no producer. YR-ROUND-RECORD's declared fields are refusals, records-demanded, detector-findings, escalations; the only emitter of any of them is tools/wall.py's counts.jsonl, which is unmerged — and even it writes only kinds refusal/pass/close-block/close-override. Nothing anywhere produces 'records-demanded' or 'detector-findings'.** **← needs an owner ruling**<br>The spec's final criterion — the human prices the enforcement against attended attention at close — rests on numbers two of which no component computes.
- **YR-ESCALATION is registered but belongs to no lane (records.toml:387-391 lists design/epic/standalone/close only), so the detector never checks for it even though the round record counts escalations. YR-BOARD-FLIP is likewise in no lane — the record the walls most depend on.**<br>The severity valve is explicitly designed to be 'measured, never vibed', and the measurement path has no checker.
- **Nothing in the factory repo knows the publication channel exists. The marketplace is a separate repo (yellow-robots/skills) that is not a clone in the workspace and is named nowhere in AGENTS.md, README.md, closing.md or any RFC; the only written record of the mechanism is the vault living map's §2 paragraph.**<br>The single most consequential fact of the release lane — that main is the channel because the marketplace entry pins no ref, and that the install cache is keyed by the version STRING — is derivable today only from a vault paragraph plus host state. A cold session running a release from the shipped docs alone cannot learn it.
- **Nothing verifies that a released version reached any host. No factory tool reads installed_plugins.json or the install cache; the '88 seconds from merge to install' and '0.9.14 installed three minutes after its merge' facts are one-off manual observations recorded in the vault.**<br>The lane's terminal state — content actually reaching consumer sessions — is unobserved by the system that produces it.
- **There is no rollback, yank or un-release transition. No canon text and no code describes withdrawing a published version; because the install cache is version-keyed and the marketplace tracks main, the only recovery from a bad release is a higher version.** **← needs an owner ruling**<br>A state with no exit is a hole in the machine — and the release is the one act in this lane whose consequences land on every consumer at once.
- **The release scan checks a skill's shape, never whether its prose is still true of the tree. Four arms are structural (router bijectivity, line ceiling, description agreement) and the fifth matches one literal.**<br>Recorded verbatim as the generalizable lesson of the 0.9.15 release session, where the live risk was exactly this: shipping a canon claim the tool no longer met. 'The second question is not on closing.md's list, and it was the one with a real defect behind it.'
- **The debt round's close-side duties 2-6 have no machine reader at all: YR-DEBT-NET-LINES is not a registry row and nothing in the tree parses it; the six close-time meters are pinned only as doc TEXT by tests/test_debt_round_standing_arms_and_close_meters.py:269; the raise issue is never disposed of by any code path (the counter 'never closes'); the held Reason is never cleared by the gate; and the re-census trigger is prose.**<br>Only one of six round-close duties (the ledger verdict) is enforced; the epic self-closes on that one alone, so the other five can be skipped with no trace and no consequence.
- **The crossover test has no artifact, no record, no owner named in code, and no output surface — closing.md §4 is its entire existence.**<br>It is the standing decision about whether the factory should keep being built at all, and it leaves nothing a later session can read.
- **The living reference's own freshness marker cannot be written by any sanctioned agent path: `Last walked:` is one mutable line inside a single ~100 KB heading, and updating it routes to the human.** **← needs an owner ruling**<br>The write-at-ship trigger's completion signal is the one part of the ship-walk an agent structurally cannot complete, which is exactly how the it-29 walk left it naming it-28.
- **It-30's own governing spec fails the detector it-30 shipped, 3 of 3 on the design lane, because the grammars were minted after the accept act; the epic's own record-before-flip comment is likewise pre-grammar prose.**<br>The lane's first real scope is non-conformant with the lane's own canon at the moment of shipping it — retro-typing the round's own design records is named as outstanding execution work.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **Disagreement #9: 'On this branch tools/wall.py::promote_check (tools/wall.py:360-376) and tools/wall.py::board_check (tools/wall.py:325-357) exist and are called by promote.sh / board_plumbing.py' — offered as evidence that records.toml's 'slice 5 — future reader, not at tip' annotations have been overtaken.**<br>Half of it is false. `promote_check` is genuinely wired (defined tools/wall.py:360, CLI subcommand at :386-395, invoked by tools/promote.sh:68). `board_check` has ZERO callers anywhere in the tree — a full-text scan of tools/, tests/, hooks/, *.md and *.toml finds the single occurrence at tools/wall.py:325 (its own def). tools/board_plumbing.py does NOT shell out to it: it carries its own inline `_attended_wall` (tools/board_plumbing.py:112-152) with a hand-spelled `l.startswith("YR-BOARD-FLIP:")` at :145, and wall.py's own `main()` (tools/wall.py:381-407) registers no `board-check` subcommand. `board_check` is dead code added by the uncommitted diff. So records.toml:351's annotation ('tools/board_plumbing.py wall — future reader, not at tip') is stale for a different reason than claimed, and the excavation's own disagreement #10 (a hand-rolled matcher minted outside textutil) is where board_plumbing actually sits. `tools/wall.py:325-357 (def, no callers) · tools/wall.py:381-407 (CLI: pre-tool/close/promote-check/counts only) · tools/board_plumbing.py:112-152, :145, :160`
- **Gap: 'The living reference's own freshness marker cannot be written by any sanctioned agent path … the write-at-ship trigger's completion signal is the one part of the ship-walk an agent structurally cannot complete, which is exactly how the it-29 walk left it naming it-28.' CLOSE-10 postcondition: 'so the one-line edit routes to the human'.**<br>The map itself records the opposite outcome. §5's `Last walked:` line today reads 'Last walked: 2026-08-05 — the **it-29 close**' (line 108), and the log's final entry (line 162) records how it got there: 'the `Last walked:` line updated to it-29, **by delegation**. The human delegated item (2) of the walk entry above to the attended session rather than the in-editor edit; executed as an app-mediated `obsidian eval` single-line replace (`app.vault.process`) — a recorded deviation from the decision table … with the parse and file-value read-backs green as usual.' An agent did complete it. What the record supports is the narrower claim the record itself makes — the decision table 'offers no row reaching one line inside this section short of whole-section regeneration' — not 'structurally cannot complete' and not 'routes to the human'. `04 projects/factory/architecture/factory-map.md:108 and :162 (§ 5 Maintenance)`
- **Gap: 'The marketplace is a separate repo (yellow-robots/skills) that is not a clone in the workspace and is named nowhere in AGENTS.md, README.md, closing.md or any RFC; the only written record of the mechanism is the vault living map's §2 paragraph.'**<br>The org AGENTS.md — the canonical `yellow-robots/.github` file symlinked at the workspace root and loaded into every session here — names it: 'Org docs live in `yellow-robots/.github`; agent skills ship as plugins from `yellow-robots/skills`.' The claim is true only of the FACTORY repo's own AGENTS.md (I confirmed 'marketplace' and 'yellow-robots/skills' appear in zero factory-repo files outside bench corpus). Everything else in the gap holds: `skills` is not a clone under /opt/yellow-robots (factory · gilda · website · yellow-robots · .github only), and no shipped doc explains the no-ref/version-keyed mechanism. `/opt/yellow-robots/.github/AGENTS.md:25 · ls /opt/yellow-robots (no `skills` clone) · tree-wide grep of the factory repo for 'marketplace' → 0 hits`
- **State 'loaded-in-a-session', stored_where: 'In-session harness state; the per-session marker files under <installPath>/.in_use/<pid>' — cited to `skills/factory/references/closing.md > Skill-release block`.**<br>closing.md's Skill-release block says nothing about `.in_use` or per-pid markers; its only session sentence is the parenthetical at :129-131 ('bundled reference files hot-reload only via /reload-plugins or a fresh session'). The marker directory does exist on this host (`~/.claude/plugins/cache/yellow-robots/factory/0.10.0/.in_use/` holding pids 2965196, 2982277, 2982282), so the fact is true — but the cited canon does not establish it, and nothing in the factory tree does either. `skills/factory/references/closing.md:102-136 (whole block) vs. ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/.in_use/`
- **State 'release-cut-on-a-branch' ('0.11.0 sits here today, unmerged') — cited to `tests/test_plugin_packaging.py:26-28`.**<br>That file at this worktree's HEAD pins "0.10.0" (assertion at :29-30, docstring at :26-27); it does not show the branch's cut at all. The underlying claim IS true, but only under a different ref: `git show origin/task/421-release:tests/test_plugin_packaging.py` line 29 reads `assert data["version"] == "0.11.0"`, and that branch's plugin.json:5 reads 0.11.0. The citation as given points at the ref that contradicts it. `tests/test_plugin_packaging.py:25-30 (worktree, pins 0.10.0) vs. origin/task/421-release:tests/test_plugin_packaging.py:29`
- **REL-1 postcondition: 'Exactly one `== "0.x"` positive pin exists suite-wide, and it must read plugin.json's live current version' — cited to `tests/test_plugin_version_pin_canonical.py:52-77`.**<br>The file is 71 lines; the cited range overruns EOF by six lines and its first eight lines (52-59) are blank/docstring for the negative-vestige test. The two tests that carry the claim are `test_exactly_one_positive_version_pin_suite_wide` at :45-51 and `test_canonical_pin_tracks_plugin_json_current_version` at :60-71. The claim itself verifies (the second test reads plugin.json's live version and asserts the single pin contains it), so REL-1's 'prevented' enforcement stands — the citation does not. `tests/test_plugin_version_pin_canonical.py:45-51, :60-71 (file ends at 71)`
- **REL-1 precondition, source 'canon': 'the tree's current version must equal the expected predecessor, else stop and report rather than guess' — cited to `bench/corpus/yellow-robots--factory/136-pr137.json`.**<br>That file is a frozen bench-corpus snapshot of ONE past task body (the 0.9.2→0.9.3 cut), which tools/textutil.is_frozen_bench_evidence explicitly excludes from every living-text guard (tools/check_model_refs.py:63). Its own text is pre-#149 era — it demands editing 'exactly these seven test files', the shape the single canonical pin replaced. It is a historical artifact, not canon and not a standing rule; the excavation's own precondition text says 'not in canon' while its `source` field says `canon`. `bench/corpus/yellow-robots--factory/136-pr137.json (prompt body) · tools/check_model_refs.py:63 · tests/test_plugin_version_pin_canonical.py:1-11`
- **CLOSE-1 precondition: 'The epic has at least one sub-issue (a childless epic is never "finished")' — cited to `tools/epic_gate.py:935-937`.**<br>Lines 935-937 are the comment for the NEXT branch (the no-open-children/debt-hold rationale). The childless guard is at :929-931 (`# (4) childless epic → do nothing` / `if not children: return []`). Claim true, citation misplaced. `tools/epic_gate.py:929-931 vs. cited :935-937`
- **REL-7 (release wall) enforcement: 'partial'. REL-8 (session close-check) enforcement: 'partial'.**<br>An enforcement value of 'partial' reads as 'some of it fires'. Neither fires at all, anywhere, today. origin/main's hooks/hooks.json carries SessionStart alone (verified by `git show origin/main:hooks/hooks.json`); the PreToolUse and Stop registrations exist only on the unmerged branch; and the installed 0.10.0 plugin tree ships no `hooks/` directory and no `tools/wall.py` (verified: ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/tools/ has 23 files, none of them wall.py). The excavation states the unreachability correctly in `guard_site` — which makes the 'partial' label an internal contradiction, not a disclosure. 'unenforced' is the honest value. `hooks/hooks.json:16-40 (branch only) · git show origin/main:hooks/hooks.json (SessionStart alone) · ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/ (no hooks/, no tools/wall.py)`
- **CLOSE-6 (ship-walk) and CLOSE-7 (round record) enforcement: 'detected'.**<br>Nothing detects. tools/check_trail.py is the only machine that reads the close lane, and a full-text scan finds no invocation anywhere outside tests/test_check_trail.py — no check_cmd, no CI step, no manifest key, no shell caller, and closing.md never names it. Its own docstring closes the door: 'advisory-tier: never wired into check_cmd, CI, or the manifest' (:16). 'detected' asserts an observation that no run ever makes; the accurate reading is 'a detector exists that no procedure runs'. (The excavation does say this in guard_site — the label still overstates.) `tools/check_trail.py:16 · tools/check_trail.py:112-137 · full-tree scan: only tests/test_check_trail.py imports it`
- **State 'epic-finished-unclosed': 'The transient state the sweep disposes of on its next tick.'**<br>Transient only when the epic's board Status is `Ready`. The sweep's item loop skips everything else — `if _fv_name(item.get("status")) != "Ready": continue` (tools/epic_gate.py:1136) is the only path to `_process_epic` (:1146), and the module docstring says so ('for each **Ready** epic', :4-7). A finished epic parked anywhere but Ready — the cord-pull, a Blocked epic, an epic never flipped — sits in this state indefinitely. The living map records exactly that case: epic #277 'stays **OPEN** on its named close condition … this epic never flips Ready, so it never self-closes', and it was closed attended by the human a day later. `tools/epic_gate.py:1136, :1146, :4-7 · 04 projects/factory/architecture/factory-map.md:124-125`
- **Disagreement #3's stated consequence: 'The direct consequence for this lane: a release cut built by the pipeline edits `.claude-plugin/plugin.json`, and that implement stage would be denied.'**<br>Asserted flatly; the source it draws on states it conditionally and marks it unverified. The it-30 ship-walk wrote: '**If the plugin were installed for `yr-factory` on yr-host**, walls would fire inside the runner's cold stages. Fail-dangerous, and unverified from the session.' The missing-guard finding is real and confirmed (in_scope() at tools/wall.py:48-72 has zero callers; dev-runner.sh:46 exports YR_MACHINERY=1; hooks/deliver.sh:21 honours it, wall.py never reads it) — but whether a pipeline release cut would actually be denied depends on a host install state nobody has checked. `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications (ship-walk bullet 2) · tools/wall.py:48-72 (no callers) · tools/dev-runner.sh:46 · hooks/deliver.sh:21`
- **Gap: 'the living map already records this as a *standing failure mode of the walk*: three consecutive walks reported a release as owed that had already shipped, and one reported shipped what was owed.'**<br>The first half is verbatim-correct; the second half inverts what the map says. The map's only counter-example runs the other way: 0.9.15 'was **found owed** at the it-27 ship-walk and shipped the same day — read off `plugin.json` at tip rather than a closing report, the standing failure mode above firing for once in the direction that actually owed work.' That is a walk getting it RIGHT about an owed release, not a walk reporting shipped what was owed. No walk of that kind is recorded. `04 projects/factory/architecture/factory-map.md:32 (§ 2 Mechanism map, the release train)`
- **Gap: tools/check_trail.py 'is named by no procedure: closing.md does not mention it.'**<br>The closing.md half is exactly right and is the load-bearing point. But 'named by no procedure' overshoots: attended-lane.md:21 names it as the lane's detector ('violations are **detectable** (`tools/check_trail.py` verifies presence and grammar against the registry')), and tools/compile_slice.py:99 stamps it into the delivered SessionStart slice ('Lane mandates (the detector checks these — `tools/check_trail.py`)'). Neither invokes it — the accurate claim is 'no procedure invokes it, and the close reference never mentions it'. `skills/factory/references/attended-lane.md:21 · tools/compile_slice.py:99 · skills/factory/references/closing.md:60-136`
- **REL-3 precondition: 'The factory repo is armed: `auto_merge = true`, shadow window complete 2026-07-07' — cited `.yr/factory.toml:16`.**<br>Line 16 is blank. `auto_merge = true` is line 15; the arming comment with the 2026-07-07 date is :11-14. The transition's other citation (`.yr/factory.toml:11-16`) covers it, so the fact is fine — the pinpoint is not. `.yr/factory.toml:11-15 (line 16 blank)`

## Found by the verifier, missing from the excavation

- The self-close's real precondition — Status=Ready — is not in CLOSE-1's precondition list at all (it appears only as the 'trigger'). `sweep_epics` filters every board item with `if _fv_name(item.get("status")) != "Ready": continue` before the only call to `_process_epic`, and the docstring states 'Children of non-Ready epics are never visited'. This makes the cord-pull (un-Readying an epic) a permanent parking brake on the close transition, not just on promotion — and gives the lane a real terminal state the excavation has no node for: a finished, non-Ready epic that only an attended human close disposes of. Live precedent on the record: it-24's epic #277. `tools/epic_gate.py:1136, :1146, :1093 · 04 projects/factory/architecture/factory-map.md:124 ('this epic never flips Ready, so it never self-closes') and :125 (closed attended, the human's act)`
- DEBT-1 has an unreported third branch: `debt-repair`. When an open raise for (repo, anchor) already exists but is NOT on the board, the sweep item-adds it and writes Status=Backlog, returning `{'action': 'debt-repair', ...}`; when it is already fully on the board it touches nothing and returns nothing. That is a distinct transition ('raise exists off-board' → 'raise on board at Backlog') plus a distinct no-op state, neither of which appears in the excavation's state list or DEBT-1's postconditions. `tools/epic_gate.py:884-899 (existing-raise branch), :898 ('debt-repair')`
- The release ships the WHOLE tracked repo tree, not just skills/ — 'the plugin is the whole repo, so anything the *tracked tree* ships rides along to every consumer machine'. This is the reason `tools/wall.py` and `hooks/` would ship at all, and the excavation's REL-1/REL-2 never state it. It also carries four shipping-hygiene guards that ride check_cmd and CI on every release and belong in the release-scan picture: no tracked `.mcp.json` at root, none anywhere, no `mcpServers`/`mcp_servers` key in any `.claude-plugin/*.json`, and no mcp config file under `.claude-plugin/`. These are enforced (`git ls-files`-based, blocking), unlike four of the five arms the excavation does list. `tests/test_plugin_packaging.py:1-8 (docstring), :33-35, :38-41, :44-55, :58-62`
- REL-3 presents 'the human's click on an attended release PR' as a live alternative for THIS lane without noting that canon has since scoped it away for this repo. The factory repo is armed (`auto_merge = true`), and attended-lane.md scopes the human's merge click to 'the merge click on a repo **not yet armed** (the named transitional exception)' while making the attended hand-merge categorical for everything else. The two most recent releases — 0.9.15 (`a3de1d4`) and 0.10.0 (`a6b9990`) — were both attended hand-merges on an armed repo, recorded as such in the living map; both predate the 2026-08-06 ruling, so they are history, not violations, but the path they used is no longer sanctioned for the factory repo. `.yr/factory.toml:15 · skills/factory/references/attended-lane.md:55, :71, :76-84 · 04 projects/factory/architecture/factory-map.md:32`
- The counts file that the round record is supposed to read has no round dimension and no repo dimension. `STATE_DIR` defaults to a user-global `~/.cache/yr-attended` (shared across every repo, workspace and round), each row carries only `{ts, kind, session, act, detail}`, and `read_counts` filters by `session` alone. So even if the wall shipped and even if the two missing kinds existed, nothing maps counts to a round — 'the round's counts' is not computable from this file. The `counts` CLI compounds it: it prints raw rows with no aggregation, no `--since`, no per-kind tally, so YR-ROUND-RECORD's four numbers would still be hand-counted. `tools/wall.py:41 (STATE_DIR default), :84 (row shape), :91-107 (read_counts), :391-399 (counts CLI)`
- `_trail_has` is not the only dead condition machinery in the wall engine — `_gh_lines` (tools/wall.py:195-202), the bounded `gh` reader it depends on, is called only from `_trail_has` (:206) and therefore also has no live caller. Together with `in_scope` (:48-72, zero callers) and `board_check` (:325-357, zero callers), four of the module's helpers are unreachable in the shipped-as-built shape. That is the sharper form of disagreement #1: the release wall's condition has no satisfiable path because the entire trail-reading layer beneath it is orphaned, not merely one helper. `tools/wall.py:195-202, :205-211, :48-72, :325-357 (full-text scan of tools/, tests/, hooks/, *.md, *.toml)`
- The delivered slice — the surface that would carry the human's 'triggering the ship-walk at close' checkpoint — has a hard byte bound that fails closed: `compile_slice()` raises SystemExit when the compiled slice exceeds MAX_BYTES ('trim the tables, never raise the bound casually'), and deliver.sh converts that into the loud YR-DELIVERY-FAILURE banner instead of the slice. So the close-lane checkpoint's delivery path can be lost to canon growth alone, silently to everyone but the banner reader. Not reported in CLOSE-6's or the delivery discussion. `tools/compile_slice.py:120-123 · hooks/deliver.sh:43-46, :53-59`

---

WHAT MAKES A RELEASED VERSION VISIBLE TO AN INSTALLED PLUGIN (the exact chain, all verified against host state and the tree):  1. `.claude-plugin/plugin.json`'s `version` string is edited on a branch, together with the single canonical pin in `tests/test_plugin_packaging.py:26-28` (a two-file commit; the pair is gate-enforced by `tests/test_plugin_version_pin_canonical.py:52-77`). 2. That branch merges to `origin/main`. **main is the channel** — the marketplace `yellow-robots/skills` lists the factory with `{"source":"url","url":"https://github.com/yellow-robots/factory.git"}` and **no ref, tag or version field** (`~/.claude/plugins/marketplaces/yellow-robots/.claude-plugin/marketplace.json`). No second repo is edited to publish. 3. The consumer host's marketplace clone refreshes (the `yellow-robots` marketplace carries `autoUpdate: true` in `~/.claude/plugins/known_marketplaces.json`) and materializes a **version-named directory**: `~/.claude/plugins/cache/yellow-robots/factory/<version>/`, plus a row in `~/.claude/plugins/installed_plugins.json`. 4. The **version string is the visibility key**. Proof from this host, both directions: release commit `a6b9990` merged 2026-08-05 00:39:53 +0200 and `.../factory/0.10.0/.claude-plugin/plugin.json` was written 00:41:21 — 88 seconds later; whereas the four it-30 slice merges of 2026-08-07 08:28–08:50, which changed shipped content but not the version, produced **no new directory and no content refresh** — the installed 0.10.0 tree still lacks `records.toml`, `tools/check_trail.py`, `tools/compile_slice.py`, `hooks/` and `references/attended-lane.md`. The vault records the same for 0.9.14 (install stamped three minutes after its own merge). 5. Bundled reference files do not hot-reload: an installed version reaches a running session only at `/reload-plugins` or a fresh session (`closing.md > Skill-release block`).  Note the host's `installed_plugins.json` row for factory carries `gitCommitSha: 8ed0f97…`, which resolves to the original 2026-07-01 packaging commit whose plugin.json reads `0.1.0` — the sha field is stale on this host and is not a reliable content pointer; the version-keyed path is.  STATUS OF EVERYTHING IN THIS LANE, STATED PLAINLY: - Slices 1-4 of it-30 are on main and reach **no session** (no bump). The SessionStart delivery hook that would surface the human's checkpoints — including "triggering the ship-walk at close" — therefore never fires anywhere today. - Slice 5 (`tools/wall.py`, the PreToolUse+Stop registrations, the promote/board in-funnel checks) is **unmerged and failed independent review at 0 of 5 acceptance criteria**; `tools/wall.py` additionally carries uncommitted local edits in this worktree (the diff adds `in_scope()`, makes `_emit_event` best-effort, makes `read_counts` tolerant, and adds `board_check`). Nothing about it is factory behaviour; every wall claim in this document is "as built on an unmerged branch, rejected". - The pending 0.11.0 release lives on `origin/task/421-release`, which is **stacked on the rejected walls branch** — merging it as it stands would ship the walls, and it would be the first plugin refresh in this org's history to ship executable hooks rather than only prose. - The branch's own `AGENTS.md:110` and `README.md:26` already describe `tools/wall.py` as repo machinery; `origin/main` carries neither row. Read those rows as branch content, not as the factory's current map.  BOUNDARY WITH ADJACENT LANES: promote-to-Ready (closing.md §1) and the merge evaluator's own conditions (closing.md §2, `tools/merge_shadow.py`) are the input-gate and output-gate lanes; I traced them only where the release/close lane consumes them (REL-3, DEBT-2, DEBT-6). The `YR-TASK-GATES` promote wall (`tools/wall.py:360-376`) is the input gate's, not this lane's, and is excavated here only as the sibling that shows the release wall's condition machinery was buildable.  VAULT CITATIONS are read-only reads of `/srv/obsidian/vaults/obsidian`; nothing was written and the obsidian CLI was not run. The two vault docs that carry this lane's canon are `04 projects/factory/architecture/factory-map.md` (the living reference — § 2 Mechanism map holds the release train and the publication mechanism) and `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md` (the it-30 verification record, which independently reached several of the disagreements above through a cold ship-walk session).
