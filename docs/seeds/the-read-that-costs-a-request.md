---
created: 2026-09-19
type: seed
status: open
summary: A read returns 300 lines, so covering the checkout the builder now works on costs 44 reads and 44 requests; the same bytes in fewer, larger reads would cost the same tokens and a third of the requests.
value: 4
effort: S
reporter: attended agent
kind: cost
version:
---

## Evidence

2026-09-19, measured in the checkout at v0.15 by the attended agent while the caps seed was being specified. `READ_LINES_CAP = 300` and `READ_BYTES_CAP = 32_000` are constants of `builder.py` since v0.2, set against a program of three hundred lines. The checkout is now 13,044 lines the tools can reach across 142 files, so reading it once costs 44 reads; the observed looking in v0.15's runs is 50 to 55 calls, which is one pass and a fifth. The largest file, `test_builder.py`, is 1,877 lines and takes seven reads on its own.

What makes this worth its own seed is where the money goes. A run's cost is driven by requests, not by tokens read: every request re-sends the conversation, and the deepest runs of the store cost about a fifth of a cent each. The same content read in fewer, larger calls is the same new tokens and fewer requests. At 300 lines a read, a file of 1,877 lines costs seven requests to see; the bytes cap would allow about 800 lines of Python in one, so the same file could be four. Nothing in the record says the model reads more than it needs; it says the model reads in small bites because that is all a read gives it.

Filed rather than built with [[caps-for-the-checkout-as-it-is]], because the two are separable and the budget there divides by whatever a read returns, so raising the read lowers the budget by itself and the change can be judged on its own numbers.

## Idea

The read caps follow the checkout as the call budget does, or are simply raised to what the bytes cap already allows, and the record says how many lines and bytes a read returned so the next reading of this question has numbers rather than a guess. What a larger read costs in tokens against what it saves in requests is the thing to measure, and the evaluation set is where to measure it: 91 runs, none of them capped, so the set can be run at both sizes and the medians compared.
