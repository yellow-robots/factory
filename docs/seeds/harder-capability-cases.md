---
created: 2026-09-17
type: seed
status: open
summary: Every green case passed every run of v0.12's set, so the set can show a regression and not an improvement; the reviews already made cases the builder failed, a first test it passed and the tests a review added after.
value: 4
effort: M
version:
---

## Evidence

2026-09-17: v0.12's set passed 33 of 33 runs, the seven cases whose word is `green` 21 of 21. Anthropic's evals guidance, 9 January 2026: "An eval at 100% tracks regressions but provides no signal for improvement" (https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), read by the attended agent on the day. The history holds harder ones with a known failure: the first builds of spread-column, review-as-document, tool-errors-column and held-out-tests, and of built-by-trailer in v0.13, were green on the attended agent's first tests, and a review then added tests those builds failed (analyst-on-api-models).

## Idea

A case per such seed: its world the red commit's parent, as set-world-outside-the-repository exports it; its goal the Goal of the first red commit; its visible test the tests of that commit; its held-out tests the ones the review added. The first build failed them, so the case starts below its ceiling and a builder that does better than the first build shows it.
