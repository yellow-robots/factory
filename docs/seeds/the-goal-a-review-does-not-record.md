---
created: 2026-09-20
type: seed
status: open
summary: A review chops the first line off the goal it was given, so its goal.txt holds a different goal than a build's for the same seed and no longer names the seed it was of.
value: 3
effort: S
reporter: reviewer
kind: quality
version:
---

## Evidence

2026-09-20, and it was found by the factory's own reviewer rather than by a person: run 20260920T124559Z, the first catch-rate measurement, case `reviewer-role`. The finding was reported at `reviewer.py:192` of commit 3e01d73 by two passes of one dimension, and it is not in any review note. **It was not in the answer key because nobody had found it.**

`builder.read_seed` returns the goal as the model gets it: `seed: <name>` as the first line and the `## Goal` text under it. A build gives the model that whole string and writes it to `goal.txt`. `reviewer.py:320` chops the first line off with `goal.split("\n", 1)[1]` and writes what is left at `reviewer.py:372`.

So for the same seed, a build's `goal.txt` and a review's hold different text, and a review's no longer names the seed it was of. Only `numbers.json` still does. The attended agent read exactly this on the catch run's own record -- `case: reviewer-role` and then the Goal's body with no seed line -- and read past it.

`test_reviewer.py:141` asserts the chopped first line, so the suite passes and always has. The reviewer's report says so itself: *the tests pass while the Goal's "the seed's `## Goal`, read the way the builder reads one" is not met.*

It is small and it is live, and what makes it worth a note is where it came from. The catch-rate seed says its answer key is a floor, never a ceiling, because it holds only what somebody already found; this is the first thing found over that floor, on the first run, and it argues the key is a floor by some real margin rather than as a caveat.

## Idea

A review's record says what a build's record says.

The goal a review is given and the goal it writes down are the goal the builder reads, first line and all, so two records of the same seed can be compared without knowing which program made them. The test that asserts the chop is asserting the defect and is amended with the fix, which is stated before the build rather than during it.

Worth pairing with anything else that touches the review record, and not worth a version of its own.
