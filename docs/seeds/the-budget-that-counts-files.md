---
created: 2026-09-20
type: seed
status: open
summary: The call budget claims to follow the reading a checkout costs; decomposed, it counts files, and more than half of what it counts is the vault the builder never opens.
value: 4
effort: M
version:
---

## Evidence

2026-09-20, measured by the attended agent in the checkout at v0.16, from research the owner commissioned into how a run should be bounded. It is a correction to [[caps-for-the-checkout-as-it-is]], built the day before.

`call_budget` sums, over every file the tools can reach, `max(1, lines // 300)` -- the reads that file costs -- and takes 55 hundredths of the total plus the writes and checks a run is allowed. The docstring says it divides by the lines a read returns. Decomposed on this checkout: of **182** one-pass reads, **156 are the one-per-file floor** and **26** come from the division. The median file is 19 lines and 124 of 156 are fifty lines or fewer. Recomputing the whole walk across a 3.3x range of `READ_LINES_CAP` moves the budget by 9%. To within 15% the formula is `0.55 x (number of files) + 38`: it counts files, and the term it is named for is inert.

Worse, what it counts is mostly not the program. By area, `docs/seeds` is 30.8% of the basis and `cases` 23.1% -- **53.9% together, from 1,581 lines averaging sixteen a file** -- while the root, which holds 10,362 of the checkout's 13,830 lines and every file the builder works in, is 27.5%. Measured against attention, it is close to inverted: across 1,454 targeted tool calls in 39 recent builds, 89.5% named the root and 3.9% named `docs/seeds`. **Each seed promoted adds about half a tool call to every run's budget, for a file the builder has no reason to open.** The budget tracks the backlog.

And no run has ever approached the pass it is a share of. Across 98 builds the median reads **6 distinct files of 156**, the ninetieth percentile 15, and the deepest run in the store read 20.

On other codebases the number is not wrong so much as unrelated to size: `genai_prices` holds 53% more lines than this checkout and earns 41% less budget, 81 against 137, because it has 13 files to this one's 156. Of nine other codebases measured, five land exactly on the floor or the ceiling and eight land at or within five calls of one.

The published prior says the increase the formula justified was the wrong lever anyway. SWE-agent, on a benchmark run tens of thousands of times: "93.0% of resolved instances are submitted before exhausting their cost budget, compared to 69.0% of instances overall", concluding that "increasing the maximum budget or token limit are unlikely to substantially increase performance" (https://arxiv.org/html/2405.15793v3). The same shape holds here -- answered builds run a median of 20 requests at $0.032, capped builds a median of 60 at $0.125 -- so the population a larger budget funds is mostly the population that was going to fail.

One more fact, across all 189 records and 5,259 tool returns: the count of returns beginning `error: cap reached` is **zero**. No cap of any kind has ever refused a call -- not the write cap, not the check cap, not the landing v0.16 exists to add. The mechanism is untested in production, which is its own finding.

## Idea

The walk goes. What replaces it is not a better estimate of reading but a different quantity: **the landing triggers on what the run has cost**, which is the thing the budget was a proxy for and the thing that is actually scarce.

The numbers are in the records and they separate cleanly. The most expensive build that ever answered cost $0.1239; the median capped build cost $0.1249. A soft ceiling at $0.125 cuts **none** of the 82 answered builds and reaches 6 of the 13 capped ones; no wall-clock threshold separates the two populations at zero cost to the answered runs. So the tools refuse and say report now when the run's spend reaches the soft ceiling, and a hard ceiling above it stops a run that will not land -- both from the factory's own `PRICE` table, which is where the numbers already come from.

Tool calls and requests stay as backstops at fixed, generous values, because a cheap counter that catches a runaway is worth having beside the meaningful bound -- that is the composition every system the research surveyed arrived at, one counter as a guard and one resource limit as the real bound. What they stop being is the budget. The record's `cap` field gains `cost`, and `calls_cap` gives way to what was actually enforced.

Two things the spec must not skip. The landing has never fired, so whatever triggers it belongs in the evaluation set before it is trusted -- no case has ever come within a factor of three of a cap, so the set as it stands cannot see this behaviour at all. And [[the-name-that-carries-the-price]] decides whether the library can enforce a cost limit itself or whether the factory must, which changes where this lives but not what it is.
