---
created: 2026-09-20
type: seed
status: done
summary: The call budget claims to follow the reading a checkout costs; decomposed, it counts files, and more than half of what it counts is the vault the builder never opens.
value: 4
effort: M
version: v0.17
---

## Evidence

2026-09-20, measured by the attended agent in the checkout at v0.16 and in the store at 190 records, from research the owner commissioned into how a run should be bounded. It is a correction to [[caps-for-the-checkout-as-it-is]], built the day before.

`call_budget` sums, over every file the tools can reach, `max(1, lines // 300)` -- the reads that file costs -- and takes 55 hundredths of the total plus the writes and checks a run is allowed. The docstring says it divides by the lines a read returns. Decomposed on this checkout: of **182** one-pass reads, **156 are the one-per-file floor** and **26** come from the division. The median file is 19 lines and 124 of 156 are fifty lines or fewer. Recomputing the whole walk across a 3.3x range of `READ_LINES_CAP` moves the budget by 9%. To within 15% the formula is `0.55 x (number of files) + 38`: it counts files, and the term it is named for is inert.

Worse, what it counts is mostly not the program. By area, `docs/seeds` is 30.8% of the basis and `cases` 23.1% -- **53.9% together, from 1,581 lines averaging sixteen a file** -- while the root, which holds 10,362 of the checkout's 13,830 lines and every file the builder works in, is 27.5%. Measured against attention, it is close to inverted: across 1,454 targeted tool calls in 39 recent builds, 89.5% named the root and 3.9% named `docs/seeds`. **Each seed promoted adds about half a tool call to every run's budget, for a file the builder has no reason to open.** The budget tracks the backlog.

And no run has ever approached the pass it is a share of. Across 99 builds the median reads **6 distinct files of 156**, the ninetieth percentile 15, and the deepest run in the store read 20.

On other codebases the number is not wrong so much as unrelated to size: `genai_prices` holds 53% more lines than this checkout and earns 41% less budget, 81 against 137, because it has 13 files to this one's 156. Of nine other codebases measured, five land exactly on the floor or the ceiling and eight land at or within five calls of one.

The published prior says the increase the formula justified was the wrong lever anyway. SWE-agent, on a benchmark run tens of thousands of times: "93.0% of resolved instances are submitted before exhausting their cost budget, compared to 69.0% of instances overall", concluding that "increasing the maximum budget or token limit are unlikely to substantially increase performance" (https://arxiv.org/html/2405.15793v3).

The store says the same and says where the line falls. Of 190 records, 99 are builds and 91 are case runs. Of the 99 builds, 85 answered and 13 were capped:

| | answered | capped |
|---|---|---|
| count | 85 | 13 |
| median cost | $0.0320 | $0.1249 |
| most expensive | $0.1239 | $0.1788 |

The two populations separate at a price. **A ceiling at $0.125 is above every one of the 85 answered builds and below 6 of the 13 capped ones.** No threshold in tool calls, requests or wall-clock separates them at zero cost to the answered runs.

One more fact, across all 190 records and 5,259 tool returns: the count of returns beginning `error: cap reached` is **zero**. No cap of any kind has ever refused a call -- not the write cap, not the check cap, not the landing v0.16 added. Every one of the 13 caps was the library's hard stop, which leaves no chance to report. The landing is untested in production, which is its own finding and the reason the last goal below exists.

**What the price is.** `PRICE` in `builder.py` is DeepSeek's published peak rate for `deepseek-flash` -- $0.006 cache hit, $0.3 cache miss, $1.2 output per 1M tokens, api-docs.deepseek.com/quick_start/pricing read 2026-09-20 -- and it is the source for this model, not a fallback: `genai_prices` has no row for the name, and its `deepseek-v4-flash` row is a different model's numbers, 0.43x, 0.68x and 0.91x of ours term by term. [[the-name-that-carries-the-price]] is the rejected seed that establishes it. DeepSeek bills half this rate outside 01:00-04:00 and 06:00-10:00 UTC on weekdays, and 85% of the store's runs started outside those windows, so the recorded spend overstates the money by 1.61x, $6.53 against $4.07. **That is deliberate and must stay.** A bound on a run must measure the work, not the hour it ran in; the flat peak rate is a stable measure of tokens spent and the money is not. The column is what a run consumed, priced at one constant rate, and no threshold here is a claim about a bill.

## Goal

A run is bounded by what it has spent, not by a walk over files it will never read.

**A. One place that prices tokens.** `price(usage)` gives the USD those tokens cost from `PRICE`, for anything carrying `input_tokens`, `cache_read_tokens` and `output_tokens`. It is the arithmetic `main` already does once at the end, moved so that two callers cannot drift: `main` computes `cost_usd` through it and the answer for a finished run does not change, which every record in the store can be checked against.

**B. The landing.** `Tools` takes `spent`, something it can call with no arguments for what the run has spent so far in USD; a `Tools` built without one refuses nothing on spend, as every call in the tests does today. It is asked at each tool call and never cached, because a run crosses the line in the middle and must land there. When it reaches `SOFT_SPEND`, every one of the six tools refuses in the shape the other caps already use -- `error: cap reached (...); report now`, naming this cap and its number -- and goes on refusing, moving no counter but `calls`. The model keeps the requests it needs to write its report, as it does for the call cap today. `SOFT_SPEND` is 0.125, the number above every answered build in the store and below six of the thirteen capped ones. `main` gives `Tools` the run's real spend, so the landing is the same arithmetic as the record's.

**C. The backstop.** `HARD_SPEND` above it stops a run that will not land whatever it is told, the way the library's limits stop one today: the run ends, `stopped` says it was capped, and the record says which cap did it. It is a guard against a runaway and not a tuned threshold -- no run in the store has ever reached 0.25 -- so it is twice the soft ceiling and is not derived from anything else.

**D. The walk goes.** `call_budget` and everything only it uses are removed, and with them the idea that a budget is a share of a pass over the checkout. `tool_calls_limit` and `request_limit` stay as fixed, generous constants: a cheap counter that catches a runaway is worth having beside the bound that means something, but it is no longer the budget and no longer derived. Pick them so that neither binds before `HARD_SPEND` on any run the store has ever seen.

> [!warning] Not built in v0.17
> 2026-09-20: goals A, B, C and E landed in run 20260919T230907Z and this one did not. It is not a smaller change than it reads: `run(agent, goal, budget)` is a signature named at 25 call sites across `test_caps.py` and `test_builder.py`, the builder may not touch a protected test, so every one of them must be amended by the attended agent before a build can start -- and that amendment is larger than the change. Deferred whole rather than started late, and carried by [[the-walk-that-bounds-nothing]]. Nothing in A, B, C or E depends on it: the spend landing is what bounds a run, and the walk now derives a number that decides nothing.

**E. What the record says.** A record names the caps it was given beside the counts they bound, as it does now, and which cap ended the run when one did. The spend ceilings join them; whatever no longer exists leaves. `numbers.json` keeps `cost_usd` and `cost_source` as they are and with the same meaning, so every reading of the table still works across the change.

The walls do not move: the write cap, the check cap, the protected paths and the hidden names are what they were.
