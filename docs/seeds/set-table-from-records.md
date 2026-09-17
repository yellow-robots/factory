---
created: 2026-09-17
type: seed
status: open
summary: The set's table is printed once, at the end of a live run, and a record does not say which run of the set it was part of, so a set on file cannot be read again under a new measure without paying for its runs again; the table is derived from the records.
value: 3
effort: S
version:
---

## Evidence

2026-09-17, read in `evals.py` by the attended agent: `main` prints the table and the rate after the last run and nowhere else; `_row` and `_pass_rate` take records, but no entry gives them records on file, and a record of the set says its case, the first line of its goal, and not the run of the set it was part of, which the attended agent tells by the stamps' times. 90 of the 146 records git tracks are the set's. The tables of v0.7's and v0.12's sets are sentences of the version notes and files of the attended agent's scratch. intervals-for-the-rate and capability-and-integrity-apart change how a set is scored, and neither can be shown on a set on file: v0.12's 33 runs again are about 33 cents and 33 minutes, and what they would show is another day's runs and not the ones the note reports.

## Idea

Each run of the set leaves in its record, in a file of the harness's beside `case.txt` of cases-that-do-not-say-what-they-probe, the set it was part of, the stamp of the set's start, and its place in it, the case and the round. `evals.py`, given a set's stamp, prints the table and the rate from the records and runs nothing, by the path the live run prints them by, so the two cannot differ. A change to how the set is scored is then shown on the sets on file before a new run is paid for, and a set's table is no longer kept in a note's prose. The sets already on file carry no such file; whether they are given one by the attended agent, from the stamps, is the spec's.
