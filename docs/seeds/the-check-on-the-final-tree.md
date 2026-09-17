---
created: 2026-09-17
type: seed
status: open
summary: A record's `check` is the last check the model chose to run, so a change after it would be graded as checked; the builder checks the tree the model leaves, and the record's check is that one.
value: 3
effort: S
version:
---

## Evidence

2026-09-17, found by the research on eval practice and read in `builder.py` by the attended agent: `check` in `numbers.json` is `checks[-1]`, the model's own last call, and `evals.py` counts a run green and honest by it, with no check of its own after the run but the held-out one; a run that writes after its last check is recorded green on a tree nobody tested. It has not happened: of the 140 records with tool calls, 90 of the set and 50 builds, none wrote or edited successfully after its last check. Anthropic's evals guidance, 9 January 2026, grades the final state of the environment, "what the agent produced, not the path it took" (https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), read by the attended agent on the day.

## Idea

When the model returns, the builder runs the check once more on the tree as it is, unless its last tool call was a check with nothing written after it; the model's checks stay in the record as they are, `check` in the numbers is the last one run, and `checks` counts it. The report's claim is judged against it, so `honest` is honesty about the tree left, in a build as in a run of the set.
