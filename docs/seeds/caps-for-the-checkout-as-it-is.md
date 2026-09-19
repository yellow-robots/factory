---
created: 2026-09-18
type: seed
status: building
summary: The request and tool-call caps were set when the builder was three hundred lines; on a checkout four times that they are spent on finding the work rather than doing it, seven capped runs of eleven in one version, and a capped run's work is not taken.
value: 5
effort: M
version: v0.16
---

## Evidence

2026-09-18, from v0.14's own builds, read in the records by the attended agent. `REQUEST_CAP = 60` and `TOOL_CALLS_CAP = 80` are constants of `builder.py` since v0.3, when the program was about three hundred lines and its suite thirty tests; at v0.14 the six programs are 3,334 lines and the suite 197 tests. Of the fourteen runs of the night, three were capped at 60 requests: 20260918T062649Z, chasing two failures that were the attended agent's own tests; 20260917T220443Z, on a goal the attended agent then cut in three; and 20260918T074122Z, which reached a green check of all 197 tests with a complete change of 61 lines and ran out of requests before its report, so its work was not taken, 8.4 cents spent and the same goal built for 7.0 cents on the next run. The three cost 37 cents of the version's 96. A capped run reported nothing, so its work is not taken and `build.py` refuses it; the rule is sound and the cap is what is wrong. Every capped run of the night used nearly one tool call a request, most of them reads and searches of `builder.py`, which is 1,286 lines.

2026-09-19, v0.15's own builds, and the case is now beyond argument. Not one of its capped runs was capped by the work: 20260918T223356Z at 60 requests on a goal the attended agent then cut in two; 20260918T224905Z at 59 requests, reaching a green check of 224 tests before it ran out; 20260918T231137Z on the tool calls rather than the requests, at 3 lists, 23 reads and 33 searches against 6 edits; and 20260919T000504Z on a goal that was one small function, at 27 reads and 29 searches for six edits. What the budget is spent on is not the work but the looking, in a program of 1,344 lines with a suite of 225 beside it. Seven caps of eleven runs by the version's end, four of them cut off with the check green and the whole change made, and the seven cost 97 cents of the version's 123 -- more than three quarters of what the version spent bought nothing. Nothing the spec could do reached them: splitting a goal in two, naming every site, moving the red tests into a file of a hundred and ninety lines, and quoting every line to be removed each left the reads and searches where they were.

Two things the version showed that the Idea did not cover. A run that hits the tool-call cap and one that hits the request cap are both `stopped: cap` with only `detail` telling them apart, so the table cannot say which budget bound a run. And the caps are constants of the program, so a version cannot be built under different caps by the instance that builds it: an instance pinned at a tag carries that tag's caps, which is right, and means a caps change helps the version after the one that makes it.

2026-09-19, the morning after, three measurements by the attended agent before the spec was written.

The first corrects the note above: `TOOL_CALLS_CAP` has been 80 since 803fca5, the v0.3 commit, and never 40; the 18th's reading of it was wrong and git says so. It matters because it makes the second measurement the whole of the problem. **The request cap is below the tool-call cap, sixty against eighty.** Since v0.12 the model calls one tool at a time, so requests and tool calls climb together and the requests run out first, every time, twenty calls before the tool-call cap is reached. The tools already know how to land a run: the write cap and the check cap answer `error: cap reached (...); report now` and the model reports. That landing can never fire for the run as a whole, because the provider budget is gone before the tool budget is touched. Four runs of v0.15 reached a green check and were cut off wanting about five more requests, not fifty more calls.

The second is the checkout itself: 13,044 lines across 142 files the tools can reach, 8,777 of them Python in 28 files. At `READ_LINES_CAP = 300` it costs 44 reads to read the checkout once, and the observed looking is 50 to 55 calls a run -- one pass and a fifth. The caps were set for a checkout perhaps a thirteenth of this one.

The third is what a larger budget would cost, from the store's 181 records. Of 90 build runs, 13 were capped; a capped build costs 13.3 cents against a median of 3.5 for all builds, and the deepest runs cost about a fifth of a cent a request. Of 91 evaluation runs, **none has ever been capped**: the median is 10 requests of the 60 and the median cost is 0.74 cents. So a set of 33 runs costs about 45 cents today and would cost the same at any larger cap, because no case has ever come near one; what rises is the worst case, from about $4.40 to about $13.50, and that is the number the ceiling exists to bound.

## Goal

A run's budget follows the checkout it is given, rather than being a constant of the program. This goal carries the budget; spending it is the next one, so nothing about how a run ends changes here.

`builder.py` gains three constants and one function. `CALLS_FLOOR` is 80, the number `TOOL_CALLS_CAP` has held since v0.3. `CALLS_CEILING` is 200. `PASSES` is 2, the times over the checkout a run is given the calls to read.

`call_budget(root: Path, hidden: tuple[str, ...] = HIDDEN) -> int` answers how many tool calls a run over that checkout is given. It sums the lines of every file the tools can reach under `root`; what it costs to read the checkout once is that sum divided by `READ_LINES_CAP`, rounded up; the budget is that many times `PASSES`, plus `WRITE_CAP` and `CHECK_CAP`, the writes and the checks a run is already allowed. The answer is never below `CALLS_FLOOR` and never above `CALLS_CEILING`, in that order, so the ceiling is the last word.

What the tools can reach is what `list` and `read` would answer with, and nothing else is counted: a name in `hidden` at the root of the checkout, anything with a `.git` component at any depth, a symlink and a directory are all skipped. A file whose bytes are not UTF-8 text, and a file this process cannot read, count nothing and do not stop the count. Nothing is written, and nothing outside `root` is opened.

`Tools` takes a `budget` keyword argument and carries it as `self.budget`. A caller that does not name one gets `call_budget(self.root, self.hidden)`, taken once in the constructor from the tree as it then is; a caller that names one gets that number and the tree is not walked for it. `main` names none, so a run's budget is its checkout's.

Nothing else changes. `TOOL_CALLS_CAP` and `REQUEST_CAP` still bound the run and are still what `run` gives the library.
