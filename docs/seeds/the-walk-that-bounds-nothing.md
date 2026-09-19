---
created: 2026-09-20
type: seed
status: open
summary: The spend now bounds a run, so the walk over the checkout that used to derive a budget still runs, still counts files, and decides nothing.
value: 3
effort: M
version:
---

## Evidence

2026-09-20, the fifth goal of [[the-budget-that-counts-files]], which is the one that did not land in v0.17. The other four did, so the spend landing exists and is what bounds a run; this is the removal of what it replaced.

The evidence for going is in that seed and is not repeated here: `call_budget` counts files rather than lines, 156 of its 182 one-pass reads on this checkout are the per-file floor, more than half of what it counts is the vault and the evaluation set the builder never opens, and each seed promoted adds about half a tool call to every run's budget. It has also never bound anything: across 190 records and 5,259 tool returns, `error: cap reached` appears zero times.

What it now costs is coherence rather than money. A reader of `builder.py` finds two bounds where there is one: `SHARE` hundredths of a pass over a tree, floored and ceilinged, sitting beside a spend ceiling that is what actually lands a run. The first is dead and looks alive.

**Why it was deferred rather than built.** The surface is wider than the change. `call_budget`, `CALLS_FLOOR`, `CALLS_CEILING`, `SHARE`, `RESERVE`, `REPORT_REQUESTS`, `limits(budget)`, `Tools.budget`, `_over_budget` and `run(agent, goal, budget)` all go or change together, and the last is a signature: 25 call sites across `test_caps.py` and `test_builder.py` name it, and `test_caps.py` is 310 lines mostly about the walk. The builder cannot touch a protected test, so every one of those call sites has to be amended by the attended agent *before* a build, and that amendment is the work rather than the change itself. The same shape cost a red build on 2026-09-19, whose lesson was recorded then: when a Goal changes a signature, grep for the name and not the shape of a call.

## Idea

The walk goes, and the counters that stay stop pretending to be a budget.

`tool_calls_limit` and `request_limit` become fixed, generous constants rather than anything derived. A cheap counter that catches a runaway is worth having beside the bound that means something -- it is the composition every system the research surveyed arrived at -- but it is not the budget and it is not a share of anything.

The numbers are measurable rather than chosen. At the expensive end of the store a run costs between $0.0021 and $0.0040 a request, so `HARD_SPEND` at 0.25 is reached somewhere between 60 and 120 requests; a request limit of 250 and a tool-call limit of 200 both sit above that, so the spend ceiling binds first on any run that is spending, while a cheap loop that spends nothing still terminates. No record in 190 has exceeded 80 tool calls or 60 requests, and both of those were the old caps doing the censoring.

The record keeps saying what bound the run: the spend ceilings are already there, and whatever no longer exists leaves the numbers with it.

The order of work is the amendment first. Every `run(...)` call site in the protected tests is made to match the new signature and committed green, and only then is the goal given to a builder, which is the discipline the red build of 2026-09-19 bought.
