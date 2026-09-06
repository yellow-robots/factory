# PM — the two rituals, as the human meets them

> **When to load this reference:** meeting the PM agent's own machinery from the human side — reading
> a triage pack, writing a `YR-TRIAGE` disposition, authoring or revising a strategy doc, reading the
> KPI report, or understanding the closed escalation list a `go` disposition runs under. For the
> machinery's own upstream mechanism (the sweep, the runners, the crossing, the close), see
> [`pipeline.md`](pipeline.md) — *The design sweep and runner*. For the architect's own fourth moment
> inside this lane, see [`architect.md`](architect.md).

---

## Why this reference exists (it-36)

The PM is one role, one actor, two duties: *headless*, it keeps every open seed **decision-ready** and
is mandated to carry a licensed one to Done end to end — drafting, review, activation, the crossing,
the build, the close; *with the owner*, it keeps the triage surface and the strategy pack current so a
decision costs minutes, never a meeting. In this tree today the sweep itself only spawns drafting
(`tools/design-runner.sh`) and the close (`tools/close-runner.sh`, once `YR-CLOSE-HOLD` fires); the two
middle hops — the review runner and the crossing — exist as tools but are not spawned by anything yet
(see [`pipeline.md`](pipeline.md) → *The design sweep and runner*). This reference is the human's own
half of the second duty — the two rituals as the owner meets them: reading a pack and writing a
disposition, and revising a strategy doc.

## Ritual 1 — the triage pack and the `YR-TRIAGE` disposition

**The pack.** For every ranked seed with no disposition yet, `tools/design_gate.py`'s sweep
(`sweep_designs`) posts one `YR-TRIAGE-PACK` comment on the component's triage issue — once, never
re-posted while the seed stays undecided:

```
YR-TRIAGE-PACK
  seed: <ideas-file-stem>

**scope:** <the seed's own summary>
**value:** <1-5>  **effort:** <S|M|L>  **rank:** <value - size discount>
**cost estimate:** $<n.nn> (mean of this repo's last merged runner PRs' usage, x the seed's own
  effort factor: S=1, M=3, L=6)
**theme:** <the strategy doc's theme id this seed serves, or none>

To triage, reply on this issue with (paste exactly, editing the disposition to `go`, `park`, or
`reject`):

    YR-TRIAGE: seed=<ideas-file-stem> disposition=go who=@<owner login>
```

The pasted sample line sits inside a code block, never at column 0 as live markdown — the same
self-triggering-record lesson `tools/epic_gate.py` already teaches: a pack can never be read back as
the disposition it is asking for.

**The record.** `YR-TRIAGE` (`records.toml`) is the **only** record this closed round names
`emitted_by = ["human"]` alone — never machinery, never an attended agent. Grammar:
`YR-TRIAGE: seed=<ideas file stem> disposition=go|park|reject who=@<login>`. It rides the triage
issue's own trail, under the owner's own GitHub identity — the one native surface that verifies its
author. The sweep's `latest_triage_dispositions` reads the **last** record per seed as the standing
disposition; a record from anyone but the configured owner login is ignored outright. Nothing a
triage record does not name ever activates: `tools/design_gate.py evaluate` (the
`design-triage-license` / `epic-triage-license` evaluators `process.toml` names on the activation and
epic-flip transitions) fails closed on an absent or non-`go` disposition — Rule M's own guarantee that
a triage-gated door can never ship ungated (see [`attended-lane.md`](attended-lane.md) → *The mandatory
step set*, cited there, never restated here).

**Reversal.** A `park`/`reject` on a seed already in flight (a design already drafting) stops it: the
sweep kills the running stage group and notes it on the triage issue — no resume without a fresh `go`.
The same withdrawal fires when a named governing epic is un-Readied or closed; the cord-pull reaches
through the license, not around it.

**One design in flight per repository.** The sweep spawns the runner's `product` stage
(`tools/design-runner.sh`) for the single top-ranked, licensed, in-direction seed with no design
already running for that repo — distinct from the epic-gate's own one-slice-per-epic rule, and
independent of it.

## Ritual 2 — the strategy doc

