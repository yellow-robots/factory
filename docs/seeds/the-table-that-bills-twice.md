---
created: 2026-09-20
type: seed
status: open
summary: A record's cost is the work at one flat rate and the bill is the work at the rate of the day it ran, so the two differ by up to half and nothing says which day a record was.
value: 3
effort: M
reporter: owner
kind: cost
version:
---

## Evidence

2026-09-20, from the owner against the provider's own account:

| | the factory's records | DeepSeek |
|---|---|---|
| requests | 2,317 | 2,515 (+8.5%) |
| tokens | 164,412,654 | 177,441,711 (+7.9%) |
| cost | $7.2317 | $3.80 |

Priced on DeepSeek's own token count the table gives $7.8048, a ratio of **2.054**, and halved it gives $3.9024 against $3.80.

**The factor of two is the off-peak discount and the table is correct.** 2026-09-20 was a **Sunday**, and DeepSeek's notice says weekends, Chinese public holidays and adjusted working days are billed off peak in their entirety -- not only within the daily window. The attended agent checked the daily window, found 96% of the day's spend between 09:00 and 15:59 UTC, concluded the discount could not explain the gap, and wrote that conclusion into this seed as a finding. It was wrong, and it was wrong in the confident direction: a measured ratio, a table of candidate rate sets, and a false premise underneath all of it.

`AGENTS.md` had the answer the whole time: *the rate is flat where DeepSeek's halves off peak, deliberately, because a bound on a run must measure the work and not the hour it ran in; what the records carry is what a run consumed at one constant rate, and no threshold from it is a claim about a bill.* That is the design, working. There is no pricing defect here.

The volume gap is separate and small: the SDK retries 429s and 5xxs twice and `RunUsage.requests` counts logical requests where the provider bills attempts, which is why a record carries `wire_attempts` beside `requests`; and the provider's day may not start when ours does.

## Idea

**What is left is not a bug, it is a missing fact: a record does not say what rate it ran at.**

Every record carries what the work cost at one flat rate, which is the right number for comparing two runs and the wrong number for anticipating a bill. Today the difference is exactly two, which is fine to know and impossible to derive from the record: nothing in `numbers.json` says whether the run was peak or off peak, and nothing in the repository knows which days are which.

That is the hard part, and it is why this is not urgent. Deciding the rate of a run needs a calendar the factory does not have and cannot derive -- weekends are easy, Chinese public holidays are a published list that changes yearly, and *adjusted working days* are Saturdays and Sundays that the Chinese State Council declares to be working days in lieu around a holiday, announced once a year. A factory that guessed at that calendar would be wrong occasionally and silently, which is worse than a flat rate that is knowably flat.

The cheap end, if it is ever wanted: a record says which rate it believes it ran at, on the one rule that is certain -- the daily window, plus weekends -- and says nothing rather than guessing about holidays. Then a projection can be quoted as a range instead of a number, and the day a bill is checked against the records, the difference is accounted for rather than investigated. The expensive end is the calendar, and it should stay unbuilt until something depends on it.

What must not change is the flat rate the ceilings use. A ceiling that moved with the hour would mean a run does more work on a Sunday than on a Tuesday for the same bound, and the whole point of bounding a run by spend is that the bound measures the work.

## Not to repeat

The attended agent had the disconfirming evidence and the correct explanation in the same file it was editing, and wrote a confident negative -- *it is not the off-peak discount* -- on one day's data, without checking what day it was. The check was `date`. When an explanation is ruled out, the cost of ruling it out wrongly is every conclusion built on top, and here that was a seed at value 5, a correction to `AGENTS.md`, and a line in a version note.
