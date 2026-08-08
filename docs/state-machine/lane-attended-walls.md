<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The attended lane: canon map versus wall engine as built

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `S-CANON-AUTHORED` | The eight-row walled-act map (act -> condition -> stance) and the eleven-row mandatory step set exist as prose canon. This is the ONLY place the per-act conditions are stated. | Git-tracked file on origin/main (tip ff8f84e): skills/factory/references/attended-lane.md, merged by slice 3 (#424). | `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)` |
| `S-REGISTRY-DECLARED` | Every machine-parsed trail grammar the lane names has a registry row (marker, mode, fields, emitter, readers, surfaces), plus the single `YR-` marker constant. A record absent from it is unsanctioned. | records.toml on origin/main (data file, loaded by tools/records.py). | `records.toml:28-31 (the [marker] constant); records.toml:316-386 (the attended-lane rows); records.toml:387-391 ([lanes])` |
| `S-CANON-UNDELIVERED` | No session receives any of it. The installed factory plugin is 0.10.0, whose payload has no hooks/ directory, no attended-lane.md, no records.toml, no check_trail.py, no compile_slice.py, no wall.py. Nothing of iteration 30 reaches any session, agent or human. | Host filesystem: ~/.claude/plugins/installed_plugins.json (entry `factory@yellow-robots`, version 0.10.0, installPath ~/.claude/plugins/cache/yellow-robots/factory/0.10.0) and that cache directory's contents (observed: no `hooks/`, no `tools/wall.py`, references/ has no attended-lane.md). | `.claude-plugin/plugin.json:5 ("version": "0.10.0"); observed listing of ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/` |
| `S-CHECKOUT-STALE` | The shared workspace checkout that operator commands are actually run from (/opt/yellow-robots/factory) sits at a6b9990, four commits behind origin/main — it does not even contain the four MERGED it-30 slices (no hooks/, no records.toml, no attended-lane.md, no check_trail.py, no compile_slice.py). | Git ref file /opt/yellow-robots/factory/.git/refs/heads/main = a6b9990a6695f7c328331b5cff1abed12b3b778a; observed directory listing of that checkout. | `/opt/yellow-robots/factory/.git/refs/heads/main (a6b9990 = "attended: skill 0.10.0 — the write-surface canon reaches sessions (#396) (#414)"); `git log a6b9990..origin/main` = 4 commits (#422,#423,#424,#425)` |
| `S-WALLS-UNMERGED` | The whole wall engine and its registrations exist only on the unmerged branch task/420-walls (HEAD dc67cbb): tools/wall.py (new file), the PreToolUse + Stop blocks in hooks/hooks.json, the promote-act wall call in tools/promote.sh, and _attended_wall in tools/board_plumbing.py. origin/main's hooks/hooks.json carries SessionStart only. | Git branch task/420-walls in this worktree; `git diff --name-status origin/main HEAD` = A tools/wall.py, A tests/test_wall.py, M hooks/hooks.json, M tools/promote.sh, M tools/board_plumbing.py, M tools/dev-runner.sh, M tools/epic_gate.py, M tests/conftest.py, M AGENTS.md, M README.md. | `git show origin/main:hooks/hooks.json (SessionStart only); hooks/hooks.json:17-40 (the branch's PreToolUse+Stop blocks)` |
| `S-WALL-UNCOMPILABLE` | The uncommitted working-tree edit to tools/wall.py embeds a literal NUL byte (0x00) at line 351, inside `out.stdout.split("\x00")` in the newly added board_check(). Python refuses to compile the module: `SyntaxError: source code cannot contain null bytes`. As it sits on disk, wall.py cannot be imported OR executed at all — not by the hook, not by promote.sh, not by the test suite. | Uncommitted working-tree file tools/wall.py (git status: ` M tools/wall.py`); byte offset 18218. The committed HEAD copy has zero NUL bytes. | `tools/wall.py:351 (observed: `python3 tools/wall.py counts` -> SyntaxError, RC=1); `git show HEAD:tools/wall.py` contains 0 NUL bytes` |
| `S-SESSION-QUIET` | A session that has attempted no walled act: no rows for its session_id in the counts ledger. close_check returns None and the session closes silently. | Absence of rows keyed by session_id in $YR_WALL_STATE/counts.jsonl (default ~/.cache/yr-attended/counts.jsonl). | `tools/wall.py:41 (STATE_DIR); tools/wall.py:277-280 (`if not events: return None`)` |
| `S-SESSION-REFUSED` | A session carrying one or more `refusal` rows for an act. Every refusal is permanently unresolved except crossing-file, because `pass` is emitted at exactly one site. | JSONL rows {ts, kind:"refusal", session, act, detail} appended to $YR_WALL_STATE/counts.jsonl. | `tools/wall.py:77-88 (_emit_event); tools/wall.py:261 (the refusal row); tools/wall.py:256 (the ONLY `pass` emitter)` |
| `S-SESSION-CLOSE-BLOCKED` | The Stop hook has refused this session's close once; a `close-block` row is on the ledger and the block reason names each refused act. | JSONL row {kind:"close-block"} in $YR_WALL_STATE/counts.jsonl, plus the returned {"decision":"block"} JSON to the harness (transient). | `tools/wall.py:292-299` |
| `S-SESSION-CLOSE-OVERRIDDEN` | A second consecutive close with no newer refusal: the close proceeds and a `close-override` row records it. Terminal — nothing ever leaves it. | JSONL row {kind:"close-override"} in $YR_WALL_STATE/counts.jsonl. | `tools/wall.py:288-291 (observed in probe: close 1 -> block, close 2 -> None, kinds = [...,'close-block','close-override'])` |
| `S-CALLER-MACHINERY` | A board-writing caller that has DECLARED itself machinery, so the in-funnel board wall passes it untouched. The runner exports it; the epic gate setdefaults it; the pytest suite sets it autouse for every test. | Process environment variable YR_MACHINERY. | `tools/dev-runner.sh:46 (`export YR_MACHINERY=1`); tools/epic_gate.py:72 (`os.environ.setdefault("YR_MACHINERY", "1")`); tests/conftest.py:21-33` |
| `S-CALLER-ATTENDED` | A board-writing caller running under a Claude session (CLAUDECODE set) with no machinery declaration and no escape: the in-funnel board wall evaluates YR-BOARD-FLIP on the item's issue trail before the write. | Process environment: CLAUDECODE set, YR_MACHINERY and YR_BOARD_WALL_OFF unset. | `tools/board_plumbing.py:126-129` |
| `S-CALLER-UNWALLED-SHELL` | A board-writing caller with CLAUDECODE unset — a plain terminal, cron, or any non-Claude process. The in-funnel board wall returns immediately and writes with no record check at all. | Process environment: CLAUDECODE unset. | `tools/board_plumbing.py:128-129 (`if not os.environ.get("CLAUDECODE"): return`)` |
| `S-BOARD-WALL-OFF` | The named single-purpose escape hatch: an environment flag that disables the in-funnel board wall entirely for that process. It appears in no canon document. | Process environment variable YR_BOARD_WALL_OFF. | `tools/board_plumbing.py:126 (`or os.environ.get("YR_BOARD_WALL_OFF")`); tests/test_wall.py:219-226` |
| `S-TASK-PRE-PROMOTE` | A standalone Task, open, on the board, not yet Ready — the state the promote act leaves from. | GitHub issue state + the Projects v2 item's Status field on the shared "Yellow Robots — Dev" board (read through tools/board_plumbing.py read-issue). | `tools/promote.sh:49-62` |
| `S-TASK-HALF-PROMOTED` | A real, reachable state with no exit: promote.sh has posted the YR-PROMOTED comment to the trail and then died on the board write, because the in-funnel board wall refused the Status flip. The trail says promoted; the board never moved. | Split across two surfaces: a YR-PROMOTED comment on the issue trail, and an unchanged Status field on the Projects item. | `tools/promote.sh:78-81 (comment first, then `_board set-field ... \|\| die "promotion record posted, but the Status=Ready write failed"`); tools/board_plumbing.py:160 (_attended_wall raises inside set_field)` |
| `S-DESIGN-ACTIVE` | The governing design's lifecycle status, the one wall condition the engine actually resolves. Read from the vault filesystem, not the MCP server. | YAML frontmatter key `status` in a vault doc under $YR_VAULT_ROOT (default /srv/obsidian/vaults/obsidian), located by a wikilink in the issue body that must contain `/iterations/`. | `tools/wall.py:214-225 (_design_status_from_body); tools/wall.py:42 (VAULT_ROOT)` |
| `S-COUNTS-LEDGER` | The round record's declared raw material: one append-only JSONL file holding every refusal / pass / close-block / close-override across every session and every repo on the host. No rotation, no per-repo scoping; only `wall.py counts` and close_check read it. | $YR_WALL_STATE/counts.jsonl, default ~/.cache/yr-attended/counts.jsonl. | `tools/wall.py:41, 83-88, 91-107, 391-399` |
| `S-LANE-MANDATES` | The detector's data: four lanes with their mandated records (design/epic/standalone/close). YR-BOARD-FLIP, YR-HUMAN-INSTRUCTION and YR-ESCALATION belong to no lane, so the detector never checks the records the walls most depend on. | The [lanes] table in records.toml, read by tools/check_trail.py. | `records.toml:387-391; tools/check_trail.py:11-13 ("the lane -> mandated-records mapping is DATA in records.toml")` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `S-CANON-AUTHORED` → `S-CANON-AUTHORED (slice injected into one session's context)` | The Claude Code harness's SessionStart hook runner, executing hooks/deliver.sh, which shells out to tools/compile_slice.py | ⚠️ **unenforced** | hooks/hooks.json:3-16 (SessionStart matcher) and hooks/deliver.sh:21 (machinery exemption). MERGED to origin/main but UNREACHABLE: the released plugin is 0.10.0 and its installed payload contains no hooks/ directory, so this hook never fires anywhere. |
| 2 | `S-CANON-UNDELIVERED` → `canon delivered to sessions (0.11.0)` | A human, or an attended session under the closing.md release block | ⚠️ **unenforced** | None. The release scan is a prose checklist in closing.md; no code runs it. tools/wall.py's `release-edit` rule would DENY the very edit that ships it (any write to a path ending `.claude-plugin/plugin.json`, unconditionally), so if 0.11.0 ever installs, the next version bump is refused with no satisfiable path. |
| 3 | `attended agent about to run a merge command` → `refused (deny) + refusal row` | Attended agent (Claude session), intercepted by the PreToolUse hook | *partial* | tools/wall.py:classify() line 121 -> decide() line 262, reached via hooks/hooks.json:17-40 PreToolUse matcher `Bash\|Write\|Edit\|mcp__obsidian__vault_patch`. UNMERGED (branch only) and, in the working tree, unreachable at all (S-WALL-UNCOMPILABLE). |
| 4 | `attended agent about to merge` → `merge proceeds, no record, no refusal` | Attended agent (Claude session) | ⚠️ **unenforced** | None on this path. classify() has no branch for `gh api`, GraphQL, or a local `git merge` + push of the merge commit. |
| 5 | `attended agent about to push` → `refused (deny) + refusal row` | Attended agent (Claude session) | *partial* | tools/wall.py:classify() lines 123-132, via the PreToolUse matcher. Unmerged; branch-blind (never reads HEAD or the remote's default branch). |
| 6 | `attended agent about to push a branch that is not a task/ branch` → `refused (deny) + refusal row — with NO satisfiable path` | Attended agent (Claude session) | *partial* | tools/wall.py:decide() lines 244-268 — the condition site the canon names does not exist. |
| 7 | `attended agent about to push` → `push proceeds, silently` | Attended agent (Claude session) | ⚠️ **unenforced** | tools/wall.py:128-131. A pass-through, not a guard; the ownership half of the canon's condition is unevaluated. |
| 8 | `attended agent about to write a board field` → `refused (deny) + refusal row — with NO satisfiable path` | Attended agent (Claude session) | *partial* | tools/wall.py:classify() line 133 -> decide() (unconditional). board_check() at tools/wall.py:325 is the check that exists but is never called; its docstring claims two callers ("the funnel shells out to this, and the hook's raw-evasion classification resolves the same item") — neither exists in the tree. |
| 9 | `attended agent about to write a board field` → `the field is written, no record, no refusal` | Attended agent (Claude session) | ⚠️ **unenforced** | None. The hook half matches only the lawful funnel call that the funnel itself already judges. |
| 10 | `S-CALLER-ATTENDED` → `write refused (RuntimeError) or write performed` | Any Python caller of tools/board_plumbing.set_field — the runner, the epic gate, tools/promote.sh, tools/watch_build.sh, an attended session | *partial* | tools/board_plumbing.py:_attended_wall (line 112), called from set_field (line 160) — the single field-write funnel, so it IS on the path every funnel caller takes. Unmerged. Open on two paths: CLAUDECODE-unset shells, and raw `gh project item-edit`. |
| 11 | `attended agent about to stamp a vault doc active/superseded` → `refused (deny) + refusal row — with NO satisfiable path` | Attended agent (Claude session) via the Obsidian MCP | *partial* | tools/wall.py:classify() lines 154-160 -> decide() (unconditional). The MCP frontmatter row it intercepts is the documentation model's SANCTIONED path for a frontmatter set. |
| 12 | `attended agent about to edit a manifest` → `refused (deny) + refusal row — with NO satisfiable path` | Attended agent (Claude session) | *partial* | tools/wall.py:classify() lines 149-150 -> decide() (unconditional). |
| 13 | `attended agent about to bump the plugin version` → `refused (deny) + refusal row — with NO satisfiable path` | Attended agent (Claude session) | *partial* | tools/wall.py:classify() lines 151-152 -> decide() (unconditional). |
| 14 | `attended agent about to file a crossing` → `the issue is filed; a `pass` row lands` | Attended agent (Claude session) | *partial* | tools/wall.py:decide() lines 253-257. This is the one act of the eight whose canon condition is actually evaluated and satisfiable. |
| 15 | `attended agent about to file a crossing` → `refused (deny) + refusal row` | Attended agent (Claude session) | *partial* | tools/wall.py:decide() lines 253-260. |
| 16 | `attended agent about to write the vault` → `refused (deny) for Write/Edit; PROCEEDS for every other write path` | Attended agent (Claude session) | *partial* | tools/wall.py:classify() lines 145-148 (Write/Edit only). The shell filesystem paths — the exact class the round's own exhibit was about — reach no guard. |
| 17 | `attended agent about to commit` → `refused (deny) for `-m`/`-F` without the trailer; PROCEEDS for -am/-qm/--amend` | Attended agent (Claude session) | *partial* | tools/wall.py:_classify_commit (line 177), reached from classify() line 142. |
| 18 | `attended agent running a read-only command` → `refused (deny) + refusal row` | Attended agent (Claude session) | *partial* | tools/wall.py:121. |
| 19 | `any wall decision` → `S-COUNTS-LEDGER grown by one row` | tools/wall.py itself (inside the hook process) | detected | tools/wall.py:_emit_event (line 77). No machine reads it into a round record; only `wall.py counts` prints it and close_check consumes it. |
| 20 | `S-SESSION-REFUSED` → `S-SESSION-CLOSE-BLOCKED` | The Claude Code harness's Stop hook, executing `wall.py close` | *partial* | tools/wall.py:close_check (line 273), registered at hooks/hooks.json:28-40 with no matcher (all Stop events). Unmerged. |
| 21 | `S-SESSION-CLOSE-BLOCKED` → `S-SESSION-CLOSE-OVERRIDDEN` | The Stop hook, on the session's second close attempt | detected | tools/wall.py:close_check lines 288-291. Terminal state — no transition leaves it. |
| 22 | `S-TASK-PRE-PROMOTE` → `refused, writing nothing` | tools/promote.sh (operator command), shelling out to `wall.py promote-check` | *partial* | tools/wall.py:promote_check (line 360), called at tools/promote.sh:68 — on the path this operator command actually takes. Bypassed entirely by flipping Status through any other route. |
| 23 | `S-TASK-PRE-PROMOTE` → `S-TASK-HALF-PROMOTED` | tools/promote.sh run inside an attended Claude session | ⚠️ **unenforced** | None guards the ordering. The board wall at tools/board_plumbing.py:160 fires after the comment has already landed. |
| 24 | `runner/epic-gate start` → `S-CALLER-MACHINERY` | tools/dev-runner.sh and tools/epic_gate.py, declaring themselves | **prevented** | tools/board_plumbing.py:126 — the only site that reads the declaration for a wall decision. |
| 25 | `a trail in any lane state` → `findings printed, exit 1 (or clean, exit 0)` | An attended session running tools/check_trail.py at ship-walk or census time | detected | tools/check_trail.py — advisory by declaration; nothing calls it automatically. |
| 26 | `S-COUNTS-LEDGER` → `YR-ROUND-RECORD on the epic/task trail` | The closing attended session (a human or agent typing a comment) | ⚠️ **unenforced** | None. The close check does not demand it (T-CLOSE-BLOCK); the detector finds its absence only if someone runs check_trail.py on the close lane. |
| 27 | `round in progress` → `YR-SHIP-WALK on the epic/task trail` | The ship-walk session (attended) | ⚠️ **unenforced** | None. |
| 28 | `an agent at a severe-implication decision surface` → `YR-ESCALATION on the trail` | The attended agent, at its own discretion (the severity valve) | ⚠️ **unenforced** | None. Purely agent-initiated prose. |
| 29 | `a design doc under review` → `YR-DESIGN-REVIEW / YR-DESIGN-FIT / YR-ACCEPT typed into the doc` | The independent cold reviewer, the architect, and the accepting session — each typing a line into the vault doc | detected | tools/check_trail.py (design lane) only — advisory, manual, and absent from both the installed plugin and the workspace checkout. |
| 30 | `any walled act` → `the act proceeds unrefused` | The Claude Code harness, on a non-zero hook exit | ⚠️ **unenforced** | tools/wall.py:main lines 400-407 — the only try/except, and it covers stdin parsing only. |

### Detail

#### 1. `S-CANON-AUTHORED` → `S-CANON-AUTHORED (slice injected into one session's context)`

`T-DELIVER`

- **Actor:** The Claude Code harness's SessionStart hook runner, executing hooks/deliver.sh, which shells out to tools/compile_slice.py
- **Trigger:** Session lifecycle event matching `startup\|clear\|compact\|resume`
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** hooks/hooks.json:3-16 (SessionStart matcher) and hooks/deliver.sh:21 (machinery exemption). MERGED to origin/main but UNREACHABLE: the released plugin is 0.10.0 and its installed payload contains no hooks/ directory, so this hook never fires anywhere.
- **Records:** `none registered`, `the failure banner literal `YR-DELIVERY-FAILURE:` — a YR- token with no records.toml row (hooks/deliver.sh:44)`
- **Preconditions:** Delivery is unconditional — independent of the session recognising the work as factory-driven, on startup, clear, compact and resume `[canon-only: skills/factory/references/attended-lane.md > Delivery, the slice, and the close]`<br>YR_MACHINERY must be unset; a cold pipeline stage is exempt and gets no attended canon `[code: hooks/deliver.sh:21]`<br>The plugin must expose hooks/hooks.json with a SessionStart block — merged to origin/main, but ABSENT from the installed 0.10.0 payload, so the precondition is unmet on every real session today `[code: hooks/hooks.json:3-16; observed: ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/ has no hooks/ directory]`
- **Postconditions:** A JSON object {hookSpecificOutput:{hookEventName:"SessionStart", additionalContext:<slice>}} is printed; the slice is compiled verbatim from attended-lane.md's two tables, records.toml's lanes, and SKILL.md's router rows, bounded at 12000 bytes `[code: hooks/deliver.sh:27-37; tools/compile_slice.py:80-124]`<br>A runtime Position block is appended: UTC timestamp, `gh repo view` repo, open PRs, and up to 12 board rows for this repo `[code: hooks/deliver.sh:61-82]`<br>Canon requires the slice to render "the step set WITH POSITION" and the round's next step (the state-machine view). Nothing computes a position within the step set — the step table is emitted verbatim and the appended Position block is repo-level (PRs/board rows) only `[canon-only: skills/factory/references/attended-lane.md > Delivery, the slice, and the close]`<br>Every failure path emits a loud non-blocking banner and exits 0 `[code: hooks/deliver.sh:43-59, 84-85]`

#### 2. `S-CANON-UNDELIVERED` → `canon delivered to sessions (0.11.0)`

`T-RELEASE-BUMP`

- **Actor:** A human, or an attended session under the closing.md release block
- **Trigger:** The skill-release block: version bump in .claude-plugin/plugin.json + the release scan
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. The release scan is a prose checklist in closing.md; no code runs it. tools/wall.py's `release-edit` rule would DENY the very edit that ships it (any write to a path ending `.claude-plugin/plugin.json`, unconditionally), so if 0.11.0 ever installs, the next version bump is refused with no satisfiable path.
- **Records:** `none — the "freeze checks' records" the map names have no registry row and no emitter anywhere in the tree`
- **Preconditions:** The release scan must be fully green (no dangling router row, no orphan reference, SKILL.md < 500 lines, descriptions agree, consumer scan green) `[canon-only: skills/factory/references/closing.md > Skill-release block]`<br>The walled-act map demands the freeze checks' RECORDS for a skill release, fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`
- **Postconditions:** 0.11.0 is owed and not shipped; nothing this round built is live `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > What shipped, and what did not]`

#### 3. `attended agent about to run a merge command` → `refused (deny) + refusal row`

`T-ACT-HAND-MERGE`

- **Actor:** Attended agent (Claude session), intercepted by the PreToolUse hook
- **Trigger:** A Bash tool call whose shlex-joined tokens match `\bgh\b.*\bpr\b.*\bmerge\b`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() line 121 -> decide() line 262, reached via hooks/hooks.json:17-40 PreToolUse matcher `Bash\|Write\|Edit\|mcp__obsidian__vault_patch`. UNMERGED (branch only) and, in the working tree, unreachable at all (S-WALL-UNCOMPILABLE).
- **Records:** `counts.jsonl {kind:"refusal", act:"hand-merge"} — unregistered JSONL shape, no records.toml row`
- **Preconditions:** Categorical — no record licenses it; merges execute through the evaluator. Stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>Code matches the regex on the joined token string only; no condition is read, which AGREES with the canon's categorical stance `[code: tools/wall.py:121-122]`
- **Postconditions:** permissionDecision=deny with reason `YR-WALL [hand-merge] — categorical: an attended hand-merge is refused outright...` (probe-observed) `[code: tools/wall.py:231, 262-268]`<br>A refusal row lands in counts.jsonl (best-effort; swallowed on OSError) `[code: tools/wall.py:77-88, 261]`

#### 4. `attended agent about to merge` → `merge proceeds, no record, no refusal`

`T-ACT-HAND-MERGE-EVADED`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A merge issued through any surface other than `gh pr merge`
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None on this path. classify() has no branch for `gh api`, GraphQL, or a local `git merge` + push of the merge commit.
- **Preconditions:** Categorical prohibition on the ACT, not on one spelling of it `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>classify() returns None for `gh api -X PUT repos/o/r/pulls/1/merge` and for `gh api graphql -f query=mutation{mergePullRequest}` (both probe-observed) `[code: tools/wall.py:114-144]`
- **Postconditions:** The tool call proceeds; nothing is written to counts.jsonl; the close check sees no activity `[code: tools/wall.py:244-250 (decide returns None on an unclassified call)]`

#### 5. `attended agent about to push` → `refused (deny) + refusal row`

`T-ACT-PUSH-MAIN`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Bash `git ... push` whose argument tail matches `(^\|\s)(origin\s+)?(main\|master)(\s\|:\|$)` or contains `:main`/`:master`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() lines 123-132, via the PreToolUse matcher. Unmerged; branch-blind (never reads HEAD or the remote's default branch).
- **Records:** `counts.jsonl {kind:"refusal", act:"push-main"}`
- **Preconditions:** `main`: categorical — the branch protection's client-side voice; stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The crossing pinned exactly this: pushing main categorically refused, the session's own task/<n>-<slug> lawful, any other shared branch requires the human-instruction record `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/02-crossing-rulings.md > The shared-branch-push condition]`<br>Text-matched only. Probe-observed: `git push origin main` -> push-main; `git push origin HEAD:main` -> push-main; `git push origin HEAD:refs/heads/main` -> push-shared (wrong rule named); bare `git push` -> None (LAWFUL, even when HEAD is main); `git push --force` with no refspec -> push-shared `[code: tools/wall.py:123-132]`
- **Postconditions:** deny with `YR-WALL [push-main] — categorical: pushing main is refused — the branch protection's client-side voice` `[code: tools/wall.py:232, 262-268]`

#### 6. `attended agent about to push a branch that is not a task/ branch` → `refused (deny) + refusal row — with NO satisfiable path`

`T-ACT-PUSH-SHARED`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Bash `git ... push` whose tail names neither main/master nor a `task/<digits>-<slug>` token
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:decide() lines 244-268 — the condition site the canon names does not exist.
- **Records:** `counts.jsonl {kind:"refusal", act:"push-shared"}`
- **Preconditions:** Condition: requires `YR-HUMAN-INSTRUCTION` — the record of the human's explicit instruction; stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The registry names tools/wall.py as a READER of YR-HUMAN-INSTRUCTION for exactly this condition `[canon-only: records.toml:394-401]`<br>The code reads no record. decide() has no branch for push-shared: it falls straight through to the unconditional refusal. `_trail_has` — the only helper that could read the record — is defined and called by nothing in the tree `[code: tools/wall.py:244-268; tools/wall.py:205-211 (dead); verified by whole-tree search: no caller]`
- **Postconditions:** deny with a reason naming a record the engine can never check; posting YR-HUMAN-INSTRUCTION changes nothing (probe-observed deny) `[code: tools/wall.py:233, 261-268]`

#### 7. `attended agent about to push` → `push proceeds, silently`

`T-ACT-PUSH-OWN-TASK-BRANCH`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A push whose text contains `task/<digits>-<slug>`, or `-u origin task/`, or is a bare `git push`
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tools/wall.py:128-131. A pass-through, not a guard; the ownership half of the canon's condition is unevaluated.
- **Preconditions:** Lawful case: THE SESSION'S OWN `task/<n>-<slug>` branch `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The code never resolves the session's branch. ANY `task/<digits>-<slug>` token in the argv passes — probe-observed: `git push origin task/999-not-mine` -> None `[code: tools/wall.py:128-131]`
- **Postconditions:** decide() returns None; no row, no decision, the harness proceeds `[code: tools/wall.py:131, 247-249]`

#### 8. `attended agent about to write a board field` → `refused (deny) + refusal row — with NO satisfiable path`

`T-ACT-BOARD-WRITE-HOOK`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Bash command containing both `board_plumbing.py` and `set-field`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() line 133 -> decide() (unconditional). board_check() at tools/wall.py:325 is the check that exists but is never called; its docstring claims two callers ("the funnel shells out to this, and the hook's raw-evasion classification resolves the same item") — neither exists in the tree.
- **Records:** `counts.jsonl {kind:"refusal", act:"board-write"}`
- **Preconditions:** Condition: a `YR-BOARD-FLIP` record on the trail before the flip; runner and epic-gate callers exempt; stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The hook half reads no trail and knows no exemption. decide() has no board-write branch — the uncommitted edit DELETED the stub that stood there. board_check(), added uncommitted at line 325 to evaluate exactly this condition, is called by nothing `[code: tools/wall.py:244-268; `git diff tools/wall.py` (removes the board-write block from decide); tools/wall.py:325-357 (uncalled)]`
- **Postconditions:** deny with `YR-WALL [board-write] — a board Status/Reason write requires the YR-BOARD-FLIP record ... first` — and posting that record does not lift it (probe-observed deny) `[code: tools/wall.py:234, 261-268]`

#### 9. `attended agent about to write a board field` → `the field is written, no record, no refusal`

`T-ACT-BOARD-WRITE-RAW`

- **Actor:** Attended agent (Claude session)
- **Trigger:** `gh project item-edit ...` or a raw `gh api graphql` mutation instead of the board_plumbing funnel
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. The hook half matches only the lawful funnel call that the funnel itself already judges.
- **Preconditions:** The canon walls the ACT (a board Status/Reason write), not one invocation spelling `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>classify() returns None for `gh project item-edit --id X --project-id P --field-id F --single-select-option-id O` (probe-observed) `[code: tools/wall.py:133-134]`
- **Postconditions:** The write lands with no YR-BOARD-FLIP anywhere; and because YR-BOARD-FLIP is in no lane, the detector will not find the omission either `[code: records.toml:387-391 ([lanes] contains no YR-BOARD-FLIP); tools/check_trail.py:11-13]`

#### 10. `S-CALLER-ATTENDED` → `write refused (RuntimeError) or write performed`

`T-ACT-BOARD-WRITE-FUNNEL`

- **Actor:** Any Python caller of tools/board_plumbing.set_field — the runner, the epic gate, tools/promote.sh, tools/watch_build.sh, an attended session
- **Trigger:** set_field(gh, item_id, field_id, opt) is called
- **Enforcement:** *partial* · **Guard site:** tools/board_plumbing.py:_attended_wall (line 112), called from set_field (line 160) — the single field-write funnel, so it IS on the path every funnel caller takes. Unmerged. Open on two paths: CLAUDECODE-unset shells, and raw `gh project item-edit`.
- **Records:** `reads YR-BOARD-FLIP (records.toml:346-353, mode=prefix); emits none`
- **Preconditions:** Runner and epic-gate callers exempt — their records are their own `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>Exemption is by DECLARATION: pass immediately if YR_MACHINERY or YR_BOARD_WALL_OFF is set; pass immediately if CLAUDECODE is NOT set; otherwise read the item's issue body + last 100 comments over GraphQL and require a line starting `YR-BOARD-FLIP:` at column 0 `[code: tools/board_plumbing.py:126-147]`<br>Every unevaluable path refuses, naming what it could not read (fail-closed, and this one is real: the bare `except Exception` re-raises as a REFUSED message) `[code+canon: tools/board_plumbing.py:148-152; skills/factory/references/attended-lane.md > The lane protects itself, and its limits are named]`
- **Postconditions:** On refusal: RuntimeError before the `gh project item-edit` argv is built — nothing is written `[code: tools/board_plumbing.py:160-166]`<br>The escape hatch YR_BOARD_WALL_OFF=1 disables the wall entirely and appears in no canon document `[code: tools/board_plumbing.py:126]`

#### 11. `attended agent about to stamp a vault doc active/superseded` → `refused (deny) + refusal row — with NO satisfiable path`

`T-ACT-LIFECYCLE-STAMP`

- **Actor:** Attended agent (Claude session) via the Obsidian MCP
- **Trigger:** mcp__obsidian__vault_patch with targetType=frontmatter, target=status, content in (active, superseded)
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() lines 154-160 -> decide() (unconditional). The MCP frontmatter row it intercepts is the documentation model's SANCTIONED path for a frontmatter set.
- **Records:** `counts.jsonl {kind:"refusal", act:"lifecycle-stamp"}; the three records it names (records.toml:316-345) are read by nothing here`
- **Preconditions:** Condition: the accept act's provenance — `YR-ACCEPT` in the accepting doc, with `YR-DESIGN-REVIEW` and `YR-DESIGN-FIT` present; stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The code never opens the doc. decide() has no lifecycle-stamp branch; it denies on classification alone (probe-observed) `[code: tools/wall.py:154-160; tools/wall.py:244-268]`
- **Postconditions:** deny naming three records it never reads. The accept act (step 4 of the eleven this same round reified) therefore has no path through its own wall `[code: tools/wall.py:235; skills/factory/references/attended-lane.md > The mandatory step set (reified — the existing mandates, not new ones)]`

#### 12. `attended agent about to edit a manifest` → `refused (deny) + refusal row — with NO satisfiable path`

`T-ACT-ARMING-EDIT`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Write or Edit whose file_path ends `.yr/factory.toml` or contains `/.yr/factory.toml`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() lines 149-150 -> decide() (unconditional).
- **Records:** `counts.jsonl {kind:"refusal", act:"arming-edit"}`
- **Preconditions:** Condition: `YR-HUMAN-INSTRUCTION` attributing her decision — arming is decided exclusively by the human, executed only under that instruction; stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The registry names tools/wall.py the reader of that record for the arming condition `[canon-only: records.toml:394-401]`<br>The code reads no record and never inspects the edit: ANY manifest edit, in ANY repo, anywhere on disk, classifies as `arming-edit` (probe-observed on /home/me/personal/.yr/factory.toml). `auto_merge` is never mentioned in wall.py `[code: tools/wall.py:149-150; tools/wall.py:244-268]`
- **Postconditions:** deny with `YR-WALL [arming-edit] — arming is decided exclusively by the human...`; every unrelated manifest key (check_cmd, model, test_paths) is walled as arming `[code: tools/wall.py:236]`

#### 13. `attended agent about to bump the plugin version` → `refused (deny) + refusal row — with NO satisfiable path`

`T-ACT-RELEASE-EDIT`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Write or Edit whose file_path ends `.claude-plugin/plugin.json`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() lines 151-152 -> decide() (unconditional).
- **Records:** `counts.jsonl {kind:"refusal", act:"release-edit"}`
- **Preconditions:** Condition: the freeze checks' records (the release scan's results, recorded); stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>No record named `freeze check` exists in records.toml at all, so there is no grammar the wall could check `[canon-only: records.toml:35-401 (no such row)]`<br>The code reads nothing and denies on the path suffix alone (probe-observed on /anything/.claude-plugin/plugin.json) `[code: tools/wall.py:151-152; tools/wall.py:244-268]`
- **Postconditions:** deny with `YR-WALL [release-edit] — a skill release requires the freeze checks' records`. Slice 6's central act is refused by slice 5 `[code: tools/wall.py:238]`

