---
created: 2026-09-18
type: seed
status: open
summary: The request and tool-call caps were set when the builder was three hundred lines; on a checkout four times that they are spent on finding the work rather than doing it, six capped runs over two nights, and a capped run's work is not taken.
value: 5
effort: M
version:
---

## Evidence

2026-09-18, from v0.14's own builds, read in the records by the attended agent. `REQUEST_CAP = 60` and `TOOL_CALLS_CAP = 40` are constants of `builder.py` since v0.3, when the program was about three hundred lines and its suite thirty tests; at v0.14 the six programs are 3,334 lines and the suite 197 tests. Of the fourteen runs of the night, three were capped at 60 requests: 20260918T062649Z, chasing two failures that were the attended agent's own tests; 20260917T220443Z, on a goal the attended agent then cut in three; and 20260918T074122Z, which reached a green check of all 197 tests with a complete change of 61 lines and ran out of requests before its report, so its work was not taken, 8.4 cents spent and the same goal built for 7.0 cents on the next run. The three cost 37 cents of the version's 96. A capped run reported nothing, so its work is not taken and `build.py` refuses it; the rule is sound and the cap is what is wrong. Every capped run of the night used nearly one tool call a request, most of them reads and searches of `builder.py`, which is 1,286 lines.

2026-09-19, v0.15's own builds, and the case is now beyond argument. Not one of its capped runs was capped by the work: 20260918T223356Z at 60 requests on a goal the attended agent then cut in two; 20260918T224905Z at 59 requests, reaching a green check of 224 tests before it ran out; 20260918T231137Z on the tool calls rather than the requests, at 3 lists, 23 reads and 33 searches against 6 edits; and 20260919T000504Z on a goal that was one small function, at 27 reads and 29 searches for six edits. What the budget is spent on is not the work but the looking, in a program of 1,344 lines with a suite of 225 beside it. Seven caps of eleven runs by the version's end, four of them cut off with the check green and the whole change made, and the seven cost 97 cents of the version's 123 -- more than three quarters of what the version spent bought nothing. Nothing the spec could do reached them: splitting a goal in two, naming every site, moving the red tests into a file of a hundred and ninety lines, and quoting every line to be removed each left the reads and searches where they were.

Two things the version showed that the Idea below does not yet cover. A run that hits the tool-call cap and one that hits the request cap are both `stopped: cap` with only `detail` telling them apart, so the table cannot say which budget bound a run. And the caps are constants of the program, so a version cannot be built under different caps by the instance that builds it: an instance pinned at a tag carries that tag's caps, which is right, and means a caps change helps the version after the one that makes it.

## Idea

The caps are read from the checkout rather than fixed in the program: a run's budget follows the size of what it must read, the caps in the record's numbers beside the counts they bound, so a cap that bit is visible in the table and a version can say whether a run was cut off or went wrong. What the budget is a function of, the lines the tools can reach or the suite's own size, and whether a run that reaches a green check is given the requests to report, are the spec's. The caps are what a run costs at worst, so raising them raises the worst cost of a set run too: the spec says what a set costs at the new caps before it is run.
