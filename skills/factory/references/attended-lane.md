# The attended lane — reified steps, walls at the acts, one registry

> **When to load this reference:** performing attended factory work — the lane where a session, not
> the runner, executes the steps. This is the lane's operating canon (it-30, epic #415): the mandatory
> step set with its records, the walled-act map with per-act conditions and stances, the output-gate
> model, and the delivered slice. The record vocabulary itself lives in `records.toml` (the registry)
> — a record absent from the registry is unsanctioned; this reference cites rows, never restates
> grammars.

---

## Why this lane has a runner now

The lower pipeline cannot skip its stages: the runner sequences them and the merge evaluator
fail-closes on the persisted review verdict. The attended lane's equivalents were mandated by the
same canon but enforced by nothing — the it-29 close-out measured the consequence (twelve violations
in one stretch, every one where no machine gate disposes). A cold session never learns; the
environment must carry what a colleague's memory would. So the lane's mandatory steps are **reified**
(each emits a typed record), its irreversible acts are **walled** (the enforcement layer refuses per
a stated per-act condition and stance), delivery is **unconditional** (the bounded slice arrives at
session start, recognition never required), and violations are **detectable** (`tools/check_trail.py`
verifies presence and grammar against the registry — content-blind; genuineness stays with
independent review and the adherence bench, never with a wall).

## The mandatory step set (reified — the existing mandates, not new ones)

Each step emits the named record on the shared trail; the registry row carries the grammar.

| # | Step | Trace it leaves (registry row where the trace is a record) | Surface |
|---|---|---|---|
| 1 | Backlog capture / sweep | the seed file (capture form) and the spec's sweep line — doc content, not a record grammar | vault-doc |
| 2 | Cold adversarial review | `YR-DESIGN-REVIEW` | vault-doc |
| 3 | Architect fit check | `YR-DESIGN-FIT` | vault-doc |
| 4 | The accept act | `YR-ACCEPT` (+ tombstone pairs, sweep run) | vault-doc |
| 5 | The crossing stamp | `crossed_to` — a frontmatter key, governed by the documentation model, not a record grammar | vault-doc |
| 6 | The technical-rfc review | the review and its per-finding dispositions on the epic trail — prose under the review discipline, not a record grammar | issue-trail |
| 7 | The standing-approval record | `YR-EPIC-APPROVAL` | issue-trail |
| 8 | The standalone gates record | `YR-TASK-GATES` — demanded at the promote act itself | issue-trail |
| 9 | Record-before-flip | `YR-BOARD-FLIP` | issue-trail |
| 10 | The ship-walk trace | `YR-SHIP-WALK` — the close names the pending walk; the trigger is a surfaced checkpoint, never a memory | issue-trail |
| 11 | The round record | `YR-ROUND-RECORD` — the close's observable counts | issue-trail |

