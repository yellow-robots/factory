---
type: seed
status: open
summary: The factory is a checkout with uv and Docker on one host; how it is installed elsewhere and which checkouts it supports is undecided.
value: 2
effort: L
version:
---

## Evidence

Owner's item 5, 2026-09-16. Today's surface, by accident: a git worktree carrying `uv.lock` and `check.Dockerfile`, tests discoverable by unittest, Docker available to the user. A version must be deployable: the artefact and its changelog are the deliverable.

## Idea

Write the checkout contract down only when a second checkout or a second host exists; until then the factory's own repository is the contract by example.
