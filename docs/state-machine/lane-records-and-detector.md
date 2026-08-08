<!-- GENERATED from the it-30 state-machine excavation (2026-08-07/08). Do not hand-edit. -->

# The record registry and the trail-shape detector

> One lane of the factory's state machine, excavated from the tree and then independently refuted by an agent that did not write it. Verifier verdict: **trustworthy-with-corrections**. Every claim carries a citation; contested claims are listed at the foot.

## States

| State | Means | Physically stored | Citation |
|---|---|---|---|
| `absent-from-tree` | A record grammar does not exist anywhere: no literal in code, hooks, templates or canon, and no registry row. The resting state before any grammar is minted. | Nowhere — the absence of both a tree literal and a `[[record]]` block in `records.toml`. | `records.toml:4` |
| `unsanctioned` | A machine-parsed or record-shaped `YR-*` token exists as a literal in the tree (or on a shared surface) with NO `[[record]]` row. The canon declares such a record unsanctioned; nothing in the tree prevents it existing, being emitted, or being parsed. Four instances live at this HEAD: `YR-DELIVERY-FAILURE` (merged), `YR-WALL` (unmerged), `YR-DEBT-NET-LINES` and `YR-DEBT-SURFACE` (merged, template-declared). | The token lives where its author wrote it — `hooks/deliver.sh:44`, `tools/wall.py:266`, `skills/factory/templates/debt-round-spec.md:54`, `skills/factory/templates/debt-census.md:35`. The state itself is the ABSENCE of a block in `records.toml` (repo root, tracked in git). | `records.toml:5` |
| `registered` | A `[[record]]` block exists and passes the loader's shape rules: unique non-empty name, non-empty marker, non-empty emitter, non-empty readers list, a mode from the closed six, at least one surface from the closed eight, and (for a `YR-`-family name) a `YR-`-family marker. 37 rows at this HEAD. | A `[[record]]` block in `records.toml` at the repo root; loaded by `records.load()` from `REGISTRY_PATH`. | `tools/records.py:58` |
| `lane-mandated` | The row's `name` appears in a list under `[lanes]`, so `check_trail` will demand it for that lane. Exactly 8 of 37 rows are in this state, across four lanes: design (YR-DESIGN-REVIEW, YR-DESIGN-FIT, YR-ACCEPT), epic (YR-EPIC-APPROVAL), standalone (YR-TASK-GATES), close (YR-SHIP-WALK, YR-ROUND-RECORD). | The `[lanes]` table in `records.toml`, lines 387–391. | `records.toml:387` |
| `registered-unmandated` | A registered row named in no lane. The detector can never demand it, whatever the row's `readers` field claims. 29 of 37 rows sit here, including `YR-BOARD-FLIP`, `YR-ESCALATION` and `YR-HUMAN-INSTRUCTION` — the three attended-lane records whose rows name `tools/check_trail.py` as a reader. | `records.toml` — the row exists, its name is absent from every list in `[lanes]`. | `records.toml:351` |
| `registry-unloadable` | `records.toml` is missing, does not parse as TOML, or violates a shape rule. `records.load()` raises `RegistryError`; every consumer of the registry refuses rather than falling back. | The bytes of `records.toml`; observed only at load time as a raised `RegistryError`. | `tools/records.py:45` |
| `umbrella-marker-bound` | The single named marker constant is bound: `[marker].yr = "YR-"`. Only two things read it: the loader's family-consistency rule and the `records.py marker`/`validate` CLI output. No production matcher in the tree derives its prefix from it. | `records.toml` lines 28–31, `[marker]` table. | `records.toml:31` |
| `canon-named` | The record's name appears backticked in `skills/factory/references/attended-lane.md` — its step-set table, walled-act map, or output-gate section. This is the state the agreement tests bind to the registry in both directions. | `skills/factory/references/attended-lane.md` (a repo file, shipped as part of the factory plugin's skill). | `skills/factory/references/attended-lane.md:29` |
| `record-emitted` | An instance of the grammar exists on one of the row's declared surfaces: a line, a fenced JSON block, or a JSONL row that matches the row's mode. | Per the row's `surfaces` value — a GitHub issue comment or issue body, a PR comment, a file in the run dir, a stage log, `$DEV_RUNNER_HOME/ledger/rows.jsonl`, a file under `bench/`, or a markdown file in the Obsidian vault. | `records.toml:19` |
| `record-never-emitted` | A registered grammar with zero live instances anywhere. The whole design-side family is here: no `YR-DESIGN-REVIEW`, `YR-DESIGN-FIT` or `YR-ACCEPT` line exists in `04 projects/factory/` (the only file mentioning any of them is the it-30 verification record, and only as prose about their absence). So is the close family — running the close lane against epic #415 reports both records absent. | The absence of the marker on the surface the row declares — the vault for the design lane, the issue trail for the close lane. | `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications` |
| `detector-unrun` | The resting state of every scope in the org: `tools/check_trail.py` has been invoked by nothing. There is no caller in the tree — no CI step, no `check_cmd`/`lint_cmd` entry, no manifest key, no runner stage, no epic-gate call, no operating-reference procedure. The only references are two doc rows, the module's own tests, seven `readers =` strings in the registry, one canon sentence, and one line of compiled slice text. | Nowhere — the absence of any invocation. `AGENTS.md:108` names the tier: 'advisory-tier'. | `tools/check_trail.py:16` |
| `detector-nothing-mandated` | `check_texts` returns `[]` and the CLI exits 0 with 'nothing mandated' because the `[lanes]` table is absent or empty. A clean result that asserts nothing about the trail. | Transient — the process's exit code and stdout; nothing durable is written. | `tools/check_trail.py:117` |
| `detector-lane-unknown` | The caller named a lane the `[lanes]` table does not carry. Exactly one finding, exit 1; no record is checked. | Transient — one stdout line, exit 1. | `tools/check_trail.py:120` |
| `detector-surface-unreadable` | A mandated row's declared surfaces got no text in this invocation (the caller passed no `--issue`/`--pr`/`--vault-doc` covering them). Reported as a finding, not silently skipped. | Transient — one stdout line per row, exit 1. | `tools/check_trail.py:126` |
| `detector-record-absent` | Texts were supplied for the row's surfaces but no line/object in them matches the row's marker under the row's mode. | Transient — one stdout line per row, exit 1. | `tools/check_trail.py:130` |
| `detector-record-malformed` | A marker-carrying text exists, but no SINGLE such text carries every field the row declares (fields pooled across separate comments never satisfy). Values are never judged — nonsense values pass. | Transient — one stdout line per row, exit 1. | `tools/check_trail.py:135` |
| `detector-clean` | Every record the lane mandates was found present and field-complete on a declared surface. Exit 0. Verified live at this HEAD for lane `epic` on issue #415. | Transient — one stdout line, exit 0. Nothing is written back to any trail, board field, or file. | `tools/check_trail.py:227` |
| `detector-error` | The run could not be performed: the registry did not load, a `gh` call failed or `gh` is unavailable, a named vault doc was unreadable, or `--vault-doc` was passed without `--vault-root`. Exit 2 — deliberately distinct from exit 1 (findings). | Transient — stderr plus exit 2. | `tools/check_trail.py:201` |

## Transitions