Reification adds records, never new duties. The design-side records (steps 2–4) are **typed lines in
the vault docs themselves** — no new surface (the crossing ruling of 2026-08-07, epic #415).

## The walled-act map (total — every act carries condition AND stance)

The enforcement layer checks the stated condition and disposes per the stated stance, naming the
missing record or the categorical rule. Stances are judged per act by consequences (owner, 2026-08-06)
— and door classification judges **consequences, never diffs**: a reversible change with irreversible
consequences is one-way.

| Act | Condition | Stance |
|---|---|---|
| PR merge (attended hand-merge) | **categorical** — no record licenses it; merges execute through the evaluator | fail-closed |
| Shared-branch push | `main`: categorical (the branch protection's client-side voice) · the session's own `task/<n>-<slug>` branch: lawful · any other shared branch: requires `YR-HUMAN-INSTRUCTION` | fail-closed |
| Board Status/Reason write | `YR-BOARD-FLIP` record on the trail before the flip (runner and epic-gate callers exempt — their records are their own) | fail-closed |
| Vault lifecycle stamp (`active` / `superseded`) | the accept act's provenance — `YR-ACCEPT` in the accepting doc, with `YR-DESIGN-REVIEW` and `YR-DESIGN-FIT` present | fail-closed |
| Arming edit (`auto_merge`) | `YR-HUMAN-INSTRUCTION` attributing her decision — arming is decided exclusively by the human, executed only under that instruction | fail-closed |
| Filing a crossing | the governing design's `status` is `active` — resolved from the vault; unreadable or unresolvable refuses | fail-closed |
| Skill release | the freeze checks' records (the release scan's results, recorded) | fail-closed |
| Write-path class: off-table vault write · commit minted on the human's git identity without the standing trailer discipline | **categorical** — the decision table names the sanctioned rows; the trailer discipline names the authoring model | fail-closed |

## The human's checkpoints (what the coordination arm surfaces)

Her gates, stated here so the delivered slice compiles them rather than an agent recalling them:

- setting a design `active` — the input gate; the accept act rides it
- ruling the callouts on a draft spec
- promoting a standalone task to Ready
- the merge click on a repo not yet armed (the named transitional exception)
- arming decisions — hers exclusively, executed only under her explicit instruction
- triggering the ship-walk at close
- the cord-pull veto — un-Readying an epic, at any time

## The output-gate model (ruled 2026-08-06, clarified same day)

The human's technical judgment sits at the **technical-RFC decision surface** — no new mandatory
human gate exists there; the standing-approval model stands. Arming is decided **exclusively by the
human** and only executed by a session or machine under explicit instruction. The **shadow phase is
pre-arming qualification**: once armed, merges are real, never shadow. The merge executes mechanically
through the evaluator under fail-closed conditions; an attended hand-merge is categorically refused;
a repo not yet armed keeps the human click as a named transitional exception — low-value by ruling,
never the design. The **severity valve**: the agent may route a severe-implication decision to the
human at the decision surface — severe means a one-way door (consequences, not diffs) — and every
escalation lands as a `YR-ESCALATION` record, counted in the round record, so the valve is measured.

## Delivery, the slice, and the close

An attended session opening a factory workspace receives the lane's operating canon at session start
— on `startup`, `clear`, `compact`, and `resume` — independent of recognition. The delivered unit is
the **bounded slice**, three parts, compiled from this reference's two tables plus the router's
pointer list, composed at delivery with the round's current position and next step (the state-machine
view): (1) the step set with position, (2) the walled-act map, (3) canon pointers with the **human's
checkpoints marked** — the harness coordinates the human the same way it coordinates the agent; when
a round reaches a step needing her input, the surface she already watches — the board item or the session's close report — names it, never her memory.
Session close is checked: a session that executed a walled act or emitted a mandated record is
refused a silent close while mandatory traces are missing (the refusal names each); a second
consecutive close with traces unchanged proceeds loud and records the override. The close report and
the round record's counts — refusals issued, records demanded, detector findings, escalations — are
emitted where the round reads them; the human prices them against attended attention at close.

## The lane protects itself, and its limits are named

A change whose mandate touches the enforcement layer — walls, registry, detector, delivery — is
**gate-touching attended work**, the same declaration duty as checks, CI, and the manifest: the
pipeline builds under fixed gates, and so does the lane. Walls check **existence and grammar only**
— record genuineness remains with independence (author ≠ reviewer, standing canon) and the
measurement instrument (the adherence bench), never with more prose. Infrastructure failure is not
condition failure: a wall that cannot evaluate a fail-closed act's condition refuses; a crashed
delivery is loud and never locks the human out of her own session.

## The standalone lane's two halves (closing the it-30 seeds)

The direct lane's fit check is walled **at the promote act** (`tools/promote.sh` demands the
`YR-TASK-GATES` record before its own promotion record — the claim-time gate downstream stays), and
standalone-shipped work earns a **defined, recorded close**: the delivering session emits the
ship-walk trace and round-record counts for its scope, exactly as an epic's close does — a standalone
task is a round of one.