#### 14. `attended agent about to file a crossing` → `the issue is filed; a `pass` row lands`

`T-ACT-CROSSING-PASS`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Bash `gh issue create` whose resolved body matches `\*\*Source:\*\*.*(product-spec\|feature-rfc)`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:decide() lines 253-257. This is the one act of the eight whose canon condition is actually evaluated and satisfiable.
- **Records:** `counts.jsonl {kind:"pass", act:"crossing-file"} — the ONLY pass event the engine can ever emit`
- **Preconditions:** Condition: the governing design's `status` is `active` — resolved from the vault; unreadable or unresolvable refuses; stance fail-closed `[code+canon: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance); tools/wall.py:253-257]`<br>The body must carry a wikilink containing `/iterations/`; the doc is read off the filesystem at $YR_VAULT_ROOT and `^status:\s*(\S+)` extracted `[code: tools/wall.py:214-225]`
- **Postconditions:** decide() returns None (the call proceeds) and emits {kind:"pass", act:"crossing-file", detail:"design active"} — probe-verified end-to-end against the real vault doc 30-attended-lane-runner/01-attended-lane-runner.md `[code: tools/wall.py:253-257]`

#### 15. `attended agent about to file a crossing` → `refused (deny) + refusal row`

`T-ACT-CROSSING-REFUSE`