| # | From → To | Actor | Enforcement | Guard site |
|--:|---|---|---|---|
| 1 | `absent-from-tree` → `unsanctioned` | any author — an attended agent, the architect, or a dev-runner build stage — writing a new marker literal into code, a hook, a template or a canon doc | ⚠️ **unenforced** | None. No tree-wide scan for unregistered markers exists anywhere. `tests/test_shared_marker_matcher.py:360` walks `tools/*.py` and `qa/*.py` but only for hand-rolled MATCHERS, never for unregistered markers; `qa/cardinality.toml` declares no marker rule; `tools/records.py` never reads the tree. |
| 2 | `unsanctioned` → `registered` | an attended agent editing `records.toml` (the canon/registry slice's author) | **prevented** | `tools/records.py::_validate` (:58–103), reached from `records.load()` on every consumer path (`records.py` CLI, `check_trail.py:199`, `compile_slice.py:83`, `wall.py:334` and `:361`). Also reached in `check_cmd`/CI, because `tests/test_records.py:27` loads the live registry. |
| 3 | `registered` → `registry-unloadable` | any agent or human editing `records.toml` | **prevented** | `tools/records.py::_validate` at every load site. Reachable on every path any actor takes, including the plugin's SessionStart hook. |
| 4 | `registered` → `lane-mandated` | an attended agent editing the `[lanes]` table in `records.toml` | **prevented** | `tools/records.py::_validate` (:94–103) for shape; `tests/test_attended_lane_canon.py:56` and `tests/test_records.py:37` for canon agreement and lane coverage — both run under `check_cmd` (`pytest tests/ -q`) and CI. |
| 5 | `registered` → `registered-unmandated` | the registry author — by omission | ⚠️ **unenforced** | None. `_validate` checks lanes→records, never records→lanes; no test asserts that a row with `check_trail.py` in `readers` is in a lane. |
| 6 | `registered` → `canon-named` | an attended agent editing `skills/factory/references/attended-lane.md` and/or `records.toml` | **prevented** | `tests/test_attended_lane_canon.py` (:47, :56, :66, :93) — runs under `check_cmd` and CI, so it is reachable on the path a build actually takes. |
| 7 | `registered` → `registered` | an attended agent editing either a registry row or the inline literal it mirrors | *partial* | `tests/test_records.py:125–172` and `tests/test_wall.py:170` — reachable under `check_cmd`/CI. |
| 8 | `umbrella-marker-bound` → `umbrella-marker-bound` | an attended agent editing `[marker].yr` | *partial* | `tools/records.py::_validate` (:89) — family consistency inside the file only. Nothing checks the tree's ~20 inline `YR-` constants against it. |
| 9 | `detector-unrun` → `detector-clean` | a human or an attended agent, by hand at a shell | ⚠️ **unenforced** | None — there is no caller anywhere in the tree. Verified: the only non-test references to `check_trail` are `AGENTS.md:108`, `README.md:24`, seven `readers =` strings in `records.toml`, `attended-lane.md:21`, and one line of compiled slice prose at `compile_slice.py:99`. `architect.md`'s ship-walk step and `closing.md` never name it. |
| 10 | `detector-unrun` → `detector-nothing-mandated` | the detector process | detected | `tools/check_trail.py::check_texts` (:115–117) and `_cli` (:203–205). |
| 11 | `detector-unrun` → `detector-lane-unknown` | the detector process | detected | `tools/check_trail.py::check_texts` (:118–120). |
| 12 | `detector-unrun` → `detector-surface-unreadable` | the detector process | detected | `tools/check_trail.py::check_texts` (:124–128); CLI surface population at `_cli` (:206–218). |
| 13 | `detector-unrun` → `detector-record-absent` | the detector process | detected | `tools/check_trail.py::_marker_present` (:37–62) and `_json_schema_present` (:65–82); reached from `check_texts` (:129). |
| 14 | `detector-unrun` → `detector-record-malformed` | the detector process | detected | `tools/check_trail.py::_missing_fields` (:85–109); reached from `check_texts` (:133). |
| 15 | `detector-unrun` → `detector-error` | the detector process | **prevented** | `tools/check_trail.py::_cli` (:198–221), `_gh_json` (:142–149), `fetch_vault_docs` (:176–185). |
| 16 | `registered` → `record-emitted` | machine emitters: the merge evaluator (`tools/merge_shadow.py`), the epic-gate sweep (`tools/epic_gate.py`), the dev-runner (`tools/dev-runner.sh`), `tools/verdict_diff.py`, `tools/ledger.py`, `tools/bench_corpus.py`, `tools/bench_replay.py`, `tools/promote.sh` | *partial* | Each emitter's own code path. None consults the registry; the only binding between emitter and row is the six agreement pins in `tests/test_records.py:125–172`. |
| 17 | `registered` → `record-emitted` | a dev-runner implement or test stage (a cold `claude -p` process) | **prevented** | `tools/dev-runner.sh:1572` (case arm), pinned to the row by `tests/test_records.py:137`. |
| 18 | `registered` → `record-emitted` | an attended session or the human, typing a comment onto an issue or PR trail | *partial* | For `YR-EPIC-APPROVAL`: `tools/epic_gate.py::_has_valid_approval` (:429), reached at the promotion path (:979) — prevented. For `YR-TASK-GATES`: `tools/dev-runner.sh:911` at claim — prevented downstream of the act; and (slice 5, UNMERGED) `tools/promote.sh:69` → `tools/wall.py::promote_check` (:360) — prevented at the act. For the other five: no guard on origin/main. |
| 19 | `registered` → `record-never-emitted` | the independent cold reviewer (YR-DESIGN-REVIEW), the architect at the spec-ready moment (YR-DESIGN-FIT), and the accepting session (YR-ACCEPT), typing lines into the reviewed/accepted vault doc | ⚠️ **unenforced** | None. The vault lifecycle-stamp wall that would demand them exists only in the unmerged slice 5 (`tools/wall.py:235` names the rule), and even there `decide()` denies the act unconditionally without reading any record — `_trail_has` (wall.py:205) has zero callers. |
| 20 | `registered` → `record-emitted` | the architect (YR-GATE-TOUCHING), a design author (YR-OPEN-QUESTION), a debt-epic author (YR-ITERATION-KIND, YR-DEBT-LEDGER) | **prevented** | `tools/epic_gate.py`: `_open_question_lines` (:450), `_gate_touching_declaration` (:460), `_is_debt_epic` (:474), `_has_ledger_verdict` (:481) — all reached on the sweep's promotion path. |
| 21 | `record-emitted` → `record-emitted` | `tools/wall.py` (UNMERGED slice 5) — the only production code that resolves a grammar THROUGH the registry | **prevented** | `tools/wall.py::promote_check` (:360–376), reached from `tools/promote.sh:69`. This exists ONLY on the unmerged slice-5 branch; `origin/main`'s `promote.sh` has no such call. |
| 22 | `record-emitted` → `record-emitted` | every other reader in the tree: `tools/dev-runner.sh` (claim gate, review gate, stage-escape), `tools/epic_gate.py`, `tools/merge_shadow.py`, `tools/nit_harvest.py`, `tools/review_bundle.py`, `tools/bench_report.py`, `tools/board_plumbing.py` (unmerged) | *partial* | `tests/test_shared_marker_matcher.py:360` — a tree-derived guard reachable under `check_cmd`/CI. It scans `tools/*.py` and `qa/*.py` only, for LITERAL or module-constant matchers; a matcher over a registry-supplied variable (as in `check_trail.py:50` and `wall.py:369`) is invisible to it. |
| 23 | `registered` → `registered` | an attended agent changing the registry, the detector, the walls, or delivery | ⚠️ **unenforced** | `tools/epic_gate.py::_gate_touching_declaration` (:460) — reachable, but keyed on an author-written body line, never on the change's content. |

### Detail

#### 1. `absent-from-tree` → `unsanctioned`

`T1-mint-unregistered`

- **Actor:** any author — an attended agent, the architect, or a dev-runner build stage — writing a new marker literal into code, a hook, a template or a canon doc
- **Trigger:** a new `YR-*` (or other machine-parsed) record literal is written anywhere in the tree
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. No tree-wide scan for unregistered markers exists anywhere. `tests/test_shared_marker_matcher.py:360` walks `tools/*.py` and `qa/*.py` but only for hand-rolled MATCHERS, never for unregistered markers; `qa/cardinality.toml` declares no marker rule; `tools/records.py` never reads the tree.
- **Preconditions:** None. Nothing is checked before a new marker literal is written. `[code: tools/records.py:30]`<br>The canon forbids the resulting STATE, not the act: 'a record absent from the registry is unsanctioned'. `[canon-only: skills/factory/references/attended-lane.md:7]`
- **Postconditions:** The token exists in the tree with no `[[record]]` row. Four live instances at this HEAD: `YR-DELIVERY-FAILURE` (hooks/deliver.sh:44, merged), `YR-WALL` (tools/wall.py:266 and :296, unmerged), `YR-DEBT-NET-LINES` (skills/factory/references/debt-rounds.md:132), `YR-DEBT-SURFACE` (skills/factory/templates/debt-census.md:35). `[code: hooks/deliver.sh:44]`<br>Nothing records the minting; no comment, no file, no board field. `[code: records.toml:6]`

#### 2. `unsanctioned` → `registered`

`T2-register-row`

- **Actor:** an attended agent editing `records.toml` (the canon/registry slice's author)
- **Trigger:** a hand edit adding a `[[record]]` block
- **Enforcement:** **prevented** · **Guard site:** `tools/records.py::_validate` (:58–103), reached from `records.load()` on every consumer path (`records.py` CLI, `check_trail.py:199`, `compile_slice.py:83`, `wall.py:334` and `:361`). Also reached in `check_cmd`/CI, because `tests/test_records.py:27` loads the live registry.
- **Records:** `the `[[record]]` block itself in records.toml`
- **Preconditions:** `[marker].yr` must be present and a string, or the whole registry is refused. `[code: tools/records.py:59]`<br>`name` non-empty, unique across the file; `marker` non-empty string; `emitter` non-empty string; `readers` a non-empty list of non-empty strings; `mode` in the closed six; `surfaces` a non-empty list drawn from the closed eight; a `YR-`-family name requires a `YR-`-family marker; `fields` (optional) a list of non-empty strings. `[code: tools/records.py:66]`<br>The registry names every machine-parsed trail grammar with emitter, reader, surface and grammar, in exactly one machine-readable home. `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)]`
- **Postconditions:** The row is visible to `records.records()`, `records.get()`, and the `list`/`show` CLI. `records.py validate` reports 37 records, marker 'YR-', 4 lanes at this HEAD. `[code: tools/records.py:143]`<br>NOTHING checks that the row's `emitter` or `readers` strings name a file, a function, or a line that exists. `[code: tools/records.py:75]`

#### 3. `registered` → `registry-unloadable`

`T3-malformed-registry-edit`

- **Actor:** any agent or human editing `records.toml`
- **Trigger:** an edit that breaks TOML parsing or a shape rule (duplicate name, unknown mode, unknown surface, missing emitter/readers, lane naming an unregistered record)
- **Enforcement:** **prevented** · **Guard site:** `tools/records.py::_validate` at every load site. Reachable on every path any actor takes, including the plugin's SessionStart hook.
- **Records:** `YR-DELIVERY-FAILURE (unregistered) — hooks/deliver.sh:44`
- **Preconditions:** No precondition — the edit succeeds; the failure surfaces at the next load. `[code: tools/records.py:49]`
- **Postconditions:** `records.load()` raises `RegistryError` with the file path and the offending row/rule named. `[code: tools/records.py:52]`<br>`records.py <cmd>` prints 'records: ERROR: …' to stderr and exits 1. `[code: tools/records.py:139]`<br>`check_trail.py` prints 'check_trail: ERROR: …' and exits 2 — deliberately not exit 1. `[code: tools/check_trail.py:200]`<br>`compile_slice.py` raises SystemExit naming the registry as the cause rather than a traceback head; `hooks/deliver.sh` catches the non-zero exit, emits the `YR-DELIVERY-FAILURE` banner as additionalContext, and exits 0 (loud, non-blocking). `[code: tools/compile_slice.py:133]`<br>`wall.py::promote_check` / `board_check` call `records.load()` with no handler; the exception propagates out of `main()` as a traceback and a non-zero exit, which `tools/promote.sh:69` turns into its own refusal. `[code: tools/wall.py:361]`

#### 4. `registered` → `lane-mandated`

`T4-mandate-in-lane`

- **Actor:** an attended agent editing the `[lanes]` table in `records.toml`
- **Trigger:** a hand edit adding a record name to a lane's list
- **Enforcement:** **prevented** · **Guard site:** `tools/records.py::_validate` (:94–103) for shape; `tests/test_attended_lane_canon.py:56` and `tests/test_records.py:37` for canon agreement and lane coverage — both run under `check_cmd` (`pytest tests/ -q`) and CI.
- **Records:** `the `[lanes]` entry in records.toml:387`
- **Preconditions:** `[lanes]` must be a table; each value a list of non-empty strings; every named record must already be registered, or the whole registry refuses to load. `[code: tools/records.py:94]`<br>Every lane-mandated record must also be named in `attended-lane.md`'s tables, or the suite fails. `[code+canon: tests/test_attended_lane_canon.py:56]`<br>The live registry must carry at least the four lanes design/epic/standalone/close, and every lane's list must be non-empty and fully registered. `[code: tests/test_records.py:37]`
- **Postconditions:** `check_trail --lane <name>` will demand that record on the row's declared surfaces. `[code: tools/check_trail.py:121]`<br>`compile_slice.py` renders the lane mandates into the delivered slice's part 1. `[code: tools/compile_slice.py:87]`

#### 5. `registered` → `registered-unmandated`

`T5-leave-unmandated`

- **Actor:** the registry author — by omission
- **Trigger:** authoring a `[[record]]` row without adding its name to any lane
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. `_validate` checks lanes→records, never records→lanes; no test asserts that a row with `check_trail.py` in `readers` is in a lane.
- **Preconditions:** None. Nothing requires a registered row to belong to a lane, whatever its `readers` field claims. `[code: tools/records.py:94]`
- **Postconditions:** The detector can never demand the record. 29 of 37 rows are in this state, including `YR-BOARD-FLIP` (records.toml:346), `YR-ESCALATION` (:376) and `YR-HUMAN-INSTRUCTION` (:394) — each of whose rows names `tools/check_trail.py` among its readers. `[code: tools/check_trail.py:121]`

#### 6. `registered` → `canon-named`

`T6-canon-registry-agreement`

- **Actor:** an attended agent editing `skills/factory/references/attended-lane.md` and/or `records.toml`
- **Trigger:** any edit to either surface
- **Enforcement:** **prevented** · **Guard site:** `tests/test_attended_lane_canon.py` (:47, :56, :66, :93) — runs under `check_cmd` and CI, so it is reachable on the path a build actually takes.
- **Preconditions:** Every backticked `YR-*` name in `attended-lane.md` must be a registry row. `[code+canon: tests/test_attended_lane_canon.py:47]`<br>Every record a lane mandates must appear in the canon's step table. `[code+canon: tests/test_attended_lane_canon.py:56]`<br>Every `YR-*` name inside the walled-act map block must be registered — the pin that exists because the arming and shared-branch conditions once named an unregistered 'human instruction' record. `[code: tests/test_attended_lane_canon.py:93]`<br>The eight attended-lane rows must carry exactly their declared field sets. `[code: tests/test_attended_lane_canon.py:66]`
- **Postconditions:** Canon and registry cannot drift on record NAMES or on the attended rows' FIELD sets. `[code: tests/test_attended_lane_canon.py:50]`<br>Nothing pins the canon's stated SURFACE column against the row's `surfaces`, nor the canon's stated condition against any reader's actual mode. `[code: tests/test_attended_lane_canon.py:93]`

#### 7. `registered` → `registered`

`T7-pin-inline-literals`

- **Actor:** an attended agent editing either a registry row or the inline literal it mirrors
- **Trigger:** any edit to `records.toml` or to one of six pinned code sites
- **Enforcement:** *partial* · **Guard site:** `tests/test_records.py:125–172` and `tests/test_wall.py:170` — reachable under `check_cmd`/CI.
- **Preconditions:** Six agreement pins hold, and only six: the claim gate's `MARKER`/`FIELDS` and strict-line mode (dev-runner.sh:888/:889), the stage-escape case arm (dev-runner.sh:1572), the review gate's verdict comparison (dev-runner.sh:2138), `textutil`'s two mode names, the epic-gate's prefix/sentinel modes for `YR-EPIC-APPROVAL` and `YR-DEBT-LEDGER`, `ledger.ROW_SCHEMA` and `merge_shadow.SCHEMA`. `[code: tests/test_records.py:125]`<br>One more pin, added by the unmerged slice 5: `board_plumbing.py` must spell `l.startswith("<row marker>")` and the row's mode must still be `prefix`. `[code: tests/test_wall.py:170]`
- **Postconditions:** Those six (plus one) literals cannot silently leave their rows. `[code: tests/test_records.py:131]`<br>No pin exists for the remaining ~30 rows' literals, for any row's `emitter`/`readers` strings, or for any cited line number. `[code: records.toml:290]`

#### 8. `umbrella-marker-bound` → `umbrella-marker-bound`

`T8-bind-marker-constant`

- **Actor:** an attended agent editing `[marker].yr`
- **Trigger:** a marker rebrand or port
- **Enforcement:** *partial* · **Guard site:** `tools/records.py::_validate` (:89) — family consistency inside the file only. Nothing checks the tree's ~20 inline `YR-` constants against it.
- **Preconditions:** After the edit, every row whose `name` starts with the new constant must carry a `marker` that also starts with it, or the registry refuses to load. `[code: tools/records.py:89]`<br>The live registry's constant must be exactly `YR-`. `[code: tests/test_records.py:33]`<br>'A future marker change is one edit here plus a migration round, never a hunt.' `[canon-only: records.toml:30]`
- **Postconditions:** `records.py marker` prints the new value; `records.py validate` reports it. `[code: tools/records.py:147]`<br>No production matcher changes: `marker_constant()` is consumed only by the CLI (records.py:143, :147) and by tests (test_records.py:33, :49). Every real matcher takes either a row's own `marker` literal or a module-level hardcoded constant. `[code: tools/records.py:106]`

#### 9. `detector-unrun` → `detector-clean`

`T9-invoke-detector`

- **Actor:** a human or an attended agent, by hand at a shell
- **Trigger:** someone types `python3 tools/check_trail.py --lane <lane> [--repo R] [--issue N] [--pr N] [--vault-root P --vault-doc D]`. Nothing else ever triggers it.
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None — there is no caller anywhere in the tree. Verified: the only non-test references to `check_trail` are `AGENTS.md:108`, `README.md:24`, seven `readers =` strings in `records.toml`, `attended-lane.md:21`, and one line of compiled slice prose at `compile_slice.py:99`. `architect.md`'s ship-walk step and `closing.md` never name it.
- **Preconditions:** `--lane` is required and caller-supplied; there is no inference from issue type, sub-issue parent, doc type, or repo. `[code: tools/check_trail.py:191]`<br>The scope is caller-supplied: no discovery of which issues, PRs or vault docs belong to the round. `[code: tools/check_trail.py:193]`<br>`--repo` defaults to the hardcoded `yellow-robots/factory`. `[code: tools/check_trail.py:192]`<br>The detector runs 'at ship-walk or census time over a declared scope'. `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)]`
- **Postconditions:** Every mandated record was found present and field-complete; stdout carries one 'check_trail: ok' line and the process exits 0. `[code: tools/check_trail.py:227]`<br>Nothing durable is written — no trail comment, no board field, no file, no ledger row. `[code: tools/check_trail.py:222]`

#### 10. `detector-unrun` → `detector-nothing-mandated`

`T10-detector-empty-lanes`

- **Actor:** the detector process
- **Trigger:** an invocation against a registry whose `[lanes]` table is absent or empty
- **Enforcement:** detected · **Guard site:** `tools/check_trail.py::check_texts` (:115–117) and `_cli` (:203–205).
- **Preconditions:** `records.lanes(reg)` returns an empty mapping. `[code: tools/records.py:121]`<br>An absent or empty lanes table means nothing mandated — clean exit, stated in output; never an error. `[code+canon: tools/check_trail.py:11]`
- **Postconditions:** `check_texts` returns `[]` before any row is examined; the CLI prints 'nothing mandated' and exits 0. `[code: tools/check_trail.py:203]`

#### 11. `detector-unrun` → `detector-lane-unknown`

`T11-detector-unknown-lane`

- **Actor:** the detector process
- **Trigger:** `--lane` names a key the `[lanes]` table does not carry
- **Enforcement:** detected · **Guard site:** `tools/check_trail.py::check_texts` (:118–120).
- **Preconditions:** `lanes.get(lane)` is None while `lanes` is non-empty. `[code: tools/check_trail.py:119]`
- **Postconditions:** Exactly one finding naming the lane and listing the known lanes; exit 1. No record is examined. `[code: tools/check_trail.py:120]`

#### 12. `detector-unrun` → `detector-surface-unreadable`

`T12-detector-no-surface`

- **Actor:** the detector process
- **Trigger:** a mandated row's declared surfaces got no text in this invocation
- **Enforcement:** detected · **Guard site:** `tools/check_trail.py::check_texts` (:124–128); CLI surface population at `_cli` (:206–218).
- **Preconditions:** `texts_by_surface` carries nothing for any surface the row declares. `[code: tools/check_trail.py:124]`<br>A named vault path that cannot be read is an ERROR, never a silent narrowing of the scope. `[code: tools/check_trail.py:177]`
- **Postconditions:** One finding per row: '<lane>: <name>: no readable surface in scope (row surfaces: …)'; exit 1. `[code: tools/check_trail.py:126]`<br>Four of the eight declared surfaces — `run-dir`, `stage-log`, `ledger`, `bench` — have NO CLI fetcher, so a lane mandating `VERDICT`, `STAGE-BLOCKED`, `yr-ledger-row/1`, `yr-bench-corpus/1`, `yr-bench-result/1` or `yr-verdict-diff/1` can only ever reach this state from the CLI. `[code: tools/check_trail.py:206]`

#### 13. `detector-unrun` → `detector-record-absent`

`T13-detector-absent`

- **Actor:** the detector process
- **Trigger:** texts exist for the row's surfaces but none matches the marker under the row's mode
- **Enforcement:** detected · **Guard site:** `tools/check_trail.py::_marker_present` (:37–62) and `_json_schema_present` (:65–82); reached from `check_texts` (:129).
- **Preconditions:** `_marker_present` is false. Mode dispatch: `prefix` → `textutil.marker_line_matches(mode=MARKER_PREFIX)` (raw column-0 startswith, no whitespace tolerance); `sentinel` → `MARKER_SENTINEL` (line.strip() == marker); `strict-line` → `l.rstrip() == marker`; `verdict-line` → `l.startswith(marker)`; `stage-escape` → last non-empty line startswith marker AND non-empty remainder; `json-schema` → some JSON OBJECT (whole text, a fenced block, or a single line) parses with `"schema" == marker`. `[code: tools/check_trail.py:37]`<br>Presence and registry grammar only, never content judgment. `[code+canon: 04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)]`
- **Postconditions:** One finding per absent row naming the marker and mode; exit 1. Verified live at this HEAD: design lane on the it-30 governing spec reports all three design records absent; close lane on issue #415 reports both close records absent. `[code: tools/check_trail.py:130]`

#### 14. `detector-unrun` → `detector-record-malformed`

`T14-detector-malformed`

- **Actor:** the detector process
- **Trigger:** a marker-carrying text exists but no single one carries every declared field
- **Enforcement:** detected · **Guard site:** `tools/check_trail.py::_missing_fields` (:85–109); reached from `check_texts` (:133).
- **Preconditions:** A field counts as present when a line, lstripped, starts with `<field>:`, or carries a boundary-anchored `<field>=`. Both forms are CASE-SENSITIVE. `[code: tools/check_trail.py:101]`<br>Fields must be complete within ONE marker-carrying text; pooling across comments never satisfies. The reported set is the fewest-missing candidate. `[code: tools/check_trail.py:94]`<br>Values are never judged: `review: THIS REVIEW NEVER HAPPENED` passes. `[code: tests/test_check_trail.py:96]`
- **Postconditions:** One finding naming the missing field(s); exit 1. `[code: tools/check_trail.py:135]`<br>Field-level rules the real readers apply are NOT applied here — notably the claim gate's placeholder refusal on `fit:` (n/a, none, exempt, skipped, tbd, -), which the row's own `notes` states. `[code: tools/dev-runner.sh:892]`

#### 15. `detector-unrun` → `detector-error`

`T15-detector-error`

- **Actor:** the detector process
- **Trigger:** the registry fails to load, a `gh` call fails or `gh` is unavailable, a named vault doc is unreadable, or `--vault-doc` was passed without `--vault-root`
- **Enforcement:** **prevented** · **Guard site:** `tools/check_trail.py::_cli` (:198–221), `_gh_json` (:142–149), `fetch_vault_docs` (:176–185).
- **Preconditions:** `records.load()` raised `RegistryError`, or a fetcher raised `RuntimeError`, or the arg pair is incomplete. `[code: tools/check_trail.py:198]`
- **Postconditions:** Message on stderr; exit 2, deliberately distinct from the findings exit 1. `[code: tools/check_trail.py:201]`<br>Comment fetches are page-safe (100-per-page loop), so a record past the `--json comments` cap can never read as absent. `[code: tools/check_trail.py:152]`

#### 16. `registered` → `record-emitted`

`T16-machine-emit-pipeline-records`

- **Actor:** machine emitters: the merge evaluator (`tools/merge_shadow.py`), the epic-gate sweep (`tools/epic_gate.py`), the dev-runner (`tools/dev-runner.sh`), `tools/verdict_diff.py`, `tools/ledger.py`, `tools/bench_corpus.py`, `tools/bench_replay.py`, `tools/promote.sh`
- **Trigger:** the emitting stage runs (a merge decision, a sweep pass, a review round, a lens run, a ledger append, a corpus/replay run, an operator promote)
- **Enforcement:** *partial* · **Guard site:** Each emitter's own code path. None consults the registry; the only binding between emitter and row is the six agreement pins in `tests/test_records.py:125–172`.
- **Records:** `YR-MERGE`, `YR-MERGE-SHADOW`, `yr-merge-record/1`, `YR-AUTO-PROMOTED`, `YR-EPIC-GATE: no-approval`, `YR-EPIC-GATE: not-a-task`, `YR-EPIC-GATE: not-onboarded`, `YR-EPIC-GATE: open-questions`, `YR-EPIC-GATE: gate-touching`, `YR-EPIC-GATE: stranded claim`, `YR-DEBT-HOLD`, `YR-DEBT-DUE`, `YR-SHADOW-REVIEW`, `YR-LENS`, `YR-NIT`, `VERDICT`, `YR-VERDICT-DIFF`, `yr-verdict-diff/1`, `yr-ledger-row/1`, `yr-bench-corpus/1`, `yr-bench-result/1`, `YR-PROMOTED`
- **Preconditions:** Each emitter's own gate conditions — not the registry's. No emitter reads `records.toml` to build its output; every one carries a hardcoded literal. `[code: tools/merge_shadow.py:51]`<br>`YR-PROMOTED` lands BEFORE the Status flip, by construction: the comment post must succeed or `promote.sh` dies without flipping. `[code+canon: tools/promote.sh:77]`
- **Postconditions:** `YR-MERGE:` / `YR-MERGE-SHADOW:` plus a fenced ```yr-merge-record JSON block on the PR trail. `[code: tools/merge_shadow.py:216]`<br>`YR-AUTO-PROMOTED` (epic_gate.py:496), the five `YR-EPIC-GATE: *` raise bodies (:505, :526, :550, and the not-a-task/not-onboarded bodies), `YR-EPIC-GATE: stranded claim` (:302), `YR-DEBT-HOLD` (:566), `YR-DEBT-DUE` (:852) on issue trails. `[code: tools/epic_gate.py:496]`<br>`YR-SHADOW-REVIEW:` (dev-runner.sh:2301), `YR-LENS (advisory)` (:2358), and the review comment carrying `VERDICT:` and `YR-NIT:` lines. `[code: tools/dev-runner.sh:2301]`<br>`YR-VERDICT-DIFF:` plus a `yr-verdict-diff/1` record (verdict_diff.py:90, :30); `yr-ledger-row/1` rows (ledger.py:185); `yr-bench-corpus/1` (bench_corpus.py:51); `yr-bench-result/1` (bench_replay.py:78). `[code: tools/verdict_diff.py:90]`

#### 17. `registered` → `record-emitted`

`T17-stage-emit-escape`

- **Actor:** a dev-runner implement or test stage (a cold `claude -p` process)
- **Trigger:** the stage judges the task undoable within the pipeline's rules
- **Enforcement:** **prevented** · **Guard site:** `tools/dev-runner.sh:1572` (case arm), pinned to the row by `tests/test_records.py:137`.
- **Records:** `STAGE-BLOCKED`
- **Preconditions:** The log's LAST non-empty line must begin exactly `STAGE-BLOCKED: ` with a non-empty reason — deliberately stricter than the verdict gate's last-line rule. `[code+canon: tools/dev-runner.sh:1560]`
- **Postconditions:** The case arm `"STAGE-BLOCKED: "?*)` fires and routes to the Blocked outcome, quoting the reason and skipping every remaining stage. `[code: tools/dev-runner.sh:1572]`

#### 18. `registered` → `record-emitted`

`T18-attended-emit-trail-records`

- **Actor:** an attended session or the human, typing a comment onto an issue or PR trail
- **Trigger:** reaching the reified step the record traces (standing approval, the standalone gates check, a board flip, the ship-walk, the close, an escalation, the human's explicit instruction)
- **Enforcement:** *partial* · **Guard site:** For `YR-EPIC-APPROVAL`: `tools/epic_gate.py::_has_valid_approval` (:429), reached at the promotion path (:979) — prevented. For `YR-TASK-GATES`: `tools/dev-runner.sh:911` at claim — prevented downstream of the act; and (slice 5, UNMERGED) `tools/promote.sh:69` → `tools/wall.py::promote_check` (:360) — prevented at the act. For the other five: no guard on origin/main.
- **Records:** `YR-EPIC-APPROVAL`, `YR-TASK-GATES`, `YR-BOARD-FLIP`, `YR-SHIP-WALK`, `YR-ROUND-RECORD`, `YR-ESCALATION`, `YR-HUMAN-INSTRUCTION`
- **Preconditions:** The canon enumerates each step and its record; reification adds records, never new duties. `[canon-only: skills/factory/references/attended-lane.md:27]`<br>For `YR-EPIC-APPROVAL`: all three of design/review/who non-empty, or the epic-gate blocks every child's promotion. `[code+canon: tools/epic_gate.py:429]`<br>For `YR-TASK-GATES`: a comment whose own line is exactly the marker, carrying review/fit/who, with `fit:` not a placeholder. On origin/main this is checked only at claim; the promote-act check exists only in the unmerged slice 5. `[code+canon: tools/dev-runner.sh:911]`<br>For `YR-BOARD-FLIP`, `YR-SHIP-WALK`, `YR-ROUND-RECORD`, `YR-ESCALATION`, `YR-HUMAN-INSTRUCTION`: nothing checks the record before the act on origin/main — no reader exists there at all. `[code: records.toml:351]`
- **Postconditions:** A comment body on the issue/PR trail carrying the marker line plus its fields. Verified live: issue #415 satisfies the `epic` lane (YR-EPIC-APPROVAL present and field-complete). `[code: records.toml:55]`<br>For the close lane, nothing is written today: `check_trail --lane close --issue 415` reports both `YR-SHIP-WALK` and `YR-ROUND-RECORD` absent. `[code: records.toml:391]`

#### 19. `registered` → `record-never-emitted`

`T19-attended-emit-vault-records`

- **Actor:** the independent cold reviewer (YR-DESIGN-REVIEW), the architect at the spec-ready moment (YR-DESIGN-FIT), and the accepting session (YR-ACCEPT), typing lines into the reviewed/accepted vault doc
- **Trigger:** the design-side steps 2–4 of the reified step set
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** None. The vault lifecycle-stamp wall that would demand them exists only in the unmerged slice 5 (`tools/wall.py:235` names the rule), and even there `decide()` denies the act unconditionally without reading any record — `_trail_has` (wall.py:205) has zero callers.
- **Records:** `YR-DESIGN-REVIEW`, `YR-DESIGN-FIT`, `YR-ACCEPT`
- **Preconditions:** The design-side records are typed lines in the vault docs themselves — no new surface (the crossing ruling of 2026-08-07). `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/02-crossing-rulings.md > it-30 crossing — night rulings (2026-08-07)]`<br>`vault-doc` is in the loader's closed surface set, so the canon slice adds rows rather than code. `[code: tools/records.py:37]`
- **Postconditions:** No such record exists anywhere. A scan of `04 projects/factory/` finds `YR-DESIGN-REVIEW`/`YR-DESIGN-FIT`/`YR-ACCEPT` in exactly one file — the it-30 verification record, and only as prose about their absence. Running the design lane against the round's own governing spec reports 3 of 3 absent. `[code: records.toml:388]`<br>The round's own testimony records the same: 'it-30's own governing spec fails the detector this round shipped, 3 of 3 on the design lane: its review, fit and accept records are prose, because the grammars were minted after the accept act.' `[canon-only: 04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications]`

#### 20. `registered` → `record-emitted`

`T20-author-emit-body-declarations`

- **Actor:** the architect (YR-GATE-TOUCHING), a design author (YR-OPEN-QUESTION), a debt-epic author (YR-ITERATION-KIND, YR-DEBT-LEDGER)
- **Trigger:** filing or editing an issue body / posting the debt round's close verdict
- **Enforcement:** **prevented** · **Guard site:** `tools/epic_gate.py`: `_open_question_lines` (:450), `_gate_touching_declaration` (:460), `_is_debt_epic` (:474), `_has_ledger_verdict` (:481) — all reached on the sweep's promotion path.
- **Records:** `YR-GATE-TOUCHING`, `YR-OPEN-QUESTION`, `YR-ITERATION-KIND`, `YR-DEBT-LEDGER`
- **Preconditions:** `YR-OPEN-QUESTION:` must never ride a filed epic — the airlock rule; presence alone blocks every slice. `[code+canon: records.toml:109]`<br>`YR-GATE-TOUCHING:` needs a non-empty reason after the prefix. `[code: tools/epic_gate.py:467]`<br>`YR-DEBT-LEDGER` needs non-empty `items` and `net-lines` — the machine-checked pair; the template mandates seven fields. `[code+canon: tools/epic_gate.py:481]`
- **Postconditions:** The sweep refuses that child's promotion (gate-touching), blocks every slice (open-question), classes the epic as debt (iteration-kind), or self-closes the debt epic (ledger verdict). `[code: tools/epic_gate.py:460]`

#### 21. `record-emitted` → `record-emitted`

`T21-registry-driven-read`

- **Actor:** `tools/wall.py` (UNMERGED slice 5) — the only production code that resolves a grammar THROUGH the registry
- **Trigger:** `tools/promote.sh:69` shells out to `wall.py promote-check` before its own promotion record
- **Enforcement:** **prevented** · **Guard site:** `tools/wall.py::promote_check` (:360–376), reached from `tools/promote.sh:69`. This exists ONLY on the unmerged slice-5 branch; `origin/main`'s `promote.sh` has no such call.
- **Preconditions:** `records.load()` then `records.get(reg, "YR-TASK-GATES")`; the marker and field list come from the row, not from a copy. `[code: tools/wall.py:361]`<br>Presence rule: `l.rstrip() == row["marker"]` over COMMENT bodies only; fields: `l.lstrip().startswith(f"{f}:")`, case-sensitive, pooled across all comment lines. `[code: tools/wall.py:369]`<br>Fail-closed: an unreadable trail refuses, naming what it could not read. `[code+canon: tools/wall.py:366]`
- **Postconditions:** Exit 0 lets `promote.sh` post `YR-PROMOTED` and flip Status; exit 1 makes `promote.sh` refuse and write nothing. `[code: tools/promote.sh:69]`<br>`board_check` (wall.py:325) resolves `YR-BOARD-FLIP` through the registry the same way — and has ZERO callers anywhere in the tree. `[code: tools/wall.py:325]`

#### 22. `record-emitted` → `record-emitted`

`T22-inline-read`

- **Actor:** every other reader in the tree: `tools/dev-runner.sh` (claim gate, review gate, stage-escape), `tools/epic_gate.py`, `tools/merge_shadow.py`, `tools/nit_harvest.py`, `tools/review_bundle.py`, `tools/bench_report.py`, `tools/board_plumbing.py` (unmerged)
- **Trigger:** the reader's own gate runs
- **Enforcement:** *partial* · **Guard site:** `tests/test_shared_marker_matcher.py:360` — a tree-derived guard reachable under `check_cmd`/CI. It scans `tools/*.py` and `qa/*.py` only, for LITERAL or module-constant matchers; a matcher over a registry-supplied variable (as in `check_trail.py:50` and `wall.py:369`) is invisible to it.
- **Preconditions:** Each reader carries its own hardcoded marker constant and its own anchoring rule; none loads `records.toml`. `[code: tools/epic_gate.py:347]`<br>Two anchoring modes are shared through `textutil.marker_line_matches`; the other four registry modes have no shared implementation. `[code: tools/textutil.py:42]`<br>A hand-rolled `YR-*` matcher outside `tools/textutil.py` is refused tree-wide. `[code: tests/test_shared_marker_matcher.py:360]`
- **Postconditions:** The gate disposes: promotion blocked/allowed, claim bounced to Needs-info, review approved, merge record parsed back, nit harvested, verdict-diff swept. `[code: tools/dev-runner.sh:2138]`<br>At this worktree HEAD the tree-wide matcher guard FAILS: `tools/board_plumbing.py:145` spells `l.startswith("YR-BOARD-FLIP:")` inline, and `tests/test_shared_marker_matcher.py::test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree` names it as the offender. `[code: tools/board_plumbing.py:145]`

#### 23. `registered` → `registered`

`T23-registry-edit-is-gate-touching`

- **Actor:** an attended agent changing the registry, the detector, the walls, or delivery
- **Trigger:** a slice whose mandate touches the enforcement layer
- **Enforcement:** ⚠️ **unenforced** · **Guard site:** `tools/epic_gate.py::_gate_touching_declaration` (:460) — reachable, but keyed on an author-written body line, never on the change's content.
- **Records:** `YR-GATE-TOUCHING`, `YR-EPIC-GATE: gate-touching`
- **Preconditions:** 'A change whose mandate touches the enforcement layer — walls, registry, detector, delivery — is gate-touching attended work, the same declaration duty as checks, CI, and the manifest.' `[canon-only: skills/factory/references/attended-lane.md:105]`<br>The epic-gate's only gate-touching reader parses a `YR-GATE-TOUCHING:` line off a slice's ISSUE BODY. It never inspects a diff, a path, or a file list. `[code: tools/epic_gate.py:460]`
- **Postconditions:** If the author writes the declaration, the sweep refuses that child's promotion and it stays attended. If the author does not, nothing notices that `records.toml` or `check_trail.py` changed. `[code: tools/epic_gate.py:1035]`

## Where the code and the canon disagree

### [material] `YR-HUMAN-INSTRUCTION` declares `tools/wall.py` as a reader; wall.py never reads it

- **code:** `tools/wall.py` contains no reference to `YR-HUMAN-INSTRUCTION` at all. The only trail-marker helper, `_trail_has` (wall.py:205), has zero callers anywhere in the tree. In `decide()`, the acts the row is meant to condition — `push-shared` and `arming-edit` — fall straight through to the unconditional `_emit_event("refusal", …)` + deny; only `crossing-file` has a satisfiable branch (wall.py:253–257).
- **canon:** records.toml:399 — `readers = ["tools/wall.py (slice 5 — the arming and shared-branch wall conditions)", "tools/check_trail.py"]`; attended-lane.md:56 and :59 state both conditions as requiring the record. `tests/test_attended_lane_canon.py:93` exists precisely so a wall condition cannot name an unregistered record — but nothing checks the converse, that the named reader reads.
- `records.toml:399`, `tools/wall.py:205`, `tools/wall.py:244`, `skills/factory/references/attended-lane.md:56`, `tests/test_attended_lane_canon.py:93`

### [material] Three rows declare `tools/check_trail.py` as a reader while sitting in no lane, so the detector can never read them

- **code:** `check_texts` iterates only `lanes.get(lane)` (check_trail.py:118–121). `YR-BOARD-FLIP`, `YR-ESCALATION` and `YR-HUMAN-INSTRUCTION` appear in no list under `[lanes]` (records.toml:387–391), so no invocation of the detector, for any lane, ever examines them.
- **canon:** records.toml:351, :381, :399 each name `tools/check_trail.py` in `readers`. The round's own testimony states the consequence: '`YR-BOARD-FLIP` is in no lane, so the detector never checks the one record the walls most depend on'.
- `tools/check_trail.py:118`, `records.toml:351`, `records.toml:381`, `records.toml:399`, `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications`

### [material] The five `YR-EPIC-GATE: *` dedup rows declare `mode = "prefix"`, but their only reader implements whole-line equality

- **code:** `tools/epic_gate.py::_has_marker` (:377–381) is `any(line.rstrip() == marker …)` — the registry's own `strict-line` mode, with no leading-whitespace tolerance and no trailing text tolerated. It is the only reader of the five raise markers (called at :965, :980, :1016, :1035, :1061).
- **canon:** records.toml:117, :125, :134, :143, :152 all declare `mode = "prefix"`, and records.toml:11 defines prefix as 'the RAW line begins with the marker at column 0'. Under the declared mode a line `YR-EPIC-GATE: no-approval — resolved` would count as present; under the actual reader it would not, and the sweep would re-post its refusal.
- `tools/epic_gate.py:377`, `records.toml:117`, `records.toml:11`, `tools/epic_gate.py:980`

### [material] `yr-merge-record/1` names a reader function that does not exist

- **code:** `tools/merge_shadow.py` has no `_extract_record`. The function that parses the fenced block back is `_parse_record_block` (:223); the marker-line locator is `_record_marker_offset` (:240).
- **canon:** records.toml:282 — `readers = ["tools/merge_shadow.py _extract_record (:224-235 — re-evaluation and shadow-complete parse it back)"]`.
- `records.toml:282`, `tools/merge_shadow.py:223`, `tools/merge_shadow.py:240`

### [material] The detector's `issue-trail` bucket includes the issue BODY; every real issue-trail reader reads comments only

- **code:** `fetch_issue_trail` returns `[body] + comments` and `_cli` extends `issue-trail` with the whole list (check_trail.py:166–168, :210). The real readers are comments-only: `epic_gate._has_valid_approval(comments)` (:429), the claim gate's `bodies = [… for c in d.get("comments")]` (dev-runner.sh:941), `wall.promote_check` via `_comment_bodies` (wall.py:363).
- **canon:** records.toml:19 declares `issue-trail` and `issue-body` as distinct surfaces, and `YR-EPIC-APPROVAL`/`YR-TASK-GATES` declare `surfaces = ["issue-trail"]` only (records.toml:62, :72).
- `tools/check_trail.py:168`, `tools/check_trail.py:210`, `tools/epic_gate.py:429`, `tools/dev-runner.sh:941`, `tools/wall.py:363`

### [material] The detector's field grammar is case-sensitive; two of the three real field readers are case-insensitive

- **code:** `check_trail._missing_fields` uses `l.lstrip().startswith(f"{f}:")` and `re.search(rf"(^\|\s){f}=")` — no case folding (check_trail.py:101). `epic_gate._extract_field` lowercases both key and line (:386–388); the claim gate's `extract` compares `s[:len(prefix)].lower() == prefix` (dev-runner.sh:895–902). A comment reading `Who: @op` satisfies the epic gate and is reported malformed by the detector.
- **canon:** records.toml:59, :69 declare the same field names for both rows, with no case rule stated anywhere; the detector's own docstring claims the rule matches 'the two field forms the tree's grammars use'.
- `tools/check_trail.py:101`, `tools/epic_gate.py:386`, `tools/dev-runner.sh:895`, `tools/check_trail.py:88`

### [material] The detector calls a `YR-TASK-GATES` record well-formed that the claim gate bounces

- **code:** `check_trail` checks only that lines `review:`/`fit:`/`who:` exist (check_trail.py:101). The claim gate additionally refuses a `fit:` value in `{n/a, none, exempt, skipped, tbd, -}` (dev-runner.sh:892, :916). `fit: n/a` therefore reads clean to the detector and bounces the task to Needs-info at claim.
- **canon:** records.toml:73 — the row's own `notes` state the placeholder rule: 'fit: refuses the placeholder set (n/a, none, exempt, skipped, tbd, -)'. The registry has no machine-readable place to carry it, and no consumer applies it.
- `records.toml:73`, `tools/check_trail.py:101`, `tools/dev-runner.sh:892`, `tools/dev-runner.sh:916`

### [material] The canon claims violations are detectable and the spec puts the detector at ship-walk and census time; no procedure or code ever runs it

- **code:** `tools/check_trail.py` has no caller. Its only non-test references in the tree are `AGENTS.md:108`, `README.md:24`, seven `readers =` strings in `records.toml`, `attended-lane.md:21`, and one line of compiled slice prose (`compile_slice.py:99`). It is absent from `.yr/factory.toml`'s `check_cmd`, `lint_cmd` and `lens_cmd`, and from `.github/workflows/ci.yml`.
- **canon:** attended-lane.md:21 — 'violations are detectable (`tools/check_trail.py` verifies presence and grammar against the registry)'. The spec's criterion: 'THE DETECTOR SHALL verify deterministically, at ship-walk or census time over a declared scope…'. But `architect.md:39` (the ship-walk step) and `closing.md` never name it, and `debt-rounds.md`'s census arms never name it.
- `skills/factory/references/attended-lane.md:21`, `skills/factory/references/architect.md:39`, `.yr/factory.toml:3`, `tools/check_trail.py:16`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)`

### [blocking] `tools/board_plumbing.py` hand-rolls a second matcher for a registry grammar; the tree-wide guard is red at this HEAD

- **code:** `board_plumbing.py:145` — `if any(l.startswith("YR-BOARD-FLIP:") for l in lines)`. `tests/test_shared_marker_matcher.py::test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree` FAILS at this HEAD naming exactly that hit. Meanwhile `tools/wall.py::board_check` (:325–357) implements the same condition through `records.get(reg, "YR-BOARD-FLIP")` and has zero callers.
- **canon:** The comment at board_plumbing.py:141–144 justifies the inline spelling ('this home imports stdlib only, by standing invariant') and points at `tests/test_wall.py:170` as the pin. The standing invariant it invokes does not hold: `textutil` is itself stdlib-only and `epic_gate.py` (a sibling) already imports it.
- `tools/board_plumbing.py:145`, `tests/test_shared_marker_matcher.py:360`, `tools/wall.py:325`, `tests/test_wall.py:170`, `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications`

### [material] `YR-ROUND-RECORD`'s four declared fields have no producer

- **code:** The only machine that counts anything is `tools/wall.py::_emit_event` (:77–88), whose `kind` values are `pass`, `refusal`, `close-block`, `close-override`. There is no producer of 'records-demanded', no producer of 'detector-findings' (the detector writes nothing durable — check_trail.py:222–229), and no producer of 'escalations' (nothing reads or writes `YR-ESCALATION`).
- **canon:** records.toml:369 — `fields = ["refusals", "records-demanded", "detector-findings", "escalations"]`; attended-lane.md:100 states these counts 'are emitted where the round reads them'. The spec's final criterion mandates them.
- `records.toml:369`, `tools/wall.py:84`, `tools/check_trail.py:222`, `skills/factory/references/attended-lane.md:100`

### [material] `tools/wall.py`'s counts file is a machine-written, machine-parsed grammar on a shared cross-session surface with no registry row and no matching surface value

- **code:** `_emit_event` appends `{ts, kind, session, act, detail}` JSON objects to `$YR_WALL_STATE/counts.jsonl` (default `~/.cache/yr-attended/counts.jsonl`); `read_counts` (:91–107) parses them back; `main` exposes them via a `counts` subcommand (:396–399). The objects carry no `schema` key, so even the `json-schema` mode could not match them.
- **canon:** records.toml:20–22 excludes only 'unversioned per-run artifacts the runner both writes and reads inside one run dir'. This file is not a run-dir artifact and is read across sessions. The spec's criterion is 'THE REGISTRY SHALL name every machine-parsed trail grammar … in exactly one machine-readable home'. `records.py:38`'s closed `SURFACES` set has no value that fits it.
- `tools/wall.py:84`, `tools/wall.py:91`, `records.toml:20`, `tools/records.py:38`, `04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md > Acceptance criteria (EARS)`

### [material] The marker constant is documented as the one edit a rebrand needs; no production matcher consumes it

- **code:** `records.marker_constant()` (records.py:106) is called only by the CLI (`validate` at :143, `marker` at :147) and by tests (test_records.py:33, :49). The loader's family rule reads `data.get("marker")` inline (:59, :89). Every real matcher uses either a row's own `marker` literal or a module-level hardcoded constant (`epic_gate.py:347`, `merge_shadow.py:51`, `nit_harvest.py:56`, `board_plumbing.py:145`, `dev-runner.sh:888`).
- **canon:** records.toml:30 — 'A future marker change is one edit here plus a migration round, never a hunt.' The spec criterion: 'THE REGISTRY SHALL define the record marker (`YR-`, as ratified) as a single named constant, so a future marker change is one migration round, never a hunt.'
- `records.toml:30`, `tools/records.py:106`, `tools/epic_gate.py:347`, `tools/merge_shadow.py:51`, `tools/dev-runner.sh:888`

### [minor] Registry line citations are unverified and already wrong — two against origin/main, and every epic_gate / dev-runner / promote.sh citation against this worktree HEAD

- **code:** Wrong on origin/main too: `yr-bench-corpus/1` cites `tools/bench_corpus.py (:25)` — `SCHEMA` is at :51; `yr-bench-result/1` cites `tools/bench_replay.py (:48)` — `SCHEMA` is at :78. Drifted by the unmerged slice-5 edits at this HEAD: `_has_valid_approval` :420→:429, gate-touching :462→:467, open-question :452→:457, debt-kind :472→:477, auto-promoted :491→:496, debt-hold :561→:566, debt-due :821/:830/:847→:826/:835/:852, hold read :938→:943, stranded :297→:302; claim gate ~:882→:888, stage-escape :1554-1566→:1559-1572, review gate :321-326/:2129-2132→:327-332/:2135-2138, shadow :2295→:2301, lens :2352→:2358, promote.sh :68→:75.
- **canon:** records.toml:7 — 'The tree is the territory — every row cites its emitter and reader sites'. No test verifies any `emitter`/`readers` string; `tools/records.py:75–80` checks only that the strings are non-empty.
- `records.toml:7`, `records.toml:290`, `tools/bench_corpus.py:51`, `records.toml:299`, `tools/bench_replay.py:78`, `tools/records.py:75`

### [minor] The registry carries build state, which the org's knowledge model forbids

- **code:** records.toml:71 and :351 both read '(slice 5 — future reader, not at tip)'. At this worktree HEAD both readers ARE at tip (`tools/promote.sh:69` → `wall.py:360`; `board_plumbing.py:112`); on `origin/main` neither exists. The parenthetical is true of neither ref.
- **canon:** AGENTS.md > Where knowledge lives — 'Rules, never state. Anything with a lifecycle belongs to the surface that owns that lifecycle; an AGENTS file that tracks state is rotting.' Work state belongs on 'the board + issue/PR trails — never a doc.'
- `records.toml:71`, `records.toml:351`, `tools/promote.sh:69`, `tools/board_plumbing.py:112`, `AGENTS.md > Where knowledge lives`

### [minor] The detector hardcodes the factory's own repo as its default scope

- **code:** `ap.add_argument("--repo", default="yellow-robots/factory")` — check_trail.py:192.
- **canon:** AGENTS.md > Invariants — 'Repo-agnostic. Builds any registered repo via its manifest; the factory holds no product knowledge'. The same class of defect was a slice-4 review blocker: the position element once hardcoded `--repo yellow-robots/factory` and told a website session the factory's PRs were its position.
- `tools/check_trail.py:192`, `AGENTS.md > Invariants — and why`, `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > The three verifications`

### [minor] The closed mode vocabulary claims six modes; only two have a shared implementation, and the detector hand-rolls the other four inside itself

- **code:** `textutil.marker_line_matches` implements `sentinel` and `prefix` only, raising on any other mode (textutil.py:63–68). `check_trail._marker_present` implements `strict-line` (`l.rstrip() == marker`, :50), `verdict-line` (`l.startswith(marker)`, :53), `stage-escape` (:55–57) and `json-schema` (:59–60, :65–82) inline. These are invisible to the wall-11 anti-recurrence guard, which only flags literal or module-constant matchers.
- **canon:** records.toml:10–17 presents all six as one closed vocabulary and says 'tools/textutil.py holds the two shared anchoring modes; the other four name reader disciplines the registry documents' — a documented split, but the practical effect is that four modes have two independent implementations (the detector's and each reader's) with nothing pinning them together.
- `tools/textutil.py:63`, `tools/check_trail.py:49`, `records.toml:10`, `tests/test_shared_marker_matcher.py:329`

### [material] The canon's walled-act map is merged to main and names records whose only readers are unmerged and rejected

- **code:** `skills/factory/references/attended-lane.md` (the walled-act map, :53–62) is on `origin/main`. On `origin/main`, `tools/promote.sh` has no gates-record check, `tools/board_plumbing.py` has no `_attended_wall` and no `YR-BOARD-FLIP` reader, `tools/wall.py` does not exist, and `hooks/hooks.json` registers no PreToolUse or Stop hook. `.claude-plugin/plugin.json` reads `0.10.0` on both refs, so none of it reaches a session at all.
- **canon:** attended-lane.md:47–48 — 'The enforcement layer checks the stated condition and disposes per the stated stance'; :57 — the board write 'requires the YR-BOARD-FLIP record on the trail before the flip'. The verification record states the slice failed 0 of 5 acceptance criteria with 7 blockers and 'is not folded, not shipped'.
- `skills/factory/references/attended-lane.md:47`, `.claude-plugin/plugin.json:5`, `tools/promote.sh:69`, `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md > What shipped, and what did not`

## Gaps

- **No tree-wide scan for unregistered `YR-*` tokens exists. The registry's central authority claim — 'a record absent from this registry is unsanctioned' — is prose with no machine behind it. Four unregistered grammars live in the tree today: `YR-DELIVERY-FAILURE` (hooks/deliver.sh:44, MERGED to main, pinned by tests/test_compile_slice.py:124 and :168), `YR-WALL` (tools/wall.py:266 and :296, UNMERGED — the PreToolUse deny reason and the Stop block reason), `YR-DEBT-NET-LINES` (skills/factory/references/debt-rounds.md:132 and skills/factory/templates/debt-round-spec.md:54/:85, a four-field record block, pinned by tests/test_templates_declaration.py:425 and tests/test_skill_factory_router.py:689), and `YR-DEBT-SURFACE` (skills/factory/templates/debt-census.md:35, a three-field record block). Five more `YR-*` tokens are deliberate non-records: `YR-NEVER-MINTED` (tests/test_records.py:57), `YR-OPEN-QUESTIONS` (tests/test_epic_gate.py:469), `YR-GATE-TOUCHING-ISH` (tests/test_epic_gate.py:1009), `YR-MERGE-PLAN` (tests/test_shared_marker_matcher.py:199), `YR-MERGE-prefixed` (tools/dev-runner.sh:2333 prose); and `YR-SHADOW-RE` appears only as a line-wrap artifact inside frozen bench evidence under bench/results/, which textutil.is_frozen_bench_evidence:31 names as a record surface, not a living doc.**<br>The round that ratified 'one marker, one home' minted two new markers outside the home in its own slices, and the registry's own authority sentence cannot catch either.
- **Nothing verifies that a row's `emitter` or `readers` strings name a file, function or line that exists. `tools/records.py:75–80` checks only non-emptiness; the six agreement pins in tests/test_records.py:125–172 bind six specific literals, never the citation strings.**<br>Two rows already cite lines wrong against origin/main (bench_corpus :25 vs :51, bench_replay :48 vs :78), one names a function that does not exist (`merge_shadow.py _extract_record`), and every epic_gate/dev-runner citation silently drifted 5–6 lines when slice 5 touched those files.
- **`tools/check_trail.py` has no automated caller of any kind: no CI step (.github/workflows/ci.yml runs only pytest), no `check_cmd`/`lint_cmd`/`lens_cmd` entry (.yr/factory.toml:3, :25, :31), no runner stage, no epic-gate call, no dispatch hook, and no procedure in any operating reference (architect.md:39's ship-walk step and closing.md never name it; debt-rounds.md's census arms never name it).** **← needs an owner ruling**<br>The lane's whole detection half rests on someone remembering to type a command — the exact failure mode the round was built to end.
- **No lane inference exists. `--lane` is required and caller-supplied (check_trail.py:191); nothing maps an issue, a PR or a vault doc to its lane. The runner's claim gate DOES condition on issue type and sub-issue parent before demanding `YR-TASK-GATES` (dev-runner.sh:938); the detector applies whatever lane the caller names, so running `--lane standalone` against an epic child (e.g. #420) reports a legitimate absence as a finding.**<br>Findings and clean results are both caller-determined, so neither is evidence about the round without the caller's judgment attached.
- **Four of the eight declared surfaces have no CLI fetcher: `run-dir`, `stage-log`, `ledger` and `bench` (check_trail.py:206–218 populates only issue-trail, issue-body, pr-trail and vault-doc). A lane mandating `VERDICT`, `STAGE-BLOCKED`, `yr-ledger-row/1`, `yr-bench-corpus/1`, `yr-bench-result/1` or `yr-verdict-diff/1` is unreachable from the command line; only the pure `check_texts` API could check them.**<br>The registry's surface vocabulary and the detector's reach are declared as one closed set but implemented as two different sets, with nothing naming the difference.
- **29 of 37 rows are in no lane. The detector demands 8 records total, across four lanes. Every merge record, every bench schema, every census grammar, `YR-PROMOTED`, `YR-AUTO-PROMOTED`, `YR-GATE-TOUCHING`, `YR-OPEN-QUESTION`, `YR-ITERATION-KIND`, `YR-DEBT-*`, `YR-NIT`, `YR-LENS`, `YR-SHADOW-REVIEW`, `YR-VERDICT-DIFF`, `VERDICT`, `STAGE-BLOCKED`, `YR-BOARD-FLIP`, `YR-ESCALATION` and `YR-HUMAN-INSTRUCTION` are unmandated (records.toml:387–391 vs the 37 rows).** **← needs an owner ruling**<br>The lanes table is the detector's entire scope; a row not in it is registry documentation only, whatever its `readers` field claims.
- **The detector has no negative rule. `check_texts` can only demand presence; there is no way to express 'this record must NOT be here'. The airlock rule the registry itself states — `YR-OPEN-QUESTION` 'must never ride a filed epic' (records.toml:109) — is expressible only in the epic-gate's own code, never in a lane.**<br>Half the record vocabulary's semantics are presence-forbidding, and the detector's data model cannot carry them.
- **The detector has no temporal or ordering check. `YR-BOARD-FLIP` is defined as landing 'before any board Status/Reason write' (records.toml:350) and `YR-PROMOTED` as landing 'before the Status flip, by construction' (records.toml:80), but `check_texts` never reads a timestamp and neither does `board_plumbing._attended_wall` (:145 checks presence only). Record-before-flip is only guaranteed where an emitter enforces its own sequencing in code (tools/promote.sh:77 dies if the comment post fails).**<br>A record posted AFTER the act it was meant to precede is indistinguishable from a compliant one to every reader in the lane.
- **No uniqueness or conflict rule. `_marker_present` returns True on the first match and `_missing_fields` reports the FEWEST-missing candidate (check_trail.py:107), so two contradictory `YR-EPIC-APPROVAL` comments, or a malformed one plus a well-formed one, read as clean.**<br>A trail can carry mutually contradictory records and pass every check in the lane.
- **`[lanes]` sits at records.toml:387–391, physically BEFORE the file's last `[[record]]` block (`YR-HUMAN-INSTRUCTION`, :393–401). TOML parses this correctly today, but a lane key appended at the end of the file would land inside that record's table rather than in `[lanes]`, and `_validate` would not see it as a lane.**<br>The file's one structural hazard sits at the exact place a future editor is most likely to append.
- **The design lane's three records exist nowhere. A scan of `04 projects/factory/` finds `YR-DESIGN-REVIEW`/`YR-DESIGN-FIT`/`YR-ACCEPT` in exactly one file — the it-30 verification record — and only as prose about their absence. Running the design lane against the round's own governing spec reports 3 of 3 absent. Their emitters are human/agent acts with no code path, and the only wall that would demand them (the vault lifecycle stamp, wall.py:235) denies unconditionally without reading anything.** **← needs an owner ruling**<br>An entire lane of the registry is a vocabulary with no speakers; the detector's only true positives today are the design and close lanes reporting their own canon's records missing.
- **`YR-DEBT-NET-LINES` and `YR-DEBT-SURFACE` are typed record blocks with named fields, mandated by the debt-round canon (skills/factory/references/debt-rounds.md:129–134) and the census/prune templates, pinned by tests — but neither has a tool reader. The registry's stated scope is 'One row per grammar a TOOL parses off a shared surface' (records.toml:7), while the canon's authority sentence is unqualified: 'a record absent from the registry is unsanctioned'. The two rules disagree about whether these belong in the registry.** **← needs an owner ruling**<br>The registry's own breadth rule and the canon's authority sentence give opposite answers for two live, canon-mandated grammars.
- **No actor owns the registry, and no guard notices when it changes. The canon classes registry/detector edits as gate-touching attended work (attended-lane.md:105), but the only gate-touching reader parses a `YR-GATE-TOUCHING:` line off a slice's ISSUE BODY (epic_gate.py:460) — it never inspects a diff, a path, or a changed-file list. A task that edits `records.toml` or `check_trail.py` without the author writing that declaration promotes and builds like any other.**<br>The enforcement layer's self-protection rule is entirely author-declared; the machine cannot see the class of change it names.
- **`records.py validate` is not wired into any gate. `.yr/factory.toml`'s `check_cmd` is `pytest tests/ -q` and `lint_cmd` is `ruff check tools/ tests/ && python3 qa/cardinality.py`; neither invokes the loader directly. The registry is validated only as a side effect of tests importing it (tests/test_records.py:27, tests/test_check_trail.py:234, tests/test_attended_lane_canon.py:37, tools/compile_slice.py via tests/test_compile_slice.py).**<br>The registry's shape enforcement is real today but incidental — it depends on which tests happen to load the live file, not on a declared gate.
- **Nothing in the lane records its own activity. `check_trail` writes no comment, no board field, no ledger row and no file (check_trail.py:222–229) — findings exist only in the invoking terminal. There is no durable record that a detector run happened, what its scope was, or what it found.**<br>The round record's `detector-findings` field has no source, and a past run leaves no evidence any later reader can find — the same 'no durable record' condition the lane was built to end for attended acts.
- **The lane's sibling rule is asymmetric: the registry mandates fields per row and the detector checks them, but the registry has no place to carry a VALUE rule, and the one row whose value rule exists in the tree (`YR-TASK-GATES`'s placeholder refusal, records.toml:73 as prose vs dev-runner.sh:892 as code) is enforced by exactly one of its three readers.**<br>A rule that exists for one reader of one record and for no other is invisible to the registry's data model, so the detector and the promote wall both call a record well-formed that the claim gate refuses.

## Contested by the independent verifier

Claims the verifier could not support from the tree, or judged misleading. Treat these cells as unsettled.

- **State `lane-mandated`: "Exactly 8 of 37 rows are in this state, across four lanes" — repeated in the gap "The detector demands 8 records total, across four lanes".**<br>The `[lanes]` table mandates 7 records, not 8. The excavation's own enumeration proves it: design (3) + epic (1) + standalone (1) + close (2) = 7. Verified live: `records.lanes()` returns 7 distinct names and 7 total entries. 37 rows and 4 lanes are correct; the mandated count is not. `records.toml:387-391 (design/epic/standalone/close = 3+1+1+2); reproduced via `records.lanes(records.load())``
- **State `registered-unmandated`: "29 of 37 rows sit here"; gap: "29 of 37 rows are in no lane".**<br>37 rows minus 7 mandated = 30 unmandated, not 29. Computed directly against the live registry. The same off-by-one propagates from the lane-mandated miscount, so both headline numbers in the lane's central inventory are wrong. `records.toml (37 `[[record]]` blocks) vs records.toml:387-391; reproduced by diffing row names against the lanes table`
- **State `record-never-emitted` / T19 postcondition / the design-lane gap: "A scan of `04 projects/factory/` finds `YR-DESIGN-REVIEW`/`YR-DESIGN-FIT`/`YR-ACCEPT` in exactly one file — the it-30 verification record, and only as prose about their absence."**<br>Those three tokens appear in ZERO files anywhere in the vault. `grep -rl "YR-DESIGN"` over the whole vault returns nothing, and the cited verification record contains only four YR- tokens: YR-BOARD-FLIP, YR-DELIVERY-FAILURE, YR-PROMOTED, YR-WALL. The cited document does not support the claim. The CONCLUSION (the design records are never emitted) is correct and in fact stronger than stated — but the stated evidence is fabricated detail, and the citation points at a section that does not contain the tokens. `04 projects/factory/iterations/30-attended-lane-runner/03-verification-record.md — token census: YR-BOARD-FLIP, YR-DELIVERY-FAILURE, YR-PROMOTED, YR-WALL only`
- **State `detector-unrun`, T9 guard_site, and disagreement 8: the only registry references to the detector are "seven `readers =` strings in `records.toml`".**<br>There are eight. `grep -c "tools/check_trail.py" records.toml` returns 8: lines 321, 331, 341, 351, 361, 371, 381, 399. The undercount matters because the excavation uses this inventory to argue the detector has no caller — the argument survives, the census does not. `records.toml:321, :331, :341, :351, :361, :371, :381, :399`
- **Notes: "A tree-wide `grep -rahoE '\bYR-[A-Za-z0-9_-]+'` yields 34 distinct tokens."**<br>Re-running the identical command yields 35 distinct tokens. The substance is unaffected — the 9-token unregistered list and the "25 map to registry rows" split both reconcile against 35 — but the stated figure does not reproduce, so the census total should not be quoted. ``grep -rahoE '\bYR-[A-Za-z0-9_-]+' --exclude-dir=.git --exclude-dir=__pycache__ . \| sort -u` → 35 lines`
- **Disagreement on line citations: "Wrong on origin/main too" is limited to `yr-bench-corpus/1` (:25 vs :51) and `yr-bench-result/1` (:48 vs :78); every epic_gate drift is attributed to slice 5.**<br>Both bench claims verify exactly. But `YR-EPIC-APPROVAL`'s row cites `_has_valid_approval (:420)` and on origin/main that function is at :424 — :420 is inside `_approval_candidates`. So the function/line pairing was already imprecise before slice 5, and the drift framing ":420→:429" implies a correctness it never had. Every other epic_gate and dev-runner citation I checked (:452, :462, :472, :478-483, :491, :561, :821, :830, :847, :938, :297; dev-runner :882, :1566, :326, :2132, :2295, :2352) is exact on origin/main, so the drift thesis itself is well founded. `records.toml:61 vs `git show origin/main:tools/epic_gate.py` (def _has_valid_approval at :424, prefix match at :420)`
- **T6 precondition: "Every backticked `YR-*` name in `attended-lane.md` must be a registry row" — enforcement `prevented`.**<br>The guard's regex is `` `(YR-[A-Z-]+)` `` — uppercase letters and hyphens only, with a closing backtick required immediately. It structurally cannot see the five `YR-EPIC-GATE: no-approval`-style names (the colon and lowercase break the match), any lowercase JSON schema name (`yr-merge-record/1`), or the two unprefixed grammars (`VERDICT`, `STAGE-BLOCKED`). The canon could name an unregistered `YR-EPIC-GATE: <anything>` record, or a wall could condition on one, and both agreement tests would pass green. "Cannot drift on record NAMES" is true only for the all-caps subset. `tests/test_attended_lane_canon.py:42 (`re.findall(r"`(YR-[A-Z-]+)`", text)`), consumed at :49, :57, :99`
- **T6/T4 precondition: "Every record a lane mandates must appear in the canon's STEP TABLE."**<br>The test named `test_every_lane_mandated_record_appears_in_the_canon_step_table` does not scan the step table — it calls `_canon_record_names(lane_text)` over the entire file. A lane could mandate a record mentioned only in a prose paragraph, or in the walled-act map, and the test passes. The excavation restates the test's NAME as its behaviour. Today all 7 mandated records are in fact in the step table, so nothing is currently broken — but the pin is weaker than the precondition asserts. `tests/test_attended_lane_canon.py:56-63 (`named = _canon_record_names(lane_text)` over the whole document)`
- **State `detector-error` / T15: "Exit 2 — deliberately distinct from exit 1 (findings)", with four enumerated triggers.**<br>A fifth path defeats the contract and is not enumerated. `_gh_json` calls `json.loads(out.stdout)` OUTSIDE any handler; a `gh` that exits 0 but returns non-JSON raises `json.JSONDecodeError` (a ValueError, not RuntimeError), which the CLI's `except RuntimeError` at :219 does not catch. Verified live with a stub `gh`: raw traceback on stderr and exit **1** — colliding with the findings code the excavation says exit 2 exists to be distinct from. A caller scripting on the exit code reads an infrastructure failure as "records missing". `tools/check_trail.py:149 (`json.loads`) vs :219 (`except RuntimeError`); reproduced: rc=1 with an unhandled JSONDecodeError`
- **T21 `enforcement: "prevented"` for the registry-driven read (`promote.sh` → `wall.py::promote_check`).**<br>This is the one path the excavation labels fully prevented, and it exists only on an unmerged branch that failed independent review at 0 of 5 acceptance criteria. On `origin/main` `promote.sh` has no such call and `wall.py` does not exist; the plugin is pinned at 0.10.0 on both refs, so it reaches no session either. The guard_site prose discloses this, but the `enforcement` field — the part a reader scans — asserts a control that guards nothing on any live path. "Unenforced (built, rejected)" is the honest value. `tools/promote.sh:68-69 and tools/wall.py:360 are absent from `git show origin/main`; .claude-plugin/plugin.json:5 reads 0.10.0 on both refs`
- **Disagreement: the wall's counts file "has ... no matching surface value"; "`records.py:38`'s closed `SURFACES` set has no value that fits it."**<br>Defensible but overstated. `ledger` is in the closed set and is exactly the "append-only JSONL the machinery writes and later reads" shape; the row would be a poor fit (different owner, different path) but the vocabulary is not structurally incapable of carrying it. The stronger and fully supportable half of the finding — no registry row, no `schema` key so `json-schema` mode could never match — stands on its own. `tools/records.py:38 (SURFACES includes "ledger") vs tools/wall.py:84 (row has ts/kind/session/act/detail, no schema key)`

## Found by the verifier, missing from the excavation

- An unhandled-exception state the state list has no name for. A `gh` invocation that SUCCEEDS but returns non-JSON crashes the detector with a raw `json.decoder.JSONDecodeError` traceback and exit 1 — no `check_trail: ERROR:` prefix, no exit 2. This is the only failure surface in the lane that violates the module's own legible-failure contract, and it is indistinguishable from a findings result to any caller. `tools/check_trail.py:142-149 (`_gh_json`), uncaught by :207-221; reproduced live with a stub `gh` returning `not json` at exit 0`
- `_validate` never enforces marker uniqueness. Only `name` is deduplicated (records.py:70-72); two rows may declare the SAME `marker` string with different modes, fields and surfaces, and the registry loads clean. A second row shadowing an existing grammar — the exact 'drift twin' the registry exists to prevent — is invisible to the loader, to `records.py validate`, and to every agreement pin. `tools/records.py:65-93 (`seen` tracks `name` only; `r.get("marker")` is checked for non-emptiness at :73, never for collision)`
- `tools/wall.py::in_scope()` (:48) is defined and has ZERO callers — `main()` routes straight to `decide()`/`close_check()` with no scope test. The excavation mentions this in its notes as a diff fact but never as a state or a gap. The consequence is behavioural: were the plugin released with the HEAD `hooks.json`, the PreToolUse wall would classify and refuse acts in EVERY session the plugin is installed in, with no workspace scoping at all — the scope gate is written, imported, and dead. `tools/wall.py:48 (def), tools/wall.py:381-407 (`main()` — no `in_scope` call); grep for `in_scope` over tools/ tests/ hooks/ skills/ returns only the definition`
- `board_check`'s own docstring asserts a fact the same file refutes: "One implementation, two callers: the funnel shells out to this, and the hook's raw-evasion classification resolves the same item." It has zero callers — no `board-check` subcommand exists in `main()`, `board_plumbing` still hand-rolls its own check, and `classify()` never reaches it. A stated invariant contradicted 50 lines below it in the same module. `tools/wall.py:328-329 (the claim) vs tools/wall.py:381-407 (`main()` exposes only pre-tool/close/promote-check/counts) and tools/board_plumbing.py:145 (the second implementation)`
- `check_trail --registry <path>` accepts an arbitrary registry file (:190), and `records.load(path)` honours it. So a run's mandates are caller-supplied at the REGISTRY level, not merely the lane level — a clean exit 0 is evidence about whatever file the caller pointed at. This compounds the excavation's own 'findings are caller-determined' gap by one further degree of freedom it does not name. `tools/check_trail.py:190 (`--registry`), tools/check_trail.py:199 (`records.load(args.registry)`)`
- `YR-DELIVERY-FAILURE` has no production READER, only test assertions — so the registry's own scope rule (records.toml:4, 'one row per grammar a TOOL parses off a shared surface') arguably excludes it, exactly as the excavation argues for `YR-DEBT-NET-LINES`/`YR-DEBT-SURFACE` in its gap 12. The excavation lists it flatly as an unregistered violation without applying its own scope test, so the sharpest version of the finding — the registry's breadth rule gives contradictory answers for THREE of the four unregistered grammars, not two — goes unstated. `hooks/deliver.sh:44 (emitter) vs tests/test_compile_slice.py:124, :168 (the only readers); records.toml:4 (the scope rule)`
- The factory repo is ARMED (`auto_merge = true`). The excavation establishes that `tests/test_shared_marker_matcher.py` is red at this HEAD but never connects it to the merge model: the failing `check_cmd` is what actually stands between this branch and an autonomous evaluator merge. That makes the red guard a blocking-tier fact about the output gate, not just a quality observation — which is the correct framing for the one finding it rates 'blocking'. `.yr/factory.toml:15 (`auto_merge = true`), .yr/factory.toml:3 (`check_cmd = "pytest tests/ -q"`)`

---

SCOPE AND REF STATE. Everything below was read from the worktree /opt/yellow-robots/factory/.claude/worktrees/task-420-walls. I verified with `git diff origin/main HEAD` that the four files this lane owns — `records.toml`, `tools/records.py`, `tools/check_trail.py`, `tools/textutil.py` — plus `skills/factory/references/attended-lane.md` and the three lane test files are BYTE-IDENTICAL between origin/main and this HEAD. So the registry and detector as described here are exactly what is merged to main. The slice-5 delta (unmerged, rejected 0/5) touches only: tools/wall.py (new), hooks/hooks.json, tools/board_plumbing.py, tools/promote.sh, tools/dev-runner.sh, tools/epic_gate.py, tests/conftest.py, tests/test_wall.py, tests/test_promote.py, tests/test_board_plumbing_pins.py, tests/test_compile_slice.py, AGENTS.md, README.md. `tools/wall.py` additionally carries UNCOMMITTED local edits (90 insertions) adding `in_scope()` (wall.py:48 — defined, zero callers), guarding `_emit_event` against OSError, making `read_counts` tolerant of truncated lines, and adding `board_check` (wall.py:325 — defined, zero callers). Wherever a wall reader is cited above I have said which ref it lives on.  LIVENESS. `.claude-plugin/plugin.json:5` reads `0.10.0` on both origin/main and this HEAD. Slices 1–4 are merged but unreleased, so no SessionStart hook fires and no delivered slice reaches any session. Nothing from iteration 30 is live anywhere; the registry and detector exist only as files a human can run by hand from a checkout.  WHAT I RAN. `python3 tools/records.py validate` → 'records: ok — 37 records, marker YR-, 4 lane(s)'. `python3 tools/check_trail.py --lane epic --issue 415` → clean over 9 texts, exit 0. `--lane close --issue 415` → both close records absent, exit 1. `--lane design --vault-root /srv/obsidian/vaults/obsidian --vault-doc '04 projects/factory/iterations/30-attended-lane-runner/01-attended-lane-runner.md'` → all three design records absent, exit 1. `--lane standalone --issue 420` → YR-TASK-GATES absent, exit 1 (#420 is an epic child, so this is the lane-inference gap, not a violation). `/opt/yellow-robots/factory/.venv/bin/python -m pytest tests/test_shared_marker_matcher.py tests/test_records.py tests/test_check_trail.py tests/test_attended_lane_canon.py -q` → 86 passed, 1 FAILED: `test_wall11_no_second_hand_rolled_marker_matcher_in_the_tree`, offender `tools/board_plumbing.py: ['.startswith(\"YR-']`.  FULL UNREGISTERED-TOKEN CENSUS. A tree-wide `grep -rahoE '\\bYR-[A-Za-z0-9_-]+'` yields 34 distinct tokens. 25 map to registry rows. The 9 that do not: YR-DEBT-NET-LINES (44 hits), YR-DELIVERY-FAILURE (3), YR-WALL (2), YR-DEBT-SURFACE (2), YR-MERGE-PLAN (3, test fixture), YR-SHADOW-RE (14, all inside frozen bench/results evidence), YR-OPEN-QUESTIONS (1, test fixture), YR-NEVER-MINTED (1, test fixture), YR-GATE-TOUCHING-ISH (1, test fixture), plus 'YR-MERGE-prefixed' as prose at tools/dev-runner.sh:2333. NOTE A TOOLING HAZARD I HIT: plain `grep` in this environment treats `tools/wall.py` as binary and silently returns nothing for it — `grep -a` is required, and my first tree-wide scan missed both `YR-WALL` occurrences because of it. Anyone re-running this census must use `grep -a`.  WHAT check_trail STRUCTURALLY CANNOT DO, in one place: judge content (by design and by test); demand any record not in `[lanes]`; infer a lane; discover a scope; read run-dir, stage-log, ledger or bench surfaces from the CLI; distinguish an issue body from an issue comment; apply a value rule; express a must-NOT-be-present rule; compare timestamps or check ordering; detect duplicate or contradictory records; or leave any durable trace of having run.
