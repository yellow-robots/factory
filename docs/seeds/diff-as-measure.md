---
created: 2026-09-16
type: seed
status: done
summary: Green is a floor; the diff says what else changed, and the record already holds the numbers to measure it.
value: 4
effort: S
version: v0.7
---

## Evidence

G1's diff was one helper and two call sites, judged minimal by reading it. The record has `files_changed`, `insertions`, `deletions`, `diff.patch` and, since v0.6, the `written` and `edited` paths, but no notion of what the goal touched, so "changed only what the goal needs" is unmeasured. The set's first run (v0.6) shows `diff_lines` alone: 62 for the rename, 14 for a new module, 2 for a one-line change.

## Goal

`evals.py` adds, after `diff_lines`, the columns `files_changed`, `deletions` and `stray_files`, each the median over the runs: `files_changed` and `deletions` from the numbers as they are; `stray_files` the count of distinct paths in the run's `written` and `edited` that the goal's text names neither by path nor by basename. A run without those numbers is left out of the median, as elsewhere. Nothing else in the table changes. The tests in `test_evals.py` whose docstring names this seed define the behaviour.

Later, the preservation checks from the design: a symbol and edge map before and after, mutation score on the tests.
