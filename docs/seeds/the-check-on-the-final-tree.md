---
created: 2026-09-17
type: seed
status: done
summary: A record's `check` is the last check the model chose to run, so a change after it would be graded as checked; the builder checks the tree the model leaves, and the record's check is that one.
value: 3
effort: S
version: v0.14
---

## Evidence

2026-09-17, found by the research on eval practice and read in `builder.py` by the attended agent: `check` in `numbers.json` is `checks[-1]`, the model's own last call, and `evals.py` counts a run green and honest by it, with no check of its own after the run but the held-out one; a run that writes after its last check is recorded green on a tree nobody tested. It has not happened: of the 140 records with tool calls, 90 of the set and 50 builds, none wrote or edited successfully after its last check. Anthropic's evals guidance, 9 January 2026, grades the final state of the environment, "what the agent produced, not the path it took" (https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), read by the attended agent on the day.

## Idea

When the model returns, the builder runs the check once more on the tree as it is, unless its last tool call was a check with nothing written after it; the model's checks stay in the record as they are, `check` in the numbers is the last one run, and `checks` counts it. The report's claim is judged against it, so `honest` is honesty about the tree left, in a build as in a run of the set.

## Goal

A record's check is the tree the model left. When the model returns, whatever ended the run, an answer, a cap or an error, the builder runs the check once more on the checkout as it then is, unless nothing was written or edited since the last check the model ran, a write a wall refused being nothing written. A run that changed the checkout and never checked it is checked once; a run that changed nothing is checked not at all, and its `check` is `none` as it is now.

That check is the model's own kind: the same sandbox, numbered after the model's checks and leaving its log beside theirs as `check-<n>.log`, its seconds summed into `check_seconds` with the rest. `checks` in the numbers counts it and `check` is the last check run, so what the record says of the tree is what was tested, and a report's claim is judged against it: `honest` in a build as in a run of the set is honesty about the tree left.

The check the builder runs is its own and not the model's, so the cap of eight checks a run binds the model's and not this one, and a sandbox that cannot run leaves the record as it is rather than losing it. It belongs where the run ends, in `main` after the loop returns and before the record's numbers are written, and what the tools know about what was written since their last check is theirs to keep.

The docstrings and comments of `builder.py` that say a record's check is the model's last call say what is now true. `README.md` and `AGENTS.md` are the attended agent's and are not a build's to write.
