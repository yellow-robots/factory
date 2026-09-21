---
created: 2026-09-16
type: seed
status: open
summary: Can an affordable API model turn a seed into a spec and its red tests, so the attended agent moves up to deciding with the owner?
value: 5
effort: M
reporter: owner
kind: autonomy
version:
---

## Evidence

Owner's item 6, 2026-09-16. Frontier models come only through subscription harnesses; the API budget allows DeepSeek and its peers. Today the attended agent writes every spec and every test.

2026-09-17, derived from git and the records at e1cdf67, the material a replay has: seven done seeds were born open, got their Goal and their red tests in one commit, and were built by the factory from the seed's path, v0.8 to v0.12. The red commit's parent is the checkout the attended agent wrote the spec in, holding the seed's Evidence and Idea and no Goal.

| seed | version | world | red | tests at red | tests now | builds | first build's check |
|---|---|---|---|---|---|---|---|
| one-goal-reader | v0.8 | 6102e51 | 8cbdca2 | 1 | 1 | 1 | green |
| spread-column | v0.9 | 71e2929 | 0ffb40d | 2 | 4 | 2 | green |
| review-as-document | v0.10 | b2a94fa | d4b2da5 | 5 | 7 | 2 | green |
| tool-errors-column | v0.11 | 32b12e2 | 0346b02 | 5 | 6 | 2 | green |
| pass-rate-error | v0.11 | 0b98480 | db099b6 | 6 | 9 | 3 | red |
| standard-error-of-the-rate | v0.12 | 0dec1f7 | e4d496c | 3 | 3 | 1 | green |
| held-out-tests | v0.12 | d90974d | 8e43430 | 4 | 6 | 2 | green |

Five of the seven took a second red commit after a review, tests for defects the first ones let through: the first builds of four were green on the attended agent's tests, and the first build of pass-rate-error was red on two older tests of `test_evals.py`, not on the seed's. The thirteen builds cost $0.436, a median of 3 cents. Before v0.8 the Goal and the red tests landed in separate commits, tool-calls-one-at-a-time and record-hardening were born with their Goal, and stale-docstring-case was the attended agent's cases with no build, so no other done seed has a world holding the idea alone, a red commit holding both and a build after it.

## Idea

An eval before a role, as a replay over the seven. The analyst is given the world, exported from its commit outside the repository with no `.git` and no `runs/`, so nothing after it and no record is on disk for the tools or for code `check` runs, and the seed's path; it reads with the builder's read-only tools, writes and edits only `test_*.py` at the root, the builder's wall turned around, runs `check`, and returns the Goal as its typed output, which the harness writes into the note; the Evidence and the Idea are not the analyst's to change. Each spec is graded by git against what happened after it:

- whole: the gate's check passes with the Goal and a test naming the seed;
- red for its reason: every test naming the seed fails on the analyst's commit, and every test it neither added nor changed is as green as in the world;
- the build accepted: the tests naming the seed pass with the non-test files of the seed's last build, a failure from a name or a signature counted apart from an assertion's;
- the defects caught: for the five with a follow-up, the tests naming the seed fail by an assertion on the non-test files of the first build; the attended agent's first tests caught none of these, since the builds they judged were green, so here an analyst can do better than the reference;
- built, when the first four hold: the builder given the analyst's spec, and the attended agent's final tests run on what it built.

Two references are graded beside the analyst on every grade: the attended agent's own spec, the red commit, and a spec that does nothing, the Idea as the Goal and no test, so a grade is read between the two. Attempts per seed are set by a power analysis before the replay, and the grades carry intervals from each seed's Beta posterior quantiles, not a standard error beside a proportion, as the research on eval practice of 2026-09-17 found. At a build's median cost, seven seeds three times each is about 65 cents before the builds of the last grade. 2026-09-17, after the owner's direction that the factory works as a deployment: as a step of the loop the analyst's input is a seed at open on a pushed branch and its output a commit on that branch holding the Goal and the red tests, the request build-from-a-pushed-branch answers.
