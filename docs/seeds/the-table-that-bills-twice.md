---
created: 2026-09-20
type: seed
status: open
summary: The factory records about 1.9 times what DeepSeek bills, so every run is landed at roughly half the work its ceiling allows and every projection made from a record is twice what it should be.
value: 5
effort: S
version:
---

## Evidence

2026-09-20, from the owner against the provider's own account: **DeepSeek reports $3.80 for the day. The factory's records say $7.2317 for the same day.** A ratio of **1.903**.

The sample is not small. Twenty-five runs, 160,611,525 input tokens of which 154,806,464 were served from cache, and 3,801,129 output. Where the recorded number comes from, at `PRICE`:

| | tokens | rate | cost | share |
|---|---|---|---|---|
| cache hits | 154,806,464 | $0.006/M | $0.9288 | 12.8% |
| cache misses | 5,805,061 | $0.300/M | $1.7415 | 24.1% |
| output | 3,801,129 | $1.200/M | $4.5614 | 63.1% |
| | | | **$7.2317** | |

### The provider's own counters, same day

The owner read three numbers off DeepSeek's account, and the third settles it:

| | the factory's records | DeepSeek |
|---|---|---|
| requests | 2,317 | 2,515 (+8.5%) |
| tokens | 164,412,654 | 177,441,711 (+7.9%) |
| cost | $7.2317 | **$3.80 (-47.5%)** |

**DeepSeek counted more tokens than we did and charged less than half.** Whatever the disagreement about volume is, it runs the wrong way to explain the cost, so the gap is in the rates and not in the accounting.

The volume gap is itself expected and small. The OpenAI SDK retries 429s and 5xxs twice on its own, and `RunUsage.requests` counts logical requests where the provider bills attempts, which is why the record carries `wire_attempts` beside `requests`; and the provider's day may not start when ours does. Neither matters here except to say the token counts agree to within eight per cent.

Priced on **DeepSeek's own token count**, the table gives **$7.8048, a ratio of 2.054 to what was billed**, and halved it gives **$3.9024 against $3.80, +2.7%** -- and the residual is about the size of the $0.2489 that ran in the 00h hour, which is the one part of the day a discount could plausibly touch. The table is twice the rate, near enough that the remainder is explained by the one thing the table already says it ignores.

**It is not the off-peak discount.** `AGENTS.md` says the table is deliberately flat where DeepSeek's halves off peak, so that is the first thing to suspect and it does not fit: 96% of the day's recorded spend falls between 09:00 and 15:59 UTC, one six-hour block in the middle of the day, with $0.2489 of $7.23 in the 00h hour. For a discount to explain a 1.9x gap it would have to cover most of the working day.

**A uniform halving of the table fits.** Recomputing the same tokens at half of every rate gives **$3.6159 against $3.80 billed, within 5%** -- and the residual is the size of the rounding in *"$3.8"*. No single-rate change fits as well: holding the other two and solving for output alone needs $0.297/M, which is not a number anybody publishes. For comparison, `genai_prices`' row for the adjacent name `deepseek-v4-flash`, which `AGENTS.md` records as a different model's numbers, is also below ours on every line -- miss $0.220 against our $0.300, output $0.660 against our $1.200 -- and gives $4.87 for the day, closer than ours and still not it.

**What it costs is not a reporting error.** v0.17 made what a run has spent the thing that bounds it, and the tools ask at every call. A run landed at `SOFT_SPEND` believes it has spent $0.125 and has really been billed about $0.066, so **every build today was landed at roughly half the work its ceiling allowed**. That is the same defect as [[the-role-priced-as-another]], which was closed this morning at 5.41x for a role served elsewhere, arriving at 1.9x on the model the builder itself runs on. The seed that fixed the first one did not look at the second, because the table was the one thing in the pricing path nobody was questioning.

Everything projected from a record inherits it. The twelve-case catch-rate set was put to the owner at about $33 and is more likely about $17.

`AGENTS.md` already says *no threshold from it is a claim about a bill*, and that sentence is still true and was never enough: the thresholds are what bound the runs, so a table that is not a claim about a bill is a table that cannot be trusted to bound one either.

## Idea

The table says what the provider charges, and something checks that it does.

The rates are read from DeepSeek's own published prices for `deepseek-flash` and `PRICE` is corrected to them -- which needs the provider's page and is therefore the owner's or an online step, not something to infer from one day's bill. The day's arithmetic above is the acceptance test: the same tokens at the corrected table, against the billed figure for the same day, agreeing to within the rounding of the bill.

Then the harder half, which is why this is worth a note rather than a one-line edit. A table read once is a table that silently rots, and it rotted here without anything noticing for at least five days. What would have caught it is the comparison itself: the factory knows every token it has ever sent and the provider knows what it charged, so one number a day, entered by hand, is enough to hold a table honest. Where that number lives and what refuses when it drifts is the part worth thinking about.

Until it is fixed, what the records carry is a constant multiple of the truth and comparisons between runs are unaffected. It is the absolute numbers -- the ceilings, and every budget put in front of somebody -- that are wrong, and they are wrong in the direction of doing less work than intended and asking for more money than needed.
