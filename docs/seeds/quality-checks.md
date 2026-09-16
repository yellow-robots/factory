---
created: 2026-09-16
type: seed
status: open
summary: The check is the test suite and nothing else; a version built the wrong way passes it. Quality checks belong inside check.
value: 3
effort: M
version:
---

## Evidence

Owner's item 1, 2026-09-16. Degradation, building the right way, is one of the two measures in the v1 findings; today the tools measure nothing about how code is written.

## Idea

Deterministic checks the checkout declares and the container runs alongside the tests: lint, types, size and edge limits, clone detection. Which ones, and their order, follows what the failure-mode set shows the tests missing.
