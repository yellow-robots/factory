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
carries a licensed one to Done end to end; *with the owner*, it keeps the triage surface and the
strategy pack current so a decision costs minutes, never a meeting. This reference is the human's own
half of that second duty — the two rituals as she meets them: reading a pack and writing a disposition,
and revising a strategy doc.

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
epic-flip transitions) fails closed on an absent or non-`go` disposition, and the model's own **Rule
M** refuses at load any one-way door naming `machinery` in `actor` with no `evaluator_pass` guard
licensing the walk — so a triage-gated door can never ship ungated by construction.

**Reversal.** A `park`/`reject` on a seed already in flight (a design already drafting) stops it: the
sweep kills the running stage group and notes it on the triage issue — no resume without a fresh `go`.
The same withdrawal fires when a named governing epic is un-Readied or closed; the cord-pull reaches
through the license, not around it.

**One design in flight per repository.** The sweep spawns the runner's `product` stage
(`tools/design-runner.sh`) for the single top-ranked, licensed, in-direction seed with no design
already running for that repo — distinct from the epic-gate's own one-slice-per-epic rule, and
independent of it.

## Ritual 2 — the strategy doc

The owner's **only** direction input, revised whenever she chooses, at no fixed cadence — no
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
factory_cap = "..."
```

A missing or malformed block is a loud finding, never a silent empty result. `loop_budget_usd_per_week`
bounds the PM's own headless loop; `factory_cap` caps the factory's own theme explicitly, so a
component's ranked backlog can never be all factory work by construction. When the sweep observes the
doc's hash change it posts `YR-STRATEGY: who=<editor> doc=<path>` on the triage issue's trail — the
record names that a change happened and who made it, never a second copy of the doc's own content.

## The KPI report (queued — it-36 slice J, #475, not yet built in this tree)

The spec's own acceptance criterion: regenerated whenever the strategy doc changes or the owner asks,
against the strategy doc's own `kpi_targets` — velocity, cycle time (seed → decision → active →
shipped), blocked/repair/revert rates, spend, backlog age and inflow versus outflow, the
product-versus-factory ratio, and deploy lag, each computed from a native surface (merged-PR usage
comments, the board's own `createdAt`/issue-timeline fields, `git log` revert detection, the
`YR-DEPLOY` trail, the ideas folder's frontmatter) — never the build-host ledger, which is per-host,
not per-repo. Slice J's own deliverable is `tools/kpi.py`, posting one `YR-KPI` note per month into
the component's operations home and a `YR-KPI` record on the triage issue; until that slice ships,
`YR-KPI`'s `records.toml` row is a declared grammar with no emitter yet. The session's own delivered
slice (`tools/compile_slice.py`) is slice J's to extend with a standing triage line naming how many
seeds await the owner's own line — read this reference again once #475 lands, this section is written
ahead of that PR.

## The closed escalation list — default-block

Out-of-direction work, arming, auth and tokens, spend over a theme's budget or the loop's, a new
external dependency, a data migration, and any PR the runner did not open: each parks the item with a
record until the owner's own approving review; everything else runs default-proceed under the
license. Two arms are wired in this tree today: `tools/design_gate.py` posts one `YR-ESCALATION:
act=idle why=loop-budget-exhausted` when a repo's trailing-week `kind=design` ledger spend exhausts
its own `loop_budget_usd_per_week`, then idles (posted once, never repeated); `tools/cross.py` files a
slice declaring `Declares: external dependency <name>` or `Declares: data migration` **untyped** — the
epic-gate's own `not-a-task` hold, so it structurally cannot promote — and carries a `YR-ESCALATION`
comment naming the declaration, with nothing else waiting on it. Arming and auth are never machinery-
capable acts at all (`process.toml`'s actor list names `human` alone on those doors) — a structural
refusal, not an escalation record. The remaining arms (spend over a *theme's* own budget, distinct
from the loop's; out-of-direction work as a named escalation rather than a silent idle) are the closed
list's own scope, not yet a second detector in this tree.