The owner's **only** direction input, revised whenever the owner chooses, at no fixed cadence — no
in-direction candidate means the PM idles and says so on the triage issue, never a fallback to factory
work. One per component, a `note` under `<component>/strategy/`, carrying exactly one fenced
` ```yr-strategy ` TOML block (`tools/strategy.py`, mirroring `tools/merge_shadow.py`'s own fence-word
grammar — find the marker, find the closing fence, parse what's between, never a second parser):

```toml
[[themes]]
id = "..."
goal = "..."
target = "..."
repos = ["..."]
budget_usd = 0
stop_when = "..."

constraints = ["..."]
kpi_targets = { ... }
loop_budget_usd_per_week = 0
factory_cap = 3
```

A missing or malformed block is a loud finding, never a silent empty result. `loop_budget_usd_per_week`
is enforced today — `tools/design_gate.py`'s own loop-budget check reads it and escalates on exhaustion
(the closed escalation list, below). `factory_cap` is declared, parsed by `tools/strategy.py`, and not
yet enforced by anything — the cap on the factory's own theme is the spec's own rule, not yet a
detector in this tree. `YR-STRATEGY` (`records.toml`) names its emitter as "the design sweep, posted
when the strategy doc it tracks changes" — `tools/design_gate.py` carries no hash tracking or emitter
for it today; like `YR-KPI` below, this is a declared grammar with no emitter yet.

## The KPI report (queued — it-36 slice J, #475, not yet built in this tree)

The spec's own acceptance criterion: regenerated whenever the strategy doc changes or the owner asks,
against the strategy doc's own `kpi_targets` — velocity, cycle time (seed → decision → active →
shipped), blocked/repair/revert rates, spend, backlog age and inflow versus outflow, the
product-versus-factory ratio, and deploy lag, each computed from a native surface (merged-PR usage
comments, the board's own `createdAt`/issue-timeline fields, `git log` revert detection, the
`YR-DEPLOY` trail, the ideas folder's frontmatter) — never the build-host ledger, which is per-host,
not per-repo. Slice J's own deliverable is `tools/kpi.py`, posting one `YR-KPI` note per month into
the component's operations home and a `YR-KPI` record on the triage issue; until that slice ships,
`YR-KPI`'s `records.toml` row is a declared grammar with no emitter yet. Slice J has since shipped: the report exists (`tools/kpi.py`), and the session's own delivered slice
(`tools/compile_slice.py`'s `position()`) now carries that standing triage line naming how many seeds
await the owner's own line — only the design sweep's own automatic trigger, running the report the
moment the strategy doc's hash changes, remains not yet built, tracked as #520.

## The closed escalation list — default-block

The spec's own closed list: out-of-direction work, arming, auth and tokens, spend over a theme's budget
or the loop's, a new external dependency, a data migration, and any PR the runner did not open — each
parks the item with a record until the owner's own approving review; everything else runs
default-proceed under the license. Where each entry actually sits in this tree today, three shapes:

- **Parks with a `YR-ESCALATION` record, wired.** `tools/design_gate.py` posts one `YR-ESCALATION:
  act=idle why=loop-budget-exhausted` when a repo's trailing-week `kind=design` ledger spend exhausts
  its own `loop_budget_usd_per_week`, then idles (posted once, never repeated). `tools/cross.py` files
  an escalated slice untyped and carries its own `YR-ESCALATION` comment — grammar cited from
  `AGENTS.md`'s own `tools/cross.py` repo-map row, never restated here.
- **Structural refusal, not an escalation record.** Arming: `process.toml`'s `arming.disarmed->armed`
  transition names `human` alone in `actor` — machinery cannot even propose it, let alone escalate a
  refusal. Auth and tokens: no `auth` machine exists in `process.toml` at all — its home is `AGENTS.md`
  → *Auth is human work*, a rule outside the model entirely, never a door for machinery to approach.
- **The closed list's own scope, not yet a second detector in this tree.** Spend over a *theme's* own
  budget (distinct from the loop's, which IS wired above); out-of-direction work as a named escalation
  rather than the silent idle `sweep_designs` posts today when no theme targets a repo.