- **Actor:** Attended agent (Claude session)
- **Trigger:** Same, when the design resolves non-active, or the link/doc/body cannot be read
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:decide() lines 253-260.
- **Records:** `counts.jsonl {kind:"refusal", act:"crossing-file"}`
- **Preconditions:** Infrastructure failure is not condition failure: a wall that cannot evaluate a fail-closed act's condition refuses `[code+canon: skills/factory/references/attended-lane.md > The lane protects itself, and its limits are named; tools/wall.py:258-260]`<br>`--body-file` pointing at an unreadable path -> refuse naming what it could not read; a body with no /iterations/ wikilink -> `resolved status: unresolvable` -> refuse (both probe-observed) `[code: tools/wall.py:164-174; tools/wall.py:214-219; tools/wall.py:258-260]`<br>A crossing governed by a feature-RFC — the technical-rfc template's own example link `[[04 projects/yellow-robots/features/<slug>/feature-rfc]]` — carries no `/iterations/` segment and so is ALWAYS unresolvable, hence always refused `[code: tools/wall.py:215-217; skills/factory/templates/technical-rfc.md:29]`<br>A `gh issue create` with no `--body`/`--body-file` resolves to an empty body, matches nothing and is not classified at all `[code: tools/wall.py:171-174; tools/wall.py:141]`
- **Postconditions:** deny naming the resolved status `[code: tools/wall.py:255-260]`

#### 16. `attended agent about to write the vault` → `refused (deny) for Write/Edit; PROCEEDS for every other write path`

`T-ACT-VAULT-FS-WRITE`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Write or Edit whose file_path starts with VAULT_ROOT + os.sep
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:classify() lines 145-148 (Write/Edit only). The shell filesystem paths — the exact class the round's own exhibit was about — reach no guard.
- **Records:** `counts.jsonl {kind:"refusal", act:"vault-fs-write"}`
- **Preconditions:** Write-path class: off-table vault write is CATEGORICAL — the decision table names the sanctioned rows; stance fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The sanctioned rows are MCP vault_read / search_simple / vault_get_document_map / vault_write (create + whole-body) / vault_patch (section + frontmatter) and CLI rename/move/delete; the table offers NO filesystem row `[canon-only: skills/factory/references/documentation-model.md > Editing safely]`<br>Code intercepts only the Write and Edit TOOLS under VAULT_ROOT. Probe-observed unclassified: `sed -i ... /srv/obsidian/...`, `cp ... /srv/obsidian/...`, and every other shell write; `mcp__obsidian__vault_write` is not even in the PreToolUse matcher `[code: tools/wall.py:145-148; hooks/hooks.json:19 (matcher `Bash\|Write\|Edit\|mcp__obsidian__vault_patch`)]`
- **Postconditions:** deny with `...categorical: a filesystem vault write is off-table` on the tool path only `[code: tools/wall.py:239]`

