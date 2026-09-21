---
created: 2026-09-19
type: seed
status: rejected
summary: The budget's walk of the checkout and the tools' own walk are the same policy written twice, so a change to what the tools hide would silently leave the budget counting files the run can no longer read.
value: 3
effort: S
reporter: review
kind: quality
version:
---

Rejected 2026-09-21 by the owner, at 87b2bcb: the budget's walk went with [[the-walk-that-bounds-nothing]] at v0.20, so only `Tools._files` remains and there is no second walk to unify.

## Evidence

2026-09-19, found by the independent reviewer of runs 20260919T064941Z, 20260919T065440Z and 20260919T070052Z, reproduced by the attended agent. `call_budget` walks the checkout to count what a run must read; `Tools._files` walks it to answer `search`. Both skip symlinks, skip anything with a `.git` component at any depth, and apply the hidden names at the root only. The reviewer built a tree with root-level hidden names, a nested `__pycache__` and `.venv`, a nested `.git`, a file that is not UTF-8 and a fifo, and the two walks agreed on every file.

They agree because they were written to the same words, not because they are the same code. The budget's whole claim is that it counts what the tools can reach; the day the two drift, the claim is false and nothing says so.

## Idea

One walk answers what the tools can reach, and both callers ask it. What the budget then counts is the tools' own answer by construction rather than by agreement, and a change to the hidden names moves the budget with it.
