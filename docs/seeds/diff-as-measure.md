---
created: 2026-09-16
type: seed
status: open
summary: Green is a floor; the diff says what else changed, and the record already holds the numbers to measure it.
value: 4
effort: S
version:
---

## Evidence

G1's diff was one helper and two call sites, judged minimal by reading it. The record has `files_changed`, `insertions`, `deletions` and `diff.patch`, but no notion of what the goal touched, so "changed only what the goal needs" is unmeasured.

## Idea

First version is arithmetic on the record: files outside the goal's named files, insertions beyond the smallest known patch, deleted lines in a green build. Later, the preservation checks from the design: a symbol and edge map before and after, mutation score on the tests.