#### 17. `attended agent about to commit` → `refused (deny) for `-m`/`-F` without the trailer; PROCEEDS for -am/-qm/--amend`

`T-ACT-COMMIT-UNTRAILED`

- **Actor:** Attended agent (Claude session)
- **Trigger:** A Bash `git ... commit` whose message text lacks `Co-Authored-By:`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:_classify_commit (line 177), reached from classify() line 142.
- **Records:** `counts.jsonl {kind:"refusal", act:"commit-untrailed"}`
- **Preconditions:** Write-path class: a commit minted ON THE HUMAN'S GIT IDENTITY without the standing trailer discipline — categorical, fail-closed `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The code never reads git identity (`user.name`/`user.email` appear nowhere in wall.py): every untrailered commit by anyone is walled `[code: tools/wall.py:177-190]`<br>Matched shapes are `-m`/`--message` (whitespace-anchored) and `-F`/`--file` (file read). Probe-observed unclassified: `git commit -am ...`, `git commit -qm ...`, `git commit --amend --no-edit`, and any editor-driven commit (deliberate, per the code comment) `[code: tools/wall.py:180-190]`
- **Postconditions:** deny with `...an attended commit carries the Co-Authored-By trailer naming the authoring model` `[code: tools/wall.py:240]`

#### 18. `attended agent running a read-only command` → `refused (deny) + refusal row`

`T-ACT-FALSE-POSITIVE`

- **Actor:** Attended agent (Claude session)
- **Trigger:** Any Bash command whose tokens satisfy `\bgh\b.*\bpr\b.*\bmerge\b` — e.g. `gh pr list --search merge` (probe-observed -> hand-merge)
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:121.
- **Records:** `counts.jsonl {kind:"refusal", act:"hand-merge"} (spurious)`
- **Preconditions:** The canon walls the merge ACT; nothing in it walls a read `[canon-only: skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)]`<br>The regex is order-only across the joined tokens, with no verb-position anchoring `[code: tools/wall.py:120-122]`
- **Postconditions:** A read is denied and a spurious `refusal` row enters the round's counts, which then blocks the session's close `[code: tools/wall.py:261; tools/wall.py:282-299]`

#### 19. `any wall decision` → `S-COUNTS-LEDGER grown by one row`

`T-COUNTS-EMIT`

- **Actor:** tools/wall.py itself (inside the hook process)
- **Trigger:** Every refusal, pass, close-block and close-override
- **Enforcement:** detected · **Guard site:** tools/wall.py:_emit_event (line 77). No machine reads it into a round record; only `wall.py counts` prints it and close_check consumes it.
- **Records:** `an unregistered JSONL row shape {ts, kind, session, act, detail} — no records.toml row exists for it`
- **Preconditions:** Every event lands in the counts where the round record reads them `[canon-only: skills/factory/references/attended-lane.md > Delivery, the slice, and the close]`<br>Bookkeeping is best-effort and silent: mkdir + append wrapped in try/except OSError, `pass` on failure — the uncommitted edit's central repair, because the unguarded form made the hook exit non-zero with no decision and (per the code's own statement) a PreToolUse hook that errors lets the call THROUGH `[code: tools/wall.py:77-88 (and `git diff tools/wall.py` — this guard is UNCOMMITTED)]`
- **Postconditions:** One JSON object per line in $YR_WALL_STATE/counts.jsonl; reads skip unparseable lines rather than raising (also uncommitted) `[code: tools/wall.py:91-107]`<br>The ledger is global: one file per host user, never scoped by repo, round, or epic; no rotation `[code: tools/wall.py:41, 85]`

#### 20. `S-SESSION-REFUSED` → `S-SESSION-CLOSE-BLOCKED`

`T-CLOSE-BLOCK`

- **Actor:** The Claude Code harness's Stop hook, executing `wall.py close`
- **Trigger:** The session attempts to conclude
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:close_check (line 273), registered at hooks/hooks.json:28-40 with no matcher (all Stop events). Unmerged.
- **Records:** `counts.jsonl {kind:"close-block"}`
- **Preconditions:** A session that executed a walled act OR EMITTED A MANDATED RECORD is refused a silent close while MANDATORY TRACES are missing (the refusal names each) `[canon-only: skills/factory/references/attended-lane.md > Delivery, the slice, and the close]`<br>The code knows nothing of mandated records. Its only "trace" notion is: a `refusal` row with no later `pass` row for the same act. Since `pass` is emitted at exactly one site (crossing-file, design active), every refusal on the other eight acts is permanently unresolvable — the block is unconditional after any refusal `[code: tools/wall.py:273-292; tools/wall.py:256]`<br>The docstring admits the reduction: "V1 traces" `[code: tools/wall.py:275-277]`
- **Postconditions:** Returns {"decision":"block", "reason":"YR-WALL [close] — this session was refused on: <acts>..."} and appends a close-block row (probe-observed) `[code: tools/wall.py:292-299]`<br>No mandated record (YR-SHIP-WALK, YR-ROUND-RECORD, YR-BOARD-FLIP, YR-TASK-GATES) is checked for at close `[code: tools/wall.py:273-299 (no registry read; `records` is not imported into this function)]`

#### 21. `S-SESSION-CLOSE-BLOCKED` → `S-SESSION-CLOSE-OVERRIDDEN`

`T-CLOSE-OVERRIDE`

- **Actor:** The Stop hook, on the session's second close attempt
- **Trigger:** A second consecutive close with no refusal newer than the last close-block
- **Enforcement:** detected · **Guard site:** tools/wall.py:close_check lines 288-291. Terminal state — no transition leaves it.
- **Records:** `counts.jsonl {kind:"close-override"}`
- **Preconditions:** A second consecutive close with traces unchanged proceeds loud and records the override `[code+canon: skills/factory/references/attended-lane.md > Delivery, the slice, and the close; tools/wall.py:288-291]`<br>"Unchanged" is implemented as `blocks[-1].ts >= max(unresolved.ts)` at one-second resolution `[code: tools/wall.py:288]`
- **Postconditions:** Returns None (close proceeds) and appends a close-override row naming the count of unresolved refusals (probe-observed) `[code: tools/wall.py:288-291]`<br>"Proceeds LOUD" is only the ledger row — nothing is printed to the session, the trail, or the human `[code: tools/wall.py:289-291 (the return is bare None; no reason field, no output)]`

#### 22. `S-TASK-PRE-PROMOTE` → `refused, writing nothing`

`T-PROMOTE-WALL`

