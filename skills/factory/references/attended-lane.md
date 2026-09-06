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
| 1 | The triage record (it-36) | `YR-TRIAGE` — the human actor class alone, on the component's triage issue; nothing below activates without a `go` naming it | issue-trail |
| 2 | Backlog capture / sweep | the seed file (capture form) and the spec's sweep line — doc content, not a record grammar | vault-doc |
| 3 | Cold adversarial review | `YR-DESIGN-REVIEW` | vault-doc |
| 4 | Architect fit check | `YR-DESIGN-FIT` | vault-doc |
| 5 | The architecture review (it-36) | `YR-ARCH-REVIEW` — the abstraction/pattern/libraries/language/boundaries verdict and its ADR, run on the draft after step 4 and again on the technical-rfc at the crossing (step 8) | vault-doc, pr-trail |
| 6 | The accept act | `YR-ACCEPT` (+ tombstone pairs, sweep run) — **the machinery's own activation (it-36):** under a `go` triage record and an independence check, `design-doc.draft->active.machinery` walks this same step, emitting the identical record | vault-doc |
| 7 | The crossing stamp | `crossed_to` — a frontmatter key, governed by the documentation model, not a record grammar | vault-doc |
| 8 | The technical-rfc review | the review and its per-finding dispositions on the epic trail — prose under the review discipline, not a record grammar | issue-trail |
| 9 | The standing-approval record | `YR-EPIC-APPROVAL` | issue-trail |
| 10 | The standalone gates record | `YR-TASK-GATES` — demanded at the promote act itself | issue-trail |
| 11 | Record-before-flip | `YR-BOARD-FLIP` | issue-trail |
| 12 | The promote's own emission | `YR-PROMOTED` (standalone funnel) / `YR-AUTO-PROMOTED` (the epic gate's mechanical child promote) / `YR-EPIC-READY` (the epic flip's own funnel, ruling 5 — it-31 slice 4: record-before-flip through `tools/promote.sh`'s Feature arm) — landed by construction at the funnel, so a promoted trail without one means the flip happened outside it (a compiled-mandate addition, ruling 3). **The machinery's own flip (it-36):** under the epic's own `go` triage record, `task.backlog->ready.epic-flip.machinery` walks this same step through the same funnel | issue-trail |
| 13 | The ship-walk trace | `YR-SHIP-WALK` — the close names the pending walk; the trigger is a surfaced checkpoint, never a memory | issue-trail |
| 14 | The round record | `YR-ROUND-RECORD` — the close's observable counts | issue-trail |
| 15 | The armed merge's record | `YR-MERGE` — the evaluator's durable decision, the compiled `merge` lane's one mandate | pr-trail |
| 16 | The release's record | `YR-RELEASE` — the validation-gated release act's typed record (ruling 6 — it-31 slice 7): the Release body and the annotated tag's message carry it, and the round's own close release is the funnel's live run | release |

**Rule M (it-36).** Every machinery variant above walks a **separate, disjoint transition row** — never
a widened `actor` on the shared human/attended-agent row — and the model refuses at load
(`tools/process.py`) any one-way door naming `machinery` in `actor` with no `evaluator_pass` guard
licensing the walk: a triage-gated door can never ship ungated.

Reification adds records, never new duties. The design-side records (steps 2–4) are **typed lines in
the vault docs themselves** — no new surface (the crossing ruling of 2026-08-07, epic #415).

## The walled-act map (total — every act carries condition AND stance)

The map is **compiled**: `build/walled-acts.md` (GENERATED from `process.toml`, committed with the
model) is the total per-act, per-caller table — condition, derived stance, on-fail, door,
enforcement, chokepoint, open paths — and the delivered slice's transitions view is its compact
form. The hand table this reference carried through v1 retired when delivery was rewired to the
generated surfaces (it-31 slice 8): a hand map beside a generated one is a drift twin, and the
model rules on any disagreement. What the generated rows cannot say alone, stated once:

- Stances are judged per act by consequences (owner, 2026-08-06) — and door classification judges
  **consequences, never diffs**: a reversible change with irreversible consequences is one-way.
- The categorical rows are permission-tier: `pr.merged` and shared `main`/`master` are writable by
  no attended class, and `manifest.auto_merge` by the human alone — no record licenses them; the
  output-gate switches owe `YR-OUTPUT-SWITCH` in both directions (detection where prevention
  cannot reach).
- An over-matching binding may never refuse: the blind-write residual advises, detection-tier.
- The funnels are coverage, never special cases: `tools/promote.sh`, `tools/release.py`, and the
  raw spellings they wrap resolve to the same transitions and the same guards.

## The human's checkpoints (what the coordination arm surfaces)

Her gates, stated here so the delivered slice compiles them rather than an agent recalling them:

- **the triage disposition (it-36)** — `go` / `park` / `reject`, the `YR-TRIAGE` record: the input
  gate itself; nothing activates outside it
- setting a design `active` directly — still hers to do; under a `go` the PM's machinery may do it
  instead
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

**The attended PR's fragment duty (it-36, issue #474)** is stated once, in full, at `AGENTS.md` →
*Conventions*, "Attended operator sessions" — cited here, never restated: a PR the runner did not open
carries no automatic changelog fragment, and the merge evaluator's `fragment_present` condition blocks
on the missing one.

## Delivery, the slice, and the close

An attended session opening a factory workspace receives the lane's operating canon at session start
— on `startup`, `clear`, `compact`, and `resume` — independent of recognition, and **only inside the
factory's declared world** (the engine's own boundary rule; outside it, walls and delivery stay
silent). The delivered unit is the **bounded slice**: the model's compiled static half
(`build/slice-static.md` — machines, transitions with derived stances, the honesty block) served
verbatim, plus the runtime position composed at delivery (it-31 slice 8: no hand-authored map
remains in the delivery path) — the harness coordinates the human the same way it coordinates the agent; when
a round reaches a step needing her input, the surface she already watches — the board item or the session's close report — names it, never her memory.
Session close is checked: a session that executed a walled act or emitted a mandated record is
refused a silent close while mandatory traces are missing (the refusal names each); a second
consecutive close with traces unchanged proceeds loud and records the override. The close report and
the round record's counts — refusals issued, records demanded, detector findings, escalations,
deployed — are emitted where the round reads them; the human prices them against attended attention
at close.

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
