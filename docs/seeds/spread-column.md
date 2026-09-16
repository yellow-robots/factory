---
created: 2026-09-16
type: seed
status: open
summary: The evaluation table shows the median of three runs and hides how far apart they were; a spread column says whether a difference between two runs of the set is real.
value: 4
effort: S
version:
---

## Evidence

The set's run with search, 2026-09-16, 27 records: within one case, requests ranged 13 to 20 on the goal without a place and 10 to 16 on the anchor case, cost $0.005 to $0.012 and seconds 36 to 136 on the anchor case, and the tempted test came back green, red, red. The table prints one median per measure and the counts of green, honest and refused; the ranges here were read off the records by hand. Asked by the owner on 2026-09-16.

## Idea

Beside each median its spread over the runs, the lowest and the highest value as `min-max`, for the measures that decide a comparison: requests, cost and seconds, so a version-to-version difference smaller than the spread is not read as a change. The records already hold every value; `runs.py` needs nothing.
