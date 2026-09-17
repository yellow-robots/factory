---
created: 2026-09-17
type: seed
status: building
summary: Tool returns that say `error:` without a wall behind them, an edit whose anchor missed or `list` on a file, are the builder's tool-use lapses; the records hold them and the table does not count them.
value: 4
effort: S
version: v0.11
---

## Evidence

2026-09-17, over the 97 records: 73 tool returns start `error:` and are not a wall's refusal, in 37 runs; `old text not found` 18 times, `not a directory: builder.py` 16, the same on the test files 19 more, `not a file: cases` and its cases 6. The set's second run alone, 45 in 20 of 27 runs. The table counts refusals, the wall's work, and nothing of these, the model's; the owner's tool-use competency, 2026-09-17, is exactly this: the tooling applied correctly in every situation.

## Idea

A column `tool_errors`, the tool returns of a run that start `error:` and are not refusals, at the median over the runs like the other counts, in `evals.py` and in `runs.py` for every record. Later, the kinds apart: an anchor that missed, a path of the wrong kind, a read past the end, a file edited without being read; the first column says whether the count moves between versions.

## Goal

A column `tool_errors` in both tables: a run's tool returns that start `error:` and are not a wall's, neither a refusal `refused` counts, nor a cap reached, `error: cap reached`, nor a check without a sandbox, `error: no sandbox`, read from the record's `messages.json` as `refused` is. In `evals.py` it sits right after `checks` in `COLUMNS` and holds the median over the case's runs, written as the other medians are; a run without messages to read lacks the measure and is left out, and the cell is empty when no run has them. In `runs.py` it sits right after `checks` in `COLUMNS` and holds the count for every record, derived when the table is printed like `input_per_request` and stored nowhere; empty for a record without messages to read. The count is one function's, called by both tables, so they never disagree on a record. The module docstrings of `evals.py` and `runs.py` name the column. From the review: the comment over `MEDIAN_COLUMNS` in `evals.py` says the count is read from `runs.py`, where it is computed, not computed in `evals.py`. The tests in `test_evals.py` and `test_runs.py` whose docstring names this seed define the behaviour.