- **Actor:** tools/promote.sh (operator command), shelling out to `wall.py promote-check`
- **Trigger:** `promote.sh <issue#> --repo <owner/name>`
- **Enforcement:** *partial* · **Guard site:** tools/wall.py:promote_check (line 360), called at tools/promote.sh:68 — on the path this operator command actually takes. Bypassed entirely by flipping Status through any other route.
- **Records:** `reads YR-TASK-GATES (records.toml:66-73, mode=strict-line, fields review/fit/who); emits none`
- **Preconditions:** The direct lane's fit check is walled AT the promote act: promote.sh demands the YR-TASK-GATES record before its own promotion record (the claim-time gate downstream stays) `[code+canon: skills/factory/references/attended-lane.md > The standalone lane's two halves (closing the it-30 seeds); tools/promote.sh:64-69]`<br>Runs after the open/on-board/not-epic refuse gate and before any write `[code: tools/promote.sh:55-69]`<br>Condition as coded: across the flattened lines of ALL comment bodies (issue body excluded), some line must `rstrip()`-equal `YR-TASK-GATES`, and for each of review/fit/who some line must `lstrip().startswith("<field>:")` — case-SENSITIVE, value emptiness unchecked, placeholders unchecked, fields may live in a DIFFERENT comment than the marker `[code: tools/wall.py:360-376]`<br>Unreadable trail refuses fail-closed, naming what it could not read `[code+canon: tools/wall.py:363-368; skills/factory/references/attended-lane.md > The lane protects itself, and its limits are named]`
- **Postconditions:** Non-zero exit -> promote.sh `refuse` -> exit 3, writing nothing `[code: tools/promote.sh:68-69, 26]`<br>TODAY this refuses EVERY promote unconditionally: the working-tree wall.py cannot compile, so the subprocess exits 1 on any input (observed), and `\|\| refuse` fires. Five tests in tests/test_promote.py fail for exactly this reason `[code: tools/wall.py:351; tools/promote.sh:68-69; observed pytest run: 5 failed in tests/test_promote.py]`

#### 23. `S-TASK-PRE-PROMOTE` → `S-TASK-HALF-PROMOTED`

`T-PROMOTE-HALF-WRITE`

- **Actor:** tools/promote.sh run inside an attended Claude session
- **Trigger:** A promote that passes the promote wall but whose board flip meets the in-funnel board wall
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None guards the ordering. The board wall at tools/board_plumbing.py:160 fires after the comment has already landed.
- **Records:** `emits YR-PROMOTED (records.toml:76-83)`
- **Preconditions:** promote.sh's design contract: every refusal writes nothing — record-before-flip is "a fact about the call order" `[canon-only: tools/promote.sh:1-16 (the file's own header contract)]`<br>The YR-PROMOTED comment is posted at line 78; the board write — and the YR-BOARD-FLIP wall inside it — happens at line 80. promote.sh never posts a YR-BOARD-FLIP record, and YR-TASK-GATES/YR-PROMOTED do not satisfy the board wall's marker `[code: tools/promote.sh:75-81; tools/board_plumbing.py:145-147]`
- **Postconditions:** A YR-PROMOTED comment exists on the trail; the board Status is unchanged; promote.sh dies with "promotion record posted, but the Status=Ready write failed" `[code: tools/promote.sh:80-81]`<br>The state is unreachable-from: the record on the trail is now a standing false claim, and re-running promote.sh posts a second one `[code: tools/promote.sh:78-81 (no idempotency check)]`<br>The suite cannot see this: tests/conftest.py declares YR_MACHINERY=1 autouse for every test, which is exactly the branch that skips the board wall `[code: tests/conftest.py:21-33; tools/board_plumbing.py:126-127]`

#### 24. `runner/epic-gate start` → `S-CALLER-MACHINERY`

`T-MACHINERY-DECLARE`

- **Actor:** tools/dev-runner.sh and tools/epic_gate.py, declaring themselves
- **Trigger:** Process start
- **Enforcement:** **prevented** · **Guard site:** tools/board_plumbing.py:126 — the only site that reads the declaration for a wall decision.
- **Records:** `none`
- **Preconditions:** Runner and epic-gate board writes are exempt — their own records are their trail `[code+canon: records.toml:353 (the row's notes); tools/dev-runner.sh:41-46]`
- **Postconditions:** YR_MACHINERY=1 in the environment, inherited by every child — including the runner's cold `claude -p` stages `[code: tools/dev-runner.sh:46; tools/epic_gate.py:72]`<br>hooks/deliver.sh honours the declaration; tools/wall.py does NOT read YR_MACHINERY anywhere on a live path — in_scope() (which does read it) is called by nothing `[code: hooks/deliver.sh:21; tools/wall.py:48-72 (uncalled); tools/wall.py:244-268 (decide never consults it)]`<br>Nothing verifies that the exempted caller's "own records" actually exist `[code: tools/board_plumbing.py:126-127 (immediate return, no record read)]`

#### 25. `a trail in any lane state` → `findings printed, exit 1 (or clean, exit 0)`

`T-DETECT`

- **Actor:** An attended session running tools/check_trail.py at ship-walk or census time
- **Trigger:** Manual invocation over a declared scope
- **Enforcement:** detected · **Guard site:** tools/check_trail.py — advisory by declaration; nothing calls it automatically.
- **Records:** `reads the lane's mandated rows (records.toml:387-391)`
- **Preconditions:** The detector verifies presence + registry grammar only, content-blind, over a declared scope; advisory-tier, never wired into check_cmd, CI or the manifest `[code+canon: skills/factory/references/attended-lane.md > Why this lane has a runner now; tools/check_trail.py:11-18]`<br>It checks only what [lanes] mandates: design/epic/standalone/close. YR-BOARD-FLIP, YR-HUMAN-INSTRUCTION and YR-ESCALATION are in no lane and are therefore never checked `[code: records.toml:387-391; tools/check_trail.py:11-13]`
- **Postconditions:** Findings one per line, exit 1 on findings `[code: tools/check_trail.py:15-16]`<br>MERGED to origin/main (#423) but absent from the installed plugin 0.10.0 and from the shared workspace checkout at a6b9990 `[code: observed listings of ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/tools and /opt/yellow-robots/factory/tools]`

#### 26. `S-COUNTS-LEDGER` → `YR-ROUND-RECORD on the epic/task trail`

`T-ROUND-CLOSE`

- **Actor:** The closing attended session (a human or agent typing a comment)
- **Trigger:** The round's close
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. The close check does not demand it (T-CLOSE-BLOCK); the detector finds its absence only if someone runs check_trail.py on the close lane.
- **Records:** `YR-ROUND-RECORD (records.toml:366-373) — mandated by the `close` lane, emitted by no code`
- **Preconditions:** The close report and the round record's counts — refusals issued, records demanded, detector findings, escalations — are emitted where the round reads them; the human prices them at close `[canon-only: skills/factory/references/attended-lane.md > Delivery, the slice, and the close]`<br>The registry declares the record with four fields and names its readers as check_trail.py and the human `[canon-only: records.toml:366-373]`
- **Postconditions:** No code emits YR-ROUND-RECORD and no code reads counts.jsonl into it; the only bridge between the ledger and the record is a person running `wall.py counts` and retyping the numbers `[code: tools/wall.py:391-399 (the counts subcommand prints JSONL and nothing more)]`<br>"records demanded" and "detector findings" have no counter anywhere — _emit_event's kinds are refusal/pass/close-block/close-override only `[code: tools/wall.py:77-88, 256, 261, 289, 292]`

#### 27. `round in progress` → `YR-SHIP-WALK on the epic/task trail`

`T-SHIP-WALK`

- **Actor:** The ship-walk session (attended)
- **Trigger:** "The close names the pending walk; the trigger is a surfaced checkpoint, never a memory"
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None.
- **Records:** `YR-SHIP-WALK (records.toml:356-363) — mandated by the `close` lane, emitted by no code`
- **Preconditions:** Step 10 of the mandatory step set; the close must surface the pending walk `[canon-only: skills/factory/references/attended-lane.md > The mandatory step set (reified — the existing mandates, not new ones)]`<br>Standalone-shipped work earns the same recorded close — a standalone task is a round of one `[canon-only: skills/factory/references/attended-lane.md > The standalone lane's two halves (closing the it-30 seeds)]`
- **Postconditions:** Nothing surfaces the checkpoint: the Stop hook's block reason names refused acts only, and no code writes to a board item or a close report `[code: tools/wall.py:292-299]`<br>The compiled slice carries the human's checkpoint bullets as a static list read from canon — the same prose, delivered earlier; no round position, no per-round prompt `[code: tools/compile_slice.py:53-61, 112-114]`

#### 28. `an agent at a severe-implication decision surface` → `YR-ESCALATION on the trail`

`T-ESCALATION`

- **Actor:** The attended agent, at its own discretion (the severity valve)
- **Trigger:** A one-way door judged by consequences, not diffs
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. Purely agent-initiated prose.
- **Records:** `YR-ESCALATION (records.toml:376-383) — declared, emitted by nothing, read by nothing`
- **Preconditions:** The agent MAY route a severe-implication decision to the human; every escalation lands as a YR-ESCALATION record, counted in the round record, so the valve is measured `[canon-only: skills/factory/references/attended-lane.md > The output-gate model (ruled 2026-08-06, clarified same day)]`
- **Postconditions:** The record has a registry row (fields act/why) and names check_trail.py plus "the round record's counts" as readers — but it belongs to no lane, so check_trail never looks for it, and no counter counts it `[code: records.toml:376-383; records.toml:387-391]`

#### 29. `a design doc under review` → `YR-DESIGN-REVIEW / YR-DESIGN-FIT / YR-ACCEPT typed into the doc`

`T-DESIGN-RECORDS`

- **Actor:** The independent cold reviewer, the architect, and the accepting session — each typing a line into the vault doc
- **Trigger:** Steps 2, 3 and 4 of the mandatory step set
- **Enforcement:** detected · **Guard site:** tools/check_trail.py (design lane) only — advisory, manual, and absent from both the installed plugin and the workspace checkout.
- **Records:** `YR-DESIGN-REVIEW (records.toml:316-323)`, `YR-DESIGN-FIT (records.toml:326-333)`, `YR-ACCEPT (records.toml:336-343)`
- **Preconditions:** The design-side records are typed lines in the vault docs themselves — no new surface (the crossing ruling of 2026-08-07) `[canon-only: skills/factory/references/attended-lane.md > The mandatory step set (reified — the existing mandates, not new ones); 04 projects/factory/iterations/30-attended-lane-runner/02-crossing-rulings.md > The design-side record surface]`<br>The lifecycle-stamp wall's stated condition is precisely the presence of these three — the one wall that would make them enforced reads none of them `[code: tools/wall.py:154-160, 244-268]`
- **Postconditions:** Mandated by the `design` lane, so check_trail.py can detect their absence; nothing prevents it `[code: records.toml:388; tools/check_trail.py:11-13]`<br>it-30's own governing spec fails the detector 3 of 3 on the design lane — its review, fit and accept records are prose, because the grammars were minted after the accept act `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications]`

#### 30. `any walled act` → `the act proceeds unrefused`

`T-HOOK-CRASH`

- **Actor:** The Claude Code harness, on a non-zero hook exit
- **Trigger:** tools/wall.py raising anything not caught in main()
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** tools/wall.py:main lines 400-407 — the only try/except, and it covers stdin parsing only.
- **Preconditions:** Infrastructure failure is not condition failure: a wall that cannot evaluate a fail-closed act's condition refuses `[canon-only: skills/factory/references/attended-lane.md > The lane protects itself, and its limits are named]`<br>main() catches only JSONDecodeError/ValueError on stdin; any other exception in classify/decide propagates and the process exits non-zero. The code states the consequence itself: "a PreToolUse hook that errors lets the call THROUGH" `[code: tools/wall.py:400-407; tools/wall.py:79-81]`<br>Today this is not hypothetical: the module does not compile at all (S-WALL-UNCOMPILABLE), so EVERY act would take this path `[code: tools/wall.py:351 (observed SyntaxError, RC=1)]`
- **Postconditions:** No decision JSON, no counts row, no refusal — the fail-open inverse of the canon's rule `[code: tools/wall.py:400-407]`

## Where the code and the canon disagree

### [blocking] Five of the canon's eight walled acts deny with no condition evaluated and no satisfiable path

- **code:** decide() branches on a condition for exactly one act (crossing-file, tools/wall.py:253-260). board-write, lifecycle-stamp, arming-edit, release-edit and push-shared fall through to the unconditional refusal at tools/wall.py:261-268. `_trail_has` (tools/wall.py:205-211) — the only helper that could read a record off a trail — is defined and called by nothing in the tree. Probe-observed: all nine classified acts return permissionDecision=deny with no trail or vault read.
- **canon:** Each of those rows states a REQUIRED RECORD SET as its condition: board write -> YR-BOARD-FLIP; lifecycle stamp -> YR-ACCEPT + YR-DESIGN-REVIEW + YR-DESIGN-FIT; arming edit -> YR-HUMAN-INSTRUCTION; skill release -> the freeze checks' records; other shared branch -> YR-HUMAN-INSTRUCTION. The spec's acceptance criterion is 'WHEN an attended session attempts a walled act whose stated condition fails THE ENFORCEMENT LAYER SHALL dispose per that act's stated stance' — a condition that is never evaluated cannot fail or pass.
- `tools/wall.py:244-268`, `tools/wall.py:205-211`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)`

### [blocking] tools/wall.py in the working tree contains a literal NUL byte and cannot be compiled, imported or executed

- **code:** tools/wall.py:351 holds `out.stdout.split("<NUL>")` — one 0x00 at byte offset 18218, introduced by the UNCOMMITTED edit that added board_check(). Observed: `python3 tools/wall.py counts` -> `SyntaxError: source code cannot contain null bytes`, RC=1. `git show HEAD:tools/wall.py` has zero NUL bytes, so this is working-tree-only damage.
- **canon:** The engine is the deciding half of the enforcement layer: PreToolUse calls are classified and disposed, and promote.sh routes its wall through it.
- `tools/wall.py:351`, `tools/wall.py:2-21`, `tools/promote.sh:68-69`

### [blocking] The uncompilable module makes both of its callers fail in opposite directions

- **code:** promote.sh:68-69 turns the non-zero exit into `refuse`, so EVERY standalone promote is now refused regardless of its trail (observed: 5 failures in tests/test_promote.py, including `test_refusal_exit_code_is_distinct_from_success - assert 3 == 0`). The PreToolUse hook, by wall.py's own stated model at tools/wall.py:79-81, lets the call through when the hook errors — so every walled act fails OPEN. 13 tests in tests/test_wall.py error out at import with the same SyntaxError.
- **canon:** Fail-closed on every act in the map; the close check never hard-locks.
- `tools/promote.sh:68-69`, `tools/wall.py:79-81`, `tools/wall.py:351`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [blocking] The machinery guard the code documents is written and never wired

- **code:** in_scope() (tools/wall.py:48-72, added by the UNCOMMITTED edit) reads YR_MACHINERY and walks for .yr/factory.toml / the factory repo / $YR_WORKSPACE / the vault. Nothing calls it: not decide(), not close_check(), not main(). Whole-tree search finds no caller. So the engine classifies and refuses in every directory of every session, and inside the runner's cold stages, which inherit YR_MACHINERY=1 from tools/dev-runner.sh:46.
- **canon:** The function's own docstring: 'The lane's authority ends where factory work ends, so the engine speaks only inside a factory-governed tree... a cold pipeline stage inherits YR_MACHINERY from the runner, exactly as delivery already honours it — one declaration, both halves.' hooks/deliver.sh:21 does honour it; wall.py does not.
- `tools/wall.py:48-72`, `tools/wall.py:244-268`, `hooks/deliver.sh:14-21`, `tools/dev-runner.sh:41-46`

### [material] board_check() is a guard that exists and is never called, and its docstring names two callers that do not exist

- **code:** tools/wall.py:325-357 (UNCOMMITTED) implements the YR-BOARD-FLIP condition over a GraphQL read. No caller anywhere: tools/board_plumbing.py:112-152 has its own inline copy, and the hook half never resolves an item id. The same edit DELETED the placeholder block that stood in decide() for board-write.
- **canon:** The docstring asserts: 'One implementation, two callers: the funnel shells out to this, and the hook's raw-evasion classification resolves the same item.' The funnel does not shell out to it, and there is no raw-evasion classification — `gh project item-edit` is unclassified (probe-observed).
- `tools/wall.py:325-357`, `tools/board_plumbing.py:140-147`, `tools/wall.py:133-134`, `git diff tools/wall.py (the removed board-write block in decide)`

### [material] The registry declares tools/wall.py a reader of YR-HUMAN-INSTRUCTION; wall.py never reads it

- **code:** The string 'YR-HUMAN-INSTRUCTION' appears nowhere in tools/wall.py. The arming and shared-branch acts both deny unconditionally.
- **canon:** records.toml:399 — `readers = ["tools/wall.py (slice 5 — the arming and shared-branch wall conditions)", "tools/check_trail.py"]`, with the row's own note: 'The record a wall condition names must itself be registered — the canon's own rule, applied to the conditions.'
- `records.toml:394-401`, `tools/wall.py:230-241`, `tools/wall.py:244-268`

### [blocking] The board-write wall is inverted: it refuses the lawful funnel call and misses the raw evasions

- **code:** The hook half matches only a Bash command containing both 'board_plumbing.py' and 'set-field' (tools/wall.py:133-134) — the exact call the in-funnel wall at tools/board_plumbing.py:160 already judges — and then refuses it unconditionally. Probe-observed unclassified: `gh project item-edit --id X --project-id P --field-id F --single-select-option-id O`, and any raw `gh api graphql` mutation.
- **canon:** The walled act is 'Board Status/Reason write', conditioned on the YR-BOARD-FLIP record with runner/epic-gate callers exempt.
- `tools/wall.py:133-134`, `tools/board_plumbing.py:155-166`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [blocking] tools/promote.sh half-writes on the attended path: it posts the promotion record and then cannot flip the board

- **code:** promote.sh posts YR-PROMOTED at line 78, then calls `_board set-field` at line 80. Inside an attended session (CLAUDECODE set, YR_MACHINERY unset) that call runs board_plumbing._attended_wall, which demands a `YR-BOARD-FLIP:` line — a record promote.sh never posts and YR-PROMOTED never satisfies. The result is a trail claiming promotion over an unmoved board, reachable and unrecoverable by re-running.
- **canon:** promote.sh's own header contract: 'the comment call precedes the status mutation in code, so record-before-flip is a fact about the call order' and 'Refuses (writing nothing — no comment, no status write)'.
- `tools/promote.sh:1-16`, `tools/promote.sh:75-81`, `tools/board_plumbing.py:126-152`, `tests/conftest.py:21-33`

### [blocking] The promote-act wall and the runner's claim-time gate disagree on the same record, in both directions

- **code:** wall.promote_check (tools/wall.py:369-370) requires a line `rstrip()`-equal to the marker and, for each field, some line whose lstrip starts with `review:`/`fit:`/`who:` — case-sensitive, value emptiness unchecked, placeholders unchecked, and the fields may come from a DIFFERENT comment than the marker (it flattens all comment bodies into one line list at tools/wall.py:364). The runner's gate (tools/dev-runner.sh:905-919) matches the field key case-INSENSITIVELY, requires a non-empty value, rejects fit values in {n/a, none, exempt, skipped, tbd, -}, and evaluates well_formed() per-comment.
- **canon:** attended-lane.md states the record is 'demanded at the promote act itself' with 'the claim-time gate downstream stays' — one record, two gates, implying agreement. The registry gives it one grammar: mode=strict-line, fields review/fit/who.
- `tools/wall.py:360-376`, `tools/dev-runner.sh:905-919`, `records.toml:66-73`, `skills/factory/references/attended-lane.md > The standalone lane's two halves (closing the it-30 seeds)`

### [material] The shared-branch wall is branch-blind: it infers 'your own task branch' from command text, never from HEAD

- **code:** tools/wall.py:128-131 passes any push whose argument text contains `task/<digits>-<slug>`, or `-u origin task/`, or that is a bare `git push`. Probe-observed: `git push origin task/999-not-mine` -> None (lawful); bare `git push` -> None even when HEAD is main; `git push origin HEAD:refs/heads/main` -> push-shared, not push-main; `git push --force` with no refspec -> push-shared.
- **canon:** 'the session's OWN `task/<n>-<slug>` branch: lawful' — pinned identically at the crossing: 'pushing main is categorically refused... the session's own task/<n>-<slug> branch is the lawful case; any other shared branch requires the record of the human's explicit instruction'.
- `tools/wall.py:123-132`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`, `04 projects/factory/iterations/30-attended-lane-runner/02-crossing-rulings.md > The shared-branch-push condition`

### [blocking] The write-path wall closes sanctioned doors and leaves off-table ones open

- **code:** It refuses mcp__obsidian__vault_patch frontmatter status writes (tools/wall.py:154-160) — a SANCTIONED row of the decision table — and refuses Write/Edit under VAULT_ROOT (tools/wall.py:145-148). It does not intercept mcp__obsidian__vault_write (not in the hook matcher at hooks/hooks.json:19), nor any shell filesystem write: probe-observed unclassified `sed -i ... /srv/obsidian/...` and `cp ... /srv/obsidian/...`.
- **canon:** The walled act is the OFF-TABLE vault write, judged against the decision table, which is 'the sole authority on sanctioned write paths' and 'offers no filesystem row'. The two-step filesystem write that raced the stamping plugin is the round's own cited exhibit.
- `tools/wall.py:145-160`, `hooks/hooks.json:19`, `skills/factory/references/documentation-model.md > Editing safely`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [material] The arming wall never looks at arming, and the release wall never looks at a release

- **code:** `arming-edit` fires on any file_path ending `.yr/factory.toml` (tools/wall.py:149-150) — probe-observed on /home/me/personal/.yr/factory.toml — with no read of the edit and no mention of `auto_merge` anywhere in wall.py. `release-edit` fires on any path ending `.claude-plugin/plugin.json` (tools/wall.py:151-152) — probe-observed on /anything/.claude-plugin/plugin.json.
- **canon:** The rows are 'Arming edit (`auto_merge`)' conditioned on YR-HUMAN-INSTRUCTION, and 'Skill release' conditioned on the freeze checks' records. No record named 'freeze check' exists in records.toml at all, so the release condition names a grammar the registry does not define — against the canon's own rule that a record absent from the registry is unsanctioned.
- `tools/wall.py:149-152`, `tools/wall.py:236-238`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`, `records.toml:35-401`

### [material] The commit wall never checks git identity and misses the common commit spellings

- **code:** _classify_commit (tools/wall.py:177-190) matches only `-m`/`--message` (whitespace-anchored) and `-F`/`--file`. Probe-observed unclassified: `git commit -am ...`, `git commit -qm ...`, `git commit --amend --no-edit`. `user.name` / `user.email` / any identity read appears nowhere in the file, so every untrailered commit is walled regardless of whose identity mints it.
- **canon:** The class is 'a commit minted ON THE HUMAN'S GIT IDENTITY without the standing trailer discipline'.
- `tools/wall.py:177-190`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [material] The hand-merge wall refuses a read and misses the API merges

- **code:** The regex `\bgh\b.*\bpr\b.*\bmerge\b` over joined tokens (tools/wall.py:121) classified `gh pr list --search merge` as hand-merge (probe-observed deny), while `gh api -X PUT repos/o/r/pulls/1/merge` and a GraphQL mergePullRequest mutation classified as None.
- **canon:** 'PR merge (attended hand-merge) \| categorical — no record licenses it; merges execute through the evaluator \| fail-closed'.
- `tools/wall.py:114-122`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [blocking] The close check checks refusals, not traces — and every refusal is permanently unresolvable

- **code:** close_check (tools/wall.py:273-292) reads only its own counts rows; a refusal counts as resolved only if a later `pass` row shares its act, and `pass` is emitted at exactly one site (tools/wall.py:256, crossing-file with an active design). It never loads records.toml, never reads a trail, and never names a mandated record. Probe-observed: nine refusals -> block naming nine acts -> second close returns None + close-override.
- **canon:** 'a session that executed a walled act OR EMITTED A MANDATED RECORD is refused a silent close while MANDATORY TRACES are missing (the refusal names each)'. The code's own docstring concedes 'V1 traces'.
- `tools/wall.py:273-299`, `tools/wall.py:256`, `skills/factory/references/attended-lane.md > Delivery, the slice, and the close`

### [material] The round that ratified one marker with one home minted two YR- tokens outside the registry

- **code:** `YR-WALL [<act>]` is emitted in every refusal reason and every close block (tools/wall.py:266, 296); `YR-DELIVERY-FAILURE:` heads the delivery banner (hooks/deliver.sh:44). Neither has a records.toml row.
- **canon:** 'The record vocabulary itself lives in records.toml (the registry) — a record absent from the registry is unsanctioned'; records.toml:28-31 defines `YR-` as the single named marker constant.
- `tools/wall.py:266`, `tools/wall.py:296`, `hooks/deliver.sh:44`, `records.toml:28-31`, `skills/factory/references/attended-lane.md > When to load this reference (the reference's own header note)`

### [material] YR-BOARD-FLIP — the record the walls most depend on — is in no detector lane

- **code:** records.toml:387-391 lists design/epic/standalone/close lanes; YR-BOARD-FLIP, YR-HUMAN-INSTRUCTION and YR-ESCALATION appear in none of them, and tools/check_trail.py reads lane membership as its only mandate source.
- **canon:** 'violations are detectable (tools/check_trail.py verifies presence and grammar against the registry)'; the board-write row is one of the eight walled acts.
- `records.toml:346-353`, `records.toml:387-391`, `tools/check_trail.py:11-13`, `skills/factory/references/attended-lane.md > Why this lane has a runner now`

### [blocking] A shipped blocking guard test is red on this branch: board_plumbing hand-rolls a YR- marker matcher

- **code:** tools/board_plumbing.py:145 spells `l.startswith("YR-BOARD-FLIP:")` inline. Observed run: tests/test_shared_marker_matcher.py::test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree FAILS with `{'tools/board_plumbing.py': ['.startswith("YR-']}`. The stated justification in the comment — 'this home imports stdlib only' — does not hold: tools/textutil.py is itself stdlib-only.
- **canon:** The it-28 anti-recurrence guard: 'every module that reads a marker must route through textutil.marker_line_matches'. The check gate runs the whole suite (AGENTS.md > Conventions: `.venv/bin/python -m pytest tests/ -q`).
- `tools/board_plumbing.py:141-147`, `tests/test_shared_marker_matcher.py:368`, `AGENTS.md > Conventions`

### [material] The delivered slice carries no position in the step set, and the human's checkpoints are surfaced nowhere but the slice itself

- **code:** compile_slice.py emits the step table verbatim (tools/compile_slice.py:84, 95-97) with no position column or marker, and the checkpoint bullets as a static list read from canon (tools/compile_slice.py:53-61, 112-114). deliver.sh appends a repo-level Position block only — timestamp, repo, open PRs, board rows (hooks/deliver.sh:61-82). Nothing writes to a board item or a close report.
- **canon:** 'composed at delivery with the round's current position and next step (the state-machine view): (1) the step set with position' and 'when a round reaches a step needing her input, the surface she already watches — the board item or the session's close report — names it, never her memory'. The spec's criterion: 'THE ENFORCEMENT LAYER SHALL surface the step and the input it needs on a surface the round already shows the human'.
- `tools/compile_slice.py:53-61, 84, 95-97, 112-114`, `hooks/deliver.sh:61-82`, `skills/factory/references/attended-lane.md > Delivery, the slice, and the close`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)`

### [blocking] 'Infrastructure failure is not condition failure' holds for one act and inverts for the rest

- **code:** The rule is implemented at tools/wall.py:258-260 (unreadable crossing body -> refuse) and in the two in-funnel walls (tools/wall.py:363-368; tools/board_plumbing.py:148-152). For the five unconditional acts there is no evaluation to fail. And at the process level the rule inverts: main() catches only stdin JSON errors (tools/wall.py:400-407), so any other exception exits non-zero — which, per the code's own statement at tools/wall.py:79-81, lets the act through.
- **canon:** 'a wall that cannot evaluate a fail-closed act's condition refuses; a crashed delivery is loud and never locks the human out of her own session.'
- `tools/wall.py:400-407`, `tools/wall.py:79-81`, `tools/wall.py:258-260`, `skills/factory/references/attended-lane.md > The lane protects itself, and its limits are named`

### [material] The in-funnel board wall carries two exemption rules the canon never states

- **code:** tools/board_plumbing.py:126-129 passes unconditionally when YR_BOARD_WALL_OFF is set, and passes unconditionally when CLAUDECODE is NOT set — so any plain shell, cron job or non-Claude process writes the board with no record check.
- **canon:** The map's only stated exemption is 'runner and epic-gate callers exempt — their records are their own'.
- `tools/board_plumbing.py:126-129`, `skills/factory/references/attended-lane.md > The walled-act map (total — every act carries condition AND stance)`

### [minor] The repo map rows describe the engine's capabilities as delivered

- **code:** AGENTS.md and README.md (both modified on this branch) list wall.py as 'PreToolUse act classification against the walled-act map, refusals naming the rule, the Stop close-check with the recorded second-close override, the promote wall, and the counts the round record reads'. Five of the eight map rows are not classified against their conditions; the counts have no reader; the file does not compile.
- **canon:** Same rows — they are the canon's own repo map.
- `AGENTS.md:110`, `README.md:26`, `tools/wall.py:244-268`, `tools/wall.py:351`

### [minor] The registry's reader annotations for two rows are stale relative to this branch

- **code:** tools/promote.sh:68 does call the YR-TASK-GATES wall, and tools/board_plumbing.py:145 does read YR-BOARD-FLIP.
- **canon:** records.toml:71 says 'tools/promote.sh promote-act wall (slice 5 — future reader, not at tip)' and records.toml:352 says 'tools/board_plumbing.py wall (slice 5 — future reader, not at tip)'. Accurate for origin/main, stale on the branch that adds the readers.
- `records.toml:66-73`, `records.toml:346-353`, `tools/promote.sh:68`, `tools/board_plumbing.py:145`

### [minor] The delivered walled-act map cannot be mapped to the engine's refusals

- **code:** The engine's act identifiers are hand-merge, push-main, push-shared, board-write, lifecycle-stamp, arming-edit, crossing-file, release-edit, vault-fs-write, commit-untrailed (tools/wall.py:230-241) — ten identifiers behind eight canon rows, with 'push-main'/'push-shared' splitting one row and 'vault-fs-write'/'commit-untrailed' splitting another. The compiled slice reproduces the canon's prose act names verbatim (tools/compile_slice.py:85, 102-104), so a refusal reading `YR-WALL [vault-fs-write]` names no row in the map the session was delivered.
- **canon:** 'the walls SHALL bind to that stated mapping' — the map is act -> condition -> stance.
- `tools/wall.py:230-241`, `tools/compile_slice.py:85, 102-104`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)`

## Gaps

- **Nothing of iteration 30 is live anywhere, and the gap is two layers deep, not one. The released plugin is 0.10.0 (~/.claude/plugins/installed_plugins.json), whose installed payload has no hooks/ directory, no wall.py, no records.toml, no check_trail.py, no compile_slice.py, and no attended-lane.md in references/. Separately, the shared workspace checkout /opt/yellow-robots/factory sits at a6b9990 — four commits behind origin/main — so even the MERGED slices (#422-#425) are absent from the tree operator commands are run from.**<br>Every 'prevented' or 'detected' cell in this lane is graded against the branch as built. On the machine today, the canon reaches no session, the detector exists in no runnable checkout, and no hook fires. The lane's entire enforcement layer is, in operational terms, prose.
- **There is no path from a refusal to a lawful act. `pass` is emitted at exactly one site (crossing-file, design active; tools/wall.py:256). For the other nine act identifiers, posting the record the refusal names changes nothing — the wall never re-reads it — and the close check treats the refusal as permanently unresolved.**<br>The refusal reason teaches a rule that cannot be obeyed. The canon's own thesis is that 'a wall that names a rule you cannot satisfy trains evasion' — and the eight evasion routes probe-verified here (gh api merge, raw item-edit, shell vault writes, -am commits, bare push, HEAD:refs/heads/main) are the doors left open beside the closed ones.
- **The counts ledger has no reader for the round record. tools/wall.py:391-399 prints JSONL and nothing more; no code reads counts.jsonl into YR-ROUND-RECORD, and two of the record's four declared fields — 'records-demanded' and 'detector-findings' — have no counter anywhere (the only event kinds are refusal/pass/close-block/close-override).**<br>The spec's final criterion and the round's whole pricing argument ('the human prices them against attended attention at close') rest on counts that a person must transcribe by hand from a global JSONL file.
- **The severity valve is unmeasured. YR-ESCALATION has a registry row naming check_trail.py and 'the round record's counts' as readers (records.toml:376-383), but it belongs to no lane (records.toml:387-391), no code emits it, and no code counts it.**<br>The output-gate ruling made escalation optional and agent-initiated precisely so it would be measured rather than vibed. Nothing measures it.
- **The counts state dir is one global append-only file per host user (~/.cache/yr-attended/counts.jsonl by default), never scoped by repo, round or epic, with no rotation or retention policy.**<br>The round record for one repo's round reads a ledger commingled with every other repo's and every personal session's activity; the file grows without bound, and the close check's cost is linear in the whole history.
- **No test asserts the PreToolUse or Stop registrations exist. tests/test_compile_slice.py:100-108 checks only the SessionStart block of hooks/hooks.json; nothing pins the matcher `Bash\|Write\|Edit\|mcp__obsidian__vault_patch` or the Stop entry.**<br>The registration is the only thing that connects the engine to a session. It can be deleted, mis-matched, or silently narrowed without a single test going red — and it is the one part of the slice with no unit-level coverage at all.
- **The machinery exemption is unverified on both sides. board_plumbing passes any YR_MACHINERY caller with no record read (tools/board_plumbing.py:126-127), on the canon's stated ground that 'their own records are their trail' — but nothing checks that the runner's or epic-gate's records actually landed. And the declaration is a plain environment variable any process can set.**<br>The exemption is the widest hole in the board wall and it is honour-system on the machine's side of the seam.
- **`strict-line` is a registry mode with no shared implementation. records.toml declares six modes (records.toml:10-17) but tools/textutil.py implements two (MARKER_SENTINEL, MARKER_PREFIX at tools/textutil.py:42-68). `strict-line` is hand-rolled twice — tools/check_trail.py:50 and tools/wall.py:369 — and `verdict-line`/`stage-escape`/`json-schema` likewise live only in check_trail.py.**<br>The it-28 anti-recurrence guard exists to stop exactly this, and it only catches literal `YR-` matchers — a variable-driven copy like wall.py:369 passes it invisibly. Two implementations of one mode is how the promote wall and the claim gate came to disagree.
- **The canon names no actor for the close report. attended-lane.md says the human's checkpoints are surfaced on 'the board item or the session's close report', but no artifact called a close report exists in code — the only close output is the Stop hook's block reason, which names refused acts and nothing else.**<br>The coordination arm — the human half of the round's thesis — has no implemented surface at all; it survives only as a static bullet list inside the delivered slice.
- **Steps 1, 5 and 6 of the eleven-step set have no record grammar and therefore no detector coverage: backlog capture/sweep and the crossing stamp are declared 'doc content, not a record grammar' / 'a frontmatter key, governed by the documentation model', and the technical-rfc review is 'prose under the review discipline'.**<br>Three of the eleven reified steps are reified in name only; the detector cannot see them, and the canon says so openly — a rule that exists for the design lane's steps 2-4 and not for its siblings.
- **The release wall and the release act are mutually blocking, and the release condition names an unregistered grammar. tools/wall.py:151-152 refuses any write to `.claude-plugin/plugin.json`; the version bump in that file is step 1 of the skill-release block; and 'the freeze checks' records' has no records.toml row to check.**<br>If 0.11.0 ever installs with these hooks, the act that ships 0.12.0 is refused by the copy already installed, with no satisfiable condition — the enforcement layer would wall its own upgrade path.
- **One owner decision is open on the record: does it-30 ship partial, or wait until the walls are right? The active spec says the walls ship; deferring them is the only choice that changes what the ruled design delivers.** **← needs an owner ruling**<br>Everything else the verification record lists — the rework, workspace scoping, the machinery guard, the promote semantics, the map diff, retro-typing the round's own design records — is named as execution belonging to the building session. This one is not.
- **factory-map.md's owed diff is unwritten: the §1 output-gate sentence is incomplete against merged canon and carries no arming sentence, §2 owes check_trail.py plus a whole enforcement-layer paragraph and a records.toml sibling, the C4 diagram predates an enforcement layer sitting between the agent and the issues/vault it reaches, and §3 carries two drift entries plus an open question on whether the categorical refusal of the attended hand-merge partially affects 01-autonomous-merge.** **← needs an owner ruling**<br>The living map of the factory does not describe the lane that now claims to govern attended work — including for the merged half that is already canon.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **T-RELEASE-BUMP, guard_site: "None. The release scan is a prose checklist in closing.md; no code runs it."**<br>Four of the release scan's five bullets are mechanized in the shipped pytest suite, which the check gate runs on every build (AGENTS.md > Conventions: `pytest tests/ -q`). closing.md:118-126 lists: no dangling router row -> tests/test_skill_factory_router.py:127 `test_no_dangling_router_links`; no orphan reference -> :137 `test_no_orphan_references` and :145 `test_no_orphan_reference_files_on_disk` (the latter enumerated from disk); SKILL.md < 500 lines -> :85 `test_skill_md_is_under_500_lines`; descriptions agree exactly -> :162 `test_skill_md_and_plugin_description_agree`. tests/test_plugin_version_pin_canonical.py additionally forces the version pin to track plugin.json. Only the consumer scan (check_model_refs.py) is left to the operator. The scan is prose PLUS a green-by-CI floor, not prose alone. `skills/factory/references/closing.md:118-126; tests/test_skill_factory_router.py:85,127,137,145,162; tests/test_plugin_version_pin_canonical.py:1-26`
- **S-CANON-AUTHORED: the eight-row walled-act map is "the ONLY place the per-act conditions are stated."**<br>Contradicted by the tree and by the excavation's own citations. The arming condition is stated independently in skills/factory/references/onboarding.md:20-23 ("a session may *execute* setting `auto_merge = true` only under the human's explicit instruction, and never decides it") — and tools/wall.py:236 cites onboarding.md as a co-authority for that very rule. The hand-merge categorical is stated in AGENTS.md:31 and AGENTS.md:205. The shared-branch-push condition is pinned verbatim in the vault at 02-crossing-rulings.md:14, which the excavation itself cites as canon under T-ACT-PUSH-MAIN. The map consolidates these; it is not their sole home. `skills/factory/references/onboarding.md:20-23; AGENTS.md:31,205; tools/wall.py:236; 04 projects/factory/iterations/30-attended-lane-runner/02-crossing-rulings.md:14`
- **T-ACT-CROSSING-REFUSE precondition: "A crossing governed by a feature-RFC ... carries no `/iterations/` segment and so is ALWAYS unresolvable, hence always refused."**<br>The cited code does not scan the Source line — it scans the WHOLE body for the first wikilink containing `/iterations/`. Probe-observed against the committed wall.py: a body whose Source is `feature-rfc [[04 projects/x/features/y/feature-rfc]]` but which also carries a grounding link `[[04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner]]` resolves `status=active` and PASSES. "Always refused" is false; worse, the condition is satisfiable by a design that does not govern the crossing at all. `tools/wall.py:214-219 (`re.search(r"\[\[([^\]]+/iterations/[^\]\|]+)\]\]", body)` over the entire body); probe: `_design_status_from_body` -> "active" for a feature-rfc Source with an unrelated iterations link`
- **T-ACT-BOARD-WRITE-FUNNEL actor: "Any Python caller of tools/board_plumbing.set_field — the runner, the epic gate, tools/promote.sh, tools/watch_build.sh, an attended session".**<br>tools/watch_build.sh contains no `set-field` / `set_field` call at all — grep over tools/ returns hits only in promote.sh:80, epic_gate.py (via `_set_field` at :577-578), dev-runner.sh's `set_status`/`set_reason`/`clear_reason` shell wrappers, and board_plumbing itself. watch_build.sh is a read-only poller. The actor list is wrong on one of its five members. `tools/watch_build.sh (no set-field); tools/epic_gate.py:577-578; tools/promote.sh:80; tools/dev-runner.sh (set_status/set_reason wrappers around `_board set-field`)`
- **S-WALLS-UNMERGED, stored_where: "`git diff --name-status origin/main HEAD` = A tools/wall.py, A tests/test_wall.py, M hooks/hooks.json, M tools/promote.sh, M tools/board_plumbing.py, M tools/dev-runner.sh, M tools/epic_gate.py, M tests/conftest.py, M AGENTS.md, M README.md."**<br>Stated as an equality but incomplete: the actual output also carries `M tests/test_board_plumbing_pins.py` and `M tests/test_promote.py`. Those two matter — test_board_plumbing_pins.py had to be edited to inject a `YR-TASK-GATES` stub (`STUB_COMMENTS`) so existing pins survive the new promote wall, which is direct evidence of the wall's blast radius on unrelated tests. Omitting them understates the change. `git diff --name-status origin/main HEAD (12 paths, not 10); tests/test_board_plumbing_pins.py:131-140 (the injected `gates` stub)`
- **T-HOOK-CRASH postcondition/state: on a non-zero hook exit "the act proceeds unrefused" — the fail-open inverse of the canon's rule.**<br>Nothing in the tree establishes this. The only support is tools/wall.py:79-81, which is the slice author's own docstring asserting harness behaviour, and the excavation elevates that assertion into a transition postcondition and an enforcement grade. No test, no vendor doc, and no observation in the repo demonstrates that a PreToolUse hook exiting non-zero lets the call through. Treat the direction of the failure as claimed-by-the-author, not verified. `tools/wall.py:79-81 (docstring); tools/wall.py:400-407 (main catches only stdin JSON errors) — no corroborating source in the tree`
- **Fourteen wall transitions carry `enforcement: "partial"` (T-ACT-HAND-MERGE, T-ACT-PUSH-MAIN, T-ACT-PUSH-SHARED, T-ACT-BOARD-WRITE-HOOK, T-ACT-BOARD-WRITE-FUNNEL, T-ACT-LIFECYCLE-STAMP, T-ACT-ARMING-EDIT, T-ACT-RELEASE-EDIT, T-ACT-CROSSING-PASS/REFUSE, T-ACT-VAULT-FS-WRITE, T-ACT-COMMIT-UNTRAILED, T-ACT-FALSE-POSITIVE, T-PROMOTE-WALL, T-CLOSE-BLOCK).**<br>"Partial" reads as "enforced some of the time." On the actor's real path today every one of these is enforced ZERO percent: the installed plugin is 0.10.0 with no `hooks/` directory (verified: ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/ has AGENTS.md, bench, deploy, docs, models.toml, qa, skills, tests, tools — and its tools/ has no wall.py, check_trail.py, compile_slice.py or records.py), so the PreToolUse and Stop hooks never fire anywhere; the shared checkout that runs promote.sh sits at a6b9990 with no wall.py at all; and the working-tree file does not compile. The notes section does disclose this convention, but a reader scanning the `enforcement` field alone is systematically misled. The honest value for every hook-mediated row is "unenforced (coded, unreachable)". `observed listing of ~/.claude/plugins/cache/yellow-robots/factory/0.10.0/tools; /opt/yellow-robots/factory/.git/refs/heads/main = a6b9990 with no tools/wall.py; py_compile on tools/wall.py -> SyntaxError (null byte, offset 18218)`
- **T-DELIVER postcondition: "Every failure path emits a loud non-blocking banner and exits 0" (hooks/deliver.sh:43-59, 84-85).**<br>The cited range covers only the compile-failure and no-temp-file paths. The runtime Position block's failures emit NO banner — hooks/deliver.sh:68 prints "Position unavailable: this directory resolves to no GitHub repo", :76 prints "PR read unavailable (gh failed or timed out)", and the board read at :78-80 prints nothing at all when `board.sh` fails or returns empty. Those are inline prose lines inside the slice, not the `YR-DELIVERY-FAILURE:` banner the claim generalizes to "every failure path". A silent board-read failure is a real, uncovered case. `hooks/deliver.sh:43-46 (the banner), 64-82 (the position block's three non-banner failure messages, one of them silent)`
- **Disagreement "The repo map rows describe the engine's capabilities as delivered" quotes one sentence and attributes it to both AGENTS.md:110 and README.md:26.**<br>Only AGENTS.md:110 carries that wording. README.md:26 reads "the attended lane's walls: act classification, refusals that name the rule, the close check, the counts" — shorter, and notably it does NOT claim the promote wall or that the counts are "the counts the round record reads". The substance of the disagreement survives for both files, but the quoted string is presented as shared text when it is not. `AGENTS.md:110 vs README.md:26`
- **Several line citations are off by one or name a container line rather than the asserted line: hooks/hooks.json:19 for the PreToolUse matcher (the matcher is at :18; :19 is `"hooks": [`); records.toml:352 for the YR-BOARD-FLIP staleness note (the `readers` line is :351); records.toml:316-386 / 346-353 / 356-363 / 366-373 / 376-383 / 394-401 each start one line after the row's `[[record]]` header.**<br>Individually trivial and none changes a conclusion — every asserted fact is present within a line or two — but they mean a reader following the citations lands on the wrong line often enough to matter when re-verifying. Flagged only for citation hygiene; all the underlying content checks out. `hooks/hooks.json:18 (matcher) vs the cited :19; records.toml:351 (readers) vs the cited :352`

## Found by the verifier, missing from the excavation

- Two shipped tests directly contradict each other, and one MUST fail. tests/test_wall.py:168-175 `test_board_funnel_marker_literal_agrees_with_its_registry_row` asserts that the source of tools/board_plumbing.py CONTAINS the literal `l.startswith("YR-BOARD-FLIP:")` — it positively pins the exact string that tests/test_shared_marker_matcher.py:361-371 forbids tree-wide. Observed: the pin test PASSES (it is not among test_wall.py's 13 import errors) while the guard test FAILS. Satisfying either one breaks the other; there is no state of tools/board_plumbing.py in which both are green. `tests/test_wall.py:168-175; tests/test_shared_marker_matcher.py:361-371; observed: `test_board_funnel_marker_literal_agrees_with_its_registry_row` passes, `test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree` fails`
- The excavation notes the wall's refusals "name the rule" as the teaching mechanism, but tools/promote.sh:80 runs the board write as `_board set-field ... >/dev/null 2>&1` — stderr discarded. The in-funnel wall's `RuntimeError` message ("REFUSED [board-write] — an attended board write requires the YR-BOARD-FLIP record ... Could not verify: ...") never reaches the operator; all they see is promote.sh's generic `die` line. The half-write state S-TASK-HALF-PROMOTED is therefore not just unrecoverable, it is illegible at the point of failure — a direct violation of the canon's own "refusals naming the rule" and "legible failure, derivable recovery". `tools/promote.sh:80-81 (`2>&1` on the set-field call); tools/board_plumbing.py:148-152 (the message that is discarded)`
- The promote wall's SCOPE diverges from the claim gate, not just its grammar. tools/wall.py:360-376 demands YR-TASK-GATES for any issue promote.sh accepts, and promote.sh only refuses Type=Feature/Epic (:58-62) — it never checks for a native parent. The runner's claim-time gate exempts a Task WITH a sub-issue parent outright (`if itype.strip().lower() != "task" or has_parent: print("")`). So a hand-promote of an epic CHILD now demands a standalone-lane record that the epic lane never emits and the downstream gate would never ask for — an unsatisfiable refusal on a lawful act, in a direction the excavation's grammar-only diff does not cover. `tools/dev-runner.sh:937-940 (`has_parent` exemption); tools/promote.sh:58-62 (type-only refusal); tools/wall.py:360-376 (no parent check)`
- The Bash arm of classify() applies NO path-based rules, so the arming and release walls have exactly the shell evasion the excavation only reported for vault writes. `sed -i s/false/true/ .yr/factory.toml`, `cat > .yr/factory.toml`, `python3 -c "..." > .claude-plugin/plugin.json` all classify as None (verified: the Bash arm at tools/wall.py:114-144 tests only the gh/push/board/issue-create/commit regexes and returns None). The two acts the excavation calls "refused with no satisfiable path" are simultaneously reachable by one line of shell. `tools/wall.py:114-144 (Bash arm — no file_path inspection) vs tools/wall.py:145-152 (the Write/Edit-only manifest and plugin.json rules)`
- An ALIASED wikilink to the governing design defeats the one condition the engine evaluates. The regex requires `[^\]\|]+` after `/iterations/`, so `[[04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner\|the spec]]` yields status=None -> REFUSED, while the identical unaliased link yields status=active -> pass (both probe-observed). Aliased wikilinks are standard practice in this vault — documentation-model.md:21 teaches `[[Note#2. Mechanism map\|§2]]` explicitly. The one satisfiable wall in the engine is defeated by the vault's own link convention. `tools/wall.py:215 (`\[\[([^\]]+/iterations/[^\]\|]+)\]\]`); skills/factory/references/documentation-model.md:21; probe: aliased -> None, plain -> active`
- The in-funnel board wall reads a different gh binary than the write uses. tools/board_plumbing.py:104 resolves `gh_bin = os.environ.get("GH_BIN", "gh")` for the module's real runner, but _attended_wall:132 hardcodes the literal `"gh"` in its subprocess argv. Under promote.sh — which threads `GH_BIN="$GH_BIN"` into every board call (tools/promote.sh:19,22) — the wall's condition read and the write it guards can hit two different binaries. In the test harness the mismatch is masked only because the stubs are also on PATH. `tools/board_plumbing.py:104 vs tools/board_plumbing.py:131-136; tools/promote.sh:19,22`
- The "this home imports stdlib only" justification at tools/board_plumbing.py:142 is weaker than the excavation says: tools/textutil.py imports NOTHING AT ALL — not one import statement in the file. Routing through it would add zero dependency of any kind, not merely a stdlib-equivalent one. The stated reason for the hand-rolled matcher is not thin, it is empty. `tools/textutil.py (zero import statements); tools/board_plumbing.py:141-145`
- No test pins the Stop registration either, and the Stop block carries no matcher at all — hooks/hooks.json:29-39 has a bare `hooks` array with no `matcher` key, unlike SessionStart and PreToolUse. The excavation flags the missing PreToolUse/Stop coverage but not that the Stop entry is also structurally different from its siblings, so a matcher-shape regression there is invisible on two axes. `hooks/hooks.json:29-39 (no matcher key); tests/test_compile_slice.py:100-108 (SessionStart only)`
- The excavation's own probe method has a blind spot it does not state: every classification/decision claim was verified against `git show HEAD:tools/wall.py`, i.e. the COMMITTED copy, because the working tree will not import. But the working-tree edit also DELETED the two dead locals flagged as blocker 7 in the round's verification record and rewrote _emit_event/read_counts. The behavioural claims are therefore graded on a file that no longer exists on disk in that form — correct as stated for HEAD, but the artifact a reviewer would actually pick up is a third object (uncompilable) distinct from both HEAD and origin/main. `git diff tools/wall.py (90 insertions, 11 deletions on top of HEAD); 04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md:28 (blocker 7, the F841 dead locals)`

---

GRADING CONVENTION. `enforcement` is graded against the branch AS BUILT (task/420-walls, committed HEAD dc67cbb), because that is the artifact under excavation. Nothing in it is live: the released plugin is 0.10.0 and its installed payload has no hooks/ at all (state S-CANON-UNDELIVERED), and the shared workspace checkout is four commits behind origin/main (S-CHECKOUT-STALE). Where a guard is coded but unreachable on the actor's real path today, guard_site says so explicitly. Read every "partial" on a wall act as: prevented on the one command spelling classify() matches, open on every other route to the same act — and, on the working tree as it sits, open on ALL of them (S-WALL-UNCOMPILABLE).  WHAT IS MERGED vs NOT. origin/main (ff8f84e) carries slices 1-4: records.toml + tools/records.py (#422), tools/check_trail.py (#423), skills/factory/references/attended-lane.md + the minted grammars and lanes (#424), tools/compile_slice.py + hooks/ with SessionStart ONLY (#425). UNMERGED, branch-only: tools/wall.py, the PreToolUse + Stop blocks in hooks/hooks.json, the promote-act wall call in tools/promote.sh, _attended_wall in tools/board_plumbing.py, the YR_MACHINERY declarations in tools/dev-runner.sh and tools/epic_gate.py, the autouse machinery fixture in tests/conftest.py, tests/test_wall.py, and the AGENTS.md/README.md repo-map rows. UNCOMMITTED on top of that (working tree only, `git status: M tools/wall.py`): in_scope(), board_check(), the fail-soft _emit_event, the tolerant read_counts, removal of the two dead locals — and the NUL byte at line 351 that makes the file uncompilable.  OBSERVED TEST STATE (this worktree, .venv pytest). tests/test_wall.py: 13 errors, all `SyntaxError: source code string cannot contain null bytes` at import. tests/test_promote.py: 5 failed (the promote-check subprocess exits 1 on the uncompilable module, so `\|\| refuse` fires on every path). tests/test_shared_marker_matcher.py::test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree: 1 failed, on tools/board_plumbing.py's inline `.startswith("YR-` — this one is independent of the NUL and fails at committed HEAD too. tests/test_compile_slice.py passes. A full-suite run was started and hit a 900s wall clock without finishing; the targeted runs above are what I observed directly.  METHOD. Every classification and decision claim in this document was verified by executing the COMMITTED wall.py (extracted to /tmp via `git show HEAD:tools/wall.py`, since the working-tree copy will not import) against constructed hook payloads, offline, with the real vault path for the one condition that reads it. The probes covered: hand-merge and its gh-api/GraphQL evasions; push main/HEAD:main/HEAD:refs/heads/main/bare/--force/task-branch/other-branch; board_plumbing set-field vs raw `gh project item-edit`; shell vault writes; commit -m/-am/-qm/--amend/-F; Write/Edit on manifest, plugin.json, and vault paths; vault_patch active/draft; vault_write; NotebookEdit; and the crossing wall against a real active design (pass, with the `pass` counts row) and against unresolvable and unreadable bodies (refuse). The close check was driven end to end: nine refusals -> one block naming nine acts -> second close returns None with a close-override row.  THE ONE-SENTENCE SHAPE OF THE LANE. The canon states eight acts, each with a condition and a stance; the engine classifies ten act identifiers by string-matching command text and file paths, evaluates a condition for exactly one of them, denies the other nine with no satisfiable path, misses at least eight routes to the same acts, has no machinery or workspace guard on any live path, keeps its counts in a global file no round record reads, checks its own refusals rather than the canon's mandated traces at close, and — in the working tree as it stands — does not compile.
